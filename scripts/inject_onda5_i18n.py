"""scripts/inject_onda5_i18n.py — Onda 5 (Fase 1) Reinos Exploráveis i18n.

Idempotent injector (clone of inject_onda4b_i18n.py). Adds ONLY missing keys to
both surfaces, keeping pt/en/es in parity:
  * _SHARED   — keys used by BOTH chat (locales/) and mini-app (miniapp/i18n/)
  * _IDENTITY — chat-only (server-resolved via core.i18n, e.g. KarmaModal label)
  * _CHAT     — extra chat-only keys
  * _MINI     — extra mini-app-only keys (tab/home-card/UI chrome)

Rules: pt = PT-BR (você/seu, ativo); every {token} placeholder appears at most
ONCE per string (t() replaces only the first); placeholders stay ASCII.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── _SHARED — both surfaces ────────────────────────────────────────────────────
_SHARED = {
    "pt": {
        # chrome
        "explore_title": "Reinos Exploráveis",
        "explore_intro": "Explore o continente onde está pelo Sentido Divino (神識): siga as pistas, recolha materiais e decida — retorno seguro ou ir mais fundo.",
        "explore_depth": "Profundidade: {depth}",
        "explore_retreat": "Retorno Seguro",
        "explore_back": "Voltar",
        "explore_wipe_teaser": "Muito mais desperta no novo mundo (lançamento).",
        # risk
        "explore_risk_safe": "Seguro",
        "explore_risk_danger": "Perigo",
        "explore_risk_choice": "Encruzilhada",
        "explore_risk_ominous": "Presença Sombria",
        # clues
        "explore_clue_cache_1": "Um perfume de ervas paira nesta direção — colheita tranquila.",
        "explore_clue_cache_2": "Veios de minério reluzem entre as pedras.",
        "explore_clue_cache_3": "Energia espiritual repousa serena por aqui.",
        "explore_clue_trash_1": "Passos furtivos — alguém guarda este caminho.",
        "explore_clue_trash_2": "O ar treme com intenção hostil.",
        "explore_clue_trash_3": "Uma presença fraca, mas armada, à espreita.",
        "explore_clue_fork_1": "Uma alma encurralada — ajuda ou armadilha?",
        "explore_clue_fork_2": "Uma escolha se abre diante de você.",
        "explore_clue_fork_3": "O destino de outro cultivador está em suas mãos.",
        "explore_clue_hidden_1": "Uma pressão esmagadora — algo poderoso se esconde aqui.",
        "explore_clue_hidden_2": "O Sentido Divino estremece: um predador à espreita.",
        "explore_clue_hidden_3": "Sangue antigo e Qi denso. Cuidado.",
        # outcomes
        "explore_advanced": "Você avança mais fundo no reino.",
        "explore_cache": "Você recolhe materiais em segurança.",
        "explore_won": "Você derrota o inimigo e segue em frente!",
        "explore_died": "Você cai em combate e perde 90% do saco!",
        "explore_retreated": "Você retorna em segurança. Saco guardado no inventário.",
        "explore_no_qi": "Qi insuficiente (precisa de {cost}).",
        "explore_cooldown": "Aguarde um instante antes de explorar de novo.",
        "explore_hp_depleted": "HP esgotado — recupere antes de lutar.",
        "explore_meditation": "Você está em meditação profunda demais para explorar.",
        "explore_stale": "O reino mudou de forma — sentindo de novo.",
        "explore_failed": "Algo se desfez na exploração.",
        "explore_finish_duel": "⚔️ Termine o duelo do Monstro Escondido no mini-app antes de continuar.",
        # forks
        "explore_fork_wounded_elder_prompt": "Um ancião ferido jaz no caminho, o anel espacial à mostra. Socorrê-lo... ou saquear?",
        "explore_fork_wounded_elder_aid": "Curar o ancião",
        "explore_fork_wounded_elder_aid_result": "Você o socorre. Grato, o ancião lhe oferece um presente.",
        "explore_fork_wounded_elder_rob": "Saquear o ferido",
        "explore_fork_wounded_elder_rob_result": "Você toma o que é dele. O peso recai sobre sua alma.",
        "explore_fork_wounded_elder_pass": "Seguir em frente",
        "explore_fork_wounded_elder_pass_result": "Você passa sem se envolver.",
        "explore_fork_sealed_cache_prompt": "Um cache selado pulsa de energia, marcado por outro cultivador — ele virá buscá-lo.",
        "explore_fork_sealed_cache_share": "Deixar a parte dele",
        "explore_fork_sealed_cache_share_result": "Você reparte o tesouro com honra.",
        "explore_fork_sealed_cache_hoard": "Levar tudo",
        "explore_fork_sealed_cache_hoard_result": "Você esvazia o cache. Tudo seu — por enquanto.",
        "explore_fork_lost_disciple_prompt": "Um discípulo perdido tropeça em sua direção, exausto e assustado.",
        "explore_fork_lost_disciple_guide": "Guiá-lo à saída",
        "explore_fork_lost_disciple_guide_result": "Você o conduz à segurança. Ele lhe deixa um agradecimento.",
        "explore_fork_lost_disciple_abandon": "Ignorá-lo",
        "explore_fork_lost_disciple_abandon_result": "Você o deixa para trás.",
        "explore_fork_lost_disciple_prey": "Fazê-lo de presa",
        "explore_fork_lost_disciple_prey_result": "Você se aproveita do indefeso. O Abismo sussurra aprovação.",
        # new-world disclosure teasers
        "explore_teaser_caverns_title": "Cavernas Pessoais 洞府",
        "explore_teaser_caverns_body": "Estabeleça uma caverna no reino para cultivar energia em idle — rendimento passivo enquanto você está fora.",
        "explore_teaser_matrices_title": "Matrizes & Formações 阵法",
        "explore_teaser_matrices_body": "Consumíveis temporizados (ataque, defesa, eficiência de Qi, compreensão do Dao) criados pela alquimia e pela forja.",
        "explore_teaser_pvp_title": "PvP em Reinos Partilhados",
        "explore_teaser_pvp_body": "Alguns reinos serão partilhados — cruze (e enfrente) outros cultivadores, por opção.",
        "explore_teaser_dungeons_title": "Masmorras viram Nós",
        "explore_teaser_dungeons_body": "As 23 masmorras tornam-se nós deste mundo explorável — uma aventura, não uma lista.",
        "explore_teaser_techniques_title": "Técnicas pelas Seitas",
        "explore_teaser_techniques_body": "As técnicas virão das Seitas e do seu Caminho — não mais do spam de pergaminhos.",
    },
    "en": {
        "explore_title": "Explorable Realms",
        "explore_intro": "Explore the continent you are in by Divine Sense (神識): follow the clues, gather materials, and decide — safe return or go deeper.",
        "explore_depth": "Depth: {depth}",
        "explore_retreat": "Safe Return",
        "explore_back": "Back",
        "explore_wipe_teaser": "Much more awakens in the new world (launch).",
        "explore_risk_safe": "Safe",
        "explore_risk_danger": "Danger",
        "explore_risk_choice": "Crossroads",
        "explore_risk_ominous": "Dark Presence",
        "explore_clue_cache_1": "A scent of herbs drifts this way — a quiet harvest.",
        "explore_clue_cache_2": "Ore veins glint among the stones.",
        "explore_clue_cache_3": "Spirit energy rests calm here.",
        "explore_clue_trash_1": "Stealthy steps — someone guards this path.",
        "explore_clue_trash_2": "The air trembles with hostile intent.",
        "explore_clue_trash_3": "A weak, but armed, presence lurks.",
        "explore_clue_fork_1": "A cornered soul — aid, or a trap?",
        "explore_clue_fork_2": "A choice opens before you.",
        "explore_clue_fork_3": "Another cultivator's fate is in your hands.",
        "explore_clue_hidden_1": "A crushing pressure — something powerful hides here.",
        "explore_clue_hidden_2": "The Divine Sense shudders: a predator waits.",
        "explore_clue_hidden_3": "Ancient blood and dense Qi. Beware.",
        "explore_advanced": "You press deeper into the realm.",
        "explore_cache": "You gather materials safely.",
        "explore_won": "You defeat the foe and move on!",
        "explore_died": "You fall in battle and lose 90% of your bag!",
        "explore_retreated": "You return safely. The bag is stored in your inventory.",
        "explore_no_qi": "Not enough Qi (needs {cost}).",
        "explore_cooldown": "Wait a moment before exploring again.",
        "explore_hp_depleted": "HP depleted — recover before fighting.",
        "explore_meditation": "You are in too deep a meditation to explore.",
        "explore_stale": "The realm shifted — sensing again.",
        "explore_failed": "Something unraveled in the exploration.",
        "explore_finish_duel": "⚔️ Finish the Hidden Monster duel in the mini-app before continuing.",
        "explore_fork_wounded_elder_prompt": "A wounded elder lies on the path, his spatial ring exposed. Save him... or loot him?",
        "explore_fork_wounded_elder_aid": "Heal the elder",
        "explore_fork_wounded_elder_aid_result": "You save him. Grateful, the elder offers you a gift.",
        "explore_fork_wounded_elder_rob": "Loot the wounded",
        "explore_fork_wounded_elder_rob_result": "You take what is his. The weight settles on your soul.",
        "explore_fork_wounded_elder_pass": "Walk on",
        "explore_fork_wounded_elder_pass_result": "You pass without getting involved.",
        "explore_fork_sealed_cache_prompt": "A sealed cache pulses with energy, marked by another cultivator — he will come for it.",
        "explore_fork_sealed_cache_share": "Leave his share",
        "explore_fork_sealed_cache_share_result": "You split the treasure with honor.",
        "explore_fork_sealed_cache_hoard": "Take it all",
        "explore_fork_sealed_cache_hoard_result": "You empty the cache. All yours — for now.",
        "explore_fork_lost_disciple_prompt": "A lost disciple stumbles your way, exhausted and afraid.",
        "explore_fork_lost_disciple_guide": "Guide him out",
        "explore_fork_lost_disciple_guide_result": "You lead him to safety. He leaves you a token of thanks.",
        "explore_fork_lost_disciple_abandon": "Ignore him",
        "explore_fork_lost_disciple_abandon_result": "You leave him behind.",
        "explore_fork_lost_disciple_prey": "Make him prey",
        "explore_fork_lost_disciple_prey_result": "You prey on the helpless. The Abyss whispers approval.",
        "explore_teaser_caverns_title": "Personal Caverns 洞府",
        "explore_teaser_caverns_body": "Establish a cavern in the realm to cultivate energy idle — passive yield while you are away.",
        "explore_teaser_matrices_title": "Matrices & Formations 阵法",
        "explore_teaser_matrices_body": "Timed consumables (attack, defense, Qi efficiency, Dao comprehension) crafted via alchemy and forging.",
        "explore_teaser_pvp_title": "PvP in Shared Realms",
        "explore_teaser_pvp_body": "Some realms will be shared — cross (and face) other cultivators, by choice.",
        "explore_teaser_dungeons_title": "Dungeons Become Nodes",
        "explore_teaser_dungeons_body": "The 23 dungeons become nodes of this explorable world — an adventure, not a list.",
        "explore_teaser_techniques_title": "Techniques from the Sects",
        "explore_teaser_techniques_body": "Techniques will come from the Sects and your Path — no more scroll spam.",
    },
    "es": {
        "explore_title": "Reinos Explorables",
        "explore_intro": "Explora el continente en el que estás por el Sentido Divino (神識): sigue las pistas, reúne materiales y decide — retorno seguro o ir más profundo.",
        "explore_depth": "Profundidad: {depth}",
        "explore_retreat": "Retorno Seguro",
        "explore_back": "Volver",
        "explore_wipe_teaser": "Mucho más despierta en el nuevo mundo (lanzamiento).",
        "explore_risk_safe": "Seguro",
        "explore_risk_danger": "Peligro",
        "explore_risk_choice": "Encrucijada",
        "explore_risk_ominous": "Presencia Oscura",
        "explore_clue_cache_1": "Un aroma de hierbas flota por aquí — cosecha tranquila.",
        "explore_clue_cache_2": "Vetas de mineral brillan entre las piedras.",
        "explore_clue_cache_3": "La energía espiritual reposa serena aquí.",
        "explore_clue_trash_1": "Pasos sigilosos — alguien guarda este camino.",
        "explore_clue_trash_2": "El aire tiembla con intención hostil.",
        "explore_clue_trash_3": "Una presencia débil, pero armada, acecha.",
        "explore_clue_fork_1": "Un alma acorralada — ¿ayuda o trampa?",
        "explore_clue_fork_2": "Una elección se abre ante ti.",
        "explore_clue_fork_3": "El destino de otro cultivador está en tus manos.",
        "explore_clue_hidden_1": "Una presión aplastante — algo poderoso se esconde aquí.",
        "explore_clue_hidden_2": "El Sentido Divino se estremece: un depredador espera.",
        "explore_clue_hidden_3": "Sangre antigua y Qi denso. Cuidado.",
        "explore_advanced": "Avanzas más profundo en el reino.",
        "explore_cache": "Reúnes materiales con seguridad.",
        "explore_won": "¡Derrotas al enemigo y sigues adelante!",
        "explore_died": "¡Caes en combate y pierdes el 90% del saco!",
        "explore_retreated": "Regresas a salvo. El saco se guardó en el inventario.",
        "explore_no_qi": "Qi insuficiente (necesita {cost}).",
        "explore_cooldown": "Espera un momento antes de explorar de nuevo.",
        "explore_hp_depleted": "HP agotado — recupérate antes de luchar.",
        "explore_meditation": "Estás en una meditación demasiado profunda para explorar.",
        "explore_stale": "El reino cambió de forma — sintiendo de nuevo.",
        "explore_failed": "Algo se deshizo en la exploración.",
        "explore_finish_duel": "⚔️ Termina el duelo del Monstruo Oculto en el mini-app antes de continuar.",
        "explore_fork_wounded_elder_prompt": "Un anciano herido yace en el camino, su anillo espacial a la vista. ¿Salvarlo... o saquearlo?",
        "explore_fork_wounded_elder_aid": "Curar al anciano",
        "explore_fork_wounded_elder_aid_result": "Lo socorres. Agradecido, el anciano te ofrece un regalo.",
        "explore_fork_wounded_elder_rob": "Saquear al herido",
        "explore_fork_wounded_elder_rob_result": "Tomas lo que es suyo. El peso recae sobre tu alma.",
        "explore_fork_wounded_elder_pass": "Seguir adelante",
        "explore_fork_wounded_elder_pass_result": "Pasas sin involucrarte.",
        "explore_fork_sealed_cache_prompt": "Un alijo sellado pulsa de energía, marcado por otro cultivador — vendrá a buscarlo.",
        "explore_fork_sealed_cache_share": "Dejar su parte",
        "explore_fork_sealed_cache_share_result": "Repartes el tesoro con honor.",
        "explore_fork_sealed_cache_hoard": "Llevarlo todo",
        "explore_fork_sealed_cache_hoard_result": "Vacías el alijo. Todo tuyo — por ahora.",
        "explore_fork_lost_disciple_prompt": "Un discípulo perdido se acerca tambaleando, exhausto y asustado.",
        "explore_fork_lost_disciple_guide": "Guiarlo a la salida",
        "explore_fork_lost_disciple_guide_result": "Lo llevas a un lugar seguro. Te deja una muestra de gratitud.",
        "explore_fork_lost_disciple_abandon": "Ignorarlo",
        "explore_fork_lost_disciple_abandon_result": "Lo dejas atrás.",
        "explore_fork_lost_disciple_prey": "Hacerlo presa",
        "explore_fork_lost_disciple_prey_result": "Te aprovechas del indefenso. El Abismo susurra aprobación.",
        "explore_teaser_caverns_title": "Cavernas Personales 洞府",
        "explore_teaser_caverns_body": "Establece una caverna en el reino para cultivar energía en idle — rendimiento pasivo mientras no estás.",
        "explore_teaser_matrices_title": "Matrices y Formaciones 阵法",
        "explore_teaser_matrices_body": "Consumibles temporizados (ataque, defensa, eficiencia de Qi, comprensión del Dao) creados por la alquimia y la forja.",
        "explore_teaser_pvp_title": "PvP en Reinos Compartidos",
        "explore_teaser_pvp_body": "Algunos reinos serán compartidos — cruza (y enfrenta) a otros cultivadores, por elección.",
        "explore_teaser_dungeons_title": "Mazmorras se vuelven Nodos",
        "explore_teaser_dungeons_body": "Las 23 mazmorras se vuelven nodos de este mundo explorable — una aventura, no una lista.",
        "explore_teaser_techniques_title": "Técnicas de las Sectas",
        "explore_teaser_techniques_body": "Las técnicas vendrán de las Sectas y de tu Camino — no más spam de pergaminos.",
    },
}

# ── _IDENTITY — chat-only, server-resolved (KarmaModal disclosure label) ───────
_IDENTITY = {
    "pt": {"karma_event_exploration_fork": "Escolha na Exploração"},
    "en": {"karma_event_exploration_fork": "Exploration Choice"},
    "es": {"karma_event_exploration_fork": "Elección en la Exploración"},
}

# ── _CHAT — extra chat-only keys ───────────────────────────────────────────────
_CHAT = {
    "pt": {"explore_qi": "🌀 Qi: {qi}"},
    "en": {"explore_qi": "🌀 Qi: {qi}"},
    "es": {"explore_qi": "🌀 Qi: {qi}"},
}

# ── _MINI — extra mini-app-only keys (tab/home-card/UI chrome) ─────────────────
_MINI = {
    "pt": {
        "tab_explore": "Explorar",
        "home_card_explore": "Reinos Exploráveis",
        "explore_qi_short": "Qi",
        "explore_pick": "Escolha uma direção:",
        "explore_retreat_hint": "Guarda 100% do saco no inventário.",
        "explore_empty": "O Sentido Divino não alcança nada por aqui.",
        "explore_hidden_title": "Monstro Escondido",
        "explore_hidden_won": "Você triunfa sobre o Monstro Escondido!",
        "explore_hidden_lost": "O Monstro Escondido foi forte demais.",
        "explore_hidden_loot_note": "O espólio já está no seu saco de expedição.",
        "explore_newworld_title": "O Novo Mundo Desperta",
        "explore_newworld_intro": "Esta é apenas a Fase 1 — o loop de exploração. No lançamento, muito mais floresce:",
    },
    "en": {
        "tab_explore": "Explore",
        "home_card_explore": "Explorable Realms",
        "explore_qi_short": "Qi",
        "explore_pick": "Choose a direction:",
        "explore_retreat_hint": "Banks 100% of the bag into your inventory.",
        "explore_empty": "The Divine Sense reaches nothing here.",
        "explore_hidden_title": "Hidden Monster",
        "explore_hidden_won": "You triumph over the Hidden Monster!",
        "explore_hidden_lost": "The Hidden Monster was too strong.",
        "explore_hidden_loot_note": "The spoils are already in your expedition bag.",
        "explore_newworld_title": "The New World Awakens",
        "explore_newworld_intro": "This is only Phase 1 — the exploration loop. At launch, much more blooms:",
    },
    "es": {
        "tab_explore": "Explorar",
        "home_card_explore": "Reinos Explorables",
        "explore_qi_short": "Qi",
        "explore_pick": "Elige una dirección:",
        "explore_retreat_hint": "Guarda el 100% del saco en tu inventario.",
        "explore_empty": "El Sentido Divino no alcanza nada aquí.",
        "explore_hidden_title": "Monstruo Oculto",
        "explore_hidden_won": "¡Triunfas sobre el Monstruo Oculto!",
        "explore_hidden_lost": "El Monstruo Oculto fue demasiado fuerte.",
        "explore_hidden_loot_note": "El botín ya está en tu saco de expedición.",
        "explore_newworld_title": "El Nuevo Mundo Despierta",
        "explore_newworld_intro": "Esta es solo la Fase 1 — el bucle de exploración. En el lanzamiento, mucho más florece:",
    },
}

LANGS = ("pt", "en", "es")
CHAT = {lc: {**_SHARED[lc], **_IDENTITY[lc], **_CHAT[lc]} for lc in LANGS}
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
