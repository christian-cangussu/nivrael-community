# -*- coding: utf-8 -*-
"""🩸 A RECUSA QUE DIZ O CAMINHO — 1 chave nova + 4 reescritas, x3 linguas.

O que isto corrige, e foi MEDIDO a 2026-09-13
---------------------------------------------
O `hp_too_low` e uma recusa honesta: o motor recusa mesmo. Mas o mini-app —
que e a superficie CANONICA — mandava o jogador **ESPERAR**:

    combat_npc_hp_depleted   "HP em zero. Espere regenerar antes de lutar."
    combat_pvp_hp_depleted   "HP em zero - espere regenerar antes de aceitar."
    combat_arena_q_err_hp    "HP baixo demais para entrar."
    lgc_mini_hp              "Recupere sua vitalidade antes de enfrentar o Eco."

e o CHAT, na mesma recusa, dizia a coisa certa desde sempre:

    hp_too_low_combat        "Seu HP esta esgotado! Medite ou use uma Pilula de
                              Cura para recuperar antes de lutar."

Duas superficies, a mesma recusa, conselhos OPOSTOS — e o errado e o que fica.
E "esperar" nao e so vago: e **o caminho mais lento dos tres**, medido no
codigo:

    passiva .......... 0,1%/min do max, e SO dentro do `cultivation_tick`, que
                       salta quem tem `last_online` > 4h (OFFLINE_CAP_SECONDS)
                       => tecto de ~24% do max POR VISITA
    meditacao leve ... 1%/min, 30 min, DE GRACA        => +30%
    meditacao profunda 5%/min, custa 50 qi             => CHEIO em 20 min
    Pilula de Cura ... instantanea, e a economia esta cheia delas (medido:
                       120 donos da Minor no main; 6,7 M unidades da Supreme)

Ou seja: a tela mandava esperar 16 horas por uma coisa que se resolve em 20
minutos, com um item que o jogador quase de certeza ja tem na mochila.

A forma da correccao: UM DONO
-----------------------------
O contexto muda (npc / arena / pvp / Eco), **o caminho de saida nao**. Por isso
ha uma so frase para a saida (`combat_hp_way_out`) e as quatro mensagens de
contexto passam a dizer apenas o FACTO. Quem as junta e `hpDepletedMsg()` em
`ui.js` — uma funcao, quatro chamadores, e uma guarda que fica vermelha se
alguem voltar a escrever a recusa a mao.

⚠️ `combat_pvp_challenger_hp_depleted` ("O desafiante ja nao pode lutar") NAO
   leva o caminho de saida, e isso e decisao e nao esquecimento: quem esta a
   zero e o OUTRO jogador. Mandar voce meditar por causa da vitalidade dele
   seria a tela a mentir.

⚠️ A palavra passa a ser **Vitalidade** e nao "HP" nas quatro. Nao e gosto: e o
   rotulo que o proprio jogo ja declara (`combat_stat_hp = "Vitalidade"`), e e
   o mesmo que a barra do hub EU passa a usar neste lote. Lei 0: a
   inconsistencia e pior do que a ausencia.

⚠️ `pt.json` e portugues BRASILEIRO. voce/seu, grafia BR, com acentos.
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYS = {
    "pt": {
        # A chave NOVA — a unica frase que diz o caminho, e o unico sitio onde
        # ela existe.
        "combat_hp_way_out": "Medite para recuperar, ou use uma Pílula de Cura.",
        # As quatro reescritas: o FACTO, sem prescrever nada.
        "combat_npc_hp_depleted": "Vitalidade em zero.",
        "combat_arena_q_err_hp": "Vitalidade baixa demais para entrar na fila.",
        "combat_pvp_hp_depleted": "Vitalidade em zero — você não pode aceitar.",
        "lgc_mini_hp": "Vitalidade em zero — o Eco não pode ser enfrentado assim.",
        # A barra que passa a ter nome no hub EU (as outras duas ja tinham
        # chave: `cultivation` e `qi` vivem no cartao da Home).
        "hub_eu_bar_vitality": "Vitalidade",
    },
    "en": {
        "combat_hp_way_out": "Meditate to recover, or use a Healing Pill.",
        "combat_npc_hp_depleted": "Vitality at zero.",
        "combat_arena_q_err_hp": "Vitality too low to queue.",
        "combat_pvp_hp_depleted": "Vitality at zero — you cannot accept.",
        "lgc_mini_hp": "Vitality at zero — the Echo cannot be faced like this.",
        "hub_eu_bar_vitality": "Vitality",
    },
    "es": {
        "combat_hp_way_out": "Medita para recuperarte, o usa una Píldora de Curación.",
        "combat_npc_hp_depleted": "Vitalidad a cero.",
        "combat_arena_q_err_hp": "Vitalidad demasiado baja para entrar en la cola.",
        "combat_pvp_hp_depleted": "Vitalidad a cero — no puedes aceptar.",
        "lgc_mini_hp": "Vitalidad a cero — no puedes enfrentar al Eco así.",
        "hub_eu_bar_vitality": "Vitalidad",
    },
}


def main():
    for lang, pairs in KEYS.items():
        path = os.path.join(ROOT, "miniapp", "i18n", "%s.json" % lang)
        with io.open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        before = len(data)
        novas = [k for k in pairs if k not in data]
        for k, v in pairs.items():
            data[k] = v
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=4)
            fh.write("\n")
        print("%s: %d -> %d chaves (novas: %s)"
              % (lang, before, len(data), ", ".join(sorted(novas)) or "nenhuma"))


if __name__ == "__main__":
    main()
