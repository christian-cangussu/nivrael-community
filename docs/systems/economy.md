# Economy

What cultivators own, how it changes hands, and the one place where real money
could enter — switched off in this edition.

## Currencies

| currency | earned by | spent on |
|---|---|---|
| **spirit stones** (`Player.spirit_stones`) | playing — fights, dungeons, quests, bounties, expeditions, the market | almost everything: crafting, travel, tempering, the ring, the market |
| **spirit jade** (`Player.spirit_jade`) | quests and streaks, achievements, events — and, where a world sells it, purchases | the shop's premium items |
| **sect contribution** (`Player.sect_contribution`) | serving an NPC house | the house's library and merit pavilion ([sects](sects-and-paths.md#the-nine-houses)) |
| **prestige points** (`Player.prestige_points`) | rebirth | the prestige pavilion ([progression](progression.md#prestige-and-rebirth)) |
| **celestial fragments** (`Player.celestial_fragments`) | the battle pass's later tiers — and, where a world sells them, the gacha and VIP milestones | exchanged in the shop for an item of the chosen rarity (`/api/miniapp/shop/fragment_exchange`) |

Every grant of jade goes through one function, `grant_jade()` in
`core/monetization.py`, which also keeps the lifetime total.

## The market

`core/economy.py`. A cultivator lists herbs, pills, ores, artifacts, cauldrons,
traps or scrolls — the 7<!--#len:core/economy.py:TRADEABLE_ITEM_TYPES--> kinds of `TRADEABLE_ITEM_TYPES` — up
to 10<!--#val:core/economy.py:MAX_LISTINGS--> listings at a time (`create_listing()`), at a fixed price or as an
auction (`place_bid()`, `finalize_auction()`). The item is held in escrow while
listed. A buyer takes the whole listing or part of it (`buy_listing()`,
`buy_partial()`); the market keeps a tax of 5%<!--#val:core/economy.py:MARKET_TAX-->. Prices are the
**buyer's**: the state of the continent they stand on and their reputation there
can make them dearer or cheaper ([living world](living-world.md#continents-and-their-states)),
and the screen says why. Every exchange is written to `Transaction`.

## Trading between players

A direct trade (`P2PTrade`) is built by both sides — items and stones in, both
confirm, then everything moves at once (`execute_trade()`), or nothing does.
A trade above 100,000<!--#val:core/economy.py:SUSPICIOUS_TRADE_THRESHOLD--> stones is reported to the admins.

## Real money

The official game sells Spirit Jade, a monthly card and the battle pass for
Telegram Stars, and has a gacha. In this edition **all of it is off by default**:

- `monetization_enabled_for()` (`database/db.py`) answers whether a world
  charges real money; with `NIVRAEL_MONETIZATION` unset it says no for every
  world, so the five checkouts — two in the client, three in the chat — refuse
  **before** charging, with a sentence that points to the official game;
- `gacha_enabled()` (`core/monetization.py`) closes the gacha at its owner:
  `perform_gacha_pull()` refuses before touching the database, and the screens
  say why;
- the shop still shows what exists, so the screens stay whole; the edition suite
  proves each refusal by calling the code that decides it
  (`scripts/_test_edicao_comunitaria.py`).

`NIVRAEL_MONETIZATION=1` restores the official behaviour — the shop
(`handlers/shop.py`, `/api/miniapp/shop/`), VIP levels and their milestones
(`get_vip_perks()`, `VIP_MILESTONES`), the monthly card, the pass
(`activate_battle_pass()`) and the gacha with its pity. Telegram Stars only pay
the owner of the bot that issues them.

## Where it lives

| | |
|---|---|
| engines | `core/economy.py`, `core/monetization.py` |
| chat | `/mercado`, `/vender`, `/trocar` |
| client API | `/api/miniapp/market/`, `/api/miniapp/trade/`, `/api/miniapp/shop/`, `/api/miniapp/shop_catalog`, `/api/miniapp/gacha/banners` |
| data | `MarketplaceListing`, `P2PTrade`, `Transaction`, `Purchase`, `PlayerVIP`, `BattlePass`, `GachaBanner`, `GachaHistory`, `GachaPity` |
| tests | `scripts/_test_edicao_comunitaria.py` |
