"""MV-9 城 "As Cinco Cidades" — injetor de i18n. Idempotente.

Molde: `scripts/inject_mv8_i18n.py`. ⚠️ `newline='\\n'` é LOAD-BEARING no Windows.
PT = **PORTUGUÊS BRASILEIRO** (você/seu; grafia BR) — nunca europeu.

ONDE VAI CADA COISA (a lei de colocação, re-confirmada nesta onda):
  * Nome/intro/traço da cidade, nome/descrição de encargo, linha da Crônica,
    recusas → SÓ `locales/{pt,en,es}.json` (chat). O servidor RESOLVE e manda a
    string pronta (padrão Crônica/jiānghú); o mini-app imprime `{city.name}` /
    `{enc.name}` cru, sem `t()`. Pôr estas keys em `miniapp/i18n` seria código
    morto — e pior, uma segunda fonte da mesma frase.
  * Rótulo da flag no painel do owner + rótulos que o CLIENTE compõe sozinho
    (título do cartão, texto do botão) → SÓ `miniapp/i18n/{pt,en,es}.json`.

⚠️ REESCRITAS (3 keys): as strings de bounty tinham "Wànshì" COZIDO no valor —
invisíveis a qualquer grep por `city_wanshi`. Com cinco cidades, um jogador em
Mòyǔ lia "Cidade dos Ecos" no cabeçalho e, três linhas abaixo, que o contrato
estava pendurado nos "Arquivos de Wànshì" — que ficam noutro continente. Passam
a receber `{city}`, resolvido no idioma de quem lê.

⚠️ A key ANTIGA `city_wanshi` ("Praça de Wànshì") NÃO é tocada: é o fallback do
caminho com a flag OFF, e mexer nela quebraria a identidade byte-a-byte do
`main`.
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Chat: tudo o que o SERVIDOR resolve ─────────────────────────────────────
CHAT: dict[str, dict[str, str]] = {
    "pt": {
        # ── As cinco cidades (nomes do world_lore §3 — zero invenção) ──────
        "city_wanshi_name":   "Cidade de Wànshì",
        "city_wanshi_intro":  "A maior praça comercial do mundo. Tudo o que se compra, se compra aqui — e tudo o que se sabe, se ouve aqui primeiro.",
        "city_wanshi_trait":  "🏙️ O berço · onde as nove seitas mandam recado",
        "city_tiequan_name":  "Templo do Punho de Ferro",
        "city_tiequan_intro": "Não há qi no pátio, só corpos. Os monges daqui quebram pedra antes do amanhecer e dizem que o Dao entra pelos ossos.",
        "city_tiequan_trait": "🏯 O corpo antes do qi · minério dos rios profundos",
        "city_wanhua_name":   "Jardim das Dez Mil Flores",
        "city_wanhua_intro":  "Um jardim que é cidade: cada muro tem uma erva rara e cada erva tem dono. Os melhores alquimistas do mundo nasceram destes canteiros.",
        "city_wanhua_trait":  "🌺 Ervas raras · o caldeirão nunca esfria",
        "city_tianhuo_name":  "Forja de Tiānhuǒ",
        "city_tianhuo_intro": "Construída dentro de um vulcão vivo. O martelo não para desde antes da Calamidade, e dizem que apagar a fornalha apagaria o mundo.",
        "city_tianhuo_trait": "🔥 A maior forja do mundo · aço e sangue",
        "city_huiyin_name":   "Cidade dos Ecos",
        "city_huiyin_intro":  "Ruínas de uma civilização anterior à Calamidade. Ninguém a construiu; alguém a deixou. As vozes que se ouvem à noite não são de ninguém que esteja vivo.",
        "city_huiyin_trait":  "🕯️ Ruínas pré-Calamidade · o proibido mora aqui",

        # ── O Encargo 城务: os 15 pedidos (name + desc) ────────────────────
        "sty_enc_linghe_selos_name":     "Selar os Portais Rasos",
        "sty_enc_linghe_selos_desc":     "Os portais em volta de Wànshì andam vomitando coisas. O magistrado paga a quem descer e fechar o que puder.",
        "sty_enc_linghe_vigilia_name":   "A Vigília das Nove Casas",
        "sty_enc_linghe_vigilia_desc":   "As nove seitas exigem um turno de meditação nos altares da praça. Quem senta, senta em nome da cidade inteira.",
        "sty_enc_linghe_escolta_name":   "Escoltar as Caravanas",
        "sty_enc_linghe_escolta_desc":   "Nenhuma caravana chegou inteira esta semana. Wànshì vive do que entra pelos portões — e agora não está entrando.",
        "sty_enc_qianhe_minerio_name":   "O Peso do Minério",
        "sty_enc_qianhe_minerio_desc":   "Os rios subterrâneos abriram veios novos. O Templo precisa de mãos que desçam e voltem carregadas.",
        "sty_enc_qianhe_provas_name":    "As Provas do Punho",
        "sty_enc_qianhe_provas_desc":    "Os discípulos do Templo precisam de alguém que bata mais forte que eles. Você serve.",
        "sty_enc_qianhe_carga_name":     "As Bestas de Carga",
        "sty_enc_qianhe_carga_desc":     "O Templo criou bestas para carregar pedra e perdeu metade delas no gelo. Traga-as de volta, ou traga outras.",
        "sty_enc_yanshan_pilulas_name":  "O Caldeirão Comum",
        "sty_enc_yanshan_pilulas_desc":  "O Jardim reparte o que se refina. Encha o caldeirão comum e ninguém pergunta de onde vieram as ervas.",
        "sty_enc_yanshan_remedio_name":  "Remédio para os Canteiros",
        "sty_enc_yanshan_remedio_desc":  "Metade dos jardineiros está de cama. O Jardim não pede pílulas — pede que alguém as USE em quem precisa.",
        "sty_enc_yanshan_colheita_name": "A Colheita das Dez Mil",
        "sty_enc_yanshan_colheita_desc":  "As flores só abrem uma vez por estação e as bestas chegam antes dos colhedores. Vá buscar o que sobrou.",
        "sty_enc_fenghuo_forja_name":    "A Fornalha Não Pode Esfriar",
        "sty_enc_fenghuo_forja_desc":    "Tiānhuǒ mede a saúde do mundo pelo que sai das bigornas. Este mês está saindo pouco.",
        "sty_enc_fenghuo_tempera_name":  "Temperar no Sangue",
        "sty_enc_fenghuo_tempera_desc":  "Aço que não bebeu nunca segura um golpe de verdade. A Forja quer lâminas provadas, não lâminas novas.",
        "sty_enc_fenghuo_arena_name":    "A Arena de Sangue Chama",
        "sty_enc_fenghuo_arena_desc":    "A cidade inteira aposta. A Forja não liga para quem ganha — liga para a casa cheia.",
        "sty_enc_moyu_ruinas_name":      "Descer aos Ecos",
        "sty_enc_moyu_ruinas_desc":      "Há andares por baixo da cidade que ninguém mapeou. Quem desce e volta traz coisas que não deviam existir.",
        "sty_enc_moyu_ecos_name":        "Calar o que Sussurra",
        "sty_enc_moyu_ecos_desc":        "Alguma coisa nas ruínas está imitando vozes de gente viva. A cidade quer silêncio.",
        "sty_enc_moyu_vigilia_name":     "A Vigília sem Lua",
        "sty_enc_moyu_vigilia_desc":     "Em Mòyǔ medita-se de olhos abertos. Fique sentado o bastante e o que sussurra acaba se mostrando.",

        # ── A Crônica: o anúncio do pedido novo (o UNFOLDING) ─────────────
        # {city} e {encargo} são resolvidos por leitor em
        # `world_pulse_engine._chronicle_localized_names` — NUNCA cozidos aqui.
        "cid_chron_encargo": "🏙️ Correu voz de {city}: agora pedem {encargo}.",

        # ── O que a cidade quer, na tela de viagem ─────────────────────────
        "cid_travel_wants": "{icon} Pede: {name}",
        "cid_travel_stale": "(notícia de {h}h atrás)",

        # ── A praça (chat) ────────────────────────────────────────────────
        "cid_plaza_encargo_title": "📜 Encargo da cidade",
        "cid_plaza_progress":      "Progresso: {n}/{total}",
        "cid_plaza_accept_hint":   "Abra o mini-app para assumir o encargo.",

        # ── As recusas, todas NOMEADAS (Lei §1) ───────────────────────────
        "cid_encargo_locked":    "📜 A cidade tem um pedido, mas ninguém está anotando nomes ainda.",
        "cid_refuse_flag":       "📜 Esta cidade ainda não recebe encargos.",
        "cid_refuse_busy":       "📜 Você já tem um encargo em mãos.",
        "cid_refuse_other_open": "📜 Você já carrega outro encargo: {name}. Termine ou deixe vencer antes de assumir este.",
        "cid_refuse_repeat":     "📜 Você acabou de entregar este mesmo encargo. A cidade volta a pedi-lo em {h}h.",
        "cid_encargo_accepted":  "📜 {city} anotou o seu nome: {name}.",
    },
    "en": {
        "city_wanshi_name":   "City of Wànshì",
        "city_wanshi_intro":  "The greatest trading square in the world. Everything that is bought is bought here — and everything that is known is heard here first.",
        "city_wanshi_trait":  "🏙️ The cradle · where the nine sects send word",
        "city_tiequan_name":  "Temple of the Iron Fist",
        "city_tiequan_intro": "No qi in this courtyard, only bodies. Its monks break stone before dawn and say the Dao enters through the bones.",
        "city_tiequan_trait": "🏯 Body before qi · ore from the deep rivers",
        "city_wanhua_name":   "Garden of Ten Thousand Flowers",
        "city_wanhua_intro":  "A garden that became a city: every wall holds a rare herb and every herb has an owner. The world's finest alchemists grew out of these beds.",
        "city_wanhua_trait":  "🌺 Rare herbs · the cauldron never cools",
        "city_tianhuo_name":  "Forge of Tiānhuǒ",
        "city_tianhuo_intro": "Built inside a living volcano. The hammer has not stopped since before the Calamity, and they say dousing the furnace would douse the world.",
        "city_tianhuo_trait": "🔥 The world's greatest forge · steel and blood",
        "city_huiyin_name":   "City of Echoes",
        "city_huiyin_intro":  "Ruins of a civilisation older than the Calamity. Nobody built it; somebody left it. The voices heard at night belong to no one alive.",
        "city_huiyin_trait":  "🕯️ Pre-Calamity ruins · the forbidden lives here",

        "sty_enc_linghe_selos_name":     "Seal the Shallow Gates",
        "sty_enc_linghe_selos_desc":     "The portals around Wànshì have been spitting things out. The magistrate pays whoever goes down and closes what they can.",
        "sty_enc_linghe_vigilia_name":   "Vigil of the Nine Houses",
        "sty_enc_linghe_vigilia_desc":   "The nine sects demand a shift of meditation at the square's altars. Whoever sits, sits for the whole city.",
        "sty_enc_linghe_escolta_name":   "Escort the Caravans",
        "sty_enc_linghe_escolta_desc":   "Not one caravan arrived whole this week. Wànshì lives on what comes through its gates — and nothing is coming through.",
        "sty_enc_qianhe_minerio_name":   "The Weight of Ore",
        "sty_enc_qianhe_minerio_desc":   "The underground rivers opened new veins. The Temple needs hands that go down and come back loaded.",
        "sty_enc_qianhe_provas_name":    "Trials of the Fist",
        "sty_enc_qianhe_provas_desc":    "The Temple's disciples need someone who hits harder than they do. You will do.",
        "sty_enc_qianhe_carga_name":     "The Beasts of Burden",
        "sty_enc_qianhe_carga_desc":     "The Temple bred beasts to haul stone and lost half of them to the ice. Bring them back, or bring others.",
        "sty_enc_yanshan_pilulas_name":  "The Common Cauldron",
        "sty_enc_yanshan_pilulas_desc":  "The Garden shares what it refines. Fill the common cauldron and nobody asks where the herbs came from.",
        "sty_enc_yanshan_remedio_name":  "Medicine for the Beds",
        "sty_enc_yanshan_remedio_desc":  "Half the gardeners are bedridden. The Garden is not asking for pills — it is asking that someone USE them on those who need them.",
        "sty_enc_yanshan_colheita_name": "Harvest of the Ten Thousand",
        "sty_enc_yanshan_colheita_desc": "The flowers open once a season and the beasts arrive before the harvesters. Go fetch what is left.",
        "sty_enc_fenghuo_forja_name":    "The Furnace Must Not Cool",
        "sty_enc_fenghuo_forja_desc":    "Tiānhuǒ measures the world's health by what leaves its anvils. This month, little is leaving.",
        "sty_enc_fenghuo_tempera_name":  "Temper It in Blood",
        "sty_enc_fenghuo_tempera_desc":  "Steel that has not drunk never holds a real blow. The Forge wants proven blades, not new ones.",
        "sty_enc_fenghuo_arena_name":    "The Blood Arena Calls",
        "sty_enc_fenghuo_arena_desc":    "The whole city is betting. The Forge does not care who wins — it cares that the house is full.",
        "sty_enc_moyu_ruinas_name":      "Descend into the Echoes",
        "sty_enc_moyu_ruinas_desc":      "There are floors beneath the city that nobody has mapped. Whoever goes down and returns brings back things that should not exist.",
        "sty_enc_moyu_ecos_name":        "Silence What Whispers",
        "sty_enc_moyu_ecos_desc":        "Something in the ruins is imitating the voices of living people. The city wants silence.",
        "sty_enc_moyu_vigilia_name":     "The Moonless Vigil",
        "sty_enc_moyu_vigilia_desc":     "In Mòyǔ one meditates with open eyes. Sit long enough and whatever whispers eventually shows itself.",

        "cid_chron_encargo": "🏙️ Word came from {city}: they are asking for {encargo} now.",
        "cid_travel_wants": "{icon} Asking for: {name}",
        "cid_travel_stale": "(news from {h}h ago)",
        "cid_plaza_encargo_title": "📜 City charge",
        "cid_plaza_progress":      "Progress: {n}/{total}",
        "cid_plaza_accept_hint":   "Open the mini-app to take the charge.",
        "cid_encargo_locked":    "📜 The city has a request, but nobody is writing names down yet.",
        "cid_refuse_flag":       "📜 This city does not take charges yet.",
        "cid_refuse_busy":       "📜 You already have a charge in hand.",
        "cid_refuse_other_open": "📜 You are already carrying another charge: {name}. Finish it or let it lapse before taking this one.",
        "cid_refuse_repeat":     "📜 You have just delivered this very charge. The city will ask again in {h}h.",
        "cid_encargo_accepted":  "📜 {city} wrote your name down: {name}.",
    },
    "es": {
        "city_wanshi_name":   "Ciudad de Wànshì",
        "city_wanshi_intro":  "La mayor plaza comercial del mundo. Todo lo que se compra se compra aquí — y todo lo que se sabe se oye aquí primero.",
        "city_wanshi_trait":  "🏙️ La cuna · donde las nueve sectas mandan recado",
        "city_tiequan_name":  "Templo del Puño de Hierro",
        "city_tiequan_intro": "No hay qi en este patio, solo cuerpos. Sus monjes rompen piedra antes del alba y dicen que el Dao entra por los huesos.",
        "city_tiequan_trait": "🏯 El cuerpo antes que el qi · mineral de los ríos profundos",
        "city_wanhua_name":   "Jardín de las Diez Mil Flores",
        "city_wanhua_intro":  "Un jardín que se volvió ciudad: cada muro guarda una hierba rara y cada hierba tiene dueño. Los mejores alquimistas del mundo salieron de estos bancales.",
        "city_wanhua_trait":  "🌺 Hierbas raras · el caldero nunca se enfría",
        "city_tianhuo_name":  "Forja de Tiānhuǒ",
        "city_tianhuo_intro": "Construida dentro de un volcán vivo. El martillo no para desde antes de la Calamidad, y dicen que apagar la fragua apagaría el mundo.",
        "city_tianhuo_trait": "🔥 La mayor forja del mundo · acero y sangre",
        "city_huiyin_name":   "Ciudad de los Ecos",
        "city_huiyin_intro":  "Ruinas de una civilización anterior a la Calamidad. Nadie la construyó; alguien la dejó. Las voces que se oyen de noche no son de nadie vivo.",
        "city_huiyin_trait":  "🕯️ Ruinas pre-Calamidad · lo prohibido vive aquí",

        "sty_enc_linghe_selos_name":     "Sellar los Portales Someros",
        "sty_enc_linghe_selos_desc":     "Los portales alrededor de Wànshì llevan días vomitando cosas. El magistrado paga a quien baje y cierre lo que pueda.",
        "sty_enc_linghe_vigilia_name":   "La Vigilia de las Nueve Casas",
        "sty_enc_linghe_vigilia_desc":   "Las nueve sectas exigen un turno de meditación en los altares de la plaza. Quien se sienta, se sienta por la ciudad entera.",
        "sty_enc_linghe_escolta_name":   "Escoltar las Caravanas",
        "sty_enc_linghe_escolta_desc":   "Ninguna caravana llegó entera esta semana. Wànshì vive de lo que entra por sus puertas — y no está entrando nada.",
        "sty_enc_qianhe_minerio_name":   "El Peso del Mineral",
        "sty_enc_qianhe_minerio_desc":   "Los ríos subterráneos abrieron vetas nuevas. El Templo necesita manos que bajen y vuelvan cargadas.",
        "sty_enc_qianhe_provas_name":    "Las Pruebas del Puño",
        "sty_enc_qianhe_provas_desc":    "Los discípulos del Templo necesitan a alguien que golpee más fuerte que ellos. Tú sirves.",
        "sty_enc_qianhe_carga_name":     "Las Bestias de Carga",
        "sty_enc_qianhe_carga_desc":     "El Templo crió bestias para acarrear piedra y perdió la mitad en el hielo. Tráelas de vuelta, o trae otras.",
        "sty_enc_yanshan_pilulas_name":  "El Caldero Común",
        "sty_enc_yanshan_pilulas_desc":  "El Jardín reparte lo que refina. Llena el caldero común y nadie pregunta de dónde salieron las hierbas.",
        "sty_enc_yanshan_remedio_name":  "Remedio para los Bancales",
        "sty_enc_yanshan_remedio_desc":  "La mitad de los jardineros está en cama. El Jardín no pide píldoras — pide que alguien las USE en quien las necesita.",
        "sty_enc_yanshan_colheita_name": "La Cosecha de las Diez Mil",
        "sty_enc_yanshan_colheita_desc": "Las flores abren una vez por estación y las bestias llegan antes que los cosechadores. Ve a buscar lo que quedó.",
        "sty_enc_fenghuo_forja_name":    "La Fragua No Puede Enfriarse",
        "sty_enc_fenghuo_forja_desc":    "Tiānhuǒ mide la salud del mundo por lo que sale de sus yunques. Este mes sale poco.",
        "sty_enc_fenghuo_tempera_name":  "Templar en Sangre",
        "sty_enc_fenghuo_tempera_desc":  "El acero que no ha bebido nunca aguanta un golpe de verdad. La Forja quiere hojas probadas, no hojas nuevas.",
        "sty_enc_fenghuo_arena_name":    "La Arena de Sangre Llama",
        "sty_enc_fenghuo_arena_desc":    "La ciudad entera apuesta. A la Forja no le importa quién gana — le importa que la casa esté llena.",
        "sty_enc_moyu_ruinas_name":      "Bajar a los Ecos",
        "sty_enc_moyu_ruinas_desc":      "Hay pisos bajo la ciudad que nadie ha cartografiado. Quien baja y vuelve trae cosas que no deberían existir.",
        "sty_enc_moyu_ecos_name":        "Callar lo que Susurra",
        "sty_enc_moyu_ecos_desc":        "Algo en las ruinas está imitando voces de gente viva. La ciudad quiere silencio.",
        "sty_enc_moyu_vigilia_name":     "La Vigilia sin Luna",
        "sty_enc_moyu_vigilia_desc":     "En Mòyǔ se medita con los ojos abiertos. Siéntate lo bastante y lo que susurra acaba mostrándose.",

        "cid_chron_encargo": "🏙️ Llegó voz de {city}: ahora piden {encargo}.",
        "cid_travel_wants": "{icon} Pide: {name}",
        "cid_travel_stale": "(noticia de hace {h}h)",
        "cid_plaza_encargo_title": "📜 Encargo de la ciudad",
        "cid_plaza_progress":      "Progreso: {n}/{total}",
        "cid_plaza_accept_hint":   "Abre la mini-app para asumir el encargo.",
        "cid_encargo_locked":    "📜 La ciudad tiene una petición, pero aún nadie anota nombres.",
        "cid_refuse_flag":       "📜 Esta ciudad todavía no recibe encargos.",
        "cid_refuse_busy":       "📜 Ya tienes un encargo entre manos.",
        "cid_refuse_other_open": "📜 Ya cargas otro encargo: {name}. Termínalo o déjalo vencer antes de asumir este.",
        "cid_refuse_repeat":     "📜 Acabas de entregar este mismo encargo. La ciudad volverá a pedirlo en {h}h.",
        "cid_encargo_accepted":  "📜 {city} anotó tu nombre: {name}.",
    },
}


# ── Mini-app: só o que o CLIENTE compõe sozinho ─────────────────────────────
MINI: dict[str, dict[str, str]] = {
    "pt": {
        # Painel do owner. A conjunção com `quests_vivas` vai em PROSA aqui —
        # não existe campo de dependências; se não estiver escrito, o owner
        # liga `cidades` sozinha e não entende por que o encargo não aparece.
        "feature_cidades": "🏙️ MV-9 — As Cinco Cidades 城",
        "feature_cidades_desc": "Cada continente ganha UMA cidade com nome próprio (Wànshì · Templo do Punho de Ferro · Jardim das Dez Mil Flores · Forja de Tiānhuǒ · Cidade dos Ecos) e um ENCARGO 城务: o pedido do lugar, que muda a cada dia e é anunciado na Crônica com atraso de viagem (você lê o que a cidade queria quando a notícia partiu). EXIGE `quests_vivas` ON para o encargo funcionar — sem ela a cidade tem nome e identidade, e diz que o encargo está fechado. Sem migration.",
        "cid_card_title":   "🏙️ A cidade",
        "cid_encargo_head": "📜 Encargo da cidade",
        "cid_encargo_btn":  "Assumir o encargo",
        "cid_encargo_open": "Você já assumiu este encargo",
        "cid_encargo_done": "✅ Pronto para entregar — veja em Missões",
        "cid_travel_head":  "🏙️ {name}",
    },
    "en": {
        "feature_cidades": "🏙️ MV-9 — The Five Cities 城",
        "feature_cidades_desc": "Every continent gains ONE named city (Wànshì · Temple of the Iron Fist · Garden of Ten Thousand Flowers · Forge of Tiānhuǒ · City of Echoes) and a CHARGE 城务: the place's standing request, which changes daily and is announced in the Chronicle with travel delay (you read what the city wanted when the news set out). REQUIRES `quests_vivas` ON for the charge to work — without it the city still has a name and an identity, and says the charge is closed. No migration.",
        "cid_card_title":   "🏙️ The city",
        "cid_encargo_head": "📜 City charge",
        "cid_encargo_btn":  "Take the charge",
        "cid_encargo_open": "You have already taken this charge",
        "cid_encargo_done": "✅ Ready to deliver — see it in Quests",
        "cid_travel_head":  "🏙️ {name}",
    },
    "es": {
        "feature_cidades": "🏙️ MV-9 — Las Cinco Ciudades 城",
        "feature_cidades_desc": "Cada continente gana UNA ciudad con nombre propio (Wànshì · Templo del Puño de Hierro · Jardín de las Diez Mil Flores · Forja de Tiānhuǒ · Ciudad de los Ecos) y un ENCARGO 城务: la petición del lugar, que cambia cada día y se anuncia en la Crónica con retraso de viaje (lees lo que la ciudad quería cuando partió la noticia). REQUIERE `quests_vivas` ON para que el encargo funcione — sin ella la ciudad conserva nombre e identidad, y dice que el encargo está cerrado. Sin migration.",
        "cid_card_title":   "🏙️ La ciudad",
        "cid_encargo_head": "📜 Encargo de la ciudad",
        "cid_encargo_btn":  "Asumir el encargo",
        "cid_encargo_open": "Ya asumiste este encargo",
        "cid_encargo_done": "✅ Listo para entregar — mira en Misiones",
        "cid_travel_head":  "🏙️ {name}",
    },
}


# ── As 3 strings que tinham "Wànshì" COZIDO no valor ────────────────────────
# Invisíveis a qualquer grep por `city_wanshi`: o nome estava dentro da frase.
# Passam a `{city}`, e os três call sites passam a cidade do continente do
# CONTRATO (nunca a do leitor — o contrato está pendurado onde foi postado).
# ⚠️ DUAS regras que o review adversarial impôs, ambas medidas no código:
#
#  (a) **Uma NOTIFICAÇÃO nunca ganha um placeholder novo.**
#      `player_notifications` guarda `body_key` + `payload` e renderiza
#      PREGUIÇOSAMENTE na leitura (`notification_engine._serialize`), sem poda
#      nem TTL. No dia em que a string ganha `{city}`, TODA linha já gravada
#      (payload antigo, sem essa chave) passa a mostrar texto partido — e isso
#      atinge o `main`, onde a flag `cidades` está OFF e nada disto devia
#      chegar. Logo `notif_bounty_claimed_body` é reescrita para uma frase
#      **sem placeholder novo**: mata a mentira ("Arquivos de Wànshì" em 4 dos
#      5 continentes) sem tocar em nenhuma row antiga.
#
#  (b) **`de {city}` é agramatical** quando o nome é um sintagma comum
#      ("Templo do Punho de Ferro" → *"nos arquivos de Templo do Punho de
#      Ferro"*). As duas strings que ficam com `{city}` são renderizadas AO
#      VIVO (o hint do chat e o intro do mini), portanto o placeholder é
#      seguro — mas a frase põe o nome depois de um travessão, onde qualquer
#      nome cai bem em pt/en/es.
REWRITE_CHAT: dict[str, dict[str, str]] = {
    "pt": {
        "wbounty_post_chat_hint": "Quer pôr a cabeça de um demônio a prêmio? Abra o mini-app para publicar um contrato nos arquivos da cidade — {city}.",
        "notif_bounty_claimed_body": "{hunter} derrotou {target} e reivindicou a recompensa que você publicou nos arquivos da cidade.",
    },
    "en": {
        "wbounty_post_chat_hint": "Want to put a demon's head up for a prize? Open the mini-app to post a contract at the city archives — {city}.",
        "notif_bounty_claimed_body": "{hunter} defeated {target} and claimed the bounty you posted at the city archives.",
    },
    "es": {
        "wbounty_post_chat_hint": "¿Quieres poner precio a la cabeza de un demonio? Abre el mini-app para publicar un contrato en los archivos de la ciudad — {city}.",
        "notif_bounty_claimed_body": "{hunter} derrotó a {target} y reclamó la recompensa que publicaste en los archivos de la ciudad.",
    },
}

REWRITE_MINI: dict[str, dict[str, str]] = {
    "pt": {
        "wbounty_post_intro": "Coloque a cabeça deste alvo a prêmio nos arquivos da cidade — {city} 万事阁. O primeiro caçador que o derrotar leva o prêmio. As pedras saem agora e são definitivas — não há reembolso.",
    },
    "en": {
        "wbounty_post_intro": "Put this target's head up for a prize at the city archives — {city} 万事阁. The first hunter to defeat them takes the prize. The stones are spent now and are final — there is no refund.",
    },
    "es": {
        "wbounty_post_intro": "Pon precio a la cabeza de este objetivo en los archivos de la ciudad — {city} 万事阁. El primer cazador que lo derrote se lleva el premio. Las piedras se gastan ahora y son definitivas — no hay reembolso.",
    },
}


# ── Os diálogos dos 15 encargos (`_d1` / `_d2`) ─────────────────────────────
# A convenção do MV-5 é `sty_<key>_name/_desc/_d1/_d2` e o guard de
# `scripts/_test_mv5_storylets.py` exige as QUATRO em todo seed — com razão: o
# encargo é uma row de `storylet_catalog` como qualquer outra, e no dia em que
# alguém lhe der peso > 0 (ou uma tela renderizar o diálogo do doador) uma key
# em falta imprimia `sty_enc_moyu_vigilia_d1` cru na cara do jogador. São as
# duas falas de quem afixa o pedido: o funcionário da cidade.
DIALOGS: dict[str, dict[str, tuple[str, str]]] = {
    "pt": {
        "enc_linghe_selos":     ("O magistrado assinou a ordem esta manhã, sem olhar para ninguém.", "Desça, feche o que puder e volte para assinar embaixo do nome dele."),
        "enc_linghe_vigilia":   ("As nove casas discutiram a noite toda e concordaram numa coisa só: alguém tem de sentar.", "Não pedimos fé. Pedimos horas."),
        "enc_linghe_escolta":   ("Três caravanas saíram. Nenhuma chegou inteira.", "A cidade come do que entra por aqueles portões. Ande com elas."),
        "enc_qianhe_minerio":   ("O rio abriu veio novo e o Templo não tem braços que cheguem.", "Desça. Volte carregado. Ninguém pergunta como."),
        "enc_qianhe_provas":    ("Os discípulos estão convencidos de que já sabem bater.", "Vá lá em baixo e desconvença-os."),
        "enc_qianhe_carga":     ("Metade das bestas de carga sumiu no gelo da estação passada.", "Traga-as de volta. Ou traga outras — o Templo não conta focinhos."),
        "enc_yanshan_pilulas":  ("O caldeirão comum está no fundo e a estação de febres começou.", "Encha-o. O Jardim não pergunta de onde veio a erva."),
        "enc_yanshan_remedio":  ("Não faltam pílulas nas prateleiras. Falta quem as dê a quem precisa.", "Ande pelos canteiros e use o que tem nas mãos."),
        "enc_yanshan_colheita": ("As Dez Mil abriram ontem e as feras chegaram primeiro.", "Vá buscar o que sobrou antes que não sobre."),
        # QoL 07/08 Item C — o d2 mandava BATER e o objetivo é `forge_artifact`.
        # Corrigido nos locales nessa sessão, mas este injector ficou com a
        # versão velha: re-corrê-lo reintroduzia o flavor que mentia. (Mesma
        # armadilha que o `inject_qol0807_i18n.py` já guardava para si próprio.)
        "enc_fenghuo_forja":    ("A fornalha mede a saúde do mundo. Este mês está fria.", "Pegue o martelo. Enquanto sair peça daquela bigorna, a fornalha vive."),
        "enc_fenghuo_tempera":  ("Aço que não bebeu não segura golpe nenhum.", "A Forja quer lâminas provadas. Vá prová-las."),
        "enc_fenghuo_arena":    ("A cidade inteira apostou e a casa está meio vazia.", "Não me importa quem ganha. Importa que tenha luta."),
        "enc_moyu_ruinas":      ("Há andares por baixo desta cidade que ninguém desenhou.", "Desça. Volte. Se voltar, traga."),
        "enc_moyu_ecos":        ("Alguma coisa lá embaixo está usando a voz da minha irmã.", "Minha irmã morreu há doze anos. Cale isso."),
        "enc_moyu_vigilia":     ("Aqui se medita de olhos abertos. Quem fecha, não abre mais.", "Fique sentado o bastante e aquilo acaba se mostrando."),
    },
    "en": {
        "enc_linghe_selos":     ("The magistrate signed the order this morning without looking at anyone.", "Go down, close what you can, and come back to sign under his name."),
        "enc_linghe_vigilia":   ("The nine houses argued all night and agreed on exactly one thing: someone has to sit.", "We are not asking for faith. We are asking for hours."),
        "enc_linghe_escolta":   ("Three caravans set out. Not one arrived whole.", "This city eats what comes through those gates. Walk with them."),
        "enc_qianhe_minerio":   ("The river opened a new vein and the Temple has no arms to spare.", "Go down. Come back loaded. Nobody asks how."),
        "enc_qianhe_provas":    ("The disciples are convinced they already know how to hit.", "Go down there and unconvince them."),
        "enc_qianhe_carga":     ("Half the beasts of burden vanished into last season's ice.", "Bring them back. Or bring others — the Temple does not count snouts."),
        "enc_yanshan_pilulas":  ("The common cauldron is scraping bottom and fever season has started.", "Fill it. The Garden does not ask where the herb came from."),
        "enc_yanshan_remedio":  ("There is no shortage of pills on the shelves. There is a shortage of people handing them out.", "Walk the beds and use what you are carrying."),
        "enc_yanshan_colheita": ("The Ten Thousand opened yesterday and the beasts got there first.", "Go fetch what is left before there is nothing left."),
        "enc_fenghuo_forja":    ("The furnace measures the health of the world. This month it is cold.", "Pick up the hammer. As long as pieces leave that anvil, the furnace lives."),
        "enc_fenghuo_tempera":  ("Steel that has not drunk holds no blow at all.", "The Forge wants proven blades. Go prove them."),
        "enc_fenghuo_arena":    ("The whole city has bet and the house is half empty.", "I do not care who wins. I care that there is a fight."),
        "enc_moyu_ruinas":      ("There are floors under this city that nobody has ever drawn.", "Go down. Come back. If you come back, bring something."),
        "enc_moyu_ecos":        ("Something down there is using my sister's voice.", "My sister died twelve years ago. Silence it."),
        "enc_moyu_vigilia":     ("Here we meditate with our eyes open. Those who close them do not open them again.", "Sit long enough and the thing shows itself."),
    },
    "es": {
        "enc_linghe_selos":     ("El magistrado firmó la orden esta mañana sin mirar a nadie.", "Baja, cierra lo que puedas y vuelve a firmar debajo de su nombre."),
        "enc_linghe_vigilia":   ("Las nueve casas discutieron toda la noche y coincidieron en una sola cosa: alguien tiene que sentarse.", "No pedimos fe. Pedimos horas."),
        "enc_linghe_escolta":   ("Salieron tres caravanas. Ninguna llegó entera.", "Esta ciudad come de lo que entra por esas puertas. Ve con ellas."),
        "enc_qianhe_minerio":   ("El río abrió una veta nueva y al Templo no le sobran brazos.", "Baja. Vuelve cargado. Nadie pregunta cómo."),
        "enc_qianhe_provas":    ("Los discípulos están convencidos de que ya saben golpear.", "Baja y desconvéncelos."),
        "enc_qianhe_carga":     ("La mitad de las bestias de carga se perdió en el hielo de la estación pasada.", "Tráelas de vuelta. O trae otras — el Templo no cuenta hocicos."),
        "enc_yanshan_pilulas":  ("El caldero común está en el fondo y empezó la temporada de fiebres.", "Llénalo. El Jardín no pregunta de dónde salió la hierba."),
        "enc_yanshan_remedio":  ("No faltan píldoras en los estantes. Falta quien se las dé a quien las necesita.", "Recorre los bancales y usa lo que llevas."),
        "enc_yanshan_colheita": ("Las Diez Mil abrieron ayer y las bestias llegaron primero.", "Ve a buscar lo que quedó antes de que no quede nada."),
        "enc_fenghuo_forja":    ("La fragua mide la salud del mundo. Este mes está fría.", "Toma el martillo. Mientras salgan piezas de ese yunque, la fragua vive."),
        "enc_fenghuo_tempera":  ("El acero que no ha bebido no aguanta ningún golpe.", "La Forja quiere hojas probadas. Ve a probarlas."),
        "enc_fenghuo_arena":    ("La ciudad entera apostó y la casa está medio vacía.", "No me importa quién gana. Me importa que haya pelea."),
        "enc_moyu_ruinas":      ("Hay pisos bajo esta ciudad que nadie ha dibujado.", "Baja. Vuelve. Si vuelves, trae algo."),
        "enc_moyu_ecos":        ("Algo ahí abajo está usando la voz de mi hermana.", "Mi hermana murió hace doce años. Cállalo."),
        "enc_moyu_vigilia":     ("Aquí se medita con los ojos abiertos. Quien los cierra, no los vuelve a abrir.", "Siéntate lo bastante y aquello acaba mostrándose."),
    },
}

for _lg, _m in DIALOGS.items():
    for _k, (_d1, _d2) in _m.items():
        CHAT[_lg][f"sty_{_k}_d1"] = _d1
        CHAT[_lg][f"sty_{_k}_d2"] = _d2


def _inject(path: str, add: dict[str, str], rewrite: dict[str, str] | None = None) -> tuple[int, int]:
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
    for lang, add in CHAT.items():
        n, total = _inject(os.path.join(ROOT, "locales", f"{lang}.json"),
                           add, REWRITE_CHAT.get(lang))
        print(f"chat  {lang}: {n:+d}  (total {total})")
    for lang, add in MINI.items():
        n, total = _inject(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"),
                           add, REWRITE_MINI.get(lang))
        print(f"mini  {lang}: {n:+d}  (total {total})")


if __name__ == "__main__":
    main()
