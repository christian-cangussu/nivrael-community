# -*- coding: utf-8 -*-
"""🐾 AS BESTAS — o dono de "o que esta besta É e o que a acção CONFIRMOU" (3.3).

A linha é do Astra (`Olho/Astra/2026-09-16-e-o-corpo-que-acende.md`, «Caverna ·
Bestas»), textual:

  *"A besta selecionada, com um selo de crescimento junto dela.
  `beasts/list.owned[]`: `level / max_level`, `exp / exp_needed`, `rank`,
  `art_key`. XP desenvolve o traço; nível/evolução confirmados fixam a marca.
  `is_companion` e `is_on_expedition` mostram função/atividade. Não somar
  todas as bestas num animal ou nível fictício."*

Três famílias de estado, e só uma acende:

  * **conquista** — o NÍVEL e o POSTO (a evolução) confirmados. Acendem UMA vez,
    na confirmação, e ficam;
  * **traço** — o XP a caminho do próximo nível (``exp / exp_needed``), sempre
    com o número;
  * **nunca acende** — companheira, expedição, pedras, núcleos, os bónus.
    *"Uma luz que não significa progresso é árvore de Natal."*

── O QUE SE MEDIU ANTES DE ESCREVER ISTO (2026-10-01) ───────────────────────

`tools/db_readonly_bestas_1001.py`, só leitura:

  main  242 jogadores · 1.107 bestas · p50 = 1 besta (148 só têm a inicial),
        p90 = 16, máx. 32 · 288 no nível 100 (162 com XP a sobrar no tecto) ·
        74 já evoluíram · 124 prontas a evoluir agora
  s2     38 jogadores ·    70 bestas · p50 = 1, máx. 10

E no código: o limiar de XP (``level × 100``) estava escrito à mão em OITO
sítios — hoje é ``beast_engine.limiar_xp`` —, e a linha da lista era um dict
montado dentro do endpoint, que o arnês copiava à mão com a evolução errada
para todas as bestas ("Próximo posto: Uncommon" numa besta Incomum).

── O QUE ESTE FICHEIRO FAZ, e só isto ─────────────────────────────────────

1. **A linha** (``serializar``) de ``beasts/list.owned[]`` — a MESMA forma de
   sempre, chave a chave e pela mesma ordem. Saiu do endpoint para que o arnês
   a peça ao mesmo dono (um mock com a forma escrita à mão mente antes do
   código).
2. **O retrato** (``retrato``) — o subconjunto que cresce: nível, XP, posto e os
   bónus que a besta dá como companheira. As MESMAS chaves da linha, para o
   cliente pôr o "depois" por cima do que já mostra.
3. **O ganho** (``ganho``) — ``{"antes", "depois", "acende"}`` de uma acção
   confirmada (treinar, treinar ×N, evoluir, recolher a expedição). O "antes"
   lê-se na MESMA transacção, com a linha da besta TRANCADA, antes do motor;
   o "depois" é o objecto que o motor acabou de mudar. **Nunca se deriva do
   "depois" menos o ganho** — um lote sobe vários níveis, e o tecto do nível
   100 come XP.

⚠️ O ganho só viaja com a onda ligada (``besta_ganho`` é chave CONDICIONAL): o
``main`` recebe as respostas de hoje, byte a byte — e sem a onda nem o "antes"
se lê (zero consultas a mais, zero trincos a mais).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Callable

Flag = Callable[[str], bool]

# As conquistas — o único campo cuja SUBIDA acende. O XP (o traço) sobe muitas
# vezes sem acender nada. Um eixo fora daqui não existe: é aqui que "o que nunca
# acende" deixa de ser prosa.
_CONQUISTA = {"nivel": "level", "posto": "rank_idx"}
EIXOS_QUE_ACENDEM = tuple(_CONQUISTA)


def _ms(dt) -> int | None:
    """O mesmo ``_ms`` do ``core/webserver`` (segundos UTC × 1000)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _bonus(beast, catalog) -> dict:
    """Os bónus EFECTIVOS (evolução + nível) para as chaves que a espécie tem —
    a mesma conta que o combate e o cultivo aplicam (``get_companion_bonuses``)."""
    from core.beast_engine import get_companion_bonuses
    raw = dict(catalog.base_stats) if catalog is not None and catalog.base_stats else {}
    out: dict = {}
    if catalog is not None:
        calc = get_companion_bonuses(beast, catalog)
        for key, val in raw.items():
            out[key] = float(calc.get(key, val))
    return out


def retrato(beast, catalog) -> dict:
    """O que CRESCE nesta besta, com as chaves da linha de ``beasts/list``.

    ⚠️ ``exp_needed`` é o limiar do motor mesmo no nível 100 — é o que a lista
    manda hoje, e a OFF-identidade não deixa mudá-lo. O cliente lê o tecto em
    ``level >= max_level`` (os DOIS números vêm daqui) e escreve "Limite atual":
    os 162 com XP a sobrar no 100 não podem ver um fio que nunca enche.
    """
    from config import BEAST_MAX_LEVEL, BEAST_RANK_INDEX
    from core.beast_engine import limiar_xp
    return {
        "level": int(beast.level),
        "max_level": BEAST_MAX_LEVEL,
        "exp": int(beast.exp or 0),
        "exp_needed": limiar_xp(beast.level),
        "rank": beast.rank,
        "rank_idx": BEAST_RANK_INDEX.get(beast.rank, 0),
        "effective_stats": _bonus(beast, catalog),
    }


def serializar(b, cat, lang: str, food_mult: float = 1.0) -> dict:
    """Uma linha de ``beasts/list.owned[]``.

    ⚠️ AS MESMAS CHAVES, PELA MESMA ORDEM, de quando isto vivia dentro do
    ``_build_beasts_payload`` — a §33 compara-as. A única diferença de valor é
    a habilidade, que passa a vir na língua do dono (``beast_ability_text``;
    sem tradução, a frase de hoje).
    """
    from config import BEAST_TRAIN_COST_PER_LEVEL, BEAST_TRAIN_EXP_PER_LEVEL
    from core.beast_engine import (get_evolution_requirements, beast_display_name,
                                   beast_art_key, beast_ability_text)
    r = retrato(b, cat)
    return {
        "id": int(b.id),
        "catalog_id": int(b.catalog_id),
        "name": beast_display_name(lang, b, cat),
        # 🔴 a chave que mantém as 15 peças de arte vivas depois da tradução
        # — sem ela o cliente monta `beast-boi-do-trovao` e a carta cai no
        # verso, em silêncio (a avaria de 14/09, 229 peças).
        "art_key": beast_art_key(cat),
        "rank": r["rank"],
        "rank_idx": r["rank_idx"],
        "level": r["level"],
        "max_level": r["max_level"],
        "exp": r["exp"],
        "exp_needed": r["exp_needed"],
        "is_companion": bool(b.is_companion),
        "is_on_expedition": bool(b.is_on_expedition),
        "expedition_returns_at_ms": _ms(b.expedition_returns_at),
        "emoji": cat.emoji if cat else "🐾",
        "element": cat.element if cat else "",
        "special_ability": beast_ability_text(lang, cat) if cat else "",
        # Bug fix 2026-05-23 ([jogador]): `base_stats` (o catálogo) E
        # `effective_stats` (evoluído + nível) — o detalhe mostrava +20% de
        # Percepção numa Lendária L1 e numa Divina L100.
        "base_stats": dict(cat.base_stats) if cat and cat.base_stats else {},
        "effective_stats": r["effective_stats"],
        "evolution": get_evolution_requirements(b),
        "train_cost": int(BEAST_TRAIN_COST_PER_LEVEL * b.level),
        "train_xp_per_step": int(BEAST_TRAIN_EXP_PER_LEVEL * food_mult),
    }


def ganho(antes: dict, depois: dict) -> dict:
    """``besta_ganho`` — o ganho CONFIRMADO de uma acção sobre UMA besta.

    ``acende`` leva só as conquistas que SUBIRAM (o nível, o posto). Vários
    níveis de um lote assentam juntos, com um resumo — não há uma fila de
    celebrações (Astra §1).
    """
    acende = [eixo for eixo, campo in _CONQUISTA.items()
              if int(depois[campo]) > int(antes[campo])]
    return {"antes": antes, "depois": depois, "acende": acende}


async def ler_antes(session, player_id: int, beast_id: int):
    """O retrato ANTES do motor — ``(retrato, catálogo)``, ou ``None`` se a besta
    não é do jogador (o motor diz a recusa à sua maneira).

    ⚠️ TRÊS escolhas, cada uma por uma razão medida:
      · **só colunas** (não a entidade): uma entidade carregada aqui ficaria no
        mapa de identidade, e a consulta do motor devolveria ESTE objecto com os
        valores DESTA leitura — a recolha da expedição trancava a linha para
        apanhar o ``is_on_expedition`` fresco (fix SEC de 01/06) e passaria a
        ler o velho: recolha a dobrar;
      · **trancada** (``FOR UPDATE``): o "antes" e o motor vêem a MESMA linha —
        sem isto, um treino noutra janela entre a leitura e o motor seria
        atribuído a esta acção (Astra: *"não atribuir à ação diferenças vindas
        de outra atualização"*);
      · **só com a onda**: sem ela ninguém chama isto — nem consulta nem trinco a
        mais no ``main``.
    """
    from sqlalchemy import select
    from database.models import PlayerBeast
    from core.beast_engine import get_beast_catalog_by_id
    row = (await session.execute(
        select(PlayerBeast.level, PlayerBeast.exp, PlayerBeast.rank, PlayerBeast.catalog_id)
        .where(PlayerBeast.player_id == player_id, PlayerBeast.id == beast_id)
        .with_for_update()
    )).first()
    if row is None:
        return None
    cat = await get_beast_catalog_by_id(session, row.catalog_id)
    return (retrato(SimpleNamespace(level=row.level, exp=row.exp, rank=row.rank), cat), cat)


async def ganho_da_acao(session, beast_id: int, antes) -> dict | None:
    """O ganho de uma acção que o motor CONFIRMOU. ``antes`` é o que
    ``ler_antes`` devolveu; sem ele (onda desligada, besta alheia) não há ganho.

    O "depois" é o objecto que o motor mudou, tirado do mapa de identidade da
    sessão (``session.get`` não emite SQL quando o objecto já lá está) — é
    exactamente o que o ``commit`` a seguir vai gravar.
    """
    if antes is None:
        return None
    from database.models import PlayerBeast
    r0, cat = antes
    b = await session.get(PlayerBeast, beast_id)
    if b is None:
        return None
    return ganho(r0, retrato(b, cat))


def no_payload(g: dict | None, flag: Flag | None = None) -> dict:
    """``{"besta_ganho": g}`` com a onda; ``{}`` sem ela. O MESMO espelho da
    chave-mestra das portas (``core/portas.onda_on``)."""
    if g is None:
        return {}
    from core.portas import onda_on
    return {"besta_ganho": g} if onda_on(flag) else {}
