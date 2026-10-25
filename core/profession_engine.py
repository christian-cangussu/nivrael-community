"""MV-7 Mundo Vivo v2 — Profissões Wuxia (o MOTOR da economia regional).

O MV-1 deu geografia, o MV-2 movimento, o MV-3 consequência, o MV-4
profundidade, o MV-5 vida às quests, o MV-6 memória pessoal. O MV-7 dá
OFÍCIO — identidade (Lei §3: "quem carrega 8 técnicas tem identidade"):

* **UMA profissão por jogador** (players.profession, Mig 135). Onda 1 = 3
  PROFUNDAS que reusam engines vivos (zero sistema paralelo):
    🧪 alquimista — XP por craft_pill  · morde: +2%/tier no sucesso do craft
       (cap +10%, DENTRO de calculate_success_chance — display = roll) +
       chance de pílula extra em pills T1-T2 · nativo: yanshan (ervas)
    ⚒️ ferreiro   — XP por forge_artifact · morde: custo de minério −5..−15%
       (na MESMA função que debita — lição MV-6) + chance de refino grátis
       (a duplicata sobrevive à tentativa; proc ANTES do charm) · fenghuo
    🩺 medico     — XP por use_pill · morde: pílulas de HP +10..+25% em si e
       NO ALVO (heal_ally = 1ª mecânica social de profissão) + circular de
       meridianos −10% tempo (MV-4 conversa) · linghe (nascente)
  As outras 6 (talismancista/domador/cozinheiro/cartografo/mercador/
  mestre_formacoes) = teaser honesto ("os salões ainda fecham suas portas").

* **XP regional** — praticar no continente NATIVO = ×1.5 (o porquê de viajar,
  MV-1); rep ≥ +25 no nativo soma +0.5 (MV-6 conversa; clamp no total 2.0);
  o knob per-world `profession_speed` MULTIPLICA tudo (o consumidor único do
  knob que espera desde o multi-server). Gancho de XP DENTRO de track_quest
  (chokepoint — lição MV-5) com prefiltro estático próprio.

* **Relatório do Mercado Imperial 📜** (lição EVE MER / Gini 0.913) — gerado
  no World Pulse (passo 5, gated), snapshot em region_states.payload
  ["market_report"] (tabela viva do MV-3 — SEM migration extra; o writer faz
  MERGE, nunca substitui o payload). Números honestos: preço BASE (o mult
  regional não persiste) e pedras QUEIMADAS (não existe venda-a-NPC hoje —
  o "faucet" do prompt não existe no engine; rótulo diz sink, Lei §1).

Tudo atrás da flag per-world ``profissoes`` (OFF por defeito → main
byte-idêntico; ver DEFAULT_WORLD_FEATURES em database/db.py).

Regras (padrão reputation_engine — tudo fail-safe, nada aqui quebra nada):
- Flag OFF → ``profissoes_on()`` False → TODA função pública é no-op sem UMA
  query (OFF-identity provada por scripts/_test_mv7_professions.py).
- Leitores de bônus são SYNC sobre o objeto Player (zero query) — os engines
  consumidores (alquimia/forja/meridianos) chamam com o player que JÁ têm.
- O engine NÃO abre sessões nem commita — exceto generate_market_reports
  (job de pulse: commit próprio + rollback engolido, padrão sync_region_states).
- Dependência disclosed: o bônus de rep (+0.5) EXIGE reputacao_rival ON — a
  linha de sinergia só aparece nas superfícies quando a rep existe (Lei §1).

Knobs: env ``PROF_*`` (engine, não DB — Lei §13). O per-world fica só no
`profession_speed` (balance knob, admin panel self-doc).
"""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timezone
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy import text as _sql_text

from core.continent_engine import CONTINENT_KEYS, is_valid_continent

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Flag + catálogo (engine data — wipe-safe, Lei §5; nunca migration)
# ══════════════════════════════════════════════════════════════════════════

def profissoes_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (padrão reputacao_on). Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("profissoes", world_key))
    except Exception:
        return False


# As 3 profissões da Onda 1. Keys canônicas sem acento (players.profession).
# name/desc/cerimônia vivem nos locales do CHAT (server-resolved ×2 superfícies,
# padrão storylet content); `tracker` = objective_type EXATO do track_quest.
PROFESSIONS: dict[str, dict[str, Any]] = {
    "alquimista": {"emoji": "🧪", "native": "yanshan", "tracker": "craft_pill"},
    "ferreiro":   {"emoji": "⚒️", "native": "fenghuo", "tracker": "forge_artifact"},
    "medico":     {"emoji": "🩺", "native": "linghe",  "tracker": "use_pill"},
}

# Teaser honesto (Lei §1 roadmap teaser): salões ainda fechados. Só i18n.
FUTURE_PROFESSIONS: tuple[str, ...] = (
    "talismancista", "domador", "cozinheiro", "cartografo", "mercador",
    "mestre_formacoes",
)

# Prefiltro estático do gancho em track_quest (padrão _TRACKED_TYPES MV-5):
# se o objective_type não é de profissão, retorno imediato — zero custo no
# hot path (login/cultivate/boss_damage disparam track_quest o tempo todo).
_PROF_TRACKED: frozenset[str] = frozenset(
    p["tracker"] for p in PROFESSIONS.values()
)

# Tiers de ofício (4, thresholds DUROS — progressão dura + visível).
PROF_TIER_COUNT = 4
PROF_TIER_T2 = int(os.getenv("PROF_TIER_T2", "100"))
PROF_TIER_T3 = int(os.getenv("PROF_TIER_T3", "400"))
PROF_TIER_T4 = int(os.getenv("PROF_TIER_T4", "1200"))

# XP (Lei §13 — knobs, nunca estoque).
PROF_XP_BASE = int(os.getenv("PROF_XP_BASE", "2"))
PROF_NATIVE_XP_MULT = float(os.getenv("PROF_NATIVE_XP_MULT", "1.5"))
PROF_REP_XP_BONUS = float(os.getenv("PROF_REP_XP_BONUS", "0.5"))
PROF_XP_MULT_CAP = float(os.getenv("PROF_XP_MULT_CAP", "2.0"))
# Cap de amount POR chamada (use_pill bulk pode vir com applied grande).
PROF_XP_AMOUNT_CAP = int(os.getenv("PROF_XP_AMOUNT_CAP", "10"))

# ── QoL-relatos (report do jogador [jogador], 28/07) — o ofício tem de PESAR ──────────
# O defeito: `gain = PROF_XP_BASE × n × mult`, onde n é a CONTAGEM de eventos
# do track_quest — nunca o valor do que foi feito. Pílula T1 == pílula T4 (2
# XP), mas a T4 custa 3× a energia: refinar alto era PUNIDO. O peso corrige.
#
# ESCALA ÚNICA 1..6 para os 3 ofícios — confirmada no código, não inventada
# (o prompt supunha 1..4; os catálogos dizem outra coisa):
#   craft_pill / use_pill → PillCatalog.required_alchemy_tier  (1..5, models:889)
#   forge_artifact        → ForgeRecipe.tier                   (1..6, models:1968)
# NÃO usar ArtifactCatalog.grade (0..8): é o grau do blueprint, e o grau
# forjado é ROLADO — pesaria a SORTE, não o esforço.
#
# ⚠️ MAX_FORGE_TIER=5 (forge_engine.py:18) é o teto do NÍVEL DO FERREIRO, NÃO
# o teto da receita. O portão real é `recipe.tier > forge_skill.tier + 1`
# (forge_engine.py:650), então um ferreiro Lendário (5) forja receitas de
# tier 6 — e há SEIS delas seedadas (as Celestiais, forge_seeds ids 26-31,
# realm 8, 20% de sucesso). Ler o cap do skill como cap da receita punia a
# receita mais dura do jogo com o MENOR XP do jogo: o mesmo defeito que este
# lote existe para corrigir, invertido no topo da escada.
#
# A CONTA (energia de alquimia por craft, config.py:209 → 10/15/20/30/50):
#   tier   1      2      3      4      5      6 (só forja — não gasta energia)
#   peso   1      2      3.5    5.5    9.5    14
#   XP     2      4      7      11     19     28    (× PROF_XP_BASE, mult 1.0)
#   XP/en  0.200  0.267  0.350  0.367  0.380  —     ← monótona: refinar alto COMPENSA
# Com o 1/2/3.5/5 do prompt, T4 dava 0.333 XP/energia — ABAIXO do T3 (0.350),
# ou seja o defeito sobreviveria no topo. §1 manda "rodar a conta; se ainda
# não compensar, o peso está errado": daí T4 5→5.5 e os T5/T6 novos. Todos
# são knobs — `PROF_XP_TIER_W=1,2,3.5,5,7,7` aproxima o proposto no prompt.
PROF_XP_TIER_COUNT = 6
_XP_TIER_W_RAW = os.getenv("PROF_XP_TIER_W", "1,2,3.5,5.5,9.5,14")

# Troca de ofício: custo alto + XP zera (disclosure honesta — identidade).
PROF_SWITCH_COST = int(os.getenv("PROF_SWITCH_COST", "10000"))

# ── O que cada ofício MORDE (caps PROVADOS no teste) ──────────────────────
# 🧪 alquimista: +2 pontos %/tier no success_chance (cap +10 — guarda).
PROF_ALCH_SUCCESS_PER_TIER = float(os.getenv("PROF_ALCH_SUCCESS_PER_TIER", "2.0"))
PROF_ALCH_SUCCESS_CAP = float(os.getenv("PROF_ALCH_SUCCESS_CAP", "10.0"))
# 🧪 pílula extra (só T1-T2 — as pills baratas; nunca heavenly): %/tier.
PROF_EXTRA_PILL_PER_TIER = float(os.getenv("PROF_EXTRA_PILL_PER_TIER", "0.04"))
PROF_EXTRA_PILL_CAP = float(os.getenv("PROF_EXTRA_PILL_CAP", "0.16"))
PROF_EXTRA_PILL_MAX_TIER = int(os.getenv("PROF_EXTRA_PILL_MAX_TIER", "2"))
# ⚒️ ferreiro: desconto de minério por tier (floor + mínimo 1 — visível).
_FORGE_DISCOUNTS_RAW = os.getenv("PROF_FORGE_DISCOUNTS", "0.05,0.08,0.12,0.15")
# ⚒️ refino grátis: chance por tier de a duplicata SOBREVIVER à tentativa.
PROF_FREE_REFINE_PER_TIER = float(os.getenv("PROF_FREE_REFINE_PER_TIER", "0.04"))
PROF_FREE_REFINE_CAP = float(os.getenv("PROF_FREE_REFINE_CAP", "0.16"))
# 🩺 médico: cura de pílula HP multiplicada por (1 + bônus do tier).
_HEAL_BONUSES_RAW = os.getenv("PROF_HEAL_BONUSES", "0.10,0.15,0.20,0.25")
# 🩺 sinergia meridianos: circular −10% tempo (qualquer tier de médico).
PROF_MEDIC_CIRCULATE_MULT = float(os.getenv("PROF_MEDIC_CIRCULATE_MULT", "0.9"))
# 🩺 heal de aliado: gap de reino espelha o P2P trade (anti-abuso).
PROF_HEAL_REALM_GAP = int(os.getenv("PROF_HEAL_REALM_GAP", "3"))

# Relatório do Mercado Imperial.
PROF_REPORT_WINDOW_DAYS = int(os.getenv("PROF_REPORT_WINDOW_DAYS", "7"))
PROF_REPORT_TOP_ITEMS = int(os.getenv("PROF_REPORT_TOP_ITEMS", "3"))


def _parse_tier_curve(raw: str, fallback: tuple[float, ...]) -> tuple[float, ...]:
    try:
        vals = tuple(float(x.strip()) for x in raw.split(",") if x.strip())
        return vals if len(vals) == PROF_TIER_COUNT else fallback
    except Exception:
        return fallback


PROF_FORGE_DISCOUNTS = _parse_tier_curve(_FORGE_DISCOUNTS_RAW, (0.05, 0.08, 0.12, 0.15))
PROF_HEAL_BONUSES = _parse_tier_curve(_HEAL_BONUSES_RAW, (0.10, 0.15, 0.20, 0.25))

# QoL-relatos — parser PRÓPRIO: o peso do ITEM tem 5 degraus, o tier do OFÍCIO tem
# 4. Reusar _parse_tier_curve (que exige len == PROF_TIER_COUNT) engoliria a
# curva de 5 em silêncio e voltaria ao fallback — dois eixos, dois parsers.
_XP_TIER_W_FALLBACK: tuple[float, ...] = (1.0, 2.0, 3.5, 5.5, 9.5, 14.0)


def _parse_xp_tier_curve(raw: str, fallback: tuple[float, ...]) -> tuple[float, ...]:
    try:
        vals = tuple(float(x.strip()) for x in raw.split(",") if x.strip())
        if len(vals) != PROF_XP_TIER_COUNT:
            return fallback
        # Peso 0/negativo mataria o XP do ofício (pior que o defeito que
        # estamos a corrigir) — um knob mal digitado nunca zera o ganho.
        return vals if all(v > 0 for v in vals) else fallback
    except Exception:
        return fallback


PROF_XP_TIER_W = _parse_xp_tier_curve(_XP_TIER_W_RAW, _XP_TIER_W_FALLBACK)


def prof_weight(tier: Any) -> tuple[int, float]:
    """UMA verdade do peso do ofício (QoL-relatos). → (tier_normalizado, peso).

    Tier ausente/inválido/< 1 → ``(0, 1.0)``: peso NEUTRO, nunca 0. O 0 no
    tier é o sinal de "não sei o que foi feito" — as superfícies usam-no para
    omitir a cláusula do peso em vez de mentir um "tier 0" (Lei §1), e o 1.0
    garante que o ganho continua idêntico ao de antes desta mudança (é o que
    mantém os testes MV-7 byte-idênticos com players sem tier).

    Tier inteiro ACIMA da curva → **topo da curva**, nunca o neutro. Um tier
    acima da escala é conteúdo mais DURO, jamais "desconhecido": tratá-lo como
    neutro pagaria o menor XP do jogo pela receita mais difícil (foi o que a
    revisão apanhou com as receitas Celestiais de tier 6). Assim, seedar um
    tier 7 amanhã degrada para o topo em vez de reabrir o buraco.
    """
    try:
        t_int = int(tier)
    except (TypeError, ValueError):
        return (0, 1.0)
    if t_int < 1:
        return (0, 1.0)
    t_int = min(t_int, PROF_XP_TIER_COUNT)
    return (t_int, float(PROF_XP_TIER_W[t_int - 1]))

# Espelho do buff_potency do alchemy_engine (apply_pill_effect:507) — o heal
# de aliado respeita a qualidade da pílula como o self-use respeita.
_QUALITY_POTENCY = {"normal": 1.0, "perfect": 1.3, "divine": 1.6, "heavenly": 2.2}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════
# Tiers / XP (puros — sem I/O)
# ══════════════════════════════════════════════════════════════════════════

def tier_thresholds() -> tuple[int, int, int, int]:
    """XP mínimo de cada tier (T1 Aprendiz = 0)."""
    return (0, PROF_TIER_T2, PROF_TIER_T3, PROF_TIER_T4)


def tier_for_xp(xp: Any) -> int:
    """Tier 1..4 derivado do XP (UMA verdade — nunca persistido)."""
    try:
        x = max(0, int(xp or 0))
    except (TypeError, ValueError):
        x = 0
    tier = 1
    for i, th in enumerate(tier_thresholds()):
        if x >= th:
            tier = i + 1
    return min(PROF_TIER_COUNT, tier)


def xp_progress(xp: Any) -> dict[str, Any]:
    """{tier, xp, floor, next} — next=None no Grão-Mestre (teto honesto)."""
    try:
        x = max(0, int(xp or 0))
    except (TypeError, ValueError):
        x = 0
    tier = tier_for_xp(x)
    ths = tier_thresholds()
    floor = ths[tier - 1]
    nxt = ths[tier] if tier < PROF_TIER_COUNT else None
    return {"tier": tier, "xp": x, "floor": floor, "next": nxt}


def profession_meta(key: Any) -> dict[str, Any] | None:
    """Meta do catálogo (None p/ key inválida). Puro."""
    return PROFESSIONS.get(str(key or ""))


def _player_prof(player) -> tuple[str, dict[str, Any], int] | None:
    """(key, meta, tier) do player — None se sem ofício/ofício inválido."""
    key = getattr(player, "profession", None)
    meta = PROFESSIONS.get(key or "")
    if not meta:
        return None
    return key, meta, tier_for_xp(getattr(player, "profession_xp", 0))


# ══════════════════════════════════════════════════════════════════════════
# Bônus que MORDEM (leitores SYNC sobre o Player — zero query, fail-safe)
# ══════════════════════════════════════════════════════════════════════════

def alchemy_success_bonus(player) -> float:
    """🧪 pontos % somados ao success_chance (0.0 com flag OFF / outro ofício).
    Entra DENTRO de calculate_success_chance → display = roll (lição MV-6)."""
    try:
        if not profissoes_on():
            return 0.0
        pp = _player_prof(player)
        if not pp or pp[0] != "alquimista":
            return 0.0
        return min(PROF_ALCH_SUCCESS_CAP, pp[2] * PROF_ALCH_SUCCESS_PER_TIER)
    except Exception:
        logger.exception("alchemy_success_bonus failed")
        return 0.0


def extra_pill_chance(player, pill_tier: Any) -> float:
    """🧪 chance de pílula extra (só pills T1-T2; 0.0 fora do ofício)."""
    try:
        if not profissoes_on():
            return 0.0
        try:
            if int(pill_tier or 1) > PROF_EXTRA_PILL_MAX_TIER:
                return 0.0
        except (TypeError, ValueError):
            return 0.0
        pp = _player_prof(player)
        if not pp or pp[0] != "alquimista":
            return 0.0
        return min(PROF_EXTRA_PILL_CAP, pp[2] * PROF_EXTRA_PILL_PER_TIER)
    except Exception:
        logger.exception("extra_pill_chance failed")
        return 0.0


def roll_extra_pill(player, pill_tier: Any) -> bool:
    """🧪 o roll da pílula extra (random module-level — testável)."""
    chance = extra_pill_chance(player, pill_tier)
    return chance > 0.0 and random.random() < chance


def forge_ore_discount(player) -> float:
    """⚒️ fração de desconto no custo de minério (0.0 fora do ofício)."""
    try:
        if not profissoes_on():
            return 0.0
        pp = _player_prof(player)
        if not pp or pp[0] != "ferreiro":
            return 0.0
        return float(PROF_FORGE_DISCOUNTS[pp[2] - 1])
    except Exception:
        logger.exception("forge_ore_discount failed")
        return 0.0


def discounted_qty(qty: Any, discount: float) -> int:
    """Qty efetiva de UM material com desconto: floor + mínimo 1 (visível —
    regra da progressão: −5% que não muda nenhum número exibido = nada).
    discount 0.0 → qty intacta (caminho legado byte-idêntico)."""
    try:
        q = int(qty or 0)
        if q <= 0 or discount <= 0.0:
            return q
        return max(1, int(q * (1.0 - min(0.9, float(discount)))))
    except Exception:
        return int(qty or 0)


def free_refine_chance(player) -> float:
    """⚒️ chance de a duplicata SOBREVIVER à tentativa de refino."""
    try:
        if not profissoes_on():
            return 0.0
        pp = _player_prof(player)
        if not pp or pp[0] != "ferreiro":
            return 0.0
        return min(PROF_FREE_REFINE_CAP, pp[2] * PROF_FREE_REFINE_PER_TIER)
    except Exception:
        logger.exception("free_refine_chance failed")
        return 0.0


def roll_free_refine(player) -> bool:
    """⚒️ o roll do refino grátis — UMA vez, ANTES do charm (o proc do ofício
    nunca 'consome' o Forge Protection Charm do jogador)."""
    chance = free_refine_chance(player)
    return chance > 0.0 and random.random() < chance


def medic_heal_bonus(player) -> float:
    """🩺 fração somada ao multiplicador da cura de pílulas HP (self E alvo)."""
    try:
        if not profissoes_on():
            return 0.0
        pp = _player_prof(player)
        if not pp or pp[0] != "medico":
            return 0.0
        return float(PROF_HEAL_BONUSES[pp[2] - 1])
    except Exception:
        logger.exception("medic_heal_bonus failed")
        return 0.0


def medic_circulate_mult(player) -> float:
    """🩺 multiplicador do TEMPO de circular dos meridianos (0.9 = −10%).
    Aplicado nos DOIS call sites do MV-4 (start_ritual E retry do break) —
    nunca dentro de refine_place_mult (que é compartilhado com o temperar)."""
    try:
        if not profissoes_on():
            return 1.0
        pp = _player_prof(player)
        if not pp or pp[0] != "medico":
            return 1.0
        return max(0.5, PROF_MEDIC_CIRCULATE_MULT)
    except Exception:
        logger.exception("medic_circulate_mult failed")
        return 1.0


# ══════════════════════════════════════════════════════════════════════════
# XP — multiplicador regional + o gancho do track_quest
# ══════════════════════════════════════════════════════════════════════════

async def xp_multiplier(session, player) -> dict[str, Any]:
    """A verdade ÚNICA do multiplicador de XP (o número mostrado vem da MESMA
    função que credita — lição MV-6). {mult, native, rep_synergy, speed}.
    native: está no continente favorável (×PROF_NATIVE_XP_MULT).
    rep_synergy: nativo E rep ≥ threshold (soma +0.5; EXIGE reputacao_rival ON).
    speed: knob per-world profession_speed (multiplica TUDO no fim)."""
    out = {"mult": 1.0, "native": False, "rep_synergy": False, "speed": 1.0}
    try:
        if not profissoes_on():
            return out
        pp = _player_prof(player)
        if not pp:
            return out
        _key, meta, _tier = pp
        cont = getattr(player, "current_continent", None) or "linghe"
        base = 1.0
        if cont == meta["native"]:
            base = PROF_NATIVE_XP_MULT
            out["native"] = True
            try:
                from core.reputation_engine import (
                    REP_DISCOUNT_THRESHOLD, get_region_rep, reputacao_on,
                )
                if reputacao_on():
                    rep = await get_region_rep(session, int(player.telegram_id), cont)
                    if rep >= REP_DISCOUNT_THRESHOLD:
                        base += PROF_REP_XP_BONUS
                        out["rep_synergy"] = True
            except Exception:
                logger.debug("xp_multiplier rep synergy failed", exc_info=True)
        base = min(PROF_XP_MULT_CAP, base)
        try:
            from database.db import get_world_balance
            speed = float(get_world_balance().get("profession_speed", 1.0) or 1.0)
        except Exception:
            speed = 1.0
        out["speed"] = speed
        out["mult"] = base * speed
        return out
    except Exception:
        logger.exception("xp_multiplier failed")
        return out


async def track_profession(session, player_id: int, objective_type: str,
                           amount: int = 1, *, weight_tier: Any = None) -> None:
    """O gancho aditivo dentro de track_quest (chokepoint — lição MV-5).
    Ordem: (1) prefiltro estático SEM flag check (hot path: login/cultivate
    pagam só um lookup de frozenset); (2) flag; (3) query. Nunca levanta.

    QoL-relatos — `weight_tier` é o tier do que foi CRIADO/USADO (1..5) e chega por
    um canal PRÓPRIO, keyword-only. É deliberadamente separado de `amount`: o
    `amount` alimenta o contador de objetivo das quests e dos storylets, logo
    mandar o peso por lá faria "forje 5 artefatos" fechar em 1 forja (a
    armadilha §0.3 do prompt). Ausente → peso 1.0 = comportamento de antes."""
    try:
        if str(objective_type) not in _PROF_TRACKED:
            return
        if not profissoes_on():
            return
        from database.models import Player
        player = (await session.execute(
            select(Player).where(Player.telegram_id == int(player_id))
        )).scalar_one_or_none()
        if player is None:
            return
        pp = _player_prof(player)
        if not pp or pp[1]["tracker"] != str(objective_type):
            return
        _key, _meta, tier_before = pp
        info = await xp_multiplier(session, player)
        n = max(1, min(PROF_XP_AMOUNT_CAP, int(amount or 1)))
        # QoL-relatos — o peso entra AQUI (nunca via `amount`, que é o contador).
        _tier, _w = prof_weight(weight_tier)
        gain = int(round(PROF_XP_BASE * n * _w * info["mult"]))
        if gain <= 0:
            return
        player.profession_xp = max(0, int(player.profession_xp or 0)) + gain
        tier_after = tier_for_xp(player.profession_xp)
        if tier_after > tier_before:
            await _notify_tier_up(session, player, tier_before, tier_after)
    except Exception:
        logger.exception("track_profession failed (player=%s, type=%s)",
                         player_id, objective_type)


def prof_xp_snapshot(player) -> int | None:
    """TEC-1 §0.1 (pedido do jogador [jogador]) — snapshot do XP de ofício ANTES do
    track_quest, para exibir o delta no resumo do craft (progressão visível,
    Lei §10). None quando flag OFF / sem ofício — o caller só emite a chave
    quando o delta > 0 (chave CONDICIONAL, lição MV-7: main byte-idêntico)."""
    try:
        if not profissoes_on():
            return None
        if not getattr(player, "profession", None):
            return None
        return max(0, int(getattr(player, "profession_xp", 0) or 0))
    except Exception:
        return None


def prof_xp_delta(player, before: int | None) -> int:
    """O XP de ofício ganho desde o snapshot (0 = não emitir a chave).
    Funciona porque track_profession muta o MESMO Player do identity map."""
    if before is None:
        return 0
    try:
        return max(0, int(getattr(player, "profession_xp", 0) or 0) - int(before))
    except Exception:
        return 0


def _bonus_delta(player_key: str, tier_a: int, tier_b: int) -> str:
    """O delta VISÍVEL do level-up (antes→depois), language-neutral
    (números+%; o domínio vem do emoji na notificação)."""
    def _fmt(prof: str, tier: int) -> str:
        t = max(1, min(PROF_TIER_COUNT, tier))
        if prof == "alquimista":
            return f"+{min(PROF_ALCH_SUCCESS_CAP, t * PROF_ALCH_SUCCESS_PER_TIER):g}%"
        if prof == "ferreiro":
            return f"-{PROF_FORGE_DISCOUNTS[t - 1] * 100:g}%"
        return f"+{PROF_HEAL_BONUSES[t - 1] * 100:g}%"
    return f"{_fmt(player_key, tier_a)} → {_fmt(player_key, tier_b)}"


async def _notify_tier_up(session, player, tier_before: int, tier_after: int) -> None:
    """Level-up de ofício: notificação com o DELTA (progressão visível).
    Best-effort — nunca derruba o crédito de XP."""
    try:
        pp = _player_prof(player)
        if not pp:
            return
        key, meta, _t = pp
        from core.notification_engine import notify
        await notify(
            session, int(player.telegram_id), "profession",
            title_key="notif_prf_tier_title",
            body_key="notif_prf_tier_body",
            payload={"emoji": meta["emoji"], "tier": tier_after,
                     "delta": _bonus_delta(key, tier_before, tier_after)},
            ref_id=f"prf:{player.telegram_id}:{tier_after}",
            icon=meta["emoji"], target_tab="profile", priority=3,
        )
    except Exception:
        logger.debug("profession tier-up notify failed", exc_info=True)


# ══════════════════════════════════════════════════════════════════════════
# Escolha / troca (cerimônia — o caller segura o lock do player e commita)
# ══════════════════════════════════════════════════════════════════════════

async def choose_profession(session, player, key: str, lang: str = "pt") -> dict[str, Any]:
    """Escolher o PRIMEIRO ofício (identidade). Refusas honestas por reason.
    O caller é dono do commit (e do lock do player)."""
    if not profissoes_on():
        return {"ok": False, "reason": "prf_locked"}
    try:
        meta = PROFESSIONS.get(str(key or ""))
        if not meta:
            return {"ok": False, "reason": "prf_bad_key"}
        if getattr(player, "profession", None) in PROFESSIONS:
            return {"ok": False, "reason": "prf_has",
                    "current": player.profession}
        player.profession = str(key)
        player.profession_xp = 0
        player.profession_started_at = _utcnow()
        await _chronicle_first_choice(session, player)
        return {"ok": True, "key": str(key), "emoji": meta["emoji"],
                "native": meta["native"], "tier": 1}
    except Exception:
        logger.exception("choose_profession failed (player=%s, key=%s)",
                         getattr(player, "telegram_id", None), key)
        return {"ok": False, "reason": "internal_error"}


async def switch_profession(session, player, key: str, lang: str = "pt") -> dict[str, Any]:
    """Trocar de ofício: custo alto + XP ZERA (disclosure honesta na UI antes
    do confirm). O caller segura o lock do player e commita."""
    if not profissoes_on():
        return {"ok": False, "reason": "prf_locked"}
    try:
        meta = PROFESSIONS.get(str(key or ""))
        if not meta:
            return {"ok": False, "reason": "prf_bad_key"}
        old = getattr(player, "profession", None)
        if old not in PROFESSIONS:
            # Sem ofício → é uma escolha, não troca (sem custo).
            return await choose_profession(session, player, key, lang)
        if old == str(key):
            return {"ok": False, "reason": "prf_same"}
        stones = int(getattr(player, "spirit_stones", 0) or 0)
        if stones < PROF_SWITCH_COST:
            return {"ok": False, "reason": "prf_no_stones",
                    "cost": PROF_SWITCH_COST, "have": stones}
        player.spirit_stones = stones - PROF_SWITCH_COST
        player.profession = str(key)
        player.profession_xp = 0
        player.profession_started_at = _utcnow()
        return {"ok": True, "key": str(key), "old": old,
                "cost": PROF_SWITCH_COST, "emoji": meta["emoji"],
                "native": meta["native"], "tier": 1}
    except Exception:
        logger.exception("switch_profession failed (player=%s, key=%s)",
                         getattr(player, "telegram_id", None), key)
        return {"ok": False, "reason": "internal_error"}


async def _chronicle_first_choice(session, player) -> None:
    """Chronicle no 1º ofício do SERVIDOR (advisory lock — padrão sty_first).
    Best-effort; probe barata via profession IS NOT NULL."""
    try:
        await session.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext('prf_first'))"))
        row = (await session.execute(
            _sql_text("SELECT 1 FROM players WHERE profession IS NOT NULL "
                      "AND telegram_id != :me LIMIT 1"),
            {"me": int(player.telegram_id)},
        )).scalar()
        if row is None:
            from core.world_pulse_engine import emit_chronicle
            await emit_chronicle(
                session, event_type="prf_first", text_key="prf_chron_first",
                continent_key=getattr(player, "current_continent", None),
                importance=1,
            )
    except Exception:
        logger.debug("profession first-choice chronicle failed", exc_info=True)


# ══════════════════════════════════════════════════════════════════════════
# View (a verdade das superfícies — /oficio, mini card, ProfileModal)
# ══════════════════════════════════════════════════════════════════════════

async def get_profession_view(session, player, lang: str = "pt") -> dict[str, Any] | None:
    """Payload ÚNICO das 2 superfícies (server-resolved — padrão storylet).
    Flag OFF → None (payload byte-idêntico em main). Nunca levanta."""
    if not profissoes_on():
        return None
    try:
        from core.i18n import t
        pp = _player_prof(player)
        if not pp:
            choices = []
            for k, m in PROFESSIONS.items():
                choices.append({
                    "key": k, "emoji": m["emoji"],
                    "name": t(lang, f"prf_name_{k}"),
                    "desc": t(lang, f"prf_desc_{k}"),
                    "native": m["native"],
                    "native_name": t(lang, f"continent_{m['native']}"),
                })
            return {
                "has": False, "choices": choices,
                "future": [t(lang, f"prf_name_{k}") for k in FUTURE_PROFESSIONS],
                "teaser": t(lang, "prf_future_teaser"),
                "switch_cost": PROF_SWITCH_COST,
            }
        key, meta, tier = pp
        prog = xp_progress(getattr(player, "profession_xp", 0))
        info = await xp_multiplier(session, player)
        bonuses: list[str] = []
        if key == "alquimista":
            bonuses.append(t(lang, "prf_bonus_alch_success",
                             pct=f"{min(PROF_ALCH_SUCCESS_CAP, tier * PROF_ALCH_SUCCESS_PER_TIER):g}"))
            ep = min(PROF_EXTRA_PILL_CAP, tier * PROF_EXTRA_PILL_PER_TIER)
            bonuses.append(t(lang, "prf_bonus_alch_extra", pct=f"{ep * 100:g}"))
        elif key == "ferreiro":
            bonuses.append(t(lang, "prf_bonus_forge_ore",
                             pct=f"{PROF_FORGE_DISCOUNTS[tier - 1] * 100:g}"))
            fr = min(PROF_FREE_REFINE_CAP, tier * PROF_FREE_REFINE_PER_TIER)
            bonuses.append(t(lang, "prf_bonus_forge_refine", pct=f"{fr * 100:g}"))
        else:
            bonuses.append(t(lang, "prf_bonus_medic_heal",
                             pct=f"{PROF_HEAL_BONUSES[tier - 1] * 100:g}"))
            bonuses.append(t(lang, "prf_bonus_medic_ally"))
            bonuses.append(t(lang, "prf_bonus_medic_meridians",
                             pct=f"{(1.0 - PROF_MEDIC_CIRCULATE_MULT) * 100:g}"))
        view: dict[str, Any] = {
            "has": True, "key": key, "emoji": meta["emoji"],
            "name": t(lang, f"prf_name_{key}"),
            "tier": tier, "tier_name": t(lang, f"prf_tier_{tier}"),
            "xp": prog["xp"], "xp_floor": prog["floor"], "xp_next": prog["next"],
            "native": meta["native"],
            "native_name": t(lang, f"continent_{meta['native']}"),
            "in_native": info["native"],
            "xp_mult": round(info["mult"], 2),
            "bonuses": bonuses,
            "switch_cost": PROF_SWITCH_COST,
        }
        # Sinergia de rep: só disclosed quando a rep EXISTE no mundo (Lei §1 —
        # nunca prometer um bônus inalcançável com reputacao_rival OFF).
        try:
            from core.reputation_engine import reputacao_on
            if reputacao_on():
                view["rep_synergy"] = info["rep_synergy"]
                view["rep_synergy_line"] = t(
                    lang, "prf_rep_synergy_on" if info["rep_synergy"]
                    else "prf_rep_synergy_off",
                    native=view["native_name"])
        except Exception:
            pass
        return view
    except Exception:
        logger.exception("get_profession_view failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return None


# ══════════════════════════════════════════════════════════════════════════
# 🩺 Heal de aliado — a 1ª mecânica social de profissão (mini-app)
# ══════════════════════════════════════════════════════════════════════════

async def heal_ally(session, healer, target_dao_name: str,
                    inventory_item_id: int, lang: str = "pt") -> dict[str, Any]:
    """Médico usa uma pílula de HP DO PRÓPRIO anel em outro cultivador.

    Regras (todas disclosed por reason — Lei §1):
    - só médico; alvo por dao_name (not-found ≡ shadow_mode — padrão trade);
    - MESMO continente (a pílula não cruza o mundo — e cria motivo de viagem);
    - gap de reino < PROF_HEAL_REALM_GAP (espelho do P2P trade);
    - alvo com HP cheio → recusa ANTES de debitar a pílula;
    - locks nos DOIS players em ordem ASCENDENTE de telegram_id (anti AB-BA,
      lição MA-39a). O caller commita.
    Cura = effect_value × qualidade × (1 + bônus do tier do médico) — sem
    facção/resistência do alvo (fórmula limpa e disclosed; resistência de
    medicina guarda pílulas de qi_capacity, não HP)."""
    if not profissoes_on():
        return {"ok": False, "reason": "prf_locked"}
    try:
        pp = _player_prof(healer)
        if not pp or pp[0] != "medico":
            return {"ok": False, "reason": "prf_not_medico"}
        from sqlalchemy import func
        from database.models import PillCatalog, Player, PlayerInventory
        dao = str(target_dao_name or "").strip()
        if not dao:
            return {"ok": False, "reason": "prf_heal_not_found"}
        target = (await session.execute(
            select(Player).where(func.lower(Player.dao_name) == dao.lower())
        )).scalar_one_or_none()
        if not target or getattr(target, "shadow_mode", False):
            return {"ok": False, "reason": "prf_heal_not_found"}
        if int(target.telegram_id) == int(healer.telegram_id):
            return {"ok": False, "reason": "prf_heal_self"}
        if abs(int(target.realm or 0) - int(healer.realm or 0)) >= PROF_HEAL_REALM_GAP:
            return {"ok": False, "reason": "prf_heal_realm_gap"}
        h_cont = getattr(healer, "current_continent", None) or "linghe"
        t_cont = getattr(target, "current_continent", None) or "linghe"
        if h_cont != t_cont:
            return {"ok": False, "reason": "prf_heal_continent",
                    "continent": t_cont}
        # Locks em ordem ascendente (anti AB-BA — lição do P2P trade).
        ids = sorted((int(healer.telegram_id), int(target.telegram_id)))
        for pid in ids:
            await session.execute(
                select(Player).where(Player.telegram_id == pid).with_for_update()
            )
        inv = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.id == int(inventory_item_id),
                PlayerInventory.player_id == int(healer.telegram_id),
                PlayerInventory.item_type == "pill",
                PlayerInventory.quantity > 0,
            ).with_for_update()
        )).scalar_one_or_none()
        if inv is None:
            return {"ok": False, "reason": "prf_heal_no_pill"}
        pill = (await session.execute(
            select(PillCatalog).where(PillCatalog.id == int(inv.item_id))
        )).scalar_one_or_none()
        if pill is None or getattr(pill, "effect_type", None) != "hp_restore":
            return {"ok": False, "reason": "prf_heal_not_hp"}
        from core.combat_engine import get_current_hp, get_max_hp, restore_hp_pct
        t_max = float(get_max_hp(target))
        t_cur = float(get_current_hp(target))
        if t_cur >= t_max - 0.5:
            return {"ok": False, "reason": "prf_heal_full"}
        quality = str(getattr(inv, "quality", None) or "normal")
        potency = _QUALITY_POTENCY.get(quality, 1.0)
        pct = float(pill.effect_value or 0.0) * potency * (1.0 + medic_heal_bonus(healer))
        # Debita a pílula SÓ depois de todas as recusas (Lei §1).
        inv.quantity = int(inv.quantity) - 1
        if inv.quantity <= 0:
            await session.delete(inv)
        restored = float(restore_hp_pct(target, pct))
        # Karma: o wire que faltava desde o v16.3 (keys já existiam).
        try:
            from core.karma_engine import apply_karma
            await apply_karma(session, int(healer.telegram_id), "heal_ally_combat")
        except Exception:
            logger.debug("heal_ally karma wire failed", exc_info=True)
        # Tracker do consumidor = o MÉDICO (alimenta quests E o XP do ofício).
        try:
            from core.quest_engine import track_quest
            # QoL-relatos — curar com uma pílula alta pesa mais que com uma baixa.
            await track_quest(session, int(healer.telegram_id), "use_pill", 1,
                              prof_weight_tier=getattr(
                                  pill, "required_alchemy_tier", None))
        except Exception:
            logger.debug("heal_ally track_quest failed", exc_info=True)
        # O alvo FICA SABENDO quem o curou (notificação best-effort).
        try:
            from core.notification_engine import notify
            await notify(
                session, int(target.telegram_id), "prf_heal",
                title_key="notif_prf_healed_title",
                body_key="notif_prf_healed_body",
                payload={"name": str(healer.dao_name or healer.username or "???"),
                         "hp": int(restored)},
                icon="🩺", target_tab="home", priority=4,
            )
        except Exception:
            logger.debug("heal_ally notify failed", exc_info=True)
        return {"ok": True, "restored": int(restored),
                "target_name": str(target.dao_name or target.username or "???"),
                "target_hp": int(get_current_hp(target)), "target_max_hp": int(t_max),
                "pill_name": getattr(pill, "name", ""), "quality": quality}
    except Exception:
        logger.exception("heal_ally failed (healer=%s)",
                         getattr(healer, "telegram_id", None))
        return {"ok": False, "reason": "internal_error"}


# ══════════════════════════════════════════════════════════════════════════
# 📜 Relatório do Mercado Imperial (World Pulse passo 5 — snapshot honesto)
# ══════════════════════════════════════════════════════════════════════════

async def generate_market_reports(session) -> dict[str, Any] | None:
    """Snapshot dos últimos 7d por continente em region_states.payload
    ["market_report"] (MERGE — nunca substitui o payload do MV-3; rows
    lazy-upserted porque o seed do MV-3 só corre com estados_regionais ON).

    Números honestos (Lei §1): preço BASE (o mult regional do MV-3/MV-6 não
    persiste — a disclosure diz "preço de tabela"); continente = carimbo em
    details.continent quando existe (só é escrito com a flag ON), senão o
    continente ATUAL do comprador; pedras da taxa E do comércio com NPCs são
    QUEIMADAS (sinks) — o relatório as rotula assim.

    Job de pulse: flag OFF → None SEM query; commit próprio; rollback engolido
    (o pulse nunca cai)."""
    if not profissoes_on():
        return None
    try:
        from datetime import timedelta

        from database.models import Player, RegionState, Transaction
        now = _utcnow()
        cutoff = now - timedelta(days=PROF_REPORT_WINDOW_DAYS)
        rows = (await session.execute(
            select(Transaction, Player.current_continent)
            .join(Player, Player.telegram_id == Transaction.from_player,
                  isouter=True)
            .where(Transaction.created_at >= cutoff,
                   Transaction.type.in_(("buy", "auction")))
        )).all()
        per_cont: dict[str, dict[str, Any]] = {
            k: {"sales": 0, "stones": 0, "tax": 0, "npc_burn": 0, "items": {}}
            for k in CONTINENT_KEYS
        }
        for tx, buyer_cont in rows:
            cont = None
            try:
                cont = (tx.details or {}).get("continent")
            except Exception:
                cont = None
            if not is_valid_continent(cont):
                cont = buyer_cont if is_valid_continent(buyer_cont) else "linghe"
            bucket = per_cont[cont]
            qty = max(1, int(tx.quantity or 1))
            unit = int((tx.price or 0) / qty)
            bucket["sales"] += 1
            bucket["stones"] += int(tx.price or 0)
            bucket["tax"] += int(tx.tax_paid or 0)
            if tx.to_player is None:
                bucket["npc_burn"] += int(tx.price or 0)
            it = str(tx.item_type or "?")
            bucket["items"].setdefault(it, []).append(unit)
        # Lazy-upsert + write com MERGE (armadilhas #1/#2 do recon).
        existing = {r.continent_key: r for r in (await session.execute(
            select(RegionState).order_by(RegionState.continent_key)
            .with_for_update()
        )).scalars().all()}
        written = 0
        for cont in CONTINENT_KEYS:
            row = existing.get(cont)
            if row is None:
                row = RegionState(continent_key=cont, payload={})
                session.add(row)
            b = per_cont[cont]
            top = sorted(b["items"].items(),
                         key=lambda kv: (len(kv[1]), kv[0]), reverse=True)
            report = {
                "window_days": PROF_REPORT_WINDOW_DAYS,
                "sales": b["sales"],
                "stones": b["stones"],
                "tax_burned": b["tax"],
                "npc_burned": b["npc_burn"],
                "top_items": [
                    {"item_type": k, "n": len(v), "median": int(median(v))}
                    for k, v in top[:PROF_REPORT_TOP_ITEMS]
                ],
                "generated_at": now.isoformat(),
            }
            payload = dict(row.payload or {})
            payload["market_report"] = report
            row.payload = payload  # dict NOVO → change tracking vê
            written += 1
        await session.commit()
        total_sales = sum(b["sales"] for b in per_cont.values())
        return {"continents": written, "sales": total_sales}
    except Exception:
        logger.exception("generate_market_reports failed")
        try:
            await session.rollback()
        except Exception:
            pass
        return None


async def market_report_view(session, player, lang: str = "pt") -> dict[str, Any] | None:
    """O snapshot do continente ATUAL do jogador, server-resolved para as 2
    superfícies (linha no /mercado + card no MarketTab). Flag OFF / sem
    snapshot → None (key opcional — payload byte-idêntico). Query DIRETA a
    RegionState (os helpers do MV-3 curto-circuitam com a flag DELES)."""
    if not profissoes_on():
        return None
    try:
        from core.i18n import t
        from database.models import RegionState
        cont = getattr(player, "current_continent", None) or "linghe"
        if not is_valid_continent(cont):
            cont = "linghe"
        row = (await session.execute(
            select(RegionState.payload).where(RegionState.continent_key == cont)
        )).scalar()
        report = (row or {}).get("market_report") if isinstance(row, dict) else None
        if not report:
            return None
        lines: list[str] = []
        sales = int(report.get("sales", 0) or 0)
        if sales <= 0:
            lines.append(t(lang, "prf_report_empty"))
        else:
            lines.append(t(lang, "prf_report_sales", n=sales,
                           stones=int(report.get("stones", 0) or 0)))
            for item in (report.get("top_items") or [])[:PROF_REPORT_TOP_ITEMS]:
                lines.append(t(lang, "prf_report_item",
                               name=t(lang, f"prf_item_{item.get('item_type', '?')}"),
                               n=int(item.get("n", 0) or 0),
                               median=int(item.get("median", 0) or 0)))
            burned = int(report.get("tax_burned", 0) or 0) + int(report.get("npc_burned", 0) or 0)
            if burned > 0:
                lines.append(t(lang, "prf_report_burned", stones=burned))
        return {
            "title": t(lang, "prf_report_title"),
            "continent": cont,
            "continent_name": t(lang, f"continent_{cont}"),
            "window": t(lang, "prf_report_window",
                        days=int(report.get("window_days", PROF_REPORT_WINDOW_DAYS))),
            "lines": lines,
        }
    except Exception:
        logger.exception("market_report_view failed")
        return None


async def transaction_continent_details(session, buyer) -> dict[str, Any] | None:
    """Carimbo do continente do comprador para Transaction.details (gated —
    com a flag OFF devolve None e a Transaction fica EXATAMENTE como hoje;
    main byte-idêntico). O relatório prefere o carimbo ao join volátil.
    `buyer` = objeto Player OU telegram_id (finalize_auction só tem o id)."""
    try:
        if not profissoes_on():
            return None
        if isinstance(buyer, int):
            from database.models import Player
            buyer = (await session.execute(
                select(Player).where(Player.telegram_id == int(buyer))
            )).scalar_one_or_none()
        if buyer is None:
            return None
        cont = getattr(buyer, "current_continent", None) or "linghe"
        return {"continent": cont if is_valid_continent(cont) else "linghe"}
    except Exception:
        return None
