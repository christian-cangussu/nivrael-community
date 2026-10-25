# -*- coding: utf-8 -*-
"""MV-11 天时 "O Tempo do Céu" — injetor de i18n. Idempotente.

    python -X utf8 scripts/inject_mv11_i18n.py

⚠️ `newline="\\n"` é LOAD-BEARING no Windows: sem ele os 4146+3662 pares
   flipam para CRLF e o diff fica ilegível.
⚠️ PT = PORTUGUÊS BRASILEIRO (você/seu, grafia BR). Comandos e {placeholders}
   NUNCA levam acento.

⚠️ ZERO MARKDOWN EM QUALQUER STRING `tsh_*`. Elas são DUAL-SURFACE: a MESMA
   string server-resolved é impressa pelo chat (que envia com
   `parse_mode="Markdown"` na tribulação, e SEM parse_mode na praça) e pelo
   mini-app (React, texto puro). Um `*negrito*` sairia com os asteriscos na
   cara do jogador em duas das três telas — é a lição literal do MV-9.5
   ("string dual-surface = plain text").

A LEI DE COLOCAÇÃO (o verificador enforça — e as duas listas têm de ser
DISJUNTAS):
  · Tudo o que o SERVIDOR resolve e manda pronto — a linha do céu, o próximo
    céu, a linha da praça, a Crônica — vive SÓ em `locales/{pt,en,es}.json`.
    O cliente imprime a string CRUA; passá-la por `t()` no mini criaria uma
    segunda fonte da mesma frase (e o `t()` do mini nem sequer tem os
    placeholders).
  · Tudo o que o CLIENTE compõe sozinho — nesta onda, SÓ o rótulo da flag no
    painel do owner — vive SÓ em `miniapp/i18n/{pt,en,es}.json`. O céu não tem
    botão, não tem cartão próprio e não tem modal: ele é ambiente.

DÍVIDA PAGA DE PASSAGEM (§4.5 do spec): `scripts/_verify_mv11_i18n.py`
generaliza o guard do `_desc` — até aqui o `feature_<flag>` era exigido para
TODA flag do catálogo mas o `_desc` só para uma tupla HARD-CODED
(`("caravana", "marca_do_tracado")`), logo uma flag com rótulo e sem descrição
passava a verde e mostrava descrição vazia no painel do owner.
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ══════════════════════════════════════════════════════════════════════════
# CHAT — `locales/{pt,en,es}.json` (server-resolved, impresso CRU nas 2 telas)
# ══════════════════════════════════════════════════════════════════════════
CHAT: dict[str, dict[str, str]] = {
    "pt": {
        # ── Os três céus (Lei §3: poucos, com dente) ───────────────────────
        "tsh_sky_sereno": "Céu Sereno",
        "tsh_sky_irado": "Céu Irado",
        "tsh_sky_velado": "Véu de Nuvens",
        # ── A frase que o jogador repete ───────────────────────────────────
        "tsh_phrase_sereno": "os raios estão como sempre",
        "tsh_phrase_irado": "os raios estão famintos",
        "tsh_phrase_velado": "o céu não te vê",
        # ── A tela da tribulação: antes→depois (Lei §10) ───────────────────
        "tsh_trib_line": "{emoji} {name} — {phrase} ({sign}{pct}% de severidade). Resistir: {before}% → {after}%.",
        "tsh_trib_line_neutral": "{emoji} {name} — {phrase}.",
        "tsh_trib_chance_flat": "Resistir: {chance}%.",
        # O clamp de 0,995 por round engole o céu acima de certa alma: aí o roll
        # é GENUINAMENTE idêntico e desenhar uma seta seria mentira.
        "tsh_trib_line_absorbed": "{emoji} {name} — {phrase} ({sign}{pct}% de severidade), mas a sua alma já não sente a diferença. Resistir: {chance}%.",
        # ── O ÚNICO futuro escrito deste jogo (Q6) ─────────────────────────
        "tsh_next_line": "O próximo céu — {emoji} {name} — chega em cerca de {hours}h.",
        "tsh_next_soon": "O próximo céu — {emoji} {name} — chega a qualquer momento.",
        # Em 37,4% das leituras o próximo céu é o MESMO — dizer "chega" ali
        # prometia uma mudança que não vem.
        "tsh_next_same": "O céu não muda no próximo turno: {emoji} {name} continua por mais cerca de {hours}h.",
        "tsh_next_same_soon": "O céu vira a qualquer momento — e continua {emoji} {name}.",
        # ── A praça: ambiente, sem chance (mas COM o preço, que é universal) ─
        "tsh_plaza_line": "{emoji} {name} — {phrase}.",
        "tsh_plaza_line_sev": "{emoji} {name} — {phrase} ({sign}{pct}% de severidade nas tribulações).",
        # ── A Crônica: uma linha por VIRADA, e só quando vira ──────────────
        "tsh_chron_sereno": "⛅ O céu se abriu. Os raios voltaram a ser o que sempre foram.",
        "tsh_chron_irado": "🌩️ O céu escureceu. Quem for enfrentar a tribulação agora encontra raios famintos.",
        "tsh_chron_velado": "🌫️ Um véu de nuvens cobriu o mundo. Por algumas horas, o céu não olha para baixo.",
    },
    "en": {
        "tsh_sky_sereno": "Serene Sky",
        "tsh_sky_irado": "Wrathful Sky",
        "tsh_sky_velado": "Veil of Clouds",
        "tsh_phrase_sereno": "the lightning is as it always was",
        "tsh_phrase_irado": "the lightning is hungry",
        "tsh_phrase_velado": "the sky does not see you",
        "tsh_trib_line": "{emoji} {name} — {phrase} ({sign}{pct}% severity). Resist: {before}% → {after}%.",
        "tsh_trib_line_neutral": "{emoji} {name} — {phrase}.",
        "tsh_trib_chance_flat": "Resist: {chance}%.",
        "tsh_trib_line_absorbed": "{emoji} {name} — {phrase} ({sign}{pct}% severity), but your soul no longer feels the difference. Resist: {chance}%.",
        "tsh_next_line": "The next sky — {emoji} {name} — arrives in about {hours}h.",
        "tsh_next_soon": "The next sky — {emoji} {name} — arrives at any moment.",
        "tsh_next_same": "The sky does not change next turn: {emoji} {name} stays for about {hours}h more.",
        "tsh_next_same_soon": "The sky turns at any moment — and stays {emoji} {name}.",
        "tsh_plaza_line": "{emoji} {name} — {phrase}.",
        "tsh_plaza_line_sev": "{emoji} {name} — {phrase} ({sign}{pct}% tribulation severity).",
        "tsh_chron_sereno": "⛅ The sky cleared. The lightning is back to what it always was.",
        "tsh_chron_irado": "🌩️ The sky darkened. Whoever faces the tribulation now meets hungry lightning.",
        "tsh_chron_velado": "🌫️ A veil of clouds covered the world. For a few hours, the sky does not look down.",
    },
    "es": {
        "tsh_sky_sereno": "Cielo Sereno",
        "tsh_sky_irado": "Cielo Airado",
        "tsh_sky_velado": "Velo de Nubes",
        "tsh_phrase_sereno": "los rayos están como siempre",
        "tsh_phrase_irado": "los rayos están hambrientos",
        "tsh_phrase_velado": "el cielo no te ve",
        "tsh_trib_line": "{emoji} {name} — {phrase} ({sign}{pct}% de severidad). Resistir: {before}% → {after}%.",
        "tsh_trib_line_neutral": "{emoji} {name} — {phrase}.",
        "tsh_trib_chance_flat": "Resistir: {chance}%.",
        "tsh_trib_line_absorbed": "{emoji} {name} — {phrase} ({sign}{pct}% de severidad), pero su alma ya no siente la diferencia. Resistir: {chance}%.",
        "tsh_next_line": "El próximo cielo — {emoji} {name} — llega en unas {hours}h.",
        "tsh_next_soon": "El próximo cielo — {emoji} {name} — llega en cualquier momento.",
        "tsh_next_same": "El cielo no cambia en el próximo turno: {emoji} {name} sigue por unas {hours}h más.",
        "tsh_next_same_soon": "El cielo gira en cualquier momento — y sigue {emoji} {name}.",
        "tsh_plaza_line": "{emoji} {name} — {phrase}.",
        "tsh_plaza_line_sev": "{emoji} {name} — {phrase} ({sign}{pct}% de severidad en las tribulaciones).",
        "tsh_chron_sereno": "⛅ El cielo se abrió. Los rayos volvieron a ser lo que siempre fueron.",
        "tsh_chron_irado": "🌩️ El cielo se oscureció. Quien enfrente la tribulación ahora encuentra rayos hambrientos.",
        "tsh_chron_velado": "🌫️ Un velo de nubes cubrió el mundo. Por unas horas, el cielo no mira hacia abajo.",
    },
}


# ══════════════════════════════════════════════════════════════════════════
# MINI — `miniapp/i18n/{pt,en,es}.json`
# SÓ o rótulo da flag no painel do owner. Sem estas 2 keys × 3 locales o
# toggle da 28ª flag mostra a KEY CRUA (`t()` faz
# `dict[key] ?? STRINGS.pt[key] ?? key` e degrada em silêncio) — foi o que
# aconteceu à 25ª (`marca_do_tracado`) e nenhum teste apanhou.
# ══════════════════════════════════════════════════════════════════════════
_DESC_TSH = {
    "pt": (
        "天时 O Tempo do Céu — o céu ganha temperamento, e ele decide QUANDO você "
        "enfrenta o raio. UM céu para o mundo inteiro (não por continente: 216 dos "
        "239 jogadores nunca saíram de Línghé, então geografia alcançaria 3 pessoas "
        "por mês), derivado do relógio a cada 12h — sem tabela, sem migration, sem "
        "job novo. Três céus: 🌩️ Irado (+12% de severidade) · ⛅ Sereno (exatamente "
        "igual a hoje) · 🌫️ Véu de Nuvens (-12%). Morde num único ponto, a força da "
        "tribulação, logo a previsão e a rolagem leem sempre o mesmo número. E é o "
        "único sistema do jogo que diz o FUTURO: a tela mostra qual é o próximo céu "
        "e em quantas horas ele chega, então esperar é uma escolha informada e nunca "
        "um castigo. O céu não é comprável nem dissipável por jade. Sem migration."
    ),
    "en": (
        "天时 The Time of Heaven — the sky gains a temper, and it decides WHEN you "
        "face the lightning. ONE sky for the whole world (not per continent: 216 of "
        "239 players never left Línghé, so geography would reach 3 people a month), "
        "derived from the clock every 12h — no table, no migration, no new job. "
        "Three skies: 🌩️ Wrathful (+12% severity) · ⛅ Serene (exactly as today) · "
        "🌫️ Veil of Clouds (-12%). It bites at a single point, the tribulation's "
        "power, so the preview and the roll always read the same number. And it is "
        "the only system in the game that states the FUTURE: the screen shows which "
        "sky comes next and in how many hours, so waiting is an informed choice and "
        "never a punishment. The sky cannot be bought or dispelled with jade. No "
        "migration."
    ),
    "es": (
        "天时 El Tiempo del Cielo — el cielo gana temperamento, y él decide CUÁNDO "
        "usted enfrenta el rayo. UN cielo para el mundo entero (no por continente: "
        "216 de 239 jugadores nunca salieron de Línghé, así que la geografía "
        "alcanzaría a 3 personas por mes), derivado del reloj cada 12h — sin tabla, "
        "sin migration, sin job nuevo. Tres cielos: 🌩️ Airado (+12% de severidad) · "
        "⛅ Sereno (exactamente igual a hoy) · 🌫️ Velo de Nubes (-12%). Muerde en un "
        "único punto, la fuerza de la tribulación, así que la previsión y la tirada "
        "leen siempre el mismo número. Y es el único sistema del juego que dice el "
        "FUTURO: la pantalla muestra cuál es el próximo cielo y en cuántas horas "
        "llega, así que esperar es una elección informada y nunca un castigo. El "
        "cielo no se compra ni se disipa con jade. Sin migration."
    ),
}

MINI: dict[str, dict[str, str]] = {
    "pt": {
        "feature_tempo_do_ceu": "天时 O Tempo do Céu",
        "feature_tempo_do_ceu_desc": _DESC_TSH["pt"],
    },
    "en": {
        "feature_tempo_do_ceu": "天时 The Time of Heaven",
        "feature_tempo_do_ceu_desc": _DESC_TSH["en"],
    },
    "es": {
        "feature_tempo_do_ceu": "天时 El Tiempo del Cielo",
        "feature_tempo_do_ceu_desc": _DESC_TSH["es"],
    },
}

# Nada é reescrito nesta onda. O céu é ADITIVO por construção: com a flag OFF
# `sky_view`/`sky_plaza_view` devolvem None, nenhuma key nova sai do servidor e
# nenhuma frase existente muda de sentido.
REWRITE_CHAT: dict[str, dict[str, str]] = {"pt": {}, "en": {}, "es": {}}
REWRITE_MINI: dict[str, dict[str, str]] = {"pt": {}, "en": {}, "es": {}}


def _inject(path: str, add: dict[str, str], rewrite: dict[str, str] | None = None
            ) -> tuple[int, int]:
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    changed = 0
    for key, val in {**add, **(rewrite or {})}.items():
        force = bool(rewrite and key in rewrite)
        if key in data and not force:
            continue
        if data.get(key) == val:
            continue
        data[key] = val
        changed += 1
    if changed:
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=4, sort_keys=True)
            fh.write("\n")
    return changed, len(data)


def main() -> None:
    for lang in ("pt", "en", "es"):
        n, total = _inject(os.path.join(ROOT, "locales", f"{lang}.json"),
                           CHAT[lang], REWRITE_CHAT.get(lang))
        print(f"chat  {lang}: {n:+d}  (total {total})")
    for lang in ("pt", "en", "es"):
        n, total = _inject(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"),
                           MINI[lang], REWRITE_MINI.get(lang))
        print(f"mini  {lang}: {n:+d}  (total {total})")


if __name__ == "__main__":
    main()
