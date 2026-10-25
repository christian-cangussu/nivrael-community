"""QoL-relatos — Uma masmorra de cada vez (report do jogador [jogador], 28/07/2026).

O MV-1 ancorou cada portal a um continente e a viagem ganhou cooldown de 4h.
Estar "dentro" de três masmorras em três continentes ao mesmo tempo desmente
a geografia que a onda anterior construiu — soa a menu, não a Wuxia (Lei §2).
Uma run aberta é `PlayerDungeon.current_floor > 0`.

UM helper (`active_run`) para os CINCO caminhos que podem abrir/consumir uma
run — chat: o ecrã de dificuldade, a entrada real (`dng_go_`) e a varredura;
mini: `dungeons/enter` e `dungeons/sweep`. Nenhuma cópia da regra em lado
nenhum: a query vive aqui.

Tudo atrás da flag per-world ``masmorra_unica`` (OFF por defeito → main
byte-idêntico; ver DEFAULT_WORLD_FEATURES em database/db.py).

A política, decidida e documentada (§2 do prompt pedia a decisão):
- **Entrar** noutra masmorra com uma run aberta → RECUSADO. A recusa diz o
  NOME e o ANDAR e oferece **Retirar-se** ali mesmo (Lei §1: um "não" sem
  saída é violação).
- **Entrar na MESMA** masmorra onde a run está aberta → inalterado. O mini já
  tem o seu `already_in_run` (MA-30b) e o chat tem o seu fluxo de retomar;
  esta onda não mexe em nenhum dos dois — o guard filtra por `exclude`.
- **Varrer (sweep) outra** masmorra já concluída → LIVRE, mesmo com uma run
  aberta noutro lado. A varredura é "revisitar o que você já dominou", não
  uma expedição: gatear isso mataria a QoL do sweep sem ganho de geografia
  (recomendação do próprio §2, adotada).
- **Varrer a masmorra onde você ESTÁ** (run aberta na mesma masmorra que se
  varre) → RECUSADO. `completed` e `current_floor` são colunas independentes,
  portanto isto é possível hoje e paga duas vezes: a varredura entrega o loot
  de uma limpeza inteira enquanto a run manual guarda o seu próprio saco.
  Aqui a recusa é literal — você está lá dentro.

Regras de casa (padrão dungeon_regions/reputation_engine — tudo fail-safe):
- Flag OFF → `masmorra_unica_on()` False → `active_run` devolve None SEM uma
  única query (OFF-identity provada em scripts/_test_qol_relatos.py).
- O engine NÃO abre sessões, não commita e não levanta: um erro aqui nunca
  pode trancar o jogador fora de uma masmorra (falha = deixa passar).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

logger = logging.getLogger(__name__)


def masmorra_unica_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (padrão regionais_on). Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("masmorra_unica", world_key))
    except Exception:
        return False


async def active_run(session, player_id: int, *, only: int | None = None,
                     exclude: int | None = None) -> dict[str, Any] | None:
    """A run aberta do jogador, ou None. UMA verdade para os 5 caminhos.

    `only=<id>`    → considera SÓ a masmorra `<id>` (usado pela varredura:
                     "você está dentro da masmorra que quer varrer").
    `exclude=<id>` → ignora a masmorra `<id>` (usado pelas entradas: a mesma
                     masmorra mantém o comportamento de hoje, intocado).

    Nunca levanta e nunca faz query com a flag OFF. O dict traz o que a recusa
    precisa para ser honesta (Lei §1): nome, emoji, andar e dificuldade — e o
    `dungeon_id`, que é o que constrói o botão `dng_retreat_<id>`.
    """
    try:
        if not masmorra_unica_on():
            return None
        from database.models import DungeonCatalog, PlayerDungeon
        stmt = (
            select(PlayerDungeon, DungeonCatalog)
            .join(DungeonCatalog, DungeonCatalog.id == PlayerDungeon.dungeon_id)
            .where(
                PlayerDungeon.player_id == int(player_id),
                PlayerDungeon.current_floor > 0,
            )
            # Determinístico: com estado legado (há 2 jogadores em prod com 2
            # runs simultâneas em 27/07) a recusa tem de nomear SEMPRE a mesma
            # masmorra, senão o botão Retirar-se dança entre pedidos.
            .order_by(PlayerDungeon.dungeon_id)
            .limit(1)
        )
        if only is not None:
            stmt = stmt.where(PlayerDungeon.dungeon_id == int(only))
        if exclude is not None:
            stmt = stmt.where(PlayerDungeon.dungeon_id != int(exclude))
        row = (await session.execute(stmt)).first()
        if row is None:
            return None
        pd, dungeon = row[0], row[1]
        return {
            "dungeon_id": int(pd.dungeon_id),
            "name": str(getattr(dungeon, "name", "") or ""),
            "emoji": str(getattr(dungeon, "emoji", "") or "🗺️"),
            "current_floor": int(pd.current_floor or 0),
            "difficulty": pd.difficulty or "normal",
        }
    except Exception:
        # Fail-open DE PROPÓSITO: se a query falhar, o jogador entra como
        # hoje. O contrário trancaria a masmorra por um erro de infra.
        logger.exception("active_run failed (player=%s)", player_id)
        return None
