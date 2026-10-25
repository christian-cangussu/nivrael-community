"""scripts/inject_onda5fase2_i18n.py — Onda 5 Fase 2 i18n keys (chat + mini-app).

Cavernas Pessoais 洞府 + Matrizes/Formações 阵法: formation catalog names/descs,
effect labels + formatters, cavern surface, the activate-target choice, the
new-world teasers wave 2 (worldboss/rivalry/cultivable/hardgate — the
caverns/matrices teasers GRADUATED to live features), and chat/mini chrome.

Idempotent: only adds keys that don't exist yet. Run once, commit the JSONs.
Rules: pt = PT-BR (você/seu, ativo); every {token} placeholder appears at most
ONCE per string (t() replaces only the first); placeholders stay ASCII.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── _SHARED — same keys on both surfaces (chat locales/ + miniapp/i18n/) ───────
_SHARED = {
    "pt": {
        # Formation catalog (names + descriptions)
        "formation_name_divine_eye": "Olho do Sentido Divino",
        "formation_desc_divine_eye": "Aguça o Sentido Divino: você enxerga mais caminhos e pistas ao explorar.",
        "formation_name_spirit_edge": "Matriz do Gume Espiritual",
        "formation_desc_spirit_edge": "Lâminas de Qi orbitam seu corpo, afiando cada golpe.",
        "formation_name_stone_carapace": "Matriz da Carapaça de Pedra",
        "formation_desc_stone_carapace": "A terra responde ao seu chamado e endurece sua defesa.",
        "formation_name_qi_spiral": "Matriz da Espiral de Qi",
        "formation_desc_qi_spiral": "Uma espiral que condensa o Qi do ambiente — sua recuperação acelera.",
        "formation_name_hidden_veil": "Matriz do Véu Oculto",
        "formation_desc_hidden_veil": "Um véu que esconde seu saco da morte: você perde bem menos ao cair explorando.",
        "formation_name_dao_mirror": "Matriz do Espelho do Dao",
        "formation_desc_dao_mirror": "Um espelho que reflete as 3000 Leis — sua compreensão do Dao se aprofunda.",
        "formation_name_dragon_edge": "Matriz do Gume do Dragão",
        "formation_desc_dragon_edge": "O rugido de um dragão ancestral habita suas mãos por horas.",
        "formation_name_celestial_wall": "Matriz da Muralha Celestial",
        "formation_desc_celestial_wall": "Uma muralha invisível entre você e o mundo.",
        "formation_name_void_breath": "Matriz da Respiração do Vazio",
        "formation_desc_void_breath": "A respiração do Vazio cultiva por você durante a noite inteira.",
        "formation_name_nine_heavens_veil": "Matriz Celestial dos Nove Céus",
        "formation_desc_nine_heavens_veil": "O véu supremo dos Nove Céus — quase nada escapa de você na morte.",
        # Effect labels + formatters
        "formation_effect_bp_boost": "Ataque",
        "formation_effect_defense_boost": "Defesa",
        "formation_effect_qi_regen_boost": "Eficiência de Qi",
        "formation_effect_dao_fragment_chance": "Compreensão do Dao",
        "formation_effect_perception_boost": "Clareza do Sentido Divino",
        "formation_effect_explore_protection": "Proteção na Exploração",
        "formation_fx_mult": "+{pct}% {label}",
        "formation_fx_prot": "{label} (-{pct}% da perda)",
        # Formations surface
        "formations_title": "Matrizes & Formações",
        "formations_intro": "Crafte Formações com os materiais da exploração e das masmorras. Ative no corpo (buff temporizado) ou deixe vibrando na sua Caverna.",
        "formation_craft_btn": "Craftar",
        "formation_activate_btn": "Ativar",
        "formation_crafted": "Formação craftada! Ela está no seu bolso de Formações.",
        "formation_activated_body": "Formação ativa no corpo por {duration}.",
        # Reasons (disclosed no-ops)
        "formation_no_stones": "Pedras espirituais insuficientes (precisa de {cost}).",
        "formation_no_materials": "Materiais insuficientes — explore para coletar mais.",
        "formation_realm_low": "Seu reino é baixo demais (precisa do reino {realm}).",
        "formation_already_active": "Já existe um efeito deste tipo ativo — espere ele expirar.",
        "formation_not_owned": "Você não possui esta Formação — crafte primeiro.",
        "formation_not_found": "Formação desconhecida.",
        # Cavern surface
        "cavern_title": "Caverna Pessoal",
        "cavern_intro": "Seu lar dentro do mundo: a caverna cultiva Qi enquanto você está fora (com teto) e abriga uma Formação de cultivo.",
        "cavern_none": "Você ainda não estabeleceu uma caverna.",
        "cavern_none_yet": "Estabeleça sua caverna no continente onde você está.",
        "cavern_already": "Você já estabeleceu sua caverna.",
        "cavern_established": "Caverna estabelecida! (-{stones} pedras)",
        "cavern_establish_btn": "Estabelecer Caverna",
        "cavern_rate_preview": "Rende ~{rate} Qi/h em idle, com teto de {cap}h.",
        "cavern_status_line": "Caverna em {continent} · ~{rate} Qi/h",
        "cavern_idle_line": "Qi acumulado: {accrued}/{cap}",
        "cavern_claim_btn": "Coletar {qi} Qi",
        "cavern_claimed": "Você coletou {qi} Qi da caverna.",
        "cavern_claim_truncated": "Seu Qi encheu — o excedente se dissipou.",
        "cavern_qi_full": "Seu Qi está cheio — gaste um pouco antes de coletar.",
        "cavern_nothing_accrued": "A caverna ainda não acumulou energia.",
        "cavern_dao_fragment": "A Formação revelou um fragmento de {law}!",
        "cavern_slot_empty": "Nenhuma Formação na caverna. Ative uma Formação de cultivo (🏯) aqui.",
        "cavern_slot_occupied": "Já existe uma Formação vibrando na caverna.",
        "cavern_slot_expired": "expirada",
        "cavern_not_cavern_type": "Esta Formação só funciona no corpo — a caverna aceita Formações de cultivo.",
        "cavern_formation_set": "A Formação agora vibra na sua caverna.",
        "cavern_cleared": "O slot da caverna foi esvaziado.",
        "cavern_clear_btn": "Esvaziar slot",
        # New-world teasers wave 2 (caverns/matrices graduated to live)
        "explore_teaser_worldboss_title": "World Boss por Continente",
        "explore_teaser_worldboss_body": "Cada continente terá seu próprio terror ancestral — e Marés Demoníacas que ameaçam o mundo inteiro.",
        "explore_teaser_rivalry_title": "Eventos de Rivalidade",
        "explore_teaser_rivalry_body": "As 9 Seitas Anciãs têm contas antigas a acertar — e você vai escolher um lado.",
        "explore_teaser_cultivable_title": "Reinos Cultiváveis",
        "explore_teaser_cultivable_body": "Solo de Tribulação, Origem do Dao… reinos onde lutar pode disparar uma Tribulação que fere — ou tempera sua fundação.",
        "explore_teaser_hardgate_title": "Continentes com Identidade",
        "explore_teaser_hardgate_body": "No novo mundo, cada continente guarda conteúdo próprio — viajar será uma decisão de verdade.",
    },
    "en": {
        "formation_name_divine_eye": "Eye of the Divine Sense",
        "formation_desc_divine_eye": "Sharpens the Divine Sense: you see more paths and clues while exploring.",
        "formation_name_spirit_edge": "Spirit Edge Matrix",
        "formation_desc_spirit_edge": "Blades of Qi orbit your body, sharpening every strike.",
        "formation_name_stone_carapace": "Stone Carapace Matrix",
        "formation_desc_stone_carapace": "The earth answers your call and hardens your defense.",
        "formation_name_qi_spiral": "Qi Spiral Matrix",
        "formation_desc_qi_spiral": "A spiral that condenses ambient Qi — your recovery accelerates.",
        "formation_name_hidden_veil": "Hidden Veil Matrix",
        "formation_desc_hidden_veil": "A veil that hides your bag from death: you lose far less when falling in exploration.",
        "formation_name_dao_mirror": "Dao Mirror Matrix",
        "formation_desc_dao_mirror": "A mirror reflecting the 3000 Laws — your Dao comprehension deepens.",
        "formation_name_dragon_edge": "Dragon Edge Matrix",
        "formation_desc_dragon_edge": "An ancestral dragon's roar dwells in your hands for hours.",
        "formation_name_celestial_wall": "Celestial Wall Matrix",
        "formation_desc_celestial_wall": "An invisible wall between you and the world.",
        "formation_name_void_breath": "Void Breath Matrix",
        "formation_desc_void_breath": "The Void's breath cultivates for you through the whole night.",
        "formation_name_nine_heavens_veil": "Nine Heavens Celestial Veil",
        "formation_desc_nine_heavens_veil": "The supreme veil of the Nine Heavens — almost nothing escapes you in death.",
        "formation_effect_bp_boost": "Attack",
        "formation_effect_defense_boost": "Defense",
        "formation_effect_qi_regen_boost": "Qi Efficiency",
        "formation_effect_dao_fragment_chance": "Dao Comprehension",
        "formation_effect_perception_boost": "Divine Sense Clarity",
        "formation_effect_explore_protection": "Exploration Protection",
        "formation_fx_mult": "+{pct}% {label}",
        "formation_fx_prot": "{label} (-{pct}% loss)",
        "formations_title": "Matrices & Formations",
        "formations_intro": "Craft Formations from exploration and dungeon materials. Activate on the body (timed buff) or let one hum in your Cavern.",
        "formation_craft_btn": "Craft",
        "formation_activate_btn": "Activate",
        "formation_crafted": "Formation crafted! It is in your Formation pouch.",
        "formation_activated_body": "Formation active on the body for {duration}.",
        "formation_no_stones": "Not enough spirit stones (needs {cost}).",
        "formation_no_materials": "Not enough materials — explore to gather more.",
        "formation_realm_low": "Your realm is too low (needs realm {realm}).",
        "formation_already_active": "An effect of this type is already active — wait for it to expire.",
        "formation_not_owned": "You don't own this Formation — craft it first.",
        "formation_not_found": "Unknown Formation.",
        "cavern_title": "Personal Cavern",
        "cavern_intro": "Your home inside the world: the cavern cultivates Qi while you are away (capped) and houses one cultivation Formation.",
        "cavern_none": "You haven't established a cavern yet.",
        "cavern_none_yet": "Establish your cavern on the continent you are in.",
        "cavern_already": "You already established your cavern.",
        "cavern_established": "Cavern established! (-{stones} stones)",
        "cavern_establish_btn": "Establish Cavern",
        "cavern_rate_preview": "Yields ~{rate} Qi/h idle, capped at {cap}h.",
        "cavern_status_line": "Cavern in {continent} · ~{rate} Qi/h",
        "cavern_idle_line": "Accrued Qi: {accrued}/{cap}",
        "cavern_claim_btn": "Claim {qi} Qi",
        "cavern_claimed": "You claimed {qi} Qi from the cavern.",
        "cavern_claim_truncated": "Your Qi filled up — the excess dissipated.",
        "cavern_qi_full": "Your Qi is full — spend some before claiming.",
        "cavern_nothing_accrued": "The cavern hasn't accrued energy yet.",
        "cavern_dao_fragment": "The Formation revealed a fragment of {law}!",
        "cavern_slot_empty": "No Formation in the cavern. Activate a cultivation Formation (🏯) here.",
        "cavern_slot_occupied": "A Formation is already humming in the cavern.",
        "cavern_slot_expired": "expired",
        "cavern_not_cavern_type": "This Formation only works on the body — the cavern takes cultivation Formations.",
        "cavern_formation_set": "The Formation now hums in your cavern.",
        "cavern_cleared": "The cavern slot was emptied.",
        "cavern_clear_btn": "Empty slot",
        "explore_teaser_worldboss_title": "World Boss per Continent",
        "explore_teaser_worldboss_body": "Each continent will have its own ancestral terror — and Demon Tides threatening the whole world.",
        "explore_teaser_rivalry_title": "Rivalry Events",
        "explore_teaser_rivalry_body": "The 9 Ancient Sects have old scores to settle — and you will pick a side.",
        "explore_teaser_cultivable_title": "Cultivable Realms",
        "explore_teaser_cultivable_body": "Tribulation Ground, Dao Origin… realms where fighting can trigger a Tribulation that wounds — or tempers your foundation.",
        "explore_teaser_hardgate_title": "Continents with Identity",
        "explore_teaser_hardgate_body": "In the new world each continent holds its own content — travel will be a real decision.",
    },
    "es": {
        "formation_name_divine_eye": "Ojo del Sentido Divino",
        "formation_desc_divine_eye": "Agudiza el Sentido Divino: ves más caminos y pistas al explorar.",
        "formation_name_spirit_edge": "Matriz del Filo Espiritual",
        "formation_desc_spirit_edge": "Hojas de Qi orbitan tu cuerpo, afilando cada golpe.",
        "formation_name_stone_carapace": "Matriz del Caparazón de Piedra",
        "formation_desc_stone_carapace": "La tierra responde a tu llamado y endurece tu defensa.",
        "formation_name_qi_spiral": "Matriz de la Espiral de Qi",
        "formation_desc_qi_spiral": "Una espiral que condensa el Qi del ambiente — tu recuperación se acelera.",
        "formation_name_hidden_veil": "Matriz del Velo Oculto",
        "formation_desc_hidden_veil": "Un velo que esconde tu saco de la muerte: pierdes mucho menos al caer explorando.",
        "formation_name_dao_mirror": "Matriz del Espejo del Dao",
        "formation_desc_dao_mirror": "Un espejo que refleja las 3000 Leyes — tu comprensión del Dao se profundiza.",
        "formation_name_dragon_edge": "Matriz del Filo del Dragón",
        "formation_desc_dragon_edge": "El rugido de un dragón ancestral habita tus manos por horas.",
        "formation_name_celestial_wall": "Matriz de la Muralla Celestial",
        "formation_desc_celestial_wall": "Una muralla invisible entre tú y el mundo.",
        "formation_name_void_breath": "Matriz de la Respiración del Vacío",
        "formation_desc_void_breath": "La respiración del Vacío cultiva por ti durante toda la noche.",
        "formation_name_nine_heavens_veil": "Matriz Celestial de los Nueve Cielos",
        "formation_desc_nine_heavens_veil": "El velo supremo de los Nueve Cielos — casi nada se te escapa en la muerte.",
        "formation_effect_bp_boost": "Ataque",
        "formation_effect_defense_boost": "Defensa",
        "formation_effect_qi_regen_boost": "Eficiencia de Qi",
        "formation_effect_dao_fragment_chance": "Comprensión del Dao",
        "formation_effect_perception_boost": "Claridad del Sentido Divino",
        "formation_effect_explore_protection": "Protección en la Exploración",
        "formation_fx_mult": "+{pct}% {label}",
        "formation_fx_prot": "{label} (-{pct}% de pérdida)",
        "formations_title": "Matrices y Formaciones",
        "formations_intro": "Craftea Formaciones con los materiales de la exploración y las mazmorras. Actívalas en el cuerpo (buff temporal) o deja una vibrando en tu Caverna.",
        "formation_craft_btn": "Craftear",
        "formation_activate_btn": "Activar",
        "formation_crafted": "¡Formación crafteada! Está en tu bolsa de Formaciones.",
        "formation_activated_body": "Formación activa en el cuerpo por {duration}.",
        "formation_no_stones": "Piedras espirituales insuficientes (necesita {cost}).",
        "formation_no_materials": "Materiales insuficientes — explora para reunir más.",
        "formation_realm_low": "Tu reino es demasiado bajo (necesita el reino {realm}).",
        "formation_already_active": "Ya hay un efecto de este tipo activo — espera a que expire.",
        "formation_not_owned": "No posees esta Formación — craftéala primero.",
        "formation_not_found": "Formación desconocida.",
        "cavern_title": "Caverna Personal",
        "cavern_intro": "Tu hogar dentro del mundo: la caverna cultiva Qi mientras no estás (con tope) y aloja una Formación de cultivo.",
        "cavern_none": "Aún no estableciste una caverna.",
        "cavern_none_yet": "Establece tu caverna en el continente donde estás.",
        "cavern_already": "Ya estableciste tu caverna.",
        "cavern_established": "¡Caverna establecida! (-{stones} piedras)",
        "cavern_establish_btn": "Establecer Caverna",
        "cavern_rate_preview": "Rinde ~{rate} Qi/h en idle, con tope de {cap}h.",
        "cavern_status_line": "Caverna en {continent} · ~{rate} Qi/h",
        "cavern_idle_line": "Qi acumulado: {accrued}/{cap}",
        "cavern_claim_btn": "Recoger {qi} Qi",
        "cavern_claimed": "Recogiste {qi} Qi de la caverna.",
        "cavern_claim_truncated": "Tu Qi se llenó — el excedente se disipó.",
        "cavern_qi_full": "Tu Qi está lleno — gasta un poco antes de recoger.",
        "cavern_nothing_accrued": "La caverna aún no acumuló energía.",
        "cavern_dao_fragment": "¡La Formación reveló un fragmento de {law}!",
        "cavern_slot_empty": "Ninguna Formación en la caverna. Activa una Formación de cultivo (🏯) aquí.",
        "cavern_slot_occupied": "Ya hay una Formación vibrando en la caverna.",
        "cavern_slot_expired": "expirada",
        "cavern_not_cavern_type": "Esta Formación solo funciona en el cuerpo — la caverna acepta Formaciones de cultivo.",
        "cavern_formation_set": "La Formación ahora vibra en tu caverna.",
        "cavern_cleared": "El slot de la caverna fue vaciado.",
        "cavern_clear_btn": "Vaciar slot",
        "explore_teaser_worldboss_title": "World Boss por Continente",
        "explore_teaser_worldboss_body": "Cada continente tendrá su propio terror ancestral — y Mareas Demoníacas que amenazan al mundo entero.",
        "explore_teaser_rivalry_title": "Eventos de Rivalidad",
        "explore_teaser_rivalry_body": "Las 9 Sectas Ancianas tienen cuentas viejas que saldar — y tú elegirás un lado.",
        "explore_teaser_cultivable_title": "Reinos Cultivables",
        "explore_teaser_cultivable_body": "Suelo de Tribulación, Origen del Dao… reinos donde luchar puede disparar una Tribulación que hiere — o templa tu fundación.",
        "explore_teaser_hardgate_title": "Continentes con Identidad",
        "explore_teaser_hardgate_body": "En el nuevo mundo cada continente guarda contenido propio — viajar será una decisión de verdad.",
    },
}

# ── _CHAT — extra chat-only keys ───────────────────────────────────────────────
_CHAT = {
    "pt": {
        "buff_explore_protection": "Véu de Proteção (exploração)",
        "cavern_open_miniapp": "🏯 Abra a Caverna no mini-app para a experiência completa (barra de idle, slot e craft).",
        "cavern_establish_cost": "Custo: 🪨 {stones}",
        "cavern_slot_remaining": "{minutes}min restantes",
        "formations_stones": "🪨 Pedras: {stones}",
        "formations_hint": "🏯 = pode vibrar na caverna (ative em /caverna)",
    },
    "en": {
        "buff_explore_protection": "Protection Veil (exploration)",
        "cavern_open_miniapp": "🏯 Open the Cavern in the mini-app for the full experience (idle bar, slot and craft).",
        "cavern_establish_cost": "Cost: 🪨 {stones}",
        "cavern_slot_remaining": "{minutes}min remaining",
        "formations_stones": "🪨 Stones: {stones}",
        "formations_hint": "🏯 = can hum in the cavern (activate via /caverna)",
    },
    "es": {
        "buff_explore_protection": "Velo de Protección (exploración)",
        "cavern_open_miniapp": "🏯 Abre la Caverna en el mini-app para la experiencia completa (barra de idle, slot y craft).",
        "cavern_establish_cost": "Costo: 🪨 {stones}",
        "cavern_slot_remaining": "{minutes}min restantes",
        "formations_stones": "🪨 Piedras: {stones}",
        "formations_hint": "🏯 = puede vibrar en la caverna (actívala en /caverna)",
    },
}

# ── _MINI — extra mini-app-only keys (tab/home-card/UI chrome) ─────────────────
_MINI = {
    "pt": {
        "pill_eff_explore_protection": "Véu de Proteção (exploração)",
        "tab_cavern": "Caverna",
        "home_card_cavern": "Caverna 洞府",
        "cavern_explore_hint": "Transforme o espólio em PODER: crafte Formações e colete o Qi idle da sua caverna.",
        "cavern_slot_title": "Slot de Formação",
        "cavern_at_cap": "no teto",
        "formation_pick_target": "Onde ativar esta Formação?",
        "formation_target_body": "No corpo (buff temporizado)",
        "formation_target_body_hint": "Combate, cultivo e exploração leem este buff enquanto durar.",
        "formation_target_cavern": "Na caverna (turbina o idle)",
        "formation_target_cavern_hint": "Vibra na caverna: turbina o rendimento idle ou a compreensão do Dao.",
        "formation_realm_chip": "Reino {realm}",
        "explore_protection_chip": "Véu {pct}%",
    },
    "en": {
        "pill_eff_explore_protection": "Protection Veil (exploration)",
        "tab_cavern": "Cavern",
        "home_card_cavern": "Cavern 洞府",
        "cavern_explore_hint": "Turn the spoils into POWER: craft Formations and claim your cavern's idle Qi.",
        "cavern_slot_title": "Formation Slot",
        "cavern_at_cap": "at cap",
        "formation_pick_target": "Where to activate this Formation?",
        "formation_target_body": "On the body (timed buff)",
        "formation_target_body_hint": "Combat, cultivation and exploration read this buff while it lasts.",
        "formation_target_cavern": "In the cavern (boosts idle)",
        "formation_target_cavern_hint": "Hums in the cavern: boosts the idle yield or Dao comprehension.",
        "formation_realm_chip": "Realm {realm}",
        "explore_protection_chip": "Veil {pct}%",
    },
    "es": {
        "pill_eff_explore_protection": "Velo de Protección (exploración)",
        "tab_cavern": "Caverna",
        "home_card_cavern": "Caverna 洞府",
        "cavern_explore_hint": "Convierte el botín en PODER: craftea Formaciones y recoge el Qi idle de tu caverna.",
        "cavern_slot_title": "Slot de Formación",
        "cavern_at_cap": "en el tope",
        "formation_pick_target": "¿Dónde activar esta Formación?",
        "formation_target_body": "En el cuerpo (buff temporal)",
        "formation_target_body_hint": "Combate, cultivo y exploración leen este buff mientras dure.",
        "formation_target_cavern": "En la caverna (potencia el idle)",
        "formation_target_cavern_hint": "Vibra en la caverna: potencia el rendimiento idle o la comprensión del Dao.",
        "formation_realm_chip": "Reino {realm}",
        "explore_protection_chip": "Velo {pct}%",
    },
}

LANGS = ("pt", "en", "es")
CHAT = {lc: {**_SHARED[lc], **_CHAT[lc]} for lc in LANGS}
MINIAPP = {lc: {**_SHARED[lc], **_MINI[lc]} for lc in LANGS}


def _apply(path, additions):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    before = len(data)
    added = 0
    for k, v in additions.items():
        if k not in data:
            data[k] = v
            added += 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4, sort_keys=True)
        fh.write("\n")
    return before, added


def main():
    for lang, adds in CHAT.items():
        p = os.path.join(ROOT, "locales", f"{lang}.json")
        before, added = _apply(p, adds)
        print(f"chat    {lang}: {before} -> {before + added} (+{added})")
    for lang, adds in MINIAPP.items():
        p = os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json")
        before, added = _apply(p, adds)
        print(f"miniapp {lang}: {before} -> {before + added} (+{added})")


if __name__ == "__main__":
    main()
