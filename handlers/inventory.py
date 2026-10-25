import logging
import math
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, func, delete, update as sa_update

from core.utils import safe_handler, rate_limit, build_pagination_keyboard, _get_player, _ensure_player, safe_answer, escape_markdown, resolve_chat_player_id
from core.i18n import t
# 名 2026-09-14 — a MOCHILA deixa de falar ingles. Eram 24 leituras cruas aqui,
# o maior bolso do jogo: pilulas, ervas, minerios, artefactos e artes. Dono unico
# em `core/i18n.py`; a contagem vive em `scripts/_audit_nomes_crus.py`.
from core.i18n import catalog_name as _cname, catalog_desc as _cdesc
from core.alchemy_engine import (
    apply_pill_effect,
    get_active_buffs,
    get_pill_effectiveness,
    increment_pill_usage,
)
from core.game_logic import format_number, get_time_display
from database.db import get_session_factory
from database.models import (
    Player, PlayerInventory, PlayerArtifact, ArtifactCatalog,
    PlayerOre, OreCatalog, HerbCatalog, PillCatalog,
    TechniqueCatalog, PlayerTechnique, PlayerSpatialRing,
    PlayerDaoFragment,
)
from config import ARTIFACT_GRADES, REALM_NAMES
from core.combat_engine import MASTERY_STAGES

ITEMS_PER_PAGE = 8
# 🎒 3.2 (2026-09-30) — a conta do anel tem UM dono, `core/anel.py`. Os nomes
# continuam importáveis daqui (o mini-app e scripts antigos liam-nos deste
# módulo); a tabela vive lá.
from core.anel import MAX_RING_TIER, RING_MAX_SLOTS, RING_UPGRADE_STONES  # noqa: E402
from core import anel as _anel  # noqa: E402
from core import itens as _itens  # noqa: E402

# Spirit stones rewarded per artifact grade on dismantle
DISMANTLE_BY_GRADE = {
    0: 50, 1: 150, 2: 500, 3: 1_500,
    4: 5_000, 5: 15_000, 6: 50_000, 7: 200_000,
    8: 750_000,
}

# Quick-sell price per unit by ore tier
ORE_SELL_PER_UNIT = {1: 80, 2: 250, 3: 800, 4: 2_500, 5: 8_000}

# Fraction of herb base_price given back on quick-sell
HERB_SELL_RATIO = 0.6

# Human-readable misc item labels — D-4 (v14.2): every misc item type the
# player can hold MUST have a real name + emoji.
# 🎒 3.2 (2026-09-30) — a tabela `_MISC_LABELS` que vivia aqui era INGLÊS fixo
# ("Beast Trap" a quem joga em pt e es), e o mini-app nem a lia: mandava
# "beast_trap #0". O nome vive agora num dono só, nas três línguas —
# `core/itens.nome` / `core/itens.emoji` —, e as duas portas perguntam-lhe.

# D-4 (v14.2): per-type action mapping. Two kinds of actions:
#   • "deeplink" → emit a callback that re-routes to an existing flow.
#   • "use"      → call core.inventory_actions module (NEW).
# beast_trap / beast_core / gacha_ticket already have working flows; they get
# discoverability buttons here so players don't think their items are stuck.
_MISC_ACTIONS = {
    "beast_trap": {"kind": "deeplink", "callback": "cmd_bestiario", "label_key": "inv_misc_action_beast_trap"},
    "beast_core": {"kind": "deeplink", "callback": "cmd_bestiario", "label_key": "inv_misc_action_beast_core"},
    "gacha_ticket": {"kind": "deeplink", "callback": "cmd_loja", "label_key": "inv_misc_action_gacha_ticket"},
    "blueprint": {"kind": "use", "label_key": "inv_misc_action_blueprint"},
    "ore_pack": {"kind": "use", "label_key": "inv_misc_action_ore_pack"},
    "pill_recipe_scroll": {"kind": "use", "label_key": "inv_misc_action_pill_recipe_scroll"},
    "mystery_box": {"kind": "use", "label_key": "inv_misc_action_mystery_box"},
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_or_create_ring(session, player_id: int) -> PlayerSpatialRing:
    ring = (await session.execute(
        select(PlayerSpatialRing).where(PlayerSpatialRing.player_id == player_id)
    )).scalar_one_or_none()
    if not ring:
        ring = PlayerSpatialRing(player_id=player_id, tier=1, max_slots=50)
        session.add(ring)
        await session.flush()
    return ring


async def _count_slots(session, player_id: int) -> int:
    inv = (await session.execute(
        select(func.count()).select_from(PlayerInventory).where(
            PlayerInventory.player_id == player_id,
            PlayerInventory.quantity > 0,
        )
    )).scalar() or 0
    ores = (await session.execute(
        select(func.count()).select_from(PlayerOre).where(
            PlayerOre.player_id == player_id,
            PlayerOre.quantity > 0,
        )
    )).scalar() or 0
    arts = (await session.execute(
        select(func.count()).select_from(PlayerArtifact).where(
            PlayerArtifact.player_id == player_id,
        )
    )).scalar() or 0
    return inv + ores + arts


async def _tab_counts(session, player_id: int) -> dict:
    async def _cnt(*extra_where):
        return (await session.execute(
            select(func.count()).select_from(PlayerInventory).where(
                PlayerInventory.player_id == player_id,
                PlayerInventory.quantity > 0,
                *extra_where,
            )
        )).scalar() or 0

    pills = await _cnt(PlayerInventory.item_type == "pill")
    herbs = await _cnt(PlayerInventory.item_type == "herb")
    techs = await _cnt(PlayerInventory.item_type == "technique_scroll")
    misc = await _cnt(PlayerInventory.item_type.notin_(["pill", "herb", "technique_scroll"]))
    ores = (await session.execute(
        select(func.count()).select_from(PlayerOre).where(
            PlayerOre.player_id == player_id,
            PlayerOre.quantity > 0,
        )
    )).scalar() or 0
    equip = (await session.execute(
        select(func.count()).select_from(PlayerArtifact).where(
            PlayerArtifact.player_id == player_id,
        )
    )).scalar() or 0
    return {"pill": pills, "herb": herbs, "tech": techs, "misc": misc, "ore": ores, "equip": equip}


async def _send_or_edit(update: Update, text: str, kb: InlineKeyboardMarkup):
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ─── Main Inventory Screen ────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        ring = await _get_or_create_ring(session, player.telegram_id)
        used = await _count_slots(session, player.telegram_id)
        counts = await _tab_counts(session, player.telegram_id)
        await session.commit()

    sep = "—" * 22
    text = (
        f"{t(lang, 'inv_title')}\n"
        f"{sep}\n"
        f"{t(lang, 'inv_ring_info', tier=ring.tier, used=used, max=ring.max_slots)}\n"
        f"{sep}"
    )
    buttons = [
        [
            InlineKeyboardButton(
                f"💊 {t(lang, 'inv_tab_pills')} ({counts['pill']})",
                callback_data="inv_tab_pill_R",
            ),
            InlineKeyboardButton(
                f"🌿 {t(lang, 'inv_tab_herbs')} ({counts['herb']})",
                callback_data="inv_tab_herb_R",
            ),
        ],
        [
            InlineKeyboardButton(
                f"⛏️ {t(lang, 'inv_tab_ores')} ({counts['ore']})",
                callback_data="inv_tab_ore_R",
            ),
            InlineKeyboardButton(
                f"⚔️ {t(lang, 'inv_tab_equip')} ({counts['equip']})",
                callback_data="inv_tab_equip_R",
            ),
        ],
        [
            InlineKeyboardButton(
                f"📜 {t(lang, 'inv_tab_tech')} ({counts['tech']})",
                callback_data="inv_tab_tech_R",
            ),
            InlineKeyboardButton(
                f"📦 {t(lang, 'inv_tab_misc')} ({counts['misc']})",
                callback_data="inv_tab_misc_R",
            ),
        ],
        [InlineKeyboardButton(f"💍 {t(lang, 'inv_upgrade_ring')}", callback_data="inv_ring_info")],
        [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="nav_main")],
    ]
    await _send_or_edit(update, text, InlineKeyboardMarkup(buttons))


# ─── Pill quality scaling (display mirror of core.alchemy_engine) ────────────
# Owner reports 2026-05-09 ([jogadores]): Perfect/Divine/Heavenly pills
# rendered the same magnitude as Normal in the ℹ️ detail card. Cause: the card
# read `pill.effect_value` raw and didn't know the quality. Engine scaling was
# already correct (alchemy_engine.apply_pill_effect); only the display was lying.
# This helper mirrors the engine's scaling so the card shows the truth.

_PILL_POTENCY = {"normal": 1.0, "perfect": 1.5, "divine": 3.0, "heavenly": 5.0}
_PILL_BUFF_POTENCY = {"normal": 1.0, "perfect": 1.3, "divine": 1.6, "heavenly": 2.2}
_PILL_BUFF_QMULT = {"normal": 1.0, "perfect": 1.5, "divine": 3.0, "heavenly": 5.0}

_PILL_MULTIPLIER_BUFFS = {
    "cb_boost", "soul_boost", "bp_boost", "perception_boost",
    "defense_boost", "luck_boost", "all_boost",
    "breakthrough_boost", "dao_fragment_chance", "qi_regen_boost",
}


def _scale_pill_for_display(pill: PillCatalog, quality: str) -> dict:
    """Mirror alchemy_engine.apply_pill_effect's magnitude/duration scaling.

    Returns a dict consumed by `_show_pill_detail` so each row in the card
    reflects the actual quality the player owns, not the base catalog row.
    """
    quality = (quality or "normal").lower()
    potency = _PILL_POTENCY.get(quality, 1.0)
    buff_potency = _PILL_BUFF_POTENCY.get(quality, 1.0)

    base_duration = int(pill.duration_minutes or 0)
    if quality == "heavenly":
        duration = base_duration * 2
    elif quality == "divine":
        duration = int(base_duration * 1.5)
    else:
        duration = base_duration

    if pill.effect_type in _PILL_MULTIPLIER_BUFFS:
        qmult = _PILL_BUFF_QMULT.get(quality, 1.0)
        if pill.effect_value > 1:
            scaled = 1.0 + (pill.effect_value - 1.0) * qmult
        else:
            scaled = pill.effect_value * qmult if qmult != 1.0 else pill.effect_value
        return {"kind": "pct", "pct": (scaled - 1.0) * 100, "duration": duration}

    if pill.effect_type == "qi_restore":
        return {"kind": "flat", "value": int(pill.effect_value * buff_potency), "duration": 0}
    if pill.effect_type == "hp_restore":
        return {"kind": "pct", "pct": pill.effect_value * buff_potency * 100, "duration": 0}

    if pill.effect_type == "stat_boost":
        return {"kind": "flat", "value": int(pill.effect_value * potency), "duration": 0}

    if pill.effect_type == "purity_boost":
        # QoL-Feedback 2026-07-29 (report [jogador] "Pureza +0"): o ramo flat
        # fazia int(0.05×potency) = 0. O número real depende da fundação do
        # jogador — o consumidor compõe via alchemy_engine.purity_gain (a
        # MESMA função do apply); este helper só marca o tipo.
        return {"kind": "purity", "duration": 0}

    if pill.effect_type in ("qi_capacity", "cb_instant",
                            "core_essence", "body_tempering_progress"):
        return {"kind": "flat", "value": int(pill.effect_value * potency), "duration": 0}

    if pill.effect_type == "eternal_foundation_reroll":
        # QoL-Feedback 03/08 (report [jogador] "unknown effects"): o ramo raw imprimia
        # "📊 Valor: 1.0" — número sem significado para uma pílula que REROLA a
        # fundação. Como no purity_boost, este helper só MARCA o tipo; o
        # consumidor compõe a disclosure honesta (fundação atual + tabela de
        # odds + risco) via foundation_engine.foundation_reroll_preview — a
        # mesma fonte que o apply.
        return {"kind": "foundation_reroll", "duration": 0}

    if pill.effect_type == "foundation_reroll":
        # Review adversarial 03/08 — a irmã (id 34, min_realm 2: MUITO mais
        # gente a tem) caía no mesmo ramo raw e imprimia "📊 Valor: 1.0" uma
        # linha abaixo do rótulo novo. Não tem tabela de odds (é uma PROVA de
        # 3 atributos), logo a disclosure honesta é a REGRA, não números.
        return {"kind": "foundation_trial", "duration": 0}

    # Revive — magnitude is not numeric
    return {"kind": "raw", "value": pill.effect_value, "duration": duration}


# ─── Pills Tab ────────────────────────────────────────────────────────────────

async def _pills_tab(update: Update, lang: str, player_id: int, page: int):
    async with get_session_factory()() as session:
        results = list((await session.execute(
            select(PlayerInventory, PillCatalog)
            .join(PillCatalog, PillCatalog.id == PlayerInventory.item_id)
            .where(
                PlayerInventory.player_id == player_id,
                PlayerInventory.item_type == "pill",
                PlayerInventory.quantity > 0,
            )
            .order_by(PillCatalog.min_realm, PillCatalog.id)
        )).all())

    total = len(results)
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(0, min(page - 1, total_pages - 1))
    page_items = results[page * ITEMS_PER_PAGE: (page + 1) * ITEMS_PER_PAGE]

    sep = "—" * 20
    lines = [f"💊 *{t(lang, 'inv_tab_pills')}*", sep]
    buttons = []

    if not results:
        lines.append(t(lang, "inv_pills_empty"))
    else:
        for inv, pill in page_items:
            quality_tag = f" ({inv.quality.upper()})" if inv.quality != "normal" else ""
            # TAPETE QoL §5 item 6 ([jogador]: "reloginho"): ⏱️ = buff temporizado.
            timed_tag = " ⏱️" if (int(pill.duration_minutes or 0) > 0 or pill.effect_type == "revive") else ""
            lines.append(f"{pill.emoji} *{_cname(lang, 'pill', pill)}*{timed_tag}{quality_tag} ×{inv.quantity}")
            lines.append(f"  _{_cdesc(lang, 'pill', pill)}_")
            lines.append("")
            row = [
                InlineKeyboardButton(
                    f"💊 {t(lang, 'inv_use_pill')} {_cname(lang, 'pill', pill)}{quality_tag}",
                    callback_data=f"inv_use_{pill.id}_{inv.quality}",
                ),
                # M-11: detail card for the pill — full effect info, duration, caps,
                # etc. Players asked for this since the inline description is short.
                # 2026-05-17 fix: pass quality so the card scales magnitude/duration.
                InlineKeyboardButton("ℹ️", callback_data=f"inv_pill_info_{pill.id}_{inv.quality}"),
            ]
            buttons.append(row)
            # H-9: bulk pill consume — only for stat_boost pills (others are timed buffs).
            # Quick-wins 2026-06-10 — the chat "atalho": ×5 / ×10 / ×Máx (the
            # mini-app is the canonical surface with the full 1/5/10/Máx/custom
            # selector). All route to the same idempotent, capped, FOR-UPDATE'd
            # bulk consume; counts are clamped to [1,50] server-side.
            # 07/08 ([jogador]): os consumíveis de reposição entram no lote —
            # `BULK_REFILL_TYPES` é a MESMA verdade que o executor consulta
            # (nunca duas listas para a mesma regra).
            from core.alchemy_engine import BULK_REFILL_TYPES as _BULK_REFILL
            if inv.quantity >= 5 and (pill.effect_type == "stat_boost"
                                      or pill.effect_type in _BULK_REFILL):
                bulk_qty = min(inv.quantity, 10)
                bulk_row = [
                    InlineKeyboardButton(
                        t(lang, "inv_use_pill_x5"),
                        callback_data=f"inv_usex_{pill.id}_{inv.quality}_5",
                    ),
                    InlineKeyboardButton(
                        t(lang, "inv_use_pill_xN", n=bulk_qty),
                        callback_data=f"inv_usex_{pill.id}_{inv.quality}_{bulk_qty}",
                    ),
                ]
                max_qty = min(inv.quantity, 50)
                if max_qty > bulk_qty:
                    bulk_row.append(InlineKeyboardButton(
                        t(lang, "inv_use_pill_max", n=max_qty),
                        callback_data=f"inv_usex_{pill.id}_{inv.quality}_{max_qty}",
                    ))
                buttons.append(bulk_row)
        if total_pages > 1:
            buttons.extend(build_pagination_keyboard(page + 1, total_pages, "inv_tab_pill_", lang))

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_main")])
    await update.callback_query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def _show_pill_detail(update: Update, pill_id: int, quality: str = "normal"):
    """M-11 + 2026-05-17 fix: pill detail card scaled to the quality the player
    selected. Magnitude/duration mirror `apply_pill_effect`; stock shows a
    per-quality breakdown so players see what they actually own."""
    query = update.callback_query
    quality = (quality or "normal").lower()
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"
        pill = (await session.execute(
            select(PillCatalog).where(PillCatalog.id == pill_id)
        )).scalar_one_or_none()
        if not pill:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        # Per-quality stock — [jogador] 2026-05-09: "a quantidade em estoque
        # também tá puxando das pílulas normais". Old card summed all qualities
        # into a single ×N total, hiding which row the player was looking at.
        stock_rows = (await session.execute(
            select(PlayerInventory.quality, func.coalesce(func.sum(PlayerInventory.quantity), 0))
            .where(
                PlayerInventory.player_id == player.telegram_id,
                PlayerInventory.item_type == "pill",
                PlayerInventory.item_id == pill_id,
            )
            .group_by(PlayerInventory.quality)
        )).all()
        stock_by_quality = {(q or "normal").lower(): int(qty) for q, qty in stock_rows}
        qty_total = sum(stock_by_quality.values())

        # QoL-Feedback 2026-07-29 Item A: o número honesto do purity_boost
        # precisa de resistência + facção (mesmos termos do apply). Buscados
        # dentro da sessão; a composição usa alchemy_engine.purity_gain.
        purity_ctx = None
        if pill.effect_type == "purity_boost":
            from core.alchemy_engine import get_pill_effectiveness
            from core.faction_engine import get_faction_bonuses
            _eff = await get_pill_effectiveness(session, player.telegram_id, pill)
            _fac = await get_faction_bonuses(session, player.telegram_id)
            _fac_mult = 1.0 + max(0.0, float(_fac.get("pill_potency_bonus", 0.0) or 0.0))
            purity_ctx = {"eff": float(_eff), "fac": _fac_mult,
                          "fq": player.foundation_quality}

        # QoL-Feedback 03/08 (report [jogador]) — a fundação ATUAL tem de ser lida
        # DENTRO da sessão (o `player` fica detached quando o `async with`
        # fecha; mesmo motivo do purity_ctx acima).
        found_ctx = None
        if pill.effect_type in ("eternal_foundation_reroll", "foundation_reroll"):
            found_ctx = {"fq": player.foundation_quality,
                         "realm": int(getattr(player, "realm", 0) or 0)}

    scaled = _scale_pill_for_display(pill, quality)

    sep = "—" * 20
    quality_tag = f" ({quality.upper()})" if quality != "normal" else ""
    lines = [
        f"{pill.emoji} *{_cname(lang, 'pill', pill)}*{quality_tag}",
        sep,
        f"📖 _{_cdesc(lang, 'pill', pill)}_",
        "",
    ]
    # Quality banner so the player can verify which row they tapped
    lines.append(t(lang, "alch_quality_display", quality=quality.upper()))

    effect_label = t(lang, f"pill_effect_label_{pill.effect_type}") if pill.effect_type else "—"
    if effect_label.startswith("[pill_effect_label_"):
        effect_label = pill.effect_type or "—"
    lines.append(t(lang, "inv_pill_detail_effect_type", type=effect_label))

    # Owner 2026-05-17: pill description is fixed flavor text and shows the
    # Normal magnitude even on Heavenly rows — players think "the effect didn't
    # apply, only the name changed". Append the Normal baseline side-by-side so
    # the scaling is *explicit*: "+125% (base Normal: +25%)".
    base = _scale_pill_for_display(pill, "normal") if quality != "normal" else None

    if scaled["kind"] == "pct":
        if base and base["kind"] == "pct" and abs(base["pct"] - scaled["pct"]) > 0.01:
            lines.append(t(lang, "inv_pill_detail_effect_pct_scaled",
                           pct=f"{scaled['pct']:.0f}", base_pct=f"{base['pct']:.0f}"))
        else:
            lines.append(t(lang, "inv_pill_detail_effect_pct", pct=f"{scaled['pct']:.0f}"))
        if scaled.get("duration"):
            base_dur = (base or {}).get("duration") if base else None
            if base_dur and base_dur != scaled["duration"]:
                lines.append(t(lang, "inv_pill_detail_duration_scaled",
                               minutes=scaled["duration"], base_minutes=base_dur))
            else:
                lines.append(t(lang, "inv_pill_detail_duration", minutes=scaled["duration"]))
    elif scaled["kind"] == "flat":
        if base and base["kind"] == "flat" and base["value"] != scaled["value"]:
            lines.append(t(lang, "inv_pill_detail_effect_flat_scaled",
                           value=scaled["value"], base_value=base["value"]))
        else:
            lines.append(t(lang, "inv_pill_detail_effect_flat", value=scaled["value"]))
    elif scaled["kind"] == "purity":
        # Ganho REAL em base de cultivo (mesma função do apply) — nunca mais
        # "Pureza +0" (report [jogador] 2026-07-28).
        from core.alchemy_engine import purity_gain
        _eff = purity_ctx["eff"] if purity_ctx else 1.0
        _facm = purity_ctx["fac"] if purity_ctx else 1.0
        _fq = purity_ctx["fq"] if purity_ctx else None
        gain = purity_gain(pill.effect_value, quality, _eff, _fq, _facm)
        base_gain = (purity_gain(pill.effect_value, "normal", _eff, _fq, _facm)
                     if quality != "normal" else None)
        if base_gain is not None and base_gain != gain:
            lines.append(t(lang, "inv_pill_detail_effect_flat_scaled",
                           value=gain, base_value=base_gain))
        else:
            lines.append(t(lang, "inv_pill_detail_effect_flat", value=gain))
        if _fq:
            lines.append(t(lang, "inv_pill_detail_purity_note",
                           foundation=t(lang, f"foundation_quality_{_fq}")))
    elif scaled["kind"] == "foundation_reroll":
        # QoL-Feedback 03/08 (report [jogador]) — Lei §10 ANTES do consumo: a fundação
        # atual (com o ×mult que ela vale), a tabela de odds real da qualidade
        # do craft e o risco de PIORAR. Mesma fonte do apply (D-1c intacto).
        from core.foundation_engine import (
            foundation_reroll_preview, FOUNDATION_QUALITIES,
        )
        prev = foundation_reroll_preview(
            (found_ctx or {}).get("fq"), quality,
            realm=(found_ctx or {}).get("realm"))

        def _fq_label(q: str) -> str:
            info = FOUNDATION_QUALITIES.get(q, FOUNDATION_QUALITIES["low"])
            return f"{t(lang, info['label_key'])} {info['emoji']}"

        if prev["current"]:
            lines.append(t(lang, "inv_pill_detail_found_current",
                           quality=_fq_label(prev["current"]),
                           mult=f"{prev['current_mult']:.2f}"))
        else:
            lines.append(t(lang, "inv_pill_detail_found_current_none"))

        if prev["locked"]:
            lines.append(t(lang, "inv_pill_detail_found_locked"))
        else:
            odds_str = " · ".join(
                t(lang, "inv_pill_detail_found_odds_row",
                  pct=f"{o['pct']:g}", quality=_fq_label(o["quality"]),
                  mult=f"{o['mult']:.2f}")
                for o in prev["odds"]
            )
            lines.append(t(lang, "inv_pill_detail_found_odds", odds=odds_str))
            if prev["sacred_path"]:
                lines.append(t(lang, "inv_pill_detail_found_sacred"))
            else:
                lines.append(t(lang, "inv_pill_detail_found_sacred_hint"))
            if prev["can_downgrade"]:
                lines.append(t(lang, "inv_pill_detail_found_risk"))
    elif scaled["kind"] == "foundation_trial":
        # A Pílula de Reparo (id 34) não tem tabela: refaz a PROVA de 3
        # atributos (Alma/Percepção/Sorte contra limiares escalados pelo
        # prestígio), teto Perfeita, e pode piorar. Dizer a regra é honesto;
        # inventar percentagens não seria.
        from core.foundation_engine import FOUNDATION_QUALITIES as _FQ3
        _fq3 = (found_ctx or {}).get("fq")
        if _fq3:
            _i3 = _FQ3.get(_fq3, _FQ3["low"])
            lines.append(t(lang, "inv_pill_detail_found_current",
                           quality=f"{t(lang, _i3['label_key'])} {_i3['emoji']}",
                           mult=f"{_i3['stat_mult']:.2f}"))
        else:
            lines.append(t(lang, "inv_pill_detail_found_current_none"))
        if _fq3 == "sacred":
            lines.append(t(lang, "inv_pill_detail_found_locked"))
        else:
            lines.append(t(lang, "inv_pill_detail_found_trial"))
            lines.append(t(lang, "inv_pill_detail_found_risk"))
    else:
        lines.append(t(lang, "inv_pill_detail_effect_value", value=scaled["value"]))

    if pill.min_realm:
        lines.append(t(lang, "inv_pill_detail_min_realm",
                        realm=REALM_NAMES[min(pill.min_realm, len(REALM_NAMES) - 1)]))

    # Stock — current quality first, breakdown second so the player understands
    # the ×N number on each line of the pills tab.
    own_now = stock_by_quality.get(quality, 0)
    lines.append(t(lang, "inv_pill_detail_quantity", qty=own_now))
    if len(stock_by_quality) > 1 or qty_total != own_now:
        order = ["normal", "perfect", "divine", "heavenly"]
        breakdown_parts = [
            f"{q.title()} ×{stock_by_quality[q]}"
            for q in order if stock_by_quality.get(q, 0) > 0
        ]
        if breakdown_parts:
            lines.append(t(lang, "inv_pill_detail_stock_breakdown",
                           total=qty_total, breakdown=" • ".join(breakdown_parts)))

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_tab_pill_R")]
    ])
    try:
        await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.warning("pill detail edit failed: %s", e)


# ─── Herbs Tab ────────────────────────────────────────────────────────────────

async def _herbs_tab(update: Update, lang: str, player_id: int, page: int):
    async with get_session_factory()() as session:
        results = list((await session.execute(
            select(PlayerInventory, HerbCatalog)
            .join(HerbCatalog, HerbCatalog.id == PlayerInventory.item_id)
            .where(
                PlayerInventory.player_id == player_id,
                PlayerInventory.item_type == "herb",
                PlayerInventory.quantity > 0,
            )
            .order_by(HerbCatalog.tier, HerbCatalog.id)
        )).all())
        # MV-9.5 商队 §1 — o `here` da disclosure precisa de saber ONDE o
        # jogador está (esta tab só recebe o `player_id`).
        _cont = (await session.execute(
            select(Player.current_continent).where(Player.telegram_id == player_id)
        )).scalar_one_or_none()

    total = len(results)
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(0, min(page - 1, total_pages - 1))
    page_items = results[page * ITEMS_PER_PAGE: (page + 1) * ITEMS_PER_PAGE]

    sep = "—" * 20
    lines = [f"🌿 *{t(lang, 'inv_tab_herbs')}*", sep]
    buttons = []

    # MV-9.5 商队 §1 — A DISCLOSURE: onde nasce cada erva do anel. Import LOCAL
    # e fail-safe: `origin_note` devolve None com a flag OFF ⇒ nenhuma linha
    # nova ⇒ a aba fica idêntica à de hoje para quem está em `main`.
    try:
        from core.caravan_engine import origin_note as _origin_note
    except Exception:
        _origin_note = None

    if not results:
        lines.append(t(lang, "inv_herbs_empty"))
    else:
        for inv, herb in page_items:
            sell_price = max(1, int(herb.base_price * HERB_SELL_RATIO)) * inv.quantity
            lines.append(f"{herb.emoji} *{_cname(lang, 'herb', herb)}* ×{inv.quantity}")
            lines.append(f"  {'⭐' * herb.tier} · 🪙 {sell_price:,} SS")
            _og = _origin_note("herb", int(herb.id), lang, _cont) if _origin_note else None
            if _og and _og.get("line"):
                # `line` já vem localizada do servidor — NUNCA passar por t().
                lines.append(f"  ↳ {_og['line']}")
            lines.append("")
            buttons.append([InlineKeyboardButton(
                f"🪙 {t(lang, 'inv_sell')} {_cname(lang, 'herb', herb)} ×{inv.quantity}",
                callback_data=f"inv_sell_herb_{inv.id}",
            )])
        if total_pages > 1:
            buttons.extend(build_pagination_keyboard(page + 1, total_pages, "inv_tab_herb_", lang))

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_main")])
    await update.callback_query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


# ─── Ores Tab ────────────────────────────────────────────────────────────────

async def _ores_tab(update: Update, lang: str, player_id: int, page: int):
    async with get_session_factory()() as session:
        results = list((await session.execute(
            select(PlayerOre, OreCatalog)
            .join(OreCatalog, OreCatalog.id == PlayerOre.ore_id)
            .where(
                PlayerOre.player_id == player_id,
                PlayerOre.quantity > 0,
            )
            .order_by(OreCatalog.tier, OreCatalog.id)
        )).all())
        # MV-9.5 商队 §1 — o `here` da disclosure precisa de saber ONDE o
        # jogador está (esta tab só recebe o `player_id`).
        _cont = (await session.execute(
            select(Player.current_continent).where(Player.telegram_id == player_id)
        )).scalar_one_or_none()

    total = len(results)
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(0, min(page - 1, total_pages - 1))
    page_items = results[page * ITEMS_PER_PAGE: (page + 1) * ITEMS_PER_PAGE]

    sep = "—" * 20
    lines = [f"⛏️ *{t(lang, 'inv_tab_ores')}*", sep]
    buttons = []

    # MV-9.5 商队 §1 — A DISCLOSURE: onde nasce cada minério do anel. Import
    # LOCAL e fail-safe: `origin_note` devolve None com a flag OFF ⇒ nenhuma
    # linha nova ⇒ a aba fica idêntica à de hoje para quem está em `main`.
    try:
        from core.caravan_engine import origin_note as _origin_note
    except Exception:
        _origin_note = None

    if not results:
        lines.append(t(lang, "inv_ores_empty"))
    else:
        for ore, cat in page_items:
            unit_price = ORE_SELL_PER_UNIT.get(cat.tier, 80)
            total_price = unit_price * ore.quantity
            lines.append(f"{cat.emoji} *{_cname(lang, 'ore', cat)}* ×{ore.quantity}")
            lines.append(f"  T{cat.tier} · 🪙 {total_price:,} SS ({unit_price}/unit)")
            _og = _origin_note("ore", int(cat.id), lang, _cont) if _origin_note else None
            if _og and _og.get("line"):
                # `line` já vem localizada do servidor — NUNCA passar por t().
                lines.append(f"  ↳ {_og['line']}")
            lines.append("")
            buttons.append([InlineKeyboardButton(
                f"🪙 {t(lang, 'inv_sell')} {_cname(lang, 'ore', cat)} ×{ore.quantity}",
                callback_data=f"inv_sell_ore_{ore.ore_id}",
            )])
        if total_pages > 1:
            buttons.extend(build_pagination_keyboard(page + 1, total_pages, "inv_tab_ore_", lang))

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_main")])
    await update.callback_query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


# ─── Equipment Tab ────────────────────────────────────────────────────────────

async def _equip_tab(update: Update, lang: str, player_id: int, page: int):
    """Equipment category menu — shows equipped items + category buttons."""
    async with get_session_factory()() as session:
        results = list((await session.execute(
            select(PlayerArtifact, ArtifactCatalog)
            .join(ArtifactCatalog, ArtifactCatalog.id == PlayerArtifact.catalog_id)
            .where(PlayerArtifact.player_id == player_id)
            .order_by(PlayerArtifact.is_equipped.desc(), PlayerArtifact.grade.desc())
        )).all())

    sep = "—" * 20
    lines = [f"⚔️ *{t(lang, 'inv_tab_equip')}*", sep]
    buttons = []

    if not results:
        lines.append(t(lang, "inv_equip_empty"))
    else:
        _GRADE_EMOJIS_TAB = {0: "⬜", 1: "🟡", 2: "🔥", 3: "🟤", 4: "💠", 5: "🌟", 6: "💎", 7: "☯️"}
        # Show currently equipped items
        equipped = [(art, cat) for art, cat in results if art.is_equipped]
        if equipped:
            lines.append(f"*{t(lang, 'inv_equip_equipped_title')}*")
            for art, cat in equipped:
                grade_name = ARTIFACT_GRADES.get(art.grade, f"G{art.grade}")
                grade_emoji = _GRADE_EMOJIS_TAB.get(art.grade, "📦")
                tags = ""
                if art.has_spirit:
                    tags += " ✨"
                if art.enchant_rune:
                    tags += " 🌀"
                slot_icon = {"weapon": "⚔️", "armor": "🛡️"}.get(cat.type, "💍")
                lines.append(f"  {slot_icon} {cat.emoji} *{_cname(lang, 'art', cat)}* ({grade_emoji} {grade_name}){tags}")
            lines.append("")

        # Count per category
        cat_counts = {"weapon": 0, "armor": 0, "accessory": 0}
        for art, cat in results:
            ctype = cat.type if cat.type in cat_counts else "accessory"
            cat_counts[ctype] += 1

        # Category buttons
        cat_info = [
            ("weapon", "⚔️", "inv_equip_cat_weapons"),
            ("armor", "🛡️", "inv_equip_cat_armor"),
            ("accessory", "💍", "inv_equip_cat_accessories"),
        ]
        for cat_key, cat_emoji, locale_key in cat_info:
            count = cat_counts.get(cat_key, 0)
            label = f"{cat_emoji} {t(lang, locale_key)} ({count})"
            buttons.append([InlineKeyboardButton(label, callback_data=f"inv_ecat_{cat_key}_R")])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_main")])
    await update.callback_query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


_GRADE_EMOJIS = {0: "⬜", 1: "🟡", 2: "🔥", 3: "🟤", 4: "💠", 5: "🌟", 6: "💎", 7: "☯️"}


async def _equip_category(update: Update, lang: str, player_id: int, cat_type: str, page: int):
    """Shows artifacts of a specific type as clickable buttons grouped by grade.

    2026-05-23 (owner): items whose ``min_realm`` exceeds the player's realm
    show a 🔒 chip so the player sees at a glance which artifacts they cannot
    equip yet — owner [jogador] report: bought Celestial Aegis Plate (min_realm 8)
    and couldn't equip it without a clear UI signal.
    """
    async with get_session_factory()() as session:
        player_realm = (await session.execute(
            select(Player.realm).where(Player.telegram_id == player_id)
        )).scalar_one_or_none() or 0
        results = list((await session.execute(
            select(PlayerArtifact, ArtifactCatalog)
            .join(ArtifactCatalog, ArtifactCatalog.id == PlayerArtifact.catalog_id)
            .where(
                PlayerArtifact.player_id == player_id,
                ArtifactCatalog.type == cat_type,
            )
            .order_by(PlayerArtifact.is_equipped.desc(), PlayerArtifact.grade.desc())
        )).all())

    cat_labels = {
        "weapon": ("⚔️", "inv_equip_cat_weapons"),
        "armor": ("🛡️", "inv_equip_cat_armor"),
        "accessory": ("💍", "inv_equip_cat_accessories"),
    }
    cat_emoji, cat_locale = cat_labels.get(cat_type, ("📦", "inv_tab_equip"))

    total = len(results)
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(0, min(page - 1, total_pages - 1))
    page_items = results[page * ITEMS_PER_PAGE: (page + 1) * ITEMS_PER_PAGE]

    sep = "—" * 20
    lines = [f"{cat_emoji} *{t(lang, cat_locale)}*  ({total})", sep]
    buttons = []

    if not results:
        lines.append(t(lang, "inv_equip_cat_empty", category=t(lang, cat_locale).lower()))
    else:
        lines.append(t(lang, "inv_equip_tap_to_view"))
        lines.append("")

        current_grade = None
        for art, cat in page_items:
            grade_name = ARTIFACT_GRADES.get(art.grade, f"G{art.grade}")
            grade_emoji = _GRADE_EMOJIS.get(art.grade, "📦")
            # Grade header in text
            if art.grade != current_grade:
                current_grade = art.grade
                lines.append(f"── {grade_emoji} *{grade_name}* ──")

            # Compact text summary
            tags = ""
            if art.is_equipped:
                tags = " ✅"
            if getattr(art, "locked", False):
                tags += " 🔒"
            # Realm gate chip — clarifies BEFORE click which items can't be
            # equipped yet. Owner [jogador] report (2026-05-23): bought R8 armor
            # without realising the gate.
            cat_min_realm = int(getattr(cat, "min_realm", 0) or 0)
            realm_locked = cat_min_realm > 0 and player_realm < cat_min_realm
            if realm_locked:
                tags += f" 🚫R{cat_min_realm}"
            stats = art.custom_stats or {}
            main_stat = ""
            if stats.get("battle_power"):
                main_stat = f"⚔️{stats['battle_power']}"
            elif stats.get("soul_strength"):
                main_stat = f"👻{stats['soul_strength']}"
            elif stats.get("luck"):
                main_stat = f"🍀{stats['luck']}"
            extra = f" +{main_stat}" if main_stat else ""
            lines.append(f"  {cat.emoji} {_cname(lang, 'art', cat)}{extra}{tags}")

            # Each item is a button → opens detail view
            btn_label = f"{grade_emoji} {_cname(lang, 'art', cat)}"
            if art.is_equipped:
                btn_label += " ✅"
            if getattr(art, "locked", False):
                btn_label += " 🔒"
            if realm_locked:
                btn_label += f" 🚫R{cat_min_realm}"
            buttons.append([InlineKeyboardButton(
                btn_label,
                callback_data=f"inv_art_{art.id}",
            )])

        if total_pages > 1:
            buttons.extend(build_pagination_keyboard(page + 1, total_pages, f"inv_ecat_{cat_type}_", lang))

    # Bulk dismantle — only show if player has at least 2 unequipped items here.
    if results:
        unequipped_count = sum(1 for art, _ in results if not art.is_equipped)
        if unequipped_count >= 2:
            buttons.append([InlineKeyboardButton(
                t(lang, "inv_bulk_dismantle_btn"),
                callback_data=f"inv_bulk_dismantle_{cat_type}",
            )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_tab_equip_R")])
    await update.callback_query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def _equip_detail(update: Update, art_id: int):
    """Show detailed view of a single artifact with Equip/Unequip/Dismantle actions."""
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        result = (await session.execute(
            select(PlayerArtifact, ArtifactCatalog)
            .join(ArtifactCatalog, ArtifactCatalog.id == PlayerArtifact.catalog_id)
            .where(
                PlayerArtifact.id == art_id,
                PlayerArtifact.player_id == player.telegram_id,
            )
        )).first()
        if not result:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        art, cat = result
        cat_type = cat.type

    grade_name = ARTIFACT_GRADES.get(art.grade, f"G{art.grade}")
    grade_emoji = _GRADE_EMOJIS.get(art.grade, "📦")
    dismantle_value = DISMANTLE_BY_GRADE.get(art.grade, 50)

    sep = "—" * 20
    lines = [
        f"{cat.emoji} *{_cname(lang, 'art', cat)}*",
        sep,
        f"{t(lang, 'inv_detail_grade')}: {grade_emoji} *{grade_name}*",
        f"{t(lang, 'inv_detail_type')}: {cat_type.capitalize()}",
    ]

    if art.is_equipped:
        lines.append(f"✅ *{t(lang, 'inv_detail_equipped')}*")
    if getattr(art, "locked", False):
        lines.append(f"🔒 *{t(lang, 'inv_detail_locked')}*")

    # Min realm requirement — show whether the player ACTUALLY meets it,
    # not just the threshold. Owner request 2026-05-23 after [jogador] bought
    # a Mahayana-gated armor below R8 and got cryptic equip alert.
    min_realm = getattr(cat, 'min_realm', 0) or 0
    if min_realm > 0:
        realm_name = REALM_NAMES[min(min_realm, len(REALM_NAMES) - 1)]
        cur_realm_idx = int(getattr(player, "realm", 0) or 0)
        cur_realm_name = REALM_NAMES[min(cur_realm_idx, len(REALM_NAMES) - 1)]
        if cur_realm_idx >= min_realm:
            lines.append(f"✅ {t(lang, 'inv_detail_min_realm')}: {realm_name}")
        else:
            lines.append(t(
                lang, "inv_detail_realm_locked",
                required=realm_name, current=cur_realm_name,
            ))

    lines.append("")

    # Stats
    stats = art.custom_stats or {}
    if stats.get("battle_power"):
        lines.append(f"  ⚔️ BP: +{format_number(stats['battle_power'])}")
    if stats.get("soul_strength"):
        lines.append(f"  👻 Soul: +{format_number(stats['soul_strength'])}")
    if stats.get("luck"):
        lines.append(f"  🍀 Luck: +{format_number(stats['luck'])}")
    if stats.get("perception"):
        lines.append(f"  🔮 Perception: +{format_number(stats['perception'])}")
    if stats.get("hp"):
        lines.append(f"  ❤️ HP: +{format_number(stats['hp'])}")

    # Special properties
    if art.has_spirit:
        lines.append(f"\n  ✨ {t(lang, 'inv_detail_spirit')}: {art.spirit_name or '???'}")
    if art.enchant_rune:
        lines.append(f"  🌀 {t(lang, 'inv_detail_enchant')}: {art.enchant_rune}")

    lines.append("")
    lines.append(f"🔨 {t(lang, 'inv_detail_dismantle_value')}: {format_number(dismantle_value)} 💰")

    # Action buttons
    action_buttons = []
    is_locked = getattr(art, "locked", False)
    if art.is_equipped:
        action_buttons.append([InlineKeyboardButton(
            f"📤 {t(lang, 'inv_unequip')}",
            callback_data=f"inv_unequip_{art.id}",
        )])
    elif is_locked:
        # Locked items cannot be dismantled — only unlock or equip.
        action_buttons.append([
            InlineKeyboardButton(
                f"⚔️ {t(lang, 'inv_equip')}",
                callback_data=f"inv_equip_{art.id}",
            ),
            InlineKeyboardButton(
                f"🔓 {t(lang, 'inv_unlock_btn')}",
                callback_data=f"inv_lock_{art.id}",
            ),
        ])
    else:
        action_buttons.append([
            InlineKeyboardButton(
                f"⚔️ {t(lang, 'inv_equip')}",
                callback_data=f"inv_equip_{art.id}",
            ),
            InlineKeyboardButton(
                f"🔒 {t(lang, 'inv_lock_btn')}",
                callback_data=f"inv_lock_{art.id}",
            ),
        ])
        action_buttons.append([InlineKeyboardButton(
            f"🔨 {t(lang, 'inv_dismantle_btn')}",
            callback_data=f"inv_dismantle_{art.id}",
        )])

    action_buttons.append([InlineKeyboardButton(
        t(lang, "btn_back"),
        callback_data=f"inv_ecat_{cat_type}_R",
    )])

    await query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(action_buttons),
    )


# ─── Techniques Tab ──────────────────────────────────────────────────────────

async def _tech_tab(update: Update, lang: str, player_id: int, page: int):
    from core.combat_engine import get_mastery_stage

    async with get_session_factory()() as session:
        # Unlearned scrolls in inventory
        scrolls = list((await session.execute(
            select(PlayerInventory, TechniqueCatalog)
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerInventory.item_id)
            .where(
                PlayerInventory.player_id == player_id,
                PlayerInventory.item_type == "technique_scroll",
                PlayerInventory.quantity > 0,
            )
            .order_by(TechniqueCatalog.req_realm, TechniqueCatalog.id)
        )).all())

        # Learned techniques
        learned = list((await session.execute(
            select(PlayerTechnique, TechniqueCatalog)
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
            .where(PlayerTechnique.player_id == player_id)
            .order_by(TechniqueCatalog.req_realm)
        )).all())

        known_ids = {pt.technique_id for pt, _ in learned}

    sep = "—" * 20
    lines = [f"📜 *{t(lang, 'inv_tab_tech')}*", sep]
    buttons = []

    # Section 1: Learned techniques summary
    if learned:
        lines.append(f"*{t(lang, 'inv_tech_learned_title')}* ({len(learned)})")
        for pt, tech in learned:
            stage = get_mastery_stage(pt.mastery_level)
            active_icon = " ⚔️" if pt.is_active_combat else ""
            lines.append(f"  {tech.emoji} {_cname(lang, 'tech', tech)} — {stage['emoji']} Lv{pt.mastery_level}{active_icon}")
        lines.append("")
        buttons.append([InlineKeyboardButton(
            f"⚔️ {t(lang, 'inv_tech_manage')}",
            callback_data="pvp_techniques_menu",
        )])
    lines.append(sep)

    # Section 2: Scrolls to learn
    if not scrolls:
        lines.append(t(lang, "inv_tech_scrolls_empty"))
    else:
        lines.append(f"*{t(lang, 'inv_tech_scrolls_title')}* ({len(scrolls)})")
        lines.append("")
        total = len(scrolls)
        total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
        page = max(0, min(page - 1, total_pages - 1))
        page_items = scrolls[page * ITEMS_PER_PAGE: (page + 1) * ITEMS_PER_PAGE]

        for inv, tech in page_items:
            realm_name = (
                REALM_NAMES[tech.req_realm]
                if tech.req_realm < len(REALM_NAMES)
                else f"R{tech.req_realm}"
            )
            already = tech.id in known_ids
            known_tag = " ✅" if already else ""
            lines.append(f"{tech.emoji} *{_cname(lang, 'tech', tech)}*{known_tag} ×{inv.quantity}")
            lines.append(f"  _{_cdesc(lang, 'tech', tech)}_")
            lines.append(f"  Req: {realm_name} | {tech.element}")
            lines.append("")
            if already:
                buttons.append([InlineKeyboardButton(
                    f"✅ {_cname(lang, 'tech', tech)} ({t(lang, 'inv_tech_known')})",
                    callback_data="inv_noop",
                )])
            else:
                buttons.append([InlineKeyboardButton(
                    f"📖 {t(lang, 'inv_learn_tech')} {_cname(lang, 'tech', tech)}",
                    callback_data=f"inv_learn_{tech.id}",
                )])
        if total_pages > 1:
            buttons.extend(build_pagination_keyboard(page + 1, total_pages, "inv_tab_tech_", lang))

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_main")])
    await update.callback_query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


# ─── Misc Tab ────────────────────────────────────────────────────────────────

async def _misc_tab(update: Update, lang: str, player_id: int, page: int):
    async with get_session_factory()() as session:
        results = list((await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == player_id,
                PlayerInventory.item_type.notin_(["pill", "herb", "technique_scroll"]),
                PlayerInventory.quantity > 0,
            )
            .order_by(PlayerInventory.item_type, PlayerInventory.item_id)
        )).scalars().all())

    total = len(results)
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(0, min(page - 1, total_pages - 1))
    page_items = results[page * ITEMS_PER_PAGE: (page + 1) * ITEMS_PER_PAGE]

    sep = "—" * 20
    lines = [f"📦 *{t(lang, 'inv_tab_misc')}*", sep]
    buttons = []

    if not results:
        lines.append(t(lang, "inv_misc_empty"))
    else:
        # D-4 (v14.2): every misc item type renders with a name + per-type Use
        # button. `inv.id` is the PlayerInventory PK and uniquely identifies
        # the row to act on (callback fits in 64 bytes: `inv_misc_<id>`).
        for inv in page_items:
            # 🎒 3.2 — o nome do DONO, na língua do jogador (o do pacote de
            # minério já traz o tier: "Pacote de Minério T3").
            emoji = _itens.emoji(inv.item_type)
            name = _itens.nome(lang, inv.item_type, inv.item_id)
            lines.append(f"{emoji} *{name}* ×{inv.quantity}")
            action = _MISC_ACTIONS.get(inv.item_type)
            if action:
                label = t(lang, action["label_key"])
                if action["kind"] == "deeplink":
                    cb = action["callback"]
                else:
                    cb = f"inv_misc_{inv.id}"
                buttons.append([InlineKeyboardButton(f"{emoji} {label}", callback_data=cb)])
        if total_pages > 1:
            buttons.extend(build_pagination_keyboard(page + 1, total_pages, "inv_tab_misc_", lang))

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_main")])
    await update.callback_query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


# ─── Action: Use Misc Item (D-4 v14.2) ──────────────────────────────────────

async def _do_use_misc(update: Update, inv_id: int):
    """Dispatch to core.inventory_actions based on PlayerInventory.item_type.
    Renders a result panel + Back button. Source of truth: core/inventory_actions.py.
    """
    from core.inventory_actions import (
        study_blueprint, open_ore_pack, learn_pill_recipe, open_mystery_box,
    )

    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        inv = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.id == inv_id,
                PlayerInventory.player_id == player.telegram_id,
                PlayerInventory.quantity > 0,
            )
        )).scalar_one_or_none()
        if not inv:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        action = _MISC_ACTIONS.get(inv.item_type)
        if not action or action["kind"] != "use":
            await safe_answer(query, t(lang, "inv_misc_no_action"), show_alert=True)
            return

        emoji = _itens.emoji(inv.item_type)
        name = _itens.nome(lang, inv.item_type, inv.item_id)

        try:
            if inv.item_type == "blueprint":
                result = await study_blueprint(session, player, inv)
            elif inv.item_type == "ore_pack":
                result = await open_ore_pack(session, player, inv)
            elif inv.item_type == "pill_recipe_scroll":
                result = await learn_pill_recipe(session, player, inv)
            elif inv.item_type == "mystery_box":
                result = await open_mystery_box(session, player, inv)
            else:
                await safe_answer(query, t(lang, "inv_misc_no_action"), show_alert=True)
                return
        except Exception as e:
            logger.exception("misc action failed: %s", e)
            await session.rollback()
            await safe_answer(query, t(lang, "inv_misc_action_failed"), show_alert=True)
            return

        if not result.get("ok"):
            await session.rollback()
            await safe_answer(query, t(lang, "inv_misc_action_failed"), show_alert=True)
            return

        await session.commit()

    # Render result panel (Telegram channel, after session closes).
    sep = "—" * 20
    lines = [f"{emoji} *{t(lang, 'inv_misc_action_used', name=escape_markdown(name))}*", sep]

    if result["kind"] == "blueprint":
        lines.append(t(lang, "inv_misc_result_blueprint",
                       xp=result["xp_gained"], total_xp=result["new_xp"]))
        if result.get("leveled_up"):
            lines.append(t(lang, "inv_misc_result_blueprint_levelup",
                           tier=result["forge_tier"]))
    elif result["kind"] == "ore_pack":
        lines.append(t(lang, "inv_misc_result_ore_pack",
                       count=result["total_rolls"], tier=result["tier"]))
        for g in result["granted"]:
            lines.append(f"  {g['emoji']} {g['name']} ×{g['qty']}")
    elif result["kind"] == "pill_recipe_scroll":
        if result.get("all_known"):
            refund = result.get("refund")
            if refund:
                lines.append(t(lang, "inv_misc_result_scroll_all_known_refund",
                               emoji=refund["emoji"], name=refund["name"], qty=refund["qty"]))
            else:
                lines.append(t(lang, "inv_misc_result_scroll_all_known"))
        else:
            pill = result["pill"]
            lines.append(t(lang, "inv_misc_result_scroll_unlocked",
                           emoji=pill["emoji"], name=pill["name"], tier=pill["tier"]))
    elif result["kind"] == "mystery_box":
        rt = result["result"]
        if rt == "stones":
            lines.append(t(lang, "inv_misc_result_box_stones", amount=result["amount"]))
        elif rt == "herb":
            lines.append(t(lang, "inv_misc_result_box_herb",
                           emoji=result["emoji"], name=result["name"], qty=result["qty"]))
        elif rt == "pill":
            lines.append(t(lang, "inv_misc_result_box_pill",
                           emoji=result["emoji"], name=result["name"]))

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_tab_misc_R")],
    ])
    await safe_answer(query)
    try:
        await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.warning("misc result render failed: %s", e)


# ─── Ring Info / Upgrade ─────────────────────────────────────────────────────

async def _ring_info(update: Update, lang: str, player_id: int):
    async with get_session_factory()() as session:
        ring = await _get_or_create_ring(session, player_id)
        player = await _get_player(player_id, session)
        await session.commit()

    sep = "—" * 22
    lines = [
        t(lang, "inv_ring_upgrade_title"),
        sep,
        t(lang, "inv_ring_tier_desc", tier=ring.tier, max=ring.max_slots),
        "",
    ]
    for tier, slots in RING_MAX_SLOTS.items():
        marker = " ◄" if tier == ring.tier else ""
        if tier == 1:
            lines.append(f"  T{tier}: {slots} slots{marker}")
        else:
            cost = RING_UPGRADE_STONES.get(tier - 1, 0)
            lines.append(f"  T{tier}: {slots} slots  _(upgrade: {cost:,} SS)_{marker}")
    lines.append(sep)

    buttons = []
    if ring.tier < MAX_RING_TIER:
        next_tier = ring.tier + 1
        cost = RING_UPGRADE_STONES[ring.tier]
        # 🎒 3.2 — era `RING_MAX_SLOTS[next_tier]`, o máximo ABSOLUTO do tier:
        # a quem comprou lugares no Pavilhão o botão anunciava 1000 e a
        # expansão (aditiva) dava 1010. Agora o anúncio é a conta que a
        # expansão faz — o mesmo dono (medido 30/09: 1 anel no `main`).
        next_max = _anel.proximo_max(ring.tier, ring.max_slots)
        stones = player.spirit_stones if player else 0
        if stones >= cost:
            buttons.append([InlineKeyboardButton(
                t(lang, "inv_ring_upgrade_btn", next=next_tier, max=next_max, cost=cost),
                callback_data="inv_ring_upgrade",
            )])
        else:
            lines.append(t(lang, "inv_not_enough_stones", need=cost, have=stones))
    else:
        lines.append(t(lang, "inv_ring_max"))

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_main")])
    await update.callback_query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


# ─── Action: Bulk Use Pill (H-9) ───────────────────────────────────────────

async def _do_use_pill_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE, pill_id: int, quality: str, count: int):
    """Apply the same stat-boost pill up to `count` times (skips pills capped by medicine resistance)."""
    query = update.callback_query
    if count <= 0 or count > 50:
        await safe_answer(query)
        return

    applied = 0
    capped = 0
    no_stock = 0
    last_effect = None
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        pill = (await session.execute(
            select(PillCatalog).where(PillCatalog.id == pill_id)
        )).scalar_one_or_none()
        if not pill:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        # QoL-Feedback 07/08 (report [jogador]): *"can't use multiple pills at
        # once … it's stressful when one is willing to use about a thousand to
        # replenish chi"*. O lote existia e estava trancado a `stat_boost` —
        # cobertura que ficou pela metade, não limitação de design. Abre para os
        # consumíveis de REPOSIÇÃO (`BULK_REFILL_TYPES`), que é exatamente onde
        # mil unidades fazem sentido. Tudo o mais continua recusado na porta.
        from core.alchemy_engine import (
            BULK_REFILL_TYPES, refill_cap_state, stat_boost_cap_state,
        )
        _is_refill = pill.effect_type in BULK_REFILL_TYPES
        if pill.effect_type != "stat_boost" and not _is_refill:
            await safe_answer(query, t(lang, "inv_pill_bulk_not_supported"), show_alert=True)
            return

        cap_stop = None
        refill_stop = None
        for _ in range(count):
            # QoL-Feedback 2 2026-07-30 (report [jogador]): checar o cap ANTES do
            # débito de cada iteração — atingiu o teto no meio do lote, as
            # restantes ficam no anel (antes eram queimadas com efeito zero).
            # 07/08: a mesma disciplina para o qi/HP — a peça (`at_cap` com
            # `value: 0`) já existia no apply; só não era consultada ANTES.
            if _is_refill:
                _rs = await refill_cap_state(session, player, pill)
                if _rs and _rs["at_cap"]:
                    refill_stop = _rs
                    break
            _cs = stat_boost_cap_state(player, pill, quality)
            if _cs and _cs["at_cap"]:
                cap_stop = _cs
                break
            upd = (
                sa_update(PlayerInventory)
                .where(
                    PlayerInventory.player_id == player.telegram_id,
                    PlayerInventory.item_type == "pill",
                    PlayerInventory.item_id == pill_id,
                    PlayerInventory.quality == quality,
                    PlayerInventory.quantity > 0,
                )
                .values(quantity=PlayerInventory.quantity - 1)
                .returning(PlayerInventory.quantity)
            )
            new_quantity = (await session.execute(upd)).scalar_one_or_none()
            if new_quantity is None:
                no_stock += 1
                break
            if new_quantity == 0:
                await session.execute(
                    delete(PlayerInventory).where(
                        PlayerInventory.player_id == player.telegram_id,
                        PlayerInventory.item_type == "pill",
                        PlayerInventory.item_id == pill_id,
                        PlayerInventory.quality == quality,
                    )
                )

            effectiveness = await get_pill_effectiveness(session, player.telegram_id, pill)
            await increment_pill_usage(session, player.telegram_id, pill)
            effect_result = await apply_pill_effect(session, player, pill, quality, effectiveness=effectiveness)
            last_effect = effect_result
            if effect_result.get("at_cap"):
                capped += 1
            else:
                applied += 1

        from core.quest_engine import track_quest
        if applied > 0:
            # QoL-relatos — o lote é de UMA pílula só, logo o tier é uniforme; o
            # `applied` continua a ser só o contador (nunca o peso).
            await track_quest(session, player.telegram_id, "use_pill", applied,
                              prof_weight_tier=pill.required_alchemy_tier)
        await session.commit()

    if cap_stop and applied == 0 and capped == 0 and no_stock == 0:
        # Já estava no teto ao tocar — nada foi consumido.
        msg = t(lang, "pill_stat_at_cap_kept", stat=cap_stop["stat"], cap=cap_stop["cap"])
    elif refill_stop and applied == 0 and capped == 0 and no_stock == 0:
        # Já estava cheio AO TOCAR — nenhuma pílula saiu do anel. Key PRÓPRIA:
        # reusar a de "encheu no meio do caminho" com used=0 era dizer duas
        # coisas falsas ao mesmo tempo (o irmão `stat_boost` já tinha key
        # própria para este estado; a reposição tinha ficado sem).
        msg = t(lang, "pill_hp_full_kept" if refill_stop["kind"] == "hp"
                      else "pill_qi_full_kept")
    else:
        msg = t(lang, "inv_pill_bulk_summary",
                applied=applied, capped=capped,
                pill=escape_markdown(_cname(lang, "pill", pill)))
        if cap_stop:
            msg += "\n" + t(lang, "pill_stat_at_cap_kept",
                            stat=cap_stop["stat"], cap=cap_stop["cap"])
        if refill_stop:
            # Lei §1 — o lote NUNCA some em silêncio: diz o que entrou e o que
            # ficou. `left` é o que o lote não chegou a consumir, não o estoque.
            msg += "\n" + t(lang, "inv_pill_bulk_cap_stop",
                            used=applied + capped,
                            left=max(0, count - applied - capped))
    await safe_answer(query, msg, show_alert=True)
    await _pills_tab(update, lang, player.telegram_id, 1)


# ─── Action: Use Pill (native) ─────────────────────────────────────────────

async def _do_use_pill(update: Update, context: ContextTypes.DEFAULT_TYPE, pill_id: int, quality: str):
    query = update.callback_query
    async with get_session_factory()() as session:
        # Onda 5 Fase 2 review: lock the player FOR UPDATE — every timed-buff
        # WRITER must serialize on this lock (the mini-app pill endpoint and
        # formation activation already do), otherwise two concurrent same-type
        # writers both pass their conflict checks and the buffs stack.
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            return
        lang = player.language or "en"

        pill = (await session.execute(
            select(PillCatalog).where(PillCatalog.id == pill_id)
        )).scalar_one_or_none()
        if not pill:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        # Check for active buff of the same type
        if pill.effect_type not in ("cb_instant", "stat_boost", "hp_restore"):
            from core.formation_engine import FORMATION_PILL_COEXIST_TYPES
            active_buffs = await get_active_buffs(session, player.telegram_id)
            for buff in active_buffs:
                if buff.buff_type == pill.effect_type:
                    # A Formação row of a coexist type (qi_regen_boost) does
                    # NOT block the pill — they live as separate rows and the
                    # tick's D-2 diminishing stack governs the pair ([jogador]
                    # 2026-06-11: matrix locked the qi pill out).
                    if (pill.effect_type in FORMATION_PILL_COEXIST_TYPES
                            and (buff.source or "").startswith("formation:")):
                        continue
                    remaining = (buff.expires_at - datetime.now(timezone.utc)).total_seconds()
                    await safe_answer(query,
                        t(lang, "alch_buff_already_active", time=get_time_display(remaining)),
                        show_alert=True,
                    )
                    return

        # QoL-Feedback 2 2026-07-30 (report [jogador]): no cap a pílula era debitada
        # e o apply devolvia at_cap sem efeito — item queimado. Checar ANTES
        # do débito; a recusa diz o cap e que NADA foi consumido (Lei §1).
        from core.alchemy_engine import stat_boost_cap_state
        _cs = stat_boost_cap_state(player, pill, quality)
        if _cs and _cs["at_cap"]:
            await safe_answer(query, t(lang, "pill_stat_at_cap_kept",
                                       stat=_cs["stat"], cap=_cs["cap"]),
                              show_alert=True)
            return

        # Review adversarial 03/08 — mesma disciplina para as pílulas de
        # fundação: sobre fundação Sagrada (ou sem fundação, na id 34) o apply
        # é no-op e o item era queimado. Recusa nomeada, zero consumo (Lei §1).
        from core.foundation_engine import foundation_pill_block_reason
        _fb = foundation_pill_block_reason(player.foundation_quality, pill.effect_type)
        if _fb:
            await safe_answer(query, t(lang, f"pill_{_fb}"), show_alert=True)
            return

        # QoL 07/08 — review adversarial: o guard de reposição nasceu no LOTE e
        # no mini, e deixou este caminho de fora. Resultado: nesta mesma tela o
        # "💊 Usar" queimava a pílula com o dantian cheio enquanto o "×5" ao
        # lado a devolvia, e o mini recusava o MESMO toque. Duas políticas para
        # o mesmo gesto — pior do que o defeito original. Mesmo helper, mesma
        # verdade, antes do débito (a id 30 continua a passar: teto ×1.10).
        from core.alchemy_engine import refill_cap_state as _refill_state
        _rs = await _refill_state(session, player, pill)
        if _rs and _rs["at_cap"]:
            await safe_answer(query, t(lang, "pill_hp_full_kept" if _rs["kind"] == "hp"
                                             else "pill_qi_full_kept"), show_alert=True)
            return

        # Atomic decrement — guards against double-tap race condition
        upd = (
            sa_update(PlayerInventory)
            .where(
                PlayerInventory.player_id == player.telegram_id,
                PlayerInventory.item_type == "pill",
                PlayerInventory.item_id == pill_id,
                PlayerInventory.quality == quality,
                PlayerInventory.quantity > 0,
            )
            .values(quantity=PlayerInventory.quantity - 1)
            .returning(PlayerInventory.quantity)
        )
        new_quantity = (await session.execute(upd)).scalar_one_or_none()
        if new_quantity is None:
            await safe_answer(query, t(lang, "alch_no_pills"), show_alert=True)
            return
        if new_quantity == 0:
            await session.execute(
                delete(PlayerInventory).where(
                    PlayerInventory.player_id == player.telegram_id,
                    PlayerInventory.item_type == "pill",
                    PlayerInventory.item_id == pill_id,
                    PlayerInventory.quality == quality,
                )
            )

        effectiveness = await get_pill_effectiveness(session, player.telegram_id, pill)
        await increment_pill_usage(session, player.telegram_id, pill)
        effect_result = await apply_pill_effect(session, player, pill, quality, effectiveness=effectiveness)
        from core.achievement_engine import check_achievements
        pill_ach = await check_achievements(session, player.telegram_id, "pills_consumed", 1)
        from core.quest_engine import track_quest
        # QoL-relatos — 🩺 médico: peso pelo tier da pílula usada.
        await track_quest(session, player.telegram_id, "use_pill", 1,
                          prof_weight_tier=pill.required_alchemy_tier)
        await session.commit()
        if pill_ach:
            from handlers.achievements import notify_achievements
            await notify_achievements(context, update.effective_user.id, pill_ach)

    await safe_answer(query)
    separator = "—" * 24
    quality_tag = f" ({quality.upper()})" if quality != "normal" else ""

    lines = [
        t(lang, "alch_pill_used", pill_name=escape_markdown(_cname(lang, "pill", pill)), quality=quality_tag),
        separator,
    ]

    if effect_result["type"] == "stat_boost":
        safe_stat = escape_markdown(str(effect_result.get("stat", "")))
        if effect_result.get("at_cap"):
            lines.append(t(lang, "pill_stat_at_cap", stat=safe_stat, cap=effect_result["cap"]))
        else:
            lines.append(t(lang, "pill_stat_boost", stat=safe_stat, gain=effect_result["gain"], new=effect_result["new_value"]))
    elif effect_result["type"] == "cb_instant":
        lines.append(t(lang, "alch_effect_cb_instant", value=format_number(effect_result["value"])))
    elif effect_result["type"] == "cb_boost":
        lines.append(t(lang, "alch_effect_cb_boost",
                        value=f"{(effect_result['value'] - 1) * 100:.0f}",
                        duration=effect_result["duration_minutes"]))
    elif effect_result["type"] == "soul_boost":
        lines.append(t(lang, "alch_effect_soul_boost",
                        value=f"{(effect_result['value'] - 1) * 100:.0f}",
                        duration=effect_result["duration_minutes"]))
    elif effect_result["type"] == "breakthrough_boost":
        lines.append(t(lang, "alch_effect_breakthrough",
                        value=f"{(effect_result['value'] - 1) * 100:.0f}",
                        duration=effect_result["duration_minutes"]))
    elif effect_result["type"] == "qi_capacity":
        lines.append(t(lang, "alch_effect_qi_capacity", value=format_number(effect_result["value"])))
    elif effect_result["type"] == "qi_restore":
        if effect_result.get("at_cap"):
            lines.append(t(lang, "pill_effect_qi_restore_at_cap"))
        else:
            lines.append(t(lang, "pill_effect_qi_restore", value=format_number(effect_result["value"])))
    elif effect_result["type"] == "purity_boost":
        lines.append(t(lang, "pill_effect_purity", value=format_number(effect_result["value"])))
    elif effect_result["type"] == "revive":
        lines.append(t(lang, "pill_effect_revive"))
    elif effect_result["type"] == "all_boost":
        lines.append(t(lang, "pill_effect_all_boost",
                        value=effect_result["value"] - 1,
                        duration=effect_result["duration_minutes"]))
    elif effect_result["type"] == "bp_boost":
        lines.append(t(lang, "pill_effect_bp_boost",
                        value=effect_result.get("value", 1.0) - 1,
                        duration=effect_result.get("duration_minutes", 60)))
    elif effect_result["type"] == "perception_boost":
        lines.append(t(lang, "pill_effect_perception_boost",
                        value=effect_result.get("value", 1.0) - 1,
                        duration=effect_result.get("duration_minutes", 60)))
    elif effect_result["type"] == "qi_regen_boost":
        # N-27 (Sprint v14.3): D-2 pills (Vortex/Heavenly Spring/Eternal River)
        # were silent — no result branch existed, so consumed pills showed only
        # the title + flavor with empty body. Multiple players reported
        # 2026-05-07/08: "usei pílula e não aparece nada".
        lines.append(t(lang, "pill_effect_qi_regen_boost",
                        value=effect_result.get("value", 1.0) - 1,
                        duration=effect_result.get("duration_minutes", 60)))
    elif effect_result["type"] == "defense_boost":
        lines.append(t(lang, "pill_effect_defense_boost",
                        value=effect_result.get("value", 1.0) - 1,
                        duration=effect_result.get("duration_minutes", 60)))
    elif effect_result["type"] == "luck_boost":
        lines.append(t(lang, "pill_effect_luck_boost",
                        value=effect_result.get("value", 1.0) - 1,
                        duration=effect_result.get("duration_minutes", 60)))
    elif effect_result["type"] == "dao_fragment_chance":
        lines.append(t(lang, "pill_effect_dao_chance",
                        value=effect_result["value"],
                        duration=effect_result["duration_minutes"]))
    elif effect_result["type"] == "hp_restore":
        lines.append(t(lang, "pill_effect_hp_restore", value=format_number(effect_result["value"]), pct=effect_result["pct"]))
        if effect_result.get("shield"):
            lines.append(t(lang, "pill_effect_hp_shield", value=format_number(effect_result["shield"])))
    elif effect_result["type"] == "eternal_foundation_reroll":
        # v14.4 D-1c — same flavor as alch_craft_result for parity.
        from core.foundation_engine import FOUNDATION_QUALITIES
        old_label = t(lang, FOUNDATION_QUALITIES.get(effect_result["old"], FOUNDATION_QUALITIES["low"])["label_key"]) if effect_result.get("old") else "—"
        new_label = t(lang, FOUNDATION_QUALITIES.get(effect_result["new"], FOUNDATION_QUALITIES["low"])["label_key"])
        # Review adversarial 03/08 — `old == new` é o resultado MAIS PROVÁVEL
        # (70% numa divine sobre fundação Perfeita) e era anunciado como
        # "🌌 Fundação Reforjada!": a queixa original ("no visible changes") com
        # celebração falsa por cima. E o downgrade PERMANENTE vinha igual ao
        # ganho. Agora a direção manda no texto (fonte: foundation_delta).
        _dir = effect_result.get("direction")
        if effect_result.get("sacred_awakened"):
            lines.append(t(lang, "pill_effect_eternal_sacred", old=old_label, new=new_label))
        elif _dir == "same":
            lines.append(t(lang, "pill_effect_eternal_same", quality=new_label,
                           mult=f"{float(effect_result.get('new_mult', 1.0)):.2f}"))
        elif _dir == "down":
            lines.append(t(lang, "pill_effect_eternal_down", old=old_label, new=new_label,
                           old_mult=f"{float(effect_result.get('old_mult', 1.0)):.2f}",
                           new_mult=f"{float(effect_result.get('new_mult', 1.0)):.2f}"))
        else:
            lines.append(t(lang, "pill_effect_eternal_reroll", old=old_label, new=new_label))
            lines.append(t(lang, "pill_effect_eternal_mult",
                           old_mult=f"{float(effect_result.get('old_mult', 1.0)):.2f}",
                           new_mult=f"{float(effect_result.get('new_mult', 1.0)):.2f}"))
    elif effect_result["type"] == "foundation_reroll":
        if effect_result.get("rerolled"):
            from core.foundation_engine import FOUNDATION_QUALITIES as _FQ2
            _ol = t(lang, _FQ2.get(effect_result.get("old"), _FQ2["low"])["label_key"]) if effect_result.get("old") else "—"
            _nl = t(lang, _FQ2.get(effect_result.get("new"), _FQ2["low"])["label_key"])
            _d2 = effect_result.get("direction")
            if _d2 == "same":
                lines.append(t(lang, "pill_effect_eternal_same", quality=_nl,
                               mult=f"{float(effect_result.get('new_mult', 1.0)):.2f}"))
            elif _d2 == "down":
                lines.append(t(lang, "pill_effect_eternal_down", old=_ol, new=_nl,
                               old_mult=f"{float(effect_result.get('old_mult', 1.0)):.2f}",
                               new_mult=f"{float(effect_result.get('new_mult', 1.0)):.2f}"))
            else:
                lines.append(t(lang, "pill_effect_foundation_reroll",
                                old=_ol, new=_nl))
        elif effect_result.get("reason") == "sacred_protected":
            lines.append(t(lang, "pill_effect_foundation_reroll_sacred"))
        else:
            lines.append(t(lang, "pill_effect_foundation_reroll_na"))

    if effectiveness < 1.0:
        pct = int(effectiveness * 100)
        lines.append(t(lang, "pill_effect_reduced", pct=pct))
    lines.append(separator)
    lines.append(t(lang, "alch_pill_consumed_flavor"))

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💊 {t(lang, 'inv_tab_pills')}", callback_data="inv_tab_pill_R")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_main")],
    ])

    await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


# ─── Action: Equip Artifact (native) ───────────────────────────────────────

async def _do_equip(update: Update, art_id: int):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        res = (await session.execute(
            select(PlayerArtifact, ArtifactCatalog)
            .join(ArtifactCatalog)
            .where(
                PlayerArtifact.id == art_id,
                PlayerArtifact.player_id == player.telegram_id,
            )
        )).first()
        if not res:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        art, cat = res

        # Check min_realm requirement
        if hasattr(cat, 'min_realm') and getattr(cat, 'min_realm', 0) > 0:
            if player.realm < cat.min_realm:
                from config import REALM_NAMES
                realm_name = REALM_NAMES[cat.min_realm] if cat.min_realm < len(REALM_NAMES) else f"Realm {cat.min_realm}"
                await safe_answer(query, t(lang, "art_realm_too_low", realm=realm_name), show_alert=True)
                return

        slot = cat.type
        if slot == "accessory":
            acc1 = (await session.execute(
                select(PlayerArtifact).where(
                    PlayerArtifact.player_id == player.telegram_id,
                    PlayerArtifact.slot == "accessory1",
                    PlayerArtifact.is_equipped == True,
                )
            )).scalar_one_or_none()
            slot = "accessory1" if not acc1 else "accessory2"

        # Unequip whatever is currently in that slot
        await session.execute(
            sa_update(PlayerArtifact).where(
                PlayerArtifact.player_id == player.telegram_id,
                PlayerArtifact.slot == slot,
                PlayerArtifact.is_equipped == True,
            ).values(is_equipped=False, slot=None)
        )

        art.is_equipped = True
        art.slot = slot
        await session.commit()

    await safe_answer(query, t(lang, "art_equipped_alert", name=_cname(lang, "art", cat)), show_alert=True)
    await _equip_detail(update, art_id)


# ─── Action: Unequip Artifact (native) ─────────────────────────────────────

async def _do_unequip(update: Update, art_id: int):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        res = (await session.execute(
            select(PlayerArtifact, ArtifactCatalog)
            .join(ArtifactCatalog)
            .where(
                PlayerArtifact.id == art_id,
                PlayerArtifact.player_id == player.telegram_id,
                PlayerArtifact.is_equipped == True,
            )
        )).first()
        if not res:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        art, cat = res
        art.is_equipped = False
        art.slot = None
        await session.commit()

    await safe_answer(query, t(lang, "art_unequipped_alert", slot=""), show_alert=True)
    await _equip_detail(update, art_id)


# ─── Action: Sell Herb ───────────────────────────────────────────────────────

async def _do_sell_herb(update: Update, inv_id: int):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        inv = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.id == inv_id,
                PlayerInventory.player_id == player.telegram_id,
                PlayerInventory.item_type == "herb",
                PlayerInventory.quantity > 0,
            )
        )).scalar_one_or_none()
        if not inv:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        herb = (await session.execute(
            select(HerbCatalog).where(HerbCatalog.id == inv.item_id)
        )).scalar_one_or_none()
        if not herb:
            await safe_answer(query, "❌ Item not found.", show_alert=True)
            return

        qty = inv.quantity
        sell_price = max(1, int(herb.base_price * HERB_SELL_RATIO)) * qty
        player.spirit_stones += sell_price
        await session.delete(inv)
        await session.commit()

    await safe_answer(query, 
        t(lang, "inv_sold", name=_cname(lang, "herb", herb), qty=qty, price=sell_price),
        show_alert=True,
    )
    await _herbs_tab(update, lang, player.telegram_id, 1)


# ─── Action: Sell Ore ────────────────────────────────────────────────────────

async def _do_sell_ore(update: Update, ore_id: int):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        result = (await session.execute(
            select(PlayerOre, OreCatalog)
            .join(OreCatalog, OreCatalog.id == PlayerOre.ore_id)
            .where(
                PlayerOre.player_id == player.telegram_id,
                PlayerOre.ore_id == ore_id,
                PlayerOre.quantity > 0,
            )
        )).first()
        if not result:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        player_ore, cat = result
        qty = player_ore.quantity
        unit_price = ORE_SELL_PER_UNIT.get(cat.tier, 80)
        sell_price = unit_price * qty
        player.spirit_stones += sell_price
        player_ore.quantity = 0
        await session.commit()

    await safe_answer(query, 
        t(lang, "inv_sold", name=_cname(lang, "ore", cat), qty=qty, price=sell_price),
        show_alert=True,
    )
    await _ores_tab(update, lang, player.telegram_id, 1)


# ─── Action: Lock / Unlock artifact (H-8) ───────────────────────────────────

async def _toggle_lock(update: Update, art_id: int):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        art = (await session.execute(
            select(PlayerArtifact).where(
                PlayerArtifact.id == art_id,
                PlayerArtifact.player_id == player.telegram_id,
            )
        )).scalar_one_or_none()
        if not art:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        new_state = not getattr(art, "locked", False)
        art.locked = new_state
        await session.commit()

    msg = t(lang, "inv_locked") if new_state else t(lang, "inv_unlocked")
    await safe_answer(query, msg, show_alert=False)
    await _equip_detail(update, art_id)


# ─── Action: Dismantle Confirmation Screen ──────────────────────────────────

async def _dismantle_confirm(update: Update, art_id: int):
    """Show a confirmation screen with item details before dismantling."""
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        result = (await session.execute(
            select(PlayerArtifact, ArtifactCatalog)
            .join(ArtifactCatalog, ArtifactCatalog.id == PlayerArtifact.catalog_id)
            .where(
                PlayerArtifact.id == art_id,
                PlayerArtifact.player_id == player.telegram_id,
            )
        )).first()
        if not result:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        art, cat = result
        if art.is_equipped:
            await safe_answer(query, t(lang, "inv_dismantle_equipped"), show_alert=True)
            return
        if getattr(art, "locked", False):
            await safe_answer(query, t(lang, "inv_dismantle_locked"), show_alert=True)
            return

    grade_name = ARTIFACT_GRADES.get(art.grade, f"G{art.grade}")
    reward = DISMANTLE_BY_GRADE.get(art.grade, 50)

    stats = art.custom_stats or {}
    stat_parts = []
    if stats.get("battle_power"):
        stat_parts.append(f"⚔️ BP +{stats['battle_power']}")
    if stats.get("soul_strength"):
        stat_parts.append(f"👻 Soul +{stats['soul_strength']}")
    if stats.get("luck"):
        stat_parts.append(f"🍀 Luck +{stats['luck']}")
    if stats.get("perception"):
        stat_parts.append(f"🔮 Perc +{stats['perception']}")

    sep = "—" * 20
    lines = [
        f"🔨 *{t(lang, 'inv_dismantle_title')}*",
        sep,
        f"{cat.emoji} *{_cname(lang, 'art', cat)}* ({grade_name})",
    ]
    if stat_parts:
        lines.append("  " + " | ".join(stat_parts))
    if art.has_spirit:
        lines.append(f"  ✨ {art.spirit_name}")
    if art.enchant_rune:
        lines.append(f"  🌀 {art.enchant_rune}")
    lines.append("")
    lines.append(t(lang, "inv_dismantle_reward", stones=reward))
    lines.append("")
    lines.append(t(lang, "inv_dismantle_warning"))

    await safe_answer(query)
    buttons = [
        [InlineKeyboardButton(
            f"🔨 {t(lang, 'inv_dismantle_confirm')} (+{reward:,} SS)",
            callback_data=f"inv_do_dismantle_{art.id}",
        )],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_tab_equip_R")],
    ]
    await query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


# ─── Action: Bulk Dismantle ─────────────────────────────────────────────────

async def _bulk_dismantle_menu(update: Update, cat_type: str):
    """Show a grade selector for bulk dismantling unequipped + unlocked items."""
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        rows = (await session.execute(
            select(PlayerArtifact, ArtifactCatalog)
            .join(ArtifactCatalog, ArtifactCatalog.id == PlayerArtifact.catalog_id)
            .where(
                PlayerArtifact.player_id == player.telegram_id,
                ArtifactCatalog.type == cat_type,
                PlayerArtifact.is_equipped == False,
                PlayerArtifact.locked == False,
            )
        )).all()

    # Group counts and rewards per grade
    by_grade: dict[int, list] = {}
    for art, _cat in rows:
        by_grade.setdefault(art.grade, []).append(art)

    if not by_grade:
        await safe_answer(query, t(lang, "inv_bulk_dismantle_empty"), show_alert=True)
        return

    sep = "—" * 20
    lines = [f"🔨 *{t(lang, 'inv_bulk_dismantle_title')}*", sep,
             t(lang, "inv_bulk_dismantle_pick")]
    buttons = []
    for grade in sorted(by_grade.keys()):
        n = len(by_grade[grade])
        per = DISMANTLE_BY_GRADE.get(grade, 50)
        total = n * per
        grade_name = ARTIFACT_GRADES.get(grade, f"G{grade}")
        emoji = _GRADE_EMOJIS.get(grade, "📦")
        buttons.append([InlineKeyboardButton(
            f"{emoji} {grade_name} — {n}× → +{total:,} SS",
            callback_data=f"inv_bulk_grade_{cat_type}_{grade}",
        )])

    # "Up to grade X" combined option — every grade ≤ X.
    # Lets the player nuke all common/uncommon trash in one click.
    grades_sorted = sorted(by_grade.keys())
    if len(grades_sorted) >= 2:
        # Default cutoff: dismantle everything below the highest grade present.
        cutoff = grades_sorted[-2]
        n_total = sum(len(by_grade[g]) for g in grades_sorted if g <= cutoff)
        ss_total = sum(len(by_grade[g]) * DISMANTLE_BY_GRADE.get(g, 50) for g in grades_sorted if g <= cutoff)
        cutoff_name = ARTIFACT_GRADES.get(cutoff, f"G{cutoff}")
        buttons.append([InlineKeyboardButton(
            t(lang, "inv_bulk_dismantle_below", grade=cutoff_name, count=n_total, stones=ss_total),
            callback_data=f"inv_bulk_below_{cat_type}_{cutoff}",
        )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"inv_ecat_{cat_type}_R")])
    await safe_answer(query)
    await query.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def _format_refunded_materials(session, refunded: dict, lang: str) -> str:
    """U2 (v16.6): turn a {ore_id: qty} refund dict into a readable string like
    '🪨 Iron Ore ×2, 🔥 Flame Ore ×1'. Empty string if nothing refunded."""
    if not refunded:
        return ""
    rows = (await session.execute(
        select(OreCatalog).where(OreCatalog.id.in_([int(k) for k in refunded.keys()]))
    )).scalars().all()
    names = {o.id: f"{o.emoji} {o.name}" for o in rows}
    parts = [f"{names.get(int(oid), f'Ore #{oid}')} ×{qty}" for oid, qty in refunded.items() if qty > 0]
    return ", ".join(parts)


async def _do_bulk_dismantle(update: Update, cat_type: str, max_grade: int, exact: bool):
    """Dismantle all unequipped artifacts of `cat_type` matching the grade rule.

    `exact`: True → only that grade; False → grade ≤ max_grade.
    """
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        stmt = (
            select(PlayerArtifact)
            .join(ArtifactCatalog, ArtifactCatalog.id == PlayerArtifact.catalog_id)
            .where(
                PlayerArtifact.player_id == player.telegram_id,
                ArtifactCatalog.type == cat_type,
                PlayerArtifact.is_equipped == False,
                PlayerArtifact.locked == False,
            )
        )
        if exact:
            stmt = stmt.where(PlayerArtifact.grade == max_grade)
        else:
            stmt = stmt.where(PlayerArtifact.grade <= max_grade)
        arts = (await session.execute(stmt)).scalars().all()

        # Cap quantity per env var to avoid massive single-shot deletes.
        import os
        bulk_limit = int(os.getenv("BULK_DISMANTLE_LIMIT", "200"))
        truncated = False
        if len(arts) > bulk_limit:
            arts = list(arts)[:bulk_limit]
            truncated = True

        if not arts:
            await safe_answer(query, t(lang, "inv_bulk_dismantle_empty"), show_alert=True)
            return

        from core.forge_engine import refund_recipe_materials
        total_stones = 0
        all_refunded: dict[int, int] = {}
        for a in arts:
            total_stones += DISMANTLE_BY_GRADE.get(a.grade, 50)
            # U2 (v16.6): recover 25% of each crafted artifact's materials.
            refunded = await refund_recipe_materials(session, player.telegram_id, a.catalog_id, ratio=0.25)
            for oid, qty in refunded.items():
                all_refunded[oid] = all_refunded.get(oid, 0) + qty
            await session.delete(a)
        player.spirit_stones += total_stones
        mats_str = await _format_refunded_materials(session, all_refunded, lang)
        await session.commit()

    msg = t(lang, "inv_bulk_dismantled", count=len(arts), stones=total_stones)
    if mats_str:
        msg += "\n" + t(lang, "inv_dismantle_materials_returned", materials=mats_str)
    if truncated:
        msg += "\n" + t(lang, "inv_bulk_dismantle_truncated", limit=bulk_limit)
    await safe_answer(query, msg, show_alert=True)
    await _equip_category(update, lang, player.telegram_id, cat_type, 1)


async def _do_dismantle(update: Update, art_id: int):
    """Actually perform the dismantle after confirmation."""
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        result = (await session.execute(
            select(PlayerArtifact, ArtifactCatalog)
            .join(ArtifactCatalog, ArtifactCatalog.id == PlayerArtifact.catalog_id)
            .where(
                PlayerArtifact.id == art_id,
                PlayerArtifact.player_id == player.telegram_id,
            )
        )).first()
        if not result:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        art, cat = result
        if art.is_equipped:
            await safe_answer(query, t(lang, "inv_dismantle_equipped"), show_alert=True)
            return
        if getattr(art, "locked", False):
            await safe_answer(query, t(lang, "inv_dismantle_locked"), show_alert=True)
            return

        reward = DISMANTLE_BY_GRADE.get(art.grade, 50)
        player.spirit_stones += reward
        # U2 (v16.6): recover 25% of the artifact's crafting materials (if it has a recipe).
        from core.forge_engine import refund_recipe_materials
        refunded = await refund_recipe_materials(session, player.telegram_id, art.catalog_id, ratio=0.25)
        mats_str = await _format_refunded_materials(session, refunded, lang)
        await session.delete(art)
        await session.commit()

    msg = t(lang, "inv_dismantled", name=_cname(lang, "art", cat), stones=reward)
    if mats_str:
        msg += "\n" + t(lang, "inv_dismantle_materials_returned", materials=mats_str)
    await safe_answer(query, msg, show_alert=True)
    await _equip_category(update, lang, player.telegram_id, cat.type, 1)


# ─── Action: Learn Technique ─────────────────────────────────────────────────

async def _do_learn_tech(update: Update, tech_id: int):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        tech = (await session.execute(
            select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
        )).scalar_one_or_none()
        if not tech:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        # Already known? → absorb scroll for mastery XP
        existing = (await session.execute(
            select(PlayerTechnique).where(
                PlayerTechnique.player_id == player.telegram_id,
                PlayerTechnique.technique_id == tech_id,
            )
        )).scalar_one_or_none()
        if existing:
            inv = (await session.execute(
                select(PlayerInventory).where(
                    PlayerInventory.player_id == player.telegram_id,
                    PlayerInventory.item_type == "technique_scroll",
                    PlayerInventory.item_id == tech_id,
                    PlayerInventory.quantity > 0,
                )
            )).scalar_one_or_none()
            if not inv:
                await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
                return

            xp_table = {0: 50, 1: 50, 2: 100, 3: 100, 4: 200, 5: 200, 6: 400, 7: 400}
            xp_gain = xp_table.get(tech.req_realm, 750)
            existing.mastery_xp += xp_gain

            levelup_msg = ""
            while existing.mastery_level < 5:
                next_stage = MASTERY_STAGES.get(existing.mastery_level + 1)
                if next_stage and existing.mastery_xp >= next_stage["xp_req"]:
                    existing.mastery_level += 1
                    stage_name = t(lang, f"technique_mastery_stage_{existing.mastery_level}")
                    stage_data = MASTERY_STAGES[existing.mastery_level]
                    levelup_msg = t(lang, "inv_tech_absorb_levelup",
                                    name=_cname(lang, "tech", tech), stage=stage_name,
                                    mult=stage_data["mult"])
                else:
                    break

            inv.quantity -= 1
            if inv.quantity <= 0:
                await session.delete(inv)
            await session.commit()

            text = t(lang, "inv_tech_absorb", name=_cname(lang, "tech", tech), xp=xp_gain)
            if levelup_msg:
                text += "\n" + levelup_msg
            await query.message.edit_text(text, parse_mode="Markdown")
            return

        # Realm check
        if player.realm < tech.req_realm:
            realm_name = (
                REALM_NAMES[tech.req_realm]
                if tech.req_realm < len(REALM_NAMES)
                else f"R{tech.req_realm}"
            )
            await safe_answer(query, t(lang, "inv_tech_realm", realm=realm_name), show_alert=True)
            return

        # Spirit root check
        if tech.req_spirit_root is not None and player.spirit_root > tech.req_spirit_root:
            # Track A item 6: the old hardcoded names were WRONG (Emperor/King/Mortal
            # don't exist — config has Heavenly/Superior/High/Mid/Low). Use the canonical
            # config list, matching handlers/combat.py's tech-detail render (parity fix).
            from config import SPIRIT_ROOT_NAMES
            req_name = SPIRIT_ROOT_NAMES[min(tech.req_spirit_root, len(SPIRIT_ROOT_NAMES) - 1)]
            await safe_answer(query, t(lang, "inv_tech_root_required", root=req_name), show_alert=True)
            return

        # Dao insight check (if required)
        if tech.required_dao_law_id and tech.required_dao_insight > 0:
            dao_frag = (await session.execute(
                select(PlayerDaoFragment).where(
                    PlayerDaoFragment.player_id == player.telegram_id,
                    PlayerDaoFragment.dao_law_id == tech.required_dao_law_id,
                )
            )).scalar_one_or_none()
            insight = dao_frag.insight_level if dao_frag else 0
            if insight < tech.required_dao_insight:
                await safe_answer(query, 
                    t(lang, "inv_tech_dao", insight=tech.required_dao_insight),
                    show_alert=True,
                )
                return

        # Consume the scroll
        inv = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == player.telegram_id,
                PlayerInventory.item_type == "technique_scroll",
                PlayerInventory.item_id == tech_id,
                PlayerInventory.quantity > 0,
            )
        )).scalar_one_or_none()
        if not inv:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        inv.quantity -= 1
        if inv.quantity <= 0:
            await session.delete(inv)

        session.add(PlayerTechnique(
            player_id=player.telegram_id,
            technique_id=tech_id,
            mastery_level=1,
            mastery_xp=0,
            is_active_combat=False,
        ))
        await session.commit()

    await safe_answer(query, t(lang, "inv_tech_learned", name=_cname(lang, "tech", tech)), show_alert=True)
    await _tech_tab(update, lang, player.telegram_id, 1)


# ─── Action: Upgrade Ring ────────────────────────────────────────────────────

async def _do_ring_upgrade(update: Update):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"
        ring = await _get_or_create_ring(session, player.telegram_id)

        if ring.tier >= MAX_RING_TIER:
            await safe_answer(query, t(lang, "inv_ring_max"), show_alert=True)
            return

        cost = RING_UPGRADE_STONES[ring.tier]
        if player.spirit_stones < cost:
            await safe_answer(query, 
                t(lang, "inv_not_enough_stones", need=cost, have=player.spirit_stones),
                show_alert=True,
            )
            return

        player.spirit_stones -= cost
        # Fix 2026-07-14 (report [jogador]): a atribuição absoluta
        # (`max_slots = RING_MAX_SLOTS[tier]`) APAGAVA as expansões compradas
        # no Pavilhão de Prestígio (que somam max_slots sem mexer no tier —
        # ex.: T4 510 → upgrade forçava 1000 e comia os +10 pagos). O delta do
        # tier preserva qualquer bónus aditivo. COMPAT: rows atuais mantêm o
        # valor que têm; ninguém perde nada.
        # 🎒 3.2 — a conta vive no dono (`core/anel.expandir`), a mesma do
        # mini-app; aqui só se cobra e se diz.
        _anel.expandir(ring)
        new_tier = ring.tier
        new_max = ring.max_slots
        await session.commit()

    await safe_answer(query, 
        t(lang, "inv_ring_upgraded", tier=new_tier, max=new_max),
        show_alert=True,
    )
    await _ring_info(update, lang, player.telegram_id)


# ─── Button Router ────────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def inventory_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    data = query.data

    # Main screen
    if data in ("inv_main", "cmd_inventory"):
        await safe_answer(query)
        await inventory_command(update, context)
        return True

    # No-op (e.g. "already learned" buttons)
    if data == "inv_noop":
        await safe_answer(query)
        return True

    # Ring info / upgrade
    if data == "inv_ring_info":
        await safe_answer(query)
        async with get_session_factory()() as session:
            player = await _get_player(update.effective_user.id, session)
            if not player:
                return True
            lang = player.language or "en"
        await _ring_info(update, lang, player.telegram_id)
        return True

    if data == "inv_ring_upgrade":
        await _do_ring_upgrade(update)
        return True

    # Tab navigation
    _TAB_FNS = {
        "pill": _pills_tab,
        "herb": _herbs_tab,
        "ore": _ores_tab,
        "equip": _equip_tab,
        "tech": _tech_tab,
        "misc": _misc_tab,
    }
    for tab, fn in _TAB_FNS.items():
        prefix = f"inv_tab_{tab}_"
        if data.startswith(prefix):
            raw = data[len(prefix):]
            saved_pages = context.user_data.setdefault("inv_pages", {})
            # H-10 fix: tab-entry buttons use "R" sentinel to restore saved page;
            # numeric values come from pagination buttons and are honoured directly,
            # so going "previous" back to page 1 actually lands on page 1.
            if raw == "R":
                page = saved_pages.get(tab, 1)
            else:
                try:
                    page = int(raw)
                except ValueError:
                    page = 1
                saved_pages[tab] = page
            await safe_answer(query)
            async with get_session_factory()() as session:
                player = await _get_player(update.effective_user.id, session)
                if not player:
                    return True
                lang = player.language or "en"
            await fn(update, lang, player.telegram_id, page)
            return True

    # Equipment category sub-view (weapon/armor/accessory)
    if data.startswith("inv_ecat_"):
        parts = data[len("inv_ecat_"):].rsplit("_", 1)
        if len(parts) == 2:
            cat_type, page_str = parts
            saved_pages = context.user_data.setdefault("inv_ecat_pages", {})
            # H-10 fix: "R" sentinel restores; numeric is honoured verbatim.
            if page_str == "R":
                page = saved_pages.get(cat_type, 1)
            else:
                try:
                    page = int(page_str)
                except ValueError:
                    page = 1
                saved_pages[cat_type] = page
            await safe_answer(query)
            async with get_session_factory()() as session:
                player = await _get_player(update.effective_user.id, session)
                if not player:
                    return True
                lang = player.language or "en"
            await _equip_category(update, lang, player.telegram_id, cat_type, page)
            return True

    # Artifact detail view
    if data.startswith("inv_art_"):
        try:
            art_id = int(data[len("inv_art_"):])
        except ValueError:
            await safe_answer(query)
            return True
        await safe_answer(query)
        await _equip_detail(update, art_id)
        return True

    # M-11: Pill detail card (full effect description, duration, caps).
    # 2026-05-17 fix: callback now carries quality so the card scales magnitude.
    # Legacy callbacks without quality default to "normal" for backward-compat.
    if data.startswith("inv_pill_info_"):
        parts = data[len("inv_pill_info_"):].split("_", 1)
        try:
            pill_id = int(parts[0])
        except (ValueError, IndexError):
            await safe_answer(query)
            return True
        quality = parts[1] if len(parts) > 1 else "normal"
        await safe_answer(query)
        await _show_pill_detail(update, pill_id, quality)
        return True

    # H-9: Bulk pill consume
    if data.startswith("inv_usex_"):
        parts = data[len("inv_usex_"):].split("_")
        try:
            pill_id = int(parts[0])
            quality = parts[1]
            count = int(parts[2])
        except (ValueError, IndexError):
            await safe_answer(query)
            return True
        await _do_use_pill_bulk(update, context, pill_id, quality, count)
        return True

    # Use pill (native)
    if data.startswith("inv_use_"):
        parts = data[len("inv_use_"):].split("_")
        try:
            pill_id = int(parts[0])
            quality = parts[1] if len(parts) > 1 else "normal"
        except (ValueError, IndexError):
            await safe_answer(query)
            return True
        await _do_use_pill(update, context, pill_id, quality)
        return True

    # Equip artifact (native)
    if data.startswith("inv_equip_"):
        try:
            art_id = int(data[len("inv_equip_"):])
        except ValueError:
            await safe_answer(query)
            return True
        await _do_equip(update, art_id)
        return True

    # Unequip artifact (native)
    if data.startswith("inv_unequip_"):
        try:
            art_id = int(data[len("inv_unequip_"):])
        except ValueError:
            await safe_answer(query)
            return True
        await _do_unequip(update, art_id)
        return True

    # Sell herb
    if data.startswith("inv_sell_herb_"):
        try:
            inv_id = int(data[len("inv_sell_herb_"):])
        except ValueError:
            await safe_answer(query)
            return True
        await _do_sell_herb(update, inv_id)
        return True

    # Sell ore
    if data.startswith("inv_sell_ore_"):
        try:
            ore_id = int(data[len("inv_sell_ore_"):])
        except ValueError:
            await safe_answer(query)
            return True
        await _do_sell_ore(update, ore_id)
        return True

    # Bulk dismantle — open grade picker
    if data.startswith("inv_bulk_dismantle_"):
        cat_type = data[len("inv_bulk_dismantle_"):]
        await _bulk_dismantle_menu(update, cat_type)
        return True

    # Bulk dismantle — exact grade
    if data.startswith("inv_bulk_grade_"):
        try:
            rest = data[len("inv_bulk_grade_"):]
            cat_type, grade_str = rest.rsplit("_", 1)
            grade = int(grade_str)
        except (ValueError, IndexError):
            await safe_answer(query)
            return True
        await _do_bulk_dismantle(update, cat_type, grade, exact=True)
        return True

    # Bulk dismantle — all grades ≤ X
    if data.startswith("inv_bulk_below_"):
        try:
            rest = data[len("inv_bulk_below_"):]
            cat_type, grade_str = rest.rsplit("_", 1)
            grade = int(grade_str)
        except (ValueError, IndexError):
            await safe_answer(query)
            return True
        await _do_bulk_dismantle(update, cat_type, grade, exact=False)
        return True

    # Lock / unlock artifact (H-8)
    if data.startswith("inv_lock_"):
        try:
            art_id = int(data[len("inv_lock_"):])
        except ValueError:
            await safe_answer(query)
            return True
        await _toggle_lock(update, art_id)
        return True

    # Dismantle artifact — confirmation screen
    if data.startswith("inv_dismantle_"):
        try:
            art_id = int(data[len("inv_dismantle_"):])
        except ValueError:
            await safe_answer(query)
            return True
        await _dismantle_confirm(update, art_id)
        return True

    # Dismantle artifact — confirmed action
    if data.startswith("inv_do_dismantle_"):
        try:
            art_id = int(data[len("inv_do_dismantle_"):])
        except ValueError:
            await safe_answer(query)
            return True
        await _do_dismantle(update, art_id)
        return True

    # D-4 (v14.2): Misc tab — use action (blueprint / ore_pack / pill_recipe_scroll / mystery_box)
    if data.startswith("inv_misc_"):
        try:
            inv_id = int(data[len("inv_misc_"):])
        except ValueError:
            await safe_answer(query)
            return True
        await _do_use_misc(update, inv_id)
        return True

    # Learn technique
    if data.startswith("inv_learn_"):
        try:
            tech_id = int(data[len("inv_learn_"):])
        except ValueError:
            await safe_answer(query)
            return True
        await _do_learn_tech(update, tech_id)
        return True

    return False
