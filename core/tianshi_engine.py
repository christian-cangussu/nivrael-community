"""MV-11 天时 — O TEMPO DO CÉU (Mundo Vivo v2).

天时地利人和 — *o tempo do Céu · a vantagem da Terra · a harmonia dos homens*.
A vantagem da Terra 地利 já é o MV-3 (estados regionais). A harmonia dos homens
人和 já é o MV-8 (o jiānghú). **天时 é QUANDO** — e é a única das três que este
jogo nunca abriu.

O EIXO GIROU DE ESPAÇO PARA TEMPO, e foi a medição que o girou (recon
2026-08-10, `tools/db_readonly_mv11.py` + `tools/tianshi_sim.py`):

    · viajar ......... 3 jogadores em 30 dias (216 dos 239 nunca saíram de Línghé)
    · mercado ........ 0 compras em 38 dias
    · region_states .. 0 rows em `main` (o MV-3 NUNCA correu lá)
    · TRIBULAÇÃO ..... 713 eventos / 22 jogadores distintos em 30 dias

Um "clima por continente" seria modulação sobre um mundo monocontinental sem
mercado — alcançaria 3 pessoas por mês. A Tribulação alcança **7× mais gente do
que a geografia inteira** e é a única mecânica de alto risco que não depende de
viajar, de mercado, de outro jogador vivo, nem de flag nenhuma. 雷劫 (tribulação
do trovão) e 天时 são o mesmo campo semântico: a cena canônica do gênero é o
cultivador que **espera o céu certo** para romper.

O DESENHO (Q1..Q8 do spec, decididas com medida):

    Q1  DERIVADO. Função pura semeada por `(world_key, epoch)`. ZERO row, ZERO
        tabela, ZERO migration, ZERO job novo, ZERO sweep de órfãos. O
        `tick_epoch` é wall-clock PURO ⇒ **imune ao drift de boot** do World
        Pulse (medido: o batimento andava 00/06/12/18 e passou a 03:52/09:52/
        15:52 porque o trigger de intervalo re-agenda a partir do boot).
    Q2  TRÊS céus (Lei §3 — poucos com dente). ⚠️ O neutro é EXATAMENTE 1.00:
        bônus no estado neutro colapsa o rodízio (medido no MV-9 — uma opção
        saía 22-25× em 28).
    Q3  É do MUNDO, não do continente. Mata de uma vez o problema de Mòyǔ (25,5
        dias parado, fora de TIDE_CONTINENTS e METEOR_CONTINENTS), o veto "5/5
        prospera", a incompatibilidade raiz↔continente e a dependência de
        viajar. **天时 é o primeiro sistema de mundo do jogo que alcança Mòyǔ**
        — porque não é do chão.
    Q4  Morde num ÚNICO chokepoint: `tribulation_engine.get_tribulation_power`.
        ±12% — decidido pela VARREDURA da simulação, não escolhido: 6% é ruído
        (1,7pp mediano, ninguém lê), 20%/30% matam o item de jade que já existe
        (`trib_blessing`, 50 jade, vale +5,5pp). 12% dá 3,3pp mediano / 4,4pp
        máximo e o jade sobrevive. Foi o que SOBROU.
    Q5  As raízes NÃO entram. Refutado por aritmética: `CONTINENT_META["linghe"]
        ["elements"] = ("universal",)` e `universal` não existe em
        `ROOT_ELEMENTS` ⇒ interseção raiz × continente de spawn = **0,00%** no
        continente onde ~100% nasce. `metal` é a raiz de 130 dos 239 jogadores
        e tem 0 continentes e 0 técnicas. 6 dos 12 elementos não têm UMA arte.
    Q6  O céu de amanhã está ESCRITO: a função é pura, logo `sky_for(world,
        epoch+1)` é de graça. É a coisa que **nenhum outro sistema deste jogo
        sabe dizer** — o MV-3 não sabe o próximo estado, o MV-2 não sabe o
        próximo evento, o MV-8 não sabe a próxima marcha.
    Q7  Jade: NÃO. O jade já vende "não esperar"; o céu vende "esperar". É o
        MESMO eixo e é Lei §4-legal desde que (a) o céu nunca seja comprável,
        dissipável ou re-rolável por jade, (b) NENHUM item de jade existente
        passe a escalar COM o céu, (c) a loja não ganhe item novo nesta onda.
    Q8  Conjunção: NENHUMA. Flag única `tempo_do_ceu` — a primeira onda MV sem
        dependência, e pode sê-lo porque é global e morde uma mecânica CORE (a
        tribulação não é gated por nada).

O AGREGADO MEDIDO, sem mudança de comportamento: **−0,04 sucessos/dia** no mundo
inteiro. O céu não é um faucet — é uma ESCOLHA. Todo o valor está em quem decide
esperar, e esperar não imprime nada.

⚠️ A ARMADILHA QUE A SIMULAÇÃO PAGOU (e que qualquer spec escrito da coluna crua
teria repetido): `players.soul_strength` **não é** a alma que enfrenta o raio. O
roll usa `calculate_total_stats(player, equip_stats)["soul_strength"]` — 4-15× a
coluna. Simular pela coluna dá 0,0% de sucesso contra 84,3% REAIS.

A ESPERA É DECISÃO, NUNCA CASTIGO (Lei §1): esperar um céu não-irado é P=75% ⇒
16h em média, a MESMA ordem do cooldown de falha que já existe (6h,
`config.TRIBULATION_COOLDOWN_FAILURE_LIGHT`). E o 🌩️ irado **não tranca nada**:
a tribulação continua disponível, só é mais cara.
"""
from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Gate da flag (molde `caravan_engine._flag` / `city_engine.cidades_on`)
# ══════════════════════════════════════════════════════════════════════════

def _flag(name: str, world_key: str | None = None) -> bool:
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world(name, world_key))
    except Exception:
        return False


def tianshi_on(world_key: str | None = None) -> bool:
    """Gate estável da onda. Flag ÚNICA — sem conjunção (Q8).

    `feature_enabled_for_world` é síncrono e **sem I/O** (lê o registry em
    memória keyed pela ContextVar), logo isto é seguro no chokepoint quente da
    tribulação. Fail-safe → False. Nunca levanta.
    """
    try:
        return _flag("tempo_do_ceu", world_key)
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════
# Tuning (engine, not DB — wipe-safe / launch-server-ready; env-overridable)
# ══════════════════════════════════════════════════════════════════════════

# 12h ⇒ 2 céus por dia, fronteiras às 00h e 12h UTC. Medido em 60 céus:
# sereno 40% · irado 31,7% · velado 28,3%; maior sequência do MESMO céu = 4
# ticks (48h) — o pior caso é ver o mesmo céu 2 dias. Alternativas medidas:
# 24h (espera média de 32h — longo demais) e 6h (espera de 8h mas o céu vira
# ruído: ninguém decide contra uma coisa que muda 4×/dia).
TIANSHI_TICK_HOURS = float(os.getenv("TIANSHI_TICK_HOURS", "12"))

# ⚠️ O neutro é EXATAMENTE 1.00. Ver Q2 — o veto do MV-9 aplica-se à letra.
# Os pesos somam 100 e o irado/velado são simétricos: o céu não é um faucet
# nem um imposto, é uma janela.
SKIES: dict[str, dict[str, Any]] = {
    "sereno": {
        "emoji": "⛅", "mult": 1.00, "weight": 50,
        "name_key": "tsh_sky_sereno", "phrase_key": "tsh_phrase_sereno",
        "chron_key": "tsh_chron_sereno",
    },
    "irado": {
        "emoji": "🌩️", "mult": 1.12, "weight": 25,
        "name_key": "tsh_sky_irado", "phrase_key": "tsh_phrase_irado",
        "chron_key": "tsh_chron_irado",
    },
    "velado": {
        "emoji": "🌫️", "mult": 0.88, "weight": 25,
        "name_key": "tsh_sky_velado", "phrase_key": "tsh_phrase_velado",
        "chron_key": "tsh_chron_velado",
    },
}

# ⚠️ Ordem FIXA e explícita: `random.choices` consome os pesos na ordem das
# chaves, e a ordem de um dict é a de inserção. Se alguém reordenar `SKIES`,
# TODO o histórico do céu muda de significado sem uma linha de diff no
# comportamento aparente. `_ORDER` é o contrato — o teste trava-o.
_ORDER: tuple[str, ...] = ("sereno", "irado", "velado")

CHRON_EVENT_TYPE = "tsh_sky"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════
# A CAMADA PURA — derivada, sem I/O, sem relógio de agendador
# (copiada verbatim de `tools/tianshi_sim.py`, que a validou: DRY_RUN_OK)
# ══════════════════════════════════════════════════════════════════════════

def tick_epoch(now: datetime | None = None) -> int:
    """O batimento do céu. **Wall-clock PURO** — não lê job nenhum, logo é
    imune ao drift de boot do World Pulse (`core/scheduler.py:327-336`)."""
    return int((now or _utcnow()).timestamp() // max(1.0, TIANSHI_TICK_HOURS * 3600.0))


def seed_for(world_key: str, epoch: int) -> str:
    """A semente — com o `world_key` DENTRO (lição MV-8, medida: o World Pulse
    semeava só com `(sect_id, epoch)` e main e s2 contaram a MESMA história
    durante 7 dias). NÃO leva continente: o céu é do MUNDO (Q3)."""
    return f"tianshi:{world_key}:{epoch}"


def sky_for(world_key: str, epoch: int) -> str:
    """O céu daquele mundo naquele batimento. PURA, determinística, sem I/O —
    é isto que torna o FUTURO legível de graça (`epoch + 1`)."""
    rng = random.Random(seed_for(world_key, epoch))
    keys = list(_ORDER)
    return rng.choices(keys, weights=[SKIES[k]["weight"] for k in keys], k=1)[0]


def sky_of(key: str | None) -> dict[str, Any]:
    """A meta de um céu. Fail-safe → o sereno (o neutro de 1.00 exato): um key
    desconhecido nunca pode inventar severidade."""
    return SKIES.get(str(key or ""), SKIES["sereno"])


def next_change_at(now: datetime | None = None) -> datetime:
    """O instante EXATO em que o céu vira (fronteira do próximo epoch)."""
    now = now or _utcnow()
    step = max(1.0, TIANSHI_TICK_HOURS * 3600.0)
    return datetime.fromtimestamp((tick_epoch(now) + 1) * step, tz=timezone.utc)


def hours_to_next(now: datetime | None = None) -> float:
    now = now or _utcnow()
    return max(0.0, (next_change_at(now) - now).total_seconds() / 3600.0)


# ══════════════════════════════════════════════════════════════════════════
# O DENTE — lido pelo chokepoint `get_tribulation_power` (Q4)
# ══════════════════════════════════════════════════════════════════════════

def current_sky(world_key: str | None = None, now: datetime | None = None) -> str | None:
    """A key do céu vigente, ou None com a flag OFF (**sem uma query**)."""
    try:
        if not tianshi_on(world_key):
            return None
        from database.db import current_world_key
        wk = world_key or current_world_key()
        return sky_for(wk, tick_epoch(now))
    except Exception:
        logger.exception("current_sky failed")
        return None


def sky_mult(world_key: str | None = None, now: datetime | None = None) -> float:
    """O multiplicador de SEVERIDADE do céu vigente.

    **Flag OFF → 1.0 sem UMA query** (`feature_enabled_for_world` é sync e lê o
    registry em memória) ⇒ `get_tribulation_power` fica byte-idêntico ao que
    sempre foi. Fail-safe → 1.0: o céu nunca pode impedir uma tribulação.
    """
    try:
        key = current_sky(world_key, now)
        if key is None:
            return 1.0
        return float(sky_of(key)["mult"])
    except Exception:
        logger.exception("sky_mult failed")
        return 1.0


# ══════════════════════════════════════════════════════════════════════════
# A DISCLOSURE — server-resolved ×N superfícies (molde `refine_place_view`)
# Sem isto a onda é decoração, e seria a 4ª modulação MUDA desta casa.
# ══════════════════════════════════════════════════════════════════════════

def _sky_block(lang: str, key: str) -> dict[str, Any]:
    from core.i18n import t as i18n_t
    meta = sky_of(key)
    return {
        "key": key,
        "emoji": str(meta["emoji"]),
        "name": i18n_t(lang, str(meta["name_key"])),
        "phrase": i18n_t(lang, str(meta["phrase_key"])),
        "mult": float(meta["mult"]),
        # Sinalizado e em pontos percentuais INTEIROS: é o número que o jogador
        # repete. 1.12 → +12 ; 0.88 → -12 ; 1.00 → 0.
        "pct": int(round((float(meta["mult"]) - 1.0) * 100)),
    }


def _next_block(lang: str, world_key: str, now: datetime | None = None) -> dict[str, Any]:
    """O ÚNICO futuro escrito deste jogo (Q6) — de graça, porque a função é pura.

    ⚠️ REVIEW ADVERSARIAL 2026-08-10 — **o próximo céu é o MESMO em 37,4% das
    leituras** (medido em 4000 epochs; analítico 0,5²+0,25²+0,25² = 37,5%: os
    epochs são sorteados independentemente, logo repetem). Dizer *"o próximo céu
    — 🌩️ Céu Irado — chega em ~6h"* quando o céu de agora JÁ É irado promete uma
    mudança que não vem — e é justamente na frase-bandeira da onda, a que existe
    para o jogador decidir se espera. Nesses casos a frase muda: o céu CONTINUA.
    """
    from core.i18n import t as i18n_t
    cur_key = sky_for(world_key, tick_epoch(now))
    nxt = _sky_block(lang, sky_for(world_key, tick_epoch(now) + 1))
    nxt["same"] = bool(nxt["key"] == cur_key)
    h = hours_to_next(now)
    # ⚠️ Honestidade > arredondamento (Lei §1): a menos de uma hora, dizer "~1h"
    # seria mentira de até 59 minutos numa frase cuja única função é ajudar
    # alguém a decidir se espera.
    soon = h < 1.0
    nxt["hours"] = 0 if soon else int(round(h))
    if nxt["same"]:
        key = "tsh_next_same_soon" if soon else "tsh_next_same"
    else:
        key = "tsh_next_soon" if soon else "tsh_next_line"
    kw: dict[str, Any] = {"emoji": nxt["emoji"], "name": nxt["name"]}
    if not soon:
        kw["hours"] = nxt["hours"]
    nxt["line"] = i18n_t(lang, key, **kw)
    return nxt


def sky_view(
    lang: str,
    *,
    soul: int | None = None,
    power: float | None = None,
    rounds: int | None = None,
    defense_mult: float = 0.0,
    strategy: str = "resist",
    world_key: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """A linha do céu na tela onde a decisão acontece, com **antes→depois**
    (Lei §10) e com o PRÓXIMO céu escrito (Q6).

    ⚠️ `power` é o valor que o chamador já tem em mão — e ele **JÁ VEM
    MULTIPLICADO** pelo céu, porque o dente vive dentro de
    `get_tribulation_power`. O "antes" é portanto derivado por DIVISÃO
    (`power / mult`), nunca por uma segunda chamada ao chokepoint: uma segunda
    chamada com outro `now` poderia cair no outro lado da fronteira do epoch e
    imprimir um antes→depois que nunca existiu.

    None com a flag OFF (payload byte-idêntico — a key some, não vem `null`).
    Nunca levanta: o céu não pode derrubar a tela da tribulação.
    """
    try:
        if not tianshi_on(world_key):
            return None
        from core.i18n import t as i18n_t
        from database.db import current_world_key
        wk = world_key or current_world_key()
        key = sky_for(wk, tick_epoch(now))
        out = _sky_block(lang, key)
        mult = float(out["mult"])

        before = after = None
        if soul and power and rounds:
            # ⚠️ Os dois números viajam CRUS (o float de 1 casa que
            # `estimate_success_chance` devolve), nunca arredondados: as 3
            # chances já impressas dois centímetros acima imprimem esse mesmo
            # float. Arredondar aqui faria a linha do céu discordar delas — um
            # display-lie por cortesia, e o `after` é literalmente o `resist`
            # que a linha de cima mostra.
            from core.tribulation_engine import estimate_success_chance
            after = estimate_success_chance(int(soul), float(power), strategy,
                                            int(rounds), defense_mult=float(defense_mult))
            base_power = float(power) / mult if mult else float(power)
            before = estimate_success_chance(int(soul), base_power, strategy,
                                             int(rounds), defense_mult=float(defense_mult))
            out["before"] = before
            out["after"] = after

        if mult == 1.0 or before is None:
            # O sereno não tem antes→depois porque não há depois: ×1.00 exato.
            out["line"] = i18n_t(lang, "tsh_trib_line_neutral",
                                 emoji=out["emoji"], name=out["name"], phrase=out["phrase"])
            if after is not None:
                out["line"] += " " + i18n_t(lang, "tsh_trib_chance_flat", chance=after)
        elif before == after:
            # ⚠️ REVIEW ADVERSARIAL 2026-08-10 — O CLAMP ENGOLE O CÉU. A
            # sobrevivência por round é limitada a 0,995 ANTES de ser elevada aos
            # rounds (`tribulation_engine.py:146` e `:207`), logo acima de certa
            # alma o ±12% é integralmente absorvido e o roll fica **genuinamente
            # idêntico**. Reproduzido com a alma CALIBRADA de produção nos
            # reinos-alvo 9 e 10.
            #
            # Desenhar `94.6% → 94.6%` com a cláusula "(-12% de severidade)" ao
            # lado é uma linha que se contradiz a si própria: promete movimento e
            # mostra nenhum. Lei §10 manda mostrar antes→depois — não manda
            # desenhar uma seta quando nada andou. Aqui o honesto é dizer as duas
            # coisas: o céu está lá, e na sua alma ele não move o número.
            out["absorbed"] = True
            out["line"] = i18n_t(
                lang, "tsh_trib_line_absorbed",
                emoji=out["emoji"], name=out["name"], phrase=out["phrase"],
                sign="+" if out["pct"] > 0 else "", pct=out["pct"], chance=after,
            )
        else:
            out["line"] = i18n_t(
                lang, "tsh_trib_line",
                emoji=out["emoji"], name=out["name"], phrase=out["phrase"],
                sign="+" if out["pct"] > 0 else "", pct=out["pct"],
                before=before, after=after,
            )
        out["next"] = _next_block(lang, wk, now)
        return out
    except Exception:
        logger.exception("sky_view failed")
        return None


def sky_plaza_view(
    lang: str,
    world_key: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """A linha do céu na praça — ambiente, SEM números (não há alma nem reino
    no contexto da praça, e inventar uma chance genérica seria um display-lie).
    Diz o que está no ar e o que vem a seguir. None com a flag OFF."""
    try:
        if not tianshi_on(world_key):
            return None
        from core.i18n import t as i18n_t
        from database.db import current_world_key
        wk = world_key or current_world_key()
        out = _sky_block(lang, sky_for(wk, tick_epoch(now)))
        # ⚠️ REVIEW ADVERSARIAL 2026-08-10 — a praça anunciava o HUMOR do céu e
        # nunca o PREÇO: o jogador lia "os raios estão famintos" sem saber se
        # isso vale 1% ou 50%, e o `pct` viajava no payload sem UM leitor (a
        # armadilha do `karma_severity`, que esta onda escreveu um assert para
        # não repetir). O ±12% é universal — não depende de alma nem de reino —
        # logo dizê-lo na praça é honesto, ao contrário de uma chance genérica.
        if out["pct"]:
            out["line"] = i18n_t(lang, "tsh_plaza_line_sev",
                                 emoji=out["emoji"], name=out["name"], phrase=out["phrase"],
                                 sign="+" if out["pct"] > 0 else "", pct=out["pct"])
        else:
            out["line"] = i18n_t(lang, "tsh_plaza_line",
                                 emoji=out["emoji"], name=out["name"], phrase=out["phrase"])
        out["next"] = _next_block(lang, wk, now)
        return out
    except Exception:
        logger.exception("sky_plaza_view failed")
        return None


# ══════════════════════════════════════════════════════════════════════════
# A CRÔNICA — 1 linha por VIRADA de céu, e SÓ quando vira
# (molde literal `city_engine.pulse_cities`, incl. a guarda de duplicados)
# ══════════════════════════════════════════════════════════════════════════

async def pulse_sky(session, now: datetime | None = None) -> dict[str, Any] | None:
    """8º sub-passo do `world_pulse_tick`: se o céu virou desde o batimento
    anterior, a Crônica anuncia. Orçamento medido: main escreve 18-36 linhas/dia
    e s2 23-53 ⇒ **+2 linhas/dia**.

    ZERO estado: o "anterior" é DERIVADO (`sky_for(epoch - 1)`), não guardado.

    ⚠️ IDEMPOTÊNCIA por epoch, não por batimento. O job do pulse tem
    `coalesce=True` + `misfire_grace_time` e o trigger de intervalo re-agenda a
    partir do BOOT — logo um deploy pode fazer o batimento disparar fora da
    grelha e repetir a comparação. Sem esta guarda a mesma virada entrava duas
    vezes, e a Crônica nunca é podada. O `epoch` viaja em `params` justamente
    para ser a chave de deduplicação exata (o molde do MV-9 deduplicava pelo
    conteúdo; aqui a JANELA é a identidade).

    Flag OFF → None sem UMA query. Nunca levanta (o caller é o pulse).
    """
    try:
        if not tianshi_on():
            return None
        from sqlalchemy import select
        from core.world_pulse_engine import emit_chronicle
        from database.db import current_world_key
        from database.models import WorldChronicle

        now = now or _utcnow()
        wk = current_world_key()
        epoch = tick_epoch(now)
        cur = sky_for(wk, epoch)
        prev = sky_for(wk, epoch - 1)
        if cur == prev:
            return {"epoch": epoch, "sky": cur, "changed": 0}

        since = now - timedelta(hours=float(TIANSHI_TICK_HOURS) * 2.0)
        dup = (await session.execute(
            select(WorldChronicle.id).where(
                WorldChronicle.event_type == CHRON_EVENT_TYPE,
                WorldChronicle.ts >= since,
                WorldChronicle.params["epoch"].astext == str(epoch),
            ).limit(1)
        )).scalar_one_or_none()
        if dup is not None:
            return {"epoch": epoch, "sky": cur, "changed": 0, "dup": True}

        await emit_chronicle(
            session,
            event_type=CHRON_EVENT_TYPE,
            text_key=str(sky_of(cur)["chron_key"]),
            params={"epoch": epoch, "sky": cur},
            # continent_key=None de propósito: o céu é GLOBAL. Uma linha sem
            # continente é visível em todas as praças (o filtro do feed é
            # `continent_key == X OR continent_key IS NULL`) — e é a única
            # notícia do jogo que alcança Mòyǔ.
            continent_key=None,
            importance=2,
            now=now,
        )
        return {"epoch": epoch, "sky": cur, "prev": prev, "changed": 1}
    except Exception:
        logger.exception("pulse_sky failed")
        return None
