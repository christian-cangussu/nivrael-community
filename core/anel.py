"""💍 O ANEL ESPACIAL — o dono único da conta do anel (🎒 3.2, 2026-09-30).

Porque existe
-------------
A conta da expansão vivia em TRÊS sítios escritos à mão:

  · `handlers/inventory._do_ring_upgrade` — a expansão pelo chat;
  · `core/webserver.api_inventory_ring_upgrade` — a expansão pelo mini-app;
  · `handlers/inventory._ring_info` — o botão do chat, que anunciava o máximo
    ABSOLUTO do tier seguinte (`RING_MAX_SLOTS[next]`) e mentia a quem comprou
    lugares no Pavilhão de Prestígio: a expansão é ADITIVA (fix de 14/07, report
    [jogador]), e um T4 com 510 lugares vê "1000" e recebe 1010.

Os dois primeiros eram iguais por sorte; o terceiro já tinha divergido. Aqui fica
a conta uma vez, e as três portas perguntam-lhe.

A regra da luz (Astra, `Olho/Astra/2026-09-16-e-o-corpo-que-acende.md`, linha
da Caverna · Inventário): *"`ring.tier` e a melhoria confirmada expandem a
inscrição do anel; `can_upgrade/next_cost` governa a próxima expansão;
`used_slots / max_slots` é ocupação."* ⇒ o TIER é conquista (acende); a
ocupação é estado (nunca acende); os lugares são a consequência, com número.

⚠️ Chaves CONDICIONAIS: com a onda desligada o bloco `ring` e a resposta da
expansão são os de hoje, byte a byte (o `main` não recebe nada de novo).
"""
from __future__ import annotations

MAX_RING_TIER = 5
RING_MAX_SLOTS = {1: 50, 2: 100, 3: 200, 4: 500, 5: 1_000}
RING_UPGRADE_STONES = {1: 1_000, 2: 5_000, 3: 25_000, 4: 100_000}

# Os eixos que podem acender numa expansão confirmada. Um eixo fora daqui
# rebenta — a luz não se inventa (mesma regra do `core/oficios.py`).
EIXOS_QUE_ACENDEM = ("tier",)


def _tier(tier) -> int:
    """`int(tier or 1)` — a MESMA leitura das portas de hoje, sem limitar.

    ⚠️ Não se prende o tier a 1..5 de propósito: com a onda OFF o bloco tem de
    sair byte a byte igual ao de antes para QUALQUER linha, incluindo uma
    impossível. Um tier fora da tabela não tem custo nem próximo (o `.get` dá
    None), exactamente como o código antigo.
    """
    return int(tier or 1)


def custo_proximo(tier) -> int | None:
    """O preço da próxima expansão, em pedras espirituais — None no topo."""
    t = _tier(tier)
    if t >= MAX_RING_TIER:
        return None
    c = RING_UPGRADE_STONES.get(t)
    return int(c) if c is not None else None


def proximo_max(tier, max_slots) -> int | None:
    """Os lugares que o anel terá DEPOIS da próxima expansão — None no topo.

    ⚠️ ADITIVO: soma o degrau do tier ao que o anel TEM, e não ao que o tier
    daria de raiz. As expansões do Pavilhão de Prestígio somam lugares sem mexer
    no tier; uma conta absoluta apagá-las-ia (foi o report [jogador], 14/07).
    """
    t = _tier(tier)
    if t >= MAX_RING_TIER or t not in RING_MAX_SLOTS or (t + 1) not in RING_MAX_SLOTS:
        return None
    base = RING_MAX_SLOTS[t]
    return int(max_slots or base) + (RING_MAX_SLOTS[t + 1] - base)


def expandir(ring) -> dict:
    """Aplica UMA expansão à linha do anel (já trancada pelo chamador) e devolve
    `{tier: {antes, depois}, max_slots: {antes, depois}}`.

    Não cobra nem recusa por preço: isso é de cada porta, que já verificou e diz
    a recusa à sua maneira (o chat num alerta, o mini-app num `reason`). No topo
    levanta `ValueError("ring_max")` — as duas portas verificam antes; chegar
    aqui no topo é um defeito, e um defeito não pode dar um tier 6.
    """
    t0 = _tier(ring.tier)
    m0 = int(ring.max_slots or RING_MAX_SLOTS[t0])
    m1 = proximo_max(t0, m0)
    if m1 is None:
        raise ValueError("ring_max")
    ring.tier = t0 + 1
    ring.max_slots = m1
    return {"tier": {"antes": t0, "depois": t0 + 1},
            "max_slots": {"antes": m0, "depois": m1}}


def retrato(tier, max_slots, used_slots, onda: bool) -> dict:
    """O bloco `ring` do payload do inventário.

    Com a onda OFF é EXACTAMENTE o de hoje — as mesmas chaves, pela mesma ordem.
    Com ela ON ganha o que a luz precisa para acompanhar o número: `max_tier`
    (o denominador — "tier 3 de 5", nunca um denominador inventado no cliente) e
    `next_max_slots` (a meta real da próxima expansão, pela conta aditiva).
    """
    t = int(tier or 1)
    custo = custo_proximo(t)
    out = {
        "tier": t,
        "max_slots": int(max_slots or 50),
        "used_slots": int(used_slots),
        "can_upgrade": bool(custo is not None),
    }
    if custo is not None:
        out["next_cost"] = int(custo)
    if onda:
        out["max_tier"] = MAX_RING_TIER
        nm = proximo_max(t, int(max_slots or 50))
        if nm is not None:
            out["next_max_slots"] = int(nm)
    return out


def ganho(antes_depois: dict) -> dict:
    """`anel_ganho` — o ganho CONFIRMADO de uma expansão, na forma do
    `oficio_ganho` da 3.1: `{tier: {antes, depois}, max_slots: {antes, depois},
    acende: [...]}`.

    `acende` leva só o eixo cuja CONQUISTA subiu — o tier. Os lugares são a
    consequência (um número antes→depois), não uma estrela; a ocupação nem
    aparece (é estado).
    """
    tier = antes_depois["tier"]
    acende = [e for e in EIXOS_QUE_ACENDEM
              if int(antes_depois[e]["depois"]) > int(antes_depois[e]["antes"])]
    return {"tier": {"antes": int(tier["antes"]), "depois": int(tier["depois"])},
            "max_slots": {"antes": int(antes_depois["max_slots"]["antes"]),
                          "depois": int(antes_depois["max_slots"]["depois"])},
            "acende": acende}


def resposta_expansao(ring, gasto: int, pedras: int, antes_depois: dict,
                      onda: bool) -> dict:
    """A resposta de uma expansão CONFIRMADA no mini-app.

    Com a onda OFF é a de hoje, chave a chave; com ela ON leva `anel_ganho`
    (a consequência confirmada e o que acende). O arnês de desenvolvimento monta
    a sua por AQUI — um mock com a forma escrita à mão mente antes do código.
    """
    out = {"ok": True, "tier": int(ring.tier), "max_slots": int(ring.max_slots),
           "spent": int(gasto), "spirit_stones": int(pedras)}
    if onda:
        out["anel_ganho"] = ganho(antes_depois)
    return out
