"""core/formation_engine.py — Onda 5 (Fase 2): Matrizes/Formações 阵法.

The system that turns the Fase 1 exploration loot into USABLE POWER. A
Formação is a craftable timed consumable (vision §4: "como pílulas — ativas
como consumível"): craft consumes herbs/ores/stones (the materials exploration
and the dungeons already drop — a REAL sink, Lei §3, NEVER jade, Lei §4) and
grants a row in ``player_formations``; activation "on the body" creates a
plain ``PlayerBuff`` row — NO parallel buff system (Lei §3) — so the existing
consumers (combat fighter build, cultivation tick, Dao meditation,
tribulation) apply 4 of the 6 effect types with ZERO new code. The two new
wire-ins live in ``core/exploration_engine.py``: ``perception_boost`` raises
Divine Sense clarity and ``explore_protection`` reduces the death-loss.

Activation "in the cavern" (the OTHER choice — Lei §1 clear disclosure) is
``core/cavern_engine.py``'s job; this engine only validates + debits the pouch.

Anti-stack rule: activation REFUSES while a buff of the same ``effect_type``
is already active (the convenience-shop precedent, ``_apply_shop_effect``) —
deliberately NOT the pill extend-and-max path, which would let a cheap 1.10×
Formação extend a divine 1.3× pill's clock (value leak) and would make a
network-retry double-spend invisible. Refusing is the idempotency marker:
a double-tap/retry gets a disclosed ``already_active`` no-op.

Concurrency: every WRITE here assumes the CALLER holds the ``player`` row FOR
UPDATE and owns the commit (the ``claim_bounty`` / ``do_travel`` pattern); the
pouch row is additionally locked FOR UPDATE in this engine.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from database.models import (
    FormationCatalog,
    HerbCatalog,
    OreCatalog,
    PlayerBuff,
    PlayerFormation,
    PlayerInventory,
    PlayerOre,
)

logger = logging.getLogger(__name__)

# Cap on the death-loss protection an explore_protection buff may grant —
# whatever the catalog says, the engine never lets the 90% loss drop below
# 90%·(1-cap) (safety rail against future seed typos).
EXPLORE_PROTECTION_CAP = float(os.getenv("EXPLORE_PROTECTION_CAP", "0.75"))

# The cavern slot accepts ONLY the cultivation-natured effects (Lei §1: the
# choice body-vs-cavern is real — combat/exploration Formações make no sense
# humming in an empty cave and are body-only).
CAVERN_EFFECT_TYPES = ("qi_regen_boost", "dao_fragment_chance")

# Pill×Formação coexistence ([jogador], 2026-06-11): the anti-stack refusal made
# the qi-regen Matriz and the qi-regen pills mutually exclusive — but for
# qi_regen_boost the cultivation tick ALREADY aggregates multiple rows with
# diminishing returns (D-2: top-3 by value × factors [1.0, 0.5, 0.25]), so the
# coexistence machinery predates the Formações. For the types listed here a
# PILL row and a FORMATION row coexist as SEPARATE PlayerBuff rows (the tick
# governs the combined value; meditating inside a qi formation while on a pill
# is peak Wuxia — Lei §2). The refusal still fires formation-vs-formation (the
# double-tap idempotency marker) and for every OTHER effect_type (no
# combat-stat stacking pre-wipe). ``_create_or_extend_buff`` never merges into
# a formation row, so the cheap-extends-expensive clock leak stays closed in
# BOTH directions.
FORMATION_PILL_COEXIST_TYPES = ("qi_regen_boost",)


# ── 印记 Marca do Traçado (Mig 138, flag `marca_do_tracado`) ───────────────────
# O report do [jogador] pedia a formação TATUADA no corpo depois de mil usos. O
# [jogador] vetou o mecanismo com razão — ativar cria um `PlayerBuff` com
# `expires_at`, e permanência = buff que nunca expira = sink morto + renda
# passiva (P2W pela porta dos fundos). O que fica é o instinto dele, que é Wuxia
# puro: *o corpo lembra as curvas*. Repetição não vira POSSE, vira MAESTRIA.
#
# Três propriedades fazem isto passar em todas as leis:
#   (a) é POR FORMAÇÃO ⇒ trocar custa a maestria acumulada — a preocupação do
#       [jogador] ("e se eu quiser usar outra?") vira o dilema interessante;
#   (b) o teto é DURAÇÃO e CUSTO, nunca POTÊNCIA — o número do buff não sobe,
#       logo nada disto toca no combate (Lei §3);
#   (c) o 3º degrau é título COSMÉTICO — a Lei §4 fechada em 04/08 fica fechada.
# Só contam ativações NO CORPO: a caverna é a OUTRA escolha e tem de doer.
MARCA_TIERS: tuple[tuple[int, int, str], ...] = (
    (1, 50,   "traco"),   # 印  Traço  — +duração
    (2, 200,  "sulco"),   # 沟  Sulco  — desconto no craft
    (3, 1000, "marca"),   # 印记 Marca — título cosmético
)
MARCA_DURATION_BONUS = 0.15   # degrau 1 — +15% na duração DESSA formação
MARCA_STONE_DISCOUNT = 0.20   # degrau 2 — -20% nas pedras do craft DELA
MARCA_MATERIAL_CUT = 1        # degrau 2 — -1 unidade na linha de material principal (mínimo 1)
MARCA_TITLE = "🔯 Marca do Traçado"


def marca_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (padrão `regionais_on`). Fail-safe → False, e com
    False TUDO nesta secção é no-op: nenhuma contagem, nenhum bônus, nenhuma
    key no payload. `main` fica byte-idêntica."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("marca_do_tracado", world_key))
    except Exception:
        return False


def marca_tier(body_uses: int) -> int:
    """0..3 — o degrau alcançado por ESTA formação. Puro."""
    tier = 0
    for lvl, need, _key in MARCA_TIERS:
        if int(body_uses or 0) >= need:
            tier = lvl
    return tier


def marca_next(body_uses: int) -> tuple[int, int] | None:
    """(degrau seguinte, ativações que faltam) — None no topo. Puro."""
    for lvl, need, _key in MARCA_TIERS:
        if int(body_uses or 0) < need:
            return lvl, need - int(body_uses or 0)
    return None


def marca_view(body_uses: int, lang: str = "pt") -> dict | None:
    """A vitrine da maestria, server-resolved — a MESMA linha nas 2 superfícies.

    Lei §10: existe desde a PRIMEIRA ativação ("印 Marca do Traçado · 1/50"),
    nunca é um número secreto que só aparece ao chegar ao fim. Devolve None
    quando não há nada a mostrar (0 ativações) — nunca levanta."""
    try:
        # A conversão fica DENTRO do try: a docstring promete que isto nunca
        # levanta, e `list_formations` é chokepoint quente — um valor
        # inesperado não pode derrubar a lista inteira de Formações.
        uses = int(body_uses or 0)
        if uses <= 0:
            return None
        from core.i18n import t as i18n_t
        tier = marca_tier(uses)
        nxt = marca_next(uses)
        out: dict[str, Any] = {
            "uses": uses,
            "tier": tier,
            "tier_key": MARCA_TIERS[tier - 1][2] if tier > 0 else None,
            "tier_name": i18n_t(lang, f"marca_tier_{MARCA_TIERS[tier - 1][2]}") if tier > 0 else None,
            "next_tier": nxt[0] if nxt else None,
            "next_at": MARCA_TIERS[nxt[0] - 1][1] if nxt else None,
            "remaining": nxt[1] if nxt else 0,
            # display == roll: os números anunciados são os que o engine aplica.
            "duration_bonus_pct": int(round(MARCA_DURATION_BONUS * 100)) if tier >= 1 else 0,
            "stone_discount_pct": int(round(MARCA_STONE_DISCOUNT * 100)) if tier >= 2 else 0,
            "material_cut": MARCA_MATERIAL_CUT if tier >= 2 else 0,
        }
        out["line"] = (
            i18n_t(lang, "marca_line_progress", uses=uses, next=out["next_at"])
            if nxt else i18n_t(lang, "marca_line_max", uses=uses)
        )
        return out
    except Exception:
        logger.debug("marca_view failed", exc_info=True)
        return None


def marca_duration_minutes(base_minutes: int, body_uses: int) -> int:
    """A duração DEPOIS da maestria (degrau 1+). Sempre >= a base — a maestria
    nunca pode encurtar nada. Puro e usado pelo activate E pela vitrine (o
    jogador lê o número que vai receber, não o de catálogo)."""
    base = max(1, int(base_minutes or 60))
    if marca_tier(body_uses) < 1:
        return base
    return max(base, int(base * (1.0 + MARCA_DURATION_BONUS)))


def marca_discount_recipe(r_stones: int, r_herbs: list, r_ores: list,
                          body_uses: int) -> tuple[int, list, list]:
    """O custo DEPOIS da maestria (degrau 2+): -20% nas pedras e -1 unidade na
    linha de material de MAIOR quantidade, com mínimo 1.

    Bounded de propósito: nunca zera uma linha, nunca toca em mais do que uma
    linha, e as pedras nunca ficam negativas — é desconto no sink, **não** a
    remoção dele (o craft continua a custar, sempre). Devolve CÓPIAS: o caller
    entrega-as ao `debit_materials`, que fica intocado (e portanto o
    `cavern_establish`, que o partilha, também).
    """
    herbs = [dict(m) for m in (r_herbs or [])]
    ores = [dict(m) for m in (r_ores or [])]
    stones = max(0, int(r_stones or 0))
    if marca_tier(body_uses) < 2:
        return stones, herbs, ores

    stones = max(0, int(stones * (1.0 - MARCA_STONE_DISCOUNT)))
    # A linha "principal" = a de maior quantidade; empate resolve-se pela ordem
    # da receita (determinístico — o preview e o débito têm de concordar).
    best = None
    for bucket in (herbs, ores):
        for m in bucket:
            if int(m.get("qty", 0) or 0) <= 1:
                continue
            if best is None or int(m["qty"]) > int(best["qty"]):
                best = m
    if best is not None:
        best["qty"] = max(1, int(best["qty"]) - MARCA_MATERIAL_CUT)
    return stones, herbs, ores


async def _marca_uses(session, player_id: int, formation_id: int) -> int:
    """Ativações no corpo desta formação. 0 com a flag OFF (sem sequer ler a
    coluna) e 0 em qualquer falha — a maestria nunca pode partir a Formação."""
    if not marca_on():
        return 0
    try:
        row = (await session.execute(
            select(PlayerFormation).where(
                PlayerFormation.player_id == int(player_id),
                PlayerFormation.formation_id == int(formation_id),
            )
        )).scalar_one_or_none()
        return int(getattr(row, "body_uses", 0) or 0) if row is not None else 0
    except Exception:
        logger.debug("marca uses read failed", exc_info=True)
        return 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_cavern_effect(effect_type: str) -> bool:
    return effect_type in CAVERN_EFFECT_TYPES


# ── Catalog / pouch reads ──────────────────────────────────────────────────────

async def _load_catalog(session) -> list:
    return list((await session.execute(
        select(FormationCatalog).order_by(FormationCatalog.tier, FormationCatalog.id)
    )).scalars().all())


async def get_formation(session, formation_id: int):
    return (await session.execute(
        select(FormationCatalog).where(FormationCatalog.id == int(formation_id))
    )).scalar_one_or_none()


async def _owned_map(session, player_id: int) -> dict:
    rows = (await session.execute(
        select(PlayerFormation).where(PlayerFormation.player_id == int(player_id))
    )).scalars().all()
    return {r.formation_id: int(r.qty or 0) for r in rows if int(r.qty or 0) > 0}


async def _material_names(session, herb_ids: list, ore_ids: list) -> tuple[dict, dict]:
    herbs, ores = {}, {}
    if herb_ids:
        for h in (await session.execute(
            select(HerbCatalog).where(HerbCatalog.id.in_(herb_ids))
        )).scalars().all():
            herbs[h.id] = f"{h.emoji} {h.name}".strip()
    if ore_ids:
        for o in (await session.execute(
            select(OreCatalog).where(OreCatalog.id.in_(ore_ids))
        )).scalars().all():
            ores[o.id] = f"{o.emoji} {o.name}".strip()
    return herbs, ores


async def _owned_materials(session, player_id: int, herb_ids: list, ore_ids: list) -> tuple[dict, dict]:
    """{herb_id: owned_qty}, {ore_id: owned_qty} for the recipe's materials."""
    herbs, ores = {}, {}
    if herb_ids:
        rows = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == int(player_id),
                PlayerInventory.item_type == "herb",
                PlayerInventory.item_id.in_(herb_ids),
            )
        )).scalars().all()
        for r in rows:
            herbs[r.item_id] = herbs.get(r.item_id, 0) + int(r.quantity or 0)
    if ore_ids:
        rows = (await session.execute(
            select(PlayerOre).where(
                PlayerOre.player_id == int(player_id),
                PlayerOre.ore_id.in_(ore_ids),
            )
        )).scalars().all()
        for r in rows:
            ores[r.ore_id] = ores.get(r.ore_id, 0) + int(r.quantity or 0)
    return herbs, ores


def _recipe_parts(recipe: dict) -> tuple[int, list, list]:
    recipe = recipe or {}
    stones = int(recipe.get("stones", 0) or 0)
    herbs = [m for m in (recipe.get("herbs") or []) if int(m.get("qty", 0) or 0) > 0]
    ores = [m for m in (recipe.get("ores") or []) if int(m.get("qty", 0) or 0) > 0]
    return stones, herbs, ores


async def list_formations(session, player, *, lang: str = "pt") -> dict:
    """READ — the full Formation surface: catalog + recipe (with the player's
    owned counts per material — Lei §1 full disclosure) + pouch + active buffs
    of formation-relevant types. No state change."""
    catalog = await _load_catalog(session)
    owned = await _owned_map(session, player.telegram_id)
    # 印记 — a maestria de TODAS as formações numa leitura só (a lista é um
    # chokepoint quente: nada de N queries). Dicionário vazio com a flag OFF.
    marca_uses_map: dict[int, int] = {}
    if marca_on():
        try:
            for r in (await session.execute(
                select(PlayerFormation).where(
                    PlayerFormation.player_id == player.telegram_id)
            )).scalars().all():
                marca_uses_map[int(r.formation_id)] = int(getattr(r, "body_uses", 0) or 0)
        except Exception:
            logger.debug("marca map read failed", exc_info=True)

    herb_ids = sorted({m["herb_id"] for f in catalog for m in _recipe_parts(f.recipe)[1]})
    ore_ids = sorted({m["ore_id"] for f in catalog for m in _recipe_parts(f.recipe)[2]})
    herb_names, ore_names = await _material_names(session, herb_ids, ore_ids)
    have_herbs, have_ores = await _owned_materials(session, player.telegram_id, herb_ids, ore_ids)

    from core.alchemy_engine import get_active_buffs
    active = await get_active_buffs(session, player.telegram_id)
    active_by_type = {}
    for b in active:
        # The ✨ effect_active chip must mean what the activation gate means:
        # for coexist types a PILL row no longer blocks activation, so it must
        # not mark the catalog card as active either (adversarial-review
        # finding — a pill-only row implied "Matriz already humming").
        if (b.buff_type in FORMATION_PILL_COEXIST_TYPES
                and not (b.source or "").startswith("formation:")):
            continue
        cur = active_by_type.get(b.buff_type)
        if cur is None or b.expires_at > cur["expires_at_dt"]:
            active_by_type[b.buff_type] = {
                "value": float(b.buff_value or 1.0),
                "source": b.source,
                "expires_at_dt": b.expires_at,
            }

    stones = int(player.spirit_stones or 0)
    realm = int(player.realm or 0)
    now = _now()
    items = []
    for f in catalog:
        r_stones, r_herbs, r_ores = _recipe_parts(f.recipe)
        # 印记 — o custo mostrado é o custo COBRADO (display == roll). O Sulco
        # desconta antes de tudo, e o `craftable` é avaliado contra o preço
        # descontado — senão o botão ficaria cinzento num craft que passaria.
        _m_uses = marca_uses_map.get(int(f.id), 0)
        _full_stones = r_stones
        r_stones, r_herbs, r_ores = marca_discount_recipe(r_stones, r_herbs, r_ores, _m_uses)
        mats = []
        craftable = stones >= r_stones and realm >= int(f.min_realm or 0)
        for m in r_herbs:
            hid, qty = int(m["herb_id"]), int(m["qty"])
            have = int(have_herbs.get(hid, 0))
            mats.append({"kind": "herb", "id": hid, "name": herb_names.get(hid, f"Herb #{hid}"),
                         "qty": qty, "owned": have, "has_enough": have >= qty})
            craftable = craftable and have >= qty
        for m in r_ores:
            oid, qty = int(m["ore_id"]), int(m["qty"])
            have = int(have_ores.get(oid, 0))
            mats.append({"kind": "ore", "id": oid, "name": ore_names.get(oid, f"Ore #{oid}"),
                         "qty": qty, "owned": have, "has_enough": have >= qty})
            craftable = craftable and have >= qty
        act = active_by_type.get(f.effect_type)
        _marca = marca_view(_m_uses, lang) if _m_uses > 0 else None
        items.append({
            "id": int(f.id),
            "key": f.key,
            "emoji": f.emoji,
            "name_key": f"formation_name_{f.key}",
            "desc_key": f"formation_desc_{f.key}",
            "effect_type": f.effect_type,
            "effect_key": f"formation_effect_{f.effect_type}",
            "effect_value": float(f.effect_value or 1.0),
            # A duração que ESTE cultivador vai receber NO CORPO (o Traço já
            # embutido) — o cartão nunca promete o número de catálogo e
            # entrega outro. Com a flag OFF isto é exatamente o valor de
            # catálogo, logo a forma do payload não muda.
            "duration_minutes": marca_duration_minutes(int(f.duration_minutes or 60), _m_uses),
            "tier": int(f.tier or 1),
            "min_realm": int(f.min_realm or 0),
            "realm_ok": realm >= int(f.min_realm or 0),
            "cost_stones": r_stones,
            "materials": mats,
            "owned": int(owned.get(f.id, 0)),
            "craftable": craftable,
            "cavern_compatible": is_cavern_effect(f.effect_type),
            "effect_active": bool(act),
            "effect_remaining_ms": (
                max(0, int((act["expires_at_dt"] - now).total_seconds() * 1000)) if act else 0
            ),
            # Keys CONDICIONAIS — com a flag OFF (ou zero ativações) o payload
            # sai exatamente como saía ontem.
            **({"marca": _marca} if _marca else {}),
            **({"cost_stones_full": _full_stones} if _full_stones > r_stones else {}),
            # A duração de CATÁLOGO, emitida só quando o Traço a esticou: a
            # caverna NÃO recebe o bônus (é a outra escolha), e sem este número
            # o seletor mostraria a duração do corpo ao lado do botão da
            # caverna — display-lie no ramo errado.
            **({"base_duration_minutes": int(f.duration_minutes or 60)}
               if marca_duration_minutes(int(f.duration_minutes or 60), _m_uses)
               > int(f.duration_minutes or 60) else {}),
        })
    return {"ok": True, "formations": items, "stones": stones, "realm": realm}


# ── Material debit (shared with cavern establish) ──────────────────────────────

async def debit_materials(session, player_id: int, r_herbs: list, r_ores: list) -> bool:
    """Row-locked, STRICTLY all-or-nothing debit of a recipe's herbs
    (PlayerInventory — the alchemy consume pattern) and ores (PlayerOre — the
    forge consume pattern). Two phases: (1) lock EVERY material row FOR UPDATE
    and validate the totals, (2) mutate. A False return mutated NOTHING — this
    matters because the endpoint convention commits even ``{"ok": False}``
    results (disclosed no-ops must stay no-ops). The lock held from phase 1
    makes the check→debit window race-free."""
    # Aggregate duplicate material lines FIRST (a future seed edit listing the
    # same id twice must not under-charge / drive a row negative — the two
    # phases below assume one entry per id).
    herb_need: dict[int, int] = {}
    for m in r_herbs:
        herb_need[int(m["herb_id"])] = herb_need.get(int(m["herb_id"]), 0) + int(m["qty"])
    ore_need: dict[int, int] = {}
    for m in r_ores:
        ore_need[int(m["ore_id"])] = ore_need.get(int(m["ore_id"]), 0) + int(m["qty"])

    herb_rows: list[tuple[list, int]] = []
    for hid, qty in herb_need.items():
        rows = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == int(player_id),
                PlayerInventory.item_type == "herb",
                PlayerInventory.item_id == hid,
            ).with_for_update()
        )).scalars().all()
        if sum(int(r.quantity or 0) for r in rows) < qty:
            return False
        herb_rows.append((rows, qty))
    ore_rows: list[tuple[object, int]] = []
    for oid, qty in ore_need.items():
        row = (await session.execute(
            select(PlayerOre).where(
                PlayerOre.player_id == int(player_id),
                PlayerOre.ore_id == oid,
            ).with_for_update()
        )).scalar_one_or_none()
        if row is None or int(row.quantity or 0) < qty:
            return False
        ore_rows.append((row, qty))

    for rows, qty in herb_rows:
        remaining = qty
        for row in rows:
            take = min(remaining, int(row.quantity or 0))
            row.quantity = int(row.quantity or 0) - take
            remaining -= take
            if row.quantity <= 0:
                await session.delete(row)
            if remaining <= 0:
                break
    for row, qty in ore_rows:
        row.quantity = int(row.quantity or 0) - qty
        if row.quantity <= 0:
            await session.delete(row)
    return True


# ── WRITE — craft ──────────────────────────────────────────────────────────────

async def craft_formation(session, player, formation_id: int) -> dict:
    """WRITE — craft ONE Formação: validates realm + materials + stones, debits
    everything, grants +1 to the pouch. The CALLER holds ``player`` FOR UPDATE
    and owns the commit, so the stone debit can't lost-update; the pouch row is
    locked here. Idempotent in the practical sense: each call is one explicit
    spend — insufficient anything is a disclosed no-op."""
    f = await get_formation(session, formation_id)
    if f is None:
        return {"ok": False, "reason": "formation_not_found"}
    if int(player.realm or 0) < int(f.min_realm or 0):
        return {"ok": False, "reason": "realm_too_low", "min_realm": int(f.min_realm or 0)}

    r_stones, r_herbs, r_ores = _recipe_parts(f.recipe)
    # 印记 degrau 2 — o desconto do Sulco. Aplicado ANTES do gate de pedras e do
    # débito: o preview (`list_formations`) mostra exatamente estes números, e
    # cobrar o cheio depois de anunciar o descontado seria display-lie.
    marca_uses = await _marca_uses(session, player.telegram_id, f.id)
    full_stones = r_stones
    r_stones, r_herbs, r_ores = marca_discount_recipe(r_stones, r_herbs, r_ores, marca_uses)
    if int(player.spirit_stones or 0) < r_stones:
        return {"ok": False, "reason": "not_enough_stones", "cost_stones": r_stones,
                "stones": int(player.spirit_stones or 0)}

    if not await debit_materials(session, player.telegram_id, r_herbs, r_ores):
        return {"ok": False, "reason": "not_enough_materials"}
    # Debit — stones on the caller-locked Player instance (travel pattern).
    player.spirit_stones = int(player.spirit_stones or 0) - r_stones

    # Grant — +1 pouch (row-locked upsert).
    pouch = (await session.execute(
        select(PlayerFormation).where(
            PlayerFormation.player_id == player.telegram_id,
            PlayerFormation.formation_id == f.id,
        ).with_for_update()
    )).scalar_one_or_none()
    if pouch is None:
        pouch = PlayerFormation(player_id=player.telegram_id, formation_id=f.id, qty=1)
        session.add(pouch)
    else:
        pouch.qty = int(pouch.qty or 0) + 1

    out = {"ok": True, "crafted": True, "formation_id": int(f.id), "key": f.key,
           "owned": int(pouch.qty), "stones": int(player.spirit_stones or 0)}
    # Key CONDICIONAL (OFF-identity do payload): só existe quando o Sulco
    # poupou mesmo alguma coisa — e diz QUANTO (Lei §10, custo dito).
    if full_stones > r_stones:
        out["marca_saved_stones"] = int(full_stones - r_stones)
    return out


# ── WRITE — activate "on the body" ─────────────────────────────────────────────

async def _consume_one(session, player_id: int, formation_id: int) -> bool:
    """Row-locked −1 on the pouch. False if the player owns none (the
    double-tap / retry guard: the second call finds an empty pouch OR the
    already_active refusal below fires first)."""
    pouch = (await session.execute(
        select(PlayerFormation).where(
            PlayerFormation.player_id == int(player_id),
            PlayerFormation.formation_id == int(formation_id),
        ).with_for_update()
    )).scalar_one_or_none()
    if pouch is None or int(pouch.qty or 0) < 1:
        return False
    pouch.qty = int(pouch.qty or 0) - 1
    # 印记 (Mig 138) — a row do bolso vazio era APAGADA, e com ela iria a
    # maestria: ficar sem stock zerava as 900 ativações acumuladas.
    #
    # São DUAS razões para a manter, e ambas são precisas:
    #   · `body_uses > 0` — não apagar maestria já ganha (vale mesmo que o
    #     mundo desligue a flag depois de a ter tido ligada);
    #   · `marca_on()` — com a flag ON o `_marca_credit` vai escrever nesta row
    #     LOGO A SEGUIR. Apagá-la aqui e recriá-la lá faria um INSERT com a
    #     MESMA chave primária de uma row deletada na mesma transação — o
    #     conflito de identity-map do SQLAlchemy — e isso apanharia justamente
    #     o caso mais comum: a PRIMEIRA ativação de quem só tem uma unidade.
    # Com a flag OFF nenhuma das duas se aplica ⇒ o delete acontece como sempre
    # aconteceu e `main` fica byte-idêntica.
    _keep = int(getattr(pouch, "body_uses", 0) or 0) > 0 or marca_on()
    if pouch.qty <= 0 and not _keep:
        await session.delete(pouch)
    return True


async def activate_on_body(session, player, formation_id: int) -> dict:
    """WRITE — consume 1 Formação and raise its timed buff on the player (a
    plain PlayerBuff row — the existing combat/cultivation/Dao readers and the
    new exploration wire-in all see it). REFUSES while a buff of the same
    effect_type is active (anti-stack + idempotency marker — see module doc).
    Caller holds ``player`` FOR UPDATE and owns the commit."""
    f = await get_formation(session, formation_id)
    if f is None:
        return {"ok": False, "reason": "formation_not_found"}
    if int(player.realm or 0) < int(f.min_realm or 0):
        return {"ok": False, "reason": "realm_too_low", "min_realm": int(f.min_realm or 0)}

    now = _now()
    live_rows = (await session.execute(
        select(PlayerBuff).where(
            PlayerBuff.player_id == player.telegram_id,
            PlayerBuff.buff_type == f.effect_type,
            PlayerBuff.expires_at > now,
        )
    )).scalars().all()
    blocking = None
    for b in live_rows:
        # A PILL row of a coexist type does not block the Formação (the tick's
        # D-2 diminishing stack governs the pair); a formation row always
        # blocks (idempotency marker), as does ANY row of a non-coexist type.
        if (f.effect_type in FORMATION_PILL_COEXIST_TYPES
                and not (b.source or "").startswith("formation:")):
            continue
        blocking = b
        break
    if blocking is not None:
        return {"ok": False, "reason": "already_active",
                "remaining_ms": max(0, int((blocking.expires_at - now).total_seconds() * 1000)),
                "source": blocking.source}

    # 印记 — a maestria ANTES do consumo (o bônus de duração é o que a vitrine
    # já prometia a quem olhou o cartão; ler DEPOIS daria o número errado).
    uses_before = await _marca_uses(session, player.telegram_id, f.id)
    minutes = marca_duration_minutes(int(f.duration_minutes or 60), uses_before)

    if not await _consume_one(session, player.telegram_id, f.id):
        return {"ok": False, "reason": "not_owned"}

    session.add(PlayerBuff(
        player_id=player.telegram_id,
        buff_type=f.effect_type,
        buff_value=float(f.effect_value or 1.0),   # POTÊNCIA nunca sobe (Lei §3)
        source=f"formation:{f.key}",
        expires_at=now + timedelta(minutes=max(1, minutes)),
    ))
    out = {"ok": True, "activated": "body", "formation_id": int(f.id), "key": f.key,
           "effect_type": f.effect_type, "effect_value": float(f.effect_value or 1.0),
           "duration_minutes": int(minutes)}

    # 印记 — a contagem. Só aqui: a caverna é a OUTRA escolha e não conta.
    if marca_on():
        try:
            marca = await _marca_credit(session, player, f, uses_before)
            if marca:
                out["marca"] = marca
        except Exception:
            logger.debug("marca credit failed", exc_info=True)
    return out


async def _marca_credit(session, player, f, uses_before: int) -> dict | None:
    """+1 ativação nesta formação, com o antes→depois DITO (Lei §10) e o
    degrau novo celebrado no momento em que cai.

    A row é RE-LIDA com `FOR UPDATE` porque `_consume_one` pode tê-la apagado
    (bolso vazio SEM marca) — nesse caso a maestria começa do zero e a row é
    recriada com `qty = 0`, que `_owned_map` já filtra. Nunca levanta para o
    caller: uma falha aqui não pode desfazer uma ativação que já aconteceu."""
    row = (await session.execute(
        select(PlayerFormation).where(
            PlayerFormation.player_id == player.telegram_id,
            PlayerFormation.formation_id == int(f.id),
        ).with_for_update()
    )).scalar_one_or_none()
    if row is None:
        row = PlayerFormation(player_id=player.telegram_id, formation_id=int(f.id),
                              qty=0, body_uses=0)
        session.add(row)
    before = int(getattr(row, "body_uses", 0) or 0)
    row.body_uses = before + 1

    lang = getattr(player, "language", None) or "pt"
    out: dict[str, Any] = {"before": before, "after": row.body_uses}
    view = marca_view(row.body_uses, lang)
    if view:
        out.update(view)
    tier_before, tier_after = marca_tier(before), marca_tier(row.body_uses)
    if tier_after > tier_before:
        out["tier_up"] = tier_after
        # Degrau 3 — o título. COSMÉTICO (Lei §4, decisão de 04/08): entra em
        # `unlocked_titles` como os do MV-4/MV-6 e não dá bônus nenhum.
        if tier_after >= 3:
            titles = list(getattr(player, "unlocked_titles", None) or [])
            if MARCA_TITLE not in titles:
                titles.append(MARCA_TITLE)
                player.unlocked_titles = titles   # reatribuição → dirty (JSONB)
                out["title_granted"] = MARCA_TITLE
    return out


# ── Exploration wire-in (READ helper used by core/exploration_engine.py) ──────

async def get_exploration_mods(session, player_id: int) -> dict:
    """The two Formação effects exploration consumes (defensive — never raises):
      * ``protection``       0.0..EXPLORE_PROTECTION_CAP — fraction of the
                              death-loss PREVENTED (0.35 → lose 58.5% not 90%).
      * ``perception_mult``  ≥1.0 — Divine Sense clarity (also honors the
                              perception_boost PILLS that already exist — the
                              same buff row, emergent depth, Lei §3).
    """
    mods = {"protection": 0.0, "perception_mult": 1.0}
    try:
        from core.alchemy_engine import get_active_buffs
        buffs = await get_active_buffs(session, int(player_id))
        for b in buffs:
            if b.buff_type == "explore_protection":
                mods["protection"] = max(mods["protection"],
                                         min(EXPLORE_PROTECTION_CAP, float(b.buff_value or 0.0)))
            elif b.buff_type == "perception_boost":
                mods["perception_mult"] = max(mods["perception_mult"], float(b.buff_value or 1.0))
    except Exception:
        logger.exception("get_exploration_mods failed (player=%s)", player_id)
    return mods
