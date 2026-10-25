"""Admin player dossier ("ver tudo do jogador") + logs-by-player i18n (mini-app).

Section headers + the "ver logs deste jogador" button label for the expanded
AdminPlayerDetail. Re-runnable; upserts admin_dossier_*/admin_player_logs and
re-dumps each locale indent=4 + ensure_ascii=False + newline. pt = PT-BR.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MINIAPP = {
    "pt": {
        "admin_player_logs": "Ver logs",
        "admin_dossier_progress": "Progresso",
        "admin_dossier_cb": "Base de cultivo",
        "admin_dossier_prestige": "Prestígio",
        "admin_dossier_foundation": "Fundação",
        "admin_dossier_core": "Núcleo",
        "admin_dossier_body": "Corpo",
        "admin_dossier_treasures": "Três Tesouros",
        "admin_dossier_economy": "Economia",
        "admin_dossier_jade_earned": "Jade ganho (total)",
        "admin_dossier_identity": "Identidade",
        "admin_dossier_continent": "Continente",
        "admin_dossier_sect": "Seita",
        "admin_dossier_spirit_root": "Raiz espiritual",
        "admin_dossier_lang": "Idioma",
        "admin_dossier_created": "Criado em",
        "admin_dossier_monet": "Monetização",
        "admin_dossier_purchases": "Compras",
        "admin_dossier_monthly": "Cartão mensal",
        "admin_dossier_collection": "Coleção",
        "admin_dossier_counts": "Téc · Inv · Conq · Art",
    },
    "en": {
        "admin_player_logs": "View logs",
        "admin_dossier_progress": "Progress",
        "admin_dossier_cb": "Cultivation base",
        "admin_dossier_prestige": "Prestige",
        "admin_dossier_foundation": "Foundation",
        "admin_dossier_core": "Core",
        "admin_dossier_body": "Body",
        "admin_dossier_treasures": "Three Treasures",
        "admin_dossier_economy": "Economy",
        "admin_dossier_jade_earned": "Jade earned (total)",
        "admin_dossier_identity": "Identity",
        "admin_dossier_continent": "Continent",
        "admin_dossier_sect": "Sect",
        "admin_dossier_spirit_root": "Spirit root",
        "admin_dossier_lang": "Language",
        "admin_dossier_created": "Created",
        "admin_dossier_monet": "Monetization",
        "admin_dossier_purchases": "Purchases",
        "admin_dossier_monthly": "Monthly card",
        "admin_dossier_collection": "Collection",
        "admin_dossier_counts": "Tech · Inv · Ach · Art",
    },
    "es": {
        "admin_player_logs": "Ver logs",
        "admin_dossier_progress": "Progreso",
        "admin_dossier_cb": "Base de cultivo",
        "admin_dossier_prestige": "Prestigio",
        "admin_dossier_foundation": "Fundación",
        "admin_dossier_core": "Núcleo",
        "admin_dossier_body": "Cuerpo",
        "admin_dossier_treasures": "Tres Tesoros",
        "admin_dossier_economy": "Economía",
        "admin_dossier_jade_earned": "Jade ganado (total)",
        "admin_dossier_identity": "Identidad",
        "admin_dossier_continent": "Continente",
        "admin_dossier_sect": "Secta",
        "admin_dossier_spirit_root": "Raíz espiritual",
        "admin_dossier_lang": "Idioma",
        "admin_dossier_created": "Creado",
        "admin_dossier_monet": "Monetización",
        "admin_dossier_purchases": "Compras",
        "admin_dossier_monthly": "Tarjeta mensual",
        "admin_dossier_collection": "Colección",
        "admin_dossier_counts": "Téc · Inv · Logr · Art",
    },
}


def _apply(path, additions):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    before = len(data)
    added = sum(1 for k in additions if k not in data)
    data.update(additions)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write("\n")
    return before, len(data), added


def main():
    for lang, adds in MINIAPP.items():
        before, after, added = _apply(
            os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"), adds)
        print(f"miniapp {lang}: {before} -> {after} (+{added})")


if __name__ == "__main__":
    main()
