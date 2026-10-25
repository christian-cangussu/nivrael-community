# -*- coding: utf-8 -*-
"""MV-9.5 商队 "A Caravana" — injetor de i18n. Idempotente.

    python -X utf8 scripts/inject_mv95_i18n.py

⚠️ `newline="\\n"` é LOAD-BEARING no Windows: sem ele os 4104+3643 pares
   flipam para CRLF e o diff fica ilegível.
⚠️ PT = PORTUGUÊS BRASILEIRO (você/seu, grafia BR: artefato, ativo, tela,
   arquivo). Comandos e {placeholders} NUNCA levam acento.

A LEI DE COLOCAÇÃO (o verificador enforça):
  · Tudo o que o SERVIDOR resolve e manda pronto — a linha de origem, a fala do
    velho, as recusas, a carga em trânsito — vive SÓ em `locales/{pt,en,es}.json`.
    O cliente imprime a string CRUA; passá-la por `t()` no mini criaria uma
    segunda fonte da mesma frase.
  · Tudo o que o CLIENTE compõe sozinho — título de cartão, texto de botão,
    rótulo da flag no painel do owner — vive SÓ em `miniapp/i18n/{pt,en,es}.json`.

DÍVIDA PAGA DE PASSAGEM: `marca_do_tracado` (a 25ª flag, shipada em 09/08)
nasceu SEM `feature_marca_do_tracado` / `_desc` em nenhum dos 3 locales do
mini-app — o painel do owner mostra a KEY CRUA hoje (`t()` faz
`dict[key] ?? STRINGS.pt[key] ?? key`, degrada em silêncio, e nenhum
verificador bate `DEFAULT_WORLD_FEATURES` contra os locales). Entra aqui para
não repetir o defeito pela segunda vez com a `caravana`.
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ══════════════════════════════════════════════════════════════════════════
# CHAT — `locales/{pt,en,es}.json` (server-resolved)
# ══════════════════════════════════════════════════════════════════════════
CHAT: dict[str, dict[str, str]] = {
    "pt": {
        # ── A disclosure: a frase que faltava ao jogo inteiro ──────────────
        "crv_origin_born": "Nasce em {places}",
        "crv_origin_gate": "(portal a partir do reino {r})",
        "crv_origin_also": "também vem de {sources}",
        "crv_src_hunt": "caçada difícil",
        "crv_src_beast": "expedição de fera",
        "crv_src_boss": "chefe do mundo",
        "crv_src_dismantle": "desmonte de artefato",
        "crv_src_encargo": "encargo de cidade",
        "crv_origin_unknown": "Ninguém sabe dizer onde isso nasce.",
        # ── Os velhos ──────────────────────────────────────────────────────
        "crv_npc_wanshi_name": "Velho Lù, mestre da caravana",
        "crv_npc_wanshi_intro": "Tudo o que se compra, se compra aqui — e o que não se compra, alguém vai buscar. Diga o que falta.",
        "crv_npc_tiequan_name": "Irmão Gāng, o carregador",
        "crv_npc_tiequan_intro": "A estrada do norte é gelo. Eu levo o seu material e trago o que o rio guarda. Mas eu olho para quem me entrega.",
        "crv_npc_wanhua_name": "Senhora Méi, das mudas",
        "crv_npc_wanhua_intro": "Muda viaja mal, mas viaja. E não me pergunte o preço em pedras: aqui não se paga com pedras.",
        "crv_npc_tianhuo_name": "Velho Yán, do fole",
        "crv_npc_tianhuo_intro": "O fole não para. Se falta material, eu mando um recado — e o recado demora.",
        "crv_npc_huiyin_name": "Nenhum caravaneiro",
        "crv_npc_huiyin_intro": "Nenhuma caravana entra na Cidade dos Ecos. Aqui só se chega indo.",
        # ── O velho nunca se vende como o melhor caminho ───────────────────
        "crv_better_to_go": "Se você puder ir, vá: a estrada rende mais do que a minha mula.",
        "crv_no_caravan_here": "Nenhuma caravana entra aqui. Na Cidade dos Ecos, só se chega indo.",
        "crv_in_transit": "Uma carga está na estrada. Chega em cerca de {h}h.",
        "crv_sent": "O recado partiu. {n} unidades chegam em cerca de {h}h.",
        # ── As recusas — cada uma diz o motivo E o requisito (Lei §1) ──────
        "crv_refuse_flag": "A caravana não passa por aqui.",
        "crv_refuse_no_caravan": "Nenhuma caravana entra aqui. Só se chega indo.",
        "crv_refuse_karma": "O velho olha o seu karma ({k}) e recolhe as mãos: ele não pega no material de quem está abaixo de {min}.",
        "crv_refuse_path": "O Jardim vira as costas ao caminho demoníaco. Procure caravana em outra cidade.",
        "crv_refuse_open": "A última carga ainda não chegou. Faltam cerca de {h}h.",
        "crv_refuse_here": "Isso você tira do chão aqui mesmo, em {place}. O velho recusa o seu material.",
        "crv_refuse_not_routable": "A caravana não vai buscar isso.",
        "crv_refuse_encargo": "O que tínhamos foi tudo para o Encargo: {name}.",
        "crv_refuse_pay_invalid": "O velho não aceita esse material como pagamento.",
        "crv_refuse_pay_short": "Falta material: o velho pede {n} unidades.",
        "crv_refuse_busy": "O velho está ocupado. Tente de novo em instantes.",
        "crv_encargo_generic": "o encargo da cidade",
        # ── A praça do chat ────────────────────────────────────────────────
        "crv_plaza_title": "🐫 商队 A Caravana",
        "crv_plaza_arrived": "🐫 A caravana chegou: {emoji} {name} ×{n}.",
        "crv_plaza_bagfull": "🐫 A caravana trouxe {emoji} {name}, mas o seu anel está cheio. A carga espera.",
        "crv_plaza_atlas_title": "🗺️ Onde nascem as coisas",
        "crv_atlas_here": "você tira daqui",
        "crv_btn_send": "{emoji} {name} ×{n} — paga {cost} {pay}",
        "crv_plaza_hint": "Toque num material para mandar vir. O custo está no botão.",
    },
    "en": {
        "crv_origin_born": "Born in {places}",
        "crv_origin_gate": "(portal from realm {r})",
        "crv_origin_also": "also comes from {sources}",
        "crv_src_hunt": "hard hunts",
        "crv_src_beast": "beast expeditions",
        "crv_src_boss": "world bosses",
        "crv_src_dismantle": "artifact dismantling",
        "crv_src_encargo": "city commissions",
        "crv_origin_unknown": "No one can say where that is born.",
        "crv_npc_wanshi_name": "Elder Lù, caravan master",
        "crv_npc_wanshi_intro": "Everything that is bought is bought here — and what is not bought, someone fetches. Say what you lack.",
        "crv_npc_tiequan_name": "Brother Gāng, the hauler",
        "crv_npc_tiequan_intro": "The northern road is ice. I take your material and bring back what the river keeps. But I look hard at who hands it to me.",
        "crv_npc_wanhua_name": "Lady Méi, of the seedlings",
        "crv_npc_wanhua_intro": "Seedlings travel badly, but they travel. And do not ask me a price in stones: nothing here is paid in stones.",
        "crv_npc_tianhuo_name": "Elder Yán, of the bellows",
        "crv_npc_tianhuo_intro": "The bellows never stop. If material runs short I send word — and word is slow.",
        "crv_npc_huiyin_name": "No caravan master",
        "crv_npc_huiyin_intro": "No caravan enters the City of Echoes. Here you only arrive by going.",
        "crv_better_to_go": "Go yourself if you can: the road yields more than my mule.",
        "crv_no_caravan_here": "No caravan enters here. In the City of Echoes you only arrive by going.",
        "crv_in_transit": "A load is on the road. It arrives in about {h}h.",
        "crv_sent": "Word has gone out. {n} units arrive in about {h}h.",
        "crv_refuse_flag": "The caravan does not pass through here.",
        "crv_refuse_no_caravan": "No caravan enters here. You only arrive by going.",
        "crv_refuse_karma": "The old man looks at your karma ({k}) and draws his hands back: he takes no material from anyone below {min}.",
        "crv_refuse_path": "The Garden turns its back on the demonic path. Seek a caravan in another city.",
        "crv_refuse_open": "The last load has not arrived yet. About {h}h to go.",
        "crv_refuse_here": "You pull that out of the ground right here, in {place}. The old man refuses your material.",
        "crv_refuse_not_routable": "The caravan does not fetch that.",
        "crv_refuse_encargo": "Everything we had went to the Commission: {name}.",
        "crv_refuse_pay_invalid": "The old man does not take that material as payment.",
        "crv_refuse_pay_short": "Not enough material: the old man asks for {n} units.",
        "crv_refuse_busy": "The old man is busy. Try again in a moment.",
        "crv_encargo_generic": "the city commission",
        "crv_plaza_title": "🐫 商队 The Caravan",
        "crv_plaza_arrived": "🐫 The caravan arrived: {emoji} {name} ×{n}.",
        "crv_plaza_bagfull": "🐫 The caravan brought {emoji} {name}, but your ring is full. The load waits.",
        "crv_plaza_atlas_title": "🗺️ Where things are born",
        "crv_atlas_here": "you pull it from here",
        "crv_btn_send": "{emoji} {name} ×{n} — pays {cost} {pay}",
        "crv_plaza_hint": "Tap a material to send for it. The cost is on the button.",
    },
    "es": {
        "crv_origin_born": "Nace en {places}",
        "crv_origin_gate": "(portal desde el reino {r})",
        "crv_origin_also": "también viene de {sources}",
        "crv_src_hunt": "cacería difícil",
        "crv_src_beast": "expedición de bestia",
        "crv_src_boss": "jefe del mundo",
        "crv_src_dismantle": "desmontaje de artefacto",
        "crv_src_encargo": "encargo de ciudad",
        "crv_origin_unknown": "Nadie sabe decir dónde nace eso.",
        "crv_npc_wanshi_name": "Anciano Lù, maestro de la caravana",
        "crv_npc_wanshi_intro": "Todo lo que se compra, se compra aquí — y lo que no se compra, alguien va a buscarlo. Diga qué le falta.",
        "crv_npc_tiequan_name": "Hermano Gāng, el porteador",
        "crv_npc_tiequan_intro": "El camino del norte es hielo. Llevo su material y traigo lo que el río guarda. Pero miro bien a quien me lo entrega.",
        "crv_npc_wanhua_name": "Señora Méi, de los esquejes",
        "crv_npc_wanhua_intro": "El esqueje viaja mal, pero viaja. Y no me pregunte el precio en piedras: aquí no se paga con piedras.",
        "crv_npc_tianhuo_name": "Anciano Yán, del fuelle",
        "crv_npc_tianhuo_intro": "El fuelle no para. Si falta material mando un recado — y el recado tarda.",
        "crv_npc_huiyin_name": "Ningún caravanero",
        "crv_npc_huiyin_intro": "Ninguna caravana entra en la Ciudad de los Ecos. Aquí solo se llega yendo.",
        "crv_better_to_go": "Si usted puede ir, vaya: el camino rinde más que mi mula.",
        "crv_no_caravan_here": "Ninguna caravana entra aquí. En la Ciudad de los Ecos solo se llega yendo.",
        "crv_in_transit": "Una carga está en el camino. Llega en unas {h}h.",
        "crv_sent": "El recado partió. {n} unidades llegan en unas {h}h.",
        "crv_refuse_flag": "La caravana no pasa por aquí.",
        "crv_refuse_no_caravan": "Ninguna caravana entra aquí. Solo se llega yendo.",
        "crv_refuse_karma": "El anciano mira su karma ({k}) y retira las manos: no toma material de quien está por debajo de {min}.",
        "crv_refuse_path": "El Jardín da la espalda al camino demoníaco. Busque caravana en otra ciudad.",
        "crv_refuse_open": "La última carga aún no llegó. Faltan unas {h}h.",
        "crv_refuse_here": "Eso lo saca del suelo aquí mismo, en {place}. El anciano rechaza su material.",
        "crv_refuse_not_routable": "La caravana no va a buscar eso.",
        "crv_refuse_encargo": "Lo que teníamos se fue todo al Encargo: {name}.",
        "crv_refuse_pay_invalid": "El anciano no acepta ese material como pago.",
        "crv_refuse_pay_short": "Falta material: el anciano pide {n} unidades.",
        "crv_refuse_busy": "El anciano está ocupado. Inténtelo de nuevo en un momento.",
        "crv_encargo_generic": "el encargo de la ciudad",
        "crv_plaza_title": "🐫 商队 La Caravana",
        "crv_plaza_arrived": "🐫 La caravana llegó: {emoji} {name} ×{n}.",
        "crv_plaza_bagfull": "🐫 La caravana trajo {emoji} {name}, pero su anillo está lleno. La carga espera.",
        "crv_plaza_atlas_title": "🗺️ Dónde nacen las cosas",
        "crv_atlas_here": "usted lo saca de aquí",
        "crv_btn_send": "{emoji} {name} ×{n} — paga {cost} {pay}",
        "crv_plaza_hint": "Toque un material para mandarlo traer. El costo está en el botón.",
    },
}


# ══════════════════════════════════════════════════════════════════════════
# MINI — `miniapp/i18n/{pt,en,es}.json` (composto pelo CLIENTE)
# ══════════════════════════════════════════════════════════════════════════
_DESC_CARAVANA = {
    "pt": "MV-9.5 商队 — o jogo passa a DIZER onde nasce cada material (a origem é a união MEDIDA das fontes vivas, nunca uma exclusividade falsa) e a cidade ganha um velho que manda vir o que a montanha do outro lado guarda: escambo material↔material com prazo, razão desfavorável (é sink), recusa por lugar/carga aberta/Encargo/karma-Caminho, e ZERO pedras no fluxo. Mòyǔ não tem caravana. EXIGE `cidades` E `dungeons_regionais` ON — sem portais ancorados a geografia não existe e a frase seria mentira.",
    "en": "MV-9.5 商队 — the game finally SAYS where each material is born (origin is the MEASURED union of live sources, never a false exclusivity) and each city gains an old man who sends for what the far mountain keeps: material-for-material barter with a delay, an unfavourable ratio (it is a sink), refusals by place / open load / Commission / karma-Path, and ZERO stones in the flow. Mòyǔ has no caravan. REQUIRES `cidades` AND `dungeons_regionais` ON — without anchored portals there is no geography and the line would be a lie.",
    "es": "MV-9.5 商队 — el juego por fin DICE dónde nace cada material (el origen es la unión MEDIDA de las fuentes vivas, nunca una exclusividad falsa) y la ciudad gana un anciano que manda traer lo que guarda la montaña de enfrente: trueque material↔material con plazo, razón desfavorable (es sumidero), rechazos por lugar / carga abierta / Encargo / karma-Camino, y CERO piedras en el flujo. Mòyǔ no tiene caravana. EXIGE `cidades` Y `dungeons_regionais` ON — sin portales anclados no hay geografía y la frase sería mentira.",
}
_DESC_MARCA = {
    "pt": "印记 Marca do Traçado — maestria POR FORMAÇÃO, contada em ativações no corpo (a caverna não conta). Três degraus visíveis: 印 Traço (50) mais duração · 沟 Sulco (200) desconto no craft dela · 印记 Marca (1000) título cosmético. Nunca toca na potência do buff, nunca torna a formação permanente e o título nunca dá bônus. Trocar de formação custa a maestria acumulada — é o dilema, não um efeito colateral.",
    "en": "印记 Mark of the Tracing — mastery PER FORMATION, counted in activations on the body (the cavern does not count). Three visible steps: 印 Stroke (50) longer duration · 沟 Groove (200) cheaper craft of that formation · 印记 Mark (1000) cosmetic title. It never touches buff power, never makes a formation permanent, and the title never grants a bonus. Switching formations costs the accumulated mastery — that is the dilemma, not a side effect.",
    "es": "印记 Marca del Trazo — maestría POR FORMACIÓN, contada en activaciones en el cuerpo (la caverna no cuenta). Tres escalones visibles: 印 Trazo (50) más duración · 沟 Surco (200) descuento en su fabricación · 印记 Marca (1000) título cosmético. Nunca toca la potencia del buff, nunca vuelve permanente la formación y el título nunca da bonificación. Cambiar de formación cuesta la maestría acumulada — ese es el dilema, no un efecto secundario.",
}

MINI: dict[str, dict[str, str]] = {
    "pt": {
        "feature_caravana": "商队 A Caravana",
        "feature_caravana_desc": _DESC_CARAVANA["pt"],
        "feature_marca_do_tracado": "印记 Marca do Traçado",
        "feature_marca_do_tracado_desc": _DESC_MARCA["pt"],
        "crv_card_title": "商队 A Caravana",
        "crv_card_cta": "Mandar vir o que falta",
        "crv_modal_title": "商队 A Caravana",
        "crv_routes_title": "O que ele vai buscar",
        "crv_atlas_title": "Onde nascem as coisas",
        "crv_pay_title": "Pagar com",
        "crv_send_btn": "Mandar vir",
        "crv_here_badge": "daqui",
        "crv_cost_label": "custa",
        "crv_transit_title": "Na estrada",
        "crv_empty": "Hoje o velho não vai a lugar nenhum.",
        "crv_origin_head": "Onde nasce",
        "crv_pick_pay": "Escolha o que entregar",
        "hub_mundo_caravana": "Caravana",
        # §4.2 dívida 1 — o botão 💰 "Mercador" da praça deep-linka para um
        # mercado com ZERO ofertas abertas em 239 jogadores, e o vazio era uma
        # lista em branco: dead-end de Lei §1 JÁ em produção. O Quadro de
        # Recompensas ao lado ensina a geografia no vazio dele
        # (`bounty_board_empty_hint`); o mercado não tinha o equivalente.
        # Independente da flag — vale para os 239 do `main`.
        "market_empty_hint": "As ofertas vêm de outros cultivadores. Quando alguém anunciar, aparece aqui.",
    },
    "en": {
        "feature_caravana": "商队 The Caravan",
        "feature_caravana_desc": _DESC_CARAVANA["en"],
        "feature_marca_do_tracado": "印记 Mark of the Tracing",
        "feature_marca_do_tracado_desc": _DESC_MARCA["en"],
        "crv_card_title": "商队 The Caravan",
        "crv_card_cta": "Send for what you lack",
        "crv_modal_title": "商队 The Caravan",
        "crv_routes_title": "What he will fetch",
        "crv_atlas_title": "Where things are born",
        "crv_pay_title": "Pay with",
        "crv_send_btn": "Send for it",
        "crv_here_badge": "from here",
        "crv_cost_label": "costs",
        "crv_transit_title": "On the road",
        "crv_empty": "Today the old man goes nowhere.",
        "crv_origin_head": "Where it is born",
        "crv_pick_pay": "Choose what to hand over",
        "hub_mundo_caravana": "Caravan",
        "market_empty_hint": "Listings come from other cultivators. When someone posts one, it shows up here.",
    },
    "es": {
        "feature_caravana": "商队 La Caravana",
        "feature_caravana_desc": _DESC_CARAVANA["es"],
        "feature_marca_do_tracado": "印记 Marca del Trazo",
        "feature_marca_do_tracado_desc": _DESC_MARCA["es"],
        "crv_card_title": "商队 La Caravana",
        "crv_card_cta": "Mandar traer lo que falta",
        "crv_modal_title": "商队 La Caravana",
        "crv_routes_title": "Lo que él irá a buscar",
        "crv_atlas_title": "Dónde nacen las cosas",
        "crv_pay_title": "Pagar con",
        "crv_send_btn": "Mandar traer",
        "crv_here_badge": "de aquí",
        "crv_cost_label": "cuesta",
        "crv_transit_title": "En el camino",
        "crv_empty": "Hoy el anciano no va a ninguna parte.",
        "crv_origin_head": "Dónde nace",
        "crv_pick_pay": "Elija qué entregar",
        "hub_mundo_caravana": "Caravana",
        "market_empty_hint": "Los anuncios vienen de otros cultivadores. Cuando alguien publique uno, aparece aquí.",
    },
}

# Nada é reescrito nesta onda: `city_wanshi_intro` ("tudo o que se compra, se
# compra aqui") deixa de ser mentira porque a caravana de Wànshì passa a mandar
# vir os três materiais que Línghé não produz — a frase vira VERDADE sem se
# tocar num carácter dela. (§6.3 do spec: o owner decidiria reescrevê-la; esta
# onda torna a reescrita desnecessária.)
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
