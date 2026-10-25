# -*- coding: utf-8 -*-
"""宗 A SEITA — o dono de "o que o posto da seita É e o que a acção CONFIRMOU" (4.1).

A linha é do Astra (`Olho/Astra/2026-09-16-e-o-corpo-que-acende.md`, «Mundo ·
Seita»), textual:

  *"Pavilhão da Seita de Cultivo, com insígnias de posto e biblioteca.
  `world/sect_hall`: `rank_key`, `contribution / next_rank.contribution_needed`;
  novo posto grava a insígnia. Em `world/sect_library`, `shelves[].rank_ok/
  rank_gap` mostra acesso às prateleiras. Usar contribuição de posto, sem a
  confundir com mérito gastável. Sem filiação, mostrar a entrada existente."*

Três famílias de estado, e só uma acende:

  * **conquista** — o POSTO confirmado (discípulo → interno → núcleo → ancião →
    herdeiro). Acende UMA vez, na confirmação, e fica;
  * **traço** — a contribuição da escada a caminho do próximo posto, sempre com
    o número (e o portão de reino, que é a outra metade do requisito);
  * **nunca acende** — o MÉRITO (o saldo gastável do Pavilhão de Mérito e das
    estantes), as pedras do tributo, as regalias, a força da casa.

── PORQUÊ A SEITA E NÃO A FACÇÃO (o prompt pedia a Facção) ──────────────────

Medido a 05/10 (`tools/db_readonly_faccao_1005.py`): a Facção é LEGADO no próprio
jogo — o aviso da aba diz *"Sistema antigo: agora é Path Trinity (☯️) (…) absorve
esta progressão nas próximas atualizações"* — e o motor dela diz que se retira por
inteiro. No Beta UM jogador fez as 99 recolhas de missão; no `main`, um em
set/out. Pôr luz num sistema anunciado como antigo é código descartável (Lei §5).
A Seita é o sistema que a absorve, e o seguinte na ordem do Mundo.

── O QUE SE MEDIU ANTES DE ESCREVER ISTO (2026-10-05) ───────────────────────

`tools/db_readonly_seita_1005.py`, só leitura:

  main  21 membros (12 activos em 30 dias) · 18 HERDEIROS — o topo — todos com
        contribuição a sobrar (máx. 20.000 contra o limiar de 1.500) · 3 com
        próximo posto (falta p50 = 140) · 3 herdeiros ABAIXO do portão de reino
        (renasceram: o motor nunca rebaixa) · 12 gastaram mérito
  s2     6 membros (5 activos) · 5 herdeiros · 1 discípulo · 2 doaram pergaminho

⚠️ Por isso o posto que se MOSTRA é o GRAVADO (``players.sect_rank``), nunca um
recalculado: recalcular rebaixaria os três renascidos no ecrã.

── O QUE ESTE FICHEIRO FAZ, e só isto ─────────────────────────────────────

1. **A escada** (``escada``) — os cinco postos com o limiar de contribuição e o
   portão de reino de cada um, do MOTOR (``world_sects_engine``). É o
   denominador das insígnias: sem ela o cliente não inscreve nada.
2. **O retrato** (``retrato``) — o que cresce: o posto gravado e a contribuição
   da escada — a de ``ladder_contribution``, a MESMA que promove (o Salão já
   lia esta, para não anunciar um progresso que a promoção não entrega).
3. **O ganho** (``ganho``) — ``{"antes", "depois", "acende"}`` de uma acção
   confirmada (o tributo, a missão da seita, a escolha de uma missão, e a
   promoção que o próprio Salão confirma ao abrir quando um portão de reino
   caiu). O "antes" lê-se na MESMA transacção, com a linha do jogador TRANCADA,
   antes do motor; o "depois" relê-se depois dele, na mesma transacção.

⚠️ O ganho só viaja com a onda ligada (``seita_ganho`` é chave CONDICIONAL): o
``main`` recebe as respostas de hoje, byte a byte — e sem a onda nem o "antes"
se lê (zero consultas a mais, zero trincos a mais).
"""
from __future__ import annotations

from typing import Callable

Flag = Callable[[str], bool]

# A conquista — o único campo cuja SUBIDA acende. A contribuição (o traço) sobe
# muitas vezes sem acender nada; o mérito nem entra no retrato.
_CONQUISTA = {"posto": "rank_index"}
EIXOS_QUE_ACENDEM = tuple(_CONQUISTA)


def escada() -> list[dict]:
    """Os cinco postos, pela ordem da promoção, com o limiar de contribuição e o
    portão de reino de cada um — lidos do motor, nunca copiados."""
    from core.world_sects_engine import (
        SECT_RANKS, SECT_RANK_THRESHOLDS, SECT_RANK_REALM_GATES, get_rank_label_key,
    )
    return [{
        "rank": r,
        "rank_key": get_rank_label_key(r),
        "threshold": int(SECT_RANK_THRESHOLDS.get(r, 0)),
        "realm_gate": int(SECT_RANK_REALM_GATES.get(r, 0)),
    } for r in SECT_RANKS]


def retrato(sect_id, rank, earned, balance, scroll_econ) -> dict | None:
    """O que cresce, para quem é membro: o posto GRAVADO e a contribuição da
    escada. ``None`` para quem não está numa casa (não há o que retratar)."""
    from core.world_sects_engine import (
        SECT_RANKS, DEFAULT_SECT_RANK, rank_index, get_rank_label_key,
        ladder_contribution, is_valid_sect,
    )
    if not is_valid_sect(sect_id):
        return None
    r = rank if rank in SECT_RANKS else DEFAULT_SECT_RANK
    return {
        "rank": r,
        "rank_key": get_rank_label_key(r),
        "rank_index": rank_index(r),
        "contribution": int(ladder_contribution(earned, balance, scroll_econ is not None)),
    }


def ganho(antes: dict, depois: dict) -> dict | None:
    """``seita_ganho`` — o ganho CONFIRMADO de uma acção sobre o posto.

    ``acende`` leva só a conquista que SUBIU (o posto). Uma acção que não mudou
    nem o posto nem a contribuição da escada (a doação de pergaminho, que só
    credita o saldo; uma missão sem contribuição) não tem ganho a dizer.
    """
    if antes is None or depois is None:
        return None
    acende = [eixo for eixo, campo in _CONQUISTA.items()
              if int(depois[campo]) > int(antes[campo])]
    if not acende and int(depois["contribution"]) == int(antes["contribution"]):
        return None
    return {"antes": antes, "depois": depois, "acende": acende}


def _colunas():
    from database.models import Player
    return (Player.sect_id, Player.sect_rank, Player.sect_contribution_earned,
            Player.sect_contribution, Player.scroll_econ)


async def _ler(session, player_id: int, trancar: bool):
    from sqlalchemy import select
    from database.models import Player
    q = select(*_colunas()).where(Player.telegram_id == player_id)
    if trancar:
        q = q.with_for_update()
    row = (await session.execute(q)).first()
    if row is None:
        return None
    return retrato(row[0], row[1], row[2], row[3], row[4])


async def ler_antes(session, player_id: int) -> dict | None:
    """O retrato ANTES do motor, ou ``None`` se o jogador não é membro.

    ⚠️ As três escolhas da 3.3, pela mesma razão:
      · **só colunas** (não a entidade) — uma entidade carregada aqui ficaria no
        mapa de identidade com os valores DESTA leitura. Os motores da seita
        refrescam-se com ``populate_existing`` (o fix dos lost-updates), mas a
        regra não depende de cada motor se lembrar disso;
      · **trancada** (``FOR UPDATE``) — o "antes" e o motor vêem a MESMA linha:
        um tributo noutra janela entre a leitura e o motor não é atribuído a
        esta acção;
      · **só com a onda** — quem chama decide (``if _onda_on()``): sem ela, nem
        consulta nem trinco a mais.
    """
    return await _ler(session, player_id, trancar=True)


async def ganho_da_acao(session, player_id: int, antes) -> dict | None:
    """O ganho de uma acção que o motor CONFIRMOU. ``antes`` é o que
    ``ler_antes`` devolveu; sem ele (onda desligada, não-membro) não há ganho.

    O "depois" relê as MESMAS colunas na mesma transacção — o autoflush leva
    primeiro as escritas pendentes do motor, portanto é exactamente o que o
    ``commit`` a seguir vai gravar.
    """
    if antes is None:
        return None
    depois = await _ler(session, player_id, trancar=False)
    return ganho(antes, depois)


def no_payload(g: dict | None, flag: Flag | None = None) -> dict:
    """``{"seita_ganho": g}`` com a onda; ``{}`` sem ela. O MESMO espelho da
    chave-mestra das portas (``core/portas.onda_on``)."""
    if g is None:
        return {}
    from core.portas import onda_on
    return {"seita_ganho": g} if onda_on(flag) else {}


def escada_no_payload(flag: Flag | None = None) -> dict:
    """``{"escada": [...]}`` no Salão, só com a onda — o denominador das
    insígnias. Sem a onda o payload do Salão é o de hoje, chave a chave."""
    from core.portas import onda_on
    return {"escada": escada()} if onda_on(flag) else {}
