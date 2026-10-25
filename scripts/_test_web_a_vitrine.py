# -*- coding: utf-8 -*-
"""WEB-A 展 A Vitrine (2026-08-19) — a porta pública, sem Telegram e sem conta.

Roda: python -X utf8 scripts/_test_web_a_vitrine.py

O que este teste protege, por ordem de gravidade:

  1. **A ALLOWLIST NÃO PODE ESCORREGAR.** O RECON avisou: "a lista tem de ser
     allowlist explícita, nunca 'tudo o que não escreve'". Aqui isso é medido
     nos dois sentidos — todo o caminho `/api/vitrine/*` registado tem de estar
     em `VITRINE_PUBLIC_PATHS`, e todo o caminho na lista tem de existir. Um
     endpoint público que ninguém declarou, ou uma declaração sem endpoint,
     partem o teste.
  2. **Os 261 endpoints do jogo continuam fechados.** Sem `init_data` válido,
     `/api/miniapp/*` responde 401 — e não existe caminho da vitrine até eles.
  3. **A vitrine NÃO ESCREVE.** Nenhum `commit`, nenhum `session.add`, nenhum
     `INSERT/UPDATE/DELETE` no módulo. Com 240 jogadores reais atrás, uma
     escrita numa superfície anónima seria a pior falha possível.
  4. **Nenhum `username` do Telegram é publicado.** O `api_leaderboard` cai para
     `Player.username` quando `dao_name` é NULL; numa página aberta isso
     publicaria o @handle de quem nunca escolheu um nome do Dao.
  5. **`shadow_mode` continua a valer** — quem escolheu a sombra não aparece.
  6. **Limitação por IP** — a página pública não tem `user_id` para limitar.
  7. **O mundo é ligado E RESETADO** — um ContextVar que vaze serve o mundo
     errado ao pedido seguinte (o `finally` do middleware existe para isso).
  8. **Lei §1: mesmo com TUDO em baixo há caminho.** Com a base inalcançável a
     resposta tem de continuar 200 com o convite.
  9. **i18n**: paridade nas 3 línguas, mesmos placeholders, PT-BR sem grafia
     europeia — e TODA key que a página usa existe (uma key a faltar não
     rebenta: desenha um rótulo VAZIO, que é pior).
 10. **A Crônica não se repete nem duplica emoji** — as duas correcções que só
     apareceram ao IMPRIMIR o que o visitante vê.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Molde _test_relatos_0818: alguns engines re-exportam core.utils, que importa
# `telegram`. Stub mínimo — este teste não fala com a rede do bot.
if "telegram" not in sys.modules:
    _tg = types.ModuleType("telegram")
    _tg.Update = object
    _errmod = types.ModuleType("telegram.error")

    class _TgErr(Exception):
        retry_after = 0

    _errmod.RetryAfter = _errmod.TimedOut = _errmod.NetworkError = _errmod.BadRequest = _TgErr
    _tg.error = _errmod
    sys.modules["telegram"] = _tg
    sys.modules["telegram.error"] = _errmod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK = 0
FAIL: list[str] = []


def chk(cond: bool, label: str) -> bool:
    global OK
    if cond:
        OK += 1
        print("  ok  " + label)
    else:
        FAIL.append(label)
        print("  XX  " + label)
    return bool(cond)


def rd(rel: str) -> str:
    with io.open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


# ══════════════════════════════════════════════════════════════════════════
print("\n=== 1. A allowlist: nos DOIS sentidos ===")
import core.webserver as W
from core import vitrine as V

app = W.create_app()
registered = sorted({
    r.resource.canonical for r in app.router.routes()
    if getattr(r, "resource", None) is not None
    and str(r.resource.canonical).startswith("/api/vitrine/")
})
chk(registered == sorted(W.VITRINE_PUBLIC_PATHS),
    "rotas /api/vitrine/* == VITRINE_PUBLIC_PATHS (%s)" % registered)
chk(len(W.VITRINE_PUBLIC_PATHS) >= 1, "a lista não está vazia")
chk(all(p.startswith("/api/vitrine/") for p in W.VITRINE_PUBLIC_PATHS),
    "nenhum caminho público fora do prefixo /api/vitrine/")
chk(not any(p.startswith("/api/miniapp/") for p in W.VITRINE_PUBLIC_PATHS),
    "NENHUM /api/miniapp/* na allowlist pública")

print("\n=== 2. A vitrine não escreve ===")
src = rd("core/vitrine.py")


def _code_only(text: str) -> str:
    """O ficheiro SEM comentários e SEM docstrings. Este módulo documenta em
    prosa exactamente o que promete não fazer (`Player.username`, `commit`) —
    procurar essas palavras no ficheiro cru daria vermelho pela documentação."""
    import ast
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and ast.get_docstring(node):
            node.body = node.body[1:]
    return ast.unparse(tree)


body = _code_only(src)
for bad in ("session.commit", "session.add(", "session.delete(",
            "flush(", "INSERT ", "UPDATE ", "DELETE "):
    chk(bad not in body, "core/vitrine.py sem `%s`" % bad.strip())
chk("await session.rollback()" in body, "o build faz rollback explícito")

print("\n=== 3. Privacidade: sem @handle, com shadow_mode ===")
chk("username" not in body, "core/vitrine.py nunca lê Player.username")
chk("shadow_mode == False" in body, "a escada filtra shadow_mode")
chk("dao_name" in body, "a escada lê dao_name")
chk("vit_ladder_anon" in body, "quem não tem nome do Dao recebe o rótulo genérico")

print("\n=== 4. Limites são do servidor, nunca do cliente ===")
chk(V.LADDER_LIMIT <= 50 and V.CHRONICLE_LIMIT <= 40,
    "tectos sãos (escada %d, crônica %d)" % (V.LADDER_LIMIT, V.CHRONICLE_LIMIT))
handler_src = rd("core/webserver.py")
seg = handler_src.split("async def api_vitrine_world", 1)[1].split("\nasync def ", 1)[0]
params = set(re.findall(r'request\.query\.get\("(\w+)"\)', seg))
# ⚠️ 2026-09-04 (FORMA): o handler deixou de ler o `?lang=` À MÃO e passou a
# delegar em `public_lang(request)` — o helper único que dá a língua a TODA
# superfície pública (a porta, as páginas legais, a vitrine) por ordem de
# autoridade: `?lang=` > cookie `nv_lang` > Accept-Language > inglês.
#
# A garantia que este bloco protege NÃO mudou: **o visitante não controla nada
# a não ser a língua.** Mudou onde isso se lê. Baixar o assert para "veio
# set(), passa" teria MATADO a guarda — um `request.query.get` novo entraria em
# silêncio amanhã. Em vez disso a guarda SEGUE a indirecção e passou a cobrir
# também o helper, que é onde o parâmetro agora vive.
if params:
    chk(params == {"lang"}, "o visitante só controla `lang` (veio %s)" % params)
else:
    chk("public_lang(request)" in seg,
        "sem leitura directa da query, o handler delega em public_lang(request)")
    hseg = handler_src.split("def public_lang(", 1)[1].split("\ndef ", 1)[0]
    hparams = set(re.findall(r'request\.query\.get\("(\w+)"\)', hseg))
    chk(hparams == {"lang"},
        "public_lang só lê `lang` da query (veio %s)" % hparams)
    hcookies = set(re.findall(r'request\.cookies\.get\(([A-Za-z_]+|"\w+")\)', hseg))
    chk(hcookies == {"LANG_COOKIE_NAME"},
        "public_lang só lê o cookie de língua (veio %s)" % hcookies)
    chk('LANG_COOKIE_NAME = "nv_lang"' in handler_src,
        "o cookie de língua chama-se nv_lang")

print("\n=== 5. normalize_lang ===")
# ⚠️ O DEFAULT das superfícies PÚBLICAS passou de `pt` para `en` a 2026-08-26
# (owner: *"quero global, quero inglês"*). O que NÃO mudou: a normalização em
# si, e a língua de quem TEM conta — essa vem de `player.language` via
# `core.utils.normalize_lang`, que continua exactamente como estava.
cases = [("pt", "pt"), ("pt-BR", "pt"), ("PT_br", "pt"), ("en-US", "en"),
         ("es-419", "es"), ("de", "en"), ("", "en"), (None, "en"),
         ("../../etc", "en"), ("en; drop", "en")]
for raw, want in cases:
    got = V.normalize_lang(raw)
    chk(got == want, "normalize_lang(%r) -> %r" % (raw, got))
chk(V.normalize_lang(None, default="pt") == "pt",
    "o default continua parametrizável (não é um literal enterrado)")
chk(V.PUBLIC_DEFAULT_LANG == "en", "o default público da casa é o inglês")

# `parse_accept_language` respeita o `q=`. A versão antiga do `serve_web_login`
# fazia `.split(",")[0]` e lia só o 1º tag: um `de,en;q=0.9` caía no default em
# vez de cair em inglês. Este bloco existe para isso não voltar.
for hdr, want in [("pt-BR,pt;q=0.9,en;q=0.8", "pt"), ("es-419,es;q=0.9", "es"),
                  ("en-US,en;q=0.9", "en"), ("sv-SE,sv;q=0.9", None),
                  ("de,en;q=0.9", "en"), ("de,pt;q=0.9,en;q=0.4", "pt"),
                  ("pt;q=0,en;q=0.1", "en"), (";;;lixo,,,", None),
                  ("", None), (None, None)]:
    got = V.parse_accept_language(hdr)
    chk(got == want, "parse_accept_language(%r) -> %r" % (hdr, got))

# A ordem de autoridade: `?lang=` > browser > inglês.
chk(V.pick_public_lang("pt", "en-US") == "pt", "`?lang=` explícito ganha do browser")
chk(V.pick_public_lang(None, "pt-BR,pt;q=0.9") == "pt",
    "um brasileiro cai em português SEM clicar em nada")
chk(V.pick_public_lang(None, "sv-SE") == "en",
    "um sueco cai em INGLÊS — nunca mais em português por acidente")
chk(V.pick_public_lang(None, None) == "en", "sem pistas nenhumas: inglês")
chk(V.pick_public_lang("xx", "pt-BR") == "pt",
    "`?lang=` inválido cai no browser, não no default")

print("\n=== 6. A Crônica: sem repetição e sem emoji a dobrar ===")


class _FakeSession:
    pass


def _rows(n_recluse=7):
    out = []
    for i in range(n_recluse):
        out.append({"event_type": "sect_seclusion", "icon": "🛡️",
                    "sect_emoji": "☁️", "text": "Casa %d recolhe-se." % i, "ts_ms": 1})
    out.append({"event_type": "sky_turn", "icon": "📜", "sect_emoji": None,
                "text": "⛅ O céu se abriu.", "ts_ms": 2})
    out.append({"event_type": "jh_march", "icon": "📜", "sect_emoji": None,
                "text": "🚩 Alguém marcha.", "ts_ms": 3})
    out.append({"event_type": "sect_raid", "icon": "⚔️", "sect_emoji": "☀️",
                "text": "Sol Ardente saqueou.", "ts_ms": 4})
    return out


async def _fake_list(session, *, limit, lang, continent=None, viewer_continent=None):
    return _rows()


_orig_wp = sys.modules.get("core.world_pulse_engine")
_stub = types.ModuleType("core.world_pulse_engine")
_stub.list_recent_chronicle = _fake_list
sys.modules["core.world_pulse_engine"] = _stub
try:
    chron = asyncio.run(V._chronicle(_FakeSession(), "pt"))
finally:
    if _orig_wp is not None:
        sys.modules["core.world_pulse_engine"] = _orig_wp
    else:
        sys.modules.pop("core.world_pulse_engine", None)

types_seen: dict[str, int] = {}
for e in chron:
    pass
chk(len(chron) <= V.CHRONICLE_LIMIT, "a crônica respeita o tecto (%d)" % len(chron))
recluse = [e for e in chron if "recolhe-se" in e["text"]]
chk(len(recluse) <= V._CHRON_MAX_PER_TYPE,
    "no máximo %d linhas do mesmo tipo (vieram %d de 7)" % (V._CHRON_MAX_PER_TYPE, len(recluse)))
sky_line = [e for e in chron if e["text"].startswith("⛅")]
chk(sky_line and sky_line[0]["icon"] == "",
    "linha que já começa com pictograma NÃO ganha um 2º ícone")
raid = [e for e in chron if "saqueou" in e["text"]]
chk(raid and raid[0]["icon"] == "☀️",
    "linha sem pictograma recebe o emoji da casa (veio %r)" % (raid[0]["icon"] if raid else None))
chk(len({e["text"] for e in chron}) == len(chron), "sem linhas duplicadas")
chk(len({e["text"][:12] for e in chron}) >= 3, "o feed mostra VARIEDADE, não um só batimento")

print("\n=== 7. O servidor HTTP: allowlist, métodos, IP, Lei §1 ===")
from aiohttp.test_utils import TestClient, TestServer


async def _http_suite():
    res: list[tuple[bool, str]] = []
    server = TestServer(W.create_app())
    client = TestClient(server)
    await client.start_server()
    try:
        r = await client.get("/api/vitrine/world", headers={"X-Forwarded-For": "10.0.0.1"})
        j = await r.json()
        res.append((r.status == 200, "GET /api/vitrine/world -> 200 (veio %d)" % r.status))
        res.append((bool(j.get("chrome")), "a resposta traz `chrome` mesmo sem base"))
        res.append((bool((j.get("cta") or {}).get("play")),
                    "Lei §1: o convite chega SEMPRE (cta.play)"))
        res.append((r.headers.get("Cache-Control", "").startswith("public"),
                    "resposta cacheável (Cache-Control=%r)" % r.headers.get("Cache-Control")))

        r = await client.post("/api/vitrine/world", json={}, headers={"X-Forwarded-For": "10.0.0.2"})
        res.append((r.status == 405, "POST na vitrine -> 405 (veio %d)" % r.status))

        r = await client.options("/api/vitrine/world", headers={"X-Forwarded-For": "10.0.0.2"})
        res.append((r.status == 204, "OPTIONS -> 204 (veio %d)" % r.status))

        for probe in ("/api/vitrine/player", "/api/vitrine/admin/servers",
                      "/api/vitrine/world/x", "/api/vitrine/"):
            r = await client.get(probe, headers={"X-Forwarded-For": "10.0.0.2"})
            res.append((r.status == 404, "%s fora da lista -> 404 (veio %d)" % (probe, r.status)))

        for probe in ("/api/miniapp/player", "/api/miniapp/leaderboard",
                      "/api/miniapp/admin/servers"):
            r = await client.post(probe, json={"init_data": ""},
                                  headers={"X-Forwarded-For": "10.0.0.2"})
            res.append((r.status == 401, "%s sem credencial -> 401 (veio %d)" % (probe, r.status)))

        r = await client.get("/play")
        res.append((r.status == 200, "/play serve a página (veio %d)" % r.status))
        html = await r.text()
        res.append(("/api/vitrine/world" in html, "a página chama o endpoint público"))
        res.append(("telegram-web-app.js" not in html,
                    "a página NÃO carrega o SDK do Telegram"))
        r = await client.get("/play/")
        res.append((r.status == 200, "/play/ serve a página (veio %d)" % r.status))

        # ⚠️ 2026-08-26 — as rotas PT saíram de circulação. Não morreram: 301.
        # `allow_redirects=False` é obrigatório, senão o cliente segue o salto
        # e o teste daria verde mesmo a um 404 disfarçado.
        for old_url in ("/mundo", "/jogar", "/jogar/"):
            r = await client.get(old_url, allow_redirects=False)
            res.append((r.status == 301,
                        "%s sai por 301, nao por 404 (veio %d)" % (old_url, r.status)))
            res.append((r.headers.get("Location") == "/play",
                        "%s aponta para a canonica /play (veio %r)"
                        % (old_url, r.headers.get("Location"))))
        r = await client.get("/jogar")
        res.append((r.status == 200, "seguir a 301 aterra na vitrine (veio %d)" % r.status))

        # Limitação por IP: o balde é 10 fichas + 0,5/s. Um IP novo gasta-as.
        ip = "203.0.113.77"
        codes = []
        for _ in range(14):
            rr = await client.get("/api/vitrine/world", headers={"X-Forwarded-For": ip})
            codes.append(rr.status)
        res.append((429 in codes, "IP a martelar leva 429 (códigos %s)" % codes[-4:]))
        rr = await client.get("/api/vitrine/world", headers={"X-Forwarded-For": "198.51.100.9"})
        res.append((rr.status == 200, "outro IP não é castigado (veio %d)" % rr.status))

        # O ContextVar não pode vazar do middleware para o resto do processo.
        from database.db import current_world_key
        res.append((current_world_key() == "main",
                    "o mundo da vitrine NÃO vaza depois do pedido (veio %r)" % current_world_key()))
    finally:
        await client.close()
    return res


for cond, label in asyncio.run(_http_suite()):
    chk(cond, label)

print("\n=== 8. A página: sem copy hardcoded, sem key fantasma ===")
page = rd("miniapp/vitrine.html")
# Qualquer literal `"vit_*"` conta: a página lê algumas keys por tabela
# (`[["players","vit_stat_players"], ...]`), não só por `t("...")` directo.
page_keys = set(re.findall(r'"(vit_\w+)"', page))
chk(page_keys, "a página usa keys vit_* (%d)" % len(page_keys))
missing = sorted(page_keys - set(V.CHROME_KEYS))
chk(not missing, "toda key usada pela página vem no `chrome` (faltam: %s)" % missing)
# `vit_ladder_anon` é resolvida no SERVIDOR (o nome já chega pronto) — por isso
# o conjunto de leitores é página ∪ módulo. Uma key sem NENHUM leitor é uma
# tradução paga e nunca mostrada.
readers = page_keys | set(re.findall(r'"(vit_\w+)"', src))
unused = sorted(set(V.CHROME_KEYS) - readers)
chk(not unused, "nenhuma key do `chrome` é enviada sem leitor (sobram: %s)" % unused)
chk(re.search(r"innerHTML\s*=", page) is None,
    "a página nunca ESCREVE innerHTML (dao_name é escrito pelo jogador)")
chk("textContent" in page, "a página escreve por textContent")

print("\n=== 9. i18n: paridade, placeholders, PT-BR ===")
chat = {l: json.loads(rd("locales/%s.json" % l)) for l in ("pt", "en", "es")}
chk(len({len(v) for v in chat.values()}) == 1,
    "locales em paridade: %s" % {k: len(v) for k, v in chat.items()})
chk(set(chat["pt"]) == set(chat["en"]) == set(chat["es"]), "mesmo conjunto de keys nas 3")
for k in V.CHROME_KEYS:
    present = all(k in chat[l] for l in ("pt", "en", "es"))
    if not chk(present, "%s existe nas 3 línguas" % k):
        continue
    ph = [set(re.findall(r"\{(\w+)\}", chat[l][k])) for l in ("pt", "en", "es")]
    chk(ph[0] == ph[1] == ph[2], "%s com os MESMOS placeholders (%s)" % (k, ph))
EUPT = ("tecto", "facto", "optim", "accao", "objectiv", "directo", "efectiv",
        "contacto", "actual", "aspecto", "ecrã", "utilizador", "ficheiro")
for k in V.CHROME_KEYS:
    if k not in chat["pt"]:
        continue
    low = chat["pt"][k].lower()
    bad = [w for w in EUPT if w in low]
    chk(not bad, "%s em PT-BR, sem grafia europeia %s" % (k, bad))
# Os elementos dos continentes eram chaves cruas (`universal`, `water`) até a
# vitrine os nomear. Os nomes já existiam SÓ no i18n do mini-app; foram copiados
# para os locales do chat. As duas telas do mesmo jogo têm de dizer o MESMO —
# este assert é o guarda contra o drift entre os dois ficheiros.
mini = {l: json.loads(rd("miniapp/i18n/%s.json" % l)) for l in ("pt", "en", "es")}
for lg in ("pt", "en", "es"):
    m = {k: v for k, v in mini[lg].items() if k.startswith("world_element_")}
    c = {k: v for k, v in chat[lg].items() if k.startswith("world_element_")}
    chk(m and m == c, "world_element_* idêntico entre chat e mini-app (%s: %d vs %d)"
        % (lg, len(c), len(m)))
from core.continent_engine import CONTINENT_META as _CM
_els = sorted({e for meta in _CM.values() for e in meta.get("elements", ())})
for e in _els:
    chk(all(("world_element_" + e) in chat[l] for l in ("pt", "en", "es")),
        "elemento `%s` tem nome nas 3 línguas" % e)

# Os placeholders que a página substitui à mão têm de ser exactamente estes.
for key, want in (("vit_house_rival", {"name"}), ("vit_house_pop", {"npc", "players"}),
                  ("vit_caravan_routes", {"n"}), ("vit_caravan_ratio", {"ratio"})):
    got = set(re.findall(r"\{(\w+)\}", chat["pt"].get(key, "")))
    chk(got == want, "%s tem os placeholders %s (veio %s)" % (key, want, got))

print("\n=== 10. NAO_PROMETER: o que a página pode e não pode prometer ===")
# ⚠️ 2026-08-25 — DUAS destas proibições EXPIRARAM, e a razão fica escrita aqui
# para ninguém as repor por hábito:
#
#   "jogar no navegador" / "play in your browser" era MENTIRA em 20/08 (o jogo
#   só rodava dentro do Telegram) e passou a ser VERDADE quando a WEB-B Fase 1
#   shippou — é literalmente o ✅ do §6 do prompt da F1: *"dá para jogar no
#   navegador, sem instalar nada"*. Mantê-la proibida seria proibir a página de
#   dizer o que o jogo faz.
#
# O que CONTINUA proibido, e porquê:
#   • "criar conta" — a F1 não cria conta nenhuma; só a F2 (provider email).
#   • "sem Telegram" — na F1 dá para jogar sem ABRIR o Telegram, tendo conta.
#   • "em breve" e qualquer DATA — `Publicacao/NAO_PROMETER.md`, sempre.
FORBIDDEN = {
    "pt": ("em breve", "criar conta", "sem telegram", "sem precisar de telegram"),
    "en": ("coming soon", "create an account", "without telegram", "no telegram account"),
    "es": ("próximamente", "crear una cuenta", "sin telegram", "sin cuenta de telegram"),
}
for lg, words in FORBIDDEN.items():
    blob = " ".join(chat[lg].get(k, "") for k in V.CHROME_KEYS).lower()
    bad = [w for w in words if w in blob]
    chk(not bad, "chrome %s sem promessa proibida %s" % (lg, bad))
    chk(not re.search(r"\b20\d\d\b", blob), "chrome %s sem data nenhuma" % lg)
chk("Telegram" in chat["pt"]["vit_enter_body"],
    "a página DIZ que a conta continua a ser a do Telegram (Lei §1)")

print("\n=== 10b. A PORTA está publicada (owner 2026-08-25: 'aponta lá') ===")
# Até 25/08 a `/login` existia e NINGUÉM lhe apontava — a feature era invisível.
chk(V.CTA_WEB_URL.startswith("/"),
    "o link da porta é RELATIVO (segue o domínio sem configuração): %r" % V.CTA_WEB_URL)
chk("VITRINE_WEB_URL" in src, "existe a válvula de ops VITRINE_WEB_URL")
chk("vit_cta_web" in V.CHROME_KEYS, "a key do botão viaja no chrome")
for lg in ("pt", "en", "es"):
    chk(bool(chat[lg].get("vit_cta_web")), "vit_cta_web existe em %s" % lg)
_body_pt = chat["pt"]["vit_enter_body"].lower()
chk("navegador" in _body_pt,
    "o convite deixou de dizer que o jogo SÓ roda no Telegram")
chk("mesmo personagem" in _body_pt,
    "o convite diz que é o MESMO personagem (ninguém teme perder o que tem)")

print("\n=== 11. O mundo da vitrine é o mundo de nascimento ===")
chk("signup_world_key" in src, "o default deriva de signup_world_key (o switch do owner)")
chk("VITRINE_WORLD" in src, "existe a válvula de ops VITRINE_WORLD")
os.environ["VITRINE_WORLD"] = "s2"
chk(V.vitrine_world_key() == "s2", "VITRINE_WORLD manda")
os.environ["VITRINE_WORLD"] = "   "
chk(V.vitrine_world_key() in ("main", "s2"), "env em branco cai no derivado")
os.environ.pop("VITRINE_WORLD", None)

print("\n" + "=" * 62)
print("  %d asserts verdes, %d vermelhos" % (OK, len(FAIL)))
if FAIL:
    print("\n  VERMELHOS:")
    for f in FAIL:
        print("   x " + f)
print("=" * 62)
sys.exit(1 if FAIL else 0)
