import uuid
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, or_, and_, desc, func
from sqlalchemy.orm.attributes import flag_modified
from database.db import get_session_factory
from database.models import (
    Player, MarketplaceListing, Transaction, P2PTrade,
    PlayerInventory, PlayerArtifact, PlayerOre, PlayerCauldron,
    HerbCatalog, PillCatalog, OreCatalog, ArtifactCatalog, CauldronCatalog
)
from core.i18n import t, catalog_text
from core.economy import (
    format_currency, create_listing, buy_listing, buy_partial, place_bid,
    initiate_trade, execute_trade, cancel_trade, get_player_transactions,
    cancel_listing,
    TRADEABLE_ITEM_TYPES,
)
from core.utils import _ensure_player, safe_handler, rate_limit, build_pagination_keyboard, get_display_name, escape_markdown, safe_answer, safe_parse_callback_int, safe_parse_callback_uuid, normalize_lang

REALM_HIERARCHY_GAP = 3  # block P2P trade if realm difference >= this value
import logging
import math

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 5

@safe_handler
@rate_limit(1)
async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        # Filter by type if provided
        item_type = context.args[0] if context.args else None
        page = 0
        if "page" in context.user_data: page = context.user_data["page"]

        await _show_market(update, context, session, player, item_type, page)

async def _show_market(update: Update, context: ContextTypes.DEFAULT_TYPE, session, player, item_type, page):
    lang = player.language or "en"
    stmt = select(MarketplaceListing).where(
        MarketplaceListing.is_sold == False,
        MarketplaceListing.expires_at > datetime.now(timezone.utc)
    )
    if item_type:
        stmt = stmt.where(MarketplaceListing.item_type == item_type)
    
    stmt = stmt.order_by(desc(MarketplaceListing.created_at)).offset(page * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    listings = (await session.execute(stmt)).scalars().all()

    text = f"💎 *{t(lang, 'market_title')}*\n"
    if item_type: text += f"📂 {t(lang, 'filter')}: {item_type}\n"
    # MV-3 — Estados Regionais: o mercado LOCAL dita (Lei §1 — nunca um preço
    # mudo): a nota só existe quando o estado do continente do comprador
    # ajusta o preço (gated `estados_regionais`; OFF → None → texto de hoje).
    try:
        from core.region_state_engine import market_note
        _rst_note = await market_note(session, player, lang)
        if _rst_note:
            text += f"{_rst_note}\n"
    except Exception:
        pass
    # MV-6 — Reputação: a nota da rep local, SÓ quando a rep muda o preço de
    # verdade vs o estado sozinho (review MV-6: −5% do estado + −5% da rep
    # exibidos juntos prometiam −10% e o clamp entrega −5% — nota que mente).
    try:
        from core.economy import MARKET_TAX as _tax
        from core.economy import _region_price_mult as _combined_mult
        from core.region_state_engine import market_price_mult as _state_mult
        _m = float(await _combined_mult(session, player))
        _s = float(await _state_mult(session, player) or 1.0)
        if abs(max(_s, 1.0 - float(_tax)) - _m) > 1e-9:
            from core.reputation_engine import market_rep_note
            _rep_note = await market_rep_note(session, player, lang)
            if _rep_note:
                text += f"{_rep_note}\n"
    except Exception:
        pass
    # MV-7 — 📜 Relatório do Mercado Imperial: snapshot dos 7d do continente
    # ATUAL (gated `profissoes`; sem snapshot/OFF → None → texto de hoje).
    # Disclosure honesta: "números do Império" — preço de tabela, nunca
    # promessa de futuro.
    try:
        from core.profession_engine import market_report_view
        _mr = await market_report_view(session, player, lang)
        if _mr:
            text += f"{_mr['title']} — {_mr['continent_name']} · {_mr['window']}\n"
            for _ln in _mr.get("lines", [])[:4]:
                text += f"  {_ln}\n"
    except Exception:
        pass
    text += "\n"

    buttons = []
    if not listings:
        text += t(lang, "market_empty")
    else:
        for l in listings:
            descr = await _get_item_descriptor(session, l, lang)
            item_name = descr["name"]
            grade_emoji = descr["grade_emoji"]
            stats_line = descr["stats_line"]
            display_name = f"{grade_emoji} {item_name}".strip() if grade_emoji else item_name
            if l.is_auction:
                price_display = format_currency(l.current_bid or l.unit_price)
            else:
                price_display = format_currency(l.unit_price)
            mode = "🔨" if l.is_auction else "💰"
            text += t(lang, "market_listing_item_desc", id=str(l.id)[:8], mode=mode, name=display_name, qty=l.quantity, price=price_display)
            if stats_line:
                # M-8: inline stat preview directly under the listing line.
                text += f"   _{stats_line}_\n"
            buttons.append([InlineKeyboardButton(f"👁️ {display_name} ({price_display})", callback_data=f"mkt_view_{l.id}")])

    # Pagination — optimised count query
    count_stmt = select(func.count()).select_from(MarketplaceListing).where(
        MarketplaceListing.is_sold == False,
        MarketplaceListing.expires_at > datetime.now(timezone.utc)
    )
    if item_type:
        count_stmt = count_stmt.where(MarketplaceListing.item_type == item_type)
    total_count = (await session.execute(count_stmt)).scalar() or 0

    total_pages = max(1, math.ceil(total_count / ITEMS_PER_PAGE))
    
    if total_pages > 1:
        prefix = f"mkt_page_{item_type}_" if item_type else "mkt_page_all_"
        buttons.extend(build_pagination_keyboard(page + 1, total_pages, prefix, lang))

    # Filters
    filters = [
        InlineKeyboardButton(f"🌿 {t(lang, 'cat_herbs')}", callback_data="mkt_filter_herb"),
        InlineKeyboardButton(f"💊 {t(lang, 'cat_pills')}", callback_data="mkt_filter_pill"),
        # FIX 2026-06-01: ore was sellable but not browsable — buyers couldn't
        # find ore listings. Add the ore filter so the browse categories match
        # the sell categories.
        InlineKeyboardButton(f"🪨 {t(lang, 'cat_ores')}", callback_data="mkt_filter_ore"),
        InlineKeyboardButton(f"⚔️ {t(lang, 'cat_artifacts')}", callback_data="mkt_filter_artifact")
    ]
    buttons.append(filters)
    buttons.append([
        InlineKeyboardButton(t(lang, "btn_sell"), callback_data="mkt_sell_start"),
        InlineKeyboardButton(f"🤝 {t(lang, 'btn_p2p_trade')}", callback_data="trd_help")
    ])
    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_status")])

    kb = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def _get_item_name(session, item_type, item_id, lang: str = "en"):
    try:
        if item_type == "herb":
            stmt = select(HerbCatalog.name).where(HerbCatalog.id == item_id)
        elif item_type == "pill":
            stmt = select(PillCatalog.name).where(PillCatalog.id == item_id)
        elif item_type == "ore":
            stmt = select(OreCatalog.name).where(OreCatalog.id == item_id)
        elif item_type == "artifact":
            stmt = select(ArtifactCatalog.name).where(ArtifactCatalog.id == item_id)
        elif item_type == "cauldron":
            stmt = select(CauldronCatalog.name).where(CauldronCatalog.id == item_id)
        elif item_type == "jade_ring":
            return "💍 Jade Ring"
        else:
            return t(lang, "market_unknown_item", type=item_type)

        res = (await session.execute(stmt)).scalar_one_or_none()
        if not res:
            return t(lang, "market_unknown_item", type=f"{item_type} #{item_id}")
        # 名 2026-09-14 — ESTE e' o chokepoint do mercado: 10 chamadores passam
        # por aqui e ja' traziam a lingua. Faltava so' resolver. A `cauldron`
        # fica de fora por nao ter familia no `_CATALOG_KINDS` (7 caldeiroes,
        # escrito no doc da sessao).
        _fam = {"herb": "herb", "pill": "pill", "ore": "ore",
                "artifact": "art"}.get(item_type)
        if _fam:
            return catalog_text(lang, _fam, item_id, "name", res)
        return res
    except Exception as e:
        logger.error(f"Error in _get_item_name: {e}")
        return t(lang, "market_unknown_item", type=f"{item_type} ID:{item_id}")


# M-8: shared grade-emoji palette used by inventory; reuse here so market and
# inventory speak the same visual language (G0 ⬜ … G8 🌠 Celestial).
_MKT_GRADE_EMOJIS = {0: "⬜", 1: "🟡", 2: "🔥", 3: "🟤", 4: "💠", 5: "🌟", 6: "💎", 7: "☯️", 8: "🌠"}


async def _get_item_descriptor(session, listing, lang: str = "en") -> dict:
    """M-8: build a rich descriptor for a market listing — grade emoji, stats summary,
    and base name. Returns a dict to keep callers tolerant of missing fields.

    Stats are pulled from the listing's `item_data` snapshot when present (set at
    listing creation time for artifacts) and fall back to catalog rows otherwise.
    """
    name = await _get_item_name(session, listing.item_type, listing.item_id, lang)
    grade_emoji = ""
    grade_label = ""
    stats_line = ""

    try:
        item_data = listing.item_data or {}
        if listing.item_type == "artifact":
            cat = (await session.execute(
                select(ArtifactCatalog).where(ArtifactCatalog.id == listing.item_id)
            )).scalar_one_or_none()
            grade = item_data.get("grade")
            if grade is None and cat is not None:
                grade = cat.grade
            if grade is not None:
                grade_emoji = _MKT_GRADE_EMOJIS.get(grade, "📦")
            stats = item_data.get("custom_stats") or {}
            parts = []
            if stats.get("battle_power"):
                parts.append(f"⚔️+{stats['battle_power']}")
            if stats.get("soul_strength"):
                parts.append(f"👻+{stats['soul_strength']}")
            if stats.get("perception"):
                parts.append(f"🔮+{stats['perception']}")
            if stats.get("luck"):
                parts.append(f"🍀+{stats['luck']}")
            if stats.get("qi_capacity"):
                parts.append(f"💧+{stats['qi_capacity']}")
            # TAPETE QoL §5 item 4 ([jogador] — disclosure de compra, Lei §1):
            # refino (qualidade inferida) + encantamento visíveis na listagem.
            from core.forge_engine import infer_artifact_quality
            quality = infer_artifact_quality(
                stats,
                cat.base_stats if cat else None,
                int(grade) if grade is not None else None,
                int(cat.grade) if cat and cat.grade is not None else None,
                bool(item_data.get("has_spirit")),
            )
            if quality and quality != "normal":
                parts.insert(0, t(lang, f"art_quality_{quality}"))
            if item_data.get("enchant_rune"):
                # Human label (config.ENCHANT_EFFECTS) — the raw snake_case key
                # would also break Markdown italics in the listing text.
                from config import ENCHANT_EFFECTS
                rune = item_data["enchant_rune"]
                rune_label = (ENCHANT_EFFECTS.get(rune) or {}).get("label") or rune.replace("_", " ")
                parts.append(f"✨{rune_label}")
            if parts:
                stats_line = " · ".join(parts)
        elif listing.item_type == "pill":
            cat = (await session.execute(
                select(PillCatalog).where(PillCatalog.id == listing.item_id)
            )).scalar_one_or_none()
            if cat is not None and getattr(cat, "grade", None) is not None:
                grade_emoji = _MKT_GRADE_EMOJIS.get(cat.grade, "📦")
        elif listing.item_type == "cauldron":
            cat = (await session.execute(
                select(CauldronCatalog).where(CauldronCatalog.id == listing.item_id)
            )).scalar_one_or_none()
            if cat is not None and getattr(cat, "tier", None) is not None:
                # Cauldrons use tier (1..7); reuse same emoji palette mapped from tier-1.
                grade_emoji = _MKT_GRADE_EMOJIS.get(max(0, cat.tier - 1), "📦")
        elif listing.item_type == "ore":
            cat = (await session.execute(
                select(OreCatalog).where(OreCatalog.id == listing.item_id)
            )).scalar_one_or_none()
            if cat is not None and getattr(cat, "tier", None) is not None:
                grade_emoji = _MKT_GRADE_EMOJIS.get(max(0, cat.tier - 1), "📦")
    except Exception as e:
        logger.warning("Failed to build item descriptor for listing %s: %s", listing.id, e)

    return {
        "name": name,
        "grade_emoji": grade_emoji,
        "grade_label": grade_label,
        "stats_line": stats_line,
    }

async def sell_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    if update.callback_query:
        query = update.callback_query
        await safe_answer(query)
    
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        
        text = f"🏪 *{t(lang, 'sell_title')}*\n\n{t(lang, 'sell_desc')}"
        buttons = [
            [InlineKeyboardButton(f"🌿 {t(lang, 'cat_herbs')}", callback_data="mkt_sell_cat_herb")],
            [InlineKeyboardButton(f"💊 {t(lang, 'cat_pills')}", callback_data="mkt_sell_cat_pill")],
            [InlineKeyboardButton(f"🪨 {t(lang, 'cat_ores')}", callback_data="mkt_sell_cat_ore")],
            [InlineKeyboardButton(f"⚔️ {t(lang, 'cat_artifacts')}", callback_data="mkt_sell_cat_artifact")],
            # FIX 2026-06-01 ([jogador]): cauldron sell removed — players have a
            # single cauldron that levels up (no spares to trade), so the
            # category was always empty + confusing. Handler kept (harmless) in
            # case a legacy spare exists; only the discoverable button is gone.
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_market")]
        ]
        kb = InlineKeyboardMarkup(buttons)
        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def sell_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    data = query.data.split("_")
    if len(data) < 4:
        await safe_answer(query)
        return
    cat = data[3]
    try:
        page = int(data[4]) if len(data) > 4 else 1
    except (ValueError, IndexError):
        page = 1
    
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        
        buttons = []
        text = f"📦 *{t(lang, 'select_item_sell')}*\n\n"
        
        if cat == "herb" or cat == "pill":
            stmt = select(PlayerInventory).where(PlayerInventory.player_id == player.telegram_id, PlayerInventory.item_type == cat)
            items = (await session.execute(stmt)).scalars().all()
            total_items = len(items)
            paginated_items = items[(page-1)*ITEMS_PER_PAGE:page*ITEMS_PER_PAGE]
            for item in paginated_items:
                name = await _get_item_name(session, cat, item.item_id, lang)
                buttons.append([InlineKeyboardButton(f"{name} (x{item.quantity})", callback_data=f"mkt_sell_item_{cat}_{item.id}")])

        elif cat == "ore":
            stmt = select(PlayerOre).where(PlayerOre.player_id == player.telegram_id)
            items = (await session.execute(stmt)).scalars().all()
            total_items = len(items)
            paginated_items = items[(page-1)*ITEMS_PER_PAGE:page*ITEMS_PER_PAGE]
            for item in paginated_items:
                name = await _get_item_name(session, cat, item.ore_id, lang)
                buttons.append([InlineKeyboardButton(f"{name} (x{item.quantity})", callback_data=f"mkt_sell_item_ore_{item.id}")])

        elif cat == "artifact":
            stmt = select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id, PlayerArtifact.is_equipped == False)
            items = (await session.execute(stmt)).scalars().all()
            total_items = len(items)
            paginated_items = items[(page-1)*ITEMS_PER_PAGE:page*ITEMS_PER_PAGE]
            for item in paginated_items:
                name = await _get_item_name(session, cat, item.catalog_id, lang)
                buttons.append([InlineKeyboardButton(f"{name} (G{item.grade})", callback_data=f"mkt_sell_item_artifact_{item.id}")])

        elif cat == "cauldron":
            stmt = select(PlayerCauldron).where(PlayerCauldron.player_id == player.telegram_id, PlayerCauldron.is_equipped == False)
            items = (await session.execute(stmt)).scalars().all()
            total_items = len(items)
            paginated_items = items[(page-1)*ITEMS_PER_PAGE:page*ITEMS_PER_PAGE]
            for item in paginated_items:
                name = await _get_item_name(session, cat, item.cauldron_id, lang)
                buttons.append([InlineKeyboardButton(f"{name}", callback_data=f"mkt_sell_item_cauldron_{item.id}")])

        if not buttons:
            text += t(lang, "no_items_category")
        else:
            total_pages = max(1, math.ceil(total_items / ITEMS_PER_PAGE))
            if total_pages > 1:
                buttons.extend(build_pagination_keyboard(page, total_pages, f"mkt_sell_cat_{cat}_", lang))
        
        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="mkt_sell_start")])
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def sell_item_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    parts = query.data.split("_")
    if len(parts) < 5:
        await safe_answer(query)
        return
    item_type = parts[3]
    try:
        instance_id = int(parts[4])
    except (ValueError, IndexError):
        await safe_answer(query)
        return
    
    context.user_data["sell_item"] = {"type": item_type, "id": instance_id}
    
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        text = t(lang, "choose_sell_mode")
        buttons = [
            [InlineKeyboardButton(f"💰 {t(lang, 'direct_sale')}", callback_data="mkt_sell_mode_direct")],
            [InlineKeyboardButton(f"🔨 {t(lang, 'auction')}", callback_data="mkt_sell_mode_auction")],
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="mkt_sell_start")]
        ]
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def sell_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    mode = query.data.split("_")[-1]
    context.user_data["sell_item"]["mode"] = mode
    
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        text = t(lang, "enter_price_stones")
        await query.message.edit_text(text, parse_mode="Markdown")
        context.user_data["awaiting_price"] = True

async def process_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    if not context.user_data.get("awaiting_price"): return
    
    try:
        price = int(update.message.text.replace(".", "").replace(",", ""))
        if price <= 0: raise ValueError
    except Exception as e:
        logger.error(f"Error in process_price_input parsing: {e}")
        lang = normalize_lang(update.effective_user.language_code)
        await update.message.reply_text(t(lang, "market_invalid_value"))
        return

    context.user_data["sell_item"]["price"] = price
    context.user_data["awaiting_price"] = False
    
    # Check if stackable to ask for quantity
    item_type = context.user_data["sell_item"]["type"]
    finalize = False
    
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        if item_type in ["herb", "pill", "ore"]:
            await update.message.reply_text(t(lang, "enter_quantity"))
            context.user_data["awaiting_qty"] = True
        else:
            context.user_data["sell_item"]["qty"] = 1
            finalize = True
            
    if finalize:
        await _finalize_sell_creation(update, context)

async def process_qty_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    if not context.user_data.get("awaiting_qty"): return
    
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        try:
            qty = int(update.message.text)
            if qty <= 0: raise ValueError
        except Exception as e:
            logger.error(f"Error in process_qty_input parsing: {e}")
            await update.message.reply_text(t(lang, "invalid_quantity"))
            return

    context.user_data["sell_item"]["qty"] = qty
    context.user_data["awaiting_qty"] = False
    await _finalize_sell_creation(update, context)

async def _finalize_sell_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    data = context.user_data["sell_item"]
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        
        listing, status = await create_listing(
            session, player, data["type"], data["id"], data["qty"], 
            data["price"], data["mode"] == "auction", 48
        )
        
        if status == "success":
            await session.commit()
            text = f"✅ {t(lang, 'listing_created_success')}"
        else:
            text = t(lang, f"market_err_{status}")
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_market")]])
        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def view_listing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    l_id = safe_parse_callback_uuid(query.data, "mkt_view_")
    if l_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"

        stmt = select(MarketplaceListing).where(MarketplaceListing.id == l_id)
        l = (await session.execute(stmt)).scalar_one_or_none()

        if not l or l.is_sold:
            await safe_answer(query, t(lang, "listing_not_found"), show_alert=True)
            return

        descr = await _get_item_descriptor(session, l, lang)
        item_name = descr["name"]
        grade_emoji = descr["grade_emoji"]
        stats_line = descr["stats_line"]

        # Determine seller display name
        is_npc = l.seller_id is None or (l.item_data or {}).get("npc")
        seller_display = (l.item_data or {}).get("seller_name", "🏮 Immortal Merchant") if is_npc else f"`{l.seller_id}`"

        header_emoji = grade_emoji if grade_emoji else "📦"
        text = f"{header_emoji} *{item_name}* (x{l.quantity})\n"
        text += f"————————————————————\n"
        if stats_line:
            text += f"📊 {stats_line}\n"
        text += f"👤 {t(lang, 'seller')}: {seller_display}\n"

        if l.is_auction:
            bid_display = format_currency(l.current_bid or l.unit_price)
            text += f"💰 {t(lang, 'price')}: {bid_display} {t(lang, 'currency_spirit_stones')}\n"
        else:
            unit_display = format_currency(l.unit_price)
            total_display = format_currency(l.unit_price * l.quantity)
            text += f"💰 {t(lang, 'market_unit_price')}: {unit_display} {t(lang, 'currency_spirit_stones')}\n"
            if l.quantity > 1:
                text += f"💎 {t(lang, 'market_total_price')}: {total_display} {t(lang, 'currency_spirit_stones')}\n"

        text += f"⏳ {t(lang, 'expires_in')}: {str(l.expires_at - datetime.now(timezone.utc)).split('.')[0]}\n"

        if l.is_auction:
            text += f"🔨 {t(lang, 'auction_mode')}\n"
            if l.highest_bidder:
                text += f"👑 {t(lang, 'highest_bidder')}: `{l.highest_bidder}`\n"

        buttons = []
        if is_npc or l.seller_id != player.telegram_id:
            if l.is_auction:
                buttons.append([InlineKeyboardButton(f"🔨 {t(lang, 'btn_bid')}", callback_data=f"mkt_bid_start_{l.id}")])
            else:
                # Quantity buttons for non-auction listings
                if l.quantity > 1:
                    qty_row = []
                    for q in [1, 5, 10]:
                        if q <= l.quantity:
                            qty_row.append(InlineKeyboardButton(
                                f"🛒 {q}x",
                                callback_data=f"mkt_buyqty_{q}_{l.id}"
                            ))
                    qty_row.append(InlineKeyboardButton(
                        f"🛒 {t(lang, 'market_buy_all')}",
                        callback_data=f"mkt_buy_confirm_{l.id}"
                    ))
                    buttons.append(qty_row)
                else:
                    buttons.append([InlineKeyboardButton(f"💰 {t(lang, 'btn_buy_now')}", callback_data=f"mkt_buy_confirm_{l.id}")])
        else:
            buttons.append([InlineKeyboardButton(f"❌ {t(lang, 'btn_cancel_listing')}", callback_data=f"mkt_cancel_{l.id}")])
            
        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_market")])
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

@rate_limit(1)
async def buy_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ⚠️ Era o ÚNICO dos 4 pontos de entrada deste ficheiro sem `@rate_limit`
    # (`market_command`:30, :762 e :1262 já o tinham). Como o `Player` comprador
    # nunca era travado FOR UPDATE antes de `spirit_stones -=` (ver abaixo), o
    # duplo-tap era um lost-update clássico a favor do comprador. Hoje é
    # teórico — o mercado tem zero listagens abertas em 239 jogadores — e é
    # exatamente por isso que se conserta agora, antes de voltar a ter tráfego.
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    l_id = safe_parse_callback_uuid(query.data, "mkt_buy_confirm_")
    if l_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        # ⚠️ O lock do comprador NÃO se faz aqui — vive em
        # `economy._lock_players_ordered`, que trava comprador e vendedor em
        # ordem ascendente de `telegram_id`. Travar o comprador antes da
        # listagem (o fix "óbvio") criava um deadlock AB-BA entre dois
        # jogadores a comprar a listagem um do outro.

        # Get listing info for notification before it's sold
        stmt = select(MarketplaceListing).where(MarketplaceListing.id == l_id)
        listing_info = (await session.execute(stmt)).scalar_one_or_none()
        is_npc_listing = False
        if listing_info:
            seller_id = listing_info.seller_id
            is_npc_listing = seller_id is None or (listing_info.item_data or {}).get("npc")
            item_name = await _get_item_name(session, listing_info.item_type, listing_info.item_id, lang)
            item_qty = listing_info.quantity
            total_price = listing_info.unit_price * listing_info.quantity

            if not is_npc_listing:
                from core.monetization import get_player_vip_level, get_vip_perks
                vip_lvl = await get_player_vip_level(session, seller_id)
                vip_perks = get_vip_perks(vip_lvl)
                base_tax = 0.05
                actual_tax_rate = max(0.0, base_tax - vip_perks["auction_tax_discount"])
            else:
                actual_tax_rate = 0.0

            tax = int(total_price * actual_tax_rate)
            received = total_price - tax

        listing, status = await buy_listing(session, player, l_id)
        if status == "success":
            mkt_ach = []
            if not is_npc_listing:
                from core.achievement_engine import check_achievements
                mkt_ach = await check_achievements(session, seller_id, "market_sales", 1)
            await session.commit()
            await safe_answer(query, t(lang, "purchase_success"), show_alert=True)

            # Notify seller (skip for NPC listings)
            if not is_npc_listing:
                try:
                    stmt_seller = select(Player.language).where(Player.telegram_id == seller_id)
                    s_lang = (await session.execute(stmt_seller)).scalar() or "en"
                    msg = f"💰 *{t(s_lang, 'item_sold')}*\n\n{t(s_lang, 'item_sold_desc').format(item=item_name, qty=item_qty, price=format_currency(total_price), received=format_currency(received))}"
                    await context.bot.send_message(chat_id=seller_id, text=msg, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Error notifying seller in buy_confirm_callback: {e}")
                    pass
            if mkt_ach:
                from handlers.achievements import notify_achievements
                await notify_achievements(context, seller_id, mkt_ach)
        else:
            await safe_answer(query, t(lang, f"market_err_{status}"), show_alert=True)
            
        await _show_market(update, context, session, player, None, 0)

async def buy_partial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quantity button clicks: mkt_buyqty_{qty}_{listing_id}"""
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    # callback_data format: mkt_buyqty_{qty}_{uuid}
    parts = query.data.split("_")
    # parts = ['mkt', 'buyqty', '<qty>', '<uuid>']
    try:
        qty = int(parts[2])
        l_id = uuid.UUID(parts[3])
    except (ValueError, IndexError):
        await safe_answer(query, "Invalid data", show_alert=True)
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"

        # Pre-fetch listing info for seller notification
        stmt = select(MarketplaceListing).where(MarketplaceListing.id == l_id)
        listing_info = (await session.execute(stmt)).scalar_one_or_none()
        is_npc_listing = False
        if listing_info:
            seller_id = listing_info.seller_id
            is_npc_listing = seller_id is None or (listing_info.item_data or {}).get("npc")
            item_name = await _get_item_name(session, listing_info.item_type, listing_info.item_id, lang)
            total_price = listing_info.unit_price * qty

            if not is_npc_listing:
                from core.monetization import get_player_vip_level, get_vip_perks
                vip_lvl = await get_player_vip_level(session, seller_id)
                vip_perks = get_vip_perks(vip_lvl)
                base_tax = 0.05
                actual_tax_rate = max(0.0, base_tax - vip_perks["auction_tax_discount"])
            else:
                actual_tax_rate = 0.0

            tax = int(total_price * actual_tax_rate)
            received = total_price - tax

        listing, status = await buy_partial(session, player, l_id, qty)
        if status == "success":
            mkt_ach = []
            if not is_npc_listing:
                from core.achievement_engine import check_achievements
                mkt_ach = await check_achievements(session, seller_id, "market_sales", 1)
            await session.commit()
            # MV-3 — o alerta mostra o valor REALMENTE debitado (estado regional
            # pode ajustar o preço local do comprador; _region_paid = a verdade).
            _paid = getattr(listing, "_region_paid", None) or total_price
            await safe_answer(query,
                t(lang, "market_buy_partial", qty=qty, item=item_name, total=format_currency(_paid)),
                show_alert=True
            )

            # Notify seller (skip for NPC)
            if not is_npc_listing:
                try:
                    stmt_seller = select(Player.language).where(Player.telegram_id == seller_id)
                    s_lang = (await session.execute(stmt_seller)).scalar() or "en"
                    msg = (
                        f"💰 *{t(s_lang, 'item_sold')}*\n\n"
                        f"{t(s_lang, 'item_sold_desc').format(item=item_name, qty=qty, price=format_currency(total_price), received=format_currency(received))}"
                    )
                    await context.bot.send_message(chat_id=seller_id, text=msg, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Error notifying seller in buy_partial_callback: {e}")
            if mkt_ach:
                from handlers.achievements import notify_achievements
                await notify_achievements(context, seller_id, mkt_ach)
        else:
            await safe_answer(query, t(lang, f"market_err_{status}"), show_alert=True)

        await _show_market(update, context, session, player, None, 0)


async def cancel_listing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    l_id = safe_parse_callback_uuid(query.data, "mkt_cancel_")
    if l_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"

        listing, status = await cancel_listing(session, player, l_id)
        if status == "success":
            await session.commit()
            await safe_answer(query, t(lang, "listing_cancelled"), show_alert=True)
        else:
            await safe_answer(query, t(lang, f"market_err_{status}"), show_alert=True)

        await _show_market(update, context, session, player, None, 0)


async def bid_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    l_id = query.data.split("_")[-1]
    context.user_data["bid_listing_id"] = l_id
    context.user_data["awaiting_bid"] = True
    
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        await query.message.reply_text(t(lang, "enter_bid_amount"))
        await safe_answer(query)

async def process_bid_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    if not context.user_data.get("awaiting_bid"): return
    
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        try:
            amount = int(update.message.text.replace(".", "").replace(",", ""))
        except Exception as e:
            logger.error(f"Error in process_bid_input parsing: {e}")
            await update.message.reply_text(t(lang, "invalid_value"))
            return

        try:
            l_id = uuid.UUID(context.user_data["bid_listing_id"])
        except (ValueError, KeyError):
            await update.message.reply_text(t(lang, "generic_error"))
            return

        listing, status = await place_bid(session, player, l_id, amount)
        if status == "success":
            await session.commit()
            await update.message.reply_text(f"✅ {t(lang, 'bid_success').format(amount=format_currency(amount))}")
        else:
            await update.message.reply_text(t(lang, f"market_err_{status}"))
            
    context.user_data["awaiting_bid"] = False

@safe_handler
@rate_limit(1)
async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        await update.message.reply_text(
            f"🤝 *{t(lang, 'trade_start_wizard_title')}*\n\n{t(lang, 'trade_start_wizard_desc')}",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_trade_daoname"] = True

async def trade_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    trade_id = safe_parse_callback_uuid(query.data, "trd_accept_")
    if trade_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"

        stmt = select(P2PTrade).where(P2PTrade.id == trade_id)
        trade = (await session.execute(stmt)).scalar_one_or_none()

        if not trade or trade.status != "pending":
            await safe_answer(query, t(lang, "trade_not_found"), show_alert=True)
            return
            
        if query.from_user.id != trade.target_id:
            await safe_answer(query, t(lang, "trade_target_only"), show_alert=True)
            return

        # Notify initiator
        try:
            stmt_init = select(Player.language).where(Player.telegram_id == trade.initiator_id)
            i_lang = (await session.execute(stmt_init)).scalar() or "en"
            await context.bot.send_message(chat_id=trade.initiator_id, text=f"✅ {t(i_lang, 'trade_partner_accepted')}")
        except Exception as e:
            logger.error(f"Error notifying initiator in trade_accept_callback: {e}")
            pass
        
        trade.target_msg_id = query.message.message_id
        await session.commit()
        await _show_trade_menu(update, context, session, trade)

async def _show_trade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, session, trade):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    # Fetch language and DAO name for both players
    stmt_i = select(Player.language, Player.dao_name).where(Player.telegram_id == trade.initiator_id)
    row_i = (await session.execute(stmt_i)).one_or_none()
    lang_i = (row_i[0] if row_i else None) or "en"
    initiator_dao = escape_markdown((row_i[1] if row_i else None) or str(trade.initiator_id))
    stmt_t = select(Player.language, Player.dao_name).where(Player.telegram_id == trade.target_id)
    row_t = (await session.execute(stmt_t)).one_or_none()
    lang_t = (row_t[0] if row_t else None) or "en"
    target_dao = escape_markdown((row_t[1] if row_t else None) or str(trade.target_id))

    # Check expiry
    if trade.expires_at < datetime.now(timezone.utc):
        trade.status = "expired"
        await session.commit()
        msg_i = f"⏳ {t(lang_i, 'trade_expired')}"
        msg_t = f"⏳ {t(lang_t, 'trade_expired')}"
        if trade.initiator_msg_id:
            try: await context.bot.edit_message_text(chat_id=trade.initiator_id, message_id=trade.initiator_msg_id, text=msg_i)
            except Exception as e:
                logger.error(f"Error updating initiator expired trade msg: {e}")
                pass
        if trade.target_msg_id:
            try: await context.bot.edit_message_text(chat_id=trade.target_id, message_id=trade.target_msg_id, text=msg_t)
            except Exception as e:
                logger.error(f"Error updating target expired trade msg: {e}")
                pass
        return

    def build_text(lang, is_initiator_ui):
        text = f"🤝 *{t(lang, 'trade_menu_title')}*\n\n"

        # Initiator Info
        i_stones = trade.offer_items.get("stones", 0)
        i_items = trade.offer_items.get("items", [])
        text += f"👤 *{t(lang, 'initiator')}* — *{initiator_dao}*:\n"
        text += f"💰 {format_currency(i_stones)} Stones\n"
        for it in i_items:
            text += f"📦 {it['name']} (x{it['qty']})\n"
        text += f"{'✅ ' + t(lang, 'confirmed') if trade.initiator_confirmed else '⏳ ' + t(lang, 'pending')}\n\n"

        # Target Info
        t_stones = trade.request_items.get("stones", 0)
        t_items = trade.request_items.get("items", [])
        text += f"👤 *{t(lang, 'target')}* — *{target_dao}*:\n"
        text += f"💰 {format_currency(t_stones)} Stones\n"
        for it in t_items:
            text += f"📦 {it['name']} (x{it['qty']})\n"
        text += f"{'✅ ' + t(lang, 'confirmed') if trade.target_confirmed else '⏳ ' + t(lang, 'pending')}\n"
        return text

    def build_kb(lang):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"➕ {t(lang, 'btn_items')}", callback_data=f"trd_add_{trade.id}"),
             InlineKeyboardButton(f"💰 {t(lang, 'btn_stones')}", callback_data=f"trd_stones_{trade.id}")],
            [InlineKeyboardButton(f"✅ {t(lang, 'btn_confirm')}", callback_data=f"trd_confirm_{trade.id}")],
            [InlineKeyboardButton(f"❌ {t(lang, 'btn_cancel')}", callback_data=f"trd_cancel_{trade.id}")]
        ])

    async def safe_update(u_id, msg_id_attr, t_text, t_kb):
        current_msg_id = getattr(trade, msg_id_attr)
        try:
            if current_msg_id:
                await context.bot.edit_message_text(
                    chat_id=u_id,
                    message_id=current_msg_id,
                    text=t_text,
                    parse_mode="Markdown",
                    reply_markup=t_kb
                )
            else:
                raise Exception("No msg id")
        except Exception as e:
            logger.error(f"Error editing message in safe_update for user {u_id}: {e}")
            try:
                msg = await context.bot.send_message(
                    chat_id=u_id,
                    text=t_text,
                    parse_mode="Markdown",
                    reply_markup=t_kb
                )
                setattr(trade, msg_id_attr, msg.message_id)
                return True # Signal that we need to commit
            except Exception as e2:
                logger.error(f"Error sending fallback message in safe_update for user {u_id}: {e2}")
                pass
        return False

    # Update Initiator UI
    needs_commit_i = await safe_update(trade.initiator_id, "initiator_msg_id", build_text(lang_i, True), build_kb(lang_i))
    # Update Target UI
    needs_commit_t = await safe_update(trade.target_id, "target_msg_id", build_text(lang_t, False), build_kb(lang_t))
    
    if needs_commit_i or needs_commit_t:
        await session.commit()

async def trade_add_item_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    trade_id = query.data.split("_")[-1]
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        try:
            trade_id_uuid = uuid.UUID(trade_id)
        except (ValueError, IndexError):
            return
        stmt = select(P2PTrade).where(P2PTrade.id == trade_id_uuid)
        trade = (await session.execute(stmt)).scalar_one_or_none()
        if not trade or trade.status != "pending":
            await safe_answer(query, t(lang, "trade_not_found"), show_alert=True)
            return
        if query.from_user.id not in (trade.initiator_id, trade.target_id):
            await safe_answer(query, t(lang, "trade_not_participant"), show_alert=True)
            return
    text = t(lang, "trade_add_items_title")
    buttons = [
        [InlineKeyboardButton(t(lang, "btn_market_herbs"), callback_data=f"trd_cat_herb_{trade_id}")],
        [InlineKeyboardButton(t(lang, "btn_market_pills"), callback_data=f"trd_cat_pill_{trade_id}")],
        [InlineKeyboardButton(t(lang, "btn_market_ores"), callback_data=f"trd_cat_ore_{trade_id}")],
        [InlineKeyboardButton(t(lang, "btn_market_artifacts"), callback_data=f"trd_cat_art_{trade_id}")],
        [InlineKeyboardButton(t(lang, "btn_market_cauldrons"), callback_data=f"trd_cat_caul_{trade_id}")],
        [InlineKeyboardButton(t(lang, "btn_market_back"), callback_data=f"trd_refresh_{trade_id}")]
    ]
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def trade_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("_")
    cat = parts[2]
    trade_id = parts[3]
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        try:
            trade_id_uuid = uuid.UUID(trade_id)
        except (ValueError, IndexError):
            return
        stmt_trade = select(P2PTrade).where(P2PTrade.id == trade_id_uuid)
        trade = (await session.execute(stmt_trade)).scalar_one_or_none()
        if not trade or trade.status != "pending":
            await safe_answer(query, t(lang, "trade_not_found"), show_alert=True)
            return
        if query.from_user.id not in (trade.initiator_id, trade.target_id):
            await safe_answer(query, t(lang, "trade_not_participant"), show_alert=True)
            return
        buttons = []
        if cat in ["herb", "pill"]:
            stmt = select(PlayerInventory).where(PlayerInventory.player_id == player.telegram_id, PlayerInventory.item_type == cat)
            items = (await session.execute(stmt)).scalars().all()
            for item in items:
                name = await _get_item_name(session, cat, item.item_id, lang)
                buttons.append([InlineKeyboardButton(f"{name} (x{item.quantity})", callback_data=f"trd_it_{cat}_{item.id}_{trade_id}")])
        elif cat == "ore":
            stmt = select(PlayerOre).where(PlayerOre.player_id == player.telegram_id)
            items = (await session.execute(stmt)).scalars().all()
            for item in items:
                name = await _get_item_name(session, cat, item.ore_id, lang)
                buttons.append([InlineKeyboardButton(f"{name} (x{item.quantity})", callback_data=f"trd_it_ore_{item.id}_{trade_id}")])
        elif cat == "art":
            stmt = select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id, PlayerArtifact.is_equipped == False)
            items = (await session.execute(stmt)).scalars().all()
            for item in items:
                name = await _get_item_name(session, "artifact", item.catalog_id, lang)
                buttons.append([InlineKeyboardButton(f"{name} (G{item.grade})", callback_data=f"trd_it_art_{item.id}_{trade_id}")])
        elif cat == "caul":
            stmt = select(PlayerCauldron).where(PlayerCauldron.player_id == player.telegram_id, PlayerCauldron.is_equipped == False)
            items = (await session.execute(stmt)).scalars().all()
            for item in items:
                name = await _get_item_name(session, "cauldron", item.cauldron_id, lang)
                buttons.append([InlineKeyboardButton(f"{name}", callback_data=f"trd_it_caul_{item.id}_{trade_id}")])
        if not buttons: buttons.append([InlineKeyboardButton(t(lang, "btn_market_empty"), callback_data="none")])
        buttons.append([InlineKeyboardButton(t(lang, "btn_market_back"), callback_data=f"trd_add_{trade_id}")])
        await query.message.edit_text(t(lang, "market_choose_item"), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def trade_item_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    parts = query.data.split("_")
    item_type = parts[2]
    instance_id = int(parts[3])
    trade_id = parts[4]
    if item_type in ["herb", "pill", "ore"]:
        context.user_data["trd_it"] = {"type": item_type, "id": instance_id, "trade_id": trade_id}
        lang = normalize_lang(update.effective_user.language_code)
        await query.message.reply_text(t(lang, "market_enter_qty"))
        context.user_data["awaiting_trd_qty"] = True
    else: await _add_item_to_trade(update, context, trade_id, item_type, instance_id, 1)

async def process_trd_qty_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    if not context.user_data.get("awaiting_trd_qty"): return
    try:
        qty = int(update.message.text)
        if qty <= 0: raise ValueError
    except Exception as e:
        logger.error(f"Error in process_trd_qty_input parsing: {e}")
        lang = normalize_lang(update.effective_user.language_code)
        await update.message.reply_text(t(lang, "market_invalid_qty"))
        return
    data = context.user_data["trd_it"]
    context.user_data["awaiting_trd_qty"] = False
    await _add_item_to_trade(update, context, data["trade_id"], data["type"], data["id"], qty)

async def _add_item_to_trade(update: Update, context: ContextTypes.DEFAULT_TYPE, trade_id, item_type, instance_id, qty):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        try:
            trade_id_uuid = uuid.UUID(trade_id)
        except (ValueError, IndexError):
            return
        stmt = select(P2PTrade).where(P2PTrade.id == trade_id_uuid)
        trade = (await session.execute(stmt)).scalar_one_or_none()
        if not trade or trade.status != "pending": return
        if update.effective_user.id not in (trade.initiator_id, trade.target_id):
            await update.effective_message.reply_text(t(player.language or "en", "trade_not_participant"))
            return
        is_initiator = player.telegram_id == trade.initiator_id
        offer = trade.offer_items if is_initiator else trade.request_items
        if "items" not in offer: offer["items"] = []
        actual_type = item_type
        if item_type == "art": actual_type = "artifact"
        if item_type == "caul": actual_type = "cauldron"

        # Whitelist guard: reject any type not explicitly approved for P2P trading
        if actual_type not in TRADEABLE_ITEM_TYPES:
            await update.effective_message.reply_text(t(player.language, "trade_err_forbidden_item"))
            return

        item_name, item_data, catalog_id = "", {}, 0
        if actual_type in ["herb", "pill"]:
            stmt_it = select(PlayerInventory).where(PlayerInventory.id == instance_id, PlayerInventory.player_id == player.telegram_id)
            p_inv = (await session.execute(stmt_it)).scalar_one_or_none()
            if not p_inv or p_inv.quantity < qty:
                await update.effective_message.reply_text(t(player.language, "market_err_item_unavailable"))
                return
            catalog_id = p_inv.item_id
            # Preserve the crafted quality tier through escrow (review 2026-06-13):
            # without this a Perfect/Divine/Heavenly pill settled as Normal.
            item_data = {"quality": p_inv.quality or "normal"}
            p_inv.quantity -= qty
            if p_inv.quantity <= 0: await session.delete(p_inv)
            item_name = await _get_item_name(session, actual_type, catalog_id, player.language)
        elif actual_type == "ore":
            stmt_it = select(PlayerOre).where(PlayerOre.id == instance_id, PlayerOre.player_id == player.telegram_id)
            p_ore = (await session.execute(stmt_it)).scalar_one_or_none()
            if not p_ore or p_ore.quantity < qty:
                await update.effective_message.reply_text(t(player.language, "market_err_item_unavailable"))
                return
            catalog_id = p_ore.ore_id
            p_ore.quantity -= qty
            if p_ore.quantity <= 0: await session.delete(p_ore)
            item_name = await _get_item_name(session, actual_type, catalog_id, player.language)
        elif actual_type == "artifact":
            # Medium (v16.6): lock the source row so two concurrent escrows of the
            # same artifact serialize — the second sees it already gone (deleted)
            # and errors out, closing the P2P duplication window.
            stmt_it = select(PlayerArtifact).where(PlayerArtifact.id == instance_id, PlayerArtifact.player_id == player.telegram_id).with_for_update()
            art = (await session.execute(stmt_it)).scalar_one_or_none()
            if not art or art.is_equipped:
                await update.effective_message.reply_text(t(player.language, "market_err_art_unavailable"))
                return
            catalog_id = art.catalog_id
            item_data = {
                "grade": art.grade,
                "enchant_rune": art.enchant_rune,
                "has_spirit": art.has_spirit,
                "spirit_name": art.spirit_name,
                "custom_stats": art.custom_stats
            }
            item_name = await _get_item_name(session, "artifact", catalog_id, player.language)
            await session.delete(art)
        elif actual_type == "cauldron":
            # Medium (v16.6): lock the source row (see artifact branch above).
            stmt_it = select(PlayerCauldron).where(PlayerCauldron.id == instance_id, PlayerCauldron.player_id == player.telegram_id).with_for_update()
            caul = (await session.execute(stmt_it)).scalar_one_or_none()
            if not caul or caul.is_equipped:
                await update.effective_message.reply_text(t(player.language, "market_err_cauldron_unavailable"))
                return
            catalog_id = caul.cauldron_id
            item_data = {"durability": caul.durability}
            item_name = await _get_item_name(session, "cauldron", catalog_id, player.language)
            await session.delete(caul)

        offer["items"].append({"type": actual_type, "id": catalog_id, "qty": qty, "name": item_name, "data": item_data})
        trade.initiator_confirmed, trade.target_confirmed = False, False
        
        # Explicitly notify SQLAlchemy about the JSONB change
        flag_modified(trade, "offer_items" if is_initiator else "request_items")
        
        await session.commit()
        await _show_trade_menu(update, context, session, trade)

async def trade_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    trade_id = safe_parse_callback_uuid(query.data, "trd_confirm_")
    if trade_id is None:
        return
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if player: lang = player.language or "en"
        stmt = select(P2PTrade).where(P2PTrade.id == trade_id)
        trade = (await session.execute(stmt)).scalar_one_or_none()
        if not trade or trade.status != "pending": return
        if query.from_user.id not in (trade.initiator_id, trade.target_id):
            await safe_answer(query, t(lang, "trade_not_participant"), show_alert=True)
            return
        if query.from_user.id == trade.initiator_id: trade.initiator_confirmed = True
        elif query.from_user.id == trade.target_id: trade.target_confirmed = True
        if trade.initiator_confirmed and trade.target_confirmed:
            total_stones = (trade.offer_items.get("stones", 0) +
                            trade.request_items.get("stones", 0))
            success = await execute_trade(session, trade)
            if success:
                await session.commit()
                await query.message.edit_text(t(lang, "trade_finished_success"))
                other_id = trade.target_id if query.from_user.id == trade.initiator_id else trade.initiator_id
                stmt_other = select(Player.language).where(Player.telegram_id == other_id)
                o_lang = (await session.execute(stmt_other)).scalar() or "en"
                try: await context.bot.send_message(chat_id=other_id, text=t(o_lang, "trade_finished_success"))
                except Exception as e:
                    logger.error(f"Error notifying other party in trade_confirm_callback: {e}")
                    pass
                # Alert admins for very large trades (>= 1M stones)
                try:
                    from handlers.admin_monetization import alert_admins_suspicious_trade
                    await alert_admins_suspicious_trade(
                        context.bot, str(trade.id),
                        trade.initiator_id, trade.target_id, total_stones
                    )
                except Exception:
                    pass
            else:
                await safe_answer(query, t(lang, "ans_erro_ao_executar_troca"), show_alert=True)
                trade.initiator_confirmed, trade.target_confirmed = False, False
                await session.commit()
        else:
            await session.commit()
            await _show_trade_menu(update, context, session, trade)

async def trade_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    trade_id = safe_parse_callback_uuid(query.data, "trd_cancel_")
    if trade_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if player: lang = player.language or "en"
        stmt = select(P2PTrade).where(P2PTrade.id == trade_id)
        trade = (await session.execute(stmt)).scalar_one_or_none()
        if not trade or trade.status != "pending": return
        if query.from_user.id not in (trade.initiator_id, trade.target_id):
            await safe_answer(query, t(lang, "trade_not_participant"), show_alert=True)
            return

        await cancel_trade(session, trade)
        await session.commit()
        
        msg = t(lang, "trade_cancelled")
        # Update Initiator
        if trade.initiator_msg_id:
            try: await context.bot.edit_message_text(chat_id=trade.initiator_id, message_id=trade.initiator_msg_id, text=msg)
            except Exception as e:
                logger.error(f"Error editing initiator message in trade_cancel_callback: {e}")
                pass
        # Update Target
        if trade.target_msg_id:
            try: await context.bot.edit_message_text(chat_id=trade.target_id, message_id=trade.target_msg_id, text=msg)
            except Exception as e:
                logger.error(f"Error editing target message in trade_cancel_callback: {e}")
                pass

async def trade_stones_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    trade_id = query.data.split("_")[-1]
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        try:
            trade_id_uuid = uuid.UUID(trade_id)
        except (ValueError, IndexError):
            return
        stmt = select(P2PTrade).where(P2PTrade.id == trade_id_uuid)
        trade = (await session.execute(stmt)).scalar_one_or_none()
        if not trade or trade.status != "pending":
            await safe_answer(query, t(lang, "trade_not_found"), show_alert=True)
            return
        if query.from_user.id not in (trade.initiator_id, trade.target_id):
            await safe_answer(query, t(lang, "trade_not_participant"), show_alert=True)
            return
    context.user_data["trade_stones_id"] = trade_id
    context.user_data["awaiting_trade_stones"] = True
    await query.message.reply_text(t(lang, "market_enter_stones_offer"))
    await safe_answer(query)

async def process_trade_stones_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    if not context.user_data.get("awaiting_trade_stones"): return
    
    try:
        amount = int(update.message.text.replace(".", "").replace(",", ""))
        if amount < 0: raise ValueError
    except Exception as e:
        logger.error(f"Error in process_trade_stones_input parsing: {e}")
        lang = normalize_lang(update.effective_user.language_code)
        await update.message.reply_text(t(lang, "market_invalid_value"))
        return

    try:
        trade_id = uuid.UUID(context.user_data["trade_stones_id"])
    except (ValueError, KeyError):
        return
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if player.spirit_stones < amount:
            await update.message.reply_text(t(player.language, "insufficient_stones"))
            return
            
        stmt = select(P2PTrade).where(P2PTrade.id == trade_id)
        trade = (await session.execute(stmt)).scalar_one_or_none()
        if not trade or trade.status != "pending":
            await update.message.reply_text(t(player.language or "en", "trade_not_found"))
            return
        if player.telegram_id not in (trade.initiator_id, trade.target_id):
            await update.message.reply_text(t(player.language or "en", "trade_not_participant"))
            return
        
        if player.telegram_id == trade.initiator_id:
            trade.offer_items["stones"] = amount
            flag_modified(trade, "offer_items")
        else:
            trade.request_items["stones"] = amount
            flag_modified(trade, "request_items")
        # ANY mutation invalidates BOTH confirmations (mirror _add_item_to_trade):
        # the deal the other side confirmed no longer exists. Previously only the
        # changer's confirm reset — a bait-and-switch window: confirm, then lower
        # your stones; the stale confirm executes the worse deal (2026-06-11).
        trade.initiator_confirmed, trade.target_confirmed = False, False

        await session.commit()
        await _show_trade_menu(update, context, session, trade)
        
    context.user_data["awaiting_trade_stones"] = False

@safe_handler
@rate_limit(1)
async def market_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    data = query.data
    
    if data == "cmd_market":
        await market_command(update, context)
        return True
    if data.startswith("mkt_page_"):
        parts = data.split("_")
        page = int(parts[-1]) - 1
        context.user_data["page"] = max(0, page)
        filter_type = parts[2] if len(parts) > 3 and parts[2] != "all" else None
        
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            await _show_market(update, context, session, player, filter_type, page)
        return True
    if data.startswith("mkt_filter_"):
        cat = data.split("_")[-1]
        context.user_data["page"] = 0
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            await _show_market(update, context, session, player, cat, 0)
        return True
    if data == "mkt_sell_start":
        await sell_wizard(update, context)
        return True
    if data.startswith("mkt_sell_cat_"):
        await sell_category_callback(update, context)
        return True
    if data.startswith("mkt_sell_item_"):
        await sell_item_select_callback(update, context)
        return True
    if data.startswith("mkt_sell_mode_"):
        await sell_mode_callback(update, context)
        return True
    if data.startswith("mkt_view_"):
        await view_listing_callback(update, context)
        return True
    if data.startswith("mkt_buyqty_"):
        await buy_partial_callback(update, context)
        return True
    if data.startswith("mkt_buy_confirm_"):
        await buy_confirm_callback(update, context)
        return True
    if data.startswith("mkt_bid_start_"):
        await bid_start_callback(update, context)
        return True
    if data.startswith("mkt_cancel_"):
        await cancel_listing_callback(update, context)
        return True

    # Trade Callbacks
    if data.startswith("trd_accept_"):
        await trade_accept_callback(update, context)
        return True
    if data.startswith("trd_refresh_"):
        trade_id = safe_parse_callback_uuid(data, "trd_refresh_")
        if trade_id is None:
            return True
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            lang = (player.language if player else None) or "en"
            stmt = select(P2PTrade).where(P2PTrade.id == trade_id)
            trade = (await session.execute(stmt)).scalar_one_or_none()
            if not trade:
                await safe_answer(update.callback_query, t(lang, "trade_not_found"), show_alert=True)
                return True
            if update.effective_user.id not in (trade.initiator_id, trade.target_id):
                await safe_answer(update.callback_query, t(lang, "trade_not_participant"), show_alert=True)
                return True
            await _show_trade_menu(update, context, session, trade)
        return True
    if data.startswith("trd_add_"):
        await trade_add_item_wizard(update, context)
        return True
    if data.startswith("trd_cat_"):
        await trade_category_callback(update, context)
        return True
    if data.startswith("trd_it_"):
        await trade_item_select_callback(update, context)
        return True
    if data.startswith("trd_stones_"):
        await trade_stones_start_callback(update, context)
        return True
    if data.startswith("trd_confirm_"):
        await trade_confirm_callback(update, context)
        return True
    if data.startswith("trd_cancel_"):
        await trade_cancel_callback(update, context)
        return True
    
    if data.startswith("mkt_history_"):
        page = safe_parse_callback_int(data, "mkt_history_")
        if page is None:
            return True
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            await _show_history(update, context, session, player, page)
        return True
    
    if data.startswith("mkt_tx_view_"):
        await view_tx_details_callback(update, context)
        return True
    
    if data == "trd_help":
        await trade_dashboard(update, context)
        return True
    if data == "trd_list_pending":
        await trade_list_pending(update, context)
        return True
    if data == "trd_start_wizard":
        await trade_start_wizard(update, context)
        return True
    
    return False

async def trade_start_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        await query.message.edit_text(f"🤝 *{t(lang, 'trade_start_wizard_title')}*\n\n{t(lang, 'trade_start_wizard_desc')}", parse_mode="Markdown")
        context.user_data["awaiting_trade_daoname"] = True

async def process_trade_daoname_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    if not context.user_data.get("awaiting_trade_daoname"): return

    dao_name_input = update.message.text.strip()
    context.user_data["awaiting_trade_daoname"] = False

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        # Search by dao_name — case-insensitive
        stmt = select(Player).where(func.lower(Player.dao_name) == dao_name_input.lower())
        target_user = (await session.execute(stmt)).scalar_one_or_none()

        if not target_user:
            await update.message.reply_text(f"❌ {t(lang, 'player_not_found').format(username=dao_name_input)}")
            return

        if target_user.telegram_id == player.telegram_id:
            await update.message.reply_text(f"❌ {t(lang, 'trade_self_error')}")
            return

        if abs(player.realm - target_user.realm) >= REALM_HIERARCHY_GAP:
            await update.message.reply_text(t(lang, "realm_too_low_for_interaction"), parse_mode="Markdown")
            return

        trade, status = await initiate_trade(session, player.telegram_id, target_user.telegram_id)
        if status == "success" or status == "already_pending":
            await session.commit()

            initiator_name = escape_markdown(player.dao_name or get_display_name(player))
            target_name = escape_markdown(target_user.dao_name or get_display_name(target_user))
            target_mention = f"*{target_name}*"

            # 1. Message in Private
            await update.message.reply_text(f"✅ {t(lang, 'trade_request_sent').format(target=target_mention)}", parse_mode="Markdown")

            # 2. DM to Target
            try:
                t_lang = target_user.language or "en"
                dm_target = f"🤝 *{t(t_lang, 'trade_invite_title')}*\n\n{t(t_lang, 'trade_invite_dm').format(initiator=initiator_name)}"
                kb_accept = InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ {t(t_lang, 'btn_accept_trade')}", callback_data=f"trd_accept_{trade.id}")]])
                await context.bot.send_message(chat_id=target_user.telegram_id, text=dm_target, parse_mode="Markdown", reply_markup=kb_accept)
            except Exception as e:
                logger.error(f"Error sending DM to trade target in process_trade_daoname_input: {e}")
                await update.message.reply_text(f"⚠️ {t(lang, 'trade_dm_error').format(target=target_mention)}")

            # 3. Open menu for Initiator
            try:
                dm_init = f"🤝 *{t(lang, 'trade_menu_title')}*\n\n{t(lang, 'trade_waiting_target').format(target=target_name)}"
                msg = await context.bot.send_message(chat_id=player.telegram_id, text=dm_init, parse_mode="Markdown")
                trade.initiator_msg_id = msg.message_id
                await session.commit()
            except Exception as e:
                logger.error(f"Error opening trade menu for initiator in process_trade_daoname_input: {e}")
                pass
        else:
            await update.message.reply_text(t(lang, f"market_err_{status}"))

async def trade_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        
        text = f"🤝 *{t(lang, 'trade_dashboard_title')}*\n\n{t(lang, 'trade_dashboard_desc')}"
        
        buttons = [
            [InlineKeyboardButton(f"📜 {t(lang, 'btn_history')}", callback_data="mkt_history_0")],
            [InlineKeyboardButton(f"📨 {t(lang, 'btn_pending_trades')}", callback_data="trd_list_pending")],
            [InlineKeyboardButton(f"➕ {t(lang, 'btn_start_new_trade')}", callback_data="trd_start_wizard")],
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_market")]
        ]
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def trade_list_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"
        
        # Find trades where player is initiator or target
        stmt = select(P2PTrade).where(
            and_(
                P2PTrade.status == "pending",
                or_(P2PTrade.initiator_id == player.telegram_id, P2PTrade.target_id == player.telegram_id)
            )
        ).order_by(desc(P2PTrade.created_at))
        
        trades = (await session.execute(stmt)).scalars().all()
        
        text = f"📨 *{t(lang, 'pending_trades_title')}*\n\n"
        buttons = []
        
        if not trades:
            text += t(lang, "no_pending_trades")
        else:
            # Collect all other-player IDs to fetch DAO names in one pass
            other_ids = {
                (tr.target_id if tr.initiator_id == player.telegram_id else tr.initiator_id)
                for tr in trades
            }
            stmt_names = select(Player.telegram_id, Player.dao_name).where(Player.telegram_id.in_(other_ids))
            dao_name_map = {row[0]: row[1] for row in (await session.execute(stmt_names)).all()}

            for tr in trades:
                role = f"📤 {t(lang, 'sent')}" if tr.initiator_id == player.telegram_id else f"📥 {t(lang, 'received')}"
                other_id = tr.target_id if tr.initiator_id == player.telegram_id else tr.initiator_id
                other_dao = escape_markdown(dao_name_map.get(other_id) or str(other_id))

                text += f"• {role} — *{other_dao}*\n"
                text += f"  └ {t(lang, 'expires_in')}: {str(tr.expires_at - datetime.now(timezone.utc)).split('.')[0]}\n"

                btn_text = f"🤝 {t(lang, 'trade_with')} {other_dao}"
                buttons.append([InlineKeyboardButton(btn_text, callback_data=f"trd_refresh_{tr.id}")])

        buttons.append([InlineKeyboardButton(f"🔙 {t(lang, 'btn_back')}", callback_data="trd_help")])
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def _show_history(update: Update, context: ContextTypes.DEFAULT_TYPE, session, player, page):
    lang = player.language or "en"
    limit = 10
    offset = page * limit
    
    try:
        txs = await get_player_transactions(session, player.telegram_id, limit, offset)
    except Exception as e:
        # Fallback if 'details' column doesn't exist yet
        from database.models import Transaction
        # ⚠️ Este é o ÚNICO leitor de `transactions` em todo o repo sem filtro de
        # `type` — os outros cinco usam whitelist (`economy.get_player_transactions`
        # e `profession_engine.generate_market_reports` filtram
        # `IN ('buy','auction',...)`). Sem a exclusão abaixo, uma linha de carga
        # da Caravana (MV-9.5, `type='caravan'`) entrava no histórico do jogador
        # e renderizava com o ícone "❓" e o slug CRU como nome, porque a cadeia
        # if/elif de baixo só cobre buy/sell/auction/trade/fee. A caravana é
        # escambo e não pertence ao extrato de compras.
        stmt = select(Transaction).where(
            or_(Transaction.from_player == player.telegram_id, Transaction.to_player == player.telegram_id),
            Transaction.type != "caravan",
        ).order_by(desc(Transaction.created_at)).offset(offset).limit(limit)
        # We exclude 'details' from the query manually to avoid the error
        from sqlalchemy.orm import defer
        stmt = stmt.options(defer(Transaction.details))
        res = await session.execute(stmt)
        txs = res.scalars().all()
    
    # Batch-fetch dao_names for other players
    other_ids = set()
    for tx in txs:
        other_id = tx.to_player if tx.from_player == player.telegram_id else tx.from_player
        if other_id:
            other_ids.add(other_id)

    dao_map = {}
    if other_ids:
        stmt_names = select(Player.telegram_id, Player.dao_name).where(Player.telegram_id.in_(other_ids))
        dao_map = {row[0]: row[1] for row in (await session.execute(stmt_names)).all()}

    text = f"{t(lang, 'history_title')}\n\n"
    buttons = []
    
    if not txs:
        text += t(lang, "history_empty")
    else:
        for tx in txs:
            # Determine icon and type name
            icon = "❓"
            type_name = tx.type
            if tx.type == "buy":
                icon = "💰"
                type_name = t(lang, "tx_buy")
            elif tx.type == "sell":
                icon = "📈"
                type_name = t(lang, "tx_sell")
            elif tx.type == "auction":
                icon = "🔨"
                type_name = t(lang, "tx_auction")
            elif tx.type == "trade":
                icon = "🤝"
                type_name = t(lang, "tx_trade")
            elif tx.type == "fee":
                icon = "🏛️"
                type_name = t(lang, "tx_fee")
            
            # Context (From/To)
            arrow = "➡️" if tx.from_player == player.telegram_id else "⬅️"
            other_id = tx.to_player if tx.from_player == player.telegram_id else tx.from_player
            
            date_str = tx.created_at.strftime("%d/%m %H:%M")
            
            # Button text
            other_name = escape_markdown(dao_map.get(other_id) or (str(other_id)[:6] + "..."))
            btn_text = f"{icon} {type_name} {arrow} {other_name} | {date_str}"
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"mkt_tx_view_{tx.id}")])

    # Smart Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(t(lang, "btn_prev"), callback_data=f"mkt_history_{page-1}"))
    
    # Check if there is a next page
    next_txs = await get_player_transactions(session, player.telegram_id, 1, offset + limit)
    if next_txs:
        nav.append(InlineKeyboardButton(t(lang, "btn_next"), callback_data=f"mkt_history_{page+1}"))
    
    if nav:
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="trd_help")])
    
    kb = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def view_tx_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    tx_id = safe_parse_callback_uuid(query.data, "mkt_tx_view_")
    if tx_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = player.language or "en"

        try:
            stmt = select(Transaction).where(Transaction.id == tx_id)
            tx = (await session.execute(stmt)).scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching transaction in tx_detail_callback: {e}")
            await safe_answer(query, t(lang, "ans_detalhes_não_disponíveis_bd"), show_alert=True)
            return
        
        if not tx:
            await safe_answer(query, t(lang, "ans_transação_não_encontrada"), show_alert=True)
            return

        summary = ""
        if tx.type == "trade" and tx.details:
            i_offer = tx.details.get("initiator_offer", {})
            t_offer = tx.details.get("target_offer", {})
            
            is_init = player.telegram_id == tx.from_player
            my_offer = i_offer if is_init else t_offer
            their_offer = t_offer if is_init else i_offer
            
            summary += t(lang, "tx_sent")
            s = my_offer.get("stones", 0)
            if s > 0: summary += f"  💰 {format_currency(s)} Stones\n"
            for it in my_offer.get("items", []):
                summary += f"  📦 {it['name']} (x{it['qty']})\n"
            
            summary += t(lang, "tx_received")
            s = their_offer.get("stones", 0)
            if s > 0: summary += f"  💰 {format_currency(s)} Stones\n"
            for it in their_offer.get("items", []):
                summary += f"  📦 {it['name']} (x{it['qty']})\n"
        else:
            # Generic Buy/Sell summary
            if tx.item_type:
                name = await _get_item_name(session, tx.item_type, tx.item_id, lang)
                summary = t(lang, "tx_item_summary", name=name, qty=tx.quantity)
            
            if tx.price > 0:
                is_out = tx.from_player == player.telegram_id
                prefix = t(lang, "tx_spent_prefix") if is_out else t(lang, "tx_received_prefix")
                summary += f"{prefix}: {format_currency(tx.price)} Stones"

        if not summary: summary = t(lang, "tx_no_details")
        
        await safe_answer(query, summary, show_alert=True)
