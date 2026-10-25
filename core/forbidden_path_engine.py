"""TEC-5 — Forbidden Path 禁道 "Caminho Proibido" (Constituição §5, Q-5 respondida).

O poder que a casa demoníaca guarda no **Cofre Proibido 禁库** (tier 6 da
Biblioteca, só `abyssal_depths`) não se compra: paga-se em karma e em ANOS.

As 5 peças (spec `Prompts/tec5_forbidden_path.md`):

  (a) **O Cofre Proibido** — tier 6 no `sect_library_engine` (gates heir → path
      demonic → karma ALINHADO ≥ FP_KARMA_MIN → registro do Rito → SEM CP).
  (b) **O custo REAL por uso** — cobrado no SETTLE varrendo o `action_log`
      (padrão PROVADO do Intent XP): `forbidden_tech_use` (−20 karma, o
      consumidor órfão que o catálogo precificou desde a v16.3) + ANOS queimados
      do Mar de Longevidade (`players.age_years`, Mig 121 — este sprint é o 1º
      WRITER da coluna) + a trava honesta: teto esgotado ⇒ a arte RECUSA.
      Fora do DuelSession as artes proibidas **não somam** (exclusão no
      `build_fighter_data` + no somador do World Boss) — a vitrine DIZ.
  (c) **O Rito do Coração-Demônio 心魔** — o corpo do stub `api_heart_demon_start`
      ("v16.7 will replace the body..."): duelo contra O REFLEXO (o próprio
      jogador), vencer ⇒ ATRAVESSAR (re-cristaliza o Path — a pendência
      estrutural karma→Path paga aqui) ou REAFIRMAR; perder ⇒ o Coração morde
      `soul_strength` e volta depois do cooldown (nunca dead-end).
  (d) **O gatilho Xuèyè** — atravessar para demonic acorda a tumba de Lǐ Xuèyè
      em Mòyǔ (força a casa `xueye` no `maybe_open_cave` do TEC-4, respeitando
      TODOS os guards vivos) + o "A Noite de Sangue viu você" no clear.
  (e) **A severidade de tribulação** — `get_tribulation_modifier` (1.5/2/3× por
      |karma|) finalmente WIRED: era display-lie desde a v16.3.

Arquitetura (padrão legacy_cave_engine/profession_engine):
  · flag `forbidden_path` OFF ⇒ **zero queries** em toda função pública, e
    `forbidden_ids()` devolve conjunto VAZIO ⇒ os somadores ficam
    byte-idênticos (OFF-identity, Lei §5);
  · ZERO migration: custo = colunas da Mig 121 · registros do Rito = `karma_log`
    (precedente `path_crystallized`, 2026-07-30) · tentativa/cooldown =
    `duel_sessions` (índice parcial da Mig 094) · Xuèyè = payload de
    `world_events`;
  · knobs env `FP_*` (a UI recebe os números no payload — nunca hardcodar no
    cliente);
  · todo write num `begin_nested()` PRÓPRIO (somos chamados de dentro do
    try/except do settle, que NÃO tem savepoint — lição TEC-4 §F7-R6).

Calibração do relógio (§3.1 do spec — verificação herdada, feita com a tabela
REAL): `REALM_LIFESPAN` dá 15.000 anos no R7 e 50.000 no R8, então o default do
spec ("FP_YEARS_PER_USE 1 × req_realm" = 8 anos/uso) precisaria de **6.250 usos**
para o teto morder — o custo seria invisível, i.e. custo nenhum (Lei §1). O
default assado passa a ser **por-mil do teto DO PRÓPRIO cultivador**
(`FP_BURN_PERMIL` 1.25 ⇒ ~800 usos até o teto, "meses de uso pesado" como o §3.1
pede) — e como o teto SOBE a cada reino, avançar ALIVIA o relógio: a saída
existe sempre (Lei §1) e é a saída Wuxia (subir, não parar). No ápice imortal
(teto ∞) o relógio deixa de existir — canon do `lifespan_engine` — e o preço
continua a ser karma + os céus mais duros.
"""
from __future__ import annotations

import logging
import os
import random as _random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from database.models import DuelSession, KarmaLog, Player, TechniqueCatalog

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Flag + knobs
# ══════════════════════════════════════════════════════════════════════════

def forbidden_on(world_key: str | None = None) -> bool:
    """Gate estável da flag per-world `forbidden_path` (padrão legacy_caves_on).
    Fail-safe → False. SYNC e sem I/O (registry em memória) — seguro no settle."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("forbidden_path", world_key))
    except Exception:
        return False


def vault_on(world_key: str | None = None) -> bool:
    """O Cofre Proibido exige a Biblioteca (TEC-1) E as estantes seladas (TEC-3)
    — sem elas não há estante onde a 6ª caber. Conjunção AQUI (uma verdade),
    como o `selado_on` faz com `biblioteca_seitas`: ligar só `forbidden_path`
    num mundo sem Biblioteca não meio-abre o Cofre, simplesmente não o abre.
    O custo por uso, o Rito e a severidade NÃO dependem disto — só a estante."""
    try:
        from core.sect_library_engine import selado_on
        return forbidden_on(world_key) and selado_on(world_key)
    except Exception:
        return False


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Karma ALINHADO mínimo do Cofre (`aligned_karma`: −karma numa casa demoníaca).
# 500 = o número da DIVERGÊNCIA: o Cofre só abre para quem já passou do ponto
# em que o Céu o chama de volta. (A Estante Oculta pede 250.)
FP_KARMA_MIN = _env_int("FP_KARMA_MIN", 500)
# Anos queimados por uso = por-mil do teto do PRÓPRIO cultivador (ver docstring).
FP_BURN_PERMIL = _env_float("FP_BURN_PERMIL", 1.25)
FP_BURN_MIN_YEARS = _env_int("FP_BURN_MIN_YEARS", 1)
# A mordida do Coração-Demônio na derrota (fração de soul_strength, piso).
FP_HD_SOUL_PCT = _env_float("FP_HD_SOUL_PCT", 0.02)
FP_HD_SOUL_MIN = _env_int("FP_HD_SOUL_MIN", 10)
FP_RITE_COOLDOWN_H = _env_int("FP_RITE_COOLDOWN_H", 24)
# Chance de a tumba de Lǐ Xuèyè despertar quando alguém ATRAVESSA para demonic.
FP_XUEYE_CHANCE = _env_float("FP_XUEYE_CHANCE", 0.5)

# O conjunto proibido v1: a Sutra de Sangue da gruta (TEC-4) + as 3 do Cofre.
VAULT_TECH_IDS: frozenset[int] = frozenset({605, 606, 607})
FORBIDDEN_TECH_IDS: frozenset[int] = frozenset({604}) | VAULT_TECH_IDS
FORBIDDEN_TIER = 6                      # a estante do Cofre
FORBIDDEN_SECT = "abyssal_depths"       # a única casa que o guarda

HD_PVE_SOURCE = "heart_demon"           # ≤ 24 chars (duel_sessions.pve_source)
HD_EVENT_CROSSED = "heart_demon_crossed"
HD_EVENT_STOOD = "heart_demon_stood"
HD_EVENT_FELL = "heart_demon_fell"
# Os 3 acima ficam FORA de KARMA_EVENTS de propósito (precedente
# `path_crystallized`): entram no log com delta 0 e o dicionário canônico é a
# lista "o que muda o meu karma" — um evento de delta 0 ali seria mentira.
HD_EVENTS: tuple[str, ...] = (HD_EVENT_CROSSED, HD_EVENT_STOOD, HD_EVENT_FELL)
HD_RECORD_EVENTS: tuple[str, ...] = (HD_EVENT_CROSSED, HD_EVENT_STOOD)


def forbidden_ids(world_key: str | None = None) -> frozenset[int]:
    """As artes proibidas ATIVAS agora — UMA verdade lida por todo somador.
    Flag OFF ⇒ `frozenset()` ⇒ nenhum filtro morde e o cálculo é byte-idêntico
    (a lição do `library_tiers()`: a constante do engine não é a resposta)."""
    return FORBIDDEN_TECH_IDS if forbidden_on(world_key) else frozenset()


def is_forbidden(tech_id: Any, world_key: str | None = None) -> bool:
    try:
        return int(tech_id or 0) in forbidden_ids(world_key)
    except (TypeError, ValueError):
        return False


def effective_karma_cost(karma: Any) -> int:
    """O karma que ESTE cultivador realmente paga por uso (valor absoluto).

    `apply_karma` clampa em `KARMA_BOUNDS`, e o gate do Cofre exige karma
    alinhado ≥ 500 — i.e. um demoníaco a caminho do piso −1000. A partir do
    piso o preço em karma é **zero**, e a vitrine que continuasse a anunciar 20
    estaria a mentir (review adversarial). Aqui a vitrine passa a dizer o que o
    settle vai debitar."""
    try:
        from core.karma_engine import _clamp_karma
        k = int(karma or 0)
        return abs(_clamp_karma(k + int(_karma_cost())) - k)
    except Exception:
        return abs(int(_karma_cost()))


def knobs_payload(karma: Any = None) -> dict[str, Any]:
    """Os números que a vitrine DIZ (display = roll, Lei §1/§10). Viajam no
    payload — o cliente nunca os hardcoda. Com `karma` dado, `karma_cost` é o
    preço EFETIVO deste cultivador (0 quando ele já tocou o fundo)."""
    out = {
        "karma_cost": abs(int(_karma_cost())),
        "burn_permil": float(FP_BURN_PERMIL),
        "karma_min": int(FP_KARMA_MIN),
        "cooldown_h": int(FP_RITE_COOLDOWN_H),
        "soul_pct": float(FP_HD_SOUL_PCT),
    }
    if karma is not None:
        out["karma_cost"] = effective_karma_cost(karma)
        out["karma_floored"] = out["karma_cost"] == 0
    return out


def _karma_cost() -> int:
    """O delta canônico de `forbidden_tech_use` (−20). Lido do catálogo do
    karma_engine — nunca duplicado aqui (uma verdade, knob do owner)."""
    try:
        from core.karma_engine import get_karma_event_delta
        return int(get_karma_event_delta("forbidden_tech_use"))
    except Exception:
        return -20


# ══════════════════════════════════════════════════════════════════════════
# (b) O custo — o Mar de Longevidade 寿海 paga cada uso
# ══════════════════════════════════════════════════════════════════════════

def years_per_use(player: Any) -> int:
    """Anos queimados por uso: por-mil do teto DO CULTIVADOR (piso
    `FP_BURN_MIN_YEARS`). `0` no ápice imortal — quem escapou do ciclo não tem
    relógio para queimar (canon `lifespan_engine`); o preço dele é o karma."""
    try:
        from core.lifespan_engine import lifespan_ceiling
        ceiling = lifespan_ceiling(player)
        if ceiling is None:
            return 0
        return max(int(FP_BURN_MIN_YEARS),
                   int(round(float(ceiling) * float(FP_BURN_PERMIL) / 1000.0)))
    except Exception:
        logger.debug("years_per_use failed", exc_info=True)
        return max(1, int(FP_BURN_MIN_YEARS))


def lifespan_state(player: Any) -> dict[str, Any]:
    """O relógio como DADO (Lei §1/§10): idade queimada, teto, o que resta e o
    preço do próximo uso. Puro. `immortal` ⇒ o relógio não segura mais."""
    try:
        from core.lifespan_engine import lifespan_ceiling
        ceiling = lifespan_ceiling(player)
        age = int(getattr(player, "age_years", 0) or 0)
        per_use = years_per_use(player)
        return {
            "age_years": age,
            "ceiling": ceiling,
            "immortal": ceiling is None,
            "left": None if ceiling is None else max(0, int(ceiling) - age),
            "years_per_use": per_use,
            "uses_left": None if (ceiling is None or per_use <= 0)
            else max(0, (max(0, int(ceiling) - age)) // per_use),
            "spent": age > 0,
        }
    except Exception:
        logger.debug("lifespan_state failed", exc_info=True)
        return {"age_years": 0, "ceiling": None, "immortal": True,
                "left": None, "years_per_use": 0, "uses_left": None, "spent": False}


def lifespan_gate_ok(player: Any, pending_uses: int = 0) -> bool:
    """A trava honesta: com o Mar esgotado a arte proibida RECUSA (o 1º dente do
    relógio). Puro — o caller já tem o Player. Imortal ⇒ sempre True.
    `pending_uses` = usos já lançados nesta luta e ainda não cobrados (o débito
    só cai no settle)."""
    st = lifespan_state(player)
    if st["immortal"] or st["ceiling"] is None:
        return True
    spent = int(st["age_years"]) + int(st["years_per_use"]) * max(0, int(pending_uses))
    return spent + int(st["years_per_use"]) <= int(st["ceiling"])


async def forbidden_use_gate(session, player_id: int, tech_id: int,
                             duel=None, side_key: str | None = None) -> dict[str, Any]:
    """O gate do `submit_action`: pode ESTA arte ser lançada agora?

    Flag OFF ou arte comum ⇒ ``{"ok": True}`` **sem query** (OFF-identity: o
    duelo de main nunca toca a DB por causa disto). Recusa NOMEADA quando o Mar
    de Longevidade não paga mais (padrão `not_enough_combat_qi`, Lei §1).

    `duel`/`side_key` (review adversarial): o débito só é escrito no SETTLE, então
    ler apenas `players.age_years` avaliaria a MESMA idade pré-duelo em todas as
    rodadas — quem visse *"resta 1 uso"* poderia lançar a arte a cada rodada que o
    pool pagasse. Contamos os usos JÁ registrados NESTE duelo e somamos ao relógio
    antes de decidir: a recusa passa a cair no uso certo, dentro da luta."""
    if not is_forbidden(tech_id):
        return {"ok": True}
    try:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == int(player_id))
        )).scalar_one_or_none()
        if player is None:
            return {"ok": True}          # nunca prender o duelo por um read falho
        pending = 0
        if duel is not None and side_key:
            pending = sum(count_forbidden_uses(
                getattr(duel, "action_log", None), side_key).values())
        if lifespan_gate_ok(player, pending_uses=pending):
            return {"ok": True}
        st = lifespan_state(player)
        return {"ok": False, "reason": "forbidden_lifespan_spent",
                "age_years": st["age_years"] + pending * st["years_per_use"],
                "ceiling": st["ceiling"],
                "years_per_use": st["years_per_use"]}
    except Exception:
        logger.debug("forbidden_use_gate failed (player=%s tech=%s)",
                     player_id, tech_id, exc_info=True)
        return {"ok": True}


def count_forbidden_uses(action_log: list | None, side_key: str,
                         ids: frozenset[int] | None = None) -> dict[int, int]:
    """Conta os usos de arte proibida de UM lado do duelo (espelho exato do
    `_count_tech_activations` dos settles — a mesma leitura de `action_log`
    que o Intent XP provou). Puro."""
    banned = FORBIDDEN_TECH_IDS if ids is None else ids
    counts: dict[int, int] = {}
    if not banned:
        return counts
    for entry in action_log or []:
        if not isinstance(entry, dict):
            continue
        side = entry.get(side_key)
        if not isinstance(side, dict):
            continue
        # `fpd` é a marca do SWING (gravada no _resolve_round); `tech` é o golpe
        # que ATERROU e some numa esquiva/desvio. O uso é o swing — o qi foi
        # gasto e a arte foi lançada.
        tid = 0
        try:
            tid = int(side.get("fpd") or 0)
        except (TypeError, ValueError):
            tid = 0
        if not tid:
            tech = side.get("tech")
            if not isinstance(tech, dict):
                continue
            try:
                tid = int(tech.get("id") or 0)
            except (TypeError, ValueError):
                continue
        if tid in banned:
            counts[tid] = counts.get(tid, 0) + 1
    return counts


FPD_LOG_MARKER = "fpd_cost"


def stamp_forbidden_cost(duel, side_key: str, cost: dict[str, Any]) -> None:
    """Carimba o custo no `action_log` — o ÚNICO carregador que os TRÊS settles
    têm em comum (só o PvE tem `payload` no marker `pve_settled`; PvP liquida
    em PVPChallenge e a arena em ArenaQueue). Fica visível de graça no
    `get_duel_state` e as duas superfícies leem pelo mesmo helper."""
    duel.action_log = (duel.action_log or []) + [{
        "round": int(getattr(duel, "round_idx", 0) or 0),
        "type": FPD_LOG_MARKER,
        "side": side_key,
        "payload": cost,
    }]
    try:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(duel, "action_log")
    except Exception:
        # O carimbo é o CARREGADOR, não o custo. Se o flag falhar, o débito já
        # aconteceu e o payload ainda tem de chegar ao jogador (Lei §1) — quem
        # levanta aqui não pode engolir o cartão inteiro.
        logger.debug("stamp_forbidden_cost flag_modified failed", exc_info=True)


def read_forbidden_cost(duel, side_key: str) -> dict[str, Any] | None:
    """O custo carimbado deste lado (ou ``None``). Puro — as superfícies leem
    daqui, nunca re-derivam (display = roll)."""
    for entry in reversed((getattr(duel, "action_log", None) or [])):
        if (isinstance(entry, dict) and entry.get("type") == FPD_LOG_MARKER
                and entry.get("side") == side_key):
            return entry.get("payload")
    return None


def side_of_player(duel, player_id: int) -> str | None:
    """O lado deste jogador no duelo ('a'/'b'), ou None. Puro."""
    try:
        pid = int(player_id)
    except (TypeError, ValueError):
        return None
    if int(getattr(duel, "attacker_id", 0) or 0) == pid:
        return "a"
    if int(getattr(duel, "defender_id", 0) or 0) == pid:
        return "b"
    return None


async def charge_all_sides(session, duel) -> None:
    """**O ÚNICO ponto de cobrança** — chamado por `apply_post_duel_effects`, por
    onde TODO duelo terminal passa.

    Estava nos 3 settles e o review adversarial provou o furo: um duelo direto
    (`combat/duel_create`) não tem `PVPChallenge` nem `ArenaQueue` nem
    `pve_source`, e `settle_pvp_duel` desiste ANTES de cobrar (`challenge is
    None → return False`) — o poder proibido saía de graça exatamente na
    superfície onde dois jogadores combinam a luta.

    Idempotente pelo marker `fpd_cost` no próprio `action_log` (o mesmo padrão
    do `hp_drained` logo acima do call site). Flag OFF ⇒ retorno imediato sem
    query. Nunca levanta: o custo nunca pode derrubar a liquidação do duelo."""
    if not forbidden_ids() or duel is None:
        return
    try:
        if any(isinstance(e, dict) and e.get("type") == FPD_LOG_MARKER
               for e in (duel.action_log or [])):
            return                       # já cobrado neste duelo
        for side, pid in (("a", getattr(duel, "attacker_id", None)),
                          ("b", getattr(duel, "defender_id", None))):
            if not pid:                  # None/0 = o NPC não paga karma nem anos
                continue
            if not count_forbidden_uses(duel.action_log, side):
                continue
            player = (await session.execute(
                select(Player).where(Player.telegram_id == int(pid)).with_for_update()
            )).scalar_one_or_none()
            if player is None:
                continue
            await charge_and_stamp(session, duel, player, side)
    except Exception:
        logger.exception("charge_all_sides failed (duel=%s)", getattr(duel, "id", None))


async def charge_and_stamp(session, duel, player, side_key: str) -> dict[str, Any] | None:
    """`charge_forbidden_uses` + o carimbo no log. O UM helper que os 3 settles
    chamam (o Intent XP mostrou que este é o lugar certo). Nunca levanta."""
    cost = None
    try:
        cost = await charge_forbidden_uses(session, duel, player, side_key)
    except Exception:
        logger.exception("charge_forbidden_uses failed (duel=%s side=%s)",
                         getattr(duel, "id", None), side_key)
        return None
    if not cost:
        return None
    try:
        stamp_forbidden_cost(duel, side_key, cost)
    except Exception:
        # O carimbo falhou, o débito não: devolvemos o custo assim mesmo para
        # que o payload do settle (PvE) ainda o mostre.
        logger.exception("stamp_forbidden_cost failed (duel=%s side=%s)",
                         getattr(duel, "id", None), side_key)
    return cost


async def charge_forbidden_uses(session, duel, player, side_key: str) -> dict[str, Any] | None:
    """O settle-hook: cobra karma + anos por cada uso de arte proibida do lado
    `side_key`. Chamado pelos 3 settles (arena/pvp/pve) no MESMO lugar do Intent
    XP. Devolve o bloco `forbidden_cost` (com antes→depois, Lei §10) ou ``None``
    quando não houve uso — key CONDICIONAL, payload OFF byte-idêntico.

    `begin_nested()` PRÓPRIO: o settle nos chama dentro de um try/except SEM
    savepoint, e um erro aqui envenenaria a transação inteira do duelo."""
    ids = forbidden_ids()
    if not ids or player is None:
        return None
    uses = count_forbidden_uses(duel.action_log if duel is not None else None,
                                side_key, ids)
    total = sum(uses.values())
    if total <= 0:
        return None

    player_id = int(player.telegram_id)
    age_before = int(getattr(player, "age_years", 0) or 0)
    per_use = years_per_use(player)
    burned = int(per_use) * int(total)
    # O relógio nunca passa do próprio teto (review adversarial): a trava do
    # `submit_action` conta os usos da luta, mas rodadas resolvidas em paralelo
    # ou um log herdado podiam empurrar `age_years` para além do Mar. Cobramos
    # até secar — e o número DITO é o cobrado (display = roll).
    _ceiling = lifespan_state(player)["ceiling"]
    if _ceiling is not None:
        burned = max(0, min(burned, int(_ceiling) - age_before))
    karma_before = int(getattr(player, "karma", 0) or 0)

    try:
        async with session.begin_nested():
            if burned > 0:
                player.age_years = age_before + burned
    except Exception:
        logger.exception("charge_forbidden_uses: lifespan write failed (duel=%s)",
                         getattr(duel, "id", None))
        burned = 0

    # O karma passa pelo mutador canônico (SAVEPOINT próprio + log + achievements
    # + o DM de divergência): UM evento por USO, como o catálogo precificou.
    karma_after = karma_before
    karma_delta = 0
    diverged = False
    try:
        from core.karma_engine import apply_karma
        for _ in range(total):
            res = await apply_karma(
                session, player_id, "forbidden_tech_use",
                metadata={"duel_id": str(getattr(duel, "id", "")), "uses": total},
            )
            if not res or not res.get("ok"):
                break
            karma_after = int(res.get("new_value", karma_after))
            diverged = bool(res.get("diverged")) or diverged
        karma_delta = karma_after - karma_before
    except Exception:
        logger.exception("charge_forbidden_uses: karma failed (duel=%s)",
                         getattr(duel, "id", None))

    st = lifespan_state(player)
    out: dict[str, Any] = {
        "uses": int(total),
        "by_tech": {str(k): int(v) for k, v in uses.items()},
        "years_burned": int(burned),
        "years_per_use": int(per_use),
        "age_before": age_before,
        "age_after": int(getattr(player, "age_years", 0) or 0),
        "ceiling": st["ceiling"],
        "immortal": bool(st["immortal"]),
        "karma_before": karma_before,
        "karma_after": karma_after,
        "karma_delta": int(karma_delta),
        "exhausted": bool(not lifespan_gate_ok(player)),
    }
    if diverged:
        out["diverged"] = True
    return out


# ══════════════════════════════════════════════════════════════════════════
# (c) O Rito do Coração-Demônio 心魔 — o corpo do stub
# ══════════════════════════════════════════════════════════════════════════

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def rogue_divergence_threshold() -> int:
    """|karma| a partir do qual um ERRANTE cristalizado também diverge. É o
    MESMO número dos outros dois caminhos (500) — não inventamos régua nova."""
    try:
        from core.karma_engine import KARMA_DIVERGENCE_THRESHOLDS
        return abs(int(KARMA_DIVERGENCE_THRESHOLDS.get("demonic", 500)))
    except Exception:
        return 500


def path_aligned_karma(karma: Any, path: str | None) -> int:
    """Quão fundo o cultivador andou a estrada DELE (não a da casa).

    `-karma` no caminho demoníaco, `+karma` no justo — a mesma operação que o
    `aligned_karma` do TEC-3 faz com a seita. O Errante não tem profundidade
    (a neutralidade não se aprofunda): devolve 0."""
    try:
        k = int(karma or 0)
    except (TypeError, ValueError):
        return 0
    if path == "demonic":
        return -k
    if path == "righteous":
        return k
    return 0


def deep_on_path(karma: Any, path: str | None) -> bool:
    """O 2º gatilho do Coração-Demônio: ir FUNDO DEMAIS na própria estrada.

    Sem isto o Cofre Proibido era **inalcançável por construção** — o gate dele
    pede karma ALINHADO ≥ 500 (i.e. karma ≤ −500 num demoníaco) E o registro do
    Rito, mas o Rito só abria por DIVERGÊNCIA, que num demoníaco dispara a
    karma ≥ **+500**: os dois requisitos eram exatamente inversos e nenhum
    cultivador podia satisfazer ambos (achado do review adversarial).

    E é o 心魔 mais canônico dos dois: o Coração-Demônio não vem só para quem
    trai o caminho — vem, sobretudo, para quem desce fundo demais nele. Aqui
    não há para onde atravessar (você JÁ é isso): vencer só oferece REAFIRMAR,
    que é exatamente o que o Cofre pede ("já atravessou **ou reafirmou**")."""
    return path_aligned_karma(karma, path) >= int(FP_KARMA_MIN)


def rogue_divergence(karma: Any, world_key: str | None = None) -> dict[str, Any]:
    """A válvula do Errante (o caso [jogador]), FLAG-GATED.

    Canon ajustado e documentado: *"a neutralidade nunca é errada — mas um
    Errante a −500 não é neutro; é um mentiroso."* Com a flag OFF devolve
    sempre `não divergiu` ⇒ `_divergence_for_path_and_karma` fica byte-idêntico
    para os 3 consumidores (apply_karma · api_player · KarmaModal)."""
    if not forbidden_on(world_key):
        return {"diverged": False, "threshold": None}
    try:
        k = int(karma or 0)
    except (TypeError, ValueError):
        return {"diverged": False, "threshold": None}
    thr = rogue_divergence_threshold()
    if k >= thr:
        return {"diverged": True, "threshold": thr, "toward": "righteous"}
    if k <= -thr:
        return {"diverged": True, "threshold": -thr, "toward": "demonic"}
    # O alvo é o lado para onde o karma já pende (disclosure do "falta quanto").
    return {"diverged": False, "threshold": thr if k >= 0 else -thr,
            "toward": "righteous" if k >= 0 else "demonic"}


def diverged_target_path(path: str | None, karma: int) -> str | None:
    """Para QUAL caminho o Coração-Demônio puxa. `righteous` afundado em malícia
    vira `demonic` e vice-versa; o Errante vai para o lado do próprio sinal."""
    try:
        k = int(karma or 0)
    except (TypeError, ValueError):
        return None
    if path == "righteous":
        return "demonic"
    if path == "demonic":
        return "righteous"
    if path == "rogue":
        return "righteous" if k >= 0 else "demonic"
    return None


async def _last_rite_duel(session, player_id: int):
    """O último Rito deste cultivador (aberto ou terminal) — índice parcial da
    Mig 094 (`attacker_id, pve_source`). Zero coluna nova."""
    return (await session.execute(
        select(DuelSession).where(
            DuelSession.attacker_id == int(player_id),
            DuelSession.pve_source == HD_PVE_SOURCE,
        ).order_by(DuelSession.created_at.desc()).limit(1)
    )).scalar_one_or_none()


async def _rite_records(session, player_id: int) -> dict[str, Any]:
    """O que o `karma_log` guarda deste cultivador sobre o Rito: se já fez a
    escolha alguma vez (a chave do Cofre) e quais duelos já foram escolhidos."""
    rows = (await session.execute(
        select(KarmaLog.event_type, KarmaLog.metadata_).where(
            KarmaLog.player_id == int(player_id),
            KarmaLog.event_type.in_(list(HD_EVENTS)),
        )
    )).all()
    chosen_duels: set[str] = set()
    faced = False
    for ev, meta in rows:
        if ev in HD_RECORD_EVENTS:
            faced = True
        did = str((meta or {}).get("duel_id") or "")
        if did and ev in HD_RECORD_EVENTS:
            chosen_duels.add(did)
    return {"faced": faced, "chosen_duels": chosen_duels}


async def rite_passed(session, player_id: int) -> bool:
    """True se este cultivador JÁ encarou o Coração-Demônio e escolheu
    (atravessar OU reafirmar) — o registro eterno que abre o Cofre. Ficar
    também conta: a escolha de permanecer é uma escolha."""
    try:
        return bool((await _rite_records(session, player_id))["faced"])
    except Exception:
        logger.debug("rite_passed failed (player=%s)", player_id, exc_info=True)
        return False


async def heart_demon_state(session, player) -> dict[str, Any]:
    """O estado do Rito para as superfícies (Lei §1 — o requisito é DITO).

    ``{on, diverged, current_path, target_path, karma, faced, open_duel_id,
    pending_choice_duel_id, cooldown_ms, can_start, threshold}``.
    Flag OFF ⇒ ``{"on": False}`` SEM query. Nunca levanta."""
    if not forbidden_on():
        return {"on": False}
    out: dict[str, Any] = {
        "on": True, "diverged": False, "deep": False,
        "current_path": getattr(player, "path", None),
        "target_path": None, "karma": int(getattr(player, "karma", 0) or 0),
        "faced": False, "open_duel_id": None, "pending_choice_duel_id": None,
        "cooldown_ms": None, "can_start": False, "threshold": None,
        "cooldown_h": int(FP_RITE_COOLDOWN_H),
    }
    try:
        from core.karma_engine import _divergence_for_path_and_karma
        player_id = int(player.telegram_id)
        karma = int(getattr(player, "karma", 0) or 0)
        path = getattr(player, "path", None)
        div = _divergence_for_path_and_karma(path, karma)
        out["diverged"] = bool(div.get("diverged"))
        out["threshold"] = div.get("threshold")
        # Duas portas para o Reflexo: a DIVERGÊNCIA (o Céu te chama de volta —
        # e aí há para onde atravessar) e a PROFUNDIDADE (você foi fundo demais
        # na sua própria estrada — não há travessia, só a reafirmação).
        out["deep"] = bool(deep_on_path(karma, path)) and not out["diverged"]
        out["target_path"] = diverged_target_path(path, karma) if out["diverged"] else None
        if out["deep"]:
            out["deep_need"] = int(FP_KARMA_MIN)
            out["deep_have"] = path_aligned_karma(karma, path)

        recs = await _rite_records(session, player_id)
        out["faced"] = bool(recs["faced"])

        duel = await _last_rite_duel(session, player_id)
        if duel is not None:
            if duel.state in ("waiting_actions", "pending_acceptance"):
                out["open_duel_id"] = str(duel.id)
                return out
            won = (duel.winner_id == player_id and duel.state == "finished")
            if won and str(duel.id) not in recs["chosen_duels"]:
                # Venceu e ainda não escolheu — a escolha É o próximo passo
                # (nunca um duelo novo por cima de uma escolha pendente).
                out["pending_choice_duel_id"] = str(duel.id)
                return out
            resolved = _aware(duel.resolved_at)
            if resolved is not None:
                until = resolved + timedelta(hours=max(0, FP_RITE_COOLDOWN_H))
                if until > _utcnow():
                    out["cooldown_ms"] = int(until.timestamp() * 1000)
                    return out
        out["can_start"] = bool(out["diverged"] or out["deep"])
        return out
    except Exception:
        logger.debug("heart_demon_state failed", exc_info=True)
        return out


def _mirror_fighter(fighter_a: dict | None, player) -> dict[str, Any]:
    """O REFLEXO: o oponente É o próprio cultivador — mesmos stats, mesmas artes,
    mesmo reino. Você luta contra quem você diz que é.

    Espelha `rehydrate_npc_fighter` (Onda 3) key a key: o dict de
    `build_fighter_data` NÃO carrega `qi_capacity`, e `start_duel_pve` lê
    `fb["qi_capacity"]` para dimensionar o pool do lado B — sem esta linha o Rito
    estouraria KeyError na criação (a mesma armadilha que o npc_cultivator
    documenta)."""
    fb = dict(fighter_a or {})
    fb["telegram_id"] = 0
    fb["is_npc"] = True
    fb["archetype"] = "heart_demon"
    fb.setdefault("difficulty", "hard")
    fb.setdefault("techniques", [])
    fb.setdefault("armor_bonus", 0.0)
    fb.setdefault("defense_boost", 1.0)
    fb["dao_name"] = getattr(player, "dao_name", None) or fb.get("name") or "?"
    fb["qi_capacity"] = float(getattr(player, "qi_capacity", 0) or 100.0)
    if not fb.get("hp"):
        fb["hp"] = float((fb.get("combat_profile") or {}).get("eff_hp", 500.0) or 500.0)
    if not fb.get("bp"):
        fb["bp"] = int(getattr(player, "battle_power", 0) or 50)
    return fb


async def start_heart_demon_rite(session, player_id: int) -> dict[str, Any]:
    """Abre o Rito do Coração-Demônio. Gates em ordem disclosed: flag →
    jogador → divergência real → escolha pendente → duelo aberto → cooldown →
    duelo alheio em curso → HP. Devolve ``{ok, duel_id}``; o caller commita.
    Espelha `start_hidden_rite`/`start_cave_run` (incluindo o lazy-settle de
    um Rito órfão — a vitória presa é liquidada AGORA, lição §5-C)."""
    if not forbidden_on():
        return {"ok": False, "reason": "fpd_off"}

    player = (await session.execute(
        select(Player).where(Player.telegram_id == int(player_id))
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}

    # Curar um Rito terminal-mas-não-liquidado ANTES de decidir (senão a
    # vitória sumia e o cooldown corria contra ele).
    prev = await _last_rite_duel(session, int(player_id))
    if prev is not None and prev.state in ("finished", "forfeited"):
        try:
            from core.duel_engine import apply_post_duel_effects
            await apply_post_duel_effects(session, prev)
            await session.flush()
        except Exception:
            logger.exception("start_heart_demon_rite: stale-duel settle failed duel=%s",
                             prev.id)

    state = await heart_demon_state(session, player)
    if state.get("open_duel_id"):
        return {"ok": True, "duel_id": state["open_duel_id"], "resumed": True}
    if state.get("pending_choice_duel_id"):
        return {"ok": False, "reason": "choice_pending",
                "duel_id": state["pending_choice_duel_id"],
                "target_path": state.get("target_path")}
    if not state.get("can_start"):
        return {"ok": False, "reason": "not_diverged",
                "current_path": state.get("current_path"),
                "current_karma": state.get("karma")}
    if state.get("cooldown_ms"):
        return {"ok": False, "reason": "rite_cooldown", "cooldown_ms": state["cooldown_ms"]}

    try:
        from core.sect_trial_engine import _has_open_duel
        open_duel = await _has_open_duel(session, int(player_id))
    except Exception:
        logger.debug("start_heart_demon_rite open-duel check failed (player=%s)",
                     player_id, exc_info=True)
        open_duel = None
    if open_duel is not None:
        return {"ok": False, "reason": "duel_already_active", "duel_id": str(open_duel.id)}

    try:
        from core.combat_engine import get_current_hp
        if get_current_hp(player) <= 0:
            return {"ok": False, "reason": "hp_depleted"}
    except Exception:
        logger.debug("start_heart_demon_rite hp check failed (player=%s)",
                     player_id, exc_info=True)

    try:
        from core.duel_engine import _build_duel_fighter, start_duel_pve
        mirror = _mirror_fighter(await _build_duel_fighter(session, player), player)
        duel = await start_duel_pve(
            session, player,
            archetype="heart_demon",          # tag de sabor (≤24 chars, String(24))
            difficulty="hard",
            source=HD_PVE_SOURCE,
            context={"path": state.get("current_path"),
                     "target_path": state.get("target_path"),
                     "karma": state.get("karma")},
            npc_realm=int(player.realm or 0),      # o Reflexo é do SEU reino
            fighter_b_override=mirror,
        )
        await session.flush()
        return {"ok": True, "duel_id": str(duel.id),
                "target_path": state.get("target_path"),
                "current_path": state.get("current_path")}
    except Exception:
        logger.exception("start_heart_demon_rite failed (player=%s)", player_id)
        return {"ok": False, "reason": "internal_error"}


async def resolve_heart_demon_from_duel(session, duel, player, won: bool) -> dict[str, Any]:
    """Liquida o Rito (chamado por `settle_pve_duel`; o row do Player já está
    LOCKED). Vencer NÃO decide nada sozinho — abre a ESCOLHA (2 botões, Lei §1).
    Perder ⇒ o Coração morde `soul_strength` (o "1 dano de Mar Mental" com dente
    real: mexe no tier exibido E na mitigação da tribulação) e o cooldown corre.

    Idempotente: o `pve_settled` do settle já barra a 2ª passagem, e o registro
    de derrota é gravado uma vez por duelo (chave = o id do duelo no log)."""
    ctx = (duel.pve_context or {}) if duel is not None else {}
    payload: dict[str, Any] = {
        "hd": "won" if won else "lost",
        "target_path": ctx.get("target_path"),
        "current_path": ctx.get("path"),
    }
    if won:
        payload["choice_pending"] = True
        return payload
    try:
        player_id = int(player.telegram_id)
        soul_before = int(getattr(player, "soul_strength", 0) or 0)
        bite = max(int(FP_HD_SOUL_MIN), int(soul_before * float(FP_HD_SOUL_PCT)))
        bite = min(bite, max(0, soul_before - 1))     # nunca zera a alma
        async with session.begin_nested():
            if bite > 0:
                player.soul_strength = soul_before - bite
            session.add(KarmaLog(
                player_id=player_id, delta=0,
                new_value=int(getattr(player, "karma", 0) or 0),
                event_type=HD_EVENT_FELL,
                metadata_={"duel_id": str(duel.id), "soul_lost": int(bite)},
            ))
        payload.update({
            "soul_before": soul_before,
            "soul_after": int(getattr(player, "soul_strength", 0) or 0),
            "soul_lost": int(bite),
            "cooldown_h": int(FP_RITE_COOLDOWN_H),
        })
        # O Mar Mental 识海 é DERIVADO (soul + percepção + reino) — a mordida
        # pode fazer o tier EXIBIDO recuar, e o jogador tem de ver isso
        # (Lei §10 antes→depois). `_tier_for_depth` é a mesma régua da tela.
        try:
            from core.mind_sea_engine import _tier_for_depth, mind_sea_depth
            depth_after = mind_sea_depth(player)
            payload["mind_sea_before"] = _tier_for_depth(depth_after + bite)[0]
            payload["mind_sea_after"] = _tier_for_depth(depth_after)[0]
        except Exception:
            logger.debug("heart demon mind-sea projection failed", exc_info=True)
        return payload
    except Exception:
        logger.exception("resolve_heart_demon_from_duel failed (duel=%s)",
                         getattr(duel, "id", None))
        return payload


async def choose_heart_demon(session, player_id: int, choice: str) -> dict[str, Any]:
    """A ESCOLHA pós-vitória: ``cross`` (⚔️ ATRAVESSAR) ou ``stand`` (🧘 REAFIRMAR).

    ATRAVESSAR re-cristaliza o Path para o lado divergido — **o único
    destrancamento legítimo do one-shot** (`set_player_path(allow_recrystallize=
    True)`, flag-gated) — e a CONSISTÊNCIA é do rito: uma casa incompatível com
    o caminho novo é deixada com o preço vivo (−75 `betray_sect_oath`), dito
    ANTES no confirm. REAFIRMAR não custa nada: ficar é livre.
    Ambos gravam o registro eterno que abre o Cofre. O caller commita."""
    if not forbidden_on():
        return {"ok": False, "reason": "fpd_off"}
    if choice not in ("cross", "stand"):
        return {"ok": False, "reason": "bad_choice"}

    player = (await session.execute(
        select(Player).where(Player.telegram_id == int(player_id))
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}

    state = await heart_demon_state(session, player)
    duel_id = state.get("pending_choice_duel_id")
    if not duel_id:
        return {"ok": False, "reason": "no_pending_choice"}

    path_before = getattr(player, "path", None)
    karma_now = int(getattr(player, "karma", 0) or 0)
    target = diverged_target_path(path_before, karma_now)
    out: dict[str, Any] = {"ok": True, "choice": choice,
                           "path_before": path_before, "path_after": path_before,
                           "duel_id": str(duel_id)}

    if choice == "stand":
        try:
            async with session.begin_nested():
                session.add(KarmaLog(
                    player_id=int(player_id), delta=0, new_value=karma_now,
                    event_type=HD_EVENT_STOOD,
                    metadata_={"duel_id": str(duel_id), "path": path_before},
                ))
        except Exception:
            logger.exception("choose_heart_demon(stand) log failed (player=%s)", player_id)
            return {"ok": False, "reason": "internal_error"}
        return out

    # ── ATRAVESSAR ────────────────────────────────────────────────────────
    if not target:
        return {"ok": False, "reason": "no_target_path"}
    try:
        from core.path_engine import set_player_path
        res = await set_player_path(session, int(player_id), target,
                                    allow_recrystallize=True)
    except Exception:
        logger.exception("choose_heart_demon: set_player_path crashed (player=%s)", player_id)
        return {"ok": False, "reason": "internal_error"}
    if not res.get("ok"):
        return {"ok": False, "reason": res.get("reason") or "path_write_failed"}
    out["path_after"] = target

    # O snapshot do momento (precedente `path_crystallized` 2026-07-30 — o card
    # do PathModal lê ESTA linha em vez do karma de hoje) + o registro do Rito.
    try:
        async with session.begin_nested():
            session.add(KarmaLog(
                player_id=int(player_id), delta=0, new_value=karma_now,
                event_type="path_crystallized",
                metadata_={"path": target, "source": "heart_demon"},
            ))
            session.add(KarmaLog(
                player_id=int(player_id), delta=0, new_value=karma_now,
                event_type=HD_EVENT_CROSSED,
                metadata_={"duel_id": str(duel_id), "from": path_before, "to": target},
            ))
    except Exception:
        logger.exception("choose_heart_demon: snapshot log failed (player=%s)", player_id)

    # Consistência de seita — a casa demoníaca não aceita quem deixou de ser
    # demoníaco (o hard-gate do join nunca é re-verificado num membro: sem isto
    # o Abismo guardaria um santo). O preço do juramento quebrado é o vivo.
    try:
        out["sect"] = await _sect_consistency_after_cross(session, player, target)
    except Exception:
        logger.exception("choose_heart_demon: sect consistency failed (player=%s)", player_id)

    # A tumba de Lǐ Xuèyè sente quem desceu (gated `legacy_caves`; guards do
    # TEC-4 respeitados — bloqueado ⇒ nada, o próximo sobrevivente rola).
    if target == "demonic":
        try:
            woke = await maybe_wake_xueye(session, player)
            if woke:
                out["xueye"] = woke
        except Exception:
            logger.exception("choose_heart_demon: xueye wake failed (player=%s)", player_id)

    try:
        from core.achievement_engine import check_achievements
        await check_achievements(session, int(player_id), "path_chosen", 1)
    except Exception:
        logger.exception("choose_heart_demon: achievement bus failed (player=%s)", player_id)

    logger.info("heart_demon_crossed: player_id=%s %s → %s karma=%s",
                player_id, path_before, target, karma_now)
    return out


def sect_incompatible_with_path(sect_id: str | None, path: str | None) -> bool:
    """A casa é incompatível com o caminho novo? (Espelho do hard-gate do
    `join_player_to_sect`: casa demoníaca exige `path == demonic`.)"""
    if not sect_id:
        return False
    try:
        from core.world_sects_engine import is_demonic_sect
        return bool(is_demonic_sect(sect_id)) and path != "demonic"
    except Exception:
        return False


async def sect_cross_preview(session, player) -> dict[str, Any] | None:
    """O que ATRAVESSAR vai custar na casa — DITO ANTES do tap (Lei §1).
    ``None`` quando não há casa ou ela continua compatível."""
    try:
        target = diverged_target_path(getattr(player, "path", None),
                                      int(getattr(player, "karma", 0) or 0))
        sect_id = getattr(player, "sect_id", None)
        if not target or not sect_incompatible_with_path(sect_id, target):
            return None
        from core.karma_engine import get_karma_event_delta
        return {"sect_id": sect_id, "leaves": True,
                "karma_cost": int(get_karma_event_delta("betray_sect_oath"))}
    except Exception:
        logger.debug("sect_cross_preview failed", exc_info=True)
        return None


async def _sect_consistency_after_cross(session, player, target_path: str) -> dict[str, Any]:
    """A saída narrativa da casa incompatível — REUSA `leave_player_from_sect`
    (uma verdade: mesmo −75, mesmo lockout de artes, mesmo chronicle)."""
    sect_id = getattr(player, "sect_id", None)
    if not sect_incompatible_with_path(sect_id, target_path):
        return {"left": False}
    from core.world_sects_engine import leave_player_from_sect
    res = await leave_player_from_sect(session, int(player.telegram_id))
    # A key é `locked_arts` (world_sects_engine) — ler "locked" devolvia [] e a
    # disclosure do que a redenção TRANCA morria num typo (review adversarial).
    return {"left": bool(res and res.get("ok")), "sect_id": sect_id,
            "locked": (res or {}).get("locked_arts") or [],
            "karma_delta": (res or {}).get("karma_delta")}


# ══════════════════════════════════════════════════════════════════════════
# (d) Lǐ Xuèyè — o gatilho que fura os ~6% do drift
# ══════════════════════════════════════════════════════════════════════════

async def maybe_wake_xueye(session, player, rng: _random.Random | None = None
                           ) -> dict[str, Any] | None:
    """Atravessar para demonic acorda a tumba da Noite de Sangue em Mòyǔ.

    Chama o `maybe_open_cave` do TEC-4 FORÇANDO a casa `xueye` e respeitando
    TODOS os guards vivos (flag `legacy_caves` · 1 gruta ativa · cooldown
    global · TTL) — bloqueado ⇒ ``None``, e o próximo sobrevivente rola.
    Zero migration: mesmo `event_type`, `payload.trigger = "heart_demon"`."""
    try:
        from core.legacy_cave_engine import CAVE_HOUSES, legacy_caves_on, maybe_open_cave
        if not (forbidden_on() and legacy_caves_on()):
            return None
        rng = rng or _random
        if rng.random() >= float(FP_XUEYE_CHANCE):
            return None
        house = CAVE_HOUSES.get("xueye") or {}
        ev = await maybe_open_cave(
            session, sect_id=None, continent_key=house.get("continent"),
            rng=rng, force_npc_key="xueye", payload_extra={"trigger": "heart_demon"},
        )
        if ev is None:
            return None
        return {"opened": True, "npc": house.get("npc"),
                "continent": ev.continent_key, "event_id": int(ev.id)}
    except Exception:
        logger.debug("maybe_wake_xueye failed", exc_info=True)
        return None


async def xueye_notice(session, player, npc_key: str) -> dict[str, Any] | None:
    """"A Noite de Sangue viu você" — o vencedor demonic que já encarou o
    Coração-Demônio é NOTADO por Lǐ Xuèyè (ela está VIVA no lore, R9).
    Chamado do resolve da gruta com `begin_nested` PRÓPRIO. Key condicional."""
    if npc_key != "xueye" or not forbidden_on():
        return None
    try:
        if getattr(player, "path", None) != "demonic":
            return None
        player_id = int(player.telegram_id)
        if not await rite_passed(session, player_id):
            return None
        async with session.begin_nested():
            try:
                from core.world_pulse_engine import emit_chronicle
                await emit_chronicle(
                    session, event_type="fpd_xueye", text_key="chron_fpd_xueye",
                    params={"npc": "Lǐ Xuèyè"}, continent_key="moyu", importance=2,
                )
            except Exception:
                logger.debug("xueye_notice chronicle failed", exc_info=True)
            # A nota PESSOAL vai pela notificação (o feed de sussurros é GLOBAL e
            # só aceita temas do catálogo — um "sussurro pessoal" ali não existe).
            try:
                from core.notification_engine import notify
                await notify(
                    session, player_id, "forbidden_path",
                    title_key="notif_fpd_xueye_title",
                    body_key="notif_fpd_xueye_body",
                    ref_id=f"fpd_xueye:{player_id}",
                    icon="🩸", target_tab="cultivation", priority=4,
                )
            except Exception:
                logger.debug("xueye_notice notify failed", exc_info=True)
        return {"seen": True, "npc": "Lǐ Xuèyè"}
    except Exception:
        logger.debug("xueye_notice failed", exc_info=True)
        return None


# ══════════════════════════════════════════════════════════════════════════
# (e) A severidade de tribulação — o consumidor que faltava
# ══════════════════════════════════════════════════════════════════════════

def tribulation_karma_mult(karma: Any, world_key: str | None = None) -> float:
    """O multiplicador dos céus por |karma| (1.5×/2×/3× em 500/750/900).

    O número JÁ é mostrado ao jogador no KarmaModal desde a v16.3 — aqui ele
    passa a MORDER. Flag OFF ⇒ 1.0 (main byte-idêntico por construção)."""
    if not forbidden_on(world_key):
        return 1.0
    try:
        from core.karma_engine import get_tribulation_modifier
        return float(get_tribulation_modifier(abs(int(karma or 0))))
    except Exception:
        return 1.0
