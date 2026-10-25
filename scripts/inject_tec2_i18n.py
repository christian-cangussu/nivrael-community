"""TEC-2 - Drop Reset + Economia do Pergaminho: injetor i18n (SO-ADICOES).

Roda: python -X utf8 scripts/inject_tec2_i18n.py

Padrao inject_tec1_i18n: adiciona apenas keys AUSENTES (nunca sobrescreve),
json.dump(ensure_ascii=False, indent=4, sort_keys=True) + newline="\\n" +
newline final (sem o newline="\\n" o Windows converte tudo para CRLF e o diff
vira o ficheiro inteiro).

CHAT (locales/*) = chrome do /pergaminhos (arca, os dois destinos, resultados
com antes->depois) + a linha de escassez da masmorra + a ponte do /biblioteca
+ os 5 nomes dos caminhos de Intencao (intent_name_*, que ate hoje so
existiam no mini). MINI (miniapp/i18n/*) = as 2 keys do painel admin
(feature_escassez_scrolls[_desc]) + o chrome do ScrollEconomyCard.

PT-BR estrito (voce/seu, nunca tu/teu); placeholders {tok} un-accented e com
o MESMO conjunto de tokens nas 3 linguas.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

CHAT = {
 "pt": {
  "scr_title": "Destino dos Pergaminhos",
  "scr_intro": "Um pergaminho não é lixo de mochila. Ou você aprende a arte, ou a entrega à sua casa, ou a queima para compreender a intenção que ela carrega.",
  "scr_empty": "Você não guarda nenhum pergaminho. Nesta era eles são raros — a Biblioteca da sua seita é o caminho mais seguro para novas artes.",
  "scr_locked_msg": "A escassez de pergaminhos não rege este mundo.",
  "scr_stale": "Este pergaminho já não está em suas mãos.",
  "scr_tier_1": "arte comum",
  "scr_tier_2": "arte rara",
  "scr_tier_3": "arte lendária",
  "scr_tier_4": "arte do ápice",
  "scr_balance_line": "🏯 Contribuição: *{balance}* · ainda cabem *{headroom}* de doação hoje",
  "scr_no_sect_hint": "_Sem uma Seita de Cultivo, não há Biblioteca para receber suas doações — mas o Ritual de Compreensão continua ao seu alcance._",
  "scr_donate_head": "📚 *Doar à Biblioteca* — a casa registra o pergaminho e credita *{cp}* de contribuição.",
  "scr_donate_after": "   Contribuição: {before} → *{after}*",
  "scr_donate_block_sect": "Só uma Seita de Cultivo pode receber o pergaminho. Entre numa casa primeiro.",
  "scr_donate_block_cap": "A casa já recebeu o bastante de você hoje (teto de {cap} de contribuição por dia). Volte amanhã.",
  "scr_btn_donate_one": "📚 Doar 1 (+{cp} 🏯)",
  "scr_btn_donate_all": "📚 Doar {n} (+{cp} 🏯)",
  "scr_burn_head": "🔥 *Ritual de Compreensão* — o pergaminho queima e a intenção fica: *+{xp}* XP no caminho da {intent}.",
  "scr_burn_dao": "   💠 E ainda +{n} fragmento de Dao — só as artes do ápice guardam tanto.",
  "scr_btn_burn_one": "🔥 Queimar 1 (+{xp} XP)",
  "scr_btn_burn_all": "🔥 Queimar {n} (+{xp} XP)",
  "scr_other_paths_hint": "_Aprender e absorver continuam onde sempre estiveram, no menu de técnicas._",
  "scr_donated_toast": "A casa agradece. +{cp} de contribuição.",
  "scr_donated_header": "📚 Você entrega {emoji} *{name}* ×{n} à Biblioteca da casa.",
  "scr_donated_delta": "🏯 Contribuição: {before} → *{after}* (+{cp})",
  "scr_donated_rank_note": "_A casa credita mérito, não posto: seu grau continua sendo ganho por feitos._",
  "scr_partial_cap": "_A casa aceitou {n} dos {asked} pergaminhos — o teto do dia falou mais alto._",
  "scr_headroom_left": "_Ainda cabem {headroom} de doação hoje._",
  "scr_burned_toast": "A chama levou o papel. +{xp} XP de intenção.",
  "scr_burned_header": "🔥 {emoji} *{name}* ×{n} vira cinza — e a intenção fica.",
  "scr_burned_delta": "🌀 Caminho da {intent}: +{xp} XP · nível {before} → *{after}*",
  "scr_burned_rankup": "✨ Sua intenção da {intent} alcança o nível *{rank}*.",
  "scr_burned_dao_line": "💠 {emoji} {law}: {frag}/{total} fragmentos",
  "scr_entry_btn": "Destino dos Pergaminhos ({n})",
  "scr_library_hint": "_Pergaminhos que você não vai usar podem virar contribuição aqui mesmo._",
  "scr_library_btn": "📜 Doar pergaminhos",
  "scr_dng_scarcity_hint": "As artes rarearam nesta era — a Biblioteca da sua seita é o caminho.",
  "scr_dng_scarcity_bare": "As artes rarearam nesta era — cada pergaminho encontrado vale o que antes valiam dez.",
  "scr_partial_stock": "_Você só tinha {n} dos {asked} pergaminhos — a casa recebeu o que havia._",
  "intent_name_sword": "Espada",
  "intent_name_fist": "Punho",
  "intent_name_body": "Corpo",
  "intent_name_dao": "Dao",
  "intent_name_killing": "Matança"
 },
 "en": {
  "scr_title": "The Scroll's Fate",
  "scr_intro": "A scroll is not bag clutter. Either you learn the art, or you hand it to your house, or you burn it to grasp the intent it carries.",
  "scr_empty": "You hold no scrolls. In this era they are rare — your sect's Library is the surer road to new arts.",
  "scr_locked_msg": "Scroll scarcity does not rule this world.",
  "scr_stale": "That scroll is no longer in your hands.",
  "scr_tier_1": "common art",
  "scr_tier_2": "rare art",
  "scr_tier_3": "legendary art",
  "scr_tier_4": "apex art",
  "scr_balance_line": "🏯 Contribution: *{balance}* · *{headroom}* of donation still fits today",
  "scr_no_sect_hint": "_Without a Cultivation Sect there is no Library to receive your donations — but the Rite of Comprehension remains within reach._",
  "scr_donate_head": "📚 *Donate to the Library* — the house records the scroll and credits *{cp}* contribution.",
  "scr_donate_after": "   Contribution: {before} → *{after}*",
  "scr_donate_block_sect": "Only a Cultivation Sect can receive the scroll. Join a house first.",
  "scr_donate_block_cap": "The house has taken enough from you today (cap of {cap} contribution per day). Return tomorrow.",
  "scr_btn_donate_one": "📚 Donate 1 (+{cp} 🏯)",
  "scr_btn_donate_all": "📚 Donate {n} (+{cp} 🏯)",
  "scr_burn_head": "🔥 *Rite of Comprehension* — the scroll burns and the intent stays: *+{xp}* XP on the path of the {intent}.",
  "scr_burn_dao": "   💠 And +{n} Dao fragment besides — only apex arts hold that much.",
  "scr_btn_burn_one": "🔥 Burn 1 (+{xp} XP)",
  "scr_btn_burn_all": "🔥 Burn {n} (+{xp} XP)",
  "scr_other_paths_hint": "_Learning and absorbing remain where they always were, in the techniques menu._",
  "scr_donated_toast": "The house thanks you. +{cp} contribution.",
  "scr_donated_header": "📚 You hand {emoji} *{name}* ×{n} to the house Library.",
  "scr_donated_delta": "🏯 Contribution: {before} → *{after}* (+{cp})",
  "scr_donated_rank_note": "_The house credits merit, not rank: your standing is still earned by deeds._",
  "scr_partial_cap": "_The house accepted {n} of the {asked} scrolls — the daily cap spoke louder._",
  "scr_headroom_left": "_{headroom} of donation still fits today._",
  "scr_burned_toast": "The flame took the paper. +{xp} intent XP.",
  "scr_burned_header": "🔥 {emoji} *{name}* ×{n} turns to ash — and the intent remains.",
  "scr_burned_delta": "🌀 Path of the {intent}: +{xp} XP · rank {before} → *{after}*",
  "scr_burned_rankup": "✨ Your {intent} intent reaches rank *{rank}*.",
  "scr_burned_dao_line": "💠 {emoji} {law}: {frag}/{total} fragments",
  "scr_entry_btn": "The Scroll's Fate ({n})",
  "scr_library_hint": "_Scrolls you will never use can become contribution right here._",
  "scr_library_btn": "📜 Donate scrolls",
  "scr_dng_scarcity_hint": "Arts grew scarce in this era — your sect's Library is the road.",
  "scr_dng_scarcity_bare": "Arts grew scarce in this era — each scroll found is worth what ten used to be.",
  "scr_partial_stock": "_You only had {n} of the {asked} scrolls — the house took what there was._",
  "intent_name_sword": "Sword",
  "intent_name_fist": "Fist",
  "intent_name_body": "Body",
  "intent_name_dao": "Dao",
  "intent_name_killing": "Killing"
 },
 "es": {
  "scr_title": "Destino de los Pergaminos",
  "scr_intro": "Un pergamino no es basura de mochila. O aprende el arte, o lo entrega a su casa, o lo quema para comprender la intención que lleva.",
  "scr_empty": "No guarda ningún pergamino. En esta era son raros — la Biblioteca de su secta es el camino más seguro hacia nuevas artes.",
  "scr_locked_msg": "La escasez de pergaminos no rige este mundo.",
  "scr_stale": "Ese pergamino ya no está en sus manos.",
  "scr_tier_1": "arte común",
  "scr_tier_2": "arte rara",
  "scr_tier_3": "arte legendaria",
  "scr_tier_4": "arte del ápice",
  "scr_balance_line": "🏯 Contribución: *{balance}* · aún caben *{headroom}* de donación hoy",
  "scr_no_sect_hint": "_Sin una Secta de Cultivo no hay Biblioteca que reciba sus donaciones — pero el Rito de Comprensión sigue a su alcance._",
  "scr_donate_head": "📚 *Donar a la Biblioteca* — la casa registra el pergamino y acredita *{cp}* de contribución.",
  "scr_donate_after": "   Contribución: {before} → *{after}*",
  "scr_donate_block_sect": "Solo una Secta de Cultivo puede recibir el pergamino. Únase a una casa primero.",
  "scr_donate_block_cap": "La casa ya recibió bastante de usted hoy (tope de {cap} de contribución por día). Vuelva mañana.",
  "scr_btn_donate_one": "📚 Donar 1 (+{cp} 🏯)",
  "scr_btn_donate_all": "📚 Donar {n} (+{cp} 🏯)",
  "scr_burn_head": "🔥 *Rito de Comprensión* — el pergamino arde y la intención queda: *+{xp}* XP en el camino de la {intent}.",
  "scr_burn_dao": "   💠 Y además +{n} fragmento de Dao — solo las artes del ápice guardan tanto.",
  "scr_btn_burn_one": "🔥 Quemar 1 (+{xp} XP)",
  "scr_btn_burn_all": "🔥 Quemar {n} (+{xp} XP)",
  "scr_other_paths_hint": "_Aprender y absorber siguen donde siempre estuvieron, en el menú de técnicas._",
  "scr_donated_toast": "La casa agradece. +{cp} de contribución.",
  "scr_donated_header": "📚 Entrega {emoji} *{name}* ×{n} a la Biblioteca de la casa.",
  "scr_donated_delta": "🏯 Contribución: {before} → *{after}* (+{cp})",
  "scr_donated_rank_note": "_La casa acredita mérito, no rango: su grado se sigue ganando con hechos._",
  "scr_partial_cap": "_La casa aceptó {n} de los {asked} pergaminos — el tope del día habló más alto._",
  "scr_headroom_left": "_Aún caben {headroom} de donación hoy._",
  "scr_burned_toast": "La llama se llevó el papel. +{xp} XP de intención.",
  "scr_burned_header": "🔥 {emoji} *{name}* ×{n} se vuelve ceniza — y la intención permanece.",
  "scr_burned_delta": "🌀 Camino de la {intent}: +{xp} XP · nivel {before} → *{after}*",
  "scr_burned_rankup": "✨ Su intención de {intent} alcanza el nivel *{rank}*.",
  "scr_burned_dao_line": "💠 {emoji} {law}: {frag}/{total} fragmentos",
  "scr_entry_btn": "Destino de los Pergaminos ({n})",
  "scr_library_hint": "_Los pergaminos que no va a usar pueden volverse contribución aquí mismo._",
  "scr_library_btn": "📜 Donar pergaminos",
  "scr_dng_scarcity_hint": "Las artes escasearon en esta era — la Biblioteca de su secta es el camino.",
  "scr_dng_scarcity_bare": "Las artes escasearon en esta era — cada pergamino hallado vale lo que antes valían diez.",
  "scr_partial_stock": "_Solo tenías {n} de los {asked} pergaminos — la casa recibió lo que había._",
  "intent_name_sword": "Espada",
  "intent_name_fist": "Puño",
  "intent_name_body": "Cuerpo",
  "intent_name_dao": "Dao",
  "intent_name_killing": "Matanza"
 }
}

MINIAPP = {
 "pt": {
  "feature_escassez_scrolls": "Escassez de Pergaminhos (TEC-2)",
  "feature_escassez_scrolls_desc": "⚠️ LAUNCH-SERVER-BOUND: não ligar em mundo com economia viva sem compensação — os pergaminhos já acumulados virariam contribuição em massa. Corta o faucet aleatório de pergaminhos (masmorra, varredura, chefe e caçada de NPC) pelo multiplicador SCR_DROP_MULT e estica o marco da arena de 10 para SCR_ARENA_WIN_STEP vitórias. Em troca, o pergaminho ganha destino: doar à Biblioteca da seita (contribuição no saldo — nunca posto) e o Ritual de Compreensão (XP de Intenção no caminho da própria arte, + fragmento de Dao no ápice). O custo em pergaminhos do refino de grau é dividido por SCR_GRADE_SCROLL_DIV para o refino não virar conteúdo morto. Doar exige uma Seita de Cultivo (recomendado ligar junto com biblioteca_seitas). Knobs env: SCR_DROP_MULT (0.15) / SCR_ARENA_WIN_STEP (50) / SCR_GRADE_SCROLL_DIV (5) / SCR_DONATE_CP_T1..T4 (25/50/100/200) / SCR_DONATE_DAILY_CAP (500) / SCR_BURN_XP_T1..T4 (25/50/100/200) / SCR_BURN_DAO_FRAG_T4 (1).",
  "scr_title": "Destino dos Pergaminhos",
  "scr_intro": "Um pergaminho não é lixo de mochila. Ou você aprende a arte, ou a entrega à sua casa, ou a queima para compreender a intenção que ela carrega.",
  "scr_stale": "Este pergaminho já não está em suas mãos.",
  "scr_tier_1": "arte comum",
  "scr_tier_2": "arte rara",
  "scr_tier_3": "arte lendária",
  "scr_tier_4": "arte do ápice",
  "scr_balance_line": "Contribuição: {balance} · ainda cabem {headroom} de doação hoje",
  "scr_no_sect_hint": "Sem uma Seita de Cultivo não há Biblioteca para receber suas doações — mas o Ritual de Compreensão continua ao seu alcance.",
  "scr_donate_head": "📚 Doar à Biblioteca: a casa credita {cp} de contribuição por pergaminho.",
  "scr_donate_block_sect": "Só uma Seita de Cultivo pode receber o pergaminho. Entre numa casa primeiro.",
  "scr_donate_block_cap": "A casa já recebeu o bastante de você hoje (teto de {cap} por dia). Volte amanhã.",
  "scr_btn_donate_one": "Doar 1 (+{cp})",
  "scr_btn_donate_all": "Doar {n} (+{cp})",
  "scr_burn_head": "🔥 Ritual de Compreensão: +{xp} XP no caminho da {intent}.",
  "scr_burn_dao": "💠 +{n} fragmento de Dao.",
  "scr_btn_burn_one": "Queimar 1 (+{xp} XP)",
  "scr_btn_burn_all": "Queimar {n} (+{xp} XP)",
  "scr_donated_delta": "Contribuição: {before} → {after} (+{cp})",
  "scr_burned_delta": "Caminho da {intent}: +{xp} XP · nível {before} → {after}",
  "scr_burned_rankup": "Sua intenção da {intent} alcança o nível {rank}.",
  "scr_dng_scarcity_bare": "As artes rarearam nesta era — cada pergaminho encontrado vale o que antes valiam dez.",
  "scr_dng_scarcity_hint": "As artes rarearam nesta era — a Biblioteca da sua seita é o caminho."
 },
 "en": {
  "feature_escassez_scrolls": "Scroll Scarcity (TEC-2)",
  "feature_escassez_scrolls_desc": "⚠️ LAUNCH-SERVER-BOUND: do not enable on a world with a live economy without compensation — already-hoarded scrolls would turn into contribution en masse. Cuts the random scroll faucet (dungeon, sweep, boss and NPC hunt) by the SCR_DROP_MULT multiplier and stretches the arena milestone from 10 to SCR_ARENA_WIN_STEP wins. In exchange the scroll gains a fate: donate it to the sect Library (contribution on the balance — never rank) and the Rite of Comprehension (Intent XP on the art's own path, + a Dao fragment at the apex). The scroll cost of grade refinement is divided by SCR_GRADE_SCROLL_DIV so refinement never becomes dead content. Donating requires a Cultivation Sect (best enabled alongside biblioteca_seitas). Env knobs: SCR_DROP_MULT (0.15) / SCR_ARENA_WIN_STEP (50) / SCR_GRADE_SCROLL_DIV (5) / SCR_DONATE_CP_T1..T4 (25/50/100/200) / SCR_DONATE_DAILY_CAP (500) / SCR_BURN_XP_T1..T4 (25/50/100/200) / SCR_BURN_DAO_FRAG_T4 (1).",
  "scr_title": "The Scroll's Fate",
  "scr_intro": "A scroll is not bag clutter. Either you learn the art, or you hand it to your house, or you burn it to grasp the intent it carries.",
  "scr_stale": "That scroll is no longer in your hands.",
  "scr_tier_1": "common art",
  "scr_tier_2": "rare art",
  "scr_tier_3": "legendary art",
  "scr_tier_4": "apex art",
  "scr_balance_line": "Contribution: {balance} · {headroom} of donation still fits today",
  "scr_no_sect_hint": "Without a Cultivation Sect there is no Library to receive your donations — but the Rite of Comprehension remains within reach.",
  "scr_donate_head": "📚 Donate to the Library: the house credits {cp} contribution per scroll.",
  "scr_donate_block_sect": "Only a Cultivation Sect can receive the scroll. Join a house first.",
  "scr_donate_block_cap": "The house has taken enough from you today (cap of {cap} per day). Return tomorrow.",
  "scr_btn_donate_one": "Donate 1 (+{cp})",
  "scr_btn_donate_all": "Donate {n} (+{cp})",
  "scr_burn_head": "🔥 Rite of Comprehension: +{xp} XP on the path of the {intent}.",
  "scr_burn_dao": "💠 +{n} Dao fragment.",
  "scr_btn_burn_one": "Burn 1 (+{xp} XP)",
  "scr_btn_burn_all": "Burn {n} (+{xp} XP)",
  "scr_donated_delta": "Contribution: {before} → {after} (+{cp})",
  "scr_burned_delta": "Path of the {intent}: +{xp} XP · rank {before} → {after}",
  "scr_burned_rankup": "Your {intent} intent reaches rank {rank}.",
  "scr_dng_scarcity_bare": "Arts grew scarce in this era — each scroll found is worth what ten used to be.",
  "scr_dng_scarcity_hint": "Arts grew scarce in this era — your sect's Library is the road."
 },
 "es": {
  "feature_escassez_scrolls": "Escasez de Pergaminos (TEC-2)",
  "feature_escassez_scrolls_desc": "⚠️ LAUNCH-SERVER-BOUND: no encender en un mundo con economía viva sin compensación — los pergaminos ya acumulados se volverían contribución en masa. Corta el faucet aleatorio de pergaminos (mazmorra, barrido, jefe y cacería de NPC) por el multiplicador SCR_DROP_MULT y estira el hito de la arena de 10 a SCR_ARENA_WIN_STEP victorias. A cambio, el pergamino gana destino: donarlo a la Biblioteca de la secta (contribución en el saldo — nunca rango) y el Rito de Comprensión (XP de Intención en el camino del propio arte, + fragmento de Dao en el ápice). El costo en pergaminos del refinado de grado se divide por SCR_GRADE_SCROLL_DIV para que el refinado no se vuelva contenido muerto. Donar exige una Secta de Cultivo (conviene encenderla junto con biblioteca_seitas). Knobs env: SCR_DROP_MULT (0.15) / SCR_ARENA_WIN_STEP (50) / SCR_GRADE_SCROLL_DIV (5) / SCR_DONATE_CP_T1..T4 (25/50/100/200) / SCR_DONATE_DAILY_CAP (500) / SCR_BURN_XP_T1..T4 (25/50/100/200) / SCR_BURN_DAO_FRAG_T4 (1).",
  "scr_title": "Destino de los Pergaminos",
  "scr_intro": "Un pergamino no es basura de mochila. O aprende el arte, o lo entrega a su casa, o lo quema para comprender la intención que lleva.",
  "scr_stale": "Ese pergamino ya no está en sus manos.",
  "scr_tier_1": "arte común",
  "scr_tier_2": "arte rara",
  "scr_tier_3": "arte legendaria",
  "scr_tier_4": "arte del ápice",
  "scr_balance_line": "Contribución: {balance} · aún caben {headroom} de donación hoy",
  "scr_no_sect_hint": "Sin una Secta de Cultivo no hay Biblioteca que reciba sus donaciones — pero el Rito de Comprensión sigue a su alcance.",
  "scr_donate_head": "📚 Donar a la Biblioteca: la casa acredita {cp} de contribución por pergamino.",
  "scr_donate_block_sect": "Solo una Secta de Cultivo puede recibir el pergamino. Únase a una casa primero.",
  "scr_donate_block_cap": "La casa ya recibió bastante de usted hoy (tope de {cap} por día). Vuelva mañana.",
  "scr_btn_donate_one": "Donar 1 (+{cp})",
  "scr_btn_donate_all": "Donar {n} (+{cp})",
  "scr_burn_head": "🔥 Rito de Comprensión: +{xp} XP en el camino de la {intent}.",
  "scr_burn_dao": "💠 +{n} fragmento de Dao.",
  "scr_btn_burn_one": "Quemar 1 (+{xp} XP)",
  "scr_btn_burn_all": "Quemar {n} (+{xp} XP)",
  "scr_donated_delta": "Contribución: {before} → {after} (+{cp})",
  "scr_burned_delta": "Camino de la {intent}: +{xp} XP · nivel {before} → {after}",
  "scr_burned_rankup": "Su intención de {intent} alcanza el nivel {rank}.",
  "scr_dng_scarcity_bare": "Las artes escasearon en esta era — cada pergamino hallado vale lo que antes valían diez.",
  "scr_dng_scarcity_hint": "Las artes escasearon en esta era — la Biblioteca de su secta es el camino."
 }
}


# ── OVERRIDES (padrao inject_mv7_i18n): sobrescrita EXPLICITA e auditavel de
# keys que ESTE lote ja escreveu. Nunca tocam keys de outras sprints.
# Motivo (review adversarial TEC-2, 2 achados reais):
#   (1) CONCORDANCIA DE GENERO — "no caminho da {intent}" so funciona com
#       Espada/Matanca; com Punho/Corpo/Dao sai "da Punho". A estrutura passa a
#       "Intencao de {intent}", que concorda com os 5 caminhos nas 3 linguas.
#   (2) TRATAMENTO EM ES — o locale espanhol vivo usa "tu" (554 strings) contra
#       9 com "usted". O lote nascera em "usted" e destoava de todo o jogo.
# O "killing" em es alinha com o intent_name_killing que ja existia no mini
# ("Asesinato"), para o mesmo caminho nao ter dois nomes nas duas superficies.
CHAT_OVERRIDES = {
 "pt": {
  "scr_burn_head": "🔥 *Ritual de Compreensão* — o pergaminho queima e a intenção fica: *+{xp}* XP na Intenção de **{intent}**.",
  "scr_burned_delta": "🌀 Intenção de {intent}: +{xp} XP · nível {before} → *{after}*",
  "scr_burned_rankup": "✨ Sua Intenção de {intent} alcança o nível *{rank}*.",
 },
 "en": {
  "scr_burn_head": "🔥 *Rite of Comprehension* — the scroll burns and the intent stays: *+{xp}* XP in the Intent of **{intent}**.",
  "scr_burned_delta": "🌀 Intent of {intent}: +{xp} XP · rank {before} → *{after}*",
  "scr_burned_rankup": "✨ Your Intent of {intent} reaches rank *{rank}*.",
 },
 "es": {
  "scr_intro": "Un pergamino no es basura de mochila. O aprendes el arte, o lo entregas a tu casa, o lo quemas para comprender la intención que lleva.",
  "scr_empty": "No guardas ningún pergamino. En esta era son raros — la Biblioteca de tu secta es el camino más seguro hacia nuevas artes.",
  "scr_stale": "Ese pergamino ya no está en tus manos.",
  "scr_no_sect_hint": "_Sin una Secta de Cultivo no hay Biblioteca que reciba tus donaciones — pero el Rito de Comprensión sigue a tu alcance._",
  "scr_donate_block_sect": "Solo una Secta de Cultivo puede recibir el pergamino. Únete a una casa primero.",
  "scr_donate_block_cap": "La casa ya recibió bastante de ti hoy (tope de {cap} de contribución por día). Vuelve mañana.",
  "scr_burn_head": "🔥 *Rito de Comprensión* — el pergamino arde y la intención queda: *+{xp}* XP en la Intención de **{intent}**.",
  "scr_donated_header": "📚 Entregas {emoji} *{name}* ×{n} a la Biblioteca de la casa.",
  "scr_donated_rank_note": "_La casa acredita mérito, no rango: tu grado se sigue ganando con hechos._",
  "scr_burned_delta": "🌀 Intención de {intent}: +{xp} XP · nivel {before} → *{after}*",
  "scr_burned_rankup": "✨ Tu Intención de {intent} alcanza el nivel *{rank}*.",
  "scr_library_hint": "_Los pergaminos que no vas a usar pueden volverse contribución aquí mismo._",
  "scr_dng_scarcity_hint": "Las artes escasearon en esta era — la Biblioteca de tu secta es el camino.",
  "intent_name_killing": "Asesinato",
 },
}

MINI_OVERRIDES = {
 "pt": {
  "scr_burn_head": "🔥 Ritual de Compreensão: +{xp} XP na Intenção de {intent}.",
  "scr_burned_delta": "Intenção de {intent}: +{xp} XP · nível {before} → {after}",
  "scr_burned_rankup": "Sua Intenção de {intent} alcança o nível {rank}.",
 },
 "en": {
  "scr_burn_head": "🔥 Rite of Comprehension: +{xp} XP in the Intent of {intent}.",
  "scr_burned_delta": "Intent of {intent}: +{xp} XP · rank {before} → {after}",
  "scr_burned_rankup": "Your Intent of {intent} reaches rank {rank}.",
 },
 "es": {
  "scr_intro": "Un pergamino no es basura de mochila. O aprendes el arte, o lo entregas a tu casa, o lo quemas para comprender la intención que lleva.",
  "scr_stale": "Ese pergamino ya no está en tus manos.",
  "scr_no_sect_hint": "Sin una Secta de Cultivo no hay Biblioteca que reciba tus donaciones — pero el Rito de Comprensión sigue a tu alcance.",
  "scr_donate_block_sect": "Solo una Secta de Cultivo puede recibir el pergamino. Únete a una casa primero.",
  "scr_donate_block_cap": "La casa ya recibió bastante de ti hoy (tope de {cap} por día). Vuelve mañana.",
  "scr_burn_head": "🔥 Rito de Comprensión: +{xp} XP en la Intención de {intent}.",
  "scr_burned_delta": "Intención de {intent}: +{xp} XP · nivel {before} → {after}",
  "scr_burned_rankup": "Tu Intención de {intent} alcanza el nivel {rank}.",
  "scr_dng_scarcity_hint": "Las artes escasearon en esta era — la Biblioteca de tu secta es el camino.",
 },
}


def _apply(path: str, additions: dict, overrides: dict | None = None) -> tuple:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    before = len(data)
    for k, v in additions.items():
        if k not in data:
            data[k] = v
    for k, v in (overrides or {}).items():
        data[k] = v
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, sort_keys=True)
        f.write("\n")
    return before, len(data)


def main() -> None:
    for lang in LANGS:
        b, a = _apply(os.path.join(ROOT, "locales", lang + ".json"), CHAT[lang],
                      CHAT_OVERRIDES.get(lang))
        print("chat " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")
    for lang in LANGS:
        b, a = _apply(os.path.join(ROOT, "miniapp", "i18n", lang + ".json"), MINIAPP[lang],
                      MINI_OVERRIDES.get(lang))
        print("mini " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")


if __name__ == "__main__":
    main()
