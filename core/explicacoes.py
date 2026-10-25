# -*- coding: utf-8 -*-
"""減 A REDUÇÃO PROGRESSIVA — o dono único de "esta frase ainda se mostra?" (P7).

A decisão é do Astra (MESA ``[017]`` §4, 2026-09-16), textual:

  *"Depois de uma acção bem-sucedida nesse sistema, oferecer «Já percebi»: a
  frase introdutória recolhe; «Ajuda» permite recuperá-la. **Sem presumir
  domínio pelo tempo de conta e sem mudar a posição dos comandos.**"*

  *"Ficam sempre: rótulo, valor actual, progresso numérico/limiar, custo,
  duração relevante, bloqueio e consequência confirmada. (…) Reduzimos a
  explicação repetida, **nunca a evidência de que o personagem avançou**."*

── O QUE SE CONTOU ANTES DE ESCREVER ISTO (2026-09-27) ──────────────────────

Toda chave ``t("…")`` dos componentes que a onda desenha (a chegada nas duas
composições, o Cultivo, o Corpo, a entrada e o preparo do Combate, a cena do
duelo, as Técnicas, a consulta das portas): **242**. Cada uma contra a pergunta
*"se ela sumir, o jogador perde um NÚMERO ou um MOTIVO?"*. Só **6** passam —
e o terreno que o prompt trazia caiu em dois pontos:

  * **Vida/Qi não tem UMA dica escrita.** Só rótulo, número, estado ("Vida
    reduzida", "Acima da capacidade") e a recusa com o caminho de saída
    (``combat_hp_way_out``). Tudo prova. Não há sistema a registar.
  * ``cena_idle_body`` ("A base cresce sozinha…") **só se desenha com a onda
    OFF** — com ela ON o Cultivo é a ``CultivationSynthesis``, que não tem frase
    explicativa nenhuma. Recolhê-la seria mexer no ecrã que tem de ficar
    byte-idêntico.

As seis que ficam, por sistema, vivem no registo do cliente (``EXPLICA`` em
``miniapp/components/ui.js``); a guarda compara as duas listas de sistemas.

── A REGRA DESTE FICHEIRO ───────────────────────────────────────────────────

**O gatilho é o SERVIDOR, na transacção da acção confirmada** — nunca o toque,
nunca o tempo de conta. Cada endpoint que conclui uma acção de um sistema
chama ``marcar_apto`` antes do seu ``commit``; se a acção for recusada, a marca
não acontece, porque não chega lá.

Três estados por sistema, e a AUSÊNCIA é o primeiro:
  * ausente      → a frase aparece; «Já percebi» NÃO é oferecido;
  * ``"apto"``   → a frase aparece; «Já percebi» é oferecido;
  * ``"recolhido"`` → a frase recolhe; «Ajuda» traz de volta.

⚠️ *"Sem preferência lida nunca é recolhido"*: o cliente só recolhe perante um
``"recolhido"`` que o servidor lhe disse. Payload sem a chave (onda OFF, ou o
``/player`` que falhou) ⇒ a frase aparece. Mostrar a mais é honesto.

⚠️ Só se escreve com a onda ligada (``core/portas.onda_on``). No ``main`` nada
disto corre e a coluna fica NULL para os 57.
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

APTO = "apto"
RECOLHIDO = "recolhido"

# ── OS SISTEMAS, e o que os dispara ─────────────────────────────────────────
# A chave é o nome do sistema; o valor diz QUAL acção o torna apto — é a
# documentação do gatilho, e a guarda §30 segue cada endpoint nomeado aqui até
# à chamada de ``marcar_apto`` (nunca uma lista à mão noutro sítio).
#
# ⚠️ O Corpo são TRÊS sistemas, não um: cada camada tem a sua acção e a sua
# frase. Recolher a explicação dos meridianos a quem só refinou a carne seria
# presumir domínio de uma coisa que o jogador nunca fez.
SISTEMAS: dict[str, tuple[str, ...]] = {
    # as duas portas que SENTAM o jogador (a lista do Cultivo e a do Dao)
    "meditar": ("api_meditate_start", "api_dao_meditate_start"),
    # equipar uma arte de COMBATE — é dela que a frase da entrada fala
    "equipar": ("api_combat_equip_technique",),
    "corpo_mortal": ("api_world_body_temper",),
    "corpo_transf": ("api_body_tempering_ascend",),
    "corpo_mer": ("api_world_meridian_start", "api_world_meridian_break"),
}

Flag = Callable[[str], bool]


def _onda(flag: Flag | None = None) -> bool:
    try:
        from core.portas import onda_on
        return onda_on(flag)
    except Exception:
        return False


def estados(player) -> dict:
    """O estado lido, só com sistemas conhecidos e valores válidos.

    Uma chave que o registo já não conhece, ou um valor estranho, some — não
    rebenta a leitura. Nunca devolve None: devolve ``{}``."""
    raw = getattr(player, "explicacoes", None)
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items()
            if k in SISTEMAS and v in (APTO, RECOLHIDO)}


def para_payload(player, flag: Flag | None = None) -> dict | None:
    """O que o ``/player`` manda: o dicionário com a onda ON, ``None`` com ela
    OFF (e aí a CHAVE nem vai — o payload do ``main`` sai byte-idêntico)."""
    if not _onda(flag):
        return None
    return estados(player)


def marcar_apto(player, sistema: str, flag: Flag | None = None) -> bool:
    """Chamado pelo endpoint da acção, ANTES do seu ``commit``.

    Nunca rebaixa: um sistema já ``recolhido`` continua recolhido (agir outra
    vez não é pedir a frase de volta). Devolve True quando escreveu."""
    if sistema not in SISTEMAS:
        raise KeyError("sistema desconhecido: %r" % (sistema,))
    if not _onda(flag):
        return False
    atual = estados(player)
    if atual.get(sistema) is not None:
        return False
    # ⚠️ Atribuir um dicionário NOVO: o SQLAlchemy não segue mutações dentro de
    # um JSONB simples, e um ``player.explicacoes[k] = v`` nunca chegava à base.
    player.explicacoes = {**atual, sistema: APTO}
    return True


def recolher(player, sistema: str, flag: Flag | None = None) -> tuple[bool, str | None]:
    """«Já percebi». Só se recolhe o que já foi oferecido — o servidor recusa
    um sistema onde o jogador ainda não agiu (``nao_apto``): o toque não é
    gatilho."""
    if not _onda(flag):
        return False, "onda_off"
    if sistema not in SISTEMAS:
        return False, "sistema_invalido"
    atual = estados(player)
    est = atual.get(sistema)
    if est == RECOLHIDO:
        return True, None           # idempotente: dois toques, um estado
    if est != APTO:
        return False, "nao_apto"
    player.explicacoes = {**atual, sistema: RECOLHIDO}
    return True, None


def repor(player, flag: Flag | None = None) -> tuple[bool, str | None]:
    """Configurações → «Mostrar as explicações de novo». Tudo o que estava
    recolhido volta a ``apto``: a frase reaparece e «Já percebi» continua a
    ser oferecido (o jogador já agiu — isso não se desaprende)."""
    if not _onda(flag):
        return False, "onda_off"
    atual = estados(player)
    player.explicacoes = {k: APTO for k in atual} or None
    return True, None
