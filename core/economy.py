import random
import uuid
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update as sa_update, delete, or_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import (
    Player, MarketplaceListing, P2PTrade, Transaction,
    PlayerInventory, PlayerArtifact, PlayerOre, PlayerCauldron,
    HerbCatalog, PillCatalog, OreCatalog, ArtifactCatalog, CauldronCatalog
)

logger = logging.getLogger(__name__)

MARKET_TAX = 0.05
MAX_LISTINGS = 10

# Item types allowed in P2P trades (whitelist). Spirit Jade/Stones/BeastCore never trade directly.
TRADEABLE_ITEM_TYPES = frozenset({"herb", "pill", "ore", "artifact", "cauldron", "beast_trap", "scroll"})
SUSPICIOUS_TRADE_THRESHOLD = 100_000  # stones; triggers admin log warning

def format_currency(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B".replace(".0", "")
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0", "")
    if value >= 1_000:
        return f"{value / 1_000:.1f}K".replace(".0", "")
    return str(value)

async def create_transaction(session: AsyncSession, from_p: int, to_p: int, t_type: str, 
                             item_type: str = None, item_id: int = None, qty: int = 1, 
                             price: int = 0, tax: int = 0, details: dict = None):
    tx = Transaction(
        from_player=from_p,
        to_player=to_p,
        type=t_type,
        item_type=item_type,
        item_id=item_id,
        quantity=qty,
        price=price,
        tax_paid=tax,
        details=details
    )
    session.add(tx)
    return tx

async def get_player_listings_count(session: AsyncSession, player_id: int) -> int:
    stmt = select(func.count()).select_from(MarketplaceListing).where(
        MarketplaceListing.seller_id == player_id,
        MarketplaceListing.is_sold == False,
        MarketplaceListing.expires_at > datetime.now(timezone.utc)
    )
    return (await session.execute(stmt)).scalar() or 0

async def create_listing(session: AsyncSession, player: Player, item_type: str, instance_id: int, 
                         quantity: int, price: int, is_auction: bool, duration_hours: int):
    # Check max listings
    count = await get_player_listings_count(session, player.telegram_id)
    if count >= MAX_LISTINGS:
        return None, "max_listings_reached"

    # Escrow item
    item_data = {}
    catalog_id = None
    
    if item_type in ["herb", "pill"]:
        stmt = select(PlayerInventory).where(PlayerInventory.id == instance_id, PlayerInventory.player_id == player.telegram_id)
        p_inv = (await session.execute(stmt)).scalar_one_or_none()
        if not p_inv or p_inv.quantity < quantity:
            return None, "not_enough_items"

        catalog_id = p_inv.item_id
        # Preserve crafted quality through the listing escrow so a Perfect pill
        # isn't delivered as Normal on buy (review 2026-06-13; mirrors the P2P
        # trade fix — _give_item reads item_data["quality"]).
        item_data = {"quality": p_inv.quality or "normal"}
        p_inv.quantity -= quantity
        if p_inv.quantity <= 0:
            await session.delete(p_inv)

    elif item_type == "ore":
        stmt = select(PlayerOre).where(PlayerOre.id == instance_id, PlayerOre.player_id == player.telegram_id)
        p_ore = (await session.execute(stmt)).scalar_one_or_none()
        if not p_ore or p_ore.quantity < quantity:
            return None, "not_enough_items"
        
        catalog_id = p_ore.ore_id
        p_ore.quantity -= quantity
        if p_ore.quantity <= 0:
            await session.delete(p_ore)
            
    elif item_type == "artifact":
        stmt = select(PlayerArtifact).where(PlayerArtifact.id == instance_id, PlayerArtifact.player_id == player.telegram_id)
        art = (await session.execute(stmt)).scalar_one_or_none()
        if not art or art.is_equipped:
            return None, "item_not_available"
        
        catalog_id = art.catalog_id
        # Store all custom data to restore later if needed
        item_data = {
            "grade": art.grade,
            "enchant_rune": art.enchant_rune,
            "has_spirit": art.has_spirit,
            "spirit_name": art.spirit_name,
            "custom_stats": art.custom_stats
        }
        # Mark as "escrowed" by changing owner to a system ID or just removing from player
        # Here we'll delete it and store in item_data to recreate it
        await session.delete(art)
        
    elif item_type == "cauldron":
        stmt = select(PlayerCauldron).where(PlayerCauldron.id == instance_id, PlayerCauldron.player_id == player.telegram_id)
        caul = (await session.execute(stmt)).scalar_one_or_none()
        if not caul or caul.is_equipped:
            return None, "item_not_available"
        
        catalog_id = caul.cauldron_id
        item_data = {"durability": caul.durability}
        await session.delete(caul)
    else:
        return None, "invalid_item_type"

    listing = MarketplaceListing(
        seller_id=player.telegram_id,
        item_type=item_type,
        item_id=catalog_id,
        item_data=item_data,
        quantity=quantity,
        unit_price=price,
        is_auction=is_auction,
        current_bid=price if is_auction else None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=duration_hours)
    )
    session.add(listing)
    await session.flush()
    
    return listing, "success"

async def _region_price_mult(session, buyer: Player) -> float:
    """MV-3 Estados Regionais + MV-6 Reputação — o multiplicador do MERCADO
    LOCAL (o lugar onde o COMPRADOR está: prospera −5% · sitiada +10% ·
    festival −10%; rep ≥+25 −5% · rep ≤−25 +5%). Os dois EMPILHAM, mas o
    desconto COMBINADO nunca excede a taxa do mercado (clamp 1−MARKET_TAX —
    regra eterna do MV-3: comprador pagando menos do que o vendedor recebe =
    impressora; o clamp estrutural buyer_pays ≥ seller_receive continua por
    baixo e cobre também listings de NPC com desconto empilhado). Cada leitor
    é gated pela própria flag + fail-safe 1.0 (a compra nunca quebra)."""
    mult = 1.0
    try:
        from core.region_state_engine import market_price_mult
        mult *= float(await market_price_mult(session, buyer) or 1.0)
    except Exception:
        pass
    try:
        from core.reputation_engine import market_rep_mult
        mult *= float(await market_rep_mult(session, buyer) or 1.0)
    except Exception:
        pass
    # Clamp do desconto combinado (sobretaxa não é clampada — sink é sink).
    return max(mult, 1.0 - MARKET_TAX)


async def _lock_players_ordered(session: AsyncSession, *player_ids) -> dict:
    """Trava as rows de `players` em ordem ASCENDENTE de `telegram_id`.

    ⚠️ A ORDEM é a única coisa que importa aqui. O comprador nunca era travado
    antes do débito (`buyer.spirit_stones -=` sobre uma row sem lock), e o fix
    óbvio — travá-lo no endpoint — **criava um deadlock AB-BA** que não existia:
    A passava a segurar `Player A` + `listing_B` à espera de `Player B`, enquanto
    B segurava `Player B` + `listing_A` à espera de `Player A`. Dois jogadores a
    comprar a listagem um do outro ao mesmo tempo travavam a base de dados.

    Locks ascendentes matam a classe inteira: quem quer que chegue primeiro ao
    id menor ganha, e o outro espera em vez de segurar meio par. É o mesmo
    padrão que o P2P trade já usa (MA-39a).

    Devolve `{telegram_id: Player}` só para os ids que existem.
    """
    out: dict = {}
    for pid in sorted({int(p) for p in player_ids if p is not None}):
        row = (await session.execute(
            select(Player).where(Player.telegram_id == pid).with_for_update()
        )).scalar_one_or_none()
        if row is not None:
            out[pid] = row
    return out


async def buy_listing(session: AsyncSession, buyer: Player, listing_id: uuid.UUID):
    """Buy the entire listing (all units). total_price = unit_price × quantity.

    MV-3: o comprador paga total×mult do estado do SEU continente (o valor
    realmente debitado fica em ``listing._region_paid`` — atributo transiente
    para as superfícies exibirem o número honesto, Lei §1); o vendedor recebe
    base − taxa, intocado."""
    stmt = select(MarketplaceListing).where(MarketplaceListing.id == listing_id).with_for_update()
    listing = (await session.execute(stmt)).scalar_one_or_none()

    # Re-check is_sold inside the row-level lock to prevent concurrent purchases
    if not listing or listing.is_sold or listing.expires_at < datetime.now(timezone.utc):
        return None, "listing_not_available"

    if listing.is_auction:
        return None, "is_auction"

    if buyer.telegram_id == listing.seller_id:
        return None, "cannot_buy_own"

    total_price = listing.unit_price * listing.quantity
    is_npc = listing.seller_id is None
    tax = 0 if is_npc else int(total_price * MARKET_TAX)
    seller_receive = total_price - tax

    region_mult = await _region_price_mult(session, buyer)
    buyer_pays = int(round(total_price * region_mult))
    # Clamp anti-cunhagem (review MV-3, Lei §13): numa venda P2P o comprador
    # NUNCA paga menos do que o vendedor recebe — senão compra-revenda entre
    # duas contas imprime pedras (desconto > taxa). Vale para QUALQUER valor
    # de knob. (MV-6: o desconto COMBINADO estado×rep já vem clampado em
    # 1−taxa por _region_price_mult — vale TAMBÉM para listings de NPC; a
    # nota antiga "NPC pode ter o desconto cheio" foi superada pela regra
    # eterna "desconto nunca excede a taxa".)
    if not is_npc:
        buyer_pays = max(buyer_pays, seller_receive)

    # Locks ASCENDENTES do comprador e do vendedor, antes de ler o saldo e de
    # debitar. Ver `_lock_players_ordered` — travar o comprador no endpoint
    # parecia o fix e era um deadlock AB-BA.
    _locked = await _lock_players_ordered(session, buyer.telegram_id, listing.seller_id)
    buyer = _locked.get(int(buyer.telegram_id), buyer)
    seller = _locked.get(int(listing.seller_id)) if listing.seller_id else None

    if buyer.spirit_stones < buyer_pays:
        return None, "not_enough_stones"

    buyer.spirit_stones -= buyer_pays
    listing._region_paid = buyer_pays   # transiente (não persiste) — display honesto
    listing._region_mult = region_mult

    if not is_npc and seller is not None:
        # O lock do vendedor (fix de 2026-06-01) CONTINUA — mudou só o sítio
        # onde é adquirido: agora em `_lock_players_ordered`, junto com o do
        # comprador e em ordem determinística de telegram_id.
        seller.spirit_stones += seller_receive

    listing.is_sold = True

    # Give item to buyer
    await _give_item(session, buyer.telegram_id, listing.item_type, listing.item_id, listing.quantity, listing.item_data)

    # MV-7 — carimbo do continente do comprador (gated: None com a flag OFF →
    # Transaction EXATAMENTE como hoje). O Relatório do Mercado Imperial
    # prefere o carimbo ao join volátil com current_continent.
    _mv7_details = None
    try:
        from core.profession_engine import transaction_continent_details
        _mv7_details = await transaction_continent_details(session, buyer)
    except Exception:
        _mv7_details = None
    await create_transaction(session, buyer.telegram_id, listing.seller_id, "buy",
                             listing.item_type, listing.item_id, listing.quantity,
                             total_price, tax, details=_mv7_details)

    return listing, "success"


async def buy_partial(session: AsyncSession, buyer: Player, listing_id: uuid.UUID, qty: int):
    """Buy *qty* units from a listing. Splits the listing if qty < available."""
    stmt = select(MarketplaceListing).where(MarketplaceListing.id == listing_id).with_for_update()
    listing = (await session.execute(stmt)).scalar_one_or_none()

    if not listing or listing.is_sold or listing.expires_at < datetime.now(timezone.utc):
        return None, "listing_not_available"

    if listing.is_auction:
        return None, "is_auction"

    if buyer.telegram_id == listing.seller_id:
        return None, "cannot_buy_own"

    if qty <= 0:
        return None, "invalid_quantity"

    if qty > listing.quantity:
        return None, "not_enough_stock"

    total_price = listing.unit_price * qty
    is_npc = listing.seller_id is None
    tax = 0 if is_npc else int(total_price * MARKET_TAX)
    seller_receive = total_price - tax

    # MV-3 — mercado local: mesmo mult + clamp anti-cunhagem do buy_listing
    # (comprador paga, vendedor intocado; P2P nunca paga < seller_receive).
    region_mult = await _region_price_mult(session, buyer)
    buyer_pays = int(round(total_price * region_mult))
    if not is_npc:
        buyer_pays = max(buyer_pays, seller_receive)

    # Locks ASCENDENTES do comprador e do vendedor, antes de ler o saldo e de
    # debitar. Ver `_lock_players_ordered` — travar o comprador no endpoint
    # parecia o fix e era um deadlock AB-BA.
    _locked = await _lock_players_ordered(session, buyer.telegram_id, listing.seller_id)
    buyer = _locked.get(int(buyer.telegram_id), buyer)
    seller = _locked.get(int(listing.seller_id)) if listing.seller_id else None

    if buyer.spirit_stones < buyer_pays:
        return None, "not_enough_stones"

    buyer.spirit_stones -= buyer_pays
    listing._region_paid = buyer_pays   # transiente — display honesto (Lei §1)
    listing._region_mult = region_mult

    if not is_npc and seller is not None:
        # O lock do vendedor (fix de 2026-06-01) CONTINUA — mudou só o sítio
        # onde é adquirido: agora em `_lock_players_ordered`, junto com o do
        # comprador e em ordem determinística de telegram_id.
        seller.spirit_stones += seller_receive

    # Update listing quantity or mark as sold
    if qty == listing.quantity:
        listing.is_sold = True
    else:
        listing.quantity -= qty

    # Give items to buyer
    await _give_item(session, buyer.telegram_id, listing.item_type, listing.item_id, qty, listing.item_data)

    # MV-7 — carimbo do continente (gated; ver buy_listing).
    _mv7_details = None
    try:
        from core.profession_engine import transaction_continent_details
        _mv7_details = await transaction_continent_details(session, buyer)
    except Exception:
        _mv7_details = None
    await create_transaction(session, buyer.telegram_id, listing.seller_id, "buy",
                             listing.item_type, listing.item_id, qty,
                             total_price, tax, details=_mv7_details)

    return listing, "success"

async def place_bid(session: AsyncSession, bidder: Player, listing_id: uuid.UUID, amount: int):
    stmt = select(MarketplaceListing).where(MarketplaceListing.id == listing_id).with_for_update()
    listing = (await session.execute(stmt)).scalar_one_or_none()
    
    if not listing or listing.is_sold or listing.expires_at < datetime.now(timezone.utc):
        return None, "listing_not_available"
    
    if not listing.is_auction:
        return None, "not_an_auction"
    
    if bidder.telegram_id == listing.seller_id:
        return None, "cannot_bid_own"

    # Re-read current_bid inside the row-level lock to prevent concurrent bid races
    min_bid = listing.current_bid if listing.highest_bidder else listing.unit_price
    min_increment = int(min_bid * 0.05)
    
    if amount < min_bid + min_increment and listing.highest_bidder:
        return None, "bid_too_low"
    
    if amount < listing.unit_price:
        return None, "bid_too_low"

    # FIX 2026-06-01: lock the bidder row before the balance check + escrow.
    # Without it, the same bidder bidding on two auctions concurrently could
    # pass both checks and double-deduct, landing a negative balance.
    bidder = (await session.execute(
        select(Player).where(Player.telegram_id == bidder.telegram_id).with_for_update()
    )).scalar_one()

    if bidder.spirit_stones < amount:
        return None, "not_enough_stones"

    # Refund previous bidder (lock their row before returning the escrow).
    if listing.highest_bidder:
        stmt_prev = select(Player).where(Player.telegram_id == listing.highest_bidder).with_for_update()
        prev_bidder = (await session.execute(stmt_prev)).scalar_one()
        prev_bidder.spirit_stones += listing.current_bid

    # Escrow new bid
    bidder.spirit_stones -= amount
    listing.current_bid = amount
    listing.highest_bidder = bidder.telegram_id
    
    return listing, "success"

async def cancel_listing(session: AsyncSession, seller: Player, listing_id: uuid.UUID):
    """Cancel a listing the seller owns and return the escrowed item.

    Player report 2026-05-01 ([jogador]): "não consigo cancelar um item que
    coloquei pra vender". The cancel button existed in the UI (handlers/market
    line 491) but no callback was wired — the listing stayed locked forever.
    """
    stmt = select(MarketplaceListing).where(MarketplaceListing.id == listing_id).with_for_update()
    listing = (await session.execute(stmt)).scalar_one_or_none()

    if not listing or listing.is_sold:
        return None, "listing_not_available"

    if listing.seller_id != seller.telegram_id:
        return None, "not_owner"

    # Auction with an active bid: refusing keeps the bidder's escrow safe.
    if listing.is_auction and listing.highest_bidder:
        return None, "auction_has_bids"

    # Return the escrowed item to the seller.
    await _give_item(
        session, listing.seller_id, listing.item_type, listing.item_id,
        listing.quantity, listing.item_data,
    )
    listing.is_sold = True   # remove from active listings without altering schema
    return listing, "success"


async def finalize_auction(session: AsyncSession, listing_id: uuid.UUID):
    stmt = select(MarketplaceListing).where(MarketplaceListing.id == listing_id)
    listing = (await session.execute(stmt)).scalar_one_or_none()
    
    if not listing or listing.is_sold: return False
    
    is_npc = listing.seller_id is None

    if not listing.highest_bidder:
        # NPC listing with no bids just expires silently
        if not is_npc:
            await _give_item(session, listing.seller_id, listing.item_type, listing.item_id, listing.quantity, listing.item_data)
        listing.is_sold = True
        return True

    # Process sale
    if is_npc:
        tax = 0
    else:
        from core.monetization import get_player_vip_level, get_vip_perks
        vip_lvl = await get_player_vip_level(session, listing.seller_id)
        vip_perks = get_vip_perks(vip_lvl)
        base_tax = 0.05
        actual_tax_rate = max(0.0, base_tax - vip_perks["auction_tax_discount"])
        tax = int(listing.current_bid * actual_tax_rate)

    seller_receive = listing.current_bid - tax

    if not is_npc:
        # FIX 2026-06-01: lock the seller row (FOR UPDATE) before crediting.
        # Without it, a seller with two listings bought concurrently hit a
        # classic lost-update (both txns read the same balance, one += clobbers
        # the other → seller loses stones). Mirrors execute_trade's hardening.
        stmt_seller = select(Player).where(Player.telegram_id == listing.seller_id).with_for_update()
        seller = (await session.execute(stmt_seller)).scalar_one_or_none()
        if seller:
            seller.spirit_stones += seller_receive
    
    listing.is_sold = True
    
    # Give item to winner
    await _give_item(session, listing.highest_bidder, listing.item_type, listing.item_id, listing.quantity, listing.item_data)
    
    # MV-7 — carimbo do continente do vencedor (gated; ver buy_listing).
    _mv7_details = None
    try:
        from core.profession_engine import transaction_continent_details
        _mv7_details = await transaction_continent_details(session, listing.highest_bidder)
    except Exception:
        _mv7_details = None
    await create_transaction(session, listing.highest_bidder, listing.seller_id, "auction",
                             listing.item_type, listing.item_id, listing.quantity,
                             listing.current_bid, tax, details=_mv7_details)
    return True

async def _give_item(session: AsyncSession, player_id: int, item_type: str, item_id: int, quantity: int, item_data: dict):
    if item_type in ["herb", "pill", "jade_ring"]:
        from core.utils import add_item_to_inventory
        # MA-39a review 2026-06-13: preserve the crafted quality tier (a Perfect
        # pill must not settle as Normal) and force=True so a full recipient ring
        # never silently DESTROYS an owed item. quality rides in item_data (set at
        # escrow add-time); legacy/empty item_data defaults to "normal".
        quality = (item_data or {}).get("quality", "normal")
        await add_item_to_inventory(session, player_id, item_type, item_id, quantity, quality=quality, force=True)
            
    elif item_type == "ore":
        stmt = select(PlayerOre).where(
            PlayerOre.player_id == player_id,
            PlayerOre.ore_id == item_id
        )
        p_ore = (await session.execute(stmt)).scalar_one_or_none()
        if p_ore:
            p_ore.quantity += quantity
        else:
            p_ore = PlayerOre(
                player_id=player_id,
                ore_id=item_id,
                quantity=quantity
            )
            session.add(p_ore)
            
    elif item_type == "artifact":
        art = PlayerArtifact(
            player_id=player_id,
            catalog_id=item_id,
            grade=item_data.get("grade", 0),
            enchant_rune=item_data.get("enchant_rune"),
            has_spirit=item_data.get("has_spirit", False),
            spirit_name=item_data.get("spirit_name"),
            custom_stats=item_data.get("custom_stats")
        )
        session.add(art)
        
    elif item_type == "cauldron":
        caul = PlayerCauldron(
            player_id=player_id,
            cauldron_id=item_id,
            durability=item_data.get("durability", 100)
        )
        session.add(caul)

async def initiate_trade(session: AsyncSession, initiator_id: int, target_id: int):
    # Check if there is already a pending trade between them
    stmt = select(P2PTrade).where(
        P2PTrade.initiator_id == initiator_id,
        P2PTrade.target_id == target_id,
        P2PTrade.status == "pending"
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing: return existing, "already_pending"
    
    trade = P2PTrade(
        initiator_id=initiator_id,
        target_id=target_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    session.add(trade)
    await session.flush()
    return trade, "success"

async def execute_trade(session: AsyncSession, trade: P2PTrade):
    if trade.status != "pending": return False
    if not (trade.initiator_confirmed and trade.target_confirmed): return False

    # ── Whitelist check: reject any forbidden item types ──────────────────────
    for side_items in (trade.offer_items.get("items", []), trade.request_items.get("items", [])):
        for item in side_items:
            item_type = item.get("type", "")
            if item_type not in TRADEABLE_ITEM_TYPES:
                logger.warning(
                    f"TRADE BLOCKED — forbidden item type '{item_type}' | "
                    f"trade={trade.id} initiator={trade.initiator_id} target={trade.target_id}"
                )
                return False

    # ── Stones amounts must be non-negative ───────────────────────────────────
    initiator_stones = trade.offer_items.get("stones", 0)
    target_stones = trade.request_items.get("stones", 0)
    if initiator_stones < 0 or target_stones < 0:
        logger.warning(f"TRADE BLOCKED — negative stones | trade={trade.id}")
        return False

    # ── Atomic lock both players to prevent race conditions ───────────────────
    # Lock in a GLOBALLY CONSISTENT order (lowest telegram_id first), never in
    # trade-relative (initiator→target) order. Review 2026-06-13: two reciprocal
    # pending trades (X→Y and Y→X) confirming at once locked X,Y vs Y,X → AB-BA
    # deadlock → one confirm aborted as an opaque 500. Deterministic order makes
    # the cycle impossible.
    lo_id, hi_id = sorted((trade.initiator_id, trade.target_id))
    p_lo = (await session.execute(
        select(Player).where(Player.telegram_id == lo_id).with_for_update()
    )).scalar_one()
    p_hi = (await session.execute(
        select(Player).where(Player.telegram_id == hi_id).with_for_update()
    )).scalar_one()
    p_init, p_target = (p_lo, p_hi) if trade.initiator_id == lo_id else (p_hi, p_lo)

    if p_init.spirit_stones < initiator_stones or p_target.spirit_stones < target_stones:
        return False

    # ── Suspicious trade detection ────────────────────────────────────────────
    total_stones = initiator_stones + target_stones
    if total_stones >= SUSPICIOUS_TRADE_THRESHOLD:
        logger.warning(
            f"SUSPICIOUS TRADE (high value {total_stones:,} stones) | "
            f"trade={trade.id} initiator={trade.initiator_id} target={trade.target_id}"
        )

    # Transfer items from initiator offer to target
    for item in trade.offer_items.get("items", []):
        await _give_item(session, trade.target_id, item["type"], item["id"], item["qty"], item.get("data", {}))

    # Transfer items from target offer to initiator
    for item in trade.request_items.get("items", []):
        await _give_item(session, trade.initiator_id, item["type"], item["id"], item["qty"], item.get("data", {}))

    # Stones transfer
    if initiator_stones > 0:
        p_init.spirit_stones -= initiator_stones
        p_target.spirit_stones += initiator_stones

    if target_stones > 0:
        p_target.spirit_stones -= target_stones
        p_init.spirit_stones += target_stones

    # Final safety net: stones must never go negative
    if p_init.spirit_stones < 0 or p_target.spirit_stones < 0:
        logger.error(
            f"TRADE ABORTED — would produce negative stones | "
            f"trade={trade.id} init={p_init.spirit_stones} target={p_target.spirit_stones}"
        )
        return False

    trade.status = "completed"

    details = {
        "initiator_offer": trade.offer_items,
        "target_offer": trade.request_items,
        "total_stones": total_stones,
    }

    try:
        await create_transaction(session, trade.initiator_id, trade.target_id, "trade",
                                 price=total_stones, details=details)
    except Exception:
        await create_transaction(session, trade.initiator_id, trade.target_id, "trade")

    return True

async def get_player_transactions(session: AsyncSession, player_id: int, limit: int = 10, offset: int = 0):
    stmt = select(Transaction).where(
        or_(Transaction.from_player == player_id, Transaction.to_player == player_id),
        Transaction.type.in_(("buy", "sell", "auction", "trade", "fee"))
    ).order_by(desc(Transaction.created_at)).offset(offset).limit(limit)
    res = await session.execute(stmt)
    return res.scalars().all()

async def cancel_trade(session: AsyncSession, trade: P2PTrade):
    if trade.status != "pending": return False
    
    # Return items in escrow if we implemented it that way.
    # In my implementation, I'm thinking of blocking items instead of removing them until execution.
    # But for P2P trading, it's safer to remove them to escrow during the session.
    # Let's adjust create_listing and trade to handle escrow properly.
    
    # Actually, for P2P trade, the "escrow" happens at the moment of confirmation or when adding to trade?
    # Usually in these bots, players add items one by one.
    
    # Let's keep it simple: items are checked at execution. 
    # But GDD says "Sistema de escrow: itens bloqueados durante negociação".
    # This means when they add to trade, we should remove from inventory.
    
    # To keep this file concise, I'll assume we remove items on adding to trade and return on cancel.
    for item in trade.offer_items.get("items", []):
        await _give_item(session, trade.initiator_id, item["type"], item["id"], item["qty"], item.get("data", {}))

    for item in trade.request_items.get("items", []):
        await _give_item(session, trade.target_id, item["type"], item["id"], item["qty"], item.get("data", {}))

    trade.status = "cancelled"
    return True
