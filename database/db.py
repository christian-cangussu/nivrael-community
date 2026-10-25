import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import (
    DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW,
    WORLD_DEFAULT_POOL_SIZE, WORLD_DEFAULT_MAX_OVERFLOW,
    MONETIZATION_ENABLED,
)

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────────────────────────────────────
# Multi-world routing (Sistema Multi-Servidor — Fase 1)
#
# The bot runs N ISOLATED game worlds (each = its own Postgres DB) inside ONE
# process. A request/job selects its world by setting the `current_world`
# ContextVar; get_session_factory() then returns THAT world's sessionmaker.
# With NO contextvar set, everything resolves to the DEFAULT world ("main"),
# bound to the unchanged DATABASE_URL + pool config — so the live server behaves
# EXACTLY as before. ContextVars are task-local, so concurrent requests/jobs
# never leak a world into one another.
#
# Safety invariants (Leis §1/§5):
#   • "main" is ALWAYS resolvable from config ALONE (DATABASE_URL + DB_POOL_SIZE)
#     WITHOUT the control DB — a control-plane outage degrades to main-only, it
#     never crashes the bot. The control row for `main` is IGNORED for engine
#     binding (so a corrupt control DB can never redirect main's traffic).
#   • Any unresolved / unknown world falls back to "main".
# ──────────────────────────────────────────────────────────────────────────────

MAIN_WORLD_KEY = "main"

# Per-world engines + sessionmakers, keyed by server_key (built lazily).
_world_engines: dict = {}
_world_sessionmakers: dict = {}

# server_key -> {db_url, pool_size, max_overflow, monetization_enabled, ...}.
# Always contains MAIN_WORLD_KEY (injected from config); secondary worlds are
# merged in by load_world_registry() at startup from the control DB.
_world_registry: dict = {}

# The world selected for the current task (request / scheduler iteration).
# None -> resolve to MAIN_WORLD_KEY.
current_world: ContextVar = ContextVar("current_world", default=None)

# Back-compat aliases: kept pointing at the DEFAULT (main) world's objects so
# `from database.db import engine` (resource_monitor pool stats) + the ops
# scripts that import `engine`/`async_session`/`_ensure_engine` keep working.
engine = None
async_session = None


def _normalize_asyncpg(url: str) -> str:
    url = (url or "").replace("postgresql://", "postgresql+asyncpg://")
    url = url.replace("postgres://", "postgresql+asyncpg://")
    return url


def _get_db_url() -> str:
    # Back-compat: the main world's URL (used by ops scripts that call this).
    return _normalize_asyncpg(DATABASE_URL)


def _main_world_row() -> dict:
    """The DEFAULT world, derivable from config ALONE (no control DB needed).
    This is what guarantees `main` is always routable even if the control DB is
    down — and it is bound to the SAME DATABASE_URL + pool config as before."""
    return {
        "key": MAIN_WORLD_KEY,
        "name": "Servidor Principal",
        "db_url": DATABASE_URL,
        "status": "active",
        "is_default": True,
        "requires_code": False,
        "monetization_enabled": MONETIZATION_ENABLED,  # 開 edição comunitária: OFF por defeito
        "is_public": True,
        "pool_size": DB_POOL_SIZE,
        "max_overflow": DB_MAX_OVERFLOW,
        "balance_config": {},  # ignored for main (get_world_balance locks defaults)
    }


def _ensure_main_registered() -> None:
    if MAIN_WORLD_KEY not in _world_registry:
        _world_registry[MAIN_WORLD_KEY] = _main_world_row()


def _registry_row(key: str) -> dict:
    """Return the registry row for `key`, falling back to main for unknown worlds
    (Lei §1: never crash on a resolution miss)."""
    _ensure_main_registered()
    row = _world_registry.get(key)
    if row is None:
        logger.warning("world %r not in registry — falling back to %r", key, MAIN_WORLD_KEY)
        return _world_registry[MAIN_WORLD_KEY]
    return row


def _build_world_engine(row: dict):
    # O registo guarda o endereço; o login vem do env (control_db, 2026-10-24).
    from database.control_db import with_env_credentials
    db_url = _normalize_asyncpg(with_env_credentials(row.get("db_url") or ""))
    if not db_url or "asyncpg://" not in db_url:
        raise RuntimeError(
            f"world {row.get('key')!r}: database URL not configured — check the registry/.env"
        )
    is_main = row.get("key") == MAIN_WORLD_KEY
    default_pool = DB_POOL_SIZE if is_main else WORLD_DEFAULT_POOL_SIZE
    default_overflow = DB_MAX_OVERFLOW if is_main else WORLD_DEFAULT_MAX_OVERFLOW
    pool_size = row.get("pool_size") or default_pool
    mo = row.get("max_overflow")
    max_overflow = mo if mo is not None else default_overflow
    return create_async_engine(
        db_url,
        echo=False,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_timeout=10,
        pool_reset_on_return="rollback",
        connect_args={
            "command_timeout": 15,
            "server_settings": {
                "idle_in_transaction_session_timeout": "30000",
                "statement_timeout": "15000",
            },
        },
    )


def _ensure_world(key: str):
    """Return (engine, sessionmaker) for `key`, building lazily. Updates the
    legacy module globals `engine`/`async_session` when (re)building main."""
    global engine, async_session
    sm = _world_sessionmakers.get(key)
    if sm is not None:
        return _world_engines[key], sm
    row = _registry_row(key)
    real_key = row["key"]  # may have been redirected to main on an unknown key
    sm = _world_sessionmakers.get(real_key)
    if sm is None:
        eng = _build_world_engine(row)
        sm = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        _world_engines[real_key] = eng
        _world_sessionmakers[real_key] = sm
        if real_key == MAIN_WORLD_KEY:
            engine, async_session = eng, sm
    return _world_engines[real_key], _world_sessionmakers[real_key]


def _resolve_world_key() -> str:
    return current_world.get() or MAIN_WORLD_KEY


def _ensure_engine():
    """Back-compat shim: ensure the DEFAULT (main) world engine + module globals
    are built. Kept because ops scripts import `_ensure_engine` directly."""
    _ensure_world(MAIN_WORLD_KEY)


# ── ContextVar helpers ──────────────────────────────────────────────────────
def set_current_world(key: str):
    """Bind the active world for the current task. Returns a token for reset."""
    return current_world.set(key)


def reset_current_world(token) -> None:
    current_world.reset(token)


@contextmanager
def use_world(key: str):
    """Scope a block of code to a world. Used by the scheduler (Fase 3) to run a
    job against each registered world: `with use_world(key): ...`."""
    token = current_world.set(key)
    try:
        yield
    finally:
        current_world.reset(token)


def current_world_key() -> str:
    """The world bound to the current task (``main`` if unset)."""
    return _resolve_world_key()


def iter_world_keys() -> list[str]:
    """All world keys the scheduler should tick (Fase 3): ``main`` first, then the
    registered secondary worlds (sorted). Returns a single ``["main"]`` when no
    secondary world exists — the scheduler uses that length-1 result to run each
    job EXACTLY as before (no per-world loop, no contextvar), so the live
    deployment is byte-identical until a secondary world is provisioned."""
    _ensure_main_registered()
    secondaries = sorted(k for k in _world_registry if k != MAIN_WORLD_KEY)
    return [MAIN_WORLD_KEY] + secondaries


def iter_active_world_keys() -> list[str]:
    """World keys the SCHEDULER should tick: ``main`` (always) + secondary worlds
    whose in-memory registry row is ``status == 'active'``.

    Distinct from ``iter_world_keys()`` (which lists EVERY known world for admin
    validation): a world that is still building (``'maintenance'``), paused
    (``'closed'``), or left over from a FAILED provision is NOT active and must
    never be ticked — it has no schema yet, so a per-world job would fail every
    cycle (2026-06-24 incident: a non-ready world made cultivation_tick churn
    ~1100 failing batches per tick). Returns ``["main"]`` when no secondary world
    is active → the scheduler keeps its byte-identical single-world fast path."""
    _ensure_main_registered()
    secondaries = sorted(
        k for k, row in _world_registry.items()
        if k != MAIN_WORLD_KEY and (row or {}).get("status", "active") == "active"
    )
    return [MAIN_WORLD_KEY] + secondaries


def signup_world_key() -> str:
    """O mundo onde um jogador NOVO nasce (pivot 2026-08-11).

    Até aqui o Nivrael não tinha este conceito: um jogador desconhecido caía em
    `main` por AUSÊNCIA de decisão (não havia row em `player_active_server`, e
    `resolve_active_world` devolvia `main`). Isso funcionou enquanto `main` era o
    único mundo com gente — mas o `main` é agora o **Mundo Legado** (240
    personagens, compras reais, balance antigo, todas as 28 flags OFF por
    construção) e quem chega hoje tem de nascer no mundo NOVO.

    A fonte de verdade é a coluna `servers.is_default` do plano de controlo — que
    existia e era **dado morto** (escrita no bootstrap, exibida no painel, lida
    por NINGUÉM). Passa a significar exatamente o que o nome diz: *é aqui que se
    nasce*.

    ⚠️ O DESEMPATE IMPORTA. `main` NUNCA lê a sua própria row de controlo: o
    registry monta-o sempre a partir de `_main_world_row()`, que fixa
    `is_default=True` (`load_world_registry` salta a row de `main` de propósito,
    para o `main` continuar routável mesmo com o control DB em baixo). Logo há
    SEMPRE pelo menos um candidato, e a preferência tem de ser explícita: um
    mundo secundário marcado por defeito GANHA do `main`. Sem isto, ligar o
    switch no control DB não teria efeito nenhum e o bug seria invisível.

    Ordem: env `SIGNUP_WORLD` (a válvula de ops) → secundário ativo com
    `is_default` → `main`. Fail-safe total: qualquer erro devolve `main`.
    """
    try:
        _ensure_main_registered()
        forced = (os.getenv("SIGNUP_WORLD") or "").strip().lower()
        if forced:
            row = _world_registry.get(forced)
            if row is not None and (row or {}).get("status", "active") == "active":
                return forced
            if forced == MAIN_WORLD_KEY:
                return MAIN_WORLD_KEY
            logger.warning("SIGNUP_WORLD=%s desconhecido/inativo — a nascer em main", forced)
            return MAIN_WORLD_KEY
        cands = sorted(
            k for k, row in _world_registry.items()
            if k != MAIN_WORLD_KEY
            and (row or {}).get("status", "active") == "active"
            and bool((row or {}).get("is_default"))
        )
        return cands[0] if cands else MAIN_WORLD_KEY
    except Exception:
        logger.warning("signup_world_key failed — a nascer em main", exc_info=True)
        return MAIN_WORLD_KEY


def world_db_target(key: str) -> str:
    """A creds-FREE ``host:port/dbname`` for a world, for diagnostic logs. NEVER
    includes the password. Returns ``'?'`` when the target is unknown."""
    try:
        from urllib.parse import urlparse
        row = _world_registry.get(key) or {}
        url = row.get("db_url") or (DATABASE_URL if key == MAIN_WORLD_KEY else "")
        if not url:
            return "?"
        p = urlparse(url.replace("+asyncpg", ""))
        return f"{p.hostname or '?'}:{p.port or ''}{p.path or ''}"
    except Exception:
        return "?"


# ── Per-server balance config (Fase 2) ──────────────────────────────────────
# Each secondary world can run a DIFFERENT balance (slower cultivation, harder
# breakthroughs, …) WITHOUT touching `main`. The knobs are stored as JSONB on the
# control-DB `servers` row and merged into the world registry; the engine reads
# them via get_world_balance() keyed by the current_world ContextVar.
#
# Only `cultivation_speed` is WIRED LIVE today (it scales CB gain in
# game_logic.calculate_cb_per_tick → every realm takes proportionally longer,
# with ZERO display inconsistency since thresholds are unchanged). The rest are
# STORED for the systems that will read them as they are built (kept honest in
# the admin UI — Lei §1). `main` ALWAYS returns the defaults: the row's config is
# ignored for main, so the 57 real players can never be affected by a stray edit.
DEFAULT_WORLD_BALANCE = {
    "cultivation_speed": 1.0,        # LIVE — <1.0 = slower cultivation (slower realms)
    "breakthrough_difficulty": 1.0,  # stored — future: scales realm thresholds
    "drop_rate": 1.0,                # stored — future: scales loot/drop chances
    "qi_cost": 1.0,                  # stored — future: scales action qi costs
    "profession_speed": 1.0,         # LIVE (MV-7) — multiplica TODO ganho de XP de profissão (profession_engine)
    # ── v16.7-K keystone (combate comensurável, server-gated; main → defaults → OFF) ──
    # NOT multipliers: see _sanitize_balance for their own ranges (0.0 floor).
    "qi_band_s": 0.0,                # LIVE — >0 saturates the qi COMBAT contribution (raw-qi units); 0 = OFF/legacy
    "body_throttle_enabled": 0.0,    # LIVE — >0 enables Limitação Corporal (body caps EXPRESSED power)
    "body_throttle_base": 0.0,       # knob — throttle base (~2.15 → 1×/10×/100× by gap); <=1 = OFF
    "body_throttle_cap": 0.0,        # knob — max gap D counted by the throttle
}

# The knobs wired into the live engine today. The admin UI surfaces all of
# DEFAULT_WORLD_BALANCE but marks the rest as not-yet-applied. body_throttle_base/cap
# ARE live (combat_engine reads them whenever body_throttle_enabled > 0) — marked live
# so the admin panel shows them as applied, not "future".
LIVE_BALANCE_KEYS = (
    "cultivation_speed", "qi_band_s",
    "body_throttle_enabled", "body_throttle_base", "body_throttle_cap",
    "profession_speed",
)

# ── Limitação Corporal — recommended "fresh-server" preset (Sprint 8/Onda 3) ──────
# Turning this ON makes the Cultivo do Corpo MATTER in combat: a cultivator whose body
# lags the realm (gap D = realm − body_stage) has THROTTLED strike = 1 / base^min(D,cap).
# This is the per-WORLD switch the owner flips on a FRESH server — it is NEVER applied to
# `main` (get_world_balance ignores main's stored config → the 57 stay at the 0.0 defaults
# = throttle OFF = byte-identical). Start MODERATE; raise `body_throttle_base` toward ~2.15
# for a harsher "the body matters a lot" world (2.15 → ~10× weaker at gap 3, ~100× at gap 6).
LAUNCH_COMBAT_PRESET = {
    "body_throttle_enabled": 1.0,   # ON
    "body_throttle_base": 1.5,      # moderate: gap 3 → ~1/3.4 strike, gap 4 → ~1/5
    "body_throttle_cap": 4.0,       # ignore gaps beyond 4 (don't crush deep neglect to 0)
}

# Self-documentation for the admin panel — what each knob DOES, what it CHANGES, and a
# sane value. Owner controls each server by switches; the panel must explain each knob
# (Lei §6 / feedback: bake defaults + self-document, don't quiz the owner).
BALANCE_KNOB_DOCS = {
    "cultivation_speed":     {"label": "Velocidade de Cultivo", "live": True,
                              "desc": "Multiplica o ganho de CB por tick. <1 = reinos mais lentos.",
                              "recommended": 1.0, "changes": "Ritmo de progressão de todos."},
    "qi_band_s":             {"label": "Banda de Qi (combate)", "live": True,
                              "desc": "Satura a contribuição do Qi no dano (Três Tesouros). 0 = legado (Qi cru). >0 = teto comensurável.",
                              "recommended": "afinar à escala de qi do servidor", "changes": "Reduz a degenração mono-qi em combate."},
    "body_throttle_enabled": {"label": "Limitação Corporal: LIGAR", "live": True,
                              "desc": "1 = liga o throttle (corpo atrasado → strike reduzido). 0 = OFF (legado).",
                              "recommended": 1.0, "changes": "Faz o Cultivo do Corpo importar em combate."},
    "body_throttle_base":    {"label": "Limitação Corporal: dureza", "live": True,
                              "desc": "Base do throttle: strike = 1/base^gap. 1.5 = moderado; 2.15 = duro (10×@gap3, 100×@gap6).",
                              "recommended": 1.5, "changes": "Quão punitivo é ter o corpo atrasado."},
    "body_throttle_cap":     {"label": "Limitação Corporal: teto do gap", "live": True,
                              "desc": "Gap máximo contado (não esmaga negligência total a zero). 4 = sensato.",
                              "recommended": 4.0, "changes": "Limita o pior caso do throttle."},
    "breakthrough_difficulty": {"label": "Dificuldade de Breakthrough", "live": False,
                              "desc": "Futuro: escala os thresholds de realm.", "recommended": 1.0, "changes": "(ainda não aplicado)"},
    "drop_rate":             {"label": "Taxa de Drops", "live": False,
                              "desc": "Futuro: escala loot/drops.", "recommended": 1.0, "changes": "(ainda não aplicado)"},
    "qi_cost":               {"label": "Custo de Qi", "live": False,
                              "desc": "Futuro: escala o custo de qi das acções.", "recommended": 1.0, "changes": "(ainda não aplicado)"},
    "profession_speed":      {"label": "Velocidade de Profissão", "live": True,
                              "desc": "MV-7: multiplica TODO ganho de XP de ofício (exige a feature 'profissoes' ON). 1.0 = normal; <1 = ofícios mais lentos.",
                              "recommended": 1.0, "changes": "Ritmo dos tiers de profissão (Aprendiz→Grão-Mestre)."},
}


def _coerce_balance_config(raw) -> dict:
    """Normalize a stored balance_config (asyncpg may hand back JSONB as a str)
    into a plain dict. Never raises — a malformed value degrades to {}."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except Exception:
            return {}
    return raw if isinstance(raw, dict) else {}


def get_world_balance(key: str | None = None) -> dict:
    """Return the active (or given) world's balance multipliers, merged over
    DEFAULT_WORLD_BALANCE. Sync + no I/O (reads the in-memory registry keyed by
    the current_world ContextVar) so it is safe on the hot cultivation path.

    `main` ALWAYS returns the defaults — its stored config is ignored so the live
    players are never affected. Unknown world → defaults (degrade to main)."""
    if key is None:
        key = _resolve_world_key()
    if key == MAIN_WORLD_KEY:
        return dict(DEFAULT_WORLD_BALANCE)
    _ensure_main_registered()
    row = _world_registry.get(key)
    if row is None:
        return dict(DEFAULT_WORLD_BALANCE)
    cfg = _coerce_balance_config(row.get("balance_config"))
    merged = dict(DEFAULT_WORLD_BALANCE)
    for k, v in cfg.items():
        if k in merged:
            try:
                merged[k] = float(v)
            except (TypeError, ValueError):
                pass  # keep the default for a non-numeric value
    return merged


def set_world_balance(key: str, config: dict) -> None:
    """Update a world's in-memory balance so a live admin edit takes effect
    without a restart (the control DB is the persistent source of truth; this
    keeps the registry hot-copy in sync). No-op for main / unknown worlds."""
    if not key or key == MAIN_WORLD_KEY:
        return
    _ensure_main_registered()
    row = _world_registry.get(key)
    if row is not None:
        row["balance_config"] = _coerce_balance_config(config)


# ── v16.7-FF per-world feature flags (mirrors the balance block above) ─────────
# On/off switches stored in servers.balance_config["features"] (a JSONB sub-block
# — ZERO migration, reuses the column). NEW/experimental features default OFF
# (FF-1: opt-in per world); base game features the `main` already runs are NOT
# gated here. `main` ALWAYS returns the defaults — its stored features are IGNORED
# (blindado por construção, exactly like get_world_balance → Lei §1). The real gate
# of each feature lands in Fase 3, one entry-point at a time; today these helpers
# are dead-but-ready (nothing calls feature_enabled_for_world yet).
DEFAULT_WORLD_FEATURES = {
    # NOVAS/experimentais — OFF por defeito (FF-1), opt-in por mundo.
    # O gate real de cada uma entra na Fase 3, quando a feature shippar.
    "cultivo_corpo_r0":    False,   # Cultivo do Corpo @ R0 (Sprint 2)
    "horta":               False,   # Horta Espiritual 灵田 (na caverna)
    "formacoes":           False,   # Formações 阵法 (na caverna)
    "breakthrough_trials": False,   # cerimónia-semente R0-R3 (BT-1..4)
    "ftue_espinha":        False,   # a 1ª hora costurada (FTUE-S1..S6)
    "racas":               False,   # Raças jogáveis (Sprint 1, disclosure-only)
    "progressao_visivel":  False,   # Progressão Visível — Poder de Combate agregado + antes→depois em todo avanço
    "combate_unificado":   False,   # Combate Unificado — TODA fonte de poder morde a luta (HP lê equip/fundação/Dao; Dao all-stats/técnicas/conquistas)
    "manifest_canary":     False,   # Sprint 0 — canário do Manifesto de Superfície (prova de gating; dormante)
    "ui_v2":               False,   # Redesign "O Pergaminho Vivo" (REDESIGN_MASTER.md) — shell v2 do mini-app.
                                    # GRADUADO (R6, 2026-07-10): 100% flag-driven — mundo ON → todos veem o v2.
                                    # Launch server nasce ON; main lê defaults (OFF eterno); kill-switch = este toggle.
    "dungeons_regionais":  False,   # MV-1 Mundo Vivo v2 — dungeons ancoradas por continente (Portais mostra só o local)
    "tiandao_director":    False,   # MV-2 Mundo Vivo v2 — o Céu gera eventos com lugar+prazo+consequência (Marés, Meteoros)
    "estados_regionais":   False,   # MV-3 Mundo Vivo v2 — cada continente tem um estado vivo (prospera/tensa/sitiada/festival) com overrides reais
    "corpo_profundo":      False,   # MV-4 Mundo Vivo v2 — meridianos (12 canais, ritual difícil) + refino ancorado em lugar (caverna > sítio > estrada)
    "quests_vivas":        False,   # MV-5 Mundo Vivo v2 — storylets/QBN: quests que só existem quando o mundo as torna verdadeiras, oferecidas por encontros com NPC
    "reputacao_rival":     False,   # MV-6 Mundo Vivo v2 — reputação regional (1 int por continente que o lugar SENTE) + o RIVAL com memória (NPC derrotado volta mais forte citando a derrota)
    "profissoes":          False,   # MV-7 Mundo Vivo v2 — Profissões Wuxia (1 ofício/jogador que MORDE nos engines: alquimia/forja/cura) + Relatório do Mercado Imperial; consome o knob profession_speed e conversa com geografia (MV-1) e rep (MV-6)
    "biblioteca_seitas":   False,   # TEC-1 Técnicas & Escassez — a Biblioteca da Seita em estantes (Externa/Interna/Núcleo): artes exclusivas da casa destrancadas por posto + contribuição (saldo do Pavilhão) + quest da casa; sair locka o tier 3 (nunca apaga); exige seita NPC (v16.4)
    "escassez_scrolls":    False,   # TEC-2 Técnicas & Escassez — Drop Reset + Economia do Pergaminho: corta o faucet de pergaminhos (masmorra/NPC/arena) e dá DESTINO ao pergaminho (doar à Biblioteca por contribuição · queimar em Ritual de Compreensão por Intenção). LAUNCH-SERVER-BOUND: nunca ligar em mundo com economia viva sem compensação
    "estantes_seladas":    False,   # TEC-3 Técnicas & Escassez — As Duas Estantes Seladas: as câmaras do Ancião 传功 (tier 4) e Oculta 秘传 (tier 5) deixam de ser teaser e viram estantes REAIS (9+9 artes novas). Ancião = posto elder + SEL_T4_CP do SALDO + reino; Oculta = posto heir + karma ALINHADO com a casa (SEL_KARMA_MIN; -karma na casa demoníaca) + a Prova da Sucessão (duelo, sem CP — o segredo não se compra). Sair da casa passa a trancar tier >= 3. DEPENDE de biblioteca_seitas ON. LAUNCH-SERVER-BOUND
    "legacy_caves":        False,   # TEC-4 Técnicas & Escassez — Grutas do Legado 传承洞: quando uma casa rola seek_inheritance no World Pulse, chance (LGC_OPEN_CHANCE) de a tumba de UM dos 5 NPCs lendários abrir VISITÁVEL no mapa por LGC_TTL_H horas (1 ativa no mundo · cooldown global · drift 70/30 de continente · pity 7d). Entrar = 1 duelo vs o Eco do Legado (1 tentativa por abertura); vitória SEMPRE paga (pedras+material+fragmento R5+); a arte única da casa (ids 600-604) sai por LGC_ART_CHANCE + pity no 3º clear. INDEPENDENTE de tiandao_director (sweep próprio). LAUNCH-SERVER-BOUND
    "forbidden_path":      False,   # TEC-5 Técnicas & Escassez — Caminho Proibido 禁道: o Cofre Proibido 禁库 (estante 6 da Biblioteca, SÓ abyssal_depths: heir + path demonic + karma ALINHADO >= FP_KARMA_MIN + o registro do Rito, SEM contribuição — o segredo não se compra) com 3 artes novas (605-607); o CUSTO REAL por uso das artes proibidas {604,605,606,607}, cobrado no settle varrendo o action_log: karma `forbidden_tech_use` (-20) + ANOS do Mar de Longevidade (age_years, o 1º writer da Mig 121) + a trava honesta no teto; fora do duelo verdadeiro elas NÃO somam (excluídas do simulate_combat e do World Boss); o Rito do Coração-Demônio 心魔 (duelo contra O REFLEXO — a divergência de karma finalmente tem corpo: ATRAVESSAR re-cristaliza o Path, REAFIRMAR é livre, perder morde soul_strength) e com ele a divergência do ERRANTE a |karma| >= 500; o gatilho da tumba de Lǐ Xuèyè em Mòyǔ (exige `legacy_caves` ON); e a SEVERIDADE de tribulação por |karma| (1.5x/2x/3x) que o KarmaModal promete desde a v16.3. O Cofre exige `biblioteca_seitas` + `estantes_seladas` ON (conjunção no engine). ZERO migration. LAUNCH-SERVER-BOUND
    "jianghu":             False,   # MV-8 Mundo Vivo v2 — O Jiānghú 江湖 "Rios e Lagos": os npc_cultivators deixam de ser estátuas e QUEREM coisas. 4 goals DERIVADOS (sem tabela nova: o goal é função pura semeada por (world_key, npc_id, tick_epoch) e resolve no próprio tick) escolhidos por utilidade contra um quadro de oportunidades também derivado — 🗡️ Atrás de você (a emboscada) · 🚩 Marchando sobre {continent} (escreve continent_key numa row `origin='seed'` ⇒ praça/explore/viagem/giver de storylet seguem o sujeito sem UM leitor novo) · 📜 Cobrando um contrato (o NPC leva o bounty que ninguém reclamou) · 🩸 Em dívida de sangue (NPC × NPC — a notícia que não é sobre você). O elenco é SÓ `origin='seed'` (source_hash NULL — as únicas rows que nenhum job reescreve; os echoes são re-assinados de 6h em 6h pelo snapshot). A EMBOSCADA é encontro com ESCOLHA (⚔️ enfrentar / 💰 subornar / 🏃 recuar), NUNCA duelo forçado (Lei §1 — o precedente é o `no forced losses` da arena). Traz também a 🚩 BANDEIRA: o 5º estado regional "ocupada" que o MV-3 deixou pendente, causado pela presença de NPCs de uma casa num continente ESTRANGEIRO. E a latência de LEITURA na Chronicle (perto: imediato; longe: 6-12h) — o que finalmente torna verdade o "simulação e interface saem da mesma tabela". Overrides mecânicos da Bandeira exigem `estados_regionais` ON; a porta de reputação da emboscada exige `reputacao_rival` ON (as duas conjunções são DECLARADAS, nunca silenciosas). ZERO migration. LAUNCH-SERVER-BOUND
    "cidades":             False,   # MV-9 Mundo Vivo v2 — As Cinco Cidades 城: cada continente deixa de ser um rótulo e ganha UMA cidade com NOME (Wànshì 万事城 · Templo do Punho de Ferro · Jardim das Dez Mil Flores · Forja de Tiānhuǒ · Cidade dos Ecos — todos do world_lore §3, zero invenção). Hoje o cabeçalho diz "Praça de Wànshì" nos CINCO continentes: para os 53% dos ativos que estão fora de Línghé isso é mentira, e o Quadro manda-os aos "Arquivos de Wànshì" que ficam noutro continente (violação de Lei §1 ANTERIOR a esta onda). A cidade traz o ENCARGO 城务 — o pedido PERMANENTE do lugar, derivado por (world_key, continent, tick de 6h) sobre `CITY_META[c]["encargos"]` e modulado pelo estado regional (MV-3) e pelo evento do Céu (MV-2): sem tabela de encargos, sem sweep de órfãos, sem kill-switch a construir. O motor é o storylet do MV-5 com DONO FIXO (weight=0 ⇒ fora do sorteio do pacer, mas SEMPRE visível na cidade — nunca escondido, Lei §1) e o progresso reusa os trackers existentes (PvP `sparring`/`win_sparring` VETADOS — 0 em 30d no main, 0 desde sempre no s2). A descoberta é o UNFOLDING derivado da Crônica: quem está longe lê o encargo que a cidade tinha quando a notícia partiu (rumor_delay_hours do MV-8 aplicado à DERIVAÇÃO, zero storage) — o nome e o emoji das cinco cidades, esses, aparecem SEMPRE. Paga a dívida do MV-1 (o `elsewhere_summary` anônimo passa a lista COMPLETA com `here`+`reason_key`, molde project_environment). O Encargo DEPENDE de `quests_vivas` ON (conjunção declarada, precedente TEC-3): com ela OFF a cidade ainda tem nome, identidade e razão-de-ir — e DIZ que o encargo está fechado. ZERO migration. LAUNCH-SERVER-BOUND
    "marca_do_tracado":    False,   # 印记 Marca do Traçado (report [jogador] "Script Master") — maestria POR FORMAÇÃO, contada em ativações NO CORPO (a caverna não conta: a escolha tem de doer). 3 degraus VISÍVEIS desde a 1ª ativação: 印 Traço (50) +MARCA_DURATION_BONUS de duração DESSA formação · 沟 Sulco (200) desconto no craft DELA (-20% pedras e -1 unidade na linha de material principal, mínimo 1) · 印记 Marca (1000) título COSMÉTICO + a marca no perfil. Nunca toca na POTÊNCIA (o número do buff não sobe), nunca torna a formação permanente (o buff continua a expirar e o sink continua a ser pago) e nunca dá bônus por título — as três coisas que matariam o sistema (Lei §3/§4). Trocar de formação custa a maestria acumulada: é o dilema, não um efeito colateral. Migration 138 (`player_formations.body_uses`). LAUNCH-SERVER-BOUND
    "caravana":            False,   # MV-9.5 商队 A Caravana (report [jogador] 06/08) — o jogo passa a DIZER onde nasce cada material, e a cidade ganha um velho que MANDA VIR o que a montanha do outro lado guarda. Escambo material↔material com prazo: ZERO pedras no fluxo (o preço em moeda é inválido por construção — para o novato de 553 pedras levar 10 ervas o preço tem de ser ≤55, para a mediana ativa de 846.985.667 ficar limitada a 1.000 tem de ser ≥846.986: conjunto vazio, 4,2 ordens de grandeza). Paga-se em material do próprio continente, a razão é sempre DESFAVORÁVEL (sink estrito) e ir a pé é sempre melhor — o velho diz isso na cara. Quatro recusas nomeadas (por lugar · por carga aberta · por Encargo vigente · por ALMA: karma/Caminho, o único eixo sem gate de flag). A disclosure é a maior parte do valor: hoje NÃO existe uma tela em todo o Nivrael que diga onde nasce um material, e a origem impressa é a UNIÃO MEDIDA das fontes vivas (seeds de masmorra + REGIONAL_BONUS_LOOT + grutas do legado + as fontes sem geografia, como a caçada difícil que solta erva t3 em qualquer lado) — nunca uma exclusividade que o código não sustenta. CONJUNÇÃO DURA com `cidades` (a caravana é da cidade) E com `dungeons_regionais` (sem portais ancorados a geografia não existe: com essa flag OFF as 23 masmorras são entráveis de qualquer continente e "vá a Qiānhé" seria mentira). ZERO migration. LAUNCH-SERVER-BOUND
    "tempo_do_ceu":        False,   # MV-11 天时 O Tempo do Céu — 天时地利人和: a vantagem da Terra 地利 já é o MV-3 e a harmonia dos homens 人和 já é o MV-8; 天时 é QUANDO, e é a única das três que este jogo nunca abriu. O céu tem temperamento: um só para o mundo inteiro (não por continente — a medição diz que a geografia alcança 3 jogadores por mês: 216 dos 239 nunca saíram de Línghé, o mercado está a zero há 38 dias e `region_states` tem 0 rows em `main`), derivado por função PURA semeada por (world_key, epoch de 12h) ⇒ ZERO tabela, ZERO row, ZERO migration, ZERO job novo, ZERO sweep de órfãos, e imune ao drift de boot do World Pulse. Três céus com dente (🌩️ Irado ×1.12 · ⛅ Sereno ×1.00 EXATO · 🌫️ Véu de Nuvens ×0.88, pesos 25/50/25) e morde num ÚNICO chokepoint — `tribulation_engine.get_tribulation_power` — logo os 5 call sites (2 rolagens + 3 previsões) herdam `display = roll` por construção, não por disciplina. A Tribulação foi escolhida por medição: 713 eventos / 22 jogadores distintos em 30d, **7× o alcance da geografia inteira**, e é a única mecânica de alto risco que não depende de viajar, de mercado, de outro jogador vivo nem de flag nenhuma — 雷劫 e 天时 são o mesmo campo semântico. ±12% foi decidido pela VARREDURA da simulação, não escolhido: 6% é ruído (1,7pp, ninguém lê) e 20%/30% matam o `trib_blessing` de 50 jade (+5,5pp) — 12% dá 3,3pp mediano e o jade sobrevive (Lei §4: o jade vende "não esperar", o céu vende "esperar"; o céu NUNCA é comprável, dissipável ou re-rolável, e nenhum item existente escala com ele). O agregado medido é −0,04 sucessos/dia no mundo inteiro: não é faucet, é ESCOLHA. E o céu é o ÚNICO futuro escrito do jogo — porque a função é pura, `epoch+1` é de graça e a tela DIZ qual é o próximo céu e em quantas horas chega (o MV-3 não sabe o próximo estado, o MV-2 não sabe o próximo evento, o MV-8 não sabe a próxima marcha). Primeiro sistema de mundo que alcança Mòyǔ (25,5 dias parado, fora de TIDE_CONTINENTS e METEOR_CONTINENTS) — porque não é do chão. SEM conjunção: flag única. ZERO migration. LAUNCH-SERVER-BOUND
    "masmorra_unica":      False,   # QoL-relatos (report [jogador]) — Uma masmorra de cada vez: com uma run aberta (current_floor > 0) em qualquer masmorra, ENTRAR noutra é recusado com nome+andar e o botão Retirar-se; varrer outra já concluída continua livre (varredura é revisitar, não expedição); varrer a masmorra onde você está é recusado. Honra a geografia do MV-1 (portal ancorado + viagem com cooldown de 4h). LAUNCH-SERVER-BOUND: ligar num mundo vivo apanha quem está a meio de uma run
    "superficie_desktop":  False,   # WEB-C 兩面 Duas Superfícies (mandato do owner 2026-08-26: "No PC fica como telefone, vamos criar versão pros 2") — o mesmo cliente ganha um layout PRÓPRIO de desktop: a navegação sai da barra inferior de telemóvel para um trilho lateral, e o conteúdo deixa de ser uma coluna de 480px centrada num ecrã de 1920. ⚠️ O corte NÃO é a largura da janela: exige superfície DECLARADA (`isWebSurface()` — dentro do Telegram é SEMPRE telemóvel, mesmo no Telegram Desktop) + largura >= 1024 + ponteiro fino (um tablet deitado passa os 1024px e continua a ser dedo). Logo, mesmo ON, ninguém que entre pelo Telegram sente NADA — o alcance é só `/app` numa aba de browser larga. Um só cliente, um só código: um fork seriam duas verdades a divergir a cada sprint (Lei §5). ZERO migration.
    "pele_quente":         False,   # WEB-D 皮 A Pele (mandato do owner 2026-08-26: "O game tá muito AI, temos que transformar em mãos humanas") — a paleta QUENTE de `GameDesign/LINGUAGEM_VISUAL_WEB_C.md §1` aplicada ao mini-app inteiro: o `--bg` deixa de ser #06080f (azul-escuro, a cor default de todo o dashboard do mundo) e passa a #0b0a0c (o preto quente que a porta `/login` já provou), o texto deixa de ser azul-esbranquiçado e passa a papel envelhecido, e o acento frio vira 朱砂 (o selo de cinábrio). ⚠️ FLAG PRÓPRIA, e a decisão é deliberada: a `ui_v2` é o *shell* do Pergaminho Vivo (5 hubs, Orbe, mapa) e é OFF eterno no `main`; a `superficie_desktop` é o layout largo. A pele é ORTOGONAL às duas — um mundo tem de poder ficar quente sem ganhar o redesign inteiro nem o trilho, e o servidor de launch nasce quente com a nav que tiver. Precedente do risco: o *Amazing Cultivation Simulator* — jogo chinês, de cultivo — foi lido como "RimWorld chinês" POR CAUSA DA UI, sem uma regra de jogo mudada; a superfície decide sozinha (Lei §2). O alcance é TODO o mini-app (chat intocado), e só existe porque a varredura da WEB-D converteu 1318 literais de cor em tokens: antes dela, trocar o `:root` mudava o fundo e mais NADA. Kill-switch = este toggle; re-render puro, ZERO migration, ZERO estado no jogador.
    "cena_cultivo":        False,   # WEB-E 坐 A Cena do Cultivo (mandato do owner 2026-08-26: "O game tá muito AI, temos que transformar em mãos humanas. Design é a chave pra fazer a galera ficar e jogar") — a tela mais aberta do jogo deixa de ser uma barra a encher e passa a ser alguém SENTADO. Licença de desenho medida em `GameDesign/LINGUAGEM_VISUAL_WEB_C.md` Achado 1: no Nivrael **esperar é o enredo**, não um defeito de ritmo — todo idle disfarça a espera com números a subir depressa; aqui dramatiza-se. O que estava mal, MEDIDO a 2026-09-02 no mini-app servido a sério (390×844, payload real): 2140px de scroll e um TOPO de quatro caixas com moldura idêntica — o orbe (decoração muda, zero informação), CULTIVO (barra), QI (barra) e MEDITAÇÃO (o estado). A resposta à pergunta 1 da régua ("isto podia ser o dashboard de qualquer SaaS?") era sim, e o estado mais volátil da tela — se você está sentado e por quanto tempo — era a TERCEIRA caixa, abaixo da dobra. A cena funde as quatro numa composição e **não remove nada** (Lei de Ferro (a)): os dois números com totais, o nome do reino, o chip de regeneração, o tipo, o multiplicador, o tempo, o interromper, os quatro assentos com cadeados e os CTAs Avançar/Renascer estão todos lá — muda a HIERARQUIA (a legenda é o ESTADO, não uma percentagem; as barras viram fios sem moldura; a acção fica onde o olho está). ⚠️ Diz a VERDADE do cume: em reino 10 camada 9 `check_breakthrough` fixa a base no limiar e devolve None — encher a barra ali não produz evento nenhum, e são **21 dos 37 activos-30d do `main` (57%)**; a cena diz isso em vez de deixar a barra fingir contagem decrescente (Lei §1). FLAG PRÓPRIA e ortogonal às outras três de superfície: `ui_v2` é o shell do Pergaminho Vivo (OFF eterno no `main`), `superficie_desktop` é o layout largo, `pele_quente` é a paleta — um mundo tem de poder ganhar a cena sem nada disso, e vice-versa. Na superfície larga o MESMO componente só troca de eixo (orbe ao lado da legenda), como o `shellStyle` já faz — não é um segundo cliente (Lei §5). Kill-switch = este toggle; re-render puro, ZERO migration, ZERO estado no jogador.
    "cultivador":          False,   # 坐 O CULTIVADOR (ordem do owner 2026-09-07, textual: "esse orb nao gostei nada, muito AI. etc. usamos uma imagem e criamos efeito nela tipo de um cultivador" · "as imagens relacionada aos reinos mudar. eu fiz ela de teste mesmo, porem deveriam ser realmente relacionada a nivrael" · "fora orb outra coisa nada de icone no game mais"). TRES coisas, uma flag. (1) O ORBE MORRE. A cena do Cultivo mostrava uma esfera de `radial-gradient` puro com um ✦ no centro — e o ✦ e' literalmente o glifo que virou o icone universal de "recurso de AI" desde 2023; fora da meditacao o centro era um EMOJI DO SISTEMA (🔮), que muda de aparelho para aparelho. Era a unica peca do jogo inteiramente feita de gradiente, num jogo que passou a WEB-D e a CARTA a tirar gradientes. No lugar dela entra um CULTIVADOR ILUSTRADO sentado, e o efeito (respiracao, aneis de qi, particulas a subir) passa a ser aplicado NELE. (2) OS ONZE REINOS VIRAM LUGARES. As 11 imagens antigas eram enfeite de landing reaproveitado (o proprio owner: "eu fiz ela de teste mesmo") e — medido a 2026-09-05 — tinham PESSOAS la dentro a fazer coisas diferentes: `realm-mortal` um viajante DE PE, `realm-core` a LEVITAR, `void-refinement` COMBATE, `true-immortal` a VOAR. Foi por isso que a cena nunca pode legendar a imagem: 5 das 11 desmentiriam a frase "voce esta sentado". As novas sao LUGARES VAZIOS, e e isso que deixa a camada de cima (o cultivador) ser o JOGADOR sem que a de baixo o contradiga. Duas camadas, duas responsabilidades: o reino diz ONDE, a figura diz QUEM, o efeito diz O QUE. (3) O GENERO (Mig 140) escolhe QUAL figura. ⚠️ NULL e estado legitimo (os 248 do beta) e tem figura propria: 背影, de costas, que e como a pintura chinesa classica retrata quem medita. ⚠️ NADA e gated por genero — em particular o casamento (`dao_partners`), que existe desde antes e continua gender-free por desenho. Ortogonal a `cartas` e a `cena_cultivo`; com esta chave OFF a cena rende exactamente o orbe de hoje.
    "cartas":              False,   # 牌 A CARTA (mandato do owner 2026-09-02/03: "Um jogo responsivo com design, items, personagens. Um jogo 2D nao. Porem algo melhor, cards etc. Design proprio" · "Quero a nivel webgame de 1.000.000 de euros investidos") — a carta-padrao do Nivrael. O jogo tem 413 usos de `<Card>` e TODOS desenham a mesma moldura de dashboard (gradiente + borda dourada de 1px + raio 10 + fio no topo + cantos ornamentados): a mesma caixa para o Qi, para uma pilula e para um aviso. A carta nova SUBTRAI (um contorno, um fio, zero gradientes, raio 4, canto inferior direito chanfrado) e poe tres marcas que carregam sentido: (1) 品 o LOMBO CONTADO — a raridade deixa de ser cor e passa a ser MEDIDA, uma faixa no bordo esquerdo cortada em tantos entalhes quantos a escala daquele conteudo tem, porque o jogo tem OITO vocabularios de raridade de comprimentos diferentes (tecnica 5 · besta 7 · artefacto 4 · pilula 5 · nucleo 4 · armadilha 6 · gacha 4 · lei do Dao 5) e um codigo de cores obrigaria o jogador a aprender oito escalas e a acreditar que o "Rare" de uma besta e o "perfected" de uma arte sao a mesma coisa (sao 3/7 e 3/5); (2) o VERSO HONESTO — aneis de tinta + o glifo da propria peca pintados SEMPRE por baixo, logo nunca ha buraco enquanto a arte carrega, se falhar, ou enquanto a peca nao tiver arte nenhuma (Lei §1; 307 pecas nao nascem no mesmo dia); (3) o SELO 朱砂 (SVG, nao caractere CJK) que marca o estado ACTIVO e so' esse — o jogo torna verdadeira sozinho a regra do doc ("uma vez por pagina, nunca duas"), porque equipam-se poucas artes e ha UM companheiro. Provada em TRES conteudos (tecnica · pilula · besta) nas DUAS superficies e nas DUAS peles. NAO converte as outras cartas: com a flag OFF cada um dos tres sitios rende exactamente o markup de hoje. Ortogonal a ui_v2, superficie_desktop, pele_quente e cena_cultivo. Re-render puro: ZERO migration, ZERO estado no jogador, kill-switch = este toggle.
    "iconografia":         False,   # 印 OS ICONES (ordem do owner 2026-09-07, textual: "fora orb outra coisa nada de icone no game mais. entende? icones genericos bom.") — a navegacao do jogo deixa de falar por emoji do sistema. MEDIDO a 2026-09-08 em `miniapp/components/{ui,tabs,app}.js`: **194 emoji distintos, 1638 ocorrencias**. O defeito NAO e' "sao feios" — e' que nao sao nossos e MUDAM DE FORMA: um emoji e' desenhado pela fonte do aparelho, portanto o pagode da aba Seita e' tres ilustracoes diferentes no iPhone, no Android e no Windows, com tres paletas que ninguem aqui escolheu. Depois de a WEB-D (pele quente), a CARTA e o CULTIVADOR construirem uma linguagem de tinta quente e cinabrio, a barra de baixo continuava a ser um conjunto de pictogramas coloridos da Apple — que e' exactamente o caso de aviso do `GameDesign/LINGUAGEM_VISUAL_WEB_C.md` (o *Amazing Cultivation Simulator*, jogo chines de cultivo, lido como "RimWorld chines" POR CAUSA DA UI). Entram **40 marcas SVG desenhadas** (`NIV_MARKS` em `components/ui.js`), todas na mesma grelha 24x24, traco 1.6, pontas redondas, `currentColor` — a cor vem SEMPRE do sitio onde a marca vive, como a `SealMark` do 朱砂 ja' fazia. NAO e' uma fonte CJK, e isso e' decisao: o mini-app nao carrega nenhuma, e a 19px o hanzi cai no fallback do sistema — seria trocar um conjunto de pictogramas alheios por outro. Alcance: os 25 destinos de `TAB_DEFS` (a barra de baixo E o trilho de desktop, que agrupa a MESMA lista), os 20 cartoes da Home, os 6 slots de equipamento e 21 sitios de estado (cadeado, incenso=espera, aviso, sim/nao, presente). ⚠️ E' tambem aqui que morre o **✦** que ainda marcava "equipado" na celula classica do artefacto — literalmente o glifo que o owner leu como "muito AI" no centro do orbe a 07/09. ⚠️ Acessibilidade: a barra de baixo so' escreve o rotulo do slot ACTIVO, logo com marcas os outros sete ficariam mudos para um leitor de ecra — por isso a flag ON traz `aria-label` no botao (Lei §1: uma marca sem nome e' pior do que um emoji). NAO toca nos emoji de CATALOGO (`beast.emoji`, `pill.emoji`, ...): esses sao CONTEUDO, e na carta sao o glifo do verso honesto de uma peca que ainda nao tem arte. Ortogonal a `ui_v2`, `superficie_desktop`, `pele_quente`, `cena_cultivo` e `cartas`. Re-render puro: ZERO migration, ZERO estado no jogador, kill-switch = este toggle; com ela OFF cada sitio desenha o emoji de hoje, byte a byte.
    "item_vivo":           False,   # 器 O ITEM VIVO (ordem do owner 2026-09-08, textual: "as espadas cards diferenciados nos Tieres. Heaven etc. tipo quanto mais alto o tier o cards mais bonito personalizado sei la como cores. Assim a espada nao e a mesma sempre, se eu abrir o item na mochila mostrar a foto dele etc.") — a peca deixa de ser intercambiavel. DUAS METADES, uma so ordem. (1) A FOTO NO DETALHE: a arte de 51/51 artefactos ja existia, ja estava no NIV_ART_INDEX e ja era servida NA CELULA desde 2026-09-06 — o modal de detalhe da mochila e que nunca a pedia: desenhava um icone de 30px numa caixa de 54. E literalmente o defeito que o owner fotografou a 07/09 no BeastDetailModal ("um emoji gigante no sitio onde a ilustracao devia estar"), corrigido nessa altura SO para as bestas com o PieceHero; o artefacto e a pilula ficaram para tras. Usa o MESMO PieceHero, por props (bleed/radius) — nunca um segundo componente, senao o verso honesto, o onError e o lazy passam a ter de ser corrigidos em dois sitios. Uma peca sem arte (ervas, minerios, materiais) continua a cair no VERSO honesto, que e o que a celula dela ja mostra. (2) OS TRES PATAMARES: a NivraelCard era a MESMA carta para uma peca de grau 0 e para uma de grau 8 — o lombo contava o posto, mas a carta nao recompensava. Passa a ter tres patamares: comum (a carta de 05/09, intocada) · notavel (o contorno ganha temperatura, o lombo acende) · celeste (esquadro nos cantos de cima, brilho para fora, e a arte sangra — o pe dissolve-se 16 pontos mais cedo). ⚠️ ISTO NAO REABRE A DECISAO DE 05/09 ("a raridade e MEDIDA, nao cor"): o jogo tem OITO vocabularios de raridade de comprimentos diferentes e um codigo de cores obrigaria o jogador a decorar oito escalas. O LOMBO DIZ QUANTO, O ORNAMENTO DIZ "ISTO E RARO" — o primeiro le-se, o segundo so se sente, e por isso nao precisa de legenda e nao colide. TRES patamares e nao nove (Lei §3): nove decisoes separadas nunca parecem um conjunto. O patamar sai de p = i/(n-1) do nivRank — DERIVADO DA ESCALA, nunca de uma lista de nomes (uma lista fixa envelhece em silencio); celeste p>=.90 (so o degrau do topo, em qualquer escala), notavel p>=.60. MEDIDO nos seeds: artefacto 63/25/12%, pilula 66/24/10%, besta 73/20/7% — uma piramide. ⚠️ MEDIDO EM PRODUCAO e escrito de proposito: o que os jogadores do main TEM nao e a piramide do catalogo (5.098 artefactos possuidos, 1.694 = 33% no grau 8), portanto numa mochila do main uma carta em cada tres seria celeste — e a inflacao conhecida da beta, o fix real e o rebalanceamento no servidor de launch, e esta flag e launch-server-bound. Ortogonal a ui_v2, superficie_desktop, pele_quente, cena_cultivo, cultivador e iconografia; a metade (2) so se ve com `cartas` tambem ON (a carta so existe la), a metade (1) e independente. Re-render puro: ZERO migration, ZERO estado no jogador, kill-switch = este toggle; com ela OFF cada sitio desenha o markup de hoje, byte a byte.
    "o_mapa":              False,   # 圖 O MAPA (ordem do owner 2026-09-08, textual: "tambem precisamos criar mapas entre outras coisas. To pensando em um HUB completo com imagem e a pessoa clica no templo ou o que seja. tipo um icone PNG porem feito por gemini no nosso estilo e abre o que quer. E nao esses menus louco onde tem que buscar de um lado ao outro. assim nos livramos do generico e o game fica mais interativo.") — a tela de hub deixa de ser uma LISTA e passa a ser um LUGAR pintado com portas tocaveis. NAO e "por uma imagem de fundo no hub": e trocar o MECANISMO de navegacao — hoje o jogador le uma lista e procura; com isto ele olha para um sitio e toca nele. O que estava la: a `HubCavernaScreen` desenhava CINCO elipses de `border-radius` organico, cada uma com um `radial-gradient` e um EMOJI de 28px ao centro (zero pixels de ilustracao — a "caverna" era CSS), e o toque abria um acordeao que revelava OUTRO botao ("Entrar"): DOIS taps para chegar onde um devia bastar. DESENHO (V5 de `GameDesign/LINGUAGEM_VISUAL_WEB_C.md`): CAMADAS SEPARADAS — o fundo e atmosfera (familia de arte `place`, que recusa por nome qualquer edificio) e CADA PORTA e a sua propria peca (familia `door`, sobre preto liso, com luz de recorte). Assim o alinhamento e do CSS e nao da pintura, uma porta nova nao obriga a regerar a cena, e cada porta ACENDE ou APAGA sem se repintar nada — que e o que torna possivel a regra da honestidade: o Salao por estabelecer aparece APAGADO e continua a ser uma porta (Lei §1 — o lugar vazio a espera, a mesma resposta que o 坐 O CULTIVADOR deu aos 11 reinos). ZERO ORFAOS: todo destino do grupo do hub tem porta (5 destinos, 5 portas na Caverna) e ha guarda que fica vermelha quando nascer um destino sem porta (MA-32b: entradas mudam, destinos NUNCA). Cada porta e um <button> com aria-label, alcancavel por Tab e com foco visivel — uma imagem com onClick nao e um botao. ⚠️ ESTA FLAG EXIGE A `ui_v2` LIGADA: as telas de hub so existem la (o gate pede as duas, de proposito). Ligar so esta nao muda NADA no ecra. ⚠️ 1 DE 4 CENAS NESTE LOTE — a Caverna (Lei §3: uma tela certa vale mais que quatro meio-feitas). O Eu, o Mundo e o Pergaminho continuam com a tela de hoje e sao PENDENTE DECLARADO, contado pela guarda (a do Mundo tem ainda por decidir como 9 destinos cabem numa pintura de 358px); o Combate nao leva cena por decisao — e hub de membro unico e o CombatTab ja E o landing. Re-render puro: ZERO migration, ZERO estado no jogador, kill-switch = este toggle; com ela OFF a tela de hub desenha o markup de hoje, byte a byte.
    "golpe_padrao":        False,   # GOLPE PADRAO (report do [jogador] 10/09 09:59, textual: "in Arena, give option to set 'default' technique to use (instead of default regular attack). This can give the option to advance paths without having to wait each time the 3 minutes counter (can do other things without worry)"; decisao do owner 12/09) - quando a ronda de 15s esgota, o motor preenche o lado que faltou com `technique_id: 0`, o GOLPE BASICO. Sempre, para toda a gente, nas DEZ familias de duelo. Quem fecha o mini-app luta a soco, e o tempo passa sem que nada no Caminho ande. Com esta flag o preenchimento passa a usar a tecnica que o jogador escolheu UMA vez (coluna `players.default_technique_id`, Migration 141, NULL = golpe basico = hoje). ISTO E O MOTOR E NAO A ARENA (Lei F-7): `check_and_handle_timeout` e UM chokepoint que serve as dez familias PvE mais o PvP, e tratar so a arena deixaria a masmorra e a caca com a regra antiga. AS TRAVAS: (1) uma arte do CAMINHO PROIBIDO nunca dispara sozinha - ela cobra karma e ANOS DE VIDA por uso, e um automatico nao pode cobrar um preco que o jogador nao escolheu naquele instante; ela nem aparece na lista de escolha, e a tela diz porque. (2) sem qi de combate, cai no basico - nunca recusar a ronda, que foi o bug dos 13 trancados. (3) a tecnica tem de estar EQUIPADA nesta luta. Toda recusa fica ESCRITA no `action_log` (`default_strike`, com o motivo): um automatico silencioso que nao faz o que lhe mandaram e a mesma ferida do "sua fila expirou" sem razao. Com a flag OFF o motor devolve o dict de hoje SEM ir a base de dados, e a coluna nunca e lida.
    "arena_encontro_rapido": False, # ENCONTRO RAPIDO (a pergunta anterior ao pedido do [jogador]) - MEDIDO a 2026-09-12 nas duas bases: 0 duelos PvP de arena em 30 dias no `main` (1 no s2, que expirou), ultimo duelo PvP de QUALQUER tipo a 2026-07-31, e 16.516 `arena_npc_fallback` all-time. A ARENA E 100% NPC ha seis semanas. Os 180s de fila nao sao uma procura: sao um ecra de espera por uma pessoa que nao esta la, ao fim do qual chega sempre o mesmo NPC - exactamente o que a Lei 1 proibe. Com esta flag a espera dura o que ha para esperar: com OUTRA alma na fila, os 180s de sempre (ha de facto alguem para encontrar); com a fila VAZIA, 30s. Trinta e nao zero DE PROPOSITO: a zero, duas pessoas que toquem "entrar" com dez segundos de diferenca nunca mais se encontrariam, e ter-se-ia matado o PvP para consertar a espera por ele. E a tela passa a DIZER a verdade enquanto espera (`pool_empty`): ninguem esta na fila agora, e o que vem a seguir e um adversario do mundo. ZERO migration. Com a flag OFF a fila dura os 180s de hoje e nem a contagem se corre.
    "cultivador_jogavel":  False,   # 坐 ONDA 1 — O CULTIVADOR JOGAVEL (desenho do Astra, MESA [011], 2026-09-15; ordem do owner "precisamos criar o mundo antes de eu divulgar a serio"). A onda 1 do recorte: **voltar ao cultivador e meditar** — um jogador abre o /app, recupera o contexto, entende o estado, inicia ou encerra uma meditacao permitida, ve a confirmacao, sai e volta. TRES metades. (S1) A CHEGADA: o erro deixa de ser uma faixa generica e passa a ser um cartao de recuperacao que diz O QUE falhou e oferece "Tentar novamente" — e uma sessao expirada (`unauthorized`/`session_expired`) ganha o seu proprio texto por plataforma (no browser a porta do /login com retorno; no Telegram reabrir pelo bot), porque hoje o `catch (e) { setError(e.message) }` mostrava "unauthorized" cru a quem so precisava de voltar a entrar. Mais as ANCORAS da aba (Cultivador · Pratica · Caminhos) sobre as tres seccoes que ja existem (`cult_sec_self`/`_practice`/`_paths`) — saltam, nunca recolhem. (S2) A SINTESE: a identidade (nome, reino traduzido, Reino N · Subcamada M, e o ESTADO dito em palavras) e os tres numeros — HP, Qi e Base de Cultivo — cada um com o atual e o maximo em LINHAS SEPARADAS e 16ch reservados, algarismos tabulares, sem reticencias e sem abreviatura obrigatoria. TRES verdades medidas em producao que a composicao TEM de aguentar: `current_hp` chega aos **12 digitos** (158.977.287.826), `qi` mede-se **2,08x acima** da capacidade num jogador real (a barra enche e a marca terminal + a linha "Acima da capacidade" dizem-no, em vez de fingir 100%), e a `cultivation_base` (10 digitos) ja passou o `cb_threshold` do apice (9 digitos). E `current_hp` NULL significa CHEIO, nunca zero (um COALESCE inventou uma vez "69% dos activos sem poder lutar"; re-medido, eram zero). A Base de Cultivo NAO e o Poder de Combate: a barra de avanco e `cultivation_base / cb_threshold` (`config.py:75` nao ve combate nenhum) e o `display_combat_power` vem null com `progressao_visivel` OFF — por isso o Poder tem linha PROPRIA, que simplesmente nao existe quando o mundo nao o calcula. (S3) A OPERACAO: as **7** modalidades em linhas, com duracao, custo (0 Qi dito por extenso) e o requisito de reino — contra as **4** que o cliente desenhava a mao. As tres que faltavam (`dao_basic` R5, `dao_deep` R6, `dao_transcend` R8) sao conteudo que o jogador destranca ao subir e que a superficie canonica nunca lhe mostrou. O catalogo passa a vir do servidor (`_meditation_catalog`, do `config.py` que o `api_meditate_start` ja valida) — UM dono, nunca dois. O vazio de S3 NAO e alcancavel e isso e MEDIDO, nao suposto: a `light` tem `min_realm` 0 e `qi_cost` 0, logo todo o jogador, em todo o reino, com zero qi, tem sempre uma linha aberta — nao ha tela de vazio para desenhar. Os 5 erros do `start` (`already_meditating` 409 · `invalid_meditation_type` 400 · `not_enough_qi` 403 · `realm_too_low` 403 · `player_not_found` 404) passam a ter cada um a sua frase DENTRO do cartao, ao lado da operacao, com a escolha e o catalogo preservados — nunca um toast que some antes de a pessoa reler. Ortogonal a `ui_v2`, `superficie_desktop`, `pele_quente`, `cena_cultivo`, `cultivador`, `cartas` e `iconografia`: com esta chave OFF a aba rende exactamente o markup de hoje, byte a byte. Re-render puro: ZERO migration, ZERO estado no jogador, kill-switch = este toggle.
    "a_obra":              False,   # 作 A OBRA (ordem do owner, 2026-09-16, textual: "amanha eu so ativo uma feature nova onde tudo que criaram juntos eu ativo e vejo como ta o game" · "so transforma o nivrael em um mundo novo — artes, tecnicas, combate, tudo jogavel, um MMORPG. meu mundo, nosso mundo. voces 2."). O INTERRUPTOR UNICO da noite de 15->16/09, em que o owner deu carta branca ao Claude e ao Astra e foi dormir. Nao e uma feature: e a CHAVE-MESTRA do que os dois construiram juntos nessa noite, para ele ligar UMA linha no painel de admin e ver o jogo inteiro mudar, em vez de ter de descobrir e ligar cinco chaves espalhadas. Hoje ela implica `cultivador_jogavel` (a tela do Cultivo com a pele da previa do Astra: tinta #0b0a0c, papel #ece5d8, ouro #c9903a, cinabrio #c8442f, Cormorant no nome a 44/60px, o fio de 2px no lugar da barra de 6, a Base de Cultivo como FECHO da progressao, S3 como seccao aberta com as 7 modalidades em lista continua, e o cartao de recuperacao que substituiu a palavra crua "unauthorized"). ⚠️ A implicacao vive num sitio SO — `ondaCultOn()` em `miniapp/components/ui.js` — e nao numa segunda copia da condicao espalhada pelos componentes: duas leituras da mesma decisao divergem sempre (Lei 0 §2), e foi exactamente assim que a lista de 4 modalidades sobreviveu meses ao lado de um servidor que aceita 7. ⚠️ E ela IMPLICA, nunca SUBSTITUI: quem tiver `cultivador_jogavel` ligada sozinha (o `s2` tem, desde 15/09) continua a ver a tela — esta chave acrescenta mundos, nao tira nenhum. ⚠️ O que ela NAO liga, e e decisao: a `iconografia` (ordem do owner de 08/09 — nao usar a flag dos icones como atalho para limpar emoji), a `pele_quente` (a [013] §C decidiu pele LOCAL: esta tela nao depende dela e nao escreve no `:root`), e a `cultivador` (a figura ilustrada; ortogonal por desenho — com ela OFF a cena rende o orbe, e isso e um estado legitimo). Ligar essas tres continua a ser decisao separada do owner, mundo a mundo. ⚠️ 2026-09-23 — ela passou a implicar tambem o **CORPO QUE ACENDE (2.1)** e o **COMBATE COMO CENA (2.2)**: o duelo deixa de ser uma lista de barras e vira uma cena de confronto (dois emblemas com nome e papel, Vida dos dois lados, Qi so' do jogador, a distancia entre eles a VAZIO, e ate' 4 artes ILUSTRADAS para escolher a rodada), a aba Combate ganha uma entrada com a arte da arte realmente equipada, e os segmentos Cacada e Arena ganham a tira 'Com o que voce vai lutar' (o `combatTechs` estava calculado e nunca desenhado desde a v15.1.4: pagava-se 10 a 100 de Qi sem ver com o que se ia lutar). ⚠️ NAO confundir com `cartas`: a arte da CARTA continua a depender dessa chave; o que entra aqui e' a arte da CENA. ⚠️ E uma coisa do 2.2 NAO esta' atras desta chave, de proposito: o nome da tecnica dentro do duelo passa a sair na lingua do jogador (o log continua a gravar cru; interpreta-se na LEITURA). Nao e' pele — e' a correccao de uma contradicao: a aba Tecnicas dizia 'Passo do Trovao' e o duelo dizia 'Thunder Step' ao mesmo jogador. Ortogonal a tudo o resto. Re-render puro: ZERO migration, ZERO estado no jogador, kill-switch = este toggle; com ela OFF cada sitio desenha o markup de hoje, byte a byte.
}


# ── FF-4 realm shell (per-world UI-shell selector) ────────────────────────────
# Each world can render a DISTINCT UI shell, chosen by its `realm`. The
# Surface Manifest carries `realm` so the mini-app switches shell WITHOUT a new
# app. Stored in balance_config["realm"] (same JSONB sub-block as features →
# ZERO migration). Every world is "mortal" today; `main` ignores its config.
DEFAULT_WORLD_REALM = "mortal"


def get_world_features(key: str | None = None) -> dict:
    """Return the active (or given) world's feature flags, merged over
    DEFAULT_WORLD_FEATURES. Sync + no I/O (reads the in-memory registry keyed by
    the current_world ContextVar) so it is safe on any hot path. EXACT mirror of
    get_world_balance.

    `main` ALWAYS returns the defaults — its stored features are ignored so the
    live players are never affected. Unknown world → defaults (degrade to main)."""
    if key is None:
        key = _resolve_world_key()
    if key == MAIN_WORLD_KEY:
        return dict(DEFAULT_WORLD_FEATURES)
    _ensure_main_registered()
    row = _world_registry.get(key)
    if row is None:
        return dict(DEFAULT_WORLD_FEATURES)
    cfg = _coerce_balance_config(row.get("balance_config"))
    raw = cfg.get("features")
    merged = dict(DEFAULT_WORLD_FEATURES)
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in merged:
                merged[k] = bool(v)  # only known keys, coerced to bool
    return merged


def feature_enabled_for_world(feature: str, world_key: str | None = None) -> bool:
    """Stable read API for gating an entry-point: True iff `feature` is ON in the
    given (or active) world. Fail-safe → False on ANY error (unknown feature,
    broken registry, anything) so a bug can never silently expose a gated feature.
    Use this — never poke get_world_features().get() directly at call-sites."""
    try:
        return bool(get_world_features(world_key).get(feature, False))
    except Exception:
        return False


def set_world_features(key: str, features: dict) -> None:
    """Update a world's in-memory feature flags so a live admin toggle takes
    effect WITHOUT a restart. Read-modify-write on balance_config — merges only
    KNOWN flags and never touches the balance knobs, so set_world_balance and
    set_world_features never stomp each other. No-op for main / unknown worlds.
    The control DB is the persistent source of truth; this keeps the registry
    hot-copy in sync. Mirrors set_world_balance."""
    if not key or key == MAIN_WORLD_KEY:
        return
    _ensure_main_registered()
    row = _world_registry.get(key)
    if row is None:
        return
    cfg = _coerce_balance_config(row.get("balance_config"))
    existing = cfg.get("features")
    cur = dict(existing) if isinstance(existing, dict) else {}
    for k, v in (features or {}).items():
        if k in DEFAULT_WORLD_FEATURES:
            cur[k] = bool(v)
    cfg["features"] = cur
    row["balance_config"] = cfg


def get_world_realm(key: str | None = None) -> str:
    """Return the active (or given) world's realm-shell id (FF-4) — the bundle the
    mini-app uses to render a per-realm UI. Sync + O(1) (in-memory registry, no
    I/O) so it is safe on the /player payload path. Mirrors get_world_features.

    `main` ALWAYS returns the default — its stored config is ignored so the live
    players are never affected. Fail-safe → "mortal" on ANY error (broken
    registry, non-str value, anything) so a bug can never strand the UI shell."""
    try:
        if key is None:
            key = _resolve_world_key()
        if key == MAIN_WORLD_KEY:
            return DEFAULT_WORLD_REALM
        _ensure_main_registered()
        row = _world_registry.get(key)
        if row is None:
            return DEFAULT_WORLD_REALM
        cfg = _coerce_balance_config(row.get("balance_config"))
        realm = cfg.get("realm")
        return realm if isinstance(realm, str) and realm else DEFAULT_WORLD_REALM
    except Exception:
        return DEFAULT_WORLD_REALM


def register_world(row: dict) -> None:
    """Merge a single world row (from the control DB) into the in-memory registry
    so a world PROVISIONED at runtime becomes routable without a restart. `main`
    is never overridden (its binding always comes from config). Used by the admin
    'provision world' flow after it writes the control-DB `servers` row."""
    key = (row or {}).get("key")
    if not key or key == MAIN_WORLD_KEY:
        return
    row = dict(row)
    row["balance_config"] = _coerce_balance_config(row.get("balance_config"))
    _world_registry[key] = row


def deregister_world(key: str) -> None:
    """Remove a secondary world from the in-memory registry so the scheduler stops
    ticking it immediately (never ``main``). Used when a provision FAILS so a
    half-built world leaves NO tickable trace for the rest of this process."""
    if not key or key == MAIN_WORLD_KEY:
        return
    _world_registry.pop(key, None)


def set_world_status(key: str, status: str) -> bool:
    """Sync a world's in-memory ``status`` so a live admin status change takes
    effect on scheduler ticking WITHOUT a restart: only ``'active'`` worlds are
    ticked (see ``iter_active_world_keys``).

    Returns True if an in-memory registry row was actually updated (the world is
    loaded → pausing/resuming takes effect live). Returns False for ``main`` /
    a world NOT currently loaded — re-activating a world that was never loaded
    (e.g. left 'maintenance' at startup) still needs a restart/provision to build
    its engine, so the caller can tell the admin the change is control-DB-only."""
    if not key or key == MAIN_WORLD_KEY:
        return False
    row = _world_registry.get(key)
    if row is not None:
        row["status"] = status
        return True
    return False


def set_world_name(key: str, name: str) -> None:
    """Sync a world's in-memory display name (admin rename) so the registry matches
    the control DB without a restart. Allowed for `main` too — it's display-only
    (the owner can rename the current world)."""
    _ensure_main_registered()
    row = _world_registry.get(key)
    if row is not None and name:
        row["name"] = name


def set_world_flags(key: str, *, monetization_enabled=None, is_public=None,
                    requires_code=None) -> None:
    """Sync a SECONDARY world's in-memory flags (admin toggle) so they take effect
    without a restart. NEVER `main` (its flags are locked invariants — always
    monetized/public/no-code so the 57 real payers are never affected)."""
    if not key or key == MAIN_WORLD_KEY:
        return
    row = _world_registry.get(key)
    if row is None:
        return
    if monetization_enabled is not None:
        row["monetization_enabled"] = bool(monetization_enabled)
    if is_public is not None:
        row["is_public"] = bool(is_public)
    if requires_code is not None:
        row["requires_code"] = bool(requires_code)


async def demote_world(key: str) -> None:
    """Take a broken secondary world OUT of service (never ``main``):

      • drop it from the in-memory registry → the scheduler stops ticking it
        (``iter_active_world_keys`` no longer returns it), AND
      • revert its control-DB row to ``'maintenance'`` → ``resolve_active_world``
        degrades its players to ``main`` (no more 500s on a schemaless world), and
        the next restart won't reload it as ``'active'``.

    Used when a world fails to initialize / verify (at startup OR during a
    provision). Best-effort: a control-DB error is logged, never raised (Lei §1)."""
    if not key or key == MAIN_WORLD_KEY:
        return
    deregister_world(key)
    try:
        from sqlalchemy import text
        from database.control_db import get_control_session_factory
        sm = get_control_session_factory()
        if sm is None:
            return
        async with sm() as session:
            await session.execute(
                text("UPDATE servers SET status='maintenance' WHERE key=:k AND key<>'main'"),
                {"k": key})
            await session.commit()
    except Exception:
        logger.warning("demote_world: could not revert control status for %r", key, exc_info=True)


def monetization_enabled_for(key: str | None = None) -> bool:
    """Whether the given (or current) world allows real-money / premium flows.
    開 Edição comunitária: o `main` (e um mundo que não se resolve, que se lê
    como o `main`) segue a flag `NIVRAEL_MONETIZATION` — desligada por defeito.
    Um mundo secundário registado devolve a sua própria flag (nasce False)."""
    if key is None:
        key = _resolve_world_key()
    if key == MAIN_WORLD_KEY:
        return MONETIZATION_ENABLED
    _ensure_main_registered()
    row = _world_registry.get(key)
    if row is None:
        return MONETIZATION_ENABLED  # unknown -> degrade to main semantics (a flag)
    return bool(row.get("monetization_enabled", False))


async def load_world_registry() -> None:
    """Merge secondary game worlds from the control DB into the registry.
    Degrades to main-only on ANY control-plane error (Lei §1). `main` is always
    bound from config and is NEVER overridden by the control row."""
    _ensure_main_registered()
    try:
        from database.control_db import fetch_world_registry
        rows = await fetch_world_registry()
    except Exception:
        logger.warning("control DB registry load failed — running main-only", exc_info=True)
        return
    for row in rows:
        key = row.get("key")
        if not key or key == MAIN_WORLD_KEY:
            continue  # main's engine binding always comes from config, not control
        # asyncpg can hand JSONB back as a str on a raw text() query — normalize
        # once here so the registry (and get_world_balance) always see a dict.
        row["balance_config"] = _coerce_balance_config(row.get("balance_config"))
        _world_registry[key] = row
    if rows:
        logger.info(
            "🌐 World registry loaded: %d world(s) [%s]",
            len(_world_registry), ", ".join(sorted(_world_registry)),
        )


async def _execute_with_lock_retry(conn, cmd_text, max_attempts: int = 6) -> None:
    """Run a single migration statement, retrying on lock-timeout/deadlock.

    Rationale (2026-05-15 incident): rolling deploys leave the *old* container
    alive and ticking on `players` while the *new* container tries to apply
    schema migrations. `ALTER TABLE` needs an AccessExclusiveLock, which
    Postgres' deadlock detector then aborts in milliseconds, killing the new
    container. By scoping a short `lock_timeout` per statement and retrying
    with exponential backoff, the new container waits for the old container's
    queries to release their locks instead of hard-crashing the deploy.

    Total worst-case wait ≈ 1+2+4+8+16+32 = 63s, well under Coolify's 5min
    healthcheck window.
    """
    import asyncio
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError, OperationalError

    for attempt in range(1, max_attempts + 1):
        try:
            # Short per-statement lock_timeout so deadlock detector fires fast
            # instead of waiting forever on the live container's row locks.
            # SET LOCAL only applies inside an explicit transaction; conn here
            # is the migration's own transaction (engine.begin in init_db).
            await conn.execute(text("SET LOCAL lock_timeout = '4s'"))
            await conn.execute(text(cmd_text))
            return
        except (DBAPIError, OperationalError) as e:
            msg = str(e).lower()
            retriable = (
                "deadlock detected" in msg
                or "lock_timeout" in msg
                or "canceling statement due to lock timeout" in msg
                or "could not obtain lock" in msg
            )
            if not retriable or attempt == max_attempts:
                raise
            wait = 2 ** (attempt - 1)  # 1, 2, 4, 8, 16, 32 seconds
            logger.warning(
                "migration statement hit lock contention (attempt %d/%d): %s — retrying in %ds",
                attempt, max_attempts, e.__class__.__name__, wait,
            )
            await asyncio.sleep(wait)


def _split_sql_statements(sql_text: str) -> list[str]:
    """Split a migration file into individual statements for the runner.

    Replaces the old ``_strip_sql_comments`` + naive ``.split(";")`` pair with a
    single pass that is aware of:
      • ``--`` line comments (full-line AND inline) — stripped, EXCEPT inside a
        string/dollar-quote literal. (A stray ``;`` inside an inline comment —
        e.g. migration 108's ``-- set on loss; gates the retry`` — once split a
        statement mid-way and crash-looped prod; stripping first fixes that.)
      • single-quoted string literals ``'...'`` (with ``''`` escaping) — a ``;``
        or ``--`` inside one is neither a delimiter nor a comment.
      • dollar-quoted blocks ``$$ … $$`` / ``$tag$ … $tag$`` — everything between
        matching tags (INCLUDING ``;``) is one opaque chunk. This is what lets a
        migration use a ``DO $$ BEGIN … ; … END $$;`` block (e.g. the guarded
        column RENAME in 044, needed so a FRESH world DB provisions cleanly)
        WITHOUT the naive ``;`` split shredding the block mid-statement.

    Quote/dollar-quote tracking spans lines (the old line-by-line stripper reset
    its quote state every newline). Backwards compatible: the 120+ existing
    migrations use no ``$$``, so their statement list is byte-identical to the
    previous strip-then-split. Returns non-empty, stripped statements in order.
    """
    def _match_dollar_tag(s: str, pos: int):
        # A Postgres dollar-quote tag is `$` + optional [A-Za-z_][A-Za-z0-9_]* + `$`.
        if s[pos] != "$":
            return None
        j = pos + 1
        while j < len(s) and (s[j].isalnum() or s[j] == "_"):
            j += 1
        if j < len(s) and s[j] == "$":
            return s[pos:j + 1]
        return None

    statements: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql_text)
    in_squote = False
    dollar_tag = None  # the active "$$"/"$tag$" while inside a dollar-quoted block

    while i < n:
        ch = sql_text[i]
        if dollar_tag is not None:
            # Inside a dollar-quoted block — copy verbatim until the closing tag.
            if ch == "$" and sql_text.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
            else:
                buf.append(ch)
                i += 1
            continue
        if in_squote:
            buf.append(ch)
            if ch == "'":
                if i + 1 < n and sql_text[i + 1] == "'":  # `''` escaped quote
                    buf.append("'")
                    i += 2
                    continue
                in_squote = False
            i += 1
            continue
        # Not inside any literal.
        if ch == "-" and i + 1 < n and sql_text[i + 1] == "-":
            j = i + 2  # inline/full-line comment → skip to end of line
            while j < n and sql_text[j] != "\n":
                j += 1
            i = j
            continue
        if ch == "'":
            in_squote = True
            buf.append(ch)
            i += 1
            continue
        tag = _match_dollar_tag(sql_text, i)
        if tag is not None:
            dollar_tag = tag
            buf.append(tag)
            i += len(tag)
            continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


async def run_migrations(conn):
    import os
    from sqlalchemy import text
    migrations_dir = os.path.join(os.path.dirname(__file__), "..", "migrations")
    if not os.path.exists(migrations_dir):
        return

    # Create a table to track applied migrations
    await conn.execute(text("CREATE TABLE IF NOT EXISTS applied_migrations (filename TEXT PRIMARY KEY);"))

    files = sorted([f for f in os.listdir(migrations_dir) if f.endswith(".sql")])
    for filename in files:
        result = await conn.execute(text("SELECT 1 FROM applied_migrations WHERE filename = :f"), {"f": filename})
        if not result.scalar():
            with open(os.path.join(migrations_dir, filename), "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():
                    # Split into individual statements via a comment-,
                    # string-, and dollar-quote-aware tokenizer. The naive
                    # ";" split used to (a) truncate a statement on a ";"
                    # inside an inline comment (crash-looped prod on migration
                    # 108) and (b) shred a `DO $$ … ; … END $$;` block. The
                    # tokenizer fixes both; already-applied migrations are
                    # skipped above, so this only affects new migrations.
                    commands = _split_sql_statements(content)
                    for cmd in commands:
                        await _execute_with_lock_retry(conn, cmd)

            await conn.execute(text("INSERT INTO applied_migrations (filename) VALUES (:f)"), {"f": filename})
            print(f"✅ Applied migration: {filename}")

async def init_db():
    """Bring the control plane + every registered GAME world online.

    Fase 1: only `main` is registered, so this is equivalent to the old
    single-world init. `main` initializes UNGUARDED (it MUST succeed). Any
    secondary world is isolated in try/except, so a broken/fresh world can never
    crash the bot or block `main` (Lei §1/§5)."""
    # Control plane first (idempotent; a total no-op without CONTROL_DATABASE_URL).
    try:
        from database.control_db import bootstrap_control_db
        await bootstrap_control_db()
    except Exception:
        logger.warning("control DB bootstrap failed — running main-only", exc_info=True)
    # A senha dos mundos sai da tabela (fica só no env) — passo próprio: falhar
    # aqui deixa as linhas como estavam, e elas continuam a ligar.
    try:
        from database.control_db import strip_registry_credentials
        await strip_registry_credentials()
    except Exception:
        logger.warning("registry credential cleanup failed — rows keep their logins", exc_info=True)
    await load_world_registry()

    # main runs exactly as before.
    await init_world_db(MAIN_WORLD_KEY)

    # Secondary worlds. Isolated failures never reach main. Bind the contextvar
    # to each world so any stray get_session_factory() inside a seed/bootstrap
    # writes to THAT world, not main (defensive — today's seeds use the passed
    # session, but this guarantees isolation for any future seed).
    #
    # 2026-06-24 incident: a secondary world can be 'active' in the control DB yet
    # have NO schema in its game DB (its `players` table is missing — a failed/
    # partial provision, a swapped DB, a transient outage at this boot). Left
    # 'active', resolve_active_world routes real players into it (→ live 500s) and
    # the scheduler ticks it (→ a flood). So: after init, VERIFY the cornerstone
    # table exists; if init OR the verify fails, DEMOTE the world to 'maintenance'
    # (degrades its players to main + stops it being ticked). `main` is untouched.
    from sqlalchemy import text as _sql_text
    for key in sorted(_world_registry):
        if key == MAIN_WORLD_KEY:
            continue
        try:
            with use_world(key):
                await init_world_db(key)
                async with get_session_factory()() as _vs:
                    await _vs.execute(_sql_text("SELECT 1 FROM players LIMIT 1"))
        except Exception:
            logger.exception(
                "secondary world %r failed init/verify — DEMOTING to 'maintenance' "
                "(its players degrade to main; it is not ticked); main unaffected", key,
            )
            await demote_world(key)

    # ── WEB-B Fase 1 — ligar cada personagem à sua identidade `telegram`. ─────
    # DEPOIS dos mundos, porque lê a tabela `players` de cada um. Idempotente
    # (ON CONFLICT DO NOTHING): corre em todo o boot e não duplica. Best-effort
    # por dentro — nunca impede o arranque (Lei §1). Sem isto, os 248 que já
    # jogam teriam de "criar conta" para entrar pela web; com isto, entram sem
    # fazer nada. (O login liga a identidade na mesma, caso isto falhe.)
    try:
        from database.control_db import backfill_telegram_identities
        await backfill_telegram_identities()
    except Exception:
        logger.warning("backfill de auth_identities falhou — a web continua a "
                       "ligar a identidade no primeiro login", exc_info=True)


async def init_world_db(key: str):
    """Run create_all + migrations + ALL seeds against a SINGLE world's DB."""
    eng, sm = _ensure_world(key)
    async with eng.begin() as conn:
        from database.models import (  # noqa: F401
            Player, HerbCatalog, PillCatalog, CauldronCatalog,
            PlayerInventory, PlayerCauldron, PlayerBuff,
            ArtifactCatalog, PlayerArtifact, OreCatalog, PlayerOre,
            Tribulation, MarketplaceListing, P2PTrade, Transaction,
            Sect, SectMember, SectBuildingLog, SectTerritory, SectWarLog, SectWarState,
            CombatLog, ArenaRanking, TechniqueCatalog, PlayerTechnique, PlayerNPCCooldown,
            QuestCatalog, PlayerQuest, LoginStreak,
            BeastCatalog, PlayerBeast, ExpeditionCatalog,
            DaoLawCatalog, PlayerDaoFragment,
            WorldBoss, WorldBossDamage,
            GachaBanner, GachaHistory, GachaPity,
            DungeonCatalog, PlayerDungeon,
            DungeonQuestCatalog, PlayerDungeonQuest,
            AchievementCatalog, PlayerAchievement,
            CelestialEvent,
            DaoPartner, DaoPartnerProposal,
            PlayerMedicineResistance,
            PlayerAlchemySkill,
            PlayerForgeSkill, ForgeRecipe, PlayerForgeMastery,
            BattlePassMission, PlayerBPMission,
            BattlePass, PlayerVIP, PrestigeLog, Purchase,
            FactionCatalog, PlayerFaction, FactionQuestCatalog,
            PlayerFactionQuest, FactionShopItem,
            DaoCategory, DaoPath, DaoPathLaw, PlayerDaoDiscovery,
            GlobalAnnouncement,
            KarmaLog, WorldSect, WorldSectRecruiterPending,
            NpcCultivator, HeavensWhisperLog,
            Bounty,
            WorldChronicle,
            PlayerExploration,
            FormationCatalog, PlayerFormation, PlayerCavern,
            StoryletCatalog, PlayerStorylet,
            PlayerRegionRep,
        )
        await conn.run_sync(Base.metadata.create_all)

    # ── Migrations in a SEPARATE, post-create_all transaction ────────────────
    # create_all (the base schema) is now COMMITTED before migrations run. They
    # used to share ONE transaction; on a FRESH secondary world, if ANY of the
    # 120+ historical migrations failed (several assume an incrementally-evolved
    # `main` DB, not a from-scratch create_all schema — see the migration-044
    # comment in _split_sql_statements), the WHOLE transaction rolled back,
    # DELETING the just-created base tables and leaving the world's DB EMPTY
    # ("relation \"players\" does not exist" on every request; 2026-06-24
    # incident). Now the complete current schema always survives. A migration
    # failure stays FATAL for `main` (its schema evolves via migrations — fail
    # loud, exactly as before) but is BEST-EFFORT for a secondary world:
    # create_all already built the full current schema, so the world is usable;
    # a failing historical migration is logged and skipped, not catastrophic.
    from sqlalchemy import text
    try:
        async with eng.begin() as conn:
            await run_migrations(conn)
    except Exception:
        if key == MAIN_WORLD_KEY:
            raise
        logger.exception(
            "init_world_db: migrations failed for secondary world %r — continuing "
            "on the create_all base schema (the world is usable)", key,
        )

    # Kill any leftover idle-in-transaction sessions from previous bot runs
    # (best-effort, its own short transaction). Scoped to THIS world's database
    # (datname = current_database()) so a shared Postgres instance hosting several
    # worlds never has one world's init terminate another world's live sessions.
    try:
        async with eng.begin() as conn:
            result = await conn.execute(text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE state = 'idle in transaction' "
                "AND datname = current_database() "
                "AND pid != pg_backend_pid()"
            ))
            killed = result.rowcount
            if killed:
                print(f"🧹 Killed {killed} leftover idle-in-transaction session(s)")
    except Exception:
        pass  # Not critical — some hosted DBs restrict pg_terminate_backend

    async with sm() as session:
        from database.seeds.alchemy_seeds import run_alchemy_seeds
        from database.seeds.artifacts_seeds import run_artifact_seeds
        from database.seeds.combat_seeds import run_combat_seeds
        from database.seeds.quests_seeds import run_quests_seeds
        from database.seeds.beasts_seeds import run_beasts_seeds
        from database.seeds.dao_seeds import run_dao_seeds
        from database.seeds.boss_seeds import run_boss_seeds
        from database.seeds.gacha_seeds import run_gacha_seeds
        from database.seeds.dungeon_seeds import run_dungeon_seeds
        from database.seeds.achievement_seeds import run_achievement_seeds
        from database.seeds.events_seeds import run_events_seeds
        from database.seeds.partner_seeds import run_partner_seeds
        from database.seeds.battle_pass_seeds import run_battle_pass_seeds
        from database.seeds.forge_seeds import run_forge_seeds
        from database.seeds.faction_seeds import run_faction_seeds
        from database.seeds.dungeon_quest_seeds import run_dungeon_quest_seeds
        from database.seeds.dao_3000_seeds import run_dao_3000_seeds
        from database.seeds.heavenly_laws_seeds import run_heavenly_seeds
        from database.seeds.world_sects_seeds import run_world_sects_seed
        from database.seeds.formation_seeds import run_formation_seeds
        from database.seeds.storylet_seeds import run_storylet_seeds
        await run_alchemy_seeds(session)
        await run_artifact_seeds(session)
        # run_dao_seeds populates `dao_laws_catalog` — the FK target of
        # `techniques_catalog.required_dao_law_id`. It MUST run BEFORE
        # run_combat_seeds, or a FRESH world (new server / wipe / launch / CI)
        # hits a ForeignKeyViolation seeding techniques (2026-06-24 incident: this
        # exact FK error DEMOTED a freshly-provisioned world). On `main` it is
        # idempotent (skips existing rows), so moving it up is a no-op there.
        await run_dao_seeds(session)
        await run_combat_seeds(session)
        # world_sects are the FK targets of QuestCatalog.sect_id (the sect-tagged
        # quest arcs, Pedra 2 wave 2), so the 9 houses MUST be seeded BEFORE
        # run_quests_seeds — otherwise a FRESH DB (wipe / launch / CI) hits a FK
        # violation inserting a sect_id="azure_cloud" quest row. Prod is unaffected
        # (the houses were already seeded on a prior boot); this only matters when
        # both run for the first time in the same boot. Idempotent + no cross-dep.
        await run_world_sects_seed(session)  # v16.4 — 9 NPC sects (FK targets)
        await run_quests_seeds(session)
        await run_beasts_seeds(session)
        await run_boss_seeds(session)
        await run_gacha_seeds(session)
        await run_dungeon_seeds(session)
        await run_achievement_seeds(session)
        await run_events_seeds(session)
        await run_partner_seeds(session)
        await run_battle_pass_seeds(session)
        await run_forge_seeds(session)
        await run_faction_seeds(session)
        await run_dungeon_quest_seeds(session)
        await run_dao_3000_seeds(session)
        await run_heavenly_seeds(session)
        await run_formation_seeds(session)  # Onda 5 Fase 2 — Matrizes/Formações 阵法
        await run_storylet_seeds(session)  # MV-5 — storylets/QBN (catálogo, sem FK externa)
        # Onda 3 — fill the world with a starting NPC-cultivator population so it
        # is never born empty (idempotent: only tops each continent to target).
        try:
            from core.npc_cultivator_engine import run_npc_cultivators_bootstrap
            await run_npc_cultivators_bootstrap(session)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("npc_cultivators bootstrap failed at startup")
        # Onda 4a — seed the Bounty Board once at startup so the plaza is never
        # born empty (idempotent: only tops each continent to target; the
        # bounty_refresh scheduler job keeps it fresh thereafter). Runs AFTER
        # the NPC bootstrap so dark-karma targets already exist.
        try:
            from core.bounty_engine import refresh_bounties
            await refresh_bounties(session)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("bounty board refresh failed at startup")
        # Track A item 5 — derive the elemental ROOT COMPOSITION for any player
        # still NULL (the 57 beta players + any created before this column).
        # Idempotent: deterministic per telegram_id + an IS NULL guard, so re-runs
        # touch only un-derived rows. Disclosure-only data; zero balance impact.
        try:
            from core.root_engine import backfill_root_elements
            n_roots = await backfill_root_elements(session)
            if n_roots:
                print(f"🌱 Derived root_elements for {n_roots} player(s)")
        except Exception:
            import logging
            logging.getLogger(__name__).exception("root_elements backfill failed at startup")
        print("✅ All seeds applied")


def get_session_factory():
    """Return the sessionmaker for the world bound to the current task.

    Reads the `current_world` ContextVar; with none set, resolves to `main`
    (identical behavior to the old singleton). The ~628 call-sites that do
    `async with get_session_factory()() as session:` need ZERO changes — the
    world routing happens entirely inside this function."""
    _, sm = _ensure_world(_resolve_world_key())
    return sm


def _is_transient_db_error(exc: Exception) -> bool:
    """Return True for transient connection/pool errors that are safe to retry."""
    from sqlalchemy.exc import (
        OperationalError,
        TimeoutError as SATimeoutError,
        InterfaceError,
    )
    return isinstance(exc, (OperationalError, SATimeoutError, InterfaceError, OSError, ConnectionError))


@asynccontextmanager
async def get_session_with_retry(retries: int = 2, delay: float = 1.0):
    """Acquire a DB session, retrying on transient connection/pool errors.

    Retries only happen during connection acquisition (before the session is
    yielded). Errors raised inside the caller's ``async with`` block propagate
    immediately — they are NOT retried.
    """
    # Resolve the world-bound sessionmaker AT CALL TIME (not the module-global
    # `async_session`) so the 14 handlers/dungeons.py sites route per-world like
    # every other call-site. This is the multi-world breaker the audit flagged.
    factory = get_session_factory()
    for attempt in range(retries + 1):
        yielded = False
        try:
            async with factory() as session:
                # Eagerly validate the connection so pool/network errors
                # surface here instead of on the first query.
                await session.connection()
                yielded = True
                yield session
                return
        except Exception as e:
            if not yielded and attempt < retries and _is_transient_db_error(e):
                wait = delay * (attempt + 1)
                logger.warning(
                    "DB connection attempt %d/%d failed (%s), retrying in %.1fs…",
                    attempt + 1, retries + 1, e, wait,
                )
                await asyncio.sleep(wait)
                continue
            # If the session was already yielded and the error is a transient
            # connection issue during cleanup (rollback on dead connection),
            # suppress it — the caller's work was already done.
            if yielded and _is_transient_db_error(e):
                logger.warning("DB connection lost during session cleanup: %s", e)
                return
            raise
