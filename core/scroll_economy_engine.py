"""TEC-2 — Drop Reset + Economia do Pergaminho 秘籍 (Técnicas & Escassez, Onda 2).

O TEC-1 fez da SEITA a fonte primária de artes (a Biblioteca em estantes).
O TEC-2 fecha o outro lado da mesma equação:

    1. AS MASMORRAS PARAM DE SANGRAR. Todo roll aleatório de pergaminho
       (masmorra/varredura/chefe + caçada de NPC) passa por UM multiplicador
       (`SCR_DROP_MULT` 0.15 ⇒ os 4-15% de hoje viram 0.6-2.2%, o default A
       da Q-1 da Constituição) e o marco determinístico da arena estica de
       10 para `SCR_ARENA_WIN_STEP` vitórias. O corte mora na MESMA
       matemática que rola — e a vitrine de drops mostra o número CORTADO
       (lição MV-6: display = roll, nunca dois números).

    2. O PERGAMINHO GANHA DESTINO. Além de aprender/absorver/descartar, ele
       passa a poder ser:
         · 📚 DOADO à Biblioteca da casa  → contribuição (o elo TEC-1↔TEC-2:
           o grind de masmorra vira mérito de seita).
         · 🔥 QUEIMADO no Ritual de Compreensão → XP de INTENÇÃO no caminho
           da própria arte (a intenção que ela carrega), + fragmento de Dao
           no topo da escada.

Régua de escassez (Constituição §2, Lei §12): *"No final, tens 8 técnicas.
E cada uma pesa."*

⚠️ LAUNCH-SERVER-BOUND (Lei §5). A flag `escassez_scrolls` fica OFF em TODO
mundo vivo: `main` e `s2` seguem byte-idênticos. O corte é RETROATIVAMENTE
INJUSTO num mundo cuja economia já rodou — o recon de 2026-07-27 encontrou
3.806.905 pergaminhos no main (224 jogadores; um só com 1.885.238) e 17.838
no s2. Ligar a doação nesses mundos sem compensação seria uma impressora de
mérito; é por isso que existe o teto diário abaixo.

Decisões de recon que corrigiram o spec (documentadas em Sessions/2026-07-27):
  · "Dao XP" NÃO EXISTE no código (grep exaustivo). O jogo inteiro tem 159
    fragmentos supremos e o Dao só destranca no Reino 5 — 100 "Dao XP" por
    pergaminho era 63% de todo o Dao do jogo, e um sink R5+ seria beco sem
    saída para o early game inteiro do servidor de launch. A queima passa a
    dar **XP de Intenção** (`core/intent_engine.award_intent_xp`, o mutador
    único, disponível desde o Reino 0, com a rodada de rank antes→depois de
    graça) no caminho que a PRÓPRIA arte carrega (`intent_affinity`), e o
    fragmento de Dao fica como o floreio do topo (T4, R5+, knob).
  · A doação credita **SÓ O SALDO**, nunca `sect_contribution_earned` (a
    escada de posto). Motivo duro, REGRA SUPREMA (Lei §4): Celestial Pass,
    Battle Pass e a troca de fragmentos entregam pergaminhos — se pergaminho
    virasse escada, JADE COMPRARIA POSTO E ARTE. Com saldo-only o jade
    compra, no máximo, poder de compra dentro da casa; o posto continua a
    ser ganho por FEITOS (quests/tributo). É a mesma verdade do TEC-1
    (`learn_library_technique` também debita só o saldo) e mata de uma vez
    o loop "10 vitórias de arena → pergaminho → posto".
  · `GRADE_UPGRADE_REQS` consome 5/10 pergaminhos DA MESMA técnica — um
    sink vivo que o spec não listou. Com o corte, 10 duplicatas de uma arte
    específica viram ~12.000 andares: beco sem saída (Lei §1). Por isso o
    MESMO interruptor divide o custo por `SCR_GRADE_SCROLL_DIV` (5/10 → 1/2).

Padrão do engine = sect_library_engine (TEC-1) / profession_engine (MV-7):
`escassez_on()` fail-safe, OFF ⇒ zero queries em toda função pública, knobs
env `SCR_*` com defaults assados (Lei §6/§13), teste isolado COMMITTED em
scripts/_test_tec2_scrolls.py.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from database.models import PlayerInventory, TechniqueCatalog

# 名 2026-09-14 — o nome da arte vem do dono unico (`core/i18n.py`), nunca cru.
from core.i18n import catalog_name, catalog_art_key

logger = logging.getLogger(__name__)


# ── Flag gate (padrão biblioteca_on — fail-safe, nunca quebra main) ──────────
def escassez_on(world_key: str | None = None) -> bool:
    """Gate estável da flag per-world `escassez_scrolls`. Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("escassez_scrolls", world_key))
    except Exception:
        return False


# ── Knobs (env SCR_*, Lei §13 — defaults assados, Lei §6) ────────────────────
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# O corte (Q-1 default A da Constituição): 0.15 × os 4-15% vivos ≈ 0.6-2.2%.
SCR_DROP_MULT = _env_float("SCR_DROP_MULT", 0.15)
# O marco determinístico da arena (hoje 1 pergaminho a cada 10 vitórias).
SCR_ARENA_WIN_STEP = _env_int("SCR_ARENA_WIN_STEP", 50)
# Divisor do custo em pergaminhos do refino de grau (5/10 → 1/2). 1 = sem corte.
SCR_GRADE_SCROLL_DIV = _env_int("SCR_GRADE_SCROLL_DIV", 5)
# Teto da recompensa GARANTIDA de pergaminho das quests (as de masmorra são
# repetíveis por cooldown e dão 1-3 — seriam a fonte dominante pós-corte).
SCR_QUEST_SCROLL_MAX = _env_int("SCR_QUEST_SCROLL_MAX", 1)
# Contribuição por pergaminho doado, por degrau de raridade.
SCR_DONATE_CP_T1 = _env_int("SCR_DONATE_CP_T1", 25)
SCR_DONATE_CP_T2 = _env_int("SCR_DONATE_CP_T2", 50)
SCR_DONATE_CP_T3 = _env_int("SCR_DONATE_CP_T3", 100)
SCR_DONATE_CP_T4 = _env_int("SCR_DONATE_CP_T4", 200)
# Teto DIÁRIO de contribuição vinda de doação (a trava anti-impressora).
SCR_DONATE_DAILY_CAP = _env_int("SCR_DONATE_DAILY_CAP", 500)
# XP de Intenção por pergaminho queimado, por degrau (curva: rank 0→1 = 100).
SCR_BURN_XP_T1 = _env_int("SCR_BURN_XP_T1", 25)
SCR_BURN_XP_T2 = _env_int("SCR_BURN_XP_T2", 50)
SCR_BURN_XP_T3 = _env_int("SCR_BURN_XP_T3", 100)
SCR_BURN_XP_T4 = _env_int("SCR_BURN_XP_T4", 200)
# Fragmento de Dao no topo da escada (T4 + Reino 5+). 0 desliga.
SCR_BURN_DAO_FRAG_T4 = _env_int("SCR_BURN_DAO_FRAG_T4", 1)
# Quantos pergaminhos uma ação pode consumir de uma vez (rajada de notificação
# de promoção + custo de query; a UI oferece 1 e "tudo" dentro deste teto).
SCR_MAX_BATCH = _env_int("SCR_MAX_BATCH", 20)

# O caminho de intenção padrão quando a arte não carrega nenhum (meditação /
# interior — ids 25-30: são artes de ESSÊNCIA, logo "dao"). Nunca None: um
# botão que não faz nada é beco sem saída (Lei §1).
DEFAULT_BURN_INTENT = "dao"

# Degraus de raridade derivados de `req_realm` — NÃO existe coluna de tier em
# techniques_catalog (recon TEC-2 §0.2; não inventar `tech.tier`). As bandas
# espelham as faixas de QI_COSTS do combat_seeds (comum R0-1 / rara R2-3 /
# lendária R4-5 / apex R6+).
TIER_BANDS: tuple[tuple[int, int], ...] = ((1, 1), (3, 2), (5, 3), (99, 4))


# ── Leitura pura (zero query) — o corte ──────────────────────────────────────
def scroll_drop_mult(world_key: str | None = None) -> float:
    """O multiplicador global do faucet ALEATÓRIO de pergaminho.

    OFF ⇒ 1.0 (identidade exata: `chance * 1.0 == chance`, e nem uma query).
    ON ⇒ `SCR_DROP_MULT`, clampado a [0, 1] — o corte nunca AUMENTA um faucet.
    """
    if not escassez_on(world_key):
        return 1.0
    return max(0.0, min(1.0, SCR_DROP_MULT))


def npc_loot_chance(drop: Any, world_key: str | None = None) -> float:
    """A chance efetiva de uma linha do `NPC_LOOT_TABLE`.

    UM helper para os 3 call sites que rolam a mesma tabela (chat, mini-app e
    o settle assíncrono) — só a linha de `technique_scroll` é cortada; pedras,
    ervas, minérios e pílulas ficam INTOCADOS (o corte é de ARTES, não de
    recompensa de caçada). OFF ⇒ devolve a chance crua.
    """
    try:
        chance = float(drop.get("chance", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        return 0.0
    if drop.get("type") != "technique_scroll":
        return chance
    return chance * scroll_drop_mult(world_key)


def arena_scroll_step(world_key: str | None = None) -> int:
    """De quantas em quantas vitórias a arena entrega um pergaminho.

    O marco da arena é DETERMINÍSTICO (`wins % 10`), logo um multiplicador de
    chance não o toca — recon TEC-2: é o faucet que sobreviveria ao corte e
    faria o loop "vitórias → pergaminho → doação". OFF ⇒ 10 (o valor vivo).
    """
    if not escassez_on(world_key):
        return 10
    return max(1, SCR_ARENA_WIN_STEP)


def grade_scroll_cost(base_cost: int, world_key: str | None = None) -> int:
    """O custo em pergaminhos de um refino de grau, sob escassez.

    Lei §1: com o faucet cortado, juntar 10 duplicatas de UMA arte específica
    é inalcançável — o refino de grau viraria conteúdo morto. O mesmo
    interruptor que corta o faucet divide o custo (`SCR_GRADE_SCROLL_DIV`),
    com piso 1 quando o custo original era ≥1 (nunca vira de graça).
    OFF ⇒ o custo original, byte a byte.
    """
    base = max(0, int(base_cost or 0))
    if base <= 0 or not escassez_on(world_key):
        return base
    div = max(1, SCR_GRADE_SCROLL_DIV)
    return max(1, base // div)


def quest_scroll_qty(base_qty: int, world_key: str | None = None) -> int:
    """Quantos pergaminhos uma recompensa GARANTIDA de quest entrega.

    O corte só toca rolls aleatórios — mas as quests de masmorra são
    REPETÍVEIS por cooldown e entregam 1-3 pergaminhos garantidos (6 seeds).
    Com o faucet aleatório cortado 85%, elas passariam a ser a fonte dominante
    e o §2 da Constituição viraria letra morta (achado do review TEC-2).

    A régua é proporcional, não destrutiva (Lei §1/§4): a quest CONTINUA
    entregando o pergaminho que promete — só não entrega três. Clampa em
    `SCR_QUEST_SCROLL_MAX`. OFF ⇒ a quantidade original, byte a byte.
    """
    base = max(0, int(base_qty or 0))
    if base <= 0 or not escassez_on(world_key):
        return base
    return max(1, min(base, max(1, SCR_QUEST_SCROLL_MAX)))


def scroll_tier(tech: Any) -> int:
    """O degrau de raridade (1-4) de um pergaminho, derivado de `req_realm`."""
    try:
        realm = int(getattr(tech, "req_realm", 0) or 0)
    except (TypeError, ValueError):
        realm = 0
    for ceiling, tier in TIER_BANDS:
        if realm <= ceiling:
            return tier
    return 4


def donate_cp(tier: int) -> int:
    """Contribuição por pergaminho doado, por degrau."""
    return {1: SCR_DONATE_CP_T1, 2: SCR_DONATE_CP_T2,
            3: SCR_DONATE_CP_T3, 4: SCR_DONATE_CP_T4}.get(int(tier or 0), SCR_DONATE_CP_T1)


def burn_xp(tier: int) -> int:
    """XP de Intenção por pergaminho queimado, por degrau."""
    return {1: SCR_BURN_XP_T1, 2: SCR_BURN_XP_T2,
            3: SCR_BURN_XP_T3, 4: SCR_BURN_XP_T4}.get(int(tier or 0), SCR_BURN_XP_T1)


def burn_intent(tech: Any) -> str:
    """O caminho de Intenção que a arte carrega (nunca None — Lei §1)."""
    from core.intent_engine import INTENT_KEYS
    intent = getattr(tech, "intent_affinity", None)
    if intent in INTENT_KEYS:
        return intent
    return DEFAULT_BURN_INTENT


# ── O livro do dia (teto da doação) ──────────────────────────────────────────
def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def donated_today(player: Any) -> int:
    """Contribuição já creditada HOJE por doação (0 num dia novo ou nunca)."""
    book = getattr(player, "scroll_econ", None)
    if not isinstance(book, dict) or book.get("d") != _today_key():
        return 0
    try:
        return max(0, int(book.get("cp", 0) or 0))
    except (TypeError, ValueError):
        return 0


def donate_headroom(player: Any) -> int:
    """Quanta contribuição por doação ainda cabe hoje (o teto é knob)."""
    cap = max(0, SCR_DONATE_DAILY_CAP)
    if cap <= 0:
        return 0
    return max(0, cap - donated_today(player))


# ── O consumo — UM helper, row-locked (os 9 sinks vivos não têm) ─────────────
async def _consume_scroll(session, player_id: int, tech_id: int, qty: int) -> int:
    """Debita `qty` pergaminhos de `tech_id`. Devolve quantos foram debitados.

    Row-lock (`with_for_update` + `populate_existing`) — os 9 sinks vivos
    repetem o idioma inline SEM lock (dívida anotada em Mecanicas/
    scroll_economy.md); os sinks NOVOS do TEC-2 nascem certos. Nunca debita
    mais do que existe: devolve 0 se o stack sumiu entre a leitura e o lock.
    """
    row = (await session.execute(
        select(PlayerInventory).where(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "technique_scroll",
            PlayerInventory.item_id == int(tech_id),
            PlayerInventory.quantity > 0,
        ).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if row is None:
        return 0
    taken = min(max(0, int(qty or 0)), int(row.quantity or 0))
    if taken <= 0:
        return 0
    row.quantity = int(row.quantity) - taken
    if row.quantity <= 0:
        await session.delete(row)
    return taken


async def _load_scroll(session, player_id: int, tech_id: int):
    """(inventário, catálogo) do pergaminho — ou (None, None)."""
    row = (await session.execute(
        select(PlayerInventory).where(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "technique_scroll",
            PlayerInventory.item_id == int(tech_id),
            PlayerInventory.quantity > 0,
        )
    )).scalar_one_or_none()
    if row is None:
        return None, None
    tech = (await session.execute(
        select(TechniqueCatalog).where(TechniqueCatalog.id == int(tech_id))
    )).scalar_one_or_none()
    return row, tech


# ── A VIEW — a arca de pergaminhos (uma verdade para chat + mini) ────────────
async def list_scrolls(session, player_id: int, lang: str = "pt") -> dict[str, Any]:
    """Todos os pergaminhos do cultivador + o que cada um VALE.

    UMA query de inventário + UMA de catálogo (as duas superfícies leem daqui).
    Inclui `learned` para a UI não oferecer "aprender" ao que já se sabe, e o
    motivo do bloqueio de cada destino. Flag OFF → ``{"on": False}`` sem query.
    """
    if not escassez_on():
        return {"on": False}

    from database.models import Player, PlayerTechnique
    from core.world_sects_engine import is_valid_sect

    row = (await session.execute(
        select(Player.sect_id, Player.sect_contribution, Player.realm,
               Player.scroll_econ)
        .where(Player.telegram_id == player_id)
    )).first()
    if row is None:
        return {"on": False}
    sect_id, balance, realm, book = row[0], int(row[1] or 0), int(row[2] or 0), row[3]

    inv_rows = (await session.execute(
        select(PlayerInventory.item_id, PlayerInventory.quantity).where(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "technique_scroll",
            PlayerInventory.quantity > 0,
        )
    )).all()
    if not inv_rows:
        return {"on": True, "in_sect": bool(is_valid_sect(sect_id)),
                "balance": balance, "headroom": _headroom_from_book(book),
                "scrolls": [], "total": 0}

    ids = [int(r[0]) for r in inv_rows]
    techs = {
        tch.id: tch for tch in (await session.execute(
            select(TechniqueCatalog).where(TechniqueCatalog.id.in_(ids))
        )).scalars().all()
    }
    learned = set((await session.execute(
        select(PlayerTechnique.technique_id).where(
            PlayerTechnique.player_id == player_id,
            PlayerTechnique.technique_id.in_(ids),
        )
    )).scalars().all())

    in_sect = bool(is_valid_sect(sect_id))
    headroom = _headroom_from_book(book)
    out: list[dict[str, Any]] = []
    for tech_id, qty in inv_rows:
        tech = techs.get(int(tech_id))
        if tech is None:
            continue  # órfão de catálogo — nunca oferecer ação sobre o vazio
        tier = scroll_tier(tech)
        per_cp = donate_cp(tier)
        out.append({
            "tech_id": int(tech_id),
            # 名 2026-09-14 — o pergaminho diz o nome da arte na lingua do dono.
            "name": catalog_name(lang, "tech", tech),
            # 武 2.2 — e a CHAVE ao lado, porque o nome traduzido não encontra a
            # arte. O nome é para LER, a chave é para ENCONTRAR (`catalog_art_key`).
            "art_key": catalog_art_key(tech),
            "emoji": tech.emoji or "📜",
            "qty": int(qty or 0),
            "tier": tier,
            "req_realm": int(tech.req_realm or 0),
            "learned": int(tech_id) in learned,
            "donate_cp": per_cp,
            "can_donate": in_sect and per_cp <= headroom,
            "donate_block": (None if in_sect and per_cp <= headroom
                             else ("no_sect" if not in_sect else "daily_cap")),
            "burn_xp": burn_xp(tier),
            "burn_intent": burn_intent(tech),
            "burn_dao": (SCR_BURN_DAO_FRAG_T4 if (tier == 4 and realm >= 5) else 0),
        })
    out.sort(key=lambda x: (-x["tier"], -x["qty"], x["tech_id"]))
    return {
        "on": True,
        "in_sect": in_sect,
        "balance": balance,
        "headroom": headroom,
        "cap": max(0, SCR_DONATE_DAILY_CAP),
        # o knob é a fonte (Lei §13) — as UIs não podem hardcodar o lote
        "max_batch": max(1, SCR_MAX_BATCH),
        "scrolls": out,
        "total": sum(x["qty"] for x in out),
    }


def _headroom_from_book(book: Any) -> int:
    """Teto restante do dia a partir do JSONB cru (a view não instancia Player)."""
    cap = max(0, SCR_DONATE_DAILY_CAP)
    if cap <= 0:
        return 0
    spent = 0
    if isinstance(book, dict) and book.get("d") == _today_key():
        try:
            spent = max(0, int(book.get("cp", 0) or 0))
        except (TypeError, ValueError):
            spent = 0
    return max(0, cap - spent)


# ── A VIEW — o que este pergaminho VALE (disclosure, Lei §1) ─────────────────
async def get_scroll_actions(session, player_id: int, tech_id: int,
                             lang: str = "pt") -> dict[str, Any]:
    """O que o cultivador pode fazer com este pergaminho, e quanto vale.

    Flag OFF → ``{"on": False}`` SEM query (OFF-identity: o payload do
    mini-app nem ganha a chave — ver o serializer). Sempre devolve os DOIS
    destinos com o motivo do bloqueio quando houver (nunca esconde: o
    requisito é DITO — Lei §1).
    """
    if not escassez_on():
        return {"on": False}

    from database.models import Player

    row = (await session.execute(
        select(Player.sect_id, Player.sect_contribution, Player.realm,
               Player.scroll_econ)
        .where(Player.telegram_id == player_id)
    )).first()
    if row is None:
        return {"on": False}
    sect_id, balance, realm, book = row[0], int(row[1] or 0), int(row[2] or 0), row[3]

    inv, tech = await _load_scroll(session, player_id, tech_id)
    if inv is None or tech is None:
        return {"on": True, "have": 0}

    from core.world_sects_engine import is_valid_sect
    tier = scroll_tier(tech)
    per_cp = donate_cp(tier)
    per_xp = burn_xp(tier)
    in_sect = bool(is_valid_sect(sect_id))
    headroom = _headroom_from_book(book)

    donate_block = None
    if not in_sect:
        donate_block = "no_sect"
    elif per_cp > headroom:
        donate_block = "daily_cap"

    intent = burn_intent(tech)
    dao_bonus = (SCR_BURN_DAO_FRAG_T4 if (tier == 4 and realm >= 5) else 0)

    return {
        "on": True,
        "tech_id": int(tech_id),
        "have": int(inv.quantity or 0),
        "tier": tier,
        "donate": {
            "cp": per_cp,
            "can": donate_block is None,
            "block": donate_block,
            "headroom": headroom,
            "balance": balance,
        },
        "burn": {
            "xp": per_xp,
            "intent": intent,
            "dao_fragments": int(dao_bonus),
            "can": True,
            "block": None,
        },
    }


# ── O WRITE 1 — doar à Biblioteca da casa ────────────────────────────────────
async def donate_scroll(session, player_id: int, tech_id: int,
                        qty: int = 1) -> dict[str, Any]:
    """Doa `qty` pergaminhos à Biblioteca da casa → contribuição (SALDO).

    Ordem dos gates é a ordem disclosed, e a seita é checada ANTES de tocar
    no item (recon: `award_sect_contribution` devolve `not_in_sect` em
    silêncio — sem esta ordem o pergaminho morria sem pagamento).

    O crédito é SÓ no saldo (`credit_earned=False`): doar papel jamais promove
    (Lei §4 — jade entrega pergaminho, e posto não se compra). Teto diário
    knob-ajustável: se só couberem 2 dos 5 pergaminhos, doa 2 e DIZ.
    Caller commita. Flag OFF → recusa SEM query.
    """
    if not escassez_on():
        return {"ok": False, "reason": "scr_off"}

    from database.models import Player
    from core.world_sects_engine import award_sect_contribution, is_valid_sect

    qty = max(1, min(int(qty or 1), max(1, SCR_MAX_BATCH)))

    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}
    if not is_valid_sect(player.sect_id):
        return {"ok": False, "reason": "not_in_sect"}

    inv, tech = await _load_scroll(session, player_id, tech_id)
    if inv is None or tech is None:
        return {"ok": False, "reason": "no_scroll"}

    tier = scroll_tier(tech)
    per_cp = donate_cp(tier)
    headroom = donate_headroom(player)
    if per_cp <= 0 or headroom < per_cp:
        return {"ok": False, "reason": "daily_cap",
                "headroom": headroom, "per_cp": per_cp,
                "cap": max(0, SCR_DONATE_DAILY_CAP)}

    # Quantos cabem: no estoque, no pedido E no teto do dia. Guardamos QUAL dos
    # dois mordeu — dizer "o teto do dia falou mais alto" quando na verdade o
    # estoque encolheu é uma mentira pequena, mas é uma mentira (review TEC-2).
    by_cap = headroom // per_cp
    in_stock = int(inv.quantity or 0)
    wanted = min(qty, in_stock, by_cap)
    capped_by = "cap" if by_cap <= in_stock and by_cap < qty else "stock"
    taken = await _consume_scroll(session, player_id, tech_id, wanted)
    if taken <= 0:
        return {"ok": False, "reason": "no_scroll"}

    gained = per_cp * taken
    balance_before = int(player.sect_contribution or 0)
    earned_before = int(player.sect_contribution_earned or 0)

    # UM crédito por ação (nunca N) — evita rajada de notificação de promoção.
    res = await award_sect_contribution(
        session, player_id, gained, source="scroll_donation", credit_earned=False,
    )
    if not res.get("ok"):
        # Não deveria acontecer (a seita já foi validada sob lock), mas se
        # acontecer NÃO podemos deixar o pergaminho morrer sem pagamento.
        return {"ok": False, "reason": res.get("reason") or "award_failed"}

    book = player.scroll_econ if isinstance(player.scroll_econ, dict) else {}
    today = _today_key()
    spent_today = (int(book.get("cp", 0) or 0) if book.get("d") == today else 0)
    # Substituição do dict inteiro: o valor é auto-contido (não há merge a
    # preservar, ao contrário do region_states.payload do MV-3/MV-7).
    player.scroll_econ = {"d": today, "cp": spent_today + gained}

    balance_after = int(player.sect_contribution or 0)
    return {
        "ok": True,
        "tech_id": int(tech_id),
        "name": catalog_name((player.language or "pt").lower(), "tech", tech),
        "emoji": tech.emoji or "📜",
        "tier": tier,
        "qty": taken,
        "requested": qty,
        "partial": taken < qty,
        "capped_by": capped_by if taken < qty else None,
        "cp_gained": gained,
        "balance_before": balance_before,
        "balance_after": balance_after,
        # A escada NUNCA se move por doação — o teste prova, e o payload diz.
        "earned_before": earned_before,
        "earned_after": int(player.sect_contribution_earned or 0),
        "headroom_after": donate_headroom(player),
        "remaining": max(0, int(inv.quantity or 0)),
    }


# ── O WRITE 2 — o Ritual de Compreensão (queimar) ────────────────────────────
async def burn_scroll(session, player_id: int, tech_id: int,
                      qty: int = 1) -> dict[str, Any]:
    """Queima `qty` pergaminhos → XP de INTENÇÃO no caminho da própria arte.

    A arte carrega uma intenção (`intent_affinity`); queimá-la é compreender
    ESSA intenção. Sem seita, sem reino mínimo, sem ter aprendido a técnica —
    é o destino que SEMPRE existe (e o que finalmente dá saída ao pergaminho
    inaprendível que hoje entope o anel para sempre; ver o beco sem saída
    anotado em Mecanicas/scroll_economy.md).

    No topo da escada (T4) e com o Dao destrancado (Reino 5+), soma ainda
    `SCR_BURN_DAO_FRAG_T4` fragmentos pelo helper canônico do dao_engine
    (nunca uma 5ª cópia do upsert — recon TEC-2).
    Caller commita. Flag OFF → recusa SEM query.
    """
    if not escassez_on():
        return {"ok": False, "reason": "scr_off"}

    from database.models import Player
    from core.intent_engine import award_intent_xp

    qty = max(1, min(int(qty or 1), max(1, SCR_MAX_BATCH)))

    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}

    inv, tech = await _load_scroll(session, player_id, tech_id)
    if inv is None or tech is None:
        return {"ok": False, "reason": "no_scroll"}

    tier = scroll_tier(tech)
    intent = burn_intent(tech)
    taken = await _consume_scroll(session, player_id, tech_id, min(qty, int(inv.quantity or 0)))
    if taken <= 0:
        return {"ok": False, "reason": "no_scroll"}

    xp_gained = burn_xp(tier) * taken
    # Sem savepoint de propósito: se o crédito falhar, a transação inteira
    # cai e o pergaminho NÃO se perde (o caller nunca commita um consumo sem
    # pagamento). O contrário — engolir o erro — é que criaria o item morto.
    res = await award_intent_xp(session, player_id, intent, xp_gained)

    frags: list[dict[str, Any]] = []
    dao_n = SCR_BURN_DAO_FRAG_T4 * taken if tier == 4 else 0
    if dao_n > 0:
        # SAVEPOINT obrigatório (lição TEC-1 F9 / review TEC-2): o fragmento é
        # um BÔNUS best-effort do ápice, mas engolir a exceção sem savepoint
        # ENVENENA a transação — o consumo e o XP acima já estão pendentes e o
        # commit do caller estouraria DEPOIS de termos devolvido ok:True (o
        # pergaminho sumia e o cultivador não recebia nada). O begin_nested
        # isola: falha aqui = só o fragmento não acontece, a queima vive.
        try:
            async with session.begin_nested():
                from core.dao_engine import grant_random_fragments
                frags = await grant_random_fragments(
                    session, player_id, dao_n, int(player.realm or 0)
                ) or []
        except Exception:
            logger.debug("burn_scroll dao fragments failed (player_id=%s)",
                         player_id, exc_info=True)
            frags = []

    return {
        "ok": True,
        "tech_id": int(tech_id),
        "name": catalog_name((player.language or "pt").lower(), "tech", tech),
        "emoji": tech.emoji or "📜",
        "tier": tier,
        "qty": taken,
        "requested": qty,
        "partial": taken < qty,
        "intent": intent,
        "xp_gained": xp_gained,
        "rank_before": int((res or {}).get("prev_rank", 0) or 0),
        "rank_after": int((res or {}).get("rank", 0) or 0),
        "rank_xp": int((res or {}).get("xp", 0) or 0),
        "leveled_up": bool((res or {}).get("leveled_up")),
        "dao_fragments": [
            {"law": f.get("law_name"), "emoji": f.get("law_emoji"),
             "fragments": f.get("fragments"), "total": f.get("total")}
            for f in frags
        ],
        "remaining": max(0, int(inv.quantity or 0)),
    }
