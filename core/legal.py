# -*- coding: utf-8 -*-
"""WEB-B Fase 2 — as páginas legais: `/privacy` e `/terms`.

⚠️ **Por que este texto NÃO vive em `locales/*.json`.** A regra da casa é
`t(lang, "key")` para toda a string do jogo, e ela continua a valer. Isto é
outra coisa: são documentos de prosa longa, com secções, que se lêem inteiros e
se alteram em bloco. Enfiá-los nas locales seria ~90 keys por língua a poluir os
4249 do jogo, e uma alteração legal passaria a ser um diff em três ficheiros
gigantes onde ninguém consegue rever o sentido. Aqui os três idiomas ficam lado
a lado e uma revisão vê a frase equivalente na linha seguinte.

⚠️ **O Google EXIGE isto.** A tela de consentimento OAuth não é publicável sem
uma URL de política de privacidade acessível. Não é enfeite: é a peça que
destranca o "Entrar com Google".

⚠️ **Este texto é honesto, não é blindagem jurídica.** Descreve o que o Nivrael
faz de facto — e foi escrito a partir do código, não de um modelo. Onde diz
"o Google guarda a sua senha", é porque `core/firebase_auth.py` só vê um `uid`.
Antes de escalar (ou de vender fora do Brasil), isto merece a leitura de um
advogado. O que está aqui não pode é ser falso.
"""
from __future__ import annotations

import os

#: Para onde um pedido de dados/apagamento vai. Env por cima (Lei §6).
#: 開 Na edição comunitária não há contacto assado: o de baixo é um marcador que
#: não recebe correio (`.invalid`, RFC 2606) e diz o que falta configurar.
CONTACT_EMAIL = (os.getenv("LEGAL_CONTACT_EMAIL") or "").strip() or "defina-LEGAL_CONTACT_EMAIL@exemplo.invalid"

#: A data da última revisão destes textos. Aparece no rodapé porque uma política
#: sem data não diz nada a quem a lê.
LAST_UPDATED = "2026-08-26"

SUPPORTED = ("pt", "en", "es")


# ── Privacidade ──────────────────────────────────────────────────────────────
PRIVACY = {
    "pt": {
        "title": "Privacidade",
        "intro": "Esta página explica, em português claro, quais dados o Nivrael guarda, "
                 "por que guarda, e o que você pode pedir a qualquer momento.",
        "sections": [
            ("Quem cuida da sua senha (não somos nós)",
             ["Quando você entra com Google, Apple ou e-mail e senha, quem verifica sua "
              "identidade é o Firebase Authentication, do Google. <strong>Nós nunca vemos "
              "nem guardamos sua senha.</strong>",
              "O que o nosso servidor recebe é um identificador único da sua conta (um código "
              "opaco), o seu e-mail e, se o provedor enviar, seu nome de exibição. É só isso "
              "que liga você ao seu personagem.",
              "O tratamento de dados pelo Google segue a política de privacidade dele."]),
            ("O que guardamos no nosso servidor",
             ["<strong>Sua conta:</strong> o identificador do provedor, seu e-mail e a data do "
              "último acesso.",
              "<strong>Seu personagem:</strong> nome de cultivo, reino, progresso, itens, "
              "seita, e todo o restante do estado do jogo.",
              "<strong>Suas compras:</strong> o registro do que foi comprado e creditado.",
              "<strong>Sua sessão:</strong> um identificador aleatório, quando ela foi criada "
              "e quando expira — para você poder sair de todos os aparelhos.",
              "Se você chegou pelo Telegram, guardamos também o seu ID numérico do Telegram e, "
              "quando disponível, o seu @usuário e primeiro nome."]),
            ("O que NÃO guardamos",
             ["Senhas. Dados de cartão ou qualquer meio de pagamento — as compras passam pelo "
              "Telegram Stars e nós recebemos só a confirmação.",
              "Seu número de telefone, sua localização precisa, sua lista de contatos.",
              "Não vendemos, alugamos nem trocamos seus dados com ninguém."]),
            ("Cookies",
             ["Usamos dois, e ambos existem só para manter você conectado: um guarda a sessão "
              "e não é legível por scripts; o outro carrega um código anti-fraude que o "
              "navegador precisa enviar de volta.",
              "Não usamos cookies de publicidade nem de rastreamento entre sites."]),
            ("Por quanto tempo",
             ["A sessão expira sozinha, e no máximo em 30 dias desde que foi criada.",
              "Os dados do personagem ficam enquanto a conta existir. Se você pedir o "
              "apagamento, apagamos."]),
            ("Seus direitos",
             ["Você pode pedir, a qualquer momento: uma cópia dos seus dados, a correção de "
              "algo errado, ou o apagamento da conta e do personagem.",
              "Escreva para <strong>{email}</strong>. Respondemos no mesmo endereço.",
              "⚠️ O apagamento é definitivo: o personagem, o progresso e o histórico de "
              "compras vão junto, e não há como recuperar depois."]),
            ("Crianças",
             ["O Nivrael não é destinado a menores de 13 anos. Se soubermos que uma conta "
              "pertence a alguém abaixo dessa idade, ela é removida."]),
            ("Mudanças",
             ["Se esta política mudar de forma relevante, a data no rodapé muda e avisamos no "
              "grupo oficial antes de a mudança valer."]),
        ],
    },
    "en": {
        "title": "Privacy",
        "intro": "This page explains, in plain English, what data Nivrael stores, why it is "
                 "stored, and what you can ask for at any time.",
        "sections": [
            ("Who handles your password (not us)",
             ["When you sign in with Google, Apple, or email and password, your identity is "
              "verified by Google's Firebase Authentication. <strong>We never see or store "
              "your password.</strong>",
              "What our server receives is a unique account identifier (an opaque code), your "
              "email, and your display name if the provider sends one. That is all that links "
              "you to your character.",
              "Google's handling of that data follows Google's own privacy policy."]),
            ("What we store on our server",
             ["<strong>Your account:</strong> the provider identifier, your email, and the "
              "date of your last sign-in.",
              "<strong>Your character:</strong> dao name, realm, progress, items, sect, and "
              "the rest of your game state.",
              "<strong>Your purchases:</strong> the record of what was bought and credited.",
              "<strong>Your session:</strong> a random identifier, when it was created, and "
              "when it expires — so you can sign out of every device.",
              "If you arrived through Telegram, we also store your numeric Telegram ID and, "
              "when available, your @username and first name."]),
            ("What we do NOT store",
             ["Passwords. Card details or any payment instrument — purchases go through "
              "Telegram Stars and we receive only the confirmation.",
              "Your phone number, your precise location, your contact list.",
              "We do not sell, rent, or trade your data with anyone."]),
            ("Cookies",
             ["We use two, and both exist only to keep you signed in: one holds the session "
              "and is not readable by scripts; the other carries an anti-fraud code your "
              "browser must send back.",
              "We use no advertising or cross-site tracking cookies."]),
            ("How long we keep it",
             ["The session expires on its own, and at most 30 days after it was created.",
              "Character data stays for as long as the account exists. If you ask for "
              "deletion, we delete it."]),
            ("Your rights",
             ["You can ask, at any time, for: a copy of your data, a correction of anything "
              "wrong, or deletion of your account and character.",
              "Write to <strong>{email}</strong>. We reply to the same address.",
              "⚠️ Deletion is permanent: the character, the progress, and the purchase "
              "history go with it, and there is no way to recover them afterwards."]),
            ("Children",
             ["Nivrael is not intended for anyone under 13. If we learn that an account "
              "belongs to someone below that age, it is removed."]),
            ("Changes",
             ["If this policy changes in a meaningful way, the date in the footer changes and "
              "we announce it in the official group before the change takes effect."]),
        ],
    },
    "es": {
        "title": "Privacidad",
        "intro": "Esta página explica, en español claro, qué datos guarda Nivrael, por qué los "
                 "guarda, y qué puede pedir usted en cualquier momento.",
        "sections": [
            ("Quién cuida su contraseña (no somos nosotros)",
             ["Cuando entra con Google, Apple o correo y contraseña, quien verifica su "
              "identidad es Firebase Authentication, de Google. <strong>Nosotros nunca vemos "
              "ni guardamos su contraseña.</strong>",
              "Lo que nuestro servidor recibe es un identificador único de su cuenta (un "
              "código opaco), su correo y, si el proveedor lo envía, su nombre para mostrar. "
              "Eso es todo lo que lo conecta con su personaje.",
              "El tratamiento de esos datos por Google sigue la política de privacidad de "
              "Google."]),
            ("Qué guardamos en nuestro servidor",
             ["<strong>Su cuenta:</strong> el identificador del proveedor, su correo y la "
              "fecha del último acceso.",
              "<strong>Su personaje:</strong> nombre de cultivo, reino, progreso, objetos, "
              "secta y el resto del estado del juego.",
              "<strong>Sus compras:</strong> el registro de lo comprado y acreditado.",
              "<strong>Su sesión:</strong> un identificador aleatorio, cuándo se creó y cuándo "
              "expira — para que pueda salir de todos los aparatos.",
              "Si llegó por Telegram, guardamos también su ID numérico de Telegram y, cuando "
              "está disponible, su @usuario y su nombre."]),
            ("Qué NO guardamos",
             ["Contraseñas. Datos de tarjeta ni ningún medio de pago — las compras pasan por "
              "Telegram Stars y nosotros solo recibimos la confirmación.",
              "Su número de teléfono, su ubicación precisa, su lista de contactos.",
              "No vendemos, alquilamos ni intercambiamos sus datos con nadie."]),
            ("Cookies",
             ["Usamos dos, y ambas existen solo para mantenerlo conectado: una guarda la "
              "sesión y no es legible por scripts; la otra lleva un código antifraude que el "
              "navegador debe devolver.",
              "No usamos cookies de publicidad ni de rastreo entre sitios."]),
            ("Por cuánto tiempo",
             ["La sesión expira sola, y como máximo a los 30 días de haber sido creada.",
              "Los datos del personaje quedan mientras exista la cuenta. Si pide el borrado, "
              "lo borramos."]),
            ("Sus derechos",
             ["Puede pedir, en cualquier momento: una copia de sus datos, la corrección de "
              "algo incorrecto, o el borrado de la cuenta y del personaje.",
              "Escriba a <strong>{email}</strong>. Respondemos a la misma dirección.",
              "⚠️ El borrado es definitivo: el personaje, el progreso y el historial de "
              "compras se van con él, y después no hay forma de recuperarlos."]),
            ("Niños",
             ["Nivrael no está dirigido a menores de 13 años. Si sabemos que una cuenta "
              "pertenece a alguien por debajo de esa edad, se elimina."]),
            ("Cambios",
             ["Si esta política cambia de forma relevante, la fecha del pie cambia y lo "
              "anunciamos en el grupo oficial antes de que el cambio tenga efecto."]),
        ],
    },
}


# ── Termos ───────────────────────────────────────────────────────────────────
TERMS = {
    "pt": {
        "title": "Termos de Uso",
        "intro": "As regras de usar o Nivrael. São curtas de propósito.",
        "sections": [
            ("A conta é sua, e é uma só",
             ["Você é responsável por manter o acesso à sua conta. Não empreste, não venda e "
              "não compre contas — a venda de contas é motivo de bloqueio.",
              "Uma pessoa, uma conta por mundo. Criar contas extras para ganhar vantagem "
              "(multi-conta) é motivo de bloqueio."]),
            ("O que você pode perder, e quando",
             ["Podemos suspender ou remover uma conta que use exploits, automação (bots), "
              "fraude de pagamento, ou que ataque outros jogadores.",
              "Antes de qualquer remoção definitiva, tentamos avisar pelo grupo oficial ou "
              "pelo e-mail da conta — salvo em fraude de pagamento, onde o bloqueio é "
              "imediato."]),
            ("Compras",
             ["Spirit Jade e o Passe Celestial são <strong>bens virtuais</strong>, com uso "
              "dentro do jogo e sem valor fora dele. Não são moeda e não são convertíveis em "
              "dinheiro.",
              "As compras são processadas pelo Telegram Stars. Reembolsos seguem as regras do "
              "Telegram e da loja do seu aparelho.",
              "⚠️ <strong>Nunca desvalorizamos o que já foi comprado.</strong> Se um item for "
              "alterado ou removido do jogo, quem o comprou recebe compensação equivalente."]),
            ("O jogo muda",
             ["O Nivrael está em desenvolvimento aberto. Sistemas mudam, valores são "
              "ajustados, e conteúdo novo entra. Isso faz parte do jogo, não é um defeito.",
              "Mudanças que afetem progresso ou compras são anunciadas antes no grupo oficial."]),
            ("O que é nosso e o que é seu",
             ["O mundo, os textos, a arte e o código do Nivrael são nossos.",
              "O que você escreve no jogo (nome de cultivo, nome de seita, mensagens) continua "
              "seu — mas você nos dá permissão para o exibir dentro do jogo."]),
            ("Sem garantias impossíveis",
             ["O jogo é oferecido como está. Fazemos o possível para manter tudo no ar e "
              "íntegro, mas não podemos garantir disponibilidade ininterrupta.",
              "Se algo se perder por falha nossa, tentamos restaurar. Onde não der para "
              "restaurar, compensamos."]),
            ("Falar connosco",
             ["Dúvida, reclamação ou pedido sobre a conta: <strong>{email}</strong>, ou o "
              "grupo oficial."]),
        ],
    },
    "en": {
        "title": "Terms of Use",
        "intro": "The rules for using Nivrael. They are short on purpose.",
        "sections": [
            ("The account is yours, and it is one",
             ["You are responsible for keeping access to your account. Do not lend, sell, or "
              "buy accounts — selling accounts is grounds for a ban.",
              "One person, one account per world. Creating extra accounts to gain an "
              "advantage (multi-accounting) is grounds for a ban."]),
            ("What you can lose, and when",
             ["We may suspend or remove an account that uses exploits, automation (bots), "
              "payment fraud, or that attacks other players.",
              "Before any permanent removal we try to warn you through the official group or "
              "the account email — except in payment fraud, where the block is immediate."]),
            ("Purchases",
             ["Spirit Jade and the Celestial Pass are <strong>virtual goods</strong>, usable "
              "inside the game and with no value outside it. They are not currency and are "
              "not convertible to money.",
              "Purchases are processed by Telegram Stars. Refunds follow the rules of Telegram "
              "and of your device's store.",
              "⚠️ <strong>We never devalue what has already been bought.</strong> If an item "
              "is changed or removed from the game, whoever bought it receives equivalent "
              "compensation."]),
            ("The game changes",
             ["Nivrael is in open development. Systems change, numbers get tuned, new content "
              "arrives. That is part of the game, not a defect.",
              "Changes affecting progress or purchases are announced in the official group "
              "beforehand."]),
            ("What is ours and what is yours",
             ["The world, the writing, the art, and the code of Nivrael are ours.",
              "What you write in the game (dao name, sect name, messages) stays yours — but "
              "you give us permission to display it inside the game."]),
            ("No impossible guarantees",
             ["The game is offered as is. We do our best to keep everything up and intact, but "
              "we cannot guarantee uninterrupted availability.",
              "If something is lost through our fault, we try to restore it. Where restoring "
              "is not possible, we compensate."]),
            ("Talking to us",
             ["Questions, complaints, or account requests: <strong>{email}</strong>, or the "
              "official group."]),
        ],
    },
    "es": {
        "title": "Términos de Uso",
        "intro": "Las reglas para usar Nivrael. Son cortas a propósito.",
        "sections": [
            ("La cuenta es suya, y es una sola",
             ["Usted es responsable de mantener el acceso a su cuenta. No preste, no venda y "
              "no compre cuentas — vender cuentas es motivo de bloqueo.",
              "Una persona, una cuenta por mundo. Crear cuentas extra para obtener ventaja "
              "(multicuenta) es motivo de bloqueo."]),
            ("Qué puede perder, y cuándo",
             ["Podemos suspender o eliminar una cuenta que use exploits, automatización "
              "(bots), fraude de pago, o que ataque a otros jugadores.",
              "Antes de una eliminación definitiva intentamos avisar por el grupo oficial o "
              "por el correo de la cuenta — salvo en fraude de pago, donde el bloqueo es "
              "inmediato."]),
            ("Compras",
             ["Spirit Jade y el Pase Celestial son <strong>bienes virtuales</strong>, de uso "
              "dentro del juego y sin valor fuera de él. No son moneda ni son convertibles en "
              "dinero.",
              "Las compras las procesa Telegram Stars. Los reembolsos siguen las reglas de "
              "Telegram y de la tienda de su aparato.",
              "⚠️ <strong>Nunca devaluamos lo ya comprado.</strong> Si un objeto cambia o se "
              "retira del juego, quien lo compró recibe una compensación equivalente."]),
            ("El juego cambia",
             ["Nivrael está en desarrollo abierto. Los sistemas cambian, los valores se "
              "ajustan y entra contenido nuevo. Eso es parte del juego, no un defecto.",
              "Los cambios que afecten al progreso o a las compras se anuncian antes en el "
              "grupo oficial."]),
            ("Qué es nuestro y qué es suyo",
             ["El mundo, los textos, el arte y el código de Nivrael son nuestros.",
              "Lo que usted escribe en el juego (nombre de cultivo, nombre de secta, mensajes) "
              "sigue siendo suyo — pero nos da permiso para mostrarlo dentro del juego."]),
            ("Sin garantías imposibles",
             ["El juego se ofrece tal como está. Hacemos lo posible por mantener todo en línea "
              "e íntegro, pero no podemos garantizar disponibilidad ininterrumpida.",
              "Si algo se pierde por fallo nuestro, intentamos restaurarlo. Donde no se pueda "
              "restaurar, compensamos."]),
            ("Hablar con nosotros",
             ["Dudas, reclamaciones o solicitudes sobre la cuenta: <strong>{email}</strong>, o "
              "el grupo oficial."]),
        ],
    },
}

#: O rodapé, e o link para o outro documento.
CHROME = {
    "pt": {"updated": "Última atualização", "back": "Voltar ao início",
           "other_privacy": "Privacidade", "other_terms": "Termos de Uso",
           "eyebrow": "Documento oficial"},
    "en": {"updated": "Last updated", "back": "Back to the start",
           "other_privacy": "Privacy", "other_terms": "Terms of Use",
           "eyebrow": "Official document"},
    "es": {"updated": "Última actualización", "back": "Volver al inicio",
           "other_privacy": "Privacidad", "other_terms": "Términos de Uso",
           "eyebrow": "Documento oficial"},
}


def get_document(kind: str, lang: str) -> dict:
    """O documento (`privacy` | `terms`) na língua pedida.

    Degrada para inglês — o default público da casa desde 2026-08-26. Nunca
    levanta: uma página legal partida seria pior do que uma feia (e o Google
    precisa de a alcançar para libertar o consentimento)."""
    lang = lang if lang in SUPPORTED else "en"
    table = TERMS if kind == "terms" else PRIVACY
    doc = table.get(lang) or table["en"]
    chrome = CHROME.get(lang) or CHROME["en"]
    return {
        "kind": "terms" if kind == "terms" else "privacy",
        "lang": lang,
        "title": doc["title"],
        "intro": doc["intro"],
        # O `{email}` é resolvido AQUI e não no template: assim uma tradução que
        # se esqueça do marcador não deixa um buraco na página.
        "sections": [
            (head, [p.replace("{email}", CONTACT_EMAIL) for p in paras])
            for head, paras in doc["sections"]
        ],
        # WEB-C §3.3 — a sobrancelha do cabeçalho novo. `.get` com recurso ao
        # inglês: uma língua a que falte a chave mostra a inglesa em vez de
        # rebentar a página que o Google TEM de alcançar.
        "eyebrow": chrome.get("eyebrow") or CHROME["en"]["eyebrow"],
        "updated_label": chrome["updated"],
        "updated": LAST_UPDATED,
        "back": chrome["back"],
        "other_label": chrome["other_privacy"] if kind == "terms" else chrome["other_terms"],
        "other_href": "/privacy" if kind == "terms" else "/terms",
    }
