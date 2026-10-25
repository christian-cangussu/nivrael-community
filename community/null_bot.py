# -*- coding: utf-8 -*-
"""O bot que não existe.

O agendador (`core.scheduler.init_scheduler`) e os avisos
(`core.announcement_engine.set_bot`) foram escritos para o Telegram: quando uma
meditação acaba, mandam uma DM. Sem bot, essa DM não tem para onde ir — e o
ciclo não pode partir por isso.

Este objecto responde a QUALQUER chamada do bot com "feito, nada a devolver" e
regista-a no log em nível DEBUG. Quem joga pelo browser já vê tudo isso no
próprio jogo (o sino, a Crónica); a DM era só um eco.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("community.null_bot")


class NullBot:
    """Aceita tudo o que um `telegram.Bot` aceitaria, e não manda nada."""

    id = 0
    username = "nivrael_local"
    first_name = "Nivrael"

    def __getattr__(self, name: str):
        async def _ignorado(*args, **kwargs):
            logger.debug("sem bot: %s(chat_id=%s) ignorado", name, kwargs.get("chat_id"))
            return None
        return _ignorado
