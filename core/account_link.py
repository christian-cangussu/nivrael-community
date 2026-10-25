# -*- coding: utf-8 -*-
"""UMA CONTA, QUALQUER PLATAFORMA — o código de vínculo.

**O problema.** Depois da Fase 2 existem duas famílias de jogador: os que
entraram pelo Telegram (`telegram_id` real) e os que entraram pelo Google/Apple/
e-mail (`telegram_id` sintético, negativo). O owner quer que sejam a MESMA
pessoa, nos dois sentidos:

  • quem joga no Telegram quer entrar no site com o Google;
  • quem entrou pelo Google quer jogar no Telegram.

**Por que um código, e não um botão "ligar".** O segundo sentido não tem
mecanismo: um jogador de Google não consegue *provar* que é dono de uma conta
do Telegram enquanto o OIDC do Telegram não existir. E o primeiro sentido, feito
com o popup do Firebase dentro do WebView do Telegram, falha com frequência
(WebViews bloqueiam popups). Um código simétrico resolve os dois com UMA peça:

    quem tem a conta a MANTER gera o código
    →  do outro lado entra-se com a credencial NOVA e resgata-se

**⚠️ E a regra que torna isto seguro: RESGATA-SE ANTES DE HAVER PERSONAGEM.**
Um jogador que acabou de entrar com o Google tem identidade e id sintético, mas
ainda não tem linha em `players` — está no ecrã "criar personagem". É aí que o
vínculo acontece. Assim nunca é preciso apagar um personagem para juntar duas
contas, e a regra da casa ("NUNCA apagar dados de jogadores") fica intacta por
construção, não por disciplina.

**O que o vínculo É, mecanicamente:** re-apontar a linha de `auth_identities` da
credencial NOVA para o `player_id` que já existe. Nada em `players` se move, as
74 FK não sabem que isto aconteceu, e o id sintético abandonado vira um buraco
na sequência — que é exactamente o preço certo.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Curto de propósito: é lido em voz alta / copiado à mão entre dois aparelhos.
CODE_TTL_SECONDS = 15 * 60
#: Sem I, O, 0 e 1 — os quatro que uma pessoa confunde ao copiar de um ecrã.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
#: Quantos códigos vivos um jogador pode ter. Gerar outro invalida o anterior,
#: portanto o número é 1 — mas o limite existe para que martelar o botão não
#: encha a tabela.
_MAX_TRIES = 6


class LinkError(Exception):
    """Falha de vínculo. `reason` é uma key estável que a UI traduz."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _sm():
    from database.control_db import get_control_session_factory
    return get_control_session_factory()


def _new_code() -> str:
    """8 caracteres do alfabeto sem ambiguidades ≈ 40 bits.

    Não é um segredo de longa duração: vive 15 minutos, é de uso único, e o
    resgate exige uma sessão já autenticada do outro lado. O que ele impede é
    adivinhar — e 32^8 com 15 minutos de janela chega para isso."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(raw) -> str:
    """O que a pessoa escreveu → o que comparamos.

    Maiúsculas, sem espaços nem hífens (as pessoas escrevem `ABCD-2345`), e as
    confusões visuais dobradas para o alfabeto: `O`→`0` não, ao contrário —
    `0`→`O`, `1`→`L`, `I`→`J`? Não. Só retiramos o que não existe no alfabeto,
    porque adivinhar a intenção da pessoa criaria colisões entre códigos."""
    s = "".join(ch for ch in str(raw or "").upper() if ch.isalnum())
    return s[:CODE_LENGTH]


async def issue_link_code(player_id: int) -> tuple[str, datetime]:
    """Gera (ou substitui) o código do jogador. Devolve `(code, expires_at)`.

    Substituir é deliberado: um jogador com dois códigos vivos é um jogador que
    não sabe qual usar, e um código antigo esquecido é superfície a mais."""
    sm = _sm()
    if sm is None:
        raise LinkError("server_misconfigured")
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=CODE_TTL_SECONDS)
    async with sm() as session:
        # O anterior morre agora, não quando expirar.
        await session.execute(text(
            "DELETE FROM account_link_codes WHERE player_id = :pid"
        ), {"pid": int(player_id)})
        for _ in range(_MAX_TRIES):
            code = _new_code()
            try:
                await session.execute(text(
                    "INSERT INTO account_link_codes (code, player_id, expires_at) "
                    "VALUES (:c, :pid, :exp)"
                ), {"c": code, "pid": int(player_id), "exp": expires})
                await session.commit()
                return code, expires
            except Exception:
                # Colisão na PK (astronomicamente improvável) ou corrida.
                await session.rollback()
                continue
    raise LinkError("server_error")


async def peek_link_code(code: str) -> int | None:
    """O `player_id` de um código VIVO, sem o gastar. `None` se não servir.

    Existe para a UI poder dizer *"vai ligar ao cultivador [jogador] — confirma?"*
    antes de uma acção irreversível. Nunca revela nada sobre um código errado."""
    sm = _sm()
    if sm is None:
        return None
    normalized = normalize_code(code)
    if len(normalized) != CODE_LENGTH:
        return None
    try:
        async with sm() as session:
            row = (await session.execute(text(
                "SELECT player_id FROM account_link_codes "
                "WHERE code = :c AND used_at IS NULL AND expires_at > now()"
            ), {"c": normalized})).first()
        return int(row[0]) if row else None
    except Exception:
        logger.warning("peek_link_code falhou", exc_info=True)
        return None


async def redeem_link_code(code: str, provider: str, provider_uid: str,
                           current_player_id: int) -> int:
    """Aponta a identidade `(provider, provider_uid)` ao dono do código.

    Devolve o `player_id` final. Levanta `LinkError` com uma razão estável.

    ⚠️ AS TRÊS RECUSAS, e cada uma existe por um estrago concreto:

    1. `link_code_invalid` — código inexistente, expirado ou já usado. Uma só
       mensagem para os três: distinguir "expirou" de "não existe" diz a quem
       adivinha que acertou no formato.
    2. `link_same_account` — o código é do próprio jogador. Não é um erro
       perigoso, mas silenciar dava a sensação de que algo aconteceu.
    3. `link_would_orphan` — ⚠️ **a importante.** A credencial que está a ser
       ligada JÁ APONTA para outro `player_id` que tem personagem. Re-apontá-la
       deixaria esse personagem vivo e inalcançável para sempre. Recusa-se, e a
       mensagem diz o que fazer.
    """
    sm = _sm()
    if sm is None:
        raise LinkError("server_misconfigured")
    normalized = normalize_code(code)
    if len(normalized) != CODE_LENGTH:
        raise LinkError("link_code_invalid")

    async with sm() as session:
        # `FOR UPDATE` fecha a corrida de duas abas a resgatar o mesmo código:
        # a segunda espera e depois vê `used_at` preenchido.
        row = (await session.execute(text(
            "SELECT player_id FROM account_link_codes "
            "WHERE code = :c AND used_at IS NULL AND expires_at > now() "
            "FOR UPDATE"
        ), {"c": normalized})).first()
        if row is None:
            raise LinkError("link_code_invalid")
        target_player_id = int(row[0])

        if target_player_id == int(current_player_id):
            raise LinkError("link_same_account")

        # ⚠️ A credencial a ligar já é de alguém com personagem?
        existing = (await session.execute(text(
            "SELECT player_id FROM auth_identities "
            "WHERE provider = :p AND provider_uid = :u"
        ), {"p": provider, "u": str(provider_uid)})).first()
        if existing is not None and int(existing[0]) != int(current_player_id):
            raise LinkError("link_would_orphan")

        if await _has_character(int(current_player_id)):
            # Esta é a regra que torna o desenho seguro: só se liga uma
            # credencial cujo personagem ainda não existe. Com personagem dos
            # dois lados, juntar seria escolher qual apagar — e isso não se faz.
            raise LinkError("link_has_character")

        await session.execute(text(
            "UPDATE auth_identities SET player_id = :target "
            "WHERE provider = :p AND provider_uid = :u"
        ), {"target": target_player_id, "p": provider, "u": str(provider_uid)})
        await session.execute(text(
            "INSERT INTO auth_identities (player_id, provider, provider_uid) "
            "VALUES (:target, :p, :u) ON CONFLICT (provider, provider_uid) DO NOTHING"
        ), {"target": target_player_id, "p": provider, "u": str(provider_uid)})
        await session.execute(text(
            "UPDATE account_link_codes SET used_at = now() WHERE code = :c"
        ), {"c": normalized})
        await session.commit()

    # ⚠️ Sem isto a pessoa continuaria a ver o personagem antigo até o TTL
    # de 60s passar — e ia recarregar a página a achar que falhou.
    try:
        from database.control_db import invalidate_identity_cache
        invalidate_identity_cache(provider, str(provider_uid))
    except Exception:
        logger.warning("vínculo: cache de identidade não invalidada", exc_info=True)

    logger.info("vínculo: %s:%s passou a apontar para pid=%s (era %s)",
                provider, provider_uid, target_player_id, current_player_id)
    return target_player_id


async def _has_character(player_id: int) -> bool:
    """Este `player_id` tem personagem em ALGUM mundo?

    Best-effort: um mundo inalcançável conta como "não sei", e nesse caso
    respondemos **True** — recusar um vínculo é reversível (a pessoa tenta
    outra vez); autorizá-lo por engano deixa um personagem órfão para sempre."""
    try:
        from database.db import get_session_factory, iter_world_keys, use_world
    except Exception:
        return True
    for key in iter_world_keys():
        try:
            with use_world(key):
                async with get_session_factory()() as gs:
                    row = (await gs.execute(text(
                        "SELECT 1 FROM players WHERE telegram_id = :pid LIMIT 1"
                    ), {"pid": int(player_id)})).first()
            if row is not None:
                return True
        except Exception:
            logger.warning("vínculo: mundo %r inalcançável — a assumir que TEM "
                           "personagem (recusar é reversível)", key, exc_info=True)
            return True
    return False


async def list_identities(player_id: int) -> list[dict]:
    """As credenciais ligadas a este jogador, para a UI as MOSTRAR.

    ⚠️ O `provider_uid` nunca sai inteiro: para o Telegram é um número que
    identifica a pessoa, para o Firebase é opaco mas ainda assim uma chave. A UI
    precisa de *reconhecer*, não de copiar — por isso vai mascarado."""
    sm = _sm()
    if sm is None:
        return []
    try:
        async with sm() as session:
            rows = (await session.execute(text(
                "SELECT provider, provider_uid, profile, created_at, last_login_at "
                "FROM auth_identities WHERE player_id = :pid ORDER BY created_at"
            ), {"pid": int(player_id)})).mappings().all()
    except Exception:
        logger.warning("list_identities falhou pid=%s", player_id, exc_info=True)
        return []

    out = []
    for r in rows:
        prof = r["profile"] if isinstance(r["profile"], dict) else {}
        out.append({
            "provider": r["provider"],
            # O e-mail é o que a pessoa reconhece — e mostramo-lo mascarado.
            "label": _mask_email(prof.get("email") or "") or _mask_uid(r["provider_uid"]),
            "sign_in_provider": prof.get("sign_in_provider") or "",
            "linked_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    return out


def _mask_email(email: str) -> str:
    """`fulano@gmail.com` → `f•••o@gmail.com`. Reconhecível, não copiável."""
    email = (email or "").strip()
    if "@" not in email:
        return ""
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return ("•" * len(local)) + "@" + domain
    return local[0] + "•" * min(5, len(local) - 2) + local[-1] + "@" + domain


def _mask_uid(uid: str) -> str:
    uid = str(uid or "")
    return ("…" + uid[-4:]) if len(uid) > 4 else "…"
