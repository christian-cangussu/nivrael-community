# -*- coding: utf-8 -*-
"""開 O jogo inteiro numa máquina, sem Telegram.

    python -m community.local          # nativo (Postgres em DATABASE_URL)
    docker compose up                  # Postgres + jogo, nada a instalar

Arranca a MESMA aplicação web do jogo oficial (`core.webserver.create_app`), a
mesma base (`database.db.init_db`: migrations e sementes, em cada mundo) e o
mesmo agendador (o cultivo corre, os eventos do mundo acontecem). Só não há bot:
quem joga entra pelo browser, em `/login`.

O que este arranque acrescenta, e só ele:
  • o MUNDO LOCAL, com o jogo de hoje ligado (`local_world.py`), onde nasce
    quem entra — `SIGNUP_WORLD` aponta para ele por defeito;
  • a PORTA LOCAL (`dev_login.py`), só com `NIVRAEL_DEV_LOGIN=1`;
  • o BOT QUE NÃO EXISTE (`null_bot.py`) no lugar das DMs do agendador;
  • um segredo de sessão gerado e guardado em `.nivrael/` quando não há
    `SESSION_SECRET` nem `BOT_TOKEN` (no jogo oficial deriva-se do token).

As variáveis lêem-se do ambiente e do `.env` — ver `.env.example`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import sys

from dotenv import load_dotenv

logger = logging.getLogger("community.local")

STATE_DIR = os.path.abspath(os.getenv("NIVRAEL_STATE_DIR") or ".nivrael")


def _flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes")


def _prepare_env() -> list[str]:
    """Os defaults desta edição — escritos ANTES de qualquer `import config`, que
    lê o ambiente uma vez só. Nada do que o operador definiu é pisado."""
    # o `.env` primeiro (o que lá estiver ganha aos defaults daqui) — o DESTA pasta,
    # nunca o de uma pasta-pai: sem caminho, o `load_dotenv()` sobe até achar um, e
    # uma cópia guardada dentro de outro projecto arrancava com a base dele
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    notas = []
    from community.local_world import WORLD_KEY
    if not os.getenv("SIGNUP_WORLD"):
        os.environ["SIGNUP_WORLD"] = WORLD_KEY
        notas.append(f"SIGNUP_WORLD={WORLD_KEY} (quem entra nasce no mundo local)")
    if _flag("NIVRAEL_DEV_LOGIN") and not os.getenv("NIVRAEL_COOKIE_INSECURE"):
        # http://localhost não é https; sem isto o browser deita fora o cookie
        # da sessão quando se abre o jogo por http://127.0.0.1 ou pelo IP da rede.
        os.environ["NIVRAEL_COOKIE_INSECURE"] = "1"
        notas.append("NIVRAEL_COOKIE_INSECURE=1 (http local, só com a porta local)")
    if not os.getenv("SESSION_SECRET") and not os.getenv("BOT_TOKEN"):
        os.makedirs(STATE_DIR, exist_ok=True)
        path = os.path.join(STATE_DIR, "session_secret")
        if os.path.isfile(path):
            secret = open(path, encoding="utf-8").read().strip()
        else:
            secret = secrets.token_urlsafe(48)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(secret + "\n")
            notas.append(f"SESSION_SECRET gerado em {path}")
        os.environ["SESSION_SECRET"] = secret
    return notas


async def run() -> None:
    from aiohttp import web

    from community import dev_login, local_world
    from community.null_bot import NullBot
    from core.webserver import create_app
    from database.db import init_db

    host = (os.getenv("NIVRAEL_HTTP_HOST") or "127.0.0.1").strip()
    port = int(os.getenv("NIVRAEL_HTTP_PORT") or "8080")

    app = create_app()
    porta_aberta = dev_login.install(app)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("🌐 a servir em http://%s:%d (a base ainda está a arrancar)", host, port)

    await init_db()
    estado = await local_world.ensure()
    logger.info("mundo local %r: %s", local_world.WORLD_KEY, estado)

    bot = NullBot()
    from core.scheduler import init_scheduler
    init_scheduler(bot)
    from core.announcement_engine import set_bot
    set_bot(bot)

    # `/healthz` lê a prontidão do `main.py` do jogo oficial — o mesmo contrato.
    import main as _main
    _main._READY = True

    shown = "localhost" if host in ("0.0.0.0", "127.0.0.1", "::") else host
    logger.info("☯️ Nivrael local pronto — http://%s:%d/%s", shown, port,
                "login" if porta_aberta else "play")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def main() -> int:
    notas = _prepare_env()
    logging.basicConfig(
        level=(os.getenv("NIVRAEL_LOG_LEVEL") or "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for n in notas:
        logger.info("· %s", n)
    if not (os.getenv("DATABASE_URL") or "").strip():
        logger.error("DATABASE_URL vazio — o jogo precisa de um Postgres. Ver .env.example "
                     "(ou `docker compose up`, que traz um).")
        return 2
    if sys.platform == "win32":
        # O loop "Proactor" do Windows despeja um ConnectionResetError no log por
        # cada ligação que o browser fecha (defeito conhecido do asyncio). No
        # Docker, que é Linux, nada disto existe.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("até à próxima meditação")
    return 0


if __name__ == "__main__":
    sys.exit(main())
