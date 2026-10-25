"""
Heavenly Dao Laws (F-11.5) — 10 paths × 10 laws = 100 laws.

Category 9 ("Heavenly Dao") is tier 5 exclusive and sits on top of the existing
8 categories of 3000 Dao Laws. Paths are gated by the 1st Celestial Trial being
passed (checked at the engine level), not only by min_realm.

IDs are chosen far above existing ones to guarantee no collision:
  - category id: 9
  - path ids:    101..110
  - law ids:     autoincrement, inserted idempotently
"""
import logging
import itertools
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DaoCategory, DaoPath, DaoPathLaw

logger = logging.getLogger(__name__)


HEAVENLY_CATEGORY = {
    "id": 9,
    "name": "Heavenly Dao",
    "name_pt": "Dao Celestial",
    "name_es": "Dao Celestial",
    "emoji": "🌠",
    "min_realm": 8,
    "bonus_type": "all_mult",
    "sort_order": 9,
    "description": "The Hundred Heavenly Laws — tier 5 paths revealed only to those who passed the first Celestial Trial.",
    "is_heavenly": True,
}

# Each path yields a bonus_type already mapped by get_dao_laws_bonuses.
HEAVENLY_PATHS = [
    {"id": 101, "category_id": 9, "name": "Path of Karma",         "name_pt": "Caminho do Karma",         "name_es": "Camino del Karma",          "emoji": "☯️", "element": "Primordial", "min_realm": 8, "bonus_type": "all_mult",  "sort_order": 1, "is_heavenly": True},
    {"id": 102, "category_id": 9, "name": "Path of Fate",          "name_pt": "Caminho do Destino",       "name_es": "Camino del Destino",        "emoji": "🎴", "element": "Primordial", "min_realm": 8, "bonus_type": "all_stats", "sort_order": 2, "is_heavenly": True},
    {"id": 103, "category_id": 9, "name": "Path of Starlight",     "name_pt": "Caminho da Luz Estelar",   "name_es": "Camino de la Luz Estelar",  "emoji": "✨", "element": "Primordial", "min_realm": 8, "bonus_type": "cb_mult",   "sort_order": 3, "is_heavenly": True},
    {"id": 104, "category_id": 9, "name": "Path of Reincarnation", "name_pt": "Caminho da Reencarnação",  "name_es": "Camino de la Reencarnación", "emoji": "🔄", "element": "Primordial", "min_realm": 8, "bonus_type": "hp_regen",  "sort_order": 4, "is_heavenly": True},
    {"id": 105, "category_id": 9, "name": "Path of Void",          "name_pt": "Caminho do Vazio Supremo", "name_es": "Camino del Vacío Supremo",  "emoji": "🌀", "element": "Primordial", "min_realm": 8, "bonus_type": "cooldown_reduction", "sort_order": 5, "is_heavenly": True},
    {"id": 106, "category_id": 9, "name": "Path of Eternity",      "name_pt": "Caminho da Eternidade",    "name_es": "Camino de la Eternidad",    "emoji": "♾️", "element": "Primordial", "min_realm": 8, "bonus_type": "all_mult",  "sort_order": 6, "is_heavenly": True},
    {"id": 107, "category_id": 9, "name": "Path of Balance",       "name_pt": "Caminho do Equilíbrio Heavenly", "name_es": "Camino del Equilibrio Celestial", "emoji": "⚖️", "element": "Primordial", "min_realm": 8, "bonus_type": "all_stats", "sort_order": 7, "is_heavenly": True},
    {"id": 108, "category_id": 9, "name": "Path of Sovereignty",   "name_pt": "Caminho da Soberania",     "name_es": "Camino de la Soberanía",    "emoji": "👑", "element": "Primordial", "min_realm": 8, "bonus_type": "bp_mult",   "sort_order": 8, "is_heavenly": True},
    {"id": 109, "category_id": 9, "name": "Path of Origin",        "name_pt": "Caminho da Origem Heavenly", "name_es": "Camino del Origen Celestial", "emoji": "🌟", "element": "Primordial", "min_realm": 8, "bonus_type": "tribulation_bonus", "sort_order": 9, "is_heavenly": True},
    {"id": 110, "category_id": 9, "name": "Path of Judgment",      "name_pt": "Caminho do Julgamento",    "name_es": "Camino del Juicio",         "emoji": "⚡", "element": "Primordial", "min_realm": 8, "bonus_type": "bp_mult",   "sort_order": 10, "is_heavenly": True},
]

# Laws per path (10): exact flavour, tier 5. Rarities: 3 common, 3 uncommon, 2 rare, 1 epic, 1 legendary.
_HEAVENLY_RARITY_DIST = ["common"] * 3 + ["uncommon"] * 3 + ["rare"] * 2 + ["epic"] * 1 + ["legendary"] * 1
LAWS_PER_HEAVENLY_PATH = 10

# Ten hand-written names per path in three languages. Indexed 0..9 — aligned with rarity dist above.
HEAVENLY_LAW_NAMES = {
    101: {  # Karma
        "en": ["Seed of Karma", "Debt of the Soul", "Bond of Cause", "Wheel of Return", "Mirror of Actions", "Weight of Sins", "Scale of Virtue", "Golden Thread of Fate", "Judgment of Ten Thousand Lives", "Karma Eternal"],
        "pt": ["Semente do Karma", "Dívida da Alma", "Elo da Causa", "Roda do Retorno", "Espelho das Ações", "Peso dos Pecados", "Balança da Virtude", "Fio Dourado do Destino", "Julgamento das Dez Mil Vidas", "Karma Eterno"],
        "es": ["Semilla del Karma", "Deuda del Alma", "Lazo de la Causa", "Rueda del Retorno", "Espejo de las Acciones", "Peso de los Pecados", "Balanza de la Virtud", "Hilo Dorado del Destino", "Juicio de las Diez Mil Vidas", "Karma Eterno"],
    },
    102: {  # Fate
        "en": ["Whisper of Fate", "Thread of Destiny", "Weaving of Lives", "Inevitable Step", "Mirror of Fortune", "Chain of Moments", "Oracle's Sight", "Loom of the Heavens", "Sovereign Verdict", "Fate Unbound"],
        "pt": ["Sussurro do Destino", "Fio do Destino", "Tecer das Vidas", "Passo Inevitável", "Espelho da Fortuna", "Corrente dos Momentos", "Visão do Oráculo", "Tear dos Céus", "Veredito Soberano", "Destino Livre"],
        "es": ["Susurro del Destino", "Hilo del Destino", "Tejido de las Vidas", "Paso Inevitable", "Espejo de la Fortuna", "Cadena de los Momentos", "Visión del Oráculo", "Telar de los Cielos", "Veredicto Soberano", "Destino Libre"],
    },
    103: {  # Starlight
        "en": ["Ray of the Dawn Star", "Cradle of Constellations", "Light of Dead Stars", "Meteor Blade", "Cosmic Lantern", "Stellar Stream", "Firmament's Sigh", "Comet of Memory", "Throne of Stars", "Starlight Sovereign"],
        "pt": ["Raio da Estrela da Aurora", "Berço das Constelações", "Luz das Estrelas Mortas", "Lâmina Meteoro", "Lanterna Cósmica", "Corrente Estelar", "Suspiro do Firmamento", "Cometa da Memória", "Trono das Estrelas", "Soberano da Luz Estelar"],
        "es": ["Rayo de la Estrella del Alba", "Cuna de Constelaciones", "Luz de Estrellas Muertas", "Hoja Meteoro", "Linterna Cósmica", "Corriente Estelar", "Suspiro del Firmamento", "Cometa de la Memoria", "Trono de Estrellas", "Soberano de la Luz Estelar"],
    },
    104: {  # Reincarnation
        "en": ["Cycle of Breath", "Memory of Past Lives", "River of Souls", "Return of the Forgotten", "Veil Between Worlds", "Ninefold Wheel", "Mother of Reincarnation", "Gate of Rebirth", "Lord of Cycles", "Samsara Unchained"],
        "pt": ["Ciclo do Sopro", "Memória de Vidas Passadas", "Rio das Almas", "Retorno do Esquecido", "Véu entre Mundos", "Roda Nónupla", "Mãe da Reencarnação", "Portão do Renascimento", "Senhor dos Ciclos", "Samsara Livre"],
        "es": ["Ciclo del Aliento", "Memoria de Vidas Pasadas", "Río de las Almas", "Retorno del Olvidado", "Velo entre Mundos", "Rueda Nónuple", "Madre de la Reencarnación", "Puerta del Renacimiento", "Señor de los Ciclos", "Samsara Libre"],
    },
    105: {  # Void
        "en": ["Breath of the Void", "Silent Step", "Depthless Eye", "Hollow Dominion", "Voidwalker's Sigh", "Empty Throne", "Consuming Horizon", "Abyss Beneath Abyss", "Void Sovereign", "Unmade Dao"],
        "pt": ["Sopro do Vazio", "Passo Silencioso", "Olho Insondável", "Domínio Oco", "Suspiro do Caminhante do Vazio", "Trono Vazio", "Horizonte Devorador", "Abismo sob o Abismo", "Soberano do Vazio", "Dao Desfeito"],
        "es": ["Aliento del Vacío", "Paso Silencioso", "Ojo Insondable", "Dominio Hueco", "Suspiro del Caminante del Vacío", "Trono Vacío", "Horizonte Devorador", "Abismo bajo el Abismo", "Soberano del Vacío", "Dao Deshecho"],
    },
    106: {  # Eternity
        "en": ["First Grain of Time", "Endless Hour", "Hymn of Ages", "Hall of Forever", "Clockwork Oblivion", "Eternal Pillar", "Witness of All Eras", "Scripture of Forever", "Empress of Time", "Eternity Without End"],
        "pt": ["Primeiro Grão do Tempo", "Hora Sem Fim", "Hino das Eras", "Salão do Sempre", "Esquecimento do Relógio", "Pilar Eterno", "Testemunha das Eras", "Escritura do Sempre", "Imperatriz do Tempo", "Eternidade Sem Fim"],
        "es": ["Primer Grano del Tiempo", "Hora sin Fin", "Himno de las Eras", "Salón del Siempre", "Olvido del Reloj", "Pilar Eterno", "Testigo de las Eras", "Escritura del Siempre", "Emperatriz del Tiempo", "Eternidad sin Fin"],
    },
    107: {  # Balance
        "en": ["Still Axis", "Two Sides of Heaven", "Middle Road", "Fulcrum of Worlds", "Quiet Scale", "Perfect Measure", "Keeper of Opposites", "Heartbeat of Balance", "Arbiter of All Paths", "Balance Supreme"],
        "pt": ["Eixo Imóvel", "Dois Lados do Céu", "Caminho do Meio", "Fulcro dos Mundos", "Balança Silenciosa", "Medida Perfeita", "Guardião dos Opostos", "Batimento do Equilíbrio", "Árbitro de Todos os Caminhos", "Equilíbrio Supremo"],
        "es": ["Eje Inmóvil", "Dos Lados del Cielo", "Camino del Medio", "Fulcro de los Mundos", "Balanza Silenciosa", "Medida Perfecta", "Guardián de los Opuestos", "Latido del Equilibrio", "Árbitro de Todos los Caminos", "Equilibrio Supremo"],
    },
    108: {  # Sovereignty
        "en": ["Born to Rule", "Crown of Unmade Kings", "Pillars of the Throne", "Shadow of the Emperor", "Edict Unbroken", "Scepter of Ten Directions", "Banner of One Hundred Worlds", "Dominion Without Equal", "Imperial Dao", "Sovereign Absolute"],
        "pt": ["Nascido para Reinar", "Coroa dos Reis Desfeitos", "Pilares do Trono", "Sombra do Imperador", "Édito Inquebrável", "Cetro das Dez Direções", "Estandarte dos Cem Mundos", "Domínio Sem Igual", "Dao Imperial", "Soberano Absoluto"],
        "es": ["Nacido para Reinar", "Corona de Reyes Deshechos", "Pilares del Trono", "Sombra del Emperador", "Edicto Inquebrantable", "Cetro de las Diez Direcciones", "Estandarte de Cien Mundos", "Dominio sin Igual", "Dao Imperial", "Soberano Absoluto"],
    },
    109: {  # Origin
        "en": ["First Spark", "Nameless Source", "Dawn Before Dawn", "Seed of Worlds", "Mother of All Rivers", "Primordial Breath", "Unwritten Word", "Root of the Heavens", "Genesis Without Cause", "Origin of All Dao"],
        "pt": ["Primeira Centelha", "Fonte Sem Nome", "Alvorecer antes do Alvorecer", "Semente dos Mundos", "Mãe de Todos os Rios", "Sopro Primordial", "Palavra Não Escrita", "Raiz dos Céus", "Génese Sem Causa", "Origem de Todo o Dao"],
        "es": ["Primera Centella", "Fuente sin Nombre", "Alba antes del Alba", "Semilla de los Mundos", "Madre de Todos los Ríos", "Aliento Primordial", "Palabra No Escrita", "Raíz de los Cielos", "Génesis sin Causa", "Origen de Todo el Dao"],
    },
    110: {  # Judgment
        "en": ["Weighing Eye", "Voice of the Verdict", "Scale of Heaven", "Sword of Truth", "Court of Ten Thousand", "Witness of the Silent", "Executioner's Dao", "Final Hour", "Throne of Arbiter", "Judgment Unopposed"],
        "pt": ["Olho que Pesa", "Voz do Veredito", "Balança do Céu", "Espada da Verdade", "Corte dos Dez Mil", "Testemunha dos Silenciosos", "Dao do Carrasco", "Hora Final", "Trono do Árbitro", "Julgamento Inoposto"],
        "es": ["Ojo que Pesa", "Voz del Veredicto", "Balanza del Cielo", "Espada de la Verdad", "Corte de los Diez Mil", "Testigo de los Silenciosos", "Dao del Verdugo", "Hora Final", "Trono del Árbitro", "Juicio Inopuesto"],
    },
}


async def run_heavenly_seeds(session: AsyncSession):
    """Seed category 9 + 10 heavenly paths + 100 laws. Idempotent."""

    # Category ─────────────────────────────────────────────────────────────
    cat_row = (await session.execute(
        select(DaoCategory).where(DaoCategory.id == HEAVENLY_CATEGORY["id"])
    )).scalar_one_or_none()
    if cat_row is None:
        session.add(DaoCategory(**HEAVENLY_CATEGORY))
    else:
        changed = False
        for k, v in HEAVENLY_CATEGORY.items():
            if k != "id" and getattr(cat_row, k) != v:
                setattr(cat_row, k, v)
                changed = True
        if changed:
            logger.info("🌠 Heavenly category updated")

    # Paths ────────────────────────────────────────────────────────────────
    added_paths = 0
    for path in HEAVENLY_PATHS:
        path["total_laws"] = LAWS_PER_HEAVENLY_PATH
        row = (await session.execute(
            select(DaoPath).where(DaoPath.id == path["id"])
        )).scalar_one_or_none()
        if row is None:
            session.add(DaoPath(**path))
            added_paths += 1
        else:
            for k, v in path.items():
                if k != "id" and getattr(row, k) != v:
                    setattr(row, k, v)

    await session.flush()

    # Laws ─────────────────────────────────────────────────────────────────
    # Idempotent per-path: skip if the path already has its 10 laws.
    added_laws = 0
    for path in HEAVENLY_PATHS:
        existing = (await session.execute(
            select(func.count(DaoPathLaw.id)).where(DaoPathLaw.path_id == path["id"])
        )).scalar() or 0
        if existing >= LAWS_PER_HEAVENLY_PATH:
            continue

        names = HEAVENLY_LAW_NAMES[path["id"]]
        # Pick up from where we left off, in case a prior seed run was interrupted.
        for idx in range(existing, LAWS_PER_HEAVENLY_PATH):
            rarity = _HEAVENLY_RARITY_DIST[idx]
            session.add(DaoPathLaw(
                path_id=path["id"],
                name=names["en"][idx],
                name_pt=names["pt"][idx],
                name_es=names["es"][idx],
                rarity=rarity,
                min_realm=8,
                description=None,
            ))
            added_laws += 1

    if added_paths or added_laws:
        logger.info("🌠 Seeded %d new heavenly paths and %d new heavenly laws", added_paths, added_laws)

    await session.commit()
