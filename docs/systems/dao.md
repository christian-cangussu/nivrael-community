# The Dao

From Soul Transformation on (`DAO_UNLOCK_REALM` in `core/dao_engine.py`), a
cultivator begins to comprehend the laws of the world. Two systems live side by
side, and `get_player_dao_bonuses()` folds both into one set of bonuses that the
[cultivator soul](../architecture.md#the-cultivator-soul) and cultivation read.

## The supreme laws

Six<!--#len:database/seeds/dao_seeds.py:DAO_LAWS--> great laws (`database/seeds/dao_seeds.py`), each comprehended by
gathering **fragments**: a fragment can come from meditation
(`try_grant_fragment()` — perception helps), from burning a rare scroll, from the
cave. Fragments raise a law through five<!--#len:core/dao_engine.py:INSIGHT_LEVELS--> levels of insight,
from none to the deepest (`INSIGHT_LEVELS`), each multiplying the Dao's weight and
easing the Dao trial of the highest tribulations (`calculate_dao_chance()` in
`core/tribulation_engine.py`).

## The three thousand laws

The second system is wide instead of deep: 3,000<!--#dao_laws--> laws
(`database/seeds/dao_3000_seeds.py`), in 8<!--#len:database/seeds/dao_3000_seeds.py:CATEGORIES--> categories and
30<!--#len:database/seeds/dao_3000_seeds.py:PATHS--> paths of 100<!--#val:database/seeds/dao_3000_seeds.py:LAWS_PER_PATH--> laws each — the path of
fire, of water, of space… (`core/dao_laws_engine.py`).

- A law is **discovered**, not trained: each meditation tick has a small chance
  (`try_discover_law()`), shaped by perception and by the law's rarity, of five
  rarities from common to legendary. The first law is guaranteed when the
  cultivator first reaches the Dao (`grant_first_law_on_unlock()`).
- A path climbs **tiers** as its share of laws discovered grows, up to the Dao
  Heart at the top (`get_path_tier()`); each category gives its own kind of bonus
  (`get_dao_laws_bonuses()`).
- The **heavenly laws** are apart: 100<!--#heavenly_laws--> of them, in paths that only
  celestial meditation can reach (`count_heavenly_discoveries()`). The apex of
  cultivation asks for all of them ([cultivation](cultivation.md#breakthroughs)).
- In Mahayana, mastering many paths opens the **Heavenly Dao**: from
  5<!--#val:core/celestial_engine.py:HEAVENLY_DAO_MIN_PATHS--> paths at their two highest tiers, +5%<!--#val:core/celestial_engine.py:HEAVENLY_DAO_BONUS_PER_PATH-->
  per path, up to +25%<!--#val:core/celestial_engine.py:HEAVENLY_DAO_MAX_BONUS--> (`get_heavenly_dao_bonus()` in
  `core/celestial_engine.py`).

## Where it lives

| | |
|---|---|
| engines | `core/dao_engine.py`, `core/dao_laws_engine.py` |
| chat | `/dao` |
| client API | `/api/miniapp/dao/summary`, `/api/miniapp/dao/path`, `/api/miniapp/dao/meditate_start`, `/api/miniapp/dao/meditate_cancel`, `/api/miniapp/celestial/heavenly_paths` |
| catalogues | `DaoLawCatalog` (`database/seeds/dao_seeds.py`), `DaoCategory`, `DaoPath`, `DaoPathLaw` (`database/seeds/dao_3000_seeds.py`, `database/seeds/heavenly_laws_seeds.py`) |
| data | `PlayerDaoFragment`, `PlayerDaoDiscovery` |
