"""Seita — teste isolado da disclosure do bloqueio de caminho (SEM DB).

Roda: python -X utf8 scripts/_test_seita_disclosure.py

Nasceu da pergunta do jogador **[jogador]** (28/07/2026): "como entro pra seita
demoníaca? aqui diz que um ancião vai aparecer pra mim". O `/seita` listava só
casas com afinidade > 0 e o hard-gate de caminho ZERA a casa do outro lado —
logo as Profundezas Abissais **nunca apareciam** para quem não era demoníaco.
Nem o nome, nem o requisito. O jogador teve de perguntar no grupo.

O que este teste protege:
  1. **O caso do [jogador]**: um cultivador SEM caminho (ou justo) vê o Abismo na
     lista de bloqueadas, com o motivo — nunca um silêncio.
  2. **O espelho exato do hard-gate**: `path_block_reason` responde a MESMA
     pergunta que `compute_affinity_breakdown` (bloqueado ⟺ path_gate False,
     para os 9×4 pares caminho/casa). Se o gate mudar e o motivo não, as duas
     telas mentem — esta é a asserção que apanha isso.
  3. **Simetria**: o demoníaco também é barrado das 8 justas, e também vê o
     motivo (o buraco existia nos DOIS sentidos).
  4. Uma casa de score 0 que NÃO está barrada não entra em nenhuma lista (é um
     "ainda não", não um segredo).
  5. i18n ×3 ×2 + o aviso da escolha irreversível + wiring nas 2 superfícies.
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

import core.affinity_engine as aff  # noqa: E402
from core.world_sects_engine import WORLD_SECT_KEYS, is_demonic_sect  # noqa: E402

PASS = 0
FAILS: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(f"{name} {('— ' + detail) if detail else ''}")


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _src(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


PATHS = (None, "righteous", "demonic", "rogue")


def _gate_blocks() -> None:
    """O motivo tem de espelhar o hard-gate EXATAMENTE — 9 casas × 4 caminhos."""
    for path in PATHS:
        for key in WORLD_SECT_KEYS:
            bd = aff.compute_affinity_breakdown(
                path=path, karma=0, current_continent=None, home_continent=None,
                guild_lineage_key=None, sect_key=key,
            )
            reason = aff.path_block_reason(path, key)
            gate_open = bool(bd.get("path_gate"))
            check(f"gate.mirror.{path}.{key}", (reason is None) == gate_open,
                  f"reason={reason} gate_open={gate_open}")
            # E o motivo é o CERTO, não só "algum motivo".
            if reason is not None:
                want = (aff.BLOCK_NEEDS_DEMONIC if is_demonic_sect(key)
                        else aff.BLOCK_BARRED_DEMONIC)
                check(f"gate.reason.{path}.{key}", reason == want, reason)

    # Casa desconhecida nunca inventa bloqueio.
    check("gate.unknown_sect", aff.path_block_reason("demonic", "nao_existe") is None)


def _relato_blocks() -> None:
    """O caso REAL: o cultivador que não é demoníaco tem de VER o Abismo."""
    abyss = [k for k in WORLD_SECT_KEYS if is_demonic_sect(k)]
    check("relato.one_demonic_house", len(abyss) == 1,
          f"{abyss} — se nascer uma 2ª casa demoníaca, a resposta ao jogador muda")
    ab = abyss[0]

    for path in (None, "righteous", "rogue"):
        check(f"relato.blocked.{path}",
              aff.path_block_reason(path, ab) == aff.BLOCK_NEEDS_DEMONIC,
              "quem não é demoníaco TEM de ver o motivo, não o silêncio")
        # E o score é mesmo 0 — é por isso que o filtro `> 0` o escondia.
        bd = aff.compute_affinity_breakdown(
            path=path, karma=-999, current_continent="moyu", home_continent="moyu",
            guild_lineage_key=ab, sect_key=ab,
        )
        check(f"relato.zero.{path}", int(bd["total"]) == 0,
              "nem karma −999 em moyu fura o hard-gate — daí o silêncio ser fatal")

    # O demoníaco, esse, entra.
    check("relato.demonic_passes", aff.path_block_reason("demonic", ab) is None)


def _symmetry_blocks() -> None:
    """O buraco existia nos DOIS sentidos."""
    righteous = [k for k in WORLD_SECT_KEYS if not is_demonic_sect(k)]
    check("sym.eight_righteous", len(righteous) == 8, str(len(righteous)))
    for key in righteous:
        check(f"sym.demonic_barred.{key}",
              aff.path_block_reason("demonic", key) == aff.BLOCK_BARRED_DEMONIC)
        for path in (None, "righteous", "rogue"):
            check(f"sym.open.{path}.{key}",
                  aff.path_block_reason(path, key) is None,
                  "casa justa não é bloqueada por falta de caminho — só pontua menos")


def _overview_blocks() -> None:
    """get_affinity_overview: elegíveis + bloqueadas, sem inventar segredo."""
    class _R:
        """Resultado fake com um valor por forma de leitura (dispatch no SQL)."""

        def __init__(self, one=None, row=None, rows=None):
            self._one, self._row, self._rows = one, row, list(rows or [])

        def scalar_one_or_none(self):
            return self._one

        def scalar(self):
            return self._one

        def first(self):
            return self._row

        def all(self):
            return list(self._rows)

        def scalars(self):
            rows = self._rows

            class S:
                def all(self_inner):
                    return list(rows)
            return S()

    class FakeSession:
        """Dispatch por substring do SQL compilado (padrão MV-7/TEC-1/TEC-2).
        Serve a MESMA linha para queries diferentes = teste que passa pelo
        motivo errado; daí o dispatch e o AssertionError no fim."""

        def __init__(self, path):
            self.path = path

        async def execute(self, stmt, params=None):
            s = str(stmt).lower()
            # A agregação das Encruzilhadas (quest_choice_log) → (r, d, n).
            if "quest_choice_log" in s or "sum(" in s:
                return _R(row=(0, 0, 0))
            # O fetch de 4 colunas do compute_all_affinity_breakdowns.
            if "home_continent" in s:
                return _R(row=(self.path, 0, None, None))
            # O fetch de 1 coluna (players.path) do get_affinity_overview.
            if "players.path" in s or "path" in s:
                return _R(one=self.path)
            if "sect_members" in s or "sects" in s:
                return _R(one=None, rows=[])
            raise AssertionError("query inesperada: " + s[:160].replace("\n", " "))

    for path in PATHS:
        ov = run(aff.get_affinity_overview(FakeSession(path), 111, n=3))
        check(f"ov.threshold.{path}", ov["threshold"] == aff.AFFINITY_THRESHOLD)
        check(f"ov.path.{path}", ov["path"] == path)
        blocked_ids = {r["sect_id"] for r in ov["blocked"]}
        expected = {k for k in WORLD_SECT_KEYS if aff.path_block_reason(path, k)}
        check(f"ov.blocked_set.{path}", blocked_ids == expected,
              f"{sorted(blocked_ids)} != {sorted(expected)}")
        # Bloqueada NUNCA aparece como elegível (seria mentira dupla).
        elig_ids = {r["sect_id"] for r in ov["eligible"]}
        check(f"ov.disjoint.{path}", not (elig_ids & blocked_ids))
        # Todo bloqueio carrega o motivo.
        check(f"ov.has_reason.{path}", all(r.get("reason") for r in ov["blocked"]))

    # O caso do [jogador] ponta a ponta: sem caminho, o Abismo está na lista.
    ov = run(aff.get_affinity_overview(FakeSession(None), 111, n=3))
    ab = [k for k in WORLD_SECT_KEYS if is_demonic_sect(k)][0]
    check("ov.relato_sees_abyss", ab in {r["sect_id"] for r in ov["blocked"]},
          "é ISTO que ele não conseguia ver")


def _i18n_blocks() -> None:
    from inject_seita_disclosure_i18n import CHAT, CHAT_OVERRIDES, MINIAPP
    for lang in ("pt", "en", "es"):
        chat = json.loads(_src("locales", lang + ".json"))
        mini = json.loads(_src("miniapp", "i18n", lang + ".json"))
        for k in CHAT[lang]:
            check(f"i18n.chat.{lang}.{k}", k in chat)
        for k in MINIAPP[lang]:
            check(f"i18n.mini.{lang}.{k}", k in mini)
        # O override PEGOU (a string passiva antiga tinha de morrer).
        for k, v in CHAT_OVERRIDES[lang].items():
            check(f"i18n.override.{lang}.{k}", chat.get(k) == v)
        check(f"i18n.no_passive.{lang}",
              "parar à sua frente" not in chat.get("wsect_menu_explain", ""),
              "a string que o jogador citou não pode voltar")
        # Os 2 motivos existem nas DUAS superfícies, com a mesma taxonomia.
        for reason in (aff.BLOCK_NEEDS_DEMONIC, aff.BLOCK_BARRED_DEMONIC):
            check(f"i18n.reason.chat.{lang}.{reason}", f"wsect_block_{reason}" in chat)
            check(f"i18n.reason.mini.{lang}.{reason}", f"wsect_block_{reason}" in mini)
        # O aviso do irreversível tem de DIZER que é irreversível.
        warn = chat.get("wsect_menu_path_warning", "")
        check(f"i18n.warn.{lang}", bool(warn) and len(warn) > 40, warn[:60])


def _wiring_blocks() -> None:
    sh = _src("handlers", "sect.py")
    ws = _src("core", "webserver.py")
    tj = _src("miniapp", "components", "tabs.js")
    check("wire.engine", "def path_block_reason(" in _src("core", "affinity_engine.py"))
    check("wire.overview", "def get_affinity_overview(" in _src("core", "affinity_engine.py"))
    check("wire.chat", "get_affinity_overview" in sh and "wsect_menu_blocked_head" in sh)
    check("wire.chat_warning", "wsect_menu_path_warning" in sh)
    check("wire.mini_payload", 'path_block' in ws and "_aff_block_reason" in ws)
    check("wire.mini_render", "wsect_block_" in tj,
          "sem o render, o motivo fica no payload e o jogador não vê nada")
    # O motivo no mini é CONDICIONAL (payload inalterado para quem não é barrado).
    check("wire.mini_conditional", "if _blk:" in ws)


def _blocks() -> None:
    _gate_blocks()
    _relato_blocks()
    _symmetry_blocks()
    _overview_blocks()
    _i18n_blocks()
    _wiring_blocks()


def main() -> None:
    _blocks()
    print(f"\n{PASS} PASS · {len(FAILS)} FAIL")
    if FAILS:
        for f in FAILS:
            print(" ✗", f)
        sys.exit(1)
    print("All green — Seita: disclosure do bloqueio de caminho (pergunta do [jogador]).")


if __name__ == "__main__":
    main()
