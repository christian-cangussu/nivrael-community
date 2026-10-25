"""QoL-Feedback 2026-08-03 — teste isolado do lote dos 3 reports (SEM DB).

Roda: python -X utf8 scripts/_test_qol_feedback_0803.py

Padrão _test_qol_feedback / _test_tec4_caves: FakeSession (dispatch por
substring do SQL compilado) prova a lógica; wiring grep-provável (helper novo
sem call-site = promessa vazia); i18n do lote presente ×3 ×2 com placeholders
idênticos.

O que este teste protege, em ordem de gravidade:

  1. **Item A — a quest de seita nunca mais depende de um segundo jogador.**
     As 10 quests de julgamento/duelo com narrativa de oponente NPC (602 +
     612…636) saem de `sparring` (que SÓ avança em duelo PvP consentido entre
     dois jogadores vivos) para `npc_combat`. A id 3 (daily "friendly spar")
     fica intacta — é PvP-temática legítima. E, sobretudo: o **SEED SYNC**
     existe e é idempotente, porque o runner é insert-only para ids
     existentes — sem esse bloco a DB viva (onde a PlayerQuest do [jogador] está
     0/1) nunca receberia a correção. Guard-rail extra: nenhuma quest de
     seita pode voltar a nascer com objetivo dependente de outro jogador.

  2. **Item B — a Pílula da Fundação Eterna deixa de ser muda (Lei §10).**
     `foundation_reroll_preview` é a UMA verdade do preview e espelha
     EXATAMENTE o ramo do apply (`alchemy_engine`): mesma ordem de decisões,
     mesmas tabelas, mesmos 100% no caminho Sacred, sacred nunca rebaixada.
     Provado por equivalência estatística contra o apply real (display ==
     roll — lição MV-6) e por asserts estruturais. Mais: as 2 superfícies
     consomem as chaves que o servidor manda (payload entregue ≠ payload
     visto) e o `power_delta` passa a cobrir o reroll — que move o Poder de
     Combate PERMANENTEMENTE via `stat_mult` em calculate_total_stats.

  3. **Item C — o teto G7 passa a FALAR (Lei §1).** O botão ✨ Refinar
     deixa de ser `disabled` mudo em G7 (o modal já tratava `at_max_grade`
     com elegância — era caminho morto), a linha do artefato ganha o chip
     ⭐ e a recusa aponta o caminho seguinte (G8 Celestial forjado inteiro).
     O teto em si NÃO se mexe: `grade >= 7` continua a recusar no engine.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# core.alchemy_engine importa core.utils → telegram. A lib não existe na
# máquina local (só no VPS) e o teste é SEM rede/DB por contrato — um stub
# mínimo satisfaz o import; nada de telegram é EXERCIDO por estes asserts.
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

import core.foundation_engine as fnd  # noqa: E402
from database.seeds.quests_seeds import (  # noqa: E402
    QUEST_SEEDS, _OBJECTIVE_TYPE_SYNC_IDS, run_quests_seeds,
)

PASS = 0
FAILS: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(f"{name} {('— ' + detail) if detail else ''}")


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
            def first(self):
                return rows[0] if rows else None

            def all(self):
                return list(rows)
        return _S()


class FakeSession:
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

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _src(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


QUALITIES = ("normal", "perfect", "divine", "heavenly")
FOUNDATIONS = (None, "low", "medium", "high", "perfect", "sacred")

# As 10 quests de seita cuja narrativa descreve um oponente NPC (um discípulo
# ladrão, um irmão de seita julgado, um prodígio rival, um enviado). NENHUMA
# descreve um duelo entre jogadores — por isso `sparring` era, além de
# dead-end, temáticamente errado.
SECT_JUDGEMENT_IDS = (602, 612, 615, 618, 621, 624, 627, 630, 633, 636)

# Trackers que SÓ avançam com a participação de um segundo jogador vivo.
# Um objetivo de quest de SEITA nunca pode usar um destes (lição MV-6, 3ª
# recorrência: storylet_seeds ×2 + este lote).
PLAYER_DEPENDENT_OBJECTIVES = {"sparring"}

# Idem no catálogo de FACÇÕES (achado do review adversarial). `pvp_win` NÃO
# entra: a arena alimenta-o e tem fallback de NPC ao expirar a fila.
PLAYER_DEPENDENT_FACTION_TYPES = {"spar_win"}


# ══════════════════════════════════════════════════════════════════════════
# Item A — a sombra sem caminho
# ══════════════════════════════════════════════════════════════════════════
def item_a_seeds() -> None:
    by_id = {s["id"]: s for s in QUEST_SEEDS}

    for qid in SECT_JUDGEMENT_IDS:
        s = by_id.get(qid)
        check(f"A/seed {qid} existe", s is not None)
        if not s:
            continue
        check(f"A/seed {qid} é npc_combat", s["objective_type"] == "npc_combat",
              f"tem {s['objective_type']!r}")
        check(f"A/seed {qid} é de seita", s.get("type") == "sect")
        # 602 é a UNIVERSAL (sect_id None — todo membro de qualquer casa a
        # recebe); as 9 de julgamento são etiquetadas por casa.
        if qid == 602:
            check("A/seed 602 é universal", s.get("sect_id") is None)
        else:
            check(f"A/seed {qid} tem sect_id", bool(s.get("sect_id")))

    # ⚠️ INVERTIDO pelo MV-9 §P6 (2026-08-06). Em 03/08 a daily id 3 ficou de
    # fora por ser "PvP-temática legítima". A medição derrubou: 0 sparrings em
    # 30d no main, 0 desde sempre no s2 — entregue a todos, todo dia, e
    # incompletável. Agora `npc_combat` (solo-completável, mesma temática).
    q3 = by_id.get(3)
    check("A/id 3 (daily spar) já não depende de outro jogador",
          q3 is not None and q3["objective_type"] not in PLAYER_DEPENDENT_OBJECTIVES,
          f"tem {q3 and q3['objective_type']!r}")

    # Guard-rail eterno: NENHUMA quest de seita pode depender de outro jogador.
    offenders = [s["id"] for s in QUEST_SEEDS
                 if s.get("type") == "sect"
                 and s["objective_type"] in PLAYER_DEPENDENT_OBJECTIVES]
    check("A/nenhuma quest de seita depende de outro jogador", not offenders,
          f"ofensoras: {offenders}")

    # …e o guard-rail NÃO pode viver só dentro de QUEST_SEEDS (achado do review
    # adversarial): o catálogo de FACÇÕES tinha a pior versão do mesmo defeito —
    # `spar_win` sem abandono nem expiração = 0/1 para sempre.
    from database.seeds.faction_seeds import FACTION_QUESTS
    fac_off = [q["id"] for q in FACTION_QUESTS
               if q["quest_type"] in PLAYER_DEPENDENT_FACTION_TYPES]
    check("A/nenhuma quest de facção depende de outro jogador", not fac_off,
          f"ofensoras: {fac_off}")
    # E o motivo de `pvp_win` ser aceitável: a arena tem fallback de NPC.
    ads = _src("core", "arena_duel_settle.py")
    check("A/pvp_win alimentado pela arena", '"pvp_win"' in ads)
    check("A/arena tem fallback de NPC", "_spawn_npc_fallback" in _src("core", "arena_engine.py"))

    # A allowlist do sync = as 10 de seita + a daily id 3.
    # ⚠️ ATUALIZADO pelo MV-9 §P6 (2026-08-06). Este bloco afirmava o CONTRÁRIO
    # ("A/allowlist NÃO contém a id 3") porque em 03/08 a id 3 foi deixada de
    # fora por ser "PvP temática legítima". A medição derrubou o argumento: 0
    # sparrings em 30 dias no main e 0 desde sempre no s2 — a daily era entregue
    # a todo jogador todos os dias e era INCOMPLETÁVEL. Passou a `npc_combat`.
    check("A/allowlist == as 10 de seita + a daily 3",
          tuple(sorted(_OBJECTIVE_TYPE_SYNC_IDS)) == tuple(sorted(tuple(SECT_JUDGEMENT_IDS) + (3,))),
          f"allowlist={_OBJECTIVE_TYPE_SYNC_IDS}")
    check("A/a id 3 ENTROU na allowlist", 3 in _OBJECTIVE_TYPE_SYNC_IDS)
    # E a seed tem de ter mudado JUNTO — a allowlist sozinha é no-op (o sync só
    # escreve quando catálogo != seed).
    check("A/a seed da id 3 já não é sparring",
          by_id[3]["objective_type"] != "sparring", f"id3={by_id[3]['objective_type']}")

    # Toda id da allowlist existe no catálogo (uma id órfã tornaria o sync
    # silenciosamente inútil — exatamente o modo de falha que este bloco cura).
    check("A/allowlist toda no catálogo",
          all(q in by_id for q in _OBJECTIVE_TYPE_SYNC_IDS))


class _FakeQuestRow:
    """Row mínima de QuestCatalog para o seed runner mexer."""

    def __init__(self, qid, objective_type, choices=None, rewards=None, is_active=True,
                 name="", description=""):
        self.id = qid
        self.objective_type = objective_type
        self.choices = choices
        self.rewards = rewards if rewards is not None else {"spirit_stones": 1, "sect_contribution": 1}
        self.is_active = is_active
        # MV-9 §P6: o bloco de sync passou a alinhar também o TEXTO da id 3 (o
        # objetivo virou `npc_combat` mas o nome continuava "Participate in
        # Sparring" nas 2 DBs de produção). O stub tem de ter os campos do
        # modelo real — a lição do MV-8 (`current_qi` inventado deu verde a um
        # ramo que recusava 100% em produção).
        self.name = name
        self.description = description


def item_a_seed_sync() -> None:
    """O runner é insert-only para ids existentes: sem o bloco de SYNC a DB
    viva nunca recebia a correção. Aqui provamos que (a) sincroniza, (b) é
    idempotente, (c) NÃO toca a id 3, (d) não escreve em row de jogador."""
    by_id = {s["id"]: s for s in QUEST_SEEDS}

    # DB "viva": todas as ids do seed já existem, com o objetivo ANTIGO nas 10
    # (e o antigo == o atual em todas as outras, incl. a id 3).
    rows = {}
    for s in QUEST_SEEDS:
        old = "sparring" if s["id"] in SECT_JUDGEMENT_IDS else s["objective_type"]
        rows[s["id"]] = _FakeQuestRow(s["id"], old, choices=s.get("choices"),
                                      rewards=s.get("rewards"),
                                      # o texto ANTIGO, como está nas DBs vivas
                                      name="Participate in Sparring",
                                      description="Participate in a friendly sparring match")

    # O FakeSession não resolve binds (o WHERE vem parametrizado), por isso
    # rodamos o runner uma vez por id-alvo, restringindo QUEST_SEEDS a esse id
    # — o comportamento do bloco é por-id e independente entre ids.
    import database.seeds.quests_seeds as qs

    def _run_for(qid):
        seed = by_id[qid]
        orig_seeds = qs.QUEST_SEEDS
        orig_ids = qs._OBJECTIVE_TYPE_SYNC_IDS
        qs.QUEST_SEEDS = [seed]
        qs._OBJECTIVE_TYPE_SYNC_IDS = tuple(q for q in orig_ids if q == qid)
        try:
            ses = FakeSession([
                # `existing_ids` sai de .scalars().all() → ints, não tuplas.
                # A tabela é `quests_catalog`; o SELECT de ids não tem WHERE.
                (lambda s: "SELECT quests_catalog.id \nFROM quests_catalog" in s
                           and "WHERE" not in s,
                 lambda: [qid]),
                (lambda s: "FROM quests_catalog" in s and "WHERE" in s,
                 lambda: [rows[qid]]),
            ])
            run(qs.run_quests_seeds(ses))
            return ses
        finally:
            qs.QUEST_SEEDS = orig_seeds
            qs._OBJECTIVE_TYPE_SYNC_IDS = orig_ids

    # Guard-rail do próprio teste: se o FakeSession deixasse de casar, o runner
    # cairia no ramo de INSERT e os asserts passariam por engano.
    _probe = _run_for(633)
    check("A/fixture: o runner viu a row como EXISTENTE", _probe.added == [],
          "o fake não casou o SELECT de ids — asserts abaixo seriam vazios")

    rows[633].objective_type = "sparring"  # rebobina para o assert de verdade
    ses = _run_for(633)
    check("A/sync 633 sparring→npc_combat", rows[633].objective_type == "npc_combat",
          f"ficou {rows[633].objective_type!r}")
    check("A/sync commitou", ses.committed)
    check("A/sync não inseriu row nova", ses.added == [])
    check("A/sync não apagou nada", ses.deleted == [])
    # Nenhuma escrita em tabela de jogador (a PlayerQuest do [jogador] não é tocada).
    check("A/sync não toca player_quests",
          not any("player_quest" in s.lower() for s in ses.seen_sql),
          str([s[:60] for s in ses.seen_sql]))

    # Idempotente: rodar de novo não muda nada nem re-escreve.
    before = rows[633].objective_type
    _run_for(633)
    check("A/sync idempotente", rows[633].objective_type == before == "npc_combat")

    # Todas as 10 convergem.
    for qid in SECT_JUDGEMENT_IDS:
        _run_for(qid)
    check("A/as 10 sincronizadas",
          all(rows[q].objective_type == "npc_combat" for q in SECT_JUDGEMENT_IDS),
          str({q: rows[q].objective_type for q in SECT_JUDGEMENT_IDS}))

    # ⚠️ INVERTIDO pelo MV-9 §P6: a id 3 ENTROU na allowlist e a sua seed mudou
    # no mesmo commit, portanto o sync TEM de a converger (uma DB viva recebe
    # `UPDATE quest_catalog SET objective_type='npc_combat' WHERE id=3` no
    # próximo arranque, e as PlayerQuest presas em 0/1 passam a progredir).
    _run_for(3)
    check("A/id 3 SINCRONIZADA (já não é sparring)",
          rows[3].objective_type == "npc_combat", f"ficou {rows[3].objective_type!r}")


def item_a_wiring() -> None:
    """`track_quest` tem de ler o objective_type do CATÁLOGO (join) — é isso
    que faz a PlayerQuest já materializada progredir sem migration. E o
    tracker `npc_combat` tem de existir de facto nas 3 pontas."""
    qe = _src("core", "quest_engine.py")
    check("A/track_quest lê do catálogo",
          "QuestCatalog.objective_type == objective_type" in qe
          and "join(QuestCatalog" in qe)

    # PlayerQuest não pode ter cópia do objective_type (senão o sync mentiria).
    models = _src("database", "models.py")
    m = re.search(r"class PlayerQuest\b.*?(?=\nclass )", models, re.S)
    check("A/PlayerQuest não copia objective_type",
          m is not None and "objective_type" not in m.group(0))

    # Os 3 call-sites reais do tracker npc_combat (chat · mini legacy · settle).
    sites = [
        ("handlers", "combat.py"),
        ("core", "webserver.py"),
        ("core", "pve_duel_settle.py"),
    ]
    for parts in sites:
        src = _src(*parts)
        # Casar a CHAMADA inteira — dois substring-checks independentes sobre um
        # ficheiro de 20k linhas passariam com "npc_combat" só num comentário
        # (achado do review adversarial).
        check(f"A/npc_combat trackeado em {parts[-1]}",
              re.search(r'track_quest\(\s*session,\s*[\w.]+,\s*"npc_combat"', src) is not None)

    # O deep-link do mini já manda npc_combat para a aba do desafio a NPC.
    tabs = _src("miniapp", "components", "tabs.js")
    check("A/deep-link npc_combat → combat", 'npc_combat: "combat"' in tabs)

    # O bloco de SYNC existe no runner e é guardado por `!=` (idempotência).
    seeds = _src("database", "seeds", "quests_seeds.py")
    check("A/bloco de SEED SYNC presente",
          "_OBJECTIVE_TYPE_SYNC_IDS" in seeds
          and "quest.objective_type != seed[\"objective_type\"]" in seeds)


# ══════════════════════════════════════════════════════════════════════════
# Item B — a fundação muda
# ══════════════════════════════════════════════════════════════════════════
class _FakePlayer:
    def __init__(self, fq):
        self.telegram_id = 1001
        self.foundation_quality = fq


def item_b_preview_pure() -> None:
    """A tabela de odds do preview TEM de ser a tabela do engine — nunca uma
    cópia. E as somas fecham em 100%."""
    for fq in FOUNDATIONS:
        for q in QUALITIES:
            prev = fnd.foundation_reroll_preview(fq, q)
            total = sum(o["pct"] for o in prev["odds"])
            check(f"B/odds somam 100 ({fq}/{q})", abs(total - 100.0) < 0.01, f"{total}")
            check(f"B/current ecoa ({fq}/{q})", prev["current"] == fq)
            check(f"B/current_mult == engine ({fq}/{q})",
                  prev["current_mult"] == fnd.get_foundation_multiplier(fq))
            for o in prev["odds"]:
                check(f"B/mult do resultado == engine ({fq}/{q}/{o['quality']})",
                      o["mult"] == fnd.FOUNDATION_QUALITIES[o["quality"]]["stat_mult"])
                exp = ("up" if o["mult"] > prev["current_mult"]
                       else "down" if o["mult"] < prev["current_mult"] else "same")
                check(f"B/direction honesta ({fq}/{q}/{o['quality']})", o["direction"] == exp)

    # Sacred: travada, nunca rebaixada, sem risco.
    for q in QUALITIES:
        p = fnd.foundation_reroll_preview("sacred", q)
        check(f"B/sacred travada ({q})", p["locked"] and not p["can_downgrade"])
        check(f"B/sacred só rola sacred ({q})", [o["quality"] for o in p["odds"]] == ["sacred"])
        check(f"B/sacred não é 'despertar' ({q})", p["sacred_path"] is False)

    # Heavenly sobre Perfeita = o ÚNICO caminho para Sagrada, e é garantido.
    p = fnd.foundation_reroll_preview("perfect", "heavenly")
    check("B/sacred_path em heavenly+perfect", p["sacred_path"] is True)
    check("B/sacred garantido", p["odds"] == [{"quality": "sacred", "pct": 100.0,
                                               "mult": 2.0, "direction": "up"}])
    for fq in FOUNDATIONS:
        for q in QUALITIES:
            if (q, fq) == ("heavenly", "perfect") or fq == "sacred":
                continue
            pp = fnd.foundation_reroll_preview(fq, q)
            check(f"B/sacred não sai de outro caminho ({fq}/{q})",
                  all(o["quality"] != "sacred" for o in pp["odds"]))

    # O risco de PIORAR é dito quando existe (D-1c intocado — só exposto).
    p = fnd.foundation_reroll_preview("perfect", "normal")
    check("B/risco dito em perfect+normal", p["can_downgrade"] is True)
    p = fnd.foundation_reroll_preview("low", "heavenly")
    check("B/sem risco falso em low+heavenly", p["can_downgrade"] is False)

    # Qualidade desconhecida degrada para a tabela `normal` — igual ao apply.
    p_unknown = fnd.foundation_reroll_preview("high", "mythic")
    p_normal = fnd.foundation_reroll_preview("high", "normal")
    check("B/craft desconhecido == normal (igual ao apply)",
          p_unknown["odds"] == p_normal["odds"])


def item_b_preview_equals_apply() -> None:
    """display == roll (lição MV-6): o preview é rodado contra o APPLY REAL.
    Para cada (fundação × qualidade), N rolls do apply têm de cair SEMPRE
    dentro do suporte anunciado, e a frequência bater com as odds."""
    import core.alchemy_engine as alch
    import core.faction_engine as fac

    # O apply consulta bónus de facção antes de qualquer ramo — irrelevante
    # para o reroll (não escala nada aqui) e é o que exigiria DB. Stub.
    _orig_fac = fac.get_faction_bonuses

    async def _no_faction(session, uid):
        return {}
    fac.get_faction_bonuses = _no_faction

    pill = types.SimpleNamespace(id=41, effect_type="eternal_foundation_reroll",
                                 effect_value=1.0, duration_minutes=0)
    N = 3000
    random.seed(20260803)

    async def _sample(fq, q):
        seen: dict[str, int] = {}
        flags = set()
        persisted = True
        for _ in range(N):
            pl = _FakePlayer(fq)
            res = await alch.apply_pill_effect(None, pl, pill, q, effectiveness=1.0)
            new = res["new"]
            seen[new] = seen.get(new, 0) + 1
            flags.add(bool(res.get("sacred_awakened")))
            # O apply escreve mesmo no jogador — o preview descrevia o real.
            if pl.foundation_quality != new:
                persisted = False
        return seen, flags, persisted

    try:
        for fq in FOUNDATIONS:
            for q in QUALITIES:
                prev = fnd.foundation_reroll_preview(fq, q)
                support = {o["quality"] for o in prev["odds"]}
                want = {o["quality"]: o["pct"] for o in prev["odds"]}
                seen, sacred_flags, persisted = run(_sample(fq, q))

                check(f"B/apply persiste no jogador ({fq}/{q})", persisted)
                check(f"B/suporte do apply ⊆ preview ({fq}/{q})",
                      set(seen) <= support, f"apply={set(seen)} preview={support}")
                # Todo resultado ANUNCIADO com peso material tem de sair de facto.
                missing = {k for k in support - set(seen) if want[k] >= 3}
                check(f"B/preview não anuncia impossível ({fq}/{q})", not missing,
                      f"nunca saiu: {missing}")
                for qual, cnt in seen.items():
                    got = cnt / N * 100
                    check(f"B/frequência bate ({fq}/{q}/{qual})",
                          abs(got - want[qual]) < 4.0,
                          f"apply={got:.1f}% preview={want[qual]}%")
                check(f"B/flag sacred_awakened == preview ({fq}/{q})",
                      sacred_flags == {prev["sacred_path"]},
                      f"apply={sacred_flags} preview={prev['sacred_path']}")
    finally:
        fac.get_faction_bonuses = _orig_fac


def item_b_wiring() -> None:
    ws = _src("core", "webserver.py")
    inv = _src("handlers", "inventory.py")
    tabs = _src("miniapp", "components", "tabs.js")

    # 1. Os 2 helpers de display marcam o tipo (nada de "Valor: 1.0").
    check("B/chat marca foundation_reroll",
          'pill.effect_type == "eternal_foundation_reroll"' in inv
          and '{"kind": "foundation_reroll"' in inv)
    check("B/mini marca foundation_reroll",
          '{"kind": "foundation_reroll", "duration": 0}' in ws)

    # 2. Ambos compõem pela MESMA fonte do apply.
    check("B/chat usa foundation_reroll_preview", "foundation_reroll_preview" in inv)
    check("B/endpoint usa foundation_reroll_preview", "foundation_reroll_preview" in ws)
    alch = _src("core", "alchemy_engine.py")
    check("B/apply usa as MESMAS tabelas", "PILL_REROLL_TABLES" in alch)

    # 3. payload entregue == payload visto: o front lê `scaled.foundation`
    #    e as chaves que o servidor mete lá dentro.
    check("B/endpoint devolve scaled.foundation", 'scaled["foundation"] = _prev' in ws)
    check("B/mini consome scaled.foundation", "found={scaled.foundation}" in tabs)
    for key in ("current", "current_mult", "current_emoji", "locked",
                "sacred_path", "can_downgrade", "odds"):
        check(f"B/mini lê found.{key}", f"found.{key}" in tabs)
    for key in ("quality", "pct", "mult", "direction", "emoji"):
        check(f"B/mini lê odds[].{key}", f"o.{key}" in tabs)

    # 4. O resultado (old→new) deixa de ser descartado no mini.
    check("B/mini lê o tipo do efeito", 'last.type === "eternal_foundation_reroll"' in tabs)
    for key in ("last.old", "last.new", "last.sacred_awakened", "last.new_mult"):
        check(f"B/mini lê {key}", key in tabs)
    # …e o servidor de facto manda essas chaves (o apply é quem as compõe).
    for key in ('"old": old_quality', '"new": new_quality',
                '"sacred_awakened": sacred_awakened', '"new_mult": new_mult'):
        check(f"B/apply devolve {key.split(':')[0]}", key in alch)

    # 5. power_delta cobre o reroll — e o motivo é real: a fundação entra no
    #    total_battle_power via stat_mult.
    m = re.search(r"_pv_on = \(feature_enabled_for_world\(\"progressao_visivel\"\)\s*\n\s*and pill\.effect_type in \(([^)]*)\)", ws)
    check("B/power_delta cobre o reroll",
          m is not None and "eternal_foundation_reroll" in m.group(1))
    check("B/power_delta ainda cobre qi_capacity",
          m is not None and "qi_capacity" in m.group(1))
    gl = _src("core", "game_logic.py")
    check("B/fundação entra no poder", "stat_mult = foundation_mult * core_mult" in gl
          and "* stat_mult" in gl)

    # 6. A fundação passa a EXISTIR numa tela do mini (paridade com /status).
    check("B/api_player expõe foundation_mult", '"foundation_mult": (' in ws)
    check("B/ProfileModal mostra a fundação",
          "player.foundation_quality &&" in tabs and "profile_foundation_label" in tabs)
    check("B/ProfileModal usa o mult do servidor", "player.foundation_mult" in tabs)
    # Lei §9 — o mini NÃO pode ter uma cópia da tabela de multiplicadores.
    check("B/mini não recalcula o mult",
          "1.6" not in tabs.split("profile_foundation_label")[0][-800:])

    # 7. A key que faltava no chat (o token cru que o jogador via).
    ptc = json.load(open(os.path.join(ROOT, "locales", "pt.json"), encoding="utf-8"))
    check("B/chat tem o label da pílula",
          "pill_effect_label_eternal_foundation_reroll" in ptc)


def item_b_review_fixes() -> None:
    """Os defeitos que o review adversarial encontrou — cada um com o seu
    guard-rail, para nunca voltarem."""
    ws = _src("core", "webserver.py")
    inv = _src("handlers", "inventory.py")
    tabs = _src("miniapp", "components", "tabs.js")
    alch = _src("core", "alchemy_engine.py")

    # ── (1) old == new NÃO pode ser anunciado como "Fundação Reforjada!" ──
    # É o resultado MAIS PROVÁVEL (70% numa divine sobre Perfeita).
    for old, new, want in [("perfect", "perfect", "same"),
                           ("perfect", "high", "down"),
                           ("high", "perfect", "up"),
                           (None, "medium", "up"),
                           ("sacred", "sacred", "same")]:
        d = fnd.foundation_delta(old, new)
        check(f"B/direction {old}→{new} == {want}", d["direction"] == want, str(d))
        check(f"B/mults de {old}→{new} vêm do engine",
              d["old_mult"] == fnd.get_foundation_multiplier(old)
              and d["new_mult"] == fnd.get_foundation_multiplier(new))
    check("B/apply devolve direction", "**_delta" in alch and "foundation_delta" in alch)
    check("B/chat ramifica por direction",
          '_dir == "same"' in inv and '_dir == "down"' in inv
          and "pill_effect_eternal_same" in inv and "pill_effect_eternal_down" in inv)
    check("B/mini ramifica por direction",
          'last.direction === "same"' in tabs and 'last.direction === "down"' in tabs
          and "pill_found_result_same" in tabs and "pill_found_result_down" in tabs)
    # …e o card/haptic não podem celebrar uma perda.
    check("B/mini não vibra sucesso num resultado ruim",
          'haptic(outcomeBad ? "warning" : "success")' in tabs)
    check("B/mini pinta o card pelo resultado", "resultBad" in tabs)

    # ── (2) Sagrada: recusa ANTES do débito, zero consumo (Lei §1) ──
    check("B/guard sacred (eternal)",
          fnd.foundation_pill_block_reason("sacred", "eternal_foundation_reroll")
          == "foundation_sacred_locked")
    check("B/guard sacred (reparo)",
          fnd.foundation_pill_block_reason("sacred", "foundation_reroll")
          == "foundation_sacred_locked")
    check("B/guard sem fundação (reparo)",
          fnd.foundation_pill_block_reason(None, "foundation_reroll")
          == "foundation_not_established")
    check("B/guard NÃO bloqueia o caso normal",
          fnd.foundation_pill_block_reason("perfect", "eternal_foundation_reroll") is None
          and fnd.foundation_pill_block_reason(None, "eternal_foundation_reroll") is None)
    check("B/guard não toca outras pílulas",
          fnd.foundation_pill_block_reason("sacred", "qi_capacity") is None)
    # O guard corre ANTES do UPDATE que debita (senão o item continua a arder).
    i_guard = ws.find("foundation_pill_block_reason")
    i_debit = ws.find("PlayerInventory.quantity - 1")
    check("B/endpoint recusa ANTES do débito", 0 < i_guard < i_debit,
          f"guard@{i_guard} debit@{i_debit}")
    # Escopo: SÓ o corpo de `_do_use_pill` (o `_do_use_pill_bulk`, que aparece
    # antes no ficheiro, é `stat_boost`-only — nenhuma pílula de fundação passa
    # por lá, provado abaixo).
    _body = inv.split("async def _do_use_pill(")[1].split(chr(10) + "async def ")[0]
    j_guard = _body.find("foundation_pill_block_reason")
    j_debit = _body.find("PlayerInventory.quantity - 1")
    check("B/chat recusa ANTES do débito", 0 <= j_guard < j_debit,
          f"guard@{j_guard} debit@{j_debit}")
    _bulk = inv.split("async def _do_use_pill_bulk(")[1].split(chr(10) + "async def ")[0]
    # QoL 07/08 (report [jogador]): o lote deixou de ser `stat_boost`-only e
    # passou a cobrir também os consumíveis de REPOSIÇÃO. O assert antigo
    # travava na string literal do gate; o que importa (e continua verdade) é a
    # INVARIANTE: nenhuma pílula de FUNDAÇÃO passa pelo lote, logo o lote não
    # precisa do `foundation_pill_block_reason`.
    from core.alchemy_engine import BULK_REFILL_TYPES as _BRT
    check("B/bulk recusa tudo o que não seja stat_boost ou reposição",
          'if pill.effect_type != "stat_boost" and not _is_refill:' in _bulk)
    check("B/nenhuma pílula de fundação entra no lote (por isso não precisa do guard)",
          not (_BRT & {"foundation_reroll", "eternal_foundation_reroll"}), str(_BRT))
    check("B/mini desabilita o botão com fundação travada",
          "scaled.foundation && scaled.foundation.locked" in tabs)
    check("B/mini nomeia a recusa", '"foundation_sacred_locked"' in tabs)

    # ── (3) âncora COMPAT: NULL em realm>=2 vale medium (×1.15) ──
    check("B/efetiva NULL@realm2 == medium",
          fnd.effective_foundation_quality(None, 2) == "medium")
    check("B/efetiva NULL@realm0 == None",
          fnd.effective_foundation_quality(None, 0) is None)
    check("B/efetiva respeita a real", fnd.effective_foundation_quality("high", 9) == "high")
    p_c = fnd.foundation_reroll_preview(None, "perfect", realm=8)
    med = next(o for o in p_c["odds"] if o["quality"] == "medium")
    check("B/COMPAT: medium não é 'ganho' falso", med["direction"] == "same", str(med))
    check("B/COMPAT: âncora == 1.15", abs(p_c["current_mult"] - 1.15) < 1e-9)
    p_n = fnd.foundation_reroll_preview(None, "perfect")
    check("B/sem realm, âncora crua", abs(p_n["current_mult"] - 1.0) < 1e-9)

    # ── (4) a pílula irmã (id 34, min_realm 2) não imprime mais "Valor: 1.0" ──
    check("B/chat marca foundation_trial", '{"kind": "foundation_trial"' in inv)
    check("B/endpoint marca foundation_trial", '{"kind": "foundation_trial"' in ws)
    check("B/chat rende a regra da prova", 'inv_pill_detail_found_trial' in inv)
    check("B/mini rende a regra da prova",
          'scaled.kind === "foundation_trial"' in tabs and 'pill_found_trial' in tabs)
    # O ramo `raw` (que imprime scaled["value"]) já não pode apanhar as duas.
    raw_branch = inv.split("# Revive — magnitude is not numeric")[-1][:200]
    check("B/só o revive sobra no ramo raw", '"kind": "raw"' in raw_branch)


# ══════════════════════════════════════════════════════════════════════════
# Item C — o refino que emudece no topo
# ══════════════════════════════════════════════════════════════════════════
def item_c_engine() -> None:
    """O teto é design e NÃO se mexe — só passa a falar."""
    fe = _src("core", "forge_engine.py")
    check("C/teto G7 intacto no engine", 'if target.grade >= 7: return None, "max_grade"' in fe)
    check("C/refino não filtra por tipo de artefato",
          "slot" not in fe.split("async def refine_artifact")[1].split("async def")[0])
    ws = _src("core", "webserver.py")
    check("C/preview devolve at_max_grade em G7",
          'return {"duplicates": 0, "at_max_grade": True}' in ws)


def item_c_wiring() -> None:
    tabs = _src("miniapp", "components", "tabs.js")

    # 1. O botão deixou de ser um mudo: o caminho `at_max_grade` do modal
    #    (que já existia, elegante) passa a ser ALCANÇÁVEL.
    m = re.search(r"<ActionBtn variant=\"ghost\"\s*\n\s*(disabled=\{\(a\.grade[^\n]*\n\s*)?onClick=\{\(\) => \{ haptic\(\"select\"\); setPicked\(\{ kind:\"refine\"",
                  tabs)
    check("C/botão Refinar não é mais disabled em G7",
          m is not None and m.group(1) is None,
          "o disabled={(a.grade ?? 0) >= 7} ainda está lá")
    check("C/o modal ainda trata at_max_grade", "preview.at_max_grade &&" in tabs)

    # 2. O chip diz o estado NA LINHA (antes de tocar em nada).
    check("C/chip ⭐ na linha do artefato G7",
          '(a.grade ?? 0) === 7 ?' in tabs and 't("refine_at_max")' in tabs)

    # 3. A recusa aponta o caminho seguinte (Lei §1).
    check("C/teaser do caminho G8 no modal", 't("refine_at_max_next")' in tabs)

    # 4. O detalhe do item no inventário fala de refino (é onde ele olhou).
    check("C/detalhe do item aponta o Ateliê", 't("inv_detail_refine_hint"' in tabs)
    check("C/detalhe do item diz o teto", 't("inv_detail_refine_at_max")' in tabs)

    # 5. A string de erro do servidor também ganhou o caminho seguinte.
    mini_pt = json.load(open(os.path.join(ROOT, "miniapp", "i18n", "pt.json"), encoding="utf-8"))
    check("C/workshop_err_max_grade enriquecida",
          "Mahayana" in mini_pt.get("workshop_err_max_grade", ""))

    # ── Correções do review adversarial ──
    # (a) o modal que agora ABRE não pode mostrar "Duplicados ×0" (o servidor
    #     faz short-circuit e não conta) nem "60%" (chance irrolável) em G7.
    check("C/card de duplicatas escondido no teto",
          "{!preview.at_max_grade && (" in tabs)
    # (b) G8 Celestial EXISTE — não se pode dizer a um G8 que o máximo é G7.
    check("C/chip distingue G8 de G7",
          "(a.grade ?? 0) >= 8 ?" in tabs and 'refine_at_absolute_max' in tabs)
    check("C/detalhe distingue G8 de G7",
          "(entry.grade ?? 0) >= 8" in tabs and 'inv_detail_refine_absolute_max' in tabs)
    fs = _src("database", "seeds", "forge_seeds.py")
    check("C/G8 é alcançável (receitas tier 6)", '"grade": 8' in _src("database", "seeds", "artifacts_seeds.py")
          or "required_realm" in fs)
    # (c) a dica não pode inventar um nome de UI que não existe.
    for lg in ("pt", "en", "es"):
        d = json.load(open(os.path.join(ROOT, "miniapp", "i18n", f"{lg}.json"), encoding="utf-8"))
        hint = d.get("inv_detail_refine_hint", "")
        check(f"C/{lg}: a dica usa o nome REAL do Ateliê", "{workshop}" in hint,
              f"{hint[:60]!r}")
        check(f"C/{lg}: nome do Ateliê existe", bool(d.get("workshop_open_btn")))
    check("C/o front interpola o nome real",
          't("inv_detail_refine_hint", { workshop: t("workshop_open_btn") })' in tabs)


# ══════════════════════════════════════════════════════════════════════════
# i18n — ×3 (chat) e ×3 (mini), placeholders idênticos
# ══════════════════════════════════════════════════════════════════════════
CHAT_KEYS = [
    "pill_effect_label_eternal_foundation_reroll",
    "pill_effect_label_foundation_reroll",
    "pill_effect_label_core_essence",
    "pill_effect_label_body_tempering_progress",
    "pill_effect_label_qi_regen_boost",
    "pill_effect_label_special",
    "inv_pill_detail_found_current",
    "inv_pill_detail_found_current_none",
    "inv_pill_detail_found_locked",
    "inv_pill_detail_found_odds",
    "inv_pill_detail_found_odds_row",
    "inv_pill_detail_found_sacred",
    "inv_pill_detail_found_sacred_hint",
    "inv_pill_detail_found_risk",
    # Correções do review adversarial
    "inv_pill_detail_found_trial",
    "pill_effect_eternal_same",
    "pill_effect_eternal_down",
    "pill_effect_eternal_mult",
    "pill_foundation_sacred_locked",
    "pill_foundation_not_established",
]

MINI_KEYS = [
    "pill_found_current",
    "pill_found_current_none",
    "pill_found_locked",
    "pill_found_odds_title",
    "pill_found_sacred_now",
    "pill_found_sacred_hint",
    "pill_found_risk",
    "pill_found_result",
    "pill_found_result_sacred",
    "pill_found_result_mult",
    "profile_foundation_label",
    "refine_at_max_next",
    "inv_detail_refine_hint",
    "inv_detail_refine_at_max",
    # Correções do review adversarial
    "pill_found_trial",
    "pill_found_result_same",
    "pill_found_result_down",
    "pill_found_result_mult_delta",
    "pill_found_locked_btn",
    "pill_foundation_sacred_locked",
    "pill_foundation_not_established",
    "refine_at_absolute_max",
    "inv_detail_refine_absolute_max",
]


def _ph(s: str) -> set:
    return set(re.findall(r"\{(\w+)\}", s or ""))


def i18n_batch() -> None:
    for label, base, keys in (("chat", "locales", CHAT_KEYS),
                              ("mini", os.path.join("miniapp", "i18n"), MINI_KEYS)):
        data = {}
        for lg in ("pt", "en", "es"):
            data[lg] = json.load(open(os.path.join(ROOT, base, f"{lg}.json"), encoding="utf-8"))
        check(f"i18n/{label} paridade de contagem",
              len(data["pt"]) == len(data["en"]) == len(data["es"]),
              f"{len(data['pt'])}/{len(data['en'])}/{len(data['es'])}")
        for k in keys:
            for lg in ("pt", "en", "es"):
                check(f"i18n/{label}:{lg} tem {k}", k in data[lg])
            if all(k in data[lg] for lg in ("pt", "en", "es")):
                check(f"i18n/{label} placeholders idênticos em {k}",
                      _ph(data["pt"][k]) == _ph(data["en"][k]) == _ph(data["es"][k]),
                      f"{_ph(data['pt'][k])} / {_ph(data['en'][k])} / {_ph(data['es'][k])}")
                for lg in ("pt", "en", "es"):
                    check(f"i18n/{label}:{lg} {k} não vazia", str(data[lg][k]).strip() != "")

    # PT-BR (memória do projeto: nunca PT-europeu nas strings de jogador).
    pt_all = {}
    pt_all.update({k: v for k, v in json.load(
        open(os.path.join(ROOT, "locales", "pt.json"), encoding="utf-8")).items() if k in CHAT_KEYS})
    pt_all.update({k: v for k, v in json.load(
        open(os.path.join(ROOT, "miniapp", "i18n", "pt.json"), encoding="utf-8")).items() if k in MINI_KEYS})
    EU_PT = ("utilizador", "ecrã", "ecra", "ficheiro", "carregue em", "clique em",
             "telemóvel", "autocarro", "a fazer", "estás", "tens de", "podes",
             "a tua", "o teu", "a sua fundação está")
    for k, v in pt_all.items():
        low = str(v).lower()
        hits = [w for w in EU_PT if w in low]
        check(f"i18n/pt-br sem EU-PT em {k}", not hits, f"{hits}")


# ══════════════════════════════════════════════════════════════════════════
def main() -> None:
    item_a_seeds()
    item_a_seed_sync()
    item_a_wiring()
    item_b_preview_pure()
    item_b_preview_equals_apply()
    item_b_wiring()
    item_b_review_fixes()
    item_c_engine()
    item_c_wiring()
    i18n_batch()

    print(f"\n{PASS} PASS · {len(FAILS)} FAIL")
    if FAILS:
        for f in FAILS:
            print(" FAIL:", f)
        sys.exit(1)
    print("All green — QoL 03/08: a quest tem caminho solo · a fundação mostra "
          "odds e antes→depois · o teto G7 fala e aponta o G8.")


if __name__ == "__main__":
    main()
