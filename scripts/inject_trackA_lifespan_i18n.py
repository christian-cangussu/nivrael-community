"""Track A (B4) — Lifespan 寿命 ("Mar de Longevidade 寿海") i18n.

Re-runnable: OVERWRITES this wave's own (uniquely-namespaced) keys with the
current values, then re-dumps each locale indent=4 + ensure_ascii=False +
trailing newline. All keys are namespaced (status_lifespan_* for chat, lifespan_*
+ npc_age for the mini) and were verified not to collide with any pre-existing key.
  * CHAT    (locales/*.json)      — the /status "Mar de Longevidade" block: title +
    current-realm ceiling line + the next-realm CARROT + the immortal flag + the
    honest future teaser (server-rendered in handlers/cultivation._lifespan_lines).
  * MINIAPP (miniapp/i18n/*.json) — the CultivationTab lifespan Card (same copy) +
    the NpcCultivatorModal "Idade: N anos" flavor chip.
pt = PT-BR (você/seu). DISCLOSURE-ONLY (Lei §1, §5): the teaser is explicit ("ainda
não corre") — NEVER a fake "morre em X" / "X anos restantes"; nothing ticks/ages/
dies this wave. The realm names interpolated into {realm}/{next} are the canonical
English game constants (config.REALM_NAMES), exactly as the rest of the game shows them.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CHAT = {
    "pt": {
        "status_lifespan_title": "🌊 Mar de Longevidade 寿海",
        "status_lifespan_ceiling": "{realm}: {anos} anos",
        "status_lifespan_next": "↳ rompa para {next} → {anos} anos",
        "status_lifespan_next_immortal": "↳ rompa para {next} → ∞ — ao tornar-se imortal, escapa do ciclo",
        "status_lifespan_immortal": "∞ — você se tornou imortal; escapou do ciclo da morte",
        "status_lifespan_future": "↳ o relógio desperta no novo mundo — ainda não corre",
    },
    "en": {
        "status_lifespan_title": "🌊 Sea of Longevity 寿海",
        "status_lifespan_ceiling": "{realm}: {anos} years",
        "status_lifespan_next": "↳ break through to {next} → {anos} years",
        "status_lifespan_next_immortal": "↳ break through to {next} → ∞ — becoming immortal, you escape the cycle",
        "status_lifespan_immortal": "∞ — you have become immortal; you escaped the cycle of death",
        "status_lifespan_future": "↳ the clock awakens in the new world — it is not running yet",
    },
    "es": {
        "status_lifespan_title": "🌊 Mar de Longevidad 寿海",
        "status_lifespan_ceiling": "{realm}: {anos} años",
        "status_lifespan_next": "↳ rompe hacia {next} → {anos} años",
        "status_lifespan_next_immortal": "↳ rompe hacia {next} → ∞ — al volverte inmortal, escapas del ciclo",
        "status_lifespan_immortal": "∞ — te has vuelto inmortal; escapaste del ciclo de la muerte",
        "status_lifespan_future": "↳ el reloj despierta en el nuevo mundo — aún no corre",
    },
}

MINIAPP = {
    "pt": {
        "lifespan_title": "Mar de Longevidade 寿海",
        "lifespan_ceiling": "{realm}: {anos} anos",
        "lifespan_next": "Rompa para {next} → {anos} anos",
        "lifespan_next_immortal": "Rompa para {next} → ∞ — ao tornar-se imortal, escapa do ciclo",
        "lifespan_immortal": "∞ — você se tornou imortal; escapou do ciclo da morte",
        "lifespan_future": "O relógio (envelhecimento) desperta no novo mundo — ainda não corre.",
        "npc_age": "Idade: {age} anos",
    },
    "en": {
        "lifespan_title": "Sea of Longevity 寿海",
        "lifespan_ceiling": "{realm}: {anos} years",
        "lifespan_next": "Break through to {next} → {anos} years",
        "lifespan_next_immortal": "Break through to {next} → ∞ — becoming immortal, you escape the cycle",
        "lifespan_immortal": "∞ — you have become immortal; you escaped the cycle of death",
        "lifespan_future": "The clock (ageing) awakens in the new world — it is not running yet.",
        "npc_age": "Age: {age} years",
    },
    "es": {
        "lifespan_title": "Mar de Longevidad 寿海",
        "lifespan_ceiling": "{realm}: {anos} años",
        "lifespan_next": "Rompe hacia {next} → {anos} años",
        "lifespan_next_immortal": "Rompe hacia {next} → ∞ — al volverte inmortal, escapas del ciclo",
        "lifespan_immortal": "∞ — te has vuelto inmortal; escapaste del ciclo de la muerte",
        "lifespan_future": "El reloj (envejecimiento) despierta en el nuevo mundo — aún no corre.",
        "npc_age": "Edad: {age} años",
    },
}


def _apply(path, additions):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    before = len(data)
    added = changed = 0
    for k, v in additions.items():
        if k not in data:
            added += 1
        elif data[k] != v:
            changed += 1
        data[k] = v  # overwrite — keys are uniquely namespaced to this wave
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write("\n")
    return before, len(data), added, changed


def main():
    for lang, adds in CHAT.items():
        before, after, added, changed = _apply(os.path.join(ROOT, "locales", f"{lang}.json"), adds)
        print(f"chat    {lang}: {before} -> {after} (+{added}, ~{changed} updated)")
    for lang, adds in MINIAPP.items():
        before, after, added, changed = _apply(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"), adds)
        print(f"miniapp {lang}: {before} -> {after} (+{added}, ~{changed} updated)")


if __name__ == "__main__":
    main()
