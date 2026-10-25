# -*- coding: utf-8 -*-
"""🩸 A BATERIA DE SABOTAGEM da §19 — 坐 o cultivador jogavel.

Mesmo contrato das outras seis (`_sabota_varredor`, `_sabota_o_mapa`,
`_sabota_a_forja`, `_sabota_o_golpe`, `_sabota_os_nomes`, `_sabota_o_hp`): cada
entrada estraga UMA coisa no codigo de producao, corre a suite, e exige que ela
fique VERMELHA **a dizer o que e'** — nunca a rebentar, e nunca por um motivo
diferente do esperado.

⚠️ O que esta bateria guarda, e porque cada ataque existe:

  · O CATALOGO tinha DOIS donos. O `config.py` aceita 7 modalidades e o cliente
    desenhava 4 — `dao_basic` (reino 5), `dao_deep` (6) e `dao_transcend` (8)
    eram conteudo destrancado que a superficie canonica nunca mostrou. As
    sabotagens 1-4 atacam o dono unico: se ele voltar a ser dois, ou se o
    catalogo mentir num custo, isto fica vermelho.
  · O NUMERO era ABREVIADO. `fmtNum` devolve `20.67B` e o `current_hp` de
    producao tem 12 digitos. As sabotagens 5-7 devolvem a abreviatura e o
    `NULL -> 0`.
  · O ERRO era a PALAVRA CRUA do servidor ("unauthorized", em ingles, num ecra
    sem um unico botao). As sabotagens 11-13 trazem o beco de volta.

⚠️ E tres ataques existem por causa de erros COMETIDOS neste lote:
  · a guarda do Poder de Combate ficou vermelha por ler uma fatia de 1200
    caracteres que engolia o bloco seguinte — a 8 ataca a delimitacao;
  · as tres chamadas ao `ico()` nasceram com o emoji num PROP (`emoji="X"`), que
    nao e' porta nenhuma, e a catraca subiu de 23 para 26 — a 19 ataca isso;
  · a mensagem de uma guarda dizia o CONTRARIO do que ela verifica.

Uso:  python scripts/_sabota_o_cultivador.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "miniapp", "components", "ui.js")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
APP = os.path.join(ROOT, "miniapp", "components", "app.js")
WEB = os.path.join(ROOT, "core", "webserver.py")
DB = os.path.join(ROOT, "database", "db.py")
ES = os.path.join(ROOT, "miniapp", "i18n", "es.json")
PT = os.path.join(ROOT, "miniapp", "i18n", "pt.json")
SUITE = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")

# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    # ── 19a/b — O CATALOGO TEM UM DONO ────────────────────────────────────
    ("o catalogo perde uma das 7 modalidades", WEB,
     "            merged.setdefault(key, info)",
     "            if key == \"dao_transcend\":\n"
     "                continue\n"
     "            merged.setdefault(key, info)",
     "catalogo devolve"),

    ("o catalogo MENTE num custo de qi", WEB,
     '            "qi_cost": int(info.get("qi_cost", 0)),',
     '            "qi_cost": 0,',
     "NAO bate com o `config.py`"),

    ("o catalogo MENTE num requisito de reino", WEB,
     '            "min_realm": int(info.get("min_realm", 0)),',
     '            "min_realm": 0,',
     "NAO bate com o `config.py`"),

    # ⚠️ Ausente tem de continuar ausente: inventar um x1 no `dao_fragment_mult`
    # poria uma linha falsa debaixo das tres praticas que nao dao fragmentos.
    #
    # 🔴 A 1a versao deste ataque FICOU VERDE, e a culpa era do ATAQUE, nao da
    # guarda: ele trocava so' a primeira metade da expressao e deixava o
    # `if ... is not None else None` intacto, portanto o valor continuava a ser
    # `None` quando a chave falta. Uma sabotagem que nao muda o comportamento
    # nao prova nada sobre quem a vigia. Agora troca a expressao INTEIRA.
    # ⚠️ E o alvo é de UMA linha, de propósito. A 2a versão usou as duas linhas
    # da expressão com `\n` — e o `core/webserver.py` é **CRLF**, portanto não
    # casava com nada e o ataque dava-se por bom. Fins-de-linha lêem-se, nunca
    # se assumem; um alvo de uma linha não tem esse problema.
    ("o catalogo INVENTA um multiplicador de Dao", WEB,
     #   ⚠️ E o ataque INVENTA um valor em vez de apagar a expressão. Apagá-la
     #   deixava `info["dao_fragment_mult"]` a levantar `KeyError` nas três
     #   práticas que não o têm — a suite ficava vermelha, sim, mas a dizer
     #   "`_meditation_catalog()` nao correu". Vermelho pelo motivo errado não
     #   prova a guarda certa: o que se quer provar é que um valor INVENTADO
     #   é apanhado, não que um crash é apanhado.
     '                                  if info.get("dao_fragment_mult") is not None else None),',
     "                                  if info.get(\"dao_fragment_mult\") is not None else 1.0),",
     "ausente continua ausente"),

    ("o cliente volta a desenhar a lista dele", TABS,
     "              catalog={data.meditation_catalog}",
     "              catalog={medTypes}",
     "catalogo DO SERVIDOR"),

    # ── 19c — as cinco recusas tem cada uma a sua frase ───────────────────
    ("a tabela de recusas perde o `not_enough_qi`", UI,
     '      not_enough_qi: "onda_med_err_qi",',
     "",
     "EXACTAMENTE os cinco"),

    # ⚠️ O `if (_MED_ERR_KEY[code])` aparece DUAS vezes (o `start` e o `stop`),
    # e o runner exige ocorrencia UNICA -- de proposito, para nao estragar um
    # sitio a pensar que se estragou outro. Ataca-se a TABELA, que e' unica.
    ("o cartao deixa de saber traduzir a recusa", UI,
     "    var _MED_ERR_KEY = {",
     "    var _MED_ERR_KEY_MORTA = {};\n    var _MED_ERR_KEY = {",
     "cobre EXACTAMENTE"),

    # ── 19d — o numero INTEIRO ───────────────────────────────────────────
    ("a cena volta a ABREVIAR o HP (`20.67B`)", UI,
     "                     now={fmtFull(curHp)} max={fmtFull(maxHp)}",
     "                     now={fmtNum(curHp)} max={fmtNum(maxHp)}",
     "NAO usa `fmtNum`"),

    ("o `fmtFull` deixa de agrupar pela lingua", UI,
     '        return v.toLocaleString(_FULL_LOCALE[LANG] || "pt-BR", { useGrouping: true });',
     "        return String(v);",
     "agrupa pela LINGUA"),

    ("`current_hp` NULL volta a valer ZERO", UI,
     "      var curHp = (hpNow === null || hpNow === undefined) ? maxHp : Number(hpNow);",
     "      var curHp = Number(hpNow) || 0;",
     "NULL resolve para o MAXIMO"),

    # ── 19e — as barras aguentam mais de 100% ────────────────────────────
    ("o transbordo do Qi deixa de ser detectado", UI,
     "      var qiOver = qiM > 0 && qiN > qiM;",
     "      var qiOver = false;",
     "transbordo do Qi e' DETECTADO"),

    ("o transbordo deixa de ser DITO em palavras", UI,
     'note={qiOver ? t("onda_qi_over", { mult: (qiN / qiM).toFixed(2) }) : null}',
     "note={null}",
     "DITO em palavras"),

    ("o `over` do ProgressBar deixa de ser aditivo", UI,
     '    function ProgressBar({ pct, variant="cult", height=8, bare=false, over=false }) {',
     '    function ProgressBar({ pct, variant="cult", height=8, bare=false, over=true }) {',
     "ADITIVOS"),

    # ── 19f — CB NAO e' Poder de Combate (MESA [012]) ────────────────────
    ("o Poder de Combate entra no bloco do LIMIAR", UI,
     '                {t("onda_cb_threshold")}',
     '                {t("onda_cb_threshold")}{combatPower}',
     "NAO entra no bloco do limiar"),

    # 🔴 O ataque a' DELIMITACAO, e o modo de falha MUDOU. O erro de ontem era a
    # fatia ENGOLIR o bloco seguinte (guarda vermelha por ler codigo alheio); o
    # perigo de hoje e' o oposto e e' pior: uma fatia que nao chega a apanhar o
    # bloco fica VERDE PARA SEMPRE sobre um pedaco de texto vazio -- a licao de
    # 08/09 (`set() <= {...}`). Por isso o ataque encolhe a fatia a 10 chars.
    ("a fatia do bloco do limiar encolhe para o vazio", SUITE,
     '_cb_j = _syn.find("{cta}", _cb_i)',
     '_cb_j = _cb_i + 10',
     "bloco do limiar foi delimitado"),

    ("o Poder aparece mesmo sem o mundo o calcular", UI,
     "          {combatPower != null ? (",
     "          {true ? (",
     "linha NAO EXISTE"),

    ("a barra do avanco passa a comparar o Poder", TABS,
     "                    cbNow={data.cultivation_base} cbMax={data.cb_threshold}",
     "                    cbNow={player.display_combat_power} cbMax={data.cb_threshold}",
     "NUNCA o Poder de Combate"),

    # ── 19g — o beco da chegada nao volta ────────────────────────────────
    ("volta a faixa com a palavra crua do servidor", APP,
     "              <CultRecovery error={error} onRetry={() => { setError(null); loadPlayer(); }}\n"
     "                            wide={_wideSurface} />",
     "              <ErrBanner msg={error} />",
     "palavra crua"),

    ("o `unauthorized` deixa de ser sessao expirada", UI,
     'var _SESSION_ERRS = ["unauthorized", "session_expired", "login_invalid", "HTTP 401"];',
     'var _SESSION_ERRS = ["session_expired"];',
     "`unauthorized` e' reconhecido"),

    ("a saida deixa de depender da plataforma", UI,
     '        ? (inTelegram ? t("onda_rec_session_telegram") : t("onda_rec_session_browser"))',
     '        ? t("onda_rec_session_browser")',
     "POR PLATAFORMA"),

    # ── 19h — as ancoras nunca apontam para o vazio ──────────────────────
    ("as ancoras deixam de filtrar pelo que EXISTE", UI,
     "      var live = (items || []).filter(function (a) { return a && a.present; });",
     "      var live = (items || []);",
     "FILTRAM por `present`"),

    ("a Pratica ganha ancora fixa (o destino pode nao existir)", TABS,
     "label:t(\"cult_sec_practice\"), present:_hasPractice }",
     "label:t(\"cult_sec_practice\"), present:true }",
     "nunca `present:true` fixo"),

    ("uma regua de seccao perde o `anchorId`", TABS,
     '<SectionRule glyph="途" label={t("cult_sec_paths")} anchorId="cult-sec-paths" />',
     '<SectionRule glyph="途" label={t("cult_sec_paths")} />',
     "`anchorId`"),

    ("uma ancora aponta para um id que NAO existe", TABS,
     'id:"cult-sec-paths",',
     'id:"cult-sec-nenhures",',
     "aponta para um `anchorId` que EXISTE"),

    # \U0001f534 ESTE ficou VERDE na 1a corrida, e foi o achado da bateria: as
    # guardas perguntavam se o `anchorId` era PASSADO e nenhuma se ele CHEGAVA
    # ao DOM. Com o `id` removido, as quatro ancoras saltavam para lado nenhum
    # e as 786 continuavam verdes. "Existe" nao e' "chega".
    ("o `anchorId` deixa de chegar ao DOM", UI,
     "        <div id={anchorId} style={{ display:\"flex\", alignItems:\"center\", gap:9,",
     "        <div style={{ display:\"flex\", alignItems:\"center\", gap:9,",
     "CHEGA ao DOM"),

    # ── 19i — a ordem muda sem duplicar o JSX ────────────────────────────
    ("a seccao e' escrita DUAS vezes (a Lei 0 §2)", TABS,
     '          <SectionRule glyph="己" label={t("cult_sec_self")} anchorId="cult-sec-self" />',
     '          <SectionRule glyph="己" label={t("cult_sec_self")} anchorId="cult-sec-self" />\n'
     '          <SectionRule glyph="己" label={t("cult_sec_self")} anchorId="cult-sec-self" />',
     "escrita UMA vez"),

    # ── 19j — a flag ─────────────────────────────────────────────────────
    ("a flag nasce LIGADA", DB,
     '    "cultivador_jogavel":  False,',
     '    "cultivador_jogavel":  True,',
     "nasce OFF"),

    ("nasce um SEGUNDO leitor da chave em `ui.js`", UI,
     "    function ondaCultOn() {",
     '    var _ondaOutra = featureEnabled("cultivador_jogavel");\n'
     "    function ondaCultOn() {",
     "lida UMA vez"),

    ("um dos dez modais some atras do CTA novo", TABS,
     "          {showTrib && (\n            <TribulationModal",
     "          {false && (\n            <OutroModal",
     "TribulationModal"),

    # ── 19k — as tres linguas ────────────────────────────────────────────
    ("uma chave da onda falta no espanhol", ES,
     '    "onda_cb_reached": "Umbral alcanzado",\n',
     "",
     "es.json` tem todas as chaves"),

    ("uma traducao perde um `{param}`", PT,
     '    "onda_qi_over": "Acima da capacidade · {mult}×",',
     '    "onda_qi_over": "Acima da capacidade",',
     "MESMOS placeholders"),

    ("o painel de admin perde o nome da flag", ES,
     '    "feature_cultivador_jogavel": "坐 Cultivador jugable",\n',
     "",
     "nomeia e descreve a flag"),

    # ── 19r — o transporte nao pendura, e o duelo nao mente ──────────────
    # ⚠️ A agulha mudou de "tem PRAZO" para "esta ARMADO", e é por causa desta
    # sabotagem: a 1ª guarda perguntava se a CONSTANTE existia e ficou VERDE
    # com o relógio desarmado (`API_TIMEOUT_MS` continuava no ficheiro). A
    # pergunta certa é se o `setTimeout` chama mesmo o `abort` com o prazo.
    ("o `fetch` perde o prazo (o jogo volta a pendurar)", UI,
     "          _tm = setTimeout(() => { try { _ctrl.abort(); } catch (e) {} }, API_TIMEOUT_MS);",
     "          _tm = null;",
     "esta ARMADO"),

    # 🔴 A ARMADILHA DO ASTRA: um relogio que repete sozinho uma mutacao cobra
    # duas vezes. "Uma resposta perdida pode corresponder a uma accao
    # CONCLUIDA no servidor" — o relogio devolve o controlo, nunca repete.
    ("o relogio passa a REPETIR sozinho (cobra duas vezes)", UI,
     "      let res;\n      try {\n        res = await fetch(",
     "      let res;\n      const _retry = 1;\n      try {\n        res = await fetch(",
     "NAO repete o pedido"),

    ("o prazo e a falha de rede colapsam num codigo so'", UI,
     'throw new Error(_abortado ? "request_timeout" : (e && e.message) || "network_error");',
     'throw new Error("network_error");',
     "codigos DIFERENTES"),

    ("a frase do prazo passa a dizer que FALHOU", PT,
     '"err_request_timeout": "O servidor demorou demais para responder. Não sabemos',
     '"err_request_timeout": "A ação falhou. Não dizemos',
     "NAO SE SABE"),

    ("o `ErrBanner` volta a ter a tabela de duas entradas", UI,
     "      return <div className=\"err-banner\">⚠️ {apiErroTexto(msg)}</div>;",
     "      const friendly = msg === \"unauthorized\" ? t(\"err_unauthorized\") : msg;\n"
     "      return <div className=\"err-banner\">⚠️ {friendly}</div>;",
     "passa pelo dono"),

    ("um codigo sem frase passa a ser ESCONDIDO", UI,
     "      return k ? t(k) : msg;",
     '      return k ? t(k) : "";',
     "sai CRU"),

    ("o duelo volta a enviar o `pickTech` cru", TABS,
     "            duel_id: duelId, technique_id: _envio,",
     "            duel_id: duelId, technique_id: pickTech,",
     "escolha VALIDADA"),

    ("a carta acende a escolha VELHA (ve-se uma, envia-se outra)", TABS,
     "                      const selected = pickEfetivo === tt.id;",
     "                      const selected = pickTech === tt.id;",
     "acendem o que vai SER ENVIADO"),

    ("a tela deixa de DIZER que a escolha caiu", TABS,
     '                      {t("duel_tech_dropped")}',
     '                      {""}',
     "DIZ porque"),

    # ── A CATRACA: um emoji novo sem porta ───────────────────────────────
    # ⚠️ O erro literal deste lote: as tres chamadas nasceram com o emoji num
    # PROP (`emoji="X"`), que a auditoria nao reconhece como porta — 23 -> 26.
    ("um emoji novo nasce sem porta (o erro de hoje)", UI,
     "    function CultValue({ children, size, lh, weight, color, align }) {",
     '    var _EMOJI_NOVO = "❤️\U0001f300\U0001f506";\n'
     "    function CultValue({ children, size, lh, weight, color, align }) {",
     "catraca"),
]


def run():
    falhas = []
    print("=" * 78)
    print("  \U0001fa78 SABOTAGEM da §19 — %d ataques" % len(SABOTAGENS))
    print("=" * 78)
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8", newline="").read()
        # ⚠️ O alvo e' verificado ANTES: uma sabotagem que nunca encontra o que
        # estragar DA-SE POR BOA, e um "32/32 mordem" assim e' um falso verde
        # com mais passos.
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
                capture_output=True, text=True, env=env, cwd=ROOT, timeout=900,
                encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split("\n") if l.strip().startswith("x ")]
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
