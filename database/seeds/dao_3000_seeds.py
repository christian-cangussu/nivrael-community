"""
3000 Dao Laws System — Seeds + Retroactive Catch-up
8 categories, 30 paths, 100 laws per path = 3000 laws total.
"""
import logging
import random
import itertools
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DaoCategory, DaoPath, DaoPathLaw, PlayerDaoDiscovery

logger = logging.getLogger(__name__)

# ── Categories ────────────────────────────────────────────────────────────────

CATEGORIES = [
    {
        "id": 1, "name": "Elemental", "name_pt": "Elemental", "name_es": "Elemental",
        "emoji": "🔥", "min_realm": 5, "bonus_type": "cb_mult", "sort_order": 1,
        "description": "Laws governing the primal elements — fire, water, lightning, ice, wind.",
    },
    {
        "id": 2, "name": "Spatial", "name_pt": "Espacial", "name_es": "Espacial",
        "emoji": "🌀", "min_realm": 5, "bonus_type": "cooldown_reduction", "sort_order": 2,
        "description": "Laws of space, void, and dimensional manipulation.",
    },
    {
        "id": 3, "name": "Life", "name_pt": "Vida", "name_es": "Vida",
        "emoji": "🌿", "min_realm": 5, "bonus_type": "hp_regen", "sort_order": 3,
        "description": "Laws of healing, growth, vitality, and the cycle of life.",
    },
    {
        "id": 4, "name": "Martial", "name_pt": "Marcial", "name_es": "Marcial",
        "emoji": "⚔️", "min_realm": 5, "bonus_type": "bp_mult", "sort_order": 4,
        "description": "Laws of combat — sword, fist, body, and formation.",
    },
    {
        "id": 5, "name": "Soul", "name_pt": "Alma", "name_es": "Alma",
        "emoji": "👻", "min_realm": 7, "bonus_type": "tribulation_bonus", "sort_order": 5,
        "description": "Laws governing the spirit, mind, and willpower.",
    },
    {
        "id": 6, "name": "Dao Natural", "name_pt": "Dao Natural", "name_es": "Dao Natural",
        "emoji": "🌍", "min_realm": 6, "bonus_type": "craft_quality", "sort_order": 6,
        "description": "Laws of creation, destruction, balance, and natural harmony.",
    },
    {
        "id": 7, "name": "Primordial", "name_pt": "Primordial", "name_es": "Primordial",
        "emoji": "🔮", "min_realm": 8, "bonus_type": "all_stats", "sort_order": 7,
        "description": "The ancient laws from before the world took form.",
    },
    {
        "id": 8, "name": "Supreme", "name_pt": "Supremo", "name_es": "Supremo",
        "emoji": "💫", "min_realm": 9, "bonus_type": "all_mult", "sort_order": 8,
        "description": "The highest laws — accessible only to those who have mastered two complete Dao paths.",
    },
]

# ── Paths ─────────────────────────────────────────────────────────────────────

PATHS = [
    # Elemental (cat 1) — 5 paths
    {"id": 1,  "category_id": 1, "name": "Path of Fire",      "name_pt": "Caminho do Fogo",       "name_es": "Camino del Fuego",       "emoji": "🔥", "element": "Fire",      "min_realm": 5, "bonus_type": "cb_mult",    "sort_order": 1},
    {"id": 2,  "category_id": 1, "name": "Path of Water",     "name_pt": "Caminho da Água",       "name_es": "Camino del Agua",        "emoji": "💧", "element": "Water",     "min_realm": 5, "bonus_type": "hp_regen",   "sort_order": 2},
    {"id": 3,  "category_id": 1, "name": "Path of Lightning", "name_pt": "Caminho do Trovão",     "name_es": "Camino del Relámpago",   "emoji": "⚡", "element": "Lightning", "min_realm": 5, "bonus_type": "cb_mult",    "sort_order": 3},
    {"id": 4,  "category_id": 1, "name": "Path of Ice",       "name_pt": "Caminho do Gelo",       "name_es": "Camino del Hielo",       "emoji": "🧊", "element": "Ice",       "min_realm": 5, "bonus_type": "bp_mult",    "sort_order": 4},
    {"id": 5,  "category_id": 1, "name": "Path of Wind",      "name_pt": "Caminho do Vento",      "name_es": "Camino del Viento",      "emoji": "🌬️", "element": "Wind",      "min_realm": 5, "bonus_type": "cooldown_reduction", "sort_order": 5},

    # Spatial (cat 2) — 3 paths
    {"id": 6,  "category_id": 2, "name": "Path of Void",      "name_pt": "Caminho do Vazio",      "name_es": "Camino del Vacío",       "emoji": "🕳️", "element": "Void",      "min_realm": 5, "bonus_type": "cooldown_reduction", "sort_order": 1},
    {"id": 7,  "category_id": 2, "name": "Path of Dimension",  "name_pt": "Caminho da Dimensão",  "name_es": "Camino de la Dimensión", "emoji": "🌌", "element": "Space",     "min_realm": 6, "bonus_type": "cooldown_reduction", "sort_order": 2},
    {"id": 8,  "category_id": 2, "name": "Path of Horizon",   "name_pt": "Caminho do Horizonte",  "name_es": "Camino del Horizonte",   "emoji": "🌅", "element": "Space",     "min_realm": 6, "bonus_type": "cb_mult",    "sort_order": 3},

    # Life (cat 3) — 3 paths
    {"id": 9,  "category_id": 3, "name": "Path of Healing",   "name_pt": "Caminho da Cura",       "name_es": "Camino de la Curación",  "emoji": "💚", "element": "Wood",      "min_realm": 5, "bonus_type": "hp_regen",   "sort_order": 1},
    {"id": 10, "category_id": 3, "name": "Path of Growth",    "name_pt": "Caminho do Crescimento","name_es": "Camino del Crecimiento", "emoji": "🌱", "element": "Wood",      "min_realm": 5, "bonus_type": "cb_mult",    "sort_order": 2},
    {"id": 11, "category_id": 3, "name": "Path of Vitality",  "name_pt": "Caminho da Vitalidade", "name_es": "Camino de la Vitalidad", "emoji": "❤️", "element": "Wood",      "min_realm": 6, "bonus_type": "hp_regen",   "sort_order": 3},

    # Martial (cat 4) — 4 paths
    {"id": 12, "category_id": 4, "name": "Path of the Sword", "name_pt": "Caminho da Espada",     "name_es": "Camino de la Espada",    "emoji": "🗡️", "element": "Metal",     "min_realm": 5, "bonus_type": "bp_mult",    "sort_order": 1},
    {"id": 13, "category_id": 4, "name": "Path of the Fist",  "name_pt": "Caminho do Punho",      "name_es": "Camino del Puño",        "emoji": "👊", "element": "Earth",     "min_realm": 5, "bonus_type": "bp_mult",    "sort_order": 2},
    {"id": 14, "category_id": 4, "name": "Path of the Body",  "name_pt": "Caminho do Corpo",      "name_es": "Camino del Cuerpo",      "emoji": "💪", "element": "Earth",     "min_realm": 5, "bonus_type": "hp_regen",   "sort_order": 3},
    {"id": 15, "category_id": 4, "name": "Path of Formation", "name_pt": "Caminho da Formação",   "name_es": "Camino de la Formación", "emoji": "🔷", "element": "Universal", "min_realm": 6, "bonus_type": "bp_mult",    "sort_order": 4},

    # Soul (cat 5) — 3 paths
    {"id": 16, "category_id": 5, "name": "Path of Spirit",    "name_pt": "Caminho do Espírito",   "name_es": "Camino del Espíritu",    "emoji": "👁️", "element": "Chaos",     "min_realm": 7, "bonus_type": "tribulation_bonus", "sort_order": 1},
    {"id": 17, "category_id": 5, "name": "Path of Mind",      "name_pt": "Caminho da Mente",      "name_es": "Camino de la Mente",     "emoji": "🧠", "element": "Chaos",     "min_realm": 7, "bonus_type": "craft_quality",     "sort_order": 2},
    {"id": 18, "category_id": 5, "name": "Path of Will",      "name_pt": "Caminho da Vontade",    "name_es": "Camino de la Voluntad",  "emoji": "🔱", "element": "Chaos",     "min_realm": 7, "bonus_type": "tribulation_bonus", "sort_order": 3},

    # Dao Natural (cat 6) — 4 paths
    {"id": 19, "category_id": 6, "name": "Path of Creation",    "name_pt": "Caminho da Criação",    "name_es": "Camino de la Creación",    "emoji": "✨", "element": "Earth",     "min_realm": 6, "bonus_type": "craft_quality", "sort_order": 1},
    {"id": 20, "category_id": 6, "name": "Path of Destruction", "name_pt": "Caminho da Destruição", "name_es": "Camino de la Destrucción", "emoji": "💥", "element": "Fire",      "min_realm": 6, "bonus_type": "bp_mult",       "sort_order": 2},
    {"id": 21, "category_id": 6, "name": "Path of Balance",     "name_pt": "Caminho do Equilíbrio", "name_es": "Camino del Equilibrio",    "emoji": "☯️", "element": "Universal", "min_realm": 6, "bonus_type": "cb_mult",       "sort_order": 3},
    {"id": 22, "category_id": 6, "name": "Path of Harmony",     "name_pt": "Caminho da Harmonia",   "name_es": "Camino de la Armonía",     "emoji": "🎵", "element": "Universal", "min_realm": 6, "bonus_type": "craft_quality", "sort_order": 4},

    # Primordial (cat 7) — 3 paths
    {"id": 23, "category_id": 7, "name": "Path of Origin",  "name_pt": "Caminho da Origem",  "name_es": "Camino del Origen",  "emoji": "🌟", "element": "Chaos",     "min_realm": 8, "bonus_type": "all_stats", "sort_order": 1},
    {"id": 24, "category_id": 7, "name": "Path of Chaos",   "name_pt": "Caminho do Caos",    "name_es": "Camino del Caos",    "emoji": "🌑", "element": "Chaos",     "min_realm": 8, "bonus_type": "bp_mult",   "sort_order": 2},
    {"id": 25, "category_id": 7, "name": "Path of Order",   "name_pt": "Caminho da Ordem",   "name_es": "Camino del Orden",   "emoji": "⚖️", "element": "Universal", "min_realm": 8, "bonus_type": "all_stats", "sort_order": 3},

    # Supreme (cat 8) — 5 paths
    {"id": 26, "category_id": 8, "name": "Path of Eternity",      "name_pt": "Caminho da Eternidade",     "name_es": "Camino de la Eternidad",      "emoji": "♾️", "element": "Chaos",     "min_realm": 9, "bonus_type": "all_mult", "sort_order": 1},
    {"id": 27, "category_id": 8, "name": "Path of Infinity",      "name_pt": "Caminho do Infinito",       "name_es": "Camino del Infinito",         "emoji": "🌌", "element": "Chaos",     "min_realm": 9, "bonus_type": "all_mult", "sort_order": 2},
    {"id": 28, "category_id": 8, "name": "Path of Transcendence", "name_pt": "Caminho da Transcendência", "name_es": "Camino de la Trascendencia",  "emoji": "🌸", "element": "Universal", "min_realm": 9, "bonus_type": "all_mult", "sort_order": 3},
    {"id": 29, "category_id": 8, "name": "Path of Heaven",        "name_pt": "Caminho do Céu",            "name_es": "Camino del Cielo",            "emoji": "☁️", "element": "Universal", "min_realm": 9, "bonus_type": "all_mult", "sort_order": 4},
    {"id": 30, "category_id": 8, "name": "Path of Fate",          "name_pt": "Caminho do Destino",        "name_es": "Camino del Destino",          "emoji": "🎭", "element": "Chaos",     "min_realm": 9, "bonus_type": "all_mult", "sort_order": 5},
]

# ── Law Templates per Path ────────────────────────────────────────────────────
# Each path gets 20 laws: 8 common, 6 uncommon, 4 rare, 2 epic
# Generated from (adjective, noun, concept) triplets

_RARITY_DIST_20 = ["common"] * 8 + ["uncommon"] * 6 + ["rare"] * 4 + ["epic"] * 2  # 20 (Phase 1)
_RARITY_DIST_80 = (  # 80 (Phase 2 expansion)
    ["common"] * 32 + ["uncommon"] * 24 + ["rare"] * 16 + ["epic"] * 6 + ["legendary"] * 2
)
LAWS_PER_PATH = 100

# Templates: (adjectives, nouns, concepts) — pick combos to make 20 unique names
# Format: "{adj} {noun} Law" or "{adj} {noun} {concept} Law"
PATH_TEMPLATES = {
    # ── Elemental ──
    1: {  # Fire
        "adj": ["Blazing", "Searing", "Molten", "Crimson", "Smoldering", "Radiant", "Scorching", "Ashen"],
        "noun": ["Flame", "Sun", "Ember", "Inferno", "Pyre", "Blaze"],
        "concept": ["Essence", "Heart", "Dominion", "Wrath"],
        "names_pt": ["Chama Ardente", "Sol Escaldante", "Brasa Fundida", "Inferno Carmesim", "Pira Fumegante", "Radiância Ígnea", "Fulgor Abrasador", "Cinza Eterna", "Essência da Chama", "Coração do Sol", "Domínio de Brasa", "Fúria do Inferno", "Fulgor da Pira", "Coração Ardente", "Essência do Blaze", "Domínio Solar", "Fúria Escaldante", "Chama Primordial", "Inferno Radiante", "Pira do Caos"],
        "names_es": ["Llama Ardiente", "Sol Abrasador", "Brasa Fundida", "Infierno Carmesí", "Pira Humeante", "Radiancia Ígnea", "Fulgor Abrasador", "Ceniza Eterna", "Esencia de la Llama", "Corazón del Sol", "Dominio de Brasas", "Furia del Infierno", "Fulgor de la Pira", "Corazón Ardiente", "Esencia del Fuego", "Dominio Solar", "Furia Abrasadora", "Llama Primordial", "Infierno Radiante", "Pira del Caos"],
    },
    2: {  # Water
        "adj": ["Flowing", "Torrential", "Serene", "Abyssal", "Tidal", "Crystalline", "Surging", "Glacial"],
        "noun": ["Wave", "Tide", "Current", "Rain", "Mist", "Depths"],
        "concept": ["Spirit", "Flow", "Calm", "Fury"],
        "names_pt": ["Onda Fluente", "Maré Torrencial", "Corrente Serena", "Chuva Abissal", "Névoa das Marés", "Profundezas Cristalinas", "Onda Impetuosa", "Maré Glacial", "Espírito da Onda", "Fluxo da Maré", "Calma da Corrente", "Fúria da Chuva", "Espírito da Névoa", "Fluxo Profundo", "Calma Cristalina", "Fúria Impetuosa", "Onda Primordial", "Maré Eterna", "Corrente Abissal", "Profundezas do Dao"],
        "names_es": ["Ola Fluida", "Marea Torrencial", "Corriente Serena", "Lluvia Abisal", "Niebla de Mareas", "Profundidades Cristalinas", "Ola Impetuosa", "Marea Glacial", "Espíritu de la Ola", "Flujo de la Marea", "Calma de la Corriente", "Furia de la Lluvia", "Espíritu de la Niebla", "Flujo Profundo", "Calma Cristalina", "Furia Impetuosa", "Ola Primordial", "Marea Eterna", "Corriente Abisal", "Profundidades del Dao"],
    },
    3: {  # Lightning
        "adj": ["Thundering", "Crackling", "Violet", "Heavenly", "Roaring", "Splitting", "Divine", "Pulsing"],
        "noun": ["Bolt", "Thunder", "Storm", "Arc", "Spark", "Tempest"],
        "concept": ["Strike", "Fury", "Dominion", "Wrath"],
        "names_pt": ["Raio Trovejante", "Trovão Crepitante", "Relâmpago Violeta", "Raio Celestial", "Trovão Rugente", "Arco Cortante", "Centelha Divina", "Tempestade Pulsante", "Golpe do Raio", "Fúria do Trovão", "Domínio da Tempestade", "Ira do Arco", "Golpe da Centelha", "Fúria Celeste", "Domínio Trovejante", "Ira Divina", "Raio Primordial", "Trovão Eterno", "Tempestade do Dao", "Arco Supremo"],
        "names_es": ["Rayo Tronante", "Trueno Crepitante", "Relámpago Violeta", "Rayo Celestial", "Trueno Rugiente", "Arco Cortante", "Centella Divina", "Tempestad Pulsante", "Golpe del Rayo", "Furia del Trueno", "Dominio de la Tempestad", "Ira del Arco", "Golpe de la Centella", "Furia Celestial", "Dominio Tronante", "Ira Divina", "Rayo Primordial", "Trueno Eterno", "Tempestad del Dao", "Arco Supremo"],
    },
    4: {  # Ice
        "adj": ["Frozen", "Glacial", "Permafrost", "Crystalline", "Bitter", "Shimmering", "Polar", "Absolute"],
        "noun": ["Frost", "Glacier", "Shard", "Tundra", "Blizzard", "Rime"],
        "concept": ["Seal", "Stillness", "Dominion", "Heart"],
        "names_pt": ["Geada Congelada", "Glaciar Eterno", "Estilhaço Permafrost", "Cristal de Gelo", "Ventania Amarga", "Geada Cintilante", "Nevasca Polar", "Gelo Absoluto", "Selo da Geada", "Quietude do Glaciar", "Domínio do Estilhaço", "Coração da Tundra", "Selo da Nevasca", "Quietude do Gelo", "Domínio Polar", "Coração Absoluto", "Geada Primordial", "Glaciar do Dao", "Nevasca Suprema", "Gelo Eterno"],
        "names_es": ["Escarcha Congelada", "Glaciar Eterno", "Esquirla Permafrost", "Cristal de Hielo", "Ventisca Amarga", "Escarcha Centelleante", "Nevada Polar", "Hielo Absoluto", "Sello de la Escarcha", "Quietud del Glaciar", "Dominio de la Esquirla", "Corazón de la Tundra", "Sello de la Nevada", "Quietud del Hielo", "Dominio Polar", "Corazón Absoluto", "Escarcha Primordial", "Glaciar del Dao", "Nevada Suprema", "Hielo Eterno"],
    },
    5: {  # Wind
        "adj": ["Howling", "Gentle", "Raging", "Unseen", "Whispering", "Sovereign", "Tempest", "Eternal"],
        "noun": ["Gale", "Breeze", "Cyclone", "Zephyr", "Gust", "Typhoon"],
        "concept": ["Dance", "Freedom", "Dominion", "Song"],
        "names_pt": ["Vendaval Uivante", "Brisa Gentil", "Ciclone Furioso", "Zéfiro Invisível", "Rajada Sussurrante", "Tufão Soberano", "Tempestade Ventosa", "Vento Eterno", "Dança do Vendaval", "Liberdade da Brisa", "Domínio do Ciclone", "Canção do Zéfiro", "Dança da Rajada", "Liberdade Soberana", "Domínio do Tufão", "Canção Eterna", "Vendaval Primordial", "Brisa do Dao", "Ciclone Supremo", "Zéfiro Celestial"],
        "names_es": ["Vendaval Aullante", "Brisa Gentil", "Ciclón Furioso", "Céfiro Invisible", "Ráfaga Susurrante", "Tifón Soberano", "Tempestad Ventosa", "Viento Eterno", "Danza del Vendaval", "Libertad de la Brisa", "Dominio del Ciclón", "Canción del Céfiro", "Danza de la Ráfaga", "Libertad Soberana", "Dominio del Tifón", "Canción Eterna", "Vendaval Primordial", "Brisa del Dao", "Ciclón Supremo", "Céfiro Celestial"],
    },

    # ── Spatial ──
    6: {  # Void
        "adj": ["Silent", "Vast", "Depthless", "Hollow", "Consuming", "Boundless", "Distant", "Absolute"],
        "noun": ["Void", "Abyss", "Emptiness", "Null", "Vacuum", "Chasm"],
        "concept": ["Step", "Gate", "Dominion", "Seal"],
        "names_pt": ["Vazio Silencioso", "Abismo Vasto", "Nulidade Profunda", "Vácuo Oco", "Abismo Devorador", "Vazio Ilimitado", "Nulidade Distante", "Vácuo Absoluto", "Passo do Vazio", "Portal do Abismo", "Domínio da Nulidade", "Selo do Vácuo", "Passo do Abismo", "Portal Ilimitado", "Domínio Profundo", "Selo Absoluto", "Vazio Primordial", "Abismo do Dao", "Nulidade Suprema", "Vácuo Eterno"],
        "names_es": ["Vacío Silencioso", "Abismo Vasto", "Nulidad Profunda", "Vacuo Hueco", "Abismo Devorador", "Vacío Ilimitado", "Nulidad Distante", "Vacuo Absoluto", "Paso del Vacío", "Portal del Abismo", "Dominio de la Nulidad", "Sello del Vacuo", "Paso del Abismo", "Portal Ilimitado", "Dominio Profundo", "Sello Absoluto", "Vacío Primordial", "Abismo del Dao", "Nulidad Suprema", "Vacuo Eterno"],
    },
    7: {  # Dimension
        "adj": ["Shifting", "Folding", "Warping", "Layered", "Piercing", "Tearing", "Bending", "Fracturing"],
        "noun": ["Dimension", "Plane", "Rift", "Realm", "Boundary", "Fabric"],
        "concept": ["Weave", "Fold", "Gate", "Bridge"],
        "names_pt": ["Dimensão Mutável", "Plano Dobrado", "Fenda Distorcida", "Reino em Camadas", "Fronteira Perfurante", "Rasgo Dimensional", "Tecido Curvado", "Plano Fracturado", "Trama da Dimensão", "Dobra do Plano", "Portal da Fenda", "Ponte do Reino", "Trama da Fronteira", "Dobra do Rasgo", "Portal Curvado", "Ponte Fracturada", "Dimensão Primordial", "Plano do Dao", "Fenda Suprema", "Reino Eterno"],
        "names_es": ["Dimensión Cambiante", "Plano Doblado", "Grieta Distorsionada", "Reino en Capas", "Frontera Perforante", "Desgarro Dimensional", "Tejido Curvado", "Plano Fracturado", "Trama de la Dimensión", "Pliegue del Plano", "Portal de la Grieta", "Puente del Reino", "Trama de la Frontera", "Pliegue del Desgarro", "Portal Curvado", "Puente Fracturado", "Dimensión Primordial", "Plano del Dao", "Grieta Suprema", "Reino Eterno"],
    },
    8: {  # Horizon
        "adj": ["Distant", "Endless", "Converging", "Vanishing", "Shimmering", "Boundless", "Fading", "Luminous"],
        "noun": ["Horizon", "Expanse", "Limit", "Edge", "Vista", "Panorama"],
        "concept": ["Sight", "Reach", "Beyond", "Span"],
        "names_pt": ["Horizonte Distante", "Vastidão Infinita", "Limite Convergente", "Borda Evanescente", "Vista Cintilante", "Panorama Ilimitado", "Horizonte Desbotado", "Expansão Luminosa", "Visão do Horizonte", "Alcance da Vastidão", "Além do Limite", "Amplitude da Borda", "Visão Cintilante", "Alcance Ilimitado", "Além Luminoso", "Amplitude Eterna", "Horizonte Primordial", "Vastidão do Dao", "Limite Supremo", "Borda do Infinito"],
        "names_es": ["Horizonte Distante", "Vastedad Infinita", "Límite Convergente", "Borde Evanescente", "Vista Centelleante", "Panorama Ilimitado", "Horizonte Desvanecido", "Expansión Luminosa", "Visión del Horizonte", "Alcance de la Vastedad", "Más Allá del Límite", "Amplitud del Borde", "Visión Centelleante", "Alcance Ilimitado", "Más Allá Luminoso", "Amplitud Eterna", "Horizonte Primordial", "Vastedad del Dao", "Límite Supremo", "Borde del Infinito"],
    },

    # ── Life ──
    9: {  # Healing
        "adj": ["Gentle", "Restorative", "Radiant", "Soothing", "Sacred", "Purifying", "Mending", "Divine"],
        "noun": ["Light", "Touch", "Spring", "Balm", "Grace", "Blessing"],
        "concept": ["Renewal", "Mend", "Harmony", "Embrace"],
        "names_pt": ["Luz Gentil", "Toque Restaurador", "Nascente Radiante", "Bálsamo Suave", "Graça Sagrada", "Bênção Purificadora", "Luz Reparadora", "Toque Divino", "Renovação da Luz", "Cura do Toque", "Harmonia da Nascente", "Abraço do Bálsamo", "Renovação Sagrada", "Cura Purificadora", "Harmonia Divina", "Abraço Reparador", "Luz Primordial", "Toque do Dao", "Nascente Suprema", "Bálsamo Eterno"],
        "names_es": ["Luz Gentil", "Toque Restaurador", "Manantial Radiante", "Bálsamo Suave", "Gracia Sagrada", "Bendición Purificadora", "Luz Reparadora", "Toque Divino", "Renovación de la Luz", "Cura del Toque", "Armonía del Manantial", "Abrazo del Bálsamo", "Renovación Sagrada", "Cura Purificadora", "Armonía Divina", "Abrazo Reparador", "Luz Primordial", "Toque del Dao", "Manantial Supremo", "Bálsamo Eterno"],
    },
    10: {  # Growth
        "adj": ["Blooming", "Verdant", "Unyielding", "Ancient", "Sprouting", "Thriving", "Towering", "Evergreen"],
        "noun": ["Root", "Branch", "Seed", "Canopy", "Grove", "Vine"],
        "concept": ["Reach", "Bloom", "Cycle", "Ascension"],
        "names_pt": ["Raiz Florescente", "Ramo Verdejante", "Semente Inabalável", "Copa Ancestral", "Bosque Brotante", "Vinha Próspera", "Raiz Imponente", "Ramo Perene", "Alcance da Raiz", "Florescer do Ramo", "Ciclo da Semente", "Ascensão da Copa", "Alcance do Bosque", "Florescer da Vinha", "Ciclo Perene", "Ascensão Imponente", "Raiz Primordial", "Ramo do Dao", "Semente Suprema", "Copa Eterna"],
        "names_es": ["Raíz Floreciente", "Rama Verdeciente", "Semilla Inquebrantable", "Copa Ancestral", "Bosque Brotante", "Vid Próspera", "Raíz Imponente", "Rama Perenne", "Alcance de la Raíz", "Florecer de la Rama", "Ciclo de la Semilla", "Ascensión de la Copa", "Alcance del Bosque", "Florecer de la Vid", "Ciclo Perenne", "Ascensión Imponente", "Raíz Primordial", "Rama del Dao", "Semilla Suprema", "Copa Eterna"],
    },
    11: {  # Vitality
        "adj": ["Pulsing", "Undying", "Surging", "Vibrant", "Resilient", "Overflowing", "Primal", "Inexhaustible"],
        "noun": ["Pulse", "Heartbeat", "Blood", "Essence", "Life Force", "Vigor"],
        "concept": ["Surge", "Core", "Eternal", "Flow"],
        "names_pt": ["Pulso Palpitante", "Batida Imorredoura", "Sangue Impetuoso", "Essência Vibrante", "Força Vital Resiliente", "Vigor Transbordante", "Pulso Primal", "Batida Inexaurível", "Ímpeto do Pulso", "Núcleo da Batida", "Eternidade do Sangue", "Fluxo da Essência", "Ímpeto Vital", "Núcleo Primal", "Eternidade Transbordante", "Fluxo Inexaurível", "Pulso Primordial", "Batida do Dao", "Sangue Supremo", "Essência Eterna"],
        "names_es": ["Pulso Palpitante", "Latido Imperecedero", "Sangre Impetuosa", "Esencia Vibrante", "Fuerza Vital Resiliente", "Vigor Desbordante", "Pulso Primal", "Latido Inagotable", "Ímpetu del Pulso", "Núcleo del Latido", "Eternidad de la Sangre", "Flujo de la Esencia", "Ímpetu Vital", "Núcleo Primal", "Eternidad Desbordante", "Flujo Inagotable", "Pulso Primordial", "Latido del Dao", "Sangre Suprema", "Esencia Eterna"],
    },

    # ── Martial ──
    12: {  # Sword
        "adj": ["Gleaming", "Relentless", "Phantom", "Razor", "Sweeping", "Piercing", "Sovereign", "Myriad"],
        "noun": ["Blade", "Edge", "Slash", "Sword", "Cut", "Steel"],
        "concept": ["Intent", "Heart", "Domain", "Will"],
        "names_pt": ["Lâmina Reluzente", "Corte Implacável", "Espada Fantasma", "Fio de Navalha", "Lâmina Varrente", "Aço Perfurante", "Espada Soberana", "Miríade de Lâminas", "Intenção da Lâmina", "Coração do Corte", "Domínio da Espada", "Vontade do Aço", "Intenção Fantasma", "Coração Soberano", "Domínio de Navalha", "Vontade Miríade", "Lâmina Primordial", "Corte do Dao", "Espada Suprema", "Aço Eterno"],
        "names_es": ["Hoja Reluciente", "Corte Implacable", "Espada Fantasma", "Filo de Navaja", "Hoja Barredora", "Acero Perforante", "Espada Soberana", "Miríada de Hojas", "Intención de la Hoja", "Corazón del Corte", "Dominio de la Espada", "Voluntad del Acero", "Intención Fantasma", "Corazón Soberano", "Dominio de Navaja", "Voluntad Miríada", "Hoja Primordial", "Corte del Dao", "Espada Suprema", "Acero Eterno"],
    },
    13: {  # Fist
        "adj": ["Iron", "Crushing", "Thundering", "Immovable", "Erupting", "Titanic", "Celestial", "Unstoppable"],
        "noun": ["Fist", "Palm", "Strike", "Impact", "Hammer", "Blow"],
        "concept": ["Force", "Power", "Fury", "Will"],
        "names_pt": ["Punho de Ferro", "Palma Esmagadora", "Golpe Trovejante", "Impacto Inamovível", "Martelo Eruptivo", "Punho Titânico", "Palma Celestial", "Golpe Imparável", "Força do Punho", "Poder da Palma", "Fúria do Golpe", "Vontade do Impacto", "Força do Martelo", "Poder Titânico", "Fúria Celestial", "Vontade Imparável", "Punho Primordial", "Palma do Dao", "Golpe Supremo", "Impacto Eterno"],
        "names_es": ["Puño de Hierro", "Palma Aplastante", "Golpe Tronante", "Impacto Inamovible", "Martillo Eruptivo", "Puño Titánico", "Palma Celestial", "Golpe Imparable", "Fuerza del Puño", "Poder de la Palma", "Furia del Golpe", "Voluntad del Impacto", "Fuerza del Martillo", "Poder Titánico", "Furia Celestial", "Voluntad Imparable", "Puño Primordial", "Palma del Dao", "Golpe Supremo", "Impacto Eterno"],
    },
    14: {  # Body
        "adj": ["Adamantine", "Tempered", "Undying", "Diamond", "Indestructible", "Vajra", "Impervious", "Transcendent"],
        "noun": ["Skin", "Bone", "Flesh", "Shell", "Form", "Frame"],
        "concept": ["Fortitude", "Refinement", "Awakening", "Ascension"],
        "names_pt": ["Pele Adamantina", "Osso Temperado", "Carne Imorredoura", "Carapaça Diamante", "Forma Indestrutível", "Esqueleto Vajra", "Pele Impermeável", "Corpo Transcendente", "Fortaleza da Pele", "Refinamento do Osso", "Despertar da Carne", "Ascensão da Carapaça", "Fortaleza Indestrutível", "Refinamento Vajra", "Despertar Impermeável", "Ascensão Transcendente", "Pele Primordial", "Osso do Dao", "Carne Suprema", "Corpo Eterno"],
        "names_es": ["Piel Adamantina", "Hueso Templado", "Carne Imperecedera", "Caparazón Diamante", "Forma Indestructible", "Esqueleto Vajra", "Piel Impermeable", "Cuerpo Trascendente", "Fortaleza de la Piel", "Refinamiento del Hueso", "Despertar de la Carne", "Ascensión del Caparazón", "Fortaleza Indestructible", "Refinamiento Vajra", "Despertar Impermeable", "Ascensión Trascendente", "Piel Primordial", "Hueso del Dao", "Carne Suprema", "Cuerpo Eterno"],
    },
    15: {  # Formation
        "adj": ["Interlocking", "Resonating", "Spiraling", "Converging", "Amplifying", "Shifting", "Ancient", "Celestial"],
        "noun": ["Array", "Circle", "Pattern", "Sigil", "Node", "Matrix"],
        "concept": ["Lock", "Weave", "Pulse", "Core"],
        "names_pt": ["Matriz Entrelaçada", "Círculo Ressonante", "Padrão Espiral", "Sigilo Convergente", "Nódulo Amplificador", "Matriz Mutável", "Círculo Ancestral", "Sigilo Celestial", "Trava da Matriz", "Trama do Círculo", "Pulso do Padrão", "Núcleo do Sigilo", "Trava do Nódulo", "Trama Ancestral", "Pulso Celestial", "Núcleo Amplificador", "Matriz Primordial", "Círculo do Dao", "Padrão Supremo", "Sigilo Eterno"],
        "names_es": ["Matriz Entrelazada", "Círculo Resonante", "Patrón Espiral", "Sigilo Convergente", "Nódulo Amplificador", "Matriz Cambiante", "Círculo Ancestral", "Sigilo Celestial", "Traba de la Matriz", "Trama del Círculo", "Pulso del Patrón", "Núcleo del Sigilo", "Traba del Nódulo", "Trama Ancestral", "Pulso Celestial", "Núcleo Amplificador", "Matriz Primordial", "Círculo del Dao", "Patrón Supremo", "Sigilo Eterno"],
    },

    # ── Soul ──
    16: {  # Spirit
        "adj": ["Ethereal", "Awakened", "Luminous", "Unfettered", "Spectral", "Transcendent", "Ascendant", "Boundless"],
        "noun": ["Spirit", "Soul", "Ghost", "Phantom", "Wraith", "Essence"],
        "concept": ["Eye", "Sight", "Reach", "Resonance"],
        "names_pt": ["Espírito Etéreo", "Alma Desperta", "Fantasma Luminoso", "Espectro Desacorrentado", "Sombra Espectral", "Essência Transcendente", "Espírito Ascendente", "Alma Ilimitada", "Olho do Espírito", "Visão da Alma", "Alcance do Fantasma", "Ressonância do Espectro", "Olho Transcendente", "Visão Ascendente", "Alcance Ilimitado", "Ressonância Espectral", "Espírito Primordial", "Alma do Dao", "Fantasma Supremo", "Essência Eterna"],
        "names_es": ["Espíritu Etéreo", "Alma Despierta", "Fantasma Luminoso", "Espectro Desencadenado", "Sombra Espectral", "Esencia Trascendente", "Espíritu Ascendente", "Alma Ilimitada", "Ojo del Espíritu", "Visión del Alma", "Alcance del Fantasma", "Resonancia del Espectro", "Ojo Trascendente", "Visión Ascendente", "Alcance Ilimitado", "Resonancia Espectral", "Espíritu Primordial", "Alma del Dao", "Fantasma Supremo", "Esencia Eterna"],
    },
    17: {  # Mind
        "adj": ["Sharp", "Serene", "Piercing", "Infinite", "Focused", "Enlightened", "Razor", "Omniscient"],
        "noun": ["Thought", "Memory", "Clarity", "Insight", "Awareness", "Perception"],
        "concept": ["Depth", "Focus", "Expansion", "Truth"],
        "names_pt": ["Pensamento Afiado", "Memória Serena", "Clareza Penetrante", "Insight Infinito", "Percepção Focada", "Consciência Iluminada", "Pensamento Cortante", "Memória Omnisciente", "Profundidade do Pensamento", "Foco da Memória", "Expansão da Clareza", "Verdade do Insight", "Profundidade da Percepção", "Foco Iluminado", "Expansão Cortante", "Verdade Omnisciente", "Pensamento Primordial", "Memória do Dao", "Clareza Suprema", "Insight Eterno"],
        "names_es": ["Pensamiento Afilado", "Memoria Serena", "Claridad Penetrante", "Insight Infinito", "Percepción Enfocada", "Conciencia Iluminada", "Pensamiento Cortante", "Memoria Omnisciente", "Profundidad del Pensamiento", "Enfoque de la Memoria", "Expansión de la Claridad", "Verdad del Insight", "Profundidad de la Percepción", "Enfoque Iluminado", "Expansión Cortante", "Verdad Omnisciente", "Pensamiento Primordial", "Memoria del Dao", "Claridad Suprema", "Insight Eterno"],
    },
    18: {  # Will
        "adj": ["Unbreakable", "Iron", "Immovable", "Absolute", "Defiant", "Unwavering", "Resolute", "Indomitable"],
        "noun": ["Will", "Resolve", "Determination", "Conviction", "Heart", "Tenacity"],
        "concept": ["Pillar", "Shield", "Flame", "Mountain"],
        "names_pt": ["Vontade Inquebrantável", "Resolução de Ferro", "Determinação Inamovível", "Convicção Absoluta", "Coração Desafiante", "Tenacidade Inabalável", "Vontade Resoluta", "Resolução Indomável", "Pilar da Vontade", "Escudo da Resolução", "Chama da Determinação", "Montanha da Convicção", "Pilar Desafiante", "Escudo Inabalável", "Chama Resoluta", "Montanha Indomável", "Vontade Primordial", "Resolução do Dao", "Determinação Suprema", "Convicção Eterna"],
        "names_es": ["Voluntad Inquebrantable", "Resolución de Hierro", "Determinación Inamovible", "Convicción Absoluta", "Corazón Desafiante", "Tenacidad Inquebrantable", "Voluntad Resuelta", "Resolución Indomable", "Pilar de la Voluntad", "Escudo de la Resolución", "Llama de la Determinación", "Montaña de la Convicción", "Pilar Desafiante", "Escudo Inquebrantable", "Llama Resuelta", "Montaña Indomable", "Voluntad Primordial", "Resolución del Dao", "Determinación Suprema", "Convicción Eterna"],
    },

    # ── Dao Natural ──
    19: {  # Creation
        "adj": ["Shaping", "Nurturing", "Manifesting", "Forging", "Breathing", "Weaving", "Birthing", "Divine"],
        "noun": ["Clay", "Spark", "Blueprint", "Essence", "Foundation", "Genesis"],
        "concept": ["Form", "Birth", "Design", "Purpose"],
        "names_pt": ["Argila Moldadora", "Centelha Nutridora", "Projeto Manifesto", "Essência Forjada", "Fundação Vivificante", "Génese Tecedora", "Argila Nascente", "Centelha Divina", "Forma da Argila", "Nascimento da Centelha", "Design do Projeto", "Propósito da Essência", "Forma da Fundação", "Nascimento da Génese", "Design Divino", "Propósito Nascente", "Argila Primordial", "Centelha do Dao", "Projeto Supremo", "Essência Eterna"],
        "names_es": ["Arcilla Moldeadora", "Centella Nutridora", "Proyecto Manifiesto", "Esencia Forjada", "Fundación Vivificante", "Génesis Tejedora", "Arcilla Naciente", "Centella Divina", "Forma de la Arcilla", "Nacimiento de la Centella", "Diseño del Proyecto", "Propósito de la Esencia", "Forma de la Fundación", "Nacimiento del Génesis", "Diseño Divino", "Propósito Naciente", "Arcilla Primordial", "Centella del Dao", "Proyecto Supremo", "Esencia Eterna"],
    },
    20: {  # Destruction
        "adj": ["Shattering", "Annihilating", "Withering", "Corrosive", "Decaying", "Obliterating", "Sundering", "Devouring"],
        "noun": ["Ruin", "Ash", "Entropy", "Decay", "Oblivion", "Devastation"],
        "concept": ["End", "Collapse", "Unmaking", "Return"],
        "names_pt": ["Ruína Estilhaçante", "Cinza Aniquiladora", "Entropia Definhante", "Decadência Corrosiva", "Oblívio Decadente", "Devastação Obliterante", "Ruína Cindida", "Cinza Devoradora", "Fim da Ruína", "Colapso da Cinza", "Desfazer da Entropia", "Retorno da Decadência", "Fim do Oblívio", "Colapso da Devastação", "Desfazer Cindido", "Retorno Devorador", "Ruína Primordial", "Cinza do Dao", "Entropia Suprema", "Decadência Eterna"],
        "names_es": ["Ruina Fragmentadora", "Ceniza Aniquiladora", "Entropía Marchitante", "Decadencia Corrosiva", "Olvido Decadente", "Devastación Obliterante", "Ruina Hendida", "Ceniza Devoradora", "Fin de la Ruina", "Colapso de la Ceniza", "Deshace de la Entropía", "Retorno de la Decadencia", "Fin del Olvido", "Colapso de la Devastación", "Deshace Hendido", "Retorno Devorador", "Ruina Primordial", "Ceniza del Dao", "Entropía Suprema", "Decadencia Eterna"],
    },
    21: {  # Balance
        "adj": ["Centered", "Neutral", "Equilibrated", "Measured", "Poised", "Symmetric", "Calibrated", "Harmonized"],
        "noun": ["Scale", "Center", "Fulcrum", "Axis", "Midpoint", "Equilibrium"],
        "concept": ["Poise", "Unity", "Stillness", "Truth"],
        "names_pt": ["Balança Centrada", "Centro Neutro", "Fulcro Equilibrado", "Eixo Medido", "Ponto Médio Ponderado", "Equilíbrio Simétrico", "Balança Calibrada", "Centro Harmonizado", "Equilíbrio da Balança", "Unidade do Centro", "Quietude do Fulcro", "Verdade do Eixo", "Equilíbrio do Ponto Médio", "Unidade Simétrica", "Quietude Calibrada", "Verdade Harmonizada", "Balança Primordial", "Centro do Dao", "Fulcro Supremo", "Eixo Eterno"],
        "names_es": ["Balanza Centrada", "Centro Neutro", "Fulcro Equilibrado", "Eje Medido", "Punto Medio Ponderado", "Equilibrio Simétrico", "Balanza Calibrada", "Centro Armonizado", "Equilibrio de la Balanza", "Unidad del Centro", "Quietud del Fulcro", "Verdad del Eje", "Equilibrio del Punto Medio", "Unidad Simétrica", "Quietud Calibrada", "Verdad Armonizada", "Balanza Primordial", "Centro del Dao", "Fulcro Supremo", "Eje Eterno"],
    },
    22: {  # Harmony
        "adj": ["Flowing", "Resonant", "Melodic", "Intertwined", "Synchronized", "Attuned", "Unified", "Celestial"],
        "noun": ["Chord", "Rhythm", "Melody", "Tone", "Song", "Symphony"],
        "concept": ["Accord", "Unity", "Resonance", "Peace"],
        "names_pt": ["Acorde Fluente", "Ritmo Ressonante", "Melodia Melódica", "Tom Entrelaçado", "Canção Sincronizada", "Sinfonia Afinada", "Acorde Unificado", "Ritmo Celestial", "Concordância do Acorde", "Unidade do Ritmo", "Ressonância da Melodia", "Paz do Tom", "Concordância da Canção", "Unidade da Sinfonia", "Ressonância Celestial", "Paz Unificada", "Acorde Primordial", "Ritmo do Dao", "Melodia Suprema", "Tom Eterno"],
        "names_es": ["Acorde Fluido", "Ritmo Resonante", "Melodía Melódica", "Tono Entrelazado", "Canción Sincronizada", "Sinfonía Afinada", "Acorde Unificado", "Ritmo Celestial", "Concordancia del Acorde", "Unidad del Ritmo", "Resonancia de la Melodía", "Paz del Tono", "Concordancia de la Canción", "Unidad de la Sinfonía", "Resonancia Celestial", "Paz Unificada", "Acorde Primordial", "Ritmo del Dao", "Melodía Suprema", "Tono Eterno"],
    },

    # ── Primordial ──
    23: {  # Origin
        "adj": ["Nascent", "Primeval", "First", "Dawning", "Proto", "Archetypal", "Seedling", "Genesis"],
        "noun": ["Source", "Origin", "Beginning", "Dawn", "Root", "Seed"],
        "concept": ["Spark", "Birth", "Foundation", "Awakening"],
        "names_pt": ["Fonte Nascente", "Origem Primeva", "Princípio Primeiro", "Aurora Nascente", "Raiz Prototípica", "Semente Arquetípica", "Fonte Seminal", "Origem da Génese", "Centelha da Fonte", "Nascimento da Origem", "Fundação do Princípio", "Despertar da Aurora", "Centelha da Raiz", "Nascimento Arquetípico", "Fundação Seminal", "Despertar da Génese", "Fonte Primordial", "Origem do Dao", "Princípio Supremo", "Aurora Eterna"],
        "names_es": ["Fuente Naciente", "Origen Primevo", "Principio Primero", "Aurora Naciente", "Raíz Prototípica", "Semilla Arquetípica", "Fuente Seminal", "Origen del Génesis", "Centella de la Fuente", "Nacimiento del Origen", "Fundación del Principio", "Despertar de la Aurora", "Centella de la Raíz", "Nacimiento Arquetípico", "Fundación Seminal", "Despertar del Génesis", "Fuente Primordial", "Origen del Dao", "Principio Supremo", "Aurora Eterna"],
    },
    24: {  # Chaos
        "adj": ["Swirling", "Untamed", "Formless", "Rampant", "Writhing", "Unstable", "Primeval", "Consuming"],
        "noun": ["Chaos", "Maelstrom", "Entropy", "Turbulence", "Storm", "Flux"],
        "concept": ["Surge", "Upheaval", "Unraveling", "Abyss"],
        "names_pt": ["Caos Espiralante", "Maelstrom Indomado", "Entropia Informe", "Turbulência Desenfreada", "Tempestade Contorcida", "Fluxo Instável", "Caos Primevo", "Maelstrom Devorador", "Ímpeto do Caos", "Revolta do Maelstrom", "Desmantelamento da Entropia", "Abismo da Turbulência", "Ímpeto da Tempestade", "Revolta do Fluxo", "Desmantelamento Primevo", "Abismo Devorador", "Caos Primordial", "Maelstrom do Dao", "Entropia Suprema", "Turbulência Eterna"],
        "names_es": ["Caos Espiralante", "Maelstrom Indomado", "Entropía Informe", "Turbulencia Desenfrenada", "Tempestad Retorcida", "Flujo Inestable", "Caos Primevo", "Maelstrom Devorador", "Ímpetu del Caos", "Revuelta del Maelstrom", "Desenmarañamiento de la Entropía", "Abismo de la Turbulencia", "Ímpetu de la Tempestad", "Revuelta del Flujo", "Desenmarañamiento Primevo", "Abismo Devorador", "Caos Primordial", "Maelstrom del Dao", "Entropía Suprema", "Turbulencia Eterna"],
    },
    25: {  # Order
        "adj": ["Structured", "Immutable", "Crystallized", "Perfect", "Geometric", "Absolute", "Eternal", "Sovereign"],
        "noun": ["Law", "Rule", "Structure", "Pattern", "Pillar", "Foundation"],
        "concept": ["Decree", "Framework", "Mandate", "Axiom"],
        "names_pt": ["Lei Estruturada", "Regra Imutável", "Estrutura Cristalizada", "Padrão Perfeito", "Pilar Geométrico", "Fundação Absoluta", "Lei Eterna", "Regra Soberana", "Decreto da Lei", "Estrutura da Regra", "Mandato da Estrutura", "Axioma do Padrão", "Decreto do Pilar", "Estrutura Absoluta", "Mandato Eterno", "Axioma Soberano", "Lei Primordial", "Regra do Dao", "Estrutura Suprema", "Padrão Eterno"],
        "names_es": ["Ley Estructurada", "Regla Inmutable", "Estructura Cristalizada", "Patrón Perfecto", "Pilar Geométrico", "Fundación Absoluta", "Ley Eterna", "Regla Soberana", "Decreto de la Ley", "Estructura de la Regla", "Mandato de la Estructura", "Axioma del Patrón", "Decreto del Pilar", "Estructura Absoluta", "Mandato Eterno", "Axioma Soberano", "Ley Primordial", "Regla del Dao", "Estructura Suprema", "Patrón Eterno"],
    },

    # ── Supreme ──
    26: {  # Eternity
        "adj": ["Timeless", "Everlasting", "Perpetual", "Unending", "Deathless", "Infinite", "Undying", "Immortal"],
        "noun": ["Eternity", "Infinity", "Permanence", "Cycle", "Eon", "Epoch"],
        "concept": ["Endurance", "Persistence", "Legacy", "Transcendence"],
        "names_pt": ["Eternidade Atemporal", "Infinito Perpétuo", "Permanência Inesgotável", "Ciclo Imorredouro", "Éon Imortal", "Época Infindável", "Eternidade Imortal", "Infinito Perene", "Resistência da Eternidade", "Persistência do Infinito", "Legado da Permanência", "Transcendência do Ciclo", "Resistência do Éon", "Persistência Imortal", "Legado Perene", "Transcendência Infindável", "Eternidade Primordial", "Infinito do Dao", "Permanência Suprema", "Ciclo Eterno"],
        "names_es": ["Eternidad Atemporal", "Infinito Perpetuo", "Permanencia Inagotable", "Ciclo Imperecedero", "Eón Inmortal", "Época Interminable", "Eternidad Inmortal", "Infinito Perenne", "Resistencia de la Eternidad", "Persistencia del Infinito", "Legado de la Permanencia", "Trascendencia del Ciclo", "Resistencia del Eón", "Persistencia Inmortal", "Legado Perenne", "Trascendencia Interminable", "Eternidad Primordial", "Infinito del Dao", "Permanencia Suprema", "Ciclo Eterno"],
    },
    27: {  # Infinity
        "adj": ["Limitless", "Boundless", "Measureless", "Fathomless", "Unfathomed", "Vast", "Cosmic", "All-Encompassing"],
        "noun": ["Expanse", "Reach", "Scope", "Extent", "Immensity", "Cosmos"],
        "concept": ["Horizon", "Beyond", "Totality", "Omnipresence"],
        "names_pt": ["Expansão Ilimitada", "Alcance Sem Fim", "Âmbito Imensurável", "Extensão Insondável", "Imensidão Inexplorada", "Cosmos Vasto", "Expansão Cósmica", "Alcance Omnipresente", "Horizonte da Expansão", "Além do Alcance", "Totalidade do Âmbito", "Omnipresença da Extensão", "Horizonte da Imensidão", "Além do Cosmos", "Totalidade Cósmica", "Omnipresença Omnipresente", "Expansão Primordial", "Alcance do Dao", "Âmbito Supremo", "Extensão Eterna"],
        "names_es": ["Expansión Ilimitada", "Alcance Sin Fin", "Ámbito Inmensurable", "Extensión Insondable", "Inmensidad Inexplorada", "Cosmos Vasto", "Expansión Cósmica", "Alcance Omnipresente", "Horizonte de la Expansión", "Más Allá del Alcance", "Totalidad del Ámbito", "Omnipresencia de la Extensión", "Horizonte de la Inmensidad", "Más Allá del Cosmos", "Totalidad Cósmica", "Omnipresencia Total", "Expansión Primordial", "Alcance del Dao", "Ámbito Supremo", "Extensión Eterna"],
    },
    28: {  # Transcendence
        "adj": ["Ascending", "Rising", "Sublime", "Exalted", "Liberated", "Awakened", "Enlightened", "Supreme"],
        "noun": ["Ascension", "Liberation", "Awakening", "Enlightenment", "Nirvana", "Apex"],
        "concept": ["Flight", "Release", "Pinnacle", "Zenith"],
        "names_pt": ["Ascensão Ascendente", "Libertação Sublime", "Despertar Exaltado", "Iluminação Libertada", "Nirvana Desperta", "Ápice Iluminado", "Ascensão Suprema", "Libertação Sublime", "Voo da Ascensão", "Soltura da Libertação", "Pináculo do Despertar", "Zénite da Iluminação", "Voo do Nirvana", "Soltura do Ápice", "Pináculo Supremo", "Zénite Iluminado", "Ascensão Primordial", "Libertação do Dao", "Despertar Supremo", "Iluminação Eterna"],
        "names_es": ["Ascensión Ascendente", "Liberación Sublime", "Despertar Exaltado", "Iluminación Liberada", "Nirvana Despierta", "Ápice Iluminado", "Ascensión Suprema", "Liberación Sublimada", "Vuelo de la Ascensión", "Soltura de la Liberación", "Pináculo del Despertar", "Cénit de la Iluminación", "Vuelo del Nirvana", "Soltura del Ápice", "Pináculo Supremo", "Cénit Iluminado", "Ascensión Primordial", "Liberación del Dao", "Despertar Supremo", "Iluminación Eterna"],
    },
    29: {  # Heaven
        "adj": ["Celestial", "Heavenly", "Divine", "Sacred", "Holy", "Empyrean", "Hallowed", "Astral"],
        "noun": ["Decree", "Mandate", "Judgment", "Grace", "Radiance", "Authority"],
        "concept": ["Will", "Order", "Blessing", "Wrath"],
        "names_pt": ["Decreto Celestial", "Mandato Divino", "Julgamento Sagrado", "Graça Celestial", "Radiância Divina", "Autoridade Empírea", "Decreto Consagrado", "Mandato Astral", "Vontade do Decreto", "Ordem do Mandato", "Bênção do Julgamento", "Ira da Graça", "Vontade da Radiância", "Ordem Empírea", "Bênção Consagrada", "Ira Astral", "Decreto Primordial", "Mandato do Dao", "Julgamento Supremo", "Graça Eterna"],
        "names_es": ["Decreto Celestial", "Mandato Divino", "Juicio Sagrado", "Gracia Celestial", "Radiancia Divina", "Autoridad Empírea", "Decreto Consagrado", "Mandato Astral", "Voluntad del Decreto", "Orden del Mandato", "Bendición del Juicio", "Ira de la Gracia", "Voluntad de la Radiancia", "Orden Empírea", "Bendición Consagrada", "Ira Astral", "Decreto Primordial", "Mandato del Dao", "Juicio Supremo", "Gracia Eterna"],
    },
    30: {  # Fate
        "adj": ["Inevitable", "Predestined", "Inescapable", "Foretold", "Woven", "Unseen", "Karmic", "Prophetic"],
        "noun": ["Thread", "Destiny", "Path", "Wheel", "String", "Tapestry"],
        "concept": ["Knot", "Turning", "Crossroads", "Revelation"],
        "names_pt": ["Fio Inevitável", "Destino Predestinado", "Caminho Inescapável", "Roda Predita", "Corda Tecida", "Tapeçaria Invisível", "Fio Cármico", "Destino Profético", "Nó do Fio", "Virada do Destino", "Encruzilhada do Caminho", "Revelação da Roda", "Nó da Corda", "Virada da Tapeçaria", "Encruzilhada Cármica", "Revelação Profética", "Fio Primordial", "Destino do Dao", "Caminho Supremo", "Roda Eterna"],
        "names_es": ["Hilo Inevitable", "Destino Predestinado", "Camino Ineludible", "Rueda Predicha", "Cuerda Tejida", "Tapiz Invisible", "Hilo Kármico", "Destino Profético", "Nudo del Hilo", "Giro del Destino", "Encrucijada del Camino", "Revelación de la Rueda", "Nudo de la Cuerda", "Giro del Tapiz", "Encrucijada Kármica", "Revelación Profética", "Hilo Primordial", "Destino del Dao", "Camino Supremo", "Rueda Eterna"],
    },
}


# ── Phase 2 Expansion: 80 additional laws per path ────────────────────────────
# Generated from: {Prefix} {PathNoun} {Suffix}
# All with full PT/ES translations

_EXPAND_PREFIXES = {
    "common": [
        ("Lesser", "Menor", "Menor"), ("Minor", "Sutil", "Sutil"),
        ("Faint", "Fraco", "Débil"), ("Shallow", "Raso", "Somero"),
        ("Surface", "Superficial", "Superficial"), ("Thin", "Fino", "Fino"),
        ("Pale", "Pálido", "Pálido"), ("Raw", "Bruto", "Crudo"),
    ],
    "uncommon": [
        ("Steady", "Estável", "Estable"), ("Rising", "Crescente", "Creciente"),
        ("Clear", "Claro", "Claro"), ("True", "Verdadeiro", "Verdadero"),
        ("Bright", "Brilhante", "Brillante"), ("Deep", "Profundo", "Profundo"),
    ],
    "rare": [
        ("Greater", "Maior", "Mayor"), ("Grand", "Grande", "Gran"),
        ("Profound", "Insondável", "Insondable"), ("Ancient", "Ancestral", "Ancestral"),
    ],
    "epic": [
        ("Transcendent", "Transcendente", "Trascendente"),
        ("Supreme", "Supremo", "Supremo"),
        ("Celestial", "Celestial", "Celestial"),
    ],
    "legendary": [
        ("Primordial", "Primordial", "Primordial"),
        ("Eternal", "Eterno", "Eterno"),
    ],
}

_EXPAND_SUFFIXES = [
    ("Axiom", "Axioma", "Axioma"),
    ("Principle", "Princípio", "Principio"),
    ("Truth", "Verdade", "Verdad"),
    ("Mandate", "Mandato", "Mandato"),
    ("Edict", "Édito", "Edicto"),
    ("Tenet", "Preceito", "Precepto"),
    ("Canon", "Cânone", "Canon"),
    ("Decree", "Decreto", "Decreto"),
]

# Path-specific nouns (4 per path) with translations
_EXPAND_NOUNS = {
    1:  [("Flame", "Chama", "Llama"), ("Blaze", "Fogo", "Fuego"), ("Ember", "Brasa", "Brasa"), ("Inferno", "Inferno", "Infierno")],
    2:  [("Wave", "Onda", "Ola"), ("Tide", "Maré", "Marea"), ("Current", "Corrente", "Corriente"), ("Torrent", "Torrente", "Torrente")],
    3:  [("Bolt", "Raio", "Rayo"), ("Thunder", "Trovão", "Trueno"), ("Storm", "Tempestade", "Tempestad"), ("Spark", "Centelha", "Centella")],
    4:  [("Frost", "Geada", "Escarcha"), ("Glacier", "Glaciar", "Glaciar"), ("Shard", "Estilhaço", "Esquirla"), ("Blizzard", "Nevasca", "Nevada")],
    5:  [("Gale", "Vendaval", "Vendaval"), ("Breeze", "Brisa", "Brisa"), ("Cyclone", "Ciclone", "Ciclón"), ("Zephyr", "Zéfiro", "Céfiro")],
    6:  [("Void", "Vazio", "Vacío"), ("Abyss", "Abismo", "Abismo"), ("Null", "Nulo", "Nulo"), ("Vacuum", "Vácuo", "Vacuo")],
    7:  [("Rift", "Fenda", "Grieta"), ("Plane", "Plano", "Plano"), ("Realm", "Reino", "Reino"), ("Fabric", "Tecido", "Tejido")],
    8:  [("Horizon", "Horizonte", "Horizonte"), ("Expanse", "Vastidão", "Vastedad"), ("Vista", "Vista", "Vista"), ("Edge", "Borda", "Borde")],
    9:  [("Light", "Luz", "Luz"), ("Spring", "Nascente", "Manantial"), ("Balm", "Bálsamo", "Bálsamo"), ("Grace", "Graça", "Gracia")],
    10: [("Root", "Raiz", "Raíz"), ("Branch", "Ramo", "Rama"), ("Seed", "Semente", "Semilla"), ("Grove", "Bosque", "Bosque")],
    11: [("Pulse", "Pulso", "Pulso"), ("Blood", "Sangue", "Sangre"), ("Essence", "Essência", "Esencia"), ("Vigor", "Vigor", "Vigor")],
    12: [("Blade", "Lâmina", "Hoja"), ("Edge", "Fio", "Filo"), ("Sword", "Espada", "Espada"), ("Steel", "Aço", "Acero")],
    13: [("Fist", "Punho", "Puño"), ("Palm", "Palma", "Palma"), ("Strike", "Golpe", "Golpe"), ("Hammer", "Martelo", "Martillo")],
    14: [("Skin", "Pele", "Piel"), ("Bone", "Osso", "Hueso"), ("Shell", "Carapaça", "Caparazón"), ("Form", "Forma", "Forma")],
    15: [("Array", "Matriz", "Matriz"), ("Sigil", "Sigilo", "Sigilo"), ("Circle", "Círculo", "Círculo"), ("Node", "Nódulo", "Nódulo")],
    16: [("Spirit", "Espírito", "Espíritu"), ("Soul", "Alma", "Alma"), ("Ghost", "Fantasma", "Fantasma"), ("Wraith", "Espectro", "Espectro")],
    17: [("Thought", "Pensamento", "Pensamiento"), ("Mind", "Mente", "Mente"), ("Clarity", "Clareza", "Claridad"), ("Insight", "Percepção", "Percepción")],
    18: [("Will", "Vontade", "Voluntad"), ("Resolve", "Resolução", "Resolución"), ("Heart", "Coração", "Corazón"), ("Tenacity", "Tenacidade", "Tenacidad")],
    19: [("Clay", "Argila", "Arcilla"), ("Mold", "Molde", "Molde"), ("Blueprint", "Projeto", "Proyecto"), ("Genesis", "Génese", "Génesis")],
    20: [("Ruin", "Ruína", "Ruina"), ("Ash", "Cinza", "Ceniza"), ("Entropy", "Entropia", "Entropía"), ("Decay", "Decadência", "Decadencia")],
    21: [("Scale", "Balança", "Balanza"), ("Center", "Centro", "Centro"), ("Axis", "Eixo", "Eje"), ("Fulcrum", "Fulcro", "Fulcro")],
    22: [("Chord", "Acorde", "Acorde"), ("Rhythm", "Ritmo", "Ritmo"), ("Melody", "Melodia", "Melodía"), ("Song", "Canção", "Canción")],
    23: [("Source", "Fonte", "Fuente"), ("Origin", "Origem", "Origen"), ("Dawn", "Aurora", "Aurora"), ("Wellspring", "Manancial", "Manantial")],
    24: [("Chaos", "Caos", "Caos"), ("Maelstrom", "Maelstrom", "Maelstrom"), ("Flux", "Fluxo", "Flujo"), ("Vortex", "Vórtice", "Vórtice")],
    25: [("Order", "Ordem", "Orden"), ("Rule", "Regra", "Regla"), ("Pillar", "Pilar", "Pilar"), ("Structure", "Estrutura", "Estructura")],
    26: [("Eternity", "Eternidade", "Eternidad"), ("Eon", "Éon", "Eón"), ("Cycle", "Ciclo", "Ciclo"), ("Epoch", "Época", "Época")],
    27: [("Expanse", "Expansão", "Expansión"), ("Cosmos", "Cosmos", "Cosmos"), ("Scope", "Âmbito", "Ámbito"), ("Reach", "Alcance", "Alcance")],
    28: [("Ascension", "Ascensão", "Ascensión"), ("Nirvana", "Nirvana", "Nirvana"), ("Apex", "Ápice", "Ápice"), ("Zenith", "Zénite", "Cénit")],
    29: [("Edict", "Édito", "Edicto"), ("Judgment", "Julgamento", "Juicio"), ("Radiance", "Radiância", "Radiancia"), ("Authority", "Autoridade", "Autoridad")],
    30: [("Thread", "Fio", "Hilo"), ("Destiny", "Destino", "Destino"), ("Wheel", "Roda", "Rueda"), ("Tapestry", "Tapeçaria", "Tapiz")],
}


def _generate_phase1_laws(path_id: int, template: dict) -> list[dict]:
    """Generate the original 20 laws from Phase 1 templates (backwards compatible)."""
    adj = template["adj"]
    noun = template["noun"]
    concept = template["concept"]
    names_pt = template.get("names_pt", [])
    names_es = template.get("names_es", [])

    seen = set()
    names = []

    for a, n in itertools.product(adj, noun):
        name = f"{a} {n} Law"
        if name not in seen:
            seen.add(name)
            names.append(name)
        if len(names) >= 12:
            break

    for a, n, c in itertools.product(adj, noun, concept):
        name = f"{a} {noun[0]} {c} Law"
        if name not in seen:
            seen.add(name)
            names.append(name)
        if len(names) >= 20:
            break

    while len(names) < 20:
        for a, c in itertools.product(adj, concept):
            name = f"{a} {c} Law"
            if name not in seen:
                seen.add(name)
                names.append(name)
            if len(names) >= 20:
                break
        break

    names = names[:20]

    laws = []
    for i, name in enumerate(names):
        rarity = _RARITY_DIST_20[i] if i < len(_RARITY_DIST_20) else "common"
        laws.append({
            "path_id": path_id,
            "name": name,
            "name_pt": names_pt[i] if i < len(names_pt) else None,
            "name_es": names_es[i] if i < len(names_es) else None,
            "rarity": rarity,
            "min_realm": 5,
        })
    return laws


def _generate_phase2_laws(path_id: int, path_min_realm: int) -> list[dict]:
    """Generate 80 additional laws for Phase 2 expansion using systematic templates."""
    nouns = _EXPAND_NOUNS.get(path_id)
    if not nouns:
        return []

    laws = []
    rarity_counts = [("common", 32), ("uncommon", 24), ("rare", 16), ("epic", 6), ("legendary", 2)]

    for rarity, count in rarity_counts:
        prefixes = _EXPAND_PREFIXES[rarity]
        n_nouns = len(nouns)
        for i in range(count):
            prefix = prefixes[i // n_nouns % len(prefixes)]
            noun = nouns[i % n_nouns]
            suffix = _EXPAND_SUFFIXES[i % len(_EXPAND_SUFFIXES)]

            laws.append({
                "path_id": path_id,
                "name": f"{prefix[0]} {noun[0]} {suffix[0]}",
                "name_pt": f"{prefix[1]} {noun[1]} {suffix[1]}",
                "name_es": f"{prefix[2]} {noun[2]} {suffix[2]}",
                "rarity": rarity,
                "min_realm": path_min_realm,
            })

    return laws  # 80 laws


async def run_dao_3000_seeds(session: AsyncSession):
    """Seed 8 categories, 30 paths, 3000 laws (100 per path)."""

    # ── Categories ──
    existing_cats = set(
        (await session.execute(select(DaoCategory.id))).scalars().all()
    )
    cat_added = 0
    for c in CATEGORIES:
        if c["id"] not in existing_cats:
            session.add(DaoCategory(**c))
            cat_added += 1
    if cat_added:
        await session.flush()
    logger.info("☯️ Dao categories: %d new, %d existing", cat_added, len(CATEGORIES) - cat_added)

    # ── Paths (create or update total_laws) ──
    existing_paths = set(
        (await session.execute(select(DaoPath.id))).scalars().all()
    )
    path_added = 0
    for p in PATHS:
        data = {k: v for k, v in p.items()}
        data["total_laws"] = LAWS_PER_PATH
        if data["id"] not in existing_paths:
            session.add(DaoPath(**data))
            path_added += 1
        else:
            # Update total_laws for existing paths (Phase 1 → Full 3000)
            await session.execute(
                DaoPath.__table__.update()
                .where(DaoPath.__table__.c.id == data["id"])
                .values(total_laws=LAWS_PER_PATH)
            )
    if path_added:
        await session.flush()
    logger.info("☯️ Dao paths: %d new, %d existing (all updated to %d laws)", path_added, len(PATHS) - path_added, LAWS_PER_PATH)

    # ── Laws ──
    from sqlalchemy import func
    path_law_counts = dict(
        (await session.execute(
            select(DaoPathLaw.path_id, func.count(DaoPathLaw.id)).group_by(DaoPathLaw.path_id)
        )).all()
    )

    law_added = 0
    for path in PATHS:
        pid = path["id"]
        existing_count = path_law_counts.get(pid, 0)

        if existing_count >= LAWS_PER_PATH:
            continue  # Already fully seeded

        # Generate all 100 laws: 20 Phase 1 + 80 Phase 2
        phase1_template = PATH_TEMPLATES.get(pid)
        if not phase1_template:
            continue

        phase1_laws = _generate_phase1_laws(pid, phase1_template)
        phase2_laws = _generate_phase2_laws(pid, path["min_realm"])
        all_laws = phase1_laws + phase2_laws

        # Add only laws after what already exists
        for law in all_laws[existing_count:]:
            law["min_realm"] = path["min_realm"]
            session.add(DaoPathLaw(**law))
            law_added += 1

    if cat_added or path_added or law_added:
        await session.commit()
        logger.info("☯️ Seeded dao 3000: %d cats, %d paths, %d laws (target: %d)", cat_added, path_added, law_added, LAWS_PER_PATH * len(PATHS))
    else:
        logger.info("☯️ All %d dao path laws already exist", LAWS_PER_PATH * len(PATHS))

    # ── Retroactive catch-up for veteran players ──
    await _retroactive_catchup(session)


# Rarity weights for retroactive grant (same as dao_laws_engine)
_RETRO_WEIGHTS = {"common": 50, "uncommon": 30, "rare": 15, "epic": 4, "legendary": 1}


async def _retroactive_catchup(session: AsyncSession):
    """
    One-time grant of 3000 Laws discoveries for veteran players.
    Runs on every startup but only affects players who:
    - Have realm >= 5 (Dao unlocked)
    - Have completed at least 1 Supreme Law
    - Have 0 discoveries in the 3000 Laws system
    Formula: completed_supreme_laws × 25 + (realm - 5) × 15
    """
    from database.models import Player, PlayerDaoFragment

    # Find players with completed supreme laws
    stmt = (
        select(
            Player.telegram_id,
            Player.realm,
            Player.perception,
            func.count(PlayerDaoFragment.dao_law_id).label("completed_count"),
        )
        .join(PlayerDaoFragment, PlayerDaoFragment.player_id == Player.telegram_id)
        .where(Player.realm >= 5, PlayerDaoFragment.is_completed == True)
        .group_by(Player.telegram_id, Player.realm, Player.perception)
    )
    veterans = (await session.execute(stmt)).all()
    if not veterans:
        return

    total_granted = 0
    for player_id, realm, perception, completed_supreme in veterans:
        # Calculate expected retroactive grant
        expected = completed_supreme * 25 + max(0, realm - 5) * 15
        if expected <= 0:
            continue

        # Check how many they already have — skip if already caught up
        existing = (await session.execute(
            select(func.count(PlayerDaoDiscovery.law_id))
            .where(PlayerDaoDiscovery.player_id == player_id)
        )).scalar() or 0
        if existing >= expected:
            continue

        grant_count = expected - existing  # Only grant the difference

        # Get all accessible undiscovered laws (excluding already discovered)
        accessible_paths = (await session.execute(
            select(DaoPath.id).where(DaoPath.min_realm <= realm)
        )).scalars().all()
        if not accessible_paths:
            continue

        already_discovered_ids = set(
            (await session.execute(
                select(PlayerDaoDiscovery.law_id).where(PlayerDaoDiscovery.player_id == player_id)
            )).scalars().all()
        )

        stmt_undiscovered = select(DaoPathLaw).where(DaoPathLaw.path_id.in_(accessible_paths))
        if already_discovered_ids:
            stmt_undiscovered = stmt_undiscovered.where(DaoPathLaw.id.notin_(already_discovered_ids))
        undiscovered = (await session.execute(stmt_undiscovered)).scalars().all()
        if not undiscovered:
            continue

        # Weight by rarity — higher perception shifts towards rarer laws
        perception_factor = min((perception or 100) / 5000.0, 2.0)
        weights = []
        for law in undiscovered:
            base_w = _RETRO_WEIGHTS.get(law.rarity, 50)
            if law.rarity in ("rare", "epic", "legendary"):
                weights.append(base_w * perception_factor)
            else:
                weights.append(base_w)

        # Pick unique laws (no duplicates)
        grant_count = min(grant_count, len(undiscovered))
        chosen = []
        remaining = list(range(len(undiscovered)))
        remaining_weights = list(weights)
        now = datetime.now(timezone.utc)

        for _ in range(grant_count):
            if not remaining:
                break
            picks = random.choices(range(len(remaining)), weights=remaining_weights, k=1)
            idx = picks[0]
            chosen.append(undiscovered[remaining[idx]])
            remaining.pop(idx)
            remaining_weights.pop(idx)

        for law in chosen:
            session.add(PlayerDaoDiscovery(
                player_id=player_id,
                law_id=law.id,
                discovered_at=now,
            ))
        total_granted += len(chosen)
        logger.info("☯️ Retroactive catch-up: player %s granted %d discoveries (realm=%d, supreme=%d)",
                     player_id, len(chosen), realm, completed_supreme)

    if total_granted:
        await session.commit()
        logger.info("☯️ Retroactive catch-up complete: %d total discoveries granted", total_granted)
    else:
        logger.info("☯️ No retroactive catch-up needed")
