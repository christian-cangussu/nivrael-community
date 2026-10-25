# -*- coding: utf-8 -*-
"""門 AS PORTAS — o dono único de "esta aba abre para ESTE jogador?" (P6).

A decisão é do Astra (MESA ``[017]`` §3, 2026-09-16):

  * **disponível** → entrada normal;
  * **próximo desbloqueio** → entrada trancada e CONSULTÁVEL, com o requisito
    real, o valor actual/limiar e o caminho — no máximo o próximo marco de cada
    hub;
  * **distante** → fora da lista corrente, numa consulta «Desbloqueios».

  *"Omitir uma entrada futura da navegação corrente é permitido; esconder o
  motivo quando ela é apresentada ou procurada, não."*

── O QUE SE MEDIU ANTES DE ESCREVER ISTO (2026-09-27) ───────────────────────

As 24 abas do ``TAB_DEFS`` contra o que o servidor recusa a um jogador R0,
lendo cada endpoint que a aba chama (nunca o mock — ``ok:true`` vazio em 247 de
265 endpoints):

  aba             abre em  dono do limiar (antes deste ficheiro)
  faction         R3       ``webserver.FACTION_MIN_REALM`` + ``handlers/faction
                           .MIN_REALM_FACTION`` — DOIS donos, o mesmo 3 à mão
  celestial       R8       ``celestial_engine.MAHAYANA_REALM``
  body_tempering  R0 / R7  R0 com ``cultivo_corpo_r0`` (o Refino Mortal); sem
                           ela, R7 (``body_tempering_engine.MIN_REALM_REQUIRED``)
  as outras 21    R0       o que recusa lá dentro é um ITEM (uma receita, uma
                           técnica, uma formação), não a aba

🔴 **A navegação não sabia nenhum destes.** Não havia um campo no payload que
os dissesse; o cliente não tem limiar próprio e só lia ``locked``/``unlocked``
DEPOIS de o jogador entrar. É isso que "o jogador entra para descobrir" queria
dizer, medido.

── A REGRA DESTE FICHEIRO ───────────────────────────────────────────────────

**Cada gate de ABA vive aqui, uma vez.** O endpoint da aba decide o seu
``locked`` chamando ESTAS funções, e o ``/player`` manda o mesmo resultado à
navegação. O mesmo predicado dos dois lados, por construção — não por duas
cópias que por acaso concordam hoje.

⚠️ Os limiares NÃO se inventam aqui (Astra: *"Corpo, Facção e Celestial seguem
os bloqueios reais já existentes; não inventar ordem nem limiares"*). Cada
função IMPORTA a constante do motor que já a aplicava.

⚠️ Um gate que rebenta devolve ``{"open": None}`` — estado desconhecido. O
cliente mostra "Verificando" e **nunca** a porta como aberta (a mesma regra:
*"estado desconhecido mostra verificação/erro, sem fingir desbloqueio"*).
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# O único ``kind`` de hoje. Um gate de outra natureza (uma missão, um item)
# entra com o seu próprio ``kind`` e o cliente tem de o saber dizer — é por isso
# que o ``kind`` viaja no payload em vez de se presumir.
KIND_REALM = "realm"

# ── O ESPELHO DA CHAVE-MESTRA ────────────────────────────────────────────────
# O cliente decide "a onda está ligada?" num sítio só, ``ondaCultOn()`` em
# ``miniapp/components/ui.js`` (``a_obra`` OU ``cultivador_jogavel``). O servidor
# precisa da MESMA resposta para decidir se manda as portas, e esta tupla é o
# único sítio onde ele a lê. A guarda §29 compara-a com o ``ui.js``: se uma das
# duas listas ganhar uma chave, fica vermelha.
ONDA_FLAGS = ("a_obra", "cultivador_jogavel")

Flag = Callable[[str], bool]


def _flag(key: str) -> bool:
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world(key))
    except Exception:
        return False


def onda_on(flag: Flag | None = None) -> bool:
    """True quando a onda 2 (a chegada, a lateral, as portas) está ligada."""
    flag = flag or _flag
    return any(flag(k) for k in ONDA_FLAGS)


def _reino(player) -> int:
    return int(getattr(player, "realm", 0) or 0)


def _por_reino(player, need: int) -> dict:
    have = _reino(player)
    if have >= int(need):
        return {"open": True}
    return {"open": False, "kind": KIND_REALM, "need": int(need), "have": have}


# ── As três portas ───────────────────────────────────────────────────────────

def porta_faccao(player, flag: Flag | None = None) -> dict:
    """A Facção abre em ``FACTION_MIN_REALM``. Lida por ``_build_faction_payload``
    e ``api_faction_pick`` — não por uma cópia da comparação."""
    from core.faction_engine import FACTION_MIN_REALM
    return _por_reino(player, FACTION_MIN_REALM)


def porta_celestial(player, flag: Flag | None = None) -> dict:
    """A Celestial abre no Mahayana. Lida por ``api_celestial_status``."""
    from core.celestial_engine import MAHAYANA_REALM
    return _por_reino(player, MAHAYANA_REALM)


def porta_corpo(player, flag: Flag | None = None) -> dict:
    """O Corpo abre quando UMA das suas três camadas (2.1) abre.

    O Corpo não é um gate só — é a soma de três, e cada um tem o seu dono:

      * **Refino Mortal** — existe sempre que ``cultivo_corpo_r0`` está ON (o
        ``/player`` projecta ``body_cultivation`` nessa condição, em qualquer
        reino) ⇒ a aba abre em R0;
      * **Meridianos** — ``corpo_profundo`` ON e reino ≥ ``MERIDIAN_MIN_REALM``;
      * **Nove Transformações** — reino ≥ ``MIN_REALM_REQUIRED``.

    Trancada, o requisito é o MAIS PRÓXIMO dos limiares que a abririam — é o
    que o jogador vai encontrar primeiro.
    """
    from core.body_tempering_engine import MIN_REALM_REQUIRED
    from core.meridian_engine import MERIDIAN_MIN_REALM
    flag = flag or _flag
    if flag("cultivo_corpo_r0"):
        return {"open": True}
    limiares = [int(MIN_REALM_REQUIRED)]
    if flag("corpo_profundo"):
        limiares.append(int(MERIDIAN_MIN_REALM))
    return _por_reino(player, min(limiares))


# A ordem é a da tabela acima. A chave é a do ``TAB_DEFS`` — é por ela que o
# cliente encontra a entrada, e a guarda §29 exige que cada uma exista lá.
PORTAS: tuple[tuple[str, Callable[..., dict]], ...] = (
    ("faction", porta_faccao),
    ("celestial", porta_celestial),
    ("body_tempering", porta_corpo),
)


def portas_do_jogador(player, flag: Flag | None = None) -> dict[str, dict]:
    """``{tab: {"open": bool|None, ...}}`` para cada aba com gate.

    Puro: zero queries. Corre no ``/player``, que se pede a cada 30s — por isso
    lê só a linha do jogador e as flags do mundo.
    """
    flag = flag or _flag
    out: dict[str, dict] = {}
    for tab, fn in PORTAS:
        try:
            out[tab] = fn(player, flag)
        except Exception:
            logger.exception("porta %s falhou (player=%s)", tab,
                             getattr(player, "telegram_id", None))
            out[tab] = {"open": None}
    return out
