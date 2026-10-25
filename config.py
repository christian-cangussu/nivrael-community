import os
from dotenv import load_dotenv

# O `.env` desta pasta, e só ele: sem caminho, o `load_dotenv()` sobe pelas
# pastas-pai até achar um, e uma cópia deste código guardada dentro de outro
# projecto leria o `.env` desse projecto — outra base, outro token. Num
# contentor sem `.env` o ambiente vem todo de fora, como antes.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PORT = int(os.getenv("PORT", "8443"))

TICK_INTERVAL_SECONDS = int(os.getenv("TICK_INTERVAL_SECONDS", "30"))
OFFLINE_CAP_SECONDS = int(os.getenv("OFFLINE_CAP_SECONDS", "14400"))  # 4h F2P cap

ADMIN_USERS = [int(x) for x in os.getenv("ADMIN_USERS", "").split(",") if x.strip()]

FEEDBACK_GROUP_URL = os.getenv("FEEDBACK_GROUP_URL", "https://t.me/Nivrael_RPG")
MINIAPP_URL = os.getenv("MINIAPP_URL", "")

REALM_NAMES = [
    "Mortal",                   # 0
    "Qi Condensation",          # 1
    "Foundation Establishment", # 2
    "Core Formation",           # 3
    "Nascent Soul",             # 4
    "Soul Transformation",      # 5
    "Void Refinement",          # 6
    "Body Integration",         # 7
    "Mahayana",                 # 8
    "Tribulation Transcendence",# 9
    "True Immortal",            # 10
]

REALM_EMOJIS = [
    "🪨", "☯️", "🏯", "🔮", "👻",
    "⚡", "🐉", "🌟", "💎", "👑", "🌸",
]

REALM_MILESTONES = {
    0:  {"unlock": "meditation",        "bonus_qi": 0,    "emoji": "🪨", "cinematic": "milestone_r0"},
    1:  {"unlock": "alchemy",           "bonus_qi": 50,   "emoji": "☯️", "cinematic": "milestone_r1"},
    2:  {"unlock": "forging",           "bonus_qi": 100,  "emoji": "🏯", "cinematic": "milestone_r2"},
    3:  {"unlock": "technique_mastery", "bonus_qi": 200,  "emoji": "🔮", "cinematic": "milestone_r3"},
    4:  {"unlock": "tribulations",      "bonus_qi": 300,  "emoji": "👻", "cinematic": "milestone_r4"},
    5:  {"unlock": "dao_laws",          "bonus_qi": 500,  "emoji": "⚡", "cinematic": "milestone_r5"},
    6:  {"unlock": "void_meditation",   "bonus_qi": 700,  "emoji": "🐉", "cinematic": "milestone_r6"},
    7:  {"unlock": "body_tempering",    "bonus_qi": 1000, "emoji": "🌟", "cinematic": "milestone_r7"},
    8:  {"unlock": "celestial_realm",   "bonus_qi": 1500, "emoji": "💎", "cinematic": "milestone_r8"},
    9:  {"unlock": "transcendence",     "bonus_qi": 2000, "emoji": "👑", "cinematic": "milestone_r9"},
    10: {"unlock": "prestige_immortal", "bonus_qi": 5000, "emoji": "🌸", "cinematic": "milestone_r10"},
}

# Per-language display names for unlocked features shown in next-milestone display
MILESTONE_FEATURE_NAMES = {
    "meditation":        {"en": "Meditation",          "pt": "Meditação",          "es": "Meditación"},
    "alchemy":           {"en": "Alchemy",              "pt": "Alquimia",            "es": "Alquimia"},
    "forging":           {"en": "Artifact Forging",     "pt": "Forja de Artefactos", "es": "Forja de Artefactos"},
    "technique_mastery": {"en": "Technique Mastery",   "pt": "Maestria de Técnica", "es": "Maestría de Técnica"},
    "tribulations":      {"en": "Heavenly Tribulations","pt": "Tribulações Celestiais","es": "Tribulaciones Celestiales"},
    "dao_laws":          {"en": "Dao Laws",             "pt": "Leis do Dao",         "es": "Leyes del Dao"},
    "void_meditation":   {"en": "Void Meditation",      "pt": "Meditação do Vazio",  "es": "Meditación del Vacío"},
    "body_tempering":    {"en": "Body Tempering",       "pt": "Têmpera Corporal",    "es": "Forja Corporal"},
    "celestial_realm":   {"en": "Celestial Realm",      "pt": "Reino Celestial",     "es": "Reino Celestial"},
    "transcendence":     {"en": "Transcendence",        "pt": "Transcendência",      "es": "Trascendencia"},
    "prestige_immortal": {"en": "Prestige: Immortal",   "pt": "Prestígio: Imortal",  "es": "Prestigio: Inmortal"},
}

SUB_LAYERS_PER_REALM = int(os.getenv("SUB_LAYERS_PER_REALM", "9"))

BASE_THRESHOLD = int(os.getenv("BASE_THRESHOLD", "1000"))
THRESHOLD_GROWTH_PER_SUBLAYER = float(os.getenv("THRESHOLD_GROWTH_PER_SUBLAYER", "0.15"))
THRESHOLD_GROWTH_PER_REALM = float(os.getenv("THRESHOLD_GROWTH_PER_REALM", "4.0"))

def get_threshold(realm: int, sub_layer: int) -> float:
    realm_factor = THRESHOLD_GROWTH_PER_REALM ** realm
    sublayer_factor = (1 + THRESHOLD_GROWTH_PER_SUBLAYER) ** sub_layer
    return BASE_THRESHOLD * realm_factor * sublayer_factor

SPIRIT_ROOTS = {
    "Heavenly": {"weight": 0.01, "multiplier": 5.0, "emoji": "🌸"},
    "Superior": {"weight": 1.0, "multiplier": 3.0, "emoji": "💎"},
    "High":     {"weight": 5.0, "multiplier": 2.0, "emoji": "⚡"},
    "Mid":      {"weight": 20.0, "multiplier": 1.5, "emoji": "☯️"},
    "Low":      {"weight": 74.0, "multiplier": 1.0, "emoji": "🪨"},
}

SPIRIT_ROOT_NAMES = list(SPIRIT_ROOTS.keys())
SPIRIT_ROOT_WEIGHTS = [v["weight"] for v in SPIRIT_ROOTS.values()]

BASE_CB_RATE = float(os.getenv("BASE_CB_RATE", "10.0"))

REALM_MULTIPLIERS = [
    1.0, 2.5, 6.0, 15.0, 40.0,
    100.0, 250.0, 600.0, 1500.0, 4000.0, 10000.0,
]

TRIBULATION_START_REALM = int(os.getenv("TRIBULATION_START_REALM", "4"))  # Nascent Soul
TRIBULATION_WINDOW_HOURS = int(os.getenv("TRIBULATION_WINDOW_HOURS", "24"))
TRIBULATION_PENALTY_RATE = float(os.getenv("TRIBULATION_PENALTY_RATE", "0.20"))  # 20% CB loss if not started
TRIBULATION_COOLDOWN_FAILURE_LIGHT = int(os.getenv("TRIBULATION_COOLDOWN_FAILURE_LIGHT", str(6 * 3600)))  # 6h
TRIBULATION_DEBUFF_DURATION_GRAVE = int(os.getenv("TRIBULATION_DEBUFF_DURATION_GRAVE", str(2 * 3600)))  # 2h

PURITY_BASE = float(os.getenv("PURITY_BASE", "1.0"))

MEDITATION_TYPES = {
    "light": {
        "name": {"en": "🧘 Light Meditation", "pt": "🧘 Meditação Leve", "es": "🧘 Meditación Ligera"},
        "multiplier": 1.5,
        "duration_minutes": 30,
        "qi_cost": 0,
        "min_realm": 0,
    },
    "deep": {
        "name": {"en": "🔮 Deep Meditation", "pt": "🔮 Meditação Profunda", "es": "🔮 Meditación Profunda"},
        "multiplier": 2.5,
        "duration_minutes": 60,
        "qi_cost": 50,
        "min_realm": 0,
    },
    "void": {
        "name": {"en": "💜 Void Meditation", "pt": "💜 Meditação do Vazio", "es": "💜 Meditación del Vacío"},
        "multiplier": 6.0,
        "duration_minutes": 120,
        "qi_cost": 0,
        "min_realm": 4,
    },
    # F-11.5 — Celestial Meditation. 8h max, Mahayana-only (realm 8+).
    # Dao-style contemplation: extremely high dao_fragment_mult, focused on
    # Heavenly Laws discovery (engine restricts the law pool when this type is
    # active).
    "celestial_dao": {
        "name": {"en": "🌠 Celestial Meditation", "pt": "🌠 Meditação Celestial", "es": "🌠 Meditación Celestial"},
        "multiplier": 0.0,  # dao-type, no cultivation
        "dao_fragment_mult": 20.0,
        "duration_minutes": 480,  # 8h
        "qi_cost": 800,
        "min_realm": 8,
    },
}

ONLINE_FACTOR = float(os.getenv("ONLINE_FACTOR", "1.0"))
OFFLINE_FACTOR = float(os.getenv("OFFLINE_FACTOR", "0.6"))

# Meditation QI regen multipliers (applied on top of base QI regen)
MEDITATION_QI_MULT = {
    "light": 10.0,
    "deep": 50.0,
    "void": 100.0,
    "dao_basic": 10.0,
    "dao_deep": 50.0,
    "dao_transcend": 100.0,
    "celestial_dao": 150.0,  # F-11.5 Celestial Meditation
}

# Meditation types that restrict combat/dungeon actions
RESTRICTED_MEDITATION = ("deep", "void", "dao_deep", "dao_transcend", "celestial_dao")

DAO_MEDITATION_TYPES = {
    "dao_basic": {
        "name": {"en": "🧘 Basic Comprehension", "pt": "🧘 Compreensão Básica", "es": "🧘 Comprensión Básica"},
        "multiplier": 0.0,
        "dao_fragment_mult": 3.0,
        "duration_minutes": 60,
        "qi_cost": 100,
        "min_realm": 5,
    },
    "dao_deep": {
        "name": {"en": "🔮 Deep Contemplation", "pt": "🔮 Contemplação Profunda", "es": "🔮 Contemplación Profunda"},
        "multiplier": 0.0,
        "dao_fragment_mult": 6.0,
        "duration_minutes": 120,
        "qi_cost": 250,
        "min_realm": 6,
    },
    "dao_transcend": {
        "name": {"en": "💜 Dao Transcendence", "pt": "💜 Transcendência do Dao", "es": "💜 Trascendencia del Dao"},
        "multiplier": 0.0,
        "dao_fragment_mult": 10.0,
        "duration_minutes": 240,
        "qi_cost": 500,
        "min_realm": 8,
    },
    # F-11.5 — Mirror of the celestial meditation type above. Listed here so the
    # cultivation handler treats it as a Dao meditation for discovery purposes.
    "celestial_dao": {
        "name": {"en": "🌠 Celestial Meditation", "pt": "🌠 Meditação Celestial", "es": "🌠 Meditación Celestial"},
        "multiplier": 0.0,
        "dao_fragment_mult": 20.0,
        "duration_minutes": 480,
        "qi_cost": 800,
        "min_realm": 8,
        "requires_first_trial": True,
        "heavenly_only": True,
    },
}

RANKING_MEDALS = ["🥇", "🥈", "🥉"]
RANKING_LIMIT = int(os.getenv("RANKING_LIMIT", "20"))

ARTIFACT_GRADES = {
    0: "Mortal", 1: "Yellow", 2: "Mystic", 3: "Earth",
    4: "Heaven", 5: "Spirit", 6: "Divine", 7: "Dao",
    8: "Celestial",  # F-11: forgeable only at Mahayana, requires celestial materials
}

ARTIFACT_SLOTS = ["weapon", "armor", "accessory1", "accessory2", "mount", "cauldron"]

ALCHEMY_ENERGY_COSTS = {
    1: 10,  # T1: 10 energy/craft
    2: 15,  # T2: 15 energy/craft
    3: 20,  # T3: 20 energy/craft
    4: 30,  # T4: 30 energy/craft
    5: 50,  # T5: 50 energy/craft
}

ALCHEMY_ENERGY_BASE = 100       # Base max energy for all players
ALCHEMY_ENERGY_REGEN_MINUTES = 3  # 1 energy per 3 min F2P → 20/hr, full cap in 5hrs
# F2P daily: log in 3×/day (every 5h) = 300 energy → 30 T1 crafts or 6 T5 crafts ✅

# VIP bonus to max energy (added on top of base 100)
# Higher max = longer burst sessions before having to wait
ALCHEMY_ENERGY_VIP_MAX_BONUS = {
    0: 0,    # max=100  — full in 5h
    1: 50,   # max=150  — full in ~6.25h
    2: 100,  # max=200  — full in ~6.7h
    3: 200,  # max=300  — full in 7.5h
    4: 400,  # max=500  — full in ~8.3h
    5: 900,  # max=1000 — big burst sessions
}

# VIP regen speed: minutes per 1 energy point (lower = faster)
ALCHEMY_ENERGY_VIP_REGEN = {
    0: 3,    # 20/hr
    1: 2.5,  # 24/hr
    2: 2,    # 30/hr
    3: 1.5,  # 40/hr
    4: 1,    # 60/hr
    5: 0.5,  # 120/hr — VIP5 feels near-unlimited
}

# 火候 Huǒhòu — "o domínio do ponto do fogo". O tier de Alquimia (ganho a
# jogar: 15.000 XP ≈ 1.600 sínteses até Celestial) valia +5% de sucesso por tier
# e MAIS NADA: a chama do Aprendiz com 4 sínteses e a do Celestial com 1.634
# eram idênticas — 100 de tecto, 1pt/3min. Medido em 2026-08-18 (report do [jogador]):
#   • `players.alchemy_energy_max` era coluna MORTA (239/240 exactamente a 100);
#   • 99 dos 134 que alguma vez sintetizaram viviam abaixo de UMA síntese T5;
#   • o único acelerador era a carteira (VIP/jade) — violação da Lei §4, que
#     manda o jade vender aceleração e nunca "saltar a parte chata".
# O eixo APRENDIDO soma-se ao eixo PAGO; nenhum desvaloriza o outro (o tecto do
# VIP soma por cima, e a recarga de jade passa a devolver MAIS energia).
ALCHEMY_ENERGY_TIER_MAX_BONUS = {1: 0, 2: 20, 3: 50, 4: 90, 5: 140}
# Multiplicador do tempo de regen (menor = mais rápido). Aplica-se POR CIMA do
# ritmo do VIP, logo o alquimista pagante continua estritamente à frente.
ALCHEMY_ENERGY_TIER_REGEN_MULT = {1: 1.0, 2: 0.92, 3: 0.84, 4: 0.76, 5: 0.68}
# Piso de segurança: `regen_minutes` é divisor em get_alchemy_energy.
ALCHEMY_ENERGY_REGEN_FLOOR = 0.25
# F2P Celestial: tecto 240, 1pt/2.04min → 29/h (era 20/h). Uma síntese T5 a
# partir do zero cai de 150min para 102min — TODA espera encurta.

# Monetization
VIP_TIERS_EUR = {
    1: 5.0,
    2: 20.0,
    3: 50.0,
    4: 150.0,
    5: 500.0,
}
GACHA_COST = int(os.getenv("GACHA_COST", "160"))

# Combat / Arena
MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "12"))  # v16.7 — ~12 tactical rounds (owner) + Heavenly-Pressure ramp
SPARRING_REWARD_MIN = int(os.getenv("SPARRING_REWARD_MIN", "100"))
SPARRING_REWARD_MAX = int(os.getenv("SPARRING_REWARD_MAX", "500"))
ARENA_BASE_REWARD = int(os.getenv("ARENA_BASE_REWARD", "200"))
ELO_K_FACTOR = int(os.getenv("ELO_K_FACTOR", "32"))
CURRENT_SEASON = int(os.getenv("CURRENT_SEASON", "1"))
ARENA_QUEUE_TIMEOUT_SECONDS = int(os.getenv("ARENA_QUEUE_TIMEOUT_SECONDS", "180"))
ARENA_ELO_RANGE = int(os.getenv("ARENA_ELO_RANGE", "200"))
CHALLENGE_EXPIRY_SECONDS = int(os.getenv("CHALLENGE_EXPIRY_SECONDS", "300"))

# Sect Wars
TERRITORY_DEFINITIONS = [
    {"name": "🏔️ Dragon Peak", "bonus_stones": 1500, "bonus_cb": 0.08},
    {"name": "🌊 Azure Sea Ruins", "bonus_stones": 1000, "bonus_cb": 0.05},
    {"name": "🌋 Infernal Forge Grounds", "bonus_stones": 1200, "bonus_cb": 0.06},
    {"name": "❄️ Frozen Tundra", "bonus_stones": 800, "bonus_cb": 0.04},
    {"name": "🌟 Celestial Peak", "bonus_stones": 2000, "bonus_cb": 0.10},
]

ENCHANT_EFFECTS = {
    "cb_boost": {"label": "⚡ Cultivo", "mult": 1.1},
    "bp_boost": {"label": "⚔️ Poder", "mult": 1.15},
    "luck_boost": {"label": "🍀 Sorte", "mult": 1.2},
    "soul_boost": {"label": "👻 Alma", "mult": 1.1},
}

# Sects
SECT_CREATION_COST = int(os.getenv("SECT_CREATION_COST", "10000"))
SECT_MAX_MEMBERS_DEFAULT = int(os.getenv("SECT_MAX_MEMBERS_DEFAULT", "50"))
SECT_WAR_DAY = os.getenv("SECT_WAR_DAY", "fri")
SECT_WAR_HOUR = int(os.getenv("SECT_WAR_HOUR", "20"))
SECT_BUILDINGS = ["training", "herb_garden", "forge", "library", "defense", "spirit_vein"]


BEAST_RANKS = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Divine"]
BEAST_RANK_INDEX = {r: i for i, r in enumerate(BEAST_RANKS)}

EXPEDITION_MIN_RANK = {
    "Common": 0,
    "Rare": 2,
    "Epic": 3,
    "Legendary": 4,
}

BEAST_TRAIN_COST_PER_LEVEL = int(os.getenv("BEAST_TRAIN_COST_PER_LEVEL", "50"))  # Spirit Stones per level
BEAST_TRAIN_EXP_PER_LEVEL = int(os.getenv("BEAST_TRAIN_EXP_PER_LEVEL", "100"))
BEAST_EVOLVE_CORES_COST = int(os.getenv("BEAST_EVOLVE_CORES_COST", "3"))
BEAST_CAPTURE_BASE_CHANCE = float(os.getenv("BEAST_CAPTURE_BASE_CHANCE", "0.5"))
BEAST_MAX_LEVEL = int(os.getenv("BEAST_MAX_LEVEL", "100"))

# Database connection pool
# Local PostgreSQL: pool_size=20 + max_overflow=20 = 40 max simultaneous connections.
# For Supabase: override via env to DB_POOL_SIZE=10, DB_MAX_OVERFLOW=10
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))

# ── Sistema Multi-Servidor (control plane) ──────────────────────────────────
# Control DB: a SEPARATE, isolated DB (not a game world) that maps
# telegram_id -> unlocked worlds + active world, and holds the server registry.
# EMPTY = multi-world DISABLED -> the bot runs exactly as a single-world ("main")
# deployment. A control-plane outage degrades to main-only, never crashes the bot.
CONTROL_DATABASE_URL = os.getenv("CONTROL_DATABASE_URL", "")
# Default pool sizing for SECONDARY worlds (main keeps DB_POOL_SIZE/DB_MAX_OVERFLOW).
# Secondary/idle worlds get a small pool so N worlds fit under Postgres max_connections.
WORLD_DEFAULT_POOL_SIZE = int(os.getenv("WORLD_DEFAULT_POOL_SIZE", "5"))
WORLD_DEFAULT_MAX_OVERFLOW = int(os.getenv("WORLD_DEFAULT_MAX_OVERFLOW", "5"))

# Scheduler / tick settings
CULTIVATION_BATCH_SIZE = int(os.getenv("CULTIVATION_BATCH_SIZE", "100"))
ONLINE_THRESHOLD_SECONDS = int(os.getenv("ONLINE_THRESHOLD_SECONDS", "300"))  # 5 min

# Admin / economy thresholds
ADMIN_ALERT_THRESHOLD = int(os.getenv("ADMIN_ALERT_THRESHOLD", "1000000"))  # 1M stones

# ── Moderação de grupo (hotfix "A Volta" 2026-07-07 — P0 legal) ──────────────
# Filtro anti-link no grupo público (handlers/moderation.py): mensagens de
# não-admins com URL fora da whitelist são apagadas + logadas + owner avisado.
# MOD_WHITELIST_DOMAINS: domínios extra aprovados (ex: "nivrael.com,youtube.com").
# MOD_WHITELIST_TME: nomes t.me/<nome> permitidos além do próprio bot (default:
# o grupo oficial, derivado de FEEDBACK_GROUP_URL).
MOD_WHITELIST_DOMAINS = {
    d.strip().lower().removeprefix("www.")
    for d in os.getenv("MOD_WHITELIST_DOMAINS", "").split(",")
    if d.strip()
}
MOD_WHITELIST_TME = {
    n.strip().lower().lstrip("@")
    for n in os.getenv("MOD_WHITELIST_TME", "Nivrael_RPG").split(",")
    if n.strip()
}
MOD_STRIKE_LIMIT = int(os.getenv("MOD_STRIKE_LIMIT", "3"))


# ── 開 Edição comunitária — a monetização nasce DESLIGADA ─────────────────────
# Na cópia pública ninguém cobra nada por defeito. As Telegram Stars só pagam a
# quem é dono do bot (o jogo oficial), e o gacha tem regras legais por país —
# por isso os dois vêm fechados e ficam documentados como "só no jogo oficial".
#
# `NIVRAEL_MONETIZATION=1` devolve o comportamento do jogo oficial: o `main`
# volta a aceitar Stars e o gacha reabre. Os mundos secundários continuam a
# nascer sandbox (`monetization_enabled=false`), como sempre.
MONETIZATION_ENABLED = (os.getenv("NIVRAEL_MONETIZATION") or "").strip().lower() in ("1", "true", "yes")

