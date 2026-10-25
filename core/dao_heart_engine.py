"""Track A (B4) — Dao Heart 道心 ("Coração Dao"): the seat of the cultivator's
WILL, revealed as VISIBLE DATA. The firmness/conviction that holds the soul against
the 心魔 Heart Demon, and the coherence between the Path you walk and what you DO.

Origin of this wave (player feedback, [jogador], 2026-06-23): "good/bad karma is
shallow; it should pass through the Dao Heart / the Will — killing someone who was
about to kill you in a cruel world is NOT the same as murder." This wave delivers
the FIRST VISIBLE step of that: revealing that *firmness + coherence* matter (not
just a good/bad scalar), while the deep model (intention-weighted karma + choice
verbs poupar/aleijar/matar/recrutar + the 心魔劫 Heart-Demon Judgment as a real
proof of firmness) stays Track B (wipe / v16.7 Forbidden Path). Grand Design
Apêndice A / B4 / Gap karma-profundo.

This wave is a **REFRAME** (the Mind Sea / item-6 precedent), NOT a new column. The
fine audit confirmed the Dao Heart already exists IMPLICIT in the Player row:
  * ``Player.path``  — the crystallized alignment (righteous/demonic/rogue, NULL
    pre-R3) — ``core.path_engine``.
  * ``Player.karma`` — the silent moral score [-1000..+1000] — ``core.karma_engine``.
  * the divergence pressure (``_divergence_for_path_and_karma`` + the ±500 Heart
    Demon thresholds) — the 心魔 ALREADY stirs and DMs the player on divergence.
So there is NO migration: this module DERIVES a read-only *firmeza* (conviction)
tier from path + karma + the distance to that existing divergence boundary, and a
*tendency* (the Will's inclination), exactly as items 5/6/B4 revealed root
composition / comprehension / longevity / the Mind Sea.

DISCLOSURE-ONLY (Lei §1, §3, §5). NOTHING here applies a modifier — no number in
combat, cultivation, alchemy, tribulation, or karma changes or newly reads the Dao
Heart. The deep mechanics are explicitly labelled FUTURE: intention-weighted karma
(self-defense ≠ murder — [jogador]'s literal ask), the choice verbs in moral forks,
and the 心魔劫 Heart-Demon Judgment (R6+, ties into the divergence that already
exists). A defensive grep guarantees no gameplay path reads ``project_dao_heart_*``
for a modifier — keep it that way until the wipe.

Derivation is pure + parity-safe: it reads the RAW ``player.path`` / ``player.karma``
(the same values the chat ``/status`` card and the mini ``CultivationTab`` card both
see) so both surfaces always agree on the same tier. It complements the KarmaModal
(which shows the scalar/bands) — it does NOT repeat it: the Dao Heart is the reading
of *firmness of Will* + the 心魔 link, not the karma number.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
# Firmeza (conviction) tiers — engine-not-DB, wipe-safe. The Dao Heart is FIRM
# when the cultivator is deep in their Path's domain and far from the divergence
# boundary where the 心魔 Heart Demon stirs; it TREMBLES as the karma nears (or
# crosses) that boundary. Labels + lore are localized via the
# ``dao_heart_tier_<key>`` / ``_lore`` i18n keys (chat + mini parity).
#
#   5 states (Lei §3 — depth over variety, + Lei §1 — never a silent void):
#     unshaken  不动心 — Coração Inabalável (deep in the Path, far from divergence)
#     firm                — Coração Firme
#     wavering            — Coração Vacilante (drifting away from the Path)
#     trembling           — Coração Trêmulo  (karma near/past divergence → 心魔 stirs)
#     forming             — Coração em Formação (pre-R3 / path NULL — not yet set)
# ══════════════════════════════════════════════════════════════════════════
FIRMEZA_EMOJI: dict[str, str] = {
    "unshaken":  "🗻",
    "firm":      "🛡️",
    "wavering":  "🌗",
    "trembling": "⚡",
    "forming":   "🫧",
}

# Firmeza thresholds on the *margin* — the signed "safe distance" between current
# karma and the divergence threshold (±500), positive = far from the 心魔. Aligned
# so that an UNSHAKEN heart sits in its Path's extreme karma band (saint for
# righteous / demonic for demonic), and TREMBLING coincides with "near the 心魔".
#   margin >= 1000 → unshaken   (righteous karma >= +500 / demonic karma <= -500)
#   margin >=  500 → firm       (holding the Path)
#   margin >=  150 → wavering   (drifting toward divergence)
#   margin <   150 → trembling  (within 150 of the boundary, or already past it)
_MARGIN_UNSHAKEN = 1000
_MARGIN_FIRM = 500
_MARGIN_WAVERING = 150


def _firmeza(path_raw, karma: int) -> tuple[str, bool]:
    """Return ``(firmeza_tier, heart_demon_near)`` for a path+karma pair.

    PURE — never a modifier; only picks a display tier. Mirrors exactly between
    the chat and mini surfaces (both call the projection below). Defensive: any
    odd input collapses to ``("forming", False)`` rather than raising.

    * Path not crystallized (NULL/invalid) → ``forming`` (the Will hasn't set).
    * Rogue → ``firm`` (the Rogue knows no divergence — neutrality is never wrong
      by canon; ``_divergence_for_path_and_karma`` always returns diverged=False —
      so its firmness is its own independence, never the 心魔's prey).
    * Righteous/Demonic → tier by the distance to the divergence boundary.
    """
    try:
        from core.path_engine import is_valid_path
        from core.karma_engine import (
            KARMA_DIVERGENCE_THRESHOLDS as _DIV,
        )
    except Exception:
        logger.debug("dao_heart._firmeza import failed", exc_info=True)
        return "forming", False

    if not is_valid_path(path_raw):
        return "forming", False

    karma = int(karma or 0)
    if path_raw == "rogue":
        # TEC-5 (flag `forbidden_path`) — o Errante passou a ter fronteira
        # (|karma| >= 500). Sem este espelho o Coração viria buscá-lo enquanto
        # este card jurava "firme, sem demônio à vista" — duas telas, duas
        # verdades (o defeito que a lição do hard-gate documenta). Flag OFF ⇒
        # `firm, False` exatamente como sempre.
        try:
            from core.forbidden_path_engine import rogue_divergence
            rog = rogue_divergence(karma)
            thr = rog.get("threshold")
            if thr is None:
                return "firm", False
            margin = abs(int(thr)) - abs(karma)
        except Exception:
            logger.debug("dao_heart rogue divergence failed", exc_info=True)
            return "firm", False
        if margin >= _MARGIN_UNSHAKEN:
            return "unshaken", False
        if margin >= _MARGIN_FIRM:
            return "firm", False
        if margin >= _MARGIN_WAVERING:
            return "wavering", False
        return "trembling", True

    # Signed "safe distance" to the Heart-Demon boundary. Righteous diverges low
    # (karma <= -500) so safety is high karma; Demonic diverges high (>= +500) so
    # safety is low karma. Rogue handled above (no boundary).
    if path_raw == "righteous":
        thr = int(_DIV.get("righteous", -500))   # -500
        margin = karma - thr                      # karma + 500
    elif path_raw == "demonic":
        thr = int(_DIV.get("demonic", 500))       # +500
        margin = thr - karma                      # 500 - karma
    else:
        # Unknown crystallized value — treat as steady, no boundary.
        return "firm", False

    if margin >= _MARGIN_UNSHAKEN:
        return "unshaken", False
    if margin >= _MARGIN_FIRM:
        return "firm", False
    if margin >= _MARGIN_WAVERING:
        return "wavering", False
    # Within 150 of the boundary (or already diverged) → the 心魔 stirs.
    return "trembling", True


def project_dao_heart_for_display(player) -> dict:
    """Structural projection for the chat + mini surfaces (the "Coração Dao 道心"
    card). PURE: the derived *firmeza* (conviction) tier + the *tendency* (the
    Will's inclination) + whether the 心魔 Heart Demon is near + the variant keys
    the surfaces render. ZERO modifier — it REVEALS what path + karma + the
    existing divergence already are; nothing new is tracked or applied (the
    intention-weighted karma / choice verbs / 心魔劫 Judgment are wipe-bound, Lei §1).

    Reads RAW ``player.path`` / ``player.karma`` (NOT a recomputed/effective value)
    so chat ``/status`` and mini ``CultivationTab`` always agree. Defensive — any
    error collapses to the honest ``forming`` default rather than raising (this is
    called on the hot ``api_player`` path).

    Shape::

        {
          tendency: 'righteous'|'demonic'|'rogue',   # the Will's inclination
          is_crystallized: bool,                      # path locked (R3+) vs projected
          firmeza: 'unshaken'|'firm'|'wavering'|'trembling'|'forming',
          firmeza_emoji: str,
          heart_demon_near: bool,
          tendency_variant: 'tendency'|'tendency_forming',  # surface i18n suffix
          demon_variant: 'demon'|'demon_near'|'demon_rogue'|'demon_forming',
        }
    """
    try:
        from core.path_engine import is_valid_path
        from core.karma_engine import derive_path_from_karma

        path_raw = getattr(player, "path", None)
        karma = int(getattr(player, "karma", 0) or 0)
        crystallized = is_valid_path(path_raw)

        # Tendency: the crystallized Path, or — pre-R3 / NULL — the Path the CURRENT
        # karma would crystallize as (honest projection, never asserts it's locked).
        tendency = path_raw if crystallized else derive_path_from_karma(karma)

        firmeza, near = _firmeza(path_raw, karma)
        emoji = FIRMEZA_EMOJI.get(firmeza, "🫧")

        # Variant selection lives HERE (single source) so chat + mini render the
        # exact same line for the same row — no surface can drift.
        if not crystallized:
            tendency_variant, demon_variant = "tendency_forming", "demon_forming"
        elif tendency == "rogue":
            tendency_variant, demon_variant = "tendency", "demon_rogue"
        elif near:
            tendency_variant, demon_variant = "tendency", "demon_near"
        else:
            tendency_variant, demon_variant = "tendency", "demon"

        return {
            "tendency": tendency,
            "is_crystallized": bool(crystallized),
            "firmeza": firmeza,
            "firmeza_emoji": emoji,
            "heart_demon_near": bool(near),
            "tendency_variant": tendency_variant,
            "demon_variant": demon_variant,
        }
    except Exception:
        logger.debug("project_dao_heart_for_display failed", exc_info=True)
        return {
            "tendency": "rogue",
            "is_crystallized": False,
            "firmeza": "forming",
            "firmeza_emoji": FIRMEZA_EMOJI["forming"],
            "heart_demon_near": False,
            "tendency_variant": "tendency_forming",
            "demon_variant": "demon_forming",
        }
