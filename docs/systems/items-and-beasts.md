# Items and beasts

What a cultivator carries — in the spatial ring — and the spirit beasts that
fight beside them and go on expeditions for them.

## The spatial ring

Everything a cultivator owns that is not equipped lives in the **spatial ring**
(`core/anel.py`, the one owner of its size and price). It has
5<!--#val:core/anel.py:MAX_RING_TIER--> tiers, from 50<!--#val:core/anel.py:RING_MAX_SLOTS[1]--> slots to
1,000<!--#val:core/anel.py:RING_MAX_SLOTS[5]-->; each expansion costs spirit stones, from
1,000<!--#val:core/anel.py:RING_UPGRADE_STONES[1]--> to 100,000<!--#val:core/anel.py:RING_UPGRADE_STONES[4]-->
(`custo_proximo()`, `expandir()`). Slots bought in the prestige shop add on top —
an expansion never takes them away. Adding anything to the ring goes through one
function that checks the free slots, `add_item_to_inventory()` in
`core/utils.py`.

The ring holds herbs, pills, ores, artifacts, cauldrons, scrolls and the
miscellaneous items. The names of the things that are not in a catalogue —
11<!--#len:core/itens.py:EMOJI--> kinds, from technique scrolls to beast eggs — come from one
place, `core/itens.py`, in the player's language.

**Using a miscellaneous item** (`core/inventory_actions.py`): a blueprint is
studied for forge experience; an ore pack opens into
1<!--#val:core/inventory_actions.py:ORE_PACK_ROLLS_MIN-->–3<!--#val:core/inventory_actions.py:ORE_PACK_ROLLS_MAX--> kinds of ore; a pill recipe scroll teaches a
random recipe the cultivator lacks; a mystery box gives one reward and never
junk. Today this is done in the chat (`/inventario`); the client lists these
items but has no button to use them yet.

## Spirit beasts

`core/beast_engine.py`. The catalogue has
15<!--#len:database/seeds/beasts_seeds.py:BEASTS--> beasts (`database/seeds/beasts_seeds.py`).

- **Capturing** (`attempt_capture()`) needs a beast trap in the ring; the best
  trap is used first.
- **Training** raises a beast's level — each level asks more experience than
  the last (`limiar_xp()`), one level or many at once (`train_beast_bulk()`) —
  and **evolving** (`evolve_beast()`) turns it into
  its next form when the requirements are met (`get_evolution_requirements()`).
- **The companion** — one beast at a time fights beside the cultivator and adds
  its bonuses (`set_companion()`, `get_companion_bonuses()`), folded into the
  [cultivator soul](../architecture.md#the-cultivator-soul); in a fight it brings
  its own ability (`get_pet_combat_ability()`).
- **Expeditions** — a beast that is not the companion can be sent on one of
  6<!--#len:database/seeds/beasts_seeds.py:EXPEDITIONS--> expeditions (`send_on_expedition()`), as many at a time as the
  cultivator has expedition slots, and comes back with
  rewards after its time (`collect_expedition()`). The expedition check job
  announces each finished expedition once. In a world with the body path, an
  expedition also brings hunt essence ([body](body.md#the-mortal-flesh)).

`core/bestas.py` owns what the beast screen confirms after an action — the
level, the experience, the rank — read from the engine before and after
(`ganho_da_acao()`), never guessed by the client.

## Where it lives

| | |
|---|---|
| engines | `core/anel.py`, `core/itens.py`, `core/inventory_actions.py`, `core/beast_engine.py`, `core/bestas.py`, `add_item_to_inventory()` in `core/utils.py` |
| chat | `/inventario`, `/bestiario` |
| client API | `/api/miniapp/inventory`, `/api/miniapp/inventory/ring_upgrade`, `/api/miniapp/beasts/` |
| catalogues | `BeastCatalog`, `ExpeditionCatalog` (`database/seeds/beasts_seeds.py`) |
| data | `PlayerInventory`, `PlayerSpatialRing`, `PlayerOre`, `PlayerArtifact`, `PlayerBeast` |
| tests | `scripts/_sabota_o_inventario.py`, `scripts/_sabota_as_bestas.py` |
