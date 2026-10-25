# -*- coding: utf-8 -*-
"""層 AS MASMORRAS — o dono de "onde a expedição está e o que o andar CONFIRMOU" (4.3).

A linha é do Astra (`Olho/Astra/2026-09-16-e-o-corpo-que-acende.md`, «Mundo ·
Masmorras»), textual:

  *"Corte da masmorra em patamares. `active_run.current_floor / floor_count`
  posiciona a expedição; os andares comprovadamente ultrapassados ficam
  marcados. Estar num andar não significa tê-lo concluído. `max_floor_reached`
  aparece como melhor alcance, separado do percurso atual e por dificuldade."*

Três famílias de estado, e só duas acendem:

  * **conquista** — o ANDAR vencido nesta expedição (o andar sobe só dentro do
    ramo da vitória: ``enter``/``advance`` gravam ``current_floor`` e
    ``max_floor_reached`` DENTRO do ``if won``; o chefe grava a conclusão no fim
    do duelo) e a DIFICULDADE concluída (``best_difficulty`` sobe). Acendem UMA
    vez, na confirmação, e ficam;
  * **leitura** — a posição (``current_floor / floor_count``), o andar mais
    fundo já vencido nesta masmorra em qualquer dificuldade
    (``max_floor_reached``, com o heal derivado de 23/07), o próximo andar;
  * **nunca acende** — a Vida e o Qi (reservas), o saco da expedição (espólio
    por levar), o recuo e a varredura (não sobem nada), a morte (o percurso
    volta ao zero — o melhor alcance fica).

── O QUE SE MEDIU ANTES DE ESCREVER ISTO (2026-10-08) ───────────────────────

`tools/db_readonly_masmorras_1008.py`, só leitura:

  main  22 dos 36 jogadores activos mexeram em masmorras em 30 dias; 2 duelos
        do chefe em 30 dias (533 no total, 303 em maio) — o `main` VARRE
        (~21 jogadores em 30 dias, estimativa); 19 runs abertas, 16 com mais de
        58 dias
  s2    10 dos 16 activos mexeram em 30 dias; **1.822 duelos do chefe em 30
        dias** (8 jogadores; um só faz 1.687, mediana de 48 s entre chefes);
        2 runs abertas, as duas à porta do chefe

⚠️ "Alcançado" no prompt era "subir ao entrar": medido, NÃO — ``current_floor``
e ``max_floor_reached`` só se escrevem no ramo da vitória (as três rotas e o
chat), e o andar do chefe só no fim do duelo ganho. Portanto ``current_floor =
N`` quer dizer "N vencido nesta expedição; o próximo a lutar é N+1" — e é por
isso que a tela diz "vencidos" e "próximo", nunca "está no andar N".

⚠️ "Por dificuldade" NÃO existe no servidor: um ``max_floor_reached`` e um
``best_difficulty`` por masmorra. O que se pode dizer por dificuldade é o que o
próprio servidor deixa fazer — as dificuldades ≤ ``best_difficulty`` são
varríveis (o gate do sweep). O andar mais fundo POR dificuldade não se inventa
(lei §5.2): fica escrito em `O_MUNDO.md` §5 (31 linhas no `main` e 1 no Beta
têm um alcance acima dos andares da melhor dificuldade concluída — numa
dificuldade que ninguém sabe qual foi).

── AS FAMÍLIAS DE ESCRITORES (contadas no código) ─────────────────────────

  * as rotas do mini-app (`core/webserver.py`): ``dungeons/enter`` (o andar 1),
    ``dungeons/advance`` (o andar seguinte, e a conclusão sem chefe — o ramo de
    segurança, medido morto: 0 runs com ``current_floor >= floor_count``),
    ``dungeons/retreat`` (só põe o percurso a zero);
  * o fim do duelo do chefe (`core/pve_duel_settle._settle_dungeon_boss`): a
    conclusão (o último andar, a dificuldade) ou a derrota;
  * o chat (`handlers/dungeons.py`) — legado, só no `main`, sem luz.

── O QUE ESTE FICHEIRO FAZ, e só isto ─────────────────────────────────────

1. **O alcance** (``alcance``) — o andar mais fundo já vencido, com o heal de
   23/07 (concluída na dificuldade X ⇒ venceu o último andar de X). A lista
   (``dungeons/list``) lê ESTE — uma conta, nunca duas.
2. **O corte** (``retrato``) — ``{dungeon_id, current_floor, difficulty,
   floor_count, max_floor_reached, best_difficulty, completed}``: o que a tela
   da expedição desenha, tudo do servidor.
3. **O ganho** (``ganho``) — ``{"antes", "depois", "acende", "andar"}`` de uma
   acção confirmada. O "antes" lê-se na MESMA transacção, só colunas, com a
   linha TRANCADA e antes de a rota carregar a entidade; o "depois" relê as
   mesmas colunas depois das escritas. ``acende`` ⊆ ``("andar", "dificuldade")``.

⚠️ O corte e o ganho só viajam com a onda ligada (chaves CONDICIONAIS): o
``main`` recebe as respostas de hoje, byte a byte — e sem a onda nem o "antes"
se lê (zero consultas a mais, zero trincos a mais).
"""
from __future__ import annotations

from typing import Callable

Flag = Callable[[str], bool]

# As conquistas — e só estas acendem. A posição, o alcance e o saco não.
EIXOS_QUE_ACENDEM = ("andar", "dificuldade")


def _ordem() -> dict:
    """``{"easy": 1, …, "nightmare": 4}`` — a do MOTOR, nunca uma cópia."""
    from handlers.dungeons import DIFF_ORDER
    return DIFF_ORDER


def dificuldade_de(nivel) -> str | None:
    """A chave de um ``best_difficulty`` (1..4); ``None`` para 0."""
    n = int(nivel or 0)
    for chave, v in _ordem().items():
        if int(v) == n:
            return chave
    return None


def andares(dungeon, dificuldade) -> int:
    """O número de andares de uma dificuldade — a conta do MOTOR
    (``_get_floor_count``: a coluna ``floor_counts`` ou ``floor_count``)."""
    from handlers.dungeons import _get_floor_count
    return int(_get_floor_count(dungeon, dificuldade) or 0)


def alcance(dungeon, max_floor_reached, completed, best_difficulty) -> int:
    """O andar mais fundo já vencido nesta masmorra, em QUALQUER dificuldade.

    Fix 2026-07-23 (report [jogador]): o settle do chefe esquecia o último andar no
    ``max_floor_reached`` (30 completos → "29"). O heal é DERIVADO (zero
    migration, zero UPDATE em massa): concluiu na dificuldade X ⇒ venceu o
    último andar de X. Vivia escrito à mão dentro da lista; agora é este — a
    lista e o ganho dizem o MESMO número.
    """
    mf = int(max_floor_reached or 0)
    bd = int(best_difficulty or 0)
    if bool(completed) and bd > 0:
        mf = max(mf, andares(dungeon, dificuldade_de(bd)))
    return mf


def retrato(dungeon, current_floor, max_floor_reached, best_difficulty, completed,
            difficulty) -> dict:
    """O corte de uma masmorra para um jogador: a posição da expedição (se há
    uma), o alcance e as dificuldades concluídas. Tudo das colunas."""
    dif = difficulty if difficulty in _ordem() else None
    cur = int(current_floor or 0)
    return {
        "dungeon_id": int(dungeon.id),
        "current_floor": cur,
        "difficulty": dif,
        # os andares do PERCURSO — os da dificuldade da expedição; sem
        # expedição não há percurso, logo nenhum denominador (lei §5.2)
        "floor_count": andares(dungeon, dif) if dif else None,
        "max_floor_reached": alcance(dungeon, max_floor_reached, completed, best_difficulty),
        "best_difficulty": int(best_difficulty or 0),
        "completed": bool(completed),
    }


def retrato_de(dungeon, pd_row) -> dict:
    """O corte a partir da entidade ``PlayerDungeon`` (a lista já a carregou)."""
    return retrato(dungeon, pd_row.current_floor, pd_row.max_floor_reached,
                   pd_row.best_difficulty, pd_row.completed, pd_row.difficulty)


def _andar_confirmado(antes: dict, depois: dict, andar: int) -> bool:
    """As colunas do "antes" e do "depois" PROVAM o andar que a rota diz ter
    vencido.

    · um andar do percurso: a expedição avançou UM andar nesta acção e ficou
      nele (``antes + 1 == andar == depois``);
    · o último (o chefe, ou a conclusão sem chefe): havia percurso, o andar é o
      ÚLTIMO dele, o percurso acabou (``current_floor == 0``), a masmorra está
      concluída e o alcance chega lá.

    ⚠️ Medido a escrever isto: só com o "depois", um andar passado no ramo da
    MORTE de uma masmorra já concluída passava (o percurso a zero e o
    ``completed`` antigo pareciam uma conclusão). As colunas não distinguem a
    vitória do chefe da derrota quando a masmorra já estava concluída — quem o
    distingue é o ramo que passa o andar, e a guarda (§36) afirma que só o ramo
    da vitória o passa.
    """
    a = int(andar)
    if int(depois["current_floor"]) == a and a == int(antes["current_floor"]) + 1:
        return True
    return (int(antes["current_floor"]) > 0 and a == int(antes["floor_count"] or 0)
            and int(depois["current_floor"]) == 0 and bool(depois["completed"])
            and int(depois["max_floor_reached"]) >= a)


def ganho(antes: dict, depois: dict, andar=None) -> dict | None:
    """``masmorra_ganho`` — o ganho CONFIRMADO de uma acção.

    ``andar`` é o andar que a acção VENCEU — quem o passa é o ramo da vitória
    (``1`` no ``enter``, ``next_floor`` no ``advance``, ``floor_count`` na
    conclusão); a morte, o recuo e a varredura não passam nenhum. As colunas do
    "depois" têm de o provar (``_andar_confirmado``). ``dificuldade`` acende
    quando ``best_difficulty`` SOBE. Uma acção que não acendeu nada não tem
    ganho a dizer (a morte diz-se no modal de hoje).
    """
    if antes is None or depois is None:
        return None
    acende = []
    if andar is not None and int(andar) > 0 and _andar_confirmado(antes, depois, int(andar)):
        acende.append("andar")
    if int(depois["best_difficulty"]) > int(antes["best_difficulty"]):
        acende.append("dificuldade")
    if not acende:
        return None
    return {
        "antes": antes,
        "depois": depois,
        "acende": acende,
        "andar": int(andar) if "andar" in acende else None,
    }


async def _ler(session, player_id: int, dungeon, trancar: bool) -> dict:
    from sqlalchemy import select
    from database.models import PlayerDungeon
    q = (select(PlayerDungeon.current_floor, PlayerDungeon.max_floor_reached,
                PlayerDungeon.best_difficulty, PlayerDungeon.completed,
                PlayerDungeon.difficulty)
         .where(PlayerDungeon.player_id == player_id,
                PlayerDungeon.dungeon_id == int(dungeon.id)))
    if trancar:
        q = q.with_for_update(of=PlayerDungeon)
    row = (await session.execute(q)).first()
    if row is None:
        # COMPAT: quem nunca entrou nesta masmorra não tem linha — e a rota
        # cria-a com zeros (`enter`). Aqui o zero É o dado do servidor (nenhum
        # andar vencido, nenhuma dificuldade), não a falta dele.
        return retrato(dungeon, 0, 0, 0, False, None)
    return retrato(dungeon, row[0], row[1], row[2], row[3], row[4])


async def ler_antes(session, player_id: int, dungeon) -> dict:
    """O corte ANTES da acção.

    ⚠️ As três escolhas da 3.3, da 4.1 e da 4.2, pela mesma razão:
      · **só colunas** (não a entidade) — uma entidade carregada aqui ficaria no
        mapa de identidade com os valores DESTA leitura;
      · **trancada** (``FOR UPDATE OF player_dungeons``) e ANTES de a rota
        carregar a linha. A ordem dos trincos é a de todas as famílias: o
        jogador primeiro (``enter``/``advance``/``retreat``/``sweep`` e o
        ``settle_pve_duel`` trancam ``players``), a linha da masmorra depois —
        nunca ao contrário, portanto sem deadlock;
      · **só com a onda** — quem chama decide (``if _onda_on()``): sem ela, nem
        consulta nem trinco a mais.
    """
    return await _ler(session, player_id, dungeon, trancar=True)


async def ganho_da_acao(session, player_id: int, dungeon, antes, andar=None) -> dict | None:
    """O ganho de uma acção que o servidor CONFIRMOU. ``antes`` é o que
    ``ler_antes`` devolveu; sem ele (onda desligada) não há ganho — e nenhuma
    consulta.

    O "depois" relê as MESMAS colunas na mesma transacção — o autoflush leva
    primeiro as escritas pendentes da rota, portanto é exactamente o que o
    ``commit`` a seguir vai gravar.
    """
    if antes is None:
        return None
    depois = await _ler(session, player_id, dungeon, trancar=False)
    return ganho(antes, depois, andar)


def no_payload(g: dict | None, flag: Flag | None = None) -> dict:
    """``{"masmorra_ganho": g}`` com a onda; ``{}`` sem ela. O MESMO espelho da
    chave-mestra das portas (``core/portas.onda_on``)."""
    if g is None:
        return {}
    from core.portas import onda_on
    return {"masmorra_ganho": g} if onda_on(flag) else {}


def corte_no_payload(dungeon, pd_row, flag: Flag | None = None) -> dict:
    """``{"corte": {...}}`` na expedição aberta da lista, só com a onda. Sem ela
    o ``active_run`` é o de hoje, chave a chave."""
    from core.portas import onda_on
    return {"corte": retrato_de(dungeon, pd_row)} if onda_on(flag) else {}
