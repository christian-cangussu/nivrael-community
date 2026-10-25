"""QoL 05/08 — injetor de i18n (report do jogador [jogador] sobre os meridianos).

SÓ-ADIÇÕES. Idempotente (rodar 2× não muda nada na 2ª vez). Molde:
`scripts/inject_tec5_i18n.py`.

O que entra: UMA key por superfície (chat + mini-app) × 3 idiomas — a "cicatriz"
persistente do ritual de meridiano. O report: *"on meridian open failure, there
is a pop up message, which disappears faster than I can read it... show the
message in persistent text until next breaking point becomes available... This
will allow memory of previous failure and chance, as well as reminder what next
(higher) chance is"*.

⚠️ newline='\\n' é LOAD-BEARING no Windows (senão o arquivo inteiro vira CRLF e o
diff explode). Idioma herdado de todos os injetores anteriores.
PT = **PORTUGUÊS BRASILEIRO** (você/seu; grafia BR) — nunca europeu.
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Chat (locales/*.json) ────────────────────────────────────────────────────
# Placeholders: {n} tentativas falhadas · {was} chance base · {now} chance atual.
CHAT: dict[str, dict[str, str]] = {
    "pt": {
        "mer_retry_memory": "💢 {n} tentativa(s) falhada(s) — a chance subiu de {was}% para {now}%. Nada se perdeu: cada falha grava o caminho no canal.",
    },
    "en": {
        "mer_retry_memory": "💢 {n} failed attempt(s) — the chance rose from {was}% to {now}%. Nothing was lost: each failure carves the path deeper into the channel.",
    },
    "es": {
        "mer_retry_memory": "💢 {n} intento(s) fallido(s) — la probabilidad subió de {was}% a {now}%. Nada se perdió: cada fallo graba el camino en el canal.",
    },
}

# ── Mini-app (miniapp/i18n/*.json) ───────────────────────────────────────────
# Mesma verdade, texto mais curto (vive dentro de um card estreito).
MINI: dict[str, dict[str, str]] = {
    "pt": {
        "mer_retry_memory": "{n} tentativa(s) falhada(s) — a chance subiu de {was}% para {now}%. Nada se perdeu.",
    },
    "en": {
        "mer_retry_memory": "{n} failed attempt(s) — the chance rose from {was}% to {now}%. Nothing was lost.",
    },
    "es": {
        "mer_retry_memory": "{n} intento(s) fallido(s) — la probabilidad subió de {was}% a {now}%. Nada se perdió.",
    },
}


def _inject(path: str, add: dict[str, str]) -> tuple[int, int]:
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    added = 0
    for key, val in add.items():
        if key in data:          # idempotente — nunca sobrescreve o que já existe
            continue
        data[key] = val
        added += 1
    if added:
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=4, sort_keys=True)
            fh.write("\n")
    return added, len(data)


def main() -> None:
    for lang, add in CHAT.items():
        p = os.path.join(ROOT, "locales", f"{lang}.json")
        n, total = _inject(p, add)
        print(f"chat  {lang}: +{n}  (total {total})")
    for lang, add in MINI.items():
        p = os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json")
        n, total = _inject(p, add)
        print(f"mini  {lang}: +{n}  (total {total})")


if __name__ == "__main__":
    main()
