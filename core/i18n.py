import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_locales: dict[str, dict[str, str]] = {}
_LOCALES_DIR = Path(__file__).parent.parent / "locales"
_DEFAULT_LANG = "pt"
_SUPPORTED_LANGS = {"pt", "en", "es"}

LANG_MAP = {
    "pt": "pt",
    "pt-br": "pt",
    "es": "es",
    "en": "en",
}


def _load_locale(lang: str) -> dict[str, str]:
    if lang in _locales:
        return _locales[lang]

    filepath = _LOCALES_DIR / f"{lang}.json"
    if not filepath.exists():
        filepath = _LOCALES_DIR / f"{_DEFAULT_LANG}.json"

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    _locales[lang] = data
    return data


def t(lang: str, key: str, fallback: str = None, **kwargs) -> str:
    if lang not in _SUPPORTED_LANGS:
        lang = _DEFAULT_LANG

    locale = _load_locale(lang)
    template = locale.get(key)

    if template is None:
        default_locale = _load_locale(_DEFAULT_LANG)
        template = default_locale.get(key)

        if template is None:
            # v15.1.5 hotfix — owner reported "notif[" raw strings leaking to
            # players (e.g. "[notif_quest_completed]"). Previously the fallback
            # was the literal `f"[{key}]"`, which surfaced the raw key in DMs
            # whenever a notify() call referenced a missing locale key.
            #
            # New behaviour:
            #   - Caller-provided `fallback` always wins
            #   - Otherwise we title-case the snake_case key so the player
            #     sees something readable ("Quest Completed" instead of
            #     "[notif_quest_completed]"). Diagnostic still logged so the
            #     missing key can be added in the next i18n pass.
            logger.warning("i18n key missing: lang=%s key=%s", lang, key)
            if fallback is not None:
                return fallback
            cleaned = key.replace("notif_", "").replace("_", " ").strip()
            return cleaned[:1].upper() + cleaned[1:] if cleaned else ""

    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError) as e:
            logger.warning(f"i18n format error: key={key}, lang={lang}, error={e}, kwargs={kwargs}")
            # ⚠️ MV-9 (2026-08-06): devolver o TEMPLATE CRU faz a frase INTEIRA
            # sair em chavetas na cara do jogador — um token em falta arruinava
            # todos os outros, que estavam corretos. É especialmente venenoso nas
            # NOTIFICAÇÕES: `player_notifications` guarda `body_key` + `payload`
            # e renderiza PREGUIÇOSAMENTE na leitura, sem poda nenhuma — logo o
            # dia em que uma string ganha um placeholder novo, TODA linha já
            # gravada (com o payload antigo, sem aquela chave) passa a mostrar o
            # template. Foi o que quase aconteceu ao `notif_bounty_claimed_body`
            # ao ganhar `{city}` nesta onda.
            # Agora degrada só o TOKEN que falta: o resto da frase continua
            # correta. `format_map` com um mapa que devolve "" para o ausente.
            class _Missing(dict):
                def __missing__(self, k):   # noqa: D105
                    return ""
            try:
                return template.format_map(_Missing(kwargs))
            except Exception:
                return template

    return template


def t_optional(lang: str, key: str, fallback: str, **kwargs) -> str:
    """Like :func:`t` but returns ``fallback`` SILENTLY when ``key`` is absent in
    both the requested and the default locale — no missing-key warning, no
    snake_case key-cleaning. For OPTIONAL content overrides (e.g. the per-quest
    ``q_<id>_name`` / ``q_<id>_desc`` sect-quest strings, Pedra 2 wave 2) that may
    or may not exist for a given row: a quest without a localized key just renders
    its stored ``name``/``description`` with zero log spam."""
    if lang not in _SUPPORTED_LANGS:
        lang = _DEFAULT_LANG

    template = _load_locale(lang).get(key)
    if template is None:
        template = _load_locale(_DEFAULT_LANG).get(key)
    if template is None:
        return fallback

    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template


def detect_language(language_code: str | None) -> str:
    if not language_code:
        return _DEFAULT_LANG

    code = language_code.lower().strip()

    if code in LANG_MAP:
        return LANG_MAP[code]

    prefix = code.split("-")[0]
    if prefix in LANG_MAP:
        return LANG_MAP[prefix]

    return _DEFAULT_LANG


def get_supported_languages() -> list[dict]:
    return [
        {"code": "pt", "name": "Português", "flag": "🇧🇷"},
        {"code": "en", "name": "English", "flag": "🇬🇧"},
        {"code": "es", "name": "Español", "flag": "🇪🇸"},
    ]


# ─── 名 O NOME DA PEÇA (2026-09-08) ──────────────────────────────────────────
#
# O PROBLEMA, MEDIDO: `techniques_catalog.name`, `pills_catalog.name`,
# `beasts_catalog.name` e `artifacts.name` eram impressos CRUS. Um jogador
# pt-BR — e o `pt.json` é a língua por omissão do jogo — lia *"Thunder Step"*,
# *"A massive ox whose fur crackles with static electricity"*, *"Next rank:
# Uncommon"*. A arte de 2026-09-06 tornou isso gritante: a ilustração é a peça,
# e por baixo dela estava uma legenda noutra língua.
#
# A DECISÃO (a pergunta que o prompt do lote mandava responder antes de traduzir
# fosse o que fosse — i18n ou coluna nova?):
#
#   **i18n indexada pelo ID do catálogo, resolvida no SERVIDOR.** Porque:
#
#   1. **Já existe e já está provada em produção.** `tech_<id>_name` /
#      `tech_<id>_desc` cobrem 53 artes × 3 línguas desde o TEC-1/TEC-4/TEC-5 e
#      são lidas pelo `sect_library_engine`, pelo `legacy_cave_engine` e pelo
#      `handlers/sect`. Não se inventa um mecanismo quando há um a funcionar.
#   2. **ZERO migration.** Uma coluna `name_pt`/`name_en`/`name_es` seria uma
#      decisão de dia-1 do servidor de launch (Lei §5) e ficaria bloqueada.
#   3. **Reversível e degradável:** chave em falta ⇒ `t_optional` devolve o nome
#      cru, sem log, sem buraco. Traduz-se peça a peça, sem big-bang.
#   4. **Resolve-se no SERVIDOR, e é aqui que a tentativa anterior falhou.** O
#      mini-app tinha 5 chaves `tech_*` de nome na sua própria i18n — e ao
#      contá-las (não presumir) elas têm **ZERO chamadores**: código morto. O
#      motivo é estrutural: o nome vem de uma linha de catálogo que TRÊS
#      superfícies imprimem (chat, mini-app, vitrine). Traduzido no cliente,
#      cada superfície precisa da sua cópia e as três divergem. Traduzido aqui,
#      há uma verdade.
#
# ⚠️ NOME DE PEÇA É CONTEÚDO, não string de UI. "Thunder Step" mal traduzido é
# pior do que em inglês — ver `GameDesign/WUXIA_BIBLE.md` antes de escrever o
# primeiro.

#   · `q` e `boss` entraram a 2026-09-14 **pela mao do owner**: ele mandou uma
#     captura do ecra do Chefe, em espanhol, a dizer "VOID BEAST" e "Attack
#     World Boss — toca para reclamar la recompensa". A contagem deste lote
#     tinha as seis de cima e falhava as DUAS superficies de nome mais vistas
#     do jogo. O prefixo `q_` (e nao `quest_`) e' o que as 32 quests de seita
#     da Pedra 2 ja' usam em producao — uma segunda convencao seria um segundo
#     dono.
_CATALOG_KINDS = {"tech", "pill", "beast", "art", "herb", "ore", "q", "boss",
                  # 旅 2026-09-15 — a EXPEDICAO. Ver `_KEYED_BY_SLUG` abaixo:
                  # esta familia indexa-se pelo SLUG e nao pelo id, porque o
                  # estado da besta guarda o NOME e nao a chave estrangeira.
                  "exped",
                  # 冶 2026-09-29 — o CALDEIRAO. Os 7 nunca tiveram traducao:
                  # um jogador pt lia "Copper Cauldron" no corpo da Alquimia
                  # (o caldeirao e' a figura do oficio na linha do Astra). E'
                  # a 4.a familia a entrar depois de a contagem a falhar; os
                  # ids sao os dos seeds (1..7), estaveis entre mundos.
                  "cauldron"}


def catalog_text(lang: str, kind: str, obj_id, field: str, fallback: str) -> str:
    """O nome/descrição LOCALIZADO de uma linha de catálogo, ou o valor cru.

    `kind` é o prefixo da família (`tech`/`pill`/`beast`/`art`/…), `field` é
    `name` ou `desc`. A chave é `<kind>_<id>_<field>`.

    ⚠️ Nunca levanta: um id nulo, um `kind` desconhecido ou uma chave em falta
    devolvem `fallback`. Uma peça sem tradução mostra o nome do catálogo — que é
    exactamente o que o jogo faz hoje, portanto isto não pode piorar nada.
    """
    if not fallback:
        fallback = fallback or ""
    if obj_id is None or kind not in _CATALOG_KINDS:
        return fallback
    return t_optional(lang, f"{kind}_{obj_id}_{field}", fallback)


# ── 名 2026-09-14 — O DONO ÚNICO, e porque é que `catalog_text` não bastava ──
#
# MEDIDO antes de tocar em nada (Lei 0, passo 1 — CONTAR os sítios):
#
#   · o CONTEÚDO das técnicas está **completo**: `tech_<id>_name`/`_desc`,
#     129 × 2 × 3 línguas, escrito e pago desde o TEC-1/TEC-4/TEC-5.
#   · o ENCANAMENTO chegava a **9 de 41** sítios — e 4 desses 9 eram uma
#     SEGUNDA implementação à mão (`t_optional(lang, f"tech_{id}_name", …)` em
#     `sect_library_engine` e `legacy_cave_engine`), que é exactamente as "duas
#     ligações à mão" que a Lei F-7 §2 proíbe.
#   · consequência: **o chat imprime o nome CRU** das 129 artes (12 leituras só
#     em `handlers/combat.py`) enquanto o mini-app imprime o traduzido. O
#     jogador pt-BR lê "Thunder Step" no chat e "Passo do Trovão" na app —
#     a inconsistência que a Lei 0 diz ser PIOR do que a ausência.
#
# Daí este par. `catalog_text` continua a ser o motor (chave → texto); o que
# faltava era uma porta com a FORMA do sítio que a chama: quem tem uma LINHA de
# catálogo na mão, não um id solto. Os 41 sítios passam a uma chamada de uma
# linha, e a catraca em `scripts/_audit_nomes_crus.py` mede quantos ainda não.
#
# ⚠️ `t_optional` cai no locale POR OMISSÃO (pt) antes de cair no `fallback`.
# Portanto uma chave escrita só em `pt.json` faz um jogador EN ler português —
# pior do que o cru. **A paridade das 3 línguas é de correcção, não de estilo.**

# ⚠️ AS FAMÍLIAS QUE NÃO SE INDEXAM PELO `id` — e porquê (medido 2026-09-14)
#
# `world_bosses.id` é **autoincremento por APARIÇÃO**, não de catálogo: o mesmo
# "Void Beast" nasce com um id novo cada vez que o céu o larga. Uma chave
# `boss_<id>_name` precisaria de uma linha nova por aparição — inútil.
#
# A identidade estável de um chefe é o **nome do molde** (`WORLD_BOSS_POOL`, 9
# entradas). Portanto a chave é `boss_<slug do nome>_name`, e a regra do slug
# vive AQUI, no dono único — se cada chamador fizesse o seu, dois slugs
# divergiriam no dia em que alguém escrevesse "Heaven-Devouring" com outro
# traço (Lei F-7 §2).
# ⚠️ 旅 2026-09-15 — `exped` entra aqui pela MESMA razao do `boss`, mas por um
# caminho diferente e vale dize-lo: o chefe usa o slug porque o `id` e
# autoincremento e muda entre mundos; a EXPEDICAO usa-o porque
# `PlayerBeast.expedition_type` guarda o **nome** e e' com ele que se
# consulta o catalogo. A consulta NAO pode mudar (Lei: a traducao e' de
# DISPLAY), logo a chave tem de ser derivavel do nome sozinho.
_KEYED_BY_SLUG = {"boss", "exped"}


def catalog_slug(text: str) -> str:
    """O slug canónico de um nome de catálogo: minúsculas, `_` entre palavras.

    "Void Beast" → `void_beast` · "Heaven-Devouring Serpent" →
    `heaven_devouring_serpent`. Tudo o que não é letra ou dígito vira `_`, e os
    `_` repetidos colapsam — para que o traço, o apóstrofo e o espaço dêem todos
    o mesmo resultado.
    """
    import re as _re
    return _re.sub(r"_+", "_", _re.sub(r"[^a-z0-9]+", "_", (text or "").lower())).strip("_")


def _catalog_key_part(kind: str, row):
    """O que entra na chave: o `id`, ou o slug do nome nas famílias sem id."""
    if kind in _KEYED_BY_SLUG:
        return catalog_slug(getattr(row, "name", "") or "") or None
    return getattr(row, "id", None)


def catalog_name(lang: str, kind: str, row, *, fallback: str = "") -> str:
    """O NOME localizado de uma linha de catálogo (`row.id` + `row.name`).

    A porta para os ~129 sítios que têm a linha na mão:
    `catalog_name(lang, "tech", tech)` em vez de `tech.name`.

    ⚠️ Nunca levanta: `row=None` devolve `fallback`; uma linha sem `id` ou sem
    chave devolve o nome cru — ou seja, o que o jogo faz hoje.
    """
    if row is None:
        return fallback
    raw = getattr(row, "name", None) or fallback
    return catalog_text(lang, kind, _catalog_key_part(kind, row), "name", raw)


def catalog_art_key(row, *, fallback: str = "") -> str:
    """O nome CANÓNICO (inglês) de uma linha de catálogo — o que nomeia a ARTE.

    🔴 PORQUE ISTO EXISTE, e é a descoberta mais cara de 2026-09-14.

    O cliente constrói o URL da peça a partir do NOME: `pieceArt(kind, x.name)`
    faz `art-` + slug(nome) e pergunta ao `NIV_ART_INDEX` se existe. Enquanto o
    nome do payload era inglês isso funcionava. **No instante em que o nome
    passa a ir traduzido, o slug muda e a peça deixa de ser encontrada** — e não
    dá erro nenhum: a carta cai no verso, que é um estado legítimo, e ninguém
    dá por isso.

        "Void Beast"      → boss-void-beast          ✅ está no índice
        "Besta do Vazio"  → boss-besta-do-vazio      ❌ não está
        "Bestia del Vacío"→ boss-bestia-del-vac-o    ❌ não está

    **MEDIDO: 229 peças por língua.** 128 técnicas + 51 artefactos + 41 pílulas
    + 9 chefes ficam invisíveis em `pt` e em `es`; em `en` não falta nenhuma.

    ⚠️ E **128 dessas já estavam invisíveis em produção desde 2026-09-08**, o
    dia em que as técnicas passaram a sair traduzidas no mini-app: a arte das
    129 artes nunca chegou a um jogador pt ou es. É a mesma avaria que o
    `ARTE_PROVENIENCIA §1.4` registou para os 51 artefactos (arte paga, em
    disco, indexada, invisível por faltar UMA ligação) — uma camada acima.

    A regra que fica: **o nome é para LER, a chave é para ENCONTRAR.** Todo
    payload que leva um nome traduzido leva também esta chave ao lado, e o
    cliente desenha com esta, nunca com aquele.
    """
    return getattr(row, "name", None) or fallback


def catalog_desc(lang: str, kind: str, row, *, fallback: str = "") -> str:
    """A DESCRIÇÃO localizada de uma linha de catálogo (`row.id` + `row.description`).

    A chave é `<kind>_<id>_desc` — **`desc`, não `description`**, porque é a
    forma que as 129 técnicas já usam em produção e uma segunda convenção seria
    um segundo dono.
    """
    if row is None:
        return fallback
    raw = getattr(row, "description", None) or fallback
    return catalog_text(lang, kind, _catalog_key_part(kind, row), "desc", raw)
