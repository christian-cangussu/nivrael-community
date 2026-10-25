# -*- coding: utf-8 -*-
"""Lote do [jogador] (12-14/08/2026) — injetor de i18n. Idempotente.

    python -X utf8 scripts/inject_relatos_0814_i18n.py

Quatro reports, quatro superfícies:
  1. 🩺 o seletor de alvo da cura (mini) — só a frase de "não há ninguém"
  2. 💰 a doação de seita no chat — as recusas que eram SILENCIOSAS
  3. 🗺️ a expedição de fera — a notificação (key NOVA, payload NOVO desde a
     1ª row: uma `notif_*` renderiza LAZY sobre o payload gravado na época)
  4. 轮回 o Caminho a re-derivar no renascimento — o antes→depois ANTES do tap

⚠️ PT = PORTUGUÊS BRASILEIRO (você/seu, grafia BR).
⚠️ `newline="\\n"` é LOAD-BEARING no Windows.
⚠️ `prestige_path_change` é impressa pelo chat com `parse_mode="Markdown"` —
   sem asteriscos desemparelhados. `prf_mini_heal_nobody` é do mini (React) —
   ZERO markdown.
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHAT: dict[str, dict[str, str]] = {
    "pt": {
        # 💰 as recusas que eram silenciosas
        "sect_donate_err_number": "💰 Não entendi o valor. Envie só o número de pedras — por exemplo: 5000",
        "sect_donate_err_no_sect": "💰 Você não pertence a nenhuma seita de jogadores, então não há tesouro para receber a doação. Entre numa seita (ou crie a sua) e tente de novo.",
        # 🗺️ a expedição (key NOVA, payload NOVO)
        "notif_expedition_done_title": "🗺️ Expedição concluída",
        "notif_expedition_done_body": "{beast} voltou da expedição. O espólio espera por você.",
        # 轮回 o Caminho re-derivado
        "prestige_path_change": "☯️ *O seu Caminho vai mudar.* O karma atravessa as vidas: com {karma} de karma, você renasce {to_emoji} {to_name} — não mais {from_emoji} {from_name}.",
    },
    "en": {
        "sect_donate_err_number": "💰 I didn't understand the amount. Send just the number of stones — for example: 5000",
        "sect_donate_err_no_sect": "💰 You don't belong to any player sect, so there's no treasury to receive the donation. Join a sect (or found your own) and try again.",
        "notif_expedition_done_title": "🗺️ Expedition complete",
        "notif_expedition_done_body": "{beast} is back from the expedition. The spoils are waiting for you.",
        "prestige_path_change": "☯️ *Your Path will change.* Karma crosses lives: with {karma} karma, you are reborn {to_emoji} {to_name} — no longer {from_emoji} {from_name}.",
    },
    "es": {
        "sect_donate_err_number": "💰 No entendí la cantidad. Envíe solo el número de piedras — por ejemplo: 5000",
        "sect_donate_err_no_sect": "💰 Usted no pertenece a ninguna secta de jugadores, así que no hay tesoro que reciba la donación. Únase a una secta (o funde la suya) e inténtelo de nuevo.",
        "notif_expedition_done_title": "🗺️ Expedición concluida",
        "notif_expedition_done_body": "{beast} volvió de la expedición. El botín le espera.",
        "prestige_path_change": "☯️ *Su Camino va a cambiar.* El karma atraviesa las vidas: con {karma} de karma, usted renace {to_emoji} {to_name} — ya no {from_emoji} {from_name}.",
    },
}

MINI: dict[str, dict[str, str]] = {
    "pt": {
        "prf_mini_heal_nobody": "Ninguém por perto precisa de cura agora. O alvo tem de estar no seu continente, dentro de 3 reinos de distância e com HP ferido.",
    },
    "en": {
        "prf_mini_heal_nobody": "Nobody nearby needs healing right now. The target must be on your continent, within 3 realms of you, and actually wounded.",
    },
    "es": {
        "prf_mini_heal_nobody": "Nadie cerca necesita curación ahora. El objetivo debe estar en su continente, a menos de 3 reinos de distancia y realmente herido.",
    },
}

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
