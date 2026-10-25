"""World Pulse 世界脉动 — Fase 1 ("O Coração que Bate").

Grand Design Track A, Pedra 1 (`NIVRAEL_GRAND_DESIGN.md §6 Camada A`). The first
stone of the world that "works EVEN without players" — and the foundation of the
LLM Dao Celestial dream. The 9 ancient sects stop being static metadata and
become AUTONOMOUS ACTORS that act on a scheduler heartbeat, and the world gains a
living CHRONICLE (Registos Celestiais 天记) anyone can read.

Two parts live here:
    * CHRONICLE — an append-only world log (`world_chronicle`). Every beat (and
      any future world event) writes one localized-server-side line. Nearly free,
      sells the "alive without me", and is the ready memory corpus for the LLM.
    * PULSE — the deterministic simulation (`run_world_pulse`). ZERO LLM. For each
      active house it scores a small menu of actions by *weighted-utility* biased
      by the house's hidden personality souls (Crusader Kings) × its state × a
      seeded RNG, picks the best (with a RimWorld-style *Director* cap on MAJOR
      actions so the world has rhythm, not spam), mutates the DB, writes a
      chronicle line, and — for the loud beats — fires one Heaven's Whisper. A raid
      additionally posts a reactive Bounty on a dark-karma NPC (the world reacts).

Design laws (the prompt's §G):
    * ADDITIVE + WIPE-SAFE (Lei §5): `strength` is an ABSTRACT new number that
      does NOT buff any of the 57 live players — it only moves the narrative (and,
      a future phase, scales the Guild blessing §4). Survives the wipe.
    * HONEST + LEGIBLE (Lei §1): the Chronicle shows what happened; each house's
      strength/momentum/last-action is visible in the directory.
    * NPCs stay OFF the ranking (`NPC_LEADERBOARD_ENABLED` untouched); no PII.
    * Idempotent: a per-sect `last_pulse_at` guard means a coalesced double-fire
      no-ops; the decision RNG is seeded by ``(sect_id, tick_epoch)`` so the same
      tick reproduces the same beats. Best-effort: one house failing (SAVEPOINT)
      never aborts the others.

The DECISION layer (`score_actions` / `pick_action` / `action_effects`) is PURE —
no DB, no clock — so it can be dry-run-simulated for N beats without a database
(see ``tools/world_pulse_sim.py``).
"""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update

from database.models import WorldChronicle, WorldSect
from core.continent_engine import CONTINENT_META, is_valid_continent
from core.world_sects_engine import (
    SECT_SOUL_SCALARS,
    WORLD_SECT_KEYS,
    WORLD_SECT_META,
    get_rival_sect,
    get_sect_soul,
    is_valid_sect,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Tuning (engine constants, wipe-safe; env-overridable for ops tuning — Lei §6)
# ══════════════════════════════════════════════════════════════════════════

# 6h default ⇒ 4 beats/day. The scheduler registers the job at this interval.
WORLD_PULSE_INTERVAL_HOURS = float(os.getenv("WORLD_PULSE_INTERVAL_HOURS", "6"))
# Director (RimWorld): at most this many MAJOR actions (raid/claim/inheritance/
# strife) per beat across the whole world — the rest are minor (recruit/fortify).
WORLD_PULSE_MAX_MAJOR_PER_TICK = int(os.getenv("WORLD_PULSE_MAX_MAJOR_PER_TICK", "2"))
# A house that just did a MAJOR action can't do another for this long (Cassandra
# cooldown) — spreads the drama across the 9 houses instead of one repeating.
WORLD_PULSE_MAJOR_COOLDOWN_HOURS = float(os.getenv("WORLD_PULSE_MAJOR_COOLDOWN_HOURS", "18"))
# Seeded decision noise amplitude (keeps beats varied but reproducible per tick).
WORLD_PULSE_NOISE = float(os.getenv("WORLD_PULSE_NOISE", "0.15"))
# Feed read cap (chronicle is append-only; reads stay bounded by this).
CHRONICLE_FEED_CAP = int(os.getenv("WORLD_CHRONICLE_FEED_CAP", "50"))

# Momentum is a small swing state; clamp to keep it from running away.
_MOMENTUM_MIN, _MOMENTUM_MAX = -50, 50


# ══════════════════════════════════════════════════════════════════════════
# The action menu (pure decision data — utility weights, effects, narration)
# ══════════════════════════════════════════════════════════════════════════
# Each action:
#   base/<scalar>   → weighted-utility terms (× the house's 0..1 soul scalar)
#   major           → counts against the Director cap + fires a whisper
#   whisper_theme   → heavens_whispers theme for the loud beats (None ⇒ chronicle-only)
#   text_key        → chronicle template (server-resolved; {sect}/{rival}/{continent})
#   icon, importance
#   needs_rival     → only available if the house has a rival_id
#   honor_below     → only available when honor < this (internal_strife = low-honor)
#   strength/momentum → (lo, hi) seeded INT delta range for the ACTOR
#   rival_strength/rival_momentum → (lo, hi) delta applied to the RIVAL (raid only)
PULSE_ACTIONS: dict[str, dict[str, Any]] = {
    "recruit": {
        "major": False, "whisper_theme": None, "text_key": "chron_recruit",
        "icon": "🏯", "importance": 1,
        "util": {"base": 0.34, "ambition": 0.42},
        "strength": (3, 7), "momentum": (0, 1),
    },
    "fortify": {
        "major": False, "whisper_theme": None, "text_key": "chron_fortify",
        "icon": "🛡️", "importance": 1,
        # The stable default — a calm, honourable house lands here, but the base
        # is tuned so the majors below stay competitive (the world must MOVE).
        # Momentum-neutral: quiet meditation doesn't build narrative momentum
        # (that's earned by the active beats — raids/claims), so it stays a signal.
        "util": {"base": 0.40, "honor": 0.28, "zeal": 0.18},
        "strength": (1, 3), "momentum": (0, 0),
    },
    "claim_node": {
        "major": True, "whisper_theme": "pulse_claim", "text_key": "chron_claim",
        "icon": "🚩", "importance": 2,
        "util": {"base": 0.40, "ambition": 0.46},
        "strength": (4, 9), "momentum": (1, 2),
    },
    "raid_rival": {
        "major": True, "whisper_theme": "pulse_raid", "text_key": "chron_raid",
        "icon": "⚔️", "importance": 2, "needs_rival": True,
        "util": {"base": 0.34, "aggression": 0.46, "greed": 0.30},
        "strength": (3, 8), "momentum": (1, 2),
        "rival_strength": (-7, -3), "rival_momentum": (-2, -1),
    },
    "seek_inheritance": {
        "major": True, "whisper_theme": "pulse_inheritance", "text_key": "chron_inheritance",
        "icon": "⚰️", "importance": 2,
        "util": {"base": 0.42, "zeal": 0.42},
        "strength": (2, 6), "momentum": (0, 1),
    },
    "internal_strife": {
        # SPECIAL: not in the weighted-utility menu — a rare blood-feud pre-roll
        # for a low-honour house only (Director-capped like any major). "Raro."
        "major": True, "special": True, "honor_below": 0.40,
        "whisper_theme": "pulse_strife", "text_key": "chron_strife",
        "icon": "🩸", "importance": 2,
        "strength": (-6, -2), "momentum": (-3, -1),
    },
}

# Per-beat chance a low-honour house fractures instead of taking a normal beat
# (when the Director still allows a major). Rare by design — the demonic Abyssal
# Depths is the only house whose honour clears the gate.
WORLD_PULSE_STRIFE_CHANCE = float(os.getenv("WORLD_PULSE_STRIFE_CHANCE", "0.12"))

# Stable iteration order (mirrors the prompt's listing) for deterministic argmax
# tie-breaking.
PULSE_ACTION_ORDER: tuple[str, ...] = (
    "recruit", "fortify", "claim_node", "raid_rival", "seek_inheritance", "internal_strife",
)
MINOR_ACTIONS: tuple[str, ...] = tuple(k for k in PULSE_ACTION_ORDER if not PULSE_ACTIONS[k]["major"])


def action_icon(action: str | None) -> str:
    return PULSE_ACTIONS.get(action or "", {}).get("icon", "📜")


def action_label_key(action: str | None) -> str:
    """i18n key for a house's last-action label (server-resolved disclosure)."""
    return f"wpulse_action_{action}" if action in PULSE_ACTIONS else "wpulse_action_idle"


# ══════════════════════════════════════════════════════════════════════════
# PURE decision layer — no DB, no clock (dry-run-simulable)
# ══════════════════════════════════════════════════════════════════════════

def _available_actions(soul: dict[str, float]) -> list[str]:
    """Actions a house with this soul may consider in the weighted-utility menu.
    SPECIAL actions (internal_strife) are excluded — they fire via a pre-roll."""
    rival = soul.get("_has_rival", True)
    out: list[str] = []
    for key in PULSE_ACTION_ORDER:
        spec = PULSE_ACTIONS[key]
        if spec.get("special"):
            continue
        if spec.get("needs_rival") and not rival:
            continue
        out.append(key)
    return out


# ══════════════════════════════════════════════════════════════════════════
# FASE A1 — AS CASAS OLHAM PARA A PRÓPRIA SITUAÇÃO (pivot 2026-08-11)
#
# `score_actions` pontuava com os 5 escalares de PERSONALIDADE e mais nada. A
# `strength` e o `momentum` acumulavam entre batimentos e `soul_from_row` nunca
# os lia: uma casa acabada de ser saqueada decidia exatamente igual a uma casa
# intacta. É a razão de raiz de as cadeias de consequência morrerem em 2-4
# saltos — nada realimentava o que podia acontecer a seguir.
#
# Os pesos são deliberadamente pequenos: a personalidade continua a MANDAR (uma
# casa ambiciosa continua ambiciosa), o contexto só INCLINA. Um mundo onde a
# situação domina a personalidade é tão previsível quanto um onde ela não conta.
# ══════════════════════════════════════════════════════════════════════════

# ⚠️ FORÇA É RELATIVA, NUNCA ABSOLUTA. A primeira versão desta camada usava
# limiares fixos (80 / 160) — e a simulação de 200 batimentos
# (`tools/motor_fase_a_sim.py`) mostrou porque é que isso é um defeito que só
# aparece tarde: `strength` é um ACUMULADOR SEM TETO. Ao fim de ~50 dias de
# mundo todas as casas passam dos 230, logo o travão do "fraco" nunca engatava
# e o bônus do "forte" disparava sempre — o contexto virava uma constante. Estes
# limiares são frações da MEDIANA do mundo: auto-normalizam para sempre.
PULSE_WEAK_RATIO = float(os.getenv("PULSE_WEAK_RATIO", "0.75"))
PULSE_STRONG_RATIO = float(os.getenv("PULSE_STRONG_RATIO", "1.25"))
PULSE_CTX_WEIGHT = float(os.getenv("PULSE_CTX_WEIGHT", "0.6"))


def _ctx_bias(action: str, ctx: dict) -> float:
    """Quanto a SITUAÇÃO da casa inclina esta ação. Pura, sem I/O.

    ctx = {strength, momentum, home_state, recent_losses, world_strength}.
    Devolve 0.0 para um ctx vazio — que é o que torna esta camada
    byte-idêntica à anterior quando ninguém a alimenta (o simulador antigo, os
    testes, e qualquer chamador que não conheça a Fase A).

    ⚠️ A VINGANÇA INCLINA, NUNCA ARRASTA. A 1ª versão dava a `raid_rival` um
    bônus por saque sofrido MAIOR do que o que dava a `fortify` — e a simulação
    provou o resultado: duas casas entravam num pingue-pongue de represália que
    NUNCA parava (cadeia de 59 elos entre o mesmo par, e o mundo ficou MAIS
    previsível do que antes da onda). É a convergência que a Fase E do documento
    nomeia como o inimigo. Agora quem apanha, sobretudo se FECHA — e revida às
    vezes. O ódio guardado (`grudges`) escolhe o ALVO; não decide a agenda.
    """
    if not ctx:
        return 0.0
    b = 0.0
    strength = float(ctx.get("strength") or 0.0)
    momentum = float(ctx.get("momentum") or 0.0)
    home = str(ctx.get("home_state") or "")
    losses = int(ctx.get("recent_losses") or 0)
    ref = float(ctx.get("world_strength") or 0.0)
    grudge = int(ctx.get("grudge_max") or 0)

    # Sem referência do mundo, a força não opina (melhor mudo do que errado).
    weak = bool(ref) and strength < ref * PULSE_WEAK_RATIO
    strong = bool(ref) and strength > ref * PULSE_STRONG_RATIO

    if action == "fortify":
        # Quem está fraco fecha as portas. Quem está sob cerco, mais ainda.
        if weak:
            b += 1.0
        if home in ("sitiada", "ocupada"):
            b += 1.5
        elif home == "tensa":
            b += 0.5
        if losses:
            b += min(1.8, 0.7 * losses)     # levar pancada fecha o portão
    elif action == "raid_rival":
        if weak:
            b -= 1.2
        if strong and momentum > 0:
            b += 0.8
        if home in ("sitiada", "ocupada"):
            b -= 1.0          # não se sai de casa com o inimigo ao portão
        # A represália pesa — mas SÓ para quem ainda tem corpo para sair. É esta
        # condição, e não o tamanho do bônus, que quebra o pingue-pongue: quem
        # apanha o suficiente fica `weak` (relativo à mediana do mundo) e passa a
        # fechar o portão em vez de revidar. A espiral morre pela FRAQUEZA, que é
        # como morre na vida real, e não por um número pequeno.
        if losses and not weak:
            b += min(1.0, 0.5 * losses)
        # ⚠️ O RANCOR MOVE A AGENDA, NÃO SÓ O ALVO. A 1ª implementação usou
        # `grudges` apenas para escolher CONTRA QUEM se marchava — e a simulação
        # de 400 batimentos mostrou o preço: 101 das 159 decisões que o contexto
        # mudava eram `→fortify`. Um mundo cuja única realimentação é "esconde-te"
        # AMORTECE consequências em vez de as propagar, e por isso as cadeias
        # morriam em 4 elos e nunca nascia um conflito fora do mapa semeado.
        # O documento pedia isto por escrito: *"score_actions lê grudges e
        # enviesa raid_rival para quem mais lhe deve"*. Uma dívida velha é uma
        # razão para SAIR de casa — e continua travada pela fraqueza acima.
        #
        # ⚠️ E A SEPARAÇÃO É NO TEMPO, NÃO NO PESO. Ligar os dois canais ao mesmo
        # tempo (dor recente E dor lembrada a empurrar para a marcha) devolveu o
        # pingue-pongue: 62 elos entre o MESMO par e as nove casas a convergir
        # para "saquear" (a diferença entre casas caiu 0,427 → 0,214 — nove
        # clones). Com o `not losses`, os dois canais nunca disparam juntos:
        #   · debaixo de fogo AGORA  → o portão fecha (o bloco `fortify` acima);
        #   · a dívida é ANTIGA      → sai-se de casa para a cobrar.
        # É o que faz uma rixa ter CAPÍTULOS — trocam-se golpes, ambos recolhem,
        # e semanas depois alguém se lembra — em vez de ser um dado rolado a
        # dobrar até o mundo inteiro ser a mesma briga.
        if grudge and not weak and not losses:
            b += min(1.2, grudge / float(max(1, GRUDGE_MAX)) * 1.2)
    elif action == "claim_node":
        if strong and momentum > 0:
            b += 0.8
        if weak:
            b -= 0.8
        if home in ("sitiada", "ocupada"):
            b -= 1.0
    elif action == "recruit":
        # Perder gente é a razão mais antiga do mundo para ir buscar mais.
        if weak:
            b += 0.8
        if momentum < 0:
            b += 0.4
        if losses:
            b += min(0.8, 0.4 * losses)
    elif action == "seek_inheritance":
        if home == "festival":
            b += 0.3
        if weak:
            b -= 0.3
    return b * PULSE_CTX_WEIGHT


def score_actions(soul: dict[str, float], rng: random.Random,
                  ctx: dict | None = None) -> dict[str, float]:
    """Weighted-utility score per AVAILABLE action: Σ(weight × soul scalar) + base
    + o viés da SITUAÇÃO (Fase A1) + a mesma noise semeada de sempre.

    Pure — same (soul, ctx, rng state) ⇒ same scores.

    ⚠️ `ctx` é OPCIONAL e o default (None) devolve exatamente os scores de antes
    desta onda: é o que mantém o simulador antigo e as suites verdes, e o que faz
    a camada nova ser uma adição e não uma reescrita.
    ⚠️ A noise é sorteada DEPOIS do viés e na MESMA ordem de sempre — a sequência
    de draws do rng não muda, logo um replay do mesmo epoch continua comparável.
    """
    scores: dict[str, float] = {}
    for key in _available_actions(soul):
        util = PULSE_ACTIONS[key]["util"]
        val = float(util.get("base", 0.0))
        for scalar in SECT_SOUL_SCALARS:
            w = util.get(scalar)
            if w:
                val += float(w) * float(soul.get(scalar, 0.5))
        val += _ctx_bias(key, ctx or {})
        val += rng.uniform(0.0, WORLD_PULSE_NOISE)
        scores[key] = val
    return scores


def _argmax(scores: dict[str, float], allowed: set[str] | None = None) -> str | None:
    """Highest-scoring action (restricted to ``allowed`` if given). Ties broken by
    PULSE_ACTION_ORDER for determinism."""
    best: str | None = None
    best_val = float("-inf")
    for key in PULSE_ACTION_ORDER:
        if key not in scores:
            continue
        if allowed is not None and key not in allowed:
            continue
        if scores[key] > best_val:
            best_val = scores[key]
            best = key
    return best


def pick_action(soul: dict[str, float], rng: random.Random, *, major_allowed: bool,
                ctx: dict | None = None) -> str:
    """Choose a house's beat. A rare blood-feud pre-roll fires first for a
    low-honour house (only when the Director still allows a major). Otherwise the
    weighted-utility argmax wins — and if that top pick is MAJOR but the Director
    budget / cooldown forbid a major this beat, fall back to the best MINOR action
    (recruit/fortify) — never a dead beat. Pure (deterministic for a given rng)."""
    # Rare internal_strife pre-roll (consumes one rng draw — deterministic).
    strife = PULSE_ACTIONS["internal_strife"]
    honor = float(soul.get("honor", 0.5))
    strife_roll = rng.random()
    if major_allowed and honor < strife["honor_below"] and strife_roll < WORLD_PULSE_STRIFE_CHANCE:
        return "internal_strife"

    scores = score_actions(soul, rng, ctx)
    best = _argmax(scores)
    if best is None:
        return "fortify"
    if PULSE_ACTIONS[best]["major"] and not major_allowed:
        minor = _argmax(scores, allowed=set(MINOR_ACTIONS))
        return minor or "fortify"
    return best


def action_effects(action: str, rng: random.Random) -> dict[str, int]:
    """Seeded INT effect of a beat: {strength, momentum, rival_strength,
    rival_momentum}. Pure."""
    spec = PULSE_ACTIONS.get(action) or {}
    def _roll(field: str) -> int:
        lo, hi = spec.get(field, (0, 0))
        return rng.randint(int(lo), int(hi)) if hi >= lo else 0
    return {
        "strength": _roll("strength"),
        "momentum": _roll("momentum"),
        "rival_strength": _roll("rival_strength"),
        "rival_momentum": _roll("rival_momentum"),
    }


# ══════════════════════════════════════════════════════════════════════════
# FASE A3 — RANCOR QUE NASCE NO JOGO (pivot 2026-08-11, Mig 139)
#
# A rivalidade era ESTÁTICA (`WORLD_SECT_META[...]["rival"]` → `rival_id`,
# semeado uma vez). Ninguém guardava ódio por um saque sofrido, e as vinganças
# do mundo eram sempre as mesmas duas casas. `grudges` é o primeiro estado que o
# mundo escreve sobre si próprio: quem me deve, e quanto.
# ══════════════════════════════════════════════════════════════════════════

GRUDGE_ON_RAID = int(os.getenv("GRUDGE_ON_RAID", "25"))
GRUDGE_DECAY = int(os.getenv("GRUDGE_DECAY", "1"))
GRUDGE_MAX = int(os.getenv("GRUDGE_MAX", "100"))
# A partir de que rancor a casa deixa de atacar o rival de sempre e vai atrás de
# quem lhe deve. Alto de propósito: a vingança tem de ser CONQUISTADA, senão o
# rival canónico deixa de significar coisa nenhuma.
#
# ⚠️ A CALIBRAÇÃO É CONTRA O DECAY, não um número bonito. Cada saque vale +25 e
# cada batimento da casa esquece 1: um único saque some em 25 batimentos (~6
# dias). Com o limiar em 35, é preciso levar DOIS saques da mesma casa dentro de
# ~10 batimentos para a memória vencer o rival de sempre — o que exige uma
# perseguição, e não um azar. Com 40/20 (a 1ª calibração) o limiar nunca era
# alcançado por um agressor NÃO-canónico e as vinganças emergentes davam ZERO na
# simulação de 200 batimentos.
GRUDGE_TARGET_MIN = int(os.getenv("GRUDGE_TARGET_MIN", "35"))


def read_grudges(row) -> dict[str, int]:
    """Os rancores de uma casa, normalizados. Fail-safe → {}."""
    try:
        raw = getattr(row, "grudges", None)
        if not isinstance(raw, dict):
            return {}
        return {str(k): int(v) for k, v in raw.items() if int(v or 0) > 0}
    except Exception:
        return {}


def bump_grudge(row, offender_id: str, amount: int = GRUDGE_ON_RAID) -> dict[str, int]:
    """Regista que `offender_id` fez mal a esta casa. Devolve o mapa NOVO.

    ⚠️ Dict NOVO, nunca mutação in-place: não há `MutableDict` neste projeto, e
    mutar um JSONB no lugar é uma escrita que o SQLAlchemy não vê — o mesmo
    contrato de `jianghu_engine._set_loadout`."""
    g = dict(read_grudges(row))
    if not offender_id:
        return g
    g[str(offender_id)] = min(GRUDGE_MAX, int(g.get(str(offender_id), 0)) + int(amount))
    return g


def decay_grudges(row) -> dict[str, int]:
    """Um batimento de esquecimento. Ódio eterno é tão morto quanto ódio nenhum:
    sem decay, ao fim de um mês todas as casas odeiam todas com o mesmo teto e a
    escolha de alvo volta a ser constante — o oposto do que esta fase serve."""
    g = read_grudges(row)
    out = {k: v - GRUDGE_DECAY for k, v in g.items() if (v - GRUDGE_DECAY) > 0}
    return out


def grudge_target(row, valid_ids) -> str | None:
    """Contra QUEM esta casa marcha. O rancor só vence o rival canónico quando
    passa de `GRUDGE_TARGET_MIN`; empate desfeito pelo id, para ser determinístico.

    Devolve None quando ninguém chega ao limiar — e aí o `rival_id` de sempre
    manda, exatamente como antes desta onda."""
    g = read_grudges(row)
    if not g:
        return None
    ok = [(v, k) for k, v in g.items()
          if v >= GRUDGE_TARGET_MIN and k in valid_ids and k != getattr(row, "id", None)]
    if not ok:
        return None
    ok.sort(key=lambda t: (-t[0], t[1]))
    return ok[0][1]


def soul_from_row(row: WorldSect) -> dict[str, float]:
    """Read a house's live soul (scalars + rival presence) off a world_sects row,
    falling back to the canonical WORLD_SECT_SOUL if a scalar is somehow unset."""
    canon = get_sect_soul(row.id)
    soul: dict[str, float] = {}
    for scalar in SECT_SOUL_SCALARS:
        v = getattr(row, scalar, None)
        soul[scalar] = float(v) if v is not None else float(canon[scalar])
    soul["_has_rival"] = bool(is_valid_sect(row.rival_id))
    return soul


# ══════════════════════════════════════════════════════════════════════════
# Chronicle — append + render + feed (server-resolved per reader language)
# ══════════════════════════════════════════════════════════════════════════

async def emit_chronicle(
    session,
    *,
    event_type: str,
    text_key: str,
    params: dict | None = None,
    continent_key: str | None = None,
    sect_id: str | None = None,
    importance: int = 1,
    now: datetime | None = None,
) -> WorldChronicle | None:
    """Append one line to the world chronicle. Best-effort, never raises. Does NOT
    commit (the pulse beat / caller owns the commit). Params stay
    language-neutral — {sect}/{rival}/{continent} are merged at render time."""
    try:
        row = WorldChronicle(
            ts=now or datetime.now(timezone.utc),
            continent_key=continent_key if is_valid_continent(continent_key) else None,
            sect_id=sect_id if is_valid_sect(sect_id) else None,
            event_type=event_type,
            text_key=text_key,
            params=dict(params or {}),
            importance=int(importance),
        )
        session.add(row)
        await session.flush()
        return row
    except Exception:
        logger.exception("emit_chronicle failed event=%s", event_type)
        return None


def _chronicle_localized_names(row: WorldChronicle, lang: str) -> dict[str, str]:
    """Resolve {sect}/{rival}/{continent}/{to_continent} for THIS reader's language.

    MV-8: a marcha ("{npc} deixou {continent} e marcha rumo a {to_continent}")
    precisa de um SEGUNDO continente. Sem este ramo o jogador leria
    `{to_continent}` cru na cara — `core.i18n.t` engole o KeyError e devolve o
    template. Nomes PRÓPRIOS ({npc}, {other}) são language-neutral e viajam em
    `params` (precedente `params={"rival": npc.name}` do MV-6); só as CHAVES de
    lore são resolvidas por leitor.
    """
    from core.i18n import t as i18n_t
    out: dict[str, str] = {}
    if is_valid_sect(row.sect_id):
        out["sect"] = i18n_t(lang, WORLD_SECT_META[row.sect_id]["name_key"])
    rival_id = (row.params or {}).get("rival_sect_id")
    if is_valid_sect(rival_id):
        out["rival"] = i18n_t(lang, WORLD_SECT_META[rival_id]["name_key"])
    if is_valid_continent(row.continent_key):
        out["continent"] = i18n_t(lang, CONTINENT_META[row.continent_key]["name_key"])
    to_cont = (row.params or {}).get("to_continent_key")
    if is_valid_continent(to_cont):
        out["to_continent"] = i18n_t(lang, CONTINENT_META[to_cont]["name_key"])
    # MV-9 — {city} e {encargo}: a linha "Correu voz de {city}: agora pedem
    # {encargo}". SEM este ramo o jogador lê `{city}` CRU na cara — `core.i18n.t`
    # engole o KeyError e devolve o template. Espelha literalmente o
    # `{to_continent}` do MV-8, três linhas acima. As duas chaves são de LORE
    # (resolvidas por leitor); nomes próprios continuam a viajar em `params`.
    try:
        from core.city_engine import CITY_META
        city_k = (row.params or {}).get("city_key")
        if city_k in CITY_META:
            out["city"] = i18n_t(lang, CITY_META[city_k]["name_key"])
        enc_k = (row.params or {}).get("encargo_key")
        if enc_k:
            out["encargo"] = i18n_t(lang, f"sty_{enc_k}_name")
    except Exception:
        logger.debug("chronicle city names failed", exc_info=True)
    return out


def render_chronicle_row(row: WorldChronicle, lang: str) -> dict[str, Any]:
    """Project a chronicle row to a ready feed entry (server-resolved text)."""
    from core.i18n import t as i18n_t
    params = dict(row.params or {})
    params.update(_chronicle_localized_names(row, lang))
    ts_ms = int(row.ts.timestamp() * 1000) if row.ts else None
    return {
        "id": int(row.id),
        "event_type": row.event_type,
        "icon": action_icon(row.event_type),
        "text": i18n_t(lang, row.text_key, **params),
        "importance": int(row.importance or 1),
        "sect_id": row.sect_id,
        "sect_emoji": WORLD_SECT_META[row.sect_id]["emoji"] if is_valid_sect(row.sect_id) else None,
        "continent_key": row.continent_key,
        "ts_ms": ts_ms,
    }


async def list_recent_chronicle(session, *, limit: int = 30, lang: str = "pt",
                                continent: str | None = None,
                                viewer_continent: str | None = None) -> list[dict[str, Any]]:
    """Recent chronicle lines projected for the feed (newest first, capped).

    When ``continent`` is given (plaza strip) the feed is scoped to that continent
    OR global lines (``continent_key`` IS NULL) — mirrors list_recent_whispers.

    MV-8 — ``viewer_continent`` (gated ``jianghu``) turns the feed into a
    RUMOUR instead of a scoreboard. The MV-3 latency never touched this table
    (``rumor_views`` reads ``world_events``), so a line landed instantly and
    identically for someone on the other side of the world. *No jiānghú,
    notícia que chega igual e na hora não é notícia — é placar.* We reuse the
    PURE ``rumor_delay_hours`` (``min(dist,2)×6h``) and hide lines from OTHER
    continents until the news would plausibly have travelled.

    Same gate buys the second dividend: ``importance`` is written by 20 call
    sites and read by NOBODY — with a small limit (the 4-line plaza strip) the
    feed sorts by ``(importance DESC, ts DESC)`` so one loud beat can't be
    pushed out by routine noise.

    Flag OFF ⇒ caller passes nothing ⇒ **byte-identical** to before.
    """
    try:
        cap = min(int(limit), CHRONICLE_FEED_CAP)
        stmt = select(WorldChronicle)
        if continent:
            stmt = stmt.where(
                (WorldChronicle.continent_key == continent)
                | (WorldChronicle.continent_key.is_(None))
            )
        latency_on = False
        if viewer_continent:
            try:
                from core.jianghu_engine import jianghu_on
                latency_on = bool(jianghu_on())
            except Exception:
                latency_on = False
        if not latency_on:
            rows = (await session.execute(
                stmt.order_by(WorldChronicle.ts.desc()).limit(cap)
            )).scalars().all()
            return [render_chronicle_row(r, lang) for r in rows]

        # ⚠️ A busca é SEMPRE por RECÊNCIA. Ordenar por `importance` no SQL
        # fazia o LIMIT escolher as linhas mais altas de TODA a história — e
        # `world_chronicle` é append-only, sem poda nenhuma. O efeito medido no
        # papel: em poucos dias existem mais de 50 linhas de importância ≥2, e
        # aí o feed congela num hall da fama (uma ocupação de três semanas
        # atrás fixa no topo, com "há 21 dias") enquanto TODA linha de
        # importância 1 fica inalcançável para sempre — inclusive o
        # `jh_chron_sumiu`, que existe só para um plano nunca acabar em
        # silêncio. O feed pararia de se mover: o oposto exato do que a onda
        # inteira serve.
        #
        # Over-fetch por recência (descartar linhas encolhe o resultado abaixo
        # do `limit`, e a tira da praça mostra 4) → filtra a latência → e só
        # ENTÃO a importância decide o que CORTAR do excedente. O que sai é
        # sempre cronológico: a tela imprime `timeAgo`.
        from core.region_state_engine import rumor_delay_hours
        now = datetime.now(timezone.utc)
        rows = (await session.execute(
            stmt.order_by(WorldChronicle.ts.desc())
            .limit(min(CHRONICLE_FEED_CAP, max(cap * 4, cap)))
        )).scalars().all()
        kept: list[Any] = []
        for r in rows:
            row_cont = r.continent_key
            if row_cont and row_cont != viewer_continent:
                ts = r.ts
                if ts is not None and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                delay = rumor_delay_hours(viewer_continent, row_cont)
                if ts is not None and delay > 0 and \
                        (now - ts) < timedelta(hours=delay):
                    continue   # a notícia ainda está na estrada
            kept.append(r)
        if len(kept) > cap:
            # A tira da praça mostra 4 de ~44 linhas/dia: aqui a `importance`
            # finalmente serve para algo (era escrita por 20 call sites e lida
            # por NINGUÉM) — escolhe QUEM fica, nunca QUEM é buscado.
            kept.sort(key=lambda r: (-int(r.importance or 1),
                                     -(r.ts.timestamp() if r.ts else 0)))
            kept = kept[:cap]
            kept.sort(key=lambda r: -(r.ts.timestamp() if r.ts else 0))
        return [render_chronicle_row(r, lang) for r in kept]
    except Exception:
        logger.exception("list_recent_chronicle failed")
        return []


# ══════════════════════════════════════════════════════════════════════════
# Dynamic-state read — "the house is alive" disclosure for directory / plaza
# ══════════════════════════════════════════════════════════════════════════

async def get_sect_pulse_map(session, lang: str = "pt") -> dict[str, dict[str, Any]]:
    """Per-house dynamic state for the UI: {sect_id: {strength, momentum,
    last_action, last_action_key, last_action_label, last_action_at_ms,
    last_pulse_at_ms}}. The last-action label is resolved server-side so chat AND
    mini-app just display the string (Lei §1 — the house's life is legible)."""
    from core.i18n import t as i18n_t
    out: dict[str, dict[str, Any]] = {}
    try:
        rows = (await session.execute(select(WorldSect))).scalars().all()
        for r in rows:
            la = r.last_action
            out[r.id] = {
                "strength": int(r.strength or 0),
                "momentum": int(r.momentum or 0),
                "last_action": la,
                "last_action_key": action_label_key(la),
                "last_action_label": i18n_t(lang, action_label_key(la)),
                "last_action_icon": action_icon(la),
                "last_action_at_ms": int(r.last_action_at.timestamp() * 1000) if r.last_action_at else None,
                "last_pulse_at_ms": int(r.last_pulse_at.timestamp() * 1000) if r.last_pulse_at else None,
            }
    except Exception:
        logger.exception("get_sect_pulse_map failed")
    return out


# ══════════════════════════════════════════════════════════════════════════
# The heartbeat — deterministic, idempotent, best-effort per house
# ══════════════════════════════════════════════════════════════════════════

def _tick_epoch(now: datetime, interval_seconds: float) -> int:
    return int(now.timestamp() // max(1.0, interval_seconds))


async def run_world_pulse(session, *, now: datetime | None = None) -> dict[str, Any]:
    """One world heartbeat. Owns its commit. Idempotent (per-sect last_pulse_at
    guard) + best-effort (a SAVEPOINT per house). Returns a summary for the log.

    Sequence per house (seeded order so the Director budget isn't always grabbed
    by the same house):
      1) skip if pulsed within ~half the interval (coalesced double-fire guard);
      2) decide an action (weighted-utility + Director cap + seeded RNG);
      3) row-lock + apply the actor effect, set last_action/last_pulse_at;
      4) write a chronicle line; loud beats fire a whisper; a raid posts a bounty;
      5) rival deltas are deferred to atomic UPDATEs after the loop (lock-safe).
    """
    now = now or datetime.now(timezone.utc)
    interval_seconds = WORLD_PULSE_INTERVAL_HOURS * 3600.0
    min_gap = interval_seconds * 0.5  # a fire within this of the last ⇒ idempotent skip
    tick_epoch = _tick_epoch(now, interval_seconds)
    major_cooldown = timedelta(hours=WORLD_PULSE_MAJOR_COOLDOWN_HOURS)

    summary = {"pulsed": 0, "skipped": 0, "chronicle": 0, "whispers": 0,
               "bounties": 0, "actions": {}, "tick_epoch": tick_epoch}
    rival_deltas: dict[str, dict[str, int]] = {}
    major_budget = WORLD_PULSE_MAX_MAJOR_PER_TICK

    # Seeded order over the 9 houses (reproducible within a tick).
    order = list(WORLD_SECT_KEYS)
    random.Random(f"world_pulse_order:{tick_epoch}").shuffle(order)

    # ── FASE A1 — o CONTEXTO do mundo, lido UMA vez para as 9 casas ──────────
    # Duas leituras baratas antes do laço (nunca dentro): o estado das regiões
    # (gated `estados_regionais`; OFF ⇒ mapa base, ZERO query) e quem levou
    # saques recentes (uma varredura da Crônica pelo índice de `ts`).
    world_states: dict[str, str] = {}
    recent_losses: dict[str, int] = {}
    world_strength: float = 0.0
    try:
        _st = [int(s or 0) for s in (await session.execute(
            select(WorldSect.strength))).scalars().all()]
        if _st:
            _st.sort()
            world_strength = float(_st[len(_st) // 2])   # mediana
    except Exception:
        logger.debug("world_pulse: strength median unavailable", exc_info=True)
    try:
        from core.region_state_engine import get_states_map
        world_states = await get_states_map(session) or {}
    except Exception:
        logger.debug("world_pulse: region states unavailable", exc_info=True)
    try:
        since = now - timedelta(hours=WORLD_PULSE_INTERVAL_HOURS * 4)
        hits = (await session.execute(
            select(WorldChronicle.params).where(
                WorldChronicle.event_type == "raid_rival",
                WorldChronicle.ts >= since,
            )
        )).scalars().all()
        for p in hits:
            vic = (p or {}).get("rival_sect_id")
            if vic:
                recent_losses[str(vic)] = recent_losses.get(str(vic), 0) + 1
    except Exception:
        logger.debug("world_pulse: recent losses unavailable", exc_info=True)

    from core.heavens_whispers_engine import emit_whisper
    from core.bounty_engine import post_bounty_on_npc

    for sect_id in order:
        try:
            async with session.begin_nested():
                row = (await session.execute(
                    select(WorldSect).where(WorldSect.id == sect_id)
                    .with_for_update().execution_options(populate_existing=True)
                )).scalar_one_or_none()
                if row is None:
                    continue

                # 1) Idempotency guard — already pulsed this window.
                if row.last_pulse_at is not None:
                    gap = (now - row.last_pulse_at).total_seconds()
                    if gap < min_gap:
                        summary["skipped"] += 1
                        continue

                # 2) Decide (Director: budget + per-house major cooldown).
                soul = soul_from_row(row)
                rng = random.Random(f"world_pulse:{sect_id}:{tick_epoch}")
                on_cooldown = (
                    row.last_action is not None
                    and PULSE_ACTIONS.get(row.last_action, {}).get("major")
                    and row.last_action_at is not None
                    and (now - row.last_action_at) < major_cooldown
                )
                major_allowed = (major_budget > 0) and not on_cooldown
                # FASE A1 — a casa olha para si própria antes de decidir.
                ctx = {
                    "strength": int(row.strength or 0),
                    "momentum": int(row.momentum or 0),
                    "home_state": world_states.get(row.continent_key or ""),
                    "recent_losses": int(recent_losses.get(sect_id, 0)),
                    # A régua do "fraco"/"forte" é o MUNDO, nunca um número fixo.
                    "world_strength": world_strength,
                    # A3 — a maior dívida por cobrar move a agenda, não só o alvo.
                    "grudge_max": max(read_grudges(row).values(), default=0),
                }
                action = pick_action(soul, rng, major_allowed=major_allowed, ctx=ctx)
                spec = PULSE_ACTIONS[action]
                is_major = bool(spec["major"])

                # 3) Apply the actor effect (row-locked mutation).
                eff = action_effects(action, rng)
                row.strength = max(0, int(row.strength or 0) + eff["strength"])
                row.momentum = max(_MOMENTUM_MIN, min(_MOMENTUM_MAX,
                                                       int(row.momentum or 0) + eff["momentum"]))
                row.last_action = action
                row.last_action_at = now
                row.last_pulse_at = now

                # FASE A3 — o rancor decai a cada batimento (esquecer faz parte).
                row.grudges = decay_grudges(row)

                # FASE A3 — CONTRA QUEM se marcha. O rival semeado continua a ser
                # o default; só um rancor que passou de `GRUDGE_TARGET_MIN` o
                # destrona — a vingança tem de ser conquistada, senão o rival
                # canónico deixaria de significar coisa nenhuma.
                rival_id = None
                if action == "raid_rival":
                    rival_id = grudge_target(row, set(WORLD_SECT_KEYS)) or row.rival_id
                continent = row.continent_key
                chron_params: dict[str, Any] = {}
                if rival_id and is_valid_sect(rival_id):
                    chron_params["rival_sect_id"] = rival_id  # the chronicle text needs {rival}

                # 4) Chronicle (always) + whisper (loud beats) + bounty (raid).
                crow = await emit_chronicle(
                    session, event_type=action, text_key=spec["text_key"],
                    params=chron_params, continent_key=continent, sect_id=sect_id,
                    importance=int(spec["importance"]), now=now,
                )
                if crow is not None:
                    summary["chronicle"] += 1

                if is_major and spec.get("whisper_theme"):
                    w = await emit_whisper(
                        session, spec["whisper_theme"],
                        continent_key=continent if is_valid_continent(continent) else None,
                        sect_id=sect_id,
                    )
                    if w is not None:
                        summary["whispers"] += 1

                if action == "raid_rival":
                    b = await post_bounty_on_npc(
                        session, rival_sect_id=rival_id, continent_key=continent,
                    )
                    if b is not None:
                        summary["bounties"] += 1

                # TEC-4 — Legacy Caves: um beat seek_inheritance pode fazer a
                # tumba despertar VISITÁVEL (flag `legacy_caves`; OFF ⇒ retorno
                # imediato sem query). SAVEPOINT PRÓPRIO: um erro de DB aqui
                # rola back só a gruta — sem ele, a exceção engolida deixaria o
                # savepoint do BEAT envenenado e o exit do with derrubaria o
                # beat inteiro (chronicle/whisper/strength perdidos).
                if action == "seek_inheritance":
                    try:
                        from core.legacy_cave_engine import maybe_open_cave
                        async with session.begin_nested():
                            cave = await maybe_open_cave(
                                session, sect_id=sect_id, continent_key=continent,
                                rng=rng, now=now,
                            )
                        if cave is not None:
                            summary["caves"] = summary.get("caves", 0) + 1
                    except Exception:
                        logger.exception("world_pulse: legacy cave hook failed (sect=%s)", sect_id)

                # 5) Commit the beat's BOOK-KEEPING only after every side effect
                # above succeeded. The Director budget decrement + the rival-delta
                # accumulation live HERE (the tail of the SAVEPOINT block) so that
                # if anything above raised — rolling the beat's DB writes back —
                # the in-memory accumulators were NEVER touched for this beat
                # (review: no double-applied rival delta, no wasted major budget).
                if is_major:
                    major_budget -= 1
                if rival_id and is_valid_sect(rival_id):
                    rd = rival_deltas.setdefault(rival_id, {"strength": 0, "momentum": 0,
                                                            "by": []})
                    rd["strength"] += eff["rival_strength"]
                    rd["momentum"] += eff["rival_momentum"]
                    rd.setdefault("by", []).append(sect_id)   # FASE A3 — quem bateu

                summary["pulsed"] += 1
                summary["actions"][action] = summary["actions"].get(action, 0) + 1
        except Exception:
            logger.exception("world_pulse: house %s beat failed (skipped)", sect_id)
            continue

    # 6) Apply deferred rival deltas — each in its OWN SAVEPOINT so a single
    # failed UPDATE can neither poison the outer transaction nor let the final
    # commit persist an ASYMMETRIC world (review): it rolls back only itself.
    for rival_id, rd in rival_deltas.items():
        try:
            async with session.begin_nested():
                await session.execute(
                    update(WorldSect).where(WorldSect.id == rival_id).values(
                        strength=func.greatest(0, WorldSect.strength + int(rd["strength"])),
                        momentum=func.greatest(
                            _MOMENTUM_MIN,
                            func.least(_MOMENTUM_MAX, WorldSect.momentum + int(rd["momentum"])),
                        ),
                    )
                )
                # FASE A3 — A VÍTIMA GUARDA O ÓDIO. É aqui, e não no beat do
                # atacante, porque é aqui que se sabe quem levou. Carrega-se a
                # row (o UPDATE acima é cego de propósito, para não travar) só
                # para reescrever o JSONB: dict NOVO, nunca mutação in-place.
                for offender in rd.get("by", ()):  # noqa: B007
                    vrow = (await session.execute(
                        select(WorldSect).where(WorldSect.id == rival_id)
                        .with_for_update().execution_options(populate_existing=True)
                    )).scalar_one_or_none()
                    if vrow is not None:
                        vrow.grudges = bump_grudge(vrow, offender)
        except Exception:
            logger.debug("world_pulse: rival delta failed for %s", rival_id, exc_info=True)

    try:
        await session.commit()
    except Exception:
        logger.exception("world_pulse: commit failed")
        try:
            await session.rollback()
        except Exception:
            pass
    return summary
