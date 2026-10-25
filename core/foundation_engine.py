import random
from database.models import Player

# v14.4 D-1c: "sacred" is the apex tier above Perfect, +25% over Perfect's
# base mult. Triggered by Eternal Foundation Pill at Heavenly grade when
# the player's foundation is already Perfect. Stored as a plain string in
# `players.foundation_quality VARCHAR(16)` — no SQL enum to alter.
FOUNDATION_QUALITIES = {
    "low":     {"stat_mult": 1.0,  "label_key": "foundation_quality_low",     "emoji": "🪨"},
    "medium":  {"stat_mult": 1.15, "label_key": "foundation_quality_medium",  "emoji": "☯️"},
    "high":    {"stat_mult": 1.35, "label_key": "foundation_quality_high",    "emoji": "⚡"},
    "perfect": {"stat_mult": 1.6,  "label_key": "foundation_quality_perfect", "emoji": "🌸"},
    "sacred":  {"stat_mult": 2.0,  "label_key": "foundation_quality_sacred",  "emoji": "🌌"},
}

# Foundation reroll outcome tables, used by D-1b (Quebrar a Fundação ritual)
# and D-1c (Eternal Foundation Pill). Each entry is a list of (quality, weight)
# tuples — weights sum to 100. Sacred is reserved for the pill's special
# branch and is NEVER in these tables.
RITUAL_REROLL_TABLES: dict[int, list[tuple[str, float]]] = {
    3: [("perfect", 70.0), ("high", 25.0), ("medium",  5.0)],
    2: [("perfect", 30.0), ("high", 50.0), ("medium", 20.0)],
    1: [("perfect",  5.0), ("high", 35.0), ("medium", 50.0), ("low", 10.0)],
    0: [("low", 100.0)],  # 0/3 = public failure, Wuxia humiliation
}

PILL_REROLL_TABLES: dict[str, list[tuple[str, float]]] = {
    "heavenly": [("perfect", 90.0), ("high", 10.0)],
    "divine":   [("perfect", 70.0), ("high", 25.0), ("medium",  5.0)],
    "perfect":  [("perfect", 50.0), ("high", 40.0), ("medium", 10.0)],
    "normal":   [("perfect", 30.0), ("high", 50.0), ("medium", 20.0)],
}


def roll_from_table(table: list[tuple[str, float]]) -> str:
    """Weighted roll from a [(quality, weight), ...] table. Caller controls input."""
    qualities = [q for q, _ in table]
    weights = [w for _, w in table]
    return random.choices(qualities, weights=weights, k=1)[0]


def foundation_pill_block_reason(current_quality: str | None, effect_type: str) -> str | None:
    """Review adversarial 03/08 — motivo pelo qual uma pílula de fundação seria
    **consumida sem efeito nenhum**. Espelha os no-op returns do próprio
    `apply_pill_effect` (`sacred_protected` / `no_foundation`) para que a recusa
    aconteça ANTES do débito, com zero consumo — o precedente `stat_at_cap`
    aberto pelo mesmo reporter em 30/07 (Lei §1: a recusa diz o porquê e não
    queima o item).

    Devolve o código do motivo, ou None se a pílula tem efeito possível.
    """
    if effect_type not in ("foundation_reroll", "eternal_foundation_reroll"):
        return None
    if current_quality == "sacred":
        # Ambas protegem a Sagrada (id 41 nunca rebaixa; id 34 tem o guard
        # explícito de 2026-07-07) — logo ambas seriam queimadas à toa.
        return "foundation_sacred_locked"
    if effect_type == "foundation_reroll" and not current_quality:
        # A Pílula de Reparo (id 34) exige uma fundação para reparar.
        return "foundation_not_established"
    return None


def foundation_delta(old_quality: str | None, new_quality: str | None) -> dict:
    """Review adversarial 03/08 — o par (antes, depois) de uma reforja, com a
    DIREÇÃO honesta. Sem isto o resultado mais provável (`old == new`, até 70%
    numa divine sobre fundação Perfeita) era anunciado como
    *"🌌 Fundação Reforjada!"* — a queixa original ("no visible changes") com
    uma celebração falsa por cima; e um downgrade PERMANENTE vinha pintado de
    vitória. Fonte única: os mesmos multiplicadores do jogo.
    """
    om = get_foundation_multiplier(old_quality)
    nm = get_foundation_multiplier(new_quality)
    return {
        "old_mult": float(om),
        "new_mult": float(nm),
        "direction": "up" if nm > om else ("down" if nm < om else "same"),
    }


def effective_foundation_quality(current_quality: str | None, realm: int | None) -> str | None:
    """A fundação que o JOGO realmente usa no cálculo — inclui o default COMPAT
    de `core/game_logic.py:158` (*"beta players may have None quality"*): NULL
    em realm >= 2 vale `medium` (×1.15), não 1.0. Sem isto o preview marcaria
    `medium ▲` (ganho) a um jogador para quem `medium` é exatamente o que já
    tem. Realm desconhecido → sem palpite (devolve o valor cru)."""
    if current_quality:
        return current_quality
    if realm is not None and realm >= 2:
        return "medium"
    return None


def foundation_reroll_preview(current_quality: str | None, craft_quality: str,
                              realm: int | None = None) -> dict:
    """QoL-Feedback 03/08 (report [jogador]) — disclosure PRÉ-USO da Pílula da Fundação
    Eterna (D-1c). O jogador criou e usou a pílula e não viu efeito nenhum:
    *"unknown effects… Can it be shown before usage? xxx —> xxx + yyyy?"*.

    Espelha EXATAMENTE o ramo `eternal_foundation_reroll` de
    `core.alchemy_engine.apply_pill_effect` — a mesma ordem de decisões, as
    mesmas tabelas — para que o preview nunca prometa o que o apply não faz
    (precedente `purity_gain`, 29/07: "o número honesto vem do servidor, pela
    MESMA fonte do apply"). NÃO altera o gamble (D-1c é intencional, incl. o
    downgrade); só o torna visível ANTES do consumo.

    Args:
        current_quality: `players.foundation_quality` (None em jogador sem
            fundação estabelecida — COMPAT beta).
        craft_quality: a qualidade do CRAFT da pílula no inventário
            (normal/perfect/divine/heavenly) — a mesma que o apply recebe.

    Returns dict:
        current        — qualidade atual (None se ainda não estabelecida)
        current_mult   — multiplicador de stats atual (1.0 sem fundação)
        locked         — True se a fundação é `sacred` (nunca é rebaixada; a
                         pílula não faz nada)
        sacred_path    — True se ESTE uso desperta a Sagrada (heavenly + perfect)
        can_downgrade  — True se algum resultado possível vale MENOS que a atual
        odds           — [{quality, pct, mult, direction: up|same|down}, ...]
                         ordenado do melhor para o pior
    """
    craft_quality = (craft_quality or "normal").lower()
    # A ÂNCORA das setas é o multiplicador EFETIVO (com o default COMPAT), não o
    # cru — senão um jogador beta sem fundação em realm >= 2 veria tudo verde.
    cur_mult = get_foundation_multiplier(
        effective_foundation_quality(current_quality, realm))

    def _entry(q: str, pct: float) -> dict:
        m = FOUNDATION_QUALITIES.get(q, FOUNDATION_QUALITIES["low"])["stat_mult"]
        return {
            "quality": q,
            "pct": round(float(pct), 2),
            "mult": float(m),
            "direction": "up" if m > cur_mult else ("down" if m < cur_mult else "same"),
        }

    # Ordem idêntica ao apply: (1) sacred nunca é rebaixada; (2) heavenly sobre
    # fundação perfeita é o ÚNICO caminho para Sagrada; (3) senão, a tabela.
    if current_quality == "sacred":
        odds = [_entry("sacred", 100.0)]
        locked, sacred_path = True, False
    elif craft_quality == "heavenly" and current_quality == "perfect":
        odds = [_entry("sacred", 100.0)]
        locked, sacred_path = False, True
    else:
        table = PILL_REROLL_TABLES.get(craft_quality, PILL_REROLL_TABLES["normal"])
        odds = [_entry(q, w) for q, w in table]
        locked, sacred_path = False, False

    odds.sort(key=lambda e: e["mult"], reverse=True)
    return {
        "current": current_quality,
        "current_mult": float(cur_mult),
        "locked": locked,
        "sacred_path": sacred_path,
        "can_downgrade": any(e["direction"] == "down" for e in odds),
        "odds": odds,
    }

FOUNDATION_BASE_THRESHOLDS = {
    "soul": 50,        # base 50 → passes without pills; with pills comfortably
    "perception": 40,  # base 40 → passes without pills; pills give margin
    "luck": 28,        # base 30*1.15=34 → good chance with 60% stat weight
}

def get_foundation_multiplier(quality: str | None) -> float:
    if quality is None:
        return 1.0  # jogadores antigos sem fundação = neutro
    return FOUNDATION_QUALITIES.get(quality, FOUNDATION_QUALITIES["low"])["stat_mult"]

def get_scaled_thresholds(player: Player) -> dict:
    """Return foundation thresholds scaled by prestige level.
    Prestige 0 = 1x, Prestige 1 = 3x, Prestige 2 = 5x, etc."""
    prestige_mult = 1 + getattr(player, "prestige_level", 0) * 2.0
    return {
        "soul": int(FOUNDATION_BASE_THRESHOLDS["soul"] * prestige_mult),
        "perception": int(FOUNDATION_BASE_THRESHOLDS["perception"] * prestige_mult),
        "luck": int(FOUNDATION_BASE_THRESHOLDS["luck"] * prestige_mult),
    }

def calculate_foundation_trial(player: Player, total_stats: dict) -> dict:
    """
    3 provas baseadas nos stats do jogador (incluindo multiplicadores).
    - Prova 1 (Alma): total_soul >= threshold
    - Prova 2 (Percepção): total_perception >= threshold
    - Prova 3 (Sorte): total_luck >= threshold (com componente random)

    Thresholds escalados pelo prestige level do jogador.
    0 provas passadas = low, 1 = medium, 2 = high, 3 = perfect
    """
    scaled = get_scaled_thresholds(player)
    base_soul = scaled["soul"]
    base_perception = scaled["perception"]
    base_luck = scaled["luck"]

    soul_val = total_stats.get("soul_strength", player.soul_strength)
    perc_val = total_stats.get("perception", player.perception)
    luck_val = total_stats.get("luck", player.luck)

    passed = 0
    results = []

    # Prova 1: Alma
    if soul_val >= base_soul:
        passed += 1
        results.append({"trial": "soul", "passed": True})
    else:
        results.append({"trial": "soul", "passed": False})

    # Prova 2: Percepção
    if perc_val >= base_perception:
        passed += 1
        results.append({"trial": "perception", "passed": True})
    else:
        results.append({"trial": "perception", "passed": False})

    # Prova 3: Sorte (60% stat + 40% random, capped at 1.0)
    luck_roll = min((luck_val / base_luck) * 0.6 + random.random() * 0.4, 1.0)
    if luck_roll >= 0.7:
        passed += 1
        results.append({"trial": "luck", "passed": True})
    else:
        results.append({"trial": "luck", "passed": False})

    quality_map = {0: "low", 1: "medium", 2: "high", 3: "perfect"}
    quality = quality_map[passed]

    return {"quality": quality, "results": results, "passed": passed}

