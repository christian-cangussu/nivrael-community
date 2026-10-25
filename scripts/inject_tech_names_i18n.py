# -*- coding: utf-8 -*-
"""名 OS NOMES DAS ARTES — as 76 tecnicas que ainda saiam em ingles (2026-09-08).

Idempotente: correr duas vezes nao duplica nada. Escreve so' em
`locales/{pt,en,es}.json` — o nome de uma peca de CATALOGO resolve-se no
SERVIDOR (`core.i18n.catalog_text`), porque a mesma linha e' impressa pelo chat,
pelo mini-app e pela vitrine. Traduzida no cliente, cada superficie precisaria da
sua copia e as tres divergiriam. Ver a nota longa no fim de `core/i18n.py`.

O QUE ESTA' AQUI, e porque sao 76 e nao 129
-------------------------------------------
Contado (nao presumido) a 2026-09-08:

    tecnicas no catalogo ................ 129
    ja' com tech_<id>_name/_desc x3 ......  53   (TEC-1/TEC-3/TEC-4/TEC-5)
    SEM ................................   76   (31 nos ids 1-45 + 45 nos 500-544)
    chaves orfas (key sem tecnica) ......    0

As 53 que ja' existiam foram escritas pelos lotes das Estantes e das Grutas e sao
a prova de que o mecanismo funciona em producao. Este script fecha o resto, e com
ele as 129 ficam a 100%.

⚠️ As 5 chaves `tech_*_name` que existiam na i18n do MINI-APP
(`tech_dragon_fist`, `tech_iron_body`, `tech_shadow_step`, `tech_thunder_step`,
`tech_void_slash`) sao CODIGO MORTO: **zero chamadores** em
`miniapp/components/*.js`, `index.html` e nos scripts de build — contados, nao
presumidos. Eram a localizacao "comecada e abandonada" que o prompt do lote
mencionava, e estavam abandonadas no sitio errado (no cliente). Ficam onde estao
— apaga-las mudaria a contagem de paridade do mini-app sem ninguem ganhar nada —
mas nao se acrescenta nem mais uma.

REGRAS DE ESCRITA (nome de peca e' CONTEUDO, nao string de UI)
-------------------------------------------------------------
* pt.json e' **portugues do BRASIL**.
* Os nomes das casas seguem o que o jogo ja' diz: `lineage_*` — "Nuvem Azul",
  "Pavilhao da Chama Eterna", "Ordem da Harmonia de Jade", "Montanha de Ferro",
  "Pico Gelado", "Mil Flores", "Vento Silencioso", "Sol Ardente", "Profundezas
  Abissais". Inventar um segundo nome para a mesma casa seria o defeito do
  "Core Formation"/"Nucleo" que a WEB-E apanhou.
* A **frase mecanica** do fim (+X% de dano, -Y% recebido, ignora Z% de armadura)
  mantem-se sempre: e' a unica informacao dura que o jogador tem no cartao.
* O `en` e' o texto do catalogo, VERBATIM. Nao e' redundante: quando o `en`
  existe como chave, o servidor devolve a mesma coisa por um caminho unico, e
  qualquer futura reescrita do catalogo nao muda o que o jogador ingles le'
  sem passar por aqui.
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

# (id, en_name, pt_name, es_name, en_desc, pt_desc, es_desc)
T = [
    # ── As artes de base (ids 1-30 + 45) ─────────────────────────────────────
    (1, "Thunder Step", "Passo do Trovão", "Paso del Trueno",
     "Lightning-fast steps that grant 30% evasion in the first round.",
     "Passos rápidos como o relâmpago: o corpo não está mais onde o golpe procurava. +30% de esquiva na primeira rodada.",
     "Pasos veloces como el relámpago: el cuerpo ya no está donde el golpe lo buscaba. +30% de evasión en la primera ronda."),
    (2, "Dragon Fist", "Punho do Dragão", "Puño del Dragón",
     "Dragon Fist — deals 2x damage on round 3.",
     "O punho se enrola como um dragão que espera, e desce quando o inimigo já se acostumou. Dano ×2 na terceira rodada.",
     "El puño se enrosca como un dragón que espera, y baja cuando el enemigo ya se acostumbró. Daño ×2 en la tercera ronda."),
    (3, "Iron Body", "Corpo de Ferro", "Cuerpo de Hierro",
     "Iron Body — reduces received damage by 50% in all rounds.",
     "A carne endurece até deixar de se distinguir do metal. -50% de dano recebido em todas as rodadas.",
     "La carne se endurece hasta dejar de distinguirse del metal. -50% de daño recibido en todas las rondas."),
    (4, "Shadow Step", "Passo das Sombras", "Paso de las Sombras",
     "Shadow Step — completely dodges an attack.",
     "Um passo para dentro da própria sombra, e o ataque atravessa o lugar onde você esteve. Esquiva completa de um ataque.",
     "Un paso hacia la propia sombra, y el ataque atraviesa el lugar donde estuviste. Esquiva completa de un ataque."),
    (5, "Void Slash", "Corte do Vazio", "Tajo del Vacío",
     "Void Slash — ignores 50% of enemy armor.",
     "A lâmina não corta a armadura: corta o espaço onde ela está. Ignora 50% da armadura inimiga.",
     "La hoja no corta la armadura: corta el espacio donde ella está. Ignora el 50% de la armadura enemiga."),
    (6, "Celestial Palm", "Palma Celestial", "Palma Celestial",
     "Celestial Palm — +50% damage all rounds.",
     "Uma palma aberta que carrega o peso do céu inteiro atrás dela. +50% de dano em todas as rodadas.",
     "Una palma abierta que carga el peso del cielo entero detrás. +50% de daño en todas las rondas."),
    (7, "Frost Shield", "Escudo de Geada", "Escudo de Escarcha",
     "Frost Shield — reduces damage taken by 35% all rounds.",
     "O ar em volta congela antes de a lâmina chegar, e a lâmina chega mais devagar. -35% de dano recebido em todas as rodadas.",
     "El aire alrededor se congela antes de que la hoja llegue, y la hoja llega más lenta. -35% de daño recibido en todas las rondas."),
    (8, "Wind Walk", "Caminhar do Vento", "Andar del Viento",
     "Wind Walk — +20% evasion all rounds.",
     "Os pés deixam de pesar; o vento passa a decidir onde o corpo fica. +20% de esquiva em todas as rodadas.",
     "Los pies dejan de pesar; el viento pasa a decidir dónde queda el cuerpo. +20% de evasión en todas las rondas."),
    (9, "Divine Finger", "Dedo Divino", "Dedo Divino",
     "Divine Finger — ignores 30% armor all rounds. Requires Dao of Speed insight.",
     "Um só dedo, apontado no instante exato: a armadura não tem tempo de existir. Ignora 30% da armadura em todas as rodadas. Exige vislumbre do Dao da Velocidade.",
     "Un solo dedo, apuntado en el instante exacto: la armadura no tiene tiempo de existir. Ignora el 30% de la armadura en todas las rondas. Exige vislumbre del Dao de la Velocidad."),
    (10, "Phoenix Strike", "Golpe da Fênix", "Golpe del Fénix",
     "Phoenix Strike — 2.5x damage on round 5. Requires Dao of Destruction mastery.",
     "A fênix não ataca cedo. Ela espera o combate cansar e então queima tudo de uma vez. Dano ×2,5 na quinta rodada. Exige maestria no Dao da Destruição.",
     "El fénix no ataca temprano. Espera a que el combate se canse y entonces lo quema todo de una vez. Daño ×2,5 en la quinta ronda. Exige maestría en el Dao de la Destrucción."),
    (11, "Heavenly Root Technique", "Técnica da Raiz Celestial", "Técnica de la Raíz Celestial",
     "Heavenly Root Technique — 3x damage on round 1. Heavenly Spirit Root ONLY.",
     "O que nasce com raiz celestial não aprende esta arte: se lembra dela. Dano ×3 na primeira rodada. SÓ para Raiz Espiritual Celestial.",
     "Quien nace con raíz celestial no aprende este arte: lo recuerda. Daño ×3 en la primera ronda. SOLO para Raíz Espiritual Celestial."),
    (12, "Soul Devourer", "Devorador de Almas", "Devorador de Almas",
     "Soul Devourer — +80% damage all rounds. Requires deep Dao of Time comprehension.",
     "Não morde a carne — morde os anos que o inimigo ainda não viveu. +80% de dano em todas as rodadas. Exige compreensão profunda do Dao do Tempo.",
     "No muerde la carne — muerde los años que el enemigo aún no vivió. +80% de daño en todas las rondas. Exige comprensión profunda del Dao del Tiempo."),
    (13, "Absolute Defense", "Defesa Absoluta", "Defensa Absoluta",
     "Absolute Defense — reduces damage by 70% on round 1. Requires Dao of Life insight.",
     "Enquanto houver vida para defender, a defesa não tem limite. -70% de dano na primeira rodada. Exige vislumbre do Dao da Vida.",
     "Mientras haya vida que defender, la defensa no tiene límite. -70% de daño en la primera ronda. Exige vislumbre del Dao de la Vida."),
    (14, "Storm Fist", "Punho da Tempestade", "Puño de la Tormenta",
     "Storm Fist — +70% damage all rounds. Speed turns to destruction.",
     "Velocidade que deixou de ser fuga e virou ruína. +70% de dano em todas as rodadas.",
     "Velocidad que dejó de ser huida y se volvió ruina. +70% de daño en todas las rondas."),
    (15, "Heaven Rend", "Rasgar o Céu", "Desgarrar el Cielo",
     "Heaven Rend — ignores 65% of enemy armor. Time unmakes all defenses.",
     "O tempo desfaz toda defesa; esta arte só o apressa. Ignora 65% da armadura inimiga.",
     "El tiempo deshace toda defensa; este arte solo la apresura. Ignora el 65% de la armadura enemiga."),
    (16, "Undying Fortress", "Fortaleza Imortal", "Fortaleza Imperecedera",
     "Undying Fortress — reduces damage by 80% on round 1. Endures through the Dao of Life.",
     "Uma muralha que não se defende do golpe: sobrevive-lhe. -80% de dano na primeira rodada. Aguenta pelo Dao da Vida.",
     "Una muralla que no se defiende del golpe: le sobrevive. -80% de daño en la primera ronda. Aguanta por el Dao de la Vida."),
    (17, "Eternal Strike", "Golpe Eterno", "Golpe Eterno",
     "Eternal Strike — 3.5x damage on round 1. Only the Eternal Dao grants such power.",
     "Um golpe que já foi dado, está sendo dado e será dado — tudo no mesmo instante. Dano ×3,5 na primeira rodada. Só o Dao Eterno concede tal poder.",
     "Un golpe que ya fue dado, está siendo dado y será dado — todo en el mismo instante. Daño ×3,5 en la primera ronda. Solo el Dao Eterno concede tal poder."),
    (18, "Boundless Evasion", "Esquiva Sem Limites", "Evasión Sin Límites",
     "Boundless Evasion — 60% evasion all rounds. Transcend the limits of form.",
     "Quem não tem forma fixa não tem onde ser atingido. +60% de esquiva em todas as rodadas.",
     "Quien no tiene forma fija no tiene dónde ser alcanzado. +60% de evasión en todas las rondas."),
    (19, "Radiant Guard", "Guarda Radiante", "Guardia Radiante",
     "Celestial breathing wraps the body in holy light, reducing all damage by 15%.",
     "A respiração celestial envolve o corpo em luz sagrada. -15% de todo o dano recebido.",
     "La respiración celestial envuelve el cuerpo en luz sagrada. -15% de todo el daño recibido."),
    (20, "Heaven's Mandate", "Mandato do Céu", "Mandato del Cielo",
     "The Heavens shield the righteous. -30% damage taken in all rounds.",
     "Os Céus protegem quem anda direito — e o Céu se lembra de quem não anda. -30% de dano recebido em todas as rodadas.",
     "Los Cielos protegen a quien anda derecho — y el Cielo recuerda a quien no. -30% de daño recibido en todas las rondas."),
    (21, "Divine Judgment", "Julgamento Divino", "Juicio Divino",
     "Call down Heaven's wrath — 2.8x damage on round 1. The Celestial Court's final verdict.",
     "Chama a ira dos Céus: a sentença da Corte Celestial não se apela. Dano ×2,8 na primeira rodada.",
     "Llama la ira de los Cielos: la sentencia de la Corte Celestial no se apela. Daño ×2,8 en la primera ronda."),
    (22, "Blood Frenzy", "Frenesi de Sangue", "Frenesí de Sangre",
     "Demonic qi fuels a blood frenzy — +20% damage in all rounds.",
     "O qi demoníaco alimenta um frenesi de sangue que não distingue dor de força. +20% de dano em todas as rodadas.",
     "El qi demoníaco alimenta un frenesí de sangre que no distingue dolor de fuerza. +20% de daño en todas las rondas."),
    (23, "Soul Rend", "Rasgar a Alma", "Desgarrar el Alma",
     "Demonic claws tear through defenses — ignores 40% of enemy armor in all rounds.",
     "Garras demoníacas passam pela armadura porque não é nela que estão interessadas. Ignora 40% da armadura inimiga em todas as rodadas.",
     "Garras demoníacas pasan por la armadura porque no es en ella donde están interesadas. Ignora el 40% de la armadura enemiga en todas las rondas."),
    (24, "Abyssal Annihilation", "Aniquilação Abissal", "Aniquilación Abisal",
     "Unleash the Abyss — 3.0x damage on round 1. Nothing survives the Demonic annihilation.",
     "Solta o Abismo pela primeira e última vez: nada do que ele toca continua a existir. Dano ×3 na primeira rodada.",
     "Suelta el Abismo por primera y última vez: nada de lo que toca sigue existiendo. Daño ×3 en la primera ronda."),
    (25, "Tranquil Mind", "Mente Tranquila", "Mente Serena",
     "A serene breathing method that calms the mind and accelerates Cultivation Base gains by 20% during meditation.",
     "Um método de respiração que acalma a mente e deixa o qi entrar sem ser puxado. +20% de ganho de Base de Cultivo durante a meditação.",
     "Un método de respiración que calma la mente y deja entrar el qi sin tirar de él. +20% de ganancia de Base de Cultivo durante la meditación."),
    (26, "Soul Gathering", "Recolhimento da Alma", "Recogimiento del Alma",
     "Draws ambient spiritual energy inward, boosting Qi regeneration by 30% while meditating.",
     "Puxa para dentro a energia espiritual que corre solta no ar. +30% de regeneração de Qi enquanto medita.",
     "Atrae hacia dentro la energía espiritual que corre suelta en el aire. +30% de regeneración de Qi mientras medita."),
    (27, "Body Restoration", "Restauração do Corpo", "Restauración del Cuerpo",
     "Channels Qi through wounded meridians during meditation, increasing HP regeneration by 50%.",
     "Conduz o Qi pelos meridianos feridos, devagar, até eles voltarem a servir. +50% de regeneração de HP durante a meditação.",
     "Conduce el Qi por los meridianos heridos, despacio, hasta que vuelvan a servir. +50% de regeneración de HP durante la meditación."),
    (28, "Iron Will", "Vontade de Ferro", "Voluntad de Hierro",
     "Tempers the soul through unwavering resolve. Permanently increases Soul Strength by 10%.",
     "Tempera a alma na mesma forja onde se tempera o ferro: repetição e nenhuma cedência. +10% de Força da Alma, permanente.",
     "Templa el alma en la misma forja donde se templa el hierro: repetición y ninguna cesión. +10% de Fuerza del Alma, permanente."),
    (29, "Eagle Eye", "Olho de Águia", "Ojo de Águila",
     "Sharpens spiritual sense beyond mortal limits. Permanently increases Perception by 10%.",
     "Afia o sentido espiritual para além do que um mortal deveria alcançar. +10% de Percepção, permanente.",
     "Afila el sentido espiritual más allá de lo que un mortal debería alcanzar. +10% de Percepción, permanente."),
    (30, "Fortune's Favor", "Favor da Fortuna", "Favor de la Fortuna",
     "Aligns one's Dao with the flow of fortune. Permanently increases Luck by 10%.",
     "Alinha o próprio Dao com a corrente da fortuna, e deixa de remar contra ela. +10% de Sorte, permanente.",
     "Alinea el propio Dao con la corriente de la fortuna, y deja de remar contra ella. +10% de Suerte, permanente."),
    (45, "Beggar's Palm", "Palma do Mendigo", "Palma del Mendigo",
     "The Old Beggar's only lesson — one honest palm, thrown with the whole body behind it. +15% damage in all rounds.",
     "A única lição do Velho Mendigo: uma palma honesta, com o corpo inteiro atrás dela. +15% de dano em todas as rodadas.",
     "La única lección del Viejo Mendigo: una palma honesta, con el cuerpo entero detrás. +15% de daño en todas las rondas."),

    # ── Nuvem Azul (500-504) ─────────────────────────────────────────────────
    (500, "Cloud Step", "Passo de Nuvem", "Paso de Nube",
     "The first art of the Azure Cloud — feet that never quite touch the earth. +12% evasion.",
     "A primeira arte da Nuvem Azul — pés que nunca chegam mesmo a tocar a terra. +12% de esquiva.",
     "El primer arte de la Nube Azul — pies que nunca llegan del todo a tocar la tierra. +12% de evasión."),
    (501, "Azure Sword Form", "Forma da Espada da Nuvem Azul", "Forma de la Espada de la Nube Azul",
     "The sword rides the wind. +18% damage in all rounds.",
     "A espada monta o vento em vez de o cortar. +18% de dano em todas as rodadas.",
     "La espada monta el viento en vez de cortarlo. +18% de daño en todas las rondas."),
    (502, "Cloud Dragon Slash", "Corte do Dragão de Nuvem", "Tajo del Dragón de Nube",
     "A dragon coils within the clouds and descends. +35% damage in all rounds.",
     "Um dragão se enrola dentro das nuvens e desce quando ninguém olha para cima. +35% de dano em todas as rodadas.",
     "Un dragón se enrosca dentro de las nubes y desciende cuando nadie mira hacia arriba. +35% de daño en todas las rondas."),
    (503, "Heaven Cloud Severance", "Cisão da Nuvem Celeste", "Escisión de la Nube Celeste",
     "The Elder's signature — a cut that the heavens cannot guard against. Ignores 40% armor.",
     "A assinatura do Ancião — um corte contra o qual os céus não sabem guardar-se. Ignora 40% da armadura.",
     "La firma del Anciano — un corte contra el que los cielos no saben guardarse. Ignora el 40% de la armadura."),
    (504, "Yún Step Reborn", "Passo Yún Renascido", "Paso Yún Renacido",
     "Founder Bái's lost art, returned to the worthy Heir. +35% evasion in all rounds.",
     "A arte perdida do Fundador Bái, devolvida ao Herdeiro que a merece. +35% de esquiva em todas as rodadas.",
     "El arte perdido del Fundador Bái, devuelto al Heredero que lo merece. +35% de evasión en todas las rondas."),

    # ── Pavilhão da Chama Eterna (505-509) ───────────────────────────────────
    (505, "Ember Palm", "Palma de Brasa", "Palma de Brasa",
     "A palm kindled with the pavilion's eternal coal. +15% damage.",
     "Uma palma acesa no carvão eterno do pavilhão, que nunca ninguém deixou apagar. +15% de dano.",
     "Una palma encendida en el carbón eterno del pabellón, que nadie dejó apagar jamás. +15% de daño."),
    (506, "Soul Fire", "Fogo da Alma", "Fuego del Alma",
     "Flame that burns the spirit, not the flesh. +22% damage.",
     "Chama que não queima a carne — queima o que a carne carrega. +22% de dano.",
     "Llama que no quema la carne — quema lo que la carne carga. +22% de daño."),
    (507, "Pill Emperor's Touch", "Toque do Imperador das Pílulas", "Toque del Emperador de las Píldoras",
     "The alchemist's body becomes its own cauldron, tempered against harm. -25% damage taken.",
     "O corpo do alquimista vira o próprio caldeirão, temperado por dentro contra o que vem de fora. -25% de dano recebido.",
     "El cuerpo del alquimista se vuelve su propio caldero, templado por dentro contra lo que viene de fuera. -25% de daño recibido."),
    (508, "Phoenix Flame Body", "Corpo de Chama da Fênix", "Cuerpo de Llama del Fénix",
     "Wreathed in undying phoenix fire. +45% damage in all rounds.",
     "Envolto no fogo da fênix, que é o único fogo que não acaba. +45% de dano em todas as rodadas.",
     "Envuelto en el fuego del fénix, que es el único fuego que no se acaba. +45% de daño en todas las rondas."),
    (509, "Nirvana Rebirth Flame", "Chama do Renascimento em Nirvana", "Llama del Renacer en Nirvana",
     "The Heir burns and is reborn, again and again. -40% damage taken.",
     "O Herdeiro queima e renasce, e queima outra vez, sem que a conta feche. -40% de dano recebido.",
     "El Heredero arde y renace, y arde otra vez, sin que la cuenta cierre. -40% de daño recibido."),

    # ── Ordem da Harmonia de Jade (510-514) ──────────────────────────────────
    (510, "Jade Shield", "Escudo de Jade", "Escudo de Jade",
     "Harmony begins with stillness. -15% damage taken.",
     "A harmonia começa na quietude, e a quietude é a primeira armadura. -15% de dano recebido.",
     "La armonía comienza en la quietud, y la quietud es la primera armadura. -15% de daño recibido."),
    (511, "Mercy Pulse", "Pulso de Misericórdia", "Pulso de Misericordia",
     "A pulse of mercy that softens every blow. -22% damage taken.",
     "Um pulso de misericórdia que amolece todo golpe antes de ele chegar. -22% de dano recebido.",
     "Un pulso de misericordia que ablanda todo golpe antes de que llegue. -22% de daño recibido."),
    (512, "Jade Formation", "Formação de Jade", "Formación de Jade",
     "Nine jade pillars rise around the cultivator. -32% damage taken.",
     "Nove pilares de jade sobem em volta do cultivador, e o mundo lá fora fica do lado de fora. -32% de dano recebido.",
     "Nueve pilares de jade suben alrededor del cultivador, y el mundo de fuera se queda fuera. -32% de daño recibido."),
    (513, "Harmony of Ten Thousand", "Harmonia dos Dez Mil", "Armonía de los Diez Mil",
     "All things in balance; nothing may break it. -42% damage taken.",
     "Todas as coisas em equilíbrio; nada tem força para quebrá-lo. -42% de dano recebido.",
     "Todas las cosas en equilibrio; nada tiene fuerza para romperlo. -42% de daño recibido."),
    (514, "Lotus of Rebirth", "Lótus do Renascimento", "Loto del Renacer",
     "The Heir blooms untouched at the heart of the storm. -50% damage taken.",
     "O Herdeiro floresce intocado no meio da tempestade, como se a tempestade fosse com outro. -50% de dano recebido.",
     "El Heredero florece intacto en medio de la tormenta, como si la tormenta fuera con otro. -50% de daño recibido."),

    # ── Montanha de Ferro (515-519) ──────────────────────────────────────────
    (515, "Iron Fist Basics", "Fundamentos do Punho de Ferro", "Fundamentos del Puño de Hierro",
     "The first lesson of the Mountain — strike like falling stone. +15% damage.",
     "A primeira lição da Montanha — golpear como pedra que cai, sem hesitar no caminho. +15% de dano.",
     "La primera lección de la Montaña — golpear como piedra que cae, sin dudar en el camino. +15% de daño."),
    (516, "Mountain Stance", "Postura da Montanha", "Postura de la Montaña",
     "Root yourself; the mountain does not move. -25% damage taken.",
     "Crie raiz: a montanha não se desvia de nada. -25% de dano recebido.",
     "Echa raíz: la montaña no se aparta de nada. -25% de daño recibido."),
    (517, "Avalanche Fist", "Punho da Avalanche", "Puño de la Avalancha",
     "One blow, and the whole slope comes down. +40% damage.",
     "Um golpe só, e a encosta inteira vem atrás dele. +40% de dano.",
     "Un solo golpe, y la ladera entera viene detrás. +40% de daño."),
    (518, "Mountain Heart Dao", "Dao do Coração da Montanha", "Dao del Corazón de la Montaña",
     "The Elder's heart is the mountain's heart — unbreakable. -40% damage taken.",
     "O coração do Ancião é o coração da montanha: não se parte porque não cede. -40% de dano recebido.",
     "El corazón del Anciano es el corazón de la montaña: no se rompe porque no cede. -40% de daño recibido."),
    (519, "Nine Mountains Body", "Corpo das Nove Montanhas", "Cuerpo de las Nueve Montañas",
     "The Heir carries nine mountains in each fist. +60% damage in all rounds.",
     "O Herdeiro carrega nove montanhas em cada punho, e não se queixa do peso. +60% de dano em todas as rodadas.",
     "El Heredero carga nueve montañas en cada puño, y no se queja del peso. +60% de daño en todas las rondas."),

    # ── Pico Gelado (520-524) ────────────────────────────────────────────────
    (520, "Frost Guard", "Guarda de Geada", "Guardia de Escarcha",
     "A thin rime of frost turns the first blows aside. -18% damage taken.",
     "Uma fina camada de geada desvia os primeiros golpes sem os enfrentar. -18% de dano recebido.",
     "Una fina capa de escarcha desvía los primeros golpes sin enfrentarlos. -18% de daño recibido."),
    (521, "Glacial Shell", "Carapaça Glacial", "Caparazón Glacial",
     "Ice armours the meridians. -28% damage taken.",
     "O gelo blinda os meridianos por dentro, onde nenhuma armadura chega. -28% de dano recebido.",
     "El hielo blinda los meridianos por dentro, donde ninguna armadura llega. -28% de daño recibido."),
    (522, "Winter's Silence", "Silêncio do Inverno", "Silencio del Invierno",
     "Move as the snowfall — unheard, unseen. +20% evasion.",
     "Mova-se como a neve que cai — sem som, sem sombra, sem aviso. +20% de esquiva.",
     "Muévete como la nieve que cae — sin sonido, sin sombra, sin aviso. +20% de evasión."),
    (523, "Frozen Heart Dao", "Dao do Coração Congelado", "Dao del Corazón Congelado",
     "A heart of glacier feels neither pain nor fear. -40% damage taken.",
     "Um coração de geleira não sente dor nem medo — e também não sente mais nada. -40% de dano recebido.",
     "Un corazón de glaciar no siente dolor ni miedo — y tampoco siente ya nada más. -40% de daño recibido."),
    (524, "Eternal Glacier Body", "Corpo da Geleira Eterna", "Cuerpo del Glaciar Eterno",
     "The Heir's flesh is the unmelting peak itself. -50% damage taken.",
     "A carne do Herdeiro é o próprio cume que nunca degela. -50% de dano recebido.",
     "La carne del Heredero es la propia cima que nunca se deshiela. -50% de daño recibido."),

    # ── Mil Flores (525-529) ─────────────────────────────────────────────────
    (525, "Spirit Garden", "Jardim Espiritual", "Jardín Espiritual",
     "A garden grows within, soft and resilient. -15% damage taken.",
     "Um jardim cresce por dentro: macio, e por isso difícil de quebrar. -15% de dano recebido.",
     "Un jardín crece por dentro: blando, y por eso difícil de romper. -15% de daño recibido."),
    (526, "Flower Communion", "Comunhão das Flores", "Comunión de las Flores",
     "Sway with the petals; let the blow pass through. +18% evasion.",
     "Balance-se com as pétalas e deixe o golpe passar por onde você não está. +18% de esquiva.",
     "Méceté con los pétalos y deja que el golpe pase por donde no estás. +18% de evasión."),
    (527, "Hundred Herb Body", "Corpo das Cem Ervas", "Cuerpo de las Cien Hierbas",
     "A body steeped in a hundred spirit herbs endures much. -30% damage taken.",
     "Um corpo curtido em cem ervas espirituais aguenta o que outro não aguentaria. -30% de dano recebido.",
     "Un cuerpo curtido en cien hierbas espirituales aguanta lo que otro no aguantaría. -30% de daño recibido."),
    (528, "Blooming Dao Heart", "Coração Dao em Flor", "Corazón Dao en Flor",
     "The Elder's Dao blossoms, and the world bends around it. +28% evasion.",
     "O Dao da Anciã floresce, e o mundo se curva ao redor dela para não tocá-la. +28% de esquiva.",
     "El Dao de la Anciana florece, y el mundo se curva a su alrededor para no tocarla. +28% de evasión."),
    (529, "Spring of Ten Thousand Blooms", "Primavera das Dez Mil Flores", "Primavera de las Diez Mil Flores",
     "Where the Heir walks, ten thousand flowers shield the way. -45% damage taken.",
     "Por onde o Herdeiro passa, dez mil flores fecham o caminho atrás dele. -45% de dano recebido.",
     "Por donde pasa el Heredero, diez mil flores cierran el camino tras él. -45% de daño recibido."),

    # ── Vento Silencioso (530-534) ───────────────────────────────────────────
    (530, "Wind Walk Art", "Arte do Caminhar do Vento", "Arte del Andar del Viento",
     "The palace's first breath — walk without sound. +18% evasion.",
     "O primeiro sopro do palácio — andar sem fazer som nenhum. +18% de esquiva.",
     "El primer soplo del palacio — andar sin hacer ruido alguno. +18% de evasión."),
    (531, "Silent Shadow Step", "Passo da Sombra Silenciosa", "Paso de la Sombra Silente",
     "Become the shadow between heartbeats. +25% evasion.",
     "Torne-se a sombra que cabe entre duas batidas do coração. +25% de esquiva.",
     "Vuélvete la sombra que cabe entre dos latidos del corazón. +25% de evasión."),
    (532, "Last Breath", "Último Suspiro", "Último Suspiro",
     "Strike on the enemy's exhale — 2x damage on round 3.",
     "Golpeie no momento em que o inimigo solta o ar e não pode recuar. Dano ×2 na terceira rodada.",
     "Golpea en el momento en que el enemigo suelta el aire y no puede retroceder. Daño ×2 en la tercera ronda."),
    (533, "Windless Assassination", "Assassinato Sem Vento", "Asesinato Sin Viento",
     "A blade that finds the gap no armour covers. Ignores 45% armour.",
     "Uma lâmina que encontra a fresta que nenhuma armadura cobre. Ignora 45% da armadura.",
     "Una hoja que encuentra la rendija que ninguna armadura cubre. Ignora el 45% de la armadura."),
    (534, "Death Without Sound", "Morte Sem Som", "Muerte Sin Sonido",
     "The Heir's killing art — for one breath, no attack can touch them (full dodge, round 1).",
     "A arte matadora do Herdeiro — por um sopro inteiro, nenhum ataque o alcança. Esquiva completa na primeira rodada.",
     "El arte asesino del Heredero — por un soplo entero, ningún ataque lo alcanza. Esquiva completa en la primera ronda."),

    # ── Sol Ardente (535-539) ────────────────────────────────────────────────
    (535, "Sun Strike", "Golpe do Sol", "Golpe del Sol",
     "A fist that carries the morning sun. +16% damage.",
     "Um punho que carrega o sol da manhã consigo. +16% de dano.",
     "Un puño que lleva consigo el sol de la mañana. +16% de daño."),
    (536, "Solar Flare Fist", "Punho da Explosão Solar", "Puño de la Llamarada Solar",
     "Flare bright enough to blind, hot enough to burn. +24% damage.",
     "Um clarão brilhante o bastante para cegar e quente o bastante para queimar. +24% de dano.",
     "Un fogonazo brillante como para cegar y caliente como para quemar. +24% de daño."),
    (537, "Forge of Eternity", "Forja da Eternidade", "Forja de la Eternidad",
     "The sect's forge-fire melts any guard. Ignores 30% armour.",
     "O fogo de forja da seita derrete qualquer guarda antes de a atravessar. Ignora 30% da armadura.",
     "El fuego de forja de la secta derrite cualquier guardia antes de atravesarla. Ignora el 30% de la armadura."),
    (538, "Sunfire Body", "Corpo de Fogo Solar", "Cuerpo de Fuego Solar",
     "The Elder's body is a small sun. +48% damage in all rounds.",
     "O corpo do Ancião é um pequeno sol, e ninguém se aproxima de um sol. +48% de dano em todas as rodadas.",
     "El cuerpo del Anciano es un pequeño sol, y nadie se acerca a un sol. +48% de daño en todas las rondas."),
    (539, "Eternal Sun Dao", "Dao do Sol Eterno", "Dao del Sol Eterno",
     "The Heir's blaze unmakes every defence. Ignores 50% armour.",
     "O incêndio do Herdeiro desfaz toda defesa em vez de a vencer. Ignora 50% da armadura.",
     "El incendio del Heredero deshace toda defensa en vez de vencerla. Ignora el 50% de la armadura."),

    # ── Profundezas Abissais (540-544) ───────────────────────────────────────
    (540, "Demon Mark", "Marca do Demônio", "Marca del Demonio",
     "A brand of the Abyss that hungers. +18% damage.",
     "Uma marca do Abismo, e marcas do Abismo têm fome. +18% de dano.",
     "Una marca del Abismo, y las marcas del Abismo tienen hambre. +18% de daño."),
    (541, "Soul Eater", "Comedor de Almas", "Comedor de Almas",
     "Devour the soul beneath the armour. Ignores 25% armour.",
     "Devora a alma que está debaixo da armadura, e ignora a armadura no caminho. Ignora 25% da armadura.",
     "Devora el alma que está bajo la armadura, e ignora la armadura por el camino. Ignora el 25% de la armadura."),
    (542, "Abyssal Grasp", "Garra Abissal", "Garra Abisal",
     "A hand from the deep that no defence escapes. Ignores 38% armour.",
     "Uma mão vinda do fundo, da qual defesa nenhuma escapa. Ignora 38% da armadura.",
     "Una mano venida del fondo, de la que ninguna defensa escapa. Ignora el 38% de la armadura."),
    (543, "Demonic Devourer", "Devorador Demoníaco", "Devorador Demoníaco",
     "The Elder feasts on the enemy's strength. +55% damage in all rounds.",
     "O Ancião se banqueteia com a força do inimigo enquanto ela ainda é dele. +55% de dano em todas as rodadas.",
     "El Anciano se banquetea con la fuerza del enemigo mientras aún es suya. +55% de daño en todas las rondas."),
    (544, "Sovereign of the Abyss", "Soberano do Abismo", "Soberano del Abismo",
     "The Heir of the Abyss — all that lives is prey. +70% damage in all rounds.",
     "O Herdeiro do Abismo — tudo o que vive é caça. +70% de dano em todas as rodadas.",
     "El Heredero del Abismo — todo lo que vive es presa. +70% de daño en todas las rondas."),
]


def main() -> int:
    # ⚠️ Guarda: um id que nao existe no catalogo seria uma chave orfa — texto
    # pago que nunca chega a nenhuma tela. Um id JA' traduzido seria uma
    # sobreposicao silenciosa de trabalho anterior.
    import sys
    sys.path.insert(0, ROOT)
    from database.seeds.combat_seeds import TECHNIQUES
    catalog = {int(x["id"]) for x in TECHNIQUES}
    ids = [row[0] for row in T]
    unknown = sorted(set(ids) - catalog)
    if unknown:
        print(f"  !! ids que nao existem no catalogo: {unknown}")
        return 1
    if len(ids) != len(set(ids)):
        print("  !! ids repetidos na tabela")
        return 1

    added_total = 0
    for lg in LANGS:
        path = os.path.join(ROOT, "locales", f"{lg}.json")
        d = json.load(io.open(path, encoding="utf-8"))
        added = 0
        for row in T:
            tid = row[0]
            # ⚠️ A tupla e' (id, EN, PT, ES, en_desc, pt_desc, es_desc) e `LANGS`
            # e' (pt, en, es): as duas ordens NAO coincidem. Mapear pelo nome da
            # lingua, nunca pelo indice do loop — trocar pt com en aqui seria um
            # erro invisivel (as tres ficheiros ficariam com o mesmo numero de
            # keys e a paridade passaria verde).
            idx = {"en": 0, "pt": 1, "es": 2}[lg]
            name = row[1 + idx]
            desc = row[4 + idx]
            for suffix, val in (("name", name), ("desc", desc)):
                k = f"tech_{tid}_{suffix}"
                if k not in d:
                    d[k] = val
                    added += 1
        d = dict(sorted(d.items()))
        io.open(path, "w", encoding="utf-8", newline="\n").write(
            json.dumps(d, ensure_ascii=False, indent=4) + "\n")
        added_total += added
        print(f"  {lg}: +{added} keys -> {len(d)} total")
    print(f"total adicionadas: {added_total}  ({len(T)} artes x 2 campos x 3 linguas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
