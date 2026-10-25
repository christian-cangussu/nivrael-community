import logging
import random
from datetime import datetime, timezone

from sqlalchemy import select
from config import (
    SPIRIT_ROOT_NAMES,
    SPIRIT_ROOT_WEIGHTS,
    SPIRIT_ROOTS,
    BASE_CB_RATE,
    REALM_MULTIPLIERS,
    PURITY_BASE,
    ONLINE_FACTOR,
    OFFLINE_FACTOR,
    OFFLINE_CAP_SECONDS,
    TICK_INTERVAL_SECONDS,
    REALM_NAMES,
    REALM_EMOJIS,
    SUB_LAYERS_PER_REALM,
    ENCHANT_EFFECTS,
    TRIBULATION_START_REALM,
    REALM_MILESTONES,
    MEDITATION_QI_MULT,
    MEDITATION_TYPES,
    get_threshold,
)
from database.models import Player, PlayerArtifact, Tribulation, PlayerTechnique, TechniqueCatalog
from core.foundation_engine import get_foundation_multiplier
from core.golden_core_engine import get_core_multiplier

logger = logging.getLogger(__name__)


async def get_active_technique_bonuses(session, player_id: int) -> dict:
    """Fetch active meditation and interior technique bonuses for a player."""
    from core.combat_engine import MASTERY_STAGES, get_grade_info

    stmt = (
        select(
            TechniqueCatalog.tech_type,
            TechniqueCatalog.effect_type,
            TechniqueCatalog.effect_value,
            PlayerTechnique.mastery_level,
            PlayerTechnique.grade,
        )
        .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
        .where(
            PlayerTechnique.player_id == player_id,
            PlayerTechnique.is_active_combat == True,
            TechniqueCatalog.tech_type.in_(("meditation", "interior")),
        )
    )
    rows = (await session.execute(stmt)).all()

    bonuses = {
        "cb_boost": 0.0,
        "qi_regen_boost": 0.0,
        "hp_regen_boost": 0.0,
        "soul_boost": 0.0,
        "perception_boost": 0.0,
        "luck_boost": 0.0,
    }
    for tech_type, effect_type, effect_value, mastery_level, grade in rows:
        mastery_mult = MASTERY_STAGES.get(mastery_level, MASTERY_STAGES[1])["mult"]
        grade_mult = get_grade_info(grade)["mult"]
        total = effect_value * mastery_mult * grade_mult
        if effect_type in bonuses:
            bonuses[effect_type] += total

    return bonuses

def get_player_equipment_stats(artifacts: list[PlayerArtifact]) -> dict:
    total_bonus = {
        "cb_mult": 1.0,
        "bp_mult": 1.0,
        "luck_mult": 1.0,
        "soul_mult": 1.0,
        "bp_flat": 0,
        "qi_flat": 0,
        "soul_flat": 0,
        "luck_flat": 0,
        "perception_flat": 0,
        # v16.7 — dedicated defensive stat (feeds the proportional Jing mitigation
        # wall in core/combat_model). DEFAULT 0; defensive artifacts get it via
        # custom_stats JSONB (migration-free). No double-dip with offensive bp.
        "armor_rating": 0,
    }

    for art in artifacts:
        if not art.is_equipped:
            continue

        stats = art.custom_stats or {}
        total_bonus["bp_flat"] += stats.get("battle_power", 0)
        total_bonus["qi_flat"] += stats.get("qi_capacity", 0)
        total_bonus["soul_flat"] += stats.get("soul_strength", 0)
        total_bonus["luck_flat"] += stats.get("luck", 0)
        total_bonus["perception_flat"] += stats.get("perception", 0)
        total_bonus["armor_rating"] += stats.get("armor_rating", 0)
        
        if art.enchant_rune:
            effect = ENCHANT_EFFECTS.get(art.enchant_rune)
            if effect:
                if art.enchant_rune == "cb_boost": total_bonus["cb_mult"] *= effect["mult"]
                elif art.enchant_rune == "bp_boost": total_bonus["bp_mult"] *= effect["mult"]
                elif art.enchant_rune == "luck_boost": total_bonus["luck_mult"] *= effect["mult"]
                elif art.enchant_rune == "soul_boost": total_bonus["soul_mult"] *= effect["mult"]
            
    return total_bonus

async def get_effective_qi_capacity(session, player, equip_stats: dict = None) -> float:
    """Canonical effective qi capacity: (raw + equipped artifact qi_flat) ×
    body-tempering mult — the same value the regen tick fills qi up to and
    /status + the mini-app header display. Any "is qi full?" gate MUST compare
    against this, never raw player.qi_capacity: regen fills qi PAST the raw
    cap for tempered/equipped players, so a raw-cap gate reports "full"
    forever (mini-app header 2026-05-10; cavern claim 2026-06-11)."""
    eq = equip_stats
    if eq is None and session is not None:
        try:
            arts = (await session.execute(
                select(PlayerArtifact).where(
                    PlayerArtifact.player_id == player.telegram_id,
                    PlayerArtifact.is_equipped == True,
                )
            )).scalars().all()
            eq = get_player_equipment_stats(arts) if arts else None
        except Exception:
            # Degrade to raw×tempering rather than crash the tick/claim — but
            # LOUDLY: the old inline tick code propagated this to the
            # scheduler's error alerting, so a silent swallow would hide a
            # persistent DB problem (adversarial-review finding).
            logger.warning(
                "get_effective_qi_capacity: artifact stats failed for player=%s; using raw cap",
                getattr(player, "telegram_id", "?"), exc_info=True)
            eq = None
    qi_flat = (eq or {}).get("qi_flat", 0)
    from core.body_tempering_engine import get_tempering_multiplier
    mult = get_tempering_multiplier(getattr(player, "body_tempering_level", 0) or 0)
    return (float(player.qi_capacity or 100) + qi_flat) * mult

def calculate_total_stats(player: Player, equip_stats: dict = None, companion_bonus: dict = None, dao_bonuses: dict = None, interior_bonuses: dict = None, achievement_bp_mult: float = 1.0) -> dict:
    if not equip_stats:
        equip_stats = {
            "cb_mult": 1.0, "bp_mult": 1.0, "luck_mult": 1.0, "soul_mult": 1.0,
            "bp_flat": 0, "qi_flat": 0, "soul_flat": 0, "luck_flat": 0, "perception_flat": 0
        }
    if not companion_bonus:
        companion_bonus = {"cb_mult": 1.0, "bp_mult": 1.0, "soul_mult": 1.0, "luck_mult": 1.0, "hp_mult": 1.0, "evasion_mult": 1.0, "qi_recovery_mult": 1.0, "perception_mult": 1.0}
    if not dao_bonuses:
        dao_bonuses = {"cb_mult": 1.0, "bp_mult": 1.0, "all_stats_mult": 1.0}
    if not interior_bonuses:
        interior_bonuses = {"soul_boost": 0.0, "perception_boost": 0.0, "luck_boost": 0.0}

    all_mult = dao_bonuses.get("all_stats_mult", 1.0)

    # COMPAT: beta players may have None quality — use defaults for calc without mutating player
    fq = player.foundation_quality if player.foundation_quality else ("medium" if player.realm >= 2 else None)
    cq = player.core_quality if player.core_quality else ("normal" if player.realm >= 3 else None)
    foundation_mult = get_foundation_multiplier(fq)
    core_mult = get_core_multiplier(cq)

    from core.body_tempering_engine import get_tempering_multiplier
    tempering_mult = get_tempering_multiplier(getattr(player, "body_tempering_level", 0))

    stat_mult = foundation_mult * core_mult

    # Interior technique passive bonuses (F-8)
    soul_interior = 1.0 + interior_bonuses.get("soul_boost", 0.0)
    percep_interior = 1.0 + interior_bonuses.get("perception_boost", 0.0)
    luck_interior = 1.0 + interior_bonuses.get("luck_boost", 0.0)

    # achievement_bp_mult (Wave 3, gated): fold the conquista "+X% BP" into the bp
    # SLICE only (not soul/qi) so the shown Poder de Combate matches what bites the
    # fight (build_fighter_data applies the same bp_mult to the CLEAN combat bp).
    # Default 1.0 → every non-display caller (incl. the combat path) is unchanged.
    bp = (player.battle_power + equip_stats["bp_flat"]) * equip_stats["bp_mult"] * companion_bonus.get("bp_mult", 1.0) * dao_bonuses.get("bp_mult", 1.0) * all_mult * stat_mult * tempering_mult * achievement_bp_mult
    soul = (player.soul_strength + equip_stats["soul_flat"]) * equip_stats["soul_mult"] * companion_bonus.get("soul_mult", 1.0) * all_mult * stat_mult * soul_interior
    luck = (player.luck + equip_stats["luck_flat"]) * equip_stats["luck_mult"] * companion_bonus.get("luck_mult", 1.0) * all_mult * stat_mult * luck_interior
    qi_cap = (player.qi_capacity + equip_stats["qi_flat"]) * tempering_mult
    percep = (player.perception + equip_stats["perception_flat"]) * all_mult * stat_mult * percep_interior * companion_bonus.get("perception_mult", 1.0)
    
    realm_mult = REALM_MULTIPLIERS[min(player.realm, len(REALM_MULTIPLIERS) - 1)]
    total_bp = (qi_cap * 0.3 + soul * 0.4 + bp * 0.3) * realm_mult
    
    return {
        "battle_power": int(bp),
        "soul_strength": int(soul),
        "luck": int(luck),
        "qi_capacity": qi_cap,
        "perception": int(percep),
        "total_battle_power": int(total_bp)
    }

def display_combat_power(total_battle_power, player) -> int:
    """Progressão Visível — the ONE visible "Poder de Combate" anchor (o número que
    SEMPRE sobe em todo upgrade). Aggregates the offense/attribute summary
    ``total_battle_power`` (which already folds equipment + Dao + foundation/core +
    companion + the realm curve) with the body's durability multiplier
    (``body_durability_mult`` — the Mortal band R0-R6 / Nine Transformations R7+),
    the single real combat factor ``total_battle_power`` omits.

    HONEST (Lei §2): the body factor is applied EXACTLY ONCE so the number never
    lies about magnitude:
      • R7+ (Nine Transformations): ``calculate_total_stats`` ALREADY folds
        get_tempering_multiplier(body_tempering_level) into bp + qi_cap, so
        ``total_battle_power`` already carries the body benefit → return it as-is
        (multiplying by body_durability_mult again would SQUARE the tempering mult).
      • R0-R6 (Mortal band): ``total_battle_power`` carries NO body factor
        (body_tempering_level=0 → tempering_mult=1.0; the Mortal band lives only in
        body_durability_mult), so fold the Mortal durability in ONCE — this is the
        whole point of early game: tempering the Carne visibly moves the headline.
    Monotonic: realm-up, equip, pill (qi_cap/soul), and body tempering each move it
    UP. DISPLAY-ONLY — no combat path reads this.

    MV-4 (review fix): the MERIDIAN durability bonus is additive on
    body_durability_mult and is NOT baked into calculate_total_stats, so the
    R7+ branch must fold exactly that increment (1 + bonus) or an R7+ channel
    open would raise real HP while the headline froze (invisible gain — the
    owner's #1 rule). OFF worlds: bonus = 0.0 → factor 1.0 → byte-identical."""
    from core.body_tempering_engine import body_durability_mult, MIN_REALM_REQUIRED
    total = float(total_battle_power or 0)
    try:
        if int(getattr(player, "realm", 0) or 0) >= MIN_REALM_REQUIRED:
            # R7+ — tempering already baked into total_battle_power (avoid
            # double-count); fold ONLY the meridian increment on top.
            from core.meridian_engine import meridian_durability_bonus
            return int(round(total * (1.0 + float(meridian_durability_bonus(player)))))
        # R0-R6 — Mortal-band durability folded in exactly once (meridians ride
        # inside body_durability_mult here, so they move the headline too).
        return int(round(total * float(body_durability_mult(player))))
    except Exception:
        return int(total)

def qi_regen_stack_mult(buffs) -> float:
    """D-2 — the CANONICAL qi-regen pill/Formação stack: top-3 live
    ``qi_regen_boost`` rows by value, diminishing factors [1.0, 0.5, 0.25],
    multiplicative. Single source of truth for the regen tick, chat /status
    and the mini-app qi chip — the display drifted from the engine twice
    (v14.13b chat; 2026-06-11 mini-app chip showed only the meditation mult,
    owner: "as pílulas/formação não informam")."""
    mult = 1.0
    rows = sorted(
        [b for b in (buffs or []) if getattr(b, "buff_type", None) == "qi_regen_boost"],
        key=lambda b: float(getattr(b, "buff_value", 1.0) or 1.0),
        reverse=True,
    )
    factors = [1.0, 0.5, 0.25]
    for i, b in enumerate(rows[:3]):
        mult *= 1.0 + (float(b.buff_value or 1.0) - 1.0) * factors[i]
    return mult


def roll_spirit_root() -> int:
    result = random.choices(range(len(SPIRIT_ROOT_NAMES)), weights=SPIRIT_ROOT_WEIGHTS, k=1)[0]
    return result

def get_spirit_root_name(index: int) -> str:
    if index >= len(SPIRIT_ROOT_NAMES):
        return SPIRIT_ROOT_NAMES[-1] # Fallback to the lowest rarity available
    return SPIRIT_ROOT_NAMES[index]

def get_spirit_root_info(index: int) -> dict:
    name = get_spirit_root_name(index)
    return SPIRIT_ROOTS[name]

def get_spirit_root_multiplier(index: int) -> float:
    info = get_spirit_root_info(index)
    return info["multiplier"]

def get_spirit_root_emoji(index: int) -> str:
    info = get_spirit_root_info(index)
    return info["emoji"]

def calculate_cb_per_tick(player: Player, is_online: bool = True, buff_multiplier: float = 1.0, equip_stats: dict = None, sect_mult: float = 1.0, companion_cb_mult: float = 1.0, dao_cb_mult: float = 1.0, partner_cb_mult: float = 1.0, achievement_cb_mult: float = 1.0) -> float:
    realm_mult = REALM_MULTIPLIERS[min(player.realm, len(REALM_MULTIPLIERS) - 1)]
    root_mult = get_spirit_root_multiplier(player.spirit_root)
    purity_mult = PURITY_BASE
    meditation_mult = player.meditation_multiplier if player.is_meditating else 1.0
    online_factor = ONLINE_FACTOR if is_online else OFFLINE_FACTOR

    art_cb_mult = equip_stats["cb_mult"] if equip_stats else 1.0

    prestige_mult = 1.0 + (player.prestige_level * 0.01)

    # COMPAT: beta players may have None quality — use defaults for calc without mutating player
    fq = player.foundation_quality if player.foundation_quality else ("medium" if player.realm >= 2 else None)
    cq = player.core_quality if player.core_quality else ("normal" if player.realm >= 3 else None)
    foundation_mult = get_foundation_multiplier(fq)
    core_mult = get_core_multiplier(cq)

    # Per-server balance (Sistema Multi-Servidor — Fase 2): a secondary world can
    # cultivate SLOWER (owner: "o jogo tem que demorar mesmo") without touching
    # main. Reads the active world's cultivation_speed via the current_world
    # ContextVar; main / unresolved → 1.0 (byte-identical to before). Defensive:
    # a balance-lookup failure must NEVER break cultivation, so it falls back to 1.0.
    try:
        from database.db import get_world_balance
        world_cb_mult = float(get_world_balance().get("cultivation_speed", 1.0) or 1.0)
    except Exception:
        world_cb_mult = 1.0

    # achievement_cb_mult (Wave 3, gated): the "+X% cb" the conquistas UI promises
    # now ACTUALLY accelerates cultivation. 1.0 for every legacy caller (and any
    # world with combate_unificado OFF) → byte-identical. Cultivation SPEED only —
    # never damage ("de acordo com o que diz").
    return BASE_CB_RATE * realm_mult * root_mult * purity_mult * meditation_mult * online_factor * buff_multiplier * art_cb_mult * sect_mult * companion_cb_mult * dao_cb_mult * prestige_mult * partner_cb_mult * foundation_mult * core_mult * world_cb_mult * achievement_cb_mult

def calculate_cb_per_hour(player: Player, is_online: bool = True, buff_multiplier: float = 1.0, equip_stats: dict = None, sect_mult: float = 1.0, companion_cb_mult: float = 1.0, dao_cb_mult: float = 1.0, partner_cb_mult: float = 1.0, achievement_cb_mult: float = 1.0) -> float:
    ticks_per_hour = 3600 / TICK_INTERVAL_SECONDS
    return calculate_cb_per_tick(player, is_online, buff_multiplier, equip_stats, sect_mult, companion_cb_mult, dao_cb_mult, partner_cb_mult, achievement_cb_mult) * ticks_per_hour

def try_finalize_meditation(player: Player) -> dict | None:
    """v15.1.5 hotfix — extracted from process_tick so any caller can lazily
    finalize meditation (mini-app endpoint poll, scheduler sweep, etc.).

    Returns:
        None — meditation was not finalized (still active or none in progress)
        {ended_type, ce_gain, hp_recovered} — meditation just finalized; caller
            owns the session so it can commit + fire bell notification.

    Idempotent: mutates `player.is_meditating=False` and clears the meditation
    fields. A second call returns None.
    """
    if not (player.is_meditating and player.meditation_end):
        return None
    now = datetime.now(timezone.utc)
    if now < player.meditation_end:
        return None

    HP_REGEN_RATES_END = {"light": 0.01, "deep": 0.05, "void": 0.10}
    _end_rate = HP_REGEN_RATES_END.get(player.meditation_type, 0)
    _med_hp_recovered = 0
    if _end_rate > 0:
        from core.combat_engine import get_max_hp
        _end_max_hp = get_max_hp(player)
        _end_duration = MEDITATION_TYPES.get(player.meditation_type, {}).get("duration_minutes", 0)
        _med_hp_recovered = min(_end_rate * _end_max_hp * _end_duration, _end_max_hp)
    _med_ended_type = player.meditation_type

    player.is_meditating = False
    player.meditation_type = None
    player.meditation_end = None
    player.meditation_multiplier = 1.0
    _med_ce = 0
    if player.realm == 2:
        # +15 por sessão de meditação (antes: +2).
        # Meta: 300 essence em ~5 dias com 4 sessões/dia → 4*15=60/dia → 300/60=5 dias ✅
        from core.golden_core_engine import add_core_essence
        _med_ce = add_core_essence(player, 15)

    return {
        "ended_type": _med_ended_type,
        "ce_gain": _med_ce,
        "hp_recovered": _med_hp_recovered,
    }


def meditation_credit_minutes(med_type: str | None, med_end: datetime | None,
                              *, now: datetime | None = None) -> int:
    """Quantos minutos de `cultivate` esta meditação MERECE. Pura, sem I/O.

    A verdade ÚNICA do crédito (report do [jogador], 2026-08-06: *"fiz cultivo do Dao
    por mais tempo que o pedido e a missão não completou"*). O código já
    declarava a regra certa — *"QUEM FINALIZA credita"* (fix de 2026-07-21) —
    mas só a aplicava nos TRÊS finalizadores automáticos (tick de 30s, sweep de
    60s, poll do mini-app). Os SETE caminhos que terminam a sessão À MÃO
    limpavam `is_meditating`/`meditation_end` e o crédito evaporava: uma vez
    limpos os campos, `try_finalize_meditation` nunca mais vê aquela sessão.
    O pior deles era `handlers/cultivation.py` "auto-end expired meditation if
    tick didn't catch it" — dispara EXATAMENTE quando a meditação completou.

    Regra (idêntica à do karma de `void`, decisão SEC 2026-06-01 / v16.6):
    só credita a sessão que **genuinamente terminou** (`now >= meditation_end`).
    Um start-then-stop imediato continua a valer ZERO — o farm de custo zero
    que a v16.6 fechou permanece fechado.

    Devolve 0 quando não há crédito a dar (sem tipo, sem fim, ainda a correr,
    tipo desconhecido) — o chamador nunca precisa de saber porquê.
    """
    try:
        if not med_type or med_end is None:
            return 0
        now = now or datetime.now(timezone.utc)
        end = med_end if med_end.tzinfo else med_end.replace(tzinfo=timezone.utc)
        if now < end:
            return 0   # ainda a correr — cancelar cedo não paga (anti-farm)
        from config import MEDITATION_TYPES as _MT, DAO_MEDITATION_TYPES as _DMT
        info = _MT.get(med_type) or _DMT.get(med_type) or {}
        return max(0, int(info.get("duration_minutes", 0) or 0))
    except Exception:
        logger.exception("meditation_credit_minutes failed type=%s", med_type)
        return 0


async def credit_meditation_if_earned(session, player, med_type: str | None,
                                      med_end: datetime | None,
                                      *, now: datetime | None = None) -> int:
    """Credita `cultivate` por uma sessão terminada À MÃO. Devolve os minutos.

    Chamado pelos caminhos que limpam o estado da meditação sem passar por
    `try_finalize_meditation`. Idempotência: o chamador limpa os campos LOGO a
    seguir (a sessão deixa de existir), portanto cada sessão paga uma vez só —
    e nunca duas, porque quem passa por aqui já não passa pelo finalizador.

    SAVEPOINT no crédito (hotfix 2026-07-21b, mesmo contrato dos outros três):
    o flush acontece aqui dentro; um erro de DB faz rollback SÓ do crédito e
    nunca envenena a transação do chamador. Nunca levanta.
    """
    try:
        minutes = meditation_credit_minutes(med_type, med_end, now=now)
        if minutes <= 0 or session is None or player is None:
            return 0
        from core.quest_engine import track_quest
        async with session.begin_nested():
            await track_quest(session, player.telegram_id, "cultivate", minutes)
        # 内功 (report do [jogador] 2026-08-11): os caminhos MANUAIS também treinam as
        # artes internas — senão parar à mão uma meditação cumprida voltaria a
        # comer progresso, que é exatamente o defeito que este helper existe para
        # não repetir.
        from core.technique_engine import credit_passive_mastery
        await credit_passive_mastery(session, player.telegram_id, minutes)
        # ⚠️ O finalizador canónico (`try_finalize_meditation`) não credita só a
        # quest: no realm 2 dá +15 de Essência de Núcleo por sessão, e essa é a
        # moeda que destranca o Núcleo Dourado. A 1ª versão deste helper
        # replicava só metade do que "finalizar" significa — os 7 caminhos
        # manuais passavam a creditar a quest e a continuar a comer a essência,
        # que é o recurso mais escasso daquele realm. Mesma condição: só sessão
        # genuinamente terminada (já garantida por `minutes > 0`).
        try:
            if int(getattr(player, "realm", 0) or 0) == 2:
                from core.golden_core_engine import add_core_essence
                add_core_essence(player, 15)
        except Exception:
            logger.exception("core essence on manual meditation finalize failed (player=%s)",
                             getattr(player, "telegram_id", None))
        return minutes
    except Exception:
        logger.exception("credit_meditation_if_earned failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return 0


async def process_tick(player: Player, is_online: bool = True, equip_stats: dict = None, session=None,
                       region_cb_mult: float = 1.0) -> dict:
    # MV-3 — `region_cb_mult`: densidade de qi do continente (Estados Regionais,
    # festival = +5% ALI). Multiplica APENAS o ganho de CB (padrão
    # event_cb_mult) — NUNCA o qi_cap nem a fórmula de regen do qi (Lei §13).
    # Default 1.0 = byte-idêntico; o scheduler passa o valor prefetchado
    # (1 query/mundo/tick, gated `estados_regionais`).
    now = datetime.now(timezone.utc)
    _med_ce = 0
    _med_ended_type = None
    _med_hp_recovered = 0

    med_fin = try_finalize_meditation(player)
    if med_fin is not None:
        _med_ended_type = med_fin["ended_type"]
        _med_ce = med_fin["ce_gain"]
        _med_hp_recovered = med_fin["hp_recovered"]
        # Fix 2026-07-21 (report do jogador: "O Passo do Peregrino não progride
        # cultivando o Dao celestial"): ESTE finalizador — o tick de 30s — quase
        # sempre vence a corrida contra o sweep (60s) e o poll do mini, e era o
        # ÚNICO que não creditava o 'cultivate'. Meditações de Dao/celestial
        # (sem crédito no start, decisão SEC v16.6) nunca creditavam NADA para
        # jogador ativo. Regra agora: QUEM FINALIZA credita (exactly-once —
        # try_finalize_meditation é idempotente, só UM caller vê med_fin).
        #
        # Hotfix 2026-07-21b (alerta cultivation_tick DBAPIError em prod): o
        # crédito roda num SAVEPOINT — sem ele, o UPDATE do progresso só é
        # emitido no COMMIT (fora do try) e um erro de DB lá (ex.: deadlock
        # com um claim concorrente: tick segura Player→escreve player_quests,
        # claim segura player_quests→escreve Player) derrubava o tick INTEIRO
        # do jogador. Com o savepoint, o flush acontece AQUI dentro; falhou →
        # rollback SÓ do crédito (perde-se 1 crédito raro, o tick e o finalize
        # seguem — self-healing na próxima meditação). Padrão notify().
        if session is not None and _med_ended_type:
            try:
                from config import MEDITATION_TYPES as _MT, DAO_MEDITATION_TYPES as _DMT
                _fin_mi = _MT.get(_med_ended_type) or _DMT.get(_med_ended_type) or {}
                _fin_dur = int(_fin_mi.get("duration_minutes", 0))
                if _fin_dur > 0:
                    from core.quest_engine import track_quest as _fin_track
                    async with session.begin_nested():
                        await _fin_track(session, player.telegram_id, "cultivate", _fin_dur)
                    # 内功 (report do [jogador] 2026-08-11): a mesma sessão que credita
                    # a diária treina as artes internas ATIVAS. Quem finaliza credita.
                    from core.technique_engine import credit_passive_mastery
                    await credit_passive_mastery(session, player.telegram_id, _fin_dur)
            except Exception:
                logger.exception("cultivate credit on tick finalize failed (player=%s)",
                                 player.telegram_id)

    sect_mult = 1.0
    spirit_vein_mult = 1.0
    if session:
        from core.sect_engine import get_sect_bonuses
        bonuses = await get_sect_bonuses(session, player.telegram_id)
        sect_mult = bonuses["training_mult"]
        spirit_vein_mult = bonuses["spirit_vein_mult"]
        # v14.2 D-3a — Sect Master CB +5% personal bonus. Compounds with the
        # +10% production already baked into training_mult for masters. Authentic
        # Wuxia: leadership tempers the cultivator.
        sect_mult *= bonuses.get("master_cb_mult", 1.0)

    companion_cb_mult = 1.0
    companion_qi_regen_mult = 1.0
    if session:
        from core.beast_engine import get_companion_beast, get_companion_bonuses
        comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
        comp_bonus = get_companion_bonuses(comp_beast, comp_catalog)
        companion_cb_mult = comp_bonus.get("cb_mult", 1.0)
        # [jogador] 2026-06-12: Bamboo Panda's "+N% Qi recovery" was DECORATIVE —
        # produced by get_companion_bonuses, consumed by NOTHING. Wire it here
        # (the same comp_bonus fetch the CB mult already pays for).
        companion_qi_regen_mult = comp_bonus.get("qi_recovery_mult", 1.0)

    event_cb_mult = 1.0
    event_qi_regen_mult = 1.0
    if session:
        from handlers.events import get_event_multipliers
        event_mults = await get_event_multipliers(session)
        event_cb_mult = event_mults.get("cb_mult", 1.0)
        event_qi_regen_mult = event_mults.get("qi_regen_mult", 1.0)

    partner_cb_mult = 1.0
    if session:
        from core.partner_engine import get_partner_cb_mult
        partner_cb_mult = await get_partner_cb_mult(session, player.telegram_id)

    dao_cb_mult = 1.0
    dao_hp_regen = 0.0
    if session:
        from core.dao_engine import get_player_dao_bonuses
        dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, player.realm)
        dao_cb_mult = dao_bonuses.get("cb_mult", 1.0)
        # Wave 3 — the Dao "HP regen" bonus (Path of Water/Healing/Vitality/Body)
        # was produced + displayed but consumed by NOTHING. Capture it here to feed
        # the OUT-OF-COMBAT recovery below (gated).
        dao_hp_regen = float(dao_bonuses.get("hp_regen", 0.0) or 0.0)

    # achievement_cb_mult (Wave 3, gated combate_unificado): the conquistas'
    # "+X% cb" now accelerates cultivation for real. Gated wrapper → 1.0 (and ZERO
    # query) when the flag is OFF, so `main` stays byte-identical and cost-free.
    achievement_cb_mult = 1.0
    if session:
        from core.achievement_engine import get_gated_achievement_multipliers
        _ach_m = await get_gated_achievement_multipliers(session, player.telegram_id)
        achievement_cb_mult = float(_ach_m.get("cb_mult", 1.0) or 1.0)

    cb_buff_mult = 1.0
    qi_regen_pill_mult = 1.0
    if session:
        from core.alchemy_engine import get_active_buffs
        _tick_buffs = await get_active_buffs(session, player.telegram_id)
        for _b in _tick_buffs:
            if _b.buff_type == "cb_boost":
                cb_buff_mult *= _b.buff_value
        # NOTE: perception_boost pill buffs (e.g. Soul Clarity Pill) must NOT
        # boost cultivation rate — they are applied on perception only at the
        # tribulation/dao-fragment sites that read total perception.

        # D-2 (DESIGN_DECISIONS_v14): Qi regen pills suite — 6+ players asked.
        # Stack até 3 simultâneas com diminishing returns (1.0/0.5/0.25), o
        # maior primeiro; >3 = ignored (anti-degenerate-stacking). A conta vive
        # em qi_regen_stack_mult (partilhada com /status e o chip do mini-app).
        qi_regen_pill_mult = qi_regen_stack_mult(_tick_buffs)

    # F-8: Fetch meditation + interior technique bonuses
    med_tech_cb = 0.0
    med_tech_qi = 0.0
    med_tech_hp = 0.0
    if session:
        tech_bonuses = await get_active_technique_bonuses(session, player.telegram_id)
        med_tech_cb = tech_bonuses.get("cb_boost", 0.0)
        med_tech_qi = tech_bonuses.get("qi_regen_boost", 0.0)
        med_tech_hp = tech_bonuses.get("hp_regen_boost", 0.0)

    cb_gained = calculate_cb_per_tick(player, is_online, buff_multiplier=cb_buff_mult, equip_stats=equip_stats, sect_mult=sect_mult, companion_cb_mult=companion_cb_mult, dao_cb_mult=dao_cb_mult, partner_cb_mult=partner_cb_mult, achievement_cb_mult=achievement_cb_mult) * event_cb_mult
    # MV-3 — densidade de qi regional (festival): multiplicativo pequeno no CB,
    # ao lado do event_cb_mult. 1.0 (default/flag OFF) = byte-idêntico.
    if region_cb_mult and region_cb_mult != 1.0:
        cb_gained *= float(region_cb_mult)
    # F-8: Meditation technique CB boost (only while meditating)
    if player.is_meditating and med_tech_cb > 0:
        cb_gained *= (1.0 + med_tech_cb)
    player.cultivation_base += cb_gained

    import random
    # E ([jogador] 2026-06-16): the old `1 if random()<0.1*mult` saturated at 1/tick
    # once 0.1*mult>=1 (Spirit Vein lvl ~180+), so the displayed "+2250%" delivered
    # nothing online above that level while the OFFLINE path scaled linearly. Use a
    # fractional Bernoulli so the per-tick expected value equals 0.1*mult exactly,
    # matching offline (process_offline_gains: int(round(0.1*mult*ticks))). The Veia
    # Espiritual now actually pays its disclosed bonus online (economy/stones only —
    # no combat ceiling touched, Lei §5). lvl450 → ~2.35/tick (2 + 0.35 chance).
    expected_stones = 0.1 * spirit_vein_mult
    base_stones = int(expected_stones)
    stone_gain = base_stones + (1 if random.random() < (expected_stones - base_stones) else 0)
    player.spirit_stones += stone_gain

    # Qi regeneration: 1 point per 60 seconds (boosted by Spirit Tide event + meditation)
    med_qi_mult = MEDITATION_QI_MULT.get(player.meditation_type, 1.0) if player.is_meditating else 1.0
    qi_regen = (TICK_INTERVAL_SECONDS / 60.0) * event_qi_regen_mult * med_qi_mult
    # F-8: Meditation technique QI regen boost
    if player.is_meditating and med_tech_qi > 0:
        qi_regen *= (1.0 + med_tech_qi)
    # D-2: Qi regen pills (Vortex/Heavenly Spring/Eternal River) stack with
    # diminishing returns — applied even when NOT meditating (pills work passively).
    qi_regen *= qi_regen_pill_mult
    # Companion qi recovery (Bamboo Panda) — passive like the pills.
    qi_regen *= companion_qi_regen_mult

    # Effective qi_capacity includes equipment + body tempering
    effective_qi_cap = player.qi_capacity
    if session:
        effective_qi_cap = await get_effective_qi_capacity(session, player, equip_stats=equip_stats)

    if player.qi < effective_qi_cap:
        player.qi = min(player.qi + qi_regen, effective_qi_cap)

    # HP regeneration per tick
    from core.combat_engine import get_max_hp, get_current_hp, restore_hp
    max_hp = get_max_hp(player)
    current_hp = get_current_hp(player)
    if current_hp < max_hp:
        # % of max_hp per minute, scaled to tick interval
        HP_REGEN_RATES = {"light": 0.01, "deep": 0.05, "void": 0.10}
        if player.is_meditating and player.meditation_type in HP_REGEN_RATES:
            regen_pct_per_min = HP_REGEN_RATES[player.meditation_type]
        else:
            regen_pct_per_min = 0.001  # 0.1% per min passive
        regen_amount = max_hp * regen_pct_per_min * (TICK_INTERVAL_SECONDS / 60.0)
        # F-8: Meditation technique HP regen boost
        if player.is_meditating and med_tech_hp > 0:
            regen_amount *= (1.0 + med_tech_hp)
        # Wave 3 (gated combate_unificado): Dao hp_regen laws now bite the
        # out-of-combat recovery — the "HP regen" the Dao UI promised finally does
        # something (Lei §1). OFF → no-op → byte-identical.
        if dao_hp_regen > 0:
            try:
                from database.db import feature_enabled_for_world
                if feature_enabled_for_world("combate_unificado"):
                    regen_amount *= (1.0 + dao_hp_regen)
            except Exception:
                pass
        restore_hp(player, regen_amount)

    breakthrough = await check_breakthrough(player, session)

    return {
        "cb_gained": cb_gained,
        "stone_gained": stone_gain,
        "breakthrough": breakthrough,
        "meditation_ce": _med_ce,
        "meditation_ended": _med_ended_type,
        "meditation_hp_recovered": _med_hp_recovered,
    }

async def check_breakthrough(player: Player, session=None, active_buffs: list = None,
                             ceremony_choice: str | None = None) -> dict | None:
    threshold = get_threshold(player.realm, player.sub_layer)

    effective_threshold = threshold
    if session:
        if active_buffs is None:
            from core.alchemy_engine import get_active_buffs
            active_buffs = await get_active_buffs(session, player.telegram_id)
            
        for _b in active_buffs:
            if _b.buff_type == "breakthrough_boost":
                effective_threshold = int(threshold / _b.buff_value)
                break

    if player.cultivation_base < effective_threshold:
        return None

    if player.realm >= len(REALM_NAMES) - 1 and player.sub_layer >= SUB_LAYERS_PER_REALM:
        player.cultivation_base = threshold
        return None

    # Check for Foundation requirement (Realm 1 -> 2 transition)
    if player.sub_layer >= SUB_LAYERS_PER_REALM and player.realm == 1:
        if player.foundation_quality is None and not player.foundation_locked:
            player.foundation_locked = True
            player.cultivation_base = threshold
            return {"foundation_required": True}
        if player.foundation_locked:
            player.cultivation_base = threshold
            return None

    # Check for Golden Core requirement (Realm 2 -> 3 transition)
    if player.sub_layer >= SUB_LAYERS_PER_REALM and player.realm == 2:
        if player.core_quality is None and not player.core_locked:
            player.core_locked = True
            player.cultivation_base = threshold
            return {"core_required": True}
        if player.core_locked:
            player.cultivation_base = threshold
            return None

    # Check for Body Tempering requirement (Realm 7 -> 8 transition)
    if player.sub_layer >= SUB_LAYERS_PER_REALM and player.realm == 7:
        bt_level = getattr(player, "body_tempering_level", 0)
        if bt_level < 3:
            player.cultivation_base = threshold
            return {"body_tempering_required": True, "current_level": bt_level, "required_level": 3}

    # Celestial Trials gate (Mahayana, sub-layers 1 / 5 / 9) — F-11
    if player.realm == 8:
        from core.celestial_engine import TRIAL_GATES as _CELESTIAL_GATES
        required_trials = _CELESTIAL_GATES.get(player.sub_layer)
        if required_trials is not None:
            passed_trials = getattr(player, "celestial_trials_passed", 0) or 0
            if passed_trials < required_trials:
                player.cultivation_base = threshold
                return {
                    "celestial_trial_required": True,
                    "trial_num": required_trials,
                    "sub_layer": player.sub_layer,
                }

    # Check for Tribulation requirement (Realm Up for Realm 4+)
    if player.sub_layer >= SUB_LAYERS_PER_REALM and player.realm >= TRIBULATION_START_REALM:
        if session:
            # Check if there is already a tribulation for this realm
            stmt = select(Tribulation).where(
                Tribulation.player_id == player.telegram_id,
                Tribulation.realm == player.realm + 1,
                Tribulation.status.in_(["pending", "in_progress"])
            ).order_by(Tribulation.started_at.desc()).limit(1)
            existing = (await session.execute(stmt)).scalars().first()
            if existing:
                return None # Already has one pending/active

            # Enforce 6h cooldown after failed tribulation
            from config import TRIBULATION_COOLDOWN_FAILURE_LIGHT
            from datetime import timedelta
            last_failed = (await session.execute(
                select(Tribulation).where(
                    Tribulation.player_id == player.telegram_id,
                    Tribulation.realm == player.realm + 1,
                    Tribulation.status == "failed"
                ).order_by(Tribulation.completed_at.desc()).limit(1)
            )).scalar_one_or_none()
            if last_failed and last_failed.completed_at:
                cooldown_end = last_failed.completed_at + timedelta(seconds=TRIBULATION_COOLDOWN_FAILURE_LIGHT)
                if datetime.now(timezone.utc) < cooldown_end:
                    # Only cap if we are exceeding the threshold, but don't delete massive amounts 
                    # if the player was already higher due to balance changes or failed tribulations.
                    # This ensures players at 100% stay at 100% but don't lose progress.
                    if player.cultivation_base > threshold:
                         # Keep their current CB if they are already over the threshold
                         # but don't let it grow further (it will be capped again in next tick if it grows)
                         pass
                    else:
                         player.cultivation_base = threshold
                    
                    remaining = (cooldown_end - datetime.now(timezone.utc)).total_seconds()
                    return {
                        "cooldown": True,
                        "remaining_seconds": max(0, remaining)
                    }

            # Create new pending tribulation
            new_trib = Tribulation(
                player_id=player.telegram_id,
                realm=player.realm + 1,
                status="pending"
            )
            session.add(new_trib)
            return {
                "tribulation_required": True,
                "target_realm": player.realm + 1
            }
        else:
            # If no session provided (shouldn't happen in tick), just return that it's required
            return {"tribulation_required": True, "target_realm": player.realm + 1}

    # Sprint 8 — Cerimónia-Semente (Breakthrough Trials). The early realm-up becomes a
    # CHOICE moment: Consolidar (safe) vs Forçar (gamble; odds worsened by the body-anomaly
    # gap, BT-3). It BLOCKS like the Foundation/Core gates above until the player chooses
    # (the resolve endpoint re-calls with ceremony_choice set). The Foundation gate
    # (realm==1) and Core gate (realm==2) already `return` above, so this naturally fires
    # at R0→R1 and R3→R4. Server-gated by `breakthrough_trials` (OFF on main → never fires
    # → byte-identical). Lei §1: Consolidar always advances, so the player is never stuck.
    if (ceremony_choice is None
            and player.sub_layer >= SUB_LAYERS_PER_REALM):
        from core.breakthrough_trials_engine import (
            BT_CEREMONY_MAX_REALM, bt_ceremony_on, project_ceremony,
        )
        if player.realm < BT_CEREMONY_MAX_REALM and bt_ceremony_on():
            player.cultivation_base = threshold
            return {"ceremony_required": True, **project_ceremony(player)}

    player.cultivation_base = max(0.0, player.cultivation_base - threshold)

    old_realm = player.realm
    old_sub = player.sub_layer

    if player.sub_layer >= SUB_LAYERS_PER_REALM:
        if player.realm < len(REALM_NAMES) - 1:
            player.realm += 1
            player.sub_layer = 1
            # NOVO: Restaurar 100% do qi ao avançar de realm (qi purificado pela
            # transformação). max(): nunca REBAIXAR — jogadores temperados/equipados
            # têm cap efetivo > raw e viam o Qi CAIR ao subir de reino ([jogador] 06/07).
            player.qi = max(player.qi, player.qi_capacity)
            _apply_realm_up_bonus(player)
            if session:
                from core.alchemy_engine import reset_medicine_resistance
                await reset_medicine_resistance(session, player.telegram_id)
            # D5 (v16.6) first-law grant lives in the tribulation-SUCCESS paths
            # (handlers/tribulation.py + webserver trib handlers), NOT here — the
            # 4→5 breakthrough always routes through Heavenly Tribulation
            # (TRIBULATION_START_REALM=4), so this plain branch never reaches realm 5.
        else:
            player.cultivation_base += threshold
            return None
    else:
        player.sub_layer += 1
        # NOVO: Restaurar 50% do qi ao avançar sub-layer (precisa estabilizar)
        player.qi = max(player.qi, int(player.qi_capacity * 0.5))
        # C-5: each Mahayana sub-layer breakthrough grants Celestial Essence
        # to keep body tempering math achievable (8 sub-breakthroughs = +160).
        if player.realm == 8:
            player.celestial_essence = (player.celestial_essence or 0) + 20

    realm_up = player.realm != old_realm
    result = {
        "old_realm": old_realm,
        "old_sub": old_sub,
        "new_realm": player.realm,
        "new_sub": player.sub_layer,
        "realm_up": realm_up,
    }
    if realm_up:
        milestone = REALM_MILESTONES.get(player.realm, {})
        result["cinematic_key"] = milestone.get("cinematic", f"milestone_r{player.realm}")
        result["qi_bonus"] = milestone.get("bonus_qi", 0)
    return result

def _apply_realm_up_bonus(player: Player):
    bonus = 1.1 + (player.realm * 0.05)
    player.battle_power = int(player.battle_power * bonus)
    player.soul_strength = int(player.soul_strength * bonus)
    player.perception = int(player.perception * bonus)
    player.luck = int(player.luck * bonus)
    player.qi_capacity = player.qi_capacity * bonus
    milestone = REALM_MILESTONES.get(player.realm, {})
    qi_bonus = milestone.get("bonus_qi", 50)
    player.qi_capacity += qi_bonus
    # max(): nunca rebaixar o Qi de quem tem cap efetivo > raw (têmpera/equip).
    player.qi = max(player.qi, player.qi_capacity)
    player.current_hp = None  # Full HP on realm-up (NULL = full)

async def calculate_offline_progress(player: Player, equip_stats: dict = None, session=None) -> dict:
    now = datetime.now(timezone.utc)
    elapsed = (now - player.last_online).total_seconds()
    
    # Base offline cap
    max_cap_seconds = OFFLINE_CAP_SECONDS
    
    if session:
        from core.monetization import get_player_vip_level, get_vip_perks, get_active_battle_pass
        vip_lvl = await get_player_vip_level(session, player.telegram_id)
        perks = get_vip_perks(vip_lvl)
        
        cap_hours = perks["offline_cap_hours"]
        
        # Battle Pass extends offline cap
        bp = await get_active_battle_pass(session, player.telegram_id)
        if bp and bp.is_premium:
            cap_hours = max(cap_hours, 12) # BP gives at least 12h
            
        # Check convenience shop buff
        from core.alchemy_engine import get_active_buffs
        buffs = await get_active_buffs(session, player.telegram_id)
        for b in buffs:
            if b.buff_type == "offline_expansion":
                cap_hours = max(cap_hours, b.buff_value)
            
        max_cap_seconds = max(max_cap_seconds, int(cap_hours * 3600))

    capped_seconds = min(elapsed, max_cap_seconds)

    if capped_seconds < TICK_INTERVAL_SECONDS:
        return {"cb_gained": 0, "stone_gained": 0, "elapsed_seconds": 0, "breakthroughs": []}

    sect_mult = 1.0
    spirit_vein_mult = 1.0
    if session:
        from core.sect_engine import get_sect_bonuses
        bonuses = await get_sect_bonuses(session, player.telegram_id)
        sect_mult = bonuses["training_mult"]
        spirit_vein_mult = bonuses["spirit_vein_mult"]

    ticks = int(capped_seconds / TICK_INTERVAL_SECONDS)
    cb_per_tick = calculate_cb_per_tick(player, is_online=False, equip_stats=equip_stats, sect_mult=sect_mult)
    total_cb = cb_per_tick * ticks
    
    total_stones = int(round(0.1 * spirit_vein_mult * ticks))

    breakthroughs = []
    player.cultivation_base += total_cb
    player.spirit_stones += total_stones

    # Optimization: fetch buffs once outside the loop
    active_buffs = None
    if session:
        from core.alchemy_engine import get_active_buffs
        active_buffs = await get_active_buffs(session, player.telegram_id)

    while True:
        bt = await check_breakthrough(player, session, active_buffs=active_buffs)
        if bt is None:
            break
        
        # If it's a non-breakthrough result (cooldown or blocking requirement),
        # we don't want to process it as a "success" breakthrough in the list
        # that triggers sublayer-up messages, but we still need to break the loop.
        # Sprint 8 — `ceremony_required` is a BLOCKING gate just like foundation/core:
        # it caps CB at threshold and does NOT advance the realm, so it MUST break the
        # loop (otherwise the offline-progress while True spins forever — the player is
        # waiting at the threshold for the Cerimónia-Semente choice).
        if bt.get("cooldown") or bt.get("tribulation_required") or bt.get("body_tempering_required") or bt.get("foundation_required") or bt.get("core_required") or bt.get("celestial_trial_required") or bt.get("ceremony_required"):
            breakthroughs.append(bt)
            break
            
        breakthroughs.append(bt)

    was_capped = elapsed > max_cap_seconds
    lost_hours = (elapsed - max_cap_seconds) / 3600 if was_capped else 0

    return {
        "cb_gained": total_cb,
        "stone_gained": total_stones,
        "elapsed_seconds": capped_seconds,
        "breakthroughs": breakthroughs,
        "was_capped": was_capped,
        "lost_hours": lost_hours,
    }

def get_progress_bar(current: float, maximum: float, length: int = 10) -> str:
    if maximum <= 0:
        return "░" * length
    ratio = min(current / maximum, 1.0)
    filled = int(ratio * length)
    empty = length - filled
    percentage = ratio * 100
    return f"{'█' * filled}{'░' * empty} {percentage:.1f}%"

def format_number(n: float) -> str:
    abs_n = abs(n)
    if abs_n >= 1_000_000_000_000:
        return f"{n / 1_000_000_000_000:.1f}T"
    if abs_n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if abs_n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if abs_n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:.0f}"

def get_realm_display(realm: int, sub_layer: int) -> str:
    emoji = REALM_EMOJIS[min(realm, len(REALM_EMOJIS) - 1)]
    name = REALM_NAMES[min(realm, len(REALM_NAMES) - 1)]
    return f"{emoji} {name} {_roman(sub_layer)}"

def _roman(n: int) -> str:
    numerals = {9: "IX", 5: "V", 4: "IV", 1: "I"}
    result = ""
    for value, numeral in numerals.items():
        while n >= value:
            result += numeral
            n -= value
    return result

def get_time_display(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"

def estimate_time_to_breakthrough(player: Player, equip_stats: dict = None, sect_mult: float = 1.0, buff_multiplier: float = 1.0, companion_cb_mult: float = 1.0, dao_cb_mult: float = 1.0, partner_cb_mult: float = 1.0) -> float | None:
    threshold = get_threshold(player.realm, player.sub_layer)
    remaining = threshold - player.cultivation_base
    if remaining <= 0:
        return 0
    cb_per_second = calculate_cb_per_tick(player, equip_stats=equip_stats, sect_mult=sect_mult, buff_multiplier=buff_multiplier, companion_cb_mult=companion_cb_mult, dao_cb_mult=dao_cb_mult, partner_cb_mult=partner_cb_mult) / TICK_INTERVAL_SECONDS
    if cb_per_second <= 0:
        return None
    eta = remaining / cb_per_second
    # N-25 (Sprint v14.3): when the player isn't meditating, meditation_mult=1.0
    # makes cb_per_second tiny, which produces astronomical ETAs (e.g.
    # "2777777777h 46m" displayed in /status). Cap at 30 days — anything
    # longer means "meditate first, then check ETA". Returning None signals
    # the caller to skip the line entirely.
    MAX_ETA_SECONDS = 30 * 24 * 3600
    if eta > MAX_ETA_SECONDS or eta != eta:  # NaN guard
        return None
    return eta

def build_breakthrough_message(bt: dict, lang: str = "en") -> str:
    try:
        from core.i18n import t
        from core.visual_engine import realm_up_art, sublayer_up_art

        # Handle special non-breakthrough cases to avoid KeyError
        if bt.get("cooldown") or bt.get("tribulation_required") or bt.get("body_tempering_required") or bt.get("foundation_required") or bt.get("core_required") or bt.get("celestial_trial_required"):
            return ""

        if "new_realm" not in bt or "new_sub" not in bt:
            # Silently fail if we don't have the required keys
            return ""

        new_realm = bt["new_realm"]
        new_sub = bt["new_sub"]
        realm_display = get_realm_display(new_realm, new_sub)

        if bt["realm_up"]:
            art = realm_up_art(new_realm, REALM_NAMES[min(new_realm, len(REALM_NAMES) - 1)], lang=lang)
            cinematic_key = bt.get("cinematic_key")
            body = t(lang, cinematic_key) if cinematic_key else t(lang, "breakthrough_realm_up", realm=realm_display)
            qi_msg = t(lang, "breakthrough_qi_restored", percent=100)
            return f"{art}\n\n{body}\n\n{qi_msg}"
        else:
            # Sublayer up
            art = sublayer_up_art(realm_display, lang=lang)
            body = t(lang, "breakthrough_sublayer_up", realm=realm_display)
            qi_msg = t(lang, "breakthrough_qi_restored", percent=50)
            return f"{art}\n\n{body}\n\n{qi_msg}"
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to build breakthrough message for %s: %s", bt, e)
        return ""
