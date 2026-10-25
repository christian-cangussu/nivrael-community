import random
from config import TRIBULATION_START_REALM

STRATEGIES = {
    "resist": {
        "dmg_mult": 1.5,
        "def_mult": 1.0,
        "bp_bonus": 0.10,
        "soul_bonus": 0.0,
        "success_mod": 1.0,
        "emoji": "🛡️",
        "name": {"en": "Resist", "pt": "Resistir", "es": "Resistir"},
    },
    "dodge": {
        "dmg_mult": 0.7,
        "def_mult": 1.0,
        "bp_bonus": 0.0,
        "soul_bonus": 0.0,
        "success_mod": 1.0,
        "emoji": "💨",
        "name": {"en": "Dodge", "pt": "Esquivar", "es": "Esquivar"},
    },
    "absorb": {
        "dmg_mult": 1.2,
        "def_mult": 0.8,
        "bp_bonus": 0.0,
        "soul_bonus": 0.15,
        "success_mod": 0.5,
        "emoji": "⚡",
        "name": {"en": "Absorb", "pt": "Absorver", "es": "Absorber"},
    },
}

# Which phases are required per target realm
TRIBULATION_PHASES = {
    4:  ["thunder"],
    5:  ["thunder"],
    6:  ["thunder", "heart_demon"],
    7:  ["thunder", "heart_demon"],
    8:  ["thunder", "heart_demon", "dao"],
    9:  ["thunder", "heart_demon", "dao"],
    10: ["thunder", "heart_demon", "dao"],
}

# Display names per phase per language
PHASE_NAMES = {
    "thunder":     {"en": "Thunder ⚡",         "pt": "Trovão ⚡",          "es": "Trueno ⚡"},
    "heart_demon": {"en": "Heart Demon 👁️",     "pt": "Demônio Interior 👁️","es": "Demonio Interior 👁️"},
    "dao":         {"en": "Dao Trial ☯️",       "pt": "Prova do Dao ☯️",    "es": "Prueba del Dao ☯️"},
}

# Heart Demon: correct answer per question index per dao element
# Questions have options 0, 1, 2
HD_ELEMENT_ANSWERS = {
    "Lightning": [0, 2, 0],   # direct/fast action
    "Fire":      [2, 2, 0],   # power/ambition
    "Wood":      [0, 0, 1],   # life/compassion
    "Chaos":     [1, 1, 1],   # balance/equilibrium
    "Earth":     [1, 0, 2],   # patience/purity
}
HD_DEFAULT_ANSWERS = [1, 1, 1]  # balanced, for players with no dao law

# Heart Demon question locale key matrix — moved here from handlers/tribulation.py
# in v15.1.3.h2 so the mini-app backend can serve the same canonical question
# bank without importing from a chat handler.
HD_QUESTIONS = [
    ("trib_heart_demon_q1", ["trib_hd_q1_opt0", "trib_hd_q1_opt1", "trib_hd_q1_opt2"]),
    ("trib_heart_demon_q2", ["trib_hd_q2_opt0", "trib_hd_q2_opt1", "trib_hd_q2_opt2"]),
    ("trib_heart_demon_q3", ["trib_hd_q3_opt0", "trib_hd_q3_opt1", "trib_hd_q3_opt2"]),
]

# Perception threshold multiplier to see all 3 options in Heart Demon (else only 2)
# Com perception inicial=40 e crescimento via realm-ups (~1.35x por realm),
# ao realm 6 o jogador tem ~170 base. Threshold = realm*50 = 300 → alcançável com equipamentos.
HD_PERCEPTION_THRESHOLD_MULT = 50   # antes: 200  (player.realm * 50)


def calculate_rounds(realm: int) -> int:
    return 3 + (realm - TRIBULATION_START_REALM) * 2


# Poder fixo por realm. Fórmula usa (soul * 40) como denominador (suaviza o cliff).
# "Hasty" = jogador com stats base * ~4 (quase sem artefactos).
# "Prepared" = jogador com stats base * ~12 (set de artefatos grade 4-5).
# Target: hasty 30-40% sucesso total, prepared 75-85% sucesso total.
#
#  Key  | Realm target | Rounds | hasty soul | prep soul | hasty% | prep%
#   4   | Nascent Soul |   3    |   ~400     |  ~1200    | ~37%   | ~79%
#   5   | Soul Transf. |   5    |   ~530     |  ~1600    | ~35%   | ~79%
#   6   | Void Refin.  |   7    |   ~700     |  ~2000    | ~34%   | ~76%
#   7   | Body Integr. |   9    |   ~900     |  ~2700    | ~35%   | ~79%
#   8   | Mahayana     |  11    |  ~1200     |  ~3500    | ~34%   | ~80%
#   9   | Trib. Trans. |  13    |  ~1600     |  ~4700    | ~36%   | ~86%
#  10   | True Immortal|  15    |  ~2200     |  ~6500    | ~30%   | ~86%
TRIBULATION_POWER_BY_REALM = {
    4:  7000,   # Nascent Soul:               3 rounds
    5:  6500,   # Soul Transformation:        5 rounds
    6:  7200,   # Void Refinement:            7 rounds
    7:  7700,   # Body Integration:           9 rounds
    8:  9000,   # Mahayana:                  11 rounds
    9:  10000,  # Tribulation Transcendence: 13 rounds
    10: 13000,  # True Immortal:             15 rounds
}


def get_tribulation_power(realm: int, karma: int | None = None) -> float:
    """A força dos céus para este reino.

    TEC-5 — `karma` (opcional; None/0 ⇒ multiplicador 1.0 ⇒ byte-idêntico ao
    que sempre foi): com a flag `forbidden_path` ON o peso kármico ENDURECE a
    tribulação (1.5×/2×/3× em |karma| 500/750/900). Esse número é mostrado ao
    jogador no KarmaModal desde a v16.3 e nunca era aplicado — display-lie que
    este sprint paga.

    MV-11 天时 — o TEMPO DO CÉU multiplica a mesma `base` (flag `tempo_do_ceu`;
    sem ela `sky_mult()` devolve 1.0 **sem uma única query**, logo o retorno é
    byte-idêntico ao que sempre foi). O céu é global e derivado do relógio:
    🌩️ Irado ×1.12 · ⛅ Sereno ×1.00 exato · 🌫️ Véu de Nuvens ×0.88.

    O multiplicador vive AQUI, dentro do chokepoint, de propósito:
    `estimate_success_chance` e `simulate_round` recebem `tribulation_power`
    como parâmetro e nunca o re-derivam, logo a PREVISÃO e a ROLAGEM leem
    exatamente o mesmo número em todos os 5 call sites (display = roll). Aplicar
    por call-site faria as duas divergirem no dia em que alguém esquecesse um.

    ⚠️ A ESTRUTURA MUDOU NO MV-11 e a razão importa: até aqui a função tinha
    TRÊS `return` e o do `if not karma` saía ANTES do passo do karma. Um
    multiplicador colocado "depois do karma", como o spec dizia, seria código
    MORTO para toda a gente com karma 0 — que é a esmagadora maioria. Agora há
    um único ponto de saída e cada modificador é um bloco `try` que só multiplica
    `base`; qualquer falha degrada para o valor anterior, nunca levanta. O céu
    NUNCA pode impedir uma tribulação."""
    base = float(TRIBULATION_POWER_BY_REALM.get(realm, realm * 150))
    if karma:
        try:
            from core.forbidden_path_engine import tribulation_karma_mult
            base = base * float(tribulation_karma_mult(karma))
        except Exception:
            pass
    # MV-11 天时 — import FUNCTION-LOCAL, como toda leitura cross-engine desta
    # casa: este ficheiro não tem UM import de `core.*` ao nível do módulo (só
    # `random` e `config`), e ser o primeiro seria risco de ciclo.
    try:
        from core.tianshi_engine import sky_mult
        base = base * float(sky_mult())
    except Exception:
        pass
    return base


async def simulate_round(player_soul_strength: int, tribulation_power: float, strategy: str, defense_mult: float = 0.0, blessing_bonus: float = 0.0) -> dict:
    strat = STRATEGIES.get(strategy, STRATEGIES["resist"])

    # Base damage from tribulation
    # Apply sect defense_mult (e.g., 0.05 = 5% reduction)
    effective_power = tribulation_power * (1.0 - defense_mult)
    base_dmg = effective_power * strat["dmg_mult"] * random.uniform(0.85, 1.15)

    # Player mitigation
    mitigation = player_soul_strength * strat["def_mult"] * random.uniform(0.9, 1.1)

    net_dmg = max(effective_power * 0.05, base_dmg - mitigation)


    safe_soul = max(1, player_soul_strength)
    survival_chance = 1.0 - (net_dmg / (safe_soul * 40))
    survival_chance = max(0.1, min(0.995, survival_chance))

    # Absorb strategy has its own failure chance (50% per round)
    if strategy == "absorb":
        survival_chance = min(survival_chance, 0.5)

    # Tribulation Blessing buff: +bonus% survival chance
    survival_chance = min(0.995, survival_chance + blessing_bonus)

    success = random.random() < survival_chance

    return {
        "success": success,
        "damage": int(net_dmg),
        "survival_chance": survival_chance,
        "message": _get_round_message(strategy, success)
    }


def _get_round_message(strategy: str, success: bool) -> str:
    messages = {
        "resist": [
            "trib_msg_resist_1",
            "trib_msg_resist_2",
            "trib_msg_resist_3"
        ],
        "dodge": [
            "trib_msg_dodge_1",
            "trib_msg_dodge_2",
            "trib_msg_dodge_3"
        ],
        "absorb": [
            "trib_msg_absorb_1",
            "trib_msg_absorb_2",
            "trib_msg_absorb_3"
        ]
    }

    fail_messages = [
        "trib_fail_1",
        "trib_fail_2",
        "trib_fail_3"
    ]

    if not success:
        return random.choice(fail_messages)

    return random.choice(messages.get(strategy, messages["resist"]))


def estimate_success_chance(player_soul_strength: int, tribulation_power: float, strategy: str, rounds: int, defense_mult: float = 0.0) -> float:
    strat = STRATEGIES.get(strategy, STRATEGIES["resist"])

    effective_power = tribulation_power * (1.0 - defense_mult)
    avg_base_dmg = effective_power * strat["dmg_mult"]
    avg_mitigation = player_soul_strength * strat["def_mult"]

    avg_net_dmg = max(effective_power * 0.05, avg_base_dmg - avg_mitigation)

    safe_soul = max(1, player_soul_strength)
    survival_chance = 1.0 - (avg_net_dmg / (safe_soul * 40))
    survival_chance = max(0.1, min(0.995, survival_chance))

    if strategy == "absorb":
        survival_chance = min(survival_chance, 0.5)

    total_chance = (survival_chance ** rounds) * 100
    return round(total_chance, 1)


def determine_outcome(strategy: str, rounds_survived: int, rounds_total: int) -> str:
    if rounds_survived < rounds_total:
        if strategy == "absorb" and random.random() < 0.5:
            return "failure_grave"
        return "failure_light"

    # Perfect chance (5%)
    if random.random() < 0.05:
        return "perfect"

    return "success"


# Os desfechos que contam como "passou a tribulação". A PERFEITA é um sucesso
# MELHOR (5% dos sucessos, acima) — nunca pode valer menos do que o sucesso.
# ⚠️ UM dono (report de 2026-09-30): eram três cópias com três regras — o passe
# de batalha aceitava as duas, o mini-app só 'success' (recusava o grau celestial
# a quem teve a tribulação perfeita) e o chat filtrava `Tribulation.result`,
# uma coluna que não existe (rebentava ao montar a query).
TRIBULATION_PASSED_OUTCOMES = ("success", "perfect")


def tribulation_passed_clause(player_id: int):
    """A condição SQL "este cultivador já passou uma tribulação" — a MESMA para
    o chat, o mini-app e o passe de batalha."""
    from database.models import Tribulation
    return (Tribulation.player_id == player_id) & Tribulation.outcome.in_(
        TRIBULATION_PASSED_OUTCOMES)


# ─────────────────────────────────────────────
# Phase routing helpers
# ─────────────────────────────────────────────

def get_required_phases(target_realm: int) -> list:
    return TRIBULATION_PHASES.get(target_realm, ["thunder"])


def get_next_phase(phases_completed: list, target_realm: int) -> str | None:
    """Returns the next phase name to complete, or None if all done."""
    required = get_required_phases(target_realm)
    completed_names = {p for p in phases_completed if isinstance(p, str)}
    for phase in required:
        if phase not in completed_names:
            return phase
    return None


def build_phases_display(phases_completed: list, target_realm: int, lang: str) -> str:
    required = get_required_phases(target_realm)
    completed_names = {p for p in phases_completed if isinstance(p, str)}
    parts = []
    for i, phase in enumerate(required, 1):
        name = PHASE_NAMES[phase].get(lang, PHASE_NAMES[phase]["en"])
        status = "✅" if phase in completed_names else "⏳"
        parts.append(f"{i}/{len(required)}: {name} {status}")
    return " | ".join(parts)


# ─────────────────────────────────────────────
# Heart Demon
# ─────────────────────────────────────────────

def get_heart_demon_correct_answers(dominant_element: str | None) -> list:
    """Returns [q1_correct, q2_correct, q3_correct] answer indices."""
    if not dominant_element:
        return HD_DEFAULT_ANSWERS[:]
    return HD_ELEMENT_ANSWERS.get(dominant_element, HD_DEFAULT_ANSWERS)[:]


def get_heart_demon_state(phases_completed: list) -> dict | None:
    """Extract the in-progress heart demon state dict, or None."""
    for item in phases_completed:
        if isinstance(item, dict) and "hd" in item:
            return item["hd"]
    return None


def set_heart_demon_state(phases_completed: list, state: dict) -> list:
    """Replace or add the hd state dict in phases_completed."""
    new_list = [item for item in phases_completed if not (isinstance(item, dict) and "hd" in item)]
    new_list.append({"hd": state})
    return new_list


def mark_heart_demon_done(phases_completed: list, passed: bool) -> list:
    """Remove hd state dict and optionally add 'heart_demon' string."""
    new_list = [item for item in phases_completed if not (isinstance(item, dict) and "hd" in item)]
    if passed:
        new_list.append("heart_demon")
    return new_list


def can_see_third_option(player_perception: int, player_realm: int) -> bool:
    return player_perception >= player_realm * HD_PERCEPTION_THRESHOLD_MULT


# ─────────────────────────────────────────────
# Dao Tribulation
# ─────────────────────────────────────────────

def calculate_dao_chance(player, fragments_by_law: list, tribulation_bonus: float = 0.0) -> dict:
    """
    Calculate Dao tribulation success chance.
    fragments_by_law: list of dicts with keys fragments_count, is_completed
    tribulation_bonus: bonus from 3000 Dao Laws (Tribulation category tiers)
    Returns dict with chance (%), penalties, can_attempt, etc.
    """
    realm = player.realm
    required_fragments = realm * 3
    total_fragments = sum(f.get("fragments_count", 0) for f in fragments_by_law)
    total_insight = sum(f.get("insight_level", 0) for f in fragments_by_law)
    completed_laws = sum(1 for f in fragments_by_law if f.get("is_completed", False))

    base_chance = 0.40
    # +5% per completed Dao law category (capped at 9 categories)
    bonus = min(len(fragments_by_law), 9) * 0.05
    if completed_laws:
        bonus += completed_laws * 0.10

    bonus += total_insight * 0.02

    # 3000 Dao Laws tribulation bonus (from Spirit/Soul/Will paths)
    bonus += tribulation_bonus

    penalties = []
    penalty = 0.0

    foundation = getattr(player, "foundation_quality", None)
    core = getattr(player, "core_quality", None)

    if foundation in ("low", None):
        penalty += 0.20
        penalties.append("foundation")

    if core in ("flawed", None):
        penalty += 0.15
        penalties.append("core")

    perfect_bonus = 0.0
    if foundation == "perfect" and core == "perfect":
        perfect_bonus = 0.10

    chance = base_chance + bonus + perfect_bonus - penalty
    chance = max(0.05, min(0.95, chance))

    return {
        "chance": round(chance * 100, 1),
        "total_fragments": total_fragments,
        "required": required_fragments,
        "can_attempt": total_fragments >= required_fragments,
        "penalties": penalties,
        "perfect_bonus": perfect_bonus > 0,
        "tribulation_bonus": tribulation_bonus > 0,
    }
