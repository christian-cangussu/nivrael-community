# -*- coding: utf-8 -*-
"""🩸 A BATERIA DE SABOTAGEM da §18 — uma guarda que nao morde nao guarda.

Mesmo contrato das outras tres (`_sabota_varredor`, `_sabota_o_mapa`,
`_sabota_a_forja`, `_sabota_o_golpe`): cada entrada estraga UMA coisa no codigo
de producao, corre a suite, e exige que ela fique VERMELHA **a dizer o que e'**
— nunca a rebentar, e nunca por um motivo diferente do esperado.

⚠️ E ha' aqui uma sabotagem que existe por causa de um erro cometido HOJE. A
primeira versao da guarda "ninguem trata `current_hp` NULL como zero" varria os
ficheiros inteiros e acusou `core/webserver.py:5985` — que era **o comentario
que eu tinha acabado de escrever a explicar o bug**. A guarda lia a PROSA e nao
o codigo, que e' a 5a recorrencia medida desta familia. Por isso duas das
sabotagens abaixo atacam o FILTRO DE COMENTARIOS: se ele deixar de filtrar (ou
passar a filtrar codigo), isto fica vermelho.

Uso:  python scripts/_sabota_o_hp.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "miniapp", "components", "ui.js")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
APP = os.path.join(ROOT, "miniapp", "components", "app.js")
PT = os.path.join(ROOT, "miniapp", "i18n", "pt.json")
WEB = os.path.join(ROOT, "core", "webserver.py")
SUITE = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")

# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    # ── 18a — NULL nao e' zero ────────────────────────────────────────────
    ("volta o `current_hp or 0` em producao", WEB,
     "                cur_hp, max_hp = float(_gch(player)), float(_gmh(player))",
     "                cur_hp, max_hp = float(player.current_hp or 0), 0.0",
     "NULL como zero"),

    # ⚠️ Esta sabotagem tem de inserir Python VALIDO: a 1a versao encavalitava
    # dois `async def` e a suite REBENTOU em vez de ficar vermelha, o que nao
    # prova nada sobre a guarda — prova que a sabotagem estava mal escrita.
    ("volta o `COALESCE(current_hp, 0)` em producao", WEB,
     "                hp_pct = max(0, min(100, round(100 * (boss.current_hp or 0) / boss.hp)))",
     "                _q = \"SELECT 1 FROM players WHERE COALESCE(current_hp, 0) <= 0\"\n"
     "                hp_pct = max(0, min(100, round(100 * (boss.current_hp or 0) / boss.hp)))",
     "NULL como zero"),

    # 🔴 As duas que atacam o FILTRO DE PROSA (o erro de hoje).
    ("o filtro de comentarios deixa de filtrar", SUITE,
     "            elif _c == \"#\":\n                _cut = _i\n                break",
     "            elif _c == \"#\":\n                pass",
     "APAGA mesmo a prosa"),

    ("o filtro de comentarios passa a apagar CODIGO", SUITE,
     "        out.append(_ln if _cut is None else _ln[:_cut])",
     "        out.append(\"\")",
     "NAO apaga codigo"),

    # ── 18b — a recusa tem dono e diz o caminho ──────────────────────────
    ("uma recusa volta ao `t()` cru (o beco volta)", TABS,
     'hp_depleted:        hpDepletedMsg("combat_npc_hp_depleted"),',
     'hp_depleted:        t("combat_npc_hp_depleted"),',
     "passa pelo dono unico"),

    ("a recusa da fila volta ao `t()` cru", TABS,
     'hp_too_low:     hpDepletedMsg("combat_arena_q_err_hp"),',
     'hp_too_low:     t("combat_arena_q_err_hp"),',
     "passa pelo dono unico"),

    ("o dono unico deixa de juntar o caminho", UI,
     'return safeT(contextKey) + " " + safeT("combat_hp_way_out");',
     "return safeT(contextKey);",
     "CAMINHO DE SAIDA"),

    ("nasce um SEGUNDO dono (a F-7 outra vez)", UI,
     "    function hpDepletedMsg(contextKey) {",
     "    function hpDepletedMsg(contextKey) { return safeT(contextKey); }\n"
     "    function hpDepletedMsg(contextKey) {",
     "UMA definicao"),

    ("o conselho do DESAFIANTE passa a mandar VOCE meditar", TABS,
     'challenger_hp_depleted:   t("combat_pvp_challenger_hp_depleted"),',
     'challenger_hp_depleted:   hpDepletedMsg("combat_pvp_challenger_hp_depleted"),',
     "nao manda VOCE meditar"),

    # ── 18c — o caminho nomeia accoes REAIS, e ninguem manda esperar ─────
    ("o caminho deixa de nomear a Pilula", PT,
     '"combat_hp_way_out": "Medite para recuperar, ou use uma Pílula de Cura."',
     '"combat_hp_way_out": "Recupere antes de lutar."',
     "nomeia `medit`"),

    ("uma recusa volta a mandar ESPERAR", PT,
     '"combat_npc_hp_depleted": "Vitalidade em zero."',
     '"combat_npc_hp_depleted": "Vitalidade em zero. Espere regenerar."',
     "nao manda ESPERAR"),

    # ── 18d — a barra diz o que e' ───────────────────────────────────────
    ("a Vitalidade volta a ser uma barra NUA", TABS,
     '                <LabeledBar label={safeT("hub_eu_bar_vitality")} variant="hp"',
     '                <ProgressBar variant="hp"',
     "barra NUA"),

    ("o rotulo da Vitalidade vira literal (sem as 3 linguas)", TABS,
     'label={safeT("hub_eu_bar_vitality")}',
     'label={"Vitalidade"}',
     "chave propria"),

    ("o `LabeledBar` deixa de desenhar a barra", UI,
     "          <ProgressBar pct={pct} variant={variant} height={height} />",
     "          <div />",
     "desenha por cima do `ProgressBar`"),

    # ── 18e — 坐 o orbe nao volta ────────────────────────────────────────
    ("volta a esfera de gradiente com emoji do sistema", TABS,
     '            <div style={{ flexShrink:0, animation:"orb-breathe 3.6s ease-in-out infinite" }}>\n'
     '              <RealmAvatar realm={data.realm} size={64}',
     '            <div style={{ borderRadius:"50%",\n'
     '              background:`radial-gradient(circle at 30% 30%, ${rc}, transparent 70%)` }}>\n'
     '              <span>{data.realm_emoji}</span></div>\n'
     '            <div style={{ display:"none" }}>\n'
     '              <RealmAvatar realm={data.realm} size={64}',
     "nenhuma esfera"),

    # 🔴 A 1a versao trocava por `RealmAvatarX` — e **`<RealmAvatarX` comeca
    # por `<RealmAvatar`**, portanto a guarda (que fazia `count("<RealmAvatar")`)
    # continuava a ver 1 e ficava VERDE com o heroi substituido por um emoji do
    # sistema. E' a licao de 11/09 ("renomear com um prefixo comum nao e'
    # sabotar") a repetir-se. A guarda ganhou `\\b`; a sabotagem usa um nome que
    # nao partilha prefixo nenhum.
    ("o heroi do hub EU perde o dono unico", TABS,
     "              <RealmAvatar realm={realm} size={orbSize}",
     "              <span>{player.realm_emoji}</span>\n"
     "              <OutroAvatar realm={realm} size={orbSize}",
     "`RealmAvatar`"),

    # 🔴 E a sabotagem-irma: o rename COM prefixo comum, que e' o caso que
    # passou verde. Se a fronteira `\\b` desaparecer da guarda, isto fica verde.
    ("o dono unico renomeado com PREFIXO comum", TABS,
     "              <RealmAvatar realm={realm} size={orbSize}",
     "              <RealmAvatarX realm={realm} size={orbSize}",
     "`RealmAvatar`"),

    ("o efeito morre junto com o orbe", TABS,
     '                      animation: burstSeq\n'
     '                        ? "orb-burst .9s cubic-bezier(.2,.8,.3,1.15)"',
     '                      animation: burstSeq\n'
     '                        ? "none"',
     "SOBREVIVERAM"),

    ("o tom derivado desaparece (marca de 21px num disco de 150)", UI,
     "    function _realmAvatarTone(size) {",
     "    function _realmAvatarToneX(size) {",
     "deriva o tom"),

    # ── 18f — o arranque nao pendura ─────────────────────────────────────
    ("a i18n perde o relogio (ecra em branco para sempre)", APP,
     "        const tm = setTimeout(() => { try { ctrl && ctrl.abort(); } catch (e) {} }, _I18N_TIMEOUT_MS);",
     "        const tm = 0;",
     "RELOGIO"),

    ("o `render()` sai do `finally`", APP,
     "    _loadI18n().finally(() => {",
     "    _loadI18n().then(() => {",
     "corre no `finally`"),
]


def run():
    falhas = []
    print("=" * 78)
    print("  🩸 SABOTAGEM da §18 — %d ataques" % len(SABOTAGENS))
    print("=" * 78)
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8", newline="").read()
        # ⚠️ O alvo e' verificado ANTES: uma sabotagem que nunca encontra o que
        # estragar DA-SE POR BOA, e um "20/20 mordem" assim e' um falso verde
        # com mais passos (licao de 09/09 e de hoje, nas 4 do `_sabota_o_mapa`).
        if orig.count(de) != 1:
            falhas.append("%-52s ALVO NAO ENCONTRADO (%d ocorrencias)"
                          % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        io.open(path, "w", encoding="utf-8", newline="").write(
            orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run(
                [sys.executable, SUITE],
                capture_output=True, text=True, env=env, cwd=ROOT, timeout=600,
                # ⚠️ `text=True` sozinho descodifica com o codec do LOCALE
                # (cp1252 no Windows) e rebenta no primeiro 漢字 da suite.
                encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split("\n") if l.strip().startswith("x ")]
            # ⚠️ O sinal honesto de crash e' o RODAPE, nunca "Traceback" no
            # stderr: a propria suite acende um de proposito no §1.
            rebentou = "asserts verdes" not in saida
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and (not agulha
                                  or any(agulha in l for l in vermelhos))
            if acertou:
                print("  ok  %-52s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-52s REBENTOU — uma guarda que rebenta nao e' "
                              "uma guarda vermelha" % rot)
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-52s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-52s ficou vermelha pelo motivo ERRADO "
                              "(esperava %r)" % (rot, agulha))
                print("  XX  " + falhas[-1])
        finally:
            io.open(path, "w", encoding="utf-8", newline="").write(orig)
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas),
                                       len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
