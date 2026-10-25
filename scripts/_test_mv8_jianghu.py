"""MV-8 江湖 "Rios e Lagos" — suíte de regressão COMMITTED (parte 2).

Molde: `scripts/_test_tec5_forbidden.py` (a geração forte). Roda offline —
nenhuma conexão de DB: as queries passam por um `FakeSession` que só responde
ao que foi DECLARADO (query inesperada = AssertionError, não um silêncio).

O que esta suíte protege, por seção:
  1.  OFF-identity — com `jianghu` OFF nenhuma função pública faz UMA query
      (`ExplodingSession`) e todo retorno é o neutro.
  2.  O planner PURO + a semente POR MUNDO (main ≠ s2).
  3.  O Quadro: gates dos irmãos (E2), a linha PERMANENTE do material nativo,
      contratos de JOGADOR fora do pool (E1/Lei §4).
  4.  Os atos: marcha move de verdade · `jh_last` só com tipos JSON-safe (E-P3)
      · o contrato vira 'expired', nunca 'claimed' (E1) · a vendeta move a
      escala nos DOIS lados, clampada.
  5.  A 🚩 Bandeira: as 5 estruturas · o ramo de ENTRADA e o de SAÍDA (E5a) ·
      nada de estado fantasma (E5b) · a Crônica não fica muda (E5c) · o
      ocupante NUNCA dentro da string do nome (E5d) · precedência assada.
  6.  A emboscada: os 3 ramos · o débito sob o lock do caller (E6) · o
      caçador que sumiu DIZ que sumiu · o fork moral aceita a fonte nova (E7).
  7.  O kill-switch honesto: plano sem autor recebe linha de fecho (Lei §1).
  8.  Wiring por GREP (helper sem call site = promessa vazia).
  9.  i18n ×3 ×2 + os placeholders que o call site realmente passa.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
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

import core.jianghu_engine as jh          # noqa: E402
import core.region_state_engine as rst    # noqa: E402

PASS = 0
FAILS: list[str] = []
# Ancorado no relógio REAL de propósito: uma data fixa faz o teste virar
# vermelho sozinho no dia seguinte (foi o que aconteceu ao _test_tec4_caves).
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(f"{name} {('— ' + detail) if detail else ''}")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


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
        self.commits = 0

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

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    def begin_nested(self):
        return _Nested()


def _rows_of(session, cls_name: str) -> list:
    return [o for o in session.added if type(o).__name__ == cls_name]


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


_ORIG_JH_ON = jh.jianghu_on
_ORIG_RST_ON = rst.estados_on


def _on(v: bool) -> None:
    jh.jianghu_on = (lambda world_key=None: v)


def _npc(**kw):
    base = dict(id=1, name="Wúmíng", realm=5, sub_layer=3, power=900,
                continent_key="linghe", sect_id="azure_cloud", sect_rank="inner",
                path="rogue", karma=0, status="active", source_hash=None,
                loadout={"combat_profile": {"faction_dmg": 1.0}, "hp": 500})
    base.update(kw)
    return Obj(**base)


def _player(**kw):
    # ⚠️ Os campos deste stub são VALIDADOS contra o modelo real (ver
    # `stub.campos_reais` na seção 6). O stub anterior inventava `current_qi`,
    # um atributo que o Player NÃO tem — e por isso deu verde a um ramo ⚔️ que
    # recusava 100% das vezes em produção. Um stub duck-typed só protege se o
    # nome dos campos for o do modelo.
    base = dict(telegram_id=7, realm=5, karma=0, path="rogue", language="pt",
                current_continent="linghe", spirit_stones=5000, qi=500.0,
                qi_capacity=500.0, last_travel_at=None, dao_name="Teste")
    base.update(kw)
    return Obj(**base)


def _board(**kw):
    ctx = {
        "now": NOW,
        "native": {k: True for k in jh.CONTINENT_KEYS},
        "events": {k: 0 for k in jh.CONTINENT_KEYS},
        "caves": {k: False for k in jh.CONTINENT_KEYS},
        "states": {k: "prospera" for k in jh.CONTINENT_KEYS},
        "bounties": {k: [] for k in jh.CONTINENT_KEYS},
        "urgent": {k: 0 for k in jh.CONTINENT_KEYS},
        "marked": {k: 0 for k in jh.CONTINENT_KEYS},
        "seeds": {k: 2 for k in jh.CONTINENT_KEYS},
        "house_seeds": {},
        "path_seeds": {},
        "houses": {k: [] for k in jh.CONTINENT_KEYS},
    }
    ctx.update(kw)
    return ctx


async def main() -> None:
    # ═══ 1. OFF-identity — ExplodingSession em TODA função pública ═══
    _on(False)
    exp = ExplodingSession()
    check("off.pulse", await jh.jianghu_pulse(exp) is None)
    check("off.occupation", await jh.occupation_map(exp) == {})
    check("off.hunters", await jh.hunters_by_continent(exp) == {})
    check("off.ambush_offer", await jh.ambush_offer(exp, _player(), source="explore") is None)
    check("off.ambush_resolve",
          (await jh.ambush_resolve(exp, _player(), npc_id=1, branch="bribe")).get("reason") == "off")
    check("off.npc_view", jh.npc_jianghu_view(_npc(loadout={"jh_last": {"goal": "marchar"}})) is None)
    check("off.strike_mult", jh.jianghu_strike_mult(_npc(loadout={"jh_scale": 3})) == 1.0)
    # o goal `cacar` sem flag NUNCA emboscar: a chance é o 1º gate (zero query)
    check("off.ambush_zero_roll",
          await jh.ambush_offer(exp, _player(), source="travel") is None)

    # A projeção do NPC continua byte-idêntica com a flag OFF: nenhuma key nova.
    import core.npc_cultivator_engine as npce
    proj_off = npce.project_npc_for_profile(_npc(loadout={"jh_last": {"goal": "marchar"}}), "pt")
    check("off.projection_sem_key", "jianghu" not in proj_off, str(sorted(proj_off)))
    # E o fighter NUNCA carrega as chaves do mundo vivo para dentro do duelo.
    fb_off = npce.rehydrate_npc_fighter(_npc(loadout={
        "combat_profile": {"faction_dmg": 1.0}, "jh_scale": 3,
        "jh_last": {"goal": "marchar"}, "jh_hunt": {"continent": "moyu"}}))
    check("off.fighter_limpo",
          not any(k.startswith("jh_") for k in fb_off), str(sorted(fb_off)))
    check("off.fighter_dmg_intacto",
          abs(float(fb_off["combat_profile"]["faction_dmg"])
              - npce.NPC_CULTIVATOR_POWER_SCALE) < 1e-9)

    # ═══ 2. O planner PURO + a semente POR MUNDO ═══
    _on(True)
    soul_just = jh.soul_from_npc(_npc(path="righteous", karma=600, sect_id="azure_cloud"))
    soul_dem = jh.soul_from_npc(_npc(path="demonic", karma=-800, sect_id=None))
    check("puro.honra_justo_maior", soul_just["honor"] > soul_dem["honor"])
    check("puro.karma_clamp", jh._clamp_karma(-1200) == -1000 and jh._clamp_karma(9999) == 1000)
    check("puro.soul_0_1", all(0.0 <= v <= 1.0 for v in soul_just.values()))

    # A semente CARREGA o mundo: main e s2 não podem contar a mesma história.
    seq_main, seq_s2 = [], []
    for npc_id in range(1, 60):
        seq_main.append(jh.pick_goal(soul_dem, {},
                                     random.Random(jh.seed_for("main", npc_id, 100))))
        seq_s2.append(jh.pick_goal(soul_dem, {},
                                   random.Random(jh.seed_for("s2", npc_id, 100))))
    div = sum(1 for a, b in zip(seq_main, seq_s2) if a != b) / float(len(seq_main))
    check("puro.mundo_diverge", div > 0.20, f"divergência {div:.0%}")
    check("puro.seed_tem_mundo", "main" in jh.seed_for("main", 1, 1))

    # O teto do Quadro: o anúncio INCLINA, nunca DITA (o "cron job com nomes
    # chineses" que o cético previu — 100% dos NPCs em fila indiana).
    huge = {g: 99.0 for g in jh.JH_GOAL_ORDER}
    scores = jh.score_goals(soul_just, huge, random.Random(1))
    spread = max(scores.values()) - min(scores.values())
    check("puro.offer_teto", spread > 0.01,
          "com offers gigantes iguais a alma ainda tem de desempatar")

    # ═══ 3. O QUADRO ═══
    ctx = _board()
    off_poor = jh.offers_for(ctx, "moyu")
    # A linha PERMANENTE: mesmo sem evento/gruta/contrato, Mòyǔ vale algo.
    check("quadro.linha_permanente", jh._place_value(ctx, "moyu") > 0.0)
    check("quadro.marchar_zero_sem_motivo", off_poor["marchar"] == 0.0,
          "todos os lugares iguais ⇒ marchar não vale nada")
    # A LEI DE FERRO: num mundo parado os QUATRO anúncios valem 0.0. Sem isto,
    # os goals com supply permanente (o board reabastece a 4 contratos por
    # continente; sempre há vizinhos) roubavam o volante da alma — medido:
    # 214 atos, ZERO marchas e ZERO caçadas em 28 batidas.
    check("quadro.mundo_parado_zera",
          all(v == 0.0 for v in jh.offers_for(ctx, "moyu", path="demonic").values()),
          str(jh.offers_for(ctx, "moyu", path="demonic")))
    rich = _board(events={"moyu": 2, "linghe": 0, "qianhe": 0, "yanshan": 0, "fenghuo": 0})
    check("quadro.marchar_sobe", jh.offers_for(rich, "linghe")["marchar"] > 0.0)
    b2 = _board(urgent={"linghe": 3, "qianhe": 0, "yanshan": 0, "fenghuo": 0, "moyu": 0},
                bounties={"linghe": [1, 2, 3], "qianhe": [], "yanshan": [],
                          "fenghuo": [], "moyu": []})
    check("quadro.contrato_e_urgencia",
          abs(jh.offers_for(b2, "linghe")["contrato"] - 2 * jh.JH_OFFER_BOUNTY) < 1e-9,
          "o anúncio é a URGÊNCIA (≤2), nunca a pilha de contratos")
    b3 = _board(bounties={"linghe": [1, 2, 3, 4], "qianhe": [], "yanshan": [],
                          "fenghuo": [], "moyu": []})
    check("quadro.estoque_nao_anuncia", jh.offers_for(b3, "linghe")["contrato"] == 0.0,
          "4 contratos parados = supply permanente = volante roubado da alma")
    homog = _board(path_seeds={("demonic", "moyu"): 4})
    check("quadro.vendeta_sem_desafeto",
          jh.offers_for(homog, "moyu", npc_id=1, path="demonic")["vendeta"] == 0.0,
          "Mòyǔ é todo demoníaco — ninguém ali tem contas a acertar")
    mixed = _board(path_seeds={("demonic", "linghe"): 2})
    check("quadro.vendeta_com_desafeto",
          jh.offers_for(mixed, "linghe", npc_id=1, path="righteous")["vendeta"] > 0.0)
    marked = _board(marked={"linghe": 2, "qianhe": 0, "yanshan": 0, "fenghuo": 0, "moyu": 0})
    check("quadro.cacar_precisa_de_cabeca",
          jh.offers_for(marked, "linghe")["cacar"] > 0.0
          and jh.offers_for(_board(), "linghe")["cacar"] == 0.0,
          "sem cabeça marcada ninguém sai à procura — e a emboscada se cala sozinha")

    # A gravidade de casa: é ela que junta 3 bandeiras num continente estrangeiro.
    grav = _board(house_seeds={("azure_cloud", "moyu"): 2})
    check("quadro.gravidade_de_casa",
          jh.offers_for(grav, "linghe", sect_id="azure_cloud")["marchar"]
          > jh.offers_for(_board(), "linghe", sect_id="azure_cloud")["marchar"])
    # E o CONTRAPESO dela: sem lotação a onda vira funil (medido em 30 dias —
    # 5 casas empilhadas no mesmo continente, Línghé e Mòyǔ esvaziando).
    crowd = _board(seeds={"linghe": 2, "qianhe": 12, "yanshan": 2,
                          "fenghuo": 2, "moyu": 2})
    check("quadro.lotacao_repele",
          jh._destination_value(crowd, "qianhe", None)
          < jh._destination_value(crowd, "yanshan", None))
    # A MESMA régua dos dois lados: medir "aqui" com uma régua e "lá" com outra
    # dava uma penalidade fixa de −0,15 a toda marcha ⇒ zero marchas em 7 dias.
    flat = _board()
    check("quadro.mesma_regua",
          jh.offers_for(flat, "linghe", sect_id=None)["marchar"] == 0.0,
          "mundo plano ⇒ marchar vale exatamente zero, nem negativo nem punido")
    # A ocupação NÃO pode aumentar a atração do destino (ratchet medido).
    occ = _board(states={"fenghuo": "ocupada", "linghe": "prospera",
                         "qianhe": "prospera", "yanshan": "prospera", "moyu": "prospera"})
    check("quadro.ocupada_nao_atrai",
          jh._place_value(occ, "fenghuo") == jh._place_value(_board(), "fenghuo"),
          "ocupar → desordem → mais atração → mais gente = ratchet sem freio")

    # O DRIFT: sem ele o continente esquecido nunca recebe ninguém.
    pop = _board(seeds={"linghe": 40, "qianhe": 2, "yanshan": 2, "fenghuo": 2, "moyu": 1})
    targets = [jh.march_target(pop, "linghe", None, random.Random(f"d{i}")) for i in range(400)]
    check("quadro.drift_alcanca_moyu", "moyu" in targets,
          "sem drift o destino seria sempre o mais rico")
    check("quadro.nunca_marcha_para_si", "linghe" not in targets)

    # ═══ 4. OS ATOS ═══
    npc = _npc(continent_key="linghe", sect_id="azure_cloud")
    ctx4 = _board(seeds={"linghe": 3, "qianhe": 1, "yanshan": 1, "fenghuo": 1, "moyu": 1})
    out = await _act(jh._act_marchar, npc, ctx4)
    check("ato.marcha_move", npc.continent_key != "linghe", str(npc.continent_key))
    check("ato.marcha_desconta_origem", ctx4["seeds"]["linghe"] == 2)
    check("ato.marcha_manda_to_continent",
          out["chron_params"].get("to_continent_key") == npc.continent_key)
    check("ato.marcha_chron_na_origem", out["chron_continent"] == "linghe",
          "a notícia parte de onde ele saiu")

    hunter = _npc(continent_key="moyu")
    await _act(jh._act_cacar, hunter, _board())
    hunt = (hunter.loadout or {}).get("jh_hunt") or {}
    check("ato.cacar_marca", hunt.get("continent") == "moyu")
    check("ato.cacar_json_safe", isinstance(hunt.get("until"), str),
          "datetime no JSONB estoura o INSERT do PRÓXIMO duelo do NPC")

    # `jh_last` só com tipos JSON-safe (a armadilha que só apareceria horas
    # depois, no duelo seguinte daquele NPC, longe da causa).
    jh._set_loadout(npc, jh_last={"goal": "marchar", "epoch": 1,
                                  "at": NOW.isoformat(), "target": "moyu"})
    try:
        json.dumps(npc.loadout)
        json_ok = True
    except TypeError:
        json_ok = False
    check("ato.loadout_serializa", json_ok)
    check("ato.loadout_dict_novo", isinstance(npc.loadout, dict))

    # A vendeta move a escala nos DOIS lados e clampa.
    a, b = _npc(id=1, power=1000), _npc(id=2, power=100)
    sess_v = FakeSession([
        (lambda s, p: "npc_cultivators" in s and "id !=" in s.replace("!=", "!="), [b]),
        (lambda s, p: "npc_cultivators" in s, lambda p: [a]),
    ])
    # (o handler acima devolve `b` para a busca de pares e `a` para os locks)
    res_v = await jh._act_vendeta(sess_v, a, _board(), random.Random(3), NOW)
    check("ato.vendeta_ocorre", res_v is not None)
    check("ato.vendeta_nomes_proprios",
          set(res_v["chron_params"]) == {"npc", "other"} if res_v else False)

    check("ato.escala_clampa",
          abs(jh.jianghu_strike_mult(_npc(loadout={"jh_scale": 99}))
              - (1.0 + jh.JH_SCALE_STEP * jh.JH_SCALE_MAX)) < 1e-9)
    check("ato.escala_negativa",
          jh.jianghu_strike_mult(_npc(loadout={"jh_scale": -99}))
          == 1.0 - jh.JH_SCALE_STEP * jh.JH_SCALE_MAX)

    # ═══ E1 — o contrato NUNCA é "reclamado" por um NPC ═══
    src_jh = _read("core/jianghu_engine.py")
    # (a menção em COMENTÁRIO é a explicação do porquê; o que não pode existir
    # é uma ESCRITA — `claimed_by` é FK para players.telegram_id, e gravar um
    # npc_id ali ou viola a FK ou atribui o contrato a um JOGADOR REAL.)
    check("e1.sem_claimed_by",
          not re.search(r"^\s*[\w.]*\.?claimed_by\s*=", src_jh, re.MULTILINE)
          and "claimed_by=" not in src_jh,
          "nenhuma ESCRITA em bounties.claimed_by")
    check("e1.sem_claim_bounty", "import claim_bounty" not in src_jh
          and "claim_bounty(" not in src_jh,
          "claim_bounty exige 5 condições de duelo que um NPC não tem")
    check("e1.usa_expired", 'row.status = "expired"' in src_jh)
    check("e1.exclui_posted_by", "Bounty.posted_by.is_(None)" in src_jh,
          "apagar contrato pago por jogador viola a Lei §4")
    check("e1.revalida_sob_lock", 'row.posted_by is not None' in src_jh)

    # ═══ 5. A 🚩 BANDEIRA ═══
    check("bandeira.valid_states", rst.STATE_OCUPADA in rst.VALID_STATES)
    check("bandeira.meta", rst.STATE_OCUPADA in rst.STATE_META)
    check("bandeira.chron_keys", rst.STATE_OCUPADA in rst._CHRON_KEYS)
    check("bandeira.price", rst.PRICE_MULTS.get(rst.STATE_OCUPADA, 1.0) > 1.0,
          "sobretaxa = SINK; um desconto aqui seria faucet de graça")
    check("bandeira.explore_risk", rst.EXPLORE_RISK_BUMPS.get(rst.STATE_OCUPADA, 0) >= 1)
    check("bandeira.nao_fecha_estrada", "STATE_OCUPADA" not in
          _read("core/region_state_engine.py").split("async def road_penalized_continents")[1][:600],
          "a ocupação NÃO fecha a estrada (Lei §1: dá para entrar e sair)")
    check("bandeira.sem_estado_fantasma",
          rst.normalize_state("ocupada") == "ocupada",
          "fora de VALID_STATES o normalize coage para prospera e o jogo "
          "inteiro leria 'Próspera' numa row que diz 'ocupada'")

    # (a) o ramo de ENTRADA e (b) o de SAÍDA — sem eles a ocupação dura 1 pulse
    check("bandeira.entra",
          rst._next_state("prospera", NOW, {"occupied_by": "abyssal_depths"}, NOW)
          == rst.STATE_OCUPADA)
    check("bandeira.persiste_na_janela",
          rst._next_state("ocupada", NOW - timedelta(hours=1), {}, NOW)
          == rst.STATE_OCUPADA,
          "o catch-all `return STATE_PROSPERA` mataria a bandeira em 6h")
    check("bandeira.sai_com_rescaldo",
          rst._next_state("ocupada",
                          NOW - timedelta(hours=rst.OCUPADA_HOURS + 1), {}, NOW)
          == rst.STATE_TENSA,
          "ocupada → tensa → prospera (o degrau que já existe)")
    # Precedência assada: sitiada > ocupada > tensa > festival > decay
    check("bandeira.sitiada_manda",
          rst._next_state("prospera", NOW,
                          {"tide_ignored": True, "occupied_by": "x"}, NOW)
          == rst.STATE_SITIADA)
    check("bandeira.ocupada_acima_de_tensa",
          rst._next_state("prospera", NOW,
                          {"tide_active": True, "occupied_by": "x"}, NOW)
          == rst.STATE_OCUPADA)
    check("bandeira.ocupada_acima_de_festival",
          rst._next_state("prospera", NOW,
                          {"festival": True, "occupied_by": "x"}, NOW)
          == rst.STATE_OCUPADA)
    # OFF-identity da máquina: sem ocupante o resultado é o de antes do MV-8.
    check("bandeira.off_identity_maquina",
          rst._next_state("prospera", NOW, {"tide_active": True}, NOW) == rst.STATE_TENSA
          and rst._next_state("sitiada", NOW, {}, NOW) == rst.STATE_TENSA
          and rst._next_state("prospera", NOW, {}, NOW) == rst.STATE_PROSPERA)

    # (c) a transição mais importante da onda não pode ser a única MUDA
    rst_src = _read("core/region_state_engine.py")
    check("bandeira.chron_get_nao_index", "_CHRON_KEYS.get(nxt)" in rst_src,
          "`_CHRON_KEYS[nxt]` cru vive dentro de um except que só loga")
    check("bandeira.chron_passa_sect", 'sect_id=(occ or {}).get("sect_id")' in rst_src,
          "sem o sect_id o {sect} da linha não resolve")
    # (d) o ocupante NUNCA dentro da string do nome (t() é chamado sem kwargs)
    loc = json.load(open(os.path.join(ROOT, "locales", "pt.json"), encoding="utf-8"))
    check("bandeira.nome_sem_placeholder",
          "{" not in loc["rst_ocupada_name"] and "{" not in loc["rst_ocupada_desc"],
          "state_views/local_state_view chamam t() SEM kwargs ⇒ a chaveta vazaria")
    check("bandeira.ocupante_e_campo_aditivo", '"occupant": occupant' in rst_src)
    check("bandeira.ocupante_com_kwargs", '"rst_ocupada_by", sect=name' in rst_src)

    # A presença é DERIVADA e só conta continente ESTRANGEIRO.
    check("bandeira.so_estrangeiro",
          "get_native_continent_for_sect(str(sect_id)) == continent" in src_jh)
    check("bandeira.so_elenco", "NpcCultivator.source_hash.is_(None)" in src_jh)

    # ═══ 6. A EMBOSCADA ═══
    hunter2 = _npc(id=42, name="Lǐ Xuèyè", continent_key="linghe", loadout={
        "combat_profile": {"faction_dmg": 1.0},
        "jh_hunt": {"continent": "linghe", "until": (NOW + timedelta(hours=5)).isoformat()},
    })
    pl = _player(spirit_stones=5000)
    sess_a = FakeSession([(lambda s, p: "karma_log" in s, []),
                          (lambda s, p: "duel_sessions" in s, []),
                          (lambda s, p: "npc_cultivators" in s, [hunter2])])
    res = await jh.ambush_resolve(sess_a, pl, npc_id=42, branch="bribe", lang="pt")
    check("emb.bribe_ok", res.get("ok") is True, str(res))
    check("emb.bribe_debita", pl.spirit_stones < 5000)
    check("emb.bribe_registra", len(_rows_of(sess_a, "KarmaLog")) == 1,
          "o pacer precisa da marca (💰/🏃 não criam duelo)")
    check("emb.bribe_delta_zero",
          all(int(r.delta) == 0 for r in _rows_of(sess_a, "KarmaLog")),
          "um suborno não é um ato de karma")

    poor = _player(spirit_stones=1)
    sess_p = FakeSession([(lambda s, p: "karma_log" in s, []), (lambda s, p: "duel_sessions" in s, []), (lambda s, p: "npc_cultivators" in s, [hunter2])])
    res_p = await jh.ambush_resolve(sess_p, poor, npc_id=42, branch="bribe")
    check("emb.bribe_sem_pedras", res_p.get("reason") == "not_enough_stones")
    check("emb.bribe_diz_o_numero", res_p.get("cost") and res_p.get("have") is not None,
          "Lei §1 — o número é dito, e o botão aparece desabilitado")
    check("emb.bribe_nao_debita", poor.spirit_stones == 1)

    pl2 = _player()
    sess_f = FakeSession([(lambda s, p: "karma_log" in s, []), (lambda s, p: "duel_sessions" in s, []), (lambda s, p: "npc_cultivators" in s, [hunter2])])
    res_f = await jh.ambush_resolve(sess_f, pl2, npc_id=42, branch="flee")
    check("emb.flee_ok", res_f.get("ok") is True)
    check("emb.flee_custa_a_estrada", pl2.last_travel_at is not None)
    check("emb.flee_nao_custa_hp_nem_karma",
          getattr(pl2, "karma", 0) == 0 and pl2.spirit_stones == 5000)

    gone = _npc(id=43, status="ascended", loadout={})
    sess_g = FakeSession([(lambda s, p: "karma_log" in s, []), (lambda s, p: "duel_sessions" in s, []), (lambda s, p: "npc_cultivators" in s, [gone])])
    res_g = await jh.ambush_resolve(sess_g, _player(), npc_id=43, branch="fight")
    check("emb.cacador_sumido_DIZ", res_g.get("reason") == "hunter_gone",
          "Lei §1 — nunca um botão que não faz nada")

    expired = _npc(id=44, loadout={"jh_hunt": {
        "continent": "linghe", "until": (NOW - timedelta(hours=1)).isoformat()}})
    sess_e = FakeSession([(lambda s, p: "karma_log" in s, []), (lambda s, p: "duel_sessions" in s, []), (lambda s, p: "npc_cultivators" in s, [expired])])
    check("emb.janela_expirada",
          (await jh.ambush_resolve(sess_e, _player(), npc_id=44, branch="fight"))
          .get("reason") == "hunter_gone")

    check("emb.ramo_invalido",
          (await jh.ambush_resolve(FakeSession([]), _player(), npc_id=1, branch="x"))
          .get("reason") == "invalid_branch")

    # ═══ 6-bis. AS REGRESSÕES PERMANENTES DO REVIEW ADVERSARIAL ═══
    # (1) O stub NÃO pode inventar campos: o `current_qi` fabricado deu verde a
    # um ramo ⚔️ que recusava 100% das vezes em produção.
    from database.models import Player as _RealPlayer
    real_cols = set(_RealPlayer.__table__.columns.keys())
    stub_fields = set(_player().__dict__)
    invented = {f for f in stub_fields if f not in real_cols}
    check("stub.campos_reais", not invented, f"campos que o Player NÃO tem: {sorted(invented)}")
    check("rev1.usa_qi_real",
          "float(player.qi or 0) < qi_cost" in src_jh
          and 'getattr(player, "current_qi"' not in src_jh
          and "player.current_qi =" not in src_jh,
          "a coluna é `qi`; `current_qi` devolvia 0 e recusava toda luta")

    # (2) O encontro é CONSUMIDO: um 2º toque em 💰 não debita de novo.
    hunter3 = _npc(id=50, continent_key="linghe", loadout={
        "combat_profile": {"faction_dmg": 1.0},
        "jh_hunt": {"continent": "linghe", "until": (NOW + timedelta(hours=5)).isoformat()},
    })
    marked_pl = _player(spirit_stones=5000)
    seen_mark = {"n": 0}

    def _cooldown_rows(p):
        # 1ª chamada: sem marca. Depois: a marca do próprio suborno.
        seen_mark["n"] += 1
        return [] if seen_mark["n"] <= 1 else [(NOW, {"branch": "bribe"})]

    sess_i = FakeSession([
        (lambda s, p: "duel_sessions" in s, []),
        (lambda s, p: "karma_log" in s, _cooldown_rows),
        (lambda s, p: "npc_cultivators" in s, [hunter3]),
    ])
    r1 = await jh.ambush_resolve(sess_i, marked_pl, npc_id=50, branch="bribe")
    stones_after = marked_pl.spirit_stones
    r2 = await jh.ambush_resolve(sess_i, marked_pl, npc_id=50, branch="bribe")
    check("rev2.primeiro_toque_paga", r1.get("ok") is True)
    check("rev2.segundo_toque_recusa", r2.get("reason") == "already_resolved", str(r2))
    check("rev2.nao_debita_duas_vezes", marked_pl.spirit_stones == stones_after)

    # (3) A fuga cobra a DÍVIDA: quem foge é procurado em metade do tempo.
    check("rev3.fuga_encurta_janela", 0.0 < jh.JH_FLEE_RETURN_FACTOR < 1.0)
    check("rev3.janela_le_o_ramo", 'meta.get("branch") or ""' in src_jh
          and "JH_FLEE_RETURN_FACTOR" in src_jh,
          "a estrada sozinha não cobra nada quando a emboscada vem logo após viajar")

    # (4) O sweep de 60s não pode custar queries vazias.
    # ⚠️ 2026-09-04: os TRÊS varredores por-fonte foram substituídos por UM só
    # (`duel_engine.sweep_orphan_pve_duels`) porque o código cria DEZ fontes e
    # sete não tinham rede nenhuma — 27 duelos expirados prendiam 13 jogadores,
    # o mais antigo há 103 dias. O gate de flag deixou de fazer sentido (o
    # varredor TEM de correr mesmo com `jianghu` OFF, pelas outras nove), mas a
    # PREOCUPAÇÃO deste assert continua válida e é a que se verifica agora:
    # **uma query indexada por tick, não uma por família**.
    # ⚠️ A FATIA E' A FUNCAO, NAO UMA JANELA DE CARACTERES (corrigido 2026-09-12).
    # Esta linha era `[:2600]` e ficou VERMELHA quando o varredor ganhou
    # comentarios — sem que uma unica linha de codigo saisse da funcao. E' a
    # SEGUNDA copia do mesmo defeito no mesmo dia (a outra estava no
    # `_test_relatos_0814.py`, com `[:4200]`): duas reguas a medir o mesmo sitio,
    # ambas por contagem de caracteres, ambas a mentir quando a prosa cresce.
    _de_src = _read("core/duel_engine.py")
    _sweep_src = _de_src.split("async def sweep_orphan_pve_duels")[1]
    _sweep_src = _sweep_src.split(chr(10) + "async def ")[0]
    check("rev4.sweep_uma_query", "pve_source.in_(PVE_SOURCES)" in _sweep_src,
          "roda a cada 60s: uma query por fonte = 14.400/dia, quase todas vazias")
    check("rev4.sweep_mais_antigo_primeiro", "created_at.asc()" in _sweep_src,
          "quem está preso há 103 dias sai à frente de quem fechou a app agora")

    # (5) A vaga do ator conta ATOS, não candidatos.
    check("rev5.conta_atos", "acted_here" in src_jh and "pool[:JH_ACTORS_PER_CONTINENT]" not in src_jh,
          "fatiar antes do cooldown fazia um NPC cansado QUEIMAR a vaga")

    # (6) O contrato expirado é sempre um URGENTE (o que o Quadro anunciou).
    check("rev6.contrato_urgente", 'ctx.get("urgent_ids"' in src_jh,
          "sortear do estoque apagava um contrato com 40h que o jogador caçava")

    # (7) A vitrine clampa a escala igual ao combate (display == roll).
    big = _npc(loadout={"jh_scale": 99})
    view_big = jh.npc_jianghu_view(big, "pt")
    mult_big = jh.jianghu_strike_mult(big)
    check("rev7.display_igual_roll",
          abs((1.0 + view_big["power_pct"] / 100.0) - mult_big) < 1e-6,
          f"card {view_big['power_pct']}% vs duelo {mult_big}")
    neg = jh.npc_jianghu_view(_npc(loadout={"jh_scale": -2}), "pt")
    check("rev7.escala_negativa_fala_outra_frase",
          "cobradas" not in (neg.get("scale_line") or "").lower(),
          "quem PERDEU a vendeta não pode ler 'dívidas cobradas'")

    # (8) O idioma da emboscada vem do JOGADOR, não de um default "pt".
    check("rev8.lang_derivado",
          'lang = (lang or getattr(player, "language", None) or "pt").lower()' in src_jh,
          "o cano de viagem (20%, o mais generoso) mandava PT a todo mundo")

    # (9) A Crônica busca por RECÊNCIA; a importância só corta o excedente.
    wpe_src2 = _read("core/world_pulse_engine.py")
    check("rev9.busca_por_recencia",
          "stmt.order_by(WorldChronicle.ts.desc())" in wpe_src2
          and "importance.desc()" not in wpe_src2,
          "ordenar por importância no SQL fazia o LIMIT pegar o hall da fama "
          "de TODA a história — o feed congelava e a importância 1 sumia")
    check("rev9.saida_cronologica",
          "kept.sort(key=lambda r: -(r.ts.timestamp() if r.ts else 0))" in wpe_src2,
          "a tela imprime timeAgo: a saída tem de ser cronológica")

    # E6 — o lock vive no CALLER, nunca no engine (duplo-tap debitaria 2×).
    check("e6.engine_nao_seleciona_player",
          "select(Player)" not in src_jh,
          "o engine tem de RECEBER a row já FOR UPDATE (contrato do do_travel)")
    ws = _read("core/webserver.py")
    check("e6.endpoint_trava",
          "api_world_jianghu_ambush" in ws
          and "select(Player).where(Player.telegram_id == user_id).with_for_update()"
          in ws.split("api_world_jianghu_ambush")[1][:1600])
    check("e6.rota_registrada",
          'add_post("/api/miniapp/world/jianghu_ambush"' in ws)
    check("e6.chat_trava",
          ".with_for_update()" in _read("handlers/sect.py")
          .split("async def jianghu_button_router")[1][:2200])

    # E7 — o fork moral NÃO nasce sozinho: a emboscada tem de OFERECER a escolha.
    #
    # ⚠️ 2026-09-16 — a guarda SEGUE A INDIRECÇÃO em vez de se baixar. Até hoje
    # a fase moral estava REIMPLEMENTADA à mão dentro deste modal, e isso era
    # exactamente o problema: havia três cópias (o perfil do NPC, esta
    # emboscada e o Monstro Escondido), as três com o mesmo defeito, e uma
    # delas já tinha perdido a linha do Caminho cristalizado. Agora há um dono
    # (`useDecisaoMoral`). O que esta guarda protege é o mesmo de sempre — *o
    # fork não pode nascer invisível* — mas medido nos DOIS saltos: o modal
    # liga-se ao dono, e o dono faz mesmo as duas coisas.
    tabs = _read("miniapp/components/tabs.js")
    check("e7.modal_existe", "function JianghuAmbushModal(" in tabs)
    _jh = tabs.split("function JianghuAmbushModal(")[1][:6000]
    check("e7.modal_liga_ao_dono",
          "useDecisaoMoral({" in _jh and "setFase: setPhase" in _jh,
          "sem a ligação ao dono, o fork nasce INVISÍVEL mesmo com o servidor correto")
    check("e7.modal_oferece_a_escolha",
          'escolher("spare")' in _jh and 'escolher("execute")' in _jh,
          "os dois botões da escolha moral têm de estar NESTA tela")
    _dono = tabs.split("function useDecisaoMoral(")[1][:6000]         if "function useDecisaoMoral(" in tabs else ""
    check("e7.dono_abre_a_fase_moral",
          'setFase("moral")' in _dono,
          "o dono tem de levar à fase moral depois de uma vitória CONFIRMADA")
    check("e7.usa_endpoint_do_fork",
          '"combat/npc_cultivator_resolve"' in _dono)
    check("e7.fonte_aceita_no_servidor",
          '"jianghu_ambush"' in _read("core/npc_cultivator_engine.py"),
          "sem a fonte na tupla o fork responde not_your_duel")

    # A fonte tem de estar no dispatcher, ou é recompensa MORTA e silenciosa.
    pds = _read("core/pve_duel_settle.py")
    check("emb.fonte_no_dispatcher", 'duel.pve_source == "jianghu_ambush"' in pds)
    check("emb.fonte_cabe_no_varchar", len(jh.JH_AMBUSH_SOURCE) <= 24,
          f"{jh.JH_AMBUSH_SOURCE} = {len(jh.JH_AMBUSH_SOURCE)} chars")
    # ⚠️ A garantia é a mesma; o sítio onde vive mudou (ver (4) acima). A fonte
    # da emboscada tem de estar no REGISTO único, e o registo tem de ser varrido
    # pelo scheduler. Baixar isto para "o nome existe algures" teria deixado a
    # emboscada sem rede no dia em que alguém renomeasse a função.
    check("emb.fonte_no_registo_unico",
          '"jianghu_ambush",' in _de_src.split("PVE_SOURCES = (")[1][:900],
          "há 23 duelos órfãos em prod hoje — sem estar no registo, ninguém varre")
    check("emb.registo_varrido_pelo_scheduler",
          "sweep_orphan_pve_duels" in _read("core/scheduler.py"))

    # O público — um OU declarado (karma sozinho alcança 6 pessoas em prod).
    check("emb.publico_karma", "JH_MARK_KARMA" in src_jh)
    check("emb.publico_ato", "JH_MARK_EVENTS" in src_jh and "combat_execute" in src_jh)
    check("emb.publico_rep", "get_region_rep" in src_jh)
    check("emb.pacer_proprio", "JH_AMBUSH_COOLDOWN_H" in src_jh,
          "o explore NÃO tem cooldown — sem pacer vira corredor de emboscadas")

    # ═══ 7. O KILL-SWITCH HONESTO ═══
    dead = _npc(id=9, status="ascended",
                loadout={"jh_last": {"goal": "marchar", "epoch": 1,
                                     "at": NOW.isoformat(), "target": "moyu"}})
    emitted: list[dict] = []

    async def _fake_emit(session, **kw):
        emitted.append(kw)
        return Obj(id=1)

    import core.world_pulse_engine as wpe
    _orig_emit = wpe.emit_chronicle
    wpe.emit_chronicle = _fake_emit
    try:
        sess_k = FakeSession([(lambda s, p: "npc_cultivators" in s, [dead])])
        closed = await jh._jianghu_sweep(sess_k, NOW)
        check("kill.fecha_o_plano", closed == 1,
              "41% do elenco do s2 já ascendeu — um plano sem fecho é o void")
        check("kill.linha_de_fecho",
              emitted and emitted[0].get("text_key") == "jh_chron_sumiu")
        check("kill.limpa_a_marca", not (dead.loadout or {}).get("jh_last"))
    finally:
        wpe.emit_chronicle = _orig_emit

    # ═══ 8. WIRING (helper sem call site = promessa vazia) ═══
    sch = _read("core/scheduler.py")
    check("wire.passo6", "jianghu_pulse" in sch)
    check("wire.passo6_depois_do_mercado",
          sch.index("generate_market_reports") < sch.index("from core.jianghu_engine import jianghu_pulse"))
    check("wire.instrumentacao", "_time.monotonic()" in src_jh,
          "o pulse não tinha NENHUMA instrumentação e MV-8 é o 1º passo O(N)")
    check("wire.cede_o_loop", "asyncio.sleep(0)" in src_jh,
          "o loop das 9 casas não cede — não repetir o defeito")
    check("wire.gate_do_irmao_director", "if director_on():" in src_jh)
    check("wire.gate_do_irmao_grutas", "if legacy_caves_on():" in src_jh)
    check("wire.dict_puro_de_loot",
          "REGIONAL_BONUS_LOOT" in src_jh and "regional_bonus_line" not in src_jh,
          "regional_bonus_line é async, dispara 10 queries e usa 'Tributo' (OCUPADA)")
    wpe_src = _read("core/world_pulse_engine.py")
    check("wire.to_continent_resolvido", 'out["to_continent"]' in wpe_src,
          "sem o 4º ramo o jogador lê `{to_continent}` cru na cara")
    check("wire.latencia", "viewer_continent" in wpe_src and "rumor_delay_hours" in wpe_src)
    check("wire.importance_lido", "int(r.importance or 1)" in wpe_src,
          "a coluna era escrita por 20 call sites e lida por NINGUÉM — agora ela "
          "escolhe o que CORTAR do excedente, nunca o que é BUSCADO")
    check("wire.dedupe_por_epoch", 'last.get("epoch", -1)) == epoch' in src_jh,
          "a Chronicle não tem dedupe nenhum e o job é coalesce=True")
    check("wire.elenco_seed_only", src_jh.count("source_hash.is_(None)") >= 3)
    check("wire.exclui_bounty_e_rival",
          "open_npc_ids" in src_jh and "rival_npc_ids" in src_jh)
    check("wire.chip_hunted", '"hunted"' in _read("core/travel_engine.py"))
    check("wire.emboscada_no_explore",
          "jianghu_ambush" in _read("core/exploration_engine.py"))
    check("wire.emboscada_na_praca", "jianghu_ambush" in ws)
    check("wire.vitrine_no_perfil",
          "npc_jianghu_view" in _read("core/npc_cultivator_engine.py"))
    check("wire.mini_praca", "d.jianghu_ambush" in tabs and "n.jianghu" in tabs)
    check("wire.mini_travel_payload",
          "res.jianghu_ambush" in _read("miniapp/components/app.js"),
          "onTraveled DESCARTAVA o payload — o encontro nascia invisível no mini")
    check("wire.chat_prefixo", 'startswith("jha_")' in _read("main.py"))
    check("wire.flag_declarada", '"jianghu"' in _read("database/db.py"))
    check("wire.storylets_ocupada",
          '"region_state": ["ocupada"]' in _read("database/seeds/storylet_seeds.py"),
          "sem eles o continente ocupado passa 72h com os storylets MUDOS")
    check("wire.zero_migration",
          not any(f.startswith("1") and "jianghu" in f.lower()
                  for f in os.listdir(os.path.join(ROOT, "migrations"))),
          "ZERO migration é restrição da onda")

    # ═══ 9. i18n ×3 ×2 ═══
    from inject_mv8_i18n import CHAT, MINI
    for label, parts, batch in (("chat", ("locales",), CHAT),
                                ("mini", ("miniapp", "i18n"), MINI)):
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

    # As keys DERIVADAS por f-string (invisíveis ao grep).
    for goal in jh.JH_GOAL_ORDER:
        check(f"i18n.derivada.{goal}", jh.goal_label_key(goal) in loc)
    check("i18n.derivada.idle", jh.goal_label_key(None) in loc)
    for reason in ("karma", "ato", "rep"):
        check(f"i18n.derivada.reason_{reason}", f"jh_amb_reason_{reason}" in loc)
    for st in rst.VALID_STATES:
        meta = rst.STATE_META[st]
        check(f"i18n.derivada.rst_{st}", meta["name_key"] in loc and meta["desc_key"] in loc)
        ck = rst._CHRON_KEYS.get(st)
        check(f"i18n.derivada.chron_{st}", ck is not None and ck[1] in loc)

    # Os placeholders que o CALL SITE realmente passa.
    call_site = {
        "jh_chron_marchar":  {"npc", "continent", "to_continent"},
        "jh_chron_cacar":    {"npc", "continent"},
        "jh_chron_contrato": {"npc", "continent"},
        "jh_chron_vendeta":  {"npc", "other", "continent"},
        "jh_chron_sumiu":    {"npc"},
        "rst_chron_ocupada": {"sect", "continent"},
        "rst_ocupada_by":    {"sect"},
        "jh_scale_line":     {"pct"},
        "jh_amb_intro":      {"npc"},
        "jh_amb_hint":       {"qi", "cost", "hours"},
        "jh_amb_btn_bribe":  {"cost"},
        "jh_amb_bribe_ok":   {"cost", "npc"},
        "jh_amb_flee_ok":    {"npc", "hours"},
        "jh_amb_no_stones":  {"cost", "have"},
        "jh_amb_qi":         {"qi"},
        "jh_hunted_chip":    {"n"},
    }
    for lang in ("pt", "en", "es"):
        d = json.load(open(os.path.join(ROOT, "locales", f"{lang}.json"), encoding="utf-8"))
        for key, expected in call_site.items():
            got = set(re.findall(r"\{(\w+)\}", d.get(key, "")))
            check(f"i18n.callsite.{lang}.{key}", got == expected,
                  f"{sorted(got)} != {sorted(expected)}")

    _on(True)
    print(("OK " if not FAILS else "FAIL ") + f"— {PASS} asserts")
    for f in FAILS:
        print(" ✗", f)
    jh.jianghu_on = _ORIG_JH_ON
    rst.estados_on = _ORIG_RST_ON
    sys.exit(1 if FAILS else 0)


async def _act(fn, npc, ctx, seed: int = 7):
    """Roda um ato que não toca no DB (marcha/caçada) com uma sessão que
    explode: se ele passar a fazer query, o teste diz."""
    return await fn(ExplodingSession(), npc, ctx, random.Random(seed), NOW)


asyncio.run(main())
