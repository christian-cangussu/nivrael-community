"""Track A item 6 — Técnicas: the Comprehension axis disclosure + Art↔Root resonance.

This wave is a REFRAME + DISCLOSURE, not a new mechanic (owner decision 2026-06-21,
DESIGN_DECISIONS §6). The fine audit found the "Compreensão" axis the Grand Design §9
asks for ALREADY EXISTS as ``PlayerTechnique.mastery_level`` — a use-gained 5-stage
ladder (Iniciante→Transcendência) feeding a LIVE combat multiplier
(``core.combat_engine.MASTERY_STAGES``). Building a second, parallel ``comprehension``
column would duplicate that axis (against Lei §3 profundidade>variedade) and be
wipe-discarded (against Lei §5). So item 6 instead RELABELS that live axis as
"Compreensão" (Vislumbre→Consumação) across the chat + mini surfaces — PURE i18n,
ZERO mechanic change (the column, the XP, and the multiplier are all untouched) —
plus two disclosures:

  * the already-enforced loadout cap (``core.combat_engine.get_max_combat_techniques``),
    surfaced honestly ("o Mar de Qi suporta N artes ativas — cresce com o reino"); and
  * this module's Art↔Root resonance flavor — does a technique's ``element`` match a
    Wuxing element the cultivator's ``root_elements`` carries (Track A item 5)?

DISCLOSURE-ONLY: resonance has ZERO mechanical effect this wave (a defensive grep keeps
it out of every number-producing path — mirror of root_engine). The real elemental
gating + the UNCAPPED non-qi Comprehension lever for soul/body/Laws builds are Track B
(WIPE), where ``mastery_level`` evolves into the no-ceiling Compreensão alongside the
technique-catalog reorg (memory: technique-scarcity-wipe-rule).
"""
from __future__ import annotations

import logging
import os

from core.root_engine import ROOT_ELEMENTS

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# 内功 — A COMPREENSÃO DAS ARTES INTERNAS (report do [jogador], 2026-08-11)
#
# *"techniques (internal and meditation): seems like they never gain experience
#  (such as luck bonus technique)… does it even has a way to gain xp?"*
#
# Ele tinha razão, e a causa era uma EXCLUSÃO DUPLA — nenhuma delas um bug de
# escrita, as duas invisíveis para quem joga:
#   1. a montagem do lutador só carrega `tech_type == "combat"`
#      (`handlers/combat.py:151`, `core/webserver.py:16936`, `core/duel_engine.py:97`);
#   2. o contador de ativações só conta os 5 effect_types de combate
#      (`core/combat_engine._accumulate_tech_activations`) — e os SEIS efeitos
#      passivos (cb/qi_regen/hp_regen/soul/perception/luck _boost) ficam fora.
# ⇒ ganhar Compreensão JOGANDO era estruturalmente impossível para as 6 artes
# internas/de meditação. A única fonte era absorver um pergaminho REPETIDO — e
# nenhuma tela dizia isso (o botão de absorver só aparece se você já tiver o
# repetido na mão). Do lado do jogador, "não tem como ganhar XP" era verdade.
#
# E não era cosmético: a Compreensão MULTIPLICA o efeito passivo
# (`game_logic.get_active_technique_bonuses` — a Bênção da Fortuna dá 10% de
# sorte no estágio 1 e 20% no 5) e ainda destranca a subida de grau.
#
# O FAUCET: 内功 treina-se sentado. Uma meditação que TERMINA de verdade
# alimenta as artes internas ATIVAS — o mesmo evento que já credita a diária de
# cultivo, no mesmo lugar, com a mesma regra ("quem finaliza credita").
# Uma única fonte, não seis (Lei §3: profundidade > variedade).
# ══════════════════════════════════════════════════════════════════════════

PASSIVE_TECH_TYPES = ("meditation", "interior")

# 0.5 XP/min ⇒ leve(30) 15 · profunda(60) 30 · vazio(120) 60. Contra os degraus
# 100/500/2000/10000: o 2º estágio chega em ~7 meditações leves, o 3º em ~13 do
# vazio, e o topo continua a ser uma jornada. Mesma ordem de grandeza do combate
# (5/ativação + 20/vitória), que é o eixo irmão.
PASSIVE_MASTERY_XP_PER_MIN = float(os.getenv("PASSIVE_MASTERY_XP_PER_MIN", "0.5"))


def passive_mastery_xp_for(minutes: int) -> int:
    """Quanta Compreensão vale uma sessão de N minutos. PURA."""
    try:
        m = int(minutes or 0)
        if m <= 0:
            return 0
        return max(1, int(m * PASSIVE_MASTERY_XP_PER_MIN))
    except Exception:
        return 0


async def award_passive_mastery_xp(session, player_id: int, minutes: int) -> list[dict]:
    """Credita Compreensão às artes internas/de meditação ATIVAS do jogador.

    Chamado pelos MESMOS quatro finalizadores de meditação que já creditam a
    diária `cultivate` — a regra de ferro desta casa é **QUEM FINALIZA CREDITA**,
    e já se pagou o preço de a esquecer num deles (fix de 2026-07-21).

    "Ativas" = `is_active_combat` True, que é a coluna que o jogo reusa como
    *equipada* também para as passivas (é exatamente o filtro que
    `game_logic.get_active_technique_bonuses` usa para as fazer MORDER) — logo o
    que você equipa é o que treina, e o que treina é o que morde.

    Devolve a lista de subidas de estágio (`{emoji, name, before, after}`) para
    o chamador as poder ANUNCIAR (Lei §10 — antes→depois). Nunca levanta: um
    erro aqui não pode derrubar o fim de uma meditação.
    """
    try:
        gain = passive_mastery_xp_for(minutes)
        if gain <= 0 or session is None or not player_id:
            return []
        from sqlalchemy import select
        from core.combat_engine import MASTERY_STAGES
        from database.models import PlayerTechnique, TechniqueCatalog

        # 名 2026-09-14 — a subida de Compreensao anuncia o nome da arte, e ele
        # saia CRU. Um destinatario so' (o dono), logo traduz-se na escrita.
        from core.i18n import catalog_text as _ct
        from database.models import Player as _P
        _lg = ((await session.execute(
            select(_P.language).where(_P.telegram_id == player_id)
        )).scalar_one_or_none() or "pt").lower()

        rows = (await session.execute(
            select(PlayerTechnique, TechniqueCatalog.name, TechniqueCatalog.emoji)
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
            .where(
                PlayerTechnique.player_id == player_id,
                PlayerTechnique.is_active_combat == True,  # noqa: E712
                TechniqueCatalog.tech_type.in_(PASSIVE_TECH_TYPES),
            )
        )).all()

        ups: list[dict] = []
        for pt, name, emoji in rows:
            before = int(pt.mastery_level or 1)
            pt.mastery_xp = int(pt.mastery_xp or 0) + gain
            while int(pt.mastery_level or 1) < 5:
                nxt = MASTERY_STAGES.get(int(pt.mastery_level or 1) + 1)
                if nxt and pt.mastery_xp >= nxt["xp_req"]:
                    pt.mastery_level = int(pt.mastery_level or 1) + 1
                else:
                    break
            after = int(pt.mastery_level or 1)
            if after > before:
                ups.append({"emoji": emoji or "📜",
                            "name": _ct(_lg, "tech", pt.technique_id, "name", name or ""),
                            "before": before, "after": after})
        return ups
    except Exception:
        logger.exception("award_passive_mastery_xp failed (player=%s)", player_id)
        return []


async def credit_passive_mastery(session, player_id: int, minutes: int) -> list[dict]:
    """`award_passive_mastery_xp` + o ANÚNCIO da subida. É esta que os quatro
    finalizadores de meditação chamam (uma linha cada).

    ⚠️ SAVEPOINT, pelo mesmo motivo que o crédito da diária ao lado: sem ele o
    UPDATE só é emitido no COMMIT do chamador — fora do try — e um erro de DB
    ali derrubaria o tick/sweep inteiro (hotfix 2026-07-21b).

    ⚠️ A notificação é uma key NOVA com payload NOVO desde a 1ª row. A regra da
    casa: uma `notif_*` renderiza PREGUIÇOSAMENTE sobre o payload gravado na
    época, e não há poda — logo acrescentar um placeholder a uma key existente
    parte retroativamente todas as linhas já gravadas.
    """
    ups: list[dict] = []
    try:
        async with session.begin_nested():
            ups = await award_passive_mastery_xp(session, player_id, minutes)
    except Exception:
        logger.exception("credit_passive_mastery award failed (player=%s)", player_id)
        return []
    if not ups:
        return []
    try:
        from core.notification_engine import notify
        first = ups[0]
        await notify(
            session, player_id, "neigong_up",
            title_key="notif_neigong_up_title",
            body_key="notif_neigong_up_body",
            payload={"emoji": first["emoji"], "name": first["name"],
                     "before": int(first["before"]), "after": int(first["after"]),
                     "extra": max(0, len(ups) - 1)},
            icon="🌀", target_tab="combat", priority=2,
        )
    except Exception:
        logger.exception("credit_passive_mastery notify failed (player=%s)", player_id)
    return ups


def technique_gain_key(tech_type: str | None) -> str:
    """A key i18n que DIZ como esta arte ganha Compreensão (Lei §1).

    Antes desta onda nenhuma tela dizia — e para as passivas a única fonte era
    absorver um pergaminho repetido, coisa que o jogador só descobria por
    acidente. Server-resolved: a MESMA frase serve o chat e o mini-app."""
    return ("tech_gain_passive" if str(tech_type or "") in PASSIVE_TECH_TYPES
            else "tech_gain_combat")


def technique_root_resonance(tech_element, root_elements) -> dict | None:
    """Pure flavor projection: does this art's element resonate with the cultivator's root?

    Returns ``{"element": <key>, "emoji": <emoji>}`` when the technique's ``element`` is a
    known Wuxing/variant element (``core.root_engine.ROOT_ELEMENTS``) AND that element is
    present in the player's ``root_elements`` composition (Track A item 5). Returns ``None``
    otherwise — e.g. "universal"/"light" techniques (no root counterpart), or an element the
    root simply does not carry. ZERO modifier; the surfaces localize the element name via the
    shared ``root_el_<key>`` i18n keys.
    """
    if not tech_element or not root_elements:
        return None
    el = str(tech_element).strip().lower()
    info = ROOT_ELEMENTS.get(el)
    if info is None:
        return None
    if el not in root_elements:
        return None
    return {"element": el, "emoji": info["emoji"]}
