"""Track A item 3 — Os Arquivos de Wànshì (player-posted bounties) i18n.

Idempotent (adds only missing keys), then re-dumps each locale indent=4 +
ensure_ascii=False + trailing newline.
  * CHAT    (locales/*.json)      — the poster-name board label, the /praca
    deep-link hint, and the SERVER-RESOLVED notification strings (claim/expire).
    These are rendered server-side via core.i18n, so they are PLAIN text (no
    Telegram markdown) with language-neutral {placeholders}.
  * MINIAPP (miniapp/i18n/*.json) — the 'Pôr a Prêmio' post panel (CTA, rules
    disclosure, errors) + the board's world/player tabs.
pt = PT-BR (você/seu, ativo, artefato).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHAT = {
    "pt": {
        "wbounty_posted_by": "Postada por {name}",
        "wbounty_post_chat_hint": "Quer pôr a cabeça de um demônio a prêmio? Abra o mini-app para publicar um contrato nos Arquivos de Wànshì.",
        "notif_bounty_claimed_title": "🏴 Recompensa reclamada",
        "notif_bounty_claimed_body": "{hunter} derrotou {target} e reivindicou a recompensa que você publicou nos Arquivos de Wànshì.",
        "notif_bounty_expired_title": "🏴 Recompensa expirada",
        "notif_bounty_expired_body": "Ninguém deteve {target} a tempo. Sua recompensa expirou — as pedras pagas não retornam.",
    },
    "en": {
        "wbounty_posted_by": "Posted by {name}",
        "wbounty_post_chat_hint": "Want to put a demon's head up for a prize? Open the mini-app to post a contract at the Wànshì Archives.",
        "notif_bounty_claimed_title": "🏴 Bounty claimed",
        "notif_bounty_claimed_body": "{hunter} defeated {target} and claimed the bounty you posted at the Wànshì Archives.",
        "notif_bounty_expired_title": "🏴 Bounty expired",
        "notif_bounty_expired_body": "No one stopped {target} in time. Your bounty expired — the stones paid are not returned.",
    },
    "es": {
        "wbounty_posted_by": "Publicada por {name}",
        "wbounty_post_chat_hint": "¿Quieres poner precio a la cabeza de un demonio? Abre el mini-app para publicar un contrato en los Archivos de Wànshì.",
        "notif_bounty_claimed_title": "🏴 Recompensa reclamada",
        "notif_bounty_claimed_body": "{hunter} derrotó a {target} y reclamó la recompensa que publicaste en los Archivos de Wànshì.",
        "notif_bounty_expired_title": "🏴 Recompensa expirada",
        "notif_bounty_expired_body": "Nadie detuvo a {target} a tiempo. Tu recompensa expiró — las piedras pagadas no se devuelven.",
    },
}

MINIAPP = {
    "pt": {
        "wbounty_tab_world": "🏴 Mundo",
        "wbounty_tab_player": "🎁 Jogadores",
        "wbounty_posted_by": "Postada por {name}",
        "wbounty_yours": "Sua recompensa",
        "wbounty_post_self_note": "Você não pode reclamar a própria recompensa — ela aguarda outro caçador.",
        "wbounty_post_cta": "🎁 Pôr a Prêmio",
        "wbounty_post_intro": "Coloque a cabeça deste alvo a prêmio nos Arquivos de Wànshì 万事阁. O primeiro caçador que o derrotar leva o prêmio. As pedras saem agora e são definitivas — não há reembolso.",
        "wbounty_post_cost": "Prêmio mínimo: {min} 🪨",
        "wbounty_post_active": "Suas recompensas ativas: {open}/{max}",
        "wbounty_post_placeholder": "Prêmio em pedras…",
        "wbounty_post_btn": "🎁 Publicar prêmio",
        "wbounty_post_ok": "🎁 Prêmio de {stones} 🪨 publicado sobre {target}!",
        "wbounty_post_too_cheap": "O prêmio mínimo é {min} 🪨.",
        "wbounty_post_no_stones": "Pedras espirituais insuficientes.",
        "wbounty_post_max": "Você já tem {max} recompensas ativas. Aguarde uma ser reclamada ou expirar.",
        "wbounty_post_not_eligible": "Só é possível pôr a prêmio cultivadores de karma sombrio.",
        "wbounty_post_already": "Já existe uma recompensa ativa sobre este alvo.",
        "wbounty_post_err": "Não foi possível publicar a recompensa.",
    },
    "en": {
        "wbounty_tab_world": "🏴 World",
        "wbounty_tab_player": "🎁 Players",
        "wbounty_posted_by": "Posted by {name}",
        "wbounty_yours": "Your bounty",
        "wbounty_post_self_note": "You cannot claim your own bounty — it awaits another hunter.",
        "wbounty_post_cta": "🎁 Set a Bounty",
        "wbounty_post_intro": "Put this target's head up for a prize at the Wànshì Archives 万事阁. The first hunter to defeat them takes the prize. The stones are spent now and are final — there is no refund.",
        "wbounty_post_cost": "Minimum prize: {min} 🪨",
        "wbounty_post_active": "Your active bounties: {open}/{max}",
        "wbounty_post_placeholder": "Prize in stones…",
        "wbounty_post_btn": "🎁 Post bounty",
        "wbounty_post_ok": "🎁 A {stones} 🪨 bounty was posted on {target}!",
        "wbounty_post_too_cheap": "The minimum prize is {min} 🪨.",
        "wbounty_post_no_stones": "Not enough spirit stones.",
        "wbounty_post_max": "You already have {max} active bounties. Wait for one to be claimed or to expire.",
        "wbounty_post_not_eligible": "Only dark-karma cultivators can be put up for a bounty.",
        "wbounty_post_already": "There is already an active bounty on this target.",
        "wbounty_post_err": "Could not post the bounty.",
    },
    "es": {
        "wbounty_tab_world": "🏴 Mundo",
        "wbounty_tab_player": "🎁 Jugadores",
        "wbounty_posted_by": "Publicada por {name}",
        "wbounty_yours": "Tu recompensa",
        "wbounty_post_self_note": "No puedes reclamar tu propia recompensa — espera a otro cazador.",
        "wbounty_post_cta": "🎁 Poner Recompensa",
        "wbounty_post_intro": "Pon precio a la cabeza de este objetivo en los Archivos de Wànshì 万事阁. El primer cazador que lo derrote se lleva el premio. Las piedras se gastan ahora y son definitivas — no hay reembolso.",
        "wbounty_post_cost": "Premio mínimo: {min} 🪨",
        "wbounty_post_active": "Tus recompensas activas: {open}/{max}",
        "wbounty_post_placeholder": "Premio en piedras…",
        "wbounty_post_btn": "🎁 Publicar recompensa",
        "wbounty_post_ok": "🎁 ¡Recompensa de {stones} 🪨 publicada sobre {target}!",
        "wbounty_post_too_cheap": "El premio mínimo es {min} 🪨.",
        "wbounty_post_no_stones": "Piedras espirituales insuficientes.",
        "wbounty_post_max": "Ya tienes {max} recompensas activas. Espera a que una sea reclamada o expire.",
        "wbounty_post_not_eligible": "Solo se puede poner recompensa a cultivadores de karma sombrío.",
        "wbounty_post_already": "Ya existe una recompensa activa sobre este objetivo.",
        "wbounty_post_err": "No se pudo publicar la recompensa.",
    },
}


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
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write("\n")
    return before, before + added, added


def main():
    for lang, adds in CHAT.items():
        before, after, added = _apply(os.path.join(ROOT, "locales", f"{lang}.json"), adds)
        print(f"chat    {lang}: {before} -> {after} (+{added})")
    for lang, adds in MINIAPP.items():
        before, after, added = _apply(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"), adds)
        print(f"miniapp {lang}: {before} -> {after} (+{added})")


if __name__ == "__main__":
    main()
