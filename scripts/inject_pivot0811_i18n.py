# -*- coding: utf-8 -*-
"""PIVOT 2026-08-11 — injetor de i18n. Idempotente.

    python -X utf8 scripts/inject_pivot0811_i18n.py

Cobre as duas superfícies que os fixes do report do [jogador] abriram:

  1. 内功 — a frase que DIZ como cada arte ganha Compreensão. Era a metade da
     Lei §1 que faltava: as artes internas/de meditação só ganhavam XP
     absorvendo um pergaminho REPETIDO, e nenhuma tela dizia isso. Do lado do
     jogador, *"não tem como ganhar XP"* era verdade.
     ⚠️ DUAL-SURFACE: a MESMA string é impressa pelo chat (com
     `parse_mode="Markdown"`) e pelo mini-app (React puro, server-resolved via
     `gain_hint`). ZERO markdown — um `*` sairia literal numa das duas.

  2. `notif_neigong_up_*` — a subida de estágio das artes internas. Key NOVA com
     payload NOVO desde a 1ª row: acrescentar um placeholder a uma `notif_*`
     existente parte RETROATIVAMENTE todas as linhas já gravadas (elas
     renderizam preguiçosamente sobre o payload da época, e não há poda).

⚠️ PT = PORTUGUÊS BRASILEIRO (você/seu, grafia BR). Placeholders sem acento.
⚠️ `newline="\\n"` é LOAD-BEARING no Windows.
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHAT: dict[str, dict[str, str]] = {
    "pt": {
        "tech_gain_combat": "📈 Ganha Compreensão sendo usada em combate — ou absorvendo um pergaminho repetido dela.",
        "tech_gain_passive": "📈 Ganha Compreensão a cada meditação concluída, se estiver equipada — ou absorvendo um pergaminho repetido dela.",
        "notif_neigong_up_title": "🌀 Compreensão aprofundada",
        "notif_neigong_up_body": "{emoji} {name} avançou do estágio {before} para o {after}.",
    },
    "en": {
        "tech_gain_combat": "📈 Gains Comprehension by being used in combat — or by absorbing a duplicate scroll of it.",
        "tech_gain_passive": "📈 Gains Comprehension with every meditation you finish, while equipped — or by absorbing a duplicate scroll of it.",
        "notif_neigong_up_title": "🌀 Comprehension deepened",
        "notif_neigong_up_body": "{emoji} {name} advanced from stage {before} to {after}.",
    },
    "es": {
        "tech_gain_combat": "📈 Gana Comprensión al ser usada en combate — o absorbiendo un pergamino repetido de ella.",
        "tech_gain_passive": "📈 Gana Comprensión con cada meditación concluida, si está equipada — o absorbiendo un pergamino repetido de ella.",
        "notif_neigong_up_title": "🌀 Comprensión profundizada",
        "notif_neigong_up_body": "{emoji} {name} avanzó de la etapa {before} a la {after}.",
    },
}

# Nada no mini-app: a frase é server-resolved (`gain_hint`) e a notificação
# renderiza no servidor. Manter as duas listas DISJUNTAS é a lei de colocação.
MINI: dict[str, dict[str, str]] = {"pt": {}, "en": {}, "es": {}}

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
