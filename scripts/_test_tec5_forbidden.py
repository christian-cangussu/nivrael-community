"""TEC-5 — teste isolado do Caminho Proibido 禁道 (SEM DB).

Roda: python -X utf8 scripts/_test_tec5_forbidden.py

Padrão _test_tec4_caves: ExplodingSession prova OFF-identity (flag OFF = zero
queries em TODA função pública); FakeSession prova a lógica ON. Cobre as
armadilhas que o recon de 2026-08-03 (+ a leitura de produção) impôs:

  · OFF-identity total: `forbidden_ids()` VAZIO ⇒ os 2 somadores passivos e o
    duelo ficam byte-idênticos; o stub do Coração-Demônio segue o da v16.3;
    a divergência do Errante e a severidade de tribulação não existem;
  · o conjunto {604,605,606,607} EXCLUÍDO dos 2 somadores passivos
    (build_fighter_data + World Boss, grep-provado) e INCLUÍDO no settle;
  · o custo: karma por USO + anos por uso derivados do teto REAL, a contagem
    lida do action_log (só o lado certo), o antes→depois e a trava no limiar
    EXATO — com a recusa NOMEADA antes da rodada;
  · o Rito: gates em ordem, o Reflexo com `qi_capacity` (a key que
    `start_duel_pve` lê e que `build_fighter_data` NÃO produz), resume,
    cooldown, escolha dupla, o registro que abre o Cofre, e a re-cristalização
    passando o one-shot SÓ com o bypass explícito;
  · o Cofre: gates na ordem disclosed com have/need, SEM CP (a armadilha do
    clamp-para-o-topo), lockout herdado (>= 3 cobre o 6) e a estante fora das
    outras 8 casas;
  · as seeds 605-607 IN-BAND, medidas contra o teto CONTADO DO CATÁLOGO
    (nunca contra o spec) + nome único (o runner é insert-only: um nome
    repetido mata TODO o seed no boot);
  · a severidade: estimate == roll (o mesmo número nos 5 call sites);
  · Xuèyè: guards do TEC-4 respeitados no gatilho forçado + notice condicional;
  · i18n ×3 ×2 com placeholders idênticos e as keys DERIVADAS presentes.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import types
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

if "telegram" not in sys.modules:
    _tg = types.ModuleType("telegram")
    _tg.Update = type("Update", (), {})
    _tg_err = types.ModuleType("telegram.error")

    class _TgErr(Exception):
        retry_after = 0
    _tg_err.RetryAfter = _TgErr
    _tg_err.TimedOut = _TgErr
    _tg_err.NetworkError = _TgErr
    _tg.error = _tg_err
    sys.modules["telegram"] = _tg
    sys.modules["telegram.error"] = _tg_err

import core.forbidden_path_engine as fp  # noqa: E402
import core.sect_library_engine as lib  # noqa: E402

PASS = 0
FAILS: list[str] = []
# Ancorado no relógio REAL de propósito: o cooldown do Rito é derivado de
# `resolved_at` vs `datetime.now()`, então uma data fixa faz o teste virar
# vermelho sozinho no dia seguinte (foi o que aconteceu ao _test_tec4_caves).
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(f"{name} {('— ' + detail) if detail else ''}")


def _read(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


# ── Fakes (espelho do harness TEC-3/TEC-4) ───────────────────────────────────
class ExplodingSession:
    def __getattr__(self, name):
        if name == "rollback":
            async def _noop():
                return None
            return _noop

        def _boom(*a, **k):
            raise AssertionError(f"query executada com flag OFF ({name})")
        return _boom


class FakeResult:
    def __init__(self, rows):
        self._rows = rows if isinstance(rows, list) else [rows]

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)

    def scalar(self):
        r = self._rows[0] if self._rows else None
        return r[0] if isinstance(r, tuple) else r

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self):
                return list(rows)
        return _S()


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    def __init__(self, handlers):
        self.handlers = handlers
        self.added: list = []
        self.flushed = 0

    async def execute(self, stmt, params=None):
        try:
            sql = str(stmt)
        except Exception:
            sql = repr(stmt)
        p = dict(params or {})
        for pred, rows in self.handlers:
            if pred(sql, p):
                return FakeResult(rows(p) if callable(rows) else rows)
        raise AssertionError("query inesperada: " + sql[:220].replace("\n", " "))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    def begin_nested(self):
        return _Nested()


def _rows_of(session, cls_name: str) -> list:
    return [o for o in session.added if type(o).__name__ == cls_name]


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class ScriptedRng:
    def __init__(self, randoms, choice=None):
        self._r = list(randoms)
        self._choice = choice

    def random(self):
        return self._r.pop(0) if self._r else 0.99

    def choice(self, seq):
        return self._choice if self._choice is not None else seq[0]


_ORIG_FP_ON = fp.forbidden_on
_ORIG_VAULT_ON = fp.vault_on
_ORIG_LIB_ON = lib.biblioteca_on
_ORIG_SEL_ON = lib.selado_on
_ORIG_FVAULT_ON = lib.forbidden_vault_on


def _on(v: bool) -> None:
    """Liga/desliga TUDO o que o TEC-5 gateia (o Cofre é conjunção)."""
    fp.forbidden_on = (lambda world_key=None: v)
    fp.vault_on = (lambda world_key=None: v)
    lib.biblioteca_on = (lambda world_key=None: v)
    lib.selado_on = (lambda world_key=None: v)
    lib.forbidden_vault_on = (lambda world_key=None: v)


def _player(**kw):
    base = dict(telegram_id=7, realm=8, karma=-800, path="demonic",
                age_years=0, lifespan_bonus_years=0, soul_strength=1000,
                qi_capacity=10000.0, sect_id="abyssal_depths", sect_rank="heir",
                language="pt", dao_name="Teste", battle_power=1000)
    base.update(kw)
    return Obj(**base)


def _log(*uses_a, side="a"):
    """action_log com N usos da(s) arte(s) dadas no lado pedido."""
    out = [{"type": "accepted"}]
    for i, tid in enumerate(uses_a, 1):
        out.append({"round": i, side: {"tech": {"id": tid}, "damage": 10},
                    ("b" if side == "a" else "a"): {"tech": {"id": 1}}})
    return out


async def main() -> None:
    # ═══ 1. OFF-identity — ExplodingSession em TODA função pública ═══
    _on(False)
    exp = ExplodingSession()
    check("off.ids_vazio", fp.forbidden_ids() == frozenset(), str(fp.forbidden_ids()))
    check("off.is_forbidden", fp.is_forbidden(605) is False)
    r = await fp.forbidden_use_gate(exp, 7, 605)
    check("off.use_gate", r == {"ok": True})
    duel = Obj(id="d1", action_log=_log(605, 605), round_idx=2, attacker_id=7,
               defender_id=None, pve_context={})
    r = await fp.charge_forbidden_uses(exp, duel, _player(), "a")
    check("off.charge", r is None)
    r = await fp.charge_and_stamp(exp, duel, _player(), "a")
    check("off.charge_stamp", r is None and len(duel.action_log) == 3)
    await fp.charge_all_sides(exp, duel)
    check("off.charge_all", len(duel.action_log) == 3, "OFF nao carimba nada")
    r = await fp.heart_demon_state(exp, _player())
    check("off.hd_state", r == {"on": False})
    r = await fp.start_heart_demon_rite(exp, 7)
    check("off.hd_start", r == {"ok": False, "reason": "fpd_off"})
    r = await fp.choose_heart_demon(exp, 7, "cross")
    check("off.hd_choose", r == {"ok": False, "reason": "fpd_off"})
    r = await fp.maybe_wake_xueye(exp, _player())
    check("off.xueye_wake", r is None)
    r = await fp.xueye_notice(exp, _player(), "xueye")
    check("off.xueye_notice", r is None)
    check("off.rogue_div", fp.rogue_divergence(-900) == {"diverged": False, "threshold": None})
    check("off.trib_mult", fp.tribulation_karma_mult(-900) == 1.0)

    # O Cofre não existe na tupla de estantes com a flag OFF.
    check("off.tiers", 6 not in lib.library_tiers(sect_id="abyssal_depths"),
          str(lib.library_tiers(sect_id="abyssal_depths")))

    # ═══ 2. ON — o conjunto proibido e a exclusão dos 2 somadores ═══
    _on(True)
    ids = fp.forbidden_ids()
    check("on.ids", ids == frozenset({604, 605, 606, 607}), str(sorted(ids)))
    check("on.604_incluso", 604 in ids, "a Sutra de Sangue entra no conjunto")
    check("on.vault_ids", fp.VAULT_TECH_IDS == frozenset({605, 606, 607}))

    ce = _read("core/combat_engine.py")
    check("grep.build_fighter_exclui",
          "forbidden_ids as _fp_ids" in ce and "continue" in ce.split("forbidden_ids as _fp_ids")[1][:600],
          "build_fighter_data tem de filtrar o conjunto (cobre os 5 simulate_combat)")
    be = _read("core/boss_engine.py")
    check("grep.boss_exclui", "notin_(list(_forbidden))" in be,
          "o World Boss soma damage_mult de tudo equipado")
    de = _read("core/duel_engine.py")
    check("grep.duel_nao_exclui",
          "forbidden_use_gate" in de
          and "_tech_bonus_from_action" in de
          and "if _forbidden" not in de,
          "no DUELO a arte proibida FUNCIONA — o duel_engine só a MARCA no log "
          "e gateia pelo relógio; quem exclui é o build_fighter_data (passivo)")
    check("grep.duel_marca_o_swing", '"fpd"' in de and "_fp_ids" in de,
          "a esquiva/desvio apaga `tech` do log — sem a marca do SWING o custo "
          "seguiria os golpes que ACERTARAM, decididos pelo adversário")
    # O custo vive no ÚNICO ponto por onde TODO duelo terminal passa — os 3
    # settles NÃO cobram (o duelo direto nem chega ao settle PvP).
    check("grep.cobranca_unica", "charge_all_sides" in de,
          "apply_post_duel_effects é o único ponto por onde todo duelo passa")
    for f in ("core/pvp_duel_settle.py", "core/arena_duel_settle.py"):
        check(f"grep.settle_nao_cobra.{os.path.basename(f)}",
              "charge_and_stamp" not in _read(f),
              "cobrar no settle deixava o duelo direto (sem PVPChallenge) de graça")
    check("grep.pve_le_o_marker", "read_forbidden_cost" in _read("core/pve_duel_settle.py"),
          "o PvE só LÊ o carimbo para o payload")
    check("grep.settle.heart_demon", '"heart_demon"' in _read("core/pve_duel_settle.py"),
          "source ausente do dispatcher = recompensa MORTA")

    # ═══ 3. O custo — contagem, karma por uso, anos, antes→depois ═══
    check("count.a", fp.count_forbidden_uses(_log(605, 606, 605), "a", ids) == {605: 2, 606: 1})
    check("count.lado_errado", fp.count_forbidden_uses(_log(605, 605), "a", ids) != {}
          and fp.count_forbidden_uses(_log(605, 605), "b", ids) == {})
    check("count.arte_comum", fp.count_forbidden_uses(_log(12, 17), "a", ids) == {})
    check("count.log_heterogeneo",
          fp.count_forbidden_uses([{"type": "hp_drained"}, None, {"a": "x"}], "a", ids) == {})

    # Os anos vêm do teto REAL do cultivador (por-mil), nunca de um número solto.
    from core.lifespan_engine import REALM_LIFESPAN
    p8 = _player(realm=8)
    expect8 = max(fp.FP_BURN_MIN_YEARS, round(REALM_LIFESPAN[8] * fp.FP_BURN_PERMIL / 1000))
    check("years.r8", fp.years_per_use(p8) == expect8, f"{fp.years_per_use(p8)} != {expect8}")
    check("years.r0_piso", fp.years_per_use(_player(realm=0)) >= fp.FP_BURN_MIN_YEARS)
    check("years.imortal_zero", fp.years_per_use(_player(realm=10)) == 0,
          "quem escapou do ciclo não tem relógio para queimar")
    check("years.bonus_conta",
          fp.years_per_use(_player(realm=8, lifespan_bonus_years=50000)) > expect8)

    # A trava do teto morde no limiar EXATO (nunca antes, nunca depois).
    ceil8 = REALM_LIFESPAN[8]
    check("gate.limiar_ok", fp.lifespan_gate_ok(_player(realm=8, age_years=ceil8 - expect8)))
    check("gate.limiar_nao", not fp.lifespan_gate_ok(_player(realm=8, age_years=ceil8 - expect8 + 1)))
    check("gate.imortal_sempre", fp.lifespan_gate_ok(_player(realm=10, age_years=10 ** 9)))

    # A recusa é NOMEADA e chega antes da rodada.
    gate_sess = FakeSession([(lambda s, p: "FROM players" in s, [_player(realm=8, age_years=ceil8)])])
    r = await fp.forbidden_use_gate(gate_sess, 7, 605)
    check("gate.recusa_nomeada", r.get("ok") is False and r.get("reason") == "forbidden_lifespan_spent"
          and r.get("ceiling") == ceil8, str(r))
    r = await fp.forbidden_use_gate(ExplodingSession(), 7, 12)
    check("gate.arte_comum_sem_query", r == {"ok": True}, "arte comum não pode custar 1 query")

    # O settle: karma por USO (não por duelo) + anos + antes→depois no payload.
    karma_calls = []

    async def _fake_apply_karma(session, pid, ev, metadata=None, **kw):
        karma_calls.append(ev)
        return {"ok": True, "new_value": -800 - 20 * len(karma_calls), "diverged": False}

    import core.karma_engine as ke
    _orig_apply = ke.apply_karma
    ke.apply_karma = _fake_apply_karma
    try:
        pl = _player(realm=8, age_years=0)
        duel = Obj(id="d2", action_log=_log(605, 605, 604), round_idx=3,
                   attacker_id=7, defender_id=None, pve_context={})
        sess = FakeSession([])
        cost = await fp.charge_and_stamp(sess, duel, pl, "a")
        check("charge.uses", cost and cost["uses"] == 3, str(cost))
        check("charge.karma_por_uso", len(karma_calls) == 3 and set(karma_calls) == {"forbidden_tech_use"},
              str(karma_calls))
        check("charge.anos", cost["years_burned"] == expect8 * 3 and pl.age_years == expect8 * 3)
        check("charge.antes_depois", cost["age_before"] == 0 and cost["age_after"] == expect8 * 3
              and cost["karma_before"] == -800 and cost["karma_after"] == -860, str(cost))
        check("charge.by_tech", cost["by_tech"] == {"605": 2, "604": 1}, str(cost["by_tech"]))
        check("charge.marker", fp.read_forbidden_cost(duel, "a") == cost)
        check("charge.marker_outro_lado", fp.read_forbidden_cost(duel, "b") is None)
        check("charge.sem_uso_none",
              await fp.charge_and_stamp(sess, Obj(id="d3", action_log=_log(12), round_idx=1,
                                                  attacker_id=7, defender_id=None), _player(), "a") is None,
              "sem uso proibido ⇒ payload byte-idêntico")
        # Imortal: karma sim, anos não.
        karma_calls.clear()
        pi = _player(realm=10, age_years=0)
        d4 = Obj(id="d4", action_log=_log(605), round_idx=1, attacker_id=7, defender_id=None)
        ci = await fp.charge_and_stamp(FakeSession([]), d4, pi, "a")
        check("charge.imortal", ci["years_burned"] == 0 and ci["immortal"] is True
              and len(karma_calls) == 1, str(ci))
    finally:
        ke.apply_karma = _orig_apply

    # O lado é resolvido pelo DUELO (nunca por challenger/target).
    dpvp = Obj(id="d5", attacker_id=11, defender_id=22)
    check("side.a", fp.side_of_player(dpvp, 11) == "a")
    check("side.b", fp.side_of_player(dpvp, 22) == "b")
    check("side.estranho", fp.side_of_player(dpvp, 33) is None)

    # ═══ 4. A divergência do Errante + o alvo da travessia ═══
    check("rogue.div_neg", fp.rogue_divergence(-500)["diverged"] is True)
    check("rogue.div_pos", fp.rogue_divergence(700)["diverged"] is True)
    check("rogue.limiar_exato", fp.rogue_divergence(-499)["diverged"] is False)
    check("rogue.alvo", fp.rogue_divergence(-900).get("toward") == "demonic")
    check("target.righteous", fp.diverged_target_path("righteous", -600) == "demonic")
    check("target.demonic", fp.diverged_target_path("demonic", 600) == "righteous")
    check("target.rogue_sinal", fp.diverged_target_path("rogue", -600) == "demonic"
          and fp.diverged_target_path("rogue", 600) == "righteous")
    check("target.sem_path", fp.diverged_target_path(None, 600) is None)
    ka = _read("core/karma_engine.py")
    check("grep.karma_rogue_gated", "rogue_divergence" in ka and 'if path == "rogue"' in ka,
          "o chokepoint da divergência tem de gatear o Errante")
    dh = _read("core/dao_heart_engine.py")
    check("grep.daoheart_espelho", "rogue_divergence" in dh,
          "sem o espelho, o card do Coração Dao jurava 'firme' enquanto o Rito abria")

    # ═══ 5. O Rito — Reflexo, gates, escolha, registro ═══
    fa = {"telegram_id": 7, "name": "X", "hp": 100.0, "bp": 50, "techniques": [{"id": 605}],
          "combat_profile": {"eff_hp": 100.0}}
    mirror = fp._mirror_fighter(fa, _player())
    check("mirror.qi_capacity", "qi_capacity" in mirror,
          "start_duel_pve lê fb['qi_capacity'] e build_fighter_data NÃO a produz")
    check("mirror.npc", mirror["telegram_id"] == 0 and mirror["is_npc"] is True)
    check("mirror.mesmas_artes", mirror["techniques"] == fa["techniques"],
          "o Reflexo é VOCÊ — as mesmas artes")
    check("mirror.archetype_curto", len(mirror["archetype"]) <= 24)
    check("rite.pve_source_curto", len(fp.HD_PVE_SOURCE) <= 24)

    # Estado: divergiu, sem duelo anterior ⇒ pode começar.
    def _hd_session(duel_rows=None, log_rows=None):
        return FakeSession([
            (lambda s, p: "karma_log" in s, log_rows or []),
            (lambda s, p: "duel_sessions" in s, duel_rows or []),
        ])

    st = await fp.heart_demon_state(_hd_session(), _player(karma=600, path="demonic"))
    check("rite.state_diverged", st["diverged"] and st["can_start"] and st["target_path"] == "righteous",
          str(st))
    st = await fp.heart_demon_state(_hd_session(), _player(karma=0, path="demonic"))
    check("rite.state_firme", st["diverged"] is False and st["can_start"] is False)

    # Duelo aberto ⇒ retomar, nunca um segundo.
    open_duel = Obj(id="D9", state="waiting_actions", winner_id=None, resolved_at=None)
    st = await fp.heart_demon_state(_hd_session([open_duel]), _player(karma=600))
    check("rite.state_open", st["open_duel_id"] == "D9" and st["can_start"] is False)

    # Vitória sem escolha ⇒ escolha PENDENTE (nunca um duelo novo por cima).
    won_duel = Obj(id="D8", state="finished", winner_id=7,
                   resolved_at=NOW - timedelta(hours=1))
    st = await fp.heart_demon_state(_hd_session([won_duel]), _player(karma=600))
    check("rite.state_pending", st["pending_choice_duel_id"] == "D8" and st["can_start"] is False)

    # Escolha já feita ⇒ cooldown corre a partir do resolved_at.
    log_chosen = [("heart_demon_crossed", {"duel_id": "D8"})]
    st = await fp.heart_demon_state(_hd_session([won_duel], log_chosen), _player(karma=600))
    check("rite.state_cooldown", st["cooldown_ms"] is not None and st["faced"] is True
          and st["pending_choice_duel_id"] is None, str(st))
    old_duel = Obj(id="D7", state="finished", winner_id=7,
                   resolved_at=NOW - timedelta(days=30))
    st = await fp.heart_demon_state(_hd_session([old_duel], [("heart_demon_crossed", {"duel_id": "D7"})]),
                                    _player(karma=600))
    check("rite.cooldown_expira", st["cooldown_ms"] is None and st["can_start"] is True, str(st))
    # Derrota: nada a escolher, o cooldown corre e o Rito volta (nunca dead-end).
    lost_duel = Obj(id="D6", state="finished", winner_id=0,
                    resolved_at=NOW - timedelta(days=30))
    st = await fp.heart_demon_state(_hd_session([lost_duel], [("heart_demon_fell", {"duel_id": "D6"})]),
                                    _player(karma=600))
    check("rite.derrota_volta", st["can_start"] is True and st["faced"] is False
          and st["pending_choice_duel_id"] is None, str(st))

    # O registro que abre o Cofre: atravessar OU reafirmar contam; cair NÃO.
    for ev, expected in (("heart_demon_crossed", True), ("heart_demon_stood", True),
                         ("heart_demon_fell", False)):
        got = await fp.rite_passed(_hd_session([], [(ev, {"duel_id": "D8"})]), 7)
        check(f"rite.registro.{ev}", got is expected)

    # A escolha exige uma vitória pendente.
    sess = _hd_session([], [])
    r = await fp.choose_heart_demon(FakeSession([
        (lambda s, p: "FROM players" in s, [_player(karma=600)]),
        (lambda s, p: "karma_log" in s, []),
        (lambda s, p: "duel_sessions" in s, []),
    ]), 7, "cross")
    check("choose.sem_pendente", r == {"ok": False, "reason": "no_pending_choice"}, str(r))
    r = await fp.choose_heart_demon(FakeSession([
        (lambda s, p: "FROM players" in s, [_player(karma=600)]),
    ]), 7, "explodir")
    check("choose.escolha_invalida", r == {"ok": False, "reason": "bad_choice"})

    # REAFIRMAR: grava o registro, não toca no caminho, não custa nada.
    pstand = _player(karma=600, path="demonic")
    s_stand = FakeSession([
        (lambda s, p: "FROM players" in s, [pstand]),
        (lambda s, p: "karma_log" in s, []),
        (lambda s, p: "duel_sessions" in s, [won_duel]),
    ])
    r = await fp.choose_heart_demon(s_stand, 7, "stand")
    logs = _rows_of(s_stand, "KarmaLog")
    check("choose.stand_ok", r["ok"] and r["path_after"] == "demonic" and pstand.path == "demonic")
    check("choose.stand_registro", len(logs) == 1 and logs[0].event_type == "heart_demon_stood"
          and logs[0].delta == 0, str([(x.event_type, x.delta) for x in logs]))

    # ATRAVESSAR: re-cristaliza + snapshot + registro (a consistência é do rito).
    import core.path_engine as pe
    calls = {}

    async def _fake_set_path(session, pid, path, *, allow_recrystallize=False):
        calls["allow"] = allow_recrystallize
        calls["path"] = path
        return {"ok": True, "path": path, "previous": "demonic"}
    _orig_set = pe.set_player_path
    pe.set_player_path = _fake_set_path
    try:
        pcross = _player(karma=600, path="demonic", sect_id=None)
        s_cross = FakeSession([
            (lambda s, p: "FROM players" in s, [pcross]),
            (lambda s, p: "karma_log" in s, []),
            (lambda s, p: "duel_sessions" in s, [won_duel]),
            (lambda s, p: "achievements" in s, []),   # o bus é best-effort
        ])
        r = await fp.choose_heart_demon(s_cross, 7, "cross")
        evs = [x.event_type for x in _rows_of(s_cross, "KarmaLog")]
        check("choose.cross_ok", r["ok"] and r["path_after"] == "righteous", str(r))
        check("choose.bypass_explicito", calls.get("allow") is True,
              "o one-shot só se destranca por bypass EXPLÍCITO")
        check("choose.snapshot", "path_crystallized" in evs and "heart_demon_crossed" in evs, str(evs))
    finally:
        pe.set_player_path = _orig_set

    # O one-shot REAL: sem bypass o caminho não muda; com bypass, muda.
    pe_src = _read("core/path_engine.py")
    check("path.bypass_gated", "allow_recrystallize" in pe_src
          and "previous is not None and not allow_recrystallize" in pe_src)
    check("path.mesmo_caminho_recusa", "previous == path" in pe_src,
          "atravessar para o caminho que já se anda não é travessia")

    # A consistência de seita: a casa demoníaca recusa quem deixou de ser.
    check("sect.incompativel", fp.sect_incompatible_with_path("abyssal_depths", "righteous") is True)
    check("sect.compativel", fp.sect_incompatible_with_path("abyssal_depths", "demonic") is False)
    check("sect.justa_fica", fp.sect_incompatible_with_path("azure_cloud", "demonic") is False,
          "só a casa demoníaca tem hard-gate de path no join")
    check("sect.sem_casa", fp.sect_incompatible_with_path(None, "righteous") is False)

    # ═══ 6. O Cofre Proibido — tupla, posto, custo, lockout ═══
    check("vault.tier_na_tupla", 6 in lib.library_tiers(sect_id="abyssal_depths"))
    check("vault.so_a_casa_do_abismo", 6 not in lib.library_tiers(sect_id="azure_cloud"),
          "as outras 8 casas não têm Cofre — nem como teaser")
    check("vault.min_rank", lib.TIER_MIN_RANK.get(6) == "heir")
    check("vault.sem_cp", lib.tier_default_cp(6) == 0,
          "sem a entrada 6 no _TIER_CP o Cofre nasceria a 6000 (clamp para o topo)")
    check("vault.cp_da_arte", lib.tier_cp_cost(Obj(library_tier=6, library_cp_cost=None)) == 0)
    check("vault.lockout_herdado",
          lib.is_library_locked(Obj(library_tier=6, sect_key="abyssal_depths"),
                                Obj(sect_id="azure_cloud")) is True
          and lib.is_library_locked(Obj(library_tier=6, sect_key="abyssal_depths"),
                                    Obj(sect_id="abyssal_depths")) is False)
    check("vault.lockout_floor", lib.LOCK_TIER_FLOOR == 3, "o >= 3 é o que cobre o 6 de graça")
    lib_src = _read("core/sect_library_engine.py")
    for needle, why in (('block = "path"', "caminho"), ('block = "fp_karma"', "karma"),
                        ('block = "hd_rite"', "rito")):
        check(f"vault.block.{why}", needle in lib_src)
    # Os 3 blocos novos existem nos DOIS mapas de superfície (o fallback mentia).
    check("vault.block_chat", all(b in _read("handlers/library.py")
                                  for b in ('"path"', '"fp_karma"', '"hd_rite"')))
    tabs = _read("miniapp/components/tabs.js")
    check("vault.block_mini", all(b in tabs for b in ('art.block === "path"',
                                                      'art.block === "fp_karma"',
                                                      'art.block === "hd_rite"')))
    check("vault.write_gates", 'reason": "path_required' in lib_src
          and 'reason": "fp_karma_too_low' in lib_src and 'reason": "hd_rite_required' in lib_src,
          "a ESCRITA repete os gates da view — nunca só a view")

    # ═══ 7. As seeds 605-607 — banda medida CONTRA O CATÁLOGO VIVO ═══
    from database.seeds.combat_seeds import FORBIDDEN_VAULT_TECHS, TECHNIQUES
    by_id = {t["id"]: t for t in TECHNIQUES}
    check("seed.tres_artes", [t["id"] for t in FORBIDDEN_VAULT_TECHS] == [605, 606, 607])
    for t in FORBIDDEN_VAULT_TECHS:
        check(f"seed.{t['id']}.casa", t["sect_key"] == "abyssal_depths")
        check(f"seed.{t['id']}.tier", t["library_tier"] == 6)
        check(f"seed.{t['id']}.cp", t["library_cp_cost"] == 0)
        check(f"seed.{t['id']}.eixo", t["effect_type"] == "damage_mult",
              "dr/ai/ev saturam nos clamps — cobrar por nada viola a Lei §1")
        check(f"seed.{t['id']}.realm", t["req_realm"] == 8)
        check(f"seed.{t['id']}.qi", t["qi_cost"] == 80)
        check(f"seed.{t['id']}.intent", t["intent_affinity"] == "killing")
        check(f"seed.{t['id']}.elemento", t["element"] == "chaos")
    # Teto por effect_type CONTADO das seeds (nunca do spec).
    dm_others = [float(t["effect_value"]) for t in TECHNIQUES
                 if t.get("effect_type") == "damage_mult" and t["id"] not in fp.VAULT_TECH_IDS]
    dm_cap = max(dm_others)
    for t in FORBIDDEN_VAULT_TECHS:
        check(f"seed.{t['id']}.dentro_do_teto", float(t["effect_value"]) <= dm_cap,
              f"{t['effect_value']} > teto vivo {dm_cap}")
    t5 = [float(x["effect_value"]) for x in TECHNIQUES
          if x.get("library_tier") == 5 and x.get("effect_type") == "damage_mult"]
    sustained = [t for t in FORBIDDEN_VAULT_TECHS if t["effect_round"] == 0]
    check("seed.acima_do_t5", all(float(t["effect_value"]) > max(t5) for t in sustained),
          f"t6 sustentado tem de passar o topo t5 ({max(t5)})")
    check("seed.qi_castavel", 80 <= max(20, int(10000 * 0.20)),
          "pool = max(20, qi_capacity×0.20); no R8 real (prod: >= 9680) sobra de longe")
    names = [t["name"] for t in TECHNIQUES]
    check("seed.nome_unico", len(names) == len(set(names)),
          "TechniqueCatalog.name é UNIQUE e o runner é insert-only: um nome repetido "
          "derruba TODO o seed no boot")
    seeds_src = _read("database/seeds/combat_seeds.py")
    check("seed.force_sync", "SECT_LIBRARY_TEC1 + SECT_LIBRARY_TEC3 + FORBIDDEN_VAULT_TECHS" in seeds_src,
          "sem force-sync as colunas de estante nunca chegam a uma row já existente")
    check("seed.604_sem_tier", by_id[604].get("library_tier") is None,
          "a Sutra de Sangue é do PORTADOR (decisão TEC-4) — nunca ganha lockout de estante")

    # ═══ 8. A severidade de tribulação — estimate == roll ═══
    from core.tribulation_engine import estimate_success_chance, get_tribulation_power
    base = get_tribulation_power(7)
    check("trib.sem_karma", get_tribulation_power(7, 0) == base)
    check("trib.karma_500", abs(get_tribulation_power(7, -500) - base * 1.5) < 1e-6)
    check("trib.karma_900", abs(get_tribulation_power(7, 900) - base * 3.0) < 1e-6,
          "santo ou demônio, o Céu não discrimina")
    p_est = get_tribulation_power(7, -900)
    check("trib.display_igual_roll",
          estimate_success_chance(1000, p_est, "resist", 3)
          == estimate_success_chance(1000, get_tribulation_power(7, -900), "resist", 3),
          "previsão e rolagem leem o MESMO número")
    _on(False)
    check("trib.off_neutro", get_tribulation_power(7, -900) == base,
          "flag OFF ⇒ multiplicador 1.0 (main byte-idêntico)")
    _on(True)
    def _calls_of(src: str, fn: str) -> list:
        """Os argumentos de cada chamada de `fn`, com parênteses BALANCEADOS
        (um regex ingénuo corta em `min(trib.realm, len(REALM_NAMES)` e
        inventaria um falso positivo)."""
        out, i = [], 0
        while True:
            i = src.find(fn + "(", i)
            if i < 0:
                return out
            j = i + len(fn) + 1
            depth, start = 1, j
            while j < len(src) and depth:
                if src[j] == "(":
                    depth += 1
                elif src[j] == ")":
                    depth -= 1
                j += 1
            out.append(src[start:j - 1])
            i = j
    trib_calls = [c for c in _calls_of(_read("handlers/tribulation.py"), "get_tribulation_power")
                  + _calls_of(_read("core/webserver.py"), "get_tribulation_power")
                  if "realm: int" not in c]
    check("trib.cinco_call_sites", len(trib_calls) == 5, f"{len(trib_calls)} call sites: {trib_calls}")
    check("trib.todos_os_call_sites", all("karma" in c for c in trib_calls),
          f"um call site sem karma faz display != roll: {trib_calls}")

    # ═══ 9. Xuèyè — guards do TEC-4 respeitados + notice condicional ═══
    import core.legacy_cave_engine as lgc
    _orig_lgc_on = lgc.legacy_caves_on
    lgc.legacy_caves_on = (lambda world_key=None: True)
    try:
        # 1 gruta ativa no mundo ⇒ o gatilho NÃO abre uma segunda.
        s_busy = FakeSession([
            (lambda s, p: "count" in s.lower() and "world_events" in s, [(1,)]),
            (lambda s, p: "world_events" in s, []),
        ])
        r = await fp.maybe_wake_xueye(s_busy, _player(), rng=ScriptedRng([0.0]))
        check("xueye.respeita_1_ativa", r is None)
        # A chance própria do gatilho corre ANTES de qualquer query.
        r = await fp.maybe_wake_xueye(ExplodingSession(), _player(), rng=ScriptedRng([0.99]))
        check("xueye.chance_antes_da_query", r is None)
        lgc_src = _read("core/legacy_cave_engine.py")
        check("xueye.force_param", "force_npc_key" in lgc_src and "payload_extra" in lgc_src)
        check("xueye.force_pula_drift",
              "if force_npc_key is not None:" in lgc_src
              and lgc_src.index("if force_npc_key is not None:") < lgc_src.index("Pity global"),
              "o gatilho externo pula chance/pity/drift, nunca os guards")
        check("xueye.notice_savepoint", "begin_nested" in _read("core/forbidden_path_engine.py"))
        # O notice é condicional: casa certa + path + registro.
        r = await fp.xueye_notice(FakeSession([]), _player(path="righteous"), "xueye")
        check("xueye.notice_so_demonic", r is None)
        r = await fp.xueye_notice(ExplodingSession(), _player(), "tianlei")
        check("xueye.notice_so_a_tumba_dela", r is None)
        r = await fp.xueye_notice(_hd_session([], []), _player(), "xueye")
        check("xueye.notice_exige_rito", r is None, "sem o registro do Rito, ela não repara")
    finally:
        lgc.legacy_caves_on = _orig_lgc_on
    check("xueye.render_mini", "xueye_notice" in tabs and "fpd_mini_xueye_seen" in tabs)
    check("xueye.render_chat", "fpd_chat_xueye_seen" in _read("handlers/sect.py"),
          "payload entregue != payload visto (lição QoL-31/07)")

    # ═══ 10. Wiring das superfícies + o carregador do custo ═══
    ws = _read("core/webserver.py")
    check("wire.endpoint_choose", "heart_demon/choose" in ws and "api_heart_demon_choose" in ws)
    check("wire.rota_registrada", 'add_post("/api/miniapp/heart_demon/choose"' in ws)
    check("wire.commit_so_em_ok", "if res.get(\"ok\"):\n                    await session.commit()" in ws
          or "if res.get('ok')" in ws)
    check("wire.duel_state_custo", 'out["forbidden_cost"]' in ws)
    check("wire.karma_info_rito", 'out["heart_demon"]' in ws)
    check("wire.lifespan_burn", 'lifespan_view["burn_on"]' in ws)
    check("wire.chat_prefixo", 'startswith("fpd_")' in _read("main.py"))
    check("wire.chat_comando", 'CommandHandler("coracao"' in _read("main.py"))
    check("wire.mini_banner", "state.forbidden_cost" in tabs and "fpd_mini_cost_title" in tabs)
    check("wire.mini_rito", "heart_demon/choose" in tabs and "fpd_mini_btn_cross" in tabs)
    check("wire.mini_lifespan", "lifespan_burned" in tabs)
    check("wire.chat_lifespan", "status_lifespan_burned" in _read("handlers/cultivation.py"))
    check("flag.declarada", '"forbidden_path"' in _read("database/db.py"))

    # ═══ 10-bis. Os 9 achados do review adversarial (regressão permanente) ═══
    # (1) BLOCKER — o Cofre era INALCANÇÁVEL: pedia karma alinhado >= 500 (num
    # demoníaco, karma <= -500) E o registro do Rito, mas o Rito só abria por
    # DIVERGÊNCIA, que num demoníaco dispara a karma >= +500. Requisitos
    # exatamente inversos. A 2ª porta (profundidade) resolve.
    check("rev1.deep_abre", fp.deep_on_path(-800, "demonic") is True,
          "um demoníaco a -800 tem de poder encarar o Reflexo")
    check("rev1.deep_justo", fp.deep_on_path(800, "righteous") is True)
    check("rev1.deep_limiar", fp.deep_on_path(-499, "demonic") is False
          and fp.deep_on_path(-500, "demonic") is True)
    check("rev1.deep_rogue", fp.deep_on_path(900, "rogue") is False,
          "a neutralidade não se aprofunda — o Errante entra pela divergência")
    st = await fp.heart_demon_state(_hd_session(), _player(karma=-800, path="demonic"))
    check("rev1.state_deep", st["can_start"] is True and st["deep"] is True
          and st["diverged"] is False and st["target_path"] is None,
          str(st))
    check("rev1.sem_travessia_sem_alvo",
          fp.diverged_target_path("demonic", -800) == "righteous",
          "o helper puro segue simétrico; quem decide é o state (target só se diverged)")
    # E o gate do Cofre passa a ser satisfazível pelo MESMO cultivador:
    _deep = _player(karma=-800, path="demonic")
    check("rev1.cofre_satisfazivel",
          lib.aligned_karma(_deep.karma, "abyssal_depths") >= fp.FP_KARMA_MIN
          and fp.deep_on_path(_deep.karma, _deep.path),
          "karma do Cofre e porta do Rito têm de ser satisfazíveis JUNTOS")

    # (2) MAJOR — a arte legada da Oculta era listada OUTRA VEZ dentro do Cofre
    # (o mapa legado é por POSTO e o tier 6 pede o mesmo 'heir' do tier 5).
    check("rev2.legado_por_tier",
          'int(legacy_entry.get("tier") or 0) != tier' in lib_src,
          "o slot legado tem de casar por TIER, não só por posto")

    # (3) MAJOR — o duelo DIRETO (combat/duel_create) não tem PVPChallenge e o
    # settle PvP desiste antes de cobrar: o custo saía de graça.
    check("rev3.ponto_unico", "charge_all_sides" in de
          and de.index("charge_all_sides") < de.index("settle dispatcher reordered"),
          "a cobrança corre ANTES do dispatcher, no ponto por onde todo duelo passa")
    check("rev3.idempotente", "FPD_LOG_MARKER" in _read("core/forbidden_path_engine.py"),
          "o marker no action_log é a chave de idempotência (padrão hp_drained)")
    _d = Obj(id="dx", action_log=_log(605, 605), round_idx=2, attacker_id=7,
             defender_id=None, pve_context={})
    fp.stamp_forbidden_cost(_d, "a", {"uses": 2})
    _before = len(_d.action_log)
    await fp.charge_all_sides(FakeSession([]), _d)
    check("rev3.nao_cobra_duas_vezes", len(_d.action_log) == _before,
          "já carimbado ⇒ nunca uma segunda cobrança")
    _d2 = Obj(id="dy", action_log=_log(605), round_idx=1, attacker_id=None,
              defender_id=None, pve_context={})
    await fp.charge_all_sides(FakeSession([]), _d2)
    check("rev3.npc_nao_paga", len(_d2.action_log) == 2,
          "o sentinela do NPC não paga karma nem anos")

    # (4) MAJOR — esquiva/desvio apagavam o `tech` do log ⇒ o custo seguia os
    # golpes que ACERTARAM, e era o ADVERSÁRIO quem decidia o preço.
    _evaded = [{"round": 1, "a": {"tech": None, "fpd": 605, "qi_spent": 80},
                "b": {"tech": {"id": 1}}}]
    check("rev4.swing_conta", fp.count_forbidden_uses(_evaded, "a", ids) == {605: 1},
          "o uso é o SWING (o qi foi gasto), não o acerto")
    check("rev4.fallback_log_antigo",
          fp.count_forbidden_uses(_log(605), "a", ids) == {605: 1},
          "logs anteriores à marca continuam a contar pelo `tech`")

    # (5) MINOR — a trava era por DUELO, não por USO: quem visse "resta 1 uso"
    # lançava a arte a cada rodada que o pool pagasse, e o relógio furava o teto.
    _p = _player(realm=8, age_years=ceil8 - expect8)
    check("rev5.gate_conta_a_luta",
          fp.lifespan_gate_ok(_p, pending_uses=0) is True
          and fp.lifespan_gate_ok(_p, pending_uses=1) is False,
          "o uso JÁ lançado nesta luta conta antes do próximo")
    _pc = _player(realm=8, age_years=ceil8 - expect8)
    _dc = Obj(id="dz", action_log=_log(605, 605, 605), round_idx=3,
              attacker_id=7, defender_id=None)
    import core.karma_engine as _ke
    _orig = _ke.apply_karma

    async def _noop_karma(session, pid, ev, metadata=None, **kw):
        return {"ok": True, "new_value": -800, "diverged": False}
    _ke.apply_karma = _noop_karma
    try:
        _cost = await fp.charge_and_stamp(FakeSession([]), _dc, _pc, "a")
    finally:
        _ke.apply_karma = _orig
    check("rev5.clamp_no_teto", _pc.age_years == ceil8
          and _cost["years_burned"] == expect8,
          f"o relógio nunca passa do teto ({_pc.age_years} vs {ceil8})")

    # (6) MINOR — a vitrine prometia karma 20 para quem já está no piso -1000.
    check("rev6.karma_efetivo_no_piso", fp.effective_karma_cost(-1000) == 0)
    check("rev6.karma_efetivo_parcial", fp.effective_karma_cost(-990) == 10)
    check("rev6.karma_efetivo_normal", fp.effective_karma_cost(-500) == 20)
    check("rev6.knobs_sem_karma", fp.knobs_payload()["karma_cost"] == 20)
    check("rev6.knobs_com_karma", fp.knobs_payload(-1000)["karma_cost"] == 0
          and fp.knobs_payload(-1000)["karma_floored"] is True)

    # (7) MINOR — o auto-piloto do chat gastava o Mar do jogador por ele.
    check("rev7.autoplay_filtra",
          "forbidden_ids as _fpi" in _read("core/sect_trial_engine.py"),
          "a IA nunca lança arte proibida: o custo é do jogador, e ele tocou UM botão")

    # (8) MINOR — as 3 recusas de ESCRITA do Cofre não tinham mensagem.
    check("rev8.recusa_chat", all(k in _read("handlers/library.py")
                                  for k in ("fpd_err_path", "fpd_err_karma", "fpd_err_rite")))
    check("rev8.recusa_mini", all(k in tabs for k in ("path_required:", "fp_karma_too_low:",
                                                      "hd_rite_required:")))

    # (9) NIT — a lista de artes trancadas pela redenção vinha vazia (key errada).
    check("rev9.locked_arts", 'get("locked_arts")' in _read("core/forbidden_path_engine.py"),
          "leave_player_from_sect devolve `locked_arts`, não `locked`")
    check("rev9.locked_dito", "fpd_crossed_sect_locked" in _read("handlers/forbidden.py"))

    # ═══ 10-ter. A tabela `world_events` é COMPARTILHADA (bug de prod 04/08) ═══
    # A Gruta do TEC-4 vive na MESMA tabela do Director (MV-2). Sem filtro por
    # tipo: o mapa imprimia a key crua `legacy_cave`, o rumor anunciava-a, a
    # gruta aparecia DUAS vezes no card — e, o pior, uma gruta aberta (TTL 72h)
    # contava como evento ativo e BLOQUEAVA Marés/Meteoros por 3 dias.
    td = _read("core/tiandao_engine.py")
    check("shared.tupla_do_director", "DIRECTOR_EVENT_TYPES" in td)
    check("shared.leitura_filtra", td.count("WorldEvent.event_type.in_(DIRECTOR_EVENT_TYPES)") >= 2,
          "as DUAS leituras (superfícies + sweep/spawn do pulse) têm de filtrar")
    check("shared.sem_key_crua", 'else ev.event_type,' not in td
          and "wev_unknown_name" in td,
          "sem meta o evento não é do Director — e a key CRUA nunca vai para a tela")
    import core.tiandao_engine as _td
    check("shared.tipos_do_director",
          set(_td.DIRECTOR_EVENT_TYPES) == set(_td.EVENT_META.keys()),
          "a tupla e o catálogo de metadados têm de ser a MESMA verdade")
    check("shared.gruta_fora", _td.CAVE_EVENT_TYPE not in _td.DIRECTOR_EVENT_TYPES
          if hasattr(_td, "CAVE_EVENT_TYPE") else
          "legacy_cave" not in _td.DIRECTOR_EVENT_TYPES,
          "a Gruta do Legado NUNCA é evento do Director (flags independentes)")

    # ═══ 11. i18n ×3 ×2 ═══
    from inject_tec5_i18n import CHAT, MINIAPP
    for label, parts, batch in (("chat", ("locales",), CHAT),
                                ("mini", ("miniapp", "i18n"), MINIAPP)):
        data = {}
        for lang in ("pt", "en", "es"):
            with open(os.path.join(ROOT, *parts, f"{lang}.json"), encoding="utf-8") as f:
                data[lang] = json.load(f)
        check(f"i18n.{label}.paridade",
              set(data["pt"]) == set(data["en"]) == set(data["es"]))
        missing = [k for k in batch["pt"] if any(k not in data[l] for l in ("pt", "en", "es"))]
        check(f"i18n.{label}.lote", not missing, str(missing[:5]))
        bad = [k for k in batch["pt"]
               if len({tuple(sorted(set(re.findall(r"\{(\w+)\}", data[l].get(k, "")))))
                       for l in ("pt", "en", "es")}) != 1]
        check(f"i18n.{label}.placeholders", not bad, str(bad[:5]))
    with open(os.path.join(ROOT, "locales", "pt.json"), encoding="utf-8") as f:
        ptc = json.load(f)
    check("i18n.estante_6", ptc.get("lib_shelf_6"), "f-string lib_shelf_{tier} — sem ela sai a key crua")
    for tid in (605, 606, 607):
        check(f"i18n.tech_{tid}", ptc.get(f"tech_{tid}_name") and ptc.get(f"tech_{tid}_desc"))

    _on(True)
    print(("OK " if not FAILS else "FAIL ") + f"— {PASS} asserts")
    for f in FAILS:
        print(" ✗", f)
    fp.forbidden_on, fp.vault_on = _ORIG_FP_ON, _ORIG_VAULT_ON
    lib.biblioteca_on, lib.selado_on = _ORIG_LIB_ON, _ORIG_SEL_ON
    lib.forbidden_vault_on = _ORIG_FVAULT_ON
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
