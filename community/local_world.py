# -*- coding: utf-8 -*-
"""O mundo local — onde quem corre o jogo em casa nasce.

⚠️ Porquê um mundo SECUNDÁRIO e não o `main`: por desenho do jogo, o `main` lê
SEMPRE as flags por defeito, todas desligadas (`database.db.get_world_features`)
— é assim que o jogo oficial protege o Mundo Legado. O jogo de hoje (o corpo, o
mapa, as masmorras em patamares, a pele, as cartas…) vive em mundos secundários
com as flags ligadas. Este módulo cria um, com as 40 ligadas, pelo MESMO caminho
que o jogo oficial usa para criar os seus (`core.world_provision.provision_world`:
base própria, migrations, sementes, registo no plano de controlo).

O mundo nasce sandbox (sem compras reais), público e sem código de acesso. Só é
criado uma vez: nos arranques seguintes, `init_db()` já o inicializa como a
qualquer outro mundo registado, e as flags que o operador mudar no painel ficam.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("community.local_world")

WORLD_KEY = (os.getenv("NIVRAEL_LOCAL_WORLD") or "local").strip().lower()
WORLD_NAME = (os.getenv("NIVRAEL_LOCAL_WORLD_NAME") or "Mundo Local").strip()


def all_features_on() -> dict:
    """As 40 flags do jogo, todas ligadas — o que o Beta do jogo oficial corre."""
    from database.db import DEFAULT_WORLD_FEATURES
    return {k: True for k in DEFAULT_WORLD_FEATURES}


async def ensure() -> str:
    """Garante o mundo local. Devolve "existia", "criado" ou "reparado"."""
    from database.db import iter_active_world_keys, set_world_features, get_world_features

    if WORLD_KEY in iter_active_world_keys():
        return "existia"

    from core.world_provision import provision_world
    features = all_features_on()
    logger.info("🌱 a criar o mundo local %r (%s) — base própria, migrations e sementes; "
                "o primeiro arranque demora", WORLD_KEY, WORLD_NAME)
    await provision_world(
        WORLD_KEY, WORLD_NAME,
        balance_config={"features": features},
        requires_code=False, is_public=True, monetization_enabled=False,
        gen_code=False,
    )

    # ⚠️ `provision_world` funde as flags que JÁ estavam guardadas por cima das
    # novas (para um re-provisionamento não apagar o que o admin mudou). Num mundo
    # que ficou a meio — linha criada, flags vazias — isso deixava tudo DESLIGADO.
    # Só então se escrevem as 40; flags guardadas a sério nunca são tocadas.
    from sqlalchemy import text
    from database.control_db import get_control_session_factory
    sm = get_control_session_factory()
    reparado = False
    async with sm() as session:
        res = await session.execute(text(
            "UPDATE servers SET balance_config = jsonb_set(COALESCE(balance_config, '{}'::jsonb), "
            "'{features}', CAST(:f AS JSONB)) "
            "WHERE key = :k AND COALESCE(balance_config->'features', '{}'::jsonb) = '{}'::jsonb"),
            {"f": json.dumps(features), "k": WORLD_KEY})
        await session.commit()
        reparado = bool(res.rowcount)
    if reparado:
        set_world_features(WORLD_KEY, features)

    ligadas = sum(1 for v in get_world_features(WORLD_KEY).values() if v)
    logger.info("✅ mundo local %r pronto — %d flags ligadas", WORLD_KEY, ligadas)
    return "reparado" if reparado else "criado"
