# -*- coding: utf-8 -*-
"""冶 OS OFÍCIOS — o dono de "o que esta acção CONFIRMOU no ofício" (3.1).

A gramática é do Astra (`Olho/Astra/2026-09-16-e-o-corpo-que-acende.md` §1 e a
linha «Caverna · Ofícios» do §3). Cada ofício tem três famílias de estado, e
só uma delas acende:

  * **conquista** — acende UMA vez, na confirmação, e fica: o posto do ofício
    (``tier`` da Alquimia e da Forja), o selo da receita (``level`` da
    maestria) e o posto do Fogo de Alma;
  * **traço** — o fio a caminho da próxima conquista, sempre com o número:
    ``xp / xp_to_next`` do ofício e do fogo, ``crafts_count / next_crafts``
    (``forges_count / next_forges``) da receita;
  * **nunca acende** — energia, o calor da execução (a chama), durabilidade do
    caldeirão, ervas e minério, chance de êxito, preço. *"Uma luz que não
    significa progresso é árvore de Natal."*

  *"Consequência confirmada: valor anterior → novo, diferença e unidade, junto
  da operação. Usar o resultado real ou snapshots validados da mesma ação."*

── O QUE ESTE FICHEIRO FAZ, e só isto ──────────────────────────────────────

1. **O retrato** de cada eixo (``retrato_*``). É a MESMA forma que a lista de
   receitas manda (``alchemy``/``forge`` e a ``mastery`` de cada receita) e que
   o resultado manda antes e depois — um só cálculo de "quanto falta" para as
   duas telas. As tabelas continuam a ser dos motores; aqui só se LÊEM.
2. **O ganho** (``ganho``) — ``{eixo: {"antes", "depois"}}`` tirado na MESMA
   transacção da acção confirmada, mais a lista ``acende`` com os eixos cuja
   CONQUISTA mudou. O "antes" lê-se antes de o motor mexer; o "depois" depois.
   **Nunca se deriva do "depois" menos o ganho:** o tecto de XP por receita da
   Forja (H-7) dá ganho 0 com a feitura confirmada, e um lote pode subir mais
   do que um degrau — a subtracção mentiria nos dois casos.

⚠️ O retrato de uma maestria que ainda não tem linha é o estado inicial REAL do
motor (nível 1, 0 feitos) — é o que ``get_or_create_*_mastery`` cria na
primeira feitura. Não é "sem dados".

⚠️ O ganho só viaja com a onda ligada (``oficio_ganho`` é chave CONDICIONAL):
o ``main`` recebe o payload de hoje, byte a byte.
"""
from __future__ import annotations

from typing import Callable

# Os três eixos que PODEM acender. Qualquer outro nome que apareça numa chamada
# a ``ganho`` é recusado: é aqui que "o que nunca acende" deixa de ser prosa.
EIXOS = ("oficio", "receita", "fogo")

Flag = Callable[[str], bool]


def _int(v, omissao: int) -> int:
    """``None`` (linha que ainda não existe, ou coluna nula) é o valor com que o
    MOTOR cria a linha; qualquer outro valor passa tal e qual — um 0 real
    continua 0."""
    return int(omissao if v is None else v)


def _proximo(tabela: dict, nivel: int, maximo: int, chave: str) -> int | None:
    """O limiar do degrau seguinte, ou ``None`` no máximo (nunca um denominador
    inventado — Astra §1: *"no máximo, escrever Concluído/Limite atual"*)."""
    if nivel >= maximo:
        return None
    return int(tabela[nivel + 1][chave])


# ── Os retratos ──────────────────────────────────────────────────────────────

def retrato_alquimia(skill) -> dict:
    from core.alchemy_engine import ALCHEMY_TIERS, MAX_ALCHEMY_TIER
    tier = _int(getattr(skill, "tier", None), 1)
    return {
        "tier": tier,
        "xp": _int(getattr(skill, "xp", None), 0),
        "xp_to_next": _proximo(ALCHEMY_TIERS, tier, MAX_ALCHEMY_TIER, "xp_req"),
        "at_max": tier >= MAX_ALCHEMY_TIER,
        "max_tier": MAX_ALCHEMY_TIER,
    }


def retrato_forja(skill) -> dict:
    from core.forge_engine import FORGE_TIERS, MAX_FORGE_TIER
    tier = _int(getattr(skill, "tier", None), 1)
    return {
        "tier": tier,
        "xp": _int(getattr(skill, "xp", None), 0),
        "xp_to_next": _proximo(FORGE_TIERS, tier, MAX_FORGE_TIER, "xp_req"),
        "at_max": tier >= MAX_FORGE_TIER,
        "max_tier": MAX_FORGE_TIER,
    }


def retrato_fogo(sf) -> dict:
    from core.alchemy_engine import SOUL_FIRE_TIERS, MAX_SOUL_FIRE_TIER
    tier = _int(getattr(sf, "fire_tier", None), 0)
    return {
        "tier": tier,
        "xp": _int(getattr(sf, "fire_exp", None), 0),
        "xp_to_next": _proximo(SOUL_FIRE_TIERS, tier, MAX_SOUL_FIRE_TIER, "xp_req"),
        "at_max": tier >= MAX_SOUL_FIRE_TIER,
        "max_tier": MAX_SOUL_FIRE_TIER,
    }


def retrato_receita_pilula(mastery) -> dict:
    """A maestria de UMA pílula — as chaves da ``mastery`` da lista de receitas
    (``level``, ``crafts_count``, ``next_crafts``, ``next_level``, ``at_max``)."""
    from core.alchemy_engine import MASTERY_LEVELS, MAX_MASTERY_LEVEL
    level = _int(getattr(mastery, "mastery_level", None), 1)
    nxt = _proximo(MASTERY_LEVELS, level, MAX_MASTERY_LEVEL, "crafts_req")
    return {
        "level": level,
        "crafts_count": _int(getattr(mastery, "crafts_count", None), 0),
        "next_crafts": nxt,
        "next_level": (level + 1) if nxt is not None else None,
        "at_max": nxt is None,
        "max_level": MAX_MASTERY_LEVEL,
    }


def retrato_receita_forja(mastery) -> dict:
    """A maestria de UMA receita da Forja (``forges_count``/``next_forges``)."""
    from core.forge_engine import FORGE_MASTERY_LEVELS, MAX_FORGE_MASTERY
    level = _int(getattr(mastery, "mastery_level", None), 1)
    nxt = _proximo(FORGE_MASTERY_LEVELS, level, MAX_FORGE_MASTERY, "forges_req")
    return {
        "level": level,
        "forges_count": _int(getattr(mastery, "forges_count", None), 0),
        "next_forges": nxt,
        "next_level": (level + 1) if nxt is not None else None,
        "at_max": nxt is None,
        "max_level": MAX_FORGE_MASTERY,
    }


# A CONQUISTA de cada eixo — o único campo cuja subida acende. O traço (xp,
# feitos) sobe muitas vezes sem acender nada.
_CONQUISTA = {"oficio": "tier", "receita": "level", "fogo": "tier"}


# ── O "antes", lido SEM criar nada ─────────────────────────────────────────
# Os motores criam a skill/maestria/fogo na primeira feitura (``get_or_create_*``).
# Tirar o retrato com essas funções criaria a linha ANTES de a acção passar os
# seus portões — e uma receita inexistente rebentaria numa chave estrangeira em
# vez de dizer ``recipe_not_found``. Aqui só se lê; uma linha que falta é o
# estado com que o motor a vai criar (``_int``), excepto o Fogo de Alma, cujo
# posto inicial depende do reino: esse fica ``None`` — não se adivinha.

async def ler_antes_alquimia(session, player_id: int, pill_id: int) -> dict:
    from sqlalchemy import select, and_
    from database.models import PlayerAlchemySkill, PlayerPillMastery, PlayerSoulFire
    skill = (await session.execute(select(PlayerAlchemySkill).where(
        PlayerAlchemySkill.player_id == player_id))).scalar_one_or_none()
    mastery = (await session.execute(select(PlayerPillMastery).where(and_(
        PlayerPillMastery.player_id == player_id,
        PlayerPillMastery.pill_id == pill_id)))).scalar_one_or_none()
    sf = (await session.execute(select(PlayerSoulFire).where(
        PlayerSoulFire.player_id == player_id))).scalar_one_or_none()
    return {
        "oficio": retrato_alquimia(skill),
        "receita": retrato_receita_pilula(mastery),
        "fogo": retrato_fogo(sf) if sf is not None else None,
    }


async def ler_antes_fogo(session, player_id: int) -> dict | None:
    """O Fogo de Alma antes de "alimentar o núcleo". ``None`` se a linha não
    existe (o posto inicial depende do reino — não se adivinha)."""
    from sqlalchemy import select
    from database.models import PlayerSoulFire
    sf = (await session.execute(select(PlayerSoulFire).where(
        PlayerSoulFire.player_id == player_id))).scalar_one_or_none()
    return retrato_fogo(sf) if sf is not None else None


async def ler_antes_forja(session, player_id: int, recipe_id: int) -> dict:
    from sqlalchemy import select, and_
    from database.models import PlayerForgeSkill, PlayerForgeMastery
    skill = (await session.execute(select(PlayerForgeSkill).where(
        PlayerForgeSkill.player_id == player_id))).scalar_one_or_none()
    mastery = (await session.execute(select(PlayerForgeMastery).where(and_(
        PlayerForgeMastery.player_id == player_id,
        PlayerForgeMastery.recipe_id == recipe_id)))).scalar_one_or_none()
    return {"oficio": retrato_forja(skill), "receita": retrato_receita_forja(mastery)}


# ── O ganho ──────────────────────────────────────────────────────────────────

def ganho(**eixos: tuple[dict | None, dict | None]) -> dict:
    """``ganho(oficio=(antes, depois), receita=(antes, depois), fogo=…)``.

    Devolve ``{"oficio": {"antes", "depois"}, …, "acende": [eixos]}``. Um eixo
    sem nenhum dos dois retratos não entra (não se inventa um "0 → 0"); um eixo
    fora de ``EIXOS`` é um erro de programação e rebenta aqui, não no ecrã.
    """
    out: dict = {}
    acende: list[str] = []
    for nome, par in eixos.items():
        if nome not in EIXOS:
            raise ValueError("eixo de ofício desconhecido: %r (os que acendem: %r)"
                             % (nome, EIXOS))
        antes, depois = par
        if antes is None and depois is None:
            continue
        out[nome] = {"antes": antes, "depois": depois}
        c = _CONQUISTA[nome]
        if antes is not None and depois is not None and int(depois[c]) > int(antes[c]):
            acende.append(nome)
    out["acende"] = acende
    return out


def ganho_alquimia(antes: dict | None, skill, mastery, sf) -> dict | None:
    """O ganho de uma feitura de pílula (simples ou lote). ``antes`` é o que
    ``ler_antes_alquimia`` devolveu; sem ele (onda desligada) não há ganho."""
    if antes is None:
        return None
    return ganho(
        oficio=(antes["oficio"], retrato_alquimia(skill) if skill is not None else None),
        receita=(antes["receita"], retrato_receita_pilula(mastery) if mastery is not None else None),
        fogo=(antes["fogo"], retrato_fogo(sf) if sf is not None else None),
    )


def ganho_forja(antes: dict | None, skill, mastery) -> dict | None:
    """O ganho de uma forja (simples ou lote). A Forja não mexe no Fogo de
    Alma — só o lê para a chance —, por isso esse eixo não entra."""
    if antes is None:
        return None
    return ganho(
        oficio=(antes["oficio"], retrato_forja(skill) if skill is not None else None),
        receita=(antes["receita"], retrato_receita_forja(mastery) if mastery is not None else None),
    )


def no_payload(g: dict | None, flag: Flag | None = None) -> dict:
    """``{"oficio_ganho": g}`` com a onda ligada; ``{}`` sem ela (o ``main``
    recebe o payload de hoje). O MESMO espelho da chave-mestra das portas."""
    if g is None:
        return {}
    from core.portas import onda_on
    return {"oficio_ganho": g} if onda_on(flag) else {}
