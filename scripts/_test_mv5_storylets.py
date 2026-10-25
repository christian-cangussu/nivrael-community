# -*- coding: utf-8 -*-
"""Teste isolado MV-5 — storylet_engine (COMMITTED, padrão _test_mv4_meridians).

Cobre:
  * OFF-identity: flag OFF → TODA função pública devolve o neutro SEM tocar a
    sessão (sessão-que-explode).
  * _matches (o coração QBN): cada requirement + AND + fail-closed em
    requirement desconhecido.
  * maybe_offer: pacer (1 oferta aberta · cooldown · anti-repetição) + mint
    (row estampado com context) + giver com nome real.
  * respond_offer: aceitar (prazo do catálogo) / recusar (livre) / expirada /
    idempotência (status re-validado).
  * track_storylets: acumula, capa no count, ignora vencida, completa.
  * sync_player_storylets: oferta vencida expira silenciosa · aceita incompleta
    expira · aceita COMPLETA nunca expira (Lei §1).
  * claim_storylet: pedras + status done + first-on-server; not_done honesto;
    re-claim é no-op.
  * Estrutura dos seeds: objective_type SEMPRE na lista viva de trackers
    (lição MV-1 — zero objetivos órfãos), reward nunca jade/técnica, e cada
    storylet tem name/desc/d1/d2 ×3 idiomas no injetor (zero key órfã).

Correr: python -X utf8 scripts/_test_mv5_storylets.py  (exit 1 se falhar)
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

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


class ExplodingSession:
    """Sessão que EXPLODE em qualquer uso — prova OFF = zero queries."""
    def execute(self, *a, **k):
        raise AssertionError("query executada com flag OFF")

    def add(self, *a, **k):
        raise AssertionError("add executado com flag OFF")

    def get(self, *a, **k):
        raise AssertionError("get executado com flag OFF")


class FakeResult:
    def __init__(self, value):
        self._v = value

    def scalars(self):
        return self

    def all(self):
        if self._v is None:
            return []
        return list(self._v) if isinstance(self._v, (list, tuple)) else [self._v]

    def scalar_one_or_none(self):
        return self._v

    def scalar(self):
        return self._v

    def first(self):
        if isinstance(self._v, (list, tuple)):
            return self._v[0] if self._v else None
        return self._v


class FakeSession:
    """Sessão ON: responde por substring da statement (padrão _test_mv4).
    rows = player_storylets do jogador · catalog = storylet_catalog ·
    npc_name = pick do giver · first_probe = probe do sty_first."""
    def __init__(self, rows=None, catalog=None, npc_name=None, first_probe=None):
        self.rows = rows if rows is not None else []
        self.catalog = catalog if catalog is not None else []
        self.npc_name = npc_name
        self.first_probe = first_probe
        self.added = []
        self._next_id = 900

    async def execute(self, stmt, params=None):
        s = str(stmt)
        if "pg_advisory_xact_lock" in s:
            return FakeResult(1)
        if "status = 'done'" in s:
            return FakeResult(self.first_probe)
        if "npc_cultivators" in s:
            return FakeResult(self.npc_name)
        if "max(player_storylets.offered_at)" in s:
            times = [r.offered_at for r in self.rows if getattr(r, "offered_at", None)]
            return FakeResult(max(times) if times else None)
        if "player_notifications" in s:
            return FakeResult(None)
        if "player_storylets" in s and "storylet_catalog" in s:
            # Semântica mínima do WHERE (o engine confia no filtro do SQL):
            rows = self.rows
            _now = now_utc()
            if "expires_at <=" in s:          # sync: só vencidas abertas
                rows = [r for r in rows if r.status in ("offered", "accepted")
                        and r.expires_at is not None and r.expires_at <= _now]
            elif "objective_type =" in s:     # track (WHERE, não a coluna do SELECT)
                rows = [r for r in rows if r.status == "accepted"]
            elif "status IN" in s:            # project: abertas
                rows = [r for r in rows if r.status in ("offered", "accepted")]
            cat_by_key = {c.key: c for c in self.catalog}
            joined = [(r, cat_by_key[r.storylet_key]) for r in rows
                      if r.storylet_key in cat_by_key]
            return FakeResult(joined)
        if "player_storylets" in s:
            if "FOR UPDATE" in s:
                # lock por id (respond/claim)
                sid = None
                if params:
                    sid = params.get("id_1")
                for r in self.rows:
                    if sid is None or int(r.id) == int(sid):
                        return FakeResult(r)
                return FakeResult(None)
            return FakeResult(self.rows)
        if "storylet_catalog" in s:
            return FakeResult(self.catalog)
        if "players.language" in s or ("FROM players" in s and "language" in s):
            return FakeResult("pt")
        raise AssertionError(f"query inesperada: {s[:100]}")

    async def get(self, model, key):
        for c in self.catalog:
            if c.key == key:
                return c
        return None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1

    def begin_nested(self):
        # Review fix — o mint insere dentro de um SAVEPOINT (índice único
        # parcial nunca envenena a transação do caller).
        class _SP:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False
        return _SP()


def fake_player(**over):
    p = SimpleNamespace(
        telegram_id=1001, realm=3, karma=0, path=None,
        current_continent="linghe", language="pt",
        spirit_stones=1_000, meridians_opened={},
    )
    for k, v in over.items():
        setattr(p, k, v)
    return p


def fake_cat(key="defesa_sitiada", giver="npc_cultivator", req=None, obj="npc_combat",
             count=5, reward=None, hours=48, weight=10, active=True):
    return SimpleNamespace(
        key=key, giver_kind=giver, emoji="🛡️",
        requirements=req if req is not None else {},
        objective_type=obj, objective_count=count,
        reward=reward if reward is not None else {"stones": 900, "karma": 10},
        expires_hours=hours, weight=weight, is_active=active,
    )


def fake_row(rid=1, key="defesa_sitiada", status="offered", progress=0,
             offered_ago_h=0.0, expires_in_h=24.0, context=None):
    now = now_utc()
    return SimpleNamespace(
        id=rid, player_id=1001, storylet_key=key, status=status,
        progress=progress, context=context if context is not None else {},
        offered_at=now - timedelta(hours=offered_ago_h),
        accepted_at=None, resolved_at=None,
        expires_at=(now + timedelta(hours=expires_in_h)) if expires_in_h is not None else None,
    )


async def main():
    # ══ 1. OFF-identity (sessão-que-explode) ══════════════════════════════
    sty.quests_vivas_on = lambda *a, **k: False
    boom = ExplodingSession()
    p = fake_player()

    check("OFF storylet_available False", (await sty.storylet_available(boom, p, fake_cat())) is False)
    check("OFF maybe_offer None", (await sty.maybe_offer(boom, p)) is None)
    check("OFF open_offer_view None", (await sty.open_offer_view(boom, p, "pt")) is None)
    r = await sty.respond_offer(boom, p, 1, True)
    check("OFF respond sty_locked", r == {"ok": False, "reason": "sty_locked"}, str(r))
    check("OFF track no-op", (await sty.track_storylets(boom, 1001, "npc_combat", 1)) is None)
    check("OFF sync 0", (await sty.sync_player_storylets(boom, 1001)) == 0)
    r = await sty.claim_storylet(boom, p, 1)
    check("OFF claim sty_locked", r == {"ok": False, "reason": "sty_locked"}, str(r))
    check("OFF project None", (await sty.project_storylets(boom, p, lang="pt")) is None)

    # ══ 2. _matches — o coração QBN (puro) ════════════════════════════════
    sty.quests_vivas_on = lambda *a, **k: True
    ctx = {"continent": "linghe", "region_state": "sitiada", "events": {"beast_tide"}}
    check("req vazio = True", sty._matches(fake_player(), {}, ctx))
    check("continent match", sty._matches(fake_player(), {"continent": ["linghe"]}, ctx))
    check("continent miss", not sty._matches(fake_player(), {"continent": ["moyu"]}, ctx))
    check("region_state match", sty._matches(fake_player(), {"region_state": ["sitiada", "tensa"]}, ctx))
    check("region_state miss", not sty._matches(fake_player(), {"region_state": ["festival"]}, ctx))
    check("world_event match", sty._matches(fake_player(), {"world_event": "beast_tide"}, ctx))
    check("world_event miss", not sty._matches(fake_player(), {"world_event": "meteor"}, ctx))
    check("karma janela dentro", sty._matches(fake_player(karma=-200), {"karma_min": -1000, "karma_max": -100}, ctx))
    check("karma janela fora", not sty._matches(fake_player(karma=0), {"karma_min": -1000, "karma_max": -100}, ctx))
    check("realm_min morde", not sty._matches(fake_player(realm=1), {"realm_min": 2}, ctx))
    check("realm_max morde", not sty._matches(fake_player(realm=5), {"realm_max": 3}, ctx))
    check("path NULL lê rogue", sty._matches(fake_player(path=None), {"path": ["rogue"]}, ctx))
    check("path demonic match", sty._matches(fake_player(path="demonic"), {"path": ["demonic"]}, ctx))
    check("path miss", not sty._matches(fake_player(path="righteous"), {"path": ["demonic"]}, ctx))
    p_mer = fake_player(meridians_opened={"pulmao": {"opened_at": "2026-01-01T00:00:00+00:00"}})
    check("meridians_min 1 match", sty._matches(p_mer, {"meridians_min": 1}, ctx))
    check("meridians_min 2 miss", not sty._matches(p_mer, {"meridians_min": 2}, ctx))
    import database.db as _dbm
    _orig_flag = _dbm.feature_enabled_for_world
    _dbm.feature_enabled_for_world = lambda *a, **k: True
    check("flag ON match", sty._matches(fake_player(), {"flag": "corpo_profundo"}, ctx))
    _dbm.feature_enabled_for_world = lambda *a, **k: False
    check("flag OFF miss", not sty._matches(fake_player(), {"flag": "corpo_profundo"}, ctx))
    _dbm.feature_enabled_for_world = _orig_flag
    check("requirement DESCONHECIDO = fail-closed",
          not sty._matches(fake_player(), {"future_req": 1}, ctx))
    check("AND entre presentes",
          not sty._matches(fake_player(realm=1), {"continent": ["linghe"], "realm_min": 2}, ctx))

    # ══ 3. maybe_offer — pacer + mint ═════════════════════════════════════
    _orig_random = sty.random
    sty.random = SimpleNamespace(choices=lambda pool, weights, k: [pool[0]], random=lambda: 0.0)

    # 3a. oferta aberta → None (1 por vez)
    ses = FakeSession(rows=[fake_row(status="offered", expires_in_h=5)], catalog=[fake_cat(req={})])
    check("pacer: oferta aberta bloqueia", (await sty.maybe_offer(ses, fake_player())) is None)
    check("pacer: nada mintado", len(ses.added) == 0)

    # 3b. cooldown (última oferta há 2h < 12h) → None
    ses = FakeSession(rows=[fake_row(status="declined", offered_ago_h=2, expires_in_h=None)],
                      catalog=[fake_cat(req={})])
    check("pacer: cooldown morde", (await sty.maybe_offer(ses, fake_player())) is None)

    # 3c. anti-repetição: mesma key há 3 dias (< 7d) bloqueada; outra oferece
    ses = FakeSession(
        rows=[fake_row(key="defesa_sitiada", status="done", offered_ago_h=72, expires_in_h=None)],
        catalog=[fake_cat(key="defesa_sitiada", req={}), fake_cat(key="peregrino_do_rio", req={}, giver="mendigo")],
        npc_name=None,
    )
    offer = await sty.maybe_offer(ses, fake_player())
    check("anti-repetição: outra key oferecida", offer is not None and offer["key"] == "peregrino_do_rio", str(offer))
    # (com begin_nested no fake, o notify também adiciona a notificação — filtrar)
    minted = [o for o in ses.added if getattr(o, "storylet_key", None)]
    check("mint: row criado", len(minted) == 1 and minted[0].storylet_key == "peregrino_do_rio")
    check("mint: context lembra o lugar", minted[0].context.get("continent") == "linghe")
    check("mint: giver mendigo genérico", offer["giver"] == "O Velho Mendigo", str(offer.get("giver")))

    # 3d. mint com giver de nome REAL (npc_cultivator local)
    ses = FakeSession(rows=[], catalog=[fake_cat(req={})], npc_name="Shen Wuya")
    offer = await sty.maybe_offer(ses, fake_player())
    check("mint: giver com rosto", offer is not None and offer["giver"] == "Shen Wuya", str(offer))
    check("mint: diálogo 2 falas", len(offer["dialogue"]) == 2)
    check("mint: reward line honesta", "🪨 900" in offer["reward_line"], offer["reward_line"])

    # 3e. requirements filtram o pool (sitiada exigida, mundo próspero → None)
    ses = FakeSession(rows=[], catalog=[fake_cat(req={"region_state": ["sitiada"]})])
    check("pool vazio → None", (await sty.maybe_offer(ses, fake_player())) is None)

    # ══ 4. respond_offer ══════════════════════════════════════════════════
    row = fake_row(rid=7, status="offered", expires_in_h=5)
    ses = FakeSession(rows=[row], catalog=[fake_cat(hours=48)])
    r = await sty.respond_offer(ses, fake_player(), 7, True)
    check("aceitar ok", r.get("ok") is True and r.get("accepted") is True, str(r))
    check("aceitar: status accepted", row.status == "accepted")
    check("aceitar: prazo do catálogo (48h)", row.expires_at is not None and
          abs((row.expires_at - now_utc()).total_seconds() - 48 * 3600) < 120)
    r2 = await sty.respond_offer(ses, fake_player(), 7, True)
    check("re-aceitar recusa (idempotente)", r2 == {"ok": False, "reason": "sty_offer_gone"}, str(r2))

    row = fake_row(rid=8, status="offered", expires_in_h=5)
    ses = FakeSession(rows=[row], catalog=[fake_cat()])
    r = await sty.respond_offer(ses, fake_player(), 8, False)
    check("recusar livre", r.get("ok") is True and r.get("declined") is True, str(r))
    check("recusar: status declined", row.status == "declined")

    row = fake_row(rid=9, status="offered", expires_in_h=-1)
    ses = FakeSession(rows=[row], catalog=[fake_cat()])
    r = await sty.respond_offer(ses, fake_player(), 9, True)
    check("oferta vencida → expirada honesta", r.get("reason") == "sty_offer_expired", str(r))
    check("oferta vencida: flip expired", row.status == "expired")

    # ══ 5. track_storylets ════════════════════════════════════════════════
    row = fake_row(rid=10, status="accepted", progress=3, expires_in_h=24)
    ses = FakeSession(rows=[row], catalog=[fake_cat(count=5)])
    await sty.track_storylets(ses, 1001, "npc_combat", 1)
    check("track acumula", row.progress == 4, str(row.progress))
    await sty.track_storylets(ses, 1001, "npc_combat", 99)
    check("track capa no count", row.progress == 5)
    row_exp = fake_row(rid=11, status="accepted", progress=0, expires_in_h=-2)
    ses = FakeSession(rows=[row_exp], catalog=[fake_cat(count=5)])
    await sty.track_storylets(ses, 1001, "npc_combat", 1)
    check("track ignora vencida", row_exp.progress == 0)
    # Review fix — prefiltro estático: objetivo que NENHUM storylet usa
    # (login/boss_damage) = ZERO query mesmo com flag ON (hot path protegido).
    boom_on = ExplodingSession()
    await sty.track_storylets(boom_on, 1001, "login", 1)
    check("track prefiltra login (zero query ON)", True)
    await sty.track_storylets(boom_on, 1001, "boss_damage", 999)
    check("track prefiltra boss_damage (zero query ON)", True)

    # ══ 6. sync — expiry honesto (Lei §1) ═════════════════════════════════
    r_off = fake_row(rid=20, status="offered", expires_in_h=-1)
    r_acc = fake_row(rid=21, status="accepted", progress=1, expires_in_h=-1)
    r_done = fake_row(rid=22, status="accepted", progress=5, expires_in_h=-1)
    ses = FakeSession(rows=[r_off, r_acc, r_done], catalog=[fake_cat(count=5)])
    flipped = await sty.sync_player_storylets(ses, 1001)
    check("sync flips 2 (oferta + aceita incompleta)", flipped == 2, str(flipped))
    check("oferta vencida expira", r_off.status == "expired")
    check("aceita incompleta expira", r_acc.status == "expired")
    check("COMPLETA NUNCA expira (Lei §1)", r_done.status == "accepted")

    # ══ 7. claim ══════════════════════════════════════════════════════════
    row = fake_row(rid=30, status="accepted", progress=5,
                   context={"continent": "linghe"})
    ses = FakeSession(rows=[row], catalog=[fake_cat(count=5, reward={"stones": 900})],
                      first_probe=None)  # None = 1º do servidor
    p = fake_player(spirit_stones=100)
    r = await sty.claim_storylet(ses, p, 30)
    check("claim ok", r.get("ok") is True, str(r))
    check("claim: pedras concedidas", p.spirit_stones == 1000, str(p.spirit_stones))
    check("claim: status done", row.status == "done")
    check("claim: 1º do servidor → chronicle", r.get("first_on_server") is True, str(r))
    r2 = await sty.claim_storylet(ses, p, 30)
    check("re-claim é no-op", r2.get("reason") == "sty_nothing_to_claim", str(r2))

    row = fake_row(rid=31, status="accepted", progress=2)
    ses = FakeSession(rows=[row], catalog=[fake_cat(count=5)])
    r = await sty.claim_storylet(ses, fake_player(), 31)
    check("claim cedo → sty_not_done", r.get("reason") == "sty_not_done", str(r))

    # ══ 8. project — a seção + disclosure do pacer ════════════════════════
    r_o = fake_row(rid=40, status="offered", offered_ago_h=1, expires_in_h=10)
    r_a = fake_row(rid=41, key="defesa_sitiada", status="accepted", progress=5, expires_in_h=10)
    ses = FakeSession(rows=[r_o, r_a], catalog=[fake_cat(count=5)])
    view = await sty.project_storylets(ses, fake_player(), lang="pt")
    check("project ok", view is not None and view.get("ok") is True, str(view))
    check("project: oferta presente", view["offer"] is not None and view["offer"]["id"] == 40)
    check("project: aceita presente", len(view["accepted"]) == 1 and view["accepted"][0]["is_completed"] is True)
    check("project: completa sem prazo (não expira)", view["accepted"][0]["expires_in"] is None)
    check("project: pacer disclosure", view["next_offer_in"] > 0)

    sty.random = _orig_random

    # ══ 9. Seeds — estrutura (zero objetivo órfão · reward limpo · i18n ×3) ═
    from database.seeds.storylet_seeds import STORYLET_SEEDS
    from inject_mv5_i18n import CHAT as CHAT5, LANGS
    # MV-6 acrescentou 2 seeds (region_rep_min) cujas keys de i18n vivem no
    # injetor mv6 — o check estrutural cobre a UNIÃO dos injetores.
    # MV-8 acrescentou mais 2 (region_state "ocupada", a 🚩 Bandeira), cujas
    # keys vivem no injetor mv8: a união cresce com cada onda que semeia.
    try:
        from inject_mv6_i18n import CHAT as CHAT6
    except Exception:
        CHAT6 = {lang: {} for lang in LANGS}
    try:
        from inject_mv8_i18n import CHAT as CHAT8
    except Exception:
        CHAT8 = {lang: {} for lang in LANGS}
    # MV-9 semeou os 15 ENCARGOS 城务 (3 por cidade), cujas keys vivem no
    # injetor mv9. A união cresce com cada onda que semeia.
    try:
        from inject_mv9_i18n import CHAT as CHAT9
    except Exception:
        CHAT9 = {lang: {} for lang in LANGS}
    CHAT = {lang: {**CHAT5.get(lang, {}), **CHAT6.get(lang, {}),
                   **CHAT8.get(lang, {}), **CHAT9.get(lang, {})} for lang in LANGS}
    LIVE_TRACKED = {
        "cultivate", "craft_pill", "use_pill", "sparring", "arena_win", "arena_top3",
        "npc_combat", "boss_attack", "boss_damage", "beast_expedition", "long_expedition",
        "tribulation_survive", "sect_contribution", "dungeon_floor",
        "breakthrough", "realm_up", "forge_artifact", "login",
    }
    # MV-9 — os 15 ENCARGOS 城务 entraram no MESMO catálogo (o encargo É um
    # storylet com dono fixo). O teto da Lei §3 vale para os SORTEÁVEIS: os
    # encargos não competem no pool aleatório (weight 0), ficam afixados na
    # cidade. Portanto conta-se o pool de sorteio, não a tabela inteira.
    from core.city_engine import ENCARGO_KEYS
    _drawable = [s for s in STORYLET_SEEDS if s["key"] not in ENCARGO_KEYS]
    check("12-20 storylets SORTEÁVEIS (Lei §3)",
          12 <= len(_drawable) <= 20, str(len(_drawable)))
    check("15 encargos MV-9 no catálogo",
          len([s for s in STORYLET_SEEDS if s["key"] in ENCARGO_KEYS]) == 15,
          str(len(STORYLET_SEEDS)))
    keys_seen = set()
    for s in STORYLET_SEEDS:
        k = s["key"]
        check(f"seed {k}: objetivo TEM tracker vivo", s["objective_type"] in LIVE_TRACKED, s["objective_type"])
        check(f"seed {k}: key única", k not in keys_seen)
        keys_seen.add(k)
        rw = s["reward"]
        check(f"seed {k}: reward limpo (nunca jade/técnica)",
              set(rw.keys()) <= {"stones", "karma", "items"}, str(rw.keys()))
        for it in rw.get("items", []):
            check(f"seed {k}: item nativo (herb/ore)", it.get("type") in ("herb", "ore"), str(it))
        check(f"seed {k}: giver válido", s["giver_kind"] in ("npc_cultivator", "service_npc", "mendigo"))
        check(f"seed {k}: requirements conhecidos",
              set(s["requirements"].keys()) <= sty._KNOWN_REQS, str(s["requirements"].keys()))
        # MV-9 — o encargo tem weight 0 DE PROPÓSITO (fora do sorteio do pacer;
        # afixado na cidade e MAIS visível, não menos). Todo o resto tem de ter
        # peso, senão seria conteúdo escondido de verdade.
        if k in ENCARGO_KEYS:
            check(f"seed {k}: encargo tem weight 0 (fora do sorteio)", int(s["weight"]) == 0)
        else:
            check(f"seed {k}: weight > 0", int(s["weight"]) > 0)
        for lang in LANGS:
            for suffix in ("name", "desc", "d1", "d2"):
                check(f"seed {k}: i18n {lang}/{suffix}",
                      f"sty_{k}_{suffix}" in CHAT[lang])

    print(f"\n{PASS} passed · {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"  FAIL: {f}")
        sys.exit(1)
    print("All green ✅")


asyncio.run(main())
