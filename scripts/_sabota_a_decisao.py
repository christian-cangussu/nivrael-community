# -*- coding: utf-8 -*-
"""🩸 A BATERIA DE SABOTAGEM do lote de 16/09 — §20 決 a decisao que nao
se perde, e §21 o facto que decide a meditacao.

Mesmo contrato das outras sete (`_sabota_varredor`, `_sabota_o_mapa`,
`_sabota_a_forja`, `_sabota_o_golpe`, `_sabota_os_nomes`, `_sabota_o_hp`,
`_sabota_o_cultivador`): cada entrada estraga UMA coisa no codigo de producao,
corre a suite, e exige que ela fique VERMELHA **a dizer o que e'** — nunca a
rebentar, e nunca por um motivo diferente do esperado.

⚠️ O que esta bateria guarda, e porque cada ataque existe:

  · O DESFECHO era um BOOLEANO. `won=false` significava ao mesmo tempo "perdi"
    e "nao consegui saber", e a tela escrevia o segundo como o primeiro: 🥀
    *"foste derrotado"* depois de uma vitoria, por causa de um `fetch` que nao
    voltou. Os ataques 2-4 poem o booleano de volta, em cada uma das tres
    formas que o servidor tem de dizer "nao sei" a **HTTP 200**.
  · A ESCOLHA MORAL sumia. O `finally` empurrava para o resultado mesmo com o
    pedido falhado, e o jogador nunca sabia que o karma nao tinha sido gravado.
    Os ataques 5-7 trazem isso de volta.
  · O CONTRATO ja' salvava o jogador e o cliente deitava fora: a recusa
    `already_resolved` **traz o desfecho dentro dela** (o servidor e'
    idempotente por duelo). O ataque 8 apaga essa leitura.
  · ⚠️ E o dono era TRES. O ataque 1 e' o mais importante desta bateria: se
    alguem voltar a copiar a decisao moral para um modal novo, isto fica
    vermelho. Foi a copia a' mao que produziu o defeito em triplicado E fez uma
    das tres perder a linha do Caminho cristalizado.

⚠️ Tres ataques existem por causa de erros COMETIDOS neste lote:
  · a minha 1a versao da §20 corrigiu **um** dos tres sitios — a propria guarda
    e' que me apanhou, e o ataque 1 e' a versao permanente disso;
  · a assert do `finally` so' sabia recusar uma frase exacta do codigo antigo
    (nao guardava comportamento nenhum) — o ataque 6 exige a versao positiva;
  · o rosto do "nao sei" quase nasceu emoji, com a catraca do §15 em 1300/1300
    — o ataque 10 prova que ela ainda morde.

Uso:  python scripts/_sabota_a_decisao.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "miniapp", "components", "ui.js")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
ES = os.path.join(ROOT, "miniapp", "i18n", "es.json")
WEB = os.path.join(ROOT, "core", "webserver.py")
APP = os.path.join(ROOT, "miniapp", "components", "app.js")
SUITE = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")

# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    # ── 1. 🔴 O DONO VOLTA A SER COPIADO ──────────────────────────────────
    # O ataque mais importante: um modal novo que reimplemente a decisao moral
    # a' mao e' exactamente como nasceram as tres copias que este lote juntou.
    ("um modal deixa de beber do dono unico", TABS,
     "        useDecisaoMoral({ duelId, setFase: setPhase, aoResolver: onDone, aoVencer: null });",
     "        useDecisaoMoralCopiadaAMao({ duelId, setFase: setPhase, aoResolver: onDone });",
     "bebem do mesmo dono"),

    # ── 2-4. O "NAO SEI" VOLTA A SER DITO COMO DERROTA ────────────────────
    # As tres formas que o servidor tem de dizer "nao sei" a HTTP 200, uma a uma.
    ("o `ok:false` a 200 volta a contar como derrota", TABS,
     '          if (!st || st.ok === false || st.state !== "finished" || youId == null) return "desconhecido";',
     '          if (!st || st.state !== "finished") return "derrota";',
     "nunca derrota"),

    ("a ausencia de `youId` volta a contar como derrota", TABS,
     '|| st.state !== "finished" || youId == null) return "desconhecido";',
     '|| st.state !== "finished") return "desconhecido";',
     "nunca derrota"),

    # ⚠️ A 1a versao deste ataque FICOU VERDE, e a culpa era do ATAQUE. Ele
    # DECLARAVA `const [won2, setWon] = useState(false)` e nunca o chamava — e a
    # assert pergunta por `setWon(`, a CHAMADA. Uma sabotagem que nao muda o
    # comportamento nao prova nada sobre quem a vigia. Agora o booleano volta
    # mesmo a ser escrito, que e' a regressao real.
    ("o desfecho volta a ser um BOOLEANO", TABS,
     '        const d = await lerDesfecho();\n'
     '        setDesfecho(d);\n'
     '        if (d === "vitoria") {\n'
     '          if (aoVencer) { try { await aoVencer(); } catch (e) {} }\n'
     '          haptic("success"); setFase("moral");\n'
     '        } else {',
     '        const d = await lerDesfecho();\n'
     '        setDesfecho(d);\n'
     '        setWon(d === "vitoria");\n'
     '        if (d === "vitoria") {\n'
     '          if (aoVencer) { try { await aoVencer(); } catch (e) {} }\n'
     '          haptic("success"); setFase("moral");\n'
     '        } else {',
     "MORREU nos tres"),

    # ── 5-7. A ESCOLHA MORAL VOLTA A SUMIR ────────────────────────────────
    ("o `finally` volta a empurrar para o resultado", TABS,
     "        } finally { setMoralBusy(false); if (aoResolver) aoResolver(); }",
     '        } finally { setMoralBusy(false); setFase("result"); if (aoResolver) aoResolver(); }',
     "solta o botao"),

    ("o `catch` da escolha avanca com a rede caida", TABS,
     '          setMoralErro({ tipo: "silencio", razao: (e && e.message) || "" });',
     '          setFase("result");',
     "NAO muda de fase"),

    ("a recusa e o silencio voltam a ser a mesma coisa", TABS,
     '            setMoralErro({ tipo: "recusa", razao: (res && res.reason) || "" });',
     '            setMoralErro({ tipo: "silencio", razao: "" });',
     "estados DISTINTOS"),

    # ── 8. O CONTRATO QUE SALVA O JOGADOR E' DEITADO FORA ─────────────────
    ("a recusa idempotente volta a ser deitada fora", TABS,
     '          } else if (res && res.reason === "already_resolved" && res.outcome) {',
     '          } else if (false) {',
     "already_resolved"),

    # ── 9-11. A TELA ──────────────────────────────────────────────────────
    ("o rosto volta a ter duas faces", TABS,
     '            {won ? textoVitoria : naoSei ? t("explore_desfecho_incerto") : textoDerrota}',
     "            {won ? textoVitoria : textoDerrota}",
     "quando o servidor a CONFIRMOU"),

    # ⚠️ O tecto do `tabs.js` esta' em 1300/1300 — zero folga. Um emoji novo no
    # rosto do "nao sei" empurra a catraca do §15 para cima.
    ("um emoji novo nasce no rosto do 'nao sei'", TABS,
     '{won ? "\U0001f3c6" : desfecho === "derrota" ? "\U0001f940" : "疑"}',
     '{won ? "\U0001f3c6" : desfecho === "derrota" ? "\U0001f940" : "❓"}',
     "catraca"),

    ("o Caminho cristalizado desaparece outra vez", TABS,
     "          {moral.karma && moral.karma.crystallized && (",
     "          {false && (",
     "cristalizado"),

    # ── 12. A LEITURA VIRA UMA MUTACAO REPETIDA ───────────────────────────
    # A regra do item 8 do Astro: *uma resposta perdida pode corresponder a uma
    # accao concluida no servidor*. Repetir a LEITURA e' de graca; repetir a
    # MUTACAO cobra duas vezes.
    ("o 'ver o desfecho' passa a repetir a MUTACAO", TABS,
     "      async function reverDesfecho() {\n"
     "        if (moralBusy) return;\n"
     "        setMoralBusy(true);\n"
     "        const d = await lerDesfecho();",
     "      async function reverDesfecho() {\n"
     "        if (moralBusy) return;\n"
     "        setMoralBusy(true);\n"
     '        await api("combat/npc_cultivator_resolve", { duel_id: duelId, outcome: "spare" });\n'
     "        const d = await lerDesfecho();",
     "UM sitio so'"),

    # ── 13-14. O DONO DO TEXTO E AS TRES LINGUAS ──────────────────────────
    ("o dono do texto de erro perde o `internal_error`", UI,
     '      internal_error:     "err_server",',
     "",
     "API_ERR_KEY"),

    ("o espanhol perde a frase do 'nao sei'", ES,
     '    "explore_desfecho_incerto"',
     '    "explore_desfecho_incerto_ROTO"',
     "es.json"),

    # ── 15. ⚠️ A PROVA DE QUE AS ASSERTS LEEM O CODIGO E NAO A PROSA ──────
    # Quatro guardas desta casa ja' ficaram verdes por lerem o comentario em vez
    # do codigo. Este ataque poe a frase do titulo num LITERAL: se `_TBC`
    # deixasse de tirar os comentarios, a assert (j) nao daria por isso.
    ("a frase do titulo entra num literal do codigo", TABS,
     "    function MoralErroAviso({ erro }) {",
     '    var _PROSA_FALSA = "A DECISAO QUE NAO SE PERDE";\n'
     "    function MoralErroAviso({ erro }) {",
     "sem comentarios"),

    # ══ §21 — O FACTO QUE DECIDE A MEDITACAO (RETIRADO a 2026-09-22) ═══
    # Os SETE ataques desta seccao morreram com o facto que vigiavam: a
    # sugestao do [jogador] mediu que a trava de combate vivia em 6 portas e
    # faltava em 15+, e ela foi unificada pelo lado permissivo. Nao ha
    # coluna para atacar. O que a substitui vive em `_sabota_o_corpo.py`:
    # uma trava que volte a nascer numa porta sozinha tem de ficar vermelha.

    # ══ §22 — 至 A CHEGADA, e os erros tontos deste lote ══════════════════
    # Cada ataque abaixo repoe um defeito que ESTE lote cometeu e que nenhuma
    # das 880 guardas existentes apanhou. Tres deles so' apareceram A OLHAR.

    # 🔴 O pior: o `/player` TEM um campo `name` que vale None. A tarefa que
    # escrevi listou-o, o Astra implementou-a a' letra, e a chegada saiu SEM
    # NOME com tudo verde.
    ("o nome do jogador volta a ler-se de `player.name`", UI,
     '      const nomeDoJogador = player.dao_name || player.name || "";',
     '      const nomeDoJogador = player.name || "";',
     "NUNCA se le'"),

    # A fronteira que eu desenhei mal: texto fora do i18n nao passa pela
    # guarda de paridade das tres linguas.
    ("a tabela de linguas a mao volta ao componente", UI,
     '        stones: t("chegada_pedras"), jade: t("chegada_jade"),',
     '        pt: { a:1 }, es: { a:1 },\n'
     '        stones: "Pedras", jade: "Jade",',
     "tabela de linguas"),

    # "Existe no ficheiro" nao e' "chega ao ecra" — 5 recorrencias nesta casa.
    # ⚠️ O alvo e' a PRIMEIRA linha da chamada, nao a chamada inteira: ela
    # ganhou props (notifCount/onSino/onLoja/onPerfil) quando o cabecalho
    # recolheu, e um alvo de varias linhas deixou de casar. O runner recusou-se
    # a dar a sabotagem por boa, que e' exactamente o que ele deve fazer.
    ("a cena existe mas deixa de ser renderizada", TABS,
     "        <ChegadaCena p={player} cult={cult} onAgir={agir} atalhos={atalhos} wide={wide}",
     "        <NadaAqui p={player} cult={cult} onAgir={agir} atalhos={atalhos} wide={wide}",
     "RENDERIZA a cena"),

    ("o agregado e a cena deixam de partilhar a condicao", TABS,
     "          {!chegadaOn && (<>",
     "          {true && (<>",
     "MESMA condicao"),

    # A regra do Astra: *ausencia de um campo nao e' estado confirmado*.
    ("um ramo da accao desaparece", TABS,
     '        return { chave:"avanco", rotulo:t("chegada_acao_avanco"),',
     '        return { chave:"nada", rotulo:t("chegada_acao_avanco"),',
     "sao os CINCO"),

    ("o duelo passa a confirmar-se pela AUSENCIA", TABS,
     "      if (acao.duelo && acao.duelo.duel_id) {",
     "      if (!acao.duelo || acao.duelo.duel_id !== null) {",
     "PRESENCA do `duel_id`"),

    ("o avanco aceita um `undefined` como sim", TABS,
     "      if (acao.avanco && acao.avanco.eligible === true) {",
     "      if (acao.avanco && acao.avanco.eligible) {",
     "igualdade estrita"),

    ("a accao promete um botao quando nao sabe nada", TABS,
     '      if (cult && cult.is_meditating === false) {\n'
     '        return { chave:"meditar", rotulo:t("chegada_acao_meditar"),\n'
     '                 porque:t("chegada_porque_meditar"), destino:"cultivation" };\n'
     '      }\n'
     '\n'
     '      return null;',
     '      return { chave:"meditar", rotulo:t("chegada_acao_meditar"),\n'
     '               porque:t("chegada_porque_meditar"), destino:"cultivation" };',
     "devolve `null`"),

    # O COALESCE que ja' inventou "69% dos activos sem poder lutar".
    ("`current_hp` NULL volta a valer zero", TABS,
     "      return (cur === null || cur === undefined) ? max : Number(cur);",
     "      return Number(cur) || 0;",
     "VIDA CHEIA"),

    # 🔴 O defeito que custou a 6ª recorrência de "existe não é chega": a
    # chegada construída numa aba que a navegação do owner nunca abre.
    ("a chegada volta a viver so' na `home`", UI,
     'return (tab === "home" || tab === "hub_eu_screen")',
     'return (tab === "home")',
     "DUAS portas de entrada"),

    ("as duas entradas deixam de partilhar o componente", TABS,
     "            <Chegada player={player} setTab={setTab} wide={_wideHub}",
     "            <ChegadaCopiadaAMao player={player} setTab={setTab} wide={_wideHub}",
     "MESMO componente"),

    # O retoque comparado com o HUB e nao com a TELA: tocar em "Eu" estando na
    # `home` abria um selector invisivel em vez de levar ao landing.
    ("o retoque volta a comparar com o hub activo", UI,
     'if (tab === h.landing && typeof onRetoque === "function")',
     'if (active && typeof onRetoque === "function")',
     "compara com o LANDING"),

    # 🔴 A chave que ENCONTRA a arte. Com a curta, o `pieceArt` devolve `null`
    # em silencio e os dois atalhos ficam sem imagem — modo de falha que a
    # carta virada ao verso esconde por construcao.
    ("o `pieceArt` volta a receber a chave CURTA", TABS,
     '        {_atalho("tecnica", t("chegada_atalho_tecnica"), "sword", "technique",',
     '        {_atalho("tecnica", t("chegada_atalho_tecnica"), "sword", "tech",',
     "chaves LONGAS"),

    ("o servidor deixa de mandar o `art_key` da arma", WEB,
     '                    "art_key": _a[1],          # o CANONICO do catálogo',
     '                    "art_key": None,',
     "`art_key` CANONICO"),

    ("sem equipamento o atalho passa a INVENTAR", TABS,
     '                      : sabido ? t("chegada_atalho_vazio")',
     '                      : sabido ? "Espada Lendaria"',
     # A guarda que o apanha e' a dos TRES estados: a frase do "confirmei
     # que nao ha'" e a do "nao sei" vivem na mesma expressao.
     "estados DIFERENTES"),

    # Os tres acabamentos do selector (Astra, §0 do `e-o-corpo`).
    ("o selector volta a ser uma seccao em FLUXO", TABS,
     "              <Modal open onClose={onFecharSeletor} title={t(\"hub_eu\")}",
     '              <div title={t("hub_eu")}',
     "SOBREPOSICAO"),

    ("o 'Inicio' volta ao selector", TABS,
     '      const pathsSeletor = paths.filter(p => p.key !== "tab_home"',
     "      const pathsSeletor = paths.filter(p => p.key !== \"nada_\"",
     "SETE destinos"),

    ("o VOLTAR nativo volta a fechar o webapp", APP,
     "        || euSeletor;",
     "        ;",
     "janela aberta"),

    # 🔴 O defeito que o owner apanhou A OLHAR: a consulta rebentava e o
    # `except` transformava isso num "Nenhum equipado" — uma AFIRMACAO.
    ("a consulta que rebenta volta a dizer 'nenhum'", TABS,
     '                      : sabido ? t("chegada_atalho_vazio")' + chr(10) +
     '                               : t("chegada_atalho_incerto")}',
     '                      : t("chegada_atalho_vazio")}',
     "estados DIFERENTES"),

    ("a arma volta a achar-se so' pelo `slot`", WEB,
     '                       or_(PlayerArtifact.slot == "weapon",' + chr(13) + chr(10) +
     '                           ArtifactCatalog.type == "weapon"))',
     '                       PlayerArtifact.slot == "weapon")',
     "`type` do catalogo OU"),

    ("os atalhos voltam a nascer com `None` dentro", WEB,
     "        atalhos = {}",
     '        atalhos = {"tecnica": None, "arma": None}',
     "nasce VAZIO"),

    # ══ §23 — o bug do [jogador]: duas superficies, duas regras ═══════════════
    # 🔴 A CAUSA REAL do bug do [jogador]: o `meditate/start` sem a trava. Ele
    # aceitava a Celestial e cobrava 800 Qi a quem ja' tinha as 100 leis.
    # ══ §24 — a lateral do PC ══════════════════════════════════════════
    ("a lateral volta a abrir TODOS os hubs", UI,
     "                {aberto && !recolhida && itens.map(function (td) {",
     "                {!recolhida && itens.map(function (td) {",
     "SO' o hub activo"),

    ("a lateral volta aos 236 px", UI,
     "      const largura = recolhida ? 64 : 216;",
     "      const largura = recolhida ? 64 : 236;",
     "216 px aberta"),

    ("recolhida, os hubs voltam a ser pictogramas mudos", UI,
     "                  aria-label={recolhida ? t(h.label_key) : undefined}",
     "                  aria-label={undefined}",
     "regressao de acessibilidade"),

    ("o `meditate/start` volta a nao ter a trava da Celestial", WEB,
     "        _trava = (await _travas_da_meditacao(session, player, user_id)).get(med_key)",
     "        _trava = None",
     "MESMO dono das travas"),

    ("o catalogo volta a ignorar a trava da Celestial", WEB,
     '            travas["celestial_dao"] = "heavenly_laws_complete"',
     '            pass',
     "DUAS regras"),

    ("a linha volta a ficar escolhivel com a trava do servidor", UI,
     "              var locked = !!r.lock_reason",
     "              var locked = false",
     "TRANCADA"),

    ("o erro da Celestial volta a chegar CRU", UI,
     '      heavenly_laws_complete: "onda_med_err_leis_completas",',
     "",
     "heavenly_laws_complete"),

    ("o espanhol perde uma chave da chegada", ES,
     '    "chegada_proximo_avanco"',
     '    "chegada_proximo_avanco_ROTO"',
     "es.json"),
]


def run():
    falhas = []
    print("=" * 78)
    print("  \U0001fa78 SABOTAGEM da §20 — %d ataques" % len(SABOTAGENS))
    print("=" * 78)
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8", newline="").read()
        # ⚠️ O alvo e' verificado ANTES: uma sabotagem que nunca encontra o que
        # estragar DA-SE POR BOA, e um "15/15 mordem" assim e' um falso verde
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
                              "(esperava %r; veio %r)"
                              % (rot, agulha, (vermelhos[:1] or [""])[0][:90]))
                print("  XX  " + falhas[-1])
        finally:
            io.open(path, "w", encoding="utf-8", newline="").write(orig)
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas),
                                       len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
