"""MV-8 江湖 — injetor de i18n. SÓ-ADIÇÕES, idempotente.

Molde: `scripts/inject_tec5_i18n.py`. ⚠️ `newline='\\n'` é LOAD-BEARING no Windows.
PT = **PORTUGUÊS BRASILEIRO** (você/seu; grafia BR) — nunca europeu.

ONDE VAI CADA COISA (a lição do MV-2, re-confirmada na verificação de 05/08):
  * Chronicle / sussurro / notificação  → SÓ `locales/{pt,en,es}.json` (chat).
    O mini-app tem ZERO keys `chron*` — ele lê a string JÁ RESOLVIDA pelo
    servidor. Pôr texto de anúncio em `miniapp/i18n` seria código morto.
  * Rótulo de flag no painel do owner   → SÓ `miniapp/i18n/{pt,en,es}.json`.
    NÃO existe registro Python de features nem campo de dependências: o backend
    manda `DEFAULT_WORLD_FEATURES` cru e o painel faz `t("feature_"+k)` /
    `t("feature_"+k+"_desc")`, caindo na string CRUA (`?? key`) se a key faltar.
    Logo as dependências e os avisos são PROSA dentro do `_desc`, ou o owner
    nunca as vê.
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Chat: os ANÚNCIOS (Chronicle) + os rótulos de goal ───────────────────────
# Placeholders resolvidos automaticamente pelo render: {sect} {rival} {continent}
# (de `_chronicle_localized_names`). Os demais viajam em `params` e são
# language-neutral — {npc} é nome próprio, nunca traduzido.
CHAT: dict[str, dict[str, str]] = {
    "pt": {
        "jh_chron_marchar":  "🚩 {npc} deixou {continent} e marcha rumo a {to_continent} — dizem que não vai voltar de mãos vazias.",
        "jh_chron_cacar":    "🗡️ {npc} anda perguntando por um nome em {continent}. Quem tem contas a acertar que ande com os olhos abertos.",
        "jh_chron_contrato": "📜 {npc} recolheu um contrato esquecido no quadro de {continent} — o nome nele já não interessa a ninguém.",
        "jh_chron_vendeta":  "🩸 {npc} e {other} cruzaram lâminas em {continent}. Uma dívida antiga ficou mais curta.",
        "jh_goal_marchar":   "🚩 Marchando",
        "jh_goal_cacar":     "🗡️ À sua procura",
        "jh_goal_contrato":  "📜 Cobrando um contrato",
        "jh_goal_vendeta":   "🩸 Em dívida de sangue",
        "jh_goal_idle":      "🏮 Em silêncio",
        # ── Parte 2 ──────────────────────────────────────────────────────
        # O fecho do kill-switch: um plano anunciado cujo autor evaporou NUNCA
        # some calado (Lei §1). 41% do elenco do s2 já ascendeu.
        "jh_chron_sumiu":    "🌫️ Ninguém mais viu {npc} desde então. No jiānghú, é assim que a maioria das histórias termina.",
        # ⚠️ DUAS linhas, não uma: a escala também DESCE (quem perdeu a vendeta
        # bate menos). Uma única frase dizia "dívidas cobradas" com −8% na tela
        # — o oposto do que aconteceu, na linha que É a disclosure do perigo.
        "jh_scale_line":     "⚔️ Golpe +{pct}% — dívidas de sangue cobradas recentemente.",
        "jh_scale_line_down": "⚔️ Golpe {pct}% — perdeu a última dívida de sangue e ainda sangra.",
        # A 🚩 Bandeira (5º estado regional). ⚠️ name/desc SEM placeholder: as
        # duas projeções chamam t() sem kwargs e a chaveta vazaria na tela.
        "rst_ocupada_name":  "Ocupada",
        "rst_ocupada_desc":  "uma bandeira estrangeira sobre a cidade — taxas mais altas, patrulhas nas estradas",
        "rst_ocupada_by":    "🚩 Bandeira de {sect}",
        "rst_chron_ocupada": "🚩 {sect} hasteou a própria bandeira sobre {continent}. Quem manda aqui mudou de nome.",
        # A emboscada — encontro com ESCOLHA, nunca duelo forçado.
        "jh_amb_title":        "🗡️ Emboscada",
        "jh_amb_intro":        "{npc} estava à sua espera. Não veio conversar.",
        "jh_amb_reason_karma": "Sua cabeça tem preço nestas estradas.",
        "jh_amb_reason_ato":   "Alguém viu o que você fez, e contou.",
        "jh_amb_reason_rep":   "Este lugar não gosta de você — e ele sabe disso.",
        "jh_amb_btn_fight":    "⚔️ Enfrentar",
        "jh_amb_btn_bribe":    "💰 Subornar ({cost})",
        "jh_amb_btn_flee":     "🏃 Recuar",
        "jh_amb_hint":         "Enfrentar custa {qi} de qi. Subornar custa {cost} pedras. Recuar custa a estrada: {hours}h de viagem.",
        "jh_amb_bribe_ok":     "💰 Você pagou {cost} pedras — exatamente o que a sua cabeça valia. {npc} guardou a lâmina e sumiu no mato.",
        "jh_amb_flee_ok":      "🏃 Você comprou distância com tempo. {npc} vai lembrar da sua fuga — e a estrada só esfria em {hours}h.",
        "jh_amb_fight_mini":   "⚔️ A luta abre no mini-app — o tabuleiro do duelo vive lá.",
        "jh_amb_gone":         "🌫️ Ele já não está aqui. As estradas engoliram mais um nome.",
        # PT-BR: "são precisas/precisos" é construção europeia — a casa usa
        # "você precisa de" (alch_not_enough_stones, explore_no_qi, ...).
        "jh_amb_no_stones":    "Pedras insuficientes: você precisa de {cost} e tem {have}.",
        "jh_amb_hp":           "Você não tem forças para levantar a lâmina. Recue ou pague.",
        "jh_amb_qi":           "Qi insuficiente: você precisa de {qi}.",
        "jh_amb_already":      "Esse encontro já terminou. O jiānghú não cobra a mesma dívida duas vezes.",
        "jh_amb_fight_won":    "⚔️ Você venceu {npc} na estrada. Espólio: 🪨 {stones}.",
        "jh_amb_fight_lost":   "🥀 {npc} levou a melhor. Você escapou com vida — e com a lição.",
        "jh_amb_fight_moral":  "☯️ Ele está caído aos seus pés. Poupar ou executar? A escolha vive no mini-app.",
        "jh_hunted_chip":      "🗡️ Caçadores rondam estas estradas ({n})",
        # Rótulo do registro de pacer no histórico de karma (delta 0). Sem esta
        # key o histórico mostraria a chave crua title-cased.
        "karma_event_jianghu_ambush": "🗡️ Encontro no jiānghú",
        # Os 2 storylets da ocupação — sem eles o continente ocupado passa 72h
        # com os storylets de sitiada/tensa/festival MUDOS (o matcher exige
        # pertença exata, e nenhum seed pedia "ocupada").
        "sty_bandeira_estrangeira_name": "A Bandeira Estrangeira",
        "sty_bandeira_estrangeira_desc": "Derrote 4 cultivadores enquanto a bandeira de outra casa estiver sobre este continente.",
        "sty_bandeira_estrangeira_d1":   "Eles cobram pedágio na ponte que meu avô construiu.",
        "sty_bandeira_estrangeira_d2":   "Não peço que expulse ninguém. Peço que eles sintam o peso de estar aqui.",
        "sty_pedagio_da_ocupacao_name":  "O Pedágio da Ocupação",
        "sty_pedagio_da_ocupacao_desc":  "Refine 3 pílulas enquanto a ocupação durar — os feridos não esperam a bandeira descer.",
        "sty_pedagio_da_ocupacao_d1":    "Com a guarnição nova, remédio virou contrabando.",
        "sty_pedagio_da_ocupacao_d2":    "Cure quem eles machucam. É a forma mais silenciosa de resistir.",
    },
    "en": {
        "jh_chron_marchar":  "🚩 {npc} has left {continent}, marching for {to_continent} — they say he will not return empty-handed.",
        "jh_chron_cacar":    "🗡️ {npc} has been asking after a name in {continent}. Whoever owes blood should walk with open eyes.",
        "jh_chron_contrato": "📜 {npc} took down a forgotten contract from the board in {continent} — the name on it no longer troubles anyone.",
        "jh_chron_vendeta":  "🩸 {npc} and {other} crossed blades in {continent}. An old debt grew shorter.",
        "jh_goal_marchar":   "🚩 Marching",
        "jh_goal_cacar":     "🗡️ Hunting you",
        "jh_goal_contrato":  "📜 Collecting a contract",
        "jh_goal_vendeta":   "🩸 Settling a blood debt",
        "jh_goal_idle":      "🏮 Silent",
        "jh_chron_sumiu":    "🌫️ Nobody has seen {npc} since. In the jianghu, that is how most stories end.",
        "jh_scale_line":     "⚔️ Strike +{pct}% — blood debts recently collected.",
        "jh_scale_line_down": "⚔️ Strike {pct}% — lost the last blood debt and is still bleeding.",
        "rst_ocupada_name":  "Occupied",
        "rst_ocupada_desc":  "a foreign banner over the city — higher tolls, patrols on the roads",
        "rst_ocupada_by":    "🚩 Banner of {sect}",
        "rst_chron_ocupada": "🚩 {sect} raised its own banner over {continent}. Who rules here has a new name.",
        "jh_amb_title":        "🗡️ Ambush",
        "jh_amb_intro":        "{npc} was waiting for you. Not to talk.",
        "jh_amb_reason_karma": "There is a price on your head along these roads.",
        "jh_amb_reason_ato":   "Someone saw what you did, and told.",
        "jh_amb_reason_rep":   "This place dislikes you — and he knows it.",
        "jh_amb_btn_fight":    "⚔️ Fight",
        "jh_amb_btn_bribe":    "💰 Bribe ({cost})",
        "jh_amb_btn_flee":     "🏃 Withdraw",
        "jh_amb_hint":         "Fighting costs {qi} qi. Bribing costs {cost} stones. Withdrawing costs the road: {hours}h of travel.",
        "jh_amb_bribe_ok":     "💰 You paid {cost} stones — exactly what your head was worth. {npc} sheathed the blade and vanished into the brush.",
        "jh_amb_flee_ok":      "🏃 You bought distance with time. {npc} will remember the running — and the road only cools in {hours}h.",
        "jh_amb_fight_mini":   "⚔️ The fight opens in the mini-app — the duel board lives there.",
        "jh_amb_gone":         "🌫️ He is no longer here. The roads swallowed another name.",
        "jh_amb_no_stones":    "Not enough stones: you need {cost} and have {have}.",
        "jh_amb_hp":           "You have no strength left to lift a blade. Withdraw or pay.",
        "jh_amb_qi":           "Not enough qi: you need {qi}.",
        "jh_amb_already":      "That encounter is over. The jianghu does not collect the same debt twice.",
        "jh_amb_fight_won":    "⚔️ You beat {npc} on the road. Spoils: 🪨 {stones}.",
        "jh_amb_fight_lost":   "🥀 {npc} got the better of you. You escaped with your life — and the lesson.",
        "jh_amb_fight_moral":  "☯️ He lies at your feet. Spare or execute? The choice lives in the mini-app.",
        "jh_hunted_chip":      "🗡️ Hunters prowl these roads ({n})",
        "karma_event_jianghu_ambush": "🗡️ Encounter in the jianghu",
        "sty_bandeira_estrangeira_name": "The Foreign Banner",
        "sty_bandeira_estrangeira_desc": "Defeat 4 cultivators while another house's banner flies over this continent.",
        "sty_bandeira_estrangeira_d1":   "They charge toll on the bridge my grandfather built.",
        "sty_bandeira_estrangeira_d2":   "I do not ask you to drive anyone out. I ask that they feel the weight of being here.",
        "sty_pedagio_da_ocupacao_name":  "The Toll of Occupation",
        "sty_pedagio_da_ocupacao_desc":  "Refine 3 pills while the occupation lasts — the wounded will not wait for the banner to come down.",
        "sty_pedagio_da_ocupacao_d1":    "With the new garrison, medicine became contraband.",
        "sty_pedagio_da_ocupacao_d2":    "Heal whoever they hurt. It is the quietest form of resistance.",
    },
    "es": {
        "jh_chron_marchar":  "🚩 {npc} dejó {continent} y marcha rumbo a {to_continent} — dicen que no volverá con las manos vacías.",
        "jh_chron_cacar":    "🗡️ {npc} anda preguntando por un nombre en {continent}. Quien deba sangre que camine con los ojos abiertos.",
        "jh_chron_contrato": "📜 {npc} recogió un contrato olvidado del tablón de {continent} — el nombre que lleva ya no le importa a nadie.",
        "jh_chron_vendeta":  "🩸 {npc} y {other} cruzaron filos en {continent}. Una deuda vieja se hizo más corta.",
        "jh_goal_marchar":   "🚩 Marchando",
        "jh_goal_cacar":     "🗡️ Buscándote",
        "jh_goal_contrato":  "📜 Cobrando un contrato",
        "jh_goal_vendeta":   "🩸 En deuda de sangre",
        "jh_goal_idle":      "🏮 En silencio",
        "jh_chron_sumiu":    "🌫️ Nadie volvió a ver a {npc} desde entonces. En el jianghu, así terminan casi todas las historias.",
        "jh_scale_line":     "⚔️ Golpe +{pct}% — deudas de sangre cobradas hace poco.",
        "jh_scale_line_down": "⚔️ Golpe {pct}% — perdió la última deuda de sangre y aún sangra.",
        "rst_ocupada_name":  "Ocupada",
        "rst_ocupada_desc":  "una bandera extranjera sobre la ciudad — peajes más altos, patrullas en los caminos",
        "rst_ocupada_by":    "🚩 Bandera de {sect}",
        "rst_chron_ocupada": "🚩 {sect} izó su propia bandera sobre {continent}. Quien manda aquí cambió de nombre.",
        "jh_amb_title":        "🗡️ Emboscada",
        "jh_amb_intro":        "{npc} te estaba esperando. No vino a conversar.",
        "jh_amb_reason_karma": "Tu cabeza tiene precio en estos caminos.",
        "jh_amb_reason_ato":   "Alguien vio lo que hiciste, y lo contó.",
        "jh_amb_reason_rep":   "Este lugar no te quiere — y él lo sabe.",
        "jh_amb_btn_fight":    "⚔️ Enfrentar",
        "jh_amb_btn_bribe":    "💰 Sobornar ({cost})",
        "jh_amb_btn_flee":     "🏃 Retirarse",
        "jh_amb_hint":         "Enfrentar cuesta {qi} de qi. Sobornar cuesta {cost} piedras. Retirarse cuesta el camino: {hours}h de viaje.",
        "jh_amb_bribe_ok":     "💰 Pagaste {cost} piedras — exactamente lo que valía tu cabeza. {npc} guardó la hoja y se perdió en el monte.",
        "jh_amb_flee_ok":      "🏃 Compraste distancia con tiempo. {npc} recordará la huida — y el camino solo se enfría en {hours}h.",
        "jh_amb_fight_mini":   "⚔️ La lucha se abre en la mini-app — el tablero del duelo vive allí.",
        "jh_amb_gone":         "🌫️ Ya no está aquí. Los caminos se tragaron otro nombre.",
        "jh_amb_no_stones":    "Piedras insuficientes: necesitas {cost} y tienes {have}.",
        "jh_amb_hp":           "No te quedan fuerzas para levantar la hoja. Retírate o paga.",
        "jh_amb_qi":           "Qi insuficiente: necesitas {qi}.",
        "jh_amb_already":      "Ese encuentro ya terminó. El jianghu no cobra la misma deuda dos veces.",
        "jh_amb_fight_won":    "⚔️ Venciste a {npc} en el camino. Botín: 🪨 {stones}.",
        "jh_amb_fight_lost":   "🥀 {npc} te ganó. Escapaste con vida — y con la lección.",
        "jh_amb_fight_moral":  "☯️ Yace a tus pies. ¿Perdonar o ejecutar? La elección vive en la mini-app.",
        "jh_hunted_chip":      "🗡️ Cazadores rondan estos caminos ({n})",
        "karma_event_jianghu_ambush": "🗡️ Encuentro en el jianghu",
        "sty_bandeira_estrangeira_name": "La Bandera Extranjera",
        "sty_bandeira_estrangeira_desc": "Derrota a 4 cultivadores mientras la bandera de otra casa ondee sobre este continente.",
        "sty_bandeira_estrangeira_d1":   "Cobran peaje en el puente que construyó mi abuelo.",
        "sty_bandeira_estrangeira_d2":   "No te pido que expulses a nadie. Te pido que sientan el peso de estar aquí.",
        "sty_pedagio_da_ocupacao_name":  "El Peaje de la Ocupación",
        "sty_pedagio_da_ocupacao_desc":  "Refina 3 píldoras mientras dure la ocupación — los heridos no esperan a que baje la bandera.",
        "sty_pedagio_da_ocupacao_d1":    "Con la guarnición nueva, la medicina se volvió contrabando.",
        "sty_pedagio_da_ocupacao_d2":    "Cura a quien ellos hieren. Es la forma más silenciosa de resistir.",
    },
}

_DESC_PT = (
    "⚠️ LAUNCH-SERVER-BOUND. Os NPCs deixam de ser estátuas com stats e passam a QUERER coisas. "
    "A cada batimento do mundo (6h), alguns escolhem um objetivo por utilidade — a alma deles vem de "
    "path/karma/casa, e o mundo só desempata: 🚩 Marchando (muda de continente de verdade — a praça, a "
    "exploração e a viagem passam a mostrá-lo no lugar novo) · 🗡️ À sua procura · 📜 Cobrando um contrato · "
    "🩸 Em dívida de sangue (NPC contra NPC — a notícia que não é sobre você). Os planos são ANUNCIADOS na "
    "Crônica: é a MESMA linha que vira o seu rumor, com atraso conforme a distância. "
    "ELENCO: só os NPCs nativos do mundo (os 'ecos' de jogadores reais são reescritos a cada 6h e por isso "
    "nunca agem). ORÇAMENTO: 3 atores por continente por batimento, mas só 2 anúncios — a maioria age em "
    "silêncio e só é vista por quem está lá (senão a Crônica vira log). "
    "DEPENDÊNCIAS: funciona sozinha, mas os efeitos mecânicos da 🚩 Bandeira exigem 'Estados Regionais' ON, "
    "e a porta de reputação da emboscada exige 'Reputação + Rival' ON — sem elas essas partes ficam apenas "
    "narrativas, nunca quebradas. ZERO migration."
)
_DESC_EN = (
    "⚠️ LAUNCH-SERVER-BOUND. NPCs stop being statues with stats and start WANTING things. "
    "On each world beat (6h) a few pick a goal by utility — their soul comes from path/karma/house, and the "
    "world only breaks ties: 🚩 Marching (they really change continent — plaza, exploration and travel show "
    "them in the new place) · 🗡️ Hunting you · 📜 Collecting a contract · 🩸 Settling a blood debt (NPC vs NPC "
    "— the news that isn't about you). Plans are ANNOUNCED in the Chronicle: it is the SAME line that becomes "
    "your rumour, delayed by distance. "
    "CAST: only world-native NPCs (the 'echoes' of real players are rewritten every 6h and therefore never act). "
    "BUDGET: 3 actors per continent per beat, but only 2 announcements — most act in silence and are seen only "
    "by whoever is there (otherwise the Chronicle becomes a log). "
    "DEPENDENCIES: works alone, but the 🚩 Banner's mechanical overrides need 'Regional States' ON, and the "
    "ambush's reputation gate needs 'Reputation + Rival' ON — without them those parts stay narrative only, "
    "never broken. ZERO migration."
)
_DESC_ES = (
    "⚠️ LAUNCH-SERVER-BOUND. Los NPCs dejan de ser estatuas con stats y pasan a QUERER cosas. "
    "En cada latido del mundo (6h) algunos eligen un objetivo por utilidad — su alma viene de path/karma/casa, "
    "y el mundo solo desempata: 🚩 Marchando (cambian de continente de verdad — la plaza, la exploración y el "
    "viaje pasan a mostrarlo en el lugar nuevo) · 🗡️ Buscándote · 📜 Cobrando un contrato · 🩸 En deuda de sangre "
    "(NPC contra NPC — la noticia que no es sobre ti). Los planes se ANUNCIAN en la Crónica: es la MISMA línea "
    "que se vuelve tu rumor, con retraso según la distancia. "
    "ELENCO: solo los NPCs nativos del mundo (los 'ecos' de jugadores reales se reescriben cada 6h y por eso "
    "nunca actúan). PRESUPUESTO: 3 actores por continente por latido, pero solo 2 anuncios — la mayoría actúa "
    "en silencio y solo la ve quien está allí (si no, la Crónica se vuelve un log). "
    "DEPENDENCIAS: funciona sola, pero los efectos mecánicos de la 🚩 Bandera exigen 'Estados Regionales' ON, y "
    "la puerta de reputación de la emboscada exige 'Reputación + Rival' ON — sin ellas esas partes quedan solo "
    "narrativas, nunca rotas. ZERO migration."
)

# ── Mini-app: SÓ o painel de flags do owner (self-doc) ───────────────────────
# O texto NARRATIVO (Crônica, motivo da emboscada, rótulo do goal, linha da
# Bandeira) é SEMPRE server-resolved e chega pronto — aqui só vive o CHROME que
# o cliente desenha sozinho.
MINI: dict[str, dict[str, str]] = {
    "pt": {
        "feature_jianghu": "O Jiānghú 江湖 — NPCs com vontade (MV-8)",
        "feature_jianghu_desc": _DESC_PT,
        "jh_amb_chip":       "🗡️ Alguém te espera",
        "jh_amb_chip_hint":  "Toque para encarar o encontro",
        "jh_amb_fight":      "⚔️ Enfrentar",
        "jh_amb_bribe":      "💰 Subornar",
        "jh_amb_flee":       "🏃 Recuar",
        "jh_amb_bribe_cost": "{cost} pedras",
        "jh_amb_bribe_hint": "Você paga o que a sua cabeça valia.",
        "jh_amb_flee_hint":  "Compra distância com tempo — a estrada esfria em {hours}h.",
        "jh_amb_fight_hint": "Custa {qi} de qi. Nenhum duelo começa sem o seu toque.",
        "jh_amb_stones":     "Suas pedras: {have}",
        "jh_amb_done":       "O encontro terminou.",
        # ⚠️ O mini-app tem o SEU t(): uma key que só existe no locale de chat
        # volta como a PRÓPRIA CHAVE (truthy — o `|| "—"` nunca dispara). Estas
        # três são os caminhos de FALHA mais quentes do encontro.
        "jh_amb_gone":       "🌫️ Ele já não está aqui. As estradas engoliram mais um nome.",
        "jh_amb_no_qi":      "Qi insuficiente: você precisa de {qi}.",
        "jh_amb_no_stones":  "Pedras insuficientes: você precisa de {cost} e tem {have}.",
        "jh_amb_already":    "Esse encontro já terminou.",
        "jh_hunted":         "🗡️ Caçadores rondam ({n})",
        "jh_npc_since":      "há {time}",
    },
    "en": {
        "feature_jianghu": "The Jiānghú 江湖 — NPCs with will (MV-8)",
        "feature_jianghu_desc": _DESC_EN,
        "jh_amb_chip":       "🗡️ Someone is waiting for you",
        "jh_amb_chip_hint":  "Tap to face the encounter",
        "jh_amb_fight":      "⚔️ Fight",
        "jh_amb_bribe":      "💰 Bribe",
        "jh_amb_flee":       "🏃 Withdraw",
        "jh_amb_bribe_cost": "{cost} stones",
        "jh_amb_bribe_hint": "You pay exactly what your head was worth.",
        "jh_amb_flee_hint":  "Buys distance with time — the road cools in {hours}h.",
        "jh_amb_fight_hint": "Costs {qi} qi. No duel starts without your tap.",
        "jh_amb_stones":     "Your stones: {have}",
        "jh_amb_done":       "The encounter is over.",
        "jh_amb_gone":       "🌫️ He is no longer here. The roads swallowed another name.",
        "jh_amb_no_qi":      "Not enough qi: you need {qi}.",
        "jh_amb_no_stones":  "Not enough stones: you need {cost} and have {have}.",
        "jh_amb_already":    "That encounter is over.",
        "jh_hunted":         "🗡️ Hunters prowl here ({n})",
        "jh_npc_since":      "{time} ago",
    },
    "es": {
        "feature_jianghu": "El Jiānghú 江湖 — NPCs con voluntad (MV-8)",
        "feature_jianghu_desc": _DESC_ES,
        "jh_amb_chip":       "🗡️ Alguien te espera",
        "jh_amb_chip_hint":  "Toca para encarar el encuentro",
        "jh_amb_fight":      "⚔️ Enfrentar",
        "jh_amb_bribe":      "💰 Sobornar",
        "jh_amb_flee":       "🏃 Retirarse",
        "jh_amb_bribe_cost": "{cost} piedras",
        "jh_amb_bribe_hint": "Pagas exactamente lo que valía tu cabeza.",
        "jh_amb_flee_hint":  "Compra distancia con tiempo — el camino se enfría en {hours}h.",
        "jh_amb_fight_hint": "Cuesta {qi} de qi. Ningún duelo empieza sin tu toque.",
        "jh_amb_stones":     "Tus piedras: {have}",
        "jh_amb_done":       "El encuentro terminó.",
        "jh_amb_gone":       "🌫️ Ya no está aquí. Los caminos se tragaron otro nombre.",
        "jh_amb_no_qi":      "Qi insuficiente: necesitas {qi}.",
        "jh_amb_no_stones":  "Piedras insuficientes: necesitas {cost} y tienes {have}.",
        "jh_amb_already":    "Ese encuentro ya terminó.",
        "jh_hunted":         "🗡️ Cazadores rondan ({n})",
        "jh_npc_since":      "hace {time}",
    },
}


# ── Keys REESCRITAS dentro da própria sessão (nunca key de outra onda) ──────
# `_inject` é add-only por contrato. Estas nasceram nesta sessão e o review
# adversarial derrubou o texto delas ANTES do deploy, então o valor bom vive
# em CHAT/MINI (UMA fonte — o verificador exige `ficheiro == injetor`) e esta
# lista apenas AUTORIZA a reescrita por cima do texto já gravado:
#   · jh_hunted_chip / jh_hunted — a contagem é GLOBAL, mas a frase dizia "há
#     quem te procure": um jogador de karma 0, que a emboscada nunca alcança,
#     lia uma ameaça inexistente. A contagem era honesta; a frase mentia.
#   · jh_amb_no_stones / jh_amb_qi — "são precisas/precisos" é PT-EUROPEU.
#   · jh_scale_line — o sinal saiu para dentro da string (há agora um par
#     _line/_line_down: a escala também DESCE).
REWRITE: frozenset = frozenset((
    "jh_hunted_chip", "jh_hunted",
    "jh_amb_no_stones", "jh_amb_qi", "jh_scale_line",
))


def _inject(path: str, add: dict[str, str]) -> tuple[int, int]:
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    added = 0
    for key, val in add.items():
        if key in data and key not in REWRITE:
            continue
        if data.get(key) == val:
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
        n, total = _inject(os.path.join(ROOT, "locales", f"{lang}.json"), add)
        print(f"chat  {lang}: +{n}  (total {total})")
    for lang, add in MINI.items():
        n, total = _inject(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"), add)
        print(f"mini  {lang}: +{n}  (total {total})")


if __name__ == "__main__":
    main()
