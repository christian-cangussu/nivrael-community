"""core/ftue_engine.py — FTUE espinha: the guided first hour (server-gated, derived-state).

Solves the audit's #1 early-game gap ("new player lands on a blank menu, no guidance"): a
GUIDED tracker that leads the cultivator through the now-meaningful early loop in the voice
of the Velho Mendigo de Línghé. It is pure DERIVED STATE — it reads existing player fields
and computes which step is next; it stores NOTHING (no migration) and CHANGES nothing (it
only guides). Server-gated by `ftue_espinha` (OFF on main → never renders → the 57 are
untouched). Reuses every motor (meditation, body, horta, breakthrough) — Lei §3.

The steps adapt so the guide is NEVER a dead-end (Lei §1): the body steps (corpo/horta) only
appear where the body axis ships (`cultivo_corpo_r0` ON); otherwise the spine is the
universal ENCHER→AVANÇAR loop. When every step is done the Mendigo departs (the handoff).
"""

_ALL_STEPS = ("meditar", "corpo", "horta", "avanco")

# MV-1 §0.3 (V-4): a técnica de GOLPE da primeira hora — Beggar's Palm
# (combat_seeds.FTUE_TECHNIQUES; sect_key "ftue_mendigo" = fora dos pools).
FTUE_STRIKE_TECHNIQUE_ID = 45


def ftue_on(world_key=None) -> bool:
    """True iff `ftue_espinha` is ON for the (active or given) world. Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("ftue_espinha", world_key))
    except Exception:
        return False


def _body_axis_on() -> bool:
    try:
        from core.body_tempering_engine import _cultivo_corpo_on
        return bool(_cultivo_corpo_on())
    except Exception:
        return False


async def grant_ftue_strike_technique(session, player_id: int) -> bool:
    """MV-1 §0.3 (V-4 [jogador]: "as 2 primeiras habilidades são de esquiva") —
    em mundos com `ftue_espinha` ON, o Velho Mendigo ensina a Beggar's Palm
    (dano, req_realm 0) no NASCIMENTO: a primeira hora tem um GOLPE.

    Grant DIRETO (padrão learn_sect_technique — sem scroll, sem learn-gate;
    o duel engine não re-verifica realm em fight-time), idempotente, e
    best-effort: nunca deixa uma exceção quebrar o onboarding. OFF (main,
    incl. todos os mundos sem a flag) → no-op absoluto."""
    if not ftue_on():
        return False
    try:
        from sqlalchemy import select
        from database.models import PlayerTechnique
        existing = (await session.execute(select(PlayerTechnique).where(
            PlayerTechnique.player_id == player_id,
            PlayerTechnique.technique_id == FTUE_STRIKE_TECHNIQUE_ID,
        ))).scalar_one_or_none()
        if existing:
            return False
        session.add(PlayerTechnique(
            player_id=player_id,
            technique_id=FTUE_STRIKE_TECHNIQUE_ID,
            mastery_level=1,
            is_active_combat=True,
        ))
        return True
    except Exception:
        import logging
        logging.getLogger(__name__).exception("grant_ftue_strike_technique failed")
        return False


def _steps_for(player):
    """The ordered (key, done) steps for this player. The body steps appear only where the
    temper path ships, so a world without it never strands the player on an impossible step."""
    realm = int(getattr(player, "realm", 0) or 0)
    cb = float(getattr(player, "cultivation_base", 0) or 0)
    steps = [("meditar", cb > 0 or realm > 0)]   # ENCHER — cultivated at all
    if _body_axis_on():
        steps.append(("corpo", int(getattr(player, "mortal_body_level", 0) or 0) > 0))
        # any of the 4 faucets produced progress (Horta/Caça/Ambiental/Combate)
        steps.append(("horta", int(getattr(player, "mortal_temper_progress", 0) or 0) > 0))
    steps.append(("avanco", realm > 0))          # crossed the first threshold
    return steps


def project_ftue(player) -> dict:
    """READ — the guide surface: the ordered checklist + the current (first not-done) step.
    PURE. The caller gates on `ftue_espinha`. `complete` once every step is done (the Mendigo
    departs). The mini-app/chat render the Mendigo line via `ftue_mendigo_<current>`."""
    realm = int(getattr(player, "realm", 0) or 0)
    steps = _steps_for(player)
    out = [{"key": k, "done": bool(d)} for k, d in steps]
    current = next((s["key"] for s in out if not s["done"]), None)
    done_n = sum(1 for s in out if s["done"])
    # The guide retires once the early game is launched: all steps done OR past the early
    # band (realm >= 1 and nothing left to teach) — it never lingers into the mid-game.
    complete = current is None or realm >= 2
    return {
        "ftue_on": True,
        "complete": bool(complete),
        "current": None if complete else current,
        "steps": out,
        "done_count": done_n,
        "total": len(out),
    }
