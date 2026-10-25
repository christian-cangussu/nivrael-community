"""QoL-Feedback 2026-08-04 — injetor de i18n (chat + mini) dos 2 reports.

Roda:  python -X utf8 scripts/inject_qol0804_i18n.py

Superfícies:
  · chat locales — a linha do **Tributo da Terra** que passa a DIZER o item e a
    quantidade (`dng_tribute_named`/`_stones`/`_hits`), os rótulos honestos dos
    bônus de conquista (`ach_bonus_*`), e as duas frases que respondem ao report
    do [jogador]: o título é **honorífico** (nota no menu de títulos + marca na
    linha da conquista) + a nota do Pavilhão de Mérito;
  · mini i18n — as MESMAS duas frases (a secção Honras e o card da conquista) e
    os mesmos rótulos de bônus.

O que NÃO precisou de key nova: a linha do tributo no mini é **server-resolved**
(`regional_bonus.line`) — as 2 telas imprimem a mesma string, e a key antiga
`dungeon_regional_bonus` fica como recuo para um payload em cache.

SÓ-ADIÇÕES: `_apply` só escreve key que AINDA NÃO existe. Idempotente.
`newline="\n"` é load-bearing (Windows CRLF).

PT = **PT-BR** (você/seu; grafia BR). Verificador: scripts/_verify_qol0804_i18n.py.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

CHAT = {
    "pt": {
        # ── O Tributo da Terra, com item e quantidade (report [jogador]) ──
        "dng_tribute_named": "🧭 Tributo da terra: {emoji} {name} cedeu {loot}",
        "dng_tribute_stones": "🪨 {stones} pedras espirituais",
        "dng_tribute_hits": "(×{hits} tributos nesta leva)",
        # ── Títulos: o benefício é prestígio, e agora está DITO (report [jogador]) ──
        "ach_title_honorary_note": "🎖️ _Títulos são honoríficos: aparecem antes do seu nome e não mudam nada no combate. O que eles carregam é a sua história._",
        "ach_title_honorary_tag": "_(honorífico)_",
        "merit_titles_honorary_note": "🎖️ _Estes títulos são honoríficos — puro prestígio da casa. Nenhum deles muda seus atributos._",
        # ── Rótulos dos bônus que MORDEM de verdade ──
        "ach_bonus_cb_mult": "de velocidade de cultivo",
        "ach_bonus_bp_mult": "de poder de combate",
    },
    "en": {
        "dng_tribute_named": "🧭 Tribute of the land: {emoji} {name} yielded {loot}",
        "dng_tribute_stones": "🪨 {stones} spirit stones",
        "dng_tribute_hits": "(×{hits} tributes in this batch)",
        "ach_title_honorary_note": "🎖️ _Titles are honorary: they show before your name and change nothing in combat. What they carry is your story._",
        "ach_title_honorary_tag": "_(honorary)_",
        "merit_titles_honorary_note": "🎖️ _These titles are honorary — pure standing within the house. None of them changes your stats._",
        "ach_bonus_cb_mult": "cultivation speed",
        "ach_bonus_bp_mult": "battle power",
    },
    "es": {
        "dng_tribute_named": "🧭 Tributo de la tierra: {emoji} {name} cedió {loot}",
        "dng_tribute_stones": "🪨 {stones} piedras espirituales",
        "dng_tribute_hits": "(×{hits} tributos en esta tanda)",
        "ach_title_honorary_note": "🎖️ _Los títulos son honoríficos: aparecen antes de su nombre y no cambian nada en el combate. Lo que llevan es su historia._",
        "ach_title_honorary_tag": "_(honorífico)_",
        "merit_titles_honorary_note": "🎖️ _Estos títulos son honoríficos — puro prestigio de la casa. Ninguno cambia sus atributos._",
        "ach_bonus_cb_mult": "de velocidad de cultivo",
        "ach_bonus_bp_mult": "de poder de combate",
    },
}

MINIAPP = {
    "pt": {
        "ach_title_honorary_note": "Títulos são honoríficos: aparecem antes do seu nome e não mudam nada no combate. O que eles carregam é a sua história.",
        "ach_title_honorary_tag": "(honorífico)",
        "ach_bonus_cb_mult": "de velocidade de cultivo",
        "ach_bonus_bp_mult": "de poder de combate",
    },
    "en": {
        "ach_title_honorary_note": "Titles are honorary: they show before your name and change nothing in combat. What they carry is your story.",
        "ach_title_honorary_tag": "(honorary)",
        "ach_bonus_cb_mult": "cultivation speed",
        "ach_bonus_bp_mult": "battle power",
    },
    "es": {
        "ach_title_honorary_note": "Los títulos son honoríficos: aparecen antes de su nombre y no cambian nada en el combate. Lo que llevan es su historia.",
        "ach_title_honorary_tag": "(honorífico)",
        "ach_bonus_cb_mult": "de velocidad de cultivo",
        "ach_bonus_bp_mult": "de poder de combate",
    },
}

# Nenhuma string já shipada foi reescrita neste lote (a antiga
# `dng_regional_bonus`/`dungeon_regional_bonus` fica como recuo).
CHAT_OVERRIDES: dict = {"pt": {}, "en": {}, "es": {}}
MINI_OVERRIDES: dict = {"pt": {}, "en": {}, "es": {}}


def _apply(path: str, additions: dict, overrides: dict | None = None) -> tuple:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    before = len(data)
    for k, v in additions.items():
        if k not in data:
            data[k] = v
    for k, v in (overrides or {}).items():
        data[k] = v
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, sort_keys=True)
        f.write("\n")
    return before, len(data)


def main() -> None:
    for lang in LANGS:
        b, a = _apply(os.path.join(ROOT, "locales", lang + ".json"), CHAT[lang],
                      CHAT_OVERRIDES.get(lang))
        print("chat " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")
    for lang in LANGS:
        b, a = _apply(os.path.join(ROOT, "miniapp", "i18n", lang + ".json"), MINIAPP[lang],
                      MINI_OVERRIDES.get(lang))
        print("mini " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")


if __name__ == "__main__":
    main()
