"""MV-6 Mundo Vivo v2 — Reputação regional + O RIVAL: injeção de i18n.

Idempotente (só insere keys AUSENTES — nunca sobrescreve) nas DUAS superfícies:
  * locales/{pt,en,es}.json          — chat (server-resolved: tiers/linhas da
    rep, notas de mercado, taunts do rival, notifs, Chronicle, título,
    storylets novos sty_*)
  * miniapp/i18n/{pt,en,es}.json     — mini-app (chrome do card do rival +
    feature keys do painel admin)

PT-BR estrito (você/seu; command literals sem acento). Notif_* keys SEMPRE no
chat i18n (lição MV-2 — o server renderiza).

Rodar:    python -X utf8 scripts/inject_mv6_i18n.py
Verificar: python -X utf8 scripts/_verify_mv6_i18n.py
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

CHAT = {
    "pt": {
        # ── Reputação: tiers + linhas ──────────────────────────────────────
        "rep_tier_reverence": "Reverenciado",
        "rep_tier_respected": "Respeitado",
        "rep_tier_neutral": "Desconhecido",
        "rep_tier_contempt": "Malvisto",
        "rep_plaza_prefix": "Sua reputação aqui:",
        "rep_travel_prefix": "Como te recebem:",
        "rep_line_reverence": "Os cultivadores da praça se curvam quando {name} passa. O mundo te chama primeiro aqui.",
        "rep_line_contempt": "Ninguém te dirige a palavra aqui. Nenhuma oferta virá deste continente enquanto seu nome for lama.",
        "rep_market_note_down": "🏮 Seu nome abre portas: −{pct}% nos preços do mercado local.",
        "rep_market_note_up": "🥀 Seu nome fecha portas: +{pct}% nos preços do mercado local.",
        "notif_rep_milestone_title": "🏮 Seu nome ecoa",
        "notif_rep_milestone_body": "Sua reputação em {continent} alcançou {rep}. O lugar te trata diferente agora.",
        # ── O RIVAL: taunts (determinísticos — seed + derrotas) ────────────
        "rvl_taunt_1": "Da última vez, provei o chão diante de você. Desta vez, é você quem vai ajoelhar.",
        "rvl_taunt_2": "Contei cada dia desde a minha queda. Todos foram seus — até hoje.",
        "rvl_taunt_3": "Você lembra do meu rosto? Eu nunca esqueci o seu.",
        "rvl_taunt_4": "A derrota foi minha mestra. Você foi apenas a lição.",
        "rvl_taunt_5": "O céu me viu cair {defeats} vezes. Nenhuma delas foi a última.",
        "rvl_taunt_6": "Sua vitória plantou isto que estou prestes a colher.",
        "rvl_taunt_spared_1": "Eu poupei sua vida. Lembre disso quando implorar de novo.",
        "rvl_taunt_spared_2": "Você caiu diante de mim — e eu deixei você respirar. A dívida cresce.",
        # ── O RIVAL: notifs (server-rendered — chat i18n, lição MV-2) ──────
        "notif_rvl_born_title": "😤 Alguém sobreviveu a você",
        "notif_rvl_born_body": "{name} sobreviveu à derrota que você impôs. E lembrará.",
        "notif_rvl_return_title": "😤 Seu rival voltou",
        "notif_rvl_return_body": "{name} reapareceu na sua praça, mais forte. “{taunt}”",
        "notif_rvl_gone_title": "🌫️ Seu rival partiu",
        "notif_rvl_gone_body": "O mundo levou {name} para longe do seu caminho. O posto de rival está vago.",
        "notif_rvl_end_asc_title": "💢 O arco se fechou",
        "notif_rvl_end_asc_body": "Derrotado pela quinta vez, {name} partiu para além das nuvens. O nome dele nunca mais cruzará o seu.",
        "notif_rvl_end_fall_title": "💢 O arco se fechou",
        "notif_rvl_end_fall_body": "A quinta derrota quebrou {name}. Ele largou a espada e desapareceu nas estradas.",
        # ── O RIVAL: praça do chat + rvl_view ──────────────────────────────
        "rvl_plaza_line": "{name} está na praça. Esperando por VOCÊ.",
        "rvl_btn_view": "Encarar seu rival",
        "rvl_gone_alert": "Seu rival já não está aqui. A última notificação do céu explica o que houve.",
        "rvl_away_alert": "Seu rival não está na praça agora — ele lambe as feridas. E voltará.",
        "notif_rvl_defeated_title": "⚔️ Seu rival caiu de novo",
        "notif_rvl_defeated_body": "{name} sumiu nas estradas para lamber as feridas. Ele voltará — mais forte.",
        "rvl_view_defeats": "⚔️ Derrotas que ele carrega: {n}",
        "rvl_view_power": "📈 Ele voltou {pct}% mais forte.",
        "rvl_view_spared": "☯️ Da última vez, ele POUPOU sua vida. Ele não esquece.",
        "rvl_open_app_hint": "O duelo espera no app: Praça → o card 😤 do seu rival.",
        # ── Chronicle + título ─────────────────────────────────────────────
        "rvl_chron_end_asc": "Após cair cinco vezes diante do mesmo cultivador, {rival} ascendeu para além das nuvens.",
        "rvl_chron_end_fall": "Humilhado cinco vezes pelo mesmo cultivador, {rival} quebrou a própria espada e sumiu.",
        "title_desc_quebra_rivais": "Fechou o arco de um rival: cinco derrotas, uma história que o mundo conta.",
        # ── Storylets novos (region_rep_min — só um nome conhecido recebe) ─
        "sty_confianca_do_magistrado_name": "A Confiança do Magistrado",
        "sty_confianca_do_magistrado_desc": "Limpe a estrada dos cultivadores errantes que extorquem viajantes — trabalho discreto, para um nome de confiança.",
        "sty_confianca_do_magistrado_d1": "Você é aquele de quem falam no mercado, não é? Preciso de alguém que resolva sem alarde.",
        "sty_confianca_do_magistrado_d2": "Quatro deles, na estrada velha. O selo do magistrado cobre seus atos. Não me decepcione.",
        "sty_encomenda_do_anciao_name": "A Encomenda do Ancião",
        "sty_encomenda_do_anciao_desc": "Um ancião reverencia seu nome e confia a você a forja de duas peças para o clã dele.",
        "sty_encomenda_do_anciao_d1": "Poucos nomes atravessam meu portão. O seu atravessou três vezes numa mesma lua.",
        "sty_encomenda_do_anciao_d2": "Duas peças, do seu próprio martelo. O clã pagará à altura do seu nome.",
    },
    "en": {
        "rep_tier_reverence": "Revered",
        "rep_tier_respected": "Respected",
        "rep_tier_neutral": "Unknown",
        "rep_tier_contempt": "Scorned",
        "rep_plaza_prefix": "Your reputation here:",
        "rep_travel_prefix": "How they receive you:",
        "rep_line_reverence": "The plaza's cultivators bow when {name} walks by. The world calls you first here.",
        "rep_line_contempt": "No one speaks to you here. No offer will come from this continent while your name is mud.",
        "rep_market_note_down": "🏮 Your name opens doors: −{pct}% on local market prices.",
        "rep_market_note_up": "🥀 Your name closes doors: +{pct}% on local market prices.",
        "notif_rep_milestone_title": "🏮 Your name echoes",
        "notif_rep_milestone_body": "Your reputation in {continent} reached {rep}. The place treats you differently now.",
        "rvl_taunt_1": "Last time, I tasted the ground before you. This time, you are the one who kneels.",
        "rvl_taunt_2": "I counted every day since my fall. All of them were yours — until today.",
        "rvl_taunt_3": "Do you remember my face? I never forgot yours.",
        "rvl_taunt_4": "Defeat was my master. You were merely the lesson.",
        "rvl_taunt_5": "Heaven watched me fall {defeats} times. None of them was the last.",
        "rvl_taunt_6": "Your victory planted what I am about to harvest.",
        "rvl_taunt_spared_1": "I spared your life. Remember that when you beg again.",
        "rvl_taunt_spared_2": "You fell before me — and I let you breathe. The debt grows.",
        "notif_rvl_born_title": "😤 Someone survived you",
        "notif_rvl_born_body": "{name} survived the defeat you dealt. And will remember.",
        "notif_rvl_return_title": "😤 Your rival has returned",
        "notif_rvl_return_body": "{name} reappeared in your plaza, stronger. “{taunt}”",
        "notif_rvl_gone_title": "🌫️ Your rival is gone",
        "notif_rvl_gone_body": "The world carried {name} far from your path. The rival's seat stands empty.",
        "notif_rvl_end_asc_title": "💢 The arc has closed",
        "notif_rvl_end_asc_body": "Defeated for the fifth time, {name} departed beyond the clouds. That name will never cross yours again.",
        "notif_rvl_end_fall_title": "💢 The arc has closed",
        "notif_rvl_end_fall_body": "The fifth defeat broke {name}. The sword was dropped and the roads swallowed the rest.",
        "rvl_plaza_line": "{name} is in the plaza. Waiting for YOU.",
        "rvl_btn_view": "Face your rival",
        "rvl_gone_alert": "Your rival is no longer here. Heaven's last notification explains what happened.",
        "rvl_away_alert": "Your rival is not in the plaza right now — licking wounds. They will return.",
        "notif_rvl_defeated_title": "⚔️ Your rival fell again",
        "notif_rvl_defeated_body": "{name} vanished into the roads to lick their wounds. They will return — stronger.",
        "rvl_view_defeats": "⚔️ Defeats they carry: {n}",
        "rvl_view_power": "📈 They came back {pct}% stronger.",
        "rvl_view_spared": "☯️ Last time, they SPARED your life. They do not forget.",
        "rvl_open_app_hint": "The duel awaits in the app: Plaza → your rival's 😤 card.",
        "rvl_chron_end_asc": "After falling five times before the same cultivator, {rival} ascended beyond the clouds.",
        "rvl_chron_end_fall": "Humiliated five times by the same cultivator, {rival} broke their own sword and vanished.",
        "title_desc_quebra_rivais": "Closed a rival's arc: five defeats, a story the world still tells.",
        "sty_confianca_do_magistrado_name": "The Magistrate's Trust",
        "sty_confianca_do_magistrado_desc": "Clear the road of the rogue cultivators extorting travelers — quiet work, for a trusted name.",
        "sty_confianca_do_magistrado_d1": "You are the one they talk about in the market, are you not? I need someone who settles things without noise.",
        "sty_confianca_do_magistrado_d2": "Four of them, on the old road. The magistrate's seal covers your deeds. Do not disappoint me.",
        "sty_encomenda_do_anciao_name": "The Elder's Commission",
        "sty_encomenda_do_anciao_desc": "An elder reveres your name and entrusts you with forging two pieces for his clan.",
        "sty_encomenda_do_anciao_d1": "Few names cross my gate. Yours crossed it three times under a single moon.",
        "sty_encomenda_do_anciao_d2": "Two pieces, from your own hammer. The clan will pay what your name is worth.",
    },
    "es": {
        "rep_tier_reverence": "Reverenciado",
        "rep_tier_respected": "Respetado",
        "rep_tier_neutral": "Desconocido",
        "rep_tier_contempt": "Malvisto",
        "rep_plaza_prefix": "Tu reputación aquí:",
        "rep_travel_prefix": "Cómo te reciben:",
        "rep_line_reverence": "Los cultivadores de la plaza se inclinan cuando {name} pasa. El mundo te llama primero aquí.",
        "rep_line_contempt": "Nadie te dirige la palabra aquí. Ninguna oferta vendrá de este continente mientras tu nombre sea barro.",
        "rep_market_note_down": "🏮 Tu nombre abre puertas: −{pct}% en los precios del mercado local.",
        "rep_market_note_up": "🥀 Tu nombre cierra puertas: +{pct}% en los precios del mercado local.",
        "notif_rep_milestone_title": "🏮 Tu nombre resuena",
        "notif_rep_milestone_body": "Tu reputación en {continent} alcanzó {rep}. El lugar te trata distinto ahora.",
        "rvl_taunt_1": "La última vez, probé el suelo ante ti. Esta vez, eres tú quien va a arrodillarse.",
        "rvl_taunt_2": "Conté cada día desde mi caída. Todos fueron tuyos — hasta hoy.",
        "rvl_taunt_3": "¿Recuerdas mi rostro? Yo nunca olvidé el tuyo.",
        "rvl_taunt_4": "La derrota fue mi maestra. Tú fuiste apenas la lección.",
        "rvl_taunt_5": "El cielo me vio caer {defeats} veces. Ninguna fue la última.",
        "rvl_taunt_6": "Tu victoria plantó esto que estoy a punto de cosechar.",
        "rvl_taunt_spared_1": "Perdoné tu vida. Recuérdalo cuando vuelvas a suplicar.",
        "rvl_taunt_spared_2": "Caíste ante mí — y te dejé respirar. La deuda crece.",
        "notif_rvl_born_title": "😤 Alguien te sobrevivió",
        "notif_rvl_born_body": "{name} sobrevivió a la derrota que le impusiste. Y recordará.",
        "notif_rvl_return_title": "😤 Tu rival volvió",
        "notif_rvl_return_body": "{name} reapareció en tu plaza, más fuerte. “{taunt}”",
        "notif_rvl_gone_title": "🌫️ Tu rival se fue",
        "notif_rvl_gone_body": "El mundo llevó a {name} lejos de tu camino. El puesto de rival quedó vacío.",
        "notif_rvl_end_asc_title": "💢 El arco se cerró",
        "notif_rvl_end_asc_body": "Derrotado por quinta vez, {name} partió más allá de las nubes. Ese nombre nunca volverá a cruzarse con el tuyo.",
        "notif_rvl_end_fall_title": "💢 El arco se cerró",
        "notif_rvl_end_fall_body": "La quinta derrota quebró a {name}. Soltó la espada y desapareció por los caminos.",
        "rvl_plaza_line": "{name} está en la plaza. Esperándote a TI.",
        "rvl_btn_view": "Encarar a tu rival",
        "rvl_gone_alert": "Tu rival ya no está aquí. La última notificación del cielo explica qué pasó.",
        "rvl_away_alert": "Tu rival no está en la plaza ahora — lame sus heridas. Y volverá.",
        "notif_rvl_defeated_title": "⚔️ Tu rival cayó de nuevo",
        "notif_rvl_defeated_body": "{name} desapareció por los caminos para lamer sus heridas. Volverá — más fuerte.",
        "rvl_view_defeats": "⚔️ Derrotas que carga: {n}",
        "rvl_view_power": "📈 Volvió {pct}% más fuerte.",
        "rvl_view_spared": "☯️ La última vez, te perdonó la vida. No lo olvida.",
        "rvl_open_app_hint": "El duelo espera en la app: Plaza → la carta 😤 de tu rival.",
        "rvl_chron_end_asc": "Tras caer cinco veces ante el mismo cultivador, {rival} ascendió más allá de las nubes.",
        "rvl_chron_end_fall": "Humillado cinco veces por el mismo cultivador, {rival} quebró su propia espada y desapareció.",
        "title_desc_quebra_rivais": "Cerró el arco de un rival: cinco derrotas, una historia que el mundo aún cuenta.",
        "sty_confianca_do_magistrado_name": "La Confianza del Magistrado",
        "sty_confianca_do_magistrado_desc": "Limpia el camino de los cultivadores errantes que extorsionan a los viajeros — trabajo discreto, para un nombre de confianza.",
        "sty_confianca_do_magistrado_d1": "Tú eres del que hablan en el mercado, ¿no? Necesito a alguien que resuelva sin alboroto.",
        "sty_confianca_do_magistrado_d2": "Cuatro de ellos, en el camino viejo. El sello del magistrado cubre tus actos. No me decepciones.",
        "sty_encomenda_do_anciao_name": "El Encargo del Anciano",
        "sty_encomenda_do_anciao_desc": "Un anciano reverencia tu nombre y te confía la forja de dos piezas para su clan.",
        "sty_encomenda_do_anciao_d1": "Pocos nombres cruzan mi puerta. El tuyo la cruzó tres veces bajo una misma luna.",
        "sty_encomenda_do_anciao_d2": "Dos piezas, de tu propio martillo. El clan pagará lo que tu nombre vale.",
    },
}

MINIAPP = {
    "pt": {
        "feature_reputacao_rival": "Reputação Regional + Rival",
        "feature_reputacao_rival_desc": "Reputação por continente (1 número que o lugar SENTE: desconto no mercado, reverência na praça, desprezo — e decai longe de você) + o RIVAL: um NPC derrotado pode voltar mais forte citando a derrota. Conversa com storylets (ofertas prioritárias aos reverenciados, suprimidas aos malvistos, missões que exigem nome conhecido), bounties (+rep) e Marés do Director (+rep). Melhor com tiandao_director e estados_regionais ON.",
        "rvl_card_title": "Seu rival: {name}",
        "rvl_challenge_cta": "Duelar",
        "rvl_defeats_chip": "⚔️ {n} derrotas",
        "rvl_power_chip": "+{pct}% mais forte",
        "rvl_modal_banner": "Seu rival. Ele lembra.",
        "rep_map_label": "Reputação",
    },
    "en": {
        "feature_reputacao_rival": "Regional Reputation + Rival",
        "feature_reputacao_rival_desc": "Per-continent reputation (one number the place FEELS: market discount, plaza reverence, scorn — decays while you are away) + the RIVAL: a defeated NPC may return stronger, quoting the defeat. Talks to storylets (priority offers for the revered, suppressed for the scorned, quests requiring a known name), bounties (+rep) and the Director's Tides (+rep). Best with tiandao_director and estados_regionais ON.",
        "rvl_card_title": "Your rival: {name}",
        "rvl_challenge_cta": "Duel",
        "rvl_defeats_chip": "⚔️ {n} defeats",
        "rvl_power_chip": "+{pct}% stronger",
        "rvl_modal_banner": "Your rival. They remember.",
        "rep_map_label": "Reputation",
    },
    "es": {
        "feature_reputacao_rival": "Reputación Regional + Rival",
        "feature_reputacao_rival_desc": "Reputación por continente (un número que el lugar SIENTE: descuento en el mercado, reverencia en la plaza, desprecio — y decae lejos de ti) + el RIVAL: un NPC derrotado puede volver más fuerte citando la derrota. Conversa con los storylets (ofertas prioritarias a los reverenciados, suprimidas a los malvistos, misiones que exigen un nombre conocido), bounties (+rep) y las Mareas del Director (+rep). Mejor con tiandao_director y estados_regionais ON.",
        "rvl_card_title": "Tu rival: {name}",
        "rvl_challenge_cta": "Duelar",
        "rvl_defeats_chip": "⚔️ {n} derrotas",
        "rvl_power_chip": "+{pct}% más fuerte",
        "rvl_modal_banner": "Tu rival. Él recuerda.",
        "rep_map_label": "Reputación",
    },
}


def _apply(path: str, additions: dict) -> tuple[int, int]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    before = len(data)
    added = 0
    for k, v in additions.items():
        if k not in data:
            data[k] = v
            added += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, sort_keys=True)
        f.write("\n")
    return before, added


def main() -> None:
    for lang in LANGS:
        before, added = _apply(os.path.join(ROOT, "locales", f"{lang}.json"), CHAT[lang])
        print(f"chat    {lang}: {before} -> {before + added} (+{added})")
    for lang in LANGS:
        before, added = _apply(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"), MINIAPP[lang])
        print(f"miniapp {lang}: {before} -> {before + added} (+{added})")


if __name__ == "__main__":
    main()
