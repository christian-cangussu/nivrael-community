# -*- coding: utf-8 -*-
"""Lote do [jogador] (12-14/08/2026) — suite COMMITTED.

    python -X utf8 scripts/_test_relatos_0814.py

  1. 🗺️ a expedição avisa UMA vez (era de hora em hora, para sempre)
  2. 💰 a doação por chat nunca mais fica MUDA
  3. 轮回 o Caminho re-deriva no renascimento — e é dito ANTES do tap
  4. 🩺 o alvo da cura é uma LISTA, e a lista espelha as recusas
"""
from __future__ import annotations

import io
import json
import os
import re
import textwrap
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

if "telegram" not in sys.modules:
    _tg = types.ModuleType("telegram")
    _tg.Update = object
    _err = types.ModuleType("telegram.error")

    class _TgErr(Exception):
        retry_after = 0

    _err.RetryAfter = _err.TimedOut = _err.NetworkError = _err.BadRequest = _TgErr
    _tg.error = _err
    sys.modules["telegram"] = _tg
    sys.modules["telegram.error"] = _err

PASS = 0
FAIL: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name} {detail}")
        print(f"  FAIL: {name} {detail}")


def _read(rel: str) -> str:
    with io.open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


LANGS = ("pt", "en", "es")
CHAT = {lg: json.loads(_read(f"locales/{lg}.json")) for lg in LANGS}
MINI = {lg: json.loads(_read(f"miniapp/i18n/{lg}.json")) for lg in LANGS}

# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] 🗺️ A EXPEDIÇÃO AVISA UMA VEZ")
# ═══════════════════════════════════════════════════════════════════════════
_be = _read("core/beast_engine.py")
_fn = _be.split("async def check_finished_expeditions")[1].split("\ndef ")[0]
# ⚠️ A causa era não haver ESTADO NENHUM: a função lia as linhas prontas e
# devolvia-as, e o job de 1h voltava a lê-las para sempre.
check("1/o aviso passa pelo notify() (que deduplica)", "notify(" in _fn)
check("1/…com um ref_id ESTÁVEL desta expedição", 'ref_id = f"exped:' in _fn)
check("1/o ref_id leva o instante do RETORNO (a próxima expedição avisa de novo)",
      "expedition_returns_at" in _fn and "_stamp" in _fn)
check("1/quem já foi avisado NÃO entra na lista de DMs",
      "if row is None:" in _fn and "continue" in _fn)
check("1/o DM continua a existir para quem é avisado pela 1ª vez",
      "notifications.append(" in _fn)
check("1/a falha do notify não derruba o job (fail-safe)",
      "except Exception:" in _fn and "row = None" in _fn)
for lg in LANGS:
    for k in ("notif_expedition_done_title", "notif_expedition_done_body"):
        check(f"1/{lg}/{k} existe", bool(CHAT[lg].get(k)))
# ⚠️ Uma notif renderiza LAZY sobre o payload gravado na época: a key é NOVA e
# o payload nasce com ela.
check("1/o payload traz {beast} desde a 1ª row",
      "{beast}" in CHAT["pt"]["notif_expedition_done_body"])
check("1/o payload é passado no emissor", '"beast": beast_name' in _fn)

# ═══════════════════════════════════════════════════════════════════════════
print("[2] 💰 A DOAÇÃO NUNCA MAIS FICA MUDA")
# ═══════════════════════════════════════════════════════════════════════════
_sect = _read("handlers/sect.py")
_don = _sect.split("async def process_sect_donation_input")[1].split("\nasync def ")[0]
check("2/o `except: return` mudo do parse morreu", "except: return" not in _don)
check("2/o parse é TOLERANTE (1.000, 1,000, '1000 pedras')",
      "ch.isdigit()" in _don)
check("2/valor ininteligível responde", "sect_donate_err_number" in _don)
check("2/quem não está em seita recebe o motivo (era o silêncio do report)",
      "sect_donate_err_no_sect" in _don)
# ⚠️ O assert que importa não é "quantos `return` existem" — é se ALGUM sai sem
# falar. Cada saída tem de ter um `reply_text` nas linhas imediatamente acima.
_lines = _don.splitlines()
_mudos = []
for _i, _ln in enumerate(_lines):
    if _ln.strip() != "return":
        continue
    _prev = " ".join(_lines[max(0, _i - 4):_i])
    if "reply_text" not in _prev:
        _mudos.append(_i)
check("2/…e NENHUM `return` sai sem falar (Lei §1)", not _mudos,
      f"linhas mudas: {[_lines[i - 1].strip()[:40] for i in _mudos]}")
# ⚠️ Sem limpar a flag, a mensagem SEGUINTE do jogador era comida outra vez.
check("2/toda saída limpa a flag `awaiting_sect_donation`",
      _don.count("_clear()") >= 5, str(_don.count("_clear()")))
check("2/o crédito da quest continua lá (o report também o citava)",
      'track_quest(session, player.telegram_id, "sect_contribution"' in _don)
check("2/o sucesso continua a confirmar", "sect_donate_success" in _don)
for lg in LANGS:
    for k in ("sect_donate_err_number", "sect_donate_err_no_sect"):
        check(f"2/{lg}/{k} existe", bool(CHAT[lg].get(k)))

# ═══════════════════════════════════════════════════════════════════════════
print("[3] 轮回 O CAMINHO RE-DERIVA NO RENASCIMENTO")
# ═══════════════════════════════════════════════════════════════════════════
import core.karma_engine as ke  # noqa: E402
import core.path_engine as pe  # noqa: E402

# A aritmética que já existia e estava certa — o buraco era não a re-correr.
check("3/karma -1000 deriva DEMONÍACO", ke.derive_path_from_karma(-1000) == "demonic")
check("3/karma -250 (o limiar exato) deriva demoníaco",
      ke.derive_path_from_karma(-250) == "demonic")
check("3/karma -249 ainda é Errante", ke.derive_path_from_karma(-249) == "rogue")
check("3/karma 0 é Errante", ke.derive_path_from_karma(0) == "rogue")
check("3/karma +250 é Justo", ke.derive_path_from_karma(250) == "righteous")
_pr = _read("core/prestige_engine.py")
check("3/o renascimento re-deriva o caminho", "derive_path_from_karma" in _pr)
check("3/…com o destrancamento explícito", "allow_recrystallize=True" in _pr)
# ⚠️ `set_player_path` exige R3+. Correr DEPOIS do reset (realm=0) seria um
# no-op silencioso — o bug mais fácil de escrever aqui.
check("3/…ANTES do reset do reino (senão a trava de R3 recusa)",
      _pr.index("derive_path_from_karma") < _pr.index("player.realm = 0"))
check("3/…e só escreve quando MUDA", "_derived != _path_before" in _pr)
check("3/a falha não derruba o renascimento", "path re-derivation failed" in _pr)
# O aviso ANTES do tap — uma mudança irreversível por surpresa seria pior.
check("3/existe a pré-visualização do caminho",
      "async def rebirth_path_preview" in _read("core/karma_engine.py"))
check("3/…e o /renascer imprime-a antes dos botões",
      "rebirth_path_preview" in _read("handlers/prestige.py"))
check("3/a pré-visualização cala-se quando NÃO muda (o caso normal)",
      "nxt == cur" in _read("core/karma_engine.py"))
for lg in LANGS:
    v = CHAT[lg].get("prestige_path_change") or ""
    check(f"3/{lg}/prestige_path_change existe", bool(v))
    check(f"3/{lg}: diz o antes E o depois (Lei §10)",
          "{from_name}" in v and "{to_name}" in v, v[:60])
    check(f"3/{lg}: diz o karma que causou", "{karma}" in v)
# A docstring do path_engine dizia que o Rito era o ÚNICO caller — deixaria de
# ser verdade no minuto em que este fix entrou.
_pe = _read("core/path_engine.py")
check("3/a docstring do path_engine já não diz 'ONLY it'", "and ONLY it" not in _pe)
check("3/…e nomeia os DOIS canais", "TWO** legitimate" in _pe or "TWO" in _pe)
check("3/o Rito continua a ser o outro canal", "choose_heart_demon" in _pe)

# ═══════════════════════════════════════════════════════════════════════════
print("[4] 🩺 O ALVO DA CURA É UMA LISTA")
# ═══════════════════════════════════════════════════════════════════════════
_ws = _read("core/webserver.py")
_tabs = _read("miniapp/components/tabs.js")
check("4/o servidor projeta os alvos", 'view["heal_targets"]' in _ws)
_blk = _ws.split('view["heal_targets"]')[0][-2600:]
# ⚠️ A lista TEM de espelhar os guardas do heal_ally, senão o seletor oferece
# alguém que o servidor vai recusar — que é como este tipo de UI ganha bugs.
check("4/espelha o guarda do CONTINENTE", "current_continent == _cont" in _blk)
check("4/espelha o guarda de NÃO-SER-VOCÊ", "telegram_id != user_id" in _blk)
check("4/espelha o guarda do GAP DE REINO", "PROF_HEAL_REALM_GAP" in _blk)
check("4/espelha o guarda do HP CHEIO", "_cu >= _mx - 0.5" in _blk)
check("4/espelha o shadow_mode (privacidade)", "shadow_mode == False" in _blk)
check("4/exclui quem nunca se nomeou (dao_name NULL é inalcançável)",
      "dao_name.is_not(None)" in _blk)
check("4/a lista é limitada (nunca um payload sem teto)", "[:12]" in _blk or ">= 12" in _blk)
check("4/o mini renderiza a lista", "view.heal_targets" in _tabs)
check("4/…e diz honestamente quando não há ninguém", "prf_mini_heal_nobody" in _tabs)
check("4/o campo de texto FICA (quem sabe o nome de alguém fora dos 12)",
      "prf_mini_heal_placeholder" in _tabs)
check("4/o alvo continua a viajar por dao_name (o mini nunca vê telegram_id)",
      "tg.dao_name" in _tabs and '"telegram_id"' not in _ws.split('view["heal_targets"]')[0][-1200:])
for lg in LANGS:
    check(f"4/{lg}/prf_mini_heal_nobody existe", bool(MINI[lg].get("prf_mini_heal_nobody")))

# ═══════════════════════════════════════════════════════════════════════════
print("[5] i18n / PT-BR / paridade")
# ═══════════════════════════════════════════════════════════════════════════
check("5/paridade ×3 no chat", len({len(v) for v in CHAT.values()}) == 1,
      str([len(v) for v in CHAT.values()]))
check("5/paridade ×3 no mini", len({len(v) for v in MINI.values()}) == 1,
      str([len(v) for v in MINI.values()]))
_new_chat = ("sect_donate_err_number", "sect_donate_err_no_sect",
             "notif_expedition_done_title", "notif_expedition_done_body",
             "prestige_path_change")
_TU = re.compile(r"\b(tu|teu|tua|teus|tuas|vosso|vossa|contigo)\b", re.IGNORECASE)
for k in _new_chat:
    _m = _TU.search(str(CHAT["pt"][k]))
    check(f"5/pt/{k}: PT-BR (sem tuteamento)", not _m, _m.group(0) if _m else "")
    # placeholders idênticos ×3
    _sets = [set(re.findall(r"\{(\w+)\}", str(CHAT[lg][k]))) for lg in LANGS]
    check(f"5/{k}: mesmos tokens ×3", _sets[0] == _sets[1] == _sets[2], str(_sets))
_m = _TU.search(str(MINI["pt"]["prf_mini_heal_nobody"]))
check("5/pt/prf_mini_heal_nobody: PT-BR", not _m, _m.group(0) if _m else "")
# A string do mini é React puro: um `*` sairia literal.
check("5/a string do mini NÃO tem markdown",
      not re.search(r"[*_`\[\]]", str(MINI["pt"]["prf_mini_heal_nobody"])))
check("5/as keys novas do chat NÃO foram parar ao mini",
      not [k for k in _new_chat if k in MINI["pt"]])

# ─────────────────────────────────────────────────────────────────────────────
# 6. 鎖 OS TRANCADOS (2026-09-04) — a guarda que impede a 6ª recorrência
#
# MEDIDO em produção a 2026-09-03: 27 duelos expirados a prender 13 jogadores,
# o mais antigo desde 23/05 (103 dias). A causa não foi lógica partida — foi que
# os varredores nasceram UM A UM, para a fonte que reclamou. O código cria DEZ
# fontes; sete não tinham varredor, incluindo a MAIOR (`arena_npc_fallback`,
# 1.352 lutas/30d) e o DEFAULT de `start_duel_pve` (`npc_hunt`).
#
# Esta secção existe para que isso não possa voltar a acontecer em silêncio.
print("\n=== 6. 鎖 os trancados: toda fonte PvE tem varredor ===")

_de = _read("core/duel_engine.py")

# 6.1 — O registo existe e é UM só.
check("6/PVE_SOURCES existe em duel_engine", "PVE_SOURCES = (" in _de)

import ast as _ast
_mod = _ast.parse(_de)
_registry: set[str] = set()
for _node in _mod.body:
    if isinstance(_node, _ast.Assign) and any(
            getattr(t, "id", "") == "PVE_SOURCES" for t in _node.targets):
        _registry = {e.value for e in _node.value.elts if isinstance(e, _ast.Constant)}
check("6/o registo tem as 10 famílias", len(_registry) == 10, str(sorted(_registry)))

# 6.2 ⚠️ A GUARDA QUE VALE O BLOCO INTEIRO.
# Varre o código à procura de qualquer `source="..."` passado ao
# `start_duel_pve` e de qualquer `pve_source == "..."`, e falha se aparecer uma
# fonte que o registo não conhece. Sem isto, a fonte nº 11 nasce sem rede e o
# jogador que a apanhar fica trancado até alguém reportar — que foi exactamente
# o ciclo que produziu os 103 dias.
_ENGINES = [
    "core/arena_engine.py", "core/exploration_engine.py", "core/webserver.py",
    "core/forbidden_path_engine.py", "core/jianghu_engine.py",
    "core/legacy_cave_engine.py", "core/sect_library_engine.py",
    "core/sect_trial_engine.py", "core/duel_engine.py", "core/pve_duel_settle.py",
    "core/npc_cultivator_engine.py",
]
_found: set[str] = set()
for _rel in _ENGINES:
    try:
        _src = _read(_rel)
    except Exception:
        continue
    _found |= set(re.findall(r'pve_source\s*==\s*"([a-z_]+)"', _src))
    _found |= set(re.findall(r'pve_source\s*=\s*"([a-z_]+)"', _src))
    # `source="x"` só dentro de uma chamada a start_duel_pve (± 12 linhas).
    for _m in re.finditer(r"start_duel_pve\(", _src):
        _seg = _src[_m.start():_m.start() + 700]
        _found |= set(re.findall(r'source\s*=\s*"([a-z_]+)"', _seg))
    # O default da própria assinatura conta como fonte real.
    _m2 = re.search(r'def start_duel_pve\([^)]*?source:\s*str\s*=\s*"([a-z_]+)"',
                    _src, re.S)
    if _m2:
        _found.add(_m2.group(1))

_orfas = sorted(_found - _registry)
check("6/⚠️ nenhuma fonte PvE fora do registo", not _orfas,
      "fontes sem varredor: %s — acrescentar a PVE_SOURCES no MESMO commit" % _orfas)

# 6.3 — O varredor é UM, cobre a família, e está ligado ao scheduler.
check("6/existe sweep_orphan_pve_duels", "async def sweep_orphan_pve_duels" in _de)
# UMA query indexada para as dez familias — nao uma por fonte (ver rev4 do MV-8:
# este varredor corre no tick de 60 s).
check("6/o varredor cobre o registo INTEIRO numa query",
      "pve_source.in_(PVE_SOURCES)" in _de)
_sched = _read("core/scheduler.py")
check("6/o scheduler chama a família inteira", "sweep_orphan_pve_duels" in _sched)

# 6.4 ⚠️ Nunca apagar uma linha: alguns presos estão GANHOS e por liquidar.
# ⚠️ A FATIA E' A FUNCAO, NAO UMA JANELA DE CARACTERES (2026-09-12).
# Esta linha era `[:4200]` e ficou VERMELHA quando o varredor ganhou comentarios
# — o `apply_post_duel_effects` saiu da janela sem sair da funcao. E' a familia
# de defeito que esta casa ja' pagou tres vezes: *a guarda afirma sobre o
# FICHEIRO (ou sobre um pedaco arbitrario dele) em vez de afirmar sobre o
# SITIO*. Uma guarda assim mente nos dois sentidos: fica verde pela ocorrencia
# errada e vermelha por prosa.
_sweep_src = _de.split("async def sweep_orphan_pve_duels")[1]
_sweep_src = _sweep_src.split(chr(10) + "async def ")[0]
# ⚠️ Medir o CÓDIGO, não a prosa: a própria docstring do varredor explica por que
# nunca apaga — e continha a palavra "DELETE", o que fazia esta guarda acender
# em cima da frase que a justifica. Mesma lição do `_code_only` da vitrine e do
# `grep -c revive` que deu falso positivo em "sobreviveria".
_sweep_code = re.sub(chr(34)*3 + ".*?" + chr(34)*3, "", _sweep_src, flags=re.S)
check("6/o varredor NUNCA apaga (só resolve)",
      "delete" not in _sweep_code.lower(),
      "um DELETE rouba duas vezes: a luta e o prémio")
check("6/o varredor paga o que ficou por liquidar",
      "apply_post_duel_effects" in _sweep_src and "_already_settled" in _sweep_src)

# ── 6.4b 🔴 O VARREDOR QUE CORREU 8 DIAS SEM CHEGAR A NINGUEM (2026-09-12) ──
#
# Report do grupo ([jogador], 11/09): *"Não quer mais entrar em combate"*.
# MEDIDO em producao a 12/09, nas duas bases:
#
#   o conjunto que o varredor varria .... 23.842 linhas (main)
#     dos quais ABERTOS .................      2
#     dos quais TERMINAIS ...............  23.840
#   as 200 que o `limit` devolvia ....... as 200 MAIS ANTIGAS da base,
#                                          de 17-21 de Maio, 200/200 ja' pagas
#   posicao dos 2 abertos na mesma ordem . 23.601 e 23.639
#
# Ou seja: UMA query com `state IN (abertos + terminais)` + `created_at ASC` +
# `limit 200` deixou a metade que DESTRANCA a morrer a' fome da metade que PAGA,
# de 60 em 60 segundos, durante oito dias (~11.500 passagens), enquanto tres
# jogadores estavam presos — o mais antigo desde 04/09 e **activo nesse dia**.
#
# ⚠️ ESTA E' A GUARDA QUE TERIA EVITADO ISTO, e ela afirma sobre o SITIO: as
# duas varreduras nao podem partilhar orcamento.
check("6b/⚠️ as duas metades NAO partilham o mesmo orcamento",
      "DUEL_OPEN_STATES + DUEL_TERMINAL_STATES" not in _sweep_code,
      "uma so' query para 2 abertos e 23.840 terminais = os abertos nunca saem")
check("6b/ha uma varredura SO' dos abertos (a que destranca)",
      "DuelSession.state.in_(DUEL_OPEN_STATES)" in _sweep_src)
check("6b/ha uma varredura SO' dos terminais (a que paga)",
      "DuelSession.state.in_(DUEL_TERMINAL_STATES)" in _sweep_src)
# ⚠️ e a que paga tem de filtrar o carimbo EM SQL, senao gasta as 200 linhas a
# reler duelos ja' pagos — a outra forma de morrer a' fome.
check("6b/a metade que paga filtra `pve_settled` em SQL",
      'contains([{"type": "pve_settled"}])' in _sweep_src,
      "sem isto o orcamento esgota-se em linhas ja' liquidadas")

# ── 6.4c 🔴 A MINA: fontes que liquidam NOUTRO sitio ───────────────────────
#
# O `arena_npc_fallback` liquida por `settle_arena_duel`, que NUNCA carimba
# `pve_settled`. MEDIDO: **16.483 duelos de arena do main** (229 do s2) parecem
# eternamente por liquidar. E o despachante escolhe o caminho da arena por haver
# uma linha em `arena_queue` ligada ao duelo — mas essa tabela tem UMA linha por
# jogador, reciclada a cada fila: so' **28 dos 16.483** ainda a tem.
# Os outros 16.455 cairiam no `settle_pve_duel`, que lhes daria XP de maestria e
# de Intencao **outra vez**.
_de_registry2 = _de.split("PVE_SOURCES_SETTLED_ELSEWHERE = (")
check("6c/existe o registo das fontes que liquidam noutro sitio",
      len(_de_registry2) > 1)
_else_src = _de_registry2[1].split(")")[0] if len(_de_registry2) > 1 else ""
check("6c/⚠️ o `arena_npc_fallback` esta la'",
      '"arena_npc_fallback"' in _else_src,
      "e' a fonte com settle proprio e sem carimbo — 16.483 linhas em producao")
# ⚠️ ANTI-GUARDA: uma fonte mal escrita aqui e' uma exclusao que nao exclui nada.
_else_names = set(re.findall(r'"([a-z_]+)"', _else_src))
check("6c/toda fonte do registo-de-excepcao existe em PVE_SOURCES",
      _else_names and _else_names <= _registry,
      "fonte fora do registo: %s" % sorted(_else_names - _registry))
# a arena SAI da metade que paga...
check("6c/a metade que paga EXCLUI as fontes com settle proprio",
      "PVE_SOURCES_SETTLED_ELSEWHERE" in _sweep_src
      and "not in PVE_SOURCES_SETTLED_ELSEWHERE" in _sweep_src)
# ...mas FICA na que destranca, que e' o proprio motivo deste conserto.
_abertos_blk = _sweep_src.split("DuelSession.state.in_(DUEL_OPEN_STATES)")[0]
check("6c/⚠️ mas a arena FICA na metade que DESTRANCA",
      "PVE_SOURCES_SETTLED_ELSEWHERE" not in _abertos_blk,
      "excluir a arena aqui era desfazer o conserto: e' ELA que prendia gente")
# e o despachante recusa a queda para o settle PvE
_apde = _de.split("async def apply_post_duel_effects")[1].split(chr(10) + "async def ")[0]
check("6c/o despachante NAO atira uma fonte com settle proprio para o PvE",
      "PVE_SOURCES_SETTLED_ELSEWHERE" in _apde,
      "um duelo de arena sem linha de fila caia no settle PvE e pagava XP 2x")

# 6.5 — O timeout passa a TERMINAR a luta (PvE), não uma ronda.
check("6/existe resolve_pve_duel_to_end", "async def resolve_pve_duel_to_end" in _de)
_rte = _de.split("async def resolve_pve_duel_to_end")[1].split(chr(10) + "async def ")[0]
check("6/⚠️ só PvE — o PvP mantém uma-ronda-por-chamada",
      "_is_pve(duel)" in _rte and "check_and_handle_timeout" in _rte,
      "resolver um PvP inteiro roubava as rondas do outro humano")
check("6/tem tecto (nunca cicla)", "budget" in _rte and "range(budget)" in _rte)
# ⚠️ O DEFEITO QUE O ENSAIO CONTRA A BASE REAL APANHOU (2026-09-04).
# A 1ª versão do laço voltava a chamar `check_and_handle_timeout` e parava,
# porque o `_resolve_round` acabara de pôr um `expires_at` NOVO no FUTURO —
# resolvia UMA ronda, exactamente como o código antigo. Contra as 27 linhas
# verdadeiras, 18 saíram ainda presas (`waiting_actions(r1) -> (r2)`). Um mock
# teria passado. A correcção empurra o prazo para o passado a cada ronda, e é
# ISSO que este assert tranca — sem ele, a regressão volta silenciosa.
check("6/⚠️ empurra o prazo p/ o passado a cada ronda (senão resolve 1 só)",
      "duel.expires_at = past" in _rte,
      "18 de 27 ficaram presos na 1ª versão por causa disto")
# A luta VIVA continua intocada: o primeiro timeout é o que decide se é órfão.
check("6/uma luta DENTRO do prazo não é tocada",
      "return False" in _rte.split("changed = True")[0],
      "o 1º check_and_handle_timeout é o portão: False = ainda no prazo")

# 6.6 — O guard destranca TUDO antes de recusar (era `.limit(1)`).
_ws = _read("core/webserver.py")
check("6/existe unlock_stuck_duels_for_player", "async def unlock_stuck_duels_for_player" in _de)
check("6/o guard do chefe destranca antes de decidir",
      "unlock_stuck_duels_for_player(session, user_id)" in _ws)

# 6.7 ⚠️ A mensagem deixou de MENTIR.
# Dizia "aguarde 15s para o timeout" — e o prazo desses duelos tinha passado há
# 103 dias: esperar 15s nunca resolveu nada. Depois do destrancamento, o único
# ramo que ainda recusa é o de uma luta VIVA, e é isso que ela tem de dizer.
for _lg in LANGS:
    _msg = str(MINI[_lg]["dungeon_duel_already_active"])
    check(f"6/{_lg}: a mensagem não promete o timeout de 15s",
          "15s" not in _msg and "15 s" not in _msg, _msg)
_m = _TU.search(str(MINI["pt"]["dungeon_duel_already_active"]))
check("6/pt: PT-BR (sem tuteamento)", not _m, _m.group(0) if _m else "")

# 6.8 — As descrições deixaram de ser cortadas sem saída (report [jogador]).
_tabs = _read("miniapp/components/tabs.js")
for _who in ("recipe.description", "dungeon.description", "tech.description"):
    _i = _tabs.find("{" + _who + "}")
    check(f"6/{_who} existe na UI", _i > 0)
    _ctx = _tabs[max(0, _i - 330):_i]
    check(f"6/⚠️ {_who} já não tem nowrap",
          'whiteSpace:"nowrap"' not in _ctx,
          "cortada sem saída = beco (Lei §1): vivia no TÍTULO, expandir não revelava")



# ═══════════════════════════════════════════════════════════════════════════
# 7. ⚔️ O GOLPE PADRÃO + ⏳ O ENCONTRO RÁPIDO (reports do [jogador], 10/09)
#
# 7.1 — O GOLPE PADRÃO. Quando a rodada esgota (15 s), o motor preenchia o lado
# que faltou com `technique_id: 0` — o SOCO — sempre, para toda a gente, nas dez
# famílias de duelo. Quem fechava o mini-app lutava a soco e nada no Caminho
# andava. Agora sai a arte que o jogador escolheu, com TRÊS travas.
#
# ⚠️ A fatia é a FUNÇÃO, nunca uma janela de caracteres: duas guardas da casa
# ficaram vermelhas a 12/09 só por o código ter ganho comentários.
_de2 = _read("core/duel_engine.py")


def _fn(src: str, needle: str) -> str:
    i = src.index(needle)
    j = src.find("\nasync def ", i + len(needle))
    k = src.find("\ndef ", i + len(needle))
    ends = [x for x in (j, k) if x > 0]
    return src[i:min(ends)] if ends else src[i:]


def _code(src: str) -> str:
    """O mesmo texto SEM os comentários `#`.

    ⚠️ Existe porque a bateria de sabotagem apanhou TRÊS guardas deste lote a
    afirmar sobre a PROSA: a mais grave procurava `is_forbidden` e encontrava-o
    no comentário que explica porque a arte proibida não dispara sozinha —
    sabotei a trava inteira e a guarda ficou VERDE. É a mesma família do assert
    que proibia um glifo e o achava no texto que explicava porque o glifo morreu.
    """
    return "\n".join(l.split("#")[0] if l.lstrip().startswith("#") else l
                     for l in src.split("\n"))


_HAS_RDS = "async def resolve_default_strike(" in _de2
check("7/a função `resolve_default_strike` existe",
      _HAS_RDS,
      "sem ela, TUDO o que vem a seguir afirma sobre o vazio — e uma guarda "
      "que REBENTA diz que o teste está errado, não o código")
_rds = _fn(_de2, "async def resolve_default_strike(") if _HAS_RDS else ""
check("7/a fatia é a FUNÇÃO", len(_rds) > 1200, f"{len(_rds)} chars")

# ⚠️ TRAVA 1 — a mais séria das três. O Caminho Proibido cobra karma e ANOS DE
# VIDA por uso; um automático não pode cobrar um preço que o jogador não
# escolheu naquele instante. Se esta ficar vermelha, o automático passou a poder
# gastar a vida de quem está a dormir.
_rds_code = _code(_rds)
check("7/o filtro de comentários tirou alguma coisa da fatia",
      len(_rds_code) < len(_rds),
      "sem isto as guardas abaixo afirmam sobre a prosa")
# ⚠️ O RAMO, não a palavra: `if is_forbidden(tech_id):` seguido do retorno que
# cai no básico. A 1ª versão procurava só os dois nomes e ficou VERDE com a
# trava inteira apagada.
check("7/⚠️ arte PROIBIDA nunca dispara sozinha",
      "if is_forbidden(tech_id):" in _rds_code
      and 'fell_back="forbidden_never_auto"' in _rds_code,
      "TEC-5 cobra karma e ANOS DE VIDA por uso — um automático não pode "
      "cobrar um preço que o jogador não escolheu naquele instante")

# ⚠️ TRAVA 2 — sem qi cai no básico, NUNCA recusa a rodada. Uma rodada recusada
# aqui deixa o duelo aberto para sempre: foi exatamente isso que prendeu 13
# jogadores fora do combate (o mais antigo há 103 dias).
check("7/⚠️ sem qi cai no básico — nunca recusa a rodada",
      'fell_back="not_enough_combat_qi"' in _rds_code
      and "combat_qi_a" in _rds_code,
      "recusar a rodada deixa o duelo aberto para sempre (os 13 trancados)")

# TRAVA 3 — a arte tem de estar equipada NESTA luta (lê o retrato, como o
# `submit_action` lê).
check("7/a arte tem de estar equipada nesta luta",
      "_find_technique(" in _rds_code
      and 'fell_back="not_equipped"' in _rds_code)

# ⚠️ A OFF-IDENTITY: com a flag OFF nem sequer vai à base de dados. Se isto
# ficar vermelho, os 57 do `main` passam a pagar uma query por cada rodada que
# esgota, para ler uma coluna que está sempre vazia.
_gate_i = _rds_code.find("if not golpe_padrao_on():")
_sel_i = _rds_code.find("select(Player)")
# ⚠️ `-1 < n` é sempre verdade: sem o `_gate_i > 0` esta guarda fica VERDE
# exatamente quando o gate desaparece, que é o caso que ela existe para apanhar.
check("7/⚠️ flag OFF ⇒ ZERO queries (o gate vem ANTES do select)",
      _gate_i > 0 and _sel_i > _gate_i,
      "o `main` não pode pagar uma query por rodada para ler um NULL")
check("7/a flag `golpe_padrao` tem gate próprio e fail-safe",
      "def golpe_padrao_on(" in _de2 and "return False" in _fn(_de2, "def golpe_padrao_on("))

# O preenchimento usa mesmo a função (e não ficou um `technique_id: 0` cravado)
_cht = _fn(_de2, "async def check_and_handle_timeout(")
_cht_code = _code(_cht)
check("7/o preenchimento chama `resolve_default_strike` nos DOIS lados",
      _cht_code.count("await resolve_default_strike(session, duel,") == 2,
      "um lado esquecido = metade da correção, que é pior que nenhuma")
check("7/⚠️ e já não há um golpe básico cravado no preenchimento",
      '"technique_id": 0, "qi_cost": 0, "auto": True,' not in _cht_code,
      "dois donos da mesma decisão divergem sempre (Lei F-7)")

# ⚠️ O AUTOMÁTICO NÃO PODE SER MUDO. Se ele cair no básico por uma das travas, o
# jogador tem de poder ver porquê — senão é a mesma ferida do "sua fila expirou"
# que não dizia nada.
check("7/⚠️ a recusa fica ESCRITA no registro do duelo",
      '_entry["default_strike"] = _said' in _cht_code
      and '"fell_back"' in _cht_code,
      "um automático silencioso que não faz o que mandaram é um beco (Lei §1)")
# ...e a key só nasce quando há o que dizer (OFF-identity do action_log)
check("7/⚠️ e a key do log só nasce quando há o que contar",
      "if _said:" in _cht_code,
      "key sempre-presente = OFF-identity quebrada (lição MV-7)")

# A coluna: nasce NULL, e a migration fala do assunto.
_mdl = _read("database/models.py")
check("7/a coluna `default_technique_id` existe e nasce NULL",
      "default_technique_id" in _mdl and "nullable=True" in
      _mdl.split("default_technique_id")[1][:200])
# ⚠️ A guarda lê o SQL, NUNCA a prosa. A 1ª versão ficou vermelha porque o
# próprio comentário explicava *"nunca `DROP`"* — a mesma família do assert que
# proibia um glifo e o encontrava no texto que explicava porque o glifo morreu.
_mig141 = _read("migrations/141_golpe_padrao.sql")
_sql141 = chr(10).join(l for l in _mig141.split(chr(10))
                       if not l.lstrip().startswith("--")).upper()
check("7/⚠️ a migration é backwards compatible",
      "ADD COLUMN IF NOT EXISTS" in _sql141 and "DEFAULT NULL" in _sql141
      and "DROP" not in _sql141,
      "jogadores reais: nunca DROP, sempre DEFAULT neutro")
# e a anti-guarda: se o filtro de comentários deixasse de filtrar, a de cima
# estaria a afirmar sobre um ficheiro de prosa.
check("7/o filtro de comentários do SQL tirou alguma coisa",
      len(_sql141) < len(_mig141) * 0.5,
      f"{len(_mig141)} -> {len(_sql141)}")

# 7.2 — O ENCONTRO RÁPIDO. A arena é 100% NPC há seis semanas (0 duelos PvP em
# 30 dias; 16.516 `arena_npc_fallback` all-time). Os 180 s de fila eram uma tela
# de espera por uma pessoa que não estava lá.
_ae = _read("core/arena_engine.py")
check("7/a flag `arena_encontro_rapido` tem gate próprio e fail-safe",
      "def encontro_rapido_on(" in _ae
      and "return False" in _fn(_ae, "def encontro_rapido_on("))
_win = _code(_fn(_ae, "async def _queue_window_seconds("))
_g2 = _win.find("if not encontro_rapido_on():")
_o2 = _win.find("_others_waiting(")
check("7/⚠️ flag OFF ⇒ os 180 s de hoje, e SEM a query da contagem",
      _g2 > 0 and _o2 > _g2,
      "o `main` não pode pagar uma contagem por cada entrada na fila")
check("7/⚠️ com OUTRA alma na fila, a espera é a de sempre",
      "if others > 0:" in _win and "ARENA_QUEUE_TIMEOUT_SECONDS" in _win,
      "encurtar com gente na fila mataria o PvP para consertar a espera por ele")
# ⚠️ QUARTA vez neste lote que uma guarda lê a PROSA em vez do código: a
# constante aparece duas vezes no ficheiro — a definição e o comentário que a
# explica ("30 e nao 0 DE PROPOSITO") — e o `re.search` casava com o comentário
# PRIMEIRO. Baixei o valor a zero e a guarda ficou verde a ler o texto.
_ae_code = _code(_ae)
_solo = re.search(r"^ARENA_QUEUE_SOLO_TIMEOUT_SECONDS = (\d+)", _ae_code, re.M)
check("7/a janela curta existe e NÃO é zero",
      _solo is not None and int(_solo.group(1)) > 0,
      "a zero, duas pessoas com 10 s de diferença nunca mais se encontrariam — "
      "seria matar o PvP para consertar a espera por ele")

# ⚠️ A MENSAGEM QUE CULPAVA O ELO. Ela dizia "ninguém com ELO compatível foi
# encontrado" e essa NUNCA foi a razão: o NPC existe precisamente para tornar o
# pool irrelevante — o jogador ia SEMPRE lutar. Culpar um sistema por algo que
# não depende dele manda o jogador consertar o que não está partido.
# ⚠️ Isto NÃO está atrás de flag nenhuma: uma mentira é uma mentira nos dois
# ramos, e corrigi-la é correção, não feature.
for _lg in ("pt", "en", "es"):
    _loc = json.loads(_read(f"locales/{_lg}.json"))
    _hint = _loc.get("combat_arena_expired_chat_hint", "")
    check(f"7/⚠️ a mensagem da fila já não culpa o ELO ({_lg})",
          "ELO" not in _hint.upper(),
          "o NPC torna o pool irrelevante — o ELO nunca foi a razão")
    check(f"7/e ela DIZ o que acontece a seguir ({_lg})",
          len(_hint) > 40)
    check(f"7/a linha da fila vazia existe ({_lg})",
          len(_loc.get("combat_arena_queue_solo", "")) > 30)

# ⚠️ AS DUAS FLAGS NASCEM OFF. O `main` lê os defaults — é a lente dos 57.
_db141 = _read("database/db.py")
_feat = _db141.split("DEFAULT_WORLD_FEATURES = {")[1].split("\n}")[0]
for _fl in ("golpe_padrao", "arena_encontro_rapido"):
    check(f"7/⚠️ a flag `{_fl}` nasce OFF",
          re.search(r'"%s":\s*False' % _fl, _feat) is not None,
          "o `main` lê defaults — uma flag ON aqui chega aos 57 sem ninguém pedir")
    for _lg in ("pt", "en", "es"):
        _mi = json.loads(_read(f"miniapp/i18n/{_lg}.json"))
        check(f"7/`feature_{_fl}` auto-documenta-se em {_lg}",
              len(_mi.get(f"feature_{_fl}", "")) > 6
              and len(_mi.get(f"feature_{_fl}_desc", "")) > 400)


# =============================================================================
# §8 — 名 O NOME: o catalogo fala a lingua do jogador, em TODO o lado
# =============================================================================
#
# O lote de 2026-09-14. A contagem que o abriu, e que derrubou a premissa do
# proprio prompt:
#
#   · `catalog_text` ACEITAVA 6 familias e so' `tech` tinha chamadores (5).
#   · o CONTEUDO das 129 tecnicas estava COMPLETO x3 desde o TEC-1, e chegava a
#     9 de 41 sitios — 4 deles uma SEGUNDA implementacao a' mao.
#   · resultado medido: o chat imprimia "Thunder Step" e o mini-app
#     "Passo do Trovao". A Lei 0 chama a isto PIOR do que a ausencia.
#
# ⚠️ E as duas familias mais vistas do jogo entraram pela mao do OWNER, que
# mandou uma captura do ecra do Chefe em espanhol a dizer "VOID BEAST" e
# "Attack World Boss — toca para reclamar la recompensa". A minha contagem
# falhava-as. A guarda existe para que a proxima nao dependa de ele ver.
print("\n=== 8. 名 o nome: o catalogo na lingua do jogador ===")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import importlib as _il
_aud = _il.import_module("_audit_nomes_crus")
_il.reload(_aud)
_scan = _aud.scan()

# 8.1 — A CATRACA. O numero de leituras cruas SO' PODE DESCER.
#       Tecto 0, medido 2026-09-14 (era 106 quando o lote abriu).
_NOMES_CRUS_TECTO = 0
check("8/⚠️ CATRACA: zero leituras de nome cru fora da lista declarada",
      _scan["total"] <= _NOMES_CRUS_TECTO,
      f"{_scan['total']} > {_NOMES_CRUS_TECTO} — "
      f"{dict(list(_scan['per_file'].items())[:4])}")

# 8.2 — a lista DECLARADA tem de ter motivo escrito, e nao pode inchar em
#       silencio. 8 sitios a 2026-09-14 (log de combate x3, besta x3, karma,
#       comparacao do chefe).
# ⚠️ DOIS LADOS, e o de baixo e' a ANTI-GUARDA. A catraca de cima e' "<= 0":
# se o filtro de comentarios passar a apagar CODIGO, o scan ve' zero em todo o
# lado e ela fica verde PARA SEMPRE. A lista declarada e' a canaria — sao 8
# sitios que SABEMOS existir, e se o varredor deixar de os ver e' porque
# cegou. (Achado pela sabotagem "o filtro passa a APAGAR CODIGO", que ficou
# verde na 1a passagem.)
# ⚠️ 2026-09-15 — o tecto desceu de 8 para 5, e a descida e' o assunto: as TRES
# declaracoes da familia BESTA sairam porque a familia deixou de ser crua. Uma
# lista declarada que so' sobe e' uma lista de desculpas.
# ⚠️ 2026-09-29 (冶 3.1) — 5 -> 6, e a subida tem motivo: o varredor deixou de
# tirar da conta a LINHA inteira que mencionasse `pill_name` (o defeito do
# `custom_name` na forma geral) e passou a ver 15 leituras cruas escondidas.
# 14 corrigidas; a 15.a e' o anuncio do Mercador NPC em `handlers/events.py`,
# gravado na BASE e visto por todas as linguas — ninguem o le, e traduzi-lo
# cozia uma lingua num dado partilhado. Fica o canonico, declarado.
check("8/a lista declarada nao incha em silencio",
      len(_scan["declared"]) <= 6,
      f"{len(_scan['declared'])} declarados — cada um precisa de motivo escrito")
check("8/⚠️ ANTI-GUARDA: o varredor CONTINUA A VER (nao cegou)",
      len(_scan["declared"]) >= 6,
      f"so' {len(_scan['declared'])} dos 6 sitios declarados foram vistos — "
      "um varredor que nao ve' nada tem a catraca verde por engano")

# 8.3 — O DONO E' UNICO. Nenhum ficheiro pode voltar a montar a chave a' mao:
#       era assim que `sect_library_engine` e `legacy_cave_engine` divergiam.
_mao = []
for _dir in ("core", "handlers"):
    for _f in sorted(os.listdir(os.path.join(ROOT, _dir))):
        if not _f.endswith(".py"):
            continue
        _src = _read(f"{_dir}/{_f}")
        _clean = "\n".join(_aud._strip_comments_py(_src))
        if re.search(r't_optional\(\s*\w+\s*,\s*f"(?:tech|art|pill|herb|ore|q|boss)_\{', _clean):
            _mao.append(f"{_dir}/{_f}")
check("8/⚠️ UM DONO: ninguem monta a chave `<fam>_<id>_name` a' mao",
      not _mao,
      f"chave montada a' mao em {_mao} — use catalog_name/catalog_desc")

# 8.4 — a lingua esta' LIGADA em toda a chamada ao resolvedor. Uma chamada com
#       `lang` nao ligado compila e so' rebenta na mao do jogador (Lei §1).
_scope = subprocess.run(
    [sys.executable, os.path.join(ROOT, "scripts", "_audit_nomes_lang_scope.py")],
    capture_output=True, cwd=ROOT,
    env={**os.environ, "PYTHONIOENCODING": "utf-8"})
check("8/toda chamada ao resolvedor tem a lingua ligada",
      _scope.returncode == 0,
      _scope.stdout.decode("utf-8", "replace")[-300:])

# 8.5 — PARIDADE DE CORRECCAO, nao de estilo. `t_optional` cai no locale por
#       omissao (pt) ANTES de cair no valor cru ⇒ uma chave so' em `pt.json`
#       faz um jogador EN ler portugues, que e' pior do que o ingles cru.
_loc8 = {_lg: json.loads(_read(f"locales/{_lg}.json")) for _lg in ("pt", "en", "es")}
_cat_keys = {_lg: {k for k in _loc8[_lg]
                   if re.match(r"^(tech|art|pill|herb|ore|boss|q|cauldron)_.+_(name|desc)$", k)}
             for _lg in ("pt", "en", "es")}
check("8/⚠️ as 3 linguas tem EXACTAMENTE as mesmas chaves de catalogo",
      _cat_keys["pt"] == _cat_keys["en"] == _cat_keys["es"],
      f"pt={len(_cat_keys['pt'])} en={len(_cat_keys['en'])} es={len(_cat_keys['es'])}")

# 8.6 — COBERTURA POR FAMILIA INTEIRA. Uma familia meia-traduzida poe duas
#       linguas no MESMO ecra — e' o "parece partido" da Lei 0. Ou todas as
#       linhas da familia tem chave, ou a familia fica de fora inteira.
sys.path.insert(0, ROOT)
from database.seeds.artifacts_seeds import ARTIFACTS as _ART8, ORES as _ORE8
from database.seeds.alchemy_seeds import HERBS as _HERB8, PILLS as _PILL8
from database.seeds.combat_seeds import TECHNIQUES as _TECH8
from database.seeds.beasts_seeds import BEASTS as _BEAST8
from database.seeds.boss_seeds import WORLD_BOSS_POOL as _BOSS8
from core.i18n import catalog_slug as _slug8

for _fam, _rows, _keyf in (
    ("art", _ART8, lambda r: r["id"]),
    ("ore", _ORE8, lambda r: r["id"]),
    ("herb", _HERB8, lambda r: r["id"]),
    ("pill", _PILL8, lambda r: r["id"]),
    ("tech", _TECH8, lambda r: r["id"]),
    # 獸 2026-09-15 — a besta entrou. Ficou de fora a 14/09 por um bloqueio
    # ESTRUTURAL e nao por esquecimento: a captura gravava `custom_name` com o
    # nome do catalogo, e como todas as telas faziam `custom_name or cat.name`,
    # o `or` NUNCA caia no catalogo — uma chave `beast_<id>_name` seria escrita
    # e nunca lida.
    ("beast", _BEAST8, lambda r: r["id"]),
    ("boss", _BOSS8, lambda r: _slug8(r["name"])),
):
    for _field in ("name", "desc"):
        _falta = [_keyf(r) for r in _rows
                  if f"{_fam}_{_keyf(r)}_{_field}" not in _loc8["pt"]]
        check(f"8/a familia `{_fam}` esta INTEIRA em _{_field} ({len(_rows)} linhas)",
              not _falta,
              f"{len(_falta)} sem chave (ex: {_falta[:5]})")

# 8.7 — o chefe indexa-se pelo SLUG, nao pelo id: `world_bosses.id` e'
#       autoincremento por APARICAO, e uma chave por aparicao nunca casaria.
_bm8 = _read("database/models.py")
check("8/⚠️ o id do chefe continua a ser por aparicao (justifica o slug)",
      re.search(r"class WorldBoss\(Base\):.*?id:.*?autoincrement=True",
                _bm8, re.S) is not None,
      "se o chefe ganhar id de catalogo, o slug deixa de ser preciso")
check("8/o slug do chefe e' estavel e colapsa traco, espaco e apostrofo",
      _slug8("Heaven-Devouring Serpent") == "heaven_devouring_serpent"
      and _slug8("Void Beast") == "void_beast")

# 8.8 — a captura do owner, ponta a ponta: as duas linhas que ele fotografou
#       tem de sair em PT e ES, e continuar identicas em EN.
from core.i18n import catalog_name as _cn8


class _Row8:
    def __init__(self, i, n):
        self.id, self.name, self.description = i, n, ""


for _kind8, _row8, _raw8 in (("boss", _Row8(999, "Void Beast"), "Void Beast"),
                             ("q", _Row8(6, "Attack World Boss"), "Attack World Boss")):
    check(f"8/⚠️ captura do owner: `{_raw8}` sai traduzido em pt",
          _cn8("pt", _kind8, _row8) != _raw8 and len(_cn8("pt", _kind8, _row8)) > 4)
    check(f"8/⚠️ captura do owner: `{_raw8}` sai traduzido em es",
          _cn8("es", _kind8, _row8) != _raw8 and len(_cn8("es", _kind8, _row8)) > 4)
    check(f"8/`{_raw8}` continua IDENTICO em en (os 112 nao sentem nada)",
          _cn8("en", _kind8, _row8) == _raw8)

# 8.8b — a DESCRICAO tem de ser uma descricao, nao o nome outra vez.
#        Sem isto, trocar a chave `_desc` por `_name` no resolvedor passava
#        despercebido: as duas telas mostrariam o mesmo texto duas vezes.
from core.i18n import catalog_desc as _cd8

_row8b = _Row8(8, "Heaven's Edge")
for _lg8 in ("pt", "en", "es"):
    _n8, _d8 = _cn8(_lg8, "art", _row8b), _cd8(_lg8, "art", _row8b)
    check(f"8/a descricao NAO e' o nome outra vez ({_lg8})",
          _d8 != _n8 and len(_d8) > len(_n8),
          f"name={_n8!r} desc={_d8!r}")

# 8.10 — 🔴 A ARTE TEM DE SOBREVIVER A' TRADUCAO DO NOME.
#
#   O cliente monta o URL da peca a partir do NOME: `art-` + slug(nome). Enquanto
#   o payload mandava ingles isso bastava. No instante em que o nome passa a ir
#   TRADUZIDO, o slug muda e a peca deixa de ser encontrada — sem erro nenhum: a
#   carta cai no verso, que e' um estado legitimo, e ninguem da' por isso.
#
#   MEDIDO a 2026-09-14: **229 pecas por lingua** invisiveis em pt e es
#   (128 tecnicas + 51 artefactos + 41 pilulas + 9 chefes), zero em en. E as 128
#   tecnicas ja' estavam assim EM PRODUCAO desde 2026-09-08, o dia em que as
#   artes passaram a sair traduzidas no mini-app.
#
#   A regra: o nome e' para LER, o `art_key` e' para ENCONTRAR.
_tabs8 = _read("miniapp/components/tabs.js")
_ui8 = _read("miniapp/components/ui.js")

_chamadas8 = [m.group(0) for m in re.finditer(r"pieceArt\([^;\n]*?\)", _tabs8)]
# a citacao dentro de um comentario (`pieceArt("artifact", ...)`) nao e' chamada
_chamadas8 = [c for c in _chamadas8 if "..." not in c]
_sem_chave8 = [c for c in _chamadas8 if "art_key" not in c and "artKey" not in c]
check("8/⚠️ toda chamada a `pieceArt` leva a CHAVE, nao so' o nome",
      not _sem_chave8,
      f"{len(_sem_chave8)} de {len(_chamadas8)} sem chave: {_sem_chave8[:2]}")

_icons8 = re.findall(r"<PieceIcon\b[^>]*?/>", _tabs8, re.S)
_sem_icon8 = [i for i in _icons8 if "artKey" not in i]
check("8/⚠️ todo `<PieceIcon>` leva `artKey`",
      not _sem_icon8,
      f"{len(_sem_icon8)} de {len(_icons8)} sem artKey")

check("8/o `pieceArt` aceita a chave e prefere-a ao nome",
      re.search(r"function pieceArt\(kind, name, artKey\)", _ui8) is not None
      and "const key = artKey || name;" in _ui8,
      "a assinatura do resolvedor de arte mudou sem a guarda saber")

# ⚠️ O mapa de prefixos do CLIENTE e o do PIPELINE sao as duas metades da mesma
# ligacao. Foi por uma ter ficado para tras que 51 pecas pagas passaram meses
# invisiveis (`ARTE_PROVENIENCIA §1.4`), e voltou a acontecer com `boss` a
# 2026-09-14: as 9 copiaram-se para `assets/` e o indice disse "ja' em dia".
_gen8 = _read("scripts/gen_art.py")
for _fam8 in ("technique", "pill", "beast", "artifact", "boss"):
    check(f"8/a familia `{_fam8}` esta nas DUAS metades (cliente + pipeline)",
          re.search(_fam8 + r':\s*"', _ui8) is not None
          and re.search(r'"' + _fam8 + r'":\s*"', _gen8) is not None,
          "arte paga fica invisivel quando so' uma das metades a conhece")

# E a prova de DADOS, nao de forma: o slug canonico de cada chefe existe mesmo
# no indice do cliente.
for _b8 in _BOSS8:
    _slugart8 = "boss-" + re.sub(r"^-+|-+$", "",
                                 re.sub(r"[^a-z0-9]+", "-", _b8["name"].lower()))
    check(f"8/o chefe `{_b8['name']}` tem a peca no indice",
          '"' + _slugart8 + '"' in _ui8,
          "arte no disco fora do indice = carta no verso, em silencio")

# ── 8.11 — 獸 A FAMILIA BESTA, e porque e' que ela precisa de guarda PROPRIA ──
#
# 🔴 A catraca geral (8.1) NAO VE ESTA FAMILIA, e isso foi PROVADO, nao suposto.
# Duas cegueiras independentes, as duas do tipo "verde sobre o conjunto vazio":
#
#   (a) `custom_name` estava na lista NOT_CATALOG do varredor, e a forma de toda
#       a familia era `b.custom_name or (c.name if c else "???")` — a linha
#       INTEIRA saia da conta. Corrigido neste lote (a palavra saiu da lista).
#   (b) a variavel do catalogo em `handlers/beasts.py` chama-se `c` e nasce de
#       `catalog_map.get(...)`, tres saltos depois de `get_beast_catalog()` e
#       sem UMA mencao a `BeastCatalog`. O dataflow-lite do varredor nao a
#       alcanca. Tentou-se um ponto fixo generico e ele trouxe **75 leituras**,
#       a maioria ruido (`path.name`, `ach.name`, `law.name`): trocar um ponto
#       cego por um nevoeiro nao e' medir melhor. Fica a medicao PRECISA, aqui.
#
# Esta seccao afirma sobre o SITIO (os dois ficheiros da familia) e nao sobre o
# ficheiro de varredura — a licao de 09/09 aplicada de proposito.
print("\n=== 8.11 獸 a familia besta ===")

_BE11 = _read("core/beast_engine.py")
_HB11 = _read("handlers/beasts.py")
_WS11 = _read("core/webserver.py")
# 🐾 3.3 (2026-10-01) — a linha de `beasts/list.owned[]` saiu do endpoint para o
# seu dono (`core/bestas.serializar`). A familia ganhou um ficheiro, e a guarda
# SEGUE a indireccao: o que ela lia no endpoint passa a ler no dono.
_BS11 = _read("core/bestas.py")
_be_clean = "\n".join(_aud._strip_comments_py(_BE11))
_hb_clean = "\n".join(_aud._strip_comments_py(_HB11))
_bs_clean = "\n".join(_aud._strip_comments_py(_BS11))

# 8.11a — UM DONO, definido uma unica vez em todo o produto.
_donos11 = len(re.findall(r"^def beast_display_name\(", _BE11, re.M))
check("8.11/UM DONO: `beast_display_name` definido exactamente uma vez",
      _donos11 == 1, f"{_donos11} definicoes")

# 8.11b — ANTI-GUARDA: o localizador VE as chamadas. Sem isto, tudo o que vem a
#         seguir compara conjuntos vazios e fica verde sem ter olhado.
_chamadas11 = len(re.findall(r"beast_display_name\(", _be_clean + _hb_clean + _WS11))
check("8.11/⚠️ ANTI-GUARDA: o localizador ve as chamadas ao dono (%d)"
      % _chamadas11,
      _chamadas11 >= 12,
      "menos de 12 chamadas: ou a familia voltou ao cru, ou o localizador cegou")

# ── 8.11b2 — 🔴 A VARREDURA PRECISA, e ela nasceu de uma sabotagem VERDE ────
#
# A 1a versao desta seccao contava chamadas ao dono (`>= 12`) e dava-se por
# satisfeita. A bateria derrubou-a no primeiro empurrao: reverter a linha do
# CATALOGO para `c.name` deixa 12+ chamadas de pe', e a suite ficava **verde**
# com uma tela do chat outra vez em ingles. Contar chamadas mede o que EXISTE;
# o que e' preciso medir e' o que FALTA.
#
# Entao varre-se o SITIO: nos dois ficheiros da familia, nenhuma variavel de
# catalogo de besta pode ter o seu `.name`/`.description` lido sem resolvedor.
# ⚠️ `exp.name` (ExpeditionCatalog) nao entra aqui de proposito — e' outra
# familia, ainda crua, e esta' contada e declarada em 8.11g.
_VAR11 = re.compile(r"\b(?:c|cat|catalog|_b_cat|bc|cats)\.(?:name|description)\b")
_RES11 = re.compile(r"beast_display_name|beast_art_key|catalog_desc|catalog_name|catalog_text")
_crus11 = []
for _f11, _c11 in (("core/beast_engine.py", _be_clean),
                   ("handlers/beasts.py", _hb_clean),
                   ("core/bestas.py", _bs_clean)):
    for _n11, _l11 in enumerate(_c11.split("\n"), 1):
        if _VAR11.search(_l11) and not _RES11.search(_l11):
            _crus11.append(f"{_f11}:{_n11}: {_l11.strip()[:70]}")
check("8.11/⚠️ ZERO leituras cruas do catalogo nos ficheiros DA FAMILIA",
      not _crus11,
      f"{len(_crus11)} leitura(s) sem resolvedor: {_crus11[:3]}")
# e a anti-guarda desta varredura: ela tem de continuar a VER linhas nestes
# ficheiros, senao um rename de ficheiro poe-na verde sobre duas strings vazias
check("8.11/⚠️ ANTI-GUARDA: a varredura ainda le os dois ficheiros",
      len(_be_clean) > 5000 and len(_hb_clean) > 5000,
      "um dos ficheiros da familia veio vazio — a varredura acima nao mediu nada")

# 8.11c — a forma ANTIGA nao volta. `custom_name or <catalogo>` era o bloqueio.
_forma_velha = re.findall(r"custom_name\s+or\s", _be_clean + _hb_clean + _WS11)
check("8.11/a forma `custom_name or ...` desapareceu dos tres ficheiros",
      not _forma_velha,
      f"{len(_forma_velha)} sobreviventes — o `or` nunca cai no catalogo, e a "
      "traducao da familia fica escrita e nunca lida")

# 8.11d — 🔴 NINGUEM VOLTA A GRAVAR `custom_name`. Era a raiz: gravado na
#         captura, congelava o nome na lingua em que a besta foi apanhada.
_escritas11 = re.findall(r"custom_name\s*=", _be_clean)
check("8.11/a captura NAO grava `custom_name` (NULL = 'ainda nao lhe dei nome')",
      not _escritas11,
      f"{len(_escritas11)} escritas — cada uma tranca uma besta nova em ingles")

# 8.11e — A SEMANTICA, provada com dados e nao com forma. As 1170 linhas de
#         producao tem `custom_name == catalog.name`; se o resolvedor as tratasse
#         como "nome escolhido", a correccao nao chegava a UM jogador vivo.
from core.beast_engine import beast_display_name as _bdn11


class _B11:
    def __init__(self, cn):
        self.custom_name = cn


class _C11:
    def __init__(self, i, n):
        self.id, self.name, self.description = i, n, ""


_cat11 = _C11(1, "Thunder Ox")
for _lg11, _esp11 in (("pt", "Boi do Trovão"), ("es", "Buey del Trueno")):
    check(f"8.11/⚠️ as 1170 linhas de producao traduzem-se ({_lg11})",
          _bdn11(_lg11, _B11("Thunder Ox"), _cat11) == _esp11,
          f"`custom_name` igual ao catalogo tem de cair no catalogo — leu "
          f"{_bdn11(_lg11, _B11('Thunder Ox'), _cat11)!r}")
check("8.11/uma besta com nome NULL tambem se traduz",
      _bdn11("pt", _B11(None), _cat11) == "Boi do Trovão")
check("8.11/⚠️ um nome ESCOLHIDO pelo jogador NUNCA e' traduzido",
      _bdn11("pt", _B11("Trovãozinho"), _cat11) == "Trovãozinho",
      "quem batizou a besta perde o nome — e isso e' apagar dados do jogador")
check("8.11/em `en` o texto e' o do catalogo (os 112 nao sentem nada)",
      _bdn11("en", _B11("Thunder Ox"), _cat11) == "Thunder Ox")

# 8.11f — 🔴 A ARTE SOBREVIVE A TRADUCAO. As 15 pecas existem em disco e sao
#         encontradas pelo NOME; traduzir sem `art_key` apaga-as as 15 em pt e
#         es, sem erro nenhum. E' a avaria de 14/09 (229 pecas) a 3a tentativa.
from core.beast_engine import beast_art_key as _bak11
check("8.11/⚠️ a chave da arte e' o nome CANONICO, nunca o traduzido",
      _bak11(_cat11) == "Thunder Ox")
_ui11 = _read("miniapp/components/ui.js")
for _b11 in _BEAST8:
    _slug11 = "beast-" + re.sub(r"^-+|-+$", "",
                                re.sub(r"[^a-z0-9]+", "-", _b11["name"].lower()))
    check(f"8.11/a besta `{_b11['name']}` tem a peca no indice do cliente",
          '"' + _slug11 + '"' in _ui11,
          "arte no disco fora do indice = carta no verso, em silencio")
# e o payload leva a chave ao lado do nome, nos tres sitios que o mandam
check("8.11/⚠️ o payload das bestas leva `art_key` ao lado do nome",
      _WS11.count('"art_key": beast_art_key(') >= 1
      and _BS11.count('"art_key": beast_art_key(cat)') == 1
      and "_bestas.serializar(b, catalog_map.get(b.catalog_id), _lang_b, food_mult)" in _WS11
      and _WS11.count('"beast_art_key": _bak_exp(') >= 1,
      "sem a chave o cliente monta `beast-boi-do-trovao` e nao acha nada")

# 8.11g — 旅 A TRANSICAO DA FAMILIA EXPEDICAO (fechada a 2026-09-15).
#
# ⚠️ Esta guarda nasceu a 15/09 a vigiar a familia enquanto PENDENTE, e a
# mensagem dela prometia *"se cair a zero sem entrar no `_CATALOG_KINDS`, foi
# apagada e nao feita"* — mas a CONDICAO era so' `>= 1`. A prosa descrevia uma
# verificacao que o codigo nunca fazia: fechar a familia punha-a VERMELHA, e o
# unico jeito de a calar seria apaga-la. Agora afirma o que dizia: a familia
# esta' num dos DOIS estados legitimos — crua e declarada, ou FEITA e ligada.
# Nunca a zero e desligada, que e' o estado "foi apagada".
_exped11 = len(re.findall(r"\bexp\.name\b|\bexp\.description\b|\be\.name\b", _hb_clean)) \
    + len(re.findall(r'"name": e\.name', _WS11))
_I11 = _read("core/i18n.py")
_exped_feita11 = ('"exped"' in _I11
                  and re.search(r'_KEYED_BY_SLUG\s*=\s*\{[^}]*"exped"', _I11)
                  and len(re.findall(r"^def expedition_display_name\(",
                                     _read("core/beast_engine.py"), re.M)) == 1)
check("8.11/a familia EXPEDICAO: crua e DECLARADA, ou FEITA e ligada",
      _exped11 >= 1 or bool(_exped_feita11),
      f"cruas={_exped11} feita={bool(_exped_feita11)} — zero e desligada = apagada")
check("8.11/⚠️ e se esta' FEITA, o §8.12 e' que a mede por inteiro",
      _exped11 >= 1 or bool(_exped_feita11),
      "a medicao exaustiva dos 10 sitios vive no §8.12")

# 8.9 — pt.json e' BRASILEIRO (o owner fica bravo, com razao, quando se viola)
_eu_pt8 = []
for _k8, _v8 in _loc8["pt"].items():
    if not re.match(r"^(art|pill|herb|ore|boss|q)_.+_(name|desc)$", _k8):
        continue
    for _w8 in ("ecrã", "está a ", "telemóvel", "autocarro", "irá ", "a decorrer"):
        if _w8 in _v8:
            _eu_pt8.append((_k8, _w8))
check("8/⚠️ as chaves novas de `pt` sao BRASILEIRO, nao europeu",
      not _eu_pt8, f"marcas EU-PT: {_eu_pt8[:5]}")


# ══ 8.12 — 旅 A FAMILIA EXPEDICAO (2026-09-15) ═══════════════════════════════
#
# 🔴 ESTA FAMILIA E' INVISIVEL AO VARREDOR **POR FORMA**, nao por omissao — e
# isso foi MEDIDO, nao suposto: pos-se `ExpeditionCatalog` no `CATALOG_MODELS`
# do `_audit_nomes_crus.py` e o total ficou **0**. Duas razoes independentes:
#
#   (a) o nome cru nao vem do catalogo. Vem de `PlayerBeast.expedition_type`,
#       uma coluna de TEXTO que guarda o nome — o varredor procura `.name` numa
#       variavel ligada a um MODELO, e aqui nao ha' modelo nenhum na linha.
#   (b) o catalogo renderiza-se em `for e in expeditions`, dois saltos depois de
#       `select(_EC)`. O dataflow-lite nao segue o segundo salto.
#
# Logo: por a familia na tupla foi CERTO (protege quem ligar o modelo
# directamente) e NAO produziu a lista de trabalho. Esta seccao e' essa lista.
#
# ⚠️ A tela imprimia, na MESMA frase: "Boi do Trovao em Herb Expedition".
# Meia frase traduzida e' PIOR do que nenhuma (Lei 0) — parece partido, nao
# parece incompleto.
print("\n=== 8.12 旅 a familia expedicao ===")

_BE12 = _read("core/beast_engine.py")
_HB12 = _read("handlers/beasts.py")
_WS12 = _read("core/webserver.py")
# ⚠️ LINHAS LOGICAS, nao fisicas. A 1a versao desta seccao varria linha a
# linha e acusou a SEGUNDA metade da propria chamada ao dono — o nome do
# resolvedor ficava na linha de cima e a de baixo era so'
# `beast.expedition_type)`. Uma guarda cega a uma chamada partida em duas
# tambem deixa passar uma leitura CRUA partida em duas: o falso positivo e o
# falso negativo sao o mesmo defeito visto dos dois lados.
_NL12 = chr(10)
def _logicas12(src):
    out, buf, depth = [], "", 0
    for ln in src.split(_NL12):
        buf = (buf + " " + ln.strip()) if buf else ln
        depth += ln.count("(") - ln.count(")")
        if depth <= 0:
            out.append(buf)
            buf, depth = "", 0
    if buf:
        out.append(buf)
    return out

_be12 = _NL12.join(_logicas12(_NL12.join(_aud._strip_comments_py(_BE12))))
_hb12 = _NL12.join(_logicas12(_NL12.join(_aud._strip_comments_py(_HB12))))
_ws12 = _NL12.join(_logicas12(_NL12.join(_aud._strip_comments_py(_WS12))))

_d12 = len(re.findall(r"^def expedition_display_name\(", _BE12, re.M))
check("8.12/UM DONO: `expedition_display_name` definido exactamente uma vez",
      _d12 == 1, f"{_d12} definicoes")

# ⚠️ ANTI-GUARDA. Sem isto tudo o que vem a seguir compara conjuntos vazios e
# fica verde sem ter olhado (a licao de 09/09).
_ch12 = len(re.findall(r"_exp_name\(|_exp_name_ws\(|_exp_desc_ws\(|"
                       r"expedition_display_name\(|expedition_display_desc\(",
                       _be12 + _hb12 + _ws12))
check("8.12/⚠️ ANTI-GUARDA: o localizador ve as chamadas ao dono (%d)" % _ch12,
      _ch12 >= 8,
      "menos de 8 chamadas: ou a familia voltou ao cru, ou o localizador cegou")

# 🔴 O QUE FALTA, nao o que existe. As excepcoes legitimas estao NOMEADAS.
_EXCEPT12 = (
    "beast.expedition_type = expedition.name",
    "exp_name = beast.expedition_type",
    "beast.expedition_type = None",
    "_PB.expedition_type",
    '"expedition_type": exped_name',
)
_cru12 = []
for _f12, _src12 in (("core/beast_engine.py", _be12),
                     ("handlers/beasts.py", _hb12),
                     ("core/webserver.py", _ws12)):
    for _i12, _l12 in enumerate(_src12.split("\n"), 1):
        if "expedition_type" not in _l12:
            continue
        if any(_e12 in _l12 for _e12 in _EXCEPT12):
            continue
        if re.search(r"_exp_name\(|_exp_name_ws\(|expedition_display_name\(", _l12):
            continue
        _cru12.append(f"{_f12}:{_i12}: {_l12.strip()[:70]}")
check("8.12/⚠️ nenhuma leitura CRUA de `expedition_type` chega ao ecra",
      not _cru12, f"{len(_cru12)} cruas: {_cru12[:3]}")

_cat12 = []
for _f12, _src12 in (("handlers/beasts.py", _hb12), ("core/webserver.py", _ws12)):
    for _i12, _l12 in enumerate(_src12.split("\n"), 1):
        if re.search(r"\bexp\.(name|description)\b", _l12) and "_exp_" not in _l12:
            _cat12.append(f"{_f12}:{_i12}: {_l12.strip()[:70]}")
check("8.12/⚠️ o CATALOGO da expedicao nao sai cru (`exp.name`/`.description`)",
      not _cat12, f"{_cat12[:3]}")

# 🔴 A TRADUCAO E' DE DISPLAY. A consulta usa o nome como CHAVE: se ela passar a
# ver o traduzido, recolher deixa de achar a linha e o jogador PERDE o espolio.
check("8.12/⚠️ a CONSULTA continua a casar pelo nome CANONICO",
      "ExpeditionCatalog.name == exp_name" in _be12,
      "a consulta mudou — recolher a expedicao deixaria de achar a linha")
check("8.12/⚠️ a GRAVACAO continua a guardar o nome CANONICO",
      "beast.expedition_type = expedition.name" in _be12,
      "gravar o traduzido tranca a besta na lingua de quem a enviou")

_I12 = _read("core/i18n.py")
_i12c = "\n".join(_aud._strip_comments_py(_I12))
check("8.12/`exped` e' uma familia de catalogo", '"exped"' in _i12c)
check("8.12/⚠️ `exped` indexa-se pelo SLUG (o estado guarda o NOME, nao o id)",
      re.search(r"_KEYED_BY_SLUG\s*=\s*\{[^}]*\"exped\"", _i12c) is not None,
      "sem isto a chave pedia um id que `expedition_type` nao tem")

# A FAMILIA INTEIRA, contada contra os DADOS seedados e nao contra o motor.
_seed12 = _read("database/seeds/beasts_seeds.py")
_ns12 = {}
exec(re.search(r"EXPEDITIONS = \[.*?\n\]", _seed12, re.S).group(0), _ns12)
_exps12 = _ns12["EXPEDITIONS"]
check("8.12/⚠️ ANTI-GUARDA: as expedicoes seedadas foram lidas (%d)" % len(_exps12),
      len(_exps12) >= 6, "sem dados nao ha' o que verificar")
_slug12 = lambda t: re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (t or "").lower())).strip("_")
_falta12 = []
for _lg12 in ("pt", "en", "es"):
    _loc12 = json.loads(_read(f"locales/{_lg12}.json"))
    for _e12 in _exps12:
        for _campo12 in ("name", "desc"):
            _k12 = f"exped_{_slug12(_e12['name'])}_{_campo12}"
            if _k12 not in _loc12:
                _falta12.append(f"{_lg12}:{_k12}")
check("8.12/⚠️ a familia INTEIRA tem nome e descricao nas 3 linguas",
      not _falta12, f"{len(_falta12)} em falta: {_falta12[:4]}")

_en12 = json.loads(_read("locales/en.json"))
_div12 = [(_e12["name"], _en12.get(f"exped_{_slug12(_e12['name'])}_name"))
          for _e12 in _exps12
          if _en12.get(f"exped_{_slug12(_e12['name'])}_name") != _e12["name"]]
check("8.12/⚠️ em `en` o nome e' IDENTICO ao canonico (o seed manda)",
      not _div12, f"{_div12[:3]}")


# == 8.13 -- O ALERTA DO TICK DIZ A CAUSA (2026-09-15) =====================
#
# Chegou um `cultivation_tick failure / DBAPIError` de producao e o alerta
# trazia SO' o nome da classe. `DBAPIError` e' o involucro generico do
# SQLAlchemy: a causa (deadlock, timeout, violacao) vive em `e.orig`. Foi
# preciso ir a base a mao para descobrir que era transitorio e ja' tinha
# recuperado -- e a mesma cegueira ja' custara uma investigacao a 21/07.
print("\n=== 8.13 o alerta do tick diz a CAUSA ===")

_SC13 = _read("core/scheduler.py")
_i13 = _SC13.rfind(chr(10), 0, _SC13.find('_orig = getattr(e, "orig", None)')) + 1
_j13 = _SC13.find("for admin_id in ADMIN_USERS", _i13)
check("8.13/ANTI-GUARDA: o bloco do alerta foi localizado", _i13 > 0 and _j13 > _i13)
_blk13 = textwrap.dedent(_SC13[_i13:_j13].rstrip()) if _j13 > _i13 else ""

# Corre-se o bloco REAL do ficheiro com um erro a fingir. Afirmar sobre o
# TEXTO do alerta deixaria passar um `_nl` que e' a string barra-n (foi
# exactamente o que aconteceu ao escreve-lo): compila, parece certo, e o
# admin le' um '\\n' literal em vez de uma linha.
class _Orig13(Exception): pass
class _Err13(Exception): pass
_e13 = _Err13("(wrapper)")
_e13.orig = _Orig13("deadlock detected on relation players" + chr(10) + "DETAIL: xxx")
_ns13 = {"e": _e13, "pid": 42, "batch": 7, "chr": chr, "err_type": type(_e13).__name__}
try:
    exec(_blk13, _ns13)
    _al13 = _ns13.get("alert", "")
except Exception as _ex13:
    _al13 = ""
    check("8.13/o bloco do alerta corre", False, str(_ex13)[:110])
check("8.13/ANTI-GUARDA: o alerta foi construido", bool(_al13))
check("8.13/o alerta nomeia a CAUSA e nao so' o involucro",
      "_Orig13" in _al13, "sem `e.orig` o alerta nao diagnostica nada")
check("8.13/⚠️ quebra de linha REAL, nunca a string barra-n",
      chr(10) in _al13 and (chr(92) + "n") not in _al13,
      "um `_nl` literal faz o admin ler barra-n em vez de uma linha")
check("8.13/so' a 1a linha da causa (o SQL e os parametros nao vao)",
      "DETAIL" not in _al13, "o SQLAlchemy anexa o SQL inteiro a seguir")
check("8.13/⚠️ a causa vai em BLOCO DE CODIGO (o Markdown rebenta com `_`)",
      "```" in _al13,
      "sem isto o send_message falha e o `except: pass` ENGOLE o alerta")


# =============================================================================
# §9 — ⚔️ A PORTA DO GOLPE PADRAO CORRE (report de 2026-09-30)
# =============================================================================
#
# *"@saint, bug: error 500 on selecting default arts for duels, in Loadout
# screen"*. A §7 guardava o MOTOR (`resolve_default_strike`) e NENHUMA guarda
# executava a porta de escrita: ela filtrava `PlayerTechnique.is_active`, uma
# coluna que nao existe (e' `is_active_combat`) — AttributeError ao MONTAR a
# query => 500 para qualquer arte; o golpe basico (0) saltava o ramo e passava.
# O arnes devolvia `ok: true` sem chamar a rota. No Beta: 0 escolhas gravadas
# desde que a flag ligou, com os 38 jogadores de arte equipada
# (`tools/db_readonly_golpe_0930.py`).
#
# Por isso esta seccao CORRE a rota verdadeira, numa sessao que COMPILA cada
# query no dialecto do Postgres: uma coluna que nao existe rebenta aqui como
# rebentou em producao — e nao numa leitura do texto.
print("\n=== 9. ⚔️ a porta do golpe padrão corre (report de 30/09) ===")

import ast as _ast9
import asyncio as _aio9
from sqlalchemy.dialects import postgresql as _pg9
import core.webserver as _W9
import core.duel_engine as _DE9
import core.forbidden_path_engine as _FP9


class _Res9:
    def __init__(self, obj):
        self._o = obj

    def scalar_one_or_none(self):
        return self._o

    def scalars(self):
        return self

    def first(self):
        return self._o


class _Jogador9:
    telegram_id = 4242
    default_technique_id = None


class _Sess9:
    """Responde pelo guiao, mas antes COMPILA a query no dialecto do Postgres.

    ⚠️ O `AttributeError` do report nasce ao MONTAR a query, antes do
    `execute` — por isso a guarda chama a ROTA, nunca uma copia da query."""

    def __init__(self, guiao):
        self._g = list(guiao)
        self.sql = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt):
        self.sql.append(str(stmt.compile(dialect=_pg9.dialect())))
        return _Res9(self._g.pop(0) if self._g else None)

    async def commit(self):
        self.commits += 1


def _porta9(tech_id, guiao, ligada=True, proibida=False):
    """Corre `api_combat_default_strike` de ponta a ponta. Devolve
    (status, corpo, sessao) — ou (None, "Erro: ...", sessao) se a rota
    rebentar, que e' o 500 do jogador visto daqui."""
    sess = _Sess9(guiao)
    orig = (_W9.get_session_factory, _DE9.golpe_padrao_on, _FP9.is_forbidden)
    _W9.get_session_factory = lambda: (lambda: sess)
    _DE9.golpe_padrao_on = lambda *a, **k: ligada
    _FP9.is_forbidden = lambda *a, **k: proibida
    try:
        resp = _aio9.run(_W9.api_combat_default_strike(
            {"user_id": 4242, "payload": {"tech_id": tech_id}}))
        return resp.status, json.loads(resp.text), sess
    except Exception as ex:
        return None, "%s: %s" % (type(ex).__name__, str(ex)[:120]), sess
    finally:
        _W9.get_session_factory, _DE9.golpe_padrao_on, _FP9.is_forbidden = orig


# 9.1 — o caso do report: uma arte EQUIPADA.
_j9 = _Jogador9()
_st9, _c9, _s9 = _porta9(7, [_j9, object()])
check("9/⚠️ escolher uma arte EQUIPADA nao rebenta (era o 500)",
      _st9 == 200, str(_c9))
check("9/e responde ok com a arte escolhida",
      isinstance(_c9, dict) and _c9.get("ok") is True
      and _c9.get("default_technique_id") == 7, str(_c9))
check("9/e GRAVA a escolha, uma vez",
      _j9.default_technique_id == 7 and _s9.commits == 1,
      "%r · %d commits" % (_j9.default_technique_id, _s9.commits))
check("9/⚠️ ANTI-GUARDA: a rota fez as DUAS queries (o jogador + a arte)",
      len(_s9.sql) == 2, "%d" % len(_s9.sql))
_q9 = _s9.sql[1] if len(_s9.sql) > 1 else ""
check("9/a arte tem de estar EQUIPADA e ser de COMBATE (na query, nao na prosa)",
      "player_techniques.is_active_combat IS true" in _q9
      and "techniques_catalog.tech_type" in _q9, _q9[:160])

# 9.2 — as recusas continuam a DIZER porque (Lei §1), e nao gravam nada.
_j9b = _Jogador9()
_st9, _c9, _s9 = _porta9(7, [_j9b, None])
check("9/uma arte NAO equipada e' recusada a dizer porque",
      _st9 == 200 and isinstance(_c9, dict) and _c9.get("ok") is False
      and _c9.get("reason") == "technique_not_equipped", str(_c9))
check("9/e a recusa nao grava nada",
      _j9b.default_technique_id is None and _s9.commits == 0)
_st9, _c9, _s9 = _porta9(7, [_Jogador9()], proibida=True)
check("9/⚠️ a arte PROIBIDA e' recusada antes de se procurar a arte",
      isinstance(_c9, dict) and _c9.get("reason") == "forbidden_never_auto"
      and len(_s9.sql) == 1 and _s9.commits == 0, str(_c9))
_j9d = _Jogador9()
_j9d.default_technique_id = 7
_st9, _c9, _s9 = _porta9(0, [_j9d])
check("9/o golpe basico (0) limpa a escolha",
      isinstance(_c9, dict) and _c9.get("ok") is True
      and _j9d.default_technique_id is None and _s9.commits == 1, str(_c9))
_st9, _c9, _s9 = _porta9(7, [_Jogador9()], ligada=False)
check("9/⚠️ flag OFF => 404 e nem UMA query (o `main` nao paga nada)",
      _st9 == 404 and len(_s9.sql) == 0, "%r · %d queries" % (_st9, len(_s9.sql)))

# 9.3 — A FAMILIA INTEIRA: toda a `Modelo.coluna` do repositorio existe no
# modelo. A 1a passagem achou um SEGUNDO igual que ninguem tinha pisado: o chat
# filtrava `Tribulation.result` (a coluna e' `outcome`) no grau celestial.
import _audit_orm_colunas as _orm9
_il.reload(_orm9)
_r9 = _orm9.scan()
check("9/⚠️ ANTI-GUARDA: o varredor viu o repositorio (%d modelos · %d referencias)"
      % (_r9["modelos"], _r9["referencias"]),
      _r9["modelos"] >= 90 and _r9["referencias"] >= 3500,
      "um varredor que nao ve nada fica verde sobre o vazio")
check("9/⚠️ toda a `Modelo.coluna` existe no modelo (0 partidas)",
      _r9["total"] == 0, str(_r9["achados"])[:300])
_mods9 = _orm9.modelos()
_v9, _p9 = _orm9.problemas(
    "from database.models import PlayerTechnique as PT" + chr(10)
    + "x = PT.is_active" + chr(10), _mods9)
check("9/⚠️ AUTO-TESTE: o varredor apanha o `is_active` do report (com `as`)",
      _p9 == [(2, "PlayerTechnique.is_active")], str(_p9))
_v9, _p9 = _orm9.problemas(
    "from database.models import PlayerTechnique" + chr(10)
    + "x = PlayerTechnique.is_active_combat" + chr(10), _mods9)
check("9/AUTO-TESTE: e nao acusa a coluna certa", _p9 == [] and _v9 == 1,
      "%r · %d" % (_p9, _v9))

# 9.4 — "PASSOU A TRIBULACAO" tem UM dono. Eram tres copias com tres regras:
# o passe aceitava success+perfect, o mini-app so' success (recusava o
# celestial a quem teve a tribulacao PERFEITA), o chat rebentava.
import core.tribulation_engine as _TE9
check("9/a PERFEITA conta como passar a tribulacao (e so' as duas)",
      set(_TE9.TRIBULATION_PASSED_OUTCOMES) == {"success", "perfect"},
      str(_TE9.TRIBULATION_PASSED_OUTCOMES))
_tq9 = str(_TE9.tribulation_passed_clause(1).compile(
    dialect=_pg9.dialect(), compile_kwargs={"literal_binds": True}))
check("9/a condicao do dono compila com os dois desfechos",
      "tribulations.outcome IN ('success', 'perfect')" in _tq9, _tq9)

# As copias descobrem-se na AST de `core/` + `handlers/`, nunca numa lista
# minha: uma comparacao de `Tribulation.outcome` com um desfecho de sucesso, ou
# o tuplo `("success", "perfect")` escrito a' mao numa funcao que RESOLVE uma
# tribulacao (a que chama `determine_outcome`).
# ⚠️ So' nessas: a 1a versao procurava o tuplo no ficheiro inteiro e acusou a
# ALQUIMIA (`roll_craft_result` tambem devolve "success"/"perfect", e e' outra
# pergunta). O desfecho da tribulacao e' o que sai de `determine_outcome`.
_OK9 = {"success", "perfect"}
_copias9, _portoes9, _n_trib9, _resolve9 = [], [], 0, []
for _d9 in ("core", "handlers"):
    for _dp9, _dn9, _fn9 in os.walk(os.path.join(ROOT, _d9)):
        for _f9 in sorted(_fn9):
            if not _f9.endswith(".py"):
                continue
            _rel9 = os.path.relpath(os.path.join(_dp9, _f9), ROOT).replace(os.sep, "/")
            if _rel9 == "core/tribulation_engine.py":
                continue
            _t9 = _ast9.parse(_read(_rel9))
            for _nd9 in _ast9.walk(_t9):
                if (isinstance(_nd9, _ast9.Attribute)
                        and isinstance(_nd9.value, _ast9.Name)
                        and _nd9.value.id == "Tribulation"):
                    _n_trib9 += 1
                if isinstance(_nd9, (_ast9.Compare, _ast9.Call)):
                    _sub9 = list(_ast9.walk(_nd9))
                    _usa9 = any(isinstance(x, _ast9.Attribute) and x.attr == "outcome"
                                and isinstance(x.value, _ast9.Name)
                                and x.value.id == "Tribulation" for x in _sub9)
                    _lit9 = any(isinstance(x, _ast9.Constant) and x.value in _OK9
                                for x in _sub9)
                    if _usa9 and _lit9:
                        _copias9.append("%s:%d" % (_rel9, _nd9.lineno))
                if (isinstance(_nd9, (_ast9.FunctionDef, _ast9.AsyncFunctionDef))
                        and any(isinstance(x, _ast9.Call)
                                and isinstance(x.func, _ast9.Name)
                                and x.func.id == "determine_outcome"
                                for x in _ast9.walk(_nd9))):
                    _resolve9.append("%s:%s" % (_rel9, _nd9.name))
                    for _x9 in _ast9.walk(_nd9):
                        if isinstance(_x9, (_ast9.Tuple, _ast9.List, _ast9.Set)):
                            _cs9 = {x.value for x in _x9.elts
                                    if isinstance(x, _ast9.Constant)}
                            if _cs9 == _OK9 and len(_x9.elts) == 2:
                                _copias9.append("%s:%d (tuplo)" % (_rel9, _x9.lineno))
                # o PORTAO: `if reqs.get("requires_tribulation"):` com uma
                # consulta la' dentro (o que so' mostra o ⚡ nao consulta nada)
                if (isinstance(_nd9, _ast9.If) and isinstance(_nd9.test, _ast9.Call)
                        and any(isinstance(a, _ast9.Constant)
                                and a.value == "requires_tribulation"
                                for a in _nd9.test.args)
                        and any(isinstance(x, _ast9.Await)
                                for b in _nd9.body for x in _ast9.walk(b))):
                    _chama9 = any(isinstance(x, _ast9.Call)
                                  and isinstance(x.func, _ast9.Name)
                                  and x.func.id == "tribulation_passed_clause"
                                  for b in _nd9.body for x in _ast9.walk(b))
                    _portoes9.append((_rel9, _nd9.lineno, _chama9))
check("9/⚠️ ANTI-GUARDA: o localizador ve as referencias a `Tribulation` (%d)"
      % _n_trib9, _n_trib9 >= 5)
check("9/⚠️ ANTI-GUARDA: as funcoes que RESOLVEM a tribulacao foram achadas (%d)"
      % len(_resolve9), len(_resolve9) >= 2,
      "o chat e o mini-app resolvem-na — sem elas o tuplo nunca e' procurado")
check("9/⚠️ a regra 'passou a tribulacao' nao tem copias fora do dono",
      not _copias9, str(_copias9))
check("9/⚠️ ANTI-GUARDA: os portoes do grau celestial foram achados (%d)"
      % len(_portoes9), len(_portoes9) >= 2,
      "o chat e o mini-app — sem eles a de baixo afirma sobre o vazio")
check("9/⚠️ todo o portao do celestial pergunta ao dono",
      all(c for _, _, c in _portoes9),
      str([(f, n) for f, n, c in _portoes9 if not c]))

# =============================================================================
# §10 — ⚔️ A CENA DO DUELO DIZ DE ONDE VEM A LUTA (report de 2026-10-03)
# =============================================================================
#
# *"@saint_nivrael, bug: in PvE arena, popup of combat shows opponent's hp out
# of bound on screen."* A vida que transbordava e' GEOMETRIA e mede-se num
# browser, nas larguras reais (`scripts/_test_cena_cabe.py`). Esta seccao guarda
# o que se mede SEM browser e que o mesmo olhar apanhou na mesma janela: o NOME
# da origem no vao da cena. A tabela `CENA_FONTES` (ui.js) nasceu a mao com seis
# chaves — duas que nenhum duelo alguma vez teve (`npc_combat`, `arena`; o
# servidor grava `arena_npc_fallback`) — e falhava seis das dez origens: no Beta
# 582 de 4.520 duelos PvE, a ARENA inteira (o do report) incluida, diziam
# "Duelo" (`tools/db_readonly_duelo_hp_1005.py`). A lista certa e' a do SERVIDOR
# — `duel_engine.PVE_SOURCES`, a fonte unica das origens PvE — e a guarda le-a
# e exige a tabela IGUAL a ela: uma origem nova no servidor sem nome na cena, ou
# uma chave na cena que o servidor nao grava, ficam vermelhas aqui.
print("\n=== 10. ⚔️ a cena diz de onde vem a luta (report de 03/10) ===")

_ui10 = _read("miniapp/components/ui.js")
_m10 = re.search(r"var CENA_FONTES = \{(.*?)\};", _ui10, re.S)
check("10/ANTI-GUARDA: a tabela CENA_FONTES existe no ui.js", bool(_m10))
# a guarda le a PROSA, nao os comentarios: uma chave comentada nao conta
_corpo10 = re.sub(r"//[^\n]*", "", _m10.group(1) if _m10 else "")
_corpo10 = re.sub(r"/\*.*?\*/", "", _corpo10, flags=re.S)
_pares10 = dict(re.findall(r"([a-z_]+)\s*:\s*\"([a-z_]+)\"", _corpo10))
_srv10 = set(_DE9.PVE_SOURCES)
check("10/ANTI-GUARDA: o servidor tem as origens PvE (%d)" % len(_srv10), len(_srv10) >= 10)
check("10/ANTI-GUARDA: a tabela foi lida (%d entradas)" % len(_pares10), len(_pares10) >= 10)
check("10/ toda origem PvE do servidor tem nome na cena",
      _srv10 <= set(_pares10), str(sorted(_srv10 - set(_pares10))))
check("10/ nenhuma chave morta na cena (que o servidor nao grava)",
      set(_pares10) <= _srv10, str(sorted(set(_pares10) - _srv10)))
check("10/ a arena (a maior origem PvE, a do report) diz Arena",
      _pares10.get("arena_npc_fallback") == "cena_fonte_arena",
      repr(_pares10.get("arena_npc_fallback")))
_i18n10 = {lg: json.loads(_read("miniapp/i18n/%s.json" % lg)) for lg in LANGS}
_nomes10 = sorted(set(_pares10.values()) | {"cena_fonte_duelo"})
_falta10 = [(lg, k) for lg in LANGS for k in _nomes10
            if not str(_i18n10[lg].get(k) or "").strip()]
check("10/ todo nome existe e nao e' vazio nas tres linguas", not _falta10, str(_falta10))
for _lg10 in LANGS:
    _v10 = [str(_i18n10[_lg10].get(k)) for k in _nomes10]
    check("10/ %s: cada nome diz uma origem so' (%d nomes, %d distintos)"
          % (_lg10, len(_v10), len(set(_v10))), len(_v10) == len(set(_v10)))
# o nome sai do DONO: o vao chama `cenaFonte(state)`, e ela le a tabela
_f10 = re.search(r"function cenaFonte\(state\) \{(.*?)\n    \}", _ui10, re.S)
check("10/ o vao pergunta o nome a cenaFonte, e ela le a CENA_FONTES",
      bool(_f10) and "CENA_FONTES[state.pve_source]" in _f10.group(1)
      and _ui10.count("{cenaFonte(state)}") == 1)

# =============================================================================
# §11 — 道 O CAMINHO QUE SOBE SE VÊ (report de 2026-10-07)
# =============================================================================
#
# *"@saint_nivrael , bug: setting default attack for PvE arena, does not
# increase relevant path experience"*. MEDIDO antes de mexer
# (`tools/db_readonly_golpe_caminho_1007.py`): SUBIA. O golpe padrão dispara na
# arena (o registo tem a técnica 4/4 no Beta), os 8 duelos de arena do report
# foram todos liquidados (o `combat_log` modo arena) e a XP de Espada mudou no
# segundo a seguir ao último duelo: +18 por duelo (3 por golpe que acerta + 15
# de vitória ao caminho dominante). O defeito era OUTRO — nenhum ecrã o dizia:
# os três settles deitavam fora o resultado do `award_post_duel_intent_xp`. A
# lei da casa: subida sem número = nada.
print("\n=== 11. 道 o caminho que sobe se vê (report de 07/10) ===")

import ast as _ast11
import asyncio as _aio11
import re as _re11
import uuid as _uuid11
from types import SimpleNamespace as _NS11
from sqlalchemy.dialects import postgresql as _pg11
from sqlalchemy.sql.dml import Insert as _Ins11
import core.intent_engine as _IE11
import core.portas as _PO11
from database.models import DuelSession as _DS11

# (a) o RECIBO pelo dono
_g11 = _IE11.caminho_ganho({"sword": {"rank": 5, "xp": 602}}, {"sword": 1}, "sword", True,
                           {"results": [{"intent": "sword", "rank": 5, "xp": 620}]})
check("11/ o recibo do report: Espada +18 (3 por golpe + 15 de vitória), 602 -> 620 de 1.048",
      _g11 == [{"intent": "sword", "xp": 18, "antes": {"rank": 5, "xp": 602, "curva": 1048},
                "depois": {"rank": 5, "xp": 620, "curva": 1048}, "subiu": False}], str(_g11))
_g11b = _IE11.caminho_ganho({"sword": {"rank": 5, "xp": 1040}}, {"sword": 2, "body": 1}, "sword", False,
                            {"results": [{"intent": "body", "rank": 0, "xp": 3},
                                         {"intent": "sword", "rank": 6, "xp": 1}]})
check("11/ o dominante primeiro; a derrota dá 3; o posto que sobe diz R5 -> R6 com a curva NOVA",
      [x["intent"] for x in _g11b] == ["sword", "body"] and _g11b[0]["xp"] == 9
      and _g11b[0]["subiu"] is True and _g11b[0]["depois"]["curva"] == _IE11.xp_for_rank(6)
      and _g11b[1]["xp"] == 3 and _g11b[1]["subiu"] is False, str(_g11b))
check("11/ só o que o settle deu entra no recibo (um caminho sem resultado não se inventa)",
      _IE11.caminho_ganho({}, {"fist": 1}, None, True, {"results": []}) == [])


# (b) o DONO grava-o no `pve_context` — só com a onda e só em PvE. O award REAL
#     sobre uma sessão que compila no Postgres e aplica o UPSERT.
class _Res11:
    def __init__(self, rows=None, one=None):
        self._rows, self._one = rows or [], one

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._one


class _Sess11:
    def __init__(self, linhas):
        self.l, self.sql = linhas, []

    def begin_nested(self):
        class _N11:
            async def __aenter__(s2):
                return s2

            async def __aexit__(s2, *a):
                return False
        return _N11()

    async def execute(self, stmt):
        _t = str(stmt.compile(dialect=_pg11.dialect(), compile_kwargs={"literal_binds": True}))
        self.sql.append(_t)
        if isinstance(stmt, _Ins11):
            _v = {c.key: getattr(p, "value", p) for c, p in stmt._values.items()}
            _k = (_v["player_id"], _v["intent"])
            if _k in self.l:
                self.l[_k].xp += int(_v["xp"])
            else:
                self.l[_k] = _NS11(rank=0, xp=int(_v["xp"]))
            return _Res11()
        _pid = int(_re11.search(r"player_intents\.player_id = (\d+)", _t).group(1))
        if len(stmt.column_descriptions) == 3:
            return _Res11([(i, r.rank, r.xp) for (p, i), r in self.l.items() if p == _pid])
        _int = _re11.search(r"player_intents\.intent = '([a-z]+)'", _t).group(1)
        return _Res11(one=self.l.get((_pid, _int)))


def _duelo11(pve=True):
    return _DS11(id=_uuid11.uuid4(), attacker_id=77, defender_id=None if pve else 88,
                 pve_source="arena_npc_fallback" if pve else None,
                 pve_context={"elo_at_match": 1000} if pve else None,
                 fighter_a={"techniques": [{"id": 15, "intent_affinity": "sword"}]},
                 fighter_b={"techniques": [{"id": 3, "intent_affinity": "body"}]},
                 action_log=[{"round": 1, "a": {"tech": {"id": 15}}, "b": {"tech": None}}])


def _corre11(onda, pve=True, xp0=602):
    _orig = _PO11.onda_on
    _PO11.onda_on = lambda *a, **k: onda
    try:
        _s = _Sess11({(77, "sword"): _NS11(rank=5, xp=xp0)})
        _d = _duelo11(pve)
        _aio11.run(_IE11.award_post_duel_intent_xp(_s, _d, 77))
        return _d, _s
    finally:
        _PO11.onda_on = _orig


_ANT11 = "SELECT player_intents.intent, player_intents.rank, player_intents.xp"
_d11, _s11 = _corre11(True)
check("11/ com a onda, o award REAL grava o recibo no `pve_context` (o [jogador]: +18, 602 -> 620)",
      (_d11.pve_context or {}).get("caminho_ganho") == _g11
      and (_d11.pve_context or {}).get("elo_at_match") == 1000, str(_d11.pve_context))
check("11/ o 'antes' lê-se ANTES da escrita (o recibo nunca se deriva do depois)",
      [i for i, q in enumerate(_s11.sql) if q.startswith(_ANT11)][:1] == [0]
      and any(q.startswith("INSERT INTO player_intents") for q in _s11.sql[1:]))
_d11, _s11 = _corre11(False)
check("11/ sem a onda: nada gravado e nenhuma leitura a mais (o `main` fica igual)",
      "caminho_ganho" not in (_d11.pve_context or {}) and not any(q.startswith(_ANT11) for q in _s11.sql))
_d11, _s11 = _corre11(True, pve=False)
check("11/ PvP: o `pve_context` continua nulo (o recibo é só PvE)", _d11.pve_context is None)
_d11, _ = _corre11(True, xp0=1040)
_r11 = ((_d11.pve_context or {}).get("caminho_ganho") or [{}])[0]
check("11/ no limiar o posto SOBE e o recibo di-lo (R5 -> R6, 10 de 1.677)",
      _r11.get("subiu") is True and _r11.get("depois") == {"rank": 6, "xp": 10, "curva": 1677}, str(_r11))

# (c) os TRÊS settles chamam o dono — e o recibo NÃO vai para o `action_log` (o
#     settle da arena copia o registo para o `combat_log` e o histórico dos
#     Caminhos lê a ÚLTIMA entrada dele: um marcador ali partia o histórico)
_chama11 = {f: _read("core/%s.py" % f).count("await award_post_duel_intent_xp(")
            for f in ("arena_duel_settle", "pve_duel_settle", "pvp_duel_settle")}
check("11/ ANTI-GUARDA: os três settles chamam o dono, uma vez cada (%r)" % _chama11,
      _chama11 == {"arena_duel_settle": 1, "pve_duel_settle": 1, "pvp_duel_settle": 1})
_ie11 = _read("core/intent_engine.py")
_aw11 = _ie11.split("async def award_post_duel_intent_xp(")[1].split("\nasync def ")[0]
check("11/ o recibo vai para o `pve_context`, NUNCA para o `action_log` (o histórico lê a última entrada)",
      '_ctx["caminho_ganho"] = _ganho' in _aw11 and "duel.action_log =" not in _aw11
      and "duel.action_log.append" not in _aw11)

# (d) o duel_state lê-o — só com a onda e só para QUEM jogou o lado A
_ws11 = _read("core/webserver.py")
_fds11 = next(_n for _n in _ast11.walk(_ast11.parse(_ws11))
              if isinstance(_n, _ast11.AsyncFunctionDef) and _n.name == "api_combat_duel_state")
_src11 = _ast11.unparse(_fds11)
check("11/ o `combat/duel_state` devolve `caminho_ganho` só com a onda, só ao lado A, do `pve_context`",
      "user_id == duel.attacker_id and _onda_on_cg()" in _src11
      and "(duel.pve_context or {}).get('caminho_ganho')" in _src11
      and "out['caminho_ganho'] = _cg" in _src11)

# (e) o cliente: o fim da luta desenha-o, com os números inteiros, em 3 línguas
_tb11 = _read("miniapp/components/tabs.js")
# o BLOCO do recibo, recortado — a guarda afirma o que ele É: nenhum número
# abreviado lá dentro e as três frases com o XP inteiro (a 1.ª versão desta
# guarda afirmava 'contém fmtFull(cg.xp)' e ficou verde com uma das três
# abreviada — a bateria apanhou-a)
_bl11 = (_tb11.split("{Array.isArray(state.caminho_ganho) && state.caminho_ganho.length > 0 && (")[1]
         .split("            )}")[0]
         if "{Array.isArray(state.caminho_ganho) && state.caminho_ganho.length > 0 && (" in _tb11 else "")
check("11/ o fim da luta desenha o recibo dos caminhos (números inteiros, a curva do servidor)",
      len(_bl11) > 400 and "fmtNum(" not in _bl11 and _bl11.count("fmtFull(cg.xp)") == 3
      and "fmtFull(d.curva)" in _bl11, "%d chars" % len(_bl11))
_mi11 = {lg: json.loads(_read("miniapp/i18n/%s.json" % lg)) for lg in LANGS}
_k11 = ("caminho_ganho_titulo", "caminho_ganho_linha", "caminho_ganho_subiu", "caminho_ganho_max")
check("11/ as 4 frases do recibo existem nas três línguas",
      all(str(_mi11[lg].get(k) or "").strip() for lg in LANGS for k in _k11))

print(f"\n{PASS} passed · {len(FAIL)} failed")
if FAIL:
    print("\nFALHAS:")
    for f in FAIL:
        print("  ·", f)
    sys.exit(1)

print(f"OK — {PASS} asserts. A expedição avisa uma vez, a doação responde "
      "sempre, o Caminho renasce com o karma, e a cura mostra quem curar.")
