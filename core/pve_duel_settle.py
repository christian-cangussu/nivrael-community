"""v15.1.4 — Settle PvE duels (NPC Hunt + Dungeon Boss) after termination.

When a turn-based PvE duel reaches a terminal state, this module runs
once (idempotent) to apply side-effects identical to the legacy
`simulate_combat` paths:

  * NPC Hunt (`pve_source='npc_hunt'`)        → mirrors `_handle_npc_fight`
    + `api_combat_duel_npc`: spirit_stones, loot table by difficulty,
    mastery XP, body tempering, quest tracking, CombatLog.
  * Dungeon Boss (`pve_source='dungeon_boss'`) → mirrors the boss-floor
    branch of `_do_dungeon_floor` + the dungeon-complete branch of
    `dungeon_advance`: if won, bag transfer, completion stamp, best
    difficulty bump, body tempering, faction/dungeon-quest tracking. If
    lost, 90% bag loss.

Called from `core/duel_engine.apply_post_duel_effects` via dispatcher:
  pve_source not None → settle_pve_duel.

Idempotency: a `pve_settled` marker entry in `duel.action_log` guards
against double-settlement on poll retries (mirror the `hp_drained` marker
already used by the mini-app duel_state poll).
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

# 名 2026-09-14 — o espolio diz o nome na lingua do cacador.
from core.i18n import catalog_name

from core.combat_engine import (
    MASTERY_STAGES,
    calculate_sparring_reward,
)
from database.models import (
    CombatLog,
    DuelSession,
    Player,
    PlayerTechnique,
)

logger = logging.getLogger(__name__)


def _already_settled(duel: DuelSession) -> bool:
    """Idempotency guard — once we stamp `pve_settled`, never run again."""
    for entry in (duel.action_log or []):
        if isinstance(entry, dict) and entry.get("type") == "pve_settled":
            return True
    return False


def _stamp_settled(duel: DuelSession, kind: str, payload: dict | None = None) -> None:
    """Append the idempotency marker. Settle path must call this once."""
    entry = {
        "round": int(duel.round_idx or 0),
        "type": "pve_settled",
        "kind": kind,
    }
    if payload:
        entry["payload"] = payload
    duel.action_log = (duel.action_log or []) + [entry]
    flag_modified(duel, "action_log")


def _count_tech_activations(action_log: list, side_key: str) -> dict[int, int]:
    """Mirror of `pvp_duel_settle._count_tech_activations` — keeps the
    mastery XP awarder shape consistent across PvP and PvE."""
    counts: dict[int, int] = {}
    for entry in action_log or []:
        side = entry.get(side_key) if isinstance(entry, dict) else None
        if not isinstance(side, dict):
            continue
        tech = side.get("tech")
        if not isinstance(tech, dict):
            continue
        tid = tech.get("id")
        if tid:
            counts[int(tid)] = counts.get(int(tid), 0) + 1
    return counts


async def _award_mastery_xp(session, player_id: int, activations: dict, won: bool) -> None:
    """Award mastery XP per technique activation. Same curve as PvP."""
    for tid, n in (activations or {}).items():
        if not n:
            continue
        row = (await session.execute(
            select(PlayerTechnique).where(
                PlayerTechnique.player_id == player_id,
                PlayerTechnique.technique_id == int(tid),
            )
        )).scalar_one_or_none()
        if not row:
            continue
        xp_gain = int(n) * 5 + (20 if won else 0)
        row.mastery_xp = int(row.mastery_xp or 0) + xp_gain
        while int(row.mastery_level or 1) < 5:
            nxt = MASTERY_STAGES.get(int(row.mastery_level or 1) + 1)
            if nxt and row.mastery_xp >= nxt["xp_req"]:
                row.mastery_level = int(row.mastery_level or 1) + 1
            else:
                break


# ── NPC Hunt settle (mirrors api_combat_duel_npc loot path) ─────────────


async def _settle_npc_hunt(session, duel: DuelSession, player: Player, won: bool) -> dict:
    """Roll NPC Hunt loot + award stones based on duel difficulty.

    Mirrors `combat_engine.NPC_LOOT_TABLE` rolls and `api_combat_duel_npc`
    side-effects. Returns a small summary dict for the action_log payload.
    """
    from core.combat_engine import NPC_LOOT_TABLE
    from database.models import (
        HerbCatalog, OreCatalog, PillCatalog, PlayerOre, TechniqueCatalog,
    )

    diff = duel.npc_difficulty or "normal"
    loot_list = NPC_LOOT_TABLE.get(diff, []) if won else []
    items_gained: list[dict] = []
    stones_gained = 0

    if won:
        for drop in loot_list:
            if drop["type"] == "core_essence" and int(player.realm or 0) > 2:
                continue
            # TEC-2 — só a linha de technique_scroll é cortada (pedras/ervas/
            # minérios/pílulas passam crus). Flag OFF ⇒ a chance original.
            from core.scroll_economy_engine import npc_loot_chance
            if random.random() > npc_loot_chance(drop):
                continue
            qty = int(drop.get("qty", 1))
            if drop["type"] == "spirit_stones":
                qty = random.randint(int(drop["min"]), int(drop["max"]))
                player.spirit_stones = int(player.spirit_stones or 0) + qty
                stones_gained += qty
                items_gained.append({"kind": "spirit_stones", "count": qty})
            elif drop["type"] == "herb":
                herbs = (await session.execute(
                    select(HerbCatalog).where(HerbCatalog.tier == int(drop["tier"]))
                )).scalars().all()
                if herbs:
                    item = random.choice(herbs)
                    from core.utils import add_item_to_inventory
                    added = await add_item_to_inventory(
                        session, player.telegram_id, "herb", int(item.id), qty,
                    )
                    if added:
                        items_gained.append({
                            "kind": "herb", "id": int(item.id),
                            "name": item.name, "count": qty,
                        })
            elif drop["type"] == "ore":
                ores = (await session.execute(
                    select(OreCatalog).where(OreCatalog.tier == int(drop["tier"]))
                )).scalars().all()
                if ores:
                    item = random.choice(ores)
                    pore = (await session.execute(
                        select(PlayerOre).where(
                            PlayerOre.player_id == player.telegram_id,
                            PlayerOre.ore_id == int(item.id),
                        )
                    )).scalar_one_or_none()
                    if pore:
                        pore.quantity = int(pore.quantity or 0) + qty
                    else:
                        session.add(PlayerOre(
                            player_id=player.telegram_id,
                            ore_id=int(item.id),
                            quantity=qty,
                        ))
                    items_gained.append({
                        "kind": "ore", "id": int(item.id),
                        "name": item.name, "count": qty,
                    })
            elif drop["type"] == "core_essence":
                if int(player.realm or 0) <= 2:
                    from core.golden_core_engine import add_core_essence
                    added = add_core_essence(player, qty)
                    if added > 0:
                        items_gained.append({"kind": "core_essence", "count": int(added)})
            elif drop["type"] == "technique_scroll":
                # v16.4c — sect signature arts (sect_key) are Library-only, never PvE scroll loot (Lei §5).
                techs = (await session.execute(
                    select(TechniqueCatalog).where(TechniqueCatalog.sect_key.is_(None))
                )).scalars().all()
                if techs:
                    item = random.choice(techs)
                    from core.utils import add_item_to_inventory
                    added = await add_item_to_inventory(
                        session, player.telegram_id, "technique_scroll", int(item.id), qty,
                    )
                    if added:
                        items_gained.append({
                            "kind": "technique_scroll", "id": int(item.id),
                            "name": item.name, "count": qty,
                        })
            elif drop["type"] == "pill":
                pill_id = int(drop["id"])
                from core.utils import add_item_to_inventory
                added = await add_item_to_inventory(
                    session, player.telegram_id, "pill", pill_id, qty,
                )
                if added:
                    pill_cat = await session.get(PillCatalog, pill_id)
                    items_gained.append({
                        "kind": "pill", "id": pill_id,
                        "name": (catalog_name((player.language or "pt").lower(), "pill", pill_cat)
                                 if pill_cat else f"Pill #{pill_id}"),
                        "count": qty,
                    })
            elif drop["type"] == "beast_trap":
                from core.utils import add_item_to_inventory
                added = await add_item_to_inventory(
                    session, player.telegram_id, "beast_trap", 0, qty,
                )
                if added:
                    items_gained.append({"kind": "beast_trap", "count": qty})

        # Side-effects identical to legacy api_combat_duel_npc.
        try:
            from core.quest_engine import track_quest
            await track_quest(session, player.telegram_id, "npc_combat", 1)
        except Exception:
            logger.exception("settle_npc_hunt: track_quest failed")
        try:
            from core.bp_engine import update_bp_mission
            await update_bp_mission(session, player.telegram_id, "win_npc_fight")
        except Exception:
            logger.exception("settle_npc_hunt: bp_mission failed")
        try:
            from core.body_tempering_engine import add_tempering_progress
            add_tempering_progress(player, 5)
        except Exception:
            logger.exception("settle_npc_hunt: body_tempering failed")
        try:
            from core.faction_engine import update_quest_progress as fac_quest_progress
            await fac_quest_progress(session, player.telegram_id, "npc_kill")
        except Exception:
            logger.exception("settle_npc_hunt: faction quest failed")

    # CombatLog entry (parity with legacy path).
    try:
        session.add(CombatLog(
            attacker_id=player.telegram_id,
            defender_id=None,
            mode="sparring",
            winner_id=player.telegram_id if won else None,
            rounds_data={"rounds": duel.action_log or [], "turn_based": True, "pve": True},
            spirit_stones_reward=int(stones_gained),
        ))
    except Exception:
        logger.exception("settle_npc_hunt: CombatLog insert failed")

    return {
        "stones_gained": int(stones_gained),
        "items_count": len(items_gained),
    }


# ── Dungeon Boss settle (mirrors dungeon_advance completion branch) ─────


async def _settle_dungeon_boss(session, duel: DuelSession, player: Player, won: bool) -> dict:
    """Apply dungeon-boss outcome: if won, complete the dungeon run; if
    lost, 90% bag loss.

    Mirrors `dungeon_advance` (handlers/dungeons.py) completion branch +
    `_lose_90_percent`. Idempotent via the `pve_settled` marker in
    `duel.action_log` (checked by caller before invoking us).
    """
    from database.models import DungeonCatalog, PlayerDungeon
    from handlers.dungeons import (
        _transfer_bag_to_inventory, _lose_90_percent, _roll_floor_loot,
        _apply_difficulty_loot_mult, _merge_bag, _get_floor_count,
        DIFF_CONFIG, DIFF_ORDER,
    )
    from core.activity_indicators import _invalidate_cache as _inv_cache

    ctx = duel.pve_context or {}
    dungeon_id = int(ctx.get("dungeon_id", 0))
    if not dungeon_id:
        logger.warning("settle_dungeon_boss: missing dungeon_id duel=%s", duel.id)
        return {"reason": "missing_dungeon_id"}

    dungeon = (await session.execute(
        select(DungeonCatalog).where(DungeonCatalog.id == dungeon_id)
    )).scalar_one_or_none()
    # 層 4.3 — com a onda, o "antes" lê-se aqui: só colunas, trancado, ANTES de
    # carregar a linha (`core/masmorra.ler_antes`). O jogador já está trancado
    # (`settle_pve_duel`), a mesma ordem das rotas. Sem a onda: nem consulta nem
    # trinco a mais. Nunca rebenta o settle (o espólio e a conclusão vêm antes).
    _antes = None
    if dungeon is not None:
        try:
            from core.portas import onda_on as _onda_on
            if _onda_on():
                from core import masmorra as _masmorra
                _antes = await _masmorra.ler_antes(session, player.telegram_id, dungeon)
        except Exception:
            logger.exception("settle_dungeon_boss: masmorra.ler_antes failed duel=%s", duel.id)
            _antes = None
    pd = (await session.execute(
        select(PlayerDungeon).where(
            PlayerDungeon.player_id == player.telegram_id,
            PlayerDungeon.dungeon_id == dungeon_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if not dungeon or not pd:
        logger.warning("settle_dungeon_boss: missing dungeon/pd duel=%s id=%s",
                       duel.id, dungeon_id)
        return {"reason": "missing_dungeon_or_pd"}

    difficulty = pd.difficulty or "normal"
    floor_count = _get_floor_count(dungeon, difficulty)
    boss_loot: dict = {}
    completed = False
    # ⚠️ BUG DE PRODUCAO (logs 2026-08-26): isto nascia DENTRO do ramo da
    # vitoria, mas o `return` no fim da funcao le-o nos DOIS ramos. Quem PERDIA
    # o chefe apanhava `UnboundLocalError` e o settle inteiro rebentava — o
    # `_lose_90_percent` e o reset de andar ficavam por gravar. Um nome so lido
    # no fim tem de nascer no topo, nunca num ramo.
    _tribute_line = ""

    if won:
        # Roll loot for the boss floor with a difficulty-scaled multiplier.
        # Boss loot = floor loot × 1.5 (boss bonus).
        boss_loot = _roll_floor_loot(dungeon.drops, difficulty, min_realm=int(dungeon.min_realm or 0))
        boss_loot = _apply_difficulty_loot_mult(boss_loot, difficulty)
        # Boss bonus: 1.5× across the board, plus a guaranteed scroll roll
        # so the boss feels rewarding even on easy.
        scaled: dict = {}
        for k, v in (boss_loot or {}).items():
            if k in ("herbs", "ores", "healing_pills") and isinstance(v, dict):
                scaled[k] = {kk: max(1, int(vv * 1.5)) for kk, vv in v.items()}
            elif k == "qi_pill_id":
                scaled[k] = v  # D4: tier marker, never scale it
            elif isinstance(v, (int, float)):
                scaled[k] = max(1, int(v * 1.5))
            else:
                scaled[k] = v
        boss_loot = scaled

        # MV-1 §5: roll extra de material NATIVO do continente na conclusão
        # de runs hard/nightmare (flag `dungeons_regionais` ON; aditivo).
        try:
            from core.dungeon_regions import regional_bonus_line, roll_regional_bonus
            _regional = roll_regional_bonus(dungeon, difficulty)
            if _regional:
                boss_loot = _merge_bag(boss_loot, _regional["loot"])
                # QoL 04/08 (report [jogador]) — TODA masmorra acaba num chefe, e o
                # chefe resolve AQUI: o tributo rolava e NINGUÉM o dizia (o dict
                # de retorno não o levava, então nem o chat nem o mini o viam).
                # Era o único caminho de conclusão REAL — o tributo só aparecia
                # na varredura, que foi exatamente onde o jogador o viu.
                _tribute_line = await regional_bonus_line(
                    session, _regional, getattr(player, "language", None) or "pt")
        except Exception:
            logger.exception("settle_dungeon_boss: roll_regional_bonus failed")

        # Merge boss loot into expedition bag, then complete the dungeon.
        merged_bag = _merge_bag(pd.expedition_bag or {}, boss_loot)
        await _transfer_bag_to_inventory(session, player, merged_bag)
        pd.current_floor = 0
        pd.expedition_bag = {}
        # Fix 2026-07-23 (report [jogador]): o andar do BOSS nunca entrava no
        # max_floor_reached — completar uma dungeon de 30 andares mostrava
        # "melhor andar: 29" (o advance só grava trash floors; o settle do
        # boss esquecia o último). Vencer o boss = alcançou o andar N.
        pd.max_floor_reached = max(int(pd.max_floor_reached or 0), int(floor_count))
        pd.completed = True
        diff_level = DIFF_ORDER[difficulty]
        pd.best_difficulty = max(int(pd.best_difficulty or 0), diff_level)
        pd.difficulty = None
        pd.last_attempt_at = datetime.now(timezone.utc)
        _inv_cache(player.telegram_id)
        completed = True

        # Side-effects identical to dungeon_advance completion path.
        try:
            from core.bp_engine import update_bp_mission
            await update_bp_mission(session, player.telegram_id, "complete_dungeon")
        except Exception:
            logger.exception("settle_dungeon_boss: bp_mission failed")
        try:
            from core.body_tempering_engine import add_tempering_progress
            tempering_base = max(10, floor_count * 3)
            tempering_diff_mult = DIFF_CONFIG[difficulty]["loot_mult"]
            add_tempering_progress(player, int(tempering_base * tempering_diff_mult))
        except Exception:
            logger.exception("settle_dungeon_boss: body_tempering failed")
        try:
            from core.faction_engine import update_quest_progress as fac_quest_progress
            await fac_quest_progress(session, player.telegram_id, "dungeon_any")
            await fac_quest_progress(
                session, player.telegram_id, "dungeon",
                target_filter={
                    "dungeon_id": dungeon_id, "floor": floor_count,
                    "difficulty": difficulty,
                },
            )
        except Exception:
            logger.exception("settle_dungeon_boss: faction quest failed")
        try:
            from core.dungeon_quest_engine import track_dungeon_quest_progress
            await track_dungeon_quest_progress(
                session, player.telegram_id, dungeon_id,
                "dungeon_complete", floor_count, difficulty, True,
            )
        except Exception:
            logger.exception("settle_dungeon_boss: dungeon_quest failed")
        # Abyssal achievement (legacy hook).
        if dungeon_id == 4:
            try:
                from core.achievement_engine import check_achievements
                await check_achievements(session, player.telegram_id, "dungeon_abyssal", 1)
            except Exception:
                logger.exception("settle_dungeon_boss: abyssal achievement failed")
    else:
        # Lost the boss → 90% bag loss + reset to floor 0 (same as a
        # death on the boss floor through the legacy path).
        lost_bag = pd.expedition_bag or {}
        survivors = _lose_90_percent(lost_bag)
        if survivors:
            await _transfer_bag_to_inventory(session, player, survivors)
        pd.current_floor = 0
        pd.expedition_bag = {}
        pd.difficulty = None
        pd.last_attempt_at = datetime.now(timezone.utc)

    # 層 4.3 — o ganho CONFIRMADO do chefe: o último andar só no ramo da
    # vitória (a derrota não passa andar nenhum e não acende); a dificuldade
    # quando `best_difficulty` sobe. Vai no payload do `pve_settled` e o
    # `duel_state` dá-o — só com a onda.
    _g = None
    if _antes is not None:
        try:
            from core import masmorra as _masmorra
            _g = await _masmorra.ganho_da_acao(session, player.telegram_id, dungeon, _antes,
                                               andar=floor_count if won else None)
        except Exception:
            logger.exception("settle_dungeon_boss: masmorra ganho failed duel=%s", duel.id)
            _g = None

    return {
        "dungeon_id": int(dungeon_id),
        "completed": bool(completed),
        "boss_loot": boss_loot if won else {},
        # Key CONDICIONAL (só quando o tributo caiu) — o duel_state expõe-a e as
        # 2 superfícies dizem o que a terra cedeu.
        **({"tribute_line": _tribute_line} if _tribute_line else {}),
        **({"masmorra_ganho": _g} if _g else {}),
    }


async def sweep_orphan_dungeon_boss_duels(session) -> int:
    """DEPRECADO desde 2026-09-04 — delega em `sweep_orphan_pve_duels`.

    ⚠️ Este varredor era um de TRES, cada um a nomear a SUA fonte, enquanto o
    codigo cria DEZ. Sete familias ficaram anos sem rede — entre elas a maior do
    jogo (`arena_npc_fallback`) e o proprio default de `start_duel_pve`
    (`npc_hunt`). Resultado medido a 2026-09-03: 27 duelos expirados a prender
    13 jogadores, o mais antigo ha' 103 dias.

    Fica como nome, nao como segunda implementacao: duas copias da mesma
    varredura divergem no primeiro fix que so' uma delas recebe. O scheduler
    chama a familia inteira, uma vez.
    """
    from core.duel_engine import sweep_orphan_pve_duels
    return await sweep_orphan_pve_duels(session)
async def settle_pve_duel(session, duel: DuelSession) -> bool:
    """Settle a PvE duel (NPC Hunt or Dungeon Boss). Idempotent.

    Returns True if settlement ran, False if skipped (not PvE-sourced,
    not terminal, or already settled).
    """
    if duel.state not in ("finished", "forfeited"):
        return False
    if not duel.pve_source:
        return False  # not a PvE duel
    if _already_settled(duel):
        return False

    # Lock attacker row for stones/HP writes.
    player = (await session.execute(
        select(Player).where(Player.telegram_id == duel.attacker_id).with_for_update()
    )).scalar_one_or_none()
    if not player:
        logger.warning("settle_pve_duel: attacker player not found duel=%s", duel.id)
        _stamp_settled(duel, kind="player_missing")
        return False

    # Player won when winner_id matches their telegram_id. 0 sentinel
    # (NPC) and forfeited state both count as a loss for the player.
    won = (duel.winner_id == duel.attacker_id and duel.state == "finished")

    # Mastery XP — counts activations on the player (side 'a') only;
    # NPC tech activations are not awarded to a real player.
    try:
        activations_a = _count_tech_activations(duel.action_log or [], "a")
        await _award_mastery_xp(session, player.telegram_id, activations_a, won=won)
    except Exception:
        logger.exception("settle_pve_duel: mastery XP failed duel=%s", duel.id)

    # v15.2 — Intent XP. PvE: only side A is a real player; the helper
    # skips side B internally (defender_id IS NULL).
    try:
        from core.intent_engine import award_post_duel_intent_xp
        await award_post_duel_intent_xp(session, duel, duel.winner_id)
    except Exception:
        logger.exception("settle_pve_duel: intent XP failed duel=%s", duel.id)

    # TEC-5 — o custo do Caminho Proibido já foi cobrado por
    # `apply_post_duel_effects` (o único ponto por onde TODO duelo passa; ver o
    # comentário lá). Aqui só LEMOS o carimbo para o payload do settle — o chat
    # lê daqui, o mini lê o mesmo marker via duel_state.
    forbidden_cost = None
    try:
        from core.forbidden_path_engine import read_forbidden_cost
        forbidden_cost = read_forbidden_cost(duel, "a")
    except Exception:
        logger.exception("settle_pve_duel: forbidden cost read failed duel=%s", duel.id)

    # Sparring reward applies to NPC Hunt (mirror legacy NPC reward shape);
    # Dungeon Boss bonuses come from boss_loot in _settle_dungeon_boss.
    payload: dict = {}
    if duel.pve_source == "npc_hunt":
        if won:
            atk_bp = int((duel.fighter_a or {}).get("bp", 0))
            def_bp = int((duel.fighter_b or {}).get("bp", 0))
            reward = calculate_sparring_reward(atk_bp, def_bp)
            player.spirit_stones = int(player.spirit_stones or 0) + int(reward)
            payload["sparring_reward"] = int(reward)
        npc_payload = await _settle_npc_hunt(session, duel, player, won)
        payload.update(npc_payload)
    elif duel.pve_source == "dungeon_boss":
        boss_payload = await _settle_dungeon_boss(session, duel, player, won)
        payload.update(boss_payload)
    elif duel.pve_source == "sect_trial":
        # v16.4b — Sect recruitment trial. The Elder duel decides membership:
        # win ⇒ join the house (+ accept the recruiter encounter); lose ⇒ 24h
        # cooldown. No loot/sparring reward — this is a rite, not a hunt.
        try:
            from core.sect_trial_engine import resolve_trial_from_duel
            trial_payload = await resolve_trial_from_duel(session, duel, player, won)
            payload.update(trial_payload)
        except Exception:
            logger.exception("settle_pve_duel: sect_trial resolve failed duel=%s", duel.id)
    elif duel.pve_source == "hidden_rite":
        # TEC-3 — a Prova da Sucessão 秘传. Vencer o Ancião que guarda a câmara
        # É o preço da Estante Oculta (Lei §4/§12: o segredo não se compra);
        # perder só arma o cooldown (derivado do resolved_at — nada a gravar).
        # Sem loot/sparring: é rito, não caçada.
        try:
            from core.sect_library_engine import resolve_hidden_rite_from_duel
            rite_payload = await resolve_hidden_rite_from_duel(session, duel, player, won)
            payload.update(rite_payload)
        except Exception:
            logger.exception("settle_pve_duel: hidden_rite resolve failed duel=%s", duel.id)
    elif duel.pve_source == "legacy_cave":
        # TEC-4 — a run da Gruta do Legado 传承洞. Vitória SEMPRE paga (pedras +
        # material regional + fragmento R5+); a ARTE única da casa sai por roll
        # + pity (Lei §12: a fonte mais rara do jogo). Derrota = a tentativa da
        # abertura foi consumida (a UI diz). Sem sparring — a gruta tem loot
        # próprio.
        try:
            from core.legacy_cave_engine import resolve_legacy_cave_from_duel
            cave_payload = await resolve_legacy_cave_from_duel(session, duel, player, won)
            payload.update(cave_payload)
        except Exception:
            logger.exception("settle_pve_duel: legacy_cave resolve failed duel=%s", duel.id)
    elif duel.pve_source == "heart_demon":
        # TEC-5 — o Rito do Coração-Demônio 心魔. Vencer NÃO decide: abre a
        # ESCOLHA (⚔️ atravessar / 🧘 reafirmar — Lei §1, 2 botões). Perder ⇒ o
        # Coração morde soul_strength e o cooldown corre. Sem loot: é rito.
        try:
            from core.forbidden_path_engine import resolve_heart_demon_from_duel
            hd_payload = await resolve_heart_demon_from_duel(session, duel, player, won)
            payload.update(hd_payload)
        except Exception:
            logger.exception("settle_pve_duel: heart_demon resolve failed duel=%s", duel.id)
    elif duel.pve_source == "npc_cultivator":
        # Onda 3 — a persistent NPC-cultivator challenge. A win grants a modest
        # reward and OFFERS a spare/execute moral choice (the karma is applied
        # later by the explicit post-duel choice — apply_combat_moral_choice —
        # not here, since the settle hook can't know the player's decision).
        try:
            from core.npc_cultivator_engine import resolve_npc_cultivator_from_duel
            npc_cult_payload = await resolve_npc_cultivator_from_duel(session, duel, player, won)
            payload.update(npc_cult_payload)
        except Exception:
            logger.exception("settle_pve_duel: npc_cultivator resolve failed duel=%s", duel.id)
    elif duel.pve_source == "exploration":
        # Onda 5 — a Reinos Exploráveis Hidden-Monster duel. A win grants 5-10×
        # the node loot into the expedition bag (+ advances depth + offers the
        # spare/execute moral fork); a loss (died deep) loses 90% of the bag.
        try:
            from core.exploration_engine import resolve_exploration_from_duel
            expl_payload = await resolve_exploration_from_duel(session, duel, player, won)
            payload.update(expl_payload)
        except Exception:
            logger.exception("settle_pve_duel: exploration resolve failed duel=%s", duel.id)
    elif duel.pve_source == "jianghu_ambush":
        # MV-8 — a emboscada do jiānghú. O jogador ESCOLHEU lutar (⚔️); os
        # outros dois ramos (💰/🏃) nunca chegam aqui porque não criam duelo.
        # Sem este ramo a fonte cairia em `unknown_source`: recompensa MORTA e
        # silenciosa, o defeito que o próprio docstring de start_duel_pve avisa.
        try:
            from core.jianghu_engine import resolve_ambush_from_duel
            amb_payload = await resolve_ambush_from_duel(session, duel, player, won)
            payload.update(amb_payload)
        except Exception:
            logger.exception("settle_pve_duel: jianghu ambush resolve failed duel=%s", duel.id)
    else:
        logger.warning("settle_pve_duel: unknown pve_source=%s duel=%s",
                       duel.pve_source, duel.id)
        _stamp_settled(duel, kind="unknown_source")
        return False

    # MV-2 — Tiandao: uma vitória PvE conta para a Maré de Bestas do continente
    # onde o jogador está (gated `tiandao_director` + fail-safe; NUNCA altera o
    # settle — padrão do hook de insight do Sprint 7).
    if won:
        try:
            from core.tiandao_engine import record_pve_victory
            _wev = await record_pve_victory(session, player)
            if _wev:
                payload["world_event"] = _wev
        except Exception:
            logger.exception("settle_pve_duel: tiandao hook failed duel=%s", duel.id)

    # TEC-5 — key CONDICIONAL no payload do settle (o chat lê daqui; o mini lê
    # o marker `fpd_cost` do action_log). OFF/sem uso ⇒ payload byte-idêntico.
    if forbidden_cost:
        payload["forbidden_cost"] = forbidden_cost

    _stamp_settled(duel, kind=duel.pve_source, payload=payload)
    return True
