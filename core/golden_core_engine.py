CORE_QUALITIES = {
    "flawed":   {"stat_mult": 1.0,  "label_key": "core_flawed",   "emoji": "💔"},
    "normal":   {"stat_mult": 1.1,  "label_key": "core_normal",   "emoji": "🔵"},
    "superior": {"stat_mult": 1.3,  "label_key": "core_superior", "emoji": "🔮"},
    "perfect":  {"stat_mult": 1.5,  "label_key": "core_perfect",  "emoji": "💎"},
}

# Foundation quality limits the maximum achievable core quality
# BUGFIX 2026-07-07: o tier "sacred" (v14.4 D-1c, migration 085) nunca entrou
# nestes 2 mapas — o .get() caía no fallback e a Fundação SAGRADA dava núcleo
# max "normal" + essência capada em 200 (report [jogador] 06/07, núcleo permanente
# capado injustamente). sacred >= perfect por design.
FOUNDATION_TO_MAX_CORE = {
    "low":     "normal",
    "medium":  "superior",
    "high":    "perfect",
    "perfect": "perfect",
    "sacred":  "perfect",
}
# Máximo de core_essence que o jogador pode acumular, baseado na foundation_quality
FOUNDATION_ESSENCE_CAP = {
    "low": 100,       # Low foundation → max Normal core (precisa de >=50)
    "medium": 200,    # Medium foundation → max Superior core (precisa de >=150)
    "high": 300,      # High/Perfect foundation → max Perfect core (precisa de >=300)
    "perfect": 300,
    "sacred": 300,
}

def get_essence_cap(foundation_quality: str) -> int:
    """Retorna o cap de core_essence baseado na foundation quality."""
    return FOUNDATION_ESSENCE_CAP.get(foundation_quality or "medium", 200)

def add_core_essence(player, amount: int) -> int:
    """Adiciona core_essence respeitando o cap. Retorna quantidade realmente adicionada."""
    if player.core_quality:
        return 0  # Core já formado, não ganha mais
    if player.realm != 2:
        return 0  # Só ganha durante Foundation Establishment (realm 2)
    cap = get_essence_cap(player.foundation_quality)
    old = player.core_essence or 0
    if old >= cap:
        return 0
    actual = min(amount, cap - old)
    player.core_essence = old + actual
    return actual

_QUALITY_ORDER = ["flawed", "normal", "superior", "perfect"]


def calculate_core_quality(player) -> dict:
    """Determine golden core quality based on core_essence and foundation_quality."""
    essence = player.core_essence or 0
    foundation = player.foundation_quality or "medium"
    max_core = FOUNDATION_TO_MAX_CORE.get(foundation, "normal")

    if essence >= 300:
        raw_quality = "perfect"
    elif essence >= 150:
        raw_quality = "superior"
    elif essence >= 50:
        raw_quality = "normal"
    else:
        raw_quality = "flawed"

    max_idx = _QUALITY_ORDER.index(max_core)
    raw_idx = _QUALITY_ORDER.index(raw_quality)
    final_quality = _QUALITY_ORDER[min(raw_idx, max_idx)]

    return {
        "quality": final_quality,
        "essence": essence,
        "was_capped": raw_idx > max_idx,
        "max_allowed": max_core,
        "raw_quality": raw_quality,
    }


def get_core_multiplier(quality: str | None) -> float:
    if quality is None:
        return 1.0
    return CORE_QUALITIES.get(quality, CORE_QUALITIES["flawed"])["stat_mult"]
