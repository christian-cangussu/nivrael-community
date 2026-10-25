"""TEC-1 — A Biblioteca da Seita 藏经阁 (Técnicas & Escassez, Onda 1).

As 9 Seitas de Cultivo abrem suas BIBLIOTECAS em estantes de jade: artes
exclusivas da casa, destrancadas por posto + contribuição + (no Núcleo) uma
quest da casa. "Entrar numa seita" vira O caminho de aprender técnicas —
North star K3-ACQ (Lei §12): *"No final, tens 8 técnicas. E cada uma pesa."*

O modelo de estantes (Constituição §3, technique_scarcity_economy.md), sobre
a fundação v16.4c que JÁ existe:

    Estante Externa (tier 1) — posto disciple. 2 artes: a lição legada
        (v16.4c, grátis por posto) + a arte nova TEC-1 (grátis ao entrar).
    Estante Interna (tier 2) — posto inner. 2 artes: legada (grátis) +
        nova (LIB_T2_CP de contribuição — SALDO do Pavilhão, nunca earned).
    Estante do Núcleo (tier 3) — posto core. 2 artes: legada (grátis) +
        nova (LIB_T3_CP + 1 quest da casa concluída — arcos 610-636).
    Estante do Ancião 传功 (tier 4) — posto elder. 2 artes: legada (grátis
        por posto, como hoje) + nova (SEL_T4_CP do SALDO + reino).
    Estante Oculta 秘传 (tier 5) — posto heir. 2 artes: legada (grátis) +
        nova, que NÃO se compra: karma ALINHADO com a casa + a Prova da
        Sucessão (duelo contra o Ancião que a guarda).

As duas últimas só existem com a flag `estantes_seladas` (TEC-3) ON — sem ela
aparecem SELADAS com o requisito dito (teaser honesto, Lei §1), exatamente
como o TEC-1 as deixou.

Regras cross-sect (Constituição §3): sair da seita LOCKA as artes tier 3
(desequipa; não usa) mas NUNCA apaga o registro (`player_sect_techniques`);
tiers 1-2 ficam ("lições básicas não se desaprendem"); voltar à MESMA casa
re-destranca. As 45 artes legadas v16.4c (ids 500-544) ficam INTOCADAS —
o lockout delas segue a decisão do owner de 2026-06-16 (sem lockout,
launch-server-bound) e o learn delas segue `learn_sect_technique`.

Padrão do engine = profession_engine (MV-7): `biblioteca_on()` fail-safe,
OFF ⇒ zero queries em toda função pública, knobs env `LIB_*`, catálogo de
estantes derivado do DB (library_tier, Migration 136), teste isolado
COMMITTED em scripts/_test_tec1_library.py. O débito de contribuição usa a
MESMA semântica do Pavilhão (buy_merit_reward): balance, nunca earned.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import func, select
from sqlalchemy import text as _sql_text

from database.models import (
    Player,
    PlayerQuest,
    PlayerSectTechnique,
    PlayerTechnique,
    QuestCatalog,
    TechniqueCatalog,
)

logger = logging.getLogger(__name__)


# ── Flag gate (padrão profissoes_on — fail-safe, nunca quebra main) ──────────
def biblioteca_on(world_key: str | None = None) -> bool:
    """Gate estável da flag per-world `biblioteca_seitas`. Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("biblioteca_seitas", world_key))
    except Exception:
        return False


# ── Flag gate TEC-3 (as duas câmaras seladas) ───────────────────────────────
def selado_on(world_key: str | None = None) -> bool:
    """Gate estável da flag per-world `estantes_seladas` (TEC-3). Fail-safe →
    False. DEPENDE de `biblioteca_seitas`: sem a Biblioteca não há estante para
    abrir, então a dependência é conjunção AQUI (uma verdade) e não uma nota no
    painel — ligar só o TEC-3 num mundo NÃO faz nada, em vez de meio-fazer."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("estantes_seladas", world_key)) \
            and bool(feature_enabled_for_world("biblioteca_seitas", world_key))
    except Exception:
        return False


# ── Knobs (env LIB_*/SEL_*, Lei §13 — engine, não DB; o seed grava no catálogo)
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


LIB_T2_CP = _env_int("LIB_T2_CP", 750)      # custo da arte nova da Estante Interna
LIB_T3_CP = _env_int("LIB_T3_CP", 3000)     # custo da arte nova da Estante do Núcleo

# TEC-3 — a Estante do Ancião VENDE (a casa te confia o que a define); a Estante
# Oculta NÃO (Lei §4/§12: o segredo não tem preço — paga-se com a Prova).
# SEL_T4_CP=6000: o recon de prod (28/07) mediu o MAIOR saldo de contribuição do
# jogo inteiro em 7455 (e o maior `earned` em 8055) depois de meses de beta — os
# 10000 CP da Constituição §3 nasceriam ACIMA do teto histórico, i.e. a Signature
# nasceria morta. 6000 = 2× o Núcleo, abaixo do teto observado, e knob-ajustável
# quando o servidor de launch tiver a sua própria curva.
SEL_T4_CP = _env_int("SEL_T4_CP", 6000)
SEL_T5_CP = _env_int("SEL_T5_CP", 0)        # a Oculta não se compra (ver §2)
# Karma ALINHADO com a casa (ver `aligned_karma`): 250 = o mesmo número em que o
# caminho CRISTALIZA (KARMA_PATH_THRESHOLDS) — "prove que ainda é quem a casa
# escolheu". Um `karma >= +250` cru trancaria a casa demoníaca para sempre.
SEL_KARMA_MIN = _env_int("SEL_KARMA_MIN", 250)
SEL_RITE_COOLDOWN_H = _env_int("SEL_RITE_COOLDOWN_H", 24)  # espelha TRIAL_LOSS_COOLDOWN_HOURS

LIBRARY_TIERS: tuple[int, ...] = (1, 2, 3)
# TEC-3 — as duas câmaras. Só entram em `library_tiers()` com a flag ON, senão
# um mundo com `biblioteca_seitas` ON e `estantes_seladas` OFF veria as artes
# novas aparecerem sozinhas (Lei §5 — OFF ⇒ byte-idêntico).
SEALED_TIERS: tuple[int, ...] = (4, 5)
# TEC-5 — o Cofre Proibido 禁库. Estante 6, e SÓ da casa do Abismo: as outras 8
# casas não a têm (nem como teaser — o Cofre não lhes é prometido, logo não há
# dead-end). Entra pela flag `forbidden_path` em conjunção com o TEC-3.
FORBIDDEN_TIERS: tuple[int, ...] = (6,)
FORBIDDEN_SECT: str = "abyssal_depths"


def forbidden_vault_on(world_key: str | None = None) -> bool:
    """Gate do Cofre (conjunção `forbidden_path` × `estantes_seladas` ×
    `biblioteca_seitas`). Delegado ao engine do TEC-5 — uma verdade."""
    try:
        from core.forbidden_path_engine import vault_on
        return bool(vault_on(world_key))
    except Exception:
        return False


def library_tiers(world_key: str | None = None, sect_id: str | None = None) -> tuple[int, ...]:
    """As estantes VISÍVEIS agora — UMA verdade lida por toda leitura E escrita.
    Nunca ler `LIBRARY_TIERS` diretamente num gate: a tupla é a BASE, não a
    resposta (lição QoL-relatos §0.0.1 — a constante do engine não é o teto do dado).

    `sect_id` (TEC-5, opcional): o Cofre Proibido só existe na casa do Abismo.
    Sem casa dada devolvemos o Cofre quando a flag está ON — o filtro final é
    o `sect_key` da própria arte (a query da view já casa casa×tier), e a
    escrita valida a casa explicitamente."""
    tiers = LIBRARY_TIERS + SEALED_TIERS if selado_on(world_key) else LIBRARY_TIERS
    if forbidden_vault_on(world_key) and (sect_id is None or sect_id == FORBIDDEN_SECT):
        tiers = tiers + FORBIDDEN_TIERS
    return tiers


# Posto mínimo por estante — a escada REAL v16.4c (recon TEC-1 §0.2: o posto
# formal existe em Player.sect_rank; o fallback "derivado de contribution" do
# prompt não se aplica). Externa=qualquer membro, Interna=inner, Núcleo=core,
# Ancião=elder, Oculta=heir (TEC-3 — os dois degraus que eram cosméticos).
# TEC-5 — o Cofre pede o MESMO posto da Oculta (heir é o topo de SECT_RANKS: não
# existe degrau acima para pedir). A exclusividade do Cofre vem de OUTRA régua —
# path demonic + karma alinhado 500 + o registro do Rito — nunca do posto.
TIER_MIN_RANK: dict[int, str] = {
    1: "disciple", 2: "inner", 3: "core", 4: "elder", 5: "heir", 6: "heir",
}

# Estantes selado-teaser (Lei §1 — o requisito é DITO). Com `estantes_seladas`
# ON elas deixam de ser teaser e viram estantes REAIS (tiers 4/5 em
# `library_tiers()`), e este teaser some — ver `get_library_shelves`.
SEALED_SHELVES: tuple[dict[str, str], ...] = (
    {"key": "signature", "rank": "elder"},
    {"key": "hidden", "rank": "heir"},
)

# O tier da câmara que exige a PROVA em vez de contribuição (Lei §4/§12).
RITE_TIER: int = 5
RITE_PVE_SOURCE = "hidden_rite"   # ≤24 chars (duel_sessions.pve_source)

# TEC-5 — o Cofre NÃO se compra (Lei §4/§12, padrão da Oculta): custo 0. A
# entrada `6: 0` é OBRIGATÓRIA — sem ela `tier_default_cp` clampa um tier
# desconhecido para o TOPO da escala (6000) e o Cofre nasceria pago.
_TIER_CP: dict[int, int] = {1: 0, 2: LIB_T2_CP, 3: LIB_T3_CP, 4: SEL_T4_CP,
                            5: SEL_T5_CP, 6: 0}


def tier_default_cp(tier: int) -> int:
    """Custo default de contribuição por estante.

    Lição QoL-relatos §0.0.2 — "fora da escala por cima" ≠ "não sei o que é isto":
    um `library_tier` 6 que apareça amanhã numa seed clampa para o TOPO da
    escala de custo (a estante mais cara), NUNCA para o ramo neutro/grátis.
    Ausente/lixo (None, 0, negativo) segue neutro — isso é "não é estante"."""
    t = int(tier or 0)
    if t <= 0:
        return 0
    if t in _TIER_CP:
        return _TIER_CP[t]
    return max(_TIER_CP.values())


def tier_cp_cost(tech: Any) -> int:
    """O custo REAL de uma arte: coluna do catálogo (seedada dos knobs) com
    fallback ao default do tier — UMA verdade, knob-ajustável por seed-sync."""
    cost = getattr(tech, "library_cp_cost", None)
    if cost is None:
        return tier_default_cp(getattr(tech, "library_tier", 0) or 0)
    return max(0, int(cost))


# O piso do lockout cross-sect (Constituição §3): tiers 1-2 são "lições básicas
# que não se desaprendem"; do Núcleo para cima a casa retoma o que é dela.
LOCK_TIER_FLOOR: int = 3


def is_library_locked(tech: Any, player: Any) -> bool:
    """True se esta arte está LOCKADA para o jogador (regra cross-sect §3):
    tier >= 3 (Núcleo/Ancião/Oculta) aprendido de uma casa que não é a atual.
    Puro (zero query) — o caller já tem o row do catálogo e o Player. Só morde
    com a flag ON (os call sites de equip verificam a flag ANTES, OFF ⇒ jamais
    chamada).

    O `>=` é incondicional de propósito: com `estantes_seladas` OFF ninguém
    consegue aprender um tier 4/5, logo `>= 3` ≡ `== 3` e main continua
    byte-idêntico; mas quem JÁ aprendeu num mundo que depois desligar a flag
    continua trancado corretamente (a arte é da casa, não da flag)."""
    try:
        if int(getattr(tech, "library_tier", 0) or 0) < LOCK_TIER_FLOOR:
            return False
        sect_key = getattr(tech, "sect_key", None)
        if not sect_key:
            return False
        return getattr(player, "sect_id", None) != sect_key
    except Exception:
        return False


# ── O karma ALINHADO — o gate da Estante Oculta (Lei §1 + o achado do [jogador]) ─
def aligned_karma(karma: Any, sect_id: str | None) -> int:
    """Quão fundo o cultivador andou a estrada DA SUA CASA.

    `-karma` numa casa demoníaca, `+karma` numa casa justa. É a MESMA operação
    que `affinity_engine` já usa para pontuar a entrada e que o
    `get_tribulation_modifier` já usa para ler |karma| ("santo ou demônio, o
    Céu não discrimina") — não inventamos régua nova.

    Por que não `karma >= X` cru (o default do prompt): a única casa demoníaca
    do jogo (abyssal_depths) exige `path == "demonic"`, que por sua vez exige
    `karma <= -250`. Um gate positivo trancaria a Estante Oculta dessa casa
    PARA SEMPRE — e em `karma >= +500` o gate seria literalmente o gatilho da
    divergência do próprio demoníaco (o Céu declarando-o traidor da casa).
    Isso é a armadilha do hard-gate que apaga a existência da opção."""
    try:
        from core.world_sects_engine import is_demonic_sect
        k = int(karma or 0)
        return -k if is_demonic_sect(sect_id) else k
    except Exception:
        return 0


def karma_gate_ok(karma: Any, sect_id: str | None) -> bool:
    """O gate da Oculta, puro. UM helper — a view e o rito leem o mesmo."""
    return aligned_karma(karma, sect_id) >= SEL_KARMA_MIN


def _tech_name(lang: str, tech: Any) -> str:
    """Nome server-resolved. 名 2026-09-14: DELEGA no dono unico.

    Era uma SEGUNDA implementacao a' mao da mesma coisa (`t_optional` com a
    chave montada aqui) — as "duas ligacoes a' mao" da Lei F-7 §2. Continua a
    existir porque 4 sitios deste motor a chamam pelo nome; o que mudou e' que
    ja' nao DECIDE nada."""
    from core.i18n import catalog_name
    return catalog_name(lang, "tech", tech)


def _tech_desc(lang: str, tech: Any) -> str:
    """Idem — delega no dono unico (`catalog_desc`)."""
    from core.i18n import catalog_desc
    return catalog_desc(lang, "tech", tech)


async def has_completed_house_quest(session, player_id: int, sect_id: str) -> bool:
    """O gate de quest do Núcleo: ≥1 quest DA CASA concluída (arcos 610-636,
    Pedra 2 wave 2 — tracker-reuse, zero quest nova). Sect quests são one-shot
    (sentinela reset_at, fora dos resets daily/weekly) ⇒ is_completed é durável."""
    try:
        row = (await session.execute(
            select(PlayerQuest.quest_id)
            .join(QuestCatalog, QuestCatalog.id == PlayerQuest.quest_id)
            .where(
                PlayerQuest.player_id == player_id,
                PlayerQuest.is_completed == True,  # noqa: E712
                QuestCatalog.sect_id == sect_id,
            )
            .limit(1)
        )).first()
        return row is not None
    except Exception:
        logger.debug("has_completed_house_quest failed (player_id=%s)", player_id, exc_info=True)
        return False


async def _equipped_loadout(session, player_id: int, lang: str = "pt") -> list[dict[str, Any]]:
    """O loadout de combate atual (para o antes→depois do confirm, Lei §10).
    Nomes via t_optional — artes da Biblioteca saem localizadas, o resto cai
    no canônico do catálogo (review TEC-1: sem mistura de línguas no confirm)."""
    from core.i18n import t_optional
    rows = (await session.execute(
        select(TechniqueCatalog.id, TechniqueCatalog.name, TechniqueCatalog.emoji)
        .join(PlayerTechnique, PlayerTechnique.technique_id == TechniqueCatalog.id)
        .where(
            PlayerTechnique.player_id == player_id,
            PlayerTechnique.is_active_combat == True,  # noqa: E712
            TechniqueCatalog.tech_type == "combat",
        )
        .order_by(TechniqueCatalog.id)
    )).all()
    from core.i18n import catalog_text
    return [{"tech_id": int(r[0]),
             # 名 2026-09-14 — linha CRUA (tupla), logo entra pelo motor e nao
             # pela porta de objecto: montar a chave aqui seria um 2º dono.
             "name": catalog_text(lang, "tech", int(r[0]), "name", r[1]),
             "emoji": r[2] or "⚔️"} for r in rows]


# ── A VIEW — as estantes da casa (server-resolved, mini recebe pronto) ───────
async def get_library_shelves(session, player_id: int, lang: str = "pt") -> dict[str, Any]:
    """Compõe as estantes da Biblioteca da casa do jogador.

    Flag OFF → ``{"on": False}`` SEM query (padrão merit_list: o modal pode
    disparar o fetch no mount; OFF curto-circuita e o cliente rende o legado).
    Não-membro → ``{"on": True, "in_sect": False}`` (disclosure: a Biblioteca
    existe, a porta é a seita — Lei §1, nunca silent void).
    """
    if not biblioteca_on():
        return {"on": False}

    from core.i18n import t as i18n_t
    from core.world_sects_engine import (
        DEFAULT_SECT_RANK,
        SECT_LIBRARY,
        get_rank_label_key,
        is_valid_sect,
        rank_index,
    )

    selado = selado_on()

    row = (await session.execute(
        select(Player.sect_id, Player.sect_rank, Player.sect_contribution,
               Player.realm, Player.sect_contribution_earned, Player.karma,
               Player.scroll_econ, Player.path, Player.age_years,
               Player.lifespan_bonus_years)
        .where(Player.telegram_id == player_id)
    )).first()
    if not row or not is_valid_sect(row[0]):
        return {"on": True, "in_sect": False}
    sect_id = row[0]
    # TEC-5 — o Cofre só entra na lista de estantes DESTA casa (as outras 8 não
    # o têm; a query abaixo já casa sect_key × tier, mas a tupla é a verdade).
    tiers = library_tiers(sect_id=sect_id)
    rank = row[1] or DEFAULT_SECT_RANK
    merit_balance = int(row[2] or 0)
    realm = int(row[3] or 0)
    karma = int(row[5] or 0)
    # O número que a ESCADA lê — nunca o saldo (UMA verdade com _apply_promotion;
    # `scroll_econ` não-NULL = já doou pergaminho ⇒ o saldo deixou de ser proxy).
    from core.world_sects_engine import ladder_contribution
    earned = ladder_contribution(row[4], row[2], row[6] is not None)
    cur_idx = rank_index(rank)
    karma_ok = karma_gate_ok(karma, sect_id) if selado else True
    rite_done = await _rite_passed(session, player_id, sect_id) if selado else False

    # TEC-5 — o estado do Cofre (só lido quando a estante 6 está de facto na
    # lista: OFF ⇒ zero queries extra, payload byte-idêntico).
    vault = FORBIDDEN_TIERS[0] in tiers
    player_path = row[7]
    fp_karma_need = 0
    fp_karma_have = 0
    fp_path_ok = True
    fp_rite_done = False
    if vault:
        from core.forbidden_path_engine import FP_KARMA_MIN, rite_passed as _fp_rite
        fp_karma_need = int(FP_KARMA_MIN)
        fp_karma_have = aligned_karma(karma, sect_id)
        fp_path_ok = (player_path == "demonic")
        fp_rite_done = await _fp_rite(session, player_id)

    # 1 query por fonte: artes novas (library_tier visível) + legadas (v16.4c).
    new_arts = {
        t.id: t for t in (await session.execute(
            select(TechniqueCatalog).where(
                TechniqueCatalog.sect_key == sect_id,
                TechniqueCatalog.library_tier.in_(tiers),
            )
        )).scalars().all()
    }
    legacy_map = {e["rank"]: e for e in SECT_LIBRARY.get(sect_id, [])}
    legacy_ids = [e["tech_id"] for e in legacy_map.values()]
    legacy_arts: dict[int, Any] = {}
    if legacy_ids:
        legacy_arts = {
            t.id: t for t in (await session.execute(
                select(TechniqueCatalog).where(TechniqueCatalog.id.in_(legacy_ids))
            )).scalars().all()
        }

    all_ids = list(new_arts.keys()) + legacy_ids
    learned_ids: set[int] = set()
    if all_ids:
        learned_ids = set((await session.execute(
            select(PlayerTechnique.technique_id).where(
                PlayerTechnique.player_id == player_id,
                PlayerTechnique.technique_id.in_(all_ids),
            )
        )).scalars().all())

    quest_done = await has_completed_house_quest(session, player_id, sect_id)

    def _art_entry(tech: Any, *, tier: int, legacy: bool, min_rank: str) -> dict[str, Any]:
        cost = 0 if legacy else tier_cp_cost(tech)
        rank_ok = cur_idx >= rank_index(min_rank)
        realm_ok = realm >= int(tech.req_realm or 0)
        needs_quest = (not legacy) and tier == 3
        quest_ok = quest_done if needs_quest else True
        # TEC-3 — a Oculta paga com a PROVA, não com contribuição (Lei §4/§12).
        needs_rite = selado and (not legacy) and tier == RITE_TIER
        # TEC-5 — o Cofre Proibido: path + karma da divergência + o Rito.
        forbidden = vault and (not legacy) and tier == FORBIDDEN_TIERS[0]
        learned = tech.id in learned_ids
        block = None
        if not learned:
            if not rank_ok:
                block = "rank"
            elif not realm_ok:
                block = "realm"
            elif needs_quest and not quest_ok:
                block = "quest"
            elif forbidden and not fp_path_ok:
                block = "path"
            elif forbidden and fp_karma_have < fp_karma_need:
                block = "fp_karma"
            elif forbidden and not fp_rite_done:
                block = "hd_rite"
            elif needs_rite and not karma_ok:
                block = "karma"
            elif needs_rite and not rite_done:
                block = "rite"
            elif cost > merit_balance:
                block = "cp"
        out = {
            "tech_id": int(tech.id),
            "name": _tech_name(lang, tech),
            "desc": _tech_desc(lang, tech),
            "emoji": tech.emoji or "⚔️",
            "effect_type": tech.effect_type,
            "effect_value": float(tech.effect_value or 0.0),
            "qi_cost": int(tech.qi_cost or 0),
            "req_realm": int(tech.req_realm or 0),
            "legacy": bool(legacy),
            "cost": int(cost),
            "needs_quest": bool(needs_quest),
            "learned": bool(learned),
            "can_learn": (not learned) and block is None,
            "block": block,
            "min_rank_key": get_rank_label_key(min_rank),
        }
        # Keys NOVAS — SEMPRE condicionais (OFF-identity: com a flag OFF
        # `needs_rite` é False em toda arte, logo o payload é byte-idêntico).
        if needs_rite:
            out["needs_rite"] = True
            out["karma_have"] = aligned_karma(karma, sect_id)
            out["karma_need"] = int(SEL_KARMA_MIN)
            out["rite_passed"] = bool(rite_done)
        # TEC-5 — keys do Cofre, também CONDICIONAIS (flag OFF ⇒ `forbidden` é
        # False em toda arte ⇒ payload byte-idêntico).
        if forbidden:
            out["forbidden"] = True
            out["path_ok"] = bool(fp_path_ok)
            out["path_need"] = "demonic"
            out["karma_have"] = fp_karma_have
            out["karma_need"] = fp_karma_need
            out["hd_rite_passed"] = bool(fp_rite_done)
        return out

    shelves: list[dict[str, Any]] = []
    for tier in tiers:
        min_rank = TIER_MIN_RANK[tier]
        arts: list[dict[str, Any]] = []
        # O mapa legado é indexado por POSTO, e o Cofre (tier 6) pede o mesmo
        # `heir` da Oculta (tier 5) — sem este filtro por TIER a arte legada da
        # Oculta era listada outra vez dentro do Cofre, grátis e sem gate
        # (achado do review adversarial). O Cofre não tem arte legada: as 45
        # v16.4c param no tier 5.
        legacy_entry = legacy_map.get(min_rank)
        if legacy_entry and int(legacy_entry.get("tier") or 0) != tier:
            legacy_entry = None
        if legacy_entry and legacy_entry["tech_id"] in legacy_arts:
            arts.append(_art_entry(
                legacy_arts[legacy_entry["tech_id"]],
                tier=tier, legacy=True, min_rank=min_rank,
            ))
        for tech in sorted(new_arts.values(), key=lambda x: x.id):
            if int(tech.library_tier or 0) == tier:
                arts.append(_art_entry(tech, tier=tier, legacy=False, min_rank=min_rank))
        shelf = {
            "tier": tier,
            "label": i18n_t(lang, f"lib_shelf_{tier}"),
            "min_rank_key": get_rank_label_key(min_rank),
            "rank_ok": cur_idx >= rank_index(min_rank),
            "arts": arts,
        }
        # Lei §1 — o caminho QUANTIFICADO: "suba a Ancião: faltam N". A escada
        # de posto lê `earned` (ladder_contribution — o saldo é só a carteira),
        # então o número que falta TEM de vir de earned, senão a promessa mente.
        if selado and not shelf["rank_ok"]:
            gap = _rank_gap(earned, realm, min_rank)
            if gap is not None:
                shelf["rank_gap"] = gap
        # TEC-5 — a estante 6 diz o que é (key condicional; as 8 outras casas
        # nunca a veem porque o tier não entra na tupla delas).
        if vault and tier == FORBIDDEN_TIERS[0]:
            shelf["forbidden"] = True
        shelves.append(shelf)

    # TEC-3 — com a flag ON as duas câmaras VIRARAM estantes reais (tiers 4/5
    # acima), então o teaser desaparece. `sealed` continua a existir como []
    # (key antiga, nunca nova) e os dois clientes rendem nada — em vez de um
    # `sealed[].art` não-legado, que o mini aprenderia pelo endpoint LEGADO
    # (sem débito, sem registro, sem chronicle) e o chat não conseguiria
    # aprender de todo (o confirm só varre `shelves[]`). Achado do recon §3.
    sealed: list[dict[str, Any]] = []
    if not selado:
        for s in SEALED_SHELVES:
            entry = legacy_map.get(s["rank"])
            art = None
            if entry and entry["tech_id"] in legacy_arts:
                art = _art_entry(legacy_arts[entry["tech_id"]],
                                 tier=3, legacy=True, min_rank=s["rank"])
            sealed.append({
                "key": s["key"],
                "label": i18n_t(lang, f"lib_shelf_{s['key']}"),
                "min_rank_key": get_rank_label_key(s["rank"]),
                "rank_ok": cur_idx >= rank_index(s["rank"]),
                "art": art,
                "teaser": i18n_t(lang, "lib_sealed_teaser"),
            })

    out = {
        "on": True,
        "in_sect": True,
        "sect_id": sect_id,
        "rank": rank,
        "rank_key": get_rank_label_key(rank),
        "merit_balance": merit_balance,
        "quest_done": bool(quest_done),
        "shelves": shelves,
        "sealed": sealed,
        "loadout": await _equipped_loadout(session, player_id, lang),
    }
    if selado:
        # Keys NOVAS, condicionais (Lei §5 — OFF ⇒ payload byte-idêntico).
        out["selado"] = True
        out["rite"] = await hidden_rite_state(session, player_id, sect_id)
    if vault:
        # TEC-5 — os números do Cofre viajam no payload (display = roll: a
        # vitrine diz o karma e os anos que ESTE cultivador paga por uso).
        from types import SimpleNamespace

        from core.forbidden_path_engine import knobs_payload, lifespan_state
        life = lifespan_state(SimpleNamespace(
            realm=realm, age_years=int(row[8] or 0),
            lifespan_bonus_years=int(row[9] or 0)))
        out["forbidden_vault"] = {
            "tier": FORBIDDEN_TIERS[0], **knobs_payload(karma),
            "years_per_use": life["years_per_use"],
            "age_years": life["age_years"], "ceiling": life["ceiling"],
            "immortal": life["immortal"], "uses_left": life["uses_left"],
        }
    return out


def _rank_gap(earned: int, realm: int, min_rank: str) -> dict[str, Any] | None:
    """O que falta para o próximo degrau, em NÚMERO (Lei §1 — o caminho é dito
    e quantificado: "suba a Ancião: faltam N de contribuição"). None se já lá
    está. `earned` TEM de vir de `ladder_contribution` — o saldo não promove."""
    try:
        from core.world_sects_engine import (
            SECT_RANK_REALM_GATES,
            SECT_RANK_THRESHOLDS,
        )
        need_cp = int(SECT_RANK_THRESHOLDS.get(min_rank, 0))
        need_realm = int(SECT_RANK_REALM_GATES.get(min_rank, 0))
        gap_cp = max(0, need_cp - int(earned or 0))
        gap_realm = max(0, need_realm - int(realm or 0))
        if not gap_cp and not gap_realm:
            return None
        return {"contribution": gap_cp, "realm": gap_realm,
                "need_contribution": need_cp, "need_realm": need_realm}
    except Exception:
        logger.debug("_rank_gap failed (min_rank=%s)", min_rank, exc_info=True)
        return None


# ── O WRITE — aprender uma arte nova das estantes ────────────────────────────
async def learn_library_technique(session, player_id: int, tech_id: int) -> dict[str, Any]:
    """Aprende uma arte NOVA das estantes VISÍVEIS (`library_tiers()`).

    Row-lock + populate_existing (padrão buy_merit_reward); débito SÓ no saldo
    `sect_contribution` (a escada de rank lê earned — comprar arte NUNCA recua
    posto); idempotente (already_learned sem débito); gates disclosed em ordem:
    membro → arte da casa → posto → realm → quest (Núcleo) → karma+Prova
    (Oculta, TEC-3) → saldo. Grava o
    registro em player_sect_techniques (a memória que sobrevive ao leave).
    Chronicle `lib_first` no 1º Núcleo do servidor por casa. Caller commita.
    Flag OFF → recusa SEM query. Devolve o loadout antes→depois (Lei §10).
    """
    if not biblioteca_on():
        return {"ok": False, "reason": "lib_off"}

    from core.world_sects_engine import (
        DEFAULT_SECT_RANK,
        get_rank_label_key,
        is_valid_sect,
        rank_index,
    )

    tech_id = int(tech_id)
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}
    if not is_valid_sect(player.sect_id):
        return {"ok": False, "reason": "not_in_sect"}

    tech = (await session.execute(
        select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
    )).scalar_one_or_none()
    if tech is None or int(tech.library_tier or 0) not in library_tiers(sect_id=player.sect_id):
        return {"ok": False, "reason": "tech_not_in_library"}
    if tech.sect_key != player.sect_id:
        return {"ok": False, "reason": "wrong_house"}

    tier = int(tech.library_tier)
    min_rank = TIER_MIN_RANK[tier]
    if rank_index(player.sect_rank or DEFAULT_SECT_RANK) < rank_index(min_rank):
        return {"ok": False, "reason": "rank_too_low",
                "req_rank_key": get_rank_label_key(min_rank)}
    if (player.realm or 0) < (tech.req_realm or 0):
        return {"ok": False, "reason": "realm_too_low", "req_realm": int(tech.req_realm or 0)}

    existing = (await session.execute(
        select(PlayerTechnique).where(
            PlayerTechnique.player_id == player_id,
            PlayerTechnique.technique_id == tech_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return {"ok": False, "reason": "already_learned"}

    # Registro prévio (review TEC-1, achado F3): renascer/prestige APAGA
    # PlayerTechnique mas NUNCA o registro da Biblioteca — sem este check o
    # re-aprender estourava o PK composto de player_sect_techniques (arte
    # PERMANENTEMENTE inaprendível). Registro existente = a casa JÁ te
    # transmitiu esta arte: re-aprender é GRÁTIS e sem quest (o débito e o
    # gate foram pagos uma vez; espelha o re-destrancar do re-join §3).
    prior_reg = (await session.execute(
        select(PlayerSectTechnique).where(
            PlayerSectTechnique.player_id == player_id,
            PlayerSectTechnique.technique_id == tech_id,
        )
    )).scalar_one_or_none()

    if prior_reg is None and tier == 3 \
            and not await has_completed_house_quest(session, player_id, player.sect_id):
        return {"ok": False, "reason": "quest_required"}

    # TEC-3 — a Estante Oculta não se compra: paga-se com a Prova da Sucessão
    # + karma ALINHADO com a casa. Ordem disclosed, DEPOIS de posto/reino (o
    # requisito mais barato de entender primeiro) e ANTES do saldo (que aqui é
    # sempre 0 — SEL_T5_CP). `prior_reg` dispensa: já provou uma vez (o mesmo
    # perdão do re-aprender pós-renascimento que o TEC-1 fixou no achado F3).
    if prior_reg is None and selado_on() and tier == RITE_TIER:
        if not karma_gate_ok(getattr(player, "karma", 0), player.sect_id):
            return {"ok": False, "reason": "karma_too_low",
                    "karma_need": int(SEL_KARMA_MIN),
                    "karma_have": aligned_karma(getattr(player, "karma", 0), player.sect_id)}
        if not await _rite_passed(session, player_id, player.sect_id):
            return {"ok": False, "reason": "rite_required"}

    # TEC-5 — o Cofre Proibido. MESMA ordem disclosed da view (posto e reino já
    # passaram acima): caminho → karma da divergência → o registro do Rito.
    # `prior_reg` dispensa (já provou uma vez — o mesmo perdão do relearn).
    if prior_reg is None and tier == FORBIDDEN_TIERS[0]:
        from core.forbidden_path_engine import FP_KARMA_MIN, rite_passed as _fp_rite
        if not forbidden_vault_on():
            return {"ok": False, "reason": "tech_not_in_library"}
        if player.sect_id != FORBIDDEN_SECT:
            return {"ok": False, "reason": "wrong_house"}
        if getattr(player, "path", None) != "demonic":
            return {"ok": False, "reason": "path_required", "path_need": "demonic"}
        _have = aligned_karma(getattr(player, "karma", 0), player.sect_id)
        if _have < int(FP_KARMA_MIN):
            return {"ok": False, "reason": "fp_karma_too_low",
                    "karma_need": int(FP_KARMA_MIN), "karma_have": _have}
        if not await _fp_rite(session, player_id):
            return {"ok": False, "reason": "hd_rite_required"}

    cost = 0 if prior_reg is not None else tier_cp_cost(tech)
    balance = int(player.sect_contribution or 0)
    if balance < cost:
        return {"ok": False, "reason": "insufficient_merit", "cost": cost, "balance": balance}

    return await _grant_library_art(
        session, player, tech, cost=cost, prior_reg=prior_reg, tier=tier,
    )


async def _grant_library_art(session, player: Any, tech: Any, *, cost: int,
                             prior_reg: Any, tier: int) -> dict[str, Any]:
    """O ATO de transmitir a arte — o UM helper que grava.

    Extraído no TEC-3 porque agora há DUAS portas para a mesma transmissão (a
    compra na estante e a vitória na Prova da Sucessão) e elas não podem
    divergir: mesmo auto-equip slot-aware, mesmo débito-só-no-saldo, mesmo
    registro eterno em `player_sect_techniques`, mesmo antes→depois (Lei §10).
    O caller já validou TODOS os gates e já travou o row do Player."""
    player_id = int(player.telegram_id)
    tech_id = int(tech.id)
    lang = getattr(player, "language", None) or "pt"
    loadout_before = await _equipped_loadout(session, player_id, lang)

    # Auto-equip slot-aware — espelho exato do learn_sect_technique v16.4c.
    auto_equip = True
    if tech.tech_type == "combat":
        try:
            from core.combat_engine import get_max_combat_techniques
            max_slots = get_max_combat_techniques(int(player.realm or 0))
            if len(loadout_before) >= max_slots:
                auto_equip = False
        except Exception:
            logger.debug("_grant_library_art slot check failed (player_id=%s)",
                         player_id, exc_info=True)

    # Débito no SALDO (earned intocado — UMA verdade com o Pavilhão).
    if cost:
        player.sect_contribution = int(player.sect_contribution or 0) - int(cost)

    session.add(PlayerTechnique(
        player_id=player_id, technique_id=tech_id,
        mastery_level=1, is_active_combat=auto_equip,
    ))
    if prior_reg is None:
        session.add(PlayerSectTechnique(
            player_id=player_id, technique_id=tech_id,
            sect_key=player.sect_id, cp_paid=int(cost),
        ))

    if tier == 3 and prior_reg is None:
        await _chronicle_first_core_art(session, player_id, player.sect_id)
    if tier == RITE_TIER and prior_reg is None:
        await _chronicle_first_hidden_art(session, player_id, player.sect_id)
    if tier == FORBIDDEN_TIERS[0] and prior_reg is None:
        await _chronicle_first_forbidden_art(session, player_id, player.sect_id)

    entry = {
        "tech_id": tech_id,
        "name": _tech_name(lang, tech),
        "emoji": tech.emoji or "⚔️",
    }
    loadout_after = list(loadout_before) + ([entry] if auto_equip else [])
    return {
        "ok": True,
        "tech_id": tech_id,
        "tier": int(tier),
        "name": entry["name"],
        "emoji": entry["emoji"],
        "cp_spent": int(cost),
        "merit_balance": int(player.sect_contribution or 0),
        "auto_equipped": bool(auto_equip),
        "loadout_before": loadout_before,
        "loadout_after": loadout_after,
    }


async def _chronicle_first_core_art(session, player_id: int, sect_id: str) -> None:
    """Chronicle `lib_first` — a 1ª arte do Núcleo do servidor POR CASA
    (advisory lock namespaced, padrão sty_first). Best-effort, nunca levanta."""
    try:
        await session.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext('lib_first:' || :k))"),
            {"k": sect_id},
        )
        other = (await session.execute(
            select(PlayerSectTechnique.player_id)
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerSectTechnique.technique_id)
            .where(
                PlayerSectTechnique.sect_key == sect_id,
                PlayerSectTechnique.player_id != player_id,
                TechniqueCatalog.library_tier == 3,
            )
            .limit(1)
        )).first()
        if other is not None:
            return
        from core.world_pulse_engine import emit_chronicle
        from core.world_sects_engine import get_native_continent_for_sect
        await emit_chronicle(
            session, event_type="lib_first", text_key="lib_chron_first",
            sect_id=sect_id, continent_key=get_native_continent_for_sect(sect_id),
            importance=1,
        )
    except Exception:
        logger.debug("lib_first chronicle failed (player_id=%s)", player_id, exc_info=True)


async def _chronicle_first_hidden_art(session, player_id: int, sect_id: str) -> None:
    """Chronicle `sel_first` — o 1º segredo da Estante Oculta do servidor POR
    CASA. Espelho exato do `lib_first` (advisory lock namespaced próprio, senão
    as duas transmissões na mesma casa serializariam uma na outra)."""
    try:
        await session.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext('sel_first:' || :k))"),
            {"k": sect_id},
        )
        other = (await session.execute(
            select(PlayerSectTechnique.player_id)
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerSectTechnique.technique_id)
            .where(
                PlayerSectTechnique.sect_key == sect_id,
                PlayerSectTechnique.player_id != player_id,
                TechniqueCatalog.library_tier == RITE_TIER,
            )
            .limit(1)
        )).first()
        if other is not None:
            return
        from core.world_pulse_engine import emit_chronicle
        from core.world_sects_engine import get_native_continent_for_sect
        await emit_chronicle(
            session, event_type="sel_first", text_key="sel_chron_first",
            sect_id=sect_id, continent_key=get_native_continent_for_sect(sect_id),
            importance=2,
        )
    except Exception:
        logger.debug("sel_first chronicle failed (player_id=%s)", player_id, exc_info=True)


async def _chronicle_first_forbidden_art(session, player_id: int, sect_id: str) -> None:
    """Chronicle `fpd_first` — a 1ª arte do Cofre Proibido do servidor (o mundo
    inteiro sente quando o Abismo abre o que não devia). Espelho exato do
    `sel_first`, com advisory lock namespaced PRÓPRIO."""
    try:
        await session.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext('fpd_first:' || :k))"),
            {"k": sect_id},
        )
        other = (await session.execute(
            select(PlayerSectTechnique.player_id)
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerSectTechnique.technique_id)
            .where(
                PlayerSectTechnique.sect_key == sect_id,
                PlayerSectTechnique.player_id != player_id,
                TechniqueCatalog.library_tier == FORBIDDEN_TIERS[0],
            )
            .limit(1)
        )).first()
        if other is not None:
            return
        from core.world_pulse_engine import emit_chronicle
        from core.world_sects_engine import get_native_continent_for_sect
        await emit_chronicle(
            session, event_type="fpd_first", text_key="fpd_chron_first",
            sect_id=sect_id, continent_key=get_native_continent_for_sect(sect_id),
            importance=3,
        )
    except Exception:
        logger.debug("fpd_first chronicle failed (player_id=%s)", player_id, exc_info=True)


# ══════════════════════════════════════════════════════════════════════════
# TEC-3 — A PROVA DA SUCESSÃO 秘传 (o gate da Estante Oculta)
# ══════════════════════════════════════════════════════════════════════════
# "O segredo não tem preço" (Lei §4/§12): a câmara mais funda não se compra com
# contribuição — prova-se num duelo contra o Ancião que a guarda. Reusa
# `DuelSession` com `pve_source` PRÓPRIO ("hidden_rite"), espelhando o rito de
# entrada v16.4b (core/sect_trial_engine.py).
#
# ZERO MIGRATION por desenho: o estado do rito JÁ vive em `duel_sessions`
# (a row aberta = rito em curso; `resolved_at` da última terminal = o cooldown),
# lido pelo índice parcial que a Migration 094 já criou
# (`idx_duel_pve_source (attacker_id, pve_source) WHERE pve_source IS NOT NULL`).
# A PROVA de que o rito foi vencido é o registro eterno em
# `player_sect_techniques` — a mesma memória que sobrevive ao renascimento.


async def _rite_passed(session, player_id: int, sect_id: str) -> bool:
    """True se esta casa JÁ transmitiu o seu segredo a este cultivador alguma
    vez (registro eterno, sobrevive a prestige/renascimento e ao leave)."""
    try:
        row = (await session.execute(
            select(PlayerSectTechnique.technique_id)
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerSectTechnique.technique_id)
            .where(
                PlayerSectTechnique.player_id == player_id,
                PlayerSectTechnique.sect_key == sect_id,
                TechniqueCatalog.library_tier == RITE_TIER,
            )
            .limit(1)
        )).first()
        return row is not None
    except Exception:
        logger.debug("_rite_passed failed (player_id=%s)", player_id, exc_info=True)
        return False


async def _last_rite_duel(session, player_id: int):
    """A última Prova deste cultivador (aberta ou terminal). Usa o índice
    parcial da Mig 094 — zero coluna nova, zero migration (§1 do prompt)."""
    from database.models import DuelSession
    return (await session.execute(
        select(DuelSession)
        .where(
            DuelSession.attacker_id == player_id,
            DuelSession.pve_source == RITE_PVE_SOURCE,
        )
        .order_by(DuelSession.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def hidden_rite_state(session, player_id: int, sect_id: str) -> dict[str, Any]:
    """O estado da Prova para a view (Lei §1 — o requisito é sempre DITO).

    ``{passed, open_duel_id, cooldown_ms, can_start}``. Nunca levanta."""
    from datetime import datetime, timedelta, timezone
    out: dict[str, Any] = {
        "passed": False, "open_duel_id": None, "cooldown_ms": None, "can_start": True,
    }
    try:
        out["passed"] = await _rite_passed(session, player_id, sect_id)
        duel = await _last_rite_duel(session, player_id)
        if duel is None:
            return out
        if duel.state in ("waiting_actions", "pending_acceptance"):
            out["open_duel_id"] = str(duel.id)
            out["can_start"] = False
            return out
        resolved = duel.resolved_at
        if resolved is not None:
            until = resolved + timedelta(hours=max(0, SEL_RITE_COOLDOWN_H))
            now = datetime.now(timezone.utc)
            if until > now:
                out["cooldown_ms"] = int(until.timestamp() * 1000)
                out["can_start"] = False
        return out
    except Exception:
        logger.debug("hidden_rite_state failed (player_id=%s)", player_id, exc_info=True)
        return out


async def start_hidden_rite(session, player_id: int, tech_id: int) -> dict[str, Any]:
    """Abre a Prova da Sucessão pela arte `tech_id` da Estante Oculta.

    Gates em ordem disclosed: flag → membro → arte da casa/tier → posto heir →
    reino → karma alinhado → já aprendida → duelo aberto → cooldown → HP.
    Devolve ``{ok, duel_id}``; o caller commita. Espelha `start_sect_trial`.
    """
    if not selado_on():
        return {"ok": False, "reason": "sel_off"}

    from core.world_sects_engine import (
        DEFAULT_SECT_RANK,
        get_rank_label_key,
        is_valid_sect,
        rank_index,
    )

    tech_id = int(tech_id)
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}
    if not is_valid_sect(player.sect_id):
        return {"ok": False, "reason": "not_in_sect"}

    tech = (await session.execute(
        select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
    )).scalar_one_or_none()
    if tech is None or int(tech.library_tier or 0) != RITE_TIER:
        return {"ok": False, "reason": "tech_not_in_library"}
    if tech.sect_key != player.sect_id:
        return {"ok": False, "reason": "wrong_house"}

    min_rank = TIER_MIN_RANK[RITE_TIER]
    if rank_index(player.sect_rank or DEFAULT_SECT_RANK) < rank_index(min_rank):
        return {"ok": False, "reason": "rank_too_low",
                "req_rank_key": get_rank_label_key(min_rank)}
    if (player.realm or 0) < (tech.req_realm or 0):
        return {"ok": False, "reason": "realm_too_low", "req_realm": int(tech.req_realm or 0)}
    if not karma_gate_ok(player.karma, player.sect_id):
        return {"ok": False, "reason": "karma_too_low",
                "karma_need": int(SEL_KARMA_MIN),
                "karma_have": aligned_karma(player.karma, player.sect_id)}

    existing = (await session.execute(
        select(PlayerTechnique).where(
            PlayerTechnique.player_id == player_id,
            PlayerTechnique.technique_id == tech_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return {"ok": False, "reason": "already_learned"}

    # Retomar / curar a Prova anterior — espelho do §5-A/C do rito de entrada:
    # uma Prova terminal-mas-não-liquidada (o cultivador fechou o app antes do
    # último poll) é liquidada AGORA, senão a vitória sumia e o cooldown corria
    # contra ele. Sem isto, o rito herdaria o "permanentemente irresolúvel" que
    # o `sect_trial` tem hoje (recon §5, gap 1).
    prev = await _last_rite_duel(session, player_id)
    if prev is not None:
        if prev.state in ("waiting_actions", "pending_acceptance"):
            return {"ok": True, "duel_id": str(prev.id), "resumed": True}
        if prev.state in ("finished", "forfeited"):
            try:
                from core.duel_engine import apply_post_duel_effects
                await apply_post_duel_effects(session, prev)
                await session.flush()
            except Exception:
                logger.exception("start_hidden_rite: stale-duel settle failed duel=%s", prev.id)
            if await _rite_passed(session, player_id, player.sect_id):
                return {"ok": False, "reason": "rite_already_passed"}

    state = await hidden_rite_state(session, player_id, player.sect_id)
    if state.get("cooldown_ms"):
        return {"ok": False, "reason": "rite_cooldown", "cooldown_ms": state["cooldown_ms"]}

    # UMA verdade do "um duelo de cada vez" — o mesmo helper do rito de entrada
    # (que também cura um duelo estagnado antes de responder).
    try:
        from core.sect_trial_engine import _has_open_duel
        open_duel = await _has_open_duel(session, player_id)
    except Exception:
        logger.debug("start_hidden_rite open-duel check failed (player_id=%s)",
                     player_id, exc_info=True)
        open_duel = None
    if open_duel is not None:
        return {"ok": False, "reason": "duel_already_active", "duel_id": str(open_duel.id)}

    # HP pelo helper CANÔNICO (o rito de entrada usa get_current_hp — o Player
    # não tem coluna current_hp; ler o atributo cru estourava AttributeError).
    try:
        from core.combat_engine import get_current_hp
        if get_current_hp(player) <= 0:
            return {"ok": False, "reason": "hp_depleted"}
    except Exception:
        logger.debug("start_hidden_rite hp check failed (player_id=%s)",
                     player_id, exc_info=True)

    try:
        from core.duel_engine import start_duel_pve
        duel = await start_duel_pve(
            session, player,
            archetype="elder",          # o Ancião que guarda a câmara
            difficulty="hard",          # a Prova é mais dura que a entrada (normal)
            source=RITE_PVE_SOURCE,
            context={"sect_id": player.sect_id, "tech_id": tech_id},
        )
        await session.flush()
        return {"ok": True, "duel_id": str(duel.id), "tech_id": tech_id}
    except Exception:
        logger.exception("start_hidden_rite failed (player_id=%s, tech=%s)", player_id, tech_id)
        return {"ok": False, "reason": "internal_error"}


async def resolve_hidden_rite_from_duel(session, duel, player, won: bool) -> dict[str, Any]:
    """Liquida a Prova: vitória ⇒ a casa TRANSMITE o segredo (pelo mesmo helper
    da estante — zero divergência); derrota ⇒ cooldown (derivado de
    `resolved_at`, nada a gravar). Chamado por `settle_pve_duel`.

    Idempotente por construção: o grant passa por `already_learned` e pelo
    registro eterno, e o `pve_settled` do settle já barra a 2ª passagem."""
    payload: dict[str, Any] = {"rite": "won" if won else "lost"}
    if not won:
        return payload
    try:
        ctx = duel.pve_context or {}
        tech_id = int(ctx.get("tech_id") or 0)
        if not tech_id:
            return payload
        tech = (await session.execute(
            select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
        )).scalar_one_or_none()
        if tech is None or int(tech.library_tier or 0) != RITE_TIER:
            return payload
        # A casa tem de ser a MESMA de quando a Prova começou (sair no meio
        # não transmite o segredo de uma casa que já não é sua).
        if tech.sect_key != player.sect_id:
            return {**payload, "rite": "wrong_house"}
        already = (await session.execute(
            select(PlayerTechnique.technique_id).where(
                PlayerTechnique.player_id == player.telegram_id,
                PlayerTechnique.technique_id == tech_id,
            )
        )).first()
        if already is not None:
            return {**payload, "already_learned": True}
        prior_reg = (await session.execute(
            select(PlayerSectTechnique).where(
                PlayerSectTechnique.player_id == player.telegram_id,
                PlayerSectTechnique.technique_id == tech_id,
            )
        )).scalar_one_or_none()
        res = await _grant_library_art(
            session, player, tech, cost=0, prior_reg=prior_reg, tier=RITE_TIER,
        )
        payload.update({"tech_id": tech_id, "name": res.get("name"),
                        "emoji": res.get("emoji"),
                        "auto_equipped": res.get("auto_equipped")})
        return payload
    except Exception:
        logger.exception("resolve_hidden_rite_from_duel failed (duel=%s)", duel.id)
        return payload


# ── Ganchos gated (join / promoção / leave) — aditivos, try/except no caller ─
async def notify_library_opened(session, player_id: int, sect_id: str) -> None:
    """Auto-offer da Estante Externa ao ENTRAR na seita: "a Biblioteca te abre
    as primeiras estantes" (notificação, não auto-learn — agência + loadout
    respeitado). Gated + best-effort; o caller (join) já engole exceções."""
    if not biblioteca_on():
        return
    try:
        from core.notification_engine import notify
        await notify(
            session, player_id, "sect_library",
            title_key="notif_lib_open_title",
            body_key="notif_lib_open_body",
            ref_id=f"lib_open:{sect_id}",
            icon="📚", target_tab="profile", priority=3,
        )
    except Exception:
        logger.debug("notify_library_opened failed (player_id=%s)", player_id, exc_info=True)


async def notify_shelf_unlocked(session, player_id: int, new_rank: str) -> None:
    """Promoção que abre estante REAL (inner → Interna, core → Núcleo):
    "novas estantes se abrem". Gated + best-effort."""
    if not biblioteca_on():
        return
    # TEC-3 — elder/heir passam a abrir estante REAL; sem a flag continuam a
    # não notificar nada (Lei §5 — OFF ⇒ byte-idêntico).
    opens = ("inner", "core", "elder", "heir") if selado_on() else ("inner", "core")
    if new_rank not in opens:
        return
    try:
        from core.notification_engine import notify
        from core.world_sects_engine import get_rank_label_key
        await notify(
            session, player_id, "sect_library",
            title_key="notif_lib_shelf_title",
            body_key="notif_lib_shelf_body",
            payload={"rank_key": get_rank_label_key(new_rank)},
            ref_id=f"lib_shelf:{new_rank}",
            icon="📚", target_tab="profile", priority=3,
        )
    except Exception:
        logger.debug("notify_shelf_unlocked failed (player_id=%s)", player_id, exc_info=True)


async def lock_core_arts_on_leave(session, player_id: int, sect_id: str,
                                  lang: str = "pt") -> dict[str, Any]:
    """Ao SAIR da casa: desequipa as artes do Núcleo PARA CIMA (library_tier >=
    3 — Núcleo, Ancião, Oculta) daquela casa — o registro NUNCA é apagado;
    voltar à MESMA casa re-destranca (o equip-gate lê a casa atual). Tiers 1-2
    ficam usáveis ("lições básicas não se desaprendem"). As 45 legadas v16.4c
    ficam INTOCADAS (decisão owner 2026-06-16). Gated: OFF ⇒ zero queries, main
    byte-idêntico (sem `estantes_seladas` não existe arte tier 4/5 aprendida,
    logo o `>=` é idêntico ao `==` de antes).

    Devolve {locked: [nomes]} para a disclosure do leave. Nunca levanta."""
    from core.i18n import catalog_text
    # ⚠️ A lingua vem por PARAMETRO, nao de uma query aqui dentro. A 1a versao
    # disto resolvia-a no topo da funcao e a suite do TEC-1 ficou vermelha na
    # hora: a docstring promete "OFF ⇒ zero queries" e ela conta-as. O chamador
    # (`world_sects_engine.leave`) ja' tem o `player` carregado — pedir-lhe a
    # lingua custa zero e mantem a promessa.
    if not biblioteca_on():
        return {"locked": []}
    try:
        # SAVEPOINT próprio (review TEC-1, achado F9): somos chamados DENTRO
        # do SAVEPOINT do leave — um erro de DB aqui, engolido sem rollback,
        # envenenaria a transação e derrubaria o leave inteiro. O begin_nested
        # interno isola: falha aqui = só o lock não acontece, o leave vive.
        async with session.begin_nested():
            rows = (await session.execute(
                select(PlayerTechnique, TechniqueCatalog.name, TechniqueCatalog.emoji)
                .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
                .where(
                    PlayerTechnique.player_id == player_id,
                    PlayerTechnique.is_active_combat == True,  # noqa: E712
                    TechniqueCatalog.sect_key == sect_id,
                    TechniqueCatalog.library_tier >= LOCK_TIER_FLOOR,
                )
            )).all()
            locked = []
            for pt, name, emoji in rows:
                pt.is_active_combat = False
                # 名 2026-09-14 — coluna desempacotada; o nome das artes que
                # ficam trancadas ao sair da casa saia cru.
                locked.append({"name": catalog_text(lang, "tech",
                                                    getattr(pt, "technique_id", None),
                                                    "name", name),
                               "emoji": emoji or "⚔️"})
        return {"locked": locked}
    except Exception:
        logger.debug("lock_core_arts_on_leave failed (player_id=%s)", player_id, exc_info=True)
        return {"locked": []}


async def count_learnable_now(session, player_id: int) -> int:
    """Quantas artes novas o membro PODE aprender agora (badge honesto do
    /biblioteca e da linha do menu — 0 é resposta válida). Flag OFF → 0 sem
    query."""
    if not biblioteca_on():
        return 0
    try:
        view = await get_library_shelves(session, player_id)
        if not view.get("in_sect"):
            return 0
        return sum(
            1 for shelf in view.get("shelves", [])
            for art in shelf.get("arts", [])
            if art.get("can_learn")
        )
    except Exception:
        logger.debug("count_learnable_now failed (player_id=%s)", player_id, exc_info=True)
        return 0
