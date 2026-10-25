# Combat

Combat is the outward face of cultivation: a fight reads the same power the
profile shows ([the cultivator soul](../architecture.md#the-cultivator-soul)), and
one damage model decides every blow, whoever the opponent is.

## One model, two engines

`core/combat_model.py` is the single source of the damage, HP and mitigation
math — the "three treasures" model, where the soul is the largest term of a
strike and the body and Qi shape the rest. Both engines call it, so a sparring
match and an arena duel can never disagree:

- `core/duel_engine.py` — **turn-based duels**: each round both sides choose a
  technique at the same time, then the round resolves. Used for PvP and for
  every PvE fight a player plays by hand.
- `simulate_combat()` in `core/combat_engine.py` — **auto-resolved** fights
  (dungeon floors, quick sparring), with the same profile and the same math.

What the model guarantees, read from its constants:

- **HP has two pools**, a core and a soul shield (`combat_hp()`).
- **Mitigation is proportional, with one global cap**: nothing reduces a blow by
  more than 70%<!--#val:core/combat_model.py:REDUCTION_CAP-->, and part of the defence is pierced.
- **Critical hits** deal ×1.5<!--#val:core/combat_model.py:CRIT_MULT-->; the chance never passes
  25%<!--#val:core/combat_model.py:CRIT_CHANCE_CAP-->.
- **Fights end.** Damage grows every round (`heaven_pressure()`), so two
  defensive cultivators cannot stall forever, and a higher realm presses on a
  lower one each round (`realm_pressure_chip()`).

## A duel, round by round

A duel (`DuelSession`) is a small state machine: a challenge waits for the
defender to accept (5<!--#val:core/duel_engine.py:ACCEPTANCE_TIMEOUT_SECONDS/60--> minutes), then each
round waits for both actions — 15<!--#val:core/duel_engine.py:ROUND_TIMEOUT_SECONDS--> seconds, after which
the clock plays for whoever did not choose (`check_and_handle_timeout()`). With
`golpe_padrao` the clock plays the technique the player chose as their default
(`resolve_default_strike()`); otherwise a basic strike that costs no Qi.

- **Combat Qi.** A fight draws on a pool of 20%<!--#val:core/duel_engine.py:COMBAT_POOL_PCT--> of the
  cultivator's Qi, regaining 10%<!--#val:core/duel_engine.py:REGEN_PCT_PER_ROUND--> each round; techniques
  cost from it.
- **Sudden death.** A duel still undecided at the end goes up to
  3<!--#val:core/duel_engine.py:SUDDEN_DEATH_MAX_EXTRA_ROUNDS--> extra rounds with defences halved.
- **Wounds stay.** When a duel ends, part of the damage taken remains on the
  cultivator's real HP (`apply_post_duel_effects()`); `current_hp` is the
  persistent pool, and an empty value means full.

Every PvE family — the arena's fallback, dungeon bosses, exploration, the heart
demon, legacy caves, sect trials, ambushes, NPC cultivators… — is listed in
`PVE_SOURCES` and settled once, idempotently, by `settle_pve_duel()`
(`core/pve_duel_settle.py`) or by its own resolver. One sweeper,
`sweep_orphan_pve_duels()`, closes duels a player abandoned, for all families.

## Opponents

- **NPC fighters** come from six<!--#len:core/npc_loadouts.py:NPC_ARCHETYPES--> archetypes (bandit, sect
  disciple, beast, demon, boss, elder), each with its own techniques
  (`core/npc_loadouts.py`), at four<!--#len:core/combat_engine.py:NPC_DIFFICULTIES--> difficulties — easy,
  normal, hard, nightmare (`NPC_DIFFICULTIES`). Their choices come from
  `pick_npc_action()` in `core/npc_ai.py`: weighted by impact, and defensive when
  their HP drops under 30%<!--#val:core/npc_ai.py:REACTIVE_HP_THRESHOLD-->.
- **NPC cultivators** are persistent people of the world — see
  [living world](living-world.md#npc-cultivators).
- **Players**, through challenges (`PVPChallenge`, with an escrowed wager settled
  by `settle_pvp_duel()` in `core/pvp_duel_settle.py`) and the arena.

## The arena

`core/arena_engine.py` keeps a queue in the database (`ArenaQueue`), shared by
the chat and the client: `join_queue()`, then `try_match()` pairs players by ELO.
A player alone in the queue for 30<!--#val:core/arena_engine.py:ARENA_QUEUE_SOLO_TIMEOUT_SECONDS--> seconds meets
an NPC instead when the world has `arena_encontro_rapido`. A finished arena duel
is settled by `settle_arena_duel()` (`core/arena_duel_settle.py`): the ELO change
and the rewards of the tier. Rankings live in `ArenaRanking`.

## Techniques in a fight

- **Mastery** — five<!--#len:core/combat_engine.py:MASTERY_STAGES--> stages, gained by use; each multiplies
  the technique (`MASTERY_STAGES`).
- **Grade** — five<!--#len:core/combat_engine.py:TECHNIQUE_GRADES--> grades, from common to celestial,
  refined with spirit stones, scrolls and pills (`GRADE_UPGRADE_REQS`).
- **Stance** — offensive, balanced or defensive before the fight
  (`apply_stance_and_focus()`).
- **Slots** — the realm sets how many combat techniques can be equipped
  (`get_max_combat_techniques()`).

How techniques are learned is in [techniques](techniques.md).

## Intent

Five<!--#len:core/intent_engine.py:INTENT_KEYS--> intents — sword, fist, body, Dao and killing
(`core/intent_engine.py`) — grow with the techniques a cultivator fights with,
up to rank 9<!--#val:core/intent_engine.py:MAX_RANK-->. They counter each other like a wheel (sword
over body, body over fist, fist over sword, Dao over killing, killing over sword,
body and Dao): the stronger intent of an exchange adds up to
50%<!--#val:core/intent_engine.py:ACTIVE_BONUS_MAX--> (`calculate_intent_modifier()`). Each technique used
gives intent experience, and the dominant intent of a duel gets more for a win
(`award_post_duel_intent_xp()`).

## The world boss

`core/boss_engine.py` spawns one boss per tier of realms — mortal, spirit,
immortal (`TIER_CONFIG`) — once a day; it lives for
24<!--#val:core/boss_engine.py:BOSS_DURATION_HOURS--> hours. Everyone in the tier attacks it, once every
30<!--#val:core/boss_engine.py:ATTACK_COOLDOWN_SECONDS/60--> minutes; the stronger bosses change phase as their HP falls
(enraged, shielded, final). When it dies or expires, the rewards are shared by
damage, and the top 10<!--#val:core/boss_engine.py:TOP_CONTRIBUTORS_COUNT--> contributors are named. Chat:
`/boss`.

## Where it lives

| | |
|---|---|
| engines | `core/combat_model.py`, `core/combat_engine.py`, `core/duel_engine.py`, `core/npc_ai.py`, `core/npc_loadouts.py`, `core/pve_duel_settle.py`, `core/pvp_duel_settle.py`, `core/arena_engine.py`, `core/arena_duel_settle.py`, `core/intent_engine.py`, `core/boss_engine.py` |
| chat | `/combate`, `/desafiar`, `/arena`, `/ranking_arena`, `/tecnicas`, `/boss` |
| client API | `/api/miniapp/combat/`, `/api/miniapp/arena/`, `/api/miniapp/intent/`, `/api/miniapp/boss/`, `/api/miniapp/world_boss` |
| data | `DuelSession`, `CombatLog`, `ArenaQueue`, `ArenaRanking`, `PVPChallenge`, `PlayerNPCCooldown`, `PlayerIntent`, `WorldBoss`, `WorldBossDamage` |
| flags | `combate_unificado`, `golpe_padrao`, `arena_encontro_rapido` |
| tests | `scripts/_test_cena_cabe.py` (the duel fits the screen, measured in a browser), `scripts/_sabota_o_golpe.py`, `scripts/_sabota_o_hp.py` |
