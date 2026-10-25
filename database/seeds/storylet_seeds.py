# -*- coding: utf-8 -*-
"""MV-5 Mundo Vivo v2 — Quests VIVAS: o catálogo de storylets (seed).

35 storylets: 20 do MV-5/MV-6/MV-8 (sorteados pelo pacer) + os 15 ENCARGOS 城务
do MV-9 (três por cidade, `weight: 0` ⇒ fora do sorteio, AFIXADOS na cidade —
ver o bloco comentado no fim da lista). A contagem dizia "16" desde julho e já
estava errada em 4 antes desta onda.

Os 20 sorteáveis (Lei §3 — poucos e com nuance) cobrem: sitiada (defesa/escolta),
tensa (vigília), festival (encomenda/mercador), maré ativa (caçada urgente),
meteoro (corrida ao céu), karma sombrio (proposta demoníaca — o fork moral vive
na OFERTA: aceitar É a escolha; recusar é livre, Lei §1), redenção (o Mendigo),
Mòyǔ (proibido), meridianos (o mestre de corpo nota seus canais) e 4 âncoras
continentais + 1 fallback de baixo peso (o mundo sempre TEM algo a dizer).

Regras eternas respeitadas:
  * objective_type SEMPRE da lista viva de trackers (track_quest — lição MV-1:
    nunca deep-linkar objetivo sem tracker). Evitados: boss_attack (só qua/sáb —
    conflita com prazo), tribulation_survive (raro demais p/ deadline),
    sect_contribution (dead-end p/ quem não tem guilda — Lei §1).
  * reward: pedras / itens NATIVOS (herb/ore ids existentes) / karma.
    NUNCA técnica (Lei §12), NUNCA jade (Lei §4).
  * requirements declarativos (ver core/storylet_engine.storylet_available).
  * nomes/descrições/diálogos server-resolved: sty_<key>_name/_desc/_d1/_d2
    nos locales de CHAT (injetados por scripts/inject_mv5_i18n.py).

Upsert verdadeiro (padrão dungeon_quest_seeds + regra seed-sync do CLAUDE.md):
insere ausentes E sobrescreve todos os campos dos existentes, com flag_modified
nos JSONB. Corre por mundo no init_world_db (multi-server).

IMPORTANTE (review fix MV-5): storylet_engine._tracked_types() prefiltra o
gancho do track_quest com o set de objective_types DESTE ficheiro (hot-path:
`login` dispara a cada interação). Um storylet inserido por SQL à mão com um
objective_type que não exista aqui NÃO trackearia — conteúdo novo entra SEMPRE
pelos seeds (convenção do projeto).
"""

import logging

from sqlalchemy.orm.attributes import flag_modified

from database.models import StoryletCatalog

logger = logging.getLogger(__name__)


STORYLET_SEEDS: list[dict] = [
    # ── O mundo em crise: sitiada / tensa (estados do MV-3) ────────────────
    {
        "key": "defesa_sitiada", "giver_kind": "npc_cultivator", "emoji": "🛡️",
        "requirements": {"region_state": ["sitiada"], "realm_min": 1},
        "objective_type": "npc_combat", "objective_count": 5,
        "reward": {"stones": 900, "karma": 10},
        "expires_hours": 48, "weight": 14,
    },
    {
        "key": "escolta_sitiada", "giver_kind": "service_npc", "emoji": "🏮",
        "requirements": {"region_state": ["sitiada", "tensa"], "realm_min": 2},
        "objective_type": "beast_expedition", "objective_count": 2,
        "reward": {"stones": 700},
        "expires_hours": 72, "weight": 8,
    },
    {
        # BUGFIX 2026-07-27 ([jogador], s2): era objective_type="sparring" — o ÚNICO
        # storylet dependente de OUTRO jogador (sparring só conta no fluxo de 2
        # jogadores; track_quest("sparring") nunca dispara vs NPC). Num servidor
        # pequeno sem parceiro = dead-end com timer (lição MV-6: nunca objetivo
        # que depende de outro jogador ao vivo). Trocado para "npc_combat" —
        # solo-completável e MAIS temático ("confrontar os inquietos" numa
        # região tensa). O runner é upsert (sincroniza objective_type a cada
        # boot) e track_storylets casa pelo catálogo AO VIVO → a instância já
        # aceita do jogador passa a progredir com os NPCs que ele já enfrenta.
        "key": "vigilia_tensa", "giver_kind": "npc_cultivator", "emoji": "⚡",
        "requirements": {"region_state": ["tensa"]},
        "objective_type": "npc_combat", "objective_count": 2,
        "reward": {"stones": 500, "karma": 5},
        "expires_hours": 48, "weight": 10,
    },
    # ── A 🚩 Bandeira: ocupada (5º estado, causado pela marcha do MV-8) ────
    # DÍVIDA DE CONTEÚDO OBRIGATÓRIA, não enfeite: o matcher exige pertença
    # EXATA à lista de `region_state`, e nenhum dos 18 seeds anteriores cita
    # "ocupada". Sem estes dois, um continente ocupado passaria as 72h da
    # ocupação com TODOS os storylets de lugar mudos — o mundo mais vivo do
    # jogo seria também o mais calado. (O runner de storylet é upsert completo,
    # então não há dívida de bloco de SYNC como a das quests de seita.)
    {
        "key": "bandeira_estrangeira", "giver_kind": "npc_cultivator", "emoji": "🚩",
        "requirements": {"region_state": ["ocupada"]},
        "objective_type": "npc_combat", "objective_count": 4,
        "reward": {"stones": 850, "karma": 5},
        "expires_hours": 48, "weight": 14,
    },
    {
        "key": "pedagio_da_ocupacao", "giver_kind": "service_npc", "emoji": "🏮",
        "requirements": {"region_state": ["ocupada"]},
        "objective_type": "craft_pill", "objective_count": 3,
        "reward": {"stones": 600},
        "expires_hours": 48, "weight": 10,
    },
    # ── O mundo em festa: festival (estado do MV-3) ────────────────────────
    {
        "key": "festival_encomenda", "giver_kind": "service_npc", "emoji": "🎊",
        "requirements": {"region_state": ["festival"]},
        "objective_type": "craft_pill", "objective_count": 3,
        "reward": {"stones": 500, "items": [{"type": "herb", "id": 9, "qty": 2}]},
        "expires_hours": 48, "weight": 12,
    },
    {
        "key": "festival_mercador", "giver_kind": "service_npc", "emoji": "💰",
        "requirements": {"region_state": ["festival"]},
        "objective_type": "use_pill", "objective_count": 2,
        "reward": {"stones": 400},
        "expires_hours": 48, "weight": 8,
    },
    # ── O Céu se move: eventos ativos do Tiandao (MV-2) ────────────────────
    {
        "key": "mare_cacada", "giver_kind": "npc_cultivator", "emoji": "🌊",
        "requirements": {"world_event": "beast_tide"},
        "objective_type": "npc_combat", "objective_count": 3,
        "reward": {"stones": 800, "karma": 5},
        "expires_hours": 24, "weight": 14,
    },
    {
        "key": "meteoro_corrida", "giver_kind": "npc_cultivator", "emoji": "☄️",
        "requirements": {"world_event": "meteor"},
        "objective_type": "cultivate", "objective_count": 60,
        "reward": {"stones": 600},
        "expires_hours": 24, "weight": 12,
    },
    # ── Karma: a proposta sombria (fork moral NA OFERTA) e a redenção ──────
    {
        "key": "proposta_sombria", "giver_kind": "npc_cultivator", "emoji": "😈",
        "requirements": {"karma_min": -1000, "karma_max": -100},
        "objective_type": "npc_combat", "objective_count": 4,
        "reward": {"stones": 1200, "karma": -15},
        "expires_hours": 48, "weight": 8,
    },
    {
        "key": "redencao_mendigo", "giver_kind": "mendigo", "emoji": "🕯️",
        "requirements": {"karma_min": -400, "karma_max": -50},
        "objective_type": "cultivate", "objective_count": 90,
        "reward": {"karma": 20},
        "expires_hours": 72, "weight": 6,
    },
    # ── Mòyǔ: o continente proibido fala com os seus ───────────────────────
    {
        "key": "moyu_colheita", "giver_kind": "npc_cultivator", "emoji": "🌑",
        "requirements": {"continent": ["moyu"], "path": ["demonic"]},
        "objective_type": "dungeon_floor", "objective_count": 6,
        "reward": {"stones": 1500},
        "expires_hours": 72, "weight": 8,
    },
    # ── Meridianos: o mestre de corpo nota seus canais (MV-4) ──────────────
    # 2026-07-21 (report [jogador], s2): objective era `sparring` — que só trackeia
    # no settle do sparring CONSENTIDO entre jogadores; num servidor de
    # população baixa (+ gate de rank nos desafios) é dead-end prático (a
    # MESMA classe que excluiu sect_contribution no MV-5). `npc_combat`
    # trackeia na caça NPC ×2 superfícies + settle PvE — soloável sempre.
    # O re-seed atualiza o catálogo no boot; rows aceitas passam a progredir
    # (o track lê o objective_type do CATÁLOGO via join).
    {
        "key": "mestre_do_corpo", "giver_kind": "mendigo", "emoji": "⛩️",
        "requirements": {"meridians_min": 1, "flag": "corpo_profundo"},
        "objective_type": "npc_combat", "objective_count": 3,
        "reward": {"stones": 800, "karma": 5},
        "expires_hours": 72, "weight": 8,
    },
    # ── Âncoras continentais (a geografia fala) ────────────────────────────
    {
        "key": "cacada_linghe", "giver_kind": "npc_cultivator", "emoji": "🏔️",
        "requirements": {"continent": ["linghe"], "realm_max": 3},
        "objective_type": "npc_combat", "objective_count": 3,
        "reward": {"stones": 400},
        "expires_hours": 48, "weight": 10,
    },
    {
        "key": "alquimia_yanshan", "giver_kind": "service_npc", "emoji": "🌸",
        "requirements": {"continent": ["yanshan"]},
        "objective_type": "craft_pill", "objective_count": 4,
        "reward": {"stones": 700, "items": [{"type": "herb", "id": 12, "qty": 2}]},
        "expires_hours": 72, "weight": 9,
    },
    {
        "key": "arena_fenghuo", "giver_kind": "npc_cultivator", "emoji": "🌋",
        "requirements": {"continent": ["fenghuo"], "realm_min": 2},
        "objective_type": "arena_win", "objective_count": 2,
        "reward": {"stones": 900},
        "expires_hours": 72, "weight": 9,
    },
    {
        "key": "abismo_qianhe", "giver_kind": "service_npc", "emoji": "⛰️",
        "requirements": {"continent": ["qianhe"], "realm_min": 1},
        "objective_type": "dungeon_floor", "objective_count": 8,
        "reward": {"stones": 850},
        "expires_hours": 72, "weight": 9,
    },
    # ── Fallback de baixo peso: o mundo sempre tem UMA voz (Lei §1) ────────
    {
        "key": "peregrino_do_rio", "giver_kind": "mendigo", "emoji": "🧘",
        "requirements": {},
        "objective_type": "cultivate", "objective_count": 120,
        "reward": {"stones": 500},
        "expires_hours": 72, "weight": 4,
    },
    # ── MV-6: só um NOME CONHECIDO recebe (region_rep_min — a rep abre portas;
    # `flag` explicita a dependência do irmão, e o fail-closed do avaliador já
    # protegeria de qualquer forma: flag OFF → rep 0 → nunca oferece) ─────────
    {
        # O magistrado local confia uma caçada delicada a quem já provou o nome.
        "key": "confianca_do_magistrado", "giver_kind": "service_npc", "emoji": "🏮",
        "requirements": {"region_rep_min": 25, "flag": "reputacao_rival"},
        "objective_type": "npc_combat", "objective_count": 4,
        "reward": {"stones": 1100, "karma": 10},
        "expires_hours": 72, "weight": 8,
    },
    {
        # Um ancião só abre o cofre de encomendas para um nome REVERENCIADO.
        "key": "encomenda_do_anciao", "giver_kind": "npc_cultivator", "emoji": "🎐",
        "requirements": {"region_rep_min": 50, "flag": "reputacao_rival"},
        "objective_type": "forge_artifact", "objective_count": 2,
        "reward": {"stones": 1400, "items": [{"type": "ore", "id": 6, "qty": 2}]},
        "expires_hours": 96, "weight": 7,
    },

    # ══════════════════════════════════════════════════════════════════════
    # MV-9 城 — OS ENCARGOS 城务 (o pedido PERMANENTE de cada cidade)
    # ══════════════════════════════════════════════════════════════════════
    # Estes 15 são storylets com DONO FIXO: três por cidade, e
    # `core.city_engine.encargo_key_for` escolhe qual está vigente em cada
    # batimento de 6h — derivado de (world_key, continent, tick), modulado pelo
    # estado regional (MV-3) e pelo evento do Céu (MV-2). O CONTEÚDO (objetivo,
    # contagem, recompensa) vive AQUI e só aqui; o engine só decide QUAL.
    #
    # ⚠️ `weight: 0` é DELIBERADO e não esconde nada. O pool do `maybe_offer`
    # filtra por `weight > 0`, então o encargo nunca é sorteado como oferta
    # aleatória de um NPC — ele é AFIXADO na cidade, visível de longe no
    # /viajar e anunciado na Crônica quando muda. Não é o anti-padrão "gate que
    # zera esconde a opção": aqui o zero tira do SORTEIO, e a opção fica MAIS
    # visível, não menos. (Se algum dia o encargo tiver de voltar ao pool,
    # basta pôr peso — nada mais no motor depende deste zero.)
    #
    # ⚠️ `requirements` usa só keys que `_KNOWN_REQS` já conhece (`continent` +
    # `flag`). O avaliador é FAIL-CLOSED: uma key nova sem entrada no frozenset
    # devolveria False para TODO jogador, sem log e sem erro. Reusar as
    # existentes evita a armadilha inteira — o gate real do encargo vive em
    # `city_engine.accept_encargo`, que nomeia cada recusa (Lei §1).
    #
    # ⚠️ Trackers: TODOS solo-completáveis. `sparring`/`win_sparring` VETADOS
    # (exigem um 2º jogador vivo e consentido: 0 sparrings em 30d no main, 0
    # desde sempre no s2 — a 4ª recorrência do mesmo dead-end). `arena_win` é
    # seguro porque a fila gera oponente NPC por timeout
    # (`arena_engine._spawn_npc_fallback` → `arena_duel_settle.py:301`).
    #
    # Recompensa: pedras + o material NATIVO daquele continente, alinhado com
    # `dungeon_regions.REGIONAL_BONUS_LOOT` (uma verdade sobre o que cada
    # continente produz). NUNCA só pedras — a mediana de 856 milhões de pedras
    # nos 30 ativos do main torna pedra pura um custo/prêmio invisível.
    # A reputação regional da entrega NÃO é somada aqui: `claim_storylet` já
    # credita `REP_STORYLET_DONE` a todo storylet resolvido (gated
    # `reputacao_rival`). Duplicar seria pagar duas vezes pela mesma entrega.

    # 🏔️ Línghé — Cidade de Wànshì 万事城 (universal · sects)
    {
        "key": "enc_linghe_selos", "giver_kind": "service_npc", "emoji": "🏛️",
        "requirements": {"continent": ["linghe"], "flag": "cidades"},
        "objective_type": "dungeon_floor", "objective_count": 8,
        "reward": {"stones": 800, "items": [{"type": "ore", "id": 2, "qty": 2}]},
        "expires_hours": 12, "weight": 0,
    },
    {
        "key": "enc_linghe_vigilia", "giver_kind": "service_npc", "emoji": "🧘",
        "requirements": {"continent": ["linghe"], "flag": "cidades"},
        "objective_type": "cultivate", "objective_count": 120,
        "reward": {"stones": 700, "items": [{"type": "herb", "id": 2, "qty": 3}]},
        "expires_hours": 12, "weight": 0,
    },
    {
        "key": "enc_linghe_escolta", "giver_kind": "service_npc", "emoji": "🛡️",
        "requirements": {"continent": ["linghe"], "flag": "cidades"},
        "objective_type": "npc_combat", "objective_count": 4,
        "reward": {"stones": 900, "items": [{"type": "ore", "id": 2, "qty": 3}]},
        "expires_hours": 12, "weight": 0,
    },

    # ⛰️ Qiānhé — Templo do Punho de Ferro (body · ores)
    {
        "key": "enc_qianhe_minerio", "giver_kind": "service_npc", "emoji": "⛏️",
        "requirements": {"continent": ["qianhe"], "flag": "cidades"},
        "objective_type": "dungeon_floor", "objective_count": 10,
        "reward": {"stones": 900, "items": [{"type": "ore", "id": 3, "qty": 2}]},
        "expires_hours": 12, "weight": 0,
    },
    {
        "key": "enc_qianhe_provas", "giver_kind": "service_npc", "emoji": "👊",
        "requirements": {"continent": ["qianhe"], "flag": "cidades"},
        "objective_type": "npc_combat", "objective_count": 5,
        "reward": {"stones": 950, "items": [{"type": "ore", "id": 3, "qty": 2}]},
        "expires_hours": 12, "weight": 0,
    },
    {
        "key": "enc_qianhe_carga", "giver_kind": "service_npc", "emoji": "🐾",
        "requirements": {"continent": ["qianhe"], "flag": "cidades"},
        "objective_type": "beast_expedition", "objective_count": 3,
        "reward": {"stones": 750, "items": [{"type": "ore", "id": 1, "qty": 4}]},
        "expires_hours": 12, "weight": 0,
    },

    # 🌸 Yǎnshān — Jardim das Dez Mil Flores (herbs · alchemy)
    {
        "key": "enc_yanshan_pilulas", "giver_kind": "service_npc", "emoji": "⚗️",
        "requirements": {"continent": ["yanshan"], "flag": "cidades"},
        "objective_type": "craft_pill", "objective_count": 5,
        "reward": {"stones": 850, "items": [{"type": "herb", "id": 9, "qty": 3}]},
        "expires_hours": 12, "weight": 0,
    },
    {
        "key": "enc_yanshan_remedio", "giver_kind": "service_npc", "emoji": "💊",
        "requirements": {"continent": ["yanshan"], "flag": "cidades"},
        "objective_type": "use_pill", "objective_count": 6,
        "reward": {"stones": 700, "items": [{"type": "herb", "id": 11, "qty": 3}]},
        "expires_hours": 12, "weight": 0,
    },
    {
        "key": "enc_yanshan_colheita", "giver_kind": "service_npc", "emoji": "🌿",
        "requirements": {"continent": ["yanshan"], "flag": "cidades"},
        "objective_type": "beast_expedition", "objective_count": 3,
        "reward": {"stones": 750, "items": [{"type": "herb", "id": 12, "qty": 3}]},
        "expires_hours": 12, "weight": 0,
    },

    # 🌋 Fēnghuǒ — Forja de Tiānhuǒ (forge · combat)
    {
        "key": "enc_fenghuo_forja", "giver_kind": "service_npc", "emoji": "🔨",
        "requirements": {"continent": ["fenghuo"], "flag": "cidades"},
        "objective_type": "forge_artifact", "objective_count": 3,
        "reward": {"stones": 1000, "items": [{"type": "ore", "id": 8, "qty": 2}]},
        "expires_hours": 12, "weight": 0,
    },
    {
        "key": "enc_fenghuo_tempera", "giver_kind": "service_npc", "emoji": "⚔️",
        "requirements": {"continent": ["fenghuo"], "flag": "cidades"},
        "objective_type": "npc_combat", "objective_count": 6,
        "reward": {"stones": 950, "items": [{"type": "ore", "id": 8, "qty": 2}]},
        "expires_hours": 12, "weight": 0,
    },
    {
        # `arena_win` ×2: a fila gera oponente NPC por timeout, logo é
        # solo-completável — mas cada vitória custa uma espera real, por isso
        # a contagem é a mais baixa dos quinze.
        "key": "enc_fenghuo_arena", "giver_kind": "service_npc", "emoji": "🏟️",
        "requirements": {"continent": ["fenghuo"], "flag": "cidades"},
        "objective_type": "arena_win", "objective_count": 2,
        "reward": {"stones": 900, "items": [{"type": "ore", "id": 9, "qty": 1}]},
        "expires_hours": 12, "weight": 0,
    },

    # 🌑 Mòyǔ — Cidade dos Ecos (forbidden · demonic)
    {
        "key": "enc_moyu_ruinas", "giver_kind": "service_npc", "emoji": "🕳️",
        "requirements": {"continent": ["moyu"], "flag": "cidades"},
        "objective_type": "dungeon_floor", "objective_count": 12,
        "reward": {"stones": 1100, "items": [{"type": "ore", "id": 6, "qty": 2}]},
        "expires_hours": 12, "weight": 0,
    },
    {
        "key": "enc_moyu_ecos", "giver_kind": "service_npc", "emoji": "👁️",
        "requirements": {"continent": ["moyu"], "flag": "cidades"},
        "objective_type": "npc_combat", "objective_count": 5,
        "reward": {"stones": 1050, "items": [{"type": "ore", "id": 6, "qty": 2}]},
        "expires_hours": 12, "weight": 0,
    },
    {
        "key": "enc_moyu_vigilia", "giver_kind": "service_npc", "emoji": "🌑",
        "requirements": {"continent": ["moyu"], "flag": "cidades"},
        "objective_type": "cultivate", "objective_count": 180,
        "reward": {"stones": 900, "items": [{"type": "herb", "id": 8, "qty": 2}]},
        "expires_hours": 12, "weight": 0,
    },
]


async def run_storylet_seeds(session):
    """Upsert do catálogo de storylets (insere ausentes + sincroniza existentes)."""
    for data in STORYLET_SEEDS:
        row = await session.get(StoryletCatalog, data["key"])
        if not row:
            row = StoryletCatalog(key=data["key"])
            session.add(row)
        row.giver_kind = data["giver_kind"]
        row.emoji = data["emoji"]
        row.requirements = data["requirements"]
        flag_modified(row, "requirements")
        row.objective_type = data["objective_type"]
        row.objective_count = data["objective_count"]
        row.reward = data["reward"]
        flag_modified(row, "reward")
        row.expires_hours = data["expires_hours"]
        row.weight = data["weight"]
        row.is_active = True
    await session.commit()
    logger.info("Seeded %d storylets.", len(STORYLET_SEEDS))
