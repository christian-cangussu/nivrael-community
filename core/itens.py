"""📦 O NOME DE CADA ITEM QUE NÃO É PÍLULA, ERVA NEM MINÉRIO — o dono único.

🎒 3.2, 2026-09-30.

Porque existe
-------------
`api_inventory` nomeava tudo o que não fosse pílula, erva ou minério como
`f"{itype} #{iid}"`, e esse texto ia para o ecrã, na secção "Outros" da vista
"Todos": **"technique_scroll #12"**, **"beast_trap #0"**. Medido a 30/09
(`tools/db_readonly_anel_0930.py` §E, só-leitura) — no `main`:

    technique_scroll ... 229 jogadores (30 técnicas diferentes)
    beast_trap ......... 200    beast_core ... 59    blueprint ... 44
    gacha_ticket ....... 12

O chat nomeava-os por outra tabela (`handlers/inventory._MISC_LABELS`), em
INGLÊS fixo para quem joga em pt e es. Duas portas, dois nomes, nenhum certo.
Aqui fica UM nome por tipo, nas três línguas, e as duas portas perguntam-lhe.

⚠️ `beast_core` usa a chave que o jogo JÁ tinha (`beast_core_name`, a das
bestas): o núcleo que se ganha numa expedição e o que se vê na mochila são a
mesma coisa e têm de ter o mesmo nome.

⚠️ Um tipo que não esteja aqui cai em "Item" — nunca no tipo cru. A guarda da
§32 descobre os tipos que o jogo ESCREVE e exige um nome para cada um.
"""
from __future__ import annotations

from core.i18n import t

# O emoji de cada tipo — o verso honesto quando não há arte.
EMOJI = {
    "technique_scroll": "📜",
    "beast_trap": "🪤",
    "beast_core": "💎",
    "gacha_ticket": "🎟️",
    "blueprint": "📜",
    "ore_pack": "📦",
    "pill_recipe_scroll": "📖",
    "mystery_box": "🎁",
    # os três que a §32 ACHOU nos escritores e nas consultas da mochila e que
    # nenhuma tabela nomeava (0 linhas em produção a 30/09 — mas o sorteio
    # escreve ovos, a facção escreve receitas e o parceiro consome anéis):
    "beast_egg": "🥚",
    "jade_ring": "💍",
    "recipe": "📖",
}

# A chave do nome, por tipo (as de `technique_scroll` e `ore_pack` levam
# parâmetro e são tratadas à parte, em `nome`).
_CHAVE = {
    "beast_trap": "inv_item_beast_trap",
    "beast_core": "beast_core_name",
    "gacha_ticket": "inv_item_gacha_ticket",
    "blueprint": "inv_item_blueprint",
    "pill_recipe_scroll": "inv_item_pill_recipe_scroll",
    "mystery_box": "inv_item_mystery_box",
    "beast_egg": "inv_item_beast_egg",
    "jade_ring": "inv_item_jade_ring",
    "recipe": "inv_item_recipe",
}

# Todos os tipos com nome — o que a guarda compara com o que o jogo escreve.
TIPOS = frozenset(EMOJI)


def nome(lang: str, item_type: str, item_id=None, tecnica: str | None = None) -> str:
    """O nome de um item fora dos catálogos, na língua do jogador.

    `tecnica` é o nome JÁ LOCALIZADO da técnica de um pergaminho (quem chama
    tem a linha do catálogo; ir buscá-la aqui seria uma query por linha).
    """
    if item_type == "technique_scroll":
        if tecnica:
            return t(lang, "inv_item_technique_scroll", name=tecnica)
        # o nome que o espólio das masmorras JÁ dá ao pergaminho — um só nome
        return t(lang, "dng_drop_scroll")
    if item_type == "ore_pack":
        try:
            tier = int(item_id or 1)
        except (TypeError, ValueError):
            tier = 1
        return t(lang, "inv_item_ore_pack", tier=tier)
    chave = _CHAVE.get(item_type)
    if chave:
        return t(lang, chave)
    return t(lang, "inv_item_generic")


def emoji(item_type: str) -> str:
    return EMOJI.get(item_type, "📦")
