# -*- coding: utf-8 -*-
"""幫 A GUILDA — o dono de "o que cada instalação É e o que a melhoria CONFIRMOU" (4.2).

A linha é do Astra (`Olho/Astra/2026-09-16-e-o-corpo-que-acende.md`, «Mundo ·
Guilda»), textual:

  *"Planta das seis instalações da guilda. `sect.sect.buildings`: `training`,
  `herb_garden`, `forge`, `library`, `defense`, `spirit_vein`; cada instalação
  mostra o seu nível confirmado, incluindo formato legado numérico ou
  `{level,effect}`. Melhoria grava um traço na instalação. `your_contribution` e
  `member_count / max_members` ficam nomeados, sem somar tudo num "nível da
  guilda" fictício."*

⚠️ A Guilda NÃO é a Seita. Desde a v16.4 (*Sect-Guild Split*) a Seita é a casa
NPC (`players.sect_*`, `core/seita.py` — a 4.1) e a Guilda é o grupo criado por
jogadores: a tabela `sects`, a aba `SectTab`, as rotas `/api/miniapp/sect*`.
Os nomes no código são os antigos.

Três famílias de estado, e só uma acende:

  * **conquista** — o NÍVEL confirmado de uma instalação. Acende UMA vez, na
    confirmação da melhoria, e fica;
  * **leitura** — o efeito de cada instalação (o número do motor), o custo do
    próximo nível contra o tesouro;
  * **nunca acende** — o TESOURO (gastável), a contribuição do membro (gastável
    na loja da guilda), os membros (ocupação).

── O QUE SE MEDIU ANTES DE ESCREVER ISTO (2026-10-07) ───────────────────────

`tools/db_readonly_guilda_1007.py`, só leitura:

  main  9 guildas · 97 membros · 30 activos em 30 dias (de 36 jogadores activos
        no mundo) · 7.644 melhorias (70 em 30 dias) · níveis de 1 a 856
  s2    4 guildas · 18 membros · 13 activos (de 18) · 1.179 melhorias (380 em 30
        dias) · níveis de 0 a 208

⚠️ Os níveis NÃO têm teto (`upgrade_building` sobe sempre; o custo é 1000 ×
(L+1)²). Sem denominador do servidor, nenhuma inscrição "N de M" (lei §5.2):
a planta mostra o nível e o custo do próximo, nunca uma fracção inventada.

── O QUE ESTE FICHEIRO FAZ, e só isto ─────────────────────────────────────

1. **A planta** (``planta``) — as seis instalações pela ordem do motor
   (``BUILDINGS``), cada uma com o nível gravado, o NÚMERO do efeito (o mesmo
   que ``format_building_effect`` escreve — ``building_effect_value``) e o custo
   do próximo nível (``calculate_upgrade_cost``). Tudo do motor: o cliente não
   repete fórmula nenhuma (antes repetia a do custo).
2. **O ganho** (``ganho``) — ``{"antes", "depois", "acende"}`` de uma melhoria
   confirmada. O "antes" lê-se na MESMA transacção, com a linha da guilda
   TRANCADA, antes de qualquer coisa carregar a entidade; o "depois" relê-se
   depois do motor, na mesma transacção.

⚠️ A planta e o ganho só viajam com a onda ligada (chaves CONDICIONAIS): o
``main`` recebe as respostas de hoje, byte a byte — e sem a onda nem o "antes"
se lê (zero consultas a mais, zero trincos a mais).
"""
from __future__ import annotations

from typing import Callable

Flag = Callable[[str], bool]

# A conquista — o único campo cuja SUBIDA acende. O tesouro desce a cada
# melhoria e nunca acende; a contribuição e os membros nem entram no retrato.
_CONQUISTA = {"nivel": "level"}
EIXOS_QUE_ACENDEM = tuple(_CONQUISTA)


def instalacoes() -> tuple:
    """As seis chaves, pela ordem da planta — as do MOTOR, nunca uma cópia."""
    from core.sect_engine import BUILDINGS
    return tuple(BUILDINGS)


def instalacao(chave: str, nivel) -> dict:
    """Uma instalação: o nível gravado, o número do efeito e o custo do próximo."""
    from core.sect_engine import building_effect_value, calculate_upgrade_cost
    lv = int(nivel or 0)
    return {
        "key": chave,
        "level": lv,
        "effect_n": int(building_effect_value(chave, lv)),
        "next_cost": int(calculate_upgrade_cost(lv)),
    }


def planta(sect) -> list[dict]:
    """As seis instalações de uma guilda (a entidade ``Sect``), pela ordem do motor."""
    return [instalacao(k, getattr(sect, k + "_lvl", 0)) for k in instalacoes()]


def retrato(chave: str, nivel, tesouro) -> dict:
    """O que a melhoria muda: o nível da instalação (com o número do efeito e o
    custo do próximo nível, do motor) e o tesouro que a pagou.

    O ``next_cost`` viaja no retrato porque a tela o mostra ANTES do toque: sem
    ele, o bloco do próximo nível sumia até a releitura e reaparecia 70 px mais
    abaixo (olhado a 390 — o botão fugia para trás da barra)."""
    from core.sect_engine import building_effect_value, calculate_upgrade_cost
    lv = int(nivel or 0)
    return {
        "key": chave,
        "level": lv,
        "effect_n": int(building_effect_value(chave, lv)),
        "next_cost": int(calculate_upgrade_cost(lv)),
        "treasury": int(tesouro or 0),
    }


def ganho(antes: dict, depois: dict) -> dict | None:
    """``guilda_ganho`` — o ganho CONFIRMADO de uma melhoria.

    ``acende`` leva só a conquista que SUBIU (o nível). Uma acção que não mudou
    nem o nível nem o tesouro não tem ganho a dizer.
    """
    if antes is None or depois is None:
        return None
    acende = [eixo for eixo, campo in _CONQUISTA.items()
              if int(depois[campo]) > int(antes[campo])]
    if not acende and int(depois["treasury"]) == int(antes["treasury"]):
        return None
    return {"antes": antes, "depois": depois, "acende": acende}


async def _ler(session, player_id: int, chave: str, trancar: bool):
    from sqlalchemy import select
    from database.models import Sect, SectMember
    coluna = getattr(Sect, chave + "_lvl", None)
    if coluna is None:
        return None
    q = (select(coluna, Sect.spirit_stones)
         .join(SectMember, SectMember.sect_id == Sect.id)
         .where(SectMember.player_id == player_id))
    if trancar:
        q = q.with_for_update(of=Sect)
    row = (await session.execute(q)).first()
    if row is None:
        return None
    return retrato(chave, row[0], row[1])


async def ler_antes(session, player_id: int, chave: str) -> dict | None:
    """O retrato ANTES do motor, ou ``None`` se o jogador não é de guilda nenhuma.

    ⚠️ As três escolhas da 3.3 e da 4.1, pela mesma razão:
      · **só colunas** (não a entidade) — uma entidade carregada aqui ficaria no
        mapa de identidade com os valores DESTA leitura;
      · **trancada** (``FOR UPDATE OF sects``) e ANTES de a rota carregar a
        guilda (``get_player_sect_info``): o motor (``upgrade_building``) não
        tranca e calcula ``spirit_stones - custo`` em Python — medido no ``main``,
        30 pares de melhorias da mesma guilda por pessoas diferentes a menos de
        2 s (maio). Com a linha trancada primeiro, a entidade que o motor usa já
        é a da linha trancada, e duas melhorias ao mesmo tempo esperam uma pela
        outra em vez de pagarem sobre um tesouro velho;
      · **só com a onda** — quem chama decide (``if _onda_on()``): sem ela, nem
        consulta nem trinco a mais.
    """
    return await _ler(session, player_id, chave, trancar=True)


async def ganho_da_acao(session, player_id: int, chave: str, antes) -> dict | None:
    """O ganho de uma melhoria que o motor CONFIRMOU. ``antes`` é o que
    ``ler_antes`` devolveu; sem ele (onda desligada, sem guilda) não há ganho —
    e nenhuma consulta.

    O "depois" relê as MESMAS colunas na mesma transacção — o autoflush leva
    primeiro as escritas pendentes do motor, portanto é exactamente o que o
    ``commit`` a seguir vai gravar.
    """
    if antes is None:
        return None
    depois = await _ler(session, player_id, chave, trancar=False)
    return ganho(antes, depois)


def no_payload(g: dict | None, flag: Flag | None = None) -> dict:
    """``{"guilda_ganho": g}`` com a onda; ``{}`` sem ela. O MESMO espelho da
    chave-mestra das portas (``core/portas.onda_on``)."""
    if g is None:
        return {}
    from core.portas import onda_on
    return {"guilda_ganho": g} if onda_on(flag) else {}


def planta_no_payload(sect, flag: Flag | None = None) -> dict:
    """``{"planta": [...]}`` na aba da guilda, só com a onda. Sem ela o payload
    é o de hoje, chave a chave."""
    from core.portas import onda_on
    return {"planta": planta(sect)} if onda_on(flag) else {}
