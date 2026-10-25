# -*- coding: utf-8 -*-
"""⚒️ A BATERIA DE SABOTAGEM da §17 — uma guarda que nao morde nao guarda.

Cada entrada estraga UMA coisa no codigo de producao, corre
`_test_web_c_superficies.py`, e exige que ele fique VERMELHO — e que fique
vermelho A DIZER O QUE E' (a mensagem tem de conter a agulha), nunca a rebentar.

As licoes desta casa estao assadas no `run()` abaixo, e sao as mesmas do
`_sabota_o_mapa.py` (o runner e' irmao dele de proposito):

  · **Uma guarda que REBENTA nao e' uma guarda vermelha.** Exige-se codigo de
    saida 1 com asserts vermelhos, nunca um traceback. E o sinal de "chegou ao
    fim" e' o RODAPE, porque a propria suite acende um traceback de proposito.
  · **Uma sabotagem que nunca encontra o alvo da-se por boa.** Cada alvo e'
    verificado ANTES; se a string nao existir, a sabotagem falha aqui, ruidosa.
  · **`text=True` sozinho rebenta no primeiro 漢字** (codec do locale). Daqui o
    `encoding="utf-8", errors="replace"`.

E ha' uma lição nova, desta sessao, que vale a pena ficar escrita: **duas das
guardas que eu proprio escrevi nasceram erradas** — a do glifo lia a PROSA que
explicava porque' o glifo foi morto (o comentario continha o ✧ que ela proibia),
e a da migration acusava `028_forge_mastery.sql`, de 2024, por a palavra
"forge" lhe aparecer no nome. As duas estavam certas sobre a coisa errada. Foi
correr isto que as apanhou.

Uso:  python scripts/_sabota_a_forja.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")

# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    # ── A CAUSA MEDIDA: a grelha com a medida do quadrado antigo ────────────
    ("a grelha volta aos 54px no ramo das cartas", TABS,
     "                      ? `repeat(auto-fill, minmax(${FORGE_RESULT_CARD_MIN}px, 1fr))`",
     '                      ? "repeat(auto-fit, minmax(54px, 1fr))"',
     "medida NOVA"),

    ("a coluna minima desce para onde o nome parte", TABS,
     "var FORGE_RESULT_CARD_MIN = 104;",
     "var FORGE_RESULT_CARD_MIN = 63; ",
     ">=96px"),

    # ── ⚠️ A OFF-IDENTIDADE: o que protege os 57 do `main` ──────────────────
    ("a medida nova escapa do ternario (OFF muda)", TABS,
     "                    gridTemplateColumns: cardsOn\n"
     "                      ? `repeat(auto-fill, minmax(${FORGE_RESULT_CARD_MIN}px, 1fr))`\n"
     '                      : "repeat(auto-fit, minmax(54px, 1fr))",',
     "                    gridTemplateColumns: `repeat(auto-fill, minmax(${FORGE_RESULT_CARD_MIN}px, 1fr))`,",
     "byte a byte"),

    ("a lista densa deixa de olhar a' flag", TABS,
     ") : cardsOn && sortedArts.length >= FORGE_RESULT_LIST_FROM ? (",
     ") : sortedArts.length >= FORGE_RESULT_LIST_FROM ? (",
     "ramo onde a avaria nasceu"),

    # ── O LIMIAR ────────────────────────────────────────────────────────────
    ("o limiar sobe para depois do 50 (nunca dispara)", TABS,
     "var FORGE_RESULT_LIST_FROM = 10;",
     "var FORGE_RESULT_LIST_FROM = 99;",
     "limiar declarado"),

    # ── ⚠️ A LISTA NAO PODE PERDER FUNCAO (trocar parede por beco) ──────────
    ("a lista densa perde o reciclar", TABS,
     '                                onClick={(e) => { e.stopPropagation(); toggleSelect(a.id); }}\n'
     '                                aria-label={t("forge_recycle_toggle")}',
     '                                aria-label={t("forge_recycle_toggle")}',
     "escolher para reciclar"),

    ("a lista densa perde o cadeado", TABS,
     "                                onClick={(e) => { e.stopPropagation(); toggleLock(a); }}\n"
     "                                aria-label={t(a.locked ? \"inv_unlock_btn\" : \"inv_lock_btn\")}",
     "                                aria-label={t(a.locked ? \"inv_unlock_btn\" : \"inv_lock_btn\")}",
     "trancar/destrancar"),

    ("a lista densa deixa de paginar", TABS,
     "{sortedArts.slice(0, listLimit).map(a => {",
     "{sortedArts.map(a => {",
     "corta em `listLimit`"),

    # ── ⚠️ A CATRACA DO EMOJI, no sitio onde eles nascem ───────────────────
    ("o cadeado sai da porta e volta a emoji cru", TABS,
     '                                {a.locked ? ico("🔒", "lock", { size:11 })\n'
     '                                          : ico("🔓", "lock", { size:11 })}',
     '                                {a.locked ? "🔒" : "🔓"}',
     "passa pela porta"),

    ("o espirito volta a ser um ✧", TABS,
     "                                {t(ART_QUALITY_KEY.spirit || \"art_quality_spirit\")}",
     # ⚠️ o CARACTER, nao o escape. A 1a versao escrevia `✧` como texto no
     # codigo-fonte e a guarda — que procura o glifo — nunca o via: a sabotagem
     # dava-se por boa sem ter feito o estrago que anuncia.
     "                                {\"✧\"}",
     "por palavra"),

    # ── ⚠️ NAO DESFAZER O 器 O ITEM VIVO ───────────────────────────────────
    ("alguem 'arruma' a grelha pintada toda", TABS,
     "                          <ArtifactCell a={a}\n",
     "                          <span>{a.name}</span>{false && <ArtifactCellX a={a}\n",
     "CONTINUA a ser desenhada"),

    # ── ⚠️ A ALQUIMIA: o outro lado da Lei F-7 ─────────────────────────────
    ("alguem poe cartas no lote da alquimia", TABS,
     '                ✅ {t("bulk_pills_added", { n: totalGood })}',
     '                <ArtifactCell a={{}} /> {t("bulk_pills_added", { n: totalGood })}',
     "SO' o resumo"),

    ("o resumo da alquimia deixa de dizer quantas", TABS,
     '{t("bulk_pills_added", { n: totalGood })}',
     "{totalGood}",
     "diz quantas entraram"),

    # ── ⚠️ AS ANTI-GUARDAS: se o localizador falhar, tudo o que vem a seguir
    #     compara conjuntos vazios, e um tecto sobre o vazio e' verde eterno.
    ("o localizador perde a funcao do resultado", TABS,
     # ⚠️ o nome novo NAO pode partilhar prefixo: `ForgeResultModalX` continuava
     # a casar com `function ForgeResultModal(`... — na verdade nao casa, porque
     # o localizador pede o parentesis. Mas o `ForgeResultModal2(` casaria com
     # um `find` mais frouxo, e amanha alguem afrouxa-o. Muda-se o nome inteiro.
     "function ForgeResultModal({ result, onClose, onPlayerRefresh }) {",
     "function ModalDoResultado({ result, onClose, onPlayerRefresh }) {",
     ""),

    # ⚠️ A fatia da lista densa vai do inicio do ramo ate' ao ramo seguinte. Se
    #    o fim deixar de se encontrar, ela passa a ser a funcao TODA — e as
    #    guardas de "a lista nao perdeu funcao" ficam verdes por estarem a ler a
    #    GRELHA, que sempre teve cadeado e seleccao. E' o mesmo erro do tecto
    #    sobre o conjunto vazio, com outra roupa.
    ("a fatia da lista densa vira a funcao inteira", TABS,
     "                ) : (\n"
     "                  <div style={{\n"
     '                    display:"grid",',
     "                ) :   (\n"
     "                  <div style={{\n"
     '                    display:"grid",',
     "e' uma PARTE do modal"),
]


def run():
    falhas = []
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8").read()
        if orig.count(de) != 1:
            falhas.append("%-46s ALVO NAO ENCONTRADO (%d ocorrencias) — a "
                          "sabotagem dava-se por boa sem nunca ter corrido"
                          % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        io.open(path, "w", encoding="utf-8", newline="").write(
            orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run(
                [sys.executable,
                 os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")],
                capture_output=True, text=True, env=env, cwd=ROOT, timeout=600,
                encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split("\n") if l.strip().startswith("x ")]
            rebentou = "asserts verdes" not in saida
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and (not agulha
                                  or any(agulha in l for l in vermelhos))
            if acertou:
                print("  ok  %-46s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-46s REBENTOU — uma guarda que rebenta nao e' "
                              "uma guarda vermelha" % rot)
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-46s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-46s ficou vermelha pelo motivo ERRADO "
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
