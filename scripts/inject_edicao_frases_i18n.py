# -*- coding: utf-8 -*-
"""開 AS FRASES DA EDIÇÃO — 2 chaves novas (x3 línguas), ao lado das do jogo oficial.

Porque existe (Open Source F4b, 2026-10-23)
-------------------------------------------
A edição comunitária REESCREVIA duas frases do jogo oficial (9 transformações
`texto` do exportador): a recusa das Stars ("Mundo de teste — compras reais só
no Servidor Principal.") e a nota do lobby ("Mundo de teste — personagem
separado, sem compras."). Na cópia, nenhum mundo cobra — apontar um Servidor
Principal que também não vende seria mentir. Mas se o jogo oficial um dia
correr do código público, o jogador do s2 leria "nesta edição comunitária",
que é falso para ELE. O owner decidiu (23/10): reconciliar — as duas frases
vivem no código, e quem escolhe é a CHAMADA:

  • `shop_purchases_official_only` — a recusa quando nenhum mundo cobra
    (`stars_refusal` em handlers/shop.py: chat e mini-app);
  • `lobby_separate_world_note` — a nota do lobby quando o `main` não cobra
    (`mainSells` no LobbyModal, de dados que o servidor já manda).

No jogo oficial o `main` cobra sempre: estas chaves existem e nunca se mostram.

Insere cada chave LOGO DEPOIS da irmã, e reescreve o ficheiro com o formato
dele (indent 2, UTF-8, `\\n` final) — o diff é só as linhas novas. Idempotente.
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (catálogo, chave nova, a irmã depois da qual entra)
CHAT = ("locales", (("shop_purchases_official_only", "shop_sandbox_blocked"),))
MINIAPP = ("miniapp/i18n", (("shop_purchases_official_only", "shop_sandbox_blocked"),
                            ("lobby_separate_world_note", "lobby_sandbox_note")))

KEYS = {
    "pt": {
        "shop_purchases_official_only":
            "Compras reais só existem no jogo oficial — nesta edição comunitária elas vêm desligadas.",
        "lobby_separate_world_note": "Mundo à parte — personagem separado, sem compras reais.",
    },
    "en": {
        "shop_purchases_official_only":
            "Real purchases exist only in the official game — this community edition ships with them turned off.",
        "lobby_separate_world_note": "Separate world — separate character, no real purchases.",
    },
    "es": {
        "shop_purchases_official_only":
            "Las compras reales solo existen en el juego oficial — en esta edición comunitaria vienen desactivadas.",
        "lobby_separate_world_note": "Mundo aparte — personaje separado, sin compras reales.",
    },
}


def _inserir(path: str, pares, valores: dict) -> list[str]:
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    novas = []
    for chave, irma in pares:
        if chave in data:
            data[chave] = valores[chave]
            continue
        if irma not in data:
            raise SystemExit(f"{path}: a irmã `{irma}` não existe — a âncora mudou")
        out = {}
        for k, v in data.items():
            out[k] = v
            if k == irma:
                out[chave] = valores[chave]
        data = out
        novas.append(chave)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return novas


def main() -> None:
    for pasta, pares in (CHAT, MINIAPP):
        for lang, valores in KEYS.items():
            path = os.path.join(ROOT, *pasta.split("/"), f"{lang}.json")
            novas = _inserir(path, pares, valores)
            print(f"{pasta}/{lang}.json: novas {', '.join(novas) or 'nenhuma'}")


if __name__ == "__main__":
    main()
