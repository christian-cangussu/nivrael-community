"""QoL-relatos — teste isolado do Peso do Ofício + Uma Masmorra de Cada Vez (SEM DB).

Roda: python -X utf8 scripts/_test_qol_relatos.py

Padrão _test_tec2_scrolls: ExplodingSession prova OFF = zero queries; helpers
puros provam identidade byte a byte; FakeSession (dispatch por substring do SQL
compilado) prova a lógica ON.

O que este teste protege, em ordem de gravidade:
  1. **A ARMADILHA (§0.3 do prompt).** O peso do ofício viaja num canal
     PRÓPRIO. Se algum dia alguém o mandar por `amount`, o contador de quest
     e o de storylet passam a andar de 5 em 5 e uma quest "forje 5 artefatos"
     fecha em 1 forja. O teste prova que o peso muda o XP do ofício e NÃO
     muda o que chega às quests/storylets.
  2. **Item A não tem flag** — logo a sua OFF-identity é numérica: tier
     ausente/inválido → peso 1.0 exato, portanto o ganho continua a ser o de
     antes desta mudança (é o que mantém os 446 asserts do MV-7 verdes).
  3. **Peso por tier nos 3 ofícios**, na escala REAL 1..5 (o prompt supunha
     1..4; os catálogos dizem required_alchemy_tier 1..5 e ForgeRecipe.tier
     1..5) — e nunca 0, nem com knob inválido.
  4. **OFF-identity do Item B** — com `masmorra_unica` OFF as entradas e as
     varreduras aceitam exatamente como hoje, sem UMA query.
  5. **Lei §1** — a recusa nomeia a masmorra e o andar e carrega o id que
     constrói a saída (Retirar-se). Um "não" sem saída é violação.
  6. **A política do sweep**, decidida e documentada: varrer OUTRA masmorra
     concluída fica livre; varrer aquela onde você está dentro, não.
  7. Wiring grep-provável (flag sem call-site = promessa vazia), incluindo os
     CINCO caminhos de entrada — o prompt dizia três, o recon achou cinco.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import core.dungeon_run_engine as dng  # noqa: E402
import core.profession_engine as prf  # noqa: E402
import core.quest_engine as qe  # noqa: E402

PASS = 0
FAILS: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(f"{name} {('— ' + detail) if detail else ''}")


# ── Fakes ────────────────────────────────────────────────────────────────────
class ExplodingSession:
    """Qualquer toque no DB explode — prova OFF = zero queries."""

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

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self):
                return list(rows)
        return _S()


class FakeSession:
    """Dispatch por substring do SQL compilado (padrão MV-7/TEC-1/TEC-2)."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.added: list = []
        self.deleted: list = []
        self.committed = False
        self.seen_sql: list[str] = []

    async def execute(self, stmt, params=None):
        try:
            sql = str(stmt)
        except Exception:
            sql = repr(stmt)
        self.seen_sql.append(sql)
        for pred, rows in self.handlers:
            if pred(sql):
                return FakeResult(rows() if callable(rows) else rows)
        raise AssertionError("query inesperada: " + sql[:200].replace("\n", " "))

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None

    def begin_nested(self):
        class _SP:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False
        return _SP()


def P(**kw):
    """Fake Player com ofício."""
    d = dict(telegram_id=111, profession="alquimista", profession_xp=0,
             realm=3, language="pt", current_continent="yanshan")
    d.update(kw)
    return types.SimpleNamespace(**d)


def PD(dungeon_id=7, floor=3, difficulty="normal"):
    """Fake PlayerDungeon row."""
    return types.SimpleNamespace(player_id=111, dungeon_id=dungeon_id,
                                 current_floor=floor, difficulty=difficulty,
                                 completed=True)


def DC(dungeon_id=7, name="Caverna do Lobo", emoji="🐺"):
    """Fake DungeonCatalog row."""
    return types.SimpleNamespace(id=dungeon_id, name=name, emoji=emoji)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _src(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


# ══════════════════════════════════════════════════════════════════════════
# Item A — o peso do ofício
# ══════════════════════════════════════════════════════════════════════════
def _weight_pure_blocks() -> None:
    """A escala REAL é 1..5 e o peso é sempre > 0."""
    N = prf.PROF_XP_TIER_COUNT
    check("w.count", N == 6,
          "pílulas vão a required_alchemy_tier 5 e RECEITAS DE FORJA a 6")
    check("w.curve_len", len(prf.PROF_XP_TIER_W) == N, str(prf.PROF_XP_TIER_W))

    # A escala tem de COBRIR o que as seeds realmente criam. Sem esta
    # asserção, seedar um tier novo reabre em silêncio o buraco que a revisão
    # apanhou (receita Celestial tier 6 a pagar o MENOR XP do jogo).
    import re as _re
    _seed = _src("database", "seeds", "forge_seeds.py")
    _max_recipe = max(int(x) for x in _re.findall(r'"tier":\s*(\d+)', _seed))
    check("w.covers_seeds", _max_recipe <= N,
          f"receita seedada de tier {_max_recipe} > curva de {N}")

    # Monotonia: refinar mais alto nunca pode pesar menos (o defeito original).
    ws = [prf.prof_weight(t)[1] for t in range(1, N + 1)]
    check("w.monotonic", all(ws[i] < ws[i + 1] for i in range(N - 1)), str(ws))
    check("w.t1_is_one", prf.prof_weight(1) == (1, 1.0),
          "T1 tem de continuar a valer exatamente o de antes")

    for t in range(1, N + 1):
        nt, w = prf.prof_weight(t)
        check(f"w.tier.{t}", nt == t and w == prf.PROF_XP_TIER_W[t - 1], f"{nt}/{w}")
        check(f"w.positive.{t}", w > 0, "peso 0 seria pior que o defeito")

    # Tier ausente/inválido/< 1 → (0, 1.0): NUNCA 0 de peso, e o 0 no tier é o
    # sinal de "não sei" que faz a superfície omitir a cláusula (Lei §1).
    for bad in (None, 0, -1, "banana", "", [], {}, 1.5j):
        nt, w = prf.prof_weight(bad)
        check(f"w.invalid.{bad!r}", (nt, w) == (0, 1.0), f"{nt}/{w}")

    # Tier ACIMA da curva → TOPO, nunca neutro. Um tier acima da escala é mais
    # DURO, jamais "desconhecido" — tratá-lo como neutro pagaria o menor XP do
    # jogo pela receita mais difícil.
    top = prf.PROF_XP_TIER_W[-1]
    for above in (N + 1, N + 5, 99):
        nt, w = prf.prof_weight(above)
        check(f"w.above.{above}", (nt, w) == (N, top), f"{nt}/{w}")
    check("w.above_beats_below", prf.prof_weight(99)[1] > prf.prof_weight(1)[1],
          "o topo NUNCA pode pagar menos que o degrau 1")

    # Float é aceite e truncado (3.7 → tier 3) em vez de virar neutro.
    check("w.float_trunc", prf.prof_weight(3.7) == (3, prf.PROF_XP_TIER_W[2]))

    # Knob inválido nunca zera nem encurta a curva (parser PRÓPRIO — o
    # _parse_tier_curve do ofício exige 4 e engoliria a curva de 5).
    fb = prf._XP_TIER_W_FALLBACK
    short = ",".join(str(i) for i in range(1, N))            # N-1 valores
    long_ = ",".join(str(i) for i in range(1, N + 2))        # N+1 valores
    zeroed = ",".join(["0"] + [str(i) for i in range(1, N)])  # tem um 0
    negged = ",".join(["-1"] + [str(i) for i in range(1, N)])
    for raw in ("", "1,2", short, long_, zeroed, negged, "a,b,c,d,e,f"):
        check(f"w.knob_bad.{raw!r}", prf._parse_xp_tier_curve(raw, fb) == fb,
              str(prf._parse_xp_tier_curve(raw, fb)))
    good = ",".join(str(i) for i in range(1, N + 1))
    check("w.knob_good", prf._parse_xp_tier_curve(good, fb) ==
          tuple(float(i) for i in range(1, N + 1)))

    # A conta do §1: XP por energia tem de SUBIR com o tier (senão o peso
    # está errado e refinar alto continua a ser punido).
    from config import ALCHEMY_ENERGY_COSTS as EC
    ratios = [round(prf.PROF_XP_BASE * prf.prof_weight(t)[1]) / EC[t]
              for t in range(1, 6)]
    check("w.xp_per_energy_monotonic",
          all(ratios[i] < ratios[i + 1] for i in range(4)),
          "XP/energia: " + " ".join(f"{r:.3f}" for r in ratios))


def _weight_track_blocks() -> None:
    """O peso morde o XP nos 3 ofícios — e SÓ com a flag ON."""
    orig = prf.profissoes_on

    # Flag OFF: zero queries, mesmo com um tier alto no canal.
    prf.profissoes_on = lambda *a, **k: False
    run(prf.track_profession(ExplodingSession(), 111, "craft_pill", 1,
                             weight_tier=5))
    check("a.off.no_query", True, "ExplodingSession não estourou")
    prf.profissoes_on = orig

    async def _xp_for(tracker, profession, tier, amount=1, mult=1.0):
        pl = P(profession=profession, profession_xp=0)
        sess = FakeSession([(lambda s: "players" in s.lower(), [pl])])
        _om = prf.xp_multiplier

        async def _fake_mult(session, player):
            return {"mult": mult, "native": False, "rep": False}
        prf.xp_multiplier = _fake_mult
        try:
            await prf.track_profession(sess, 111, tracker, amount,
                                       weight_tier=tier)
        finally:
            prf.xp_multiplier = _om
        return int(pl.profession_xp or 0)

    prf.profissoes_on = lambda *a, **k: True
    try:
        for tracker, prof in (("craft_pill", "alquimista"),
                              ("forge_artifact", "ferreiro"),
                              ("use_pill", "medico")):
            for tier in range(1, prf.PROF_XP_TIER_COUNT + 1):
                got = run(_xp_for(tracker, prof, tier))
                want = int(round(prf.PROF_XP_BASE * 1 *
                                 prf.PROF_XP_TIER_W[tier - 1] * 1.0))
                check(f"a.xp.{prof}.t{tier}", got == want, f"{got} != {want}")

            # Tier ausente → EXATAMENTE o ganho de antes desta mudança.
            base = run(_xp_for(tracker, prof, None))
            check(f"a.xp.{prof}.legacy", base == prf.PROF_XP_BASE,
                  f"{base} != {prf.PROF_XP_BASE} (é o que mantém o MV-7 verde)")
            # ...e o mesmo para um tier lixo.
            check(f"a.xp.{prof}.garbage",
                  run(_xp_for(tracker, prof, "banana")) == prf.PROF_XP_BASE)

        # O tracker ERRADO para o ofício não ganha nada, por mais alto o tier.
        check("a.xp.wrong_tracker",
              run(_xp_for("use_pill", "alquimista", 5)) == 0)

        # amount e peso multiplicam-se, mas são eixos independentes.
        check("a.xp.amount_x_weight",
              run(_xp_for("use_pill", "medico", 3, amount=4)) ==
              int(round(prf.PROF_XP_BASE * 4 * prf.PROF_XP_TIER_W[2])))
    finally:
        prf.profissoes_on = orig


def _trap_blocks() -> None:
    """§0.3 — o PESO NÃO PODE MOVER O CONTADOR DE QUEST/STORYLET.

    Este é o bloco que prova que não caímos na armadilha. `track_quest` é
    espiado nos dois ganchos que recebem `amount`: se o peso alguma vez for
    empurrado por lá, o número que chega às quests deixa de ser 1.
    """
    seen: dict = {"storylet": [], "profession": [], "quest_amount": []}

    async def _spy_storylets(session, pid, ot, amount=1):
        seen["storylet"].append((ot, amount))

    async def _spy_profession(session, pid, ot, amount=1, *, weight_tier=None):
        seen["profession"].append((ot, amount, weight_tier))

    import core.storylet_engine as sty
    _o_sty, _o_prf = sty.track_storylets, prf.track_profession
    sty.track_storylets = _spy_storylets
    prf.track_profession = _spy_profession

    # A query das quests devolve zero linhas — o que interessa aqui é o
    # `amount` que a chamada carrega, não o UPDATE.
    sess = FakeSession([(lambda s: True, [])])
    try:
        run(qe.track_quest(sess, 111, "craft_pill", 1, prof_weight_tier=5))
    finally:
        sty.track_storylets, prf.track_profession = _o_sty, _o_prf

    check("trap.storylet_unweighted", seen["storylet"] == [("craft_pill", 1)],
          f"storylets receberam {seen['storylet']} — o peso vazou para o contador")
    check("trap.profession_got_weight",
          seen["profession"] == [("craft_pill", 1, 5)],
          f"o gancho de ofício recebeu {seen['profession']}")

    # A assinatura é keyword-only: nenhum call site posicional pode empurrar
    # o peso para dentro de `amount` por engano.
    import inspect
    sig = inspect.signature(qe.track_quest)
    p = sig.parameters.get("prof_weight_tier")
    check("trap.kwonly", p is not None and p.kind is inspect.Parameter.KEYWORD_ONLY,
          str(sig))
    sig2 = inspect.signature(prf.track_profession)
    p2 = sig2.parameters.get("weight_tier")
    check("trap.kwonly_engine",
          p2 is not None and p2.kind is inspect.Parameter.KEYWORD_ONLY, str(sig2))

    # E o default continua a ser "sem peso" → legado intocado.
    check("trap.default_none", p.default is None and p2.default is None)


# ══════════════════════════════════════════════════════════════════════════
# Item B — uma masmorra de cada vez
# ══════════════════════════════════════════════════════════════════════════
def _off_blocks() -> None:
    """Flag OFF → main byte-idêntico, sem UMA query."""
    check("b.off.gate", dng.masmorra_unica_on() is False,
          "sem DB o gate fail-safe é False")
    for kwargs in ({}, {"only": 7}, {"exclude": 7}):
        check(f"b.off.active_run{kwargs}",
              run(dng.active_run(ExplodingSession(), 111, **kwargs)) is None)


def _active_run_blocks() -> None:
    """Flag ON — a query encontra a run e devolve o que a recusa precisa."""
    orig = dng.masmorra_unica_on
    dng.masmorra_unica_on = lambda *a, **k: True
    try:
        sess = FakeSession([(lambda s: "player_dungeons" in s,
                             [(PD(7, 3), DC(7))])])
        got = run(dng.active_run(sess, 111))
        check("b.on.found", got is not None)
        check("b.on.names", got and got["name"] == "Caverna do Lobo",
              "Lei §1: a recusa tem de DIZER o nome")
        check("b.on.floor", got and got["current_floor"] == 3,
              "Lei §1: e o andar")
        check("b.on.id_for_exit", got and got["dungeon_id"] == 7,
              "é o id que constrói o botão dng_retreat_<id>")
        check("b.on.emoji", got and got["emoji"] == "🐺")
        check("b.on.difficulty", got and got["difficulty"] == "normal")

        # Sem run aberta → None (a entrada segue como hoje).
        empty = FakeSession([(lambda s: "player_dungeons" in s, [])])
        check("b.on.none", run(dng.active_run(empty, 111)) is None)

        # A query filtra por current_floor > 0 e ordena — determinismo.
        sess2 = FakeSession([(lambda s: "player_dungeons" in s,
                              [(PD(7, 3), DC(7))])])
        run(dng.active_run(sess2, 111))
        sql = " ".join(sess2.seen_sql)
        check("b.sql.floor_filter", "current_floor" in sql)
        check("b.sql.order", "ORDER BY" in sql.upper(),
              "sem ordem o botão Retirar-se dança entre pedidos")
        check("b.sql.limit", "LIMIT" in sql.upper())

        # only= / exclude= produzem filtros diferentes (as duas políticas).
        s_only = FakeSession([(lambda s: "player_dungeons" in s, [])])
        run(dng.active_run(s_only, 111, only=7))
        s_excl = FakeSession([(lambda s: "player_dungeons" in s, [])])
        run(dng.active_run(s_excl, 111, exclude=7))
        check("b.sql.only_ne_exclude",
              " ".join(s_only.seen_sql) != " ".join(s_excl.seen_sql),
              "only= (varredura) e exclude= (entrada) são políticas distintas")
        check("b.sql.exclude_is_ne", "!=" in " ".join(s_excl.seen_sql))

        # Fail-open: um erro de infra NUNCA tranca o jogador fora. O engine
        # loga a exceção de propósito — calamos o logger só aqui para o
        # teste imprimir limpo (o traceback esperado viraria ruído).
        class Boom:
            async def execute(self, *a, **k):
                raise RuntimeError("db down")
        dng.logger.disabled = True
        try:
            check("b.fail_open", run(dng.active_run(Boom(), 111)) is None,
                  "falhar fechado trancaria a masmorra por um erro de infra")
        finally:
            dng.logger.disabled = False
    finally:
        dng.masmorra_unica_on = orig


def _policy_blocks() -> None:
    """A política do sweep, decidida e documentada (§2)."""
    src = _src("core", "dungeon_run_engine.py")
    check("b.policy.documented", "varredura" in src.lower() and "LIVRE" in src,
          "§2 mandava DECIDIR e DOCUMENTAR")

    dgs = _src("handlers", "dungeons.py")
    ws = _src("core", "webserver.py")
    # Entradas usam exclude= (a MESMA masmorra fica com o fluxo de hoje).
    check("b.policy.enter_exclude", dgs.count("exclude=dungeon_id") == 2,
          "os 2 caminhos de entrada do chat")
    check("b.policy.enter_exclude_mini", "exclude=dungeon_id" in ws)
    # Varreduras usam only= (livre noutra masmorra, recusada na própria).
    check("b.policy.sweep_only_chat", "only=dungeon_id" in dgs)
    check("b.policy.sweep_only_mini", "only=dungeon_id" in ws)


def _i18n_blocks() -> None:
    from inject_qol_relatos_i18n import CHAT, MINIAPP
    for lang in ("pt", "en", "es"):
        chat = json.loads(_src("locales", lang + ".json"))
        mini = json.loads(_src("miniapp", "i18n", lang + ".json"))
        for k in CHAT[lang]:
            check(f"i18n.chat.{lang}.{k}", k in chat)
        for k in MINIAPP[lang]:
            check(f"i18n.mini.{lang}.{k}", k in mini)

        # As recusas TÊM de nomear a masmorra e o andar (Lei §1).
        for k in ("dng_run_elsewhere", "dng_run_here"):
            v = chat.get(k, "")
            check(f"i18n.disclose.{lang}.{k}",
                  "{name}" in v and "{floor}" in v, v[:60])
        # A linha do peso tem de mostrar o tier E o peso (Lei §10).
        for surface, d, key, n in (("chat", chat, "prf_xp_gain_line_tier", "xp"),
                                   ("mini", mini, "prf_mini_xp_gain_tier", "n")):
            v = d.get(key, "")
            check(f"i18n.weight.{surface}.{lang}",
                  "{tier}" in v and "{w}" in v and "{" + n + "}" in v, v[:60])
        # A key ANTIGA continua viva (é o fallback de tier desconhecido e o
        # _test_tec1_library asserta-a).
        check(f"i18n.legacy.chat.{lang}", "prf_xp_gain_line" in chat)
        check(f"i18n.legacy.mini.{lang}", "prf_mini_xp_gain" in mini)

        # O painel auto-documenta-se (Lei §6) e grita o risco (Lei §5).
        desc = mini.get("feature_masmorra_unica_desc", "")
        check(f"i18n.feature_warn.{lang}", "LAUNCH-SERVER-BOUND" in desc,
              desc[:60])
        check(f"i18n.feature_label.{lang}",
              bool(mini.get("feature_masmorra_unica")))


def _wiring_blocks() -> None:
    """Flag sem call-site = promessa vazia."""
    check("wire.flag", '"masmorra_unica":' in _src("database", "db.py"))
    check("wire.engine", "def active_run(" in _src("core", "dungeon_run_engine.py"))

    dgs = _src("handlers", "dungeons.py")
    ws = _src("core", "webserver.py")
    tj = _src("miniapp", "components", "tabs.js")

    # OS CINCO CAMINHOS (o prompt dizia 3; o recon achou 5).
    check("wire.path1_diff_screen", "dungeon_start_difficulty" in dgs and
          dgs.count("from core.dungeon_run_engine import active_run") == 3,
          "picker + executor dng_go_ + varredura")
    check("wire.path2_executor", "_dungeon_start_with_stance" in dgs)
    check("wire.path3_sweep_chat", "dungeon_sweep_exec" in dgs)
    check("wire.path4_enter_mini", 'reason": "run_elsewhere"' in ws)
    check("wire.path5_sweep_mini", 'reason": "run_here"' in ws)
    check("wire.mini_engine_import",
          ws.count("from core.dungeon_run_engine import active_run as _dng_active_run") == 2)

    # A saída existe nas duas superfícies (Lei §1 — recusa sem saída é bug).
    check("wire.exit_chat", "dng_retreat_{run['dungeon_id']}" in dgs)
    check("wire.exit_mini", 'api("dungeons/retreat"' in tj)
    check("wire.reason_mini", '"run_elsewhere"' in tj and '"run_here"' in tj,
          "sem o case no dngReason o jogador vê 'ação falhou' genérico")

    # Item A: o canal e os 12 call sites.
    check("wire.channel", "prof_weight_tier=None" in _src("core", "quest_engine.py"))
    check("wire.helper", "def prof_weight(" in _src("core", "profession_engine.py"))
    n_sites = sum(_src(*p).count("prof_weight_tier=")
                  for p in (("handlers", "alchemy.py"), ("handlers", "inventory.py"),
                            ("handlers", "artifacts.py"), ("core", "webserver.py"),
                            ("core", "profession_engine.py")))
    check("wire.all_sites", n_sites >= 12, f"{n_sites} call sites com o peso")
    check("wire.payload_helper", "def _prof_xp_payload(" in ws)
    check("wire.payload_conditional", "return {}" in ws,
          "key nova = SEMPRE condicional (payload do main byte-idêntico)")
    check("wire.mini_shows_weight", "prf_mini_xp_gain_tier" in tj)


def _blocks() -> None:
    _weight_pure_blocks()
    _weight_track_blocks()
    _trap_blocks()
    _off_blocks()
    _active_run_blocks()
    _policy_blocks()
    _i18n_blocks()
    _wiring_blocks()


def main() -> None:
    # Espia do notify: o tier-up do ofício dispara uma notificação
    # best-effort e sem o espia o FakeSession cospe tracebacks engolidos —
    # o defeito de ruído que o MV-4 tem.
    import core.notification_engine as ne
    _o_notify = ne.notify

    async def _spy_notify(session, pid, kind, **kw):
        return None

    ne.notify = _spy_notify
    try:
        _blocks()
    finally:
        ne.notify = _o_notify

    print(f"\n{PASS} PASS · {len(FAILS)} FAIL")
    if FAILS:
        for f in FAILS:
            print(" ✗", f)
        sys.exit(1)
    print("All green — QoL-relatos Peso do Ofício + Uma Masmorra de Cada Vez.")


if __name__ == "__main__":
    main()
