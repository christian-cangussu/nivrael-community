"""MV-6 — teste isolado do reputation_engine (SEM DB — padrão _test_mv5).

Cobre:
  1. OFF-identity: TODA função pública com a sessão-que-explode (flag OFF =
     zero queries — os 57 do main byte-idênticos por construção).
  2. Puras: clamp, tiers, chip, curva do rival (+12%/derrota cap +60%),
     escala strike-only, taunt determinístico, janela de volta.
  3. Mutador: antes→depois, clamp ±100, milestone 25/50 (notify), corrida do
     insert (savepoint), continente inválido.
  4. Faucet de vitória NPC: cap diário + rollover do dia.
  5. Efeitos: market mult por tier + nota; pacer mods (8h reverência /
     supressão no desprezo).
  6. Decay semanal: rumo a zero (dois sentidos), presença segura a memória,
     âncora respeitada, commit próprio.
  7. O RIVAL: nascimento 8% (nunca de NPC caído) · derrota (defeats+1,
     some de novo) · misericórdia (spared) · conclusão no 5º (título +
     Chronicle + slot livre) · pulse (volta + kill-switch honesto) · view.
  8. Integração storylet: region_rep_min em _KNOWN_REQS + _matches; keys de
     i18n do engine todas no injetor ×3.

Rodar: python -X utf8 scripts/_test_mv6_reputation.py
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import core.reputation_engine as rep  # noqa: E402
import core.storylet_engine as sty  # noqa: E402

PASS = 0
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name} {('— ' + detail) if detail else ''}")


def now_utc():
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════
# Fakes (padrão _test_mv5: dispatch por substring do SQL compilado)
# ══════════════════════════════════════════════════════════════════════════

class ExplodingSession:
    """Sessão que EXPLODE em qualquer uso — prova OFF = zero queries."""
    def execute(self, *a, **k):
        raise AssertionError("query executada com flag OFF")
    def add(self, *a, **k):
        raise AssertionError("add executado com flag OFF")
    def get(self, *a, **k):
        raise AssertionError("get executado com flag OFF")
    async def commit(self):
        raise AssertionError("commit executado com flag OFF")
    async def rollback(self):
        pass


class FakeResult:
    def __init__(self, value):
        self.value = value
    def scalars(self):
        return self
    def all(self):
        if self.value is None:
            return []
        return list(self.value) if isinstance(self.value, list) else [self.value]
    def scalar_one_or_none(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value
    def scalar(self):
        return self.scalar_one_or_none()
    def first(self):
        return self.scalar_one_or_none()


class _SP:
    """SAVEPOINT fake (async CM no-op)."""
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False


class FakeSession:
    """Sessão ON: responde por substring da statement compilada."""
    def __init__(self, rep_rows=None, players=None, npcs=None, lang="pt",
                 explode_insert=False):
        self.rep_rows = list(rep_rows or [])
        self.players = list(players or [])
        self.npcs = dict(npcs or {})
        self.lang = lang
        self.explode_insert = explode_insert
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self._next_id = 900

    def _params(self, stmt):
        try:
            return dict(stmt.compile().params)
        except Exception:
            return {}

    async def execute(self, stmt, params=None):
        s = str(stmt)
        p = self._params(stmt)
        if "player_region_rep" in s:
            if "player_region_rep.rep !=" in s:
                return FakeResult([r for r in self.rep_rows if int(r.rep or 0) != 0])
            if "player_region_rep.continent_key =" in s:
                pid = p.get("player_id_1")
                cont = p.get("continent_key_1")
                hit = [r for r in self.rep_rows
                       if int(r.player_id) == int(pid) and r.continent_key == cont]
                if "player_region_rep.rep" in s.split("FROM")[0] and "player_region_rep.payload" not in s.split("FROM")[0]:
                    return FakeResult(hit[0].rep if hit else None)  # select(rep) escalar
                return FakeResult(hit[0] if hit else None)
            # mapa do jogador inteiro
            pid = p.get("player_id_1")
            return FakeResult([r for r in self.rep_rows if int(r.player_id) == int(pid)])
        if "npc_cultivators" in s:
            if "IN (" in s or "in_" in s or "npc_cultivators.id IN" in s:
                ids: list = []
                for k, v in p.items():
                    if k.startswith("id_"):
                        ids.extend(v if isinstance(v, (list, tuple, set)) else [v])
                if ids:
                    return FakeResult([self.npcs[int(i)] for i in ids if int(i) in self.npcs])
                return FakeResult(list(self.npcs.values()))
            nid = p.get("id_1")
            return FakeResult(self.npcs.get(int(nid)) if nid is not None else None)
        if "FROM players" in s:
            head = s.split("FROM")[0]
            if "rival_npc_id IS NOT NULL" in s:
                if head.count("players.") == 1:
                    # select(Player.rival_npc_id) — só a coluna
                    return FakeResult([pl.rival_npc_id for pl in self.players if pl.rival_npc_id])
                return FakeResult([pl for pl in self.players if pl.rival_npc_id is not None])
            if "players.language" in head and head.count("players.") == 1:
                return FakeResult(self.lang)
            if head.count("players.") == 2 and "players.telegram_id" in head \
                    and "players.current_continent" in head:
                return FakeResult([(int(pl.telegram_id), pl.current_continent) for pl in self.players])
            return FakeResult(self.players)
        raise AssertionError(f"query inesperada: {s[:120]}")

    def add(self, obj):
        if self.explode_insert:
            raise AssertionError("insert em corrida (esperado: savepoint engole)")
        self.added.append(obj)
        self.rep_rows.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                self._next_id += 1
                try:
                    obj.id = self._next_id
                except Exception:
                    pass

    def begin_nested(self):
        if self.explode_insert:
            raise RuntimeError("savepoint estourou (corrida simulada)")
        return _SP()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def fake_player(pid=1, cont="linghe", karma=0, rival_id=None, rival_state=None,
                titles=None, lang="pt"):
    return SimpleNamespace(
        telegram_id=pid, current_continent=cont, karma=karma, realm=3,
        language=lang, dao_name="Kuu", username="kuu",
        rival_npc_id=rival_id, rival_state=rival_state,
        unlocked_titles=list(titles or []), meridians_opened={}, path="rogue",
    )


def fake_rep_row(pid=1, cont="linghe", rep_v=0, payload=None, updated_at=None):
    return SimpleNamespace(
        player_id=pid, continent_key=cont, rep=rep_v,
        payload=dict(payload or {}), updated_at=updated_at or now_utc(),
        id=None,
    )


def fake_npc(nid=10, name="Bai Wuji", cont="linghe", status="active", realm=3):
    return SimpleNamespace(id=nid, name=name, continent_key=cont, status=status,
                           realm=realm, power=500)


# Recorders para notify/emit_chronicle (import deferido no engine → patch no módulo)
NOTIFY_CALLS: list[tuple] = []
CHRON_CALLS: list[dict] = []


async def _fake_notify(session, pid, kind, **kw):
    NOTIFY_CALLS.append((int(pid), kind, kw))
    return None


async def _fake_chronicle(session, **kw):
    CHRON_CALLS.append(kw)
    return None


async def main():
    import core.notification_engine as ne
    import core.world_pulse_engine as wpe
    _orig_notify = ne.notify
    _orig_chron = wpe.emit_chronicle
    ne.notify = _fake_notify
    wpe.emit_chronicle = _fake_chronicle

    # ══ 1. OFF-identity — TODA função pública, sessão-que-explode ══════════
    rep.reputacao_on = lambda *a, **k: False
    x = ExplodingSession()
    check("OFF get_region_rep=0", await rep.get_region_rep(x, 1, "linghe") == 0)
    check("OFF get_rep_map neutro", all(v == 0 for v in (await rep.get_rep_map(x, 1)).values()))
    check("OFF rep_chip_map={}", await rep.rep_chip_map(x, fake_player(), "pt") == {})
    check("OFF local_rep_view=None", await rep.local_rep_view(x, fake_player(), "pt") is None)
    check("OFF add_region_rep=None", await rep.add_region_rep(x, 1, "linghe", 3, "t") is None)
    check("OFF add_npc_win_rep=None", await rep.add_npc_win_rep(x, fake_player(), "linghe") is None)
    check("OFF market_rep_mult=1.0", await rep.market_rep_mult(x, fake_player()) == 1.0)
    check("OFF market_rep_note=None", await rep.market_rep_note(x, fake_player(), "pt") is None)
    mods = await rep.offer_pacer_mods(x, fake_player())
    check("OFF offer_pacer_mods neutro", mods == {"cooldown_hours": None, "suppressed": False})
    check("OFF decay=None", await rep.decay_region_rep(x) is None)
    check("OFF rival_npc_ids=set()", await rep.rival_npc_ids(x) == set())
    check("OFF on_npc_duel_settled=None", await rep.on_npc_duel_settled(x, fake_player(), 10, True) is None)
    check("OFF rival_pulse=None", await rep.rival_pulse(x) is None)
    check("OFF rival_view=None", await rep.rival_view(x, fake_player(rival_id=10), "pt") is None)

    # ══ 2. Puras ═══════════════════════════════════════════════════════════
    check("faucet negativo existe (desprezo alcançável)", rep.REP_STORYLET_EXPIRED < 0)
    check("clamp 250→100", rep.clamp_rep(250) == 100)
    check("clamp -250→-100", rep.clamp_rep(-250) == -100)
    check("clamp None→0", rep.clamp_rep(None) == 0)
    check("tier 50=reverence", rep.rep_tier(50) == "reverence")
    check("tier 49=respected", rep.rep_tier(49) == "respected")
    check("tier 25=respected", rep.rep_tier(25) == "respected")
    check("tier 24=neutral", rep.rep_tier(24) == "neutral")
    check("tier 0=neutral", rep.rep_tier(0) == "neutral")
    check("tier -24=neutral", rep.rep_tier(-24) == "neutral")
    check("tier -25=contempt", rep.rep_tier(-25) == "contempt")
    chip = rep.rep_chip(50, "pt")
    check("chip line assinada", "+50" in chip["line"], chip["line"])
    check("chip emoji reverence", chip["emoji"] == "🏮")
    chipn = rep.rep_chip(-30, "pt")
    check("chip negativo", "-30" in chipn["line"] and chipn["tier"] == "contempt")
    check("power_mult 1 derrota", abs(rep.rival_power_mult({"defeats": 1}) - 1.12) < 1e-9)
    check("power_mult 3 derrotas", abs(rep.rival_power_mult({"defeats": 3}) - 1.36) < 1e-9)
    check("power_mult cap 5", abs(rep.rival_power_mult({"defeats": 5}) - 1.60) < 1e-9)
    check("power_mult cap 10", abs(rep.rival_power_mult({"defeats": 10}) - 1.60) < 1e-9)
    check("power_mult None→1.0", rep.rival_power_mult(None) == 1.0)
    fighter = {"combat_profile": {"faction_dmg": 0.95, "eff_hp": 1000.0}, "hp": 1000.0}
    scaled = rep.apply_rival_scaling(dict(fighter), {"defeats": 2})
    check("escala strike-only ×1.24", abs(scaled["combat_profile"]["faction_dmg"] - 0.95 * 1.24) < 1e-9)
    check("escala não toca hp", scaled["hp"] == 1000.0)
    check("escala não toca eff_hp", scaled["combat_profile"]["eff_hp"] == 1000.0)
    check("escala stampa mult", abs(scaled["rival_power_mult"] - 1.24) < 1e-9)
    noprof = rep.apply_rival_scaling({"hp": 5.0}, {"defeats": 2})
    check("escala sem profile não quebra", noprof["hp"] == 5.0)
    st = {"taunt_seed": 3, "defeats": 2}
    t1 = rep.rival_taunt(st, "pt")
    t2 = rep.rival_taunt(dict(st), "pt")
    check("taunt determinístico", t1 == t2 and len(t1) > 0, t1[:40])
    t3 = rep.rival_taunt({"taunt_seed": 3, "defeats": 3}, "pt")
    check("taunt muda com derrotas", t1 != t3)
    tsp = rep.rival_taunt({"taunt_seed": 3, "defeats": 2, "spared": True}, "pt")
    check("taunt spared é outro", tsp != t1 and len(tsp) > 0)
    check("janela 48h×2", rep._rival_return_window({"defeats": 2}) == timedelta(hours=96))

    # ══ 3. Mutador (ON) ════════════════════════════════════════════════════
    rep.reputacao_on = lambda *a, **k: True
    NOTIFY_CALLS.clear()
    fs = FakeSession(rep_rows=[fake_rep_row(1, "linghe", 20)])
    out = await rep.add_region_rep(fs, 1, "linghe", 10, "test", lang="pt")
    check("mutador antes→depois", out and out["before"] == 20 and out["after"] == 30, str(out))
    check("milestone 25 no out", out.get("milestone") == 25)
    check("milestone notificou", any(k == "region_rep_milestone" for _, k, _2 in NOTIFY_CALLS))
    fs = FakeSession(rep_rows=[fake_rep_row(1, "linghe", 95)])
    out = await rep.add_region_rep(fs, 1, "linghe", 10, "test", lang="pt")
    check("clamp no topo", out["after"] == 100 and out["delta"] == 5)
    fs = FakeSession(rep_rows=[fake_rep_row(1, "linghe", -95)])
    out = await rep.add_region_rep(fs, 1, "linghe", -10, "test", lang="pt")
    check("clamp no fundo", out["after"] == -100)
    fs = FakeSession()
    out = await rep.add_region_rep(fs, 1, "linghe", 3, "test", lang="pt")
    check("insert row nova", out and out["after"] == 3 and len(fs.added) == 1, str(out))
    check("delta 0 → None", await rep.add_region_rep(FakeSession(), 1, "linghe", 0, "t") is None)
    check("continente inválido → None", await rep.add_region_rep(FakeSession(), 1, "atlantida", 5, "t") is None)
    fs = FakeSession(explode_insert=True)
    out = await rep.add_region_rep(fs, 1, "linghe", 3, "test", lang="pt")
    check("corrida do insert não levanta", out is None)

    # ══ 4. Faucet NPC com cap diário ═══════════════════════════════════════
    today = now_utc().date().isoformat()
    row = fake_rep_row(1, "linghe", 5, payload={"day": today, "wins": 2})
    fs = FakeSession(rep_rows=[row])
    out = await rep.add_npc_win_rep(fs, fake_player(), "linghe")
    check("win 3/3 conta", out and out["after"] == 6, str(out))
    check("payload wins=3", row.payload.get("wins") == 3)
    out = await rep.add_npc_win_rep(fs, fake_player(), "linghe")
    check("win 4 capada", out is None)
    row2 = fake_rep_row(1, "linghe", 5, payload={"day": "2020-01-01", "wins": 3})
    fs = FakeSession(rep_rows=[row2])
    out = await rep.add_npc_win_rep(fs, fake_player(), "linghe")
    check("rollover do dia reseta", out is not None and row2.payload.get("wins") == 1)

    # ══ 5. Efeitos: mercado + pacer ════════════════════════════════════════
    async def _mult_for(v):
        return await rep.market_rep_mult(FakeSession(rep_rows=[fake_rep_row(1, "linghe", v)]), fake_player())
    check("mult 30 → 0.95", await _mult_for(30) == rep.REP_DISCOUNT_MULT)
    check("mult 60 → 0.95", await _mult_for(60) == rep.REP_DISCOUNT_MULT)
    check("mult -30 → 1.05", await _mult_for(-30) == rep.REP_CONTEMPT_MULT)
    check("mult 10 → 1.0", await _mult_for(10) == 1.0)
    note = await rep.market_rep_note(FakeSession(rep_rows=[fake_rep_row(1, "linghe", 30)]), fake_player(), "pt")
    check("nota desconto existe", note is not None and "5" in note, str(note))
    note0 = await rep.market_rep_note(FakeSession(rep_rows=[fake_rep_row(1, "linghe", 0)]), fake_player(), "pt")
    check("nota neutra = None", note0 is None)
    m = await rep.offer_pacer_mods(FakeSession(rep_rows=[fake_rep_row(1, "linghe", 55)]), fake_player())
    check("pacer reverência 8h", m["cooldown_hours"] == rep.REP_PRIORITY_COOLDOWN_HOURS and not m["suppressed"])
    m = await rep.offer_pacer_mods(FakeSession(rep_rows=[fake_rep_row(1, "linghe", -40)]), fake_player())
    check("pacer desprezo suprime", m["suppressed"] and m["cooldown_hours"] is None)
    m = await rep.offer_pacer_mods(FakeSession(rep_rows=[fake_rep_row(1, "linghe", 10)]), fake_player())
    check("pacer neutro", m == {"cooldown_hours": None, "suppressed": False})

    # ══ 6. Decay semanal ═══════════════════════════════════════════════════
    old = now_utc() - timedelta(days=10)
    r_far = fake_rep_row(1, "qianhe", 10, updated_at=old)
    r_here = fake_rep_row(1, "linghe", 10, updated_at=old)
    r_neg = fake_rep_row(1, "moyu", -10, updated_at=old)
    r_fresh = fake_rep_row(1, "fenghuo", 10, updated_at=now_utc() - timedelta(days=1))
    fs = FakeSession(rep_rows=[r_far, r_here, r_neg, r_fresh],
                     players=[fake_player(1, "linghe")])
    out = await rep.decay_region_rep(fs)
    check("decay contou 2", out and out["decayed"] == 2, str(out))
    check("decay longe 10→9", r_far.rep == 9)
    check("decay presença intocada", r_here.rep == 10)
    check("decay negativo -10→-9 (cicatriza)", r_neg.rep == -9)
    check("decay âncora fresca intocada", r_fresh.rep == 10)
    check("decay stampa last_decay", "last_decay" in r_far.payload)
    check("decay commit próprio", fs.commits == 1)
    fs2 = FakeSession(rep_rows=[r_far], players=[fake_player(1, "linghe")])
    await rep.decay_region_rep(fs2)
    check("decay não repete na mesma semana", r_far.rep == 9)

    # ══ 7. O RIVAL ═════════════════════════════════════════════════════════
    _orig_random = rep.random
    rep.random = SimpleNamespace(random=lambda: 0.01, randint=lambda a, b: 7,
                                 uniform=_orig_random.uniform)
    # 7a. Nascimento (win, sem rival, npc ativo, roll < 8%)
    NOTIFY_CALLS.clear()
    p = fake_player(1, "linghe")
    npc = fake_npc(10, status="active")
    fs = FakeSession(rep_rows=[], npcs={10: npc})
    out = await rep.on_npc_duel_settled(fs, p, 10, True)
    check("nascimento: rival stampado", p.rival_npc_id == 10)
    check("nascimento: defeats=1", (p.rival_state or {}).get("defeats") == 1)
    check("nascimento: taunt_seed determinístico", (p.rival_state or {}).get("taunt_seed") == 7)
    check("nascimento: notify born", any(k == "rival_born" for _, k, _2 in NOTIFY_CALLS))
    check("nascimento: rep do win no out", out and "rep" in out, str(out))
    # 7b. NUNCA de NPC caído
    p2 = fake_player(2, "linghe")
    fs = FakeSession(npcs={11: fake_npc(11, status="fallen")})
    await rep.on_npc_duel_settled(fs, p2, 11, True)
    check("caído nunca vira rival", p2.rival_npc_id is None)
    # 7c. Roll alto → sem nascimento
    rep.random = SimpleNamespace(random=lambda: 0.99, randint=lambda a, b: 7,
                                 uniform=_orig_random.uniform)
    p3 = fake_player(3, "linghe")
    fs = FakeSession(npcs={12: fake_npc(12)})
    await rep.on_npc_duel_settled(fs, p3, 12, True)
    check("roll 0.99 → sem rival", p3.rival_npc_id is None)
    # 7d. Derrota do rival (defeats+1, some de novo) — PRESENTE (returned)
    rep.random = SimpleNamespace(random=lambda: 0.01, randint=lambda a, b: 7,
                                 uniform=_orig_random.uniform)
    NOTIFY_CALLS.clear()
    p4 = fake_player(4, "linghe", rival_id=10,
                     rival_state={"defeats": 1, "returned": True, "taunt_seed": 7,
                                  "last_defeat_at": (now_utc() - timedelta(days=3)).isoformat()})
    fs = FakeSession(rep_rows=[], npcs={10: npc})
    out = await rep.on_npc_duel_settled(fs, p4, 10, True)
    check("rival derrotado: defeats=2", (p4.rival_state or {}).get("defeats") == 2)
    check("rival derrotado: some (returned=False)", (p4.rival_state or {}).get("returned") is False)
    check("rival derrotado: event no out", (out or {}).get("rival", {}).get("event") == "defeated")
    check("rival derrotado: notify (Lei §1 — nunca void)",
          any(k == "rival_defeated" for _, k, _2 in NOTIFY_CALLS))
    # 7d-bis. PRESENCE GATE (review MV-6): rival AUSENTE (nem returned nem
    # spared) → a memória NÃO avança (o arco não é farmável pela lista de NPCs)
    p4b = fake_player(40, "linghe", rival_id=10,
                      rival_state={"defeats": 2, "returned": False, "spared": False,
                                   "taunt_seed": 7,
                                   "last_defeat_at": now_utc().isoformat()})
    fs = FakeSession(rep_rows=[], npcs={10: npc})
    out = await rep.on_npc_duel_settled(fs, p4b, 10, True)
    check("presence gate: defeats NÃO avança ausente",
          (p4b.rival_state or {}).get("defeats") == 2)
    check("presence gate: sem event rival no out", "rival" not in (out or {}))
    out = await rep.on_npc_duel_settled(fs, p4b, 10, False)
    check("presence gate: perder ausente NÃO vira spared",
          not (p4b.rival_state or {}).get("spared"))
    # 7e. Misericórdia (você perdeu)
    p5 = fake_player(5, "linghe", rival_id=10,
                     rival_state={"defeats": 2, "returned": True, "taunt_seed": 7})
    fs = FakeSession(npcs={10: npc})
    out = await rep.on_npc_duel_settled(fs, p5, 10, False)
    check("misericórdia: spared=True", (p5.rival_state or {}).get("spared") is True)
    check("misericórdia: spared_count=1", (p5.rival_state or {}).get("spared_count") == 1)
    check("misericórdia: rival segue vivo", p5.rival_npc_id == 10)
    check("misericórdia: taunt no out", "taunt" in (out or {}).get("rival", {}))
    # 7f. Conclusão no 5º (título + Chronicle + slot livre)
    NOTIFY_CALLS.clear()
    CHRON_CALLS.clear()
    p6 = fake_player(6, "linghe", rival_id=10,
                     rival_state={"defeats": 4, "returned": True, "taunt_seed": 7})
    fs = FakeSession(rep_rows=[], npcs={10: npc})
    out = await rep.on_npc_duel_settled(fs, p6, 10, True)
    rv = (out or {}).get("rival", {})
    check("conclusão: event concluded", rv.get("event") == "concluded", str(rv))
    check("conclusão: fate ascended (roll 0.01)", rv.get("fate") == "ascended")
    check("conclusão: slot livre", p6.rival_npc_id is None and p6.rival_state is None)
    check("conclusão: título granted", rep.RIVAL_TITLE in p6.unlocked_titles)
    check("conclusão: Chronicle emitida", any(c.get("event_type") == "rvl_end" for c in CHRON_CALLS))
    check("conclusão: notify end", any(k == "rival_end" for _, k, _2 in NOTIFY_CALLS))
    p6b = fake_player(7, "linghe", rival_id=10, titles=[rep.RIVAL_TITLE],
                      rival_state={"defeats": 4, "returned": True})
    fs = FakeSession(npcs={10: npc})
    await rep.on_npc_duel_settled(fs, p6b, 10, True)
    check("título idempotente", p6b.unlocked_titles.count(rep.RIVAL_TITLE) == 1)
    # 7g. Pulse: a volta
    NOTIFY_CALLS.clear()
    p7 = fake_player(8, "linghe", rival_id=10,
                     rival_state={"defeats": 1, "returned": False, "taunt_seed": 7,
                                  "last_defeat_at": (now_utc() - timedelta(hours=100)).isoformat()})
    fs = FakeSession(players=[p7], npcs={10: npc})
    out = await rep.rival_pulse(fs)
    check("pulse: voltou", out and out["returned"] == 1, str(out))
    check("pulse: returned=True", (p7.rival_state or {}).get("returned") is True)
    check("pulse: notify com taunt", any(k == "rival_return" and "taunt" in kw.get("payload", {})
                                          for _, k, kw in NOTIFY_CALLS))
    check("pulse: commit", fs.commits == 1)
    p8 = fake_player(9, "linghe", rival_id=10,
                     rival_state={"defeats": 2, "returned": False, "taunt_seed": 7,
                                  "last_defeat_at": (now_utc() - timedelta(hours=50)).isoformat()})
    fs = FakeSession(players=[p8], npcs={10: npc})
    out = await rep.rival_pulse(fs)
    check("pulse: 50h < 96h não volta", out["returned"] == 0 and not (p8.rival_state or {}).get("returned"))
    # 7h. Pulse: kill-switch honesto (NPC caiu por conta própria)
    NOTIFY_CALLS.clear()
    p9 = fake_player(10, "linghe", rival_id=11,
                     rival_state={"defeats": 1, "returned": True})
    fs = FakeSession(players=[p9], npcs={11: fake_npc(11, status="ascended")})
    out = await rep.rival_pulse(fs)
    check("kill-switch: limpo", out["cleared"] == 1 and p9.rival_npc_id is None)
    check("kill-switch: notify gone", any(k == "rival_gone" for _, k, _2 in NOTIFY_CALLS))
    # 7i. rival_view
    pv = fake_player(11, "linghe", rival_id=10,
                     rival_state={"defeats": 2, "returned": True, "taunt_seed": 7})
    view = await rep.rival_view(FakeSession(npcs={10: npc}), pv, "pt")
    check("view: card presente", view and view["npc_id"] == 10 and view["power_bonus_pct"] == 24, str(view))
    check("view: taunt presente", bool(view.get("taunt")))
    pv2 = fake_player(12, "linghe", rival_id=10,
                      rival_state={"defeats": 2, "returned": False})
    check("view: ausente enquanto lambe feridas",
          await rep.rival_view(FakeSession(npcs={10: npc}), pv2, "pt") is None)
    pv3 = fake_player(13, "linghe", rival_id=11,
                      rival_state={"defeats": 1, "returned": True})
    check("view: NPC caído → None",
          await rep.rival_view(FakeSession(npcs={11: fake_npc(11, status="fallen")}), pv3, "pt") is None)
    check("view: sem rival → None",
          await rep.rival_view(FakeSession(), fake_player(14), "pt") is None)
    # 7j. rival_npc_ids (exclusão de bounty)
    ids = await rep.rival_npc_ids(FakeSession(players=[fake_player(1, rival_id=10),
                                                        fake_player(2, rival_id=None),
                                                        fake_player(3, rival_id=12)]))
    check("rival_npc_ids", ids == {10, 12}, str(ids))
    rep.random = _orig_random

    # ══ 8. Integração storylet ═════════════════════════════════════════════
    check("region_rep_min em _KNOWN_REQS", "region_rep_min" in sty._KNOWN_REQS)
    pl = fake_player(1, "linghe")
    ctx = {"continent": "linghe", "region_state": "prospera", "events": set(), "region_rep": 30}
    check("_matches rep 30 ≥ 25", sty._matches(pl, {"region_rep_min": 25}, ctx) is True)
    check("_matches rep 30 < 50", sty._matches(pl, {"region_rep_min": 50}, ctx) is False)
    ctx0 = {"continent": "linghe", "region_state": "prospera", "events": set()}
    check("_matches sem ctx rep = fail", sty._matches(pl, {"region_rep_min": 25}, ctx0) is False)
    check("_matches req desconhecido fail-closed", sty._matches(pl, {"rep_min_v2": 1}, ctx) is False)
    # Keys de i18n que o ENGINE resolve — todas no injetor ×3 (zero órfãs).
    from inject_mv6_i18n import CHAT, LANGS, MINIAPP
    need_chat = (
        ["rep_tier_reverence", "rep_tier_respected", "rep_tier_neutral", "rep_tier_contempt",
         "rep_line_reverence", "rep_line_contempt", "rep_market_note_down", "rep_market_note_up",
         "rep_plaza_prefix", "rep_travel_prefix",
         "notif_rep_milestone_title", "notif_rep_milestone_body",
         "notif_rvl_born_title", "notif_rvl_born_body",
         "notif_rvl_return_title", "notif_rvl_return_body",
         "notif_rvl_gone_title", "notif_rvl_gone_body",
         "notif_rvl_end_asc_title", "notif_rvl_end_asc_body",
         "notif_rvl_end_fall_title", "notif_rvl_end_fall_body",
         "rvl_chron_end_asc", "rvl_chron_end_fall", "title_desc_quebra_rivais",
         "rvl_plaza_line", "rvl_btn_view", "rvl_gone_alert", "rvl_away_alert",
         "notif_rvl_defeated_title", "notif_rvl_defeated_body",
         "rvl_view_defeats", "rvl_view_power", "rvl_view_spared", "rvl_open_app_hint"]
        + [f"rvl_taunt_{i}" for i in range(1, 7)]
        + [f"rvl_taunt_spared_{i}" for i in range(1, 3)]
        + [f"sty_{k}_{sfx}" for k in ("confianca_do_magistrado", "encomenda_do_anciao")
           for sfx in ("name", "desc", "d1", "d2")]
    )
    for lang in LANGS:
        for k in need_chat:
            check(f"i18n chat {lang}/{k}", k in CHAT[lang])
        for k in ("feature_reputacao_rival", "feature_reputacao_rival_desc",
                  "rvl_card_title", "rvl_challenge_cta", "rvl_defeats_chip",
                  "rvl_power_chip", "rvl_modal_banner", "rep_map_label"):
            check(f"i18n mini {lang}/{k}", k in MINIAPP[lang])
    # Seeds novos: requirements conhecidos + tracker vivo (o teste MV-5 cobre
    # a estrutura toda; aqui provamos o PAR rep_min+flag dos 2 novos).
    from database.seeds.storylet_seeds import STORYLET_SEEDS
    new = {s["key"]: s for s in STORYLET_SEEDS
           if s["key"] in ("confianca_do_magistrado", "encomenda_do_anciao")}
    check("2 seeds novos presentes", len(new) == 2)
    for k, s in new.items():
        check(f"seed {k}: region_rep_min presente", "region_rep_min" in s["requirements"])
        check(f"seed {k}: flag reputacao_rival", s["requirements"].get("flag") == "reputacao_rival")

    ne.notify = _orig_notify
    wpe.emit_chronicle = _orig_chron

    print(f"\n{PASS} passed · {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"  FAIL: {f}")
        sys.exit(1)
    print("All green ✅")


asyncio.run(main())
