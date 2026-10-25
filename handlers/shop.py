from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, PreCheckoutQueryHandler, MessageHandler, filters

from database.db import get_session_factory
from database.models import Player
from core.monetization import (
    get_player_vip_level,
    get_vip_perks,
    VIP_TIERS_EUR,
    get_active_battle_pass,
    claim_daily_bp_jade,
    claim_battle_pass_tier,
)
from core.i18n import t

from core.utils import _ensure_player, safe_handler, rate_limit, safe_answer, add_item_to_inventory, resolve_chat_player_id

# Jade packages: callback_key -> {jade, bonus, stars}
JADE_PACKAGES = {
    "pack_1": {"jade": 60,  "bonus": 6,   "stars": 50},
    "pack_2": {"jade": 300, "bonus": 30,  "stars": 250},
    "pack_3": {"jade": 980, "bonus": 110, "stars": 800},
}

@safe_handler
@rate_limit(1)
async def cmd_loja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        vip_lvl = await get_player_vip_level(session, player.telegram_id)
        
        text = t(lang, "shop_main_title", jade=player.spirit_jade, vip=vip_lvl)

        keyboard = [
            [
                InlineKeyboardButton(t(lang, "btn_shop_jade"), callback_data="shop_jade"),
                InlineKeyboardButton(t(lang, "btn_shop_vip"), callback_data="shop_vip")
            ],
            [
                InlineKeyboardButton(t(lang, "btn_shop_pass"), callback_data="shop_pass"),
                InlineKeyboardButton(t(lang, "btn_shop_gacha"), callback_data="shop_gacha")
            ],
            [
                InlineKeyboardButton(t(lang, "shop_btn_root_reroll"), callback_data="shop_vip_root")
            ],
            [
                InlineKeyboardButton(t(lang, "shop_btn_convenience"), callback_data="shop_convenience")
            ],
            [
                InlineKeyboardButton(t(lang, "shop_btn_monthly_card"), callback_data="shop_monthly"),
                InlineKeyboardButton(t(lang, "shop_btn_fragments"), callback_data="shop_fragments")
            ],
            [
                InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_status")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_shop_routes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    data = query.data

    if data == "shop_jade":
        await _show_jade_shop(update, context)
    elif data == "shop_vip":
        await _show_vip_info(update, context)
    elif data == "shop_pass":
        await _show_battle_pass(update, context)
    elif data == "shop_convenience":
        await _show_convenience_shop(update, context)
    elif data.startswith("shop_conv_"):
        category = data.replace("shop_conv_", "")
        await _show_convenience_category(update, context, category)
    elif data.startswith("bp_missions_"):
        try:
            page = int(data.split("_")[-1])
        except (ValueError, IndexError):
            page = 0
        await _show_bp_missions(update, context, page)
    elif data.startswith("bp_claim_miss_"):
        try:
            mission_id = int(data.split("_")[-1])
        except (ValueError, IndexError):
            await safe_answer(query, "Invalid mission.", show_alert=True)
            return
        await _handle_bp_mission_claim(update, context, mission_id)
    elif data == "shop_gacha":
        from handlers.gacha import return_gacha_menu
        await return_gacha_menu(update, context)
    elif data.startswith("buy_jade_"):
        # Launch Telegram Stars Invoice
        pack_key = data.replace("buy_jade_", "")
        pack = JADE_PACKAGES.get(pack_key)
        if not pack:
            await safe_answer(query, "Invalid package.", show_alert=True)
            return
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player: return
            lang = player.language or "en"
            
            jade_amount = pack["jade"]
            bonus = pack["bonus"]
            total_jade = jade_amount + bonus
            stars_cost = pack["stars"]
            payload = f"jade_{total_jade}_{player.telegram_id}"
            prices = [LabeledPrice(t(lang, "shop_jade_pack_label", jade=total_jade), stars_cost)]

            # provider_token is empty for Telegram Stars
            await context.bot.send_invoice(
                chat_id=update.effective_chat.id,
                title=t(lang, "shop_jade_invoice_title"),
                description=t(lang, "shop_jade_invoice_desc", jade=total_jade, stars=stars_cost),
                payload=payload,
                provider_token="",
                currency="XTR",
                prices=prices
            )
    elif data == "shop_vip_root":
        await _show_root_reroll(update, context)
    elif data == "buy_vip_root_confirm":
        await _handle_root_reroll_buy(update, context, protected=False)
    elif data == "buy_vip_root_protect":
        await _handle_root_reroll_buy(update, context, protected=True)
    elif data.startswith("buy_item_"):
        await _handle_convenience_buy(update, context, data)
    elif data == "shop_monthly":
        await _show_monthly_cards(update, context)
    elif data.startswith("buy_monthly_"):
        card_type = data.replace("buy_monthly_", "")
        await _handle_monthly_card_buy(update, context, card_type)
    elif data == "claim_monthly":
        await _handle_monthly_card_claim(update, context)
    elif data.startswith("vip_ms_claim_"):
        try:
            threshold = int(data.replace("vip_ms_claim_", ""))
        except (ValueError, IndexError):
            await safe_answer(query, "Invalid milestone.", show_alert=True)
            return
        await _handle_vip_milestone_claim(update, context, threshold)
    elif data == "shop_fragments":
        await _show_fragment_exchange(update, context)
    elif data.startswith("frag_exchange_"):
        await _handle_fragment_exchange(update, context, data)
    elif data == "buy_bp_premium":
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player: return
            lang = player.language or "en"
            
            stars_cost = 250
            payload = f"bp_premium_{player.telegram_id}"
            prices = [LabeledPrice("Celestial Pass", stars_cost)]

            await context.bot.send_invoice(
                chat_id=update.effective_chat.id,
                title="Celestial Pass",
                description=t(lang, "shop_bp_stars_invoice_desc"),
                payload=payload,
                provider_token="",
                currency="XTR",
                prices=prices
            )

    elif data.startswith("bp_tier_"):
        try:
            tier_num = int(data.split("_")[-1])
        except (ValueError, IndexError):
            await safe_answer(query, "Invalid tier.", show_alert=True)
            return
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player: return
            lang = player.language or "en"
            res = await claim_battle_pass_tier(session, player.telegram_id, tier_num, lang=lang)
            await session.commit()
            if res["success"]:
                rewards_text = "\n".join(res["granted"])
                await safe_answer(query, t(lang, "shop_bp_tier_claimed", tier=tier_num), show_alert=True)
                await _show_battle_pass(update, context)
            else:
                error_msgs = {
                    "no_active_pass": t(lang, "shop_bp_err_no_pass"),
                    "tier_not_reached": t(lang, "shop_bp_err_not_reached"),
                    "already_claimed": t(lang, "shop_bp_err_already"),
                }
                await safe_answer(query, error_msgs.get(res['error'], res['error']), show_alert=True)

    elif data == "shop_main":
        # Simulate /loja call
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player: return
            lang = player.language or "en"
            vip_lvl = await get_player_vip_level(session, player.telegram_id)
            
            text = t(lang, "shop_main_title", jade=player.spirit_jade, vip=vip_lvl)

            keyboard = [
                [
                    InlineKeyboardButton(t(lang, "btn_shop_jade"), callback_data="shop_jade"),
                    InlineKeyboardButton(t(lang, "btn_shop_vip"), callback_data="shop_vip")
                ],
                [
                    InlineKeyboardButton(t(lang, "btn_shop_pass"), callback_data="shop_pass"),
                    InlineKeyboardButton(t(lang, "btn_shop_gacha"), callback_data="shop_gacha")
                ],
                [
                    InlineKeyboardButton(t(lang, "shop_btn_root_reroll"), callback_data="shop_vip_root")
                ],
                [
                    InlineKeyboardButton(t(lang, "shop_btn_convenience"), callback_data="shop_convenience")
                ],
                [
                    InlineKeyboardButton(t(lang, "shop_btn_monthly_card"), callback_data="shop_monthly"),
                    InlineKeyboardButton(t(lang, "shop_btn_fragments"), callback_data="shop_fragments")
                ],
                [
                    InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_status")
                ]
            ]
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "claim_bp_jade":
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player: return
            lang = player.language or "en"
            res = await claim_daily_bp_jade(session, player.telegram_id)
            await session.commit()
            
            if res["success"]:
                await safe_answer(query, t(lang, "shop_claim_jade_success", granted=res['granted']), show_alert=True)
                await _show_battle_pass(update, context)
            else:
                error_msg = t(lang, res.get("error_key", "err_player_not_found"), **res.get("error_params", {}))
                await safe_answer(query, error_msg, show_alert=True)

async def _show_jade_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        # Check if player has ever bought jade (for First Top-Up banner)
        from database.models import Purchase
        from sqlalchemy import select as sa_select, func as sa_func
        jade_purchases = (await session.execute(
            sa_select(sa_func.count()).select_from(Purchase).where(
                Purchase.player_id == player.telegram_id,
                Purchase.product_id.like("jade_%"),
                Purchase.payment_method == "telegram_stars",
                Purchase.status == "completed"
            )
        )).scalar() or 0

    text = t(lang, "shop_jade_title")
    if jade_purchases == 0:
        text += "\n" + t(lang, "shop_first_topup_banner")

    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_shop_jade_60"), callback_data="buy_jade_pack_1")],
        [InlineKeyboardButton(t(lang, "btn_shop_jade_300"), callback_data="buy_jade_pack_2")],
        [InlineKeyboardButton(t(lang, "btn_shop_jade_980"), callback_data="buy_jade_pack_3")],
        [InlineKeyboardButton(t(lang, "btn_market_back"), callback_data="shop_main")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def _show_vip_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        vip_lvl = await get_player_vip_level(session, player.telegram_id)
        from database.models import PlayerVIP
        from sqlalchemy import select
        stmt = select(PlayerVIP).where(PlayerVIP.player_id == player.telegram_id)
        vip_record = (await session.execute(stmt)).scalar_one_or_none()
        total_spent = vip_record.total_spent_eur if vip_record else 0.0

        perks = get_vip_perks(vip_lvl)
        
        next_lvl = vip_lvl + 1
        next_req = VIP_TIERS_EUR.get(next_lvl)
        if next_req:
            progress_text = t(lang, "shop_vip_progress", next_lvl=next_lvl, total_spent=total_spent, next_req=next_req)
        else:
            progress_text = t(lang, "shop_vip_maxed")

        from config import ALCHEMY_ENERGY_BASE
        alch_energy_max = ALCHEMY_ENERGY_BASE + perks['alchemy_energy_max_bonus']
        alch_regen = perks['alchemy_energy_regen_minutes']

        text = t(lang, "shop_vip_title", vip_lvl=vip_lvl, total_spent=total_spent, progress=progress_text,
                 exp_slots=perks['expedition_slots'], alch_energy_max=alch_energy_max, alch_regen=alch_regen,
                 tax_discount=int(perks['auction_tax_discount']*100), offline_cap=perks['offline_cap_hours'])

        if perks['priority_world_boss']:
            text += t(lang, "shop_vip_perk_wb")
        if perks['custom_announce']:
            text += t(lang, "shop_vip_perk_announce")
        if perks['exclusive_title']:
            text += t(lang, "shop_vip_perk_title")
            
        text += t(lang, "shop_vip_footer")

        # VIP Milestone progress
        from core.monetization import VIP_MILESTONES
        claimed_ms = list(vip_record.vip_milestones_claimed or []) if vip_record else []
        text += "\n" + t(lang, "shop_vip_milestones_title") + "\n"
        for threshold_eur, rewards in sorted(VIP_MILESTONES.items()):
            if threshold_eur in claimed_ms:
                text += f"  ✅ €{threshold_eur} — *{rewards['label']}* (claimed)\n"
            elif total_spent >= threshold_eur:
                text += f"  🎁 €{threshold_eur} — *{rewards['label']}* (claimable!)\n"
            else:
                remaining = threshold_eur - total_spent
                text += f"  ⏳ €{threshold_eur} — *{rewards['label']}* (€{remaining:.1f} to go)\n"

        keyboard = []
        for threshold_eur, rewards in sorted(VIP_MILESTONES.items()):
            if threshold_eur not in claimed_ms and total_spent >= threshold_eur:
                keyboard.append([InlineKeyboardButton(
                    f"🎁 Claim: {rewards['label']}", callback_data=f"vip_ms_claim_{threshold_eur}"
                )])
        keyboard.append([InlineKeyboardButton(t(lang, "btn_market_back"), callback_data="shop_main")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def _handle_vip_milestone_claim(update: Update, context: ContextTypes.DEFAULT_TYPE, threshold: int):
    query = update.callback_query

    from core.monetization import VIP_MILESTONES
    rewards = VIP_MILESTONES.get(threshold)
    if not rewards:
        await safe_answer(query, "Invalid milestone.", show_alert=True)
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"

        from database.models import PlayerVIP
        from sqlalchemy import select
        stmt = select(PlayerVIP).where(PlayerVIP.player_id == player.telegram_id)
        vip_record = (await session.execute(stmt)).scalar_one_or_none()

        if not vip_record or vip_record.total_spent_eur < threshold:
            await safe_answer(query, t(lang, "shop_vip_ms_not_eligible"), show_alert=True)
            return

        claimed_ms = list(vip_record.vip_milestones_claimed or [])
        if threshold in claimed_ms:
            await safe_answer(query, t(lang, "shop_vip_ms_already_claimed"), show_alert=True)
            return

        # Grant rewards
        if rewards.get("jade"):
            from core.monetization import grant_jade
            await grant_jade(session, player, rewards["jade"])
        if rewards.get("stones"):
            player.spirit_stones += rewards["stones"]
        if rewards.get("fragments"):
            player.celestial_fragments = (player.celestial_fragments or 0) + rewards["fragments"]
        if rewards.get("title"):
            # Add to persistent unlocked_titles list
            titles = list(player.unlocked_titles or [])
            if rewards["title"] not in titles:
                titles.append(rewards["title"])
                player.unlocked_titles = titles
                from sqlalchemy.orm.attributes import flag_modified as fm2
                fm2(player, "unlocked_titles")
            player.active_title = rewards["title"]

        claimed_ms.append(threshold)
        vip_record.vip_milestones_claimed = claimed_ms
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(vip_record, "vip_milestones_claimed")
        await session.commit()

        jade = rewards.get("jade", 0)
        stones = rewards.get("stones", 0)
        frags = rewards.get("fragments", 0)
        title = rewards.get("title")
        msg = t(lang, "shop_vip_ms_claimed", label=rewards["label"], jade=jade, stones=stones)
        if frags:
            msg += f"\n✨ +{frags} Celestial Fragments"
        if title:
            msg += f"\n🎖️ Title: *{title}*"
        await safe_answer(query, msg, show_alert=True)

    # Refresh VIP info
    await _show_vip_info(update, context)


# Root Reroll Pity milestones: {total_rerolls_needed: guaranteed_max_root_index}
# 0=Heavenly, 1=Superior, 2=High, 3=Mid
REROLL_PITY_MILESTONES = [
    (10, 2, "High"),       # 10 rerolls → guaranteed High or better
    (25, 1, "Superior"),   # 25 rerolls → guaranteed Superior or better
    (50, 0, "Heavenly"),   # 50 rerolls → guaranteed Heavenly
]


def _get_next_pity_milestone(total_rerolls: int) -> tuple | None:
    """Returns (threshold, max_root_index, root_name) for next unclaimed milestone, or None."""
    for threshold, max_idx, name in REROLL_PITY_MILESTONES:
        if total_rerolls < threshold:
            return threshold, max_idx, name
    return None  # Already past all milestones


def _build_pity_progress_bar(total_rerolls: int) -> str:
    """Build a visual progress bar showing reroll milestones."""
    lines = []
    for threshold, _idx, name in REROLL_PITY_MILESTONES:
        if total_rerolls >= threshold:
            lines.append(f"  ✅ {threshold} — *{name}+* guaranteed (reached!)")
        else:
            remaining = threshold - total_rerolls
            filled = min(10, int((total_rerolls / threshold) * 10))
            bar = "█" * filled + "░" * (10 - filled)
            lines.append(f"  ⏳ {threshold} — *{name}+* [{bar}] ({remaining} left)")
    return "\n".join(lines)


def _check_pity_guarantee(total_rerolls: int) -> int | None:
    """If the player has EXACTLY hit a milestone, return the max root index for guaranteed roll.
    Returns None if no milestone is active for this exact count."""
    for threshold, max_idx, _name in REROLL_PITY_MILESTONES:
        if total_rerolls == threshold:
            return max_idx
    return None


async def _show_root_reroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return

        from datetime import datetime, timezone
        from database.models import PlayerVIP
        from sqlalchemy import select, func

        # Get total rerolls from VIP record (with retroactive count fallback)
        vip_rec = (await session.execute(
            select(PlayerVIP).where(PlayerVIP.player_id == player.telegram_id)
        )).scalar_one_or_none()
        total_rerolls = vip_rec.total_rerolls if vip_rec and vip_rec.total_rerolls else 0

        # Retroactive: if total_rerolls is 0 but player has historical purchases, backfill
        if total_rerolls == 0:
            from database.models import Purchase
            historical = (await session.execute(
                select(func.count()).select_from(Purchase).where(
                    Purchase.player_id == player.telegram_id,
                    Purchase.product_id.in_(["vip_root_reroll", "vip_root_protect"]),
                    Purchase.status == "completed"
                )
            )).scalar() or 0
            if historical > 0:
                total_rerolls = historical
                if vip_rec:
                    vip_rec.total_rerolls = historical
                    await session.commit()

        from config import SPIRIT_ROOT_NAMES, SPIRIT_ROOTS
        root_name = SPIRIT_ROOT_NAMES[player.spirit_root] if player.spirit_root < len(SPIRIT_ROOT_NAMES) else f"Unknown ({player.spirit_root})"
        root_data = list(SPIRIT_ROOTS.values())[player.spirit_root] if player.spirit_root < len(SPIRIT_ROOTS) else {}
        root_emoji = root_data.get("emoji", "")

        lang = player.language or "en"
        text = t(lang, "shop_root_title")
        text += t(lang, "shop_root_current", root=f"{root_emoji} {root_name}")
        text += t(lang, "shop_root_warning")
        text += t(lang, "shop_root_protected")
        text += t(lang, "shop_root_probabilities")

        # Pity progress display
        text += "\n" + t(lang, "shop_root_pity_title", total=total_rerolls) + "\n"
        text += _build_pity_progress_bar(total_rerolls) + "\n\n"

        next_ms = _get_next_pity_milestone(total_rerolls)
        if next_ms:
            threshold, _idx, ms_name = next_ms
            remaining = threshold - total_rerolls
            text += t(lang, "shop_root_pity_next", remaining=remaining, root=ms_name) + "\n\n"
        else:
            text += t(lang, "shop_root_pity_all_done") + "\n\n"

        text += t(lang, "shop_root_balance", jade=player.spirit_jade)

        keyboard = []
        if player.spirit_jade >= 500:
            keyboard.append([InlineKeyboardButton(t(lang, "shop_root_btn_normal", cost=500), callback_data="buy_vip_root_confirm")])
        else:
            keyboard.append([InlineKeyboardButton(t(lang, "shop_root_btn_not_enough", cost=500), callback_data="none")])

        if player.spirit_jade >= 800:
            keyboard.append([InlineKeyboardButton(t(lang, "shop_root_btn_protected", cost=800), callback_data="buy_vip_root_protect")])
        else:
            keyboard.append([InlineKeyboardButton(t(lang, "shop_root_btn_not_enough", cost=800), callback_data="none")])

        keyboard.append([InlineKeyboardButton(t(lang, "shop_root_btn_back"), callback_data="shop_main")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def _handle_root_reroll_buy(update: Update, context: ContextTypes.DEFAULT_TYPE, protected=False):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return

        from datetime import datetime, timezone
        from database.models import Purchase, PlayerVIP
        from sqlalchemy import select, func

        cost = 800 if protected else 500

        if player.spirit_jade < cost:
            await safe_answer(query, t(player.language or "en", "shop_root_not_enough_jade"), show_alert=True)
            return

        old_root = player.spirit_root

        # Guard: player already has Heavenly root (index 0), protected reroll would loop forever
        if protected and old_root == 0:
            await safe_answer(query, t(player.language or "en", "shop_root_already_best"), show_alert=True)
            return

        player.spirit_jade -= cost

        # ── Increment total rerolls counter ──
        vip_rec = (await session.execute(
            select(PlayerVIP).where(PlayerVIP.player_id == player.telegram_id)
        )).scalar_one_or_none()
        if not vip_rec:
            vip_rec = PlayerVIP(player_id=player.telegram_id, total_rerolls=0)
            session.add(vip_rec)
            await session.flush()
        vip_rec.total_rerolls = (vip_rec.total_rerolls or 0) + 1
        new_total = vip_rec.total_rerolls

        # Roll according to db weights but exclude 'Low' (index 4)
        from config import SPIRIT_ROOT_NAMES, SPIRIT_ROOT_WEIGHTS
        import random
        indices = list(range(len(SPIRIT_ROOT_WEIGHTS)))

        # Custom weights for reroll: 0 for Low (last element)
        reroll_weights = [0.01, 1.0, 19.0, 80.0, 0.0]

        # ── Check pity milestone guarantee ──
        pity_guarantee = _check_pity_guarantee(new_total)
        pity_triggered = False

        if pity_guarantee is not None:
            # Guaranteed roll: only allow roots with index <= pity_guarantee
            pity_weights = [reroll_weights[i] if i <= pity_guarantee else 0.0 for i in indices]
            new_root = random.choices(indices, weights=pity_weights, k=1)[0]
            pity_triggered = True
        elif protected:
            # Keep rolling until we get a root <= current root (lower index = better)
            for _attempt in range(500):
                new_root = random.choices(indices, weights=reroll_weights, k=1)[0]
                if new_root <= old_root:
                    break
            else:
                new_root = old_root
        else:
            new_root = random.choices(indices, weights=reroll_weights, k=1)[0]

        player.spirit_root = new_root

        session.add(Purchase(
            player_id=player.telegram_id,
            product_id="vip_root_protect" if protected else "vip_root_reroll",
            amount_eur=0.0,
            spirit_jade_granted=0,
            payment_method="jade",
            status="completed"
        ))

        await session.commit()

        from config import SPIRIT_ROOTS
        old_root_name = SPIRIT_ROOT_NAMES[old_root] if old_root < len(SPIRIT_ROOT_NAMES) else f"Unknown ({old_root})"
        new_root_name = SPIRIT_ROOT_NAMES[new_root] if new_root < len(SPIRIT_ROOT_NAMES) else f"Unknown ({new_root})"
        old_emoji = list(SPIRIT_ROOTS.values())[old_root].get("emoji", "") if old_root < len(SPIRIT_ROOTS) else ""
        new_emoji = list(SPIRIT_ROOTS.values())[new_root].get("emoji", "") if new_root < len(SPIRIT_ROOTS) else ""

        # M-6: build an explicit, persistent result message — alert popups can be
        # missed (player feedback "deducted jade, but I didn't get any results").
        protection_text = " (Protected)" if protected else ""
        lang = player.language or "en"
        old_label = f"{old_emoji} {old_root_name}"
        new_label = f"{new_emoji} {new_root_name}"

        if pity_triggered:
            alert_msg = t(lang, "shop_root_pity_triggered", old=old_label, new=new_label, milestone=new_total)
            chat_msg = alert_msg
        elif protected:
            if new_root < old_root:
                outcome = t(lang, "shop_root_outcome_upgrade")
            elif new_root == old_root:
                outcome = t(lang, "shop_root_outcome_protected_kept")
            else:
                outcome = t(lang, "shop_root_outcome_unchanged")
            chat_msg = t(
                lang,
                "shop_root_result_full",
                old=old_label,
                new=new_label,
                protection=t(lang, "shop_root_protection_on"),
                outcome=outcome,
                jade=player.spirit_jade,
                total=new_total,
            )
            alert_msg = t(lang, "shop_root_result", protection=protection_text, old=old_label, new=new_label)
        else:
            if new_root < old_root:
                outcome = t(lang, "shop_root_outcome_upgrade")
            elif new_root == old_root:
                outcome = t(lang, "shop_root_outcome_unchanged")
            else:
                outcome = t(lang, "shop_root_outcome_downgrade")
            chat_msg = t(
                lang,
                "shop_root_result_full",
                old=old_label,
                new=new_label,
                protection=t(lang, "shop_root_protection_off"),
                outcome=outcome,
                jade=player.spirit_jade,
                total=new_total,
            )
            alert_msg = t(lang, "shop_root_result", protection=protection_text, old=old_label, new=new_label)

        await safe_answer(query, alert_msg, show_alert=True)

        # Persistent chat message so the player has a record even after the popup closes.
        try:
            await context.bot.send_message(
                chat_id=player.telegram_id,
                text=chat_msg,
                parse_mode="Markdown",
            )
        except Exception:
            pass

        # Re-render the same page with updated balance and limits
        await _show_root_reroll(update, context)

async def _show_battle_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        
        bp = await get_active_battle_pass(session, player.telegram_id)
        is_premium = bp.is_premium if bp else False
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        can_claim = False
        if is_premium:
            if not bp.daily_jade_claimed_at or bp.daily_jade_claimed_at.date() < now.date():
                can_claim = True

        status_str = t(lang, "shop_bp_status_active") if is_premium else t(lang, "shop_bp_status_inactive")
        
        text = t(lang, "shop_bp_title", status=status_str)
        
        if is_premium:
            current_tier = bp.tier if bp else 1
            claimed = bp.claimed_tiers or [] if bp else []

            # Show tier progress
            text += t(lang, "shop_bp_tier_progress", tier=current_tier)
            text += "\u2500" * 24 + "\n"

            # Show next 5 claimable tiers (including overflow beyond 30)
            from core.monetization import get_bp_rewards_for_tier
            shown = 0
            for tier_num in range(1, current_tier + 1):
                if tier_num in claimed:
                    continue
                rewards = get_bp_rewards_for_tier(tier_num)
                reward_text = ", ".join(
                    r.get("name", r.get("value", r["type"]).replace("_", " ").title()) if "name" in r or "value" in r
                    else f"{r['type'].replace('_', ' ').title()} x{r.get('amount', r.get('qty', 1))}"
                    for r in rewards
                )
                tier_label = f"Tier {tier_num}" if tier_num <= 30 else f"Tier {tier_num} ♾️"
                text += f"🎁 {tier_label}: {reward_text}\n"
                shown += 1
                if shown >= 5:
                    remaining = sum(1 for t_n in range(tier_num+1, current_tier+1) if t_n not in claimed)
                    if remaining > 0:
                        text += t(lang, "shop_bp_more_claimable", count=remaining)
                    break

            if not shown:
                text += t(lang, "shop_bp_all_claimed")

            if can_claim:
                text += "\n" + t(lang, "shop_bp_claim_available")
                btn_claim = InlineKeyboardButton(t(lang, "btn_shop_claim_bp"), callback_data="claim_bp_jade")
            else:
                text += "\n" + t(lang, "shop_bp_claim_done")
                btn_claim = InlineKeyboardButton(t(lang, "btn_shop_claimed_bp"), callback_data="none")

            # Add claim tier buttons for unclaimed tiers (including overflow)
            keyboard = [[btn_claim]]
            for tier_num in range(1, current_tier + 1):
                if tier_num not in claimed:
                    keyboard.append([InlineKeyboardButton(t(lang, "shop_bp_claim_tier", tier=tier_num), callback_data=f"bp_tier_{tier_num}")])
                    if len(keyboard) >= 6:  # max 5 tier buttons + jade claim
                        break
            keyboard.append([InlineKeyboardButton(t(lang, "btn_bp_missions"), callback_data="bp_missions_0")])
            keyboard.append([InlineKeyboardButton(t(lang, "btn_market_back"), callback_data="shop_main")])
        else:
            text += t(lang, "shop_bp_inactive_footer")
            keyboard = [
                [InlineKeyboardButton(t(lang, "btn_bp_missions"), callback_data="bp_missions_0")],
                [InlineKeyboardButton(t(lang, "shop_bp_btn_purchase"), callback_data="buy_bp_premium")],
                [InlineKeyboardButton(t(lang, "btn_market_back"), callback_data="shop_main")]
            ]

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


# ─── Convenience Shop ────────────────────────────────────────────────────────

CONVENIENCE_ITEMS = {
    "offline_exp":   {"name_key": "shop_conv_offline",      "jade": 200, "desc_key": "shop_conv_offline_desc", "category": "utility"},
    "name_change":   {"name_key": "shop_conv_name_change",   "jade": 300, "desc_key": "shop_conv_name_change_desc", "category": "utility"},
    "trap_pack":     {"name_key": "shop_conv_trap_pack",     "jade": 150, "desc_key": "shop_conv_trap_pack_desc", "category": "utility"},
    "trib_insurance": {"name_key": "shop_conv_trib_insurance", "jade": 150, "desc_key": "shop_conv_trib_insurance_desc", "daily": 1, "category": "combat"},
    "alchemy_recharge": {"name_key": "shop_conv_alchemy_recharge", "jade": 30, "desc_key": "shop_conv_alchemy_recharge_desc", "daily": 3, "category": "crafting"},
    "cultivation_pill": {"name_key": "shop_conv_cultivation_pill", "jade": 60, "desc_key": "shop_conv_cultivation_pill_desc", "daily": 2, "category": "combat"},
    "forge_charm": {"name_key": "shop_conv_forge_charm", "jade": 25, "desc_key": "shop_conv_forge_charm_desc", "daily": 3, "category": "crafting"},
    "beast_food": {"name_key": "shop_conv_beast_food", "jade": 40, "desc_key": "shop_conv_beast_food_desc", "daily": 1, "category": "crafting"},
    "pill_charm": {"name_key": "shop_conv_pill_charm", "jade": 30, "desc_key": "shop_conv_pill_charm_desc", "daily": 3, "category": "crafting"},
    "trib_blessing": {"name_key": "shop_conv_trib_blessing", "jade": 50, "desc_key": "shop_conv_trib_blessing_desc", "daily": 1, "category": "combat"},
    "beast_lure": {"name_key": "shop_conv_beast_lure", "jade": 20, "desc_key": "shop_conv_beast_lure_desc", "daily": 2, "category": "crafting"},
    "fortune_incense": {"name_key": "shop_conv_fortune_incense", "jade": 15, "desc_key": "shop_conv_fortune_incense_desc", "daily": 2, "category": "combat"},
    # F-11.5 (2026-05-23 universal extension owner [jogador] report): now clears
    # BOTH the 6h Celestial Trial CD (Mahayana) AND the 6h Heavenly Tribulation
    # failure CD. Player kept buying it expecting trib CD relief.
    # 80 jade (~€0.60 retail), daily limit 1 so it cannot become an infinite retry token.
    "trial_cd_break": {"name_key": "shop_conv_trial_cd_break", "jade": 80, "desc_key": "shop_conv_trial_cd_break_desc", "daily": 1, "category": "combat"},
    # C-5 — Celestial Essence Pellet. +100 essence per use, 3×/day, Mahayana
    # only. Closes the body tempering math gap and gives a paid alternative.
    "celestial_essence": {"name_key": "shop_conv_celestial_essence", "jade": 120, "desc_key": "shop_conv_celestial_essence_desc", "daily": 3, "category": "crafting"},
}

CONVENIENCE_CATEGORIES = {
    "combat":   {"emoji": "⚔️", "name_key": "shop_conv_cat_combat"},
    "crafting":  {"emoji": "🔧", "name_key": "shop_conv_cat_crafting"},
    "utility":  {"emoji": "🛠️", "name_key": "shop_conv_cat_utility"},
}

async def _show_convenience_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show convenience shop category selector."""
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        text = t(lang, "shop_convenience_title")
        text += t(lang, "shop_convenience_jade", jade=player.spirit_jade)
        text += "\n" + t(lang, "shop_conv_choose_category")

        keyboard = []
        for cat_key, cat in CONVENIENCE_CATEGORIES.items():
            count = sum(1 for v in CONVENIENCE_ITEMS.values() if v.get("category") == cat_key)
            label = f"{cat['emoji']} {t(lang, cat['name_key'])} ({count})"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"shop_conv_{cat_key}")])
        keyboard.append([InlineKeyboardButton(t(lang, "shop_convenience_btn_back"), callback_data="shop_main")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_convenience_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    """Show items in a specific convenience category."""
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        cat = CONVENIENCE_CATEGORIES.get(category)
        if not cat:
            await safe_answer(query, "Invalid category.", show_alert=True)
            return

        text = f"{cat['emoji']} *{t(lang, cat['name_key'])}*\n"
        text += t(lang, "shop_convenience_jade", jade=player.spirit_jade) + "\n"

        keyboard = []
        for key, item in CONVENIENCE_ITEMS.items():
            if item.get("category") != category:
                continue
            # Hide endgame-only items from players who can never use them.
            # `celestial_essence` stays Mahayana-only (R8+).
            # `trial_cd_break` is now universal (Trib + Celestial CD) — visible from
            # TRIBULATION_START_REALM (R4) when trib failures first become possible.
            if key == "celestial_essence" and player.realm < 8:
                continue
            if key == "trial_cd_break":
                from config import TRIBULATION_START_REALM
                if (player.realm or 0) < TRIBULATION_START_REALM:
                    continue
            name = t(lang, item['name_key'])
            desc = t(lang, item['desc_key'])
            text += f"\n{name}\n  💎 {item['jade']} jade — _{desc}_\n"
            keyboard.append([InlineKeyboardButton(f"{name} — 💎{item['jade']}", callback_data=f"buy_item_{key}")])

        keyboard.append([InlineKeyboardButton(t(lang, "shop_convenience_btn_back"), callback_data="shop_convenience")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def _handle_convenience_buy(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    item_key = data.replace("buy_item_", "")
    item = CONVENIENCE_ITEMS.get(item_key)
    if not item:
        await safe_answer(query, "Unknown item.", show_alert=True)
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return

        # Check jade balance
        if player.spirit_jade < item["jade"]:
            await safe_answer(query, t(player.language or "en", "shop_not_enough_jade", need=item['jade'], have=player.spirit_jade), show_alert=True)
            return

        # Monthly limit check for root reroll
        if item.get("monthly"):
            from datetime import datetime, timezone
            from database.models import Purchase
            from sqlalchemy import select, func
            now = datetime.now(timezone.utc)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            recent = (await session.execute(
                select(func.count()).select_from(Purchase).where(
                    Purchase.player_id == player.telegram_id,
                    Purchase.product_id == f"convenience_{item_key}",
                    Purchase.created_at >= month_start
                )
            )).scalar() or 0
            if recent >= 1:
                await safe_answer(query, t(player.language or "en", "shop_monthly_limit"), show_alert=True)
                return

        # Daily limit check
        if item.get("daily"):
            from datetime import datetime, timezone, timedelta
            from database.models import Purchase
            from sqlalchemy import select, func
            now = datetime.now(timezone.utc)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            daily_count = (await session.execute(
                select(func.count()).select_from(Purchase).where(
                    Purchase.player_id == player.telegram_id,
                    Purchase.product_id == f"convenience_{item_key}",
                    Purchase.created_at >= day_start
                )
            )).scalar() or 0
            if daily_count >= item["daily"]:
                lang = player.language or "en"
                await safe_answer(query, t(lang, "shop_daily_limit", limit=item["daily"]), show_alert=True)
                return

        # Deduct jade
        player.spirit_jade -= item["jade"]

        # Apply effect
        result_msg = ""
        if item_key == "offline_exp":
            # Grant a 30-day buff that extends offline cap
            from database.models import PlayerBuff
            from datetime import datetime, timezone, timedelta
            from sqlalchemy import select
            
            now = datetime.now(timezone.utc)
            max_future_date = now + timedelta(days=90)

            # Fetch all in case there were duplicates from the old bug
            stmt = select(PlayerBuff).where(
                PlayerBuff.player_id == player.telegram_id,
                PlayerBuff.buff_type == "offline_expansion"
            )
            all_buffs = (await session.execute(stmt)).scalars().all()

            existing_buff = None
            if all_buffs:
                existing_buff = all_buffs[0]
                # Cleanup duplicates if they exist from before the old bug
                for dup in all_buffs[1:]:
                    session.delete(dup)

            if existing_buff and existing_buff.expires_at > now:
                # Cap new_expiry at 90 days from today instead of refusing the
                # purchase — players still get at least some extension.
                new_expiry = min(
                    existing_buff.expires_at + timedelta(days=30),
                    max_future_date,
                )
                if new_expiry <= existing_buff.expires_at:
                    # Already at the absolute cap — refund and inform.
                    player.spirit_jade += item["jade"]
                    await safe_answer(query, t(player.language or "en", "shop_offline_max"), show_alert=True)
                    return
                existing_buff.expires_at = new_expiry
                existing_buff.source = "offline_expansion"
                days_left = (existing_buff.expires_at - now).days
            else:
                if existing_buff:
                    session.delete(existing_buff)
                buff = PlayerBuff(
                    player_id=player.telegram_id,
                    buff_type="offline_expansion",
                    buff_value=24.0,  # 24 hours cap
                    source="offline_expansion",
                    expires_at=now + timedelta(days=30)
                )
                session.add(buff)
                days_left = 30
            result_msg = t(player.language or "en", "shop_offline_result", days=days_left)

        elif item_key == "name_change":
            # Consume jade directly and await for message input
            context.user_data["awaiting_daoname_change"] = True
            result_msg = t(player.language or "en", "shop_name_change_result")

        elif item_key == "trap_pack":
            added = await add_item_to_inventory(session, player.telegram_id, "beast_trap", 0, 5, "common")
            if not added:
                player.spirit_jade += item["jade"]  # refund
                from core.utils import _get_or_create_ring, _count_used_slots
                ring = await _get_or_create_ring(session, player.telegram_id)
                used = await _count_used_slots(session, player.telegram_id)
                await safe_answer(query, t(player.language or "en", "inv_full", used=used, max=ring.max_slots), show_alert=True)
                return
            result_msg = t(player.language or "en", "shop_trap_result")

        elif item_key == "trib_insurance":
            # Heavenly Shield Talisman — tribulation insurance buff
            from database.models import PlayerBuff
            from datetime import datetime, timezone, timedelta
            from sqlalchemy import select as sa_select

            now = datetime.now(timezone.utc)
            # Check if already has active insurance
            existing = (await session.execute(
                sa_select(PlayerBuff).where(
                    PlayerBuff.player_id == player.telegram_id,
                    PlayerBuff.buff_type == "trib_insurance",
                    PlayerBuff.expires_at > now
                )
            )).scalar_one_or_none()
            if existing:
                player.spirit_jade += item["jade"]  # refund
                lang = player.language or "en"
                await safe_answer(query, t(lang, "shop_trib_insurance_active"), show_alert=True)
                return

            buff = PlayerBuff(
                player_id=player.telegram_id,
                buff_type="trib_insurance",
                buff_value=1.0,
                source="convenience_shop",
                expires_at=now + timedelta(days=30)  # lasts until used or 30d
            )
            session.add(buff)
            result_msg = t(player.language or "en", "shop_trib_insurance_result")

        elif item_key == "alchemy_recharge":
            # Celestial Flame Essence — full alchemy energy recharge
            from core.alchemy_engine import get_alchemy_energy, get_alchemy_tier
            from core.monetization import get_player_vip_level
            from datetime import datetime, timezone

            vip_lvl = await get_player_vip_level(session, player.telegram_id)
            a_tier = await get_alchemy_tier(session, player.telegram_id)
            current, energy_max, _ = get_alchemy_energy(player, vip_lvl, a_tier)
            if current >= energy_max:
                player.spirit_jade += item["jade"]  # refund
                lang = player.language or "en"
                await safe_answer(query, t(lang, "shop_alchemy_already_full"), show_alert=True)
                return

            player.alchemy_energy = energy_max
            player.alchemy_energy_updated_at = datetime.now(timezone.utc)
            result_msg = t(player.language or "en", "shop_alchemy_recharge_result", energy=energy_max)

        elif item_key == "cultivation_pill":
            # Cultivation Pill — grants 12h worth of offline CB instantly
            try:
                from config import get_threshold, TICK_INTERVAL_SECONDS
                from core.game_logic import calculate_cb_per_tick

                threshold = get_threshold(player.realm, player.sub_layer)
                cb_per_tick = calculate_cb_per_tick(player, is_online=False)
                cb_per_sec = cb_per_tick / TICK_INTERVAL_SECONDS
                cb_gained = cb_per_sec * 12 * 3600  # 12 hours of offline cultivation
                player.cultivation_base = (player.cultivation_base or 0) + cb_gained
                # Cap to avoid accidentally overflowing past threshold too much
                cap = threshold * 1.5
                if player.cultivation_base > cap:
                    cb_gained -= (player.cultivation_base - cap)
                    player.cultivation_base = cap
                if cb_gained <= 0:
                    # Nothing meaningful to grant — refund instead of silently doing nothing
                    player.spirit_jade += item["jade"]
                    lang = player.language or "en"
                    await safe_answer(query, t(lang, "shop_cultivation_pill_full"), show_alert=True)
                    return
                result_msg = t(player.language or "en", "shop_cultivation_pill_result", cb=int(cb_gained))
            except Exception as e:
                # Refund on any unexpected error and tell the player
                player.spirit_jade += item["jade"]
                lang = player.language or "en"
                await safe_answer(query, t(lang, "shop_purchase_error"), show_alert=True)
                import logging as _shop_logging
                _shop_logging.getLogger("shop").exception(
                    "cultivation_pill purchase failed for %s: %s", player.telegram_id, e
                )
                return

        elif item_key == "forge_charm":
            # Forge Protection Charm — next refinement failure doesn't lose durability
            from database.models import PlayerBuff
            from datetime import datetime, timezone, timedelta
            from sqlalchemy import select as sa_select

            now = datetime.now(timezone.utc)
            existing = (await session.execute(
                sa_select(PlayerBuff).where(
                    PlayerBuff.player_id == player.telegram_id,
                    PlayerBuff.buff_type == "forge_protection",
                    PlayerBuff.expires_at > now
                )
            )).scalar_one_or_none()
            if existing:
                player.spirit_jade += item["jade"]
                lang = player.language or "en"
                await safe_answer(query, t(lang, "shop_forge_charm_active"), show_alert=True)
                return

            buff = PlayerBuff(
                player_id=player.telegram_id,
                buff_type="forge_protection",
                buff_value=1.0,
                source="convenience_shop",
                expires_at=now + timedelta(days=7)  # lasts until used or 7d
            )
            session.add(buff)
            result_msg = t(player.language or "en", "shop_forge_charm_result")

        elif item_key == "beast_food":
            # Beast Food Pack — 3× beast training XP buff for 24h
            from database.models import PlayerBuff
            from datetime import datetime, timezone, timedelta
            from sqlalchemy import select as sa_select

            now = datetime.now(timezone.utc)
            existing = (await session.execute(
                sa_select(PlayerBuff).where(
                    PlayerBuff.player_id == player.telegram_id,
                    PlayerBuff.buff_type == "beast_food",
                    PlayerBuff.expires_at > now
                )
            )).scalar_one_or_none()
            if existing:
                player.spirit_jade += item["jade"]
                lang = player.language or "en"
                await safe_answer(query, t(lang, "shop_beast_food_active"), show_alert=True)
                return

            buff = PlayerBuff(
                player_id=player.telegram_id,
                buff_type="beast_food",
                buff_value=3.0,  # 3× XP multiplier
                source="convenience_shop",
                expires_at=now + timedelta(hours=24)
            )
            session.add(buff)
            result_msg = t(player.language or "en", "shop_beast_food_result")

        elif item_key == "pill_charm":
            # Heavenly Pill Charm — +10% Heavenly pill chance for 3 crafts
            from database.models import PlayerBuff
            from datetime import datetime, timezone, timedelta
            from sqlalchemy import select as sa_select

            now = datetime.now(timezone.utc)
            existing = (await session.execute(
                sa_select(PlayerBuff).where(
                    PlayerBuff.player_id == player.telegram_id,
                    PlayerBuff.buff_type == "pill_charm",
                    PlayerBuff.expires_at > now
                )
            )).scalar_one_or_none()
            if existing:
                player.spirit_jade += item["jade"]
                await safe_answer(query, t(player.language or "en", "shop_charm_active"), show_alert=True)
                return

            buff = PlayerBuff(
                player_id=player.telegram_id,
                buff_type="pill_charm",
                buff_value=3.0,  # 3 uses remaining
                source="convenience_shop",
                expires_at=now + timedelta(days=7)
            )
            session.add(buff)
            result_msg = t(player.language or "en", "shop_pill_charm_result")

        elif item_key == "trib_blessing":
            # Tribulation Blessing — +15% trib success for 1 tribulation
            from database.models import PlayerBuff
            from datetime import datetime, timezone, timedelta
            from sqlalchemy import select as sa_select

            now = datetime.now(timezone.utc)
            existing = (await session.execute(
                sa_select(PlayerBuff).where(
                    PlayerBuff.player_id == player.telegram_id,
                    PlayerBuff.buff_type == "trib_blessing",
                    PlayerBuff.expires_at > now
                )
            )).scalar_one_or_none()
            if existing:
                player.spirit_jade += item["jade"]
                await safe_answer(query, t(player.language or "en", "shop_charm_active"), show_alert=True)
                return

            buff = PlayerBuff(
                player_id=player.telegram_id,
                buff_type="trib_blessing",
                buff_value=0.15,  # +15% success
                source="convenience_shop",
                expires_at=now + timedelta(days=30)
            )
            session.add(buff)
            result_msg = t(player.language or "en", "shop_trib_blessing_result")

        elif item_key == "beast_lure":
            # Beast Lure — +20% beast capture rate for 5 attempts
            from database.models import PlayerBuff
            from datetime import datetime, timezone, timedelta
            from sqlalchemy import select as sa_select

            now = datetime.now(timezone.utc)
            existing = (await session.execute(
                sa_select(PlayerBuff).where(
                    PlayerBuff.player_id == player.telegram_id,
                    PlayerBuff.buff_type == "beast_lure",
                    PlayerBuff.expires_at > now
                )
            )).scalar_one_or_none()
            if existing:
                player.spirit_jade += item["jade"]
                await safe_answer(query, t(player.language or "en", "shop_charm_active"), show_alert=True)
                return

            buff = PlayerBuff(
                player_id=player.telegram_id,
                buff_type="beast_lure",
                buff_value=5.0,  # 5 uses remaining
                source="convenience_shop",
                expires_at=now + timedelta(days=7)
            )
            session.add(buff)
            result_msg = t(player.language or "en", "shop_beast_lure_result")

        elif item_key == "fortune_incense":
            # Fortune Incense — +5% dungeon drop rate for 1h
            from database.models import PlayerBuff
            from datetime import datetime, timezone, timedelta
            from sqlalchemy import select as sa_select

            now = datetime.now(timezone.utc)
            existing = (await session.execute(
                sa_select(PlayerBuff).where(
                    PlayerBuff.player_id == player.telegram_id,
                    PlayerBuff.buff_type == "fortune_incense",
                    PlayerBuff.expires_at > now
                )
            )).scalar_one_or_none()
            if existing:
                player.spirit_jade += item["jade"]
                await safe_answer(query, t(player.language or "en", "shop_charm_active"), show_alert=True)
                return

            buff = PlayerBuff(
                player_id=player.telegram_id,
                buff_type="fortune_incense",
                buff_value=0.05,  # +5% drop rate
                source="convenience_shop",
                expires_at=now + timedelta(hours=1)
            )
            session.add(buff)
            result_msg = t(player.language or "en", "shop_fortune_incense_result")

        elif item_key == "celestial_essence":
            # C-5 — Celestial Essence Pellet. Mahayana-only; refund and warn
            # otherwise so non-endgame players don't burn jade by accident.
            lang = player.language or "en"
            if player.realm < 8:
                player.spirit_jade += item["jade"]  # refund
                await safe_answer(query, t(lang, "shop_celestial_essence_not_mahayana"), show_alert=True)
                return
            player.celestial_essence = (player.celestial_essence or 0) + 100
            result_msg = t(lang, "shop_celestial_essence_result", amount=100)

        elif item_key == "trial_cd_break":
            # F-11.5 + 2026-05-23 universal extension: clears BOTH the 6h
            # Celestial Trial CD and the 6h Heavenly Tribulation failure CD,
            # whichever (or both) are active. Refunds only if neither is set.
            from datetime import datetime, timezone, timedelta
            from config import TRIBULATION_COOLDOWN_FAILURE_LIGHT
            from database.models import Tribulation
            from sqlalchemy import select as sa_select, desc as sa_desc
            now = datetime.now(timezone.utc)
            lang = player.language or "en"

            # 1) Celestial Trial CD (Mahayana, R8 sub 1/5/9 trials).
            celestial_cd = getattr(player, "celestial_trial_cooldown_until", None)
            celestial_active = bool(celestial_cd and celestial_cd > now)

            # 2) Heavenly Tribulation failure CD (computed from latest failed
            # Tribulation row for the NEXT realm — same query as game_logic).
            cutoff = now - timedelta(seconds=TRIBULATION_COOLDOWN_FAILURE_LIGHT)
            last_failed_trib = (await session.execute(
                sa_select(Tribulation).where(
                    Tribulation.player_id == player.telegram_id,
                    Tribulation.realm == (player.realm or 0) + 1,
                    Tribulation.status == "failed",
                    Tribulation.completed_at != None,  # noqa: E711
                ).order_by(sa_desc(Tribulation.completed_at)).limit(1)
            )).scalar_one_or_none()
            trib_active = bool(
                last_failed_trib
                and last_failed_trib.completed_at
                and last_failed_trib.completed_at > cutoff
            )

            if not celestial_active and not trib_active:
                player.spirit_jade += item["jade"]  # refund
                await safe_answer(query, t(lang, "shop_trial_cd_not_active"), show_alert=True)
                return

            if celestial_active:
                player.celestial_trial_cooldown_until = None
            if trib_active:
                # Push completed_at past the 6h window so check_breakthrough
                # treats the failure as expired. Single mutation, no migration.
                last_failed_trib.completed_at = cutoff - timedelta(minutes=1)
            result_msg = t(lang, "shop_trial_cd_break_result")

        else:
            result_msg = t(player.language or "en", "shop_item_purchased")

        # Log purchase
        from database.models import Purchase
        session.add(Purchase(
            player_id=player.telegram_id,
            product_id=f"convenience_{item_key}",
            amount_eur=0.0,
            spirit_jade_granted=0,
            payment_method="jade",
            status="completed"
        ))

        await session.commit()
        
        # Display the result directly instead of just a popup window
        lang = player.language or "en"
        text = t(lang, "shop_purchase_success", result=result_msg, cost=item['jade'])
        keyboard = [
            [InlineKeyboardButton(t(lang, "shop_purchase_btn_back_conv"), callback_data="shop_convenience")],
            [InlineKeyboardButton(t(lang, "shop_purchase_btn_main"), callback_data="cmd_status")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def process_daoname_change_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_daoname_change"):
        return

    name = update.message.text.strip()
    lang = "en"  # will be overridden after player lookup
    if len(name) < 3 or len(name) > 16:
        await update.message.reply_text(t(lang, "shop_name_length"))
        return

    # Check valid characters like in start.py
    import re
    if not re.match(r"^[A-Za-z0-9_]+$", name):
        await update.message.reply_text(t(lang, "shop_name_invalid_chars"))
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        from sqlalchemy import select, func
        stmt = select(Player).where(func.lower(Player.dao_name) == name.lower())
        existing = (await session.execute(stmt)).scalar_one_or_none()
        
        if existing:
            await update.message.reply_text(t(lang, "shop_name_taken"))
            return
            
        old_name = player.dao_name
        player.dao_name = name
        await session.commit()
    
    context.user_data["awaiting_daoname_change"] = False
    await update.message.reply_text(t(lang, "shop_name_success", old=old_name, new=name))

@safe_handler
@rate_limit(1)
async def cmd_gastos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Quick command to see total spent
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        
        from database.models import PlayerVIP
        from sqlalchemy import select
        stmt = select(PlayerVIP).where(PlayerVIP.player_id == player.telegram_id)
        vip_record = (await session.execute(stmt)).scalar_one_or_none()
        total_spent = vip_record.total_spent_eur if vip_record else 0.0
        
        await update.message.reply_text(t(lang, "shop_total_spent", total=total_spent), parse_mode="Markdown")

def stars_refusal() -> tuple[str, str]:
    """(razão, chave i18n) de quem tenta pagar Stars num mundo que NÃO cobra — o
    dono das duas superfícies (o pre-checkout do chat e as 2 cobranças do mini-app).

    Se o `main` cobra, há para onde ir, e a frase aponta-o ("compras reais só no
    Servidor Principal"). Se nenhum mundo desta instalação cobra, apontar um
    Servidor Principal que também não vende seria mentir — a frase diz que as
    compras reais só existem no jogo oficial. (Open Source F4b, 23/10: as duas
    frases vivem no código, e a edição comunitária deixa de reescrever a primeira.)
    """
    from database.db import monetization_enabled_for
    if monetization_enabled_for("main"):
        return "sandbox_world", "shop_sandbox_blocked"
    return "purchases_official_only", "shop_purchases_official_only"


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    payload = query.invoice_payload or ""
    if payload.startswith("jade_") or payload.startswith("bp_premium_") or payload.startswith("monthly_"):
        # Multi-Servidor SANDBOX (2026-07-10) — invoice links do Telegram são
        # DURÁVEIS: um link gerado num mundo sandbox ANTES do guard de geração
        # (webserver buy_jade/buy_monthly) continua pagável para sempre. Este é
        # o portão que recusa ANTES da cobrança: parse do mundo do payload
        # (MESMA lógica do successful_payment: world = parts[3:] joined) e
        # recusa honesta se o mundo não monetiza. Fail-open por construção:
        # payload sem mundo / mundo desconhecido / QUALQUER erro interno →
        # aprova (pagantes do main nunca bloqueados por falha do control-plane).
        _refuse = False
        _lang = "pt"
        _refuse_key = "shop_sandbox_blocked"
        try:
            from database.db import monetization_enabled_for, iter_world_keys
            _pp = payload.split("_")
            _w = "_".join(_pp[3:]) if len(_pp) > 3 else "main"
            if _w not in set(iter_world_keys()):
                _w = "main"
            if not monetization_enabled_for(_w):
                _refuse = True
                try:
                    _refuse_key = stars_refusal()[1]
                except Exception:
                    pass
                try:
                    async with get_session_factory()() as session:
                        from sqlalchemy import select as _select
                        _l = (await session.execute(
                            _select(Player.language).where(Player.telegram_id == await resolve_chat_player_id(query.from_user.id))
                        )).scalar_one_or_none()
                    _lang = (_l or "pt").lower()
                    if _lang not in ("pt", "en", "es"):
                        _lang = "pt"
                except Exception:
                    pass
        except Exception:
            _refuse = False  # fail-open — nunca travar um pagamento do main por erro interno
        # Resposta FORA do try (Telegram aceita UM answer — decidir antes, responder 1×).
        if _refuse:
            await safe_answer(query, ok=False, error_message=t(_lang, _refuse_key))
        else:
            await safe_answer(query, ok=True)
    else:
        await safe_answer(query, ok=False, error_message="Invalid payload.")

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import logging as _logging
    _pay_logger = _logging.getLogger("payments")

    payment = update.message.successful_payment
    payload = payment.invoice_payload
    _pay_logger.info("successful_payment_callback: payload=%s total_amount=%s", payload, payment.total_amount)

    # Multi-Servidor: credit the purchase to the world it was MADE in. Mini-app
    # invoices append the active world to the payload (jade_<amt>_<id>_<world> /
    # monthly_<type>_<id>_<world> / bp_premium_<id>_<world>); chat invoices omit it.
    # This payment is a CHAT update (main-only contextvar), so WITHOUT binding the
    # world the grant always landed in `main` — a Stars purchase in a secondary
    # world credited the wrong world (2026-06-24). For ALL 3 prefixes player_id is
    # parts[2] and the world is parts[3:] (joined — world keys may contain `_`);
    # absent (old/chat payload) or unknown world → main (safe + backwards-compat).
    from database.db import set_current_world, reset_current_world, iter_world_keys
    _pp = payload.split("_")
    _pay_world = "_".join(_pp[3:]) if len(_pp) > 3 else "main"
    if _pay_world not in set(iter_world_keys()):
        _pay_world = "main"
    _pay_world_token = set_current_world(_pay_world)
    _pay_logger.info("successful_payment_callback: crediting world=%s", _pay_world)

    try:
        if payload.startswith("jade_"):
            parts = payload.split("_")
            amount = int(parts[1])
            player_id = int(parts[2])

            async with get_session_factory()() as session:
                from database.models import Purchase
                from sqlalchemy import select

                # Fetch player
                stmt = select(Player).where(Player.telegram_id == player_id)
                player = (await session.execute(stmt)).scalar_one_or_none()

                if player:
                    from core.monetization import grant_jade
                    await grant_jade(session, player, amount)

                    # Log transaction (using stars total amount)
                    purchase = Purchase(
                        player_id=player_id,
                        product_id=f"jade_{amount}",
                        amount_eur=float(payment.total_amount), # Represented as stars
                        spirit_jade_granted=amount,
                        payment_method="telegram_stars",
                        status="completed"
                    )
                    session.add(purchase)

                    # Check VIP spending (Optional tracking: 50 stars ~= 1 eur approx)
                    from core.monetization import add_vip_spending
                    vip_result = await add_vip_spending(session, player_id, payment.total_amount * 0.02)

                    # ── First Top-Up Bonus ──────────────────────────
                    from sqlalchemy import func as sa_func
                    prev_jade_count = (await session.execute(
                        select(sa_func.count()).select_from(Purchase).where(
                            Purchase.player_id == player_id,
                            Purchase.product_id.like("jade_%"),
                            Purchase.payment_method == "telegram_stars",
                            Purchase.status == "completed",
                            Purchase.id != purchase.id  # exclude current
                        )
                    )).scalar() or 0

                    first_topup_bonus = 0
                    if prev_jade_count == 0:
                        # First jade purchase ever! Give 2x jade + 5000 stones + title
                        first_topup_bonus = amount  # extra jade (total = 2x)
                        await grant_jade(session, player, first_topup_bonus)
                        player.spirit_stones = (player.spirit_stones or 0) + 5000
                        # Grant title "Patron of the Dao"
                        ft_titles = list(player.unlocked_titles or [])
                        if "Patron of the Dao" not in ft_titles:
                            ft_titles.append("Patron of the Dao")
                            player.unlocked_titles = ft_titles
                            from sqlalchemy.orm.attributes import flag_modified as fm_ft
                            fm_ft(player, "unlocked_titles")
                        if not player.active_title or player.active_title == "":
                            player.active_title = "Patron of the Dao"
                        _pay_logger.info("FIRST TOP-UP BONUS: player=%s extra_jade=%s stones=5000", player_id, first_topup_bonus)

                    await session.commit()
                    _pay_logger.info("jade purchase committed: player=%s jade=%s", player_id, amount)

                    # Tell user
                    lang = player.language or "en"
                    if first_topup_bonus > 0:
                        await update.message.reply_text(
                            t(lang, "shop_first_topup_bonus", amount=amount, bonus=first_topup_bonus, total=amount + first_topup_bonus),
                            parse_mode="Markdown"
                        )
                    else:
                        await update.message.reply_text(t(lang, "shop_payment_success", amount=amount))

                    # ── VIP Milestone notifications ──
                    for ms in vip_result.get("milestones", []):
                        ms_text = t(lang, "shop_vip_milestone",
                                    label=ms["label"], threshold=ms["threshold"],
                                    jade=ms["jade"], stones=ms["stones"])
                        if ms.get("fragments"):
                            ms_text += f"\n🔮 +{ms['fragments']} Celestial Fragments"
                        if ms.get("title"):
                            ms_text += f"\n🏅 Title: *{ms['title']}*"
                        await update.message.reply_text(ms_text, parse_mode="Markdown")
                else:
                    _pay_logger.error("jade purchase FAILED: player %s not found in DB!", player_id)

        elif payload.startswith("bp_premium_"):
            parts = payload.split("_")
            player_id = int(parts[2])

            async with get_session_factory()() as session:
                from core.monetization import activate_battle_pass, add_vip_spending
                from database.models import Purchase

                success = await activate_battle_pass(session, player_id)
                if success:
                    purchase = Purchase(
                        player_id=player_id,
                        product_id="battle_pass_premium",
                        amount_eur=float(payment.total_amount),
                        spirit_jade_granted=0,
                        payment_method="telegram_stars",
                        status="completed"
                    )
                    session.add(purchase)

                    # 50 stars ~= 1 eur approx for VIP
                    bp_vip_result = await add_vip_spending(session, player_id, payment.total_amount * 0.02)
                    await session.commit()
                    _pay_logger.info("battle_pass purchase committed: player=%s", player_id)

                    from sqlalchemy import select as sa_select
                    p = (await session.execute(sa_select(Player).where(Player.telegram_id == player_id))).scalar_one_or_none()
                    if not p:
                        return
                    lang = p.language or "en"
                    await update.message.reply_text(t(lang, "shop_payment_success", amount="(Celestial Pass)"))
                    for ms in bp_vip_result.get("milestones", []):
                        ms_text = t(lang, "shop_vip_milestone", label=ms["label"], threshold=ms["threshold"], jade=ms["jade"], stones=ms["stones"])
                        if ms.get("fragments"): ms_text += f"\n🔮 +{ms['fragments']} Celestial Fragments"
                        if ms.get("title"): ms_text += f"\n🏅 Title: *{ms['title']}*"
                        await update.message.reply_text(ms_text, parse_mode="Markdown")
                else:
                    _pay_logger.warning("battle_pass activate returned False (already active?) for player=%s", player_id)

        elif payload.startswith("monthly_"):
            # monthly_silver_12345 or monthly_golden_12345
            parts = payload.split("_")
            card_type = parts[1]  # "silver" or "golden"
            player_id = int(parts[2])

            async with get_session_factory()() as session:
                from database.models import Purchase, PlayerVIP
                from core.monetization import add_vip_spending
                from sqlalchemy import select as sa_select
                from datetime import datetime as dt, timezone as tz, timedelta as td

                player = (await session.execute(sa_select(Player).where(Player.telegram_id == player_id))).scalar_one_or_none()
                if not player:
                    _pay_logger.error("monthly card FAILED: player %s not found!", player_id)
                    return

                # Get or create VIP record
                vip_rec = (await session.execute(
                    sa_select(PlayerVIP).where(PlayerVIP.player_id == player_id)
                )).scalar_one_or_none()
                if not vip_rec:
                    vip_rec = PlayerVIP(player_id=player_id)
                    session.add(vip_rec)
                    await session.flush()

                # Activate card
                now = dt.now(tz.utc)
                instant_jade = 50 if card_type == "silver" else 150
                vip_rec.monthly_card_type = card_type
                vip_rec.monthly_card_expires = now + td(days=30)
                vip_rec.monthly_card_claimed_today = None  # Can claim today

                from core.monetization import grant_jade
                await grant_jade(session, player, instant_jade)

                # Log purchase
                session.add(Purchase(
                    player_id=player_id,
                    product_id=f"monthly_{card_type}",
                    amount_eur=float(payment.total_amount),
                    spirit_jade_granted=instant_jade,
                    payment_method="telegram_stars",
                    status="completed"
                ))

                mc_vip_result = await add_vip_spending(session, player_id, payment.total_amount * 0.02)
                await session.commit()
                _pay_logger.info("monthly_card purchase committed: player=%s type=%s", player_id, card_type)

                lang = player.language or "en"
                daily = 8 if card_type == "silver" else 15
                await update.message.reply_text(
                    t(lang, "shop_monthly_activated", type=card_type.title(), jade=instant_jade, daily=daily),
                    parse_mode="Markdown"
                )
                for ms in mc_vip_result.get("milestones", []):
                    ms_text = t(lang, "shop_vip_milestone", label=ms["label"], threshold=ms["threshold"], jade=ms["jade"], stones=ms["stones"])
                    if ms.get("fragments"): ms_text += f"\n🔮 +{ms['fragments']} Celestial Fragments"
                    if ms.get("title"): ms_text += f"\n🏅 Title: *{ms['title']}*"
                    await update.message.reply_text(ms_text, parse_mode="Markdown")

    except Exception as exc:
        _pay_logger.exception("CRITICAL: successful_payment_callback FAILED for payload=%s: %s", payload, exc)
        # Notify admins
        from config import ADMIN_USERS
        if ADMIN_USERS:
            try:
                import traceback, html
                err_trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                msg = (
                    f"🚨 <b>PAYMENT CALLBACK FAILED</b>\n"
                    f"<b>Payload:</b> <code>{html.escape(payload)}</code>\n"
                    f"<b>Amount:</b> {payment.total_amount}\n\n"
                    f"<pre>{html.escape(err_trace[:3500])}</pre>"
                )
                await context.bot.send_message(chat_id=ADMIN_USERS[0], text=msg, parse_mode="HTML")
            except Exception:
                pass
    finally:
        # ALWAYS unbind the purchase's world (contextvar is task-local; a leak would
        # misroute later work on this task).
        reset_current_world(_pay_world_token)

_BP_MISSIONS_PER_PAGE = 5


async def _show_bp_missions(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        from core.bp_engine import get_player_missions
        from core.monetization import get_active_battle_pass

        bp = await get_active_battle_pass(session, player.telegram_id)
        is_premium = bp.is_premium if bp else False

        all_missions = await get_player_missions(session, player.telegram_id)
        total = len(all_missions)
        total_pages = max(1, -(-total // _BP_MISSIONS_PER_PAGE))
        page = max(0, min(page, total_pages - 1))

        start = page * _BP_MISSIONS_PER_PAGE
        page_missions = all_missions[start: start + _BP_MISSIONS_PER_PAGE]

        text = t(lang, "bp_missions_title")
        if not is_premium:
            text += t(lang, "bp_missions_no_premium_note") + "\n"
        text += "\n"

        keyboard = []
        for entry in page_missions:
            mission = entry["mission"]
            progress = entry["progress"]
            is_completed = entry["is_completed"]
            claimed = entry["claimed"]

            premium_badge = f" {t(lang, 'bp_missions_premium_badge')}" if mission.is_premium_only else ""
            desc = t(lang, mission.description_key, value=mission.objective_value)
            jade_str = f"💎{mission.reward_jade}" if mission.reward_jade else ""
            times_done = entry.get("times_completed", 0)

            # Reset type badge
            if mission.reset_type == "daily":
                type_badge = f" {t(lang, 'bp_badge_daily')}"
            elif mission.reset_type == "weekly":
                type_badge = f" {t(lang, 'bp_badge_weekly')}"
            else:
                type_badge = f" [T{mission.tier}]"

            if claimed:
                status = t(lang, "bp_missions_claimed_badge")
            elif is_completed:
                status = t(lang, "bp_missions_claimable")
            else:
                status = t(lang, "bp_missions_progress", current=progress, target=mission.objective_value)

            # Show completion count for repeatables
            repeat_str = f" (x{times_done})" if mission.reset_type != "none" and times_done > 0 else ""

            text += f"▫️ *{type_badge}* {desc}{premium_badge}{repeat_str}\n"
            text += f"   {status}  {jade_str}\n\n"

            if is_completed and not claimed:
                keyboard.append([InlineKeyboardButton(
                    t(lang, "bp_missions_claim_btn", tier=mission.tier) if mission.reset_type == "none" else t(lang, "bp_missions_claim_repeatable_btn", desc=t(lang, mission.description_key, value=mission.objective_value)[:20]),
                    callback_data=f"bp_claim_miss_{mission.id}"
                )])

        # Pagination buttons
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀", callback_data=f"bp_missions_{page - 1}"))
        nav.append(InlineKeyboardButton(t(lang, "bp_missions_page", page=page + 1, total=total_pages), callback_data="none"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("▶", callback_data=f"bp_missions_{page + 1}"))
        if nav:
            keyboard.append(nav)

        keyboard.append([InlineKeyboardButton(t(lang, "btn_market_back"), callback_data="shop_pass")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def _handle_bp_mission_claim(update: Update, context: ContextTypes.DEFAULT_TYPE, mission_id: int):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        from core.bp_engine import claim_bp_mission_reward

        result = await claim_bp_mission_reward(session, player.telegram_id, mission_id)
        await session.commit()

        if result["success"]:
            granted_str = " + ".join(result["granted"]) if result["granted"] else "—"
            await safe_answer(query, t(lang, "bp_missions_claim_success", rewards=granted_str), show_alert=True)
            # Refresh missions page
            await _show_bp_missions(update, context, page=0)
        elif result.get("error") == "premium_required":
            # Show CTA for free players instead of just an error toast
            text = t(lang, "bp_free_mission_cta")
            keyboard = [
                [InlineKeyboardButton(t(lang, "bp_free_mission_cta_btn"), callback_data="buy_bp_premium")],
                [InlineKeyboardButton(t(lang, "btn_market_back"), callback_data="bp_missions_0")]
            ]
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            error_map = {
                "not_completed":    t(lang, "bp_missions_err_not_done"),
                "already_claimed":  t(lang, "bp_missions_err_claimed"),
                "player_not_found": t(lang, "bp_missions_err_not_done"),
                "not_found":        t(lang, "bp_missions_err_not_done"),
            }
            await safe_answer(query, error_map.get(result["error"], result["error"]), show_alert=True)


def secure_cmd(func, limit=1):
    from core.utils import safe_handler, rate_limit
    return safe_handler(rate_limit(limit)(func))

# ─── Monthly Cards ────────────────────────────────────────────────────────────

MONTHLY_CARDS = {
    "silver": {"stars": 100, "instant_jade": 50,  "daily_jade": 8,  "name_key": "shop_monthly_silver"},
    "golden": {"stars": 300, "instant_jade": 150, "daily_jade": 15, "name_key": "shop_monthly_golden"},
}


async def _show_monthly_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        from database.models import PlayerVIP
        from sqlalchemy import select as sa_select
        from datetime import datetime, timezone

        vip_rec = (await session.execute(
            sa_select(PlayerVIP).where(PlayerVIP.player_id == player.telegram_id)
        )).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        has_active = False
        active_type = None
        days_left = 0
        can_claim = False

        if vip_rec and vip_rec.monthly_card_type and vip_rec.monthly_card_expires and vip_rec.monthly_card_expires > now:
            has_active = True
            active_type = vip_rec.monthly_card_type
            days_left = (vip_rec.monthly_card_expires - now).days
            today = now.date()
            can_claim = vip_rec.monthly_card_claimed_today != today

        text = t(lang, "shop_monthly_title")

        if has_active:
            card = MONTHLY_CARDS[active_type]
            claim_status = "✅" if not can_claim else "🎁"
            text += t(lang, "shop_monthly_active",
                      type=active_type.title(), daily=card["daily_jade"],
                      days=days_left, claim_status=claim_status)
        else:
            text += t(lang, "shop_monthly_none")

        text += "\n" + t(lang, "shop_monthly_silver_desc")
        text += t(lang, "shop_monthly_golden_desc")

        keyboard = []
        if has_active and can_claim:
            keyboard.append([InlineKeyboardButton(
                t(lang, "shop_monthly_btn_claim", jade=MONTHLY_CARDS[active_type]["daily_jade"]),
                callback_data="claim_monthly"
            )])

        if not has_active:
            keyboard.append([InlineKeyboardButton(
                t(lang, "shop_monthly_btn_silver"), callback_data="buy_monthly_silver"
            )])
            keyboard.append([InlineKeyboardButton(
                t(lang, "shop_monthly_btn_golden"), callback_data="buy_monthly_golden"
            )])

        keyboard.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="shop_main")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def _handle_monthly_card_buy(update: Update, context: ContextTypes.DEFAULT_TYPE, card_type: str):
    query = update.callback_query
    card = MONTHLY_CARDS.get(card_type)
    if not card:
        await safe_answer(query, "Invalid card type.", show_alert=True)
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        from database.models import PlayerVIP
        from sqlalchemy import select as sa_select
        from datetime import datetime, timezone

        vip_rec = (await session.execute(
            sa_select(PlayerVIP).where(PlayerVIP.player_id == player.telegram_id)
        )).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if vip_rec and vip_rec.monthly_card_type and vip_rec.monthly_card_expires and vip_rec.monthly_card_expires > now:
            await safe_answer(query, t(lang, "shop_monthly_already_active"), show_alert=True)
            return

        stars_cost = card["stars"]
        payload = f"monthly_{card_type}_{player.telegram_id}"
        prices = [LabeledPrice(t(lang, card["name_key"]), stars_cost)]

        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title=t(lang, card["name_key"]),
            description=t(lang, "shop_monthly_invoice_desc", type=card_type.title(),
                          instant=card["instant_jade"], daily=card["daily_jade"]),
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=prices
        )


async def _handle_monthly_card_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        from database.models import PlayerVIP
        from sqlalchemy import select as sa_select
        from datetime import datetime, timezone

        vip_rec = (await session.execute(
            sa_select(PlayerVIP).where(PlayerVIP.player_id == player.telegram_id)
        )).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        today = now.date()

        if not vip_rec or not vip_rec.monthly_card_type or not vip_rec.monthly_card_expires or vip_rec.monthly_card_expires <= now:
            await safe_answer(query, t(lang, "shop_monthly_no_card"), show_alert=True)
            return

        if vip_rec.monthly_card_claimed_today == today:
            await safe_answer(query, t(lang, "shop_monthly_already_claimed"), show_alert=True)
            return

        card = MONTHLY_CARDS.get(vip_rec.monthly_card_type)
        if not card:
            return

        daily_jade = card["daily_jade"]
        from core.monetization import grant_jade
        await grant_jade(session, player, daily_jade)
        vip_rec.monthly_card_claimed_today = today
        await session.commit()

        days_left = (vip_rec.monthly_card_expires - now).days
        await safe_answer(query, t(lang, "shop_monthly_claimed", jade=daily_jade, days=days_left), show_alert=True)
        await _show_monthly_cards(update, context)


# ─── Celestial Fragment Exchange ──────────────────────────────────────────────

FRAGMENT_EXCHANGE = {
    "rare":      {"cost": 30,  "label_key": "shop_frag_rare"},
    "epic":      {"cost": 100, "label_key": "shop_frag_epic"},
    "legendary": {"cost": 300, "label_key": "shop_frag_legendary"},
}


async def _show_fragment_exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        frags = player.celestial_fragments or 0
        text = t(lang, "shop_frag_title", fragments=frags)
        text += t(lang, "shop_frag_info")

        keyboard = []
        for rarity, info in FRAGMENT_EXCHANGE.items():
            label = t(lang, info["label_key"], cost=info["cost"])
            can_afford = "✅" if frags >= info["cost"] else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{can_afford} {label}", callback_data=f"frag_exchange_{rarity}"
            )])
        keyboard.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="shop_main")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def _handle_fragment_exchange(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    rarity = data.replace("frag_exchange_", "")
    exchange = FRAGMENT_EXCHANGE.get(rarity)
    if not exchange:
        await safe_answer(query, "Invalid exchange.", show_alert=True)
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        frags = player.celestial_fragments or 0
        if frags < exchange["cost"]:
            await safe_answer(query, t(lang, "shop_frag_not_enough", need=exchange["cost"], have=frags), show_alert=True)
            return

        # Pick a random item from the gacha pool of that rarity
        from database.models import GachaBanner
        from sqlalchemy import select as sa_select
        import random

        banner = (await session.execute(
            sa_select(GachaBanner).where(GachaBanner.is_active == True)
        )).scalars().first()

        if not banner or not banner.items:
            await safe_answer(query, "No active banner available.", show_alert=True)
            return

        rarity_bucket = banner.items.get(rarity)
        if isinstance(rarity_bucket, dict):
            item_list = rarity_bucket.get("items", [])
        elif isinstance(rarity_bucket, list):
            item_list = rarity_bucket
        else:
            item_list = []

        if not item_list:
            await safe_answer(query, "No items available for this rarity.", show_alert=True)
            return

        chosen = random.choice(item_list)
        item_name = chosen.get("name", "Unknown Item")
        item_type = chosen.get("type", "item")

        # Deduct fragments
        player.celestial_fragments = frags - exchange["cost"]

        # Grant item (reuse same logic as gacha)
        from core.utils import add_item_to_inventory
        if item_type == "artifact":
            catalog_id = chosen.get("catalog_id") or chosen.get("id")
            if catalog_id:
                from database.models import ArtifactCatalog, PlayerArtifact
                cat = (await session.execute(sa_select(ArtifactCatalog).where(ArtifactCatalog.id == int(catalog_id)))).scalar_one_or_none()
                art_grade = cat.grade or 0 if cat else 0
                art_stats = {}
                if cat and cat.base_stats:
                    art_stats = cat.base_stats.copy()
                    mult = 1.0 + (art_grade * 0.5)
                    for k in art_stats:
                        art_stats[k] = int(art_stats[k] * mult)
                session.add(PlayerArtifact(player_id=player.telegram_id, catalog_id=int(catalog_id), grade=art_grade, custom_stats=art_stats))
        elif item_type == "herb":
            item_id = chosen.get("herb_id") or chosen.get("id")
            qty = chosen.get("qty", 1)
            await add_item_to_inventory(session, player.telegram_id, "herb", int(item_id), qty)
        elif item_type == "pill":
            item_id = chosen.get("pill_id") or chosen.get("id")
            qty = chosen.get("qty", 1)
            await add_item_to_inventory(session, player.telegram_id, "pill", int(item_id), qty)
        elif item_type == "ore":
            item_id = chosen.get("ore_id") or chosen.get("id")
            qty = chosen.get("qty", 1)
            from database.models import PlayerOre
            ore = (await session.execute(sa_select(PlayerOre).where(
                PlayerOre.player_id == player.telegram_id, PlayerOre.ore_id == int(item_id)
            ))).scalars().first()
            if ore:
                ore.quantity += qty
            else:
                session.add(PlayerOre(player_id=player.telegram_id, ore_id=int(item_id), quantity=qty))
        elif item_type == "technique_scroll":
            tech_id = chosen.get("technique_id") or chosen.get("id")
            await add_item_to_inventory(session, player.telegram_id, "technique_scroll", int(tech_id))
        elif item_type in ("spirit_stones", "stones"):
            amount = chosen.get("amount", 1000)
            player.spirit_stones += amount
        else:
            player.spirit_stones += 1000
            item_name = "1000 Spirit Stones"

        await session.commit()

        rarity_emoji = {"rare": "💙", "epic": "💜", "legendary": "🌟"}.get(rarity, "")
        await safe_answer(query, t(lang, "shop_frag_exchanged", emoji=rarity_emoji, rarity=rarity.title(), name=item_name, cost=exchange["cost"]), show_alert=True)
        await _show_fragment_exchange(update, context)


def setup_shop_handlers(application):
    application.add_handler(CommandHandler("loja", secure_cmd(cmd_loja)))
    application.add_handler(CommandHandler("vip", secure_cmd(cmd_loja))) # alias
    application.add_handler(CommandHandler("pass", secure_cmd(cmd_loja))) # alias
    application.add_handler(CommandHandler("jade", secure_cmd(cmd_loja))) # alias
    application.add_handler(CommandHandler("gastos", secure_cmd(cmd_gastos)))

    application.add_handler(CallbackQueryHandler(secure_cmd(handle_shop_routes), pattern="^shop_.*|^buy_jade_.*|^buy_item_.*|^bp_tier_.*|^bp_missions_.*|^bp_claim_miss_.*|^buy_vip_root_confirm$|^buy_vip_root_protect$|^claim_bp_jade$|^buy_bp_premium$|^buy_monthly_.*|^claim_monthly$|^frag_exchange_.*|^vip_ms_claim_.*"))
    
    # Telegram Stars Handlers
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
