# -*- coding: utf-8 -*-
"""全 O JOGO INTEIRO — as strings novas do lote (2026-09-08).

Idempotente: correr duas vezes nao duplica nada.

Escreve so' em `miniapp/i18n/{pt,en,es}.json`. O chat nao ganha nada AQUI (as
keys de nome de tecnica, que sao conteudo de catalogo e servem as duas
superficies, vivem em `locales/` e tem script proprio:
`inject_tech_names_i18n.py`).

Quatro familias, todas MEDIDAS antes de escritas:

1. `art_grade_0..8` — os NOVE degraus do artefacto (`config.ARTIFACT_GRADES`).
   ⚠️ O prompt deste lote dizia que a escala do artefacto era de QUATRO
   (`normal|perfect|divine|spirit`). Nao e': esses quatro sao a *qualidade de
   forja*, que o motor infere post-hoc, nunca persiste e o refino APAGA — e
   `refined` esta' "OUTSIDE the order on purpose" (`core/forge_engine.py`). O
   posto e' o `grade`, e os seeds provam-no: os 51 artefactos ocupam os nove
   degraus (3/3/10/7/9/7/3/3/6). Uma escala de 4 saturaria dois tercos do
   catalogo no topo.
   Os nomes sao a escada classica 黄玄地天 (Amarelo/Mistico/Terra/Ceu) com
   Mortal por baixo e Espirito/Divino/Dao/Celestial por cima — e ate' hoje eram
   impressos CRUS em ingles, tambem no chat (6 sitios em `handlers/`).

2. `law_rank_*` (5) — `core/dao_laws_engine.py` RARITY_WEIGHTS. ⚠️ E' a raridade
   da LEI. O `TIER_THRESHOLDS` 0..5 do mesmo ficheiro e' outra coisa: a
   compreensao do CAMINHO pelo jogador, nao o posto da peca.

3. `trap_rank_*` (6) — `core/beast_engine.py` TRAP_QUALITY_ORDER. ⚠️ Aqui
   `mythic` esta' ABAIXO de `legendary`, ao contrario do `BEAST_RANKS`. E' o
   motor; a carta segue o motor de cada conteudo.

4. `gacha_rank_*` (4) — os baldes do banner (`database/seeds/gacha_seeds.py`).

Mais as strings de UI que a conversao precisou (mochila, capturas, o bloco de
accoes que desceu da lista para o modal da besta).
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

KEYS = {
    "pt": {
        # 1 — os nove degraus do artefacto
        "art_grade_0": "Mortal",
        "art_grade_1": "Amarelo",
        "art_grade_2": "Místico",
        "art_grade_3": "Terra",
        "art_grade_4": "Céu",
        "art_grade_5": "Espírito",
        "art_grade_6": "Divino",
        "art_grade_7": "Dao",
        "art_grade_8": "Celestial",
        # 2 — a raridade da lei do Dao
        "law_rank_common": "Comum",
        "law_rank_uncommon": "Incomum",
        "law_rank_rare": "Rara",
        "law_rank_epic": "Épica",
        "law_rank_legendary": "Lendária",
        # 3 — a qualidade da armadilha
        "trap_rank_normal": "Simples",
        "trap_rank_common": "Comum",
        "trap_rank_rare": "Rara",
        "trap_rank_epic": "Épica",
        "trap_rank_mythic": "Mítica",
        "trap_rank_legendary": "Lendária",
        # 4 — o balde do gacha
        "gacha_rank_common": "Comum",
        "gacha_rank_rare": "Raro",
        "gacha_rank_epic": "Épico",
        "gacha_rank_legendary": "Lendário",
        # UI da conversao
        "beasts_detail_actions": "Ações",
        "beasts_detail_need_stones": "Faltam {n} pedras espirituais para treinar.",
        "beasts_capture_state_owned": "JÁ POSSUI",
        "inv_card_slot_empty": "Vazio",
        "inv_card_slot_weapon": "Arma",
        "inv_card_slot_armor": "Armadura",
        "inv_card_slot_accessory1": "Anel",
        "inv_card_slot_accessory2": "Amuleto",
        "inv_card_kind_artifact": "Artefato",
        "inv_card_kind_pill": "Pílula",
        "inv_card_kind_herb": "Erva",
        "inv_card_kind_ore": "Minério",
        "inv_card_kind_item": "Item",
        "inv_card_equipped": "EQUIPADO",
        "inv_card_qty": "×{n}",
        "inv_card_realm_locked": "Requer reino {n}",
    },
    "en": {
        "art_grade_0": "Mortal",
        "art_grade_1": "Yellow",
        "art_grade_2": "Mystic",
        "art_grade_3": "Earth",
        "art_grade_4": "Heaven",
        "art_grade_5": "Spirit",
        "art_grade_6": "Divine",
        "art_grade_7": "Dao",
        "art_grade_8": "Celestial",
        "law_rank_common": "Common",
        "law_rank_uncommon": "Uncommon",
        "law_rank_rare": "Rare",
        "law_rank_epic": "Epic",
        "law_rank_legendary": "Legendary",
        "trap_rank_normal": "Plain",
        "trap_rank_common": "Common",
        "trap_rank_rare": "Rare",
        "trap_rank_epic": "Epic",
        "trap_rank_mythic": "Mythic",
        "trap_rank_legendary": "Legendary",
        "gacha_rank_common": "Common",
        "gacha_rank_rare": "Rare",
        "gacha_rank_epic": "Epic",
        "gacha_rank_legendary": "Legendary",
        "beasts_detail_actions": "Actions",
        "beasts_detail_need_stones": "{n} more spirit stones needed to train.",
        "beasts_capture_state_owned": "OWNED",
        "inv_card_slot_empty": "Empty",
        "inv_card_slot_weapon": "Weapon",
        "inv_card_slot_armor": "Armor",
        "inv_card_slot_accessory1": "Ring",
        "inv_card_slot_accessory2": "Amulet",
        "inv_card_kind_artifact": "Artifact",
        "inv_card_kind_pill": "Pill",
        "inv_card_kind_herb": "Herb",
        "inv_card_kind_ore": "Ore",
        "inv_card_kind_item": "Item",
        "inv_card_equipped": "EQUIPPED",
        "inv_card_qty": "×{n}",
        "inv_card_realm_locked": "Requires realm {n}",
    },
    "es": {
        "art_grade_0": "Mortal",
        "art_grade_1": "Amarillo",
        "art_grade_2": "Místico",
        "art_grade_3": "Tierra",
        "art_grade_4": "Cielo",
        "art_grade_5": "Espíritu",
        "art_grade_6": "Divino",
        "art_grade_7": "Dao",
        "art_grade_8": "Celestial",
        "law_rank_common": "Común",
        "law_rank_uncommon": "Poco común",
        "law_rank_rare": "Rara",
        "law_rank_epic": "Épica",
        "law_rank_legendary": "Legendaria",
        "trap_rank_normal": "Simple",
        "trap_rank_common": "Común",
        "trap_rank_rare": "Rara",
        "trap_rank_epic": "Épica",
        "trap_rank_mythic": "Mítica",
        "trap_rank_legendary": "Legendaria",
        "gacha_rank_common": "Común",
        "gacha_rank_rare": "Raro",
        "gacha_rank_epic": "Épico",
        "gacha_rank_legendary": "Legendario",
        "beasts_detail_actions": "Acciones",
        "beasts_detail_need_stones": "Faltan {n} piedras espirituales para entrenar.",
        "beasts_capture_state_owned": "YA LA TIENES",
        "inv_card_slot_empty": "Vacío",
        "inv_card_slot_weapon": "Arma",
        "inv_card_slot_armor": "Armadura",
        "inv_card_slot_accessory1": "Anillo",
        "inv_card_slot_accessory2": "Amuleto",
        "inv_card_kind_artifact": "Artefacto",
        "inv_card_kind_pill": "Píldora",
        "inv_card_kind_herb": "Hierba",
        "inv_card_kind_ore": "Mineral",
        "inv_card_kind_item": "Objeto",
        "inv_card_equipped": "EQUIPADO",
        "inv_card_qty": "×{n}",
        "inv_card_realm_locked": "Requiere reino {n}",
    },
}


def main() -> int:
    added_total = 0
    for lg in LANGS:
        path = os.path.join(ROOT, "miniapp", "i18n", f"{lg}.json")
        d = json.load(io.open(path, encoding="utf-8"))
        added = 0
        for k, v in KEYS[lg].items():
            if k not in d:
                d[k] = v
                added += 1
        d = dict(sorted(d.items()))
        io.open(path, "w", encoding="utf-8", newline="\n").write(
            json.dumps(d, ensure_ascii=False, indent=4) + "\n")
        added_total += added
        print(f"  {lg}: +{added} keys -> {len(d)} total")
    print(f"total adicionadas: {added_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
