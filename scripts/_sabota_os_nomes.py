# -*- coding: utf-8 -*-
"""名 A BATERIA DE SABOTAGEM da §8 — uma guarda que nao morde nao guarda.

Mesmo contrato das cinco irmas (`_sabota_varredor`, `_sabota_o_mapa`,
`_sabota_a_forja`, `_sabota_o_golpe`, `_sabota_o_hp`): cada entrada estraga UMA
coisa no codigo de producao, corre a suite, e exige que ela fique VERMELHA **a
dizer o que e'** — nunca a rebentar, e nunca por um motivo diferente.

⚠️ A suite alvo aqui e' `_test_relatos_0814.py`, que fala outro dialecto do que a
`_test_web_c_superficies.py`: as falhas saem como `FAIL:` e o rodape honesto e'
`passed ·`. Um detector copiado da outra bateria daria falso verde em tudo —
foi a primeira coisa que se verificou, com a anti-guarda la' em baixo.

As licoes de 13/09 que estao mecanizadas aqui:

  · **a guarda le' a PROSA** — duas sabotagens atacam o filtro de comentarios,
    UMA EM CADA DIRECCAO (falha se ele deixar de filtrar; falha se passar a
    apagar codigo). A pior guarda do lote anterior encontrava o seu alvo no
    comentario que explicava a correccao, e ficou verde com a coisa sabotada.
  · **renomear com prefixo comum nao e' sabotar** — ha' duas irmas: uma troca
    `catalog_name` por um nome SEM prefixo comum, a outra por
    `catalog_nameX`, que COMECA por `catalog_name`. A segunda existe so' para
    vigiar a fronteira do `\\b`.
  · **uma sabotagem que parte o parser nao prova nada** — toda a substituicao
    abaixo deixa Python valido; o rodape distingue REBENTOU de VERMELHA.

Uso:  python scripts/_sabota_os_nomes.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ⚠️ As ancoras multi-linha montam-se com este `NL` e NUNCA com um `\n`
# escrito no literal: as ancoras deste ficheiro passam por shells e editores
# que colapsam a barra, e uma ancora partida vira erro de sintaxe (ou, pior,
# uma sabotagem que nao encontra o alvo e se da' por boa).
NL = chr(10)
SUITE = os.path.join(ROOT, "scripts", "_test_relatos_0814.py")
I18N = os.path.join(ROOT, "core", "i18n.py")
AUDIT = os.path.join(ROOT, "scripts", "_audit_nomes_crus.py")
COMBAT = os.path.join(ROOT, "handlers", "combat.py")
INV = os.path.join(ROOT, "handlers", "inventory.py")
QUESTS = os.path.join(ROOT, "handlers", "quests.py")
BOSS = os.path.join(ROOT, "core", "boss_engine.py")
BEAST = os.path.join(ROOT, "core", "beast_engine.py")
HBEAST = os.path.join(ROOT, "handlers", "beasts.py")
WS = os.path.join(ROOT, "core", "webserver.py")
SECTLIB = os.path.join(ROOT, "core", "sect_library_engine.py")
PT = os.path.join(ROOT, "locales", "pt.json")
EN = os.path.join(ROOT, "locales", "en.json")
ES = os.path.join(ROOT, "locales", "es.json")

# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    # ── 8.1 a CATRACA: volta um nome cru a producao ──────────────────────
    ("volta o nome cru da arte ao chat (1 sitio)", COMBAT,
     "f\"{tech.emoji} *{_cname(lang, 'tech', tech)}*\",",
     "f\"{tech.emoji} *{tech.name}*\",",
     "CATRACA"),

    ("volta o nome cru da pilula a' mochila", INV,
     "lines.append(f\"{pill.emoji} *{_cname(lang, 'pill', pill)}*{timed_tag}{quality_tag} ×{inv.quantity}\")",
     "lines.append(f\"{pill.emoji} *{pill.name}*{timed_tag}{quality_tag} ×{inv.quantity}\")",
     "CATRACA"),

    ("volta o nome cru da MISSAO (a captura do owner)", QUESTS,
     "\"title\": f\"{quest.emoji} *{_cname(player_lang, 'q', quest)}*\" if quest else \"\",",
     "\"title\": f\"{quest.emoji} *{quest.name}*\" if quest else \"\",",
     "CATRACA"),

    ("volta o nome cru do CHEFE (a captura do owner)", BOSS,
     "safe_name = escape_markdown(catalog_name(lang, \"boss\", boss))",
     "safe_name = escape_markdown(boss.name)",
     "CATRACA"),

    # ── 8.3 UM DONO: alguem volta a montar a chave a' mao ────────────────
    ("alguem volta a montar a chave `tech_<id>_name` a' mao", SECTLIB,
     "    from core.i18n import catalog_name\n    return catalog_name(lang, \"tech\", tech)",
     "    from core.i18n import t_optional\n    return t_optional(lang, f\"tech_{tech.id}_name\", tech.name)",
     "UM DONO"),

    # ── 8.4 a lingua tem de estar LIGADA ─────────────────────────────────
    #
    # 🔴 2026-09-15 — ESTAS DUAS SAO IRMAS E A SEGUNDA E' A QUE IMPORTA.
    # A primeira usa `idioma_que_nao_existe`: um nome que nao esta' ligado em
    # sitio NENHUM do ficheiro. A guarda apanhava-o mesmo estando CEGA, e por
    # isso este 8.4 esteve verde o tempo todo — sobre o caso facil.
    # O caso REAL e' o de baixo: `lang` esta' ligado em SEIS funcoes IRMAS do
    # mesmo ficheiro, e o colector de escopo colhia todo o `Store` da arvore
    # inteira como se fosse de modulo. Medido: `_claim_quest` rebentou com
    # `NameError` na mao de 3 jogadores, 7 vezes em 2 dias, com esta bateria a
    # dizer 24/24 e a suite a dizer VERDE.
    # Uma sabotagem so' vale o caso que ela consegue distinguir.
    ("uma chamada ao resolvedor com `lang` NAO ligado", INV,
     "lines.append(f\"{herb.emoji} *{_cname(lang, 'herb', herb)}* ×{inv.quantity}\")",
     "lines.append(f\"{herb.emoji} *{_cname(idioma_que_nao_existe, 'herb', herb)}* ×{inv.quantity}\")",
     "lingua ligada"),

    ("`lang` ligado numa funcao IRMA, nao NESTA (o caso de producao)", QUESTS,
     "\"title\": f\"{quest.emoji} *{_cname(player_lang, 'q', quest)}*\" if quest else \"\",",
     "\"title\": f\"{quest.emoji} *{_cname(lang, 'q', quest)}*\" if quest else \"\",",
     "lingua ligada"),

    # ── 8.5 PARIDADE: uma chave so' numa lingua ──────────────────────────
    # ⚠️ Esta e' a mais importante das nove: `t_optional` cai no locale POR
    # OMISSAO (pt) antes de cair no cru, portanto uma chave que exista so' em
    # `pt.json` faz um jogador EN ler PORTUGUES — pior do que o ingles cru.
    ("apaga uma chave so' do `en.json` (jogador EN leria pt)", EN,
     '    "art_8_name": "Heaven\'s Edge",\n', "",
     "mesmas chaves de catalogo"),

    # ── 8.6 FAMILIA INTEIRA: meia familia mistura duas linguas no ecra ───
    ("apaga uma peca do meio da familia `pill`", PT,
     '    "pill_27_name": "Pílula de Cura Menor",\n', "",
     "INTEIRA"),

    ("apaga uma peca do meio da familia `art`", PT,
     '    "art_8_name": "Fio do Céu",\n', "",
     "INTEIRA"),

    # ── 8.7 o SLUG do chefe ──────────────────────────────────────────────
    ("o slug do chefe deixa de colapsar o traco", I18N,
     'return _re.sub(r"_+", "_", _re.sub(r"[^a-z0-9]+", "_", (text or "").lower())).strip("_")',
     'return (text or "").lower().replace(" ", "_")',
     "slug"),

    # ── 8.8 a captura do owner, ponta a ponta ────────────────────────────
    # ⚠️ a ancora desta mudou a 15/09 quando `exped` entrou no conjunto: a
    # correccao de uma familia DESARMA a sabotagem da irma, em silencio, e o
    # runner so' o diz porque verifica o alvo ANTES de estragar.
    ("o `boss` deixa de se indexar pelo slug e volta ao id", I18N,
     '_KEYED_BY_SLUG = {"boss", "exped"}',
     '_KEYED_BY_SLUG = {"exped"}',
     "captura do owner"),

    ("o EN deixa de ser identico (os 112 sentiriam)", EN,
     '    "boss_void_beast_name": "Void Beast",',
     '    "boss_void_beast_name": "Bestia del Vacio",',
     "IDENTICO em en"),

    # ── 8.9 pt.json e' BRASILEIRO ────────────────────────────────────────
    ("mete um europeismo numa chave nova de pt", PT,
     '    "art_8_desc": "Espada que o raio celeste tocou.',
     '    "art_8_desc": "O ecrã está a mostrar. Espada que o raio celeste tocou.',
     "BRASILEIRO"),

    # ── 🔴 O FILTRO DE PROSA, NAS DUAS DIRECCOES ─────────────────────────
    # A licao de 13/09, paga duas vezes no mesmo lote: uma guarda encontrou o
    # seu alvo no COMENTARIO que explicava a correccao e ficou verde com a
    # coisa sabotada. Se o filtro deixar de filtrar, a §8.3 passa a encontrar
    # `t_optional(lang, f"tech_{` dentro dos comentarios que o citam — e fica
    # vermelha sem ninguem ter partido nada. Se passar a apagar codigo, a
    # catraca ve' zero em todo o lado e fica verde para sempre.
    ("o filtro de comentarios DEIXA DE FILTRAR", AUDIT,
     "            elif ch == \"#\":\n                cut = i\n                break",
     "            elif ch == \"#\":\n                pass",
     None),

    ("o filtro de comentarios passa a APAGAR CODIGO", AUDIT,
     "        if cut is not None:\n            s = s[:cut]\n        out.append(s)",
     "        if cut is not None:\n            s = s[:cut]\n        out.append(\"\")",
     None),

    # ── 🔴 O RESOLVEDOR DEIXA DE RESOLVER, sem partir nada ───────────────
    # ⚠️ A primeira versao destas duas RENOMEAVA o `catalog_name`, e as duas
    # REBENTARAM a suite em vez de a por vermelha — o que nao prova nada sobre
    # a guarda (licao 5 de 13/09). Renomear a definicao parte os imports de 20
    # ficheiros: e' um erro de sintaxe com outro nome. Estas duas fazem o que
    # aquelas queriam fazer — o resolvedor passa a MENTIR — sem tocar na forma.
    ("o resolvedor devolve sempre o nome CRU", I18N,
     "    raw = getattr(row, \"name\", None) or fallback\n"
     "    return catalog_text(lang, kind, _catalog_key_part(kind, row), \"name\", raw)",
     "    raw = getattr(row, \"name\", None) or fallback\n"
     "    return raw",
     "captura do owner"),

    ("a descricao passa a resolver pela chave do NOME", I18N,
     "    raw = getattr(row, \"description\", None) or fallback\n"
     "    return catalog_text(lang, kind, _catalog_key_part(kind, row), \"desc\", raw)",
     "    raw = getattr(row, \"description\", None) or fallback\n"
     "    return catalog_text(lang, kind, _catalog_key_part(kind, row), \"name\", raw)",
     None),

    # ═══ 獸 8.11 — A FAMILIA BESTA (2026-09-15) ════════════════════════════
    #
    # ⚠️ A primeira destas e' a que importa, e e' a razao de a §8.11 existir: a
    # catraca geral (8.1) NAO VE esta familia. Se esta sabotagem ficasse verde,
    # a familia inteira estaria fora de qualquer medicao.
    ("volta o nome cru da besta ao chat (o botao da lista)", HBEAST,
     "                name = beast_display_name(lang, b, c)" + NL
     + "                short = f\"{emoji} {name}\"",
     "                name = b.custom_name or (c.name if c else \"???\")" + NL
     + "                short = f\"{emoji} {name}\"",
     "8.11"),

    ("volta o nome cru da besta ao CATALOGO (o que se captura)", HBEAST,
     "        lines.append(f\"{c.emoji} *{beast_display_name(lang, None, c)}* — {c.rank}\")",
     "        lines.append(f\"{c.emoji} *{c.name}* — {c.rank}\")",
     "8.11"),

    # 🔴 A RAIZ. Voltar a gravar na captura tranca cada besta NOVA na lingua em
    # que foi apanhada — e nao muda uma unica linha das telas, portanto nenhuma
    # guarda de FORMA a apanharia.
    ("a captura volta a gravar `custom_name`", BEAST,
     "        level=1," + NL + "        exp=0," + NL + "    )" + NL
     + "    session.add(new_beast)",
     "        custom_name=catalog.name," + NL + "        level=1," + NL
     + "        exp=0," + NL + "    )" + NL + "    session.add(new_beast)",
     "8.11"),

    # ⚠️ A SEMANTICA, e e' a sabotagem que separa este lote do plano que o
    # prompt trazia: tratar `custom_name == catalog.name` como nome escolhido
    # deixa as 1170 linhas de producao em ingles para sempre, e NAO parte forma
    # nenhuma — o codigo continua bonito e nenhum jogador vivo ve a traducao.
    ("o resolvedor passa a respeitar a copia da captura", BEAST,
     "    if escolhido and escolhido != raw:" + NL + "        return escolhido",
     "    if escolhido:" + NL + "        return escolhido",
     "producao"),

    # ⚠️ E o inverso: apagar o ramo do nome escolhido apaga o nome que um
    # jogador deu a' besta. Hoje sao zero linhas; no dia do botao de renomear
    # seria perda de dados, silenciosa.
    ("o resolvedor deixa de respeitar o nome ESCOLHIDO", BEAST,
     "    if escolhido and escolhido != raw:" + NL + "        return escolhido",
     "    if False:" + NL + "        return escolhido",
     "ESCOLHIDO"),

    # 🔴 A ARTE. Sem a chave, traduzir os 15 nomes apaga as 15 pecas em pt e es
    # — sem erro nenhum, porque o verso da carta e' um estado legitimo.
    ("o payload da besta deixa de mandar a chave da arte", WS,
     "            \"art_key\": beast_art_key(cat),",
     "            \"emoji_dummy_art_key\": beast_art_key(cat),",
     "art_key"),

    # ═══ 旅 8.12 — A FAMILIA EXPEDICAO (2026-09-15) ═══════════════════════
    #
    # ⚠️ A catraca geral (8.1) tambem NAO VE esta familia, e desta vez foi
    # provado por construcao: pos-se `ExpeditionCatalog` no `CATALOG_MODELS` e
    # o total ficou 0. O nome cru vem de uma COLUNA DE TEXTO e de um segundo
    # salto que o dataflow-lite nao segue. Sem estas sabotagens, o §8.12 seria
    # uma seccao que ninguem sabe se olha para alguma coisa.
    ("volta o nome cru da expedicao ao badge da lista", HBEAST,
     'escape_markdown(_exp_name(lang, b.expedition_type))',
     "escape_markdown(b.expedition_type)",
     "8.12"),

    ("volta o nome cru da expedicao a LINHA da escolha", HBEAST,
     "*{escape_markdown(_exp_name(lang, exp))}*",
     "*{escape_markdown(exp.name)}*",
     "8.12"),

    # 🔴 A que o prompt NAO previa: a descricao. O prompt contava 5 sitios, a
    # minha contagem 9, e foi o §8.12 a correr que achou o 10o.
    ("volta a descricao crua da expedicao ao chat", HBEAST,
     "escape_markdown(_exp_desc(lang, exp)[:50])",
     "escape_markdown(exp.description[:50])",
     "8.12"),

    ("volta o nome cru da expedicao a API do mini-app", WS,
     '"expedition_name": _exp_name_ws(_lang_exp, b.expedition_type),',
     '"expedition_name": b.expedition_type,',
     "8.12"),

    # 🔴 A MAIS PERIGOSA DAS OITO, e nao parte tela nenhuma: se a CONSULTA
    # passar a casar pelo nome traduzido, recolher uma expedicao deixa de
    # achar a linha e o jogador PERDE o espolio — em silencio, e so' em pt/es.
    # Existe para que o proximo a passar por aqui nao 'melhore' isto.
    ("a CONSULTA passa a casar pelo nome TRADUZIDO", BEAST,
     "select(ExpeditionCatalog).where(ExpeditionCatalog.name == exp_name)",
     "select(ExpeditionCatalog).where(ExpeditionCatalog.id == exp_name)",
     "CANONICO"),

    ("a GRAVACAO passa a guardar o nome traduzido", BEAST,
     "beast.expedition_type = expedition.name",
     "beast.expedition_type = expedition.description",
     "CANONICO"),

    ("`exped` sai do _KEYED_BY_SLUG (a chave pediria um id)", I18N,
     '_KEYED_BY_SLUG = {"boss", "exped"}',
     '_KEYED_BY_SLUG = {"boss"}',
     "SLUG"),

    ("apaga uma expedicao do meio da familia (so' em es)", ES,
     '  "exped_demon_wastes_name": "Yermos Demoníacos",',
     "",
     "INTEIRA"),

    ("traduz o nome em `en` (o canonico deixa de bater)", EN,
     '  "exped_ancient_ruins_name": "Ancient Ruins",',
     '  "exped_ancient_ruins_name": "Olde Ruins",',
     "IDENTICO ao canonico"),

    ("a chave da arte passa a ser o nome TRADUZIDO", BEAST,
     "def beast_art_key(catalog) -> str:",
     "def beast_art_key(catalog, _x=None) -> str:" + NL
     + '    return beast_display_name("pt", None, catalog)',
     "CANONICO"),
]


def run() -> int:
    falhas = []
    print("=" * 74)
    print("  名 SABOTAGEM da §8 — a guarda do nome so' vale se morder")
    print("=" * 74)
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8", newline="").read()
        # ⚠️ 3ª VEZ EM 3 LOTES QUE O ARNES MENTE ANTES DO CODIGO.
        # Estes ficheiros estao gravados em CRLF, e `newline=""` preserva-o —
        # portanto TODA ancora multi-linha escrita com `\n` falhava com
        # "ALVO NAO ENCONTRADO", e 6 das 17 sabotagens davam-se por boas sem
        # nunca terem estragado nada. O erro era da bateria, nao da guarda.
        # Aqui tenta-se a ancora tal como esta' e, se nao casar, com CRLF.
        if orig.count(de) != 1 and orig.count(de.replace("\n", "\r\n")) == 1:
            de, para = de.replace("\n", "\r\n"), para.replace("\n", "\r\n")
        # O alvo e' verificado ANTES: uma sabotagem que nunca encontra o que
        # estragar DA-SE POR BOA, e um "17/17 mordem" assim e' um falso verde
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
                capture_output=True, text=True, env=env, cwd=ROOT, timeout=600,
                # ⚠️ `text=True` sozinho descodifica com o codec do LOCALE
                # (cp1252 no Windows) e rebenta no primeiro 漢字 da suite.
                encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.stderr or "")
            # ⚠️ O dialecto desta suite: falhas sao `FAIL:`, rodape e' `passed ·`.
            vermelhos = [l for l in saida.split("\n") if "FAIL:" in l]
            rebentou = "passed" not in saida
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
