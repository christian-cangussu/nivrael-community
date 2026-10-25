"""Prestige Shop — endgame catalog spent via Player.prestige_points.

v14.14c (2026-05-28): owner directiva "prestige é o final do game" — port
o stub `loja_prestige` (chat + mini-app) para conteúdo real, WIPE-friendly
e thematicamente Wuxia (lei §2).

Catálogo (7 items / 3 categorias):

  PERMANENT — soul echoes que sobrevivem ao renascer (stats base re-aplicados
    após process_prestige reset; ring max_slots persiste naturalmente).
  CONSUMABLE — gifts cósmicos one-shot (core essence / CB push imediato).
  TITLE — nome inscrito nos céus (Player.unlocked_titles).

Engine reuse: 100% — nenhuma outra engine é tocada. process_prestige ganha
uma chamada a `re_apply_persistent_perks(player)` no fim do reset block.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Player, PlayerPrestigePurchase, PlayerSpatialRing

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CATÁLOGO
# ─────────────────────────────────────────────────────────────────────────────
# Cada item tem:
#   id              — string única, persiste em player_prestige_purchases
#   category        — permanent | consumable | title
#   emoji           — leading glyph (UI + chat)
#   cost            — preço em prestige_points
#   max_purchases   — cap de compras (0 = ilimitado)
#   min_prestige    — gate de prestige_level mínimo
#   effect.kind     — discriminador:
#                       stat_boost (permanent, persists across rebirth)
#                       ring_slots (permanent, applied to PlayerSpatialRing)
#                       core_essence (consumable, one-shot)
#                       cb_boost (consumable, one-shot)
#                       title (one-shot, added to unlocked_titles)
PRESTIGE_SHOP_CATALOG: list[dict[str, Any]] = [
    {
        "id": "soul_echo_triad",
        "category": "permanent",
        "emoji": "🌟",
        "cost": 300,
        "max_purchases": 5,
        "min_prestige": 0,
        "effect": {"kind": "stat_boost",
                   "stats": {"soul_strength": 5, "perception": 5, "luck": 5}},
    },
    {
        "id": "ring_expansion",
        "category": "permanent",
        "emoji": "💍",
        "cost": 200,
        "max_purchases": 10,
        "min_prestige": 0,
        "effect": {"kind": "ring_slots", "amount": 10},
    },
    {
        "id": "cosmic_whisper",
        "category": "consumable",
        "emoji": "🌬️",
        "cost": 100,
        "max_purchases": 0,
        "min_prestige": 0,
        "effect": {"kind": "core_essence", "amount": 20},
    },
    {
        "id": "celestial_inheritance",
        "category": "consumable",
        "emoji": "💫",
        "cost": 250,
        "max_purchases": 0,
        "min_prestige": 0,
        "effect": {"kind": "cb_boost", "amount": 5000.0},
    },
    {
        "id": "title_reborn",
        "category": "title",
        "emoji": "🔄",
        "cost": 200,
        "max_purchases": 1,
        "min_prestige": 1,
        "effect": {"kind": "title", "title": "🔄 O Renascido"},
    },
    {
        "id": "title_walker",
        "category": "title",
        "emoji": "🌀",
        "cost": 1000,
        "max_purchases": 1,
        "min_prestige": 3,
        "effect": {"kind": "title", "title": "🌀 Caminhante das Mil Vidas"},
    },
    {
        "id": "title_heaven_pet",
        "category": "title",
        "emoji": "✨",
        "cost": 2000,
        "max_purchases": 1,
        "min_prestige": 5,
        "effect": {"kind": "title", "title": "✨ Estimado dos Céus"},
    },
]

_CATALOG_BY_ID: dict[str, dict[str, Any]] = {it["id"]: it for it in PRESTIGE_SHOP_CATALOG}


def get_item(item_id: str) -> dict[str, Any] | None:
    return _CATALOG_BY_ID.get(item_id)


# ─────────────────────────────────────────────────────────────────────────────
# LEITURA — purchase counts + shop view
# ─────────────────────────────────────────────────────────────────────────────

async def get_purchase_counts(session: AsyncSession, player_id: int) -> dict[str, int]:
    rows = (await session.execute(
        select(PlayerPrestigePurchase.item_id, PlayerPrestigePurchase.count)
        .where(PlayerPrestigePurchase.player_id == player_id)
    )).all()
    return {item_id: int(count or 0) for item_id, count in rows}


async def get_shop_view(session: AsyncSession, player: Player) -> dict[str, Any]:
    """Return the catalog enriched with per-player state.

    Each item gets ``purchased_count``, ``cap_reached``, ``locked`` (insufficient
    prestige level), and ``affordable`` (enough points right now).
    """
    counts = await get_purchase_counts(session, player.telegram_id)
    p_level = int(player.prestige_level or 0)
    p_points = int(player.prestige_points or 0)
    items_out: list[dict[str, Any]] = []
    for it in PRESTIGE_SHOP_CATALOG:
        bought = counts.get(it["id"], 0)
        cap = int(it["max_purchases"] or 0)
        cap_reached = cap > 0 and bought >= cap
        locked = p_level < int(it["min_prestige"] or 0)
        items_out.append({
            "id": it["id"],
            "category": it["category"],
            "emoji": it["emoji"],
            "cost": int(it["cost"]),
            "max_purchases": cap,
            "min_prestige": int(it["min_prestige"] or 0),
            "purchased_count": bought,
            "cap_reached": cap_reached,
            "locked": locked,
            "affordable": p_points >= int(it["cost"]),
        })
    # v15.1.5-hf5 — title manager support. Expose every title the player
    # has unlocked through prestige/VIP purchases (raw JSONB) + the currently
    # equipped one so the mini-app can render an "Equip" / "Equipped" row
    # right next to the prestige titles in the shop. Achievement titles
    # remain managed via AchievementsModal (their data source is a different
    # table).
    title_items: list[dict[str, Any]] = []
    for it in PRESTIGE_SHOP_CATALOG:
        if it.get("category") != "title":
            continue
        title_value = (it.get("effect") or {}).get("title")
        if not title_value:
            continue
        owned = title_value in (player.unlocked_titles or [])
        title_items.append({
            "item_id": it["id"],
            "title": title_value,
            "emoji": it.get("emoji") or "✨",
            "owned": owned,
            "equipped": owned and (player.active_title or "") == title_value,
        })

    return {
        "prestige_level": p_level,
        "prestige_points": p_points,
        "items": items_out,
        "active_title": player.active_title,
        "unlocked_titles": list(player.unlocked_titles or []),
        "prestige_title_options": title_items,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COMPRA — atómica: valida → debita → aplica efeito → grava ledger
# ─────────────────────────────────────────────────────────────────────────────

async def buy_shop_item(
    session: AsyncSession, player: Player, item_id: str
) -> dict[str, Any]:
    """Compra de um item da loja. Retorna {ok, reason?, item?, applied?}.

    Razões de falha:
      unknown_item · prestige_locked · cap_reached · not_enough_points
    """
    item = _CATALOG_BY_ID.get(item_id)
    if not item:
        return {"ok": False, "reason": "unknown_item"}

    p_level = int(player.prestige_level or 0)
    if p_level < int(item["min_prestige"] or 0):
        return {"ok": False, "reason": "prestige_locked",
                "min_prestige": int(item["min_prestige"] or 0)}

    cap = int(item["max_purchases"] or 0)
    bought_row = (await session.execute(
        select(PlayerPrestigePurchase).where(
            PlayerPrestigePurchase.player_id == player.telegram_id,
            PlayerPrestigePurchase.item_id == item_id,
        )
    )).scalar_one_or_none()
    current_count = int(bought_row.count) if bought_row else 0
    if cap > 0 and current_count >= cap:
        return {"ok": False, "reason": "cap_reached", "cap": cap}

    cost = int(item["cost"])
    if int(player.prestige_points or 0) < cost:
        return {"ok": False, "reason": "not_enough_points",
                "cost": cost, "have": int(player.prestige_points or 0)}

    # Apply side-effects FIRST so a crash mid-apply rolls back the spend too.
    applied = await _apply_effect(session, player, item)

    # Debit + ledger.
    player.prestige_points = int(player.prestige_points or 0) - cost
    if bought_row:
        bought_row.count = current_count + 1
        bought_row.last_purchased_at = datetime.now(timezone.utc)
    else:
        session.add(PlayerPrestigePurchase(
            player_id=player.telegram_id,
            item_id=item_id,
            count=1,
        ))

    return {
        "ok": True,
        "item_id": item_id,
        "cost": cost,
        "applied": applied,
        "new_count": current_count + 1,
        "remaining_points": int(player.prestige_points or 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# APLICAÇÃO DE EFEITOS
# ─────────────────────────────────────────────────────────────────────────────

async def _apply_effect(
    session: AsyncSession, player: Player, item: dict[str, Any]
) -> dict[str, Any]:
    """Aplica o efeito do item ao player. Retorna dict descritivo do que mudou."""
    eff = item.get("effect") or {}
    kind = eff.get("kind")

    if kind == "stat_boost":
        stats = eff.get("stats") or {}
        for col, delta in stats.items():
            current = int(getattr(player, col, 0) or 0)
            setattr(player, col, current + int(delta))
        # Bump perks ledger so process_prestige can re-apply after rebirth reset.
        perks = dict(player.prestige_perks or {})
        perks["soul_echoes"] = int(perks.get("soul_echoes") or 0) + 1
        player.prestige_perks = perks
        return {"kind": "stat_boost", "stats": stats}

    if kind == "ring_slots":
        amount = int(eff.get("amount") or 0)
        ring = (await session.execute(
            select(PlayerSpatialRing).where(PlayerSpatialRing.player_id == player.telegram_id)
        )).scalar_one_or_none()
        if not ring:
            ring = PlayerSpatialRing(player_id=player.telegram_id, tier=1, max_slots=50)
            session.add(ring)
            await session.flush()
        ring.max_slots = int(ring.max_slots or 50) + amount
        perks = dict(player.prestige_perks or {})
        perks["ring_expansions"] = int(perks.get("ring_expansions") or 0) + 1
        player.prestige_perks = perks
        return {"kind": "ring_slots", "amount": amount, "new_max": int(ring.max_slots)}

    if kind == "core_essence":
        amount = int(eff.get("amount") or 0)
        player.core_essence = int(player.core_essence or 0) + amount
        return {"kind": "core_essence", "amount": amount,
                "new_total": int(player.core_essence)}

    if kind == "cb_boost":
        amount = float(eff.get("amount") or 0.0)
        player.cultivation_base = float(player.cultivation_base or 0.0) + amount
        return {"kind": "cb_boost", "amount": amount,
                "new_total": float(player.cultivation_base)}

    if kind == "title":
        title = eff.get("title")
        auto_equipped = False
        if title:
            current_list = list(player.unlocked_titles or [])
            if title not in current_list:
                current_list.append(title)
                player.unlocked_titles = current_list
            # v15.1.5-hf5 — owner report: players bought titles and saw
            # nothing in their profile. Reason: the title was added to the
            # `unlocked_titles` JSONB but the profile reads `active_title`
            # which stayed NULL. Auto-equip the just-bought title when the
            # player has no active title set, so the purchase is immediately
            # visible in the header. Players can still swap titles later via
            # the title manager in PrestigeShopModal / AchievementsModal.
            current_active = (player.active_title or "").strip()
            if not current_active:
                player.active_title = title
                auto_equipped = True
        return {"kind": "title", "title": title, "auto_equipped": auto_equipped}

    logger.warning("prestige_shop: unknown effect kind %r for item %s",
                   kind, item.get("id"))
    return {"kind": "unknown"}


# ─────────────────────────────────────────────────────────────────────────────
# REBIRTH HOOK — chamado por process_prestige após o reset block.
# ─────────────────────────────────────────────────────────────────────────────

def re_apply_persistent_perks(player: Player) -> None:
    """Re-apply permanent perks after process_prestige reset block.

    Soul Echo Triad: stats base voltaram a 50/40/30; somar (echo_count × 5) a
    soul/perception/luck. ring_expansions persiste naturalmente em
    PlayerSpatialRing (não tocado pelo rebirth) — não precisa de re-apply.
    """
    perks = dict(player.prestige_perks or {})
    echoes = int(perks.get("soul_echoes") or 0)
    if echoes > 0:
        player.soul_strength = int(player.soul_strength or 50) + echoes * 5
        player.perception = int(player.perception or 40) + echoes * 5
        player.luck = int(player.luck or 30) + echoes * 5
