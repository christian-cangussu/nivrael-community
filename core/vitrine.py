"""WEB-A 展 A Vitrine — o mundo de Nivrael visto de fora, sem conta, sem Telegram.

Origem: comentario do No-Ride613 no r/incremental_games ("se fosse um jogo
autonomo de verdade, eu me interessaria"), +5 votos — o unico comentario com
votos positivos no post. O RECON (`Prompts/2026-08-19-web-standalone-recon.md`)
mediu que a canalizacao da autenticacao e pequena (2 chokepoints) mas que o
PRODUTO nao esta pronto para uma conta web: um jogador web nao consegue pagar
(Telegram Stars), nao consegue ser avisado (todo `notify()` sai por DM) e nao
consegue fundir contas (abriria um SEGUNDO personagem). WEB-A e a metade que
nao bate em nenhuma dessas paredes: **ver** o mundo, nunca joga-lo.

REGRAS DESTE MODULO — todas verificadas por `scripts/_test_web_a_vitrine.py`:

  1. **Nunca escreve.** Nenhuma funcao aqui abre transacao de escrita, e o
     build faz rollback explicito. Nao existe caminho de commit.
  2. **Nunca le um jogador especifico.** Nao ha `user_id` nesta superficie —
     nao ha nada para pedir em nome de ninguem.
  3. **Nunca publica `username`.** O `api_leaderboard` cai para
     `Player.username` (preenchido pelo Telegram) quando `dao_name` e NULL;
     na web aberta isso seria publicar o @handle de 240 pessoas. Aqui o
     fallback e o rotulo generico. `shadow_mode` continua a valer.
  4. **Toda seccao e fail-safe.** Uma seccao que levante e OMITIDA; a pagina
     continua a existir e o convite de entrada continua la (Lei §1 — nunca
     preso sem caminho).
  5. **Tudo vem localizado do servidor.** A pagina publica nao tem UMA string
     de copy hardcoded: os engines ja projectam por `lang` (o molde da Cronica)
     e o `chrome` traz o resto de `locales/{pt,en,es}.json`.

O MUNDO QUE A VITRINE MOSTRA. `main` le SEMPRE os defaults (28 flags OFF por
construcao — `database/db.get_world_features`), logo mostrar `main` seria mostrar
um mundo sem Mundo Vivo: medido em 2026-08-19, `main` tem 0 eventos vivos e 0
estados regionais, contra 15 e 5 no `s2`. A escolha nao e hardcoded: a vitrine
mostra o mundo onde se NASCE hoje (`database.db.signup_world_key`, a mesma
verdade que decide onde cai quem chega agora), com a valvula de ops
`VITRINE_WORLD` por cima. O owner controla por switch, sem deploy.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any

from sqlalchemy import func, select

from config import FEEDBACK_GROUP_URL, REALM_EMOJIS, REALM_NAMES
from core.i18n import t as i18n_t
from database.models import Player, Tribulation

logger = logging.getLogger(__name__)

# Limites duros — esta superficie e anonima, logo TODO numero e teto, nunca
# parametro do cliente. Nada aqui e paginavel, de proposito.
LADDER_LIMIT = 12
CHRONICLE_LIMIT = 12
CARAVAN_EXAMPLES = 3
_CHRON_MAX_PER_TYPE = 2

# ⚠️ O CACHE NAO E OTIMIZACAO — E A PROTECCAO DO JOGO VIVO. Esta pagina existe
# para ser postada no Reddit, e cada visita anonima custa ~8 queries na MESMA
# base onde 240 pessoas estao a cultivar. Sem cache, um post que corra bem e
# indistinguivel de um ataque. A resposta e identica para TODO visitante da
# mesma lingua (nao ha `user_id` nesta superficie — e por construcao que ela e
# cacheavel), e as fontes mexem-se devagar: o ceu vira de 12h em 12h, a Cronica
# de 6h em 6h, o encargo de 6h em 6h. 45s e conservador por duas ordens de
# grandeza e mantem a escada e o pulso a parecerem vivos.
CACHE_TTL_SECONDS = 45.0
_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}

# O convite. `FEEDBACK_GROUP_URL` ja aponta ao grupo; o bot tem env propria para
# o caso de o handle mudar sem deploy de codigo.
CTA_BOT_URL = os.getenv("VITRINE_BOT_URL", "https://t.me/Nivrael_bot")
#: A PORTA (WEB-B F1). Relativo — mesma origem da vitrine, zero configuração.
CTA_WEB_URL = os.getenv("VITRINE_WEB_URL", "/login")
CTA_GROUP_URL = FEEDBACK_GROUP_URL

SUPPORTED_LANGS = ("pt", "en", "es")

# As strings de chrome da pagina (titulos de seccao, convite, rodape). Vivem em
# `locales/*.json` como todo o resto — a pagina nao inventa copy.
CHROME_KEYS = (
    "vit_title", "vit_tagline", "vit_lede",
    "vit_sec_sky", "vit_sec_map", "vit_sec_houses", "vit_sec_chronicle",
    "vit_sec_caravan", "vit_sec_ladder", "vit_sec_enter",
    "vit_sky_next", "vit_city_wants", "vit_house_rival", "vit_house_pop",
    "vit_caravan_none", "vit_caravan_routes", "vit_caravan_ratio",
    "vit_ladder_anon", "vit_ladder_note",
    "vit_enter_body", "vit_cta_web", "vit_cta_play", "vit_cta_group",
    "vit_readonly_note", "vit_footer", "vit_empty",
    "vit_stat_players", "vit_stat_active", "vit_stat_npcs", "vit_stat_trials",
)


def vitrine_world_key() -> str:
    """O mundo que a vitrine mostra. Env `VITRINE_WORLD` (valvula de ops) →
    o mundo de nascimento (`signup_world_key`) → `main`. Nunca levanta."""
    try:
        forced = (os.getenv("VITRINE_WORLD") or "").strip().lower()
        if forced:
            return forced
        from database.db import signup_world_key
        return signup_world_key()
    except Exception:
        logger.warning("vitrine_world_key failed — a mostrar main", exc_info=True)
        return "main"


#: O idioma das SUPERFÍCIES PÚBLICAS (vitrine, porta, legais). Decisão do owner
#: 2026-08-26: *"quero global, quero inglês"*. Só o DEFAULT mudou — o conteúdo
#: do jogo continua nos 3 idiomas, e quem já joga continua a ler `player.language`
#: (que sai de `core.utils.normalize_lang`, INTOCADO). Isto aqui só decide o que
#: um visitante ANÓNIMO vê antes de existir uma conta.
PUBLIC_DEFAULT_LANG = "en"


def normalize_lang(raw: str | None, default: str = PUBLIC_DEFAULT_LANG) -> str:
    """`pt-BR` → `pt`, `es-419` → `es`, lixo → `default`.

    ⚠️ O default passou de `pt` para `en` a 2026-08-26 (owner). Isto NÃO toca em
    nenhum jogador existente: a língua de quem tem conta vem de
    `player.language`, resolvida por `core.utils.normalize_lang`, que continua
    exactamente como estava. O `default` fica parametrizável para o dia em que
    alguma superfície precise do contrário sem re-abrir esta discussão."""
    s = str(raw or "").strip().lower().replace("_", "-")
    head = s.split("-", 1)[0]
    return head if head in SUPPORTED_LANGS else default


def parse_accept_language(header: str | None) -> str | None:
    """O 1º idioma SUPORTADO de um `Accept-Language`, respeitando o `q=`.

    `"pt-BR,pt;q=0.9,en;q=0.8"` → `"pt"`. Um header sem nada que saibamos falar
    devolve `None` (e não o default) — assim quem chama distingue *"o browser
    pediu inglês"* de *"o browser não pediu nada que eu saiba"*, que é o que
    torna a detecção honesta em vez de um palpite.

    Nunca levanta: um header malformado vale o mesmo que header nenhum."""
    if not header:
        return None
    best: tuple[float, int, str] | None = None
    for idx, part in enumerate(str(header).split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        tag = tag.strip().lower().replace("_", "-").split("-", 1)[0]
        if tag not in SUPPORTED_LANGS:
            continue
        q = 1.0
        for param in params.split(";"):
            k, _, v = param.strip().partition("=")
            if k.strip().lower() == "q":
                try:
                    q = float(v)
                except (TypeError, ValueError):
                    q = 0.0
        # `-idx` mantém a ordem do header como desempate: o browser lista por
        # preferência, e dois `q` iguais têm de resolver pelo primeiro.
        cand = (q, -idx, tag)
        if q > 0 and (best is None or cand > best):
            best = cand
    return best[2] if best else None


def pick_public_lang(query_lang: str | None, accept_language: str | None) -> str:
    """A língua de uma superfície pública, por ordem de autoridade.

    1. `?lang=` — uma escolha EXPLÍCITA do visitante manda sempre.
    2. `Accept-Language` — o browser dele, se falar algo que sabemos falar.
    3. `PUBLIC_DEFAULT_LANG` (inglês) — o default global.

    É o contrato "inglês por default + detectar o navegador" (owner 2026-08-26):
    um brasileiro com o Chrome em pt-BR continua a cair em português sem clicar
    em nada, e um sueco cai em inglês em vez de cair em português."""
    explicit = str(query_lang or "").strip()
    if explicit:
        head = explicit.lower().replace("_", "-").split("-", 1)[0]
        if head in SUPPORTED_LANGS:
            return head
    detected = parse_accept_language(accept_language)
    return detected or PUBLIC_DEFAULT_LANG


def _chrome(lang: str) -> dict[str, str]:
    return {k: i18n_t(lang, k) for k in CHROME_KEYS}


# ── As seccoes ────────────────────────────────────────────────────────────────
# Cada uma devolve o seu bloco ou vazio e NUNCA levanta: o `_safe` wrapper faz
# desta regra uma propriedade do modulo, nao uma disciplina de quem escreve.

async def _safe(label: str, coro, default):
    try:
        return await coro
    except Exception:
        logger.exception("vitrine section failed: %s", label)
        return default


def _sky(lang: str, world_key: str | None) -> dict[str, Any] | None:
    """天时 O Tempo do Ceu — o unico futuro escrito do jogo. Funcao PURA
    (semeada por world+epoch de 12h), logo a vitrine le exactamente o mesmo ceu
    que a tribulacao do jogador le nesse instante. Flag OFF → None."""
    try:
        from core.tianshi_engine import sky_plaza_view
        return sky_plaza_view(lang, world_key)
    except Exception:
        logger.exception("vitrine sky failed")
        return None


async def _continents(session, lang: str) -> list[dict[str, Any]]:
    """Os cinco continentes, cada um com a sua cidade, o seu estado vivo e o que
    a cidade PEDE agora.

    A vitrine nao esta em lado nenhum — nao ha viajante, logo nao ha atraso de
    rumor (`delay_hours=0`). Isto e deliberado e e honesto: o unfolding do MV-9
    modela o que UM jogador sabe de onde esta; um visitante de fora ve o mundo
    como o Ceu o ve.
    """
    from core.continent_engine import get_all_continents_for_display

    out = get_all_continents_for_display(lang)

    states: dict[str, Any] = {}
    try:
        from core.region_state_engine import state_views
        states = await state_views(session, lang)
    except Exception:
        logger.exception("vitrine region states failed")

    for c in out:
        key = c["key"]
        # Os elementos vinham como chaves cruas (`universal`, `water`, ...): numa
        # montra isso é um rótulo por traduzir. Os nomes já existiam — mas SÓ no
        # i18n do mini-app, que o servidor não lê. Foram copiados para
        # `locales/*` com os MESMOS valores (o teste guarda a igualdade), e a
        # chave crua viaja ao lado para quem precisar de a mapear.
        c["elements"] = [{"key": e, "label": i18n_t(lang, "world_element_" + str(e))}
                         for e in (c.get("elements") or [])]
        try:
            from core.city_engine import city_view
            city = city_view(key, lang)
            if city:
                c["city"] = city
        except Exception:
            logger.exception("vitrine city_view failed continent=%s", key)
        st = states.get(key)
        if st:
            c["state"] = st
        try:
            from core.city_engine import encargo_view
            enc = await encargo_view(session, key, lang, delay_hours=0.0)
            # A recusa nomeada (`locked`) e informacao para um jogador dentro do
            # jogo, nao para um visitante: aqui ela seria ruido sobre uma
            # mecanica que ele ainda nao viu. So o pedido REAL entra.
            if enc and not enc.get("locked") and enc.get("name"):
                c["wants"] = {"icon": enc.get("icon") or "", "name": enc["name"],
                              "desc": enc.get("desc") or ""}
        except Exception:
            logger.exception("vitrine encargo failed continent=%s", key)
        try:
            crv = _caravan_for(key, lang)
            if crv:
                c["caravan"] = crv
        except Exception:
            logger.exception("vitrine caravan failed continent=%s", key)
    return out


def _caravan_for(continent: str, lang: str) -> dict[str, Any] | None:
    """商队 A Caravana daquele continente — quantos materiais o velho manda vir,
    a que razao, e alguns exemplos com a linha de ORIGEM (a disclosure que o
    MV-9.5 trouxe: hoje o jogo diz onde nasce cada coisa).

    Flag OFF → None. Continente sem caravana → `{"none": True}`, que e uma
    verdade do mundo (na Cidade dos Ecos so se chega indo), nao uma ausencia.
    """
    from core.caravan_engine import (
        caravana_on, has_caravan, origin_line, ratio_for, routes_for,
    )
    if not caravana_on():
        return None
    if not has_caravan(continent):
        return {"none": True}
    routes = routes_for(continent)
    examples: list[dict[str, str]] = []
    for kind, item_id in routes[:CARAVAN_EXAMPLES]:
        line = origin_line(kind, item_id, lang)
        name = _material_name(kind, item_id)
        if line and name:
            examples.append({"name": name, "line": line})
    return {"none": False, "routes": len(routes), "ratio": ratio_for(continent),
            "examples": examples}


def _material_name(kind: str, item_id: int) -> str:
    """`emoji + nome` do material a partir das seeds (o jogo inteiro mostra
    estes nomes em ingles nas tres linguas — a vitrine nao inventa uma quarta
    convencao)."""
    try:
        rows = ()
        if str(kind) == "herb":
            from database.seeds.alchemy_seeds import HERBS
            rows = HERBS
        else:
            from database.seeds.artifacts_seeds import ORES
            rows = ORES
        for row in rows:
            if int(row["id"]) == int(item_id):
                return f"{row.get('emoji', '')} {row['name']}".strip()
    except Exception:
        logger.debug("material name failed kind=%s id=%s", kind, item_id, exc_info=True)
    return ""


async def _houses(session, lang: str) -> list[dict[str, Any]]:
    """As nove Grandes Casas com a sua populacao viva (NPCs + jogadores)."""
    from core.continent_engine import CONTINENT_META
    from core.world_sects_engine import get_all_sects_for_display

    houses = get_all_sects_for_display(lang)

    npc_counts: dict[str, int] = {}
    try:
        from core.npc_cultivator_engine import count_sect_npc_population
        npc_counts = await count_sect_npc_population(session)
    except Exception:
        logger.exception("vitrine npc population failed")
    player_counts: dict[str, int] = {}
    try:
        rows = (await session.execute(
            select(Player.sect_id, func.count())
            .where(Player.sect_id.is_not(None))
            .group_by(Player.sect_id)
        )).all()
        player_counts = {s: int(n) for s, n in rows if s}
    except Exception:
        logger.exception("vitrine sect player counts failed")

    for h in houses:
        k = h["key"]
        h["npc"] = int(npc_counts.get(k, 0))
        h["players"] = int(player_counts.get(k, 0))
        meta = CONTINENT_META.get(h.get("continent") or "")
        if meta:
            h["continent_emoji"] = meta["emoji"]
            h["continent_name"] = i18n_t(lang, meta["name_key"])
        # `bonuses` e o balanco interno da casa — numeros sem contexto para quem
        # ainda nao joga. A vitrine mostra identidade, nao a folha de stats.
        h.pop("bonuses", None)
    return houses


def _leading_symbol(text: str) -> bool:
    """A linha ja comeca com um pictograma? (`So` = Symbol, other — a categoria
    dos emoji). Serve para nao desenhar DOIS emojis colados."""
    try:
        import unicodedata
        return bool(text) and unicodedata.category(text[0]) == "So"
    except Exception:
        return False


async def _chronicle(session, lang: str) -> list[dict[str, Any]]:
    """天记 A Cronica — o que o mundo fez sozinho. SEM `viewer_continent`: nao ha
    viajante nesta superficie, logo nao ha latencia de rumor a aplicar.

    ⚠️ DUAS CORRECCOES QUE SO APARECERAM AO IMPRIMIR O QUE O VISITANTE VE:

    1. **O batimento repete-se.** O World Pulse corre as nove casas no MESMO
       tick, logo as 12 linhas mais recentes eram 7 vezes *"recolhe-se em
       reclusao"*. Dentro do jogo isso le-se como um dia calmo; numa montra
       le-se como um feed partido. Buscamos mais fundo e deixamos no maximo
       `_CHRON_MAX_PER_TYPE` linhas por tipo de acontecimento — o mundo mostra
       a sua VARIEDADE sem que uma unica verdade seja apagada.
    2. **O emoji vinha a dobrar.** `render_chronicle_row` devolve `icon` E um
       `text` que, nas linhas do MV-8/MV-9/MV-11, ja comeca com pictograma
       (`📜 📜 Em Qianhe...`). Aqui o icone so viaja quando a frase nao traz o
       seu.
    """
    from core.world_pulse_engine import list_recent_chronicle
    rows = await list_recent_chronicle(session, limit=CHRONICLE_LIMIT * 4, lang=lang)
    seen: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for r in rows:
        text = r.get("text") or ""
        if not text:
            continue
        etype = str(r.get("event_type") or "")
        n = seen.get(etype, 0)
        if n >= _CHRON_MAX_PER_TYPE:
            continue
        seen[etype] = n + 1
        icon = r.get("sect_emoji") or r.get("icon") or ""
        out.append({"icon": "" if _leading_symbol(text) else icon,
                    "text": text, "ts_ms": r.get("ts_ms")})
        if len(out) >= CHRONICLE_LIMIT:
            break
    return out


async def _ladder(session, lang: str) -> list[dict[str, Any]]:
    """Os que ja subiram. Mesma ordenacao do `api_leaderboard` (cultivacao),
    mesmo filtro de privacidade (`shadow_mode`) — e SEM o fallback para
    `username`: numa pagina publica isso publicaria o @handle do Telegram de
    quem nunca escolheu um nome do Dao."""
    anon = i18n_t(lang, "vit_ladder_anon")
    rows = (await session.execute(
        select(Player.dao_name, Player.realm, Player.sub_layer, Player.prestige_level)
        .where(Player.shadow_mode == False)  # noqa: E712
        .order_by(
            Player.prestige_level.desc(), Player.realm.desc(),
            Player.sub_layer.desc(), Player.cultivation_base.desc(),
        )
        .limit(LADDER_LIMIT)
    )).all()
    out = []
    for i, (dao, realm, sub, prestige) in enumerate(rows):
        r = int(realm or 0)
        out.append({
            "rank": i + 1,
            "name": dao or anon,
            "realm": r,
            "realm_name": REALM_NAMES[r] if 0 <= r < len(REALM_NAMES) else REALM_NAMES[0],
            "realm_emoji": REALM_EMOJIS[r] if 0 <= r < len(REALM_EMOJIS) else REALM_EMOJIS[0],
            "sub_layer": int(sub or 1),
            "prestige": int(prestige or 0),
        })
    return out


async def _pulse(session) -> dict[str, int]:
    """Quatro numeros que provam que o mundo esta ligado. A tribulacao entra
    aqui de proposito: e a mecanica que o Tempo do Ceu morde, e dizer quantos
    raios cairam em 7 dias e a forma mais curta de dizer o que ela e."""
    from database.models import NpcCultivator
    cut = datetime.now(timezone.utc) - timedelta(days=7)
    out: dict[str, int] = {}
    out["players"] = int((await session.execute(
        select(func.count()).select_from(Player))).scalar() or 0)
    out["active_7d"] = int((await session.execute(
        select(func.count()).select_from(Player)
        .where(Player.last_online >= cut))).scalar() or 0)
    try:
        out["npcs"] = int((await session.execute(
            select(func.count()).select_from(NpcCultivator)
            .where(NpcCultivator.status == "active"))).scalar() or 0)
    except Exception:
        logger.exception("vitrine npc count failed")
    try:
        out["trials_7d"] = int((await session.execute(
            select(func.count()).select_from(Tribulation)
            .where(Tribulation.started_at >= cut))).scalar() or 0)
    except Exception:
        logger.exception("vitrine tribulation count failed")
    return out


# ── O ponto de entrada ────────────────────────────────────────────────────────

async def build_world_view(lang: str) -> dict[str, Any]:
    """A vitrine inteira, num payload. O chamador ja ligou o mundo (ContextVar).

    Nunca levanta e nunca devolve vazio: mesmo com TODAS as seccoes em baixo, o
    `chrome` e o convite chegam — a pagina sem mundo continua a ter caminho
    (Lei §1). O consumidor desenha so as seccoes que existem no payload.
    """
    from database.db import get_session_factory

    lang = normalize_lang(lang)
    world: str | None = None
    try:
        from database.db import current_world_key
        world = current_world_key()
    except Exception:
        logger.debug("vitrine world key read failed", exc_info=True)

    view: dict[str, Any] = {
        "ok": True,
        "lang": lang,
        "chrome": _chrome(lang),
        # `web` é o botão PRIMÁRIO desde 2026-08-25 (WEB-B F1): joga-se na aba,
        # sem instalar nada. Caminho RELATIVO de propósito — a porta vive na
        # mesma origem que a vitrine, e assim segue o domínio sem configuração
        # nenhuma (funciona igual em nivrael.com, em staging ou em localhost).
        "cta": {"web": CTA_WEB_URL, "play": CTA_BOT_URL, "group": CTA_GROUP_URL},
    }

    sky = _sky(lang, world)
    if sky:
        view["sky"] = sky

    try:
        async with get_session_factory()() as session:
            view["continents"] = await _safe("continents", _continents(session, lang), [])
            view["houses"] = await _safe("houses", _houses(session, lang), [])
            view["chronicle"] = await _safe("chronicle", _chronicle(session, lang), [])
            view["ladder"] = await _safe("ladder", _ladder(session, lang), [])
            view["pulse"] = await _safe("pulse", _pulse(session), {})
            # Leitura pura: desfaz qualquer transacao implicita que o SQLAlchemy
            # tenha aberto para os SELECTs. Nao existe caminho de commit neste
            # modulo, e este rollback torna isso verificavel.
            await session.rollback()
    except Exception:
        logger.exception("vitrine build failed — a servir so o convite")
        view.setdefault("continents", [])
        view.setdefault("houses", [])
        view.setdefault("chronicle", [])
        view.setdefault("ladder", [])
        view.setdefault("pulse", {})
    return view


async def get_world_view(lang: str) -> dict[str, Any]:
    """`build_world_view` com o cache (`CACHE_TTL_SECONDS`) a frente.

    Chave = (mundo ligado, lingua). O mundo entra na chave porque a vitrine e
    apontavel a qualquer servidor pelo switch `VITRINE_WORLD` — sem ele, virar o
    switch serviria o mundo antigo ate o TTL expirar.

    ⚠️ Sem lock de coalescencia de proposito: o miss e barato (~8 SELECTs) e um
    lock partilhado num processo single-worker seria mais uma peca a poder
    encravar a pagina publica. Um bando simultaneo paga alguns misses e nunca
    fica bloqueado.
    """
    lang = normalize_lang(lang)
    world = "main"
    try:
        from database.db import current_world_key
        world = current_world_key()
    except Exception:
        logger.debug("vitrine cache key world read failed", exc_info=True)
    key = (world, lang)
    now = monotonic()
    hit = _cache.get(key)
    if hit is not None and (now - hit[0]) < CACHE_TTL_SECONDS:
        return hit[1]
    view = await build_world_view(lang)
    _cache[key] = (now, view)
    # O dicionario e limitado por construcao (mundos × 3 linguas), mas a poda
    # mantem-no verdadeiro mesmo se um dia houver dezenas de mundos.
    if len(_cache) > 64:
        for k in [k for k, (ts, _) in _cache.items() if now - ts > CACHE_TTL_SECONDS * 4]:
            _cache.pop(k, None)
    return view
