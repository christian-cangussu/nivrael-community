"""QoL-Feedback 07/08 (Item C — report do [jogador]) + Item A (report do [jogador]).

Injeta, com paridade nos 3 locales de CHAT (`locales/{pt,en,es}.json`):

  1. `sty_obj_<objective_type>` × 8 — **o objetivo DITO em palavras**. São
     resolvidas NO SERVIDOR (`storylet_engine.objective_line`) e viajam prontas
     para as duas superfícies, portanto NÃO precisam de existir em
     `miniapp/i18n/*` — a mesma regra do `reward_line`/`name`/`desc` do MV-5.
     O estilo é copiado de `bp_miss_forge_artifact` ("Forjar {value} artefato(s)"),
     que já dizia exatamente isto para o Battle Pass.
  2. A reescrita de `sty_enc_fenghuo_forja_d2` × 3 — a linha que mandava
     "bater em alguma coisa" num encargo cujo objetivo é FORJAR.
  3. `inv_pill_bulk_cap_stop` × 3 (Item A) — o lote de reposição que parou
     porque encheu, com o número do que sobrou dito (Lei §1).

PT-BR obrigatório no `pt.json` (você/seu, grafia brasileira). Idempotente.

Run:  python scripts/inject_qol0807_i18n.py
"""
from __future__ import annotations

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 1. O objetivo em palavras ────────────────────────────────────────────────
# ⚠️ UMA entrada por `objective_type` usado por `STORYLET_SEEDS`. O teste desta
# onda bate as seeds contra `_OBJ_EMOJI`/`_OBJ_CHAT_CMD` e contra estas keys —
# um tipo novo que entre sem passar por aqui rebenta o teste, de propósito
# (é a enésima recorrência de "enum novo exige grep a TODOS os mapas").
CHAT: dict[str, dict[str, str]] = {
    "pt": {
        "sty_obj_cultivate":        "Meditar {n} minutos",
        "sty_obj_craft_pill":       "Refinar {n} pílula(s)",
        "sty_obj_use_pill":         "Usar {n} pílula(s)",
        # ⚠️ "combate" sozinho mentia: `npc_combat` SÓ é creditado em PvE (o
        # settle de PvP escreve outro enum), logo quem fosse duelar um jogador
        # via o chip "→" ficava a 0/N sem explicação — o report do [jogador] outra vez.
        # Alinhado com o precedente `bp_miss_win_npc_fight`.
        "sty_obj_npc_combat":       "Vencer {n} luta(s) contra NPC",
        "sty_obj_arena_win":        "Vencer {n} luta(s) na arena",
        "sty_obj_dungeon_floor":    "Limpar {n} andar(es) de masmorra",
        "sty_obj_beast_expedition": "Concluir {n} expedição(ões) de bestas",
        "sty_obj_forge_artifact":   "Forjar {n} artefato(s)",
        # A linha que mentia: o objetivo é FORJAR, e ela mandava bater.
        "sty_enc_fenghuo_forja_d2": "Pegue o martelo. Enquanto sair peça daquela bigorna, a fornalha vive.",
        # Item A — o lote de reposição que parou por ter enchido A MEIO.
        "inv_pill_bulk_cap_stop":   "Usou {used} · encheu no meio do caminho · {left} continuam no anel.",
        # ...e o estado DIFERENTE: já estava cheio ao tocar, nada saiu do anel.
        # Key própria (o irmão `stat_boost` já tinha a dele) — reusar a de cima
        # com used=0 dizia duas coisas falsas de uma vez.
        "pill_qi_full_kept":        "⚠️ Seu dantian já está cheio — nenhuma pílula saiu do anel.",
        "pill_hp_full_kept":        "⚠️ Seu corpo já está inteiro — nenhuma pílula saiu do anel.",
    },
    "en": {
        "sty_obj_cultivate":        "Meditate for {n} minutes",
        "sty_obj_craft_pill":       "Refine {n} pill(s)",
        "sty_obj_use_pill":         "Use {n} pill(s)",
        "sty_obj_npc_combat":       "Win {n} NPC fight(s)",
        "sty_obj_arena_win":        "Win {n} arena match(es)",
        "sty_obj_dungeon_floor":    "Clear {n} dungeon floor(s)",
        "sty_obj_beast_expedition": "Complete {n} beast expedition(s)",
        "sty_obj_forge_artifact":   "Forge {n} artifact(s)",
        "sty_enc_fenghuo_forja_d2": "Pick up the hammer. As long as pieces leave that anvil, the furnace lives.",
        "inv_pill_bulk_cap_stop":   "Used {used} · you filled up partway · {left} remain in the ring.",
        "pill_qi_full_kept":        "⚠️ Your dantian is already full — no pill left the ring.",
        "pill_hp_full_kept":        "⚠️ Your body is already whole — no pill left the ring.",
    },
    "es": {
        "sty_obj_cultivate":        "Meditar {n} minutos",
        "sty_obj_craft_pill":       "Refinar {n} píldora(s)",
        "sty_obj_use_pill":         "Usar {n} píldora(s)",
        "sty_obj_npc_combat":       "Ganar {n} pelea(s) contra NPC",
        "sty_obj_arena_win":        "Ganar {n} combate(s) en la arena",
        "sty_obj_dungeon_floor":    "Limpiar {n} piso(s) de mazmorra",
        "sty_obj_beast_expedition": "Completar {n} expedición(es) de bestias",
        "sty_obj_forge_artifact":   "Forjar {n} artefacto(s)",
        "sty_enc_fenghuo_forja_d2": "Toma el martillo. Mientras salgan piezas de ese yunque, la fragua vive.",
        "inv_pill_bulk_cap_stop":   "Usaste {used} · se llenó a mitad de camino · {left} siguen en el anillo.",
        "pill_qi_full_kept":        "⚠️ Tu dantian ya está lleno — ninguna píldora salió del anillo.",
        "pill_hp_full_kept":        "⚠️ Tu cuerpo ya está entero — ninguna píldora salió del anillo.",
    },
}

# ── 2. Mini-app (Item A) ─────────────────────────────────────────────────────
# Estas TÊM de viver em `miniapp/i18n/*` porque são resolvidas no CLIENTE (o
# painel da pílula desenha as suas próprias linhas de resultado/recusa).
MINI: dict[str, dict[str, str]] = {
    "pt": {
        "pill_panel_qi_full_refused": "Seu dantian já está cheio — nenhuma pílula saiu do anel.",
        "pill_panel_hp_full_refused": "Seu corpo já está inteiro — nenhuma pílula saiu do anel.",
        "pill_panel_refill_stopped":  "Encheu no meio do caminho · {left} continuam no anel.",
    },
    "en": {
        "pill_panel_qi_full_refused": "Your dantian is already full — no pill left the ring.",
        "pill_panel_hp_full_refused": "Your body is already whole — no pill left the ring.",
        "pill_panel_refill_stopped":  "You filled up partway · {left} remain in the ring.",
    },
    "es": {
        "pill_panel_qi_full_refused": "Tu dantian ya está lleno — ninguna píldora salió del anillo.",
        "pill_panel_hp_full_refused": "Tu cuerpo ya está entero — ninguna píldora salió del anillo.",
        "pill_panel_refill_stopped":  "Se llenó a mitad de camino · {left} siguen en el anillo.",
    },
}

# Keys que já existiam e são REESCRITAS de propósito (o injector é idempotente,
# mas uma reescrita tem de ser explícita para não parecer acidente).
# ⚠️ Reescritas do review adversarial desta mesma sessão: "combate" sozinho não
# dizia NPC (e só PvE credita `npc_combat`), e o ES tinha estreado "usted" em
# painéis que tratam por "tú".
OVERWRITE = {"sty_enc_fenghuo_forja_d2", "sty_obj_npc_combat",
             "inv_pill_bulk_cap_stop"}
MINI_OVERWRITE = {"pill_panel_qi_full_refused", "pill_panel_hp_full_refused"}


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4, sort_keys=True)
        fh.write("\n")


def main() -> int:
    total_new = total_rw = 0
    for lang, keys in CHAT.items():
        path = os.path.join(ROOT, "locales", f"{lang}.json")
        data = _load(path)
        new = rw = 0
        for k, v in keys.items():
            if k in data:
                if k in OVERWRITE and data[k] != v:
                    data[k] = v
                    rw += 1
                continue
            data[k] = v
            new += 1
        _save(path, data)
        total_new += new
        total_rw += rw
        print(f"  locales/{lang}.json: +{new} novas · {rw} reescritas · total {len(data)}")

    mini_new = 0
    for lang, keys in MINI.items():
        path = os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json")
        data = _load(path)
        new = 0
        for k, v in keys.items():
            if k in data:
                if k in MINI_OVERWRITE and data[k] != v:
                    data[k] = v
                continue
            data[k] = v
            new += 1
        _save(path, data)
        mini_new += new
        print(f"  miniapp/i18n/{lang}.json: +{new} novas · total {len(data)}")

    sizes = {lang: len(_load(os.path.join(ROOT, "locales", f"{lang}.json"))) for lang in CHAT}
    msizes = {lang: len(_load(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"))) for lang in MINI}
    print(f"\n  chat: +{total_new} · reescritas {total_rw} · mini: +{mini_new}")
    print(f"  paridade chat: {sizes}")
    print(f"  paridade mini: {msizes}")
    if len(set(sizes.values())) != 1 or len(set(msizes.values())) != 1:
        print("  ❌ PARIDADE QUEBRADA")
        return 1
    print("  ✅ paridade OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
