"""TEC-3 — As Duas Estantes Seladas: injetor de i18n (chat + mini-app).

Roda:  python -X utf8 scripts/inject_tec3_i18n.py

SO-ADICOES: `_apply` so escreve uma key que AINDA NAO existe (`if k not in
data`). Re-rodar e idempotente e nunca clobbera uma string viva. O unico jeito
de reescrever uma key deste mesmo lote e pelos dicts *_OVERRIDES explicitos —
que NUNCA tocam keys de outras sprints.

Conteudo (as 18 artes novas) vai SO para os locales do chat, como
`tech_<id>_name` / `tech_<id>_desc`: o servidor resolve com `t_optional` e o
mini-app recebe a string ja localizada no payload (padrao TEC-1 / q_<id>).

Chrome do chat = prefixo `sel_` (+ os dois `lib_shelf_4/5` que o engine deriva
por f-string, senao o jogador le a KEY CRUA). Chrome do mini = `sel_mini_`,
mais a auto-documentacao do painel (`feature_estantes_seladas` + `_desc`).

PT-BR estrito: voce/seu, grafia BR, zero sotaque europeu (o verificador
`_verify_tec3_i18n.py` carrega o bloco de 14 idiomas EU-PT do QoL-relatos).
`newline="\\n"` na escrita e load-bearing: sem isso o Windows converte o
ficheiro inteiro para CRLF e o diff vira o ficheiro inteiro.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

# ── As 18 artes (580-588 Anciao 传功 · 590-598 Oculta 秘传) ────────────────────
# A desc SEMPRE fecha com o numero MECANICO exato do seed (o teste isolado
# confere `int(round(effect_value*100))` dentro da desc PT — anti-drift).
_ARTS_PT = {
    580: ("Decreto da Nuvem que Corta o Céu",
          "O que o Ancião assina com a espada, o Céu referenda: um único decreto traçado no ar, e a guarda que existia simplesmente deixa de fazer parte do mundo. Ignora 44% da armadura do inimigo."),
    590: ("A Nuvem Não Escrita de Bái",
          "O fundador Bái nunca pôs esta forma no papel — dizia que uma nuvem que se pode desenhar já é uma nuvem que se pode cortar. Só ao Herdeiro ela é mostrada, uma vez, e ele tem de lembrar. +66% de dano em todas as rodadas."),
    581: ("Chama do Nono Refino",
          "Oito refinos fazem uma pílula; o nono faz uma arma. O Ancião alimenta o próprio dao no caldeirão e golpeia com o que sai de lá. +48% de dano em todas as rodadas."),
    591: ("Cinza do Primeiro Caldeirão",
          "Uma pitada de cinza do caldeirão que fundou a casa, guardada por mil anos. Vestida sobre a pele, ela lembra de cada fogo que já sobreviveu. Reduz o dano recebido em 52%."),
    582: ("Acordo de Jade Inquebrado",
          "O Ancião não recusa o golpe — ele concorda com o golpe, e um acordo não se quebra pela força. Reduz o dano recebido em 42%."),
    592: ("A Misericórdia que Sobrevive à Espada",
          "O segredo mais fundo da casa não é uma técnica, é um voto: nunca ferir o que ainda pode ser poupado, e nada que golpeie você encontrará onde pousar. Reduz o dano recebido em 55%."),
    583: ("Queda de Dez Mil Jin",
          "O Ancião não arremessa o punho. Ele solta o punho, e a montanha faz o resto. +48% de dano em todas as rodadas."),
    593: ("O Cume Responde Uma Só Vez",
          "O Herdeiro aprende o nome que o fundador gravou na pedra do topo. Diga esse nome e, por uma respiração, você não está sobre a montanha — você é a montanha. +68% de dano em todas as rodadas."),
    584: ("Inverno Sem Degelo",
          "O frio do Ancião já não espera pela estação: ele simplesmente decide que a primavera não vai chegar aqui. Reduz o dano recebido em 43%."),
    594: ("A Geleira que Lembra do Mar",
          "Antes de congelar, o pico era água — e a água já esteve dentro de tudo. O golpe do Herdeiro encontra a fresta que conheceu mil anos atrás. Ignora 54% da armadura do inimigo."),
    585: ("Jardim das Dez Mil Voltas",
          "O Ancião caminha por uma trilha que só o jardim conhece, e o jardim se reorganiza com gentileza atrás dele. +30% de evasão em todas as rodadas."),
    595: ("A Semente Guardada de Toda Colheita",
          "Cada geração separou uma semente e nunca a plantou. O Herdeiro a carrega, e enquanto ela não for plantada nada neste mundo terminou com você. Reduz o dano recebido em 52%."),
    586: ("O Fio que Chega Antes do Som",
          "O Ancião chega meia respiração antes do barulho de chegar; lâminas mandadas para onde ele está insistem em achar onde ele estava. +31% de evasão em todas as rodadas."),
    596: ("Nome Apagado do Vento",
          "O Herdeiro entrega o próprio nome ao vento da montanha. O que não tem nome não tem forma, e o que não tem forma nunca esteve do lado de fora da armadura. Ignora 56% da armadura do inimigo."),
    587: ("Bigorna do Meio-Dia Parado",
          "O Ancião segura o meio-dia imóvel sobre a forja e trabalha a guarda do inimigo como minério que ainda não decidiu virar lâmina. Ignora 45% da armadura do inimigo."),
    597: ("O Sol Só Se Põe Para a Nossa Casa",
          "A jactância mais velha de Fēnghuǒ, e a única arte que a merece: por uma troca de golpes, o punho do Herdeiro guarda a hora que o resto do mundo já perdeu. +67% de dano em todas as rodadas."),
    588: ("Pacto do Ancião Afogado",
          "Todo Ancião do Abismo assina o mesmo contrato com o que jaz embaixo, e o abismo cumpre a parte dele: nada vestido na superfície vai proteger ninguém de você. Ignora 46% da armadura do inimigo."),
    598: ("O que o Abismo Guardou Para o Seu Herdeiro",
          "O fundo não dá; ele empresta, e só empresta a quem já caiu longe o bastante para merecer confiança. O Herdeiro vem cobrar. +68% de dano em todas as rodadas."),
}

_ARTS_EN = {
    580: ("Sky-Severing Cloud Decree",
          "What the Elder signs with the sword, the heavens countersign: a single decree drawn across the sky, and the guard that was there is simply no longer part of the world. Ignores 44% of the enemy's armor."),
    590: ("Bai's Unwritten Cloud",
          "Founder Bai never set this form to paper — he said a cloud that can be drawn is already a cloud that can be cut. Only the Successor is shown it, once, and must remember. +66% damage in all rounds."),
    581: ("Ninth Refinement Blaze",
          "Eight refinements make a pill; the ninth makes a weapon. The Elder feeds their own dao into the furnace and strikes with what comes out. +48% damage in all rounds."),
    591: ("Ash of the First Cauldron",
          "A pinch of ash from the cauldron that started the house, kept for a thousand years. Worn on the skin, it remembers every fire it has already survived. Reduces damage taken by 52%."),
    582: ("Unbroken Jade Accord",
          "The Elder does not refuse the blow — they agree with it, and an agreement cannot be broken by force. Reduces damage taken by 42%."),
    592: ("Mercy That Outlasts the Sword",
          "The house's deepest secret is not a technique but a vow: harm nothing that can still be spared, and nothing that strikes you will find a place to land. Reduces damage taken by 55%."),
    583: ("Ten Thousand Catty Descent",
          "The Elder does not throw the fist. They let go of it, and the mountain does the rest. +48% damage in all rounds."),
    593: ("The Peak Answers Only Once",
          "The Successor learns the name the founder carved into the summit stone. Speak it, and for one breath you are not standing on the mountain — you are the mountain. +68% damage in all rounds."),
    584: ("Winter Without Thaw",
          "The Elder's cold no longer waits for the season: it simply decides that spring will not be arriving here. Reduces damage taken by 43%."),
    594: ("Glacier That Remembers the Sea",
          "Before the peak froze it was water, and water has been inside everything. The Successor's strike finds the seam it knew a thousand years ago. Ignores 54% of the enemy's armor."),
    585: ("Garden of Ten Thousand Turnings",
          "The Elder walks a path only the garden knows, and the garden rearranges itself politely behind them. +30% evasion in all rounds."),
    595: ("The Seed Kept From Every Harvest",
          "Every generation set one seed aside and never planted it. The Successor carries it, and while it is unplanted nothing in this world is finished with you. Reduces damage taken by 52%."),
    586: ("Edge That Precedes the Sound",
          "The Elder arrives a half-breath before the noise of arriving; blades sent to where they are keep finding where they were. +31% evasion in all rounds."),
    596: ("Name Erased From the Wind",
          "The Successor gives up their name to the mountain wind. What has no name has no shape, and what has no shape was never outside the armor to begin with. Ignores 56% of the enemy's armor."),
    587: ("Anvil of the Standing Noon",
          "The Elder holds the noon still above the forge and works the enemy's guard like ore that has not yet decided to be a blade. Ignores 45% of the enemy's armor."),
    597: ("The Sun Sets For No House But Ours",
          "Fenghuo's oldest boast, and the only art that earns it: for one exchange the Successor's fist keeps the hour the rest of the world has already lost. +67% damage in all rounds."),
    588: ("Covenant of the Drowned Elder",
          "Every Elder of the Abyss signs the same contract with what lies beneath, and the abyss keeps its half: nothing worn on the surface will protect anyone from you. Ignores 46% of the enemy's armor."),
    598: ("What the Abyss Kept For Its Heir",
          "The deep does not give; it lends, and it lends only to the one who has already fallen far enough to be trusted. The Successor collects. +68% damage in all rounds."),
}

_ARTS_ES = {
    580: ("Decreto de la Nube que Corta el Cielo",
          "Lo que el Anciano firma con la espada, el Cielo lo refrenda: un único decreto trazado en el aire, y la guardia que estaba ahí simplemente deja de formar parte del mundo. Ignora el 44% de la armadura del enemigo."),
    590: ("La Nube No Escrita de Bái",
          "El fundador Bái nunca puso esta forma en papel — decía que una nube que se puede dibujar ya es una nube que se puede cortar. Solo al Heredero se la muestran, una vez, y debe recordarla. +66% de daño en todas las rondas."),
    581: ("Llama del Noveno Refinado",
          "Ocho refinados hacen una píldora; el noveno hace un arma. El Anciano alimenta su propio dao en el caldero y golpea con lo que sale de ahí. +48% de daño en todas las rondas."),
    591: ("Ceniza del Primer Caldero",
          "Una pizca de ceniza del caldero que fundó la casa, guardada durante mil años. Llevada sobre la piel, recuerda cada fuego al que ya ha sobrevivido. Reduce el daño recibido en un 52%."),
    582: ("Acuerdo de Jade Inquebrantable",
          "El Anciano no rechaza el golpe — está de acuerdo con él, y un acuerdo no se rompe por la fuerza. Reduce el daño recibido en un 42%."),
    592: ("La Misericordia que Sobrevive a la Espada",
          "El secreto más hondo de la casa no es una técnica sino un voto: no dañar nada que aún pueda perdonarse, y nada que te golpee hallará dónde posarse. Reduce el daño recibido en un 55%."),
    583: ("Caída de Diez Mil Jin",
          "El Anciano no lanza el puño. Lo suelta, y la montaña hace el resto. +48% de daño en todas las rondas."),
    593: ("La Cumbre Responde Una Sola Vez",
          "El Heredero aprende el nombre que el fundador grabó en la piedra de la cima. Dilo y, por un aliento, no estás sobre la montaña — eres la montaña. +68% de daño en todas las rondas."),
    584: ("Invierno Sin Deshielo",
          "El frío del Anciano ya no espera la estación: sencillamente decide que la primavera no va a llegar aquí. Reduce el daño recibido en un 43%."),
    594: ("El Glaciar que Recuerda el Mar",
          "Antes de congelarse, el pico era agua — y el agua ha estado dentro de todo. El golpe del Heredero encuentra la juntura que conoció hace mil años. Ignora el 54% de la armadura del enemigo."),
    585: ("Jardín de las Diez Mil Vueltas",
          "El Anciano camina por un sendero que solo el jardín conoce, y el jardín se reordena con cortesía a su espalda. +30% de evasión en todas las rondas."),
    595: ("La Semilla Guardada de Toda Cosecha",
          "Cada generación apartó una semilla y nunca la plantó. El Heredero la lleva consigo, y mientras no se plante nada en este mundo ha terminado contigo. Reduce el daño recibido en un 52%."),
    586: ("El Filo que Llega Antes del Sonido",
          "El Anciano llega medio aliento antes del ruido de llegar; las hojas enviadas a donde está siguen encontrando donde estaba. +31% de evasión en todas las rondas."),
    596: ("Nombre Borrado del Viento",
          "El Heredero entrega su propio nombre al viento de la montaña. Lo que no tiene nombre no tiene forma, y lo que no tiene forma nunca estuvo fuera de la armadura. Ignora el 56% de la armadura del enemigo."),
    587: ("Yunque del Mediodía Detenido",
          "El Anciano sostiene el mediodía inmóvil sobre la forja y trabaja la guardia del enemigo como mineral que aún no ha decidido ser hoja. Ignora el 45% de la armadura del enemigo."),
    597: ("El Sol Solo Se Pone Para Nuestra Casa",
          "La jactancia más vieja de Fēnghuǒ, y el único arte que la merece: por un intercambio de golpes, el puño del Heredero conserva la hora que el resto del mundo ya ha perdido. +67% de daño en todas las rondas."),
    588: ("Pacto del Anciano Ahogado",
          "Todo Anciano del Abismo firma el mismo contrato con lo que yace debajo, y el abismo cumple su parte: nada vestido en la superficie protegerá a nadie de ti. Ignora el 46% de la armadura del enemigo."),
    598: ("Lo que el Abismo Guardó Para Su Heredero",
          "El fondo no da; presta, y solo presta a quien ya ha caído lo bastante lejos como para merecer confianza. El Heredero viene a cobrar. +68% de daño en todas las rondas."),
}


def _art_keys(table: dict) -> dict:
    out = {}
    for tid, (name, desc) in table.items():
        out[f"tech_{tid}_name"] = name
        out[f"tech_{tid}_desc"] = desc
    return out


CHAT = {
    "pt": {
        **_art_keys(_ARTS_PT),
        # as duas estantes que deixaram de ser teaser (o engine deriva a key
        # por f-string: lib_shelf_<tier> — sem estas duas o jogador le a key)
        "lib_shelf_4": "Estante do Ancião 传功",
        "lib_shelf_5": "Estante Oculta 秘传",
        # bloqueios novos (enum novo => TODO mapa .get() — licao QoL-relatos)
        "sel_block_karma": "exige convicção {have}/{need} no caminho da casa",
        "sel_block_rite": "exige vencer a Prova da Sucessão",
        # o caminho quantificado (Lei §1)
        "sel_gap_cp": "↑ faltam {cp} de contribuição para este degrau",
        "sel_gap_realm": "↑ falta subir {realm} reino(s) para este degrau",
        "sel_gap_both": "↑ faltam {cp} de contribuição e {realm} reino(s) para este degrau",
        # o rito
        "sel_btn_rite": "⚔️ Prova da Sucessão — {name}",
        "sel_rite_toast": "⚔️ O Ancião guardião se levanta...",
        "sel_rite_won": "🏆 *Você venceu o Ancião guardião em {rounds} rodadas.* A casa abre a câmara mais funda e transmite o que nunca vendeu.",
        "sel_rite_lost": "🩸 *O Ancião guardião te derrubou em {rounds} rodadas.* O segredo continua sendo dele — por enquanto.",
        "sel_rite_cooldown": "⏳ A Prova da Sucessão só se repete em {hours}h.",
        "sel_err_cooldown": "A Prova da Sucessão só se repete em {hours}h.",
        "sel_err_karma": "Sua convicção ainda não basta: {have} de {need} no caminho da casa.",
        "sel_err_busy": "Você já está em um duelo. Termine antes de encarar a Prova.",
        "sel_err_hp": "Você está ferido demais para encarar o Ancião guardião.",
        "sel_chron_first": "秘传 Em {continent}, {sect} confiou o seu segredo mais fundo a um Herdeiro pela primeira vez nesta era.",
    },
    "en": {
        **_art_keys(_ARTS_EN),
        "lib_shelf_4": "Elder's Shelf 传功",
        "lib_shelf_5": "Hidden Shelf 秘传",
        "sel_block_karma": "requires conviction {have}/{need} on the house's road",
        "sel_block_rite": "requires winning the Succession Trial",
        "sel_gap_cp": "↑ {cp} more contribution for this rung",
        "sel_gap_realm": "↑ {realm} more realm(s) for this rung",
        "sel_gap_both": "↑ {cp} more contribution and {realm} more realm(s) for this rung",
        "sel_btn_rite": "⚔️ Succession Trial — {name}",
        "sel_rite_toast": "⚔️ The guardian Elder rises...",
        "sel_rite_won": "🏆 *You bested the guardian Elder in {rounds} rounds.* The house opens its deepest chamber and hands over what it never sold.",
        "sel_rite_lost": "🩸 *The guardian Elder put you down in {rounds} rounds.* The secret is still theirs — for now.",
        "sel_rite_cooldown": "⏳ The Succession Trial can only be faced again in {hours}h.",
        "sel_err_cooldown": "The Succession Trial can only be faced again in {hours}h.",
        "sel_err_karma": "Your conviction is not enough yet: {have} of {need} on the house's road.",
        "sel_err_busy": "You are already in a duel. Finish it before facing the Trial.",
        "sel_err_hp": "You are too wounded to face the guardian Elder.",
        "sel_chron_first": "秘传 In {continent}, {sect} entrusted its deepest secret to a Successor for the first time this era.",
    },
    "es": {
        **_art_keys(_ARTS_ES),
        "lib_shelf_4": "Estante del Anciano 传功",
        "lib_shelf_5": "Estante Oculto 秘传",
        "sel_block_karma": "exige convicción {have}/{need} en el camino de la casa",
        "sel_block_rite": "exige vencer la Prueba de Sucesión",
        "sel_gap_cp": "↑ faltan {cp} de contribución para este peldaño",
        "sel_gap_realm": "↑ falta subir {realm} reino(s) para este peldaño",
        "sel_gap_both": "↑ faltan {cp} de contribución y {realm} reino(s) para este peldaño",
        "sel_btn_rite": "⚔️ Prueba de Sucesión — {name}",
        "sel_rite_toast": "⚔️ El Anciano guardián se levanta...",
        "sel_rite_won": "🏆 *Venciste al Anciano guardián en {rounds} rondas.* La casa abre su cámara más honda y entrega lo que nunca vendió.",
        "sel_rite_lost": "🩸 *El Anciano guardián te derribó en {rounds} rondas.* El secreto sigue siendo suyo — por ahora.",
        "sel_rite_cooldown": "⏳ La Prueba de Sucesión solo se repite en {hours}h.",
        "sel_err_cooldown": "La Prueba de Sucesión solo se repite en {hours}h.",
        "sel_err_karma": "Tu convicción aún no basta: {have} de {need} en el camino de la casa.",
        "sel_err_busy": "Ya estás en un duelo. Termínalo antes de encarar la Prueba.",
        "sel_err_hp": "Estás demasiado herido para encarar al Anciano guardián.",
        "sel_chron_first": "秘传 En {continent}, {sect} confió su secreto más hondo a un Heredero por primera vez en esta era.",
    },
}

# ── Mini-app: chrome proprio (`sel_mini_`) + a auto-documentacao do painel ────
# A desc do painel segue a casa (aviso -> comportamento -> dependencia -> knobs
# com defaults entre parenteses). Sem estas keys o painel mostra a KEY CRUA.
_FEATURE_DESC_PT = (
    "⚠️ LAUNCH-SERVER-BOUND: as duas câmaras que o TEC-1 deixou seladas viram "
    "estantes REAIS, com 18 artes novas (1 por câmara por casa). "
    "Estante do Ancião 传功 (tier 4): posto elder + SEL_T4_CP de contribuição "
    "tirada do SALDO do Pavilhão (o posto NUNCA recua) + reino. "
    "Estante Oculta 秘传 (tier 5): posto heir + karma ALINHADO com a casa "
    "(SEL_KARMA_MIN — numa casa demoníaca conta o karma NEGATIVO, senão a única "
    "casa demoníaca do jogo ficaria trancada para sempre) + vencer a Prova da "
    "Sucessão, um duelo contra o Ancião guardião. A Oculta NÃO custa "
    "contribuição: o segredo não se vende. "
    "Sair da casa passa a TRANCAR tier >= 3 (Núcleo, Ancião e Oculta) — o "
    "registro nunca se apaga e voltar à mesma casa destranca. "
    "EXIGE biblioteca_seitas ON (sem ela esta flag não faz nada). "
    "Knobs env: SEL_T4_CP (6000) / SEL_T5_CP (0) / SEL_KARMA_MIN (250) / "
    "SEL_RITE_COOLDOWN_H (24)."
)
_FEATURE_DESC_EN = (
    "⚠️ LAUNCH-SERVER-BOUND: the two chambers TEC-1 left sealed become REAL "
    "shelves, with 18 new arts (1 per chamber per house). "
    "Elder's Shelf 传功 (tier 4): elder rank + SEL_T4_CP contribution taken from "
    "the Pavilion BALANCE (rank never regresses) + realm. "
    "Hidden Shelf 秘传 (tier 5): heir rank + karma ALIGNED with the house "
    "(SEL_KARMA_MIN — in a demonic house NEGATIVE karma counts, otherwise the "
    "game's only demonic house would be locked out forever) + winning the "
    "Succession Trial, a duel against the guardian Elder. The Hidden Shelf "
    "costs NO contribution: the secret is not for sale. "
    "Leaving the house now LOCKS tier >= 3 (Core, Elder and Hidden) — the "
    "record is never erased and returning to the same house unlocks it. "
    "REQUIRES biblioteca_seitas ON (without it this flag does nothing). "
    "Env knobs: SEL_T4_CP (6000) / SEL_T5_CP (0) / SEL_KARMA_MIN (250) / "
    "SEL_RITE_COOLDOWN_H (24)."
)
_FEATURE_DESC_ES = (
    "⚠️ LAUNCH-SERVER-BOUND: las dos cámaras que TEC-1 dejó selladas se vuelven "
    "estantes REALES, con 18 artes nuevas (1 por cámara por casa). "
    "Estante del Anciano 传功 (tier 4): rango elder + SEL_T4_CP de contribución "
    "tomada del SALDO del Pabellón (el rango NUNCA retrocede) + reino. "
    "Estante Oculto 秘传 (tier 5): rango heir + karma ALINEADO con la casa "
    "(SEL_KARMA_MIN — en una casa demoníaca cuenta el karma NEGATIVO, si no la "
    "única casa demoníaca del juego quedaría trancada para siempre) + vencer la "
    "Prueba de Sucesión, un duelo contra el Anciano guardián. El Estante Oculto "
    "NO cuesta contribución: el secreto no se vende. "
    "Salir de la casa ahora TRANCA tier >= 3 (Núcleo, Anciano y Oculto) — el "
    "registro nunca se borra y volver a la misma casa lo destranca. "
    "EXIGE biblioteca_seitas ON (sin ella esta flag no hace nada). "
    "Knobs env: SEL_T4_CP (6000) / SEL_T5_CP (0) / SEL_KARMA_MIN (250) / "
    "SEL_RITE_COOLDOWN_H (24)."
)

MINIAPP = {
    "pt": {
        "sel_mini_gap_cp": "faltam {cp} de contribuição",
        "sel_mini_gap_realm": "falta subir {realm} reino(s)",
        "sel_mini_gap_both": "faltam {cp} de contribuição e {realm} reino(s)",
        "sel_mini_block_karma": "convicção {have}/{need}",
        "sel_mini_rite_btn": "Prova",
        "sel_mini_rite_cooldown": "⏳ A Prova da Sucessão só se repete em {hours}h.",
        "sel_mini_err_cooldown": "A Prova só se repete em {hours}h.",
        "sel_mini_err_karma": "Convicção insuficiente: {have} de {need} no caminho da casa.",
        "sel_mini_err_busy": "Você já está em um duelo.",
        "sel_mini_err_hp": "Ferido demais para encarar o Ancião guardião.",
        "feature_estantes_seladas": "As Duas Estantes Seladas (TEC-3)",
        "feature_estantes_seladas_desc": _FEATURE_DESC_PT,
    },
    "en": {
        "sel_mini_gap_cp": "{cp} more contribution",
        "sel_mini_gap_realm": "{realm} more realm(s)",
        "sel_mini_gap_both": "{cp} more contribution and {realm} more realm(s)",
        "sel_mini_block_karma": "conviction {have}/{need}",
        "sel_mini_rite_btn": "Trial",
        "sel_mini_rite_cooldown": "⏳ The Succession Trial can only be faced again in {hours}h.",
        "sel_mini_err_cooldown": "The Trial can only be faced again in {hours}h.",
        "sel_mini_err_karma": "Not enough conviction: {have} of {need} on the house's road.",
        "sel_mini_err_busy": "You are already in a duel.",
        "sel_mini_err_hp": "Too wounded to face the guardian Elder.",
        "feature_estantes_seladas": "The Two Sealed Shelves (TEC-3)",
        "feature_estantes_seladas_desc": _FEATURE_DESC_EN,
    },
    "es": {
        "sel_mini_gap_cp": "faltan {cp} de contribución",
        "sel_mini_gap_realm": "falta subir {realm} reino(s)",
        "sel_mini_gap_both": "faltan {cp} de contribución y {realm} reino(s)",
        "sel_mini_block_karma": "convicción {have}/{need}",
        "sel_mini_rite_btn": "Prueba",
        "sel_mini_rite_cooldown": "⏳ La Prueba de Sucesión solo se repite en {hours}h.",
        "sel_mini_err_cooldown": "La Prueba solo se repite en {hours}h.",
        "sel_mini_err_karma": "Convicción insuficiente: {have} de {need} en el camino de la casa.",
        "sel_mini_err_busy": "Ya estás en un duelo.",
        "sel_mini_err_hp": "Demasiado herido para encarar al Anciano guardián.",
        "feature_estantes_seladas": "Los Dos Estantes Sellados (TEC-3)",
        "feature_estantes_seladas_desc": _FEATURE_DESC_ES,
    },
}

# Sem overrides neste lote — TEC-3 e 100% adicoes.
CHAT_OVERRIDES: dict = {}
MINI_OVERRIDES: dict = {}


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
