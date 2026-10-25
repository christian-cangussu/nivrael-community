// components/ui.js — Phase 2 split (2026-05-02).
// Helpers + UI primitives + chrome. Loaded FIRST. Top-level `var` declarations
// are shared with tabs.js and app.js via the global scope (HTML classic-script
// spec). See MINIAPP_PARITY.md §0.5 for conventions.
    var { useState, useEffect, useCallback, useMemo, useRef } = React;

    // ─── Telegram setup ──────────────────────────────────────────────────────
    var tg = window.Telegram?.WebApp;
    if (tg) {
      try { tg.ready(); tg.expand(); } catch (e) {}
      try { tg.disableVerticalSwipes && tg.disableVerticalSwipes(); } catch (e) {}
    }

    // 2026-05-26 — Telegram BackButton + Closing Confirmation integration.
    //
    // Owner reported the mini-app sometimes closes back to the chat list
    // when navigating (Android system back gesture, swipe-down, Telegram's
    // top-left arrow) — player loses their nav stack and re-enters at
    // home. The fix is two-layered:
    //
    //   • BackButton — Telegram's native back arrow + system-back gesture
    //     run our `onBack` handler INSTEAD of closing the WebApp. Shown
    //     conditionally based on `visible` (typically: modal open OR tab
    //     != home).
    //   • ClosingConfirmation (ECC) — for the remaining close paths
    //     (swipe-down, hamburger close), Telegram shows a "Close anyway?"
    //     prompt instead of closing immediately. Toggled together with
    //     BackButton visibility — at idle home with no modals open, ECC
    //     is OFF so an explicit close is fast (no annoying prompt).
    //
    // Refs hold `onBack` so we can update the closure without re-registering
    // with Telegram every render (offClick needs the exact same reference
    // that onClick was given).
    function useTelegramBackButton({ visible, onBack }) {
      const handlerRef = useRef(onBack);
      useEffect(() => { handlerRef.current = onBack; }, [onBack]);
      useEffect(() => {
        if (!tg) return;
        const wrapped = () => { try { handlerRef.current && handlerRef.current(); } catch (e) {} };
        if (visible) {
          try { tg.BackButton && tg.BackButton.show(); } catch (e) {}
          try { tg.BackButton && tg.BackButton.onClick(wrapped); } catch (e) {}
          try { tg.enableClosingConfirmation && tg.enableClosingConfirmation(); } catch (e) {}
          return () => {
            try { tg.BackButton && tg.BackButton.offClick(wrapped); } catch (e) {}
            try { tg.BackButton && tg.BackButton.hide(); } catch (e) {}
            try { tg.disableClosingConfirmation && tg.disableClosingConfirmation(); } catch (e) {}
          };
        } else {
          try { tg.BackButton && tg.BackButton.hide(); } catch (e) {}
          try { tg.disableClosingConfirmation && tg.disableClosingConfirmation(); } catch (e) {}
        }
      }, [visible]);
    }
    var haptic = (kind = "light") => {
      try {
        if (kind === "select") tg?.HapticFeedback?.selectionChanged?.();
        else if (kind === "success") tg?.HapticFeedback?.notificationOccurred?.("success");
        else if (kind === "warning") tg?.HapticFeedback?.notificationOccurred?.("warning");
        else if (kind === "error") tg?.HapticFeedback?.notificationOccurred?.("error");
        else tg?.HapticFeedback?.impactOccurred?.(kind);
      } catch (e) {}
    };

    // Same-origin: nivrael.com/api/miniapp/* — no CORS, no API_BASE override.
    var API_BASE = "";

    // ─── WEB-B Fase 1 (2026-08-21) — jogar na aba do browser ─────────────────
    // O mesmo cliente serve as duas superfícies. A diferença é UMA: dentro do
    // Telegram a credencial é o `init_data`; fora dele é o par
    // cookie `nv_session` (HttpOnly, o browser manda sozinho) + o header
    // `X-Nivrael-Session`, que o JS monta a partir do cookie `nv_csrf`.
    // O cookie SOZINHO não autentica — é por isso que o header existe, e é o que
    // torna CSRF impossível: um <form> de outro site manda o cookie, mas não
    // consegue pôr um header.
    var CSRF_COOKIE = "nv_csrf";
    var CSRF_HEADER = "X-Nivrael-Session";
    var LOGIN_URL = "/login";   // canónica; `/entrar` continua a servir

    function readCookie(name) {
      try {
        const parts = (document.cookie || "").split("; ");
        for (const part of parts) {
          const i = part.indexOf("=");
          if (i > 0 && part.slice(0, i) === name) return decodeURIComponent(part.slice(i + 1));
        }
      } catch (e) {}
      return "";
    }

    // `true` quando arrancámos FORA do Telegram. Nota: `telegram-web-app.js`
    // define `window.Telegram.WebApp` mesmo num browser normal — o que distingue
    // as duas superfícies é o `initData` estar vazio, não o `tg` não existir.
    function isWebSurface() { return !(tg && tg.initData); }

    // ─── WEB-C 兩面 — as DUAS superfícies ────────────────────────────────────
    // Mandato do owner (2026-08-26): *"No PC fica como telefone, vamos criar
    // versão pros 2."* Um só cliente, um só código — duas superfícies.
    //
    // ⚠️ O ponto de corte NÃO é `window.innerWidth`. Três condições, e cada uma
    // existe por um engano concreto:
    //
    //  1. **Fora do Telegram.** Dentro do Telegram é SEMPRE telemóvel, mesmo no
    //     Telegram Desktop: a janela do WebApp é uma coluna estreita encaixada
    //     no cliente, e um layout de 3 colunas lá dentro fica ilegível. É por
    //     isso que o corte começa por `isWebSurface()` — a superfície DECLARADA,
    //     não a largura medida.
    //  2. **Largura.** Abaixo de DESKTOP_MIN_WIDTH duas colunas não cabem sem
    //     espremer a leitura.
    //  3. **Ponteiro fino.** Um tablet deitado passa os 1024px e continua a ser
    //     dedo: alvos de rato (hover, 28px) num ecrã táctil são um castigo.
    //     `(pointer: fine)` fala do dispositivo PRIMÁRIO — é a pergunta certa.
    var DESKTOP_MIN_WIDTH = 1024;

    function isDesktopSurface() {
      try {
        if (!isWebSurface()) return false;
        if ((window.innerWidth || 0) < DESKTOP_MIN_WIDTH) return false;
        var mq = window.matchMedia && window.matchMedia("(pointer: fine)");
        // Sem `matchMedia` (browser antigo) a largura decide sozinha — degradar
        // para telemóvel num ecrã de 1600px seria pior do que o falso positivo.
        return mq ? !!mq.matches : true;
      } catch (e) { return false; }
    }

    // O mesmo, reactivo: re-renderiza quando a janela muda de lado do corte.
    // Só dispara `setState` quando o BOOLEANO vira — arrastar a borda da janela
    // não pode custar um render por pixel.
    function useDesktopSurface() {
      const [wide, setWide] = useState(isDesktopSurface);
      useEffect(() => {
        let raf = 0;
        const check = () => {
          cancelAnimationFrame(raf);
          raf = requestAnimationFrame(() => {
            const now = isDesktopSurface();
            setWide((prev) => (prev === now ? prev : now));
          });
        };
        window.addEventListener("resize", check);
        window.addEventListener("orientationchange", check);
        return () => {
          cancelAnimationFrame(raf);
          window.removeEventListener("resize", check);
          window.removeEventListener("orientationchange", check);
        };
      }, []);
      return wide;
    }

    // ⏱️ O RELOGIO DO TRANSPORTE (item 8 da auditoria do Astra, 16/09).
    //
    // 🔴 MEDIDO: o `fetch` daqui não tinha prazo nenhum. Um pedido que nunca
    // resolve — rede que cai a meio do aperto de mão, túnel, servidor a pensar
    // — deixava o botão em `busy` e o jogador **pendurado para sempre**, sem
    // erro, sem caminho e sem saber se a coisa aconteceu. É a Lei §1 na forma
    // mais pura: preso sem caminho.
    //
    // ⚠️ **E ele NÃO REPETE NADA.** A regra é do Astra e é a parte que se
    // esquece: *"uma resposta perdida pode corresponder a uma ação concluída no
    // servidor"*. Repetir sozinho um `market/buy` ou um `meditate/start` que
    // já passou cobra duas vezes. O relógio devolve o CONTROLO e diz que **não
    // sabe** — `request_timeout`, que o cliente traduz para *"confirmando
    // estado"* e nunca para *"falhou"*.
    //
    // ⚠️ 30s e não 5: isto corre num WebView do Telegram, em redes móveis, e
    // algumas acções do servidor são mesmo lentas (uma masmorra, um chefe). O
    // valor tem de ser generoso o bastante para nunca matar um pedido VÁLIDO —
    // o que ele substitui é o infinito, não um segundo.
    var API_TIMEOUT_MS = 30000;
    async function api(endpoint, extra = {}) {
      const initData = tg?.initData || "";
      const headers = { "Content-Type": "application/json" };
      const opts = {
        method: "POST",
        headers,
        body: JSON.stringify({ init_data: initData, ...extra }),
      };
      if (!initData) {
        const csrf = readCookie(CSRF_COOKIE);
        if (csrf) headers[CSRF_HEADER] = csrf;
        opts.credentials = "include";
      }
      // ⚠️ `AbortController` pode não existir num cliente muito velho — aí o
      // comportamento é exactamente o de hoje (sem prazo), nunca um crash.
      let _ctrl = null, _tm = null;
      try {
        if (typeof AbortController === "function") {
          _ctrl = new AbortController();
          opts.signal = _ctrl.signal;
          _tm = setTimeout(() => { try { _ctrl.abort(); } catch (e) {} }, API_TIMEOUT_MS);
        }
      } catch (e) { _ctrl = null; }
      let res;
      try {
        res = await fetch(`${API_BASE}/api/miniapp/${endpoint}`, opts);
      } catch (e) {
        // ⚠️ Distinguir o PRAZO da falha de rede importa: um prazo significa
        // "não sei"; uma falha de rede significa "não saiu". São conselhos
        // diferentes para o jogador, e o segundo permite repetir sem risco.
        const _abortado = _ctrl && _ctrl.signal && _ctrl.signal.aborted;
        throw new Error(_abortado ? "request_timeout" : (e && e.message) || "network_error");
      } finally {
        if (_tm != null) clearTimeout(_tm);
      }
      if (res.status === 401 && !initData) {
        // Lei §1 — nunca preso sem caminho. Sem sessão (expirou, foi revogada,
        // ou nunca existiu) o jogador ia ficar num ecrã de erro que não diz o
        // que fazer. Levamo-lo à porta, e o `next` traz-no de volta ao sítio.
        try {
          const back = encodeURIComponent(window.location.pathname + window.location.search);
          window.location.replace(LOGIN_URL + "?next=" + back);
        } catch (e) {}
        throw new Error("session_expired");
      }
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try { const j = await res.json(); if (j.error) msg = j.error; } catch (e) {}
        throw new Error(msg);
      }
      return res.json();
    }

    // Abrir um pagamento nas DUAS superfícies. Dentro do Telegram é o
    // `openInvoice` de sempre (com o callback de estado). Fora dele, o
    // `invoice_link` é um link `t.me` que abre o pagamento na app/web do
    // Telegram — e aí NÃO existe callback: o crédito chega pelo bot, do lado do
    // servidor, e aparece no refresh seguinte. O toast tem de dizer isso (Lei §1
    // — nunca um botão que parece não ter feito nada), e uma janela bloqueada
    // pelo browser tem de dizer o que fazer em vez de morrer em silêncio.
    function openPaymentLink(link, onPaid) {
      if (tg?.openInvoice) {
        tg.openInvoice(link, (status) => {
          if (status === "paid") { haptic("success"); showToast(t("shop_invoice_paid")); onPaid && onPaid(); }
          else if (status === "cancelled") { haptic("warning"); showToast(t("shop_invoice_cancelled"), "err"); }
          else if (status === "failed") { haptic("error"); showToast(t("shop_invoice_failed"), "err"); }
          else if (status === "pending") { showToast(t("shop_invoice_pending")); }
        });
        return;
      }
      let opened = null;
      try { opened = window.open(link, "_blank", "noopener"); } catch (e) {}
      if (!opened) {
        haptic("error");
        showToast(t("shop_invoice_popup_blocked"), "err");
        return;
      }
      showToast(t("shop_invoice_external"));
    }

    function useApi(endpoint, extra, deps) {
      const [state, setState] = useState({ data: null, loading: true, error: null });
      const extraJson = JSON.stringify(extra || {});
      useEffect(() => {
        let cancelled = false;
        setState(s => ({ ...s, loading: true }));
        api(endpoint, JSON.parse(extraJson))
          .then(d => { if (!cancelled) setState({ data: d, loading: false, error: null }); })
          .catch(e => { if (!cancelled) setState({ data: null, loading: false, error: e.message }); });
        return () => { cancelled = true; };
      // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [endpoint, extraJson, ...(deps || [])]);
      return state;
    }

    // Auto-refresh that pauses when the tab is hidden (Telegram client off
    // screen, browser backgrounded). With 100+ players hitting cultivation
    // every 5s and world boss every 8s, this saves ~12 req/min/player when
    // they're not even looking. Resumes on visibilitychange.
    //
    // 🐛 2026-09-22 (report do [jogador]): *"health (current) is different between
    // telegram and web based (telegram is updated, seems web based is behind,
    // but waited more than 30 seconds, moved and came back to another page…
    // no refresh)"*. MEDIDO: a conta dele estava certa (mesmo personagem, mesmo
    // mundo nas duas portas). O que ficava para trás era o SEPARADOR: ao voltar
    // a ficar visível, o intervalo recomeçava do zero e o primeiro pedido só
    // saía `ms` depois — 30s para o jogador, com o valor velho à vista. E o
    // Windows marca como "hidden" uma janela TAPADA por outra (o Telegram
    // Desktop por cima do browser), portanto comparar as duas lado a lado
    // pausava exactamente o separador que ele estava a olhar.
    // Agora o regresso (separador visível de novo, ou janela com foco) faz UM
    // pedido imediato. Com uma trava de 2s, para o `visibilitychange` e o
    // `focus` — que chegam juntos — não dispararem dois.
    function useVisibleInterval(fn, ms) {
      const ref = useRef(fn);
      useEffect(() => { ref.current = fn; }, [fn]);
      useEffect(() => {
        let id = null;
        let ultimo = Date.now();
        const tick = () => { ultimo = Date.now(); try { ref.current && ref.current(); } catch (e) {} };
        const start = () => {
          if (id == null && (typeof document === "undefined" || document.visibilityState !== "hidden")) {
            id = setInterval(tick, ms);
          }
        };
        const stop = () => { if (id != null) { clearInterval(id); id = null; } };
        // o regresso pede JÁ, se o último pedido tiver mais de 2s
        const regresso = () => { if (Date.now() - ultimo > 2000) tick(); };
        const onVis = () => {
          if (document.visibilityState === "hidden") { stop(); return; }
          regresso(); start();
        };
        const onFocus = () => { regresso(); };
        start();
        document.addEventListener("visibilitychange", onVis);
        window.addEventListener("focus", onFocus);
        return () => {
          stop();
          document.removeEventListener("visibilitychange", onVis);
          window.removeEventListener("focus", onFocus);
        };
      }, [ms]);
    }

    // ─── i18n ────────────────────────────────────────────────────────────────
    // Strings live in miniapp/i18n/{pt,en,es}.json — fetched by bootstrap
    // (bottom of file) before the React tree mounts. The 3 dicts MUST stay
    // in parity (same key set). Adding a string = add the key in all 3
    // .json files. See MINIAPP_PARITY.md §0.5.
    var LANG = "pt";
    var STRINGS = { pt: {}, en: {}, es: {} };
    // ⚠️ A LÍNGUA ANTES DE HAVER JOGADOR (2026-09-04).
    //
    // `LANG` só passa a valer o `player.language` quando o payload do jogador
    // chega. Para quem JÁ tem personagem isso é um piscar de olhos. Mas quem
    // chega pela porta web e ainda NÃO tem personagem recebe
    // `needs_world_start` — e esse ecrã (o nome do Dao, o primeiro acto do
    // jogador no mundo) ficava INTEIRAMENTE em português, tivesse ele
    // escolhido o que tivesse escolhido na porta. Era a terceira metade do
    // *"idiomas mezclados"* do report do owner, e a única que aparece no
    // primeiro ecrã que uma pessoa nova vê.
    //
    // A porta grava a escolha em `nv_lang` (não é `HttpOnly` precisamente para
    // isto). O `?lang=` continua a mandar, como em toda a casa. Se não houver
    // nem uma coisa nem outra, o `player.language` corrige daqui a um
    // instante e nada disto se nota — logo dentro do Telegram é NO-OP.
    (function initialLang() {
      var supported = ["pt", "en", "es"];
      function ok(v) {
        v = String(v || "").toLowerCase().replace("_", "-").split("-")[0];
        return supported.indexOf(v) >= 0 ? v : "";
      }
      try {
        var q = ok(new URLSearchParams(window.location.search).get("lang"));
        if (q) { definirLang(q); return; }
        var m = document.cookie.match(/(?:^|;\s*)nv_lang=([^;]*)/);
        var c = ok(m ? decodeURIComponent(m[1]) : "");
        if (c) { definirLang(c); return; }
      } catch (e) { /* um cookie ilegível nunca pode partir o arranque */ }
    })();
    // 語 O DONO UNICO DA LINGUA (2026-09-23 — a 2a metade do bug do [jogador]).
    //
    // `LANG` tinha TRES escritores (o arranque aqui, o `/player` no `app.js`, o
    // `world_start` no `tabs.js`) e **nenhum deles dizia ao BROWSER** qual era a
    // lingua: o `<html lang>` do `/app` ficou fixo em `pt-BR` desde sempre. O
    // `/login` e a vitrine ja' o faziam; o jogo, nao.
    //
    // A consequencia, medida na captura do [jogador]: um jogador a jogar em ingles
    // recebe do Chrome a oferta de traduzir uma pagina que jura ser portuguesa,
    // aceita, e o Google reescreve os nos de texto — o nome proprio dele
    // incluido. "C" no Telegram (a webview nao traduz) e "W" no browser, na
    // MESMA conta, ao mesmo tempo.
    //
    // ⚠️ Um sitio so', e os tres escritores passam por ele: duas ligacoes a' mao
    // da mesma decisao divergem sempre (Lei 0 §2), e esta decisao ja' tinha tres.
    function definirLang(v) {
      if (!v || !STRINGS[v]) return LANG;
      LANG = v;
      try {
        document.documentElement.lang = v === "pt" ? "pt-BR" : v;
      } catch (e) { /* sem documento, a lingua do jogo continua certa */ }
      return LANG;
    }
    function t(key, params) {
      const dict = STRINGS[LANG] || STRINGS.pt;
      let s = dict[key] ?? STRINGS.pt[key] ?? key;
      if (params) for (const [k, v] of Object.entries(params)) s = s.replace(`{${k}}`, v);
      return s;
    }
    function realmName(idx) { return t(`realm_${Math.min(Math.max(idx ?? 0, 0), 10)}`); }
    function realmShort(idx) { return realmName(idx).split(" ")[0]; }
    var realmColor = r => `var(--realm-${Math.min(r||0, 10)})`;
    // R5 (varredura do anti-pattern) — irmão HEX LITERAL do realmColor.
    // Concatenar alpha num var() (`${cssHex(rc)}88`) é inválido at-computed-value-time
    // e derruba a declaração INTEIRA (lição R3; a R5 varreu os glows mortos).
    // Para QUALQUER cor que vá ganhar sufixo alpha usar realmHex/cssHex —
    // nunca realmColor. Espelho de index.html :root — manter em sync.
    // ⚠️ ESPELHO do :root de index.html — NÃO é uma segunda paleta.
    // Existe porque três sítios exigem HEX literal e não sabem ler `var()`:
    //   1. o alpha-concat (`${cssHex(x)}88`) — a lição R3/R5;
    //   2. `tg.setHeaderColor()` — a API do Telegram recebe uma string "#rrggbb";
    //   3. `<svg fill="...">` — `var()` NÃO resolve em atributo de apresentação.
    // `scripts/_test_web_c_superficies.py` falha se este bloco divergir do
    // :root. Mudar uma cor = mudar o :root E esta linha, no mesmo commit.
    var REALM_HEX = ["#9ca3af","#60a5fa","#fbbf24","#a855f7","#2dd4bf","#3b82f6","#8b5cf6","#f59e0b","#38bdf8","#eab308","#f472b6"];
    var realmHex = r => REALM_HEX[Math.min(Math.max(r||0, 0), 10)];
    var CSS_VAR_HEX = {
      "--gold":"#c9903a", "--gold2":"#f5c97a", "--gold3":"#fde68a",
      "--jade":"#3ecf7e", "--red":"#e5534b", "--warn":"#f59e0b",
      "--border":"#1e3060", "--border2":"#253f7a",
      "--muted":"#6e89bf", "--muted2":"#3d5a9e", "--text":"#e2eaff",
      "--bg":"#06080f", "--card":"#0d1422", "--panel":"#111d35",
      // WEB-D — os sete novos (ver :root). Sem eles, `cssHex("var(--red2)")`
      // caía no fallback dourado e o dano ficava cor de ouro.
      "--surface":"#141c32", "--surface2":"#0a0e1c", "--surface3":"#0c101e",
      "--glow":"#3c5ab4", "--text2":"#dce6ff", "--accent2":"#7896ff",
      "--red2":"#fca5a5",
      // 牌 — 朱砂. Igual nas duas peles (ver o :root): o selo e' assinatura,
      // nao moldura. Sem esta linha `cssHex("var(--seal)")` caia no dourado.
      "--seal":"#c8442f",
    };
    // ⚠️ Os fallbacks desta funcao sao HEX LITERAL de proposito — e' a UNICA
    // funcao do ficheiro onde `var(--gold2)` seria um bug. `cssHex` existe para
    // TIRAR o var(); quem a chama vai colar um alpha ao resultado
    // (`${cssHex(x)}88`), e `var(--gold2)88` e' invalido at-computed-value-time
    // e derruba a declaracao inteira em silencio (licao R3/R5). A varredura da
    // WEB-D converteu-os por engano e o teste `_test_web_c_superficies` passou
    // a vigiar isto.
    var cssHex = (c, fb) => {
      if (typeof c !== "string") return fb || "#f5c97a";
      const m = c.match(/^var\((--[a-z0-9-]+)\)$/i);
      if (!m) return c;
      if (m[1].indexOf("--realm-") === 0) return realmHex(parseInt(m[1].slice(8), 10) || 0);
      return CSS_VAR_HEX[m[1]] || fb || "#f5c97a";
    };

    // Realm icons (NO chinese glyphs — emojis the user already has)
    var REALM_EMOJIS = ["🪨","☯️","🏯","🔮","👻","⚡","🐉","🌟","💎","👑","🌸"];
    var orbCenterIcon = (realm, meditating) => meditating ? "✦" : REALM_EMOJIS[Math.min(realm||0,10)];

    // ─── Helpers ─────────────────────────────────────────────────────────────
    function fmtNum(n) {
      n = Number(n) || 0;
      if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(2) + "B";
      if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
      if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
      return Math.round(n).toString();
    }
    function fmtDuration(ms) {
      if (ms <= 0) return "—";
      const s = Math.floor(ms / 1000);
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
      if (h > 0) return `${h}h ${m}m`;
      if (m > 0) return `${m}m ${sec}s`;
      return `${sec}s`;
    }
    function timeAgo(ms) {
      if (!ms) return "";
      const diff = Date.now() - ms, s = Math.floor(diff / 1000);
      if (s < 60) return t("time_now");
      if (s < 3600) return t("time_min_ago", { n: Math.floor(s / 60) });
      if (s < 86400) return t("time_hour_ago", { n: Math.floor(s / 3600) });
      return t("time_day_ago", { n: Math.floor(s / 86400) });
    }
    // v14.13e (2026-05-25) — Owner caught raw snake_case stat names leaking
    // to paying players (screenshot: "battle_power+6000 · soul_strength+600
    // · percep..."). Single global helper to map stat key → localized label.
    // Strategy:
    //   1. Try `t(key)` first — most artifact stat names are TOP-LEVEL keys
    //      (battle_power, soul_strength, perception, luck — locales pt/en/es
    //      have them as canonical labels).
    //   2. Try `t(stat_<key>)` — future-proof if we move to namespaced keys.
    //   3. Fallback: title-case the snake_case (Battle Power, Soul Strength).
    //      NEVER leak underscores.
    function humanizeStat(key) {
      if (!key) return "";
      const direct = t(key);
      if (direct && direct !== key) return direct;
      const prefixed = t("stat_" + key);
      if (prefixed && prefixed !== "stat_" + key) return prefixed;
      return String(key).replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    }

    // v14.13e — Defensive resolver for dynamic key sources (q.description_key,
    // it.name_key, etc.) where a stale i18n cache / missing key should NEVER
    // leak the raw snake_case to the user. Returns:
    //   - Translated string if `t(key)` resolves.
    //   - Server-provided `fallback` string if non-empty (e.g. pre-rendered).
    //   - `humanizeStat(key)` if all else fails (title-case the snake_case).
    // ALWAYS prefer this over `t(dynamicKey) || ""` for user-visible text.
    function safeT(key, params, fallback) {
      if (!key) return fallback || "";
      const v = t(key, params);
      if (v && v !== key) return v;
      if (fallback) return fallback;
      return humanizeStat(key);
    }

    // v15.1.5-hf3 — Lightweight Telegram-Markdown → JSX renderer.
    //
    // Source i18n strings were authored for Telegram parse_mode="Markdown":
    //   *bold*, `code`, _italic_, line breaks via \n. Mini-app modals
    //   that drop the raw string into a <div> get literal asterisks/
    //   backticks shown to the player (owner screenshot: Heart Demon
    //   tutorial wall-of-text).
    //
    // This renderer preserves the same content without needing to fork
    // every locale string. It handles:
    //   - Paragraph splits on blank lines (\n\n) → <div> blocks
    //   - Soft line breaks (single \n) inside paragraph → <br>
    //   - **text** or *text* → <strong>
    //   - `code` → <code> (subtle background)
    //   - _text_ → <em>
    //   - Bullet lines starting with "• " kept as-is (visual bullet)
    //
    // Returns a JSX fragment. Safe to render anywhere a string would go.
    function MD({ text }) {
      if (!text) return null;
      const inline = (s, keyPrefix) => {
        // Tokenise by *bold*, `code`, _italic_ — preserve original order.
        const parts = [];
        let i = 0, key = 0;
        const push = (node) => parts.push(<React.Fragment key={`${keyPrefix}-${key++}`}>{node}</React.Fragment>);
        while (i < s.length) {
          const remaining = s.slice(i);
          // **bold** (greedy, double asterisk first)
          let m = /^\*\*([^*]+)\*\*/.exec(remaining);
          if (m) { push(<strong>{m[1]}</strong>); i += m[0].length; continue; }
          // *bold*
          m = /^\*([^*\n]+)\*/.exec(remaining);
          if (m) { push(<strong>{m[1]}</strong>); i += m[0].length; continue; }
          // code span (delimited by U+0060 backtick — written as ` in
          // the regex source so tooling that handles template literals
          // doesn't mistakenly enter template-mode on a regex backtick).
          m = /^`([^`\n]+)`/.exec(remaining);
          if (m) {
            push(<code style={{
              background: "rgba(var(--gold2-rgb),.12)",
              padding: "1px 5px", borderRadius: 4,
              fontSize: "0.92em", fontFamily: "monospace",
              color: "var(--gold3)",
            }}>{m[1]}</code>);
            i += m[0].length; continue;
          }
          // _italic_
          m = /^_([^_\n]+)_/.exec(remaining);
          if (m) { push(<em>{m[1]}</em>); i += m[0].length; continue; }
          // Plain text up to the next markdown trigger or end
          m = /^[^*`_]+/.exec(remaining);
          if (m) { push(m[0]); i += m[0].length; continue; }
          // Fallback (lone markdown chars that didn't match — emit as text)
          push(remaining[0]); i += 1;
        }
        return parts;
      };
      // Split into paragraphs on blank-line boundaries.
      const paragraphs = String(text).split(/\n\s*\n/);
      return (
        <>
          {paragraphs.map((para, pi) => {
            const lines = para.split("\n");
            return (
              <div key={pi} style={{ marginBottom: pi < paragraphs.length - 1 ? 10 : 0 }}>
                {lines.map((ln, li) => (
                  <React.Fragment key={li}>
                    {inline(ln, `p${pi}-l${li}`)}
                    {li < lines.length - 1 ? <br /> : null}
                  </React.Fragment>
                ))}
              </div>
            );
          })}
        </>
      );
    }

    function rankChip(rank) {
      if (rank === 1) return { color: "#ffd700", glow: "rgba(255,215,0,.5)" };
      if (rank === 2) return { color: "#c0c0c0", glow: "rgba(192,192,192,.5)" };
      if (rank === 3) return { color: "#cd7f32", glow: "rgba(205,127,50,.5)" };
      return { color: "var(--gold2)", glow: "transparent" };
    }

    // ─── Toast (transient feedback for actions) ──────────────────────────────
    var _toastSetter = null;
    function showToast(msg, kind = "ok") {
      if (_toastSetter) _toastSetter({ msg, kind, id: Math.random() });
      setTimeout(() => { if (_toastSetter) _toastSetter(null); }, 2400);
    }
    function ToastHost() {
      const [toast, setToast] = useState(null);
      useEffect(() => { _toastSetter = setToast; return () => { _toastSetter = null; }; }, []);
      if (!toast) return null;
      return <div key={toast.id} className={"toast" + (toast.kind === "err" ? " err" : "")}>{toast.msg}</div>;
    }

    // ─── Notification Toast Stack (v14.13c Item 2) ───────────────────────────
    // Distinct from `showToast` above:
    //   - `showToast` = bottom transient feedback for user-triggered actions
    //     (claim done, recipe crafted, etc). Single slot, 2.4s.
    //   - `pushNotifToast` = top-anchored stackable push popups for
    //     SERVER-DETECTED events (new quest ready, breakthrough ready, PvP
    //     incoming). Up to 3 visible, 6s each, tappable to drill-in.
    //
    // Owner P1 round 2026-05-08: "as notificacoes tambem do jogador quests
    // e tudo mais" — v14.7 shipped the bell+inbox poll-based surface. This
    // adds the PROACTIVE push surface for items that just arrived (delta
    // detection happens in app.js via seenIdsRef vs polled inbox snapshot).
    // Toasts respect notification_prefs from the inbox response — opt-out
    // for the 4 mapped types (breakthrough_ready, trib_cooldown_done,
    // pill_finished, alchemy_energy_full); always-on for quest/faction/PvP
    // (action-required, players want to react fast).
    var _notifToastEmitter = null;
    function pushNotifToast({ icon, title, body, target_tab, type, onClick } = {}) {
      if (_notifToastEmitter) {
        _notifToastEmitter({
          id: Math.random().toString(36).slice(2),
          icon: icon || "🔔",
          title: title || "",
          body: body || "",
          target_tab: target_tab || null,
          type: type || "",
          onClick: onClick || null,
          createdAt: Date.now(),
        });
      }
    }
    function NotifToastStack() {
      const [stack, setStack] = useState([]);
      useEffect(() => {
        _notifToastEmitter = (item) => {
          setStack(prev => {
            // Dedupe by `type:title` so back-to-back polls don't double-emit.
            const dedupe = prev.filter(p => !(p.type === item.type && p.title === item.title));
            // Cap at 3 visible — drop oldest when overflowing.
            const next = [...dedupe, item];
            return next.slice(-3);
          });
        };
        return () => { _notifToastEmitter = null; };
      }, []);
      // Auto-dismiss each toast 6s after its arrival.
      useEffect(() => {
        if (stack.length === 0) return;
        const timers = stack.map(item => {
          const elapsed = Date.now() - item.createdAt;
          const remaining = Math.max(0, 6000 - elapsed);
          return setTimeout(() => {
            setStack(prev => prev.filter(p => p.id !== item.id));
          }, remaining);
        });
        return () => timers.forEach(clearTimeout);
      }, [stack]);
      if (stack.length === 0) return null;
      return (
        <div style={{
          position:"fixed", top:8, left:0, right:0,
          zIndex:120, pointerEvents:"none",
          display:"flex", flexDirection:"column", alignItems:"center", gap:6,
          padding:"0 12px",
        }}>
          {stack.map(item => (
            <div key={item.id}
                 onClick={() => {
                   if (typeof haptic === "function") haptic("select");
                   if (item.onClick) item.onClick(item);
                   setStack(prev => prev.filter(p => p.id !== item.id));
                 }}
                 style={{
                   pointerEvents:"auto",
                   width:"100%", maxWidth:440,
                   background:"linear-gradient(180deg,rgba(var(--surface-rgb),.96),rgba(10,16,32,.98))",
                   border:"1px solid rgba(var(--gold2-rgb),.45)",
                   borderRadius:10, padding:"9px 12px",
                   display:"flex", alignItems:"center", gap:10,
                   cursor: item.target_tab || item.onClick ? "pointer" : "default",
                   boxShadow:"0 4px 16px rgba(0,0,0,.55), 0 0 12px rgba(var(--gold2-rgb),.18)",
                   animation:"notif-toast-in 280ms cubic-bezier(.2,1.4,.4,1)",
                 }}>
              <div style={{
                fontSize:22, flexShrink:0,
                filter:"drop-shadow(0 0 6px rgba(var(--gold2-rgb),.45))",
              }}>{item.icon}</div>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{
                  fontFamily:"'Cinzel',serif", fontSize:12.5, fontWeight:700,
                  color:"var(--gold2)", letterSpacing:.3,
                  whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis",
                }}>{item.title}</div>
                {item.body && (
                  <div style={{
                    fontSize:11, color:"var(--muted)", marginTop:1,
                    lineHeight:1.35,
                    overflow:"hidden", display:"-webkit-box",
                    WebkitLineClamp:2, WebkitBoxOrient:"vertical",
                  }}>{item.body}</div>
                )}
              </div>
              {item.target_tab && (
                <span style={{ fontSize:14, color:"var(--gold3)", flexShrink:0 }}>›</span>
              )}
            </div>
          ))}
        </div>
      );
    }

    // ─── Atmospheric Background (stars + 3 mountain layers + pagoda + glows) ─
    function AtmoBg() {
      const stars = useMemo(() => Array.from({length:34}, (_, i) => ({
        x: (((i*137.508)%1)*100).toFixed(2),
        y: (((i*73.13)%1)*55).toFixed(2),
        s: (.4 + ((i*31.7)%1)*1.0).toFixed(2),
        d: ((i*.7)%4).toFixed(1),
        dur: (1.5 + i%3).toFixed(1),
      })), []);
      return (
        <div style={{ position:"absolute", inset:0, pointerEvents:"none", zIndex:0, overflow:"hidden" }}>
          {stars.map((star, i) => (
            <div key={i} style={{
              position:"absolute", left: star.x+"%", top: star.y+"%",
              width: star.s+"px", height: star.s+"px", borderRadius:"50%",
              background:"rgba(255,240,200,.78)",
              animation: `constellation-twinkle ${star.dur}s ease-in-out infinite`,
              animationDelay: star.d+"s",
            }} />
          ))}
          <svg viewBox="0 0 480 180" preserveAspectRatio="xMidYMax slice"
               style={{ position:"absolute", bottom:72, left:0, width:"100%", opacity:.18, pointerEvents:"none" }}>
            <path d="M0,180 L50,80 L90,110 L140,45 L190,90 L230,55 L275,85 L315,25 L360,65 L400,40 L445,70 L480,50 L480,180Z" style={{ fill:"rgba(var(--amb-ridge1-rgb),.5)" }} />
            <path d="M0,180 L35,100 L75,120 L120,70 L165,105 L205,78 L250,100 L295,60 L340,88 L385,62 L430,85 L480,72 L480,180Z" style={{ fill:"rgba(var(--amb-ridge2-rgb),.45)" }} />
            <path d="M0,180 L25,125 L65,140 L105,95 L150,128 L195,108 L240,125 L285,88 L325,112 L370,92 L415,108 L480,95 L480,180Z" style={{ fill:"rgba(var(--amb-ridge3-rgb),.5)" }} />
            <g transform="translate(320,20)" opacity=".5" style={{ fill:"rgba(var(--amb-pagoda-rgb),.6)" }}>
              <rect x="-2" y="30" width="4" height="20" />
              <polygon points="-10,30 10,30 5,20 -5,20" />
              <polygon points="-14,20 14,20 8,8 -8,8" />
              <polygon points="-8,8 8,8 4,0 -4,0" />
            </g>
          </svg>
          <div style={{ position:"absolute", top:0, left:0, right:0, height:220,
            background:"radial-gradient(ellipse at 50% -10%,rgba(var(--amb-sky-rgb),.22),transparent 65%)" }} />
          <div style={{ position:"absolute", bottom:0, left:0, right:0, height:250,
            background:"radial-gradient(ellipse at 50% 110%,rgba(160,90,20,.14),transparent 60%)" }} />
          <div style={{ position:"absolute", inset:0,
            background:"radial-gradient(ellipse at 50% 50%,transparent 55%,rgba(0,0,0,.35) 100%)" }} />
        </div>
      );
    }

    // ─── Ornate corners (replaces chinese-glyph drift bg) ────────────────────
    function OrnateCorners({ color="rgba(var(--gold-rgb),.45)", size=14 }) {
      const corners = [
        { style:{ top:0, left:0 }, rotate:"0" },
        { style:{ top:0, right:0 }, rotate:"90" },
        { style:{ bottom:0, right:0 }, rotate:"180" },
        { style:{ bottom:0, left:0 }, rotate:"270" },
      ];
      return corners.map((c, i) => (
        <svg key={i} width={size} height={size} viewBox="0 0 14 14"
             style={{ position:"absolute", ...c.style, pointerEvents:"none", zIndex:1 }}>
          <g transform={`rotate(${c.rotate},7,7)`} stroke={color} strokeWidth="1" fill="none">
            <path d="M1,7 L1,1 L7,1" />
            <path d="M1,4 L4,1" />
            <circle cx="1" cy="1" r="1" fill={color} stroke="none" />
          </g>
        </svg>
      ));
    }

    // ─── Player Header (ornamental, gradient name, glow realm pill) ──────────
    // ═══ 至 A CHEGADA É DONA DO ECRÃ ═══════════════════════════════════════
    //
    // Decisão do Astra (`Olho/Astra/2026-09-16-d-o-cabecalho.md`), escolha (a):
    // *"com a flag ON e a nova chegada efectivamente montada, o `PlayerHeader`
    // antigo recolhe por inteiro (…) é uma excepção explícita (…) **não é uma
    // reforma das 25 abas**."*
    //
    // 🔴 MEDIDO no ecrã servido, e foi o que a motivou: com a cena montada por
    // baixo do cabeçalho antigo, **o nome, o jade, as pedras e o reino
    // apareciam DUAS vezes cada**, com **181 px** de cromo a empurrar a
    // paisagem para baixo.
    //
    // ⚠️ UM dono para a decisão, e as duas superfícies que recolhem
    // perguntam-lhe a ela. Duas condições escritas à mão divergiriam — e o
    // estado em que uma recolhe e a outra não é pior do que ambas ficarem.
    //
    // ⚠️ `typeof ChegadaCena === "function"` faz parte da pergunta de
    // propósito: se a cena não existir (bundle antigo em cache), o cabeçalho
    // TEM de ficar — recolher o antigo sem ter o novo deixava o jogador sem
    // identidade nenhuma no ecrã.
    function chegadaDona(tab) {
      // 🔴 AS DUAS ABAS, e a segunda e' a que importa. Medido: com a `ui_v2`
      // ligada — o que o owner corre — o hub Eu abre em `hub_eu_screen`, e a
      // chegada tinha sido construida so' em `home`. Ela existia, estava
      // certa, e **a navegacao dele nunca lhe passava**. 6a vez nesta casa que
      // "existe" nao foi "chega".
      return (tab === "home" || tab === "hub_eu_screen")
        && typeof ondaCultOn === "function" && ondaCultOn()
        && typeof ChegadaCena === "function";
    }

    function PlayerHeader({ player, tab, onBack, onJadeClick, onBellClick, onProfileClick, notifCount }) {
      if (!player) return null;
      // R5: hex literal — o rc é concatenado com alpha nos glows (avatar 548,
      // pill 628); com var() a declaração inteira morria silenciosa.
      const rc = realmHex(player.realm);
      // 2026-05-26 redesign — identity chips (continent / path / karma) moved
      // into ProfileModal accessed by tapping the name+avatar area. Top row
      // now: back arrow (drill-in tabs) + avatar/name tap-target + bell +
      // realm chip. See GameDesign/profile_modal_spec.md.
      // 坐 O avatar mudou de dono: `RealmAvatar` (acima) é o único sítio onde a
      // bolinha do jogador é desenhada — aqui e no `ProfileModal`. O array de
      // 11 emoji e o gradiente viviam AQUI e outra vez lá; ver a nota lá em cima.
      // Show "back to Home" arrow only when current tab is a drill-in
      // destination (not part of the visible BottomNav). Default tab "home"
      // never shows it; cultivation/inventory/crafting/settings have their
      // own tab in the nav so back is redundant there too.
      // Onda R2 (ui_v2) — no shell v2 as RAÍZES são os LANDINGS dos 5 hubs
      // (review R1: 3 landings mostravam seta permanente). typeof-guards
      // fail-safe → OFF/cliente-cacheado cai no BOTTOM_VISIBLE de sempre.
      // 至 A chegada carrega a zona 1 inteira (identidade, saldos, sino, Loja).
      if (chegadaDona(tab)) return null;
      const _v2Nav = (typeof featureEnabled === "function" && featureEnabled("ui_v2")
                      && typeof HUB_DEFS !== "undefined");
      const _navRoots = _v2Nav ? HUB_DEFS.map(h => h.landing) : BOTTOM_VISIBLE;
      // 坐 ONDA 1 — a moldura que ACOMPANHA a tela do Cultivo ([013] §C.1).
      // ⚠️ `tab === "cultivation"` e não só a flag: o cabeçalho renderiza nas 25
      // abas, e uma pele nova em todas trocava um choque por vinte e quatro.
      const _ondaFrame = typeof ondaCultOn === "function" && ondaCultOn()
                         && tab === "cultivation";
      const showBack = !!tab && !_navRoots.includes(tab);
      // 印 O chip do reino, ramo LIGADO: tipografia em vez de pictograma (a
      // decisão está escrita por extenso lá em baixo, onde ele é usado).
      const _realmChipTypo = (
        <React.Fragment>
          <div style={{ fontSize:13, lineHeight:1.05, color:rc, letterSpacing:.6,
                        fontFamily:"'Cinzel',serif", fontWeight:700 }}>
            {realmShort(player.realm)}
          </div>
          <div style={{ fontSize:8.5, color:rc, opacity:.72, letterSpacing:.4,
                        fontFamily:"'Cinzel',serif", fontWeight:600 }}>
            {safeT("profile_sub_layer", { n: player.sub_layer || 1 })}
          </div>
        </React.Fragment>
      );
      return (
        <div style={{
          position:"relative", zIndex:2,
          padding:"14px 16px 11px",
          display:"flex", flexDirection:"column", gap:9,
          borderBottom: _ondaFrame
            ? "1px solid " + NIV_ONDA.line
            : "1px solid rgba(var(--gold-rgb),.2)",
          background: _ondaFrame
            ? NIV_ONDA.ink
            : "linear-gradient(180deg,rgba(var(--surface2-rgb),.95) 0%,rgba(var(--surface2-rgb),.75) 80%,transparent 100%)",
        }}>
          <div style={{ position:"absolute", top:0, left:16, right:16, height:1,
            background: _ondaFrame
              ? "transparent"
              : "linear-gradient(90deg,transparent,rgba(var(--gold-rgb),.5),rgba(var(--gold-rgb),.85),rgba(var(--gold-rgb),.5),transparent)" }} />
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", gap:10 }}>
            <div style={{ minWidth:0, display:"flex", alignItems:"center", gap:8, flex:1 }}>
              {showBack && (
                <button onClick={() => { haptic("select"); onBack && onBack(); }}
                        aria-label={t("back")}
                        style={{
                          background:"rgba(0,0,0,.35)",
                          border:"1px solid rgba(var(--gold2-rgb),.35)",
                          borderRadius:6, width:28, height:28,
                          color:"var(--gold2)", cursor:"pointer",
                          display:"grid", placeItems:"center",
                          fontFamily:"'Cinzel',serif", fontSize:14, lineHeight:1,
                          boxShadow:"0 0 8px rgba(var(--gold2-rgb),.18) inset",
                          flexShrink:0, transition:"all .15s",
                        }}>◂</button>
              )}
              {/* Avatar + name area = tap-target for ProfileModal.
                  The whole row is clickable; the avatar is the visual
                  affordance ("this is a person → tap for profile"). */}
              <button onClick={() => {
                if (!onProfileClick) return;
                haptic("select"); onProfileClick();
              }}
                aria-label={safeT("profile_modal_title")}
                title={safeT("profile_modal_title")}
                disabled={!onProfileClick}
                style={{
                  display:"flex", alignItems:"center", gap:9,
                  padding:"3px 9px 3px 4px", borderRadius:8,
                  background:"transparent", border:"1px solid transparent",
                  color:"inherit", cursor: onProfileClick ? "pointer" : "default",
                  fontFamily:"inherit", textAlign:"left",
                  minWidth:0, flex:1, maxWidth:"100%",
                  transition:"all .12s",
                }}>
                {/* Realm-emoji avatar (compact, with subtle glow per realm).
                    Karma-divergence red dot floats over the top-right of the
                    avatar so the alert survives the chip removal. */}
                <div style={{
                  position:"relative", flexShrink:0,
                }}>
                  <RealmAvatar realm={player.realm} size={34} />
                  {player.karma_diverged && (
                    <span style={{
                      position:"absolute", top:-2, right:-2,
                      width:9, height:9, borderRadius:5,
                      background:"var(--red)",
                      boxShadow:"0 0 6px rgba(var(--red-rgb),.85)",
                      border:"1.5px solid rgba(var(--surface2-rgb),.95)",
                    }} />
                  )}
                </div>
                <div style={{ minWidth:0, flex:1 }}>
                  <div style={_ondaFrame ? {
                    // ⚠️ Aqui o nome PODE cortar, e é deliberado: o cabeçalho tem
                    // 390px e o nome chega aos 63 caracteres. Quem quer o nome
                    // inteiro tem-no 60px abaixo, em Cormorant a 44px, sem
                    // corte nenhum — e é á que ele é dito.
                    fontFamily: NIV_ONDA.serif, fontSize:20, fontWeight:500,
                    letterSpacing:"-.01em", color: NIV_ONDA.paper,
                    whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis",
                  } : {
                    fontFamily:"'Cinzel',serif", fontSize:18, fontWeight:700, letterSpacing:.5,
                    background:"linear-gradient(90deg,var(--gold3),var(--gold2),var(--gold))",
                    WebkitBackgroundClip:"text", backgroundClip:"text", WebkitTextFillColor:"transparent",
                    whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis",
                  }}>{player.dao_name}</div>
                  {player.active_title && (
                    <div style={{
                      fontSize:10, color:"rgba(var(--gold-rgb),.78)", marginTop:1, letterSpacing:.3,
                      whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis",
                    }}>
                      {t("title_prefix")} {player.active_title}
                    </div>
                  )}
                </div>
              </button>
            </div>
            <div style={{ display:"inline-flex", alignItems:"center", gap:8 }}>
              {/* v14.7 Item 4 — Notifications bell. Click opens NotificationsModal.
                  Hidden until App passes onBellClick (always set in current flow,
                  but defensive for older test contexts). Red dot with count when
                  notifCount > 0. */}
              {onBellClick && (
                <button
                  onClick={(e) => { e.stopPropagation(); haptic("select"); onBellClick(); }}
                  aria-label={t("notif_inbox_open") || "Notifications"}
                  style={{
                    position:"relative",
                    background:"rgba(0,0,0,.45)",
                    border:`1px solid ${notifCount > 0 ? "rgba(var(--red-rgb),.55)" : "rgba(var(--gold2-rgb),.35)"}`,
                    borderRadius:8, width:32, height:32,
                    display:"grid", placeItems:"center",
                    color:"var(--gold2)", cursor:"pointer",
                    fontSize:15, padding:0,
                    boxShadow: notifCount > 0
                      ? "0 0 10px rgba(var(--red-rgb),.45)"
                      : "0 0 6px rgba(var(--gold2-rgb),.18)",
                    transition:"all .15s",
                  }}>
                  {/* 鐘 o sino do templo. `aria-label` já existia acima, portanto
                      a marca não perde nome nenhum ao substituir o emoji. */}
                  {ico("🔔", "bell", { size:17 })}
                  {notifCount > 0 && (
                    <span style={{
                      position:"absolute", top:-3, right:-3,
                      minWidth:14, height:14, padding:"0 3px",
                      borderRadius:7,
                      background:"var(--red)",
                      color:"#fff", fontSize:9, fontWeight:700,
                      lineHeight:"14px", textAlign:"center",
                      boxShadow:"0 0 6px rgba(var(--red-rgb),.7)",
                      fontFamily:"'Cinzel',serif",
                    }}>
                      {notifCount > 99 ? "99+" : notifCount}
                    </span>
                  )}
                </button>
              )}
              {/* 2026-05-26 — Continent / Path / Karma chips REMOVED from
                  header. They live inside ProfileModal now (tap the
                  name+avatar area to open). A small red-dot indicator on
                  the avatar shows when karma diverged from path so the
                  cultivator still notices alerts without 4 separate chips. */}
              <div style={{
                display:"inline-flex", flexDirection:"column", alignItems:"center",
                padding:"6px 12px 5px", borderRadius:6, border:`1px solid ${rc}`,
                background:"rgba(0,0,0,.5)", boxShadow:`0 0 14px ${cssHex(rc)}55`,
                whiteSpace:"nowrap", gap:1, position:"relative",
              }}>
                {/* 印 O CHIP DO REINO — e a decisão aqui foi NÃO pôr marca nenhuma.
                    O pictograma que estava nesta linha dizia *o reino*; e o reino
                    já está dito, na linha de baixo, em PALAVRAS e na língua do
                    jogador. Uma marca aqui só podia ser o 山 da montanha — que na
                    barra de baixo quer dizer **Casa**. O mesmo glifo com dois
                    sentidos no mesmo ecrã é pior do que o emoji que veio
                    substituir. Com a flag ON o lugar do símbolo passa a ser
                    TIPOGRAFIA: o nome do reino sobe para o corpo grande e a
                    camada fica dita por extenso, em vez de um número nu ao lado.
                    ⚠️ A régua do desenho: *"o vazio é a composição"* — mas um
                    buraco não é vazio. O chip mantém a massa e a cor do reino;
                    o que sai é a repetição, não a informação. */}
                {/* ⚠️ O ramo LIGADO sai para uma variável e o ternário fica curto
                    DE PROPÓSITO: a auditoria só reconhece um literal como
                    "protegido pela flag" se o portão estiver a menos de 420
                    caracteres dele, e um ramo ON gordo empurrava o
                    `player.realm_emoji` para fora dessa janela — a medição
                    passava a acusar de CRU um sítio que está gated. Código que
                    a medição consegue ler é uma exigência, não um estilo. */}
                {iconografiaOn() ? _realmChipTypo : (
                  <React.Fragment>
                    <div style={{ fontSize:18, lineHeight:1 }}>{player.realm_emoji}</div>
                    <div style={{ fontSize:9, color:rc, letterSpacing:.5, fontFamily:"'Cinzel',serif", fontWeight:600 }}>
                      {realmShort(player.realm)} {player.sub_layer}
                    </div>
                  </React.Fragment>
                )}
              </div>
            </div>
          </div>
          <div style={{ display:"flex", gap:12, fontSize:12, flexWrap:"wrap", alignItems:"center" }}>
            {/* Hotfix "A Volta" 2026-07-07 — badge do mundo ativo. SÓ renderiza
                em mundos secundários (main = byte-idêntico): mata a confusão
                main/test quando a mesma conta alterna servidores no lobby. */}
            {player.world_key && player.world_key !== "main" && (
              <span style={{
                display:"inline-flex", alignItems:"center", gap:4,
                padding:"3px 9px", borderRadius:8,
                background:"rgba(90,120,255,.12)",
                border:"1px solid rgba(var(--accent2-rgb),.45)",
                color:"#aebcff", fontSize:11, letterSpacing:.4,
                fontFamily:"'Cinzel',serif", fontWeight:600,
                boxShadow:"0 0 8px rgba(var(--accent2-rgb),.2)",
              }}>
                {/* 界 — "mundo". ⚠️ Não é marca SVG de propósito: não existe
                    pictograma honesto para *"você está no servidor s2"*, e
                    inventar um dava um ícone a mais para o jogador decifrar. O
                    漢字 é vocabulário da casa (já cá vivem 68 no i18n do
                    mini-app, e 修己途道 no `tabs.js`), não muda de forma entre
                    aparelhos e a auditoria não o conta como emoji do sistema —
                    porque foi escolhido, não herdado. */}
                {iconografiaOn() ? "界" : "🌐"} {player.world_key}
              </span>
            )}
            {/* Tap jade → opens Premium Shop modal (Taoist Idle Immortal style).
                The chip becomes a button when onJadeClick is provided so the
                Shop is more discoverable for paying players, without nesting
                a tab inside another tab — the shop opens as a full-screen
                modal preserving the current tab context. */}
            {onJadeClick ? (
              <button onClick={(e) => { e.stopPropagation(); haptic("select"); onJadeClick(); }}
                aria-label={t("shop_open_via_jade")}
                style={{
                  display:"inline-flex", alignItems:"center", gap:4,
                  padding:"3px 9px", borderRadius:8,
                  background:"linear-gradient(180deg, rgba(var(--jade-rgb),.16), rgba(20,60,40,.18))",
                  border:"1px solid rgba(var(--jade-rgb),.45)",
                  color:"rgba(200,220,255,.78)", cursor:"pointer",
                  fontSize:12, fontFamily:"inherit", letterSpacing:.2,
                  boxShadow:"0 0 10px rgba(var(--jade-rgb),.18)",
                  transition:"all .15s",
                }}>
                {/* 印 O cabecalho e' o unico bloco que aparece em TODAS as telas, e as
                     tres moedas eram tres emoji do sistema — a azul da Apple, a cinzenta
                     do Android, a amarela do Windows, lado a lado com o ouro da casa.
                     O numero ao lado ja' diz o que e' cada uma, portanto a marca nao
                     precisa de `title` (o botao ja' tem `aria-label`). */}
                <span style={{ filter:"drop-shadow(0 0 5px rgba(var(--jade-rgb),.7))",
                               ...(markOn("jade") ? { display:"inline-flex", color:"var(--jade)" } : {}) }}>{ico("💎","jade",{ size:14 })}</span>
                <b style={{ color:"var(--text)", fontWeight:600 }}>{fmtNum(player.spirit_jade)}</b>
                <span style={{ fontSize:9, color:"var(--jade)", marginLeft:2, fontFamily:"'Cinzel',serif", letterSpacing:.4 }}>+</span>
              </button>
            ) : (
              <span style={{ display:"inline-flex", alignItems:"center", gap:4, color:"rgba(200,220,255,.6)" }}>
                {markOn("jade")
                  ? <span style={{ display:"inline-flex", color:"var(--jade)" }}><Mark name="jade" size={14} /></span>
                  : "💎"} <b style={{ color:"var(--text)", fontWeight:600 }}>{fmtNum(player.spirit_jade)}</b>
              </span>
            )}
            <span style={{ display:"inline-flex", alignItems:"center", gap:4, color:"rgba(200,220,255,.6)" }}>
              {markOn("stone")
                ? <span style={{ display:"inline-flex", color:"var(--muted)" }}><Mark name="stone" size={14} /></span>
                : "🪨"} <b style={{ color:"var(--text)", fontWeight:600 }}>{fmtNum(player.spirit_stones)}</b>
            </span>
            {player.celestial_fragments > 0 && (
              <span style={{ display:"inline-flex", alignItems:"center", gap:4, color:"rgba(200,220,255,.6)" }}>
                {markOn("shard")
                  ? <span style={{ display:"inline-flex", color:"var(--gold2)" }}><Mark name="shard" size={14} /></span>
                  : "✨"} <b style={{ color:"var(--text)", fontWeight:600 }}>{fmtNum(player.celestial_fragments)}</b>
              </span>
            )}
            {/* Progressão Visível — the anchored Poder de Combate that count-ups
                on every upgrade (realm-up, equip, pílula, corpo). Gated: absent on
                `main` (display_combat_power=null) → header byte-identical. */}
            {typeof featureEnabled === "function" && featureEnabled("progressao_visivel")
             && player.display_combat_power != null && (
              <span title={t("vp_combat_power")}
                    style={{ display:"inline-flex", alignItems:"center", gap:4, color:"rgba(200,220,255,.6)" }}>
                <span style={{ filter:"drop-shadow(0 0 5px rgba(var(--red-rgb),.55))",
                               ...(markOn("sword") ? { display:"inline-flex", color:"var(--red)" } : {}) }}>{ico("⚔️","sword",{ size:14 })}</span>
                <b style={{ color:"var(--text)", fontWeight:600 }}>
                  <CountUp value={player.display_combat_power} />
                </b>
              </span>
            )}
            <span style={{ marginLeft:"auto", fontSize:10.5, fontFamily:"'Cinzel',serif", color:"var(--gold2)", letterSpacing:.3 }}>
              {player.spirit_root_emoji} {player.spirit_root}
            </span>
          </div>
          <div style={{ position:"absolute", bottom:0, left:16, right:16, height:1,
            background:"linear-gradient(90deg,transparent,rgba(var(--gold-rgb),.3),rgba(var(--gold-rgb),.5),rgba(var(--gold-rgb),.3),transparent)" }} />
        </div>
      );
    }

    // ─── 印 AS MARCAS — a iconografia da casa (2026-09-08) ────────────────────
    //
    // PORQUE ISTO EXISTE
    // ------------------
    // Ordem do owner (2026-09-07, textual): *"fora orb outra coisa nada de
    // icone no game mais. entende? icones genericos bom."*
    //
    // Medido a 2026-09-08 em `components/{ui,tabs,app}.js`: **194 emoji
    // distintos, 1638 ocorrencias**. O defeito nao e' "sao feios" — e' que
    // **nao sao nossos e mudam de forma**. Um emoji e' desenhado pela FONTE DO
    // APARELHO: o pagode no iPhone, no Android e no Windows sao tres
    // ilustracoes diferentes, com tres paletas que ninguem aqui escolheu. O
    // jogo passou WEB-D (a pele quente), A CARTA e O CULTIVADOR a construir uma
    // linguagem de tinta quente e cinabrio — e depois entregava a NAVEGACAO a
    // um conjunto de pictogramas coloridos da Apple. E' exactamente o caso de
    // aviso do `GameDesign/LINGUAGEM_VISUAL_WEB_C.md` (Achado 2): o *Amazing
    // Cultivation Simulator*, jogo chines de cultivo, foi lido como *"RimWorld
    // chines"* POR CAUSA DA UI.
    //
    // A DECISAO DE FORMA — e porque NAO e' uma fonte CJK
    // --------------------------------------------------
    // O mini-app **nao carrega** uma face CJK. A 19px o hanzi cai no fallback do
    // sistema, que muda de aparelho para aparelho — seria trocar um conjunto de
    // pictogramas alheios por outro. Foi por isso que o selo 朱砂 ja' e' SVG
    // (`Mecanicas/miniapp.md` §1.8.3), e a mesma razao vale aqui.
    // ⇒ **Marcas SVG desenhadas, `currentColor`, traco, zero preenchimento
    // chapado, zero cor propria** — a cor vem do token do sitio onde vivem,
    // como a `SealMark` ja' faz.
    //
    // A GRELHA (o que faz as 40 parecerem UM conjunto e nao 40 decisoes)
    // -----------------------------------------------------------------
    //   viewBox 24x24 · area viva 3..21 · traco 1.6 · pontas e juntas redondas
    //   fill:none (os `c` sao pontos cheios, deliberados: olho, contas, cabeca)
    //   nunca mais de ~5 tracos por marca — a barra de baixo desenha a 20px
    //
    // ⚠️ **O sparkle de quatro pontas ESTA' PROIBIDO NESTE FICHEIRO.** A estrela
    // concava e' o glifo que a industria usa desde 2023 para dizer *"gerado por
    // IA"* — foi ela, no centro do orbe, que o owner leu como *"muito AI"* a
    // 2026-09-07. O ceu do Nivrael desenha-se com **pontos redondos ligados**
    // (星象, a marca `stars`), nunca com sparkles.
    //
    // ⚠️ **Uma marca sem NOME e' pior do que um emoji.** Toda marca ou tem
    // rotulo ao lado (o trilho, os cartoes, as seccoes) ou recebe `title` e sai
    // com `aria-label` (a barra de baixo, os slots). Lei §1.
    var NIV_MARK_GRID = { view: 24, stroke: 1.6 };

    // `p` = tracos (fill:none) · `o` = circulos em contorno · `c` = pontos cheios
    var NIV_MARKS = {
      // ── navegacao: os 24 destinos de TAB_DEFS ──────────────────────────────
      // 山 — uma montanha, muitos caminhos. A espinha do jogo e' a
      // casa do jogador.
      mountain:   { p:["M2.8 19.4 L9.4 7.6 L15.6 19.4", "M12.4 19.4 L17 11.2 L21.2 19.4"] },
      // 坐 — a figura sentada. E' a identidade que O CULTIVADOR (07/09) poe no
      // centro da tela do Cultivo; aqui ela e' a propria aba.
      seated:     { c:[[12,6.9,2.3]],
                    p:["M7 18 C7.5 13.4 9.3 11.3 12 11.3 C14.7 11.3 16.5 13.4 17 18",
                       "M5.6 18.1 C8.2 19.8 15.8 19.8 18.4 18.1"] },
      // 宗 — o pagode de tres beirais. A casa que ensina.
      pagoda:     { p:["M12 3.6 V6.4", "M8.4 8.8 C9.6 7.4 14.4 7.4 15.6 8.8",
                       "M6.6 13.2 C8.4 11.6 15.6 11.6 17.4 13.2",
                       "M4.6 17.8 C7.2 16 16.8 16 19.4 17.8", "M8 20.4 H16"] },
      // 盟 — dois que se ligam. A guilda e' gente, nao um predio.
      allies:     { c:[[8.4,7.9,2.1],[15.6,7.9,2.1]],
                    p:["M4 19.2 C4 14.6 5.8 12.5 8.4 12.5 C10.4 12.5 11.6 13.7 12 15.5 C12.4 13.7 13.6 12.5 15.6 12.5 C18.2 12.5 20 14.6 20 19.2"] },
      // 饕餮 — a mascara de besta do bronze chines: a testa recta, a mandibula, os
      // dois olhos e dois chifres FINOS que sobem por fora. QUARTA tentativa, e as
      // tres anteriores morreram AO OLHAR, cada uma por seu motivo: o S com
      // espinhas lia-se como grafico de linhas; o anel fechado (团龙) lia-se como
      // maca; e chifres TRIANGULARES colados a cabeca liam-se como orelhas de GATO
      // (o que era pior, porque a aba das bestas fica ao lado). Uma silhueta
      // simetrica e fechada sobrevive a 20px; uma serpentina nao. E o taotie e' o
      // vocabulario do genero, nao um cranio de MMO.
      dragon:     { c:[[9.4,13,1.05],[14.6,13,1.05]],
                    p:["M4.4 9.8 C7.6 8.2 16.4 8.2 19.6 9.8",
                       "M6 12.4 C6 17.4 8.6 20.3 12 20.3 C15.4 20.3 18 17.4 18 12.4",
                       "M4.9 9.6 C3.6 7.3 3.4 4.7 4.5 2.6",
                       "M19.1 9.6 C20.4 7.3 20.6 4.7 19.5 2.6"] },
      // 城 — a muralha com beiral e o portao. As Cinco Cidades do MV-9.
      city:       { p:["M3.4 20 H20.6", "M5.4 20 V12.6 H18.6 V20",
                       "M4 12.6 C6.4 10.8 17.6 10.8 20 12.6",
                       "M9.8 20 V15.6 C9.8 14.2 14.2 14.2 14.2 15.6 V20"] },
      // 罗盘 — a agulha. Sair daqui e' a unica forma de ver o continente.
      compass:    { o:[[12,12,8.4]], p:["M15 9 L10.4 10.8 L9 15 L13.6 13.2 Z"] },
      // 阵 — a matriz. "Estar na caverna" e' ter uma Formacao viva (MV-4).
      formation:  { c:[[7.4,7.4,0.85],[16.6,7.4,0.85],[16.6,16.6,0.85],[7.4,16.6,0.85]],
                    p:["M12 3.8 L20.2 12 L12 20.2 L3.8 12 Z",
                       "M12 8.4 L15.6 12 L12 15.6 L8.4 12 Z"] },
      // 门 — o portal dentro do portal. As 23 masmorras entram-se por uma porta.
      portal:     { p:["M4.6 20.4 V12.2 C4.6 7.4 8.2 4.6 12 4.6 C15.8 4.6 19.4 7.4 19.4 12.2 V20.4",
                       "M8.8 20.4 V12.6 C8.8 9.8 10.3 8.4 12 8.4 C13.7 8.4 15.2 9.8 15.2 12.6 V20.4"] },
      // 鼎 — o caldeirao de tres pes com as duas orelhas. Alquimia E forja.
      cauldron:   { p:["M5.2 9.4 H18.8",
                       "M7 9.4 C7 15.1 9.2 17.7 12 17.7 C14.8 17.7 17 15.1 17 9.4",
                       "M6.8 9.4 C6.8 7.2 8.8 7.2 8.8 9.4", "M15.2 9.4 C15.2 7.2 17.2 7.2 17.2 9.4",
                       "M9.2 17.9 L8.2 20.9", "M14.8 17.9 L15.8 20.9", "M12 17.9 V20.9"] },
      // 劍 — UMA lamina, de pe', com borla. Duas espadas cruzadas sao vocabulario
      // de MMO ocidental (regra 3 da regua); uma espada de pe' e' wuxia.
      sword:      { p:["M10.7 14.4 V6.5 L12 3.4 L13.3 6.5 V14.4 Z", "M8.6 14.8 H15.4",
                       "M12 15 V18.8", "M12 18.8 C13.4 19.4 13.8 20.7 13.1 21.4"] },
      // 爪 — a pata. As bestas espirituais.
      paw:        { c:[[7.2,9.6,1.65],[10.9,7.5,1.75],[15,7.7,1.75],[18.2,10.4,1.6]],
                    p:["M8.2 15.8 C8.2 13.1 10 11.9 12.4 11.9 C14.8 11.9 16.6 13.1 16.6 15.8 C16.6 19 14.6 20.6 12.4 20.6 C10.2 20.6 8.2 19 8.2 15.8 Z"] },
      // 旗 — a bandeira de andorinha. A faccao marcha (MV-8).
      banner:     { p:["M6.6 3.2 V20.8", "M6.6 4.8 H19.2 L16 8.6 L19.2 12.4 H6.6"] },
      // 月 — a lua com duas estrelas REDONDAS. Uma carta de estrelas (pontos
      // ligados por uma linha) lia-se como grafico; a lua e' uma silhueta fechada.
      // ⚠️ Deliberadamente NAO e' um sparkle de quatro pontas (ver o aviso acima).
      heavens:    { c:[[19.7,7.2,1.15],[21.2,12.2,0.85]],
                    p:["M16.2 4.2 A9 9 0 1 0 16.2 19.8 A7.2 7.2 0 1 1 16.2 4.2 Z"] },
      // 大 — a postura de pe', com a faixa da tempera. Difere da `seated` pela
      // POSE: pernas abertas, bracos em arco, sem a base de lotus.
      stance:     { c:[[12,4.8,2.1]],
                    p:["M12 7.2 V14.8", "M5.6 10.6 C8.4 12.9 15.6 12.9 18.4 10.6",
                       "M12 14.8 L7.4 21", "M12 14.8 L16.6 21",
                       "M9.5 10.3 H14.5", "M9.9 13.5 H14.1"] },
      // 雙環 — os dois aneis de jade entrelacados. ⚠️ A 1a versao era o fio
      // vermelho atado (dois cordoes a cruzarem-se num no'), e AO OLHAR no trilho
      // de desktop ela lia-se como um ✕ — que numa navegacao quer dizer FECHAR.
      // O no' central desaparecia a 15px e so' sobravam as duas diagonais. Dois
      // aneis entrelacados nunca dizem "cancelar", e continuam do genero.
      knot:       { o:[[9.3,12,4.6],[14.7,12,4.6]] },
      // 碑 — a estela gravada, com base. As conquistas ficam em pedra; o `tally`
      // pendura-se e esta cravou-se — e' por ai' que se distinguem a 16px.
      stele:      { p:["M7.4 20.4 V7.6 C7.4 4.6 16.6 4.6 16.6 7.6 V20.4",
                       "M5.6 20.6 H18.4", "M9.9 10.8 H14.1", "M9.9 13.8 H14.1", "M9.9 16.8 H12.8"] },
      // 牌 — a tabuleta de madeira pendurada. O passe conta-se em marcas.
      tally:      { o:[[12,8.2,1]],
                    p:["M8 7.4 C8 4 16 4 16 7.4 V18.6 C16 20.4 8 20.4 8 18.6 Z",
                       "M10 12.4 H14", "M10 15.4 H14"] },
      // 榜 — a lista afixada: tres reguas a encurtar, com o ponto do lugar.
      // NAO e' um trofeu (vocabulario desportivo ocidental).
      ranks:      { c:[[4.8,7.6,1.2],[4.8,12.6,1.2],[4.8,17.6,1.2]],
                    p:["M7.6 7.6 H20", "M7.6 12.6 H17.4", "M7.6 17.6 H14.6"] },
      // 囊 — a bolsa atada. O Anel Espacial visto por fora.
      pouch:      { p:["M6.4 10 H17.6",
                       "M6.4 10 C4.4 13 4.4 20.4 12 20.4 C19.6 20.4 19.6 13 17.6 10",
                       "M9.2 10 C9.2 6 14.8 6 14.8 10"] },
      // 榜文 — o pergaminho pendurado. A missao afixa-se, nao se "aceita num menu".
      notice:     { p:["M4.8 5.4 H19.2", "M4.8 18.6 H19.2", "M6.8 5.4 V18.6",
                       "M17.2 5.4 V18.6", "M9.6 11.4 H14.4"] },
      // 玉佩 — o disco de jade com borla. A loja vende jade, nao "moedas".
      jade:       { o:[[12,10.4,6.2],[12,10.4,2]],
                    p:["M9.6 16.2 L8.4 20.8", "M12 16.6 V21.1", "M14.4 16.2 L15.6 20.8"] },
      // 方孔錢 — a moeda de furo quadrado. O mercado entre jogadores.
      coin:       { o:[[12,12,8.1]], p:["M9.4 9.4 H14.6 V14.6 H9.4 Z"] },
      // 鐘 — o sino do templo. O anuncio bate-se, nao "notifica".
      bell:       { o:[[12,4.4,1.2]],
                    p:["M7 18.4 C7 12 8.4 6.4 12 6.4 C15.6 6.4 17 12 17 18.4",
                       "M5.6 18.4 C8 20.2 16 20.2 18.4 18.4", "M7.8 14.4 H16.2"] },
      // 筆 — o pincel: cabo, virola, tufo. "Voce escreve o seu proprio caminho."
      // ⚠️ Deliberadamente NAO e' uma roda dentada — a engrenagem e' a marca do
      // painel de qualquer SaaS do mundo (pergunta 1 da regua).
      brush:      { p:["M11.2 2.6 H12.8 V8.8 H11.2 Z", "M9.2 8.8 H14.8",
                       "M9.2 9 C8.4 13 9.6 17.4 12 21.6 C14.4 17.4 15.6 13 14.8 9 Z"] },
      // o canario do Manifesto de Superficie (dormante, so' aparece com a flag).
      flask:      { p:["M10 3.6 H14", "M10.8 3.6 V9.4 L6.6 18.2 C5.9 19.7 6.8 20.8 8.3 20.8 H15.7 C17.2 20.8 18.1 19.7 17.4 18.2 L13.2 9.4 V3.6",
                       "M8.6 15 H15.4"] },

      // ── seccoes e slots da mochila ─────────────────────────────────────────
      // 葫蘆 — a cabaca. E' onde a pilula vive, em todo o genero.
      gourd:      { p:["M10.2 3.4 H13.8", "M12 3.4 V5.2",
                       "M9.4 8.4 C9.4 10.4 10.8 11.2 10.8 12.4 C10.8 13.8 6.8 14.8 6.8 17.6 C6.8 19.8 9 21 12 21 C15 21 17.2 19.8 17.2 17.6 C17.2 14.8 13.2 13.8 13.2 12.4 C13.2 11.2 14.6 10.4 14.6 8.4 C14.6 6.6 13.4 5.2 12 5.2 C10.6 5.2 9.4 6.6 9.4 8.4 Z"] },
      // 草 — o ramo de duas folhas.
      herb:       { p:["M12 21 V4.4",
                       "M12 12.8 C9 12.8 6.6 11.2 6 8.4 C9 7.8 11.4 9.4 12 12.8 Z",
                       "M12 9.4 C15 9.4 17.4 7.8 18 5 C15 4.4 12.6 6 12 9.4 Z"] },
      // 石 — a pedra espiritual lapidada.
      stone:      { p:["M12 3.4 L19.6 8.6 L16.8 19.2 H7.2 L4.4 8.6 Z",
                       "M4.4 8.6 L12 11.6 L19.6 8.6", "M12 11.6 V19.2"] },
      // 碎 — a lasca. Ao lado do `stone` (simetrico, lapidado) ela e' inclinada e
      // partida: e' isso que separa "uma pedra" de "um fragmento" a 16px.
      shard:      { p:["M12.8 2.8 L19.8 13.2 L9.2 21.2 L4.2 11 Z", "M4.2 11 L12.8 2.8",
                       "M9.2 21.2 L11.4 10.6"] },
      // 包袱 — a trouxa com laco: a recompensa.
      gift:       { p:["M5.6 11.2 C5.6 9.6 18.4 9.6 18.4 11.2 V18.4 C18.4 20.4 5.6 20.4 5.6 18.4 Z",
                       "M8.8 10.4 C7.2 7.6 10.6 5.9 11.7 8.8",
                       "M15.2 10.4 C16.8 7.6 13.4 5.9 12.3 8.8", "M12 8.8 V20.2"] },
      // 袍 — o manto: gola em V, mangas, faixa.
      robe:       { p:["M8.4 4 C8.4 7.2 15.6 7.2 15.6 4",
                       "M8.4 4 L4.6 6.6 L6.4 10.8 L8 10 V20.4 H16 V10 L17.6 10.8 L19.4 6.6 L15.6 4",
                       "M6.6 14.6 H17.4"] },
      // 戒 — o anel com a pedra em cunha.
      ring:       { o:[[12,14.9,5.3]], p:["M9.8 9.8 L12 5.4 L14.2 9.8"] },
      // 念珠 — as contas. Oito, em circulo: le-se a 20px sem hesitar.
      beads:      { c:[[12,4.6,1.5],[17.3,7,1.4],[19.5,12.3,1.4],[17.3,17.6,1.4],
                       [12,20,1.5],[6.7,17.6,1.4],[4.5,12.3,1.4],[6.7,7,1.4]] },
      // 雲 — a nuvem 如意. Lei da Adaptacao: a montaria mortal e' o primeiro
      // degrau de uma escada que acaba em ir de nuvem.
      cloud:      { p:["M4.6 16.8 C2.9 16.8 2.7 13.9 4.7 13.5 C4.3 10.2 8.5 8.6 10.5 11.1 C11.3 8 15.9 7.8 16.9 11.1 C19.7 10.5 21.7 13.1 20.5 15.6 C19.9 16.6 18.7 16.8 17.5 16.8 Z"] },

      // ── estado e aviso ─────────────────────────────────────────────────────
      // 鎖 — o cadeado. Aqui a clareza ganha ao sabor: um cadeado le-se em
      // qualquer cultura, e um estado mal lido tranca o jogador (Lei §1).
      lock:       { c:[[12,14.2,1.15]],
                    p:["M4.8 10.6 H19.2 V18.4 H4.8 Z",
                       "M8.4 10.6 V8 C8.4 5.2 15.6 5.2 15.6 8 V10.6", "M12 15.4 V16.8"] },
      // 一炷香 — uma vara de incenso. No wuxia o tempo mede-se assim, e a
      // ampulheta e' o relogio de outra gente.
      incense:    { c:[[12,7.9,1.2]],
                    p:["M12 19.4 V9.1",
                       "M7.8 19.2 C7.8 21.6 16.2 21.6 16.2 19.2 Z",
                       "M12 6 C14.6 4.4 9.4 3.4 12 1.8"] },
      // aviso: um pictograma de seguranca. Nao ha versao "wuxia" de um aviso que
      // se leia mais depressa, e este tem de se ler primeiro.
      warn:       { c:[[12,17.3,1.1]], p:["M12 4.2 L21 19.8 H3 Z", "M12 9.6 V14.6"] },
      check:      { p:["M4.6 12.8 L9.8 18 L19.4 6.6"] },
      cross:      { p:["M6.2 6.2 L17.8 17.8", "M17.8 6.2 L6.2 17.8"] },
    };

    // A marca, desenhada. `currentColor` de proposito: a cor vem SEMPRE do
    // sitio onde ela vive (o trilho activo e' `--gold2`, a seccao e' `--muted`),
    // exactamente como a `SealMark`. Uma marca com cor propria seria mais um
    // conjunto alheio, so' que nosso.
    function Mark({ name, size = 20, title, style, strokeWidth }) {
      const m = NIV_MARKS[name];
      if (!m) return null;
      const sw = strokeWidth || NIV_MARK_GRID.stroke;
      return (
        <svg width={size} height={size} viewBox="0 0 24 24"
             role={title ? "img" : undefined} aria-hidden={title ? undefined : "true"}
             aria-label={title || undefined} focusable="false"
             style={Object.assign({ display:"block", flexShrink:0, overflow:"visible" }, style || {})}>
          <g fill="none" stroke="currentColor" strokeWidth={sw}
             strokeLinecap="round" strokeLinejoin="round">
            {(m.p || []).map((d, i) => <path key={"p" + i} d={d} />)}
            {(m.o || []).map((k, i) => <circle key={"o" + i} cx={k[0]} cy={k[1]} r={k[2]} />)}
          </g>
          {(m.c || []).map((k, i) => (
            <circle key={"c" + i} cx={k[0]} cy={k[1]} r={k[2]} fill="currentColor" stroke="none" />
          ))}
        </svg>
      );
    }

    // 印 O COMUTADOR. Com a flag OFF devolve **a mesma string de emoji de hoje**,
    // e por isso o DOM do `main` sai byte-identico — a promessa aos 248.
    // O `NIV_MARKS[name]` no AND nao e' paranoia: um `mark:` mal escrito passaria
    // a desenhar NADA no sitio de um icone, e um sitio vazio e' pior do que um
    // emoji feio (Lei §1). Sem marca ⇒ o emoji continua.
    function iconografiaOn() {
      return typeof featureEnabled === "function" && featureEnabled("iconografia");
    }
    // `markOn(name)` — "este sitio vai desenhar uma marca?". Existe porque
    // metade dos sitios precisa de mudar tambem o LAYOUT a' volta do icone (um
    // emoji e' texto e centra-se com `text-align`; um SVG e' um bloco e precisa
    // de flex) — e sem uma resposta unica as duas decisoes divergiam.
    function markOn(name) {
      return !!(name && NIV_MARKS[name] && iconografiaOn());
    }
    function ico(emoji, name, opts) {
      if (!name || !NIV_MARKS[name] || !iconografiaOn()) return emoji;
      const o = opts || {};
      return <Mark name={name} size={o.size || 20} title={o.title}
                   style={o.style} strokeWidth={o.strokeWidth} />;
    }

    // ─── 坐 O AVATAR DO JOGADOR — o dono ÚNICO da bolinha ────────────────────
    // Existia escrito **à mão em dois sítios**: o `PlayerHeader` (34px) e o
    // `ProfileModal` (60px). O mesmo `radial-gradient`, o mesmo array de 11
    // emoji, dois consertos por cada mudança. É a Lei 0 passo 2 na letra, e a
    // razão de o orbe ter sobrevivido a 07/09: a cena do Cultivo tinha um dono,
    // o avatar tinha dois.
    //
    // ⚠️ **É a TERCEIRA vida do orbe.** O 坐 O CULTIVADOR (07/09) matou a bola
    // na cena do Cultivo e o `ProfileModal` ficou com a dele; este ficou com a
    // terceira, e esta renderiza em TODAS as telas. Com a `iconografia` ON a
    // bola morre nos dois de uma vez.
    //
    // ⚠️ **E a marca NÃO é o reino — é VOCÊ.** O reino já está dito a 8px de
    // distância, em PALAVRAS e na língua do jogador, pelo chip ao lado. Um
    // avatar que repete o reino é a mesma informação duas vezes na mesma linha;
    // 坐 (a figura sentada) diz a única coisa que faltava dizer: *este é o
    // cultivador*. A cor do reino continua a pintar o anel — o reino não some,
    // deixa de ser dito duas vezes.
    //
    // ⚠️ E **não** é a figura `cultivator-*.webp`: essa só existe SENTADA (a lei
    // escrita no `CultivatorFigure`), e o cabeçalho está lá quando o jogador
    // está de pé. Uma figura a meditar por cima de um jogador que não medita é
    // exactamente a tela a contradizer-se que a WEB-E foi corrigir.
    var REALM_AVATAR_DEFS = [
      // O ramo OFF, um por reino, byte a byte o de hoje — e a marca ao lado,
      // como em `TAB_DEFS`. A tabela é por reino de propósito: é aqui que uma
      // marca POR reino entraria um dia sem tocar em mais nada.
      { emoji:"🪨", mark:"seated" }, { emoji:"☯️", mark:"seated" },
      { emoji:"🏯", mark:"seated" }, { emoji:"🔮", mark:"seated" },
      { emoji:"👻", mark:"seated" }, { emoji:"⚡", mark:"seated" },
      { emoji:"🐉", mark:"seated" }, { emoji:"🌟", mark:"seated" },
      { emoji:"💎", mark:"seated" }, { emoji:"👑", mark:"seated" },
      { emoji:"🌸", mark:"seated" },
    ];
    // ⚠️ Os dois tamanhos **não derivam** um do outro, e isso é medição, não
    // preguiça: os dois sítios à mão divergiam em SEIS valores (brilho .35/.4 ·
    // glow 9/20px · alfa 44/55 · inset 5/12px · alfa .15/.18 · anel .3/.4).
    // Derivar por regra mudava o DOM do ramo OFF, e a promessa aos jogadores é
    // que com a flag OFF o ecrã sai byte-idêntico. Ficam TABELADOS: uma tabela
    // num sítio continua a ser UM dono; duas cópias em dois ficheiros não.
    var REALM_AVATAR_TONES = {
      34: { hi:".35", glow:9,  ga:"44", inset:5,  ia:".15", ring:".3", font:17, mark:21 },
      60: { hi:".4",  glow:20, ga:"55", inset:12, ia:".18", ring:".4", font:32, mark:36 },
    };
    // 2026-09-13 — o dono passou a servir um tamanho que a tabela não tinha.
    // ⚠️ Antes, QUALQUER tamanho fora de {34,60} caía silenciosamente no tom de
    // 34: um avatar de 150px desenhava a marca a 21px — um ponto perdido no
    // meio de um disco. A tabela continua a mandar nos dois tamanhos que já
    // existiam (34 e 60 nunca chegam aqui ⇒ OFF-identidade intacta ao byte); só
    // o que não está nela é que passa a ser DERIVADO em vez de errado.
    function _realmAvatarTone(size) {
      const base = REALM_AVATAR_TONES[60];
      const k = size / 60;
      return { hi: base.hi, ga: base.ga, ia: base.ia, ring: base.ring,
               glow: Math.round(base.glow * k), inset: Math.round(base.inset * k),
               font: Math.round(base.font * k), mark: Math.round(base.mark * k) };
    }
    function RealmAvatar({ realm, size = 34, style }) {
      const r = Math.min(Math.max(realm || 0, 0), 10);
      const rc = realmHex(r);
      const tone = REALM_AVATAR_TONES[size] || _realmAvatarTone(size);
      const def = REALM_AVATAR_DEFS[r];
      const on = markOn(def.mark);
      // 印 A BOLA MORRE: com a flag ON não há esfera nenhuma — fica o disco de
      // tinta do fundo e **o anel do reino**, que é o que a bola estava a tentar
      // dizer com um gradiente de três paragens.
      //
      // ⚠️ A ORDEM das propriedades abaixo é a de hoje, e isso não é cosmética
      // de código: o ensaio do DOM comparou os dois lados e deu **8 abas
      // diferem** com os ficheiros do MESMO tamanho ao byte — a única diferença
      // era o `background` ter passado para depois do `fontSize` por causa de um
      // `...spread`. Os pixels eram iguais; o atributo `style` não era. Por isso
      // as três propriedades que JÁ existiam escolhem o valor por ternário, no
      // lugar onde sempre estiveram, e só a `color` — que é genuinamente nova —
      // entra pelo spread condicional.
      return (
        <div style={Object.assign({
          width:size, height:size, borderRadius:"50%",
          background: on
            ? "rgba(var(--surface-rgb),.55)"
            : `radial-gradient(circle at 35% 30%,rgba(255,240,200,${tone.hi}),transparent 50%),radial-gradient(circle at 50% 50%,${rc},rgba(var(--surface-rgb),.85) 75%)`,
          display:"grid", placeItems:"center",
          fontSize:tone.font, lineHeight:1,
          boxShadow: on
            ? `0 0 ${tone.glow}px ${cssHex(rc)}22`
            : `0 0 ${tone.glow}px ${cssHex(rc)}${tone.ga}, inset 0 0 ${tone.inset}px rgba(255,255,255,${tone.ia})`,
          border: on
            ? `1px solid ${rc}`
            : `1px solid rgba(var(--gold2-rgb),${tone.ring})`,
          ...(on ? { color:rc } : {}),
        }, style || {})}>
          {/* ⚠️ O `title` não é enfeite: uma marca SVG é MUDA para o leitor de
              ecrã, e o emoji de hoje ainda era anunciado. Sem ele a iconografia
              seria uma regressão de acessibilidade (a mesma regra da barra). */}
          {markOn(def.mark)
            ? <Mark name={def.mark} size={tone.mark} title={realmName(r)} />
            : def.emoji}
        </div>
      );
    }

    // ─── Bottom Nav (SVG cloud divider, label-above-icon, active glow) ───────
    // MA-32b — TAB_DEFS keeps ALL routes (hub-home migration must NOT delete
    // any existing destination — they're reachable as drill-ins from the
    // Home cards). BOTTOM_VISIBLE is the curated subset that actually
    // appears in the BottomNav. Tabs absent from BOTTOM_VISIBLE still
    // render via the same `tab` state — they're just not navigable from
    // the bottom strip.
    var TAB_DEFS = [
      { key:"home",          ico:"🏠", mark:"mountain", label_key:"tab_home" },
      { key:"cultivation",   ico:"☯️", mark:"seated", label_key:"tab_cultivation" },
      { key:"sect",          ico:"🏯", mark:"pagoda", label_key:"tab_sect" },
      { key:"guild",         ico:"🤝", mark:"allies", label_key:"tab_guild" },
      { key:"world_boss",    ico:"🐉", mark:"dragon", label_key:"tab_world_boss" },
      { key:"plaza",         ico:"🏙️", mark:"city", label_key:"tab_plaza" },
      { key:"explore",       ico:"🧭", mark:"compass", label_key:"tab_explore" },
      { key:"cavern",        ico:"🏯", mark:"formation", label_key:"tab_cavern" },
      { key:"dungeons",      ico:"🏛️", mark:"portal", label_key:"tab_dungeons" },
      { key:"crafting",      ico:"🛠️", mark:"cauldron", label_key:"tab_crafting" },
      { key:"combat",        ico:"⚔️", mark:"sword", label_key:"tab_combat" },
      { key:"beasts",        ico:"🐾", mark:"paw", label_key:"tab_beasts" },
      { key:"faction",       ico:"🔱", mark:"banner", label_key:"tab_faction" },
      { key:"celestial",     ico:"🌠", mark:"heavens", label_key:"tab_celestial" },
      { key:"body_tempering",ico:"💪", mark:"stance", label_key:"tab_body_tempering" },
      { key:"partner",       ico:"💞", mark:"knot", label_key:"tab_partner" },
      { key:"battle_pass",   ico:"🎫", mark:"tally", label_key:"tab_battle_pass" },
      { key:"leaderboard",   ico:"🏆", mark:"ranks", label_key:"tab_leaderboard" },
      { key:"inventory",     ico:"🎒", mark:"pouch", label_key:"tab_inventory" },
      { key:"quests",        ico:"🎯", mark:"notice", label_key:"tab_quests" },
      { key:"shop",          ico:"💎", mark:"jade", label_key:"tab_shop" },
      { key:"market",        ico:"💰", mark:"coin", label_key:"tab_market" },
      { key:"announcements", ico:"📜", mark:"bell", label_key:"tab_announcements" },
      { key:"settings",      ico:"⚙️", mark:"brush", label_key:"tab_settings" },
      // Sprint 0 (FF-3) — canary. `requires` gates a tab against the Surface
      // Manifest: it only renders where the feature is ON. OFF everywhere by
      // default → invisible on `main` and every world until toggled (s2) to
      // prove the gate, then left dormant. The pattern existing tabs follow:
      // NO `requires` → always render → `main` byte-identical.
      { key:"__manifest_canary", requires:"manifest_canary", ico:"🧪", mark:"flask", label_key:"tab_manifest_canary" },
    ];
    // The 8 main destinations, displayed evenly across the full phone width.
    // Owner request 2026-05-06: "tem que completar o telefone e nao ficar
    // faltando" — 5 was leaving empty space on the right. 8 fills cleanly
    // (~12% per slot) and still hits everything daily-touched.
    // Drill-in only (no slot in nav): Sect, Shop, Ranking, Announcements
    // (already reachable via Home cards).
    var BOTTOM_VISIBLE = ["home", "cultivation", "world_boss", "dungeons", "crafting", "inventory", "quests", "settings",
      // Sprint 0 (FF-3) — canary slot. Gated by `requires:'manifest_canary'`
      // below, so it is filtered out everywhere by default (main stays 8 slots,
      // byte-identical); appears only on a world where the flag is toggled ON.
      "__manifest_canary"];

    // WEB-D §1 — a MESMA pergunta, uma só resposta. O `app.js` já compunha
    // "superfície larga AND flag AND o componente existe" para decidir o
    // trilho; as ABAS precisam da mesma resposta para deixarem de assumir
    // 480px de largura (a grelha da Home fazia cartões de 514x514 num ecrã de
    // 1920 — medido). Duas cópias da conjunção divergiriam no primeiro sprint
    // que mexesse na flag, e o mini-app ficaria com trilho de desktop e
    // cartões de telemóvel — que foi exactamente o que a WEB-C entregou.
    function useWideShell() {
      const wide = useDesktopSurface();
      return wide
        && typeof featureEnabled === "function"
        && featureEnabled("superficie_desktop");
    }

    // ─── WEB-E 段 — o DIVISOR DE MOVIMENTO ──────────────────────────────────
    // A tela do Cultivo tinha 1985px de altura e CATORZE cartões com moldura
    // idêntica: um anúncio da loja lia-se tão importante como o seu Qi, porque
    // nada dizia o contrário. Isto não é decoração — é a estrutura a dizer uma
    // verdade sobre o conteúdo: o que está a ACONTECER agora (a cena, sem
    // rótulo — não se rotula o óbvio), o que você PRATICA, QUEM você é, e para
    // onde pode IR.
    //
    // O glifo é 漢字 e não passa pela i18n de propósito: 修 é 修 nas três
    // línguas, e é o mesmo vocabulário da porta (`login.html`). A régua tipográfica
    // é a dos grupos do trilho (9px, .22em, maiúsculas, `--muted2`), para as duas
    // superfícies falarem a mesma língua.
    // 坐 ONDA 1 — `anchorId` é ADITIVO e por omissão **undefined**: um atributo
    // `id` com valor `undefined` não é escrito no DOM, portanto os sítios que
    // não o passam desenham o mesmo markup, byte a byte. Existe porque as
    // âncoras da aba (`CultAnchors`) precisam de um alvo REAL para saltar — e
    // o alvo certo é a própria régua da secção, não um `<div>` novo à volta
    // dela (um invólucro mudaria o DOM também com a flag desligada).
    function SectionRule({ glyph, label, anchorId }) {
      return (
        <div id={anchorId} style={{ display:"flex", alignItems:"center", gap:9,
                      margin:"22px 2px 9px", userSelect:"none",
                      scrollMarginTop: anchorId ? 12 : undefined }}>
          {/* ⚠️ O glifo NAO leva o Cormorant: e' uma face latina, e um 漢字
              cai na fonte CJK do sistema de qualquer forma — declarar o
              Cormorant aqui so' engana quem ler o codigo. (Medido por contagem
              de pixels em canvas: 己 pinta 765px e um glifo REALMENTE em falta
              pinta 162 — renderiza sempre; o problema era o TAMANHO.)
              A 17px com opacidade .85 os tres tracos do 己 nao resolviam e ele
              lia-se como um rectangulo vazio. A 21px, cheio, e' um caracter. */}
          <span style={{ fontSize:21, lineHeight:1, color:"var(--gold)",
                         flexShrink:0, letterSpacing:0 }}>{glyph}</span>
          <span style={{ fontSize:9, letterSpacing:".22em", textTransform:"uppercase",
                         color:"var(--muted2)", whiteSpace:"nowrap", flexShrink:0 }}>
            {label}
          </span>
          {/* o fio de tinta que se esvai — 水墨: o vazio faz parte da composição */}
          <span aria-hidden="true" style={{ flex:1, height:1, minWidth:0,
                  background:"linear-gradient(90deg,rgba(var(--gold-rgb),.28),transparent)" }} />
        </div>
      );
    }

    // ─── WEB-C 兩面 — o TRILHO da superfície de desktop ──────────────────────
    // A barra inferior é um gesto de POLEGAR: 8 slots, o rótulo só no activo,
    // e 16 destinos sem lugar nenhum (alcançáveis só por drill-in). Num ecrã
    // largo há altura a mais e polegar a menos — o trilho inverte as duas
    // trocas: TODOS os destinos ficam à vista, com nome, sempre.
    //
    // ⚠️ Lei de Ferro da UI (a): 100% das features alcançáveis, zero órfãos.
    // Por isso o trilho não tem lista própria de teclas — agrupa `TAB_DEFS`, e
    // uma aba que não esteja em grupo nenhum cai no último em vez de
    // desaparecer. Entradas mudam, destinos NUNCA (MA-32b): o trilho não
    // inventa uma tela, só abre mais portas para as que já existem.
    var RAIL_GROUPS = [
      { key:"rail_group_self",   tabs:["home", "cultivation", "body_tempering", "cavern", "inventory", "quests"] },
      { key:"rail_group_world",  tabs:["plaza", "explore", "dungeons", "world_boss", "celestial"] },
      { key:"rail_group_people", tabs:["sect", "guild", "faction", "partner", "leaderboard", "market"] },
      { key:"rail_group_craft",  tabs:["crafting", "combat", "beasts"] },
      { key:"rail_group_gate",   tabs:["battle_pass", "shop", "announcements", "settings"] },
    ];

    function railSections() {
      const byKey = {};
      TAB_DEFS.forEach((td) => { byKey[td.key] = td; });
      const placed = {};
      const out = RAIL_GROUPS.map((g) => {
        const items = [];
        g.tabs.forEach((k) => {
          if (byKey[k]) { items.push(byKey[k]); placed[k] = true; }
        });
        return { key: g.key, items: items };
      });
      // A rede de segurança: uma aba nova em `TAB_DEFS` que ninguém agrupou
      // aparece na mesma (no último grupo). Sem isto, acrescentar uma tela
      // criava um órfão SILENCIOSO — e é exactamente assim que a Lei nº 1 se
      // perde: não por decisão, por esquecimento.
      const orfas = TAB_DEFS.filter((td) => !placed[td.key]);
      if (orfas.length) out[out.length - 1].items = out[out.length - 1].items.concat(orfas);
      return out;
    }

    // O invólucro das duas superfícies. No telemóvel é um Fragment — o DOM sai
    // BYTE-IDÊNTICO ao de hoje, que é a única forma de prometer aos 248 que
    // nada mudou. No desktop vira a coluna de conteúdo ao lado do trilho.
    // Um só cliente: a alternativa (duplicar a árvore) seriam duas verdades a
    // divergir a cada sprint (Lei §5).
    function SurfaceColumn({ on, children }) {
      if (!on) return <React.Fragment>{children}</React.Fragment>;
      return (
        <div style={{ flex:"1 1 0", minWidth:0, display:"flex", flexDirection:"column",
                      position:"relative", zIndex:2, height:"100%" }}>
          {children}
        </div>
      );
    }

    // ═══ 至 P5 — A LATERAL DO PC ([017] §1) ════════════════════════
    //
    // 🔴 O QUE ESTAVA AQUI, medido: **24 destinos = 1.131 px de trilho**, todos
    // abertos ao mesmo tempo, num ecra de 720 px. Oito ficavam por baixo da
    // dobra. E' a mesma doenca da chegada (21 portas iguais) do lado do PC.
    //
    // A decisao do Astra, e ele REVIU a propria escolha de barra superior da
    // [016] depois de eu lhe mandar a pesquisa:
    //
    //   *"Fica uma lateral com os cinco hubs (…) **So' o hub activo expoe os
    //   seus destinos**; os restantes conservam apenas o titulo. (…) Reservar
    //   cerca de **216 px expandida ou 64 px recolhida**."*
    //
    // ⚠️ O precedente e' o Melvor Idle — o idle RPG mais completo do browser,
    // com MAIS sistemas do que nos, que navega com uma lateral colapsavel de
    // quatro niveis. Mas a razao e' nossa, palavras dele: *"a lateral permite
    // alternar entre sistemas mantendo visiveis o lugar actual e os seus
    // destinos, sem consumir mais altura da cena. O precedente do Melvor
    // reforca esta escolha; **nao prova sozinho que ela seja superior**."*
    //
    // ⚠️ O RATO NAO E' O UNICO ACESSO: *"clique/toque e teclado abrem os
    // rotulos e o ramo. Hover pode antecipar essa abertura, **nunca ser o unico
    // acesso**. Sem saltos do conteudo ao passar o rato."* Por isso o ramo
    // abre-se pelo `tab` (o sitio onde o jogador ESTA'), e nao por `:hover`.
    var _RAIL_PREF = "niv_rail_recolhida";

    function SideRailHubs({ tab, setTab, player, onPorta }) {
      // ⚠️ `localStorage` pode rebentar (janela privada, dados bloqueados) e
      // pode voltar vazio. A preferencia e' uma comodidade por-visitante: se
      // falhar, abre-se expandida e o jogo nao da' por isso.
      const [recolhida, setRecolhida] = useState(function () {
        try { return window.localStorage.getItem(_RAIL_PREF) === "1"; }
        catch (e) { return false; }
      });
      function alternar() {
        setRecolhida(function (v) {
          const nv = !v;
          try { window.localStorage.setItem(_RAIL_PREF, nv ? "1" : "0"); } catch (e) {}
          return nv;
        });
      }
      const hubActivo = (HUB_DEFS.find(h => h.group.includes(tab)) || {}).key;
      const largura = recolhida ? 64 : 216;
      const gated = (td) => !td.requires
        || (typeof featureEnabled === "function" && featureEnabled(td.requires));

      return (
        <nav aria-label={t("rail_nav_label")} className="scroll-area nv-rail" style={{
          flex: "0 0 " + largura + "px", width: largura, height:"100%", overflowY:"auto",
          borderRight:"1px solid rgba(var(--gold-rgb),.16)",
          background:"linear-gradient(180deg, rgba(var(--surface2-rgb),.97), rgba(8,10,20,.99))",
          padding:"14px 0 20px", position:"relative", zIndex:6,
        }}>
          <div style={{ display:"flex", alignItems:"center",
                        justifyContent: recolhida ? "center" : "space-between",
                        gap:8, padding: recolhida ? "0 8px 14px" : "0 14px 14px" }}>
            {!recolhida && (
              <div style={{ minWidth:0 }}>
                <div style={{ fontFamily:"'Cormorant Garamond','Cinzel',serif", fontSize:21,
                              letterSpacing:".12em", color:"var(--gold2)", lineHeight:1 }}>
                  NIVRAEL
                </div>
              </div>
            )}
            {/* O interruptor. ⚠️ Alvo de 44 px e rotulo acessivel nos dois
                estados — recolhida, o unico texto do ecra e' este. */}
            <button type="button" onClick={alternar} className="nv-rail-item"
                    aria-label={t(recolhida ? "rail_expandir" : "rail_recolher")}
                    aria-expanded={!recolhida}
                    style={{ minWidth:44, minHeight:44, display:"grid", placeItems:"center",
                             background:"none", border:"1px solid rgba(var(--gold-rgb),.22)",
                             borderRadius:8, color:"var(--muted)", cursor:"pointer",
                             font:"inherit", flexShrink:0 }}>
              <Mark name={recolhida ? "portal" : "knot"} size={16} />
            </button>
          </div>

          {HUB_DEFS.map(function (h) {
            const aberto = hubActivo === h.key;
            const todos = aberto
              ? h.group.filter(k => !k.endsWith("_screen") && k !== "home")
                  .map(k => TAB_DEFS.find(td => td.key === k))
                  .filter(Boolean).filter(gated)
              : [];
            // 門 P6 — so' o proximo marco de cada hub fica na lista; o resto vai
            // para a consulta «Desbloqueios» (a entrada no fim do ramo).
            const ph = portasDoHub(player, todos.map(td => td.key), tab);
            const itens = todos.filter(td => ph.lista.some(x => x.key === td.key));
            return (
              <div key={h.key} style={{ marginBottom: aberto ? 10 : 2 }}>
                <button type="button" className="nv-rail-item"
                  aria-current={aberto ? "true" : undefined}
                  aria-label={recolhida ? t(h.label_key) : undefined}
                  onClick={() => { haptic("select"); setTab(h.landing); }}
                  style={{
                    display:"flex", alignItems:"center",
                    justifyContent: recolhida ? "center" : "flex-start",
                    gap:10, width:"100%", minHeight:44,
                    background: aberto ? "rgba(var(--gold-rgb),.10)" : "none",
                    border:"none",
                    borderLeft:"2px solid " + (aberto ? "var(--gold2)" : "transparent"),
                    color: aberto ? "var(--gold2)" : "var(--muted)",
                    padding: recolhida ? "0" : "0 16px", cursor:"pointer",
                    textAlign:"left", font:"inherit", fontSize:13,
                  }}>
                  <span style={{ display:"inline-flex", flexShrink:0 }}>
                    {ico(h.ico, h.mark, { size:18 })}
                  </span>
                  {/* ⚠️ Recolhida, o nome sai do ECRA mas nao da ARVORE: fica no
                      `aria-label` do botao. Cinco pictogramas mudos seriam uma
                      regressao de acessibilidade, e ja' foi essa a licao da
                      barra de baixo. */}
                  {!recolhida && <span style={{ minWidth:0 }}>{t(h.label_key)}</span>}
                </button>

                {/* 🔴 SO' O HUB ACTIVO expoe os destinos. Os outros quatro
                    conservam apenas o titulo — e' isto que impede o trilho de
                    voltar aos 1.131 px de 24 portas abertas ao mesmo tempo. */}
                {aberto && !recolhida && itens.map(function (td) {
                  const sel = tab === td.key;
                  // 門 P6 — a porta trancada CONTINUA na lista e diz porquê;
                  // tocar-lhe abre a consulta, nunca a aba que a recusaria.
                  const pp = portaDe(player, td.key);
                  if (pp.estado !== "aberta") {
                    return (
                      <button key={td.key} type="button" className="nv-rail-item"
                        aria-current={sel ? "page" : undefined}
                        aria-label={portaAria(t(td.label_key), pp)}
                        onClick={() => { haptic("select");
                                         if (onPorta) onPorta(h.key, td.key); else setTab(td.key); }}
                        style={{
                          display:"flex", alignItems:"center", justifyContent:"space-between",
                          gap:9, width:"100%", minHeight:36, background:"none", border:"none",
                          // o Astra (MESA [020]): a cor das abertas NAO seleccionadas,
                          // mesmo com o jogador dentro — *"a porta trancada nao ganha
                          // destaque por estar trancada"*; o `aria-current` diz onde esta'.
                          color:"var(--muted2)", padding:"0 16px 0 44px", cursor:"pointer",
                          textAlign:"left", font:"inherit", fontSize:12.5,
                        }}>
                        <span style={{ minWidth:0 }}>{t(td.label_key)}</span>
                        <PortaSelo porta={pp} />
                      </button>
                    );
                  }
                  return (
                    <button key={td.key} type="button" className="nv-rail-item"
                      aria-current={sel ? "page" : undefined}
                      onClick={() => { haptic("select"); setTab(td.key); }}
                      style={{
                        display:"flex", alignItems:"center", gap:9, width:"100%",
                        minHeight:36, background:"none", border:"none",
                        color: sel ? "var(--gold3)" : "var(--muted2)",
                        padding:"0 16px 0 44px", cursor:"pointer", textAlign:"left",
                        font:"inherit", fontSize:12.5,
                      }}>
                      <span style={{ minWidth:0 }}>{t(td.label_key)}</span>
                    </button>
                  );
                })}
                {/* 門 P6 — «Desbloqueios»: so' existe quando ha' portas FORA da
                    lista. Com uma unica trancada ela ja' esta' a' vista e abre a
                    mesma consulta — uma entrada a mais seria a mesma porta duas
                    vezes. */}
                {aberto && !recolhida && ph.distantes.length > 0 && (
                  <button type="button" className="nv-rail-item"
                    onClick={() => { haptic("select"); if (onPorta) onPorta(h.key, null); }}
                    style={{
                      display:"flex", alignItems:"center", justifyContent:"space-between",
                      gap:9, width:"100%", minHeight:36, background:"none", border:"none",
                      color:"var(--muted2)", padding:"0 16px 0 44px", cursor:"pointer",
                      textAlign:"left", font:"inherit", fontSize:12.5,
                    }}>
                    <span style={{ minWidth:0 }}>{t("porta_desbloqueios")}</span>
                    <PortaConta n={ph.distantes.length} />
                  </button>
                )}
              </div>
            );
          })}
        </nav>
      );
    }

    function SideRail({ tab, setTab }) {
      const sections = railSections();
      const gated = (td) => !td.requires
        || (typeof featureEnabled === "function" && featureEnabled(td.requires));
      // WEB-D §1 — MEDIDO a servir o jogo: 24 destinos = 1131px de trilho. Num
      // ecrã de 720px oito deles ficam por baixo da dobra e o `.nv-rail` (CSS)
      // devolve a barra que os anuncia. Falta a outra metade: se o jogador
      // ESTÁ nas Configurações, o trilho tem de o mostrar. Sem isto ele abre
      // o jogo na aba certa e o trilho jura que ela não existe.
      // `block:"nearest"` → não mexe quando o activo já está visível (o caso
      // comum), portanto nenhum salto gratuito ao trocar de aba.
      const railRef = useRef(null);
      useEffect(() => {
        const root = railRef.current;
        if (!root) return;
        const el = root.querySelector('[aria-current="page"]');
        if (!el || root.scrollHeight <= root.clientHeight) return;
        try { el.scrollIntoView({ block: "nearest" }); } catch (e) { /* no-op */ }
      }, [tab]);
      return (
        <nav aria-label={t("rail_nav_label")} ref={railRef} className="scroll-area nv-rail" style={{
          flex:"0 0 236px", width:236, height:"100%", overflowY:"auto",
          borderRight:"1px solid rgba(var(--gold-rgb),.16)",
          background:"linear-gradient(180deg, rgba(var(--surface2-rgb),.97), rgba(8,10,20,.99))",
          padding:"14px 0 20px", position:"relative", zIndex:6,
        }}>
          <div style={{ padding:"0 18px 14px" }}>
            <div style={{ fontFamily:"'Cormorant Garamond','Cinzel',serif", fontSize:23,
                          letterSpacing:".12em", color:"var(--gold2)", lineHeight:1 }}>
              NIVRAEL
            </div>
            <div style={{ fontSize:9.5, letterSpacing:".28em", textTransform:"uppercase",
                          color:"var(--muted2)", marginTop:6 }}>
              {t("rail_brand_sub")}
            </div>
          </div>
          {sections.map((sec) => {
            const items = sec.items.filter(gated);
            if (!items.length) return null;
            return (
              <div key={sec.key} style={{ marginBottom:9 }}>
                <div style={{ fontSize:9, letterSpacing:".22em", textTransform:"uppercase",
                              color:"var(--muted2)", padding:"0 18px 4px" }}>
                  {t(sec.key)}
                </div>
                {items.map((td) => {
                  const active = tab === td.key;
                  return (
                    <button key={td.key} className="nv-rail-item"
                      aria-current={active ? "page" : undefined}
                      onClick={() => { haptic("select"); setTab(td.key); }}
                      style={{
                        display:"flex", alignItems:"center", gap:10, width:"100%",
                        background: active ? "rgba(var(--gold-rgb),.10)" : "none",
                        border:"none", borderLeft:"2px solid " + (active ? "var(--gold2)" : "transparent"),
                        color: active ? "var(--gold2)" : "var(--muted)",
                        padding:"8px 18px", cursor:"pointer", textAlign:"left",
                        font:"inherit", fontSize:13, minHeight:31,
                        transition:"background .12s, color .12s",
                      }}>
                      {/* 印 A marca. O trilho tem SEMPRE o rotulo ao lado, portanto a
                           marca e' decorativa aqui (`aria-hidden` dentro do `Mark`):
                           dar-lhe `title` faria o leitor de ecra dizer o nome duas
                           vezes. Com a flag OFF isto e' a mesma `<span>{td.ico}</span>`
                           de hoje, caracter a caracter. */}
                      <span style={{ fontSize:15, lineHeight:1, opacity: active ? 1 : .72,
                                     width:19, textAlign:"center", flexShrink:0,
                                     display: markOn(td.mark) ? "flex" : undefined,
                                     justifyContent: markOn(td.mark) ? "center" : undefined }}>
                        {ico(td.ico, td.mark, { size:17 })}
                      </span>
                      <span style={{ overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap",
                                     minWidth:0, letterSpacing:".02em" }}>{t(td.label_key)}</span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </nav>
      );
    }

    function BottomNav({ tab, setTab }) {
      // Pre-MA-32b the nav was a horizontal scroll with fade indicators +
      // scrollIntoView on tab change. Now (8 slots × flex:1) the bar is fixed
      // width and never overflows, so all that machinery is removed.

      return (
        <div style={{
          position:"absolute", bottom:0, left:0, right:0, zIndex:5,
          display:"flex", flexDirection:"column",
        }}>
          <div style={{ position:"relative", height:20, overflow:"hidden", pointerEvents:"none" }}>
            <svg viewBox="0 0 480 20" preserveAspectRatio="none"
                 style={{ position:"absolute", bottom:0, left:0, width:"100%", height:"100%" }}>
              <defs>
                <linearGradient id="divGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="rgba(201,144,58,0)" />
                  <stop offset="20%" stopColor="rgba(201,144,58,0.6)" />
                  <stop offset="50%" stopColor="rgba(245,201,122,0.92)" />
                  <stop offset="80%" stopColor="rgba(201,144,58,0.6)" />
                  <stop offset="100%" stopColor="rgba(201,144,58,0)" />
                </linearGradient>
              </defs>
              <path d="M0,20 C40,14 70,6 105,10 C130,13 145,18 175,15 C200,12 215,5 240,8 C265,11 280,18 305,15 C330,12 345,5 375,8 C400,11 425,18 455,14 C470,11 480,8 480,8 L480,20Z"
                    fill="rgba(10,14,28,0.97)" />
              <path d="M0,20 C40,14 70,6 105,10 C130,13 145,18 175,15 C200,12 215,5 240,8 C265,11 280,18 305,15 C330,12 345,5 375,8 C400,11 425,18 455,14 C470,11 480,8 480,8"
                    fill="none" stroke="url(#divGrad)" strokeWidth="1.2" />
              {[[105,10],[175,15],[240,8],[305,15],[375,8]].map(([x, y], i) => (
                <circle key={i} cx={x} cy={y} r="1.6" fill="rgba(245,201,122,.78)" />
              ))}
            </svg>
          </div>
          <div style={{ position:"relative" }}>
            {/* Items use `flex:1 1 0` to spread evenly across the full phone
                 width (no trailing empty space on the right). 8 slots ≈ 12%
                 each on a 360-430px phone — icons stay readable, labels
                 fit without wrap. No overflow scroll. */}
            <div style={{
              display:"flex", justifyContent:"space-between",
              padding:"6px 2px calc(12px + env(safe-area-inset-bottom))",
              background:"rgba(var(--surface2-rgb),.97)", borderTop:"1px solid rgba(var(--gold-rgb),.18)",
              width:"100%",
            }} className="scroll-area">
              {/* Sprint 0 (FF-3) — Surface Manifest gate. A tab with `requires`
                   draws only where that feature is ON in the active world. Tabs
                   without `requires` always draw (→ `main` byte-identical). The
                   `typeof` guard is fail-safe → OFF if the helper somehow isn't
                   defined yet (gated tabs hide rather than crash). */}
              {TAB_DEFS.filter(td => BOTTOM_VISIBLE.includes(td.key)
                  && (!td.requires || (typeof featureEnabled === "function" && featureEnabled(td.requires)))).map(td => {
                const active = tab === td.key;
                return (
                  <button key={td.key}
                    /* 印 Lei §1 — a barra de baixo so' escreve o rotulo do slot ACTIVO,
                       logo os outros sete nao tem nome nenhum. Enquanto o conteudo era
                       um emoji, o leitor de ecra ainda anunciava "casa"/"mochila"; uma
                       marca SVG e' muda. Por isso a flag ON traz `aria-label` — sem ele
                       a iconografia seria uma REGRESSAO de acessibilidade. */
                    aria-label={markOn(td.mark) ? t(td.label_key) : undefined}
                    onClick={() => { haptic("select"); setTab(td.key); }} style={{
                    flex:"1 1 0", minWidth:0, background:"none", border:"none",
                    display:"flex", flexDirection:"column", gap:1, alignItems:"center",
                    justifyContent:"center", height:46,
                    cursor:"pointer", padding:"3px 1px", borderRadius:8, position:"relative",
                    transition:"transform .12s", overflow:"hidden",
                    // 🔴 ⚠️ **A MARCA SAÍA PRETA SOBRE PRETO.** Um `<button>` não
                    // herda a cor da página: a folha do agente põe-lhe
                    // `color: buttontext` (= **preto**), e a `Mark` desenha em
                    // `currentColor` de propósito. Um emoji não quer saber da cor
                    // — por isso a omissão foi invisível durante um lote inteiro
                    // e a guarda ficou verde: ela perguntava se `TAB_DEFS` tinha
                    // `mark:`, não se o traço se via. MEDIDO a 2026-09-09 no jogo
                    // servido: **8 marcas pretas por ecrã, em todas as 6 abas
                    // olhadas**, e ZERO problemas no trilho de desktop — que é o
                    // único sítio da navegação que já declarava `color`.
                    // O `--gold2` fica igual para activo e inactivo: quem separa
                    // os dois é a opacidade que já cá estava, exactamente como
                    // separava dois emoji iguais.
                    color: markOn(td.mark) ? "var(--gold2)" : undefined,
                  }}>
                    {/* Icon — always visible, slightly larger when active */}
                    <div style={{
                      fontSize: active ? 22 : 21, lineHeight:1,
                      filter: active
                        ? "drop-shadow(0 0 6px rgba(var(--gold2-rgb),.75)) drop-shadow(0 0 12px rgba(var(--gold-rgb),.4))"
                        : "opacity(.55)",
                      opacity: active ? 1 : 0.55,
                      transition:"filter .15s, opacity .15s, font-size .15s, transform .15s",
                      transform: active ? "scale(1.06) translateY(-1px)" : "scale(1)",
                      display: markOn(td.mark) ? "flex" : undefined,
                      alignItems: markOn(td.mark) ? "center" : undefined,
                      justifyContent: markOn(td.mark) ? "center" : undefined,
                    }}>{ico(td.ico, td.mark, { size: active ? 22 : 21 })}</div>
                    {/* Label — ONLY shown for the active tab. Avoids clipping
                         on narrow phones (owner request 2026-05-06: "o nome
                         fica ruim, meio que desaparece"). Inactive tabs
                         convey identity through icon alone — iOS-native pattern. */}
                    {active && (
                      <div style={{
                        fontSize:8.5, fontWeight:700, letterSpacing:.5,
                        color:"var(--gold2)", textTransform:"uppercase",
                        fontFamily:"'Cinzel',serif",
                        whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis",
                        maxWidth:"100%",
                        animation:"fadein .2s ease",
                      }}>{t(td.label_key)}</div>
                    )}
                    {active && (
                      <div style={{
                        position:"absolute", bottom:0, left:"50%", transform:"translateX(-50%)",
                        width:24, height:2, borderRadius:99,
                        background:"linear-gradient(90deg,transparent,rgba(var(--gold2-rgb),.9),transparent)",
                        boxShadow:"0 0 8px rgba(var(--gold2-rgb),.6)",
                      }} />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      );
    }

    // ─── UI v2 "O Pergaminho Vivo" (REDESIGN_MASTER.md, Onda R1) ──────────────
    // Gated by featureEnabled("ui_v2") — flag per-world (graduado no R6: mundo
    // ON → todos veem o v2). OFF → nada disto renderiza → main byte-idêntico.
    // 5 hubs de domínio substituem as 8 slots; TODAS as tabs existentes continuam
    // alcançáveis (mudam os PONTOS DE ENTRADA, não os destinos — regra MA-32b).
    // `group` liga cada tab existente ao seu hub para o estado ativo; `landing`
    // é a tab aberta ao tocar o hub (R2-R4 trocam landings por telas próprias).
    // 印 ⚠️ **`mark:` é obrigatório aqui, tal como no `TAB_DEFS`.** Durante um
    // lote inteiro o `TAB_DEFS` teve 25/25 marcas e o `HUB_DEFS` teve 0/5 — e é
    // esta a barra que o owner tem debaixo do polegar quando corre a `ui_v2`.
    // Cada marca é a do destino ÂNCORA do hub (o `landing`, ou a aba que dá nome
    // ao domínio), portanto o mesmo domínio fala o mesmo glifo nas duas
    // navegações em vez de inventar um segundo alfabeto.
    var HUB_DEFS = [
      { key:"hub_eu",         ico:"🧘", mark:"seated",    label_key:"hub_eu",         landing:"hub_eu_screen",
        group:["hub_eu_screen","home","cultivation","body_tempering","celestial","partner","settings","shop"] },
      { key:"hub_mundo",      ico:"🗺️", mark:"compass",   label_key:"hub_mundo",      landing:"hub_mundo_screen",
        group:["hub_mundo_screen","explore","plaza","sect","guild","world_boss","dungeons","leaderboard","faction"] },
      { key:"hub_caverna",    ico:"🏠", mark:"formation", label_key:"hub_caverna",    landing:"hub_caverna_screen",
        group:["hub_caverna_screen","cavern","crafting","inventory","beasts","market"] },
      // COMBATE é hub de membro único: o CombatTab É o landing (sem tela nova).
      { key:"hub_combate",    ico:"⚔️", mark:"sword",     label_key:"hub_combate",    landing:"combat",
        group:["combat"] },
      { key:"hub_pergaminho", ico:"📜", mark:"notice",    label_key:"hub_pergaminho", landing:"hub_pergaminho_screen",
        group:["hub_pergaminho_screen","quests","battle_pass","announcements"] },
    ];

    // ═══ 門 P6 — A NAVEGAÇÃO ACOMPANHA A PROGRESSÃO ([017] §3) ═════════════
    //
    // 🔴 O QUE ESTAVA AQUI, medido a 2026-09-27: a navegação não sabia NENHUM
    // gate. Das 24 abas, três recusam o jogador por reino — Facção (R3),
    // Celestial (R8) e o Corpo (R7, num mundo sem o Refino Mortal) — e as três
    // apareciam na lateral, na faixa do hub, no selector do Eu e no Céu do Mundo
    // IGUAIS às outras. O jogador entrava para descobrir. E o cliente não tinha
    // limiar nenhum: só lia `locked`/`unlocked` DEPOIS de entrar.
    //
    // A regra do Astra, textual:
    //   · disponível → entrada normal;
    //   · próximo desbloqueio → trancada e CONSULTÁVEL, com o requisito real, o
    //     valor actual/limiar e o caminho — *"no máximo o próximo marco de cada
    //     hub"*; requisitos empatados agrupam-se;
    //   · distante → fora da lista corrente, numa consulta «Desbloqueios»;
    //   · *"destino já descoberto, antes acessível ou alcançado por atalho
    //     continua identificável"*; *"estado desconhecido mostra
    //     verificação/erro, sem fingir desbloqueio"*;
    //   · e nunca a opção (c): uma porta trancada que aparece como aberta.
    //
    // ⚠️ UM DONO — E NÃO É ESTE FICHEIRO. O gate vive em `core/portas.py`, que
    // é o que o endpoint de cada aba chama para decidir o seu `locked`; o
    // `/player` manda o MESMO resultado em `nav_gates`. Aqui não há um único
    // limiar: um `realm >= 3` escrito neste ficheiro seria o segundo dono, e a
    // Facção já tinha dois (a guarda §29 conta-os).
    //
    // ⚠️ Com a onda OFF (`main`), ou sem `nav_gates` no payload, toda porta é
    // `aberta` e cada sítio desenha o markup de hoje, byte a byte.
    function portasOn(player) {
      return typeof ondaCultOn === "function" && ondaCultOn()
        && !!(player && player.nav_gates && typeof player.nav_gates === "object");
    }

    // → `{estado:"aberta"}` · `{estado:"trancada", tipo, precisa, tem}` ·
    //   `{estado:"incerta"}`. Um gate que o servidor não conseguiu calcular
    //   chega como `open:null` e sai INCERTO — nunca aberto.
    function portaDe(player, key) {
      if (!portasOn(player)) return { estado: "aberta" };
      const g = player.nav_gates;
      if (!Object.prototype.hasOwnProperty.call(g, key)) return { estado: "aberta" };
      const p = g[key] || {};
      if (p.open === true) return { estado: "aberta" };
      if (p.open === false && p.kind === "realm" && typeof p.need === "number") {
        return { estado: "trancada", tipo: "realm", precisa: p.need,
                 tem: typeof p.have === "number" ? p.have : null };
      }
      return { estado: "incerta" };
    }

    // A regra do marco, num sítio só. `keys` são os destinos de UM hub, pela
    // ordem em que o sítio os mostra; `aqui` é a aba onde o jogador está.
    // → `{ lista, distantes }` — `lista` é o que o sítio desenha (pela mesma
    // ordem, sem mexer na posição de ninguém), `distantes` o que fica para a
    // consulta «Desbloqueios».
    function portasDoHub(player, keys, aqui) {
      const todas = (keys || []).map(k => ({ key: k, porta: portaDe(player, k) }));
      const trancadas = todas.filter(x => x.porta.estado === "trancada");
      if (!trancadas.length) return { lista: todas, distantes: [] };
      const marco = Math.min.apply(null, trancadas.map(x => x.porta.precisa));
      // *"antes acessível"*: quem renasceu já esteve do outro lado destas
      // portas. O reino volta a zero; a memória do sítio não.
      const renascido = ((player && player.prestige_level) || 0) >= 1;
      const fica = (x) => x.porta.estado !== "trancada" || renascido
                          || x.porta.precisa === marco || x.key === aqui;
      return { lista: todas.filter(fica), distantes: todas.filter(x => !fica(x)) };
    }

    // O CAMINHO de cada tipo de requisito. O `kind` viaja no payload em vez de
    // se presumir — um requisito novo no servidor sem caminho aqui fica
    // vermelho na §29, em vez de sair uma porta que diz o QUE falta e não COMO.
    var PORTA_CAMINHOS = {
      realm: { texto: "porta_caminho_reino", botao: "porta_ir_cultivo", tab: "cultivation" },
    };

    function portaRotulo(porta) {
      if (!porta) return "";
      if (porta.estado === "trancada") return t("porta_reino_n", { n: porta.precisa });
      if (porta.estado === "incerta") return t("porta_incerta");
      return "";
    }

    // O nome acessível da porta INTEIRA: um leitor de ecrã ouve o motivo e o
    // número, não "botão, cadeado".
    function portaAria(nome, porta) {
      if (!porta || porta.estado === "aberta") return undefined;
      if (porta.estado === "trancada") {
        return t("porta_aria_trancada", { nome: nome, n: porta.precisa,
                  reino: realmName(porta.precisa), tem: porta.tem == null ? "—" : porta.tem });
      }
      return t("porta_aria_incerta", { nome: nome });
    }

    // O SELO — o único desenhador do "trancada, e porquê" dentro de uma porta.
    // Os quatro sítios têm geometrias diferentes (chip, fila da lateral, botão
    // do selector, chip do Céu) e é por isso que o dono é o selo e não o botão.
    // ⚠️ A marca nunca vai sozinha: vai com o número. E declara `color` — uma
    // `<Mark>` em `currentColor` dentro de um `<button>` sai PRETA (09/09).
    function PortaSelo({ porta, cor }) {
      if (!porta || porta.estado === "aberta") return null;
      const incerta = porta.estado === "incerta";
      return (
        <span aria-hidden="true" className="nv-porta-selo"
              style={Object.assign({}, _ONDA_TNUM, {
                display:"inline-flex", alignItems:"center", gap:4, flexShrink:0,
                whiteSpace:"nowrap", fontSize:12, lineHeight:1, letterSpacing:".02em",
                color: cor || NIV_ONDA.muted })}>
          {/* ⚠️ INCERTA vai só com a palavra. Olhado a 390px: a marca do
              incenso a 11px lia-se como uma SETA PARA BAIXO — "descarregar" no
              sítio de "não sei". Uma marca que diz outra coisa é pior do que
              nenhuma; a palavra basta. */}
          {!incerta && <Mark name="lock" size={12} />}
          <span>{portaRotulo(porta)}</span>
        </span>
      );
    }

    // 門 A FORMA DA PORTA — decidida pelo Astra (MESA [020], 2026-09-27), num
    // dono só. Os quatro sítios têm geometrias diferentes; o que não pode
    // divergir entre eles é isto:
    //   · o contorno tracejado SÓ na porta trancada, e só onde o sítio já tem
    //     contorno (a lateral do PC fica com a fila e o selo, sem caixa);
    //   · «Desbloqueios» é uma consulta DISPONÍVEL — contorno contínuo, *"porque
    //     hoje parece outra porta trancada"*.
    //   · *"A porta continua consultável, por isso deve ter leitura inteira, sem
    //     parecer um botão desactivado"* — opacidade 1, e o NOME com a MESMA
    //     cor das portas abertas do mesmo sítio.
    // 🔴 O "mesma cor" é MEDIDO, não gosto. O Astra fixou o nome em papel, e
    // aplicado à letra, olhado a 390 e a 1440, a porta trancada saía MAIS CLARA
    // do que as abertas: na faixa, abertas `rgb(110,137,191)` e o Corpo trancado
    // `rgb(236,229,216)`; na lateral, o mesmo. Uma porta que não abre a gritar
    // mais alto do que as que abrem é a hierarquia ao contrário. O significado
    // é do SELO (*"a geometria pertence ao sítio; o significado pertence ao
    // selo"*); o nome lê-se como os vizinhos. Onde as abertas já são claras (o
    // selector, o Céu) o resultado é o papel dele.
    // ⚠️ É uma FUNÇÃO e não um `var` de objecto: o `NIV_ONDA` é declarado mais
    // abaixo neste ficheiro, e um objecto avaliado aqui leria `undefined` no
    // arranque e rebentava o script inteiro.
    function portaTom() {
      return {
        trancada: "1px dashed " + NIV_ONDA.line,
        consulta: "1px solid " + NIV_ONDA.line,
      };
    }

    // O contador de «Desbloqueios»: *"passa de «1» para «+1»"* — conta destinos
    // ADICIONAIS aos que já estão à vista, e a consulta mostra-os todos.
    function PortaConta({ n }) {
      return (
        <span style={Object.assign({}, _ONDA_TNUM, { color: NIV_ONDA.muted, fontSize:12,
                                                     flexShrink:0 })}>
          {"+" + n}
        </span>
      );
    }

    // A CONSULTA — «Desbloqueios» de um hub. É a mesma janela para as duas
    // entradas que o Astra pediu: tocar numa porta trancada abre-a com essa
    // porta em primeiro (`foco`); a entrada «Desbloqueios» abre-a sem foco.
    // Uma janela, um dono — duas seria a Lei F-7 outra vez.
    function PortaConsulta({ player, hubKey, foco, onClose, onIr }) {
      const hub = HUB_DEFS.find(h => h.key === hubKey);
      const keys = hub ? hub.group.filter(k => !k.endsWith("_screen") && k !== "home") : [];
      const peso = (x) => x.porta.estado === "trancada" ? x.porta.precisa : 999;
      const linhas = keys
        .map(k => ({ key: k, td: TAB_DEFS.find(td => td.key === k), porta: portaDe(player, k) }))
        .filter(x => x.td && x.porta.estado !== "aberta")
        .sort((a, b) => (a.key === foco ? -1 : b.key === foco ? 1 : peso(a) - peso(b)));
      const ph = portasDoHub(player, keys, foco);
      const perto = (k) => ph.lista.some(x => x.key === k);
      const tipos = {};
      linhas.forEach(x => { if (x.porta.estado === "trancada") tipos[x.porta.tipo] = true; });
      const rot = { fontFamily: NIV_ONDA.label, fontSize:10, letterSpacing:".16em",
                    textTransform:"uppercase", color: NIV_ONDA.muted };
      const linhaPar = (rotulo, valor) => (
        <div style={{ display:"grid", gridTemplateColumns:"96px minmax(0,1fr)", gap:10,
                      alignItems:"baseline", padding:"3px 0" }}>
          <span style={rot}>{rotulo}</span>
          <span style={Object.assign({}, _ONDA_TNUM, { fontSize:13, color: NIV_ONDA.paper })}>{valor}</span>
        </div>
      );
      let viuDistante = false;
      return (
        <Modal open onClose={onClose} compact maxWidth={420} zIndex={72}
               title={t("porta_titulo", { hub: hub ? t(hub.label_key) : "" })}>
          <div style={{ display:"grid", gap:0 }}>
            {!linhas.length && (
              <div style={{ fontSize:13, color: NIV_ONDA.muted, padding:"4px 0 8px" }}>
                {t("porta_nada")}
              </div>
            )}
            {linhas.map((x, i) => {
              const tr = x.porta.estado === "trancada";
              const falta = tr && typeof x.porta.tem === "number"
                ? Math.max(0, x.porta.precisa - x.porta.tem) : null;
              const cabecaDistante = !perto(x.key) && !viuDistante;
              if (cabecaDistante) viuDistante = true;
              return (
                <div key={x.key} style={{ padding:"12px 0",
                       borderTop: i ? "1px solid " + NIV_ONDA.line : "none" }}>
                  {/* A etiqueta so' se escreve sobre uma porta TRANCADA: de uma
                      incerta nao se sabe se e' o proximo marco ou se ja' abriu. */}
                  {tr && ((i === 0 && perto(x.key)) || cabecaDistante) ? (
                    <div style={Object.assign({}, rot, { marginBottom:6,
                           color: perto(x.key) ? NIV_ONDA.gold : NIV_ONDA.muted })}>
                      {t(perto(x.key) ? "porta_proximo_marco" : "porta_mais_longe")}
                    </div>
                  ) : null}
                  <div style={{ display:"flex", alignItems:"center", gap:9, marginBottom:6,
                                color: NIV_ONDA.paper }}>
                    <Mark name={x.td.mark || "lock"} size={18} />
                    <span style={{ fontFamily: NIV_ONDA.serif, fontSize:20, lineHeight:1.1,
                                   minWidth:0 }}>{t(x.td.label_key)}</span>
                    <span style={{ flex:1 }} />
                    <PortaSelo porta={x.porta} />
                  </div>
                  {tr ? (
                    <React.Fragment>
                      {linhaPar(t("porta_lin_requer"),
                                t("porta_valor_reino", { n: x.porta.precisa, reino: realmName(x.porta.precisa) }))}
                      {typeof x.porta.tem === "number" && linhaPar(t("porta_lin_voce"),
                                t("porta_valor_reino", { n: x.porta.tem, reino: realmName(x.porta.tem) }))}
                      {falta != null && falta > 0 && (
                        <div style={{ fontSize:12, color: NIV_ONDA.muted, paddingTop:4 }}>
                          {t(falta === 1 ? "porta_faltam_1" : "porta_faltam_n", { n: falta })}
                        </div>
                      )}
                    </React.Fragment>
                  ) : (
                    <div style={{ fontSize:12.5, color: NIV_ONDA.muted, lineHeight:1.5 }}>
                      {t("porta_incerta_nota")}
                    </div>
                  )}
                </div>
              );
            })}
            {Object.keys(tipos).map(k => {
              const c = PORTA_CAMINHOS[k];
              if (!c) return null;
              return (
                <div key={k} style={{ borderTop:"1px solid " + NIV_ONDA.line, paddingTop:12,
                                      display:"grid", gap:10 }}>
                  <div style={{ fontSize:12.5, color: NIV_ONDA.muted, lineHeight:1.5 }}>{t(c.texto)}</div>
                  {onIr && (
                    <OndaBtn onClick={() => { haptic("select"); onIr(c.tab); }}>{t(c.botao)}</OndaBtn>
                  )}
                </div>
              );
            })}
          </div>
        </Modal>
      );
    }

    // Chrome Telegram explícito do v2 (pesquisa §2.7: override tem de ser
    // EXPLÍCITO ou o app fica numa moldura desencontrada). Chamado 1× pelo
    // App SÓ quando ui_v2 está ativo → main nunca muda de moldura.
    // ─── WEB-D 皮 — A PELE QUENTE ────────────────────────────────────────────
    // Aplica a paleta de `GameDesign/LINGUAGEM_VISUAL_WEB_C.md §1` ao jogo
    // inteiro escrevendo os TRIPLETOS no <html>. É uma função de ~20 linhas
    // porque a varredura da WEB-D §2.1 converteu 1318 literais em tokens: sem
    // ela, isto mudava o fundo e mais NADA (medido: `tabs.js` tinha 412 hex +
    // 1459 rgba escritos à mão, e um `background:"#0d1422"` dentro de um
    // componente ignora o :root).
    //
    // ⚠️ Só os tripletos são escritos. As linhas `--X: rgb(var(--X-rgb))` do
    // :root derivam sozinhas — é por isso que UMA escrita repinta bordas,
    // sombras, gradientes e glows de uma vez.
    //
    // ⚠️ O QUE NÃO MUDA, e é decisão, não esquecimento:
    //  · `--realm-*` — as 11 cores dos reinos são IDENTIDADE do jogo, não pele.
    //    O jogador sabe que Núcleo Dourado é roxo; trocar isso é mexer na
    //    legibilidade da escada, não na moldura (Lei §5: a pele é o shell).
    //  · `--gold*` — "Já era nosso. Fica." (doc §1).
    //  · `rgba(0,0,0,…)` (239×) e `rgba(255,255,255,…)` (61×) — sombra e
    //    brilho são profundidade, não paleta. Uma sombra preta sobre preto
    //    quente continua certa; converter 300 sítios por zero pixels de
    //    ganho era churn contra um ficheiro de 1,5 MB.
    //  · A tipografia. O doc pede Cormorant no display (decisão 2 de 3), mas
    //    isso são ~200 `fontFamily:"'Cinzel',serif"` a decidir um a um —
    //    é desenho por sítio, não uma troca de valor, e vive na V4 (a régua
    //    tipográfica). Fazer metade agora deixava dois displays a discordar.
    var WARM_SKIN_RGB = {
      // O preto QUENTE — a única troca que mais afasta de "dashboard genérico".
      "bg": "11,10,12",           // #0b0a0c — `--ink` do doc, verbatim
      "card": "20,16,19",         // #141013
      "panel": "28,21,25",        // #1c1519
      "surface": "31,23,26",      // #1f171a
      "surface2": "16,12,15",     // #100c0f
      "surface3": "18,14,16",     // #120e10
      // Papel envelhecido em vez de azul-esbranquiçado: o texto deixa de
      // parecer terminal.
      "text": "236,229,216",      // #ece5d8 — `--paper` do doc, verbatim
      "text2": "245,239,227",     // #f5efe3
      "muted": "160,141,120",     // #a08d78
      "muted2": "107,88,71",      // #6b5847
      // Tinta castanha em vez de azul de borda.
      "border": "58,42,34",       // #3a2a22
      "border2": "77,56,43",      // #4d382b
      "glow": "122,74,40",        // #7a4a28 — o halo ambiente do shell
      // 朱砂 — o selo de cinábrio. É o acento que ASSINA a página, e é o
      // único que não vem do jogo: vem do mundo dele.
      "accent2": "200,68,47",     // #c8442f — `--seal` do doc, verbatim
      "red": "200,68,47",         // #c8442f
      "red2": "232,160,140",      // #e8a08c
      // O verde de sucesso dessatura o suficiente para pousar sobre papel.
      "jade": "95,166,120",       // #5fa678
      // O AMBIENTE — o céu, as três cristas e o pagode do fundo de constelação
      // (+ a auréola do shell). É a maior superfície do jogo: sem estas seis
      // linhas a pele aquecia tudo e deixava uma montanha AZUL por cima.
      // Tinta lavada 水墨 sobre preto quente: as cristas afastam-se ficando
      // mais frias-castanhas, nunca mais azuis.
      "amb-sky": "150,86,44",     // #96562c — o clarão do horizonte
      "amb-ridge1": "150,112,78", // #96704e — a mais distante, a mais clara
      "amb-ridge2": "112,80,56",  // #705038
      "amb-ridge3": "68,46,34",   // #442e22 — a mais próxima, a mais escura
      "amb-pagoda": "126,92,60",  // #7e5c3c
      "amb-aura": "150,70,40",    // #964628 — a auréola inferior
    };
    var WARM_SKIN_HEX = {
      "--bg":"#0b0a0c", "--card":"#141013", "--panel":"#1c1519",
      "--surface":"#1f171a", "--surface2":"#100c0f", "--surface3":"#120e10",
      "--text":"#ece5d8", "--text2":"#f5efe3", "--muted":"#a08d78", "--muted2":"#6b5847",
      "--border":"#3a2a22", "--border2":"#4d382b", "--glow":"#7a4a28",
      "--accent2":"#c8442f", "--red":"#c8442f", "--red2":"#e8a08c", "--jade":"#5fa678",
    };
    var _warmSkinOn = false;
    var applyWarmSkin = () => {
      if (_warmSkinOn) return;          // idempotente: re-aplicar = no-op
      _warmSkinOn = true;
      try {
        const root = document.documentElement;
        for (const k in WARM_SKIN_RGB) root.style.setProperty("--" + k + "-rgb", WARM_SKIN_RGB[k]);
        // O espelho em JS tem de seguir, senão o alpha-concat (`${cssHex(x)}88`)
        // e os atributos de SVG continuam a pintar com a paleta fria — que é
        // exactamente o "mundo meio quente e meio azul" que o doc proíbe.
        for (const k in WARM_SKIN_HEX) CSS_VAR_HEX[k] = WARM_SKIN_HEX[k];
        // E a moldura do Telegram, que não sabe ler var().
        tg?.setHeaderColor?.(WARM_SKIN_HEX["--bg"]);
        tg?.setBackgroundColor?.(WARM_SKIN_HEX["--bg"]);
      } catch (e) { /* no-op: pior caso fica a pele fria */ }
    };

    var applyV2Chrome = () => {
      try {
        tg?.setHeaderColor?.("#06080f");
        tg?.setBackgroundColor?.("#06080f");
      } catch (e) { /* desktop/clientes antigos: no-op */ }
    };

    function V2BottomNav({ tab, setTab, onRetoque }) {
      // Mesma linguagem visual do BottomNav (divisor-nuvem + glow ativo), 5 slots.
      const activeHub = (HUB_DEFS.find(h => h.group.includes(tab)) || {}).key;
      // 坐 ONDA 1 — ver a nota longa junto ao rótulo, abaixo.
      const _hubNames = typeof ondaCultOn === "function" && ondaCultOn();
      return (
        <div style={{
          position:"absolute", bottom:0, left:0, right:0, zIndex:5,
          display:"flex", flexDirection:"column",
        }}>
          <div style={{ position:"relative", height:20, overflow:"hidden", pointerEvents:"none" }}>
            <svg viewBox="0 0 480 20" preserveAspectRatio="none"
                 style={{ position:"absolute", bottom:0, left:0, width:"100%", height:"100%" }}>
              <defs>
                <linearGradient id="divGradV2" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="rgba(201,144,58,0)" />
                  <stop offset="20%" stopColor="rgba(201,144,58,0.6)" />
                  <stop offset="50%" stopColor="rgba(245,201,122,0.92)" />
                  <stop offset="80%" stopColor="rgba(201,144,58,0.6)" />
                  <stop offset="100%" stopColor="rgba(201,144,58,0)" />
                </linearGradient>
              </defs>
              <path d="M0,20 C40,14 70,6 105,10 C130,13 145,18 175,15 C200,12 215,5 240,8 C265,11 280,18 305,15 C330,12 345,5 375,8 C400,11 425,18 455,14 C470,11 480,8 480,8 L480,20Z"
                    fill="rgba(10,14,28,0.97)" />
              <path d="M0,20 C40,14 70,6 105,10 C130,13 145,18 175,15 C200,12 215,5 240,8 C265,11 280,18 305,15 C330,12 345,5 375,8 C400,11 425,18 455,14 C470,11 480,8 480,8"
                    fill="none" stroke="url(#divGradV2)" strokeWidth="1.2" />
            </svg>
          </div>
          <div style={{
            display:"flex", justifyContent:"space-between",
            padding:"6px 2px calc(12px + env(safe-area-inset-bottom))",
            background:"rgba(var(--surface2-rgb),.97)", borderTop:"1px solid rgba(var(--gold-rgb),.18)",
            width:"100%",
          }}>
            {HUB_DEFS.map(h => {
              const active = activeHub === h.key;
              return (
                <button key={h.key}
                  /* 印 Lei §1 — a barra só escreve o rótulo do hub ACTIVO; os
                     outros quatro não têm nome nenhum. Enquanto o conteúdo era
                     emoji o leitor de ecrã ainda anunciava "casa"; uma marca SVG
                     é muda. Sem isto a iconografia seria uma REGRESSÃO de
                     acessibilidade (mesma regra do `BottomNav`). */
                  aria-label={markOn(h.mark) ? t(h.label_key) : undefined}
                  onClick={() => {
                    haptic("select");
                    // 至 [017] §3 — *"tocar novamente em **Eu**, ja' activo, abre
                    // esse selector"*. Um `setTab` para onde ja' se esta' nao
                    // faz nada; este e' o gesto que a decisao pede.
                    //
                    // 🔴 `tab === h.landing`, e NAO `active`. Medido a olhar: o
                    // `active` e' verdadeiro para qualquer aba do GRUPO do hub
                    // — e o `home` esta' no grupo do Eu. Com `active`, tocar em
                    // "Eu" estando na `home` abria um selector invisivel em vez
                    // de LEVAR ao landing. O retoque e' "ja' estou NESTA tela",
                    // nao "ja' estou neste hub".
                    if (tab === h.landing && typeof onRetoque === "function") { onRetoque(h.key); return; }
                    setTab(h.landing);
                  }} style={{
                  flex:"1 1 0", minWidth:0, background:"none", border:"none",
                  display:"flex", flexDirection:"column", gap:1, alignItems:"center",
                  justifyContent:"center", height:46,
                  cursor:"pointer", padding:"3px 1px", borderRadius:8, position:"relative",
                  transition:"transform .12s", overflow:"hidden",
                  // 🔴 O MESMO preto-sobre-preto do `BottomNav` (a nota longa
                  // está lá). ⚠️ **Este é o sítio nº 2, e é a razão de esta
                  // linha existir aqui:** a barra da `ui_v2` é uma cópia à mão
                  // da outra, e um conserto só num dos lados é a Lei F-7 a
                  // repetir-se dentro do lote que a está a cumprir.
                  color: markOn(h.mark) ? "var(--gold2)" : undefined,
                }}>
                  <div style={{
                    fontSize: active ? 22 : 21, lineHeight:1,
                    filter: active
                      ? "drop-shadow(0 0 6px rgba(var(--gold2-rgb),.75)) drop-shadow(0 0 12px rgba(var(--gold-rgb),.4))"
                      : "opacity(.55)",
                    opacity: active ? 1 : 0.55,
                    transition:"filter .15s, opacity .15s, font-size .15s, transform .15s",
                    transform: active ? "scale(1.06) translateY(-1px)" : "scale(1)",
                    display: markOn(h.mark) ? "flex" : undefined,
                    alignItems: markOn(h.mark) ? "center" : undefined,
                    justifyContent: markOn(h.mark) ? "center" : undefined,
                  }}>{ico(h.ico, h.mark, { size: active ? 22 : 21 })}</div>
                  {/* 坐 ONDA 1 — os CINCO nomes, e não só o do hub activo.
                      ⚠️ MEDIDO no ficheiro: a barra escrevia o rótulo APENAS do
                      slot activo, portanto os outros quatro destinos do jogo
                      eram quatro pictogramas mudos — o jogador tinha de tocar
                      para descobrir onde ia. Enquanto o conteúdo era emoji
                      ainda havia um palpite; com a `iconografia` ON é um traço
                      abstracto, e adivinhar passa a ser a única forma. O desenho
                      (MESA [011] §6) decidiu **sempre acompanhadas do nome**:
                      activo em ouro, inactivos em texto secundário.
                      Com a flag OFF continua só o activo, byte a byte. */}
                  {(active || _hubNames) && (
                    <div style={{
                      fontSize:8.5, fontWeight:700, letterSpacing:.5,
                      color: active ? "var(--gold2)" : "var(--muted2)",
                      textTransform:"uppercase",
                      fontFamily:"'Cinzel',serif",
                      whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis",
                      maxWidth:"100%",
                      animation: active ? "fadein .2s ease" : undefined,
                    }}>{t(h.label_key)}</div>
                  )}
                  {active && (
                    <div style={{
                      position:"absolute", bottom:0, left:"50%", transform:"translateX(-50%)",
                      width:24, height:2, borderRadius:99,
                      background:"linear-gradient(90deg,transparent,rgba(var(--gold2-rgb),.9),transparent)",
                      boxShadow:"0 0 8px rgba(var(--gold2-rgb),.6)",
                    }} />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      );
    }

    // Onda R2-fix (review: Lei de Ferro nº 1) — a FAIXA DO DOMÍNIO: chips de
    // navegação intra-hub sob o header. Garante que TODO membro do grupo do hub
    // ativo fica a 1 tap (matou os órfãos: home one-way, crafting/inventory sem
    // entrada). Interina — R3/R4 substituem por telas próprias (mapa/caverna).
    // Não renderiza: fora do v2, em tab sem hub, e nos landings-tela (a grade
    // "Seu Caminho" / o mapa R3 já SÃO a faixa deles). Navegação, não informação
    // (Lei nº 2).
    function V2HubStrip({ tab, setTab, player, onPorta }) {
      // R4: skip/filter GENERALIZADO por sufixo — 4 landings-tela agora
      // (eu/mundo/caverna/pergaminho); a lista explícita já não escala. Um
      // landing-tela nunca mostra a faixa (a tela É a faixa do hub) e nunca
      // vira chip (não existe em TAB_DEFS de qualquer forma).
      if (tab.endsWith("_screen")) return null;
      // 至 *"a fila desaparece da chegada. Cultivo, Corpo, Celestial,
      // Parceiro e Configurações vivem no ramo Eu da lateral no PC e no
      // selector do hub Eu no telemóvel"* — decisão (a) do Astra.
      if (chegadaDona(tab)) return null;
      const hub = HUB_DEFS.find(h => h.group.includes(tab));
      if (!hub) return null;
      const todos = hub.group
        .filter(k => k !== tab && !k.endsWith("_screen"))
        .map(k => TAB_DEFS.find(td => td.key === k))
        .filter(Boolean);
      // 門 P6 — o mesmo marco da lateral: so' o proximo desbloqueio do hub
      // fica na faixa; com a onda OFF toda porta e' aberta e `chips` = `todos`.
      const ph = portasDoHub(player, todos.map(td => td.key), tab);
      const chips = todos.filter(td => ph.lista.some(x => x.key === td.key));
      if (!chips.length && !ph.distantes.length) return null;
      return (
        <div className="scroll-area" style={{
          position:"relative", zIndex:2, display:"flex", gap:6,
          padding:"7px 14px 6px", overflowX:"auto",
          borderBottom:"1px solid rgba(var(--gold-rgb),.12)",
          background:"rgba(var(--surface2-rgb),.55)",
        }}>
          {chips.map(td => {
            const pp = portaDe(player, td.key);
            // 門 P6 — trancada: a mesma pilula, apagada, com o selo e o numero;
            // o toque abre a consulta em vez de levar a uma aba que recusa.
            if (pp.estado !== "aberta") {
              return (
                <button key={td.key} aria-label={portaAria(t(td.label_key), pp)}
                        onClick={() => { haptic("select");
                                         if (onPorta) onPorta(hub.key, td.key); else setTab(td.key); }}
                        style={{
                          display:"inline-flex", alignItems:"center", gap:6, flexShrink:0,
                          padding:"4px 10px", borderRadius:99,
                          background:"transparent", border: portaTom().trancada,
                          color:"var(--muted)", cursor:"pointer", fontFamily:"inherit",
                          fontSize:10.5, whiteSpace:"nowrap", transition:"all .15s",
                        }}>
                  <span>{t(td.label_key)}</span>
                  <PortaSelo porta={pp} />
                </button>
              );
            }
            return (
            <button key={td.key} onClick={() => { haptic("select"); setTab(td.key); }}
                    style={{
                      display:"inline-flex", alignItems:"center", gap:5, flexShrink:0,
                      padding:"4px 10px", borderRadius:99,
                      background:"rgba(0,0,0,.35)", border:"1px solid rgba(var(--gold2-rgb),.22)",
                      color:"var(--muted)", cursor:"pointer", fontFamily:"inherit",
                      fontSize:10.5, whiteSpace:"nowrap", transition:"all .15s",
                    }}>
              <span style={{ fontSize:13, lineHeight:1 }}>{td.ico}</span>
              <span>{t(td.label_key)}</span>
            </button>
            );
          })}
          {ph.distantes.length > 0 && (
            <button onClick={() => { haptic("select"); if (onPorta) onPorta(hub.key, null); }}
                    style={{
                      display:"inline-flex", alignItems:"center", gap:6, flexShrink:0,
                      padding:"4px 10px", borderRadius:99,
                      background:"transparent", border: portaTom().consulta,
                      color:"var(--muted)", cursor:"pointer", fontFamily:"inherit",
                      fontSize:10.5, whiteSpace:"nowrap",
                    }}>
              <span>{t("porta_desbloqueios")}</span>
              <PortaConta n={ph.distantes.length} />
            </button>
          )}
        </div>
      );
    }

    // ═══ 圖 O MAPA — a tela de hub deixa de ser uma LISTA e vira um LUGAR ═════
    //
    // Ordem do owner (2026-09-08, textual): *"To pensando em um HUB completo com
    // imagem e a pessoa clica no templo ou o que seja. (…) E nao esses menus
    // louco onde tem que buscar de um lado ao outro."*
    //
    // ⚠️ Isto NAO e' "por uma imagem de fundo no hub" — e' trocar o MECANISMO:
    // hoje o jogador LE' UMA LISTA E PROCURA; aqui ele OLHA PARA UM SITIO E TOCA.
    // O que estava la' (a `HubCavernaScreen`, a tela que o owner fotografou):
    // cinco elipses de `border-radius` organico, cada uma com um
    // `radial-gradient` e um EMOJI de 28px ao centro — zero pixels de
    // ilustracao — e o toque abria um acordeao que revelava OUTRO botao
    // ("Entrar ›"): DOIS taps para chegar onde um devia bastar.
    //
    // ── A DECISAO CENTRAL: CAMADAS SEPARADAS (V5 §3.2) ───────────────────────
    // O fundo e' ATMOSFERA (familia de arte `place`, que recusa por nome
    // qualquer edificio) e CADA PORTA e' a SUA propria peca (familia `door`,
    // sobre preto liso, com luz de recorte e a base a dissolver-se).
    //
    // ⚠️ A alternativa — uma unica pintura com os cinco sitios la' dentro e as
    // coordenadas escritas aqui — e' a ARMADILHA, e o precedente esta' no repo:
    // `ARTE_PROVENIENCIA.md §2.5` obriga a que **regenerar = ficheiro NOVO**.
    // Com a geometria no codigo e o desenho na pintura, o dia em que a arte
    // mudar o mapa passa a MENTIR sem partir nenhum teste. Separadas:
    //   · o alinhamento e' do CSS, nao da pintura;
    //   · uma porta nova nao obriga a regerar a cena;
    //   · e cada porta ACENDE ou APAGA sem se repintar nada — que e' o que torna
    //     possivel a regra da honestidade abaixo.
    //
    // ── A HONESTIDADE: o apagado CONTINUA a ser uma porta (Lei §1) ───────────
    // O exemplo e' do proprio owner: *"um templo com nome guilda"* — e se ele
    // nao tiver guilda? O templo nao pode parecer habitado, e NAO PODE SUMIR: a
    // porta para criar/entrar numa guilda e' a unica que ele tem. A resposta ja'
    // existe nesta casa — **o lugar vazio a' espera**, que foi o que o 坐 O
    // CULTIVADOR decidiu para os 11 reinos. Duas leituras da MESMA arte, feitas
    // em CSS e nunca em ficheiros diferentes.
    //
    // ── UM DONO (Lei 0 passo 2 / Lei F-7) ───────────────────────────────────
    // A cena, as portas, os estados, o `aria-label`, a cor da marca e o recurso
    // vivem TODOS aqui. Uma ligacao a' mao por hub seria a quarta recorrencia do
    // mesmo defeito em cinco dias.
    //
    // ⚠️ E a clausula de 09/09 aplica-se em cheio: **todo sitio que desenha em
    // `currentColor` dentro de um `<button>` TEM DE DECLARAR `color`** — a folha
    // do agente po~e-lhe `color: buttontext` (PRETO). Foi assim que as 8 marcas
    // das barras de baixo sairam pretas sobre preto durante um lote inteiro,
    // com a guarda verde.
    var HUB_SCENE_DEFS = {
      // `x`/`y`/`w` sao PERCENTAGENS DA CAIXA, nunca pixels: e' o que faz a
      // composicao ser a mesma a 390 e a 1440 (V5 §3.7 — a cena nao estica,
      // cresce ate' um tecto e respira a' volta).
      // ⚠️ A ordem desta lista e' a ordem do DOM e portanto a ordem do Tab. Esta'
      // escrita na ordem de LEITURA da cena (o Salao em cima ao centro, depois o
      // par do meio, depois o par de baixo) — um leitor de ecra e um dedo
      // percorrem o mesmo caminho.
      hub_caverna: {
        art: "hub-caverna-scene.webp",
        doors: [
          { key:"salao",    tab:"cavern",    label_key:"hub_caverna_salao",
            art:"door-caverna-salao.webp",    x:31, y:4,  w:39 },
          { key:"forja",    tab:"crafting",  label_key:"hub_caverna_forja",
            art:"door-caverna-forja.webp",    x:2,  y:33, w:32 },
          { key:"anel",     tab:"inventory", label_key:"hub_caverna_anel",
            art:"door-caverna-anel.webp",     x:65, y:37, w:32 },
          { key:"estabulo", tab:"beasts",    label_key:"hub_caverna_estabulo",
            art:"door-caverna-estabulo.webp", x:4,  y:67, w:32 },
          // ⚠️ o Mercado nao vive na sua caverna: a porta dele e' um LIMIAR (um
          // arco aberto na rocha, com a luz de uma rua do outro lado). Uma banca
          // de feira dentro de uma gruta seria a cena a mentir (regua #4).
          { key:"mercado",  tab:"market",    label_key:"tab_market",
            art:"door-caverna-mercado.webp",  x:62, y:70, w:34 },
        ],
      },
      // ═══ 州 O MUNDO — e sao CINCO portas, nao nove (2026-09-13) ═══════════
      //
      // 🔴 O pendente de 11/09 dizia *"o hub do Mundo tem NOVE destinos, e nove
      // portas numa pintura de 358px e' uma sopa"*. Servido e OLHADO, o
      // `HubMundoScreen` desenha **CINCO** elipses. O nove era o
      // `HUB_DEFS.group` — um array que conta o proprio landing e as abas que
      // se alcancam de DENTRO da tela:
      //
      //   O CEU (faixa de chips)  world_boss · leaderboard · faction · guild
      //   A ILHA (gaveta)         explore · plaza · sect · dungeons
      //   o landing               hub_mundo_screen
      //   ---------------------------------------------------------------
      //   9 no `group`      ·      MAS 5 continentes desenhados
      //
      // E' a armadilha *"um assert sobre o repositorio em vez do assunto"*
      // feita em prosa: contou-se o array e nao o ecra. E a decisao que sai
      // disso e' a que mantem a tela honesta:
      //
      //  · os quatro do CEU **nao pertencem a lugar nenhum** — e' isso que a
      //    palavra Ceu quer dizer. Ficam na faixa, e uma porta pintada para o
      //    Chefe Mundial teria de a por nalgum continente, que seria mentira.
      //  · os quatro da ILHA sao **locais de onde voce esta'**: mudam com o
      //    continente, com o estado da regiao, com o evento vivo. Sao a gaveta,
      //    e e' por isso que estas portas ABREM (`onSelect`) em vez de irem.
      //
      // ⚠️ O fundo e' o **espaco ENTRE** os continentes (um mar de nuvens antes
      // da madrugada, sem UM pedaco de terra dentro). Se a terra viesse na
      // pintura, o mapa passava a ter dois Fenghuo — um pintado e outro
      // tocavel — que e' o defeito exacto que a proibicao de edificios da
      // familia `place` existe para impedir.
      //
      // ⚠️ A ordem e' a de LEITURA e a do Tab, e e' a mesma do
      // `CONTINENT_META` / `isles` do `HubMundoScreen`: Linghe, Qianhe,
      // Yanshan, Fenghuo, Moyu. Duas listas com a mesma ordem nao e'
      // coincidencia — e' o que a guarda da §16 compara.
      hub_mundo: {
        art: "hub-mundo-noite-scene.webp",
        // 🔴 O QUE "APAGADO" QUER DIZER MUDA COM O HUB — apanhado a OLHAR.
        //
        // Na Caverna, apagado = *"ainda não estabelecida"*, e o sufixo do
        // `aria-label` diz **"apagado, à espera"**: é um sítio que ainda não
        // existe, e esperar é literalmente o que ele faz. Aplicado ao Mundo,
        // isso vira uma MENTIRA: um continente onde você não está não está à
        // espera de ser construído — ele existe, está cheio de gente, e você é
        // que está noutro sítio. Um leitor de ecrã ouvia "Fēnghuǒ — apagado, à
        // espera" cinco vezes seguidas, e nenhuma delas era verdade.
        //
        // E a FORÇA também muda. Na Caverna o apagado é raro (uma porta, e só
        // enquanto não há caverna) e pode ser duro. Aqui são **sempre quatro em
        // cinco**: com o `grayscale(.62) brightness(.52)` da Caverna o mundo
        // inteiro saía morto. O que se quer dizer é *distante*, não *desligado*
        // — por isso a versão suave, que ainda deixa ver a cor de cada terra.
        dim: "grayscale(.34) brightness(.72)",
        dim_key: "mapa_porta_longe",
        doors: [
          { key:"linghe",  tab:"explore", label_key:"continent_linghe",
            art:"land-mundo-linghe.webp",  x:30, y:2,  w:40 },
          { key:"qianhe",  tab:"explore", label_key:"continent_qianhe",
            art:"land-mundo-qianhe.webp",  x:1,  y:26, w:36 },
          { key:"yanshan", tab:"explore", label_key:"continent_yanshan",
            art:"land-mundo-yanshan.webp", x:62, y:29, w:36 },
          { key:"fenghuo", tab:"explore", label_key:"continent_fenghuo",
            art:"land-mundo-fenghuo.webp", x:4,  y:60, w:36 },
          { key:"moyu",    tab:"explore", label_key:"continent_moyu",
            art:"land-mundo-moyu.webp",    x:60, y:63, w:36 },
        ],
      },
    };

    // ═══ 圖 V7 — O DENTRO DO CONTINENTE (2026-09-15, ordem do owner) ═══════
    //
    // Owner, 14/09: *"quando abrir tem la' os icones das coisas do que fazer
    // como dungeons etc explorer **nao em menu** e sim naquele estilo"*.
    //
    // ⚠️ SEIS pecas e nao trinta, e a decisao foi escrita na V7 ANTES de se
    // desenhar um pixel: as seis portas sao as MESMAS nos cinco continentes —
    // o que muda entre eles e' o TERRITORIO, nao a lista de coisas a fazer.
    // Trinta pecas seriam cinco vezes a mesma decisao, cinco vezes o custo, e
    // cinco oportunidades de divergirem.
    //
    // ⚠️ E NAO ha' pintura por baixo desta grelha, de proposito. A alternativa
    // — um continente pintado com os seis sitios la' dentro e as coordenadas no
    // codigo — ja' foi rejeitada duas vezes (V5 §2, V7): `ARTE_PROVENIENCIA
    // §2.5` obriga a ficheiro NOVO ao regerar, e nesse dia o alinhamento passa
    // a MENTIR em silencio. As pecas `door` nascem sobre quase-preto por
    // contrato e assentam na superficie escura da gaveta.
    //
    // ⚠️ A chave e' a do DESTINO (`explore`, `plaza`, ...) e nao uma palavra
    // traduzida: e' assim que o ficheiro se deriva mecanicamente e que a guarda
    // da §16h consegue exigir peca para CADA sitio, com o nome do que falta.
    var ISLE_DOOR_ART = {
      explore:   "door-mundo-explore.webp",
      plaza:     "door-mundo-plaza.webp",
      sect:      "door-mundo-sect.webp",
      dungeons:  "door-mundo-dungeons.webp",
      caravan:   "door-mundo-caravan.webp",
      chronicle: "door-mundo-chronicle.webp",
    };

    // ═══ 州 O CHÃO DE CADA CONTINENTE (2026-09-16 — correcção do owner) ═════
    //
    // 🔴 A 15/09 eu entreguei os seis locais como uma GRELHA de azulejos por
    // baixo do mapa. O owner corrigiu, textual: *"quando estou no continente eu
    // abro ele **tipo um mapa mundial**, e dentro tem a imagem da praça,
    // aventura, as dungeons"*. Uma grelha de azulejos bonitos continua a ser
    // uma grelha — o que ele pediu é que o continente ABRA COMO UM LUGAR, com
    // os sítios POSTOS DENTRO dele. É o que a Caverna e o Mundo já fazem uma
    // camada acima, e faltava esta.
    //
    // ⚠️ Isto NÃO reabre a proibição da V5 §2 / V7. O que lá está proibido é
    // *"uma pintura única do continente com os seis sítios LÁ DENTRO"* — os
    // edifícios pintados no fundo. Estas cinco são `place`: **chão vazio**, e as
    // seis `door-mundo-*` continuam a ser peças separadas postas por CSS.
    // Regerar o chão não move uma porta; é a mesma hipótese (b), um nível abaixo.
    var ISLE_SCENE_ART = {
      linghe:  "isle-linghe-scene.webp",
      qianhe:  "isle-qianhe-scene.webp",
      yanshan: "isle-yanshan-scene.webp",
      fenghuo: "isle-fenghuo-scene.webp",
      moyu:    "isle-moyu-scene.webp",
    };

    // ⚠️ A posição é a MESMA nos cinco continentes, e isso é desenho e não
    // preguiça: o jogador aprende onde fica a Praça uma vez e ela está sempre
    // ali. O que muda entre continentes é o TERRITÓRIO, nunca a geografia dos
    // seus lugares — a mesma decisão que fez as portas serem 6 e não 30.
    // ⚠️ E NÃO é uma grelha: as seis estão espalhadas fora de eixo, porque um
    // mapa não alinha os seus lugares em colunas. A §16d confirma que nenhuma
    // fica por cima de outra (uma porta tapada é um destino inalcançável sem
    // erro nenhum), lendo a razão da caixa do próprio `HubScene`.
    var ISLE_DOOR_LAYOUT = {
      explore:   { x:6,  y:8,  w:30 },
      plaza:     { x:58, y:4,  w:34 },
      sect:      { x:30, y:30, w:32 },
      dungeons:  { x:2,  y:52, w:30 },
      caravan:   { x:62, y:56, w:32 },
      chronicle: { x:28, y:76, w:30 },
    };

    // ⚠️ "Pendente" e' um estado LEGITIMO; "esquecido" nao e' (Lei 0 passo 5).
    // Esta tabela existe para a guarda da §15 poder CONTAR o que falta com o
    // motivo escrito, em vez de o silencio passar por conclusao.
    // ⚠️ "Pendente" e' um estado LEGITIMO; "esquecido" nao e' (Lei 0 passo 5).
    //
    // 🔴 2026-09-13 — ESTA TABELA ESTAVA A MENTIR, e a mentira era de CATEGORIA.
    // Ela dizia "3 cenas pendentes" como se os quatro hubs fossem lugares a'
    // espera de uma pintura. Servidos e OLHADOS a 390x844, so' DOIS deles sao
    // lugares. Uma cena `place`+`door` e' o idioma de um hub que **E'** um
    // sitio; aplicada aos outros dois seria uma moldura por cima de uma coisa
    // que ja' tem o seu idioma certo:
    //
    //   Caverna ...... e' um lugar (a gruta, com salas) ......... cena ✅ 11/09
    //   Mundo ........ e' um lugar (os cinco continentes) ....... cena ✅ 13/09
    //   Eu ........... e' uma PESSOA, nao um sitio ............. decisao
    //   Pergaminho ... e' um OBJECTO (o dia num rolo) .......... decisao
    //   Combate ...... membro unico ........................... decisao 11/09
    //
    // ⇒ **2 de 2 cenas de lugar estao feitas.** O que fica nao e' "arte por
    // pintar": sao duas telas com o idioma certo e defeitos PROPRIOS, cada um
    // com o seu numero, escritos aqui para nao voltarem a passar por "cena
    // pendente" — que e' uma etiqueta que nunca ninguem ia levantar.
    var HUB_SCENE_PENDING = {
      hub_eu:         "decisao, nao pendente: o Eu e' uma PESSOA e nao um lugar — uma cena `place` poria a identidade do jogador dentro de uma paisagem, e a lei do `CultivatorFigure` (07/09) e' que a figura SO' existe sentada. O idioma certo e' o que o cabecalho ja' decidiu a 09/09: a marca 坐 com o anel do reino (`RealmAvatar`), que e' o dono unico e passou a servir tambem este hub neste lote.",
      hub_pergaminho: "decisao, nao pendente: e' o unico hub que NAO e' um lugar nem uma pessoa — e' um OBJECTO, o dia do cultivador num rolo de papel, e a metafora ja' foi construida no R4b (bastoes, selo de cera, tres seccoes). Uma cena por tras dele seria uma moldura a' volta de uma coisa que ja' tem forma. 2026-09-15 — o PENDENTE DE PELE que aqui estava FECHOU: o rolo ocupava 253 dos 601px da caixa de conteudo (42%) e deixava 348px de PAGINA vazia; passou a 589 de 601 (98%), medido a 390x844, e o papel ganhou envelhecimento TONAL (a 1a tentativa, com dois repetidores cruzados, saiu papel MILIMETRICO e so' se viu a OLHAR).",
      hub_combate:    "decisao, nao pendente: hub de membro unico — o CombatTab JA' E' o landing, e uma cena com uma porta so' e' uma porta com moldura (V5 §3.1)",
    };

    // ⚠️ O gate pede as DUAS flags de proposito. As telas de hub so' existem com
    // a `ui_v2` ligada; sem isto, ligar so' a `o_mapa` nao mudava um pixel e o
    // owner concluia que a flag estava avariada (Lei §6 — o painel tem de dizer
    // a verdade). A descricao da flag no painel diz o mesmo por palavras.
    function mapaOn() {
      return typeof featureEnabled === "function"
             && featureEnabled("o_mapa") && featureEnabled("ui_v2");
    }

    // `doors` = o estado VIVO por porta, so' onde ele existe:
    //   { <key>: { lit: bool, line: string } }
    // Uma porta sem entrada esta' acesa e muda. O componente nunca vai buscar
    // dados: quem ja' tem o payload e' que os passa (regra da Fonte Unica).
    // ═══ 門 A PORTA PINTADA — UM DONO, duas montagens (2026-09-15) ══════════
    //
    // 🔴 PORQUE ISTO SAIU DE DENTRO DO `HubScene`.
    //
    // O owner, a 14/09: *"o mapa deveria ser que nem o sistema da mochila com
    // imagens, ai tu clica, viaja la' e quando abrir tem la' os icones das
    // coisas do que fazer como dungeons etc explorer **nao em menu** e sim
    // naquele estilo"*. O lado de FORA (a Caverna, o Mundo) ja' era isso; o
    // lado de DENTRO — os locais de um continente — continuava a ser uma
    // grelha de seis emoji do sistema.
    //
    // Desenhar essa grelha com a mesma linguagem exigia repetir aqui a arte, a
    // mascara, os dois estados, o nome, a linha e o `aria-label`. **Uma
    // capacidade com duas ligacoes a' mao diverge sempre** — e' a Lei F-7 §2, e
    // foi medida quatro vezes em quatro dias. Entao a porta sai para aqui e as
    // duas telas montam-na: a cena posiciona-a em absoluto, a gaveta poe-a numa
    // grelha. O que muda e' o `style`; tudo o resto e' o mesmo codigo.
    //
    // ⚠️ A clausula de 09/09 vive aqui dentro e nao no chamador: quem desenha
    // dentro de um `<button>` DECLARA `color` — a folha do agente poe
    // `color: buttontext` (PRETO) e apaga o texto sem ninguem dar por isso.
    function SceneDoor({ art, name, line, lit, dim, dimKey, onActivate, style }) {
      const [failed, setFailed] = useState(false);
      const aceso = lit !== false;
      return (
        <button type="button" className="nv-door"
          /* ⚠️ Uma porta pintada sem nome e' pior do que uma marca sem nome: a
             imagem e' `alt=""` de proposito (e' decoracao do botao), portanto o
             botao TEM de se anunciar. E o estado vai junto — um leitor de ecra
             nao ve' o cinzento. */
          aria-label={aceso ? name
                            : name + " — " + safeT(dimKey || "mapa_porta_apagada")}
          onClick={() => { haptic("select"); onActivate && onActivate(); }}
          style={Object.assign({
            padding:0, border:"none", background:"none", cursor:"pointer",
            fontFamily:"inherit",
            // 🔴 a clausula de 09/09 — um `<button>` nao herda a cor da pagina.
            color:"var(--gold2)",
          }, style || {})}>
          <span style={{ position:"relative", display:"block", width:"100%",
                         aspectRatio:"1 / 1" }}>
            {/* A chapa de recurso: a arte pode nao carregar, e um botao
                invisivel e' um beco (Lei §1).
                ⚠️ **So' existe quando a arte FALHA**, e isso foi apanhado a
                OLHAR, nao a ler. A 1a versao desenhava-a sempre "por baixo", a
                contar que a imagem a tapasse — mas a imagem da porta e'
                dissolvida nos bordos por uma mascara radial, e o que se via
                eram CINCO RECTANGULOS ARREDONDADOS a emoldurar as portas. Ou
                seja: a chapa honesta tinha-se tornado a moldura que a carta
                passou 05/09 a tirar. */}
            {failed && (
              <span aria-hidden="true" style={{
                position:"absolute", inset:"15%", borderRadius:10,
                background:"linear-gradient(160deg, rgba(var(--surface-rgb),.92),"
                           + " rgba(var(--surface3-rgb),.96))",
                border:"1px solid rgba(var(--gold-rgb),.28)",
              }} />
            )}
            {!failed && (
              <img src={artUrl(art)} alt="" loading="lazy" decoding="async"
                   onError={() => setFailed(true)}
                   style={{
                     position:"absolute", inset:0, width:"100%", height:"100%",
                     objectFit:"contain", display:"block",
                     // ⚠️ NADA de `mix-blend-mode` — a licao do
                     // `CultivatorFigure` (07/09): `screen` nao remove o preto,
                     // CLAREIA tudo. A peca ja' nasce sobre quase-preto; basta
                     // esbater a aresta com a mascara.
                     WebkitMaskImage:"radial-gradient(circle at 50% 50%, #000 52%, transparent 78%)",
                     maskImage:"radial-gradient(circle at 50% 50%, #000 52%, transparent 78%)",
                     // Os DOIS estados, na mesma arte.
                     filter: aceso
                       ? "drop-shadow(0 0 14px rgba(var(--glow-rgb),.45))"
                       : (dim || "grayscale(.62) brightness(.52)"),
                     transition:"filter .3s ease",
                   }} />
            )}
            {/* ⚠️ O nome NAO e' uma caixa. A 1a versao punha um bloco de
                gradiente por baixo de cada nome e o resultado, visto a olho,
                eram cinco RECTANGULOS CINZENTOS colados por cima de uma
                pintura — o "menu disfarcado de paisagem" outra vez, so' que com
                arte melhor. Agora e' tinta sobre a peca: a base da porta ja' e'
                escura por construcao (o `door` pede-o ao modelo) e a sombra do
                texto chega. E' o mesmo idioma do `PieceHero`. */}
            <span style={{
              position:"absolute", left:"-6%", right:"-6%", bottom:"-1%",
              display:"flex", flexDirection:"column", alignItems:"center", gap:1,
            }}>
              <span style={{
                fontFamily:"'Cinzel',serif", fontSize:10.5, fontWeight:700,
                letterSpacing:.3, lineHeight:1.2, textAlign:"center",
                color: aceso ? "var(--gold2)" : "var(--muted)",
                textShadow:"0 1px 2px #000, 0 0 9px rgba(0,0,0,.95),"
                           + " 0 0 18px rgba(0,0,0,.8)",
              }}>{name}</span>
              {line && (
                <span style={{
                  fontSize:8.5, lineHeight:1.3, textAlign:"center",
                  color: aceso ? "var(--muted)" : "var(--muted2)",
                  textShadow:"0 1px 2px #000, 0 0 9px rgba(0,0,0,.95)",
                }}>{line}</span>
              )}
            </span>
          </span>
        </button>
      );
    }

    // ⚠️ `sceneDef` (2026-09-16) — uma cena que NAO vem do `HUB_SCENE_DEFS`.
    // Nasceu da correccao do owner: o continente abre como um LUGAR, e um
    // continente nao e' um hub (nao esta' no `HUB_DEFS`, nao tem `group`). Sem
    // isto havia duas saidas, as duas piores: por os 5 continentes na tabela dos
    // hubs (e partir a §16, que compara essa tabela com o `HUB_DEFS`), ou
    // escrever uma segunda cena a' mao — que e' a Lei F-7 §2 outra vez, agora
    // com a CAIXA em vez da porta. Quem passa `sceneDef` traz a sua propria
    // definicao; quem passa `hub` continua byte a byte como estava.
    function HubScene({ hub, setTab, doors, sceneDef }) {
      const [bgFailed, setBgFailed] = useState(false);
      const def = sceneDef || HUB_SCENE_DEFS[hub];
      if (!def) return null;
      const st = doors || {};
      return (
        <div style={{
          // ⚠️ TRES valores que o OLHAR corrigiu, e nenhum deles era obvio a ler:
          //  · `1 / 1.70` e nao `1 / 1.02`. A 390x844 uma caixa quadrada ocupava
          //    365px e deixava 300px de pagina vazia por baixo: a cena lia-se
          //    como um CARTAO a flutuar, nao como o sitio onde se esta'. O lugar
          //    tem de ocupar o ecra. MEDIDO a 390x844: do fim do cabecalho
          //    (148px) ao topo da barra (775px) ha' 627px, e 358 x 1.70 = 609.
          //  · sem `border`. Uma linha a' volta faz da pintura um anexo — e' a
          //    mesma razao por que o pe' da chapa da carta se dissolve (05/09).
          //  · o veu desceu de .58 para .44 no bordo: a 1a versao apagava a boca
          //    da gruta, que e' a unica luz da pintura.
          // ⚠️ A ALTURA E' A ALTURA DAS PORTAS. `y`/`w` sao % de eixos
          // diferentes, portanto mexer aqui MOVE tudo — a guarda da §16 le' esta
          // razao do proprio ficheiro para nunca discordar dela.
          position:"relative", width:"100%", maxWidth:520, margin:"4px auto 10px",
          aspectRatio:"1 / 1.70", borderRadius:14, overflow:"hidden",
          // Lei §1 — se a pintura nao carregar, o lugar continua a ser um lugar:
          // fica a tinta lavada por baixo e as cinco portas continuam tocaveis.
          background:"radial-gradient(ellipse at 50% 38%, rgba(var(--glow-rgb),.20), transparent 62%),"
                     + "linear-gradient(180deg, rgba(var(--surface-rgb),.92), rgb(var(--bg-rgb)))",
          animation:"fade-up .3s ease",
        }}>
          {!bgFailed && (
            <img src={artUrl(def.art)} alt="" loading="lazy" decoding="async"
                 onError={() => setBgFailed(true)}
                 style={{ position:"absolute", inset:0, width:"100%", height:"100%",
                          objectFit:"cover", objectPosition:"50% 46%", display:"block",
                          opacity:.88 }} />
          )}
          {/* O veu. Sem ele a pintura briga com as portas — e as portas sao o
              assunto. E' tambem o que faz as bordas cairem no preto, para a
              caixa nao ter aresta (o mesmo truque do pe' da chapa da carta).
              🔴 2026-09-16 — O VEU PASSA A SER DECLARAVEL PELA CENA, e a razao
              foi vista a OLHAR, nao a ler. O veu de cima foi afinado para o mar
              de nuvens do Mundo e para a rocha da Caverna, que sao quase-pretos.
              Os cinco continentes NAO sao: o vale de Linghe tem um brilho no
              horizonte e terracos claros. Com o veu fraco, cada peca `door` (que
              nasce sobre quase-preto por contrato) apareceu como um DISCO ESCURO
              colado ao vale — cinco halos, que e' a mesma avaria de 13/09 ao
              contrario: nao e' o fundo claro demais a fazer buracos, e' o fundo
              claro demais a fazer AUREOLAS. A regra e' a mesma, e vale a pena
              escreve-la outra vez: **o chao tem de ser mais escuro do que as
              figuras que assentam nele.** */}
          <div aria-hidden="true" style={{
            position:"absolute", inset:0, pointerEvents:"none",
            background: def.veil
              || "radial-gradient(ellipse at 50% 44%, rgba(var(--bg-rgb),.06),"
                 + " rgba(var(--bg-rgb),.44) 78%, rgb(var(--bg-rgb)) 100%)",
          }} />
          {def.doors.map(d => {
            const ds = st[d.key] || {};
            return (
              <SceneDoor
                key={d.key}
                art={d.art}
                name={safeT(d.label_key)}
                line={ds.line}
                lit={ds.lit !== false}
                dim={def.dim}
                dimKey={def.dim_key}
                /* 州 2026-09-13 — a porta pode ABRIR em vez de IR, e isso e' o
                   que deixou o Mundo ter cena sem perder a informacao viva.
                   Na Caverna uma porta e' uma saida: toca-se e vai-se. No
                   Mundo um continente NAO e' um destino — e' um sitio que
                   revela os seus locais, o estado da regiao, o evento do Ceu,
                   a gruta e a viagem. Uma porta que NAVEGASSE apagava tudo
                   isso para ganhar atmosfera, que e' exactamente a troca que a
                   chapa de recurso perdeu a 11/09.
                   ⚠️ O `d.tab` continua a ser o caminho por omissao: quem nao
                   passa `onSelect` tem o comportamento de hoje byte a byte. */
                onActivate={() => {
                  if (typeof ds.onSelect === "function") { ds.onSelect(d.key); return; }
                  setTab(d.tab);
                }}
                style={{ position:"absolute", left:d.x + "%", top:d.y + "%",
                         width:d.w + "%" }} />
            );
          })}
        </div>
      );
    }

    // ─── Card / CardTitle / StatGrid / ProgressBar / Badge ────────────────────
    function Card({ children, style, ornate=true, onClick }) {
      // v14.13d (2026-05-25) — Bug fix root-cause of "Market buy não funciona"
      // (owner round 2026-05-24). `MarketListingCard` passed `onClick={onTap}`
      // expecting Card to forward, but Card silently dropped it. Affects every
      // Card-wrapped clickable surface (currently only MarketListingCard, but
      // future callers benefit). When onClick is set, also expose cursor:pointer
      // hint unless the caller explicitly overrides via style.
      return (
        <div onClick={onClick} style={{
          position:"relative",
          background:"linear-gradient(160deg,rgba(var(--surface-rgb),.92) 0%,rgba(var(--surface3-rgb),.95) 100%)",
          border:"1px solid rgba(var(--gold-rgb),.25)",
          borderRadius:10, padding:"14px 14px 12px",
          marginBottom:10, animation:"fade-up .35s ease",
          overflow:"hidden",
          cursor: onClick ? "pointer" : undefined,
          ...style,
        }}>
          <div style={{ position:"absolute", top:0, left:0, right:0, height:1,
            background:"linear-gradient(90deg,transparent,rgba(var(--gold-rgb),.4),transparent)",
            pointerEvents:"none" }} />
          <div style={{ position:"absolute", inset:0, opacity:.025, pointerEvents:"none",
            backgroundImage:"repeating-linear-gradient(0deg,rgba(var(--gold-rgb),.5) 0px,transparent 1px,transparent 4px)",
            backgroundSize:"100% 4px" }} />
          {ornate && <OrnateCorners />}
          <div style={{ position:"relative", zIndex:1 }}>{children}</div>
        </div>
      );
    }
    function CardTitle({ left, right }) {
      return (
        <div style={{
          display:"flex", justifyContent:"space-between", alignItems:"center",
          marginBottom:10, paddingBottom:8,
          borderBottom:"1px solid rgba(var(--gold-rgb),.15)",
        }}>
          <span style={{
            fontFamily:"'Cinzel',serif", fontSize:11, letterSpacing:1.2,
            textTransform:"uppercase", color:"rgba(var(--gold-rgb),.85)",
          }}>{left}</span>
          {right != null && (
            <span style={{ fontFamily:"'Cinzel',serif", fontSize:11, fontWeight:600, color:"var(--gold2)" }}>{right}</span>
          )}
        </div>
      );
    }
    // ═══ 牌 A CARTA — a carta-padrão do Nivrael (2026-09-05) ══════════════════
    //
    // Mandato do owner (2026-09-02/03, textual): *"Um jogo responsivo com
    // design, items, personagens. Um jogo 2D não. Porém algo melhor, cards etc."*
    //
    // O QUE ESTAVA MAL, contado: o jogo tem **413 usos de `<Card>`** e todos
    // desenham a mesma moldura — gradiente, borda dourada de 1px, raio 10, um
    // fio no topo, cantos ornamentados e uma trama de linhas. É a moldura de
    // qualquer dashboard, e é a mesma para o Qi, para uma pílula e para um
    // aviso. Nada nela diz *jogo de cartas*, e nada nela diz *Nivrael*.
    //
    // Esta carta SUBTRAI: **um** contorno, **um** fio, nenhum gradiente,
    // nenhum canto ornamentado, nenhuma trama. O que sobra é a arte, o vazio,
    // e três marcas que carregam sentido. Raio **4**, não 10 — uma folha
    // cortada, não um azulejo de aplicação. O canto inferior direito é
    // **chanfrado**: uma carta física gasta-se ali, e é a silhueta que se
    // reconhece de longe sem ler nada.
    //
    // ─── 1. A ASSINATURA: 品 o LOMBO CONTADO ────────────────────────────────
    //
    // ⚠️ Este jogo **não pode** ter código de cores de raridade, e isso foi
    // MEDIDO no motor, não suposto. Há **oito** vocabulários de raridade vivos,
    // com comprimentos diferentes:
    //
    //   técnica    5  common · refined · perfected · transcendent · celestial
    //   besta      7  Common … Divine                    (config.BEAST_RANKS)
    //   artefacto  4  normal · perfect · divine · spirit (forge_engine)
    //   pílula     5  difficulty / required_alchemy_tier 1..5
    //   núcleo     4  flawed · normal · superior · perfect (golden_core_engine)
    //   armadilha  6  normal · common · rare · epic · mythic · legendary
    //   gacha      4  common · rare · epic · legendary
    //   lei do Dao 5  common · uncommon · rare · epic · legendary
    //
    // Pintar "roxo = épico" obrigaria o jogador a aprender oito escalas e a
    // acreditar que o *Rare* de uma besta vale o mesmo que o *perfected* de uma
    // arte — o que é falso: um é 3 de 7, o outro é 3 de 5.
    //
    // Então a raridade deixa de ser uma **cor** e passa a ser uma **MEDIDA**:
    // uma faixa vertical no bordo esquerdo, cortada em exactamente tantos
    // entalhes quantos a escala DAQUELE conteúdo tem, com `índice+1` entintados.
    // Lê-se "3 de 5" e "3 de 7" sem saber nenhum dos dois vocabulários, e sem o
    // jogo mentir que são a mesma coisa. É também o que o género faz: no wuxia
    // os graus **contam-se** (三品丹 — pílula de terceiro grau), não se pintam.
    //
    // O bordo esquerdo é o **lombo** de um volume encadernado: um 秘籍 é um
    // livro, e o grau está entalhado na lombada.
    //
    // ⚠️ Um valor DESCONHECIDO não desenha lombo nenhum (`nivRank` → null).
    // Desenhar 1 de 5 para um grau que não se reconhece seria afirmar "isto é
    // do grau mais baixo" — uma mentira. Silêncio é melhor do que um número
    // errado (a mesma regra da tela do Cultivo no cume).
    //
    // ─── 2. O VERSO HONESTO (Lei §1) ────────────────────────────────────────
    //
    // 307 peças de arte não nascem no mesmo dia. A carta **nunca** tem buraco:
    // o verso — anéis de tinta e o glifo da própria peça — está sempre pintado
    // POR BAIXO, e a ilustração aparece por cima quando (e se) carregar. É o
    // que se vê enquanto carrega, é o que fica se falhar, e é o que fica
    // enquanto a peça não tiver arte. Sem spinner, sem ícone de imagem partida,
    // sem tela vazia. Uma carta virada para baixo é um estado legítimo de um
    // jogo de cartas; um rectângulo cinzento não é.
    //
    // ─── 3. O SELO 朱砂 ─────────────────────────────────────────────────────
    //
    // `LINGUAGEM_VISUAL_WEB_C.md §1`: *"O selo é a assinatura. (…) Aparece uma
    // vez por página, nunca duas."* Aqui ele marca o estado **activo** — arte
    // equipada, besta companheira, efeito a correr — e o jogo torna a regra
    // verdadeira sozinho: equipam-se poucas artes e há **um** companheiro.
    // Não-possuído e trancado não têm selo: um carimbo é posse, não catálogo.
    //
    // ⚠️ É um SVG, não um caractere. `印` dependeria de uma fonte CJK que o
    // mini-app não carrega, e a 22px o fallback do sistema muda de aparelho
    // para aparelho. O desenho é 白文 (intaglio: a marca é o vazio na tinta).
    //
    // ─── 4. A HIERARQUIA ────────────────────────────────────────────────────
    //
    // Hoje é tudo 10–13px: o nome, o efeito, o custo e o estado pesam o mesmo.
    // Aqui há **quatro** degraus e uma única régua horizontal no cartão inteiro:
    //   sobrancelha  Cinzel 8.5 · tracking .18em · tipo · GRAU
    //   nome         Cormorant Garamond 17        ← o único texto grande
    //   ── fio de 22px ──                          ← a ÚNICA régua interior
    //   efeito       11.5 · o NÚMERO em ouro
    //   pé           10.5 · custo à esquerda
    //
    // O Cormorant é a decisão 2 de 3 do doc da linguagem visual, e a fonte já
    // está carregada desde a WEB-C. Esta carta é um sítio NOVO — aplicá-la aqui
    // é "desenho por sítio", que é exactamente o que a V2c pedia; não é a
    // varredura dos ~200 Cinzel existentes, que continua a viver na V4.
    //
    // ─── 5. O QUE ELA NÃO FAZ ───────────────────────────────────────────────
    //
    // Não anima nada. Nem brilho no grau máximo, nem `+1` a saltar, nem
    // contadores. A entrada usa o `fade-up` que a casa já tem e mais nada
    // (`LINGUAGEM_VISUAL_WEB_C.md` Achado 1: celebrar não-eventos é proibido).
    // A única diferença do grau máximo é a palavra do grau em `--gold3`.

    // As escalas de raridade do jogo, com o comprimento REAL de cada uma.
    // Acrescentar uma escala é acrescentar uma linha aqui — nunca um `if` na
    // carta. As três abaixo são as provadas neste lote.
    var NIV_RANK_SCALES = {
      // core/combat_engine.py — TECHNIQUE_GRADES / GRADE_ORDER
      technique: { order: ["common", "refined", "perfected", "transcendent", "celestial"],
                   label: v => t("technique_grade_" + v) },
      // config.py — BEAST_RANKS (os valores chegam Capitalizados da base)
      beast:     { order: ["common", "uncommon", "rare", "epic", "legendary", "mythic", "divine"],
                   label: v => t("beast_rank_" + v) },
      // ⚠️ `required_alchemy_tier` (1..`MAX_ALCHEMY_TIER`=5), NÃO `difficulty`.
      // A 1ª versão desta linha usava `difficulty` e estava ERRADA: medido nos
      // seeds, `difficulty` vai a **7** (dist. 7/6/9/5/10/2/2), logo as pílulas
      // de grau 6 e 7 saturavam em 5 de 5 e ficavam indistinguíveis das de 5 —
      // o lombo a mentir exactamente como uma cor mentiria. `required_alchemy_tier`
      // é a escada de verdade: 1..5 (10/10/7/10/4), é o que fecha a receita, é
      // o que agrupa o payload e é o que tem nome próprio (`ALCHEMY_TIERS`).
      // `difficulty` é uma entrada da chance de sucesso, não um posto.
      pill:      { steps: 5, numeric: true, label: n => t("alch_grade", { n }) },

      // ─── acrescentadas 2026-09-08, cada uma MEDIDA no motor E nos seeds ───
      //
      // ⚠️ ARTEFACTO: são **NOVE** degraus (`grade` 0..8), não os quatro que o
      // prompt deste lote nomeava. Os quatro (`normal·perfect·divine·spirit`,
      // `ARTIFACT_QUALITY_ORDER`) são a **qualidade de forja**, e o motor diz
      // por escrito que não são uma escada: são inferidos *post-hoc*
      // (`infer_artifact_quality`), nunca persistidos, APAGADOS pelo refino, e
      // `refined` está "OUTSIDE the order on purpose". É exactamente o mesmo
      // tipo de campo que o `difficulty` da pílula — uma entrada, não um posto.
      //
      // O posto do artefacto é o `grade`: é a escada que a forja sobe, é o que
      // o payload já traz mastigado (`grade_name`), é o que o filtro da mochila
      // agrupa, e tem nome próprio por degrau em `config.ARTIFACT_GRADES`
      // (Mortal·Amarelo·Místico·Terra·Céu·Espírito·Divino·Dao·Celestial — a
      // escada clássica 黄玄地天). Medido nos seeds: os 51 artefactos ocupam
      // os NOVE degraus (3/3/10/7/9/7/3/3/6), logo uma escala de 4 saturaria
      // dois terços do catálogo no topo — o lombo a mentir como uma cor mentiria.
      //
      // ⇒ DECIDIDO E ESCRITO (a pergunta que o prompt mandava responder):
      //   **`refined` NÃO é o 5º degrau. É um eixo à parte** — e por isso não
      //   entra no lombo de todo: continua a ser o chip de qualidade que a
      //   TAPETE QoL §5 já desenha (`ART_QUALITY_*`). Um artefacto refinado
      //   diz-se pelo `grade` que subiu, que é precisamente o que o lombo conta.
      // ⚠️ `base: 0` — é a única escala do jogo que começa em ZERO.
      artifact:  { steps: 9, numeric: true, base: 0,
                   label: n => t("art_grade_" + n) },

      // core/dao_laws_engine.py — RARITY_WEIGHTS (a raridade da LEI; o
      // `TIER_THRESHOLDS` 0..5 é outra coisa: a compreensão do CAMINHO pelo
      // jogador, não o posto da peça).
      dao_law:   { order: ["common", "uncommon", "rare", "epic", "legendary"],
                   label: v => t("law_rank_" + v) },

      // core/beast_engine.py — TRAP_QUALITY_ORDER.
      // ⚠️ Aqui `mythic` está ABAIXO de `legendary`, ao contrário do
      // `BEAST_RANKS` onde está acima. Não é gralha minha: é o motor. A carta
      // segue o motor de cada conteúdo — é essa a razão de existirem oito
      // vocabulários em vez de um código de cores.
      trap:      { order: ["normal", "common", "rare", "epic", "mythic", "legendary"],
                   label: v => t("trap_rank_" + v) },

      // database/seeds/gacha_seeds.py — os baldes do banner.
      // (O `FRAGMENT_EXCHANGE` só vende três deles; `common` existe no bolo.)
      gacha:     { order: ["common", "rare", "epic", "legendary"],
                   label: v => t("gacha_rank_" + v) },
    };

    // → { i, n, label } · null quando o valor não pertence à escala.
    function nivRank(kind, value) {
      const sc = NIV_RANK_SCALES[kind];
      if (!sc || value == null || value === "") return null;
      if (sc.numeric) {
        const raw = parseInt(value, 10);
        // ⚠️ `base` é o primeiro degrau da escada, não um offset cosmético: a
        // escala do artefacto começa em 0 e um `grade` 0 tem de acender o
        // entalhe de baixo (1 de 9), nunca devolver `null` — "grau desconhecido"
        // e "grau mais baixo" são coisas diferentes e a carta não pode confundi-las.
        const base = sc.base == null ? 1 : sc.base;
        if (!isFinite(raw) || raw < base) return null;
        const n = Math.min(sc.steps, raw - base + 1);   // 1..steps — o entalhe
        // ⚠️ o rótulo usa o valor **grampeado**, não o cru: um `grade` 12 vindo
        // de um dado sujo acende 9 de 9 e tem de dizer "Celestial", não pedir
        // um `art_grade_12` que não existe e imprimir a chave em cima da carta.
        return { i: n - 1, n: sc.steps, label: sc.label(n - 1 + base) };
      }
      const low = String(value).toLowerCase();
      const idx = sc.order.indexOf(low);
      if (idx < 0) return null;   // ⚠️ desconhecido ⇒ SEM lombo (ver o cabeçalho)
      return { i: idx, n: sc.order.length, label: sc.label(sc.order[idx]) };
    }

    // ═══ 器 OS TRÊS PATAMARES (2026-09-10) ═══════════════════════════════════
    //
    // Ordem do owner (2026-09-08, textual): *"as espadas cards diferenciados nos
    // Tieres. Heaven etc. tipo quanto mais alto o tier o cards mais bonito
    // personalizado sei la como cores. Assim a espada nao é a mesma sempre."*
    //
    // ⚠️ ISTO NÃO REABRE A DECISÃO DE 05/09. O lombo continua a dizer **quanto**
    // — contado, honesto sobre oito escalas de comprimentos diferentes. O que se
    // acrescenta diz outra coisa: **"isto é raro"**. As duas coexistem porque
    // respondem a perguntas diferentes: **o lombo é para LER, o ornamento é para
    // NOTAR** — e por isso o ornamento não precisa de legenda nenhuma. Um código
    // de cores continuaria a mentir (o *Rare* de uma besta é 3/7 e o *perfected*
    // de uma arte é 3/5); um ornamento não afirma nada de traduzível, logo não
    // pode mentir.
    //
    // ─── Porque TRÊS e não nove ─────────────────────────────────────────────
    // Lei §3 (profundidade > variedade), e uma razão de desenho: nove decisões
    // separadas nunca parecem um conjunto — parecem nove acidentes. Três
    // patamares são um SISTEMA, e aprendem-se sem que ninguém os explique.
    //
    // ─── Onde cortam, e porque é uma RAZÃO e nunca uma lista ────────────────
    // O patamar sai de `p = i / (n - 1)` — a posição RELATIVA do degrau dentro
    // da escala DAQUELE conteúdo, que é exactamente o que o `nivRank` já mede.
    // ⚠️ Uma lista de nomes ("celestial, divine, legendary…") envelhece em
    // silêncio: a lição de 07/09 (a guarda dos `*Classic` cobria 3 de 5 e ficou
    // verde) e a de 06/09 (a escala do artefacto tinha NOVE degraus e o prompt
    // dizia quatro). Assim, acrescentar uma escala ao `NIV_RANK_SCALES` dá-lhe
    // os três patamares de graça, no mesmo commit, sem tocar aqui.
    //
    //   celeste  p >= .90   → em QUALQUER escala, só o degrau do topo
    //   notável  p >= .60   → a antecâmara do topo
    //   comum    o resto    → a carta de 05/09, intocada
    //
    // MEDIDO NOS SEEDS (regra da casa: comparar com os DADOS, não só com o
    // motor — foi assim que a escala de 4 do artefacto morreu a 06/09):
    //   artefacto  51 peças → comum 32 (63%) · notável 13 (25%) · celeste 6 (12%)
    //   pílula     41 peças → comum 27 (66%) · notável 10 (24%) · celeste 4 (10%)
    //   besta      15 peças → comum 11 (73%) · notável  3 (20%) · celeste 1 ( 7%)
    // Uma pirâmide nas três famílias com catálogo próprio — que é o que a régua
    // deste lote exige: *"se tudo ficar bonito, o topo deixou de ser topo?"*.
    //
    // ⚠️ E MEDIDO EM PRODUÇÃO, que diz outra coisa e tem de ficar escrito.
    // O que os jogadores do `main` TÊM não é a pirâmide do catálogo: 5.098
    // artefactos possuídos, dos quais **1.694 (33%) são grau 8** e 48% são grau
    // 7-8. Numa mochila do `main` uma carta em cada três seria celeste e o topo
    // deixaria de ser topo. Isso **não** move os cortes: é a inflação conhecida
    // da beta (o fix real é o rebalanceamento no servidor de launch), esta flag
    // é launch-server-bound e nasce OFF em todo o lado. Fica escrito para quem
    // um dia a ligar num mundo de inventário inflacionado saber o que vai ver.
    // Simétrico e mais silencioso: nenhum jogador do `main` passou de
    // `perfected` em técnica (840/320/60/0/0), portanto nas ARTES o ornamento do
    // topo hoje não apareceria a ninguém. **O ornamento não inventa raridade —
    // mostra a que existe.**
    var NIV_TIER_CUTS = { celestial: .90, notable: .60 };
    // → "common" | "notable" | "celestial". ⚠️ Sem posto reconhecido ⇒ "common",
    // pela mesma razão que um grau desconhecido não desenha lombo: ornamentar o
    // que não se sabe medir é afirmar uma raridade que ninguém verificou.
    function nivTier(rank) {
      if (!rank || !(rank.n > 1)) return "common";
      const p = rank.i / (rank.n - 1);
      if (p >= NIV_TIER_CUTS.celestial) return "celestial";
      if (p >= NIV_TIER_CUTS.notable) return "notable";
      return "common";
    }

    // A arte servida pelo jogo. A rota é `/miniapp/assets/` (regra `assets` do
    // `_MINIAPP_SUBDIR_RULES`); a pasta física é `miniapp/newapp/assets/`.
    var NIV_ART_BASE = "/miniapp/assets/";
    var artUrl = file => (file ? NIV_ART_BASE + file : null);

    // As 11 ilustrações de reino que existem desde 2026-05-01 e que o servidor
    // nunca serviu até 2026-09-05.
    // ⚠️ São enfeite de landing REAPROVEITADO — palavras do próprio owner
    // ("eu fiz ela de teste mesmo"), registadas em `ARTE_PROVENIENCIA.md §1.1`.
    // Ficam aqui como caminho de `cultivador` OFF, e por mais nada.
    var REALM_ART_FILES = [
      "realm-mortal.webp", "realm-qi.webp", "realm-foundation.webp",
      "realm-core.webp", "realm-nascent-soul.webp", "realm-soul-transformation.webp",
      "realm-void-refinement.webp", "realm-body-integration.webp",
      "realm-mahayana.webp", "realm-tribulation.webp", "realm-true-immortal.webp",
    ];

    // ─── 坐 O CULTIVADOR (2026-09-07) ────────────────────────────────────────
    //
    // Os onze reinos, agora como LUGARES VAZIOS. A diferença não é de gosto:
    // as antigas têm PESSOAS lá dentro, e cada uma a fazer coisa diferente —
    // `realm-mortal` um viajante DE PÉ, `realm-core` a LEVITAR,
    // `void-refinement` COMBATE, `true-immortal` a VOAR (tabela peça a peça em
    // `newapp/README.md`, medida a 2026-09-05). Foi por isso que a cena do
    // Cultivo nunca pôde legendar a imagem: cinco das onze desmentiriam a frase
    // *"você está sentado"*, e a regra que ficou foi "a arte diz ONDE, o orbe
    // diz O QUÊ".
    //
    // Com o lugar VAZIO, a camada de cima passa a poder ser o JOGADOR sem que a
    // de baixo o contradiga. Duas camadas, duas responsabilidades:
    //   o reino diz ONDE · a figura diz QUEM · o efeito diz O QUÊ.
    //
    // ⚠️ Sufixo `-place` e não `-v2`: a rota `assets` serve com
    // `max-age=31536000, immutable`, portanto trocar o corpo por baixo de um
    // nome já servido deixaria quem tem a antiga em cache com ela para sempre
    // (`ARTE_PROVENIENCIA.md §2.5` — "regenerar = ficheiro NOVO").
    var REALM_PLACE_FILES = REALM_ART_FILES.map(f => f.replace(".webp", "-place.webp"));

    var realmArtUrl = (r, places) => artUrl(
      (places ? REALM_PLACE_FILES : REALM_ART_FILES)[Math.min(Math.max(r || 0, 0), 10)]);

    // A figura que substitui o orbe. TRÊS peças, não vinte e duas: assar a
    // figura dentro de cada reino custaria 11×2 e trancava — uma terceira opção
    // passaria a custar +11 em vez de +1.
    // ⚠️ `null`/desconhecido → 背影, a figura de costas. Não é um fallback
    // envergonhado: é o estado HONESTO de quem ainda não escolheu (os ~248 do
    // beta nascem com `gender` NULL), e a figura de costas é como a pintura
    // chinesa clássica retrata quem medita — genérica sem ser evasiva.
    var CULTIVATOR_ART = { male: "cultivator-male.webp", female: "cultivator-female.webp" };
    var cultivatorArtUrl = g => artUrl(CULTIVATOR_ART[g] || "cultivator-back.webp");

    // ─── A arte das PEÇAS (2026-09-06) ───────────────────────────────────────
    //
    // O nome do ficheiro **deriva** do nome do catálogo, mecanicamente. Não há
    // tabela de mapeamento à mão — e isso é desenho, não preguiça: com ~307
    // peças, uma tabela de 307 linhas escrita à mão diverge do catálogo no
    // primeiro rename e ninguém dá por isso. `scripts/gen_art.py` faz
    // EXACTAMENTE a mesma transformação ao gravar o ficheiro; se as duas um dia
    // discordarem, a carta cai no verso honesto em vez de partir.
    // ⚠️ 2026-09-15 — `.normalize("NFD")` + tirar os acentos NAO e' cosmetica:
    // e' a metade que faltava para esta funcao e a `slugify()` do `gen_art.py`
    // darem o MESMO slug. Em Python `"ú".isalnum()` e' True e o ficheiro nascia
    // `tech-yún-step-reborn.webp`; aqui `ú` nao casa `[a-z0-9]` e pedia-se
    // `tech-y-n-step-reborn`. Uma peca paga ficou invisivel por este caracter.
    // Com a dobra, ambos os lados dao `tech-yun-step-reborn`.
    var _artSlug = name => String(name || "")
      .normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    // ⚠️ `artifact: "art"` faltava, e era por isso que **51 peças de arte pagas
    // e indexadas não apareciam em lado nenhum do jogo** (registado no
    // `ARTE_PROVENIENCIA.md §1.4`): os ficheiros `art-*.webp` estavam no disco e
    // no índice abaixo, mas nenhum `pieceArt("artifact", …)` sabia construir o
    // slug. Arte fora do índice cai no verso em silêncio — e o verso é um estado
    // legítimo, portanto ninguém dava por isso.
    // ⚠️ 2026-09-14 — `boss` entrou aqui NO MESMO COMMIT em que as 9 peças
    // nasceram, e de propósito: este mapa e o `KIND_PREFIX` do `gen_art.py` são
    // as DUAS metades da mesma ligação, e foi por uma delas ter ficado para trás
    // que 51 peças pagas passaram meses invisíveis. Peça nova ⇒ as duas linhas
    // no mesmo lote, ou a arte cai no verso em silêncio.
    var ART_KIND_PREFIX = { technique: "tech", pill: "pill", beast: "beast",
                            artifact: "art", boss: "boss" };

    // ⚠️ O ÍNDICE do que existe. Sem ele, 307 cartas pediriam 307 URLs que dão
    // 404: o verso apanharia todas (Lei §1 cumprida) mas à custa de um pedido
    // por carta. Com ele, uma peça sem arte nem chega a tentar.
    // Actualizado por `gen_art.py --approve`; peça aprovada = linha aqui + linha
    // em `GameDesign/ARTE_PROVENIENCIA.md §1.2`.
    var NIV_ART_INDEX = new Set([
      "art-abyssal-exoskeleton", "art-ancient-copper-ring", "art-asura-s-cleaver",
      "art-azure-dragon-robe", "art-black-iron-sword", "art-blade-of-ten-thousand-virtues",
      "art-bloodweave-mantle", "art-celestial-aegis-plate", "art-celestial-arbiter-sword",
      "art-celestial-ascension-spear", "art-celestial-dao-ring", "art-celestial-empyrean-vestment",
      "art-celestial-karma-pendant", "art-celestial-sundering-blade", "art-dao-annihilation-lance",
      "art-dao-crown-fragment", "art-dao-immortal-vestment", "art-demonlord-s-fang",
      "art-divine-cosmic-blade", "art-divine-phoenix-cloak", "art-divine-star-earring",
      "art-earth-cleaver", "art-earth-core-plate", "art-earth-heart-amulet",
      "art-empyrean-holy-armor", "art-fanged-shadow-blade", "art-flaming-sword",
      "art-godslayer-s-eclipse", "art-halo-of-clarity", "art-heaven-guardian-mail",
      "art-heaven-s-edge", "art-heaven-warden-plate", "art-infernal-scale-mail",
      "art-iron-scale-vest", "art-jade-pendant", "art-mandate-of-heaven-ring",
      "art-mystic-tiger-fang", "art-nethervoid-warlord-armor", "art-purifier-s-blade",
      "art-radiant-silk-robe", "art-ring-of-the-blood-pact", "art-seraph-s-vestment",
      "art-skull-bone-talisman", "art-spirit-bead-bracelet", "art-spirit-dragon-ring",
      "art-spirit-emperor-robe", "art-spirit-severing-sword", "art-spirit-wind-blade",
      "art-spiritual-linen-tunic", "art-sword-of-the-morning-star", "art-void-eye-pendant",
      "beast-bamboo-panda", "beast-celestial-crane", "beast-chaos-dragon",
      "beast-crystal-spider", "beast-fire-fox", "beast-frost-bear",
      "beast-golden-carp", "beast-infernal-salamander", "beast-jade-turtle",
      "beast-phoenix-chick", "beast-river-serpent", "beast-shadow-wolf",
      "beast-storm-eagle", "beast-thunder-ox", "beast-wind-hawk",
      "boss-ancient-dragon", "boss-celestial-demon", "boss-corrupted-immortal",
      "boss-demonic-emperor", "boss-heaven-devouring-serpent", "boss-primordial-chaos-beast",
      "boss-shadow-wolf-alpha", "boss-void-beast", "boss-void-wraith",
      "pill-battle-fury-pill", "pill-body-refining-pill", "pill-breakthrough-pill",
      "pill-celestial-qi-pill", "pill-cleansing-pill", "pill-core-essence-pill",
      "pill-dao-comprehension-pill", "pill-eternal-foundation-pill", "pill-eternal-river-pill",
      "pill-fortune-pill", "pill-foundation-pill", "pill-foundation-repair-pill",
      "pill-greater-fortune-pill", "pill-greater-healing-pill", "pill-greater-mind-pill",
      "pill-greater-soul-pill", "pill-healing-pill", "pill-heaven-defying-pill",
      "pill-heavenly-qi-restoration-pill", "pill-heavenly-spring-pill", "pill-immortal-ascension-pill",
      "pill-iron-skin-pill", "pill-lucky-star-pill", "pill-mind-clarity-pill",
      "pill-minor-healing-pill", "pill-nascent-soul-pill", "pill-phoenix-rebirth-pill",
      "pill-qi-amass-pill", "pill-qi-condensation-pill", "pill-qi-gathering-pill",
      "pill-qi-vortex-pill", "pill-realm-insight-pill", "pill-soul-clarity-pill",
      "pill-soul-condensation-pill", "pill-soul-expansion-pill", "pill-soul-strength-pill",
      "pill-spirit-vein-pill", "pill-supreme-healing-pill", "pill-time-dilation-pill",
      "pill-transcendence-pill", "pill-void-cleansing-pill", "tech-absolute-defense",
      "tech-abyssal-annihilation", "tech-abyssal-grasp", "tech-anvil-of-the-standing-noon",
      "tech-ash-of-the-first-cauldron", "tech-ashen-mantle", "tech-avalanche-fist",
      "tech-azure-sword-form", "tech-bai-s-unwritten-cloud", "tech-beggar-s-palm",
      "tech-blood-frenzy", "tech-blood-night-devouring-art", "tech-blood-sutra",
      "tech-blooming-dao-heart", "tech-body-restoration", "tech-boundless-evasion",
      "tech-bulwark-of-devoured-souls", "tech-celestial-palm", "tech-cliffbreaker-fist",
      "tech-cloud-dragon-slash", "tech-cloud-step", "tech-cloudpiercer-thrust",
      "tech-covenant-of-the-drowned-elder", "tech-crucible-palm", "tech-death-without-sound",
      "tech-demon-mark", "tech-demonic-devourer", "tech-divine-finger",
      "tech-divine-judgment", "tech-dragon-fist", "tech-drifting-nimbus-veil",
      "tech-eagle-eye", "tech-edge-that-precedes-the-sound", "tech-ember-palm",
      "tech-eternal-glacier-body", "tech-eternal-strike", "tech-eternal-sun-dao",
      "tech-everfrost-bastion", "tech-flower-communion", "tech-forge-of-eternity",
      "tech-formless-zephyr-veil", "tech-fortune-s-favor", "tech-frost-guard",
      "tech-frost-shield", "tech-frost-that-seeps-through-iron", "tech-frozen-heart-dao",
      "tech-garden-of-ten-thousand-turnings", "tech-glacial-shell", "tech-glacier-that-remembers-the-sea",
      "tech-granite-hide-tempering", "tech-harmony-of-ten-thousand", "tech-heaven-cloud-severance",
      "tech-heaven-rend", "tech-heaven-s-mandate", "tech-heavenly-root-technique",
      "tech-hollow-breeze-piercer", "tech-hundred-herb-body", "tech-hunger-of-the-deep",
      "tech-iron-body", "tech-iron-fist-basics", "tech-iron-will",
      "tech-jade-formation", "tech-jade-shield", "tech-last-breath",
      "tech-last-thunder", "tech-lotus-of-rebirth", "tech-mercy-pulse",
      "tech-mercy-that-outlasts-the-sword", "tech-molten-dawn-guard", "tech-mountain-heart-dao",
      "tech-mountain-stance", "tech-name-erased-from-the-wind", "tech-nine-deaths-one-breath",
      "tech-nine-mountains-body", "tech-nine-transformations-body", "tech-ninefold-cloud-aegis",
      "tech-ninth-refinement-blaze", "tech-nirvana-rebirth-flame", "tech-peak-sundering-seal",
      "tech-petalfall-evasion", "tech-phoenix-flame-body", "tech-phoenix-strike",
      "tech-pill-beyond-tribulation", "tech-pill-emperor-s-touch", "tech-pill-furnace-cataclysm",
      "tech-radiant-guard", "tech-shadow-step", "tech-silent-shadow-step",
      "tech-sky-severing-cloud-decree", "tech-smelting-ray-fist", "tech-snowdrift-step",
      "tech-solar-flare-fist", "tech-soul-devourer", "tech-soul-eater",
      "tech-soul-fire", "tech-soul-gathering", "tech-soul-rend",
      "tech-sovereign-of-the-abyss", "tech-spirit-garden", "tech-spring-of-ten-thousand-blooms",
      "tech-still-water-piercing-art", "tech-storm-fist", "tech-sun-strike",
      "tech-sunfire-body", "tech-ten-thousand-catty-descent", "tech-the-abyss-wears-your-name",
      "tech-the-peak-answers-only-once", "tech-the-seed-kept-from-every-harvest", "tech-the-sun-sets-for-no-house-but-ours",
      "tech-thorn-vine-lash", "tech-thunder-step", "tech-tranquil-mind",
      "tech-umbral-tide-drift", "tech-unbroken-jade-accord", "tech-undying-fortress",
      "tech-veil-of-a-hundred-petals", "tech-void-slash", "tech-void-walk",
      "tech-what-the-abyss-kept-for-its-heir", "tech-whispering-gale-edge", "tech-willow-branch-lash",
      "tech-wind-walk", "tech-wind-walk-art", "tech-windless-assassination",
      "tech-winter-s-silence", "tech-winter-without-thaw", "tech-withering-pollen-dao",
      "tech-yun-step-reborn", "tech-zenith-supernova-fist",
    ]);

    // → URL da arte da peça, ou `null` (⇒ o verso honesto).
    // 🔴 `artKey` NÃO é um extra — é o que faz a arte existir fora do inglês.
    //
    // O slug da peça deriva do NOME. Enquanto o payload mandava o nome canónico
    // isso bastava; desde que ele passou a vir TRADUZIDO, o slug muda e a peça
    // deixa de ser encontrada — sem erro, sem log, só a carta virada ao verso
    // (que é um estado legítimo, e por isso ninguém dá por ela).
    //
    //     "Void Beast"       → boss-void-beast        ✅ está no índice
    //     "Besta do Vazio"   → boss-besta-do-vazio    ❌ não está
    //     "Bestia del Vacío" → boss-bestia-del-vac-o  ❌ não está
    //
    // MEDIDO a 2026-09-14: **229 peças por língua** (128 técnicas · 51
    // artefactos · 41 pílulas · 9 chefes) invisíveis em `pt` e `es`, zero em
    // `en`. E as 128 técnicas já estavam assim **em produção desde 2026-09-08**.
    //
    // A regra: **o nome é para LER, a chave é para ENCONTRAR.** O servidor manda
    // `art_key` (o nome canónico) ao lado de cada nome traduzido.
    function pieceArt(kind, name, artKey) {
      const pre = ART_KIND_PREFIX[kind];
      const key = artKey || name;
      if (!pre || !key) return null;
      const slug = pre + "-" + _artSlug(key);
      return NIV_ART_INDEX.has(slug) ? artUrl(slug + ".webp") : null;
    }

    // 朱砂 — o carimbo. Ver §3 do cabeçalho.
    function SealMark({ size = 22, title }) {
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" role="img"
             aria-label={title || undefined} focusable="false"
             style={{ transform: "rotate(-5deg)", flexShrink: 0,
                      filter: "drop-shadow(0 1px 2px rgba(0,0,0,.55))" }}>
          <rect x="1.2" y="1.2" width="21.6" height="21.6" rx="2.6"
                fill={cssHex("var(--seal)", "#c8442f")} fillOpacity=".93" />
          {/* 白文 — a marca é o VAZIO na tinta, não um traço por cima dela. */}
          <g stroke={cssHex("var(--bg)", "#0b0a0c")} strokeWidth="1.7"
             strokeLinecap="square" fill="none" opacity=".82">
            <path d="M6 7.2 H18" />
            <path d="M8.8 7.2 V18" />
            <path d="M15.2 7.2 V18" />
            <path d="M8.8 12.4 H15.2" />
            <path d="M6 18 H18" />
          </g>
        </svg>
      );
    }

    // 品 — o lombo contado. `aria-hidden`: a leitura em palavras vive na
    // sobrancelha ("COMBATE · APERFEIÇOADA"), e repetir aqui só duplicaria.
    // ⚠️ `tier` (器, 2026-09-10) chega SÓ com a flag `item_vivo` ligada; sem ela
    // é `undefined` e cada entalhe desenha o mesmo `style` de 05/09, chave a
    // chave. "O lombo acende" é a metade *notável* do ornamento — a mesma
    // medida, mais luz. A largura NÃO muda: engrossar o lombo mexeria na
    // composição da carta, e o patamar tem de se sentir, não de empurrar.
    function RankSpine({ rank, tier }) {
      if (!rank) return null;
      const lit = tier === "celestial"
        ? { on: "linear-gradient(180deg,rgba(var(--gold3-rgb),1),rgba(var(--gold2-rgb),.85))",
            glow: "0 0 8px rgba(var(--gold3-rgb),.75)" }
        : tier === "notable"
        ? { on: "linear-gradient(180deg,rgba(var(--gold2-rgb),1),rgba(var(--gold-rgb),.85))",
            glow: "0 0 6px rgba(var(--gold2-rgb),.5)" }
        : null;
      const marks = [];
      for (let k = 0; k < rank.n; k++) {
        const on = k <= rank.i;
        marks.push(
          <i key={k} style={{
            display: "block", flex: 1, minHeight: 2, borderRadius: .5,
            background: on
              ? (lit ? lit.on
                     : "linear-gradient(180deg,rgba(var(--gold2-rgb),.95),rgba(var(--gold-rgb),.7))")
              : "rgba(var(--gold-rgb),.13)",
            boxShadow: on ? (lit ? lit.glow : "0 0 4px rgba(var(--gold-rgb),.3)") : "none",
          }} />
        );
      }
      return (
        <div aria-hidden="true" style={{
          position: "absolute", left: 5, top: 8, bottom: 8, width: 3,
          display: "flex", flexDirection: "column", gap: 3, zIndex: 2,
        }}>{marks}</div>
      );
    }

    // A chapa de arte + o VERSO. Ver §2 do cabeçalho.
    //
    // ⚠️ 2026-09-08 — o MODAL usa a MESMA chapa, por props (`aspect`,
    // `glyphSize`, `focus`), nunca um segundo componente. O owner fotografou o
    // `BeastDetailModal` a mostrar um emoji ⚡ gigante no sítio onde a
    // ilustração devia estar — e a arte da Thunder Ox existia, estava a ser
    // servida, e aparecia no cartão POR TRÁS do próprio modal. Bifurcar a chapa
    // faria com que o verso honesto, o `onError` e o `lazy` tivessem de ser
    // corrigidos em dois sítios; um deles ficaria para trás.
    //
    // `focus` existe porque o corte muda: a arte foi gerada 4:3 com "the lower
    // third intentionally empty" (ARTE_PROVENIENCIA §3.2). Num recorte mais
    // largo, `cover` comeria headroom em cima E vazio em baixo, meio a meio —
    // puxar o foco para cima come o vazio, que é o que lá está para ser comido.
    // ⚠️ `dissolve` (器, 2026-09-10): a altura, em %, a que o pé da arte começa a
    // dissolver-se na carta. `undefined` ⇒ a rampa literal de 05/09, byte a
    // byte — e é por isso que o ramo por omissão é uma STRING inteira e não uma
    // conta: `42 + (100-42)*.55` dá **73.9**, não 74, e uma casa decimal a mais
    // já é um DOM diferente. É assim que o patamar *celeste* faz a arte
    // "sangrar": dissolvendo-se 16 pontos mais cedo, a ilustração deixa de ter
    // chapa e passa a SER a carta.
    // ⚠️ `fill` (武 2.2, 2026-09-23) — a chapa ENCHE o pai em vez de se medir
    // por proporção. Existe porque a cena do combate precisa de uma altura FIXA
    // (62–96px, a medida que o Astra deu para a arte ser reconhecível antes da
    // escolha) e não de uma razão de aspecto — a largura dela vem da coluna.
    //
    // 🔴 E entra AQUI, no dono, porque a guarda F-7 (B) me apanhou a escrever
    // uma SEXTA chapa. Ela existe porque o verso honesto já se duplicou três
    // vezes nesta casa. Um prop novo no dono é barato; um segundo desenhador
    // custa a mesma correcção duas vezes, e a segunda esquece-se.
    function CardArt({ src, glyph, accent, dim, aspect, glyphSize, focus, dissolve, fill }) {
      const [failed, setFailed] = useState(false);
      const [loaded, setLoaded] = useState(false);
      useEffect(() => { setFailed(false); setLoaded(false); }, [src]);
      const hex = cssHex(accent || "var(--gold)", "#c9903a");
      return (
        <div style={{
          position: "relative", width: "100%",
          ...(fill ? { height: "100%" } : { aspectRatio: aspect || "4 / 3" }),
          overflow: "hidden",
          // O verso: anéis de tinta a partir do centro. Não é textura por
          // textura — é a ondulação de qi na água, que é o que uma peça
          // guardada num anel espacial parece antes de se olhar para ela.
          background:
            "radial-gradient(circle at 50% 46%, " + hex + "1f, transparent 60%)," +
            "repeating-radial-gradient(circle at 50% 46%, transparent 0 8px, " + hex + "0e 8px 9px)," +
            "linear-gradient(180deg, rgba(var(--surface-rgb),.92), rgb(var(--card-rgb)))",
          filter: dim ? "grayscale(.75) brightness(.6)" : undefined,
        }}>
          <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>
            <span aria-hidden="true" style={{
              fontSize: glyphSize || 40, lineHeight: 1, opacity: .34,
              filter: "drop-shadow(0 0 12px " + hex + "66)",
            }}>{glyph || "◈"}</span>
          </div>
          {src && !failed && (
            <img src={src} alt="" loading="lazy" decoding="async"
                 onError={() => setFailed(true)} onLoad={() => setLoaded(true)}
                 style={{
                   position: "absolute", inset: 0, width: "100%", height: "100%",
                   objectFit: "cover", objectPosition: focus || undefined,
                   display: "block",
                   opacity: loaded ? 1 : 0, transition: "opacity .45s ease",
                 }} />
          )}
          {/* O pé da arte DISSOLVE-SE na carta. Uma moldura à volta da
              ilustração faria dela um anexo; sem linha dura, ela É a carta. */}
          <div aria-hidden="true" style={{
            position: "absolute", inset: 0, pointerEvents: "none",
            background: dissolve == null
              ? "linear-gradient(180deg,transparent 42%," +
                "rgba(var(--card-rgb),.5) 74%,rgb(var(--card-rgb)) 100%)"
              : "linear-gradient(180deg,transparent " + dissolve + "%," +
                "rgba(var(--card-rgb),.5) " + Math.round(dissolve + (100 - dissolve) * .55) +
                "%,rgb(var(--card-rgb)) 100%)",
          }} />
        </div>
      );
    }

    // 大牌 O HERÓI DO MODAL — a peça com a página inteira só para ela.
    //
    // Porque existe (owner, foto de 2026-09-06): o modal é o único sítio onde a
    // peça não divide o ecrã com nada, e era o único onde a arte NÃO aparecia.
    // Aqui a ilustração é MAIOR, não ausente.
    //
    // ⚠️ Sangra para fora do `padding:14px` do corpo do modal (`margin:-14px`).
    // Uma chapa com goteira de 14px à volta seria uma moldura — exactamente o
    // que a carta passou 05/09 a tirar. A arte encosta ao vidro.
    // ⚠️ `subtitle` é o sítio da linha que hoje vive ao lado do emoji gigante
    // (posto · nível · elemento). Fica POR CIMA do pé dissolvido, que é escuro
    // por construção — nenhuma peça precisa de caixa por baixo do texto.
    // ⚠️ `bleed` (器, 2026-09-10): a goteira do corpo do modal que a chapa tem
    // de comer para encostar ao vidro. O `Modal` da casa tem `padding:14`; o
    // `DetailModal` da mochila é feito à mão e tem **18**. Um valor assado em
    // 14 deixaria uma tira de 4px do fundo do modal à volta da arte — que é
    // exactamente a moldura que este componente existe para não ter.
    // `radius` existe pela mesma razão: o painel da mochila tem cantos de 14 e
    // uma chapa de cantos rectos passaria por FORA deles.
    // ⚠️ Ambos `undefined` ⇒ o markup de 08/09, byte a byte (`-14px -14px 12px`,
    // sem `borderRadius`) — é o que mantém o modal da BESTA intocado.
    function PieceHero({ src, glyph, accent, title, subtitle, seal, sealLabel,
                         dim, aspect, bleed, radius, children }) {
      const b = bleed == null ? 14 : bleed;
      return (
        <div style={{ position: "relative", margin: "-" + b + "px -" + b + "px 12px",
                      overflow: "hidden",
                      ...(radius ? { borderRadius: radius } : {}) }}>
          <CardArt src={src} glyph={glyph} accent={accent} dim={dim}
                   aspect={aspect || "16 / 10"} glyphSize={64} focus="50% 38%" />
          <div style={{
            position: "absolute", left: b, right: b, bottom: 9,
            display: "flex", alignItems: "flex-end", gap: 8,
            justifyContent: "space-between", pointerEvents: "none",
          }}>
            <div style={{ minWidth: 0 }}>
              {title && (
                <div style={{
                  fontFamily: "'Cormorant Garamond',Georgia,serif", fontWeight: 600,
                  fontSize: 21, lineHeight: 1.1, color: "var(--text)",
                  textShadow: "0 2px 10px rgba(0,0,0,.85)", overflowWrap: "anywhere",
                }}>{title}</div>
              )}
              {subtitle && (
                <div style={{
                  fontFamily: "'Cinzel',serif", fontSize: 9.5, letterSpacing: ".13em",
                  textTransform: "uppercase", color: "var(--gold2)", marginTop: 3,
                  textShadow: "0 1px 6px rgba(0,0,0,.9)", lineHeight: 1.4,
                }}>{subtitle}</div>
              )}
            </div>
            {seal && <SealMark size={24} title={sealLabel || undefined} />}
          </div>
          {children}
        </div>
      );
    }

    // 器 O ORNAMENTO — o que cada patamar acrescenta, e nada mais.
    //
    // ⚠️ O ornamento é o MESMO em todas as oito famílias, e isso é a decisão
    // inteira. A `GRADE_VISUALS` tem nove cores e elas JÁ entram na carta pelo
    // `accent` (a tinta do verso, o halo do glifo). Se o patamar TAMBÉM pintasse
    // por grau, o código de cores voltava por uma porta lateral — nove
    // aparências —, e a decisão de 05/09 morria sem ninguém a ter reaberto.
    // Aqui há três aparências e elas não dizem QUAL grau: dizem QUÃO ALTO.
    //
    // notável  — o contorno ganha TEMPERATURA e o lombo acende. Mais nada: tem
    //   de se dar conta sem parar para olhar. O segundo fio a 1px é a moldura
    //   dupla de um volume encadernado — a mesma gramática do lombo.
    // celeste  — moldura própria (o esquadro dos cantos), brilho para FORA, e a
    //   arte sangra (o pé dissolve-se 16 pontos mais cedo).
    var NIV_TIER_ORN = {
      common: null,
      notable: {
        edgeRgb: "var(--gold2-rgb)", edge: ".44",
        shadow: "0 0 0 1px rgba(var(--gold-rgb),.10)",
        dissolve: 42, corners: false,
      },
      celestial: {
        edgeRgb: "var(--gold3-rgb)", edge: ".62",
        shadow: "0 0 0 1px rgba(var(--gold3-rgb),.16), 0 0 22px -7px rgba(var(--gold3-rgb),.55)",
        dissolve: 26, corners: true,
      },
    };

    function itemVivoOn() {
      return typeof featureEnabled === "function" && featureEnabled("item_vivo");
    }

    // 角花 — o esquadro dos cantos, e só no patamar CELESTE.
    // ⚠️ DOIS cantos, não quatro: o inferior direito já tem a diagonal
    // chanfrada que é a silhueta da carta desde 05/09 (e o `clipPath` cortaria
    // um esquadro lá), e o inferior esquerdo é onde o lombo acaba. Dois
    // esquadros EMOLDURAM a arte; quatro fariam uma caixa — e a carta passou
    // 05/09 inteiro a fugir de caixas.
    function TierCorners() {
      const c = "rgba(var(--gold3-rgb),.55)";
      return (
        <div aria-hidden="true" style={{
          position: "absolute", inset: 0, zIndex: 3, pointerEvents: "none",
        }}>
          <i style={{ position: "absolute", left: 4, top: 4, width: 11, height: 1, background: c }} />
          <i style={{ position: "absolute", left: 4, top: 4, width: 1, height: 11, background: c }} />
          <i style={{ position: "absolute", right: 4, top: 4, width: 11, height: 1, background: c }} />
          <i style={{ position: "absolute", right: 4, top: 4, width: 1, height: 11, background: c }} />
        </div>
      );
    }

    // 器 A FACE DA PECA (2026-09-10) — a resposta ao report do owner:
    // *"imagens nao aparecem de espadas algumas vezes sim e outras nao, ainda
    // usam icones do proprio emoji. tem que fixar isso. funcionar em tudo."*
    //
    // ⚠️ E ELE TEM RAZAO, E A CAUSA E' ESTRUTURAL — nao e' arte em falta.
    // MEDIDO a 2026-09-10: as quatro familias estao COMPLETAS no indice
    // (artefacto 51/51 · pilula 41/41 · besta 15/15 · tecnica 128), e mesmo
    // assim so' **12 pontos** de todo o cliente pediam `pieceArt(...)`. Todas as
    // outras telas onde uma peca aparece — a Forja, o Atelie, o encanto, o
    // refino, o mercado, a troca, o perfil, o detalhe da tecnica, a receita da
    // pilula — desenhavam um `<div style={{fontSize:38}}>{a.emoji}</div>` a
    // mao. Nao havia componente nenhum que respondesse "mostra-me esta peca":
    // havia doze ligacoes manuais e cem telas que nunca foram ligadas.
    //
    // ⇒ Uma peca passa a ter UMA cara, e ela vive aqui. Onde houver `kind` +
    // `name`, ha' arte; onde nao houver arte, ha' o VERSO honesto com o emoji
    // do catalogo por cima — que e' exactamente o que a tela ja' mostrava, e
    // portanto nada piora nunca.
    //
    // ⚠️ Por dentro e' o MESMO `CardArt`, nao uma segunda chapa. A licao ja'
    // custou este defeito uma vez: a correccao de 07/09 fez um caminho proprio
    // para as bestas e o artefacto e a pilula ficaram tres dias para tras.
    // `dissolve={100}` desliga o pe dissolvido (a rampa fica `transparent 100%`)
    // — num quadrado de 40px o degrade comeria a peca inteira.
    function PieceIcon({ kind, name, artKey, emoji, size = 40, accent, dim, radius = 8,
                         style, title }) {
      return (
        <div title={title || undefined} style={{
          width: size, height: size, flexShrink: 0, borderRadius: radius,
          overflow: "hidden", ...style,
        }}>
          <CardArt src={pieceArt(kind, name, artKey)} glyph={emoji} accent={accent}
                   dim={dim} aspect="1 / 1" glyphSize={Math.round(size * .52)}
                   focus="50% 42%" dissolve={100} />
        </div>
      );
    }

    var NIV_CARD_STATES = { active: 1, owned: 1, locked: 1, unowned: 1 };

    function NivraelCard({
      name, glyph, art, accent,
      kind, rank,            // → lombo + a palavra do grau
      eyebrow,               // o tipo ("COMBATE", "PÍLULA", "BESTA")
      effect,                // uma linha: o que faz
      note,                  // ⚠️ Lei §1 — PORQUÊ está trancada/indisponível
      foot,                  // o pé: custo, nível, o que o conteúdo pedir
      body,                  // extra sob o efeito (barra de XP, ingredientes…)
      actions,               // botões, no fundo
      state = "owned",
      stateLabel,            // a palavra do estado ("EQUIPADA", "COMPANHEIRA")
      // 朱砂 — ⚠️ 2026-09-08, corrigido a OLHAR, e é uma correcção de DESENHO,
      // não de código. O selo marcava o estado `active` sempre, e a mecânica
      // dizia que "uma vez por página, nunca duas" se cumpria sozinha porque se
      // equipam poucas artes e há UM companheiro. A mochila derrubou isso na
      // primeira tela: equipam-se **quatro** artefactos, e a secção EQUIPADO
      // mostrava quatro carimbos de cinábrio de uma vez. Quatro deixam de ser um
      // acento e passam a ser um padrão — e o cinábrio deixa de querer dizer
      // alguma coisa.
      // A regra que fica: **o selo distingue, e só distingue onde há do que
      // distinguir.** Numa lista MISTA (artes possuídas, das quais 2 estão
      // equipadas) o selo é a resposta a "qual delas?". Numa lista em que TODAS
      // estão activas — e cujo cabeçalho já diz "EQUIPADO 3/4" — não há pergunta
      // nenhuma, e o selo é ruído. Esses sítios passam `seal={false}`.
      seal,
      onClick, style,
    }) {
      const st = NIV_CARD_STATES[state] ? state : "owned";
      const isActive = st === "active";
      const showSeal = seal === undefined ? isActive : !!seal;
      const isLocked = st === "locked";
      const isGhost = st === "unowned";
      const r = nivRank(kind, rank);
      const topGrade = !!r && r.i === r.n - 1;
      const acc = accent || "var(--gold)";
      const edge = isActive ? ".46" : isGhost ? ".12" : ".2";
      // 器 2026-09-10 — o ornamento do patamar. Com `item_vivo` OFF é `null` e
      // cada `style` abaixo escreve a mesma chave com o mesmo valor de 05/09.
      // ⚠️ `isGhost` fica de FORA de propósito: um fantasma é uma entrada de
      // catálogo que o jogador não tem, e fazê-la brilhar é publicidade, não
      // informação. Um `locked` MANTÉM o ornamento — a arte celestial que ainda
      // não se pode aprender continua a ser celestial, e dizê-lo é Lei §1
      // (mostrar o caminho), não provocação.
      const orn = (!isGhost && itemVivoOn()) ? NIV_TIER_ORN[nivTier(r)] : null;
      return (
        <div onClick={onClick} style={{
          position: "relative",
          display: "flex", flexDirection: "column",
          background: "rgb(var(--card-rgb))",
          border: "1px solid rgba(" + (orn ? orn.edgeRgb : "var(--gold-rgb)") + "," +
                  (orn ? orn.edge : edge) + ")",
          ...(orn ? { boxShadow: orn.shadow } : {}),
          borderRadius: 4,
          // O canto chanfrado — a silhueta da carta. `clipPath` não desenha
          // borda na diagonal; o fio dela é o <i> no fim deste componente.
          clipPath: "polygon(0 0, 100% 0, 100% calc(100% - 11px), calc(100% - 11px) 100%, 0 100%)",
          opacity: isGhost ? .62 : 1,
          overflow: "hidden",
          cursor: onClick ? "pointer" : undefined,
          animation: "fade-up .35s ease",
          ...style,
        }}>
          <RankSpine rank={r} tier={orn ? nivTier(r) : undefined} />
          {orn && orn.corners && <TierCorners />}

          <div style={{ position: "relative" }}>
            <CardArt src={art} glyph={glyph} accent={acc} dim={isLocked || isGhost}
                     dissolve={orn ? orn.dissolve : undefined} />
            {/* A tira do pé da arte: o estado à esquerda, o selo à direita.
                É onde as duas marcas se encontram, e só existe quando há
                alguma coisa verdadeira para pôr lá. */}
            {(stateLabel || showSeal) && (
              <div style={{
                position: "absolute", left: 11, right: 8, bottom: 6,
                display: "flex", alignItems: "flex-end", gap: 6,
                justifyContent: "space-between", pointerEvents: "none",
              }}>
                {stateLabel ? (
                  <span style={{
                    fontFamily: "'Cinzel',serif", fontSize: 8.5, letterSpacing: ".14em",
                    textTransform: "uppercase", padding: "2px 6px", borderRadius: 2,
                    background: "rgba(0,0,0,.55)",
                    color: isActive ? "var(--jade)" : isLocked ? "var(--muted)" : "var(--gold2)",
                    border: "1px solid " + (isActive ? "rgba(var(--jade-rgb),.4)" : "rgba(var(--gold-rgb),.22)"),
                  }}>{isLocked ? "\u{1F512} " + stateLabel : stateLabel}</span>
                ) : <span />}
                {showSeal && <SealMark size={19} title={stateLabel || undefined} />}
              </div>
            )}
          </div>

          <div style={{ padding: "9px 11px 10px 13px", flex: 1,
                        display: "flex", flexDirection: "column" }}>
            {/* ⚠️ OLHAR corrigiu isto (2026-09-05): com um separador " · " a
                colar as duas palavras, "COMBATE · TRANSCENDENTE" a 164px
                partia a linha DEIXANDO O PONTO ÓRFÃO no fim da primeira. Uma
                fila com quebra e espaço próprio quebra onde deve e nunca deixa
                pontuação pendurada. `wordBreak:"keep-all"` porque a palavra do
                grau nunca se parte a meio — é um nome. */}
            {(eyebrow || r) && (
              <div style={{
                display: "flex", flexWrap: "wrap", columnGap: 6, rowGap: 1,
                fontFamily: "'Cinzel',serif", fontSize: 8.5, letterSpacing: ".13em",
                textTransform: "uppercase", color: "var(--muted2)", lineHeight: 1.35,
                wordBreak: "keep-all",
              }}>
                {eyebrow && <span>{eyebrow}</span>}
                {r && <span style={{ color: topGrade ? "var(--gold3)" : "var(--gold2)" }}>{r.label}</span>}
              </div>
            )}

            <div style={{
              fontFamily: "'Cormorant Garamond',Georgia,serif", fontWeight: 600,
              fontSize: 17, lineHeight: 1.14, marginTop: 3,
              color: isGhost ? "var(--muted)" : "var(--text)",
              overflowWrap: "anywhere",
            }}>{name}</div>

            {/* a ÚNICA régua dentro da carta */}
            <i aria-hidden="true" style={{
              display: "block", width: 22, height: 1, margin: "7px 0 6px",
              background: "rgba(var(--gold-rgb)," + (isGhost ? ".25" : ".5") + ")",
            }} />

            {effect != null && effect !== "" && (
              <div style={{ fontSize: 11.5, lineHeight: 1.45, color: "var(--muted)",
                            overflowWrap: "anywhere" }}>{effect}</div>
            )}
            {note && (
              <div style={{ fontSize: 10.5, lineHeight: 1.4, marginTop: 5,
                            color: "var(--warn)", overflowWrap: "anywhere" }}>{note}</div>
            )}
            {body && <div style={{ marginTop: 8 }}>{body}</div>}

            {foot != null && foot !== "" && (
              <div style={{
                marginTop: "auto", paddingTop: 9, fontSize: 10.5,
                color: "var(--muted2)", display: "flex", alignItems: "center",
                justifyContent: "space-between", gap: 6, flexWrap: "wrap",
              }}>{foot}</div>
            )}
            {actions && <div style={{ marginTop: 9 }}>{actions}</div>}
          </div>

          {/* o fio da diagonal — a borda que o clipPath não desenha */}
          <i aria-hidden="true" style={{
            position: "absolute", right: -4, bottom: 3, width: 20, height: 1,
            background: "rgba(var(--gold-rgb)," + edge + ")",
            transform: "rotate(-45deg)", transformOrigin: "center", pointerEvents: "none",
          }} />
        </div>
      );
    }

    // A grelha das cartas. `auto-fill` põe MAIS cartas por linha num ecrã
    // largo, nunca cartas maiores — a lição dos quadrados de 514×514 que a
    // WEB-D teve de desfazer. `min` é o que decide 2 colunas a 390px.
    function CardGrid({ children, min = 158, gap = 9, style }) {
      return (
        <div style={{
          display: "grid", gap,
          gridTemplateColumns: "repeat(auto-fill,minmax(" + min + "px,1fr))",
          ...style,
        }}>{children}</div>
      );
    }

    // ═══ §2.1 — TIRAR A MOLDURA A QUEM HOSPEDA A CARTA (2026-09-08) ══════════
    //
    // O passo mais barato do lote e o que mais muda o que se vê. Uma grelha de
    // cartas vivia dentro de um `<Card>` de secção — gradiente, borda dourada,
    // raio 10, fio no topo, cantos ornamentados, trama — e a de fora é
    // exactamente a moldura de dashboard de que a carta passou 05/09 a fugir.
    // Moldura dentro de moldura, e a de fora ganha sempre: ela é maior.
    //
    // Com `cartas` ON, um painel que hospeda cartas passa a ser **um título
    // tipográfico e espaço**. Sem caixa. Com a flag OFF é o `<Card>` de hoje,
    // com o `CardTitle` de hoje, byte a byte.
    //
    // ⚠️ Isto NÃO é "converter `<Card>` em carta". Um aviso, um painel de
    // estatísticas e um cabeçalho continuam `<Card>` — o que muda aqui é só
    // quem tem cartas lá dentro. Converter um aviso seria o erro simétrico.
    //
    // ⚠️ O ritmo vertical passa a ser feito por ESPAÇO, não por borda. Se as
    // cartas parecerem flutuar, a resposta é espaçamento, nunca devolver a
    // moldura — foi assim que o jogo ficou com 417 caixas iguais.
    function CardHost({ cards, title, right, children, style }) {
      if (!cards) {
        return (
          <Card style={style}>
            {(title != null || right != null) && <CardTitle left={title} right={right} />}
            {children}
          </Card>
        );
      }
      return (
        <div style={{ marginBottom: 18, animation: "fade-up .35s ease", ...style }}>
          {(title != null || right != null) && (
            <div style={{
              display: "flex", alignItems: "baseline", justifyContent: "space-between",
              gap: 8, margin: "0 2px 9px",
            }}>
              <span style={{
                fontFamily: "'Cinzel',serif", fontSize: 11, letterSpacing: ".16em",
                textTransform: "uppercase", color: "rgba(var(--gold-rgb),.8)",
              }}>{title}</span>
              {right != null && (
                <span style={{
                  fontFamily: "'Cinzel',serif", fontSize: 10.5, color: "var(--muted2)",
                }}>{right}</span>
              )}
            </div>
          )}
          {children}
        </div>
      );
    }

    // O irmão do `CardHost` para quem já escreve o seu próprio cabeçalho: só
    // troca a CAIXA por espaço, e deixa os filhos exactamente como estão.
    // ⚠️ Com `cards` falso devolve o `<Card>` com as MESMAS props — o `style`
    // que o chamador passava continua a chegar lá, intocado.
    function CardShell({ cards, children, style, ornate }) {
      if (!cards) return <Card style={style} ornate={ornate}>{children}</Card>;
      // Só o espaçamento sobrevive: o `padding` de uma moldura que já não
      // existe encolheria a grelha para dentro de uma margem invisível.
      return (
        <div style={{ marginBottom: 18, animation: "fade-up .35s ease" }}>{children}</div>
      );
    }

    function StatGrid({ stats }) {
      return (
        <div style={{ display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:7 }}>
          {stats.map((s, i) => (
            <div key={i} style={{
              background:"rgba(0,0,0,.35)",
              border:"1px solid rgba(var(--gold-rgb),.12)",
              borderRadius:7, padding:"8px 10px",
              position:"relative", overflow:"hidden",
            }}>
              <div style={{ position:"absolute", top:0, left:0, right:0, height:1,
                background:"linear-gradient(90deg,transparent,rgba(var(--gold-rgb),.2),transparent)" }} />
              <div style={{ fontSize:9.5, color:"rgba(var(--muted-rgb),.85)", textTransform:"uppercase", letterSpacing:.8 }}>{s.label}</div>
              <div style={{ fontSize:14, fontWeight:600, marginTop:3, color: s.color || "var(--text)" }}>
                {s.value}{s.sub && <small style={{ color:"var(--muted)", fontSize:10.5, fontWeight:400 }}> {s.sub}</small>}
              </div>
            </div>
          ))}
        </div>
      );
    }
    // `bare` (WEB-E 坐): o mesmo gradiente, sem moldura dourada e sem o brilho
    // superior — o "fio de tinta" da cena do Cultivo. É uma OPÇÃO deste
    // componente e não uma segunda barra de propósito: as três cores vivem numa
    // só casa, e uma paleta nova não pode aquecer uma barra e esquecer a outra.
    function ProgressBar({ pct, variant="cult", height=8, bare=false, over=false }) {
      const grad = {
        cult:"linear-gradient(90deg,#a06020,var(--gold),var(--gold2))",
        qi:  "linear-gradient(90deg,#1e7a9e,#4cc4ff,#7be3ff)",
        hp:  "linear-gradient(90deg,#7f1d1d,#dc2626,var(--red2))",
      }[variant];
      return (
        <div style={{
          width:"100%", height, background:"rgba(0,0,0,.5)", borderRadius:height/2,
          overflow:"hidden", position:"relative",
          border: bare ? "none" : "1px solid rgba(var(--gold-rgb),.18)",
        }}>
          <div style={{
            height:"100%", borderRadius:height/2, transition:"width .4s ease",
            width: Math.min(100, Math.max(0, pct)) + "%", background: grad, position:"relative",
          }}>
            {!bare && (
              <div style={{
                position:"absolute", top:0, left:0, right:0, height:"50%",
                background:"rgba(255,255,255,.15)", borderRadius:height/2,
              }} />
            )}
          </div>
          {/* 坐 ONDA 1 — a MARCA TERMINAL do transbordo. Aditiva: `over` é
              `false` por omissão, portanto os 14 usos de hoje desenham o mesmo
              markup, byte a byte. Existe porque o Qi de um jogador REAL mede-se
              **2,08× acima da capacidade** — uma barra que só sabe encher até
              100% apaga exactamente o facto que vale a pena dizer. O número
              continua a ser o total real; quem explica é a frase por baixo. */}
          {over && (
            <div aria-hidden="true" style={{
              position:"absolute", top:-1, bottom:-1, right:0, width:3,
              background:"var(--gold2)", borderRadius:1,
              boxShadow:"0 0 6px rgba(var(--gold2-rgb),.9)",
            }} />
          )}
        </div>
      );
    }
    // 🩸 A RECUSA QUE DIZ O CAMINHO — UM DONO (2026-09-13).
    //
    // Medido: o mini-app tinha QUATRO recusas de Vitalidade e duas delas
    // mandavam o jogador **ESPERAR** ("HP em zero. Espere regenerar antes de
    // lutar."), enquanto o CHAT, na mesmíssima recusa, dizia desde sempre a
    // coisa certa: *"Medite ou use uma Pílula de Cura"* (`hp_too_low_combat`).
    // Duas superfícies, a mesma recusa, conselhos opostos — e a que fica com o
    // errado é a **canónica**.
    //
    // E "esperar" não é só vago, é o caminho mais lento dos três, medido no
    // motor:
    //     passiva ........ 0,1%/min, e só dentro do `cultivation_tick`, que
    //                      salta quem esteve offline mais de 4h
    //                      ⇒ tecto ~24% do máximo POR VISITA
    //     meditação leve . 1%/min · 30 min · DE GRAÇA        ⇒ +30%
    //     meditação prof.  5%/min · 50 qi                    ⇒ CHEIO em 20 min
    //     Pílula de Cura . instantânea — e a economia está cheia delas
    //                      (medido em produção: 120 donos da Minor no `main`)
    // A tela mandava esperar horas por uma coisa que se resolve em 20 minutos,
    // com um item que o jogador quase de certeza já tem na mochila (Lei §1: uma
    // recusa honesta ainda é um beco se não disser o caminho de saída).
    //
    // ⚠️ O contexto muda (npc / fila / pvp / Eco); **o caminho de saída não**.
    // Por isso há uma só frase para a saída e uma só função que a junta. Quatro
    // cópias da mesma frase seriam a mesma família de defeito que produziu tudo
    // o resto deste ficheiro.
    //
    // ⚠️ `combat_pvp_challenger_hp_depleted` NÃO passa por aqui, e isso é
    // decisão: quem está a zero é o OUTRO jogador. Mandar VOCÊ meditar por
    // causa da vitalidade dele seria a tela a mentir.
    function hpDepletedMsg(contextKey) {
      return safeT(contextKey) + " " + safeT("combat_hp_way_out");
    }

    // 🩸 2026-09-13 — UMA BARRA QUE NÃO DIZ O QUE É NÃO É UMA BARRA.
    //
    // Isto nasce de um defeito medido, não de uma preferência: o hub EU
    // desenhava três `ProgressBar` nuas, empilhadas, sem rótulo e sem número — e
    // a terceira delas era a **Vitalidade**, o único sítio do mini-app inteiro
    // onde ela aparece. O jogador via uma linha vermelha encurtar durante
    // semanas sem nunca lhe ser dito o nome, e a primeira frase que o jogo lhe
    // dizia sobre o assunto era a RECUSA (`hp_too_low`) no momento de lutar.
    //
    // O cartão da Home já fazia o certo (rótulo à esquerda, valor à direita) —
    // à mão, dentro da sua própria tela. Passa a haver **um dono**: quem quiser
    // uma barra com significado usa esta, e a Home é a forma que ela copia.
    //
    // ⚠️ `ProgressBar` continua a existir e continua nua de propósito: há sítios
    // onde a barra está DENTRO de uma coisa que já tem título (o `CardTitle` da
    // aba Cultivo, as barras de HP dentro de um duelo). Esta serve o caso
    // oposto — a barra sozinha, sem nada à volta que a explique.
    function LabeledBar({ label, pct, right, variant="cult", height=7 }) {
      return (
        <div>
          <div style={{
            display:"flex", justifyContent:"space-between", alignItems:"baseline",
            gap:8, marginBottom:3,
          }}>
            <span style={{
              fontFamily:"'Cinzel',serif", fontSize:9.5, letterSpacing:1,
              textTransform:"uppercase", color:"var(--gold3)",
              overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap",
            }}>{label}</span>
            {right != null && (
              <span style={{
                fontSize:10.5, color:"var(--muted)", fontVariantNumeric:"tabular-nums",
                flexShrink:0, whiteSpace:"nowrap",
              }}>{right}</span>
            )}
          </div>
          <ProgressBar pct={pct} variant={variant} height={height} />
        </div>
      );
    }
    function Badge({ children, variant="jade" }) {
      const styles = {
        jade:{ bg:"rgba(var(--jade-rgb),.15)", color:"var(--jade)", border:"rgba(var(--jade-rgb),.3)" },
        warn:{ bg:"rgba(var(--warn-rgb),.14)", color:"var(--warn)", border:"rgba(var(--warn-rgb),.3)" },
        red: { bg:"rgba(var(--red-rgb),.14)", color:"var(--red)", border:"rgba(var(--red-rgb),.3)" },
        gold:{ bg:"rgba(var(--gold-rgb),.15)", color:"var(--gold2)", border:"rgba(var(--gold-rgb),.35)" },
      }[variant] || {};
      return (
        <span style={{
          display:"inline-block", padding:"2px 8px", borderRadius:3,
          fontSize:9.5, fontWeight:600, letterSpacing:.3,
          background:styles.bg, color:styles.color, border:`1px solid ${styles.border}`,
          fontFamily:"'Cinzel',serif",
        }}>{children}</span>
      );
    }

    // ─── Progressão Visível — count-up + before→after delta primitives ───────
    // The owner's hard rule: every advance must SHOW the number going up. These
    // two primitives are reused by the header Poder de Combate chip, the Atributos
    // card, and the breakthrough/temper/equip deltas. Pure display — gated upstream
    // by featureEnabled("progressao_visivel").
    //
    // CountUp animates from the value it last rendered to the new `value` (~0.6s,
    // easeOutCubic). No animation on first mount (from === to) — it only "pops"
    // when the number actually changes after a refetch, so every upgrade climbs.
    function CountUp({ value, fmt, style, className }) {
      const format = fmt || fmtNum;
      const target = Number(value) || 0;
      const curRef = useRef(target);
      const rafRef = useRef(0);
      const [, force] = useState(0);
      useEffect(() => {
        const from = curRef.current;
        const to = target;
        if (from === to) { curRef.current = to; return; }
        cancelAnimationFrame(rafRef.current);
        const dur = 650;
        const t0 = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
        const step = (now) => {
          const p = Math.min(1, (now - t0) / dur);
          const e = 1 - Math.pow(1 - p, 3); // easeOutCubic
          curRef.current = from + (to - from) * e;
          force(x => x + 1);
          if (p < 1) rafRef.current = requestAnimationFrame(step);
          else { curRef.current = to; force(x => x + 1); }
        };
        rafRef.current = requestAnimationFrame(step);
        return () => cancelAnimationFrame(rafRef.current);
      }, [target]);
      return <span className={className} style={style}>{format(curRef.current)}</span>;
    }

    // DeltaPanel renders "label: before → after (+gain)" rows in green (drop = red).
    // `deltas` = { key: {before, after}, ... }. Rows with no change are hidden.
    var VP_DELTA_LABELS = {
      display_combat_power: "vp_combat_power",
      max_hp:               "vp_max_hp",
      qi_capacity:          "vp_qi_capacity",
      battle_power:         "battle_power",
    };
    function DeltaPanel({ deltas, order, style }) {
      if (!deltas) return null;
      const keys = (order || ["display_combat_power", "max_hp", "qi_capacity"])
        .filter(k => deltas[k] && Number(deltas[k].after) !== Number(deltas[k].before));
      if (!keys.length) return null;
      return (
        <div style={{
          marginTop: 10, padding: "9px 11px", borderRadius: 9,
          background: "rgba(var(--jade-rgb),.07)", border: "1px solid rgba(var(--jade-rgb),.28)",
          // QoL 31/07 — sweep do fix do Salão: sem template, o valor nowrap estica a coluna
          display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 5, ...style,
        }}>
          {keys.map(k => {
            const d = deltas[k];
            const before = Number(d.before) || 0, after = Number(d.after) || 0;
            const gain = after - before, up = gain >= 0;
            const col = up ? "var(--jade)" : "var(--red)";
            return (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 6, fontSize: 12 }}>
                <span style={{ color: "var(--muted)", fontFamily: "'Cinzel',serif", letterSpacing: .3, minWidth: 0 }}>
                  {safeT(VP_DELTA_LABELS[k] || k)}
                </span>
                {/* o número do antes→depois nunca é cortado (Lei §10) — o rótulo é quem cede */}
                <span style={{ whiteSpace: "nowrap", flexShrink: 0 }}>
                  <span style={{ color: "var(--muted)" }}>{fmtNum(before)}</span>
                  <span style={{ color: "var(--gold2)", margin: "0 3px" }}>→</span>
                  <b style={{ color: col }}>{fmtNum(after)}</b>
                  <small style={{ color: col, marginLeft: 4 }}>({up ? "+" : ""}{fmtNum(gain)})</small>
                </span>
              </div>
            );
          })}
        </div>
      );
    }

    // Compact "\n⚔️ before → after (+gain)" line appended to an action toast so a
    // gain the player made is never silent. Returns "" when nothing moved (or the
    // server sent no power_delta because the feature is OFF). Server passes
    // {before, after} from _display_combat_power (equip/pill/temper endpoints).
    function vpPowerLine(pd) {
      if (!pd || pd.before == null || pd.after == null) return "";
      const before = Number(pd.before) || 0, after = Number(pd.after) || 0;
      if (after === before) return "";
      const gain = after - before, up = gain >= 0;
      return "\n" + t("vp_power_toast", {
        before: fmtNum(before), after: fmtNum(after),
        delta: (up ? "+" : "") + fmtNum(gain),
      });
    }

    // ─── Dot Spinner ─────────────────────────────────────────────────────────
    // Three bouncing dots overlay. Used by ActionBtn so the button's content
    // size never changes when it switches to busy state — fixes the "square
    // collapse" flash where {busy ? '…' : children} shrunk the inline-flex
    // button to the width of a single ellipsis.
    function DotSpinner({ color = "currentColor", size = 4 }) {
      const dot = (delay) => ({
        width: size, height: size, borderRadius:"50%",
        background: color, opacity: .5,
        animation: `dot-bounce 1s ease-in-out ${delay}s infinite`,
      });
      return (
        <span style={{ display:"inline-flex", gap:3, alignItems:"center" }}>
          <span style={dot(0)} /><span style={dot(.16)} /><span style={dot(.32)} />
        </span>
      );
    }

    // ─── Action Button (with optimistic loading + haptic) ────────────────────
    function ActionBtn({ onClick, children, variant="primary", style, disabled }) {
      const [busy, setBusy] = useState(false);
      const _palettes = {
        primary:{ border:"var(--gold)", bg:"linear-gradient(180deg,rgba(var(--gold-rgb),.32),rgba(120,80,30,.55))", color:"var(--gold2)" },
        danger: { border:"rgba(var(--red-rgb),.4)", bg:"rgba(var(--red-rgb),.12)", color:"var(--red)" },
        ghost:  { border:"var(--border)", bg:"linear-gradient(180deg,rgba(40,60,110,.6),rgba(20,32,60,.85))", color:"var(--text)" },
      };
      // Defensive: an UNKNOWN variant must never crash the whole modal on
      // `palette.border` (this black-screened the Sect Hall for every member via
      // a stray variant="secondary"). Fall back to primary — Lei §1 never-stuck.
      const palette = _palettes[variant] || _palettes.primary;
      return (
        <button disabled={busy || disabled} onClick={async () => {
          haptic("light");
          setBusy(true);
          try { await onClick(); } finally { setBusy(false); }
        }} style={{
          position:"relative",
          display:"inline-flex", alignItems:"center", justifyContent:"center", gap:6,
          padding:"9px 14px", borderRadius:10, border:`1px solid ${palette.border}`,
          background: palette.bg, color: palette.color,
          fontFamily:"'Cinzel',serif", fontSize:12, fontWeight:600, letterSpacing:.5,
          cursor: (busy || disabled) ? "default" : "pointer",
          opacity: disabled ? .6 : 1,
          transition:"transform .08s, opacity .15s",
          ...style,
        }}>
          {/* Children stay mounted but invisible during busy — preserves width */}
          <span style={{ visibility: busy ? "hidden" : "visible", display:"inline-flex", alignItems:"center", gap:6 }}>
            {children}
          </span>
          {busy && (
            <span style={{ position:"absolute", inset:0, display:"grid", placeItems:"center" }}>
              <DotSpinner />
            </span>
          )}
        </button>
      );
    }

    // ─── Cultivation Orb (per-realm gradients, octagram ticks, NO glyph) ─────
    // ═══ 坐 O CULTIVADOR — a figura que substitui o orbe (2026-09-07) ════════
    //
    // Ordem do owner, textual: *"esse orb nao gostei nada, muito AI. etc. usamos
    // uma imagem e criamos efeito nela tipo de um cultivador."*
    //
    // E ele tem razão por uma razão mais dura do que "parece AI": **o ✦ que
    // estava no centro É o ícone de AI.** Desde 2023 é o glifo que toda a
    // indústria usa para dizer "isto foi gerado" — e estava no meio da tela mais
    // aberta do jogo. Fora da meditação o centro era pior ainda: um EMOJI DO
    // SISTEMA (🔮), que muda de forma de aparelho para aparelho. E o resto era
    // `radial-gradient` puro: a esfera era a única peça do jogo feita
    // inteiramente de gradiente, depois de a WEB-D e a CARTA passarem dois lotes
    // a tirá-los.
    //
    // O que fica: **o efeito muda de suporte, não desaparece.** A respiração, os
    // anéis, as partículas de qi — tudo o que a WEB-E provou ser a única coisa
    // do ecrã que muda quando o jogador se senta — passa a ser aplicado a uma
    // PESSOA em vez de a uma bola. É literalmente o que o owner pediu: "usamos
    // uma imagem e criamos efeito nela".
    //
    // ⚠️ A figura tem de ser SENTADA, e só sentada. Ela é a única camada que
    // pode falar do jogador, e o jogador ou está a meditar ou está de pé à
    // espera — nenhuma pose inventada pode entrar aqui, sob pena de repetir o
    // defeito das 11 imagens antigas (§ o comentário do `REALM_PLACE_FILES`).
    //
    // ⚠️ Com a flag OFF, o corpo inteiro desta função é o de hoje, byte a byte.
    // 坐 ONDA 1 — `size` e `plain` são ADITIVOS (por omissão 212 e `false`),
    // portanto os sítios de hoje desenham exactamente o mesmo. Existem porque a
    // [013] apanhou um defeito concreto: **a figura guarda `212 × 212` por
    // dentro**, logo mudar só o invólucro para 128 ou 360 não a redimensionava
    // — ficava do mesmo tamanho dentro de uma caixa maior, que é pior do que
    // não ter mudado nada. O tamanho tem de alcançar o elemento visual real.
    function CultivationOrb({ realm=1, meditating=false, gender=null, size, plain }) {
      const figureOn = typeof featureEnabled === "function" && featureEnabled("cultivador");
      if (figureOn) return <CultivatorFigure realm={realm} meditating={meditating}
                                             gender={gender} size={size} plain={plain} />;
      return <CultivationOrbClassic realm={realm} meditating={meditating} size={size} />;
    }

    // 坐 A figura. O mesmo tamanho, o mesmo sítio, as mesmas três animações —
    // só o SUPORTE mudou.
    function CultivatorFigure({ realm=1, meditating=false, gender=null, size, plain,
                                diagrama, children, rotulo }) {
      const r = Math.min(realm, 10);
      // ⚠️ O tamanho REAL. Sem isto o `size` mudava o invólucro e a figura
      // ficava nos 212 de sempre, centrada num vazio maior.
      const _SZ = Number(size) || 212;
      const rc = realmHex(r);
      const [loaded, setLoaded] = useState(false);
      const [failed, setFailed] = useState(false);
      const src = cultivatorArtUrl(gender);
      useEffect(() => { setLoaded(false); setFailed(false); }, [src]);

      // ⚠️ As mesmas 18 partículas do orbe, com a MESMA semente de aleatório —
      // não é nostalgia: é o que mantém o ensaio do DOM a conseguir normalizá-las
      // com o mesmo padrão dos dois lados.
      const particles = useMemo(() => Array.from({length:18}, () => ({
        left: 26 + Math.random()*48 + "%",
        dx: (Math.random()*70 - 35) + "px",
        delay: -(Math.random()*3) + "s",
        size: 2.5 + Math.random()*2.5,
      })), [meditating]);

      // 星 2.1 — O MODO DE DIAGRAMA, pedido pelo Astra com todas as letras:
      // *"o Corpo precisa de um modo explícito de diagrama, que mostre a figura
      // em repouso sem falsificar meditação"*. Fora dele a figura só existe
      // SENTADA A MEDITAR (a lei de cima); aqui ela é uma CONSULTA do próprio
      // corpo, e não finge que o jogador está sentado — por isso não herda
      // anéis, partículas, auréola nem respiração.
      // ⚠️ É um MODO desta função e não um componente novo: uma segunda
      // etiqueta de imagem para a mesma pintura seria o segundo dono que a
      // guarda F-7 (B) conta — e contou, quando a 1ª versão do Corpo o fez.
      // ⚠️ Por baixo da pintura há SEMPRE uma silhueta vectorial com a mesma
      // caixa: demora ou falha de arte nunca tira as marcas nem os números,
      // que vêm por `children` e partilham o MESMO rectângulo da imagem.
      if (diagrama) {
        return (
          <div role="img" aria-label={rotulo}
               style={{ position:"relative", width:_SZ, height:_SZ, maxWidth:"100%",
                        margin:"0 auto", flexShrink:0 }}>
            <svg aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none"
                 style={{ position:"absolute", inset:0, width:"100%", height:"100%", zIndex:1,
                          opacity: (loaded && !failed) ? 0 : 1, transition:"opacity .5s ease" }}>
              <g fill="rgba(236,229,216,.05)" stroke="rgba(236,229,216,.2)" strokeWidth="1">
                <circle cx="50" cy="12" r="3" vectorEffect="non-scaling-stroke" />
                <ellipse cx="50" cy="23" rx="7" ry="8.6" vectorEffect="non-scaling-stroke" />
                <path d="M36 40 Q50 33 64 40 L67 63 Q50 67 33 63 Z" vectorEffect="non-scaling-stroke" />
                <path d="M36 40 Q28 50 31 63 Q37 71 47 71" vectorEffect="non-scaling-stroke" />
                <path d="M64 40 Q72 50 69 63 Q63 71 53 71" vectorEffect="non-scaling-stroke" />
                <ellipse cx="50" cy="77" rx="33" ry="9" vectorEffect="non-scaling-stroke" />
              </g>
            </svg>
            {!failed && (
              <img src={src} alt="" loading="lazy" decoding="async"
                   onError={() => setFailed(true)} onLoad={() => setLoaded(true)}
                   style={{ position:"absolute", inset:0, width:"100%", height:"100%",
                            objectFit:"contain", display:"block", zIndex:2,
                            opacity: loaded ? 1 : 0, transition:"opacity .5s ease",
                            // a borda dissolve-se; a máscara é só da pintura,
                            // nunca das marcas nem do texto
                            WebkitMaskImage:"radial-gradient(ellipse at 50% 50%, #000 48%, transparent 74%)",
                            maskImage:"radial-gradient(ellipse at 50% 50%, #000 48%, transparent 74%)" }} />
            )}
            {children}
          </div>
        );
      }

      return (
        <div style={{ position:"relative", width:_SZ, height:_SZ,
                      margin: plain ? 0 : "6px auto 14px",
                      display:"grid", placeItems:"center",
                      // 坐 ONDA 1 — a respiração discreta que a [013] deixou no
                      // lugar dos anéis: só opacidade, só a meditar, 8s.
                      animation: (plain && meditating)
                        ? "onda-breathe 8s ease-in-out infinite" : undefined }}>
          {/* o anel de fora, que já existia: o único enfeite que sobrevive
              — e que a variante `plain` corta, porque numa cena que já tem
              paisagem ele vira um segundo enquadramento a competir com ela. */}
          {!plain && (
            <div style={{
              position:"absolute", inset:-4, borderRadius:"50%",
              border:"1px solid rgba(var(--gold-rgb),.16)",
              animation:"orb-rotate 60s linear infinite",
            }} />
          )}
          {!plain && meditating && [0,1,2].map(i => (
            <div key={i} style={{
              position:"absolute", inset:-4, borderRadius:"50%",
              border:`1px solid ${cssHex(rc)}44`,
              animation:`orb-ring-out 3s ease-out ${i}s infinite`,
            }} />
          ))}
          {/* A AURÉOLA vai POR BAIXO da figura (zIndex 1) e é discreta.
              ⚠️ Visto a olho: a .30 e por cima, ela TINGIA o rosto de roxo e a
              figura virava um fantasma. Ela ILUMINA a pessoa; não a pinta.
              É também o que respira — a peça que carrega o estado. */}
          <div style={{
            position:"absolute", inset:2, borderRadius:"50%", zIndex:1,
            background: `radial-gradient(circle at 50% 56%, ${cssHex(rc)}${meditating ? "3a" : "22"},`
                        + ` ${cssHex(rc)}0f 45%, transparent 68%)`,
            animation:`orb-breathe ${meditating ? "2.6" : "4"}s ease-in-out infinite`,
          }} />
          {/* ⚠️ NADA de `mix-blend-mode`. A 1ª tentativa usou `screen` porque a
              figura vem sobre preto — e `screen` não remove o preto, CLAREIA
              tudo: as vestes escuras desapareciam, a pessoa ficava translúcida e
              a aresta quadrada da imagem ficava à vista. A figura já nasce sobre
              quase-preto, que é o MESMO fundo da cena; basta esbater a aresta
              com uma máscara radial — o mesmo truque que o pé da chapa da carta
              já usa. */}
          {/* ⚠️ A FIGURA SÓ EXISTE SENTADA — e isto foi apanhado a OLHAR, não a
              pensar. A 1ª versão desenhava o cultivador sempre, e a tela ficou
              a dizer **"VOCÊ NÃO ESTÁ SENTADO"** por baixo de uma figura
              sentada. É exactamente o defeito que a WEB-E encontrou no cume (a
              barra que prometia um avanço impossível) e o que matou o plano de
              legendar as 11 imagens antigas: a tela a contradizer-se.
              Vazio é a resposta CERTA, não a resposta pobre: quando o jogador
              não está a cultivar, o lugar está à espera dele — e o lugar já foi
              desenhado com o assento vazio lá dentro. Sentar-se passa a ser o
              momento em que você APARECE no mundo, que é infinitamente mais do
              que uma bola mudar de cor. (Régua do desenho: *"o vazio é a
              composição; enchê-lo é o instinto errado"*.) */}
          {meditating && !failed && (
            <img src={src} alt="" loading="lazy" decoding="async"
                 onError={() => setFailed(true)} onLoad={() => setLoaded(true)}
                 style={{
                   position:"relative", zIndex:2, width:"100%", height:"100%",
                   objectFit:"contain", display:"block",
                   opacity: loaded ? 1 : 0, transition:"opacity .5s ease",
                   // 坐 ONDA 1 — a ARESTA, apanhada a olhar a 1440x900.
                   // MEDIDO no DOM: com `objectFit:contain` num invólucro de
                   // 360x360 a imagem fica **228 x 360** — deixa de ser quadrada.
                   // Um `circle` dimensiona-se pelo canto mais distante do
                   // ELEMENTO, portanto a 52%/76% o desvanecimento horizontal
                   // acabava a ~162px do centro, com o elemento a ter só 114px
                   // de meia-largura: os lados eram CORTADOS a direito em vez de
                   // esbatidos, e a figura ganhava a moldura rectangular que a
                   // [013] §B.2 proíbe ("nenhuma aresta retangular visível").
                   // Um `ellipse` escala em cada eixo e esbate nos quatro lados.
                   // ⚠️ Só na variante `plain`: a 212x212 de hoje era quadrada e
                   // o círculo estava certo — não se conserta o que não partiu.
                   WebkitMaskImage: plain
                     ? "radial-gradient(ellipse at 50% 52%, #000 42%, transparent 74%)"
                     : "radial-gradient(circle at 50% 52%, #000 52%, transparent 76%)",
                   maskImage: plain
                     ? "radial-gradient(ellipse at 50% 52%, #000 42%, transparent 74%)"
                     : "radial-gradient(circle at 50% 52%, #000 52%, transparent 76%)",
                 }} />
          )}
          {/* De pé, o que ocupa o círculo é o ASSENTO VAZIO: um anel de tinta
              fino e nada mais. Não é um buraco — é a cadeira posta. */}
          {!meditating && (
            <div aria-hidden="true" style={{
              position:"absolute", inset:"38% 30% 30%", zIndex:2, borderRadius:"50%",
              border:`1px solid ${cssHex(rc)}2e`,
              background:`radial-gradient(ellipse at 50% 55%, ${cssHex(rc)}14, transparent 70%)`,
            }} />
          )}
          {/* Lei §1 — se a figura falhar, a cena não fica com um buraco: fica a
              auréola a respirar, que continua a dizer se o jogador está sentado. */}
          <div style={{ position:"absolute", inset:0, pointerEvents:"none", zIndex:3 }}>
            {!plain && meditating && particles.map((p, i) => (
              <span key={i} style={{
                position:"absolute", bottom:"46%", left: p.left,
                width: p.size, height: p.size, borderRadius:"50%",
                background: cssHex(rc), boxShadow: `0 0 5px ${cssHex(rc)}`,
                animation: `qi-rise 3s ease-out ${p.delay} infinite`,
                "--dx": p.dx,
              }} />
            ))}
          </div>
        </div>
      );
    }

    function CultivationOrbClassic({ realm=1, meditating=false, size }) {
      const r = Math.min(realm, 10);
      // 坐 ONDA 1 — o orbe clássico também aceita `size`, e por uma razão
      // que não é simetria: a cena da onda pode correr num mundo com a
      // `cultivador` OFF, e aí quem lá está é ele. Sem isto a composição
      // reservava 192 ou 360px e desenhava 200 — alinhado em lado nenhum.
      const _SZ = Number(size) || 200;
      // R5: hex literal — o glow (linha ~1320) concatena alpha; com var() o
      // orbe grande do cultivo nunca teve aura (declaração inteira caía).
      const rc = realmHex(r);
      const orbGradients = {
        0:`radial-gradient(circle at 35% 30%,rgba(200,210,220,.4),transparent 45%),radial-gradient(circle at 50% 50%,var(--realm-0),#4b5563 70%,#1f2937)`,
        1:`radial-gradient(circle at 35% 30%,rgba(200,230,255,.5),transparent 45%),radial-gradient(circle at 50% 50%,var(--realm-1),#1d4ed8 70%,#0c1a4a)`,
        2:`radial-gradient(circle at 35% 30%,rgba(255,240,180,.5),transparent 45%),radial-gradient(circle at 50% 50%,var(--realm-2),#92400e 70%,#3a1a05)`,
        3:`radial-gradient(circle at 35% 30%,rgba(230,200,255,.5),transparent 45%),radial-gradient(circle at 50% 50%,var(--realm-3),#6b21a8 70%,#2d0a5c)`,
        4:`radial-gradient(circle at 35% 30%,rgba(180,255,240,.5),transparent 45%),radial-gradient(circle at 50% 50%,var(--realm-4),#0f766e 70%,#042f2e)`,
        5:`radial-gradient(circle at 35% 30%,rgba(180,210,255,.5),transparent 45%),radial-gradient(circle at 50% 50%,var(--realm-5),#1e3a8a 70%,#0a1a4a)`,
        6:`radial-gradient(circle at 35% 30%,rgba(200,185,255,.5),transparent 45%),radial-gradient(circle at 50% 50%,var(--realm-6),#4c1d95 70%,#1e0a40)`,
        7:`radial-gradient(circle at 35% 30%,rgba(255,230,170,.5),transparent 45%),radial-gradient(circle at 50% 50%,var(--warn),#92400e 70%,#3a1505)`,
        8:`radial-gradient(circle at 35% 30%,rgba(180,240,255,.5),transparent 45%),radial-gradient(circle at 50% 50%,var(--realm-8),#0369a1 70%,#022d4a)`,
        9:`radial-gradient(circle at 35% 30%,rgba(255,240,150,.5),transparent 45%),radial-gradient(circle at 50% 50%,var(--realm-9),#854d0e 70%,#362003)`,
        10:`radial-gradient(circle at 35% 30%,rgba(255,200,230,.6),transparent 40%),radial-gradient(circle at 70% 70%,rgba(var(--gold-rgb),.5),transparent 55%),radial-gradient(circle at 50% 50%,#f9a8d4,var(--gold) 60%,#7c2d12)`,
      };
      const medOrb = `radial-gradient(circle at 35% 30%,rgba(255,255,255,.6),transparent 45%),radial-gradient(circle at 70% 70%,rgba(var(--realm-3-rgb),.55),transparent 60%),radial-gradient(circle at 50% 50%,#b478ff,#5f2da3 70%,#2a0e5e)`;
      const orbBg = meditating ? medOrb : (orbGradients[r] || orbGradients[1]);
      const orbGlow = meditating
        ? "0 0 60px rgba(var(--realm-3-rgb),.6),0 0 100px rgba(var(--realm-3-rgb),.25),inset 0 0 24px rgba(220,200,255,.4)"
        : r === 10
          ? "0 0 60px rgba(var(--realm-10-rgb),.5),0 0 90px rgba(var(--gold-rgb),.3),inset 0 0 24px rgba(255,240,200,.4)"
          : `0 0 45px ${cssHex(rc)}77,0 0 70px ${cssHex(rc)}33,inset 0 0 18px rgba(255,255,255,.2)`;

      const particles = useMemo(() => Array.from({length:18}, () => ({
        left: 26 + Math.random()*48 + "%",
        dx: (Math.random()*70 - 35) + "px",
        delay: -(Math.random()*3) + "s",
        size: 2.5 + Math.random()*2.5,
        color: meditating ? "rgba(200,160,255,.92)" : "rgba(170,210,255,.85)",
      })), [meditating]);

      return (
        <div style={{ position:"relative", width:_SZ, height:_SZ, margin:"6px auto 14px", display:"grid", placeItems:"center" }}>
          <div style={{
            position:"absolute", inset:0, borderRadius:"50%",
            border:"1px solid rgba(var(--gold-rgb),.18)",
            animation:"orb-rotate 60s linear infinite",
          }} />
          {meditating && [0,1,2].map(i => (
            <div key={i} style={{
              position:"absolute", inset:0, borderRadius:"50%",
              border:"1px solid rgba(var(--realm-3-rgb),.28)",
              animation:`orb-ring-out 3s ease-out ${i}s infinite`,
            }} />
          ))}
          <svg style={{ position:"absolute", inset:0, width:"100%", height:"100%", opacity:.4 }}
               viewBox="0 0 200 200">
            <circle cx="100" cy="100" r="96" stroke="rgba(201,144,58,.4)" strokeWidth=".5" fill="none" strokeDasharray="4 8" />
            {Array.from({length:8}, (_, i) => {
              const angle = (i/8)*Math.PI*2, r1=88, r2=96;
              const x1 = 100 + r1*Math.cos(angle), y1 = 100 + r1*Math.sin(angle);
              const x2 = 100 + r2*Math.cos(angle), y2 = 100 + r2*Math.sin(angle);
              return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(245,201,122,.75)" strokeWidth="1.5" />;
            })}
          </svg>
          <div style={{
            position:"absolute", inset:22, borderRadius:"50%",
            background: orbBg, boxShadow: orbGlow,
            animation:`orb-breathe ${meditating ? "2.6" : "4"}s ease-in-out infinite`,
          }} />
          <div style={{ position:"absolute", inset:0, pointerEvents:"none" }}>
            {meditating && particles.map((p, i) => (
              <span key={i} style={{
                position:"absolute", bottom:"50%", left: p.left,
                width: p.size, height: p.size, borderRadius:"50%",
                background: p.color, boxShadow: `0 0 5px ${p.color}`,
                animation: `qi-rise 3s ease-out ${p.delay} infinite`,
                "--dx": p.dx,
              }} />
            ))}
          </div>
          <div style={{
            position:"relative", zIndex:2,
            fontSize: meditating ? 44 : 50, fontWeight:700,
            color:"rgba(255,255,255,.94)", lineHeight:1,
            textShadow:`0 0 16px rgba(255,255,255,.6), 0 0 30px ${rc}`,
            pointerEvents:"none",
          }}>{orbCenterIcon(r, meditating)}</div>
        </div>
      );
    }

    // ═══ WEB-E 坐 A CENA DO CULTIVO ═══════════════════════════════════════════
    // O achado que dá licença a isto (LINGUAGEM_VISUAL_WEB_C.md, Achado 1): no
    // Nivrael **esperar é o enredo**, não um defeito de ritmo. Todo idle luta
    // contra a vergonha de o jogador estar a esperar e disfarça com números a
    // subir depressa. Aqui não se disfarça — dramatiza-se.
    //
    // O que estava mal, MEDIDO a 2026-09-02 (a 390×844, com o payload real):
    // 2140px de scroll, e o topo eram QUATRO caixas com a mesma moldura — o
    // orbe (decoração muda, sem uma única informação), CULTIVO (barra), QI
    // (barra) e MEDITAÇÃO (o estado). A resposta à pergunta 1 da régua ("isto
    // podia ser o dashboard de qualquer SaaS?") era **sim**: duas barras e um
    // botão. E o estado mais volátil da tela — se você está sentado e por
    // quanto tempo — era a TERCEIRA caixa, abaixo da dobra no telemóvel.
    //
    // Esta cena funde as quatro numa só composição e **não remove nada**
    // (Lei de Ferro (a)): o orbe, os dois números com os seus totais, o nome
    // do reino, o chip de regeneração, o tipo de meditação, o multiplicador, o
    // tempo, o botão de interromper, os quatro assentos com os seus cadeados e
    // os CTAs de Avançar/Renascer estão todos aqui. O que muda é a HIERARQUIA:
    //   · a legenda da cena é o ESTADO (sentado ou não), não uma percentagem;
    //   · as duas barras viram fios de tinta sem caixa — o vazio é a composição
    //     (水墨), e não há moldura a dizer que um Qi vale o mesmo que um aviso;
    //   · a acção fica onde o olho já está, em vez de 400px abaixo.
    //
    // ⚠️ O que NÃO se faz aqui (§3.3 do prompt): zero confetes, zero `+1` a
    // saltar, zero celebração de não-eventos, e NENHUM número animado que não
    // tenha subido de verdade.
    //
    // ⚠️ Duas verdades foram VERIFICADAS no motor antes de virarem texto:
    //   1. meditar é um MULTIPLICADOR, não um interruptor —
    //      `calculate_cb_per_tick` faz `meditation_mult = ... if is_meditating
    //      else 1.0`, logo a base cresce sozinha. Um rascunho desta cena dizia
    //      "a base só cresce enquanto você cultiva": era mentira, e teria sido
    //      mentira impressa na tela mais aberta do jogo.
    //   2. no cume (reino 10, camada 9) `check_breakthrough` **fixa** a base no
    //      limiar e devolve `None`: encher a barra ali não produz evento nenhum.
    //      São 21 dos 37 activos-30d do `main` (57%) — a maioria de quem abre
    //      esta tela. A cena DIZ isso em vez de deixar a barra fingir contagem
    //      decrescente (Lei §1: honest disclosure, nunca silent void).
    //
    // Superfície larga: o mesmo componente, o mesmo conteúdo, só o eixo muda
    // (orbe ao lado da legenda em vez de por cima) — como o `shellStyle` já
    // faz. Não é um segundo cliente (Lei §5).
    function SceneThread({ label, pct, variant, left, right }) {
      return (
        <div style={{ marginTop: 14 }}>
          <div style={{ display:"flex", alignItems:"baseline", gap:8, marginBottom:5 }}>
            <span style={{ fontSize:9, letterSpacing:".22em", textTransform:"uppercase",
                           color:"var(--muted2)", flexShrink:0 }}>{label}</span>
            <span style={{ fontSize:10.5, color:"var(--muted)", minWidth:0,
                           overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{left}</span>
            <span style={{ marginLeft:"auto", flexShrink:0, display:"flex",
                           alignItems:"center", gap:6 }}>{right}</span>
          </div>
          {/* o fio de tinta: 3px, sem moldura. A barra de 8px com borda dourada
              era a peça que mais fazia a tela parecer um dashboard — mas o
              GRADIENTE é o mesmo do resto do jogo (`ProgressBar` com `bare`),
              para uma paleta futura não aquecer uma barra e esquecer a outra. */}
          <ProgressBar pct={pct} variant={variant} height={3} bare />
        </div>
      );
    }

    // 牌 2026-09-05 — A ARTE DO REINO entra na cena. Existia desde 2026-05-01 e
    // o servidor nunca serviu um byte dela (rota `assets` nova no webserver).
    //
    // ⚠️ A DECISÃO QUE OLHAR MUDOU. O plano escrito (RECON §3.3) era *"a
    // ilustração É a cena; o orbe passa a camada de qi por cima, ou sai"*.
    // Abri as ONZE imagens a 2026-09-05 e isso não é possível — elas não são um
    // conjunto de "um cultivador no estado X". São **um retrato do REINO**, e a
    // postura muda:
    //
    //   0  mortal              paisagem ao lusco-fusco, viajante DE PÉ ao longe
    //   1  qi condensation     sentado de pernas cruzadas numa saliência ✔
    //   2  foundation          silhueta DE PÉ diante de um templo-lótus
    //                          (⚠️ e é CIANO, não âmbar como o README dizia)
    //   3  core                lótus a LEVITAR, braços abertos ✔
    //   4  nascent soul        sentado, o espírito nascente por cima ✔
    //   5  soul transformation sentada num estrado, galáxias e borboletas ✔
    //   6  void refinement     em COMBATE, espada fora, a partir o espaço
    //   7  body integration    meio-lótus suspenso na tempestade ✔
    //   8  mahayana            sentado num cume, espiral de runas ✔
    //   9  tribulation         DE PÉ num penhasco, a receber o raio
    //   10 true immortal       a VOAR, asas abertas
    //
    // **Seis de onze estão sentados; cinco não.** Pôr a `realm-tribulation`
    // debaixo de "Meditação Profunda · 47m" seria imprimir uma mentira por cima
    // da imagem — e o reino 10 é onde estão **21 dos 37 activos-30d do `main`
    // (57%)**, ou seja a maioria veria um homem alado a voar debaixo da frase
    // "você está sentado, à espera". É a armadilha que a FORMA já pagou uma vez
    // (a `realm-core` descrita como "sentado" quando levita), agora ×5.
    //
    // **Então a arte é o LUGAR, e o orbe continua a ser o ESTADO.** A
    // ilustração entra como fundo da composição, com o pé dissolvido no preto
    // quente; o orbe fica por cima porque é a única peça do ecrã que muda
    // quando o jogador se senta (respiração, anéis, partículas). A legenda
    // continua a dizer o estado. Nada na tela afirma nada sobre a figura
    // pintada — e por isso nenhuma das onze pode mentir.
    //
    // ⚠️ Carrega SÓ o reino do jogador (43–81 KB, `loading="lazy"`), nunca os
    // onze. E se falhar não há buraco: o `onError` apaga o fundo e a cena volta
    // a ser exactamente a de 02/09 (Lei §1 — o erro nunca tira o tap).
    function RealmBackdrop({ realm, wide, fill }) {
      const [failed, setFailed] = useState(false);
      const [loaded, setLoaded] = useState(false);
      // ⚠️ A arte NOVA (o reino como lugar vazio) só entra com `cultivador` ON.
      // As duas flags ficam ortogonais: `cena_cultivo` sozinha rende exactamente
      // a cena de 02/09, com as 11 imagens de landing reaproveitadas.
      const places = typeof featureEnabled === "function" && featureEnabled("cultivador");
      const src = realmArtUrl(realm, places);
      if (!src || failed) return null;
      return (
        <div aria-hidden="true" style={{
          position: "absolute", left: -14, right: -14, top: -14,
          // 坐 ONDA 1 — `fill` faz o fundo acompanhar a ALTURA DA CENA em vez
          // de um limite fixo. A [013]: *"a paisagem deixa de ser uma faixa no
          // topo"*. Aditivo: sem ele os 300/340 de hoje ficam.
          bottom: fill ? -14 : undefined,
          height: fill ? undefined : (wide ? 300 : 340),
          overflow: "hidden", pointerEvents: "none",
          zIndex: 0, opacity: loaded ? 1 : 0, transition: "opacity .7s ease",
        }}>
          <img src={src} alt="" loading="lazy" decoding="async"
               onError={() => setFailed(true)} onLoad={() => setLoaded(true)}
               style={{
                 width: "100%", height: "100%", objectFit: "cover",
                 objectPosition: wide ? "center 38%" : "center 30%",
                 display: "block",
                 // 坐 ONDA 1 — a [013] pediu a imagem mais funda e menos
                 // saturada, para o papel e o ouro do texto ganharem a tela.
                 opacity: fill ? 1 : .5,
                 filter: fill ? "brightness(.63) saturate(.7)" : undefined,
               }} />
          {/* o pé DISSOLVE-SE: sem esta camada a ilustração tem uma aresta, e
              uma aresta transforma o retrato do reino num banner.
              ⚠️ Com `fill` o véu é outro, e a cor é a TINTA da onda e não o
              `--bg` global — a [013] §C.4 proíbe esta tela de depender da pele
              global para ter a sua. No PC o véu é horizontal (a leitura fica à
              esquerda, a figura respira à direita); no telemóvel é vertical e
              fecha antes dos recursos. */}
          {fill ? (
            <div style={{
              position: "absolute", inset: 0,
              background: wide
                ? "linear-gradient(90deg,rgba(11,10,12,.92) 0%,rgba(11,10,12,.80) 45%," +
                  "rgba(11,10,12,.20) 100%)"
                : "linear-gradient(180deg,rgba(11,10,12,.55) 0%,rgba(11,10,12,.30) 22%," +
                  "rgba(11,10,12,.80) 62%,rgb(11,10,12) 88%)",
            }} />
          ) : (
            <React.Fragment>
              <div style={{
                position: "absolute", inset: 0,
                background: "linear-gradient(180deg,rgba(var(--bg-rgb),.35) 0%," +
                            "rgba(var(--bg-rgb),.15) 26%,rgba(var(--bg-rgb),.72) 66%," +
                            "rgb(var(--bg-rgb)) 100%)",
              }} />
              <div style={{
                position: "absolute", inset: 0,
                background: "linear-gradient(90deg,rgb(var(--bg-rgb)) 0%,transparent 16%," +
                            "transparent 84%,rgb(var(--bg-rgb)) 100%)",
              }} />
            </React.Fragment>
          )}
        </div>
      );
    }

    function CultivationScene({
      realm, meditating, cbPct, qiPct, cbNow, cbMax, qiNow, qiMax, qiRegenMult,
      realmLabel, medLabel, medMult, remainMs, medTypes, atCeiling,
      onStart, onStop, cta, gender,
    }) {
      const wide = useWideShell();
      const caption = (
        <div style={{ minWidth:0, flex: wide ? 1 : undefined,
                      textAlign: wide ? "left" : "center" }}>
          {meditating ? (
            <div>
              <div style={{ fontFamily:"'Cinzel',serif", fontSize:13, letterSpacing:1,
                            color:"var(--gold3)", display:"flex", gap:8,
                            alignItems:"center", flexWrap:"wrap",
                            justifyContent: wide ? "flex-start" : "center" }}>
                <span>{medLabel}</span>
                {medMult > 0 && <Badge variant="gold">×{medMult.toFixed(1)}</Badge>}
              </div>
              {/* O tempo é o número herói da cena — é a única coisa que muda
                  enquanto se olha, e é literalmente o enredo do género. */}
              <div style={{ fontSize:30, fontWeight:600, lineHeight:1.15, marginTop:4,
                            color:"var(--text)", fontVariantNumeric:"tabular-nums" }}>
                {fmtDuration(remainMs)}
              </div>
              <div style={{ fontSize:10.5, color:"var(--muted)", marginTop:2 }}>
                {t("cena_remaining")}
              </div>
            </div>
          ) : (
            <div>
              <div style={{ fontFamily:"'Cinzel',serif", fontSize:17, letterSpacing:.6,
                            color:"var(--text)" }}>
                {t("cena_idle_title")}
              </div>
              <div style={{ fontSize:11.5, color:"var(--muted)", marginTop:5, lineHeight:1.5 }}>
                {t("cena_idle_body")}
              </div>
            </div>
          )}
        </div>
      );
      return (
        <div style={{ position:"relative", padding: wide ? "6px 4px 20px" : "2px 2px 18px",
                      marginBottom:6, animation:"fade-up .35s ease" }}>
          <RealmBackdrop realm={realm} wide={wide} />
          {/* ⚠️ TODO o conteúdo da cena sobe uma camada. Sem este invólucro os
              fios e os assentos — que são blocos NÃO posicionados — pintavam
              POR BAIXO do fundo posicionado e desapareciam atrás da
              ilustração. Ordem no DOM só decide entre irmãos da mesma
              camada. */}
          <div style={{ position:"relative", zIndex:1 }}>
          <div style={{ display:"flex", alignItems:"center",
                        flexDirection: wide ? "row" : "column",
                        gap: wide ? 34 : 0 }}>
            <div style={{ flexShrink:0 }}>
              <CultivationOrb realm={realm} meditating={meditating} gender={gender} />
            </div>
            {caption}
          </div>

          {/* ⚠️ o rótulo REUSA `cultivation` ("Cultivo") de propósito: é o nome
              que o jogador já lê no cartão de hoje e no chat. Uma cena nova não
              é sítio para rebaptizar o número principal do jogo. */}
          <SceneThread label={t("cultivation")} pct={cbPct} variant="cult"
            left={`${fmtNum(cbNow)} / ${fmtNum(cbMax)}`}
            right={<span style={{ fontSize:10.5, color:"var(--gold2)" }}>{realmLabel}</span>} />
          <SceneThread label={t("qi")} pct={qiPct} variant="qi"
            left={`${fmtNum(qiNow)} / ${fmtNum(qiMax)}`}
            right={qiRegenMult > 1
              ? <Badge variant="jade">×{qiRegenMult.toFixed(1)} qi/s</Badge>
              : <span style={{ fontSize:10.5, color:"var(--muted2)" }}>{Math.round(qiPct)}%</span>} />

          {/* ⚠️ Lei §1 — o cume DITO. Sem esta linha a barra de cima finge uma
              contagem decrescente para a maioria de quem abre a tela. */}
          {atCeiling && (
            <div style={{ marginTop:14, paddingLeft:11,
                          borderLeft:"2px solid rgba(var(--gold-rgb),.35)" }}>
              <div style={{ fontFamily:"'Cinzel',serif", fontSize:11.5,
                            letterSpacing:.8, color:"var(--gold3)" }}>
                {t("cena_ceiling_title")}
              </div>
              <div style={{ fontSize:11, color:"var(--muted)", marginTop:3, lineHeight:1.5 }}>
                {t("cena_ceiling_body")}
              </div>
            </div>
          )}

          {/* ⚠️ Um botão de 1070px é o mesmo erro que os cartões de 514×514 que a
              WEB-D consertou: um ecrã largo serve para mostrar MAIS de uma vez,
              nunca para inchar o que já cabia. Os fios ficam à largura toda (são
              uma MEDIDA, e os números vivem nas duas pontas); a acção não. */}
          <div style={{ maxWidth: wide ? 460 : undefined }}>
            {cta}

            {/* A acção fica na cena. Sentado: interromper. De pé: os assentos —
                os MESMOS quatro, com os mesmos cadeados de reino. */}
            <div style={{ marginTop:16 }}>
              {meditating ? (
                <ActionBtn onClick={onStop} variant="danger" style={{ width:"100%" }}>
                  {t("meditate_stop")}
                </ActionBtn>
              ) : (
                <div>
                  <div style={{ fontSize:9, letterSpacing:".22em", textTransform:"uppercase",
                                color:"var(--muted2)", marginBottom:8 }}>
                    {t("cena_idle_choose")}
                  </div>
                  <div style={{ display:"grid", gap:8, gridTemplateColumns:"1fr 1fr" }}>
                    {medTypes.map(m => {
                      const locked = (realm ?? 0) < m.min_realm;
                      return (
                        <ActionBtn key={m.key} variant="ghost" disabled={locked}
                                   onClick={() => onStart(m.key)}>
                          {locked ? <>{ico("🔒","lock",{ size:12, style:{ display:"inline-block", verticalAlign:"-2px" } })}{" "}{t(m.label_key)}</> : t(m.label_key)}
                        </ActionBtn>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
          </div>
        </div>
      );
    }

    // ═══ 坐 ONDA 1 — O CULTIVADOR JOGÁVEL ═══════════════════════════════════
    // Desenho do Astra: geometria na MESA [011], **a pele e a forma na [013]**.
    // Os dados vêm da medição [010] e das correcções de [012]. Flag
    // `cultivador_jogavel`, OFF em todo o mundo: com ela desligada NADA disto
    // renderiza e a aba desenha o markup de hoje.
    //
    // 🔴 PORQUE HÁ UMA SEGUNDA VERSÃO. A [011] foi implementada à letra e o
    // **owner recusou-a a olhar**, no `s2`, textual: *"Não foi isso que eu vi
    // antes na prévia."* Ele tinha razão, e o diagnóstico é curto: **a [011]
    // descreve GEOMETRIA, e eu construí geometria** — as proporções certas
    // desenhadas com os tokens antigos do mini-app. É a lição de 04/09 ao
    // contrário: dessa vez a FORMA ficou certa e a PELE ficou a velha.
    //
    // A [013] fecha a régua peça por peça e muda cinco coisas de FORMA:
    //   1. no telefone a identidade SAI do lado da figura (largura toda);
    //   2. a paisagem deixa de ser uma faixa no topo;
    //   3. a Base de Cultivo deixa de ser "mais um bloco" e vira o FECHO da
    //      progressão (o limiar, a distância, o ápice e o avanço juntos);
    //   4. S3 perde a moldura e vira secção aberta;
    //   5. as sete modalidades viram lista contínua, sem caixas.
    // 作 A OBRA — a chave-mestra. O owner pediu **UM** interruptor para ligar
    // tudo o que saíu da noite de 15→16/09, em vez de ter de descobrir e ligar
    // cinco chaves espalhadas pelo painel.
    //
    // ⚠️ Ela IMPLICA, nunca SUBSTITUI: quem tem `cultivador_jogavel` ligada
    // sozinha (o `s2`, desde 15/09) continua a ver a tela. A chave-mestra
    // acrescenta mundos; não tira nenhum.
    //
    // ⚠️ E a implicação vive AQUI, num sítio só. Escrever
    // `featureEnabled("a_obra") || featureEnabled("cultivador_jogavel")` em cada
    // componente seria a mesma decisão com dois donos — e foi assim que uma
    // lista de 4 modalidades sobreviveu meses ao lado de um servidor que aceita
    // 7 (Lei 0 §2).
    function ondaCultOn() {
      if (typeof featureEnabled !== "function") return false;
      return featureEnabled("a_obra") || featureEnabled("cultivador_jogavel");
    }

    // ⚠️ A PELE, LOCAL. Decisão explícita da [013] §C: a paleta vive AQUI, num
    // objecto JS lido pelos componentes do recorte — **nunca escrita no `:root`
    // e nunca dependente da `pele_quente`**. Três razões, e a terceira sozinha
    // bastava:
    //   · a `pele_quente` usa OUTROS secundários e preserva os ouros antigos;
    //     ligá-la não entrega estes cinco valores nem a tipografia nem as
    //     molduras;
    //   · escrever no `:root` repintaria o jogo inteiro a partir de uma flag
    //     que só decidiu UMA tela;
    //   · o cartão de recuperação desenha-se ANTES de haver manifesto — tem de
    //     saber a sua cor sem perguntar ao servidor que acabou de falhar.
    var NIV_ONDA = {
      ink:    "#0b0a0c",   // tinta — fundo contínuo, e texto sobre botão claro
      paper:  "#ece5d8",   // papel — nome, números, títulos, o que é principal
      gold:   "#c9903a",   // ouro — reino, selecção, cultivo, foco
      seal:   "#c8442f",   // cinábrio — o fio de HP e as marcas de erro
      muted:  "#baad97",   // secundário — contexto, limites, custos, explicação
      line:   "rgba(236,229,216,.17)",   // o separador e o trilho
      wash:   "rgba(236,229,216,.08)",   // o fundo de um controlo indisponível
      edge:   "rgba(236,229,216,.35)",   // a borda de uma acção secundária
      serif:  "'Cormorant Garamond', Georgia, serif",
      body:   "'Noto Sans', Arial, sans-serif",
      label:  "'Cinzel', Georgia, serif",
    };
    // ⚠️ `Cinzel` SAIU do fallback do Cormorant, e é decisão da [013]: as duas
    // são serifadas mas de carácter oposto, e enquanto a primeira não carrega o
    // título fica com a personalidade errada — não com uma personalidade
    // parecida.

    // Os algarismos, sempre tabulares. Um número que salta de sítio a cada
    // segundo lê-se pior do que um número parado — e isto é uma tela onde o
    // tempo corre à vista.
    var _ONDA_TNUM = {
      fontFamily: NIV_ONDA.body,
      fontVariantNumeric: "tabular-nums",
      fontFeatureSettings: "\"tnum\" 1",
    };

    // ⚠️ O NÚMERO INTEIRO. O `fmtNum` abrevia (`20.67B`) e isso está certo numa
    // lista de 40 linhas — aqui é uma mentira por omissão: o desenho diz, com
    // todas as letras, *"não usar reticências, abreviação obrigatória ou tooltip
    // como único acesso ao número completo"*. E há porquê: o HP de produção tem
    // **12 dígitos** (158.977.287.826), e um jogador que lê `158.98B` não sabe
    // quanto tem — sabe a ordem de grandeza, que é outra coisa.
    //
    // O agrupamento vem da LÍNGUA (pt-BR 158.977.287.826 · en 158,977,287,632),
    // pelo `Intl`, nunca por concatenação à mão. Um browser sem `Intl` cai no
    // número cru em vez de rebentar (Lei §1 — a falha nunca tira o tap).
    var _FULL_LOCALE = { pt: "pt-BR", en: "en-US", es: "es-ES" };
    function fmtFull(n) {
      var v = Number(n);
      if (!isFinite(v)) return "—";
      v = Math.round(v);
      try {
        return v.toLocaleString(_FULL_LOCALE[LANG] || "pt-BR", { useGrouping: true });
      } catch (e) { return String(v); }
    }

    // 🔴 O NÚMERO INTEIRO NUNCA SAI DO ECRÃ (report do [jogador], 03/10/2026: *"in PvE
    // arena, popup of combat shows opponent's hp out of bound on screen"*).
    //
    // O `fmtFull` devolve UMA palavra sem espaço nenhum — `1.212.935.443` — e
    // uma palavra sem ponto de quebra, numa coluna estreita, só tem um destino:
    // transbordar. Aqui o número sai igual, dígito a dígito, mas com um `<wbr>`
    // DEPOIS de cada separador de milhar: se (e só se) a coluna não o couber
    // inteiro, a linha quebra entre grupos (`1.146.050.083.` / `754`) e nunca
    // a meio de um (`1.146.050.083.75` / `4`). Um `<wbr>` não é carácter: o
    // texto copiado, lido ou procurado continua a ser `1.212.935.443`.
    //
    // ⚠️ É o ÚLTIMO recurso, não a forma: quem desenha a coluna dá-lhe largura
    // para o número caber numa linha. Isto só garante que, quando não couber,
    // o número continua dentro do ecrã — inteiro, e legível.
    function fmtFullQuebra(n) {
      var s = fmtFull(n), out = [], buf = "";
      for (var i = 0; i < s.length; i++) {
        var c = s.charAt(i);
        buf += c;
        if ((c < "0" || c > "9") && i < s.length - 1) {
          out.push(buf);
          out.push(<wbr key={"q" + i} />);
          buf = "";
        }
      }
      if (buf) out.push(buf);
      return out;
    }

    // ⚠️ O EMOJI SAI DO NOME EXIBIDO, e só do exibido. As sete modalidades
    // trazem um emoji dentro da própria string traduzida (`🧘 Leve`) porque a
    // origem é o `config.py`, não a i18n. Numa tela cujo desenho é tinta,
    // papel e Cormorant, um pictograma colorido do sistema operativo no meio do
    // nome é o único sítio onde a pele se parte — e parte-se sete vezes, em
    // lista. **A chave e a tradução ficam intactas**; muda o que se pinta.
    var _EMOJI_RE = new RegExp("[\\u2190-\\u21FF\\u2300-\\u27BF\\u2B00-\\u2BFF\\uFE0F\\u20E3]|[\\uD83C-\\uDBFF][\\uDC00-\\uDFFF]", "g");
    function ondaNomeLimpo(s) {
      try { return String(s == null ? "" : s).replace(_EMOJI_RE, "").trim(); }
      catch (e) { return String(s == null ? "" : s).trim(); }
    }

    // ⚠️ UM valor, com o espaço dele RESERVADO. `16ch` de largura mínima e
    // `tabular-nums` são a mesma decisão vista de dois lados: o número não salta
    // de sítio quando muda, e a linha não encolhe quando ele encurta.
    //
    // E o transbordo NÃO se resolve com `ellipsis`: a linha quebra e o valor
    // ocupa a largura toda por baixo do rótulo. Isso é `flexWrap` e mais nada —
    // sem medir texto em JS, sem um `useLayoutEffect` a correr a cada poll de
    // 5s. O bloco cresce; é o que o desenho manda.
    function CultValue({ children, size, lh, weight, color, align }) {
      return (
        <span style={Object.assign({}, _ONDA_TNUM, {
          marginLeft: align === "left" ? 0 : "auto",
          minWidth: "16ch",
          textAlign: align === "left" ? "left" : "right",
          fontSize: size, lineHeight: (lh / size),
          fontWeight: weight || 500,
          color: color || NIV_ONDA.paper,
          whiteSpace: "nowrap",
        })}>{children}</span>
      );
    }

    // ⚠️ O FIO. A [013] substitui a barra de 6px por um trilho de **2px**, cor
    // sólida, pontas rectas — e corta os gradientes, o brilho superior e a
    // sombra luminosa. Não é o `ProgressBar` com outra altura: aquele desenha
    // três gradientes e um véu branco por dentro, e é usado em 14 sítios que
    // NÃO são esta tela. Um `variant` novo lá dentro obrigaria os 14 a carregar
    // uma pele que não é deles.
    //
    // ⚠️ A MARCA DE TRANSBORDO fica FORA da camada que recorta o preenchimento
    // — é a razão de haver duas `<div>` irmãs e não uma aninhada. Ela pode
    // ultrapassar a espessura do fio (2 × 10px, contra 2px de trilho); dentro
    // de um `overflow:hidden` seria cortada exactamente onde precisa de se ver.
    function CultFio({ pct, color, over }) {
      var p = Math.min(100, Math.max(0, Number(pct) || 0));
      return (
        <div style={{ position:"relative", height:10, display:"flex", alignItems:"center" }}>
          <div style={{ position:"relative", width:"100%", height:2,
                        background: NIV_ONDA.line, overflow:"hidden" }}>
            <div style={{ position:"absolute", left:0, top:0, bottom:0,
                          width: p + "%", background: color,
                          transition:"width .4s ease" }} />
          </div>
          {over ? (
            <div aria-hidden="true" style={{
              position:"absolute", right:0, top:0, width:2, height:10,
              background: NIV_ONDA.gold,
            }} />
          ) : null}
        </div>
      );
    }

    // HP e Qi partilham a MESMA anatomia (rótulo + atual · máximo · fio · nota).
    // ⚠️ A Base de Cultivo NÃO usa isto — a [013] separou-a de propósito: ela é
    // o fecho da progressão, não o terceiro de três iguais. Ver `CultFecho`.
    //
    // ⚠️ E os pequenos ícones dos rótulos SAÍRAM. Numa tela que já carrega uma
    // figura principal, três ilustrações de 13px ao lado de três palavras são
    // ruído — a [013] cortou-as, e cortá-las também devolveu a catraca do emoji
    // ao tecto (as três nasceram como `emoji="X"` num prop, que não é porta).
    function CultBlock({ label, now, max, maxLabel, color, pct, over, note,
                         noteTone, wide }) {
      return (
        <div style={{ paddingBottom: 4 }}>
          <div style={{ display:"flex", flexWrap:"wrap", alignItems:"baseline",
                        columnGap:10, rowGap:2 }}>
            <span style={{ flexShrink:0, fontFamily: NIV_ONDA.label,
                           fontSize:11, lineHeight:(16/11), letterSpacing:".12em",
                           textTransform:"uppercase", color: NIV_ONDA.muted }}>
              {label}
            </span>
            <CultValue size={wide ? 22 : 20} lh={wide ? 28 : 26}>{now}</CultValue>
          </div>
          <div style={{ display:"flex", flexWrap:"wrap", alignItems:"baseline",
                        columnGap:10, rowGap:2, marginTop:2 }}>
            <span style={{ flexShrink:0, fontFamily: NIV_ONDA.body, fontSize:12,
                           lineHeight:(18/12), color: NIV_ONDA.muted }}>{maxLabel}</span>
            <CultValue size={16} lh={22} weight={400} color={NIV_ONDA.muted}>{max}</CultValue>
          </div>
          <div style={{ marginTop:6 }}>
            <CultFio pct={pct} color={color} over={over} />
          </div>
          {note ? (
            <div style={{ marginTop:4, fontFamily: NIV_ONDA.body, fontSize:12,
                          lineHeight:(18/12),
                          color: noteTone === "gold" ? NIV_ONDA.gold : NIV_ONDA.muted }}>
              {note}
            </div>
          ) : null}
        </div>
      );
    }

    // S2 — a IDENTIDADE. Nome, reino traduzido, Reino N · Camada M, e o estado
    // dito em palavras.
    //
    // ⚠️ O nome chega aos **63 caracteres** em produção, e por isso ele QUEBRA
    // em vez de cortar: um nome com reticências é um jogador que não se
    // reconhece na própria tela. E não encolhe de fonte para caber — a [013]:
    // *"nome longo cresce em fluxo; não reduzir a fonte para conservar uma
    // altura"*.
    // ⚠️ Os inteiros vêm do servidor já normalizados (`realm or 0`,
    // `sub_layer or 1`) — a interface não consegue recuperar a ausência que o
    // `or` apagou, e não inventa um zero novo por cima.
    function CultIdentity({ name, realmLabel, realm, subLayer, state, stateTone,
                            combatPower, onJump, jumpLabel, wide }) {
      return (
        <div style={{ minWidth:0 }}>
          <div style={{
            fontFamily: NIV_ONDA.serif,
            fontSize: wide ? 60 : 44, lineHeight: wide ? 1 : (46/44),
            fontWeight:400, letterSpacing:"-.025em", color: NIV_ONDA.paper,
            overflowWrap:"anywhere", wordBreak:"break-word",
          }}>{name}</div>
          <div style={{ fontFamily: NIV_ONDA.body, fontWeight:500,
                        fontSize: wide ? 16 : 14, lineHeight: wide ? (24/16) : (20/14),
                        color: NIV_ONDA.gold, marginTop:8 }}>
            {realmLabel}
          </div>
          <div style={{ fontFamily: NIV_ONDA.body, fontWeight:400,
                        fontSize: wide ? 14 : 13, lineHeight: wide ? (22/14) : (20/13),
                        color: NIV_ONDA.muted }}>
            {t("onda_realm_layer", { realm: realm, sub: subLayer })}
          </div>
          <div style={{ fontFamily: NIV_ONDA.body, fontSize:14, lineHeight:(22/14),
                        marginTop:12,
                        color: stateTone === "active" ? NIV_ONDA.paper : NIV_ONDA.muted }}>
            {state}
          </div>
          {/* ⚠️ A operação ficou LONGE. Com a identidade a ocupar a largura toda
              e a paisagem a seguir, S3 caiu bem abaixo da primeira dobra — e a
              coisa que o jogador veio fazer não pode exigir uma viagem às
              cegas. Um salto textual, com área de toque de 44px, é o que a
              [013] pediu em vez de comprimir a abertura. */}
          {onJump ? (
            <button type="button" onClick={onJump}
              style={{ marginTop:6, minHeight:44, padding:"0 0", background:"none",
                       border:"none", cursor:"pointer", textAlign:"left",
                       fontFamily: NIV_ONDA.body, fontSize:14, lineHeight:(22/14),
                       fontWeight:500, color: NIV_ONDA.gold }}>
              {jumpLabel}
            </button>
          ) : null}
          {/* ⚠️ O PODER DE COMBATE, e só quando o mundo o calcula. Leitura
              SECUNDÁRIA junto à identidade, longe do limiar: o limiar compara-se
              com a `cultivation_base` e ao lado dele o Poder faria a barra
              mentir (MESA [012]). A ausência não reserva espaço. */}
          {combatPower != null ? (
            <div style={{ display:"flex", alignItems:"baseline", gap:8, marginTop:10 }}>
              <span style={{ fontFamily: NIV_ONDA.body, fontSize:12, lineHeight:(18/12),
                             color: NIV_ONDA.muted }}>{t("battle_power")}</span>
              <span style={Object.assign({}, _ONDA_TNUM, {
                fontSize:12, lineHeight:(18/12), fontWeight:500, color: NIV_ONDA.paper,
              })}>{fmtFull(combatPower)}</span>
            </div>
          ) : null}
        </div>
      );
    }

    // S1 — as ÂNCORAS da aba. Saltam para secções que EXISTEM; nunca recolhem
    // conteúdo nenhum.
    //
    // ⚠️ Só são desenhadas as âncoras cuja secção está mesmo na página, e a
    // faixa inteira desaparece abaixo de duas. As três secções do Cultivo são
    // CONDICIONAIS (a Prática pede reino 5 ou elegibilidade de Recomeço; os
    // Caminhos pedem reino 4 ou prestígio) — uma âncora fixa levaria um jogador
    // novo a tocar num destino que não existe, que é a Lei §1 partida pela
    // decoração.
    // ⚠️ E NÃO há estado "seleccionado": a [013] proibiu-o por uma razão que é
    // honestidade, não estética — marcar uma secção como activa sem seguir a
    // posição real da página seria a tela a afirmar onde você está sem saber.
    function CultAnchors({ items, wide }) {
      var live = (items || []).filter(function (a) { return a && a.present; });
      if (live.length < 2) return null;
      function jump(id) {
        haptic("select");
        var el = null;
        try { el = document.getElementById(id); } catch (e) { el = null; }
        if (!el) return;
        try {
          var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
          el.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block:"start" });
        }
        catch (e) { try { el.scrollIntoView(); } catch (e2) {} }
      }
      return (
        <div role="navigation" aria-label={t("onda_anchors_aria")}
             style={{ display:"flex", gap:20, alignItems:"stretch",
                      marginBottom: wide ? 20 : 12 }}>
          {live.map(function (a) {
            return (
              <button key={a.key} type="button" onClick={function () { jump(a.id); }}
                style={{
                  minWidth:0, minHeight:44, cursor:"pointer",
                  background:"none", border:"none", padding:0,
                  color: NIV_ONDA.muted, fontFamily: NIV_ONDA.body,
                  fontSize:12, lineHeight:(18/12), fontWeight:500,
                  letterSpacing:".02em", textAlign:"left",
                  display:"flex", alignItems:"center", gap:6,
                  whiteSpace:"nowrap", overflow:"hidden",
                }}>
                <span aria-hidden="true" style={{ fontSize:13, color: NIV_ONDA.gold,
                                                  lineHeight:1 }}>{a.glyph}</span>
                <span style={{ overflow:"hidden", textOverflow:"ellipsis" }}>{a.label}</span>
              </button>
            );
          })}
        </div>
      );
    }

    // ⚠️ O BOTÃO da onda. Papel sólido com texto em tinta, raio ZERO, sem
    // sombra, sem gradiente, sem textura. Não é o `ActionBtn` com props: aquele
    // é usado em **345 sítios** e carrega o gradiente, o raio e a borda dourada
    // que esta tela foi cortar — dar-lhe uma variante nova era pôr 344 ecrãs a
    // carregar uma pele que não é deles (a [013] §C.2 diz o mesmo pelo outro
    // lado: "os estilos internos também precisam respeitar a variante").
    //
    // ⚠️ Durante o envio a PALAVRA fica ("Iniciando…"), nunca um spinner no
    // lugar dela: um botão que perde o texto é um botão que deixou de dizer o
    // que está a fazer.
    // 宗 4.1 — `ariaLabel` opcional: quando o texto visível é curto ("250
    // pedras" / "+10"), o nome inteiro do gesto vai para o leitor de ecrã. Sem
    // ele o React não escreve o atributo — os botões de hoje ficam iguais.
    function OndaBtn({ children, onClick, kind, disabled, style, ariaLabel }) {
      var base = {
        minHeight:48, padding:"12px 20px", borderRadius:0, width:"100%",
        fontFamily: NIV_ONDA.body, fontSize:13, lineHeight:(20/13),
        fontWeight:500, letterSpacing:".02em", textAlign:"center",
        cursor: disabled ? "default" : "pointer", transition:"border-color .15s",
        boxShadow:"none", backgroundImage:"none",
      };
      var skin = disabled
        ? { background: NIV_ONDA.wash, color: NIV_ONDA.muted,
            border:"1px solid " + NIV_ONDA.line }
        : (kind === "ghost"
            ? { background:"transparent", color: NIV_ONDA.paper,
                border:"1px solid " + NIV_ONDA.edge }
            : { background: NIV_ONDA.paper, color: NIV_ONDA.ink,
                border:"1px solid transparent" });
      return (
        <button type="button" disabled={!!disabled} aria-label={ariaLabel}
                onClick={disabled ? undefined : onClick}
                style={Object.assign(base, skin, style || {})}>
          {children}
        </button>
      );
    }

    // ═══ 減 P7 — A REDUÇÃO PROGRESSIVA ══════════════════════════════════════
    //
    // A decisão é do Astra (MESA [017] §4), textual: *"Depois de uma acção
    // bem-sucedida nesse sistema, oferecer «Já percebi»: a frase introdutória
    // recolhe; «Ajuda» permite recuperá-la. Sem presumir domínio pelo tempo de
    // conta e SEM MUDAR A POSIÇÃO DOS COMANDOS."* E o que fica sempre: rótulo,
    // valor, limiar, custo, duração, bloqueio, consequência confirmada.
    //
    // 🔴 O REGISTO. Contaram-se as 242 chaves que as telas da onda mostram e
    // só SEIS explicam sem carregar número nem motivo (a pergunta: *"se ela
    // sumir, o jogador perde um NÚMERO ou um MOTIVO?"*). São estas, e mais
    // nenhuma. A guarda §30 descobre sozinha todo sítio do cliente que desenha
    // uma destas chaves e exige que passe pelo `Explica` — uma frase nova aqui
    // acusa, no dia em que entra, quem a mostra sem a poder recolher.
    //
    // ⚠️ VIDA/QI NÃO ESTÁ AQUI, e é medição, não esquecimento: nas telas da
    // onda não há UMA dica de Vida/Qi escrita — só rótulo, número, estado e a
    // recusa com o caminho de saída (`combat_hp_way_out`). Tudo isso é prova.
    //
    // ⚠️ O Corpo são três sistemas: cada camada tem a sua acção e a sua frase.
    // Recolher os meridianos a quem só forjou a carne seria presumir domínio.
    //
    // ⚠️ A lista de SISTEMAS é a mesma do servidor (`core/explicacoes.SISTEMAS`)
    // — é lá que o gatilho vive — e a guarda compara as duas.
    var EXPLICA = {
      meditar:      ["chegada_porque_meditar", "chegada_porque_meditacao"],
      equipar:      ["cena_entrada_com"],
      corpo_mortal: ["corpo_explica_mortal"],
      corpo_transf: ["corpo_explica_transf"],
      corpo_mer:    ["corpo_explica_mer"],
    };

    // O estado LIDO do `/player` (`player.explicacoes`). ⚠️ Sem preferência lida
    // nunca é "recolhido": um payload sem a chave (onda OFF, ou o pedido que
    // falhou) devolve `null` e a frase APARECE — mostrar a mais é honesto,
    // esconder sem saber era a opção (c) outra vez.
    function explicaEstado(estados, sistema) {
      if (!estados || typeof estados !== "object") return null;
      var v = estados[sistema];
      return (v === "apto" || v === "recolhido") ? v : null;
    }

    // Os dois botões de texto. ⚠️ O alvo tem 44px de altura e NÃO mexe na
    // linha: `inline-block` com o padding compensado por margem negativa — a
    // caixa de toque cresce, a caixa da linha não. Sem isto, a primeira vez
    // que «Já percebi» aparecesse empurrava o comando de baixo, que é o que a
    // decisão proíbe.
    var _EXPLICA_BTN = {
      display:"inline-block", padding:"13px 6px", margin:"-13px -6px",
      background:"none", border:"none", cursor:"pointer",
      fontFamily: NIV_ONDA.body, fontSize:12, lineHeight:(18/12), fontWeight:500,
      color: NIV_ONDA.gold, textDecoration:"underline", textUnderlineOffset:3,
      whiteSpace:"nowrap",
    };

    // 🔴 O COMANDO NÃO MUDA DE POSIÇÃO — e é a geometria que o garante, não a
    // disciplina de cada sítio. As duas camadas (a frase com «Já percebi»; a
    // «Ajuda») vivem na MESMA célula de uma grelha: a altura é a da maior, nos
    // quatro estados (primeira vez · depois da acção · recolhida · «Ajuda»
    // aberta). Recolher troca o que se LÊ; a caixa fica.
    //   · «Já percebi» existe sempre na camada da frase — invisível enquanto o
    //     servidor não confirmar a acção — para a linha já ter o seu tamanho
    //     final antes de ele aparecer;
    //   · `visibility`, nunca `display`: o que está escondido continua a medir,
    //     e sai da ordem de tabulação e da árvore de acessibilidade.
    //
    // 🔴 SÓ O CONFIRMADO CONTA. O toque em «Já percebi» pede ao servidor; a
    // frase recolhe quando a RESPOSTA diz "recolhido". Até lá fica — e se a
    // rede falhar, fica (nada muda sem ok).
    // ⚠️ `conf` guarda essa resposta contra o payload que estava na mão quando
    // se tocou (`base`). Quando o `/player` refrescado chega, é um objecto novo
    // e a verdade volta a ser a dele — uma segunda cópia do estado nunca
    // sobrevive ao pedido que a confirmou.
    function Explica({ sistema, estados, onRefresh, children }) {
      const [aberta, setAberta] = useState(false);
      const [busy, setBusy] = useState(false);
      const [conf, setConf] = useState(null);
      const lido = explicaEstado(estados, sistema);
      const est = (conf && conf.base === estados) ? conf.estado : lido;
      const recolhida = est === "recolhido" && !aberta;
      const oferece = est === "apto" || (est === "recolhido" && aberta);

      async function recolher() {
        if (busy) return;
        // Com a «Ajuda» aberta o servidor já disse "recolhido": fechar é só
        // desta vista, e não gasta um pedido.
        if (est === "recolhido") { setAberta(false); return; }
        setBusy(true);
        try {
          const r = await api("settings/update", { explicacao_recolher: sistema });
          const novo = (r && r.ok && r.explicacoes) ? r.explicacoes[sistema] : null;
          if (novo === "recolhido") {
            haptic("select");
            setConf({ base: estados, estado: novo });
            setAberta(false);
            if (onRefresh) onRefresh();
          } else {
            // Lei §1 — um toque que não faz nada tem de o DIZER. Visto a
            // servir com o pedido a falhar: a frase ficava (certo) e o
            // jogador não sabia porquê.
            haptic("error");
            showToast(t("settings_explica_erro"), "err");
          }
        } catch (e) {
          // Sem resposta, nada muda: a frase continua à vista — e diz-se.
          haptic("error");
          showToast(t("settings_explica_erro"), "err");
        } finally {
          setBusy(false);
        }
      }

      return (
        <span className="explica" style={{ display:"grid", gridTemplateColumns:"minmax(0,1fr)" }}>
          <span style={{ gridArea:"1 / 1", minWidth:0,
                         visibility: recolhida ? "hidden" : "visible" }}>
            {children}{" "}
            <button type="button" onClick={recolher} disabled={!oferece || busy}
                    aria-label={t("explica_ja_percebi_aria")}
                    style={Object.assign({}, _EXPLICA_BTN,
                                         { visibility: oferece ? "visible" : "hidden" })}>
              {t("explica_ja_percebi")}
            </button>
          </span>
          <span style={{ gridArea:"1 / 1", minWidth:0,
                         visibility: recolhida ? "visible" : "hidden" }}>
            <button type="button" onClick={() => { haptic("select"); setAberta(true); }}
                    aria-label={t("explica_ajuda_aria")}
                    style={_EXPLICA_BTN}>
              {t("explica_ajuda")}
            </button>
          </span>
        </span>
      );
    }

    // S1 — o CARTÃO DE RECUPERAÇÃO (variantes 3 e 4 do desenho).
    //
    // ⚠️ MEDIDO: o cliente fazia `catch (e) { setError(e.message) }` e o
    // `ErrBanner` mostrava a string crua. O 401 do mini-app é
    // `_err("unauthorized", 401)`, portanto quem tinha a sessão expirada lia
    // literalmente **"unauthorized"** — uma palavra em inglês, num jogo em
    // português, que não diz o que fazer a seguir. Os motivos SEMPRE chegaram
    // ao cliente; o que faltava era encanamento, e é este.
    //
    // ⚠️ E a saída é POR PLATAFORMA, porque só uma delas tem porta: no browser
    // o `api()` já redirecciona para o `/login` com `next` de volta — aqui o
    // botão é a mesma viagem, à mão, para quem caiu no ecrã antes do salto. No
    // Telegram não há `/login` nenhum: a sessão vem do `initData` e a única
    // recuperação verdadeira é reabrir pelo bot. Oferecer "Entrar novamente"
    // lá dentro seria um botão que não faz nada.
    //
    // ⚠️ A pele aqui é AUTÓNOMA ([013] §C.3) e isso não é repetição: esta
    // superfície desenha-se antes de haver manifesto, portanto não pode
    // perguntar a uma flag que chega dentro do pedido que acabou de falhar.
    var _SESSION_ERRS = ["unauthorized", "session_expired", "login_invalid", "HTTP 401"];
    function CultRecovery({ error, onRetry, wide }) {
      var raw = String(error == null ? "" : error);
      var isSession = _SESSION_ERRS.indexOf(raw) >= 0;
      var inTelegram = !!(typeof tg !== "undefined" && tg && tg.initData);
      var title = isSession ? t("onda_rec_session_title") : t("onda_rec_error_title");
      // ⚠️ O MESMO dono do `ErrBanner`: o motivo tem de ler igual nos dois
      // sitios, senao o jogador ve duas frases para a mesma falha.
      var _traduzido = typeof apiErroTexto === "function" ? apiErroTexto(raw) : raw;
      var body = isSession
        ? (inTelegram ? t("onda_rec_session_telegram") : t("onda_rec_session_browser"))
        : (_traduzido !== raw ? _traduzido : t("onda_rec_error_body"));
      return (
        <div style={{ maxWidth: wide ? 448 : 358, margin:"32px auto 0",
                      background: NIV_ONDA.ink }}>
          {/* ⚠️ O rectângulo vermelho SAIU. Um traço de 32×2px diz a mesma
              coisa sem transformar uma recuperação num alarme — e o cinábrio
              continua a ser a cor do erro, só que como acento, não como caixa. */}
          <div aria-hidden="true" style={{ width:32, height:2, background: NIV_ONDA.seal }} />
          <div style={{ marginTop:16, fontFamily: NIV_ONDA.serif,
                        fontSize: wide ? 32 : 28, lineHeight: wide ? (36/32) : (32/28),
                        fontWeight:400, letterSpacing:"-.02em", color: NIV_ONDA.paper }}>
            {title}
          </div>
          <div style={{ marginTop:10, fontFamily: NIV_ONDA.body, fontSize:13,
                        lineHeight:(21/13), color: NIV_ONDA.muted }}>{body}</div>
          {/* O motivo cru fica VISÍVEL mas em segundo plano: é o que o jogador
              cola num report, e é o que nos poupa uma sessão de adivinhação. */}
          {raw ? (
            <div style={{ marginTop:10, fontFamily: NIV_ONDA.body, fontSize:12,
                          lineHeight:(18/12), color: NIV_ONDA.muted, opacity:.75 }}>
              {t("onda_rec_reason", { reason: raw })}
            </div>
          ) : null}
          <div style={{ display:"flex", gap:12, marginTop:20, flexWrap:"wrap" }}>
            <OndaBtn onClick={onRetry} style={{ flex:"1 1 140px", width:"auto" }}>
              {t("onda_rec_retry")}
            </OndaBtn>
            {isSession && !inTelegram && (
              <OndaBtn kind="ghost" style={{ flex:"1 1 140px", width:"auto" }}
                onClick={function () {
                  try {
                    var back = encodeURIComponent(window.location.pathname + window.location.search);
                    window.location.replace(LOGIN_URL + "?next=" + back);
                  } catch (e) {}
                }}>
                {t("onda_rec_login")}
              </OndaBtn>
            )}
          </div>
        </div>
      );
    }

    // ─── S2 — A SÍNTESE DO CULTIVADOR ────────────────────────────────────────
    // É CENA, não cartão: a pessoa ocupa a paisagem e os recursos pousam sobre
    // tinta contínua, com fios finos a separar. Uma moldura à volta disto
    // devolvia-a ao muro de caixas iguais que a onda foi corrigir.
    //
    // 🔴 O QUE A [013] REVOGOU da [011], e é o que o owner viu de relance:
    //   · **a abertura de 176px no telefone.** Ela comprimia a identidade e
    //     reduzia a figura a um acessório. A identidade passa a ocupar a
    //     largura toda e a paisagem vem A SEGUIR, com 208px no mínimo.
    //   · **a barra de 6px.** Vira um fio de 2px, cor sólida, sem gradiente.
    //   · **a Base de Cultivo como terceiro bloco igual.** Vira o FECHO.
    //
    // Reaproveita a paisagem (`RealmBackdrop`) e a figura (`CultivationOrb`).
    // Zero arte nova — é a ordem do desenho.
    //
    // 🔴 A CORRECÇÃO QUE CUSTA MAIS SE FOR IGNORADA (MESA [012]): **CB não é
    // Poder de Combate.** O limiar do avanço compara-se com a `cultivation_base`
    // (`config.py:75` não vê combate nenhum; o servidor compara
    // `player.cultivation_base >= threshold`). O Poder vive junto à identidade,
    // longe do limiar, e não existe quando o mundo não o calcula
    // (`display_combat_power` vem `null` com `progressao_visivel` OFF, que é o
    // estado do `main`).
    function CultivationSynthesis({
      name, realm, subLayer, realmLabel, meditating, medLabel, remainMs,
      hpNow, hpMax, qiNow, qiMax, cbNow, cbMax, combatPower,
      gender, atCeiling, cta, wide, onJumpMeditar,
    }) {
      // ⚠️ `current_hp` NULL significa **CHEIO**, nunca zero. Um `COALESCE(…, 0)`
      // já inventou uma vez "69% dos activos sem poder lutar"; re-medido, eram
      // zero. A resolução vive AQUI, num sítio só.
      var maxHp = Number(hpMax) || 0;
      var curHp = (hpNow === null || hpNow === undefined) ? maxHp : Number(hpNow);
      var hpPct = maxHp > 0 ? (curHp / maxHp) * 100 : 0;

      var qiN = Number(qiNow) || 0, qiM = Number(qiMax) || 0;
      var qiPct = qiM > 0 ? (qiN / qiM) * 100 : 0;
      var qiOver = qiM > 0 && qiN > qiM;

      var cbN = Number(cbNow) || 0, cbM = Number(cbMax) || 0;
      var cbPct = cbM > 0 ? (cbN / cbM) * 100 : 0;
      var cbOver = cbM > 0 && cbN > cbM;

      var stateLine = meditating
        ? t("onda_state_meditating", { name: ondaNomeLimpo(medLabel),
                                       time: fmtDuration(remainMs) })
        : t("onda_state_idle");

      // ── A ABERTURA: quem você é ──
      var identidade = (
        <CultIdentity name={name} realmLabel={realmLabel} realm={realm}
                      subLayer={subLayer} state={stateLine}
                      stateTone={meditating ? "active" : null}
                      combatPower={combatPower}
                      onJump={onJumpMeditar}
                      jumpLabel={meditating ? t("onda_jump_ver") : t("onda_jump_meditar")}
                      wide={wide} />
      );

      // ── A PAISAGEM + A FIGURA ──
      // ⚠️ A figura é a MESMA (`CultivationOrb` → `CultivatorFigure`), com a
      // lei dela intacta: só existe SENTADA. De pé o que se vê é o LUGAR à
      // espera — e é isso que faz sentar-se ser o momento em que você aparece
      // no mundo. A variante local só lhe tira os anéis e as partículas e
      // deixa-lhe uma respiração de opacidade ([013] §B.2).
      var figura = (
        <div style={{ minHeight: wide ? 456 : 208, display:"flex",
                      alignItems:"center", justifyContent:"center" }}>
          <CultivationOrb realm={realm} meditating={meditating} gender={gender}
                          size={wide ? 360 : 192} plain />
        </div>
      );

      // ── OS RECURSOS ──
      var recursos = (
        <div>
          <CultBlock label={t("onda_hp_label")}
                     now={fmtFull(curHp)} max={fmtFull(maxHp)}
                     maxLabel={t("onda_hp_max")} color={NIV_ONDA.seal}
                     pct={hpPct} wide={wide} />
          <div style={{ height:16 }} />
          <CultBlock label={t("qi")}
                     now={fmtFull(qiN)} max={fmtFull(qiM)}
                     maxLabel={t("onda_qi_cap")} color={NIV_ONDA.paper}
                     pct={qiPct} over={qiOver}
                     note={qiOver ? t("onda_qi_over", { mult: (qiN / qiM).toFixed(2) }) : null}
                     noteTone={qiOver ? "gold" : null}
                     wide={wide} />

          {/* ── O FECHO DA PROGRESSÃO ──
              ⚠️ A [013] tirou a Base de Cultivo da fila dos iguais. Ela não é
              "mais um recurso": é o número que decide se você sobe. Por isso
              ganha título próprio em Cormorant, alinha à ESQUERDA (os outros
              dois alinham à direita, e a diferença é deliberada — esta lê-se,
              as outras comparam-se), e traz para dentro dela o limiar, a
              distância, o aviso do cume e o acionador do avanço. */}
          <div style={{ marginTop:24 }}>
            <div style={{ fontFamily: NIV_ONDA.serif, fontWeight:500,
                          fontSize: wide ? 28 : 24, lineHeight: wide ? (32/28) : (28/24),
                          letterSpacing:"-.01em", color: NIV_ONDA.paper }}>
              {t("onda_cb_label")}
            </div>
            <div style={{ display:"flex", flexWrap:"wrap", alignItems:"baseline",
                          columnGap:10, rowGap:2, marginTop:8 }}>
              <CultValue size={wide ? 26 : 24} lh={wide ? 32 : 30} align="left">
                {fmtFull(cbN)}
              </CultValue>
            </div>
            <div style={{ display:"flex", flexWrap:"wrap", alignItems:"baseline",
                          columnGap:8, rowGap:2, marginTop:2 }}>
              <span style={{ flexShrink:0, fontFamily: NIV_ONDA.body, fontSize:12,
                             lineHeight:(18/12), color: NIV_ONDA.muted }}>
                {t("onda_cb_threshold")}
              </span>
              <CultValue size={16} lh={22} weight={400} color={NIV_ONDA.muted} align="left">
                {fmtFull(cbM)}
              </CultValue>
            </div>
            <div style={{ marginTop:8 }}>
              <CultFio pct={cbPct} color={NIV_ONDA.gold} over={cbOver} />
            </div>
            {/* ⚠️ `!atCeiling` — no cume esta linha CALA-SE. Ver a nota do
                aviso, logo abaixo: dizer "faltam 136.000 para o limiar" dois
                centímetros acima de "encher esta barra já não abre avanço
                nenhum" é a tela a desmentir-se a si própria. */}
            {cbM > 0 && !atCeiling ? (
              <div style={{ marginTop:4, fontFamily: NIV_ONDA.body, fontSize:12,
                            lineHeight:(18/12),
                            color: cbN >= cbM ? NIV_ONDA.gold : NIV_ONDA.muted }}>
                {/* ⚠️ Alcançar o limiar NÃO autoriza, sozinho, anunciar "avanço
                    disponível" — essa decisão continua nos fluxos próprios
                    (prova, núcleo, tribulação). A linha diz o FACTO; o acionador
                    abaixo aparece quando o jogo o autoriza. */}
                {cbN >= cbM ? t("onda_cb_reached") : t("onda_cb_left", { n: fmtFull(cbM - cbN) })}
              </div>
            ) : null}

            {/* ⚠️ Lei §1 — o cume DITO, e agora no sítio certo. Em reino 10
                camada 9 a base fica presa no limiar e encher a barra não produz
                evento nenhum; sem esta linha ela finge uma contagem decrescente
                para a maioria de quem abre a tela (**21 dos 37 activos-30d do
                `main`, 57%**). A [013] tirou-a da posição de apêndice e pô-la
                aqui, que é onde a pergunta nasce.
                ⚠️ E é por isso que a linha da distância se cala acima: as duas
                juntas diziam "falta X" e "X não serve para nada" à mesma
                pessoa, no mesmo ecrã, com quatro pixels entre elas. */}
            {atCeiling && (
              <div style={{ marginTop:12 }}>
                <div style={{ fontFamily: NIV_ONDA.serif, fontWeight:500,
                              fontSize:22, lineHeight:(26/22), color: NIV_ONDA.paper }}>
                  {t("cena_ceiling_title")}
                </div>
                <div style={{ marginTop:4, fontFamily: NIV_ONDA.body, fontSize:12,
                              lineHeight:(18/12), color: NIV_ONDA.muted }}>
                  {t("cena_ceiling_body")}
                </div>
              </div>
            )}

            {/* ⚠️ Um botão de 1070px é o mesmo erro dos cartões de 514×514 que a
                WEB-D consertou: um ecrã largo serve para mostrar MAIS de uma vez,
                nunca para inchar o que já cabia. */}
            <div style={{ maxWidth: wide ? 460 : undefined, marginTop:12 }}>
              {cta}
            </div>
          </div>
        </div>
      );

      // ⚠️ A PAISAGEM deixa de ser uma faixa. `fill` faz o fundo acompanhar a
      // altura da cena inteira, e o véu por cima é que decide onde a imagem
      // desaparece — nunca uma aresta rectangular ([013] §B.2).
      return (
        <div style={{ position:"relative", background: NIV_ONDA.ink,
                      marginBottom:8, animation:"fade-up .35s ease" }}>
          <RealmBackdrop realm={realm} wide={wide} fill />
          {/* ⚠️ TODO o conteúdo sobe uma camada: sem este invólucro os blocos
              não-posicionados pintam POR BAIXO do fundo posicionado e somem
              atrás da ilustração (lição da cena de 02/09). */}
          <div style={{ position:"relative", zIndex:1 }}>
            {wide ? (
              /* PC — identidade/recursos à esquerda (360px), figura ao lado,
                 a acompanhar toda a coluna de leitura. */
              <div style={{ display:"flex", gap:32, alignItems:"flex-start",
                            padding:"24px 24px 24px 0" }}>
                <div style={{ width:360, flexShrink:0 }}>
                  {identidade}
                  <div style={{ marginTop:32 }}>{recursos}</div>
                </div>
                <div style={{ flex:1, minWidth:0 }}>{figura}</div>
              </div>
            ) : (
              <div style={{ padding:"16px 16px 24px" }}>
                {identidade}
                <div style={{ marginTop:16 }}>{figura}</div>
                <div style={{ marginTop:24 }}>{recursos}</div>
              </div>
            )}
          </div>
        </div>
      );
    }

    // ─── S3 — A SECÇÃO OPERACIONAL DA MEDITAÇÃO ──────────────────────────────
    // ⚠️ A [013] revogou o "cartão" da [011]: **S3 é uma secção ABERTA**. Fundo
    // tinta, sem contorno nos quatro lados, sem cantos ornamentais, sem raio,
    // sem textura e sem sombra — um separador e mais nada. E não bastava passar
    // `ornate={false}` ao `Card`: ele continua a desenhar fundo, borda, brilho
    // superior e textura.
    //
    // 🔴 O DEFEITO QUE ISTO FECHA, e é o maior da onda: o cliente desenhava
    // **4** modalidades (`medTypes`, uma lista literal em `tabs.js`) e o
    // servidor aceita **7**. As três em falta — `dao_basic` (reino 5),
    // `dao_deep` (6) e `dao_transcend` (8) — são práticas que o jogador
    // destranca ao subir e que a superfície canónica NUNCA lhe mostrou. O
    // catálogo passa a vir do servidor (`_meditation_catalog`, do mesmo
    // `config.py` que o `api_meditate_start` valida): UM dono.
    //
    // ⚠️ O vazio desta tela NÃO é alcançável, e é medido: a `light` tem
    // `min_realm` 0 e `qi_cost` 0, logo todo o jogador, em todo o reino, com
    // zero qi, tem sempre uma linha aberta. Não há tela de vazio para desenhar
    // — e um catálogo que chegasse vazio é uma falha de dados, não um estado.
    function MeditationRow({ row, locked, lockWhy, selected, onSelect, disabled }) {
      var isDao = row.dao_fragment_mult != null;
      var nome = ondaNomeLimpo(
        t("meditation_" + (row.key === "celestial_dao" ? "celestial" : row.key)));
      return (
        <button type="button" role="radio" aria-checked={!!selected}
          disabled={!!disabled}
          onClick={function () { if (!disabled) { haptic("select"); onSelect(row.key); } }}
          style={{
            width:"100%", minHeight:88, textAlign:"left",
            cursor: disabled ? "default" : "pointer",
            display:"flex", alignItems:"flex-start", gap:0,
            padding:"12px 0", margin:0,
            background:"none", border:"none",
            borderBottom:"1px solid " + NIV_ONDA.line,
            borderRadius:0, font:"inherit", color: NIV_ONDA.paper,
          }}>
          {/* ⚠️ A faixa esquerda de 20px existe SEMPRE, com ou sem selecção: é
              o que impede a lista de saltar 20px para o lado quando se escolhe
              uma linha. O traço mora nela. */}
          <span aria-hidden="true" style={{ flexShrink:0, width:20,
                                            alignSelf:"stretch", display:"flex",
                                            alignItems:"center" }}>
            {selected ? (
              <span style={{ width:2, height:24, background: NIV_ONDA.gold }} />
            ) : null}
          </span>
          <span style={{ minWidth:0, flex:1 }}>
            <span style={{ display:"block", fontFamily: NIV_ONDA.serif, fontWeight:500,
                           fontSize:22, lineHeight:(26/22),
                           color: locked ? NIV_ONDA.muted
                                : (selected ? NIV_ONDA.gold : NIV_ONDA.paper) }}>
              {nome}
            </span>
            {/* 🔴 O QUE DECIDE A ESCOLHA, na linha QUE JA' EXISTIA.
                Ordem do owner, 16/09 06:20, com a tela dele a' frente: *"muito
                grande essa tela (...) a pessoa nao tem que buscar (...) cria
                icone"*. A 1a versao disto era uma linha nova — +18px x 7 filas
                = +126px numa lista que ja' nao cabia no ecra. Entregar o facto
                e piorar a tela ao mesmo tempo nao e' entregar o facto.
                Medido no `config.py` (`RESTRICTED_MEDITATION`, linha 157):
                cinco das sete trancam o combate, duas nao — e nenhuma o dizia.
                E' o unico facto que separa mesmo as praticas: somando
                `multiplier` x `duration`, a Void rende 12,0 de graca contra 2,5
                por 50 Qi da Deep, logo a unica pergunta real e' *"quero
                continuar a lutar?"*.
                ⚠️ 2026-09-22 — A COLUNA SAIU, e o facto com ela: a
                sugestao do [jogador] (*"when meditating, I can do Arena battle but
                not NPC battle. Why?"*) mediu que a trava vivia em 6 portas e
                faltava em 15. Unificou-se pelo lado permissivo, portanto
                nenhuma pratica tranca combate e escrever "livre" em todas era
                ruido. O servidor deixou de mandar `restricts_combat`. */}
            <span style={{ display:"flex", alignItems:"center", flexWrap:"wrap",
                           columnGap:6, fontFamily: NIV_ONDA.body, fontSize:12,
                           lineHeight:(18/12), color: NIV_ONDA.muted, marginTop:4 }}>
              <span>
                {t("onda_med_line", {
                  dur: t("onda_med_minutes", { n: row.duration_minutes }),
                  qi: t("onda_med_cost", { n: fmtFull(row.qi_cost) }),
                })}
              </span>
            </span>
            {/* ⚠️ O que o servidor NÃO manda, a linha não escreve: uma
                meditação de Dao tem `multiplier` 0.0 (é verdade, não ausência)
                e dá fragmentos; as outras não trazem `dao_fragment_mult`. */}
            <span style={{ display:"block", fontFamily: NIV_ONDA.body, fontSize:12,
                           lineHeight:(18/12), color: NIV_ONDA.muted, marginTop:2 }}>
              {isDao
                ? t("onda_med_dao_mult", { n: row.dao_fragment_mult.toFixed(1) })
                : t("onda_med_cb_mult", { n: row.multiplier.toFixed(1) })}
            </span>
            {/* ⚠️ A linha trancada CONTINUA LEGÍVEL — o motivo em PAPEL, não em
                cinzento: a [013] cortou o `opacity:.72`, porque baixar a
                opacidade de uma linha esconde exactamente a informação que ela
                existe para dar (o que falta para a destrancar). */}
            {locked && lockWhy ? (
              <span style={{ display:"flex", alignItems:"center", gap:6, marginTop:6,
                             fontFamily: NIV_ONDA.body, fontSize:12,
                             lineHeight:(18/12), color: NIV_ONDA.paper }}>
                <span style={{ color: NIV_ONDA.muted, display:"inline-flex", flexShrink:0 }}>
                  {<Mark name="lock" size={16} />}
                </span>
                <span>{lockWhy}</span>
              </span>
            ) : null}
          </span>
          {selected && !locked ? (
            <span style={{ color: NIV_ONDA.gold, display:"inline-flex", flexShrink:0,
                           marginLeft:10, marginTop:2 }}>
              {<Mark name="check" size={16} />}
            </span>
          ) : null}
        </button>
      );
    }

    // ⚠️ As cinco recusas do `start` têm cada uma a SUA frase, e ela aparece
    // DENTRO da secção, logo abaixo do botão — nunca num toast que desaparece
    // antes de a pessoa acabar de ler. A escolha e o catálogo são preservados.
    var _MED_ERR_KEY = {
      already_meditating: "onda_med_err_already",
      invalid_meditation_type: "onda_med_err_invalid",
      not_enough_qi: "onda_med_err_qi",
      realm_too_low: "onda_med_err_realm",
      player_not_found: "onda_med_err_noplayer",
      // 至 Bug do [jogador] (21/09): o servidor recusa a Celestial com estas duas e
      // nenhuma tinha frase — o jogador lia o CODIGO. Agora le' o motivo.
      heavenly_laws_complete: "onda_med_err_leis_completas",
      needs_first_trial: "onda_med_err_primeiro_julgamento",
    };

    function MeditationCard({ catalog, realm, qi, meditating, medType, medMult,
                              remainMs, onStart, onStop, onRefresh, wide, anchorId }) {
      var rows = Array.isArray(catalog) ? catalog : [];
      var [sel, setSel] = useState("light");
      var [phase, setPhase] = useState(null);   // starting | stopping | confirming
      var [err, setErr] = useState(null);
      var [ok, setOk] = useState(null);

      // ⚠️ A selecção segue o catálogo, não o contrário: se a chave escolhida
      // deixar de existir (catálogo ainda a chegar, ou um mundo que a retire),
      // volta à primeira — que é a `light`, a única garantidamente aberta a
      // toda a gente.
      useEffect(function () {
        if (!rows.length) return;
        if (!rows.some(function (r) { return r.key === sel; })) setSel(rows[0].key);
      }, [catalog]);

      // ⚠️ O CRONÓMETRO LOCAL A ZERO NÃO ANUNCIA O FIM. Ele diz "a confirmar" e
      // espera o servidor: o `api_cultivation` finaliza a meditação vencida no
      // próprio poll, portanto a verdade chega em ≤5s. Anunciar o término aqui
      // seria a interface a afirmar um facto que ninguém escreveu.
      var timedOut = meditating && remainMs <= 0;

      var busy = phase === "starting" || phase === "stopping";
      var selRow = rows.filter(function (r) { return r.key === sel; })[0] || null;
      var selLocked = !!(selRow && (selRow.lock_reason || (realm || 0) < selRow.min_realm));
      var selPoor = !!(selRow && selRow.qi_cost > 0 && (qi || 0) < selRow.qi_cost);

      function lockWhy(r) {
        // 🔴 A trava que o SERVIDOR conhece vem primeiro. Bug do [jogador] (21/09):
        // a Celestial aparecia escolhivel aqui e o `start` recusava-a com
        // `heavenly_laws_complete` — o jogador so' descobria a regra pelo erro.
        // O catalogo passou a trazer `lock_reason`, calculado pelas MESMAS
        // regras do `start` (dono unico: `_travas_da_meditacao`).
        if (r.lock_reason && _MED_ERR_KEY[r.lock_reason]) {
          return t(_MED_ERR_KEY[r.lock_reason]);
        }
        if ((realm || 0) < r.min_realm) {
          return t("onda_med_need_realm", { realm: realmName(r.min_realm), n: r.min_realm });
        }
        if (r.qi_cost > 0 && (qi || 0) < r.qi_cost) {
          return t("onda_med_need_qi", { need: fmtFull(r.qi_cost), have: fmtFull(qi || 0) });
        }
        return null;
      }

      async function doStart() {
        if (busy || !selRow) return;
        setErr(null); setOk(null); setPhase("starting");
        try {
          await onStart(selRow.key);
          haptic("success");
          setOk(t("onda_med_ok_started"));
          setPhase(null);
        } catch (e) {
          haptic("error");
          var code = String((e && e.message) || "");
          if (_MED_ERR_KEY[code]) {
            setErr(t(_MED_ERR_KEY[code]));
            setPhase(null);
            // ⚠️ Toda recusa conhecida puxa os dados frescos: `already_meditating`
            // significa que existe uma sessão que esta tela ainda não viu, e as
            // outras quatro mudam o que as linhas devem dizer.
            onRefresh && onRefresh();
          } else {
            // Resultado INCERTO (rede, timeout, 5xx): não se repete o envio nem
            // se declara falha. Consulta-se o estado real e diz-se isso.
            setErr(null); setPhase("confirming");
            onRefresh && onRefresh();
            setTimeout(function () { setPhase(null); }, 1200);
          }
        }
      }

      async function doStop() {
        if (busy) return;
        setErr(null); setOk(null); setPhase("stopping");
        try {
          await onStop();
          haptic("success");
          setOk(t("onda_med_ok_stopped"));
          setPhase(null);
        } catch (e) {
          haptic("error");
          var code = String((e && e.message) || "");
          if (_MED_ERR_KEY[code]) { setErr(t(_MED_ERR_KEY[code])); setPhase(null); onRefresh && onRefresh(); }
          else { setErr(null); setPhase("confirming"); onRefresh && onRefresh();
                 setTimeout(function () { setPhase(null); }, 1200); }
        }
      }

      var statusLine = phase === "confirming" ? t("onda_med_confirming")
                     : timedOut ? t("onda_med_confirming_end")
                     : null;

      return (
        <section id={anchorId}
                 style={{ background: NIV_ONDA.ink, scrollMarginTop:12,
                          borderTop: wide ? "none" : "1px solid " + NIV_ONDA.line,
                          borderLeft: wide ? "1px solid " + NIV_ONDA.line : "none",
                          paddingTop: wide ? 0 : 24,
                          paddingLeft: wide ? 24 : 16,
                          paddingRight: wide ? 0 : 16,
                          paddingBottom: 24 }}>
          <h2 style={{ margin:0, fontFamily: NIV_ONDA.serif, fontWeight:400,
                       fontSize: wide ? 36 : 32, lineHeight: wide ? (40/36) : (36/32),
                       letterSpacing:"-.02em", color: NIV_ONDA.paper }}>
            {t("meditation")}
          </h2>

          {/* ── O TOPO: o que está a acontecer, ou o que vai acontecer ── */}
          {meditating ? (
            <div style={{ minHeight:44, marginTop:12 }}>
              <div style={{ display:"flex", alignItems:"baseline", gap:10, flexWrap:"wrap" }}>
                <span style={{ fontFamily: NIV_ONDA.serif, fontWeight:500,
                               fontSize:22, lineHeight:(26/22), color: NIV_ONDA.paper }}>
                  {medType
                    ? ondaNomeLimpo(t("meditation_" + (medType === "celestial_dao" ? "celestial" : medType)))
                    : t("onda_med_unknown_type")}
                </span>
                {/* ⚠️ O `Badge` saiu: um chip dourado com uma borda é a moldura
                    que esta tela foi cortar. O multiplicador é TEXTO. */}
                {medMult > 0 ? (
                  <span style={{ fontFamily: NIV_ONDA.body, fontSize:12,
                                 lineHeight:(18/12), color: NIV_ONDA.muted }}>
                    {t("onda_med_cb_mult", { n: medMult.toFixed(1) })}
                  </span>
                ) : null}
              </div>
              <div style={{ display:"flex", alignItems:"baseline", gap:10, marginTop:8 }}>
                <span style={{ fontFamily: NIV_ONDA.body, fontSize:12,
                               lineHeight:(18/12), color: NIV_ONDA.muted }}>
                  {t("ends_in")}
                </span>
                {/* 9ch reservados para o cronómetro — o desenho pede-os, e é o
                    que impede a linha de dançar a cada segundo. E ele NÃO é
                    dourado: o estado já se lê na figura e na frase acima. */}
                <span style={Object.assign({}, _ONDA_TNUM, {
                  minWidth:"9ch", fontSize:20, lineHeight:(26/20), fontWeight:500,
                  color: NIV_ONDA.paper,
                })}>
                  {timedOut ? "—" : fmtDuration(remainMs)}
                </span>
              </div>
            </div>
          ) : (
            <div style={{ minHeight:44, marginTop:12, fontFamily: NIV_ONDA.body,
                          fontSize:13, lineHeight:(20/13), color: NIV_ONDA.muted }}>
              {selRow
                ? t("onda_med_summary", {
                    name: ondaNomeLimpo(t("meditation_" + (selRow.key === "celestial_dao" ? "celestial" : selRow.key))),
                    dur: t("onda_med_minutes", { n: selRow.duration_minutes }),
                    qi: t("onda_med_cost", { n: fmtFull(selRow.qi_cost) }),
                  })
                : t("onda_med_loading")}
            </div>
          )}

          {/* ── A ACÇÃO ──
              ⚠️ "Encerrar meditação" deixou o vermelho de perigo: parar de
              meditar não destrói nada, e pintá-lo como uma acção destrutiva
              ensinava o contrário. */}
          <div style={{ marginTop:16 }}>
            {meditating ? (
              <OndaBtn kind="ghost" disabled={busy} onClick={doStop}>
                {phase === "stopping" ? t("onda_med_stopping") : t("meditate_stop")}
              </OndaBtn>
            ) : (
              <OndaBtn disabled={busy || !selRow || selLocked || selPoor} onClick={doStart}>
                {phase === "starting" ? t("onda_med_starting") : t("onda_med_start")}
              </OndaBtn>
            )}
          </div>

          {/* ── O QUE ACONTECEU, dito AQUI e não num toast ── */}
          {statusLine ? (
            <div style={{ marginTop:10, fontFamily: NIV_ONDA.body, fontSize:13,
                          lineHeight:(20/13), color: NIV_ONDA.muted }}>{statusLine}</div>
          ) : null}
          {err ? (
            <div style={{ display:"flex", gap:8, alignItems:"flex-start", marginTop:10,
                          fontFamily: NIV_ONDA.body, fontSize:13, lineHeight:(20/13),
                          color: NIV_ONDA.paper }}>
              <span style={{ display:"inline-flex", flexShrink:0, marginTop:2,
                             color: NIV_ONDA.seal }}>
                {<Mark name="warn" size={16} />}
              </span>
              <span>{err}</span>
            </div>
          ) : null}
          {ok && !err ? (
            <div style={{ display:"flex", gap:8, alignItems:"center", marginTop:10,
                          fontFamily: NIV_ONDA.body, fontSize:13, lineHeight:(20/13),
                          color: NIV_ONDA.paper }}>
              <span style={{ display:"inline-flex", flexShrink:0, color: NIV_ONDA.gold }}>
                {<Mark name="check" size={16} />}
              </span>
              <span>{ok}</span>
            </div>
          ) : null}

          {/* ── O CATÁLOGO: as SETE, sempre visíveis ──
              Também durante a meditação: a escada não desaparece por o jogador
              estar sentado — ele continua a poder ver o que vem a seguir. As
              linhas ficam inertes (não se troca de prática sem parar antes; é
              o servidor que diz `already_meditating`), mas NÃO esmaecidas: a
              [013] cortou o `opacity:.8`, porque esbater a lista inteira é
              esconder informação a quem está exactamente no momento de
              planear o passo seguinte. */}
          <div role="radiogroup" aria-label={t("meditate_choose")}
               style={{ marginTop:24 }}>
            <div style={{ fontFamily: NIV_ONDA.label, fontSize:11, lineHeight:(16/11),
                          letterSpacing:".12em", textTransform:"uppercase",
                          color: NIV_ONDA.muted, marginBottom:8 }}>
              {t("meditate_choose")}
            </div>
            {rows.length === 0 ? (
              /* Catálogo ausente é FALHA DE DADOS, não estado vazio (a `light`
                 está sempre aberta). Diz-se isso e oferece-se a recuperação. */
              <div style={{ fontFamily: NIV_ONDA.body, fontSize:13, lineHeight:(20/13),
                            color: NIV_ONDA.muted }}>
                {t("onda_med_catalog_missing")}
                <div style={{ marginTop:12 }}>
                  <OndaBtn kind="ghost" onClick={onRefresh}>{t("onda_rec_retry")}</OndaBtn>
                </div>
              </div>
            ) : rows.map(function (r) {
              var locked = !!r.lock_reason
                        || (realm || 0) < r.min_realm
                        || (r.qi_cost > 0 && (qi || 0) < r.qi_cost);
              return (
                <MeditationRow key={r.key} row={r} locked={locked} lockWhy={lockWhy(r)}
                               selected={!meditating && sel === r.key}
                               disabled={meditating || busy}
                               onSelect={function (k) { setErr(null); setOk(null); setSel(k); }} />
              );
            })}
          </div>
        </section>
      );
    }

    // ─── LeaderRow + Loading + SegControl ────────────────────────────────────
    // MA-32b — `onClick` is optional. When provided, the whole row becomes a
    // tap target for opening the player's profile card. Active state visual
    // (subtle hover background) only triggers when the row is interactive.
    function LeaderRow({ rank, name, meta, isYou, onClick }) {
      const chip = rankChip(rank);
      const interactive = typeof onClick === "function";
      return (
        <div onClick={interactive ? () => { haptic("select"); onClick(); } : undefined}
             role={interactive ? "button" : undefined}
             tabIndex={interactive ? 0 : undefined}
             style={{
          display:"flex", alignItems:"center", gap:10,
          padding:"9px 6px 8px",
          borderBottom:"1px solid rgba(var(--gold-rgb),.1)",
          background: isYou ? "linear-gradient(90deg,rgba(var(--gold-rgb),.14),transparent)" : "transparent",
          borderRadius: isYou ? 6 : 0,
          cursor: interactive ? "pointer" : "default",
          transition: interactive ? "background .15s" : undefined,
        }}>
          <div style={{
            fontFamily:"'Cinzel',serif", fontSize:12, fontWeight:700,
            color: chip.color, width:28, textAlign:"center",
            textShadow: chip.glow !== "transparent" ? `0 0 6px ${chip.glow}` : "none",
          }}>
            {rank <= 3 ? ["①","②","③"][rank-1] : `#${rank}`}
          </div>
          <div style={{ flex:1, fontSize:12.5, fontWeight:500, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{name}</div>
          <div style={{ fontSize:10.5, color:"var(--muted)", textAlign:"right", whiteSpace:"nowrap" }}>{meta}</div>
          {interactive && (
            <div style={{ fontSize:11, color:"rgba(var(--gold2-rgb),.5)", marginLeft:2, fontFamily:"'Cinzel',serif" }}>›</div>
          )}
        </div>
      );
    }
    function Loading() {
      return (
        <div style={{ display:"grid", placeItems:"center", height:"100%", gap:14, padding:"40px 0" }}>
          <div style={{
            fontFamily:"'Cinzel',serif", fontSize:54, fontWeight:700,
            background:"linear-gradient(90deg,var(--gold),var(--gold2),var(--gold3),var(--gold2),var(--gold))",
            backgroundSize:"200% 100%",
            WebkitBackgroundClip:"text", backgroundClip:"text", WebkitTextFillColor:"transparent",
            animation:"shimmer 2.5s linear infinite",
          }}>Nivrael</div>
          <div style={{ fontSize:11, letterSpacing:2, color:"rgba(var(--gold-rgb),.65)", textTransform:"uppercase",
            fontFamily:"'Cinzel',serif" }}>{t("loading_label")}</div>
        </div>
      );
    }

    // Skeleton primitive — a shimmering placeholder block. Cheap visual hint
    // that content is on its way, instead of an empty void. Kept compact so
    // tabs can compose layout-matching skeletons inline.
    function Skel({ h = 14, w = "100%", mt = 0, mb = 0, br = 6, style }) {
      return <div className="skel" style={{ height: h, width: w, marginTop: mt, marginBottom: mb, borderRadius: br, ...style }} />;
    }
    function SkelCard({ children }) {
      return (
        <div style={{
          background:"linear-gradient(180deg,rgba(20,30,55,.7),rgba(var(--card-rgb),.85))",
          border:"1px solid rgba(var(--glow-rgb),.18)",
          borderRadius:12, padding:"14px 14px 16px", marginBottom:10,
        }}>{children}</div>
      );
    }
    // Per-tab skeleton variants. Each mirrors the rough layout of the real
    // tab so the UI doesn't jump when data arrives.
    function CultivationSkeleton() {
      return (
        <div>
          <div style={{ width:200, height:200, margin:"6px auto 14px", borderRadius:"50%" }} className="skel" />
          <SkelCard><Skel h={12} w="40%" /><Skel h={10} mt={10} /><Skel h={10} w="60%" mt={6} /></SkelCard>
          <SkelCard><Skel h={12} w="30%" /><Skel h={10} mt={10} /><Skel h={10} w="55%" mt={6} /></SkelCard>
          <SkelCard><Skel h={12} w="35%" /><div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8, marginTop:10 }}>
            <Skel h={36} br={8} /><Skel h={36} br={8} /><Skel h={36} br={8} /><Skel h={36} br={8} />
          </div></SkelCard>
        </div>
      );
    }
    function ListSkeleton({ rows = 6 }) {
      return (
        <SkelCard>
          <Skel h={12} w="40%" mb={12} />
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} style={{ display:"flex", alignItems:"center", gap:10, padding:"8px 2px" }}>
              <Skel h={20} w={28} br={4} />
              <Skel h={12} style={{ flex:1 }} />
              <Skel h={10} w={60} />
            </div>
          ))}
        </SkelCard>
      );
    }
    function GridSkeleton({ slots = 12 }) {
      return (
        <SkelCard>
          <Skel h={12} w="35%" mb={12} />
          <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:6 }}>
            {Array.from({ length: slots }).map((_, i) => <Skel key={i} h={56} br={8} />)}
          </div>
        </SkelCard>
      );
    }
    function BossSkeleton() {
      return (
        <div>
          <SkelCard>
            <div style={{ display:"grid", placeItems:"center", padding:"8px 0" }}>
              <Skel h={56} w={56} br={28} />
              <Skel h={14} w="50%" mt={10} />
              <Skel h={9} w="30%" mt={6} />
            </div>
            <Skel h={11} mt={14} br={8} />
            <div style={{ display:"flex", justifyContent:"space-between", marginTop:8 }}>
              <Skel h={10} w="35%" /><Skel h={10} w="25%" />
            </div>
          </SkelCard>
          <ListSkeleton rows={4} />
        </div>
      );
    }
    function FeedSkeleton({ rows = 5 }) {
      return (
        <SkelCard>
          <Skel h={12} w="40%" mb={12} />
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} style={{ display:"flex", gap:10, padding:"8px 0" }}>
              <Skel h={22} w={22} br={11} />
              <div style={{ flex:1 }}>
                <Skel h={11} />
                <Skel h={9} w="45%" mt={6} />
              </div>
            </div>
          ))}
        </SkelCard>
      );
    }
    function SegControl({ options, value, onChange }) {
      return (
        <div style={{
          display:"flex", gap:3,
          background:"rgba(0,0,0,.4)", border:"1px solid rgba(var(--gold-rgb),.2)",
          borderRadius:7, padding:3, marginBottom:10,
        }}>
          {options.map(o => (
            <button key={o.value} onClick={() => { haptic("select"); onChange(o.value); }} style={{
              flex:1,
              background: value === o.value
                ? "linear-gradient(180deg,rgba(var(--gold-rgb),.32),rgba(120,80,30,.4))" : "none",
              border: value === o.value ? "1px solid rgba(var(--gold-rgb),.4)" : "1px solid transparent",
              color: value === o.value ? "var(--gold2)" : "var(--muted2)",
              fontSize:10.5, fontWeight:600, padding:"7px 0",
              borderRadius:5, cursor:"pointer", letterSpacing:.5,
              fontFamily:"'Cinzel',serif", transition:"all .15s",
              // 印 uma marca e' um bloco; centra-la exige flex. Condicional para
              // que o `style` fique letra a letra igual quando o rotulo e' texto.
              ...(o.label && typeof o.label === "object"
                  ? { display:"flex", alignItems:"center", justifyContent:"center" } : {}),
            }}>{o.label}</button>
          ))}
        </div>
      );
    }
    // 🔴 UM DONO para o codigo de erro (item 8/9 da auditoria do Astra).
    //
    // A tabela vivia AQUI dentro com **duas** entradas escritas a mao, e o
    // `core/webserver.py` tem **85 codigos distintos** — os genericos
    // (`player_not_found` 171 usos, `bad_request` 63, `not_found` 27,
    // `engine_error` 13) chegavam ao jogador em ingles cru, exactamente como o
    // "unauthorized" que a onda 1 foi tirar do ecra de chegada.
    //
    // ⚠️ Ela sai para fora do `ErrBanner` porque o `CultRecovery` precisa da
    // MESMA traducao. Duas tabelas divergiriam na primeira semana — foi assim
    // que uma lista de 4 modalidades sobreviveu meses ao lado de um servidor
    // que aceita 7 (Lei 0 §2).
    //
    // ⚠️ E o DESCONHECIDO cai para o codigo CRU, de proposito: esconder um
    // codigo que nao sei traduzir tira ao jogador a unica coisa que ele podia
    // colar num report, e a mim a unica pista.
    var API_ERR_KEY = {
      unauthorized:       "err_unauthorized",
      session_expired:    "err_unauthorized",
      login_invalid:      "err_unauthorized",
      player_not_found:   "err_player_not_found",
      bad_request:        "err_bad_request",
      bad_json:           "err_bad_request",
      not_found:          "err_not_found",
      method_not_allowed: "err_not_found",
      engine_error:       "err_server",
      server_error:       "err_server",
      server_misconfigured: "err_server",
      rate_limited:       "err_rate_limited",
      // os dois do CLIENTE, que o relogio do transporte criou
      request_timeout:    "err_request_timeout",
      network_error:      "err_network",
      // 決 (16/09) — os codigos que o servidor manda a **HTTP 200** e que
      // por isso nunca passam pelo `catch`. `internal_error` e' o que
      // `api_combat_npc_cultivator_*` devolve em qualquer excepcao; os dois
      // seguintes vem do `apply_combat_moral_choice` (npc_cultivator_engine).
      internal_error:     "err_server",
      not_won:            "npc_cult_erro_nao_venceu",
      not_your_duel:      "npc_cult_erro_nao_e_seu",
    };
    function apiErroTexto(msg) {
      var k = API_ERR_KEY[String(msg == null ? "" : msg)];
      return k ? t(k) : msg;
    }
    function ErrBanner({ msg }) {
      return <div className="err-banner">⚠️ {apiErroTexto(msg)}</div>;
    }

    // Per-tab ErrorBoundary so a runtime crash in one feature (e.g. an
    // undefined deref inside CraftingTab) doesn't unmount the entire app
    // shell into a black void. The user sees a recoverable error message
    // and can switch tabs to keep playing.
    class TabErrorBoundary extends React.Component {
      constructor(props) {
        super(props);
        this.state = { error: null };
      }
      static getDerivedStateFromError(error) {
        return { error: (error && error.message) || String(error) };
      }
      componentDidCatch(error, info) {
        try { console.error("[tab-error]", this.props.tabKey, error, info); } catch (e) {}
        // Beacon the real exception + component stack to the server (best-effort)
        // so crashes we can't reproduce still surface the exact cause.
        try {
          api("client_error", {
            error: (error && (error.stack || error.message)) || String(error),
            stack: (info && info.componentStack) || "",
            ctx: "tab:" + (this.props.tabKey || ""),
          }).catch(function () {});
        } catch (e) {}
      }
      componentDidUpdate(prevProps) {
        if (prevProps.tabKey !== this.props.tabKey && this.state.error) {
          this.setState({ error: null });
        }
      }
      render() {
        if (this.state.error) {
          return (
            <div style={{ padding:"24px 12px" }}>
              <div className="err-banner">⚠️ {t("err_tab_crash", { msg: this.state.error })}</div>
              <div style={{ fontSize:11, color:"var(--muted)", textAlign:"center", marginTop:14, lineHeight:1.6 }}>
                {t("err_tab_crash_hint")}
              </div>
            </div>
          );
        }
        return this.props.children;
      }
    }

    // Root-mounted modals live OUTSIDE the per-tab TabErrorBoundary, so a render
    // (or mount-effect) crash inside one — e.g. the Sect Hall — used to unmount
    // the ENTIRE app into a black void (player report: [jogador], "apertei na minha
    // seita anciã e ficou tela preta", 2026-06-17). This boundary catches it,
    // logs the REAL error (console → so the actual trigger surfaces for diagnosis),
    // and shows a recoverable card whose CTA peels the crashed modal via the
    // parent's _handleBack — never a silent black screen (Lei §1 never-stuck). It
    // resets when `resetKey` (the open-modal signature) changes.
    class ModalErrorBoundary extends React.Component {
      constructor(props) { super(props); this.state = { error: null }; }
      static getDerivedStateFromError(error) { return { error: (error && error.message) || String(error) }; }
      componentDidCatch(error, info) {
        const cs = (info && info.componentStack) || "";
        try { console.error("[modal-error]", this.props.label || "", error, info); } catch (e) {}
        // Surface WHICH component threw (first frames) on the card + beacon the
        // full error/stack to the server — so a crash we can't reproduce (e.g.
        // [jogador]'s Sect Hall) reveals its exact cause from a screenshot OR the log.
        try { this.setState({ stack: String(cs).trim().split("\n").slice(0, 3).join("\n") }); } catch (e) {}
        try {
          api("client_error", {
            error: (error && (error.stack || error.message)) || String(error),
            stack: String(cs).slice(0, 1500),
            ctx: "modal:" + (this.props.label || ""),
          }).catch(function () {});
        } catch (e) {}
      }
      componentDidUpdate(prevProps) {
        if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
          this.setState({ error: null });
        }
      }
      render() {
        if (this.state.error) {
          const dismiss = () => {
            try { this.props.onClose && this.props.onClose(); } catch (e) {}
            this.setState({ error: null });
          };
          return (
            <div style={{ position:"fixed", inset:0, zIndex:99999, display:"flex", alignItems:"center", justifyContent:"center", padding:24, background:"rgba(6,10,24,.94)" }}>
              <div style={{ maxWidth:330, width:"100%", textAlign:"center", background:"var(--card,#0d1226)", border:"1px solid rgba(var(--gold2-rgb),.28)", borderRadius:16, padding:"24px 18px" }}>
                <div style={{ fontSize:36, marginBottom:10 }}>🏯</div>
                <div className="err-banner" style={{ marginBottom:12 }}>⚠️ {t("err_modal_crash")}</div>
                {/* Diagnostic detail (the real error + the component that threw) —
                    screenshot-able for diagnosis; muted so it doesn't alarm. */}
                {(this.state.error || this.state.stack) && (
                  <div style={{ marginBottom:12, fontSize:9.5, color:"var(--muted)", fontFamily:"monospace", textAlign:"left", whiteSpace:"pre-wrap", wordBreak:"break-word", maxHeight:120, overflowY:"auto", background:"rgba(0,0,0,.28)", borderRadius:8, padding:"7px 9px", lineHeight:1.4 }}>
                    {this.state.error}{this.state.stack ? "\n" + this.state.stack : ""}
                  </div>
                )}
                <button onClick={dismiss} style={{ width:"100%", padding:"11px 0", borderRadius:10, fontSize:13, fontWeight:600, cursor:"pointer", border:"1px solid rgba(var(--gold2-rgb),.4)", background:"rgba(var(--gold2-rgb),.16)", color:"var(--gold3,var(--gold2))" }}>
                  {t("err_modal_close")}
                </button>
                <div onClick={() => { try { location.reload(); } catch (e) {} }} style={{ marginTop:12, fontSize:11, color:"var(--muted)", cursor:"pointer", textDecoration:"underline" }}>
                  {t("err_modal_reload")}
                </div>
              </div>
            </div>
          );
        }
        return this.props.children;
      }
    }

    // ─── Modal primitive (MA-MODAL, 2026-05-10) ──────────────────────────────
    // Owner pain point: every modal in the app had two systemic bugs on
    // mobile (Telegram WebView, iOS Safari):
    //   (1) Title clipped under PlayerHeader — header scrolled away with body.
    //   (2) Primary CTA off-screen on tall content (Sweep / Confirm / Continue
    //       fell below the fold and the user couldn't reach it).
    //   (3) Background page rubber-banded when swiping inside the modal.
    //
    // Witness case: DungeonEntryModal (owner reported by phone 2026-05-09).
    // Pattern is identical across ~19 bespoke modals.
    //
    // The canonical <Modal> below fixes all three universally:
    //   • Sticky header (always visible, even mid-scroll).
    //   • Scrollable body (overscroll-behavior: contain → no rubber-band leak).
    //   • Sticky footer (CTAs always visible — owner's main complaint).
    //   • Body scroll lock via stack counter so nested modals nest correctly
    //     (e.g. ProfileCardModal inside LeaderboardTab).
    //   • dvh fallback to vh for older Telegram WebView; safe-area inset
    //     padding for iOS home indicator collision.
    //
    // Usage:
    //   <Modal title="Title" onClose={fn} footer={<Cancel + Confirm />}>
    //     ...scrollable body...
    //   </Modal>
    //
    // Props:
    //   open?              — convenience flag; if false, returns null. (Most
    //                         callers conditionally render so default is true.)
    //   onClose            — required; called by backdrop click + ✕ button.
    //   title              — header content. String or ReactNode.
    //   accent             — CSS color for borders + header underline.
    //   maxWidth           — px (default 380). Ignored when fullScreen.
    //   fullScreen         — true → take whole viewport (used by ShopOverlayModal).
    //   zIndex             — default 60. Use 70 for results stacked over a
    //                         detail modal, 75 for full-screen overlays, 80
    //                         for cinematics (cinematics don't use this; they
    //                         render their own full-screen <div>).
    //   showCloseBtn       — default true.
    //   allowBackdropClose — default true.
    //   footer             — sticky footer ReactNode. Omit if no CTAs.
    //   cardStyle          — extra style for the card (gradient overrides etc).
    //   bodyStyle          — extra style for the scroll body.
    //   bodyClassName      — extra className for the scroll body.
    //   animation          — override card mount animation.
    //   shake              — when true, applies bt-shake-horizontal once
    //                         (used by BreakthroughModal on gate fail).
    var _modalScrollLockCount = 0;
    var _modalScrollLockPrev = null;
    // ⌨️ A TECLA QUE FECHA (item 1 da auditoria do Astra, 2026-09-16).
    //
    // 🔴 MEDIDO: a palavra `Escape` nao aparecia UMA vez no mini-app inteiro
    // — zero ocorrencias em `ui.js`, `tabs.js` e `app.js`. As **74 janelas** do
    // jogo (72 `<Modal>` + 2 `<Overlay>`) fechavam-se com o rato e mais nada.
    // Quem entra numa delas pelo teclado fica **preso la' dentro**: e' a Lei §1
    // na forma mais pura, e e' impedimento, nao preferencia.
    //
    // ⚠️ A PILHA existe por causa do aninhamento, que nesta casa e' real (o
    // `_handleBack` do `app.js` ja' trata a sua). Um `keydown` no documento por
    // cada janela aberta fechava-as TODAS de uma vez — trocar "nao fecha
    // nenhuma" por "fecha demais" nao e' melhorar. So' o TOPO responde.
    //
    // ⚠️ E a condicao e' exactamente a do pano de fundo
    // (`allowBackdropClose`): o teclado ganha o que o rato ja' podia fazer,
    // nunca mais do que isso. Uma janela que o desenho selou continua selada.
    // Medido: ZERO janelas passam `allowBackdropClose={false}` hoje — portanto
    // na pratica as 74 passam a fechar, que e' o ponto.
    //
    // ⚠️ O `onClose` vive numa `ref` de proposito. Com ele nas dependencias,
    // um `onClose={() => ...}` escrito em linha (que e' o caso da esmagadora
    // maioria das 74) remontava o efeito a cada render, e a pilha reordenava-se
    // debaixo dos pes: o "topo" deixava de ser a janela de cima.
    var _PILHA_ESC = [];
    function useEscapeFecha(activa, onClose) {
      const _fecha = useRef(onClose);
      _fecha.current = onClose;
      useEffect(function () {
        if (!activa) return;
        var marca = {};
        _PILHA_ESC.push(marca);
        function aoTeclar(ev) {
          // `Esc` e' o nome antigo; ha' WebViews que ainda o mandam.
          if (ev.key !== "Escape" && ev.key !== "Esc") return;
          if (_PILHA_ESC[_PILHA_ESC.length - 1] !== marca) return;
          if (typeof _fecha.current !== "function") return;
          ev.preventDefault();
          ev.stopPropagation();
          _fecha.current();
        }
        document.addEventListener("keydown", aoTeclar, true);
        return function () {
          document.removeEventListener("keydown", aoTeclar, true);
          var i = _PILHA_ESC.indexOf(marca);
          if (i >= 0) _PILHA_ESC.splice(i, 1);
        };
      }, [activa]);
    }

    // 🖱️→⌨️ O ALVO QUE O TECLADO ALCANCA (o mesmo item 1).
    //
    // 🔴 MEDIDO: **33 elementos nativos** do mini-app tinham `onClick` sem
    // forma nenhuma de serem accionados por teclado (`<div onClick>`), contra
    // 137 que ja' eram `<button>`. Um `div` com `onClick` nao recebe foco, nao
    // responde ao Enter nem ao Espaco, e nao se anuncia como botao: o jogador
    // que depende do teclado encontra DECISOES que nao consegue tomar.
    //
    // ⚠️ Porque nao se troca tudo por `<button>`: varios destes cartoes TEM
    // botoes la' dentro. Um botao dentro de um botao e' HTML invalido e o
    // browser parte a arvore. A marca vai por fora — `role="button"` +
    // `tabIndex` + Enter/Espaco — que e' o que a norma manda para este caso.
    //
    // ⚠️ E devolve `{}` quando nao ha' `onClick`. Sem isso, um cartao
    // decorativo ganhava `tabIndex=0` e entrava na ordem do Tab sem fazer nada
    // — encher a viagem de paragens mudas e' outra forma de a estragar.
    function clicavel(onClick, rotulo) {
      if (typeof onClick !== "function") return {};
      return {
        onClick: onClick,
        role: "button",
        tabIndex: 0,
        "aria-label": rotulo || undefined,
        onKeyDown: function (ev) {
          if (ev.key !== "Enter" && ev.key !== " " && ev.key !== "Spacebar") return;
          // ⚠️ O Espaco rola a pagina por omissao. Sem isto, accionar um
          // cartao pelo teclado fazia a tela SALTAR ao mesmo tempo.
          ev.preventDefault();
          ev.stopPropagation();
          onClick(ev);
        },
      };
    }

    function useBodyScrollLock(active) {
      // Guard: only lock while active. Stack counter so nested modals nest.
      useEffect(() => {
        if (active === false) return;
        if (_modalScrollLockCount === 0) {
          _modalScrollLockPrev = document.body.style.overflow;
          document.body.style.overflow = "hidden";
        }
        _modalScrollLockCount += 1;
        return () => {
          _modalScrollLockCount = Math.max(0, _modalScrollLockCount - 1);
          if (_modalScrollLockCount === 0) {
            document.body.style.overflow = _modalScrollLockPrev || "";
          }
        };
      }, [active]);
    }

    // ─── 窗 O OVERLAY — o dono ÚNICO de "uma janela por cima do jogo" ────────
    //
    // ⚠️ NASCEU DE UM RELATO DO OWNER (2026-09-08, do telemóvel dele, textual):
    // *"quando abro o item no telefone não posso fechar a janela. cobre tudo e
    // nao deixa o X."* — e a causa está escrita, palavra por palavra, no
    // comentário do `Modal` aqui em baixo, datado de **2026-05-10**:
    //
    //   *"on iPhone Telegram WebView, the modal TOP was hidden behind the
    //    PlayerHeader — couldn't reach the ✕ button. Cause: iOS Safari (…)
    //    `position:fixed` elements inside scrolling containers get scoped to
    //    the scroll container's coordinates instead of the viewport."*
    //
    // O `Modal` foi consertado nessa altura com um **portal para o
    // `document.body`**. Os modais escritos À MÃO nunca foram — e um deles é o
    // detalhe do item, que o 器 (08/09) tornou MAIS ALTO ao pôr a ilustração no
    // topo. O mesmo defeito, no mesmo sítio, quatro meses depois, porque a
    // correcção teve **um** dono e o problema tinha **três**.
    //
    // É a Lei F-7 na sua forma mais pura: *uma capacidade sem UM dono no código
    // volta sempre a divergir*. Esta função é esse dono para "sobrepor uma
    // janela ao jogo". MEDIDO a 2026-09-08: `position:"fixed"` + `inset:0`
    // aparece **10** vezes nos componentes — 1 é o `Modal`, 1 é o `ErrBanner`,
    // **6 são cinemáticas** (`pointerEvents:"none"`, sem ✕, sem conteúdo para
    // rolar — não são janelas e por isso NÃO passam por aqui), e **2 eram
    // janelas de verdade escritas à mão**: o detalhe do item e o escolhedor de
    // slot. São essas duas que passam a ter dono.
    //
    // O que esta função garante, e nenhuma das duas tinha:
    //   1. **PORTAL** para o `document.body` — o `position:fixed` escapa a
    //      `.scroll-area` e cobre mesmo o ecrã todo (o bug do iOS).
    //   2. **ROLA SEM CORTAR.** O fundo é `overflowY:auto` e o cartão centra-se
    //      com `margin:auto` — e não com `place-items:center`, que numa peça
    //      mais alta que o pai corta as DUAS pontas e deixa o ✕ fora do ecrã
    //      sem maneira de lá chegar. `margin:auto` nunca corta.
    //   3. **ALTURA LIMITADA** (`bounded`): o cartão nunca passa do ecrã, o
    //      corpo rola por dentro, e o que vier em `pinned` fica FORA desse
    //      corpo — ou seja, o ✕ está sempre lá, mesmo a meio da rolagem.
    //   4. **TRAVA O FUNDO** (`useBodyScrollLock`) e reserva as safe-areas do
    //      entalhe e da barra de baixo, como o `Modal` já reservava.
    function Overlay({ onClose, zIndex, background, padding, maxWidth,
                       cardStyle, bodyStyle, bodyClassName,
                       bounded, pinned, children }) {
      useBodyScrollLock(true);
      // O `Overlay` nao tem `allowBackdropClose`: o pano de fundo dele fecha
      // sempre (`onClick={onClose}`), logo o Escape tambem.
      useEscapeFecha(true, onClose);
      // A mesma reserva do `Modal`: entalhe em cima, BottomNav + home indicator
      // em baixo. Sem isto o ✕ nasce por baixo do entalhe do iPhone.
      const pad = padding || "max(env(safe-area-inset-top), 12px) 12px"
                             + " max(110px, calc(env(safe-area-inset-bottom) + 90px))";
      const content = (
        <div onClick={onClose} style={{
          position:"fixed", inset:0, zIndex: zIndex || 60,
          background: background || "rgba(4,6,12,.92)",
          // ⚠️ `overflowY:auto` + `margin:auto` no filho. As duas metades da
          // mesma correcção: sem a primeira não há como chegar ao que sai do
          // ecrã; sem a segunda o centramento CORTA o topo em vez de o empurrar.
          overflowY:"auto", overscrollBehavior:"contain",
          display:"flex", flexDirection:"column",
          padding: pad,
          animation:"fadein 180ms ease",
        }}>
          <div onClick={(e) => e.stopPropagation()} style={{
            width:"100%", maxWidth: maxWidth || 380,
            margin:"auto", flexShrink:0, position:"relative",
            ...(bounded ? {
              // `100dvh` a par de `100vh`: no WebView do Telegram a barra de
              // endereço entra e sai e o `vh` mente. O menor dos dois é o que
              // existe de certeza.
              maxHeight:"min(calc(100vh - 96px), calc(100dvh - 96px))",
              display:"flex", flexDirection:"column", overflow:"hidden",
            } : {}),
            ...cardStyle,
          }}>
            {pinned}
            {bounded ? (
              // ⚠️ `flex:"0 1 auto"` e NAO `flex:"1 1 0"`. O `Modal` usa `1 1 0`
              // porque fixa uma ALTURA definida no cartao; aqui o cartao tem
              // apenas `maxHeight` (cresce com o conteudo ate' ao tecto), e com
              // base 0 o corpo COLAPSA para 0px — visto a olho: o modal abriu
              // com 36px de altura e nada dentro, so' o ✕. Um teste teria dito
              // "o ✕ esta' alcancavel" e estaria certo sobre uma janela vazia.
              // `0 1 auto` cresce com o conteudo e encolhe quando o tecto morde.
              <div className={"scroll-area" + (bodyClassName ? " " + bodyClassName : "")}
                   style={{ flex:"0 1 auto", minHeight:0, overflowY:"auto",
                            WebkitOverflowScrolling:"touch", ...bodyStyle }}>
                {children}
              </div>
            ) : children}
          </div>
        </div>
      );
      return ReactDOM.createPortal(content, document.body);
    }

    // ── 窗 2026-09-15 — A LARGURA DE UMA JANELA, e porque ela tem UM dono ──
    //
    // Ordem do owner, a olhar para o ecra de PC: *"falta melhoras no modal etc.
    // ele tem que cubrir tudo"*. E ele tem razao — o `Modal` ja' ocupava quase
    // toda a ALTURA (`100vh - 180px` desde 05/2026) e continuava com 380px de
    // LARGURA. Num ecra de 1440 isso e' uma coluna de telemovel a flutuar no
    // meio do nada, que e' exactamente a "grelha de azulejos" do lote passado
    // vista de outro angulo: a pele mudou, a FORMA nao.
    //
    // ⚠️ CONTADO ANTES (Lei 0 passo 1): 86 `<Modal>` no `tabs.js` — 58 declaram
    // largura propria (360..520), 2 sao `fullScreen`, 26 herdam o default.
    // Mexer so' no default consertava 26 de 86 e deixava o jogo com metade das
    // janelas largas e metade estreitas — a inconsistencia que a Lei 0 diz ser
    // PIOR do que a ausencia. Por isso a pergunta passa a ser feita aqui, UMA
    // vez, e a largura declarada em cada sitio passa a ser o que sempre quis
    // ser: a PROPORCAO da janela (uma de 520 e' mais larga que uma de 380),
    // nao um numero de pixeis de telemovel.
    //
    // ⚠️ OFF-identidade: com `superficie_desktop` OFF, `useWideShell()` e'
    // false e isto devolve o numero declarado — byte a byte o de hoje.
    function modalWidth(declarado, wide, onda) {
      const d = Number(declarado) || 380;
      if (!wide) return d;
      // 窗 2026-09-21 — A PRÉVIA MANDA. O owner, a olhar para a Fundação no PC
      // (uma janela de 912x720 com três linhas lá dentro): *"Todos modals etc.
      // Bom a prévia que eu VI. quero aquilo."* A janela da prévia aprovada
      // (`newapp/preview/portal-v1.html`) tem **610px**. O factor 1,6 leva o
      // default 380 a 608 e mantém a PROPORÇÃO entre janelas (520 -> 832) —
      // a regra de 15/09 continua, com a escala da prévia.
      if (onda) return `min(${Math.round(d * 1.6)}px, 1120px, 88vw)`;
      // 2.4x leva 380 -> 912 e 520 -> 1248; o tecto de 1120px impede que uma
      // janela num monitor largo vire uma linha de texto de ponta a ponta
      // (a medida de leitura ainda manda), e `88vw` guarda a moldura nas
      // larguras intermedias (1024..1280), onde o tecto ainda nao morde.
      return `min(${Math.round(d * 2.4)}px, 1120px, 88vw)`;
    }

    // 窗 A MOLDURA DA PRÉVIA, num sítio só. Os valores são os do `dialog` da
    // prévia aprovada, medidos no CSS dela: fundo `#151211`, fio `#6b5336`,
    // cantos rectos, sombra longa, título em Cormorant e um × simples.
    // ⚠️ A moldura é do DONO. Muitas chamadas passam `cardStyle` com o seu
    // gradiente (a Fundação pintava-se de AZUL por cima de tudo); com a onda,
    // o que é MOLDURA — fundo, borda, raio, sombra — deixa de ser de cada
    // sítio, senão 84 janelas voltavam a ser 84 peles. O resto do `cardStyle`
    // (tamanhos, layout) passa intacto.
    var ONDA_JANELA = {
      fundo: "#151211", fio: "#6b5336", veu: "rgba(5,4,5,.86)",
      sombra: "0 20px 100px rgba(0,0,0,.53)",
    };
    var _MOLDURA_KEYS = { background: 1, backgroundImage: 1, backgroundColor: 1,
                          border: 1, borderColor: 1, borderRadius: 1, boxShadow: 1 };
    function semMoldura(st) {
      if (!st) return st;
      var out = {};
      Object.keys(st).forEach(function (k) { if (!_MOLDURA_KEYS[k]) out[k] = st[k]; });
      return out;
    }

    function Modal({
      open, onClose, title, accent, maxWidth, fullScreen, zIndex,
      showCloseBtn, allowBackdropClose, footer, children,
      cardStyle, bodyStyle, bodyClassName, animation, shake,
      headerExtra, compact,
    }) {
      useBodyScrollLock(open !== false);
      // ⌨️ A mesma condicao do pano de fundo, 30 linhas abaixo: o teclado ganha
      // o que o rato ja' podia fazer. Nunca mais.
      useEscapeFecha(open !== false && allowBackdropClose !== false, onClose);
      // ⚠️ o hook corre SEMPRE, antes do `return null`: chamar um hook
      // depois de um return condicional parte a ordem dos hooks do React.
      const _modalWide = useWideShell();
      // 窗 a prévia, pelo dono único da chave-mestra (nunca um `featureEnabled`
      // novo — a guarda do §19 conta os leitores).
      const _onda = typeof ondaCultOn === "function" && ondaCultOn();
      // 窗 2026-09-21 — A JANELA MEDE-SE. A altura fixa existe por causa do
      // WebKit do iPhone (o `flex:1 1 0` só rola com um pai de altura
      // definida) e fica: uma janela cujo conteúdo NÃO cabe continua a usá-la.
      // Uma janela cujo conteúdo cabe passa a ter a altura dele — nas duas
      // larguras. Visto a 390x844: os Avisos vazios ocupavam 660px de caixa
      // para duas linhas; no PC, a Fundação 912x720 para três.
      // ⚠️ Mede ANTES de pintar (layout effect) e volta a medir quando o
      // conteúdo muda de tamanho — uma janela que carrega dados e cresce
      // regressa ao caminho fixo, que é o que rola no iPhone.
      const _cardRef = useRef(null);
      const _bodyRef = useRef(null);
      const [_cabe, _setCabe] = useState(false);
      const _uLE = React.useLayoutEffect || useEffect;
      _uLE(() => {
        if (!_onda || fullScreen || open === false) return undefined;
        const card = _cardRef.current, body = _bodyRef.current;
        if (!card || !body) return undefined;
        const medir = () => {
          try {
            // ⚠️ NÃO o `scrollHeight`: ele nunca é menor do que a caixa visível,
            // e com a altura fixa a janela diria sempre "não cabe". Mede-se o
            // FUNDO do conteúdo, filho a filho.
            // ⚠️ E em medidas de LAYOUT, nunca `getBoundingClientRect`: a janela
            // entra com uma animação de ESCALA, e o rectângulo transformado
            // mente — visto no Perfil a 1440x900: 741px pareciam 710 no 1º
            // instante, a janela dizia "cabe" e ficava presa assim (nada muda
            // de tamanho real depois, logo ninguém voltava a medir).
            let fundo = 0;
            Array.prototype.forEach.call(body.children, function (c) {
              const base = c.offsetParent === body ? 0 : body.offsetTop;
              const b = c.offsetTop - base + c.offsetHeight;
              if (b > fundo) fundo = b;
            });
            const pb = parseFloat(getComputedStyle(body).paddingBottom) || 0;
            const extra = card.offsetHeight - body.clientHeight;
            const precisa = Math.ceil(fundo + pb) + extra;
            const teto = (window.innerHeight || 0) - 180;
            const cabeAgora = teto > 0 && precisa <= teto - 1;
            _setCabe(prev => (prev === cabeAgora ? prev : cabeAgora));
          } catch (e) { /* sem medida, fica a altura fixa — o caminho seguro */ }
        };
        medir();
        let ro = null;
        if (typeof ResizeObserver === "function") {
          ro = new ResizeObserver(medir);
          Array.prototype.forEach.call(body.children, function (c) { ro.observe(c); });
        }
        window.addEventListener("resize", medir);
        return () => { if (ro) ro.disconnect(); window.removeEventListener("resize", medir); };
      });
      if (open === false) return null;

      // Owner reported (2026-05-10 round 5): on iPhone Telegram WebView,
      // the modal TOP was hidden behind the PlayerHeader — couldn't reach
      // the ✕ button. Cause: iOS Safari has a long-standing quirk where
      // `position:fixed` elements inside scrolling containers (the
      // mini-app's `.scroll-area` with `overflowY:auto`) get scoped to
      // the scroll container's coordinates instead of the viewport. So
      // `inset:0` covers only the scroll area, NOT the PlayerHeader area
      // above it. On desktop this works because Chrome/Firefox handle
      // position:fixed strictly per spec. iOS doesn't.
      // Fix: render via React Portal directly to document.body. This
      // guarantees the modal is OUTSIDE the scroll-area in the DOM tree,
      // so position:fixed escapes all ancestors and overlays the entire
      // viewport (PlayerHeader, BottomNav, AtmoBg, everything).

      const accentColor = accent || "rgba(var(--gold2-rgb),.42)";
      const fs = !!fullScreen;
      const z = zIndex || 60;
      const shouldShowClose = showCloseBtn !== false;
      const handleBackdrop = (allowBackdropClose !== false) ? onClose : undefined;
      // Reserve 180px:
      //   - safe-area-inset-top  (~44px iPhone notch)
      //   - safe-area-inset-bottom (~34px home indicator)
      //   - BottomNav (~80px main row + 20px cloud SVG = ~100px)
      //   - Padding 12px × 2 + breathing room
      // Total: ~180px reserved at the EDGES so the card NEVER overlaps
      // the BottomNav. Owner round 4 (2026-05-10): "parte de baixo
      // ocupada" — footer buttons (Sweep × N) were clipped by the
      // BottomNav's gold cloud SVG + icons. With 180px reservation +
      // explicit backdrop bottom-padding, card stays cleanly above nav
      // chrome on iPhone, Android, desktop.
      const cardMaxHeight = fs ? "100%" : "min(calc(100vh - 180px), calc(100dvh - 180px))";
      // Owner request 2026-05-08 (P1 round): "Olha o tamanho do modal
      // quando forja. Muito feio". Default modals lock to cardMaxHeight
      // for premium "screen" feel, but result modals (forge/alchemy
      // outcome) look bloated when content is short. `compact={true}`
      // lets the card grow to its natural content size while still
      // capping at cardMaxHeight so a long bulk forge stays scrollable.
      // 窗 2026-09-21 — A JANELA TEM A ALTURA DO QUE TEM DENTRO quando cabe
      // (medido acima, `_cabe`); quando não cabe, a altura fixa de sempre —
      // o caminho que rola no WebKit do iPhone.
      const _conteudo = !fs && (compact || (_onda && _cabe));
      const cardHeight = _conteudo ? "auto" : cardMaxHeight;
      // ⚠️ E COM ALTURA AUTOMÁTICA O CORPO NÃO PODE TER BASE ZERO. Medido a
      // 21/09 a 390x844: o selector do Eu (o único `compact` do jogo) abria
      // com o cartão a **80px** e o corpo a **28px** com 260px de conteúdo —
      // os sete destinos escondidos numa faixa. É a lição do `Overlay`
      // (`flex:"0 1 auto"`: cresce com o conteúdo e encolhe quando o tecto
      // morde), que o `Modal` nunca tinha aprendido.
      const bodyFlex = _conteudo ? "0 1 auto" : "1 1 0";

      const modalContent = (
        <div
          onClick={handleBackdrop}
          style={{
            position:"fixed", inset:0, zIndex: z,
            // Darker bg (.92) compensates for the removed blur. Owner
            // reported (2026-05-10) "Apèrto no meio do modal nao seleciona
            // bem nao pode subir nem baixar" on iPhone Telegram WebView.
            // backdrop-filter is a known WebKit bug on Telegram WebView:
            // it creates a GPU compositing layer that intercepts touch
            // events on the children. Removing the blur is the only
            // reliable fix for tap+scroll working inside the modal on iOS.
            // The mini-app is the same WebView on Android, so this fix
            // benefits all phones.
            background: _onda ? ONDA_JANELA.veu : "rgba(4,6,12,.92)",
            pointerEvents:"auto",
            display:"flex",
            alignItems: fs ? "stretch" : "center",
            justifyContent:"center",
            // Bottom padding reserves 110px MIN for BottomNav clearance OR
            // safe-area-inset-bottom + 90px (whichever is larger). This
            // ensures the modal card NEVER renders behind the BottomNav
            // chrome (gold cloud SVG + icon row). Top padding stays at
            // safe-area-inset-top OR 12px so the header is visible below
            // the iPhone notch.
            // Onda R3 — fs modals portal para o body e escapam o padding do
            // shell: em Telegram-fullscreen (Bot API 8.0, o mapa) as DUAS
            // safe-areas protegem o título/✕; fora do fullscreen valem 0px →
            // byte-idêntico ao antigo `0`.
            padding: fs
              ? "calc(var(--tg-safe-area-inset-top, 0px) + var(--tg-content-safe-area-inset-top, 0px)) 0 0"
              : "max(env(safe-area-inset-top), 12px) 12px max(110px, calc(env(safe-area-inset-bottom) + 90px))",
            animation:"fadein 180ms ease",
          }}
        >
          <div
            ref={_cardRef}
            onClick={(e) => e.stopPropagation()}
            style={{
              width:"100%",
              maxWidth: fs ? "100%" : modalWidth(maxWidth, _modalWide, _onda),
              // Owner request 2026-05-10 (3:47 screenshots): modal deve
              // ocupar quase toda a altura — "o ideal é o modal do meio
              // poder mexer dentro e o titulo encima e os botao embaixo".
              // Fixar height = cardMaxHeight resolve 2 coisas:
              //   (a) garante que o pattern sticky-header / scroll-body /
              //       sticky-footer é VISÍVEL — body ocupa o middle
              //       generoso, com header e footer sempre presentes.
              //   (b) Fixa o iOS scroll bug — flex:1 1 0 + overflow:auto
              //       só funciona em iOS quando o pai tem altura definida.
              //       Com height:auto + maxHeight a altura efectiva ficava
              //       intrínseca-ao-conteúdo no WebKit.
              // Trade-off: modais com pouco conteúdo terão body com algum
              // espaço vazio, mas o visual fica mais premium e consistente
              // (todos os modais agora se sentem como "screens" focadas).
              // EXCEPTION: result modals pass compact={true} to grow to
              // their natural height (capped at cardMaxHeight). The body
              // still scrolls if content overflows because we keep
              // maxHeight bounded.
              height: cardHeight,
              maxHeight: cardMaxHeight,
              background:"linear-gradient(180deg, rgba(var(--card-rgb),.98), rgba(6,9,16,1))",
              border: fs ? "none" : `1px solid ${accentColor}`,
              borderRadius: fs ? 0 : 14,
              display:"flex", flexDirection:"column",
              overflow:"hidden",
              boxShadow: fs ? "none" : "0 20px 60px rgba(0,0,0,.7)",
              animation: animation || (shake ? "bt-shake-horizontal .35s ease-in-out" : "modal-in 220ms cubic-bezier(.2,.8,.2,1)"),
              position:"relative",
              // isolation:isolate gives the card its own stacking context
              // independent of the backdrop's GPU compositing layer. iOS
              // Safari needs this when the modal child has touchAction set
              // and uses overflow:auto.
              isolation:"isolate",
              ...(_onda && !fs ? semMoldura(cardStyle) : cardStyle),
              ...(_onda && !fs ? {
                background: ONDA_JANELA.fundo,
                border: "1px solid " + ONDA_JANELA.fio,
                borderRadius: 0,
                boxShadow: ONDA_JANELA.sombra,
              } : {}),
            }}
          >
            {_onda && !fs && (title != null || shouldShowClose || headerExtra) && (
              <div style={{
                flexShrink:0, position:"relative", zIndex:2,
                display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:12,
                padding: _modalWide ? "28px 24px 6px 40px" : "20px 12px 4px 22px",
              }}>
                <div style={{
                  flex:1, minWidth:0, paddingTop: 4,
                  fontFamily: NIV_ONDA.serif, fontWeight:400, color: NIV_ONDA.paper,
                  fontSize: _modalWide ? 34 : 28, lineHeight: _modalWide ? (38/34) : (32/28),
                  letterSpacing:"-.02em", overflowWrap:"anywhere",
                }}>{typeof title === "string" ? ondaNomeLimpo(title) : title}</div>
                {headerExtra}
                {shouldShowClose && (
                  <button onClick={onClose} aria-label={t("btn_close") || "Close"} style={{
                    flexShrink:0, background:"none", border:"none", cursor:"pointer",
                    width:44, height:44, padding:0, display:"grid", placeItems:"center",
                    color: NIV_ONDA.paper, fontFamily: NIV_ONDA.serif, fontSize:26, lineHeight:1,
                  }}>×</button>
                )}
              </div>
            )}
            {!(_onda && !fs) && (title != null || shouldShowClose || headerExtra) && (
              <div style={{
                flexShrink:0,
                display:"flex", alignItems:"center", justifyContent:"space-between",
                gap:10, padding:"11px 14px 10px",
                background:"linear-gradient(180deg, rgba(var(--surface-rgb),.96), rgba(var(--card-rgb),.92))",
                borderBottom:`1px solid ${accentColor}`,
                position:"relative", zIndex:2,
              }}>
                <div style={{
                  fontFamily:"'Cinzel',serif", fontSize:13.5, fontWeight:700,
                  color:"var(--gold2)", letterSpacing:.4, lineHeight:1.3,
                  flex:1, minWidth:0,
                  overflow:"hidden", textOverflow:"ellipsis",
                }}>{title}</div>
                {headerExtra}
                {shouldShowClose && (
                  <button onClick={onClose} aria-label={t("btn_close") || "Close"} style={{
                    flexShrink:0, background:"rgba(0,0,0,.4)",
                    border:`1px solid ${accentColor}`,
                    borderRadius:8, width:28, height:28,
                    color:"var(--gold2)", cursor:"pointer", fontSize:15,
                    display:"grid", placeItems:"center", padding:0,
                  }}>✕</button>
                )}
              </div>
            )}
            <div
              ref={_bodyRef}
              className={"scroll-area" + (bodyClassName ? " " + bodyClassName : "")}
              style={{
                // flex:1 1 0 (NOT auto) forces iOS to compute available
                // space from the parent's max-height MINUS header/footer,
                // ignoring intrinsic content size. With basis:auto the
                // content's natural height took precedence and pushed the
                // card past max-height before the scroll constraint kicked
                // in — which is why owner couldn't scroll on iPhone (the
                // scroll container's effective height was content-size,
                // not viewport-bounded).
                flex: bodyFlex,
                minHeight:0,
                overflowY:"auto",
                overflowX:"hidden",
                WebkitOverflowScrolling:"touch",
                overscrollBehavior:"contain",
                // touch-action:pan-y on the actual scrolling element is the
                // single most important line for iOS Telegram WebView.
                // Without it the WebView consumes vertical drag for its own
                // gestures (the host chat scroll). Owner reported (2026-05-10):
                // "no telefone não posso subir e nem baixar" + "Apèrto no
                // meio do modal nao seleciona bem".
                touchAction:"pan-y",
                padding: (_onda && !fs) ? (_modalWide ? "10px 40px 30px" : "8px 22px 22px") : "14px",
                ...bodyStyle,
              }}
            >
              {children}
            </div>
            {footer && (
              <div style={(_onda && !fs) ? {
                flexShrink:0, position:"relative", zIndex:2,
                padding: _modalWide ? "0 40px 32px" : "0 22px max(env(safe-area-inset-bottom), 20px)",
              } : {
                flexShrink:0,
                padding:"10px 14px max(env(safe-area-inset-bottom), 12px)",
                borderTop:`1px solid ${accentColor}`,
                background:"linear-gradient(0deg, rgba(var(--card-rgb),.98), rgba(var(--card-rgb),.85))",
                position:"relative", zIndex:2,
              }}>{footer}</div>
            )}
          </div>
        </div>
      );

      // Render to document.body via Portal so position:fixed escapes
      // any ancestor scroll container (the iOS Safari bug).
      return ReactDOM.createPortal(modalContent, document.body);
    }

    // 至 P1 — a chegada ([016]). Só apresentação; P2/P3 entram como ReactNode
    // em onAgir. Não escolhe operações, não navega, não activa flags.
    function ChegadaCena({ p, cult, onAgir, atalhos, wide, notifCount, onSino, onLoja, onPerfil,
                          portas, onPortas }) {
      // Pelo DONO UNICO, nunca com um `featureEnabled("a_obra")` novo: a
      // guarda do §19 conta as leituras por ficheiro exactamente para
      // impedir que a chave-mestra volte a ter dois donos.
      const enabled = typeof ondaCultOn === "function" && ondaCultOn();
      const player = p || {};
      // 🔴 O NOME DO JOGADOR E' `dao_name`. O `/player` TEM um campo `name` e
      // ele vale `None` — `name` pertence aos objectos aninhados (`sect.name`,
      // `boss.name`). A 1a versao desta cena lia `player.name` porque a MINHA
      // tarefa listou o campo errado, e a chegada saiu **sem nome nenhum** com
      // 880 guardas verdes. So' apareceu a OLHAR.
      const nomeDoJogador = player.dao_name || player.name || "";
      // HomeTab passa useApi; aceitar também o payload já desembrulhado.
      const data = cult && (cult.data || cult);
      const live = key => data && Object.prototype.hasOwnProperty.call(data, key)
        ? data[key] : player[key];
      const meditating = !!live("is_meditating");
      const endMs = Number(live("meditation_end_ms")) || 0;
      const [now, setNow] = useState(Date.now);
      useEffect(() => {
        if (!enabled || !meditating || endMs <= 0) return;
        setNow(Date.now());
        if (endMs <= Date.now()) return;
        const timer = setInterval(() => {
          const time = Date.now();
          setNow(time);
          if (time >= endMs) clearInterval(timer);
        }, 1000);
        return () => clearInterval(timer);
      }, [enabled, meditating, endMs]);
      // OFF não monta sequer o estilo local; alternar a flag conserva os hooks.
      if (!enabled || !p) return null;

      // ⚠️ As palavras desta peça vivem em `miniapp/i18n/*.json`, como todas
      // as outras. A 1ª versão trazia-as inlineadas nas três línguas dentro
      // deste ficheiro — e a culpa era da TAREFA, que proibia tocar em
      // ficheiros partilhados. Texto fora do i18n não passa pela guarda de
      // paridade das três línguas e diverge em silêncio.
      const w = {
        stones: t("chegada_pedras"), jade: t("chegada_jade"),
        resources: t("chegada_recursos"), fragments: t("chegada_fragmentos"),
        life: t("chegada_vida"), next: t("chegada_proximo_avanco"),
        full: t("chegada_vida_cheia"), hurt: t("chegada_vida_reduzida"),
        empty: t("chegada_sem_vida"), over: t("chegada_acima_capacidade"),
        ceiling: t("chegada_ultima_camada"), ending: t("chegada_a_terminar"),
        until: t("chegada_termina_em"),
      };
      const realm = Math.min(10, Math.max(0, Number(live("realm")) || 0));
      const subLayer = Number(live("sub_layer")) || 1;
      const atCeiling = realm >= 10 && subLayer >= 9;
      const hpMax = Math.max(0, Number(live("max_hp")) || 0);
      // NULL é cheio. O teste de ausência nunca pode ser um teste de truthiness.
      const hpRaw = live("current_hp");
      const hp = hpRaw == null ? hpMax : Math.max(0, Number(hpRaw) || 0);
      const qi = Math.max(0, Number(live("qi")) || 0);
      const qiMax = Math.max(0, Number(live("qi_capacity")) || 0);
      const cb = Math.max(0, Number(live("cultivation_base")) || 0);
      const threshold = Math.max(0, Number(live("cb_threshold")) || 0);
      const cbPct = threshold > 0 ? Math.min(100, cb / threshold * 100) : 0;
      const medKeys = { light:"meditation_light", deep:"meditation_deep", void:"meditation_void",
        celestial_dao:"meditation_celestial", dao_basic:"meditation_dao_basic",
        dao_deep:"meditation_dao_deep", dao_transcend:"meditation_dao_transcend" };
      const medKey = medKeys[live("meditation_type")];
      const remaining = Math.max(0, endMs - now);
      const state = meditating
        ? (endMs > 0 && remaining === 0 ? w.ending
          : [ondaNomeLimpo(t("home_meditating")), medKey ? ondaNomeLimpo(t(medKey)) : null,
             endMs > 0 ? w.until + " " + fmtDuration(remaining) : null].filter(Boolean).join(" · "))
        : t("onda_state_idle");
      const healthState = hp <= 0 ? w.empty : hp < hpMax ? w.hurt : w.full;
      const power = player.display_combat_power;
      const realmLabel = realmName(realm);
      const balances = [
        { mark:"stone", label:w.stones, value:player.spirit_stones },
        { mark:"jade", label:w.jade, value:player.spirit_jade },
      ];
      const bands = [
        { label:w.life, value:hp, max:hpMax, color:NIV_ONDA.seal },
        { label:t("qi"), value:qi, max:qiMax, color:NIV_ONDA.paper },
      ];

      return (
        <section className={"chegada-cena" + (wide ? " chegada-cena--wide" : "")}
          aria-label={nomeDoJogador}
          style={{ background:NIV_ONDA.ink, color:NIV_ONDA.paper, fontFamily:NIV_ONDA.body,
            "--chegada-ink":NIV_ONDA.ink, "--chegada-line":NIV_ONDA.line, "--chegada-muted":NIV_ONDA.muted,
            "--chegada-gold":NIV_ONDA.gold, "--chegada-label":NIV_ONDA.label,
            "--chegada-paper":NIV_ONDA.paper, "--chegada-wash":NIV_ONDA.wash,
            "--chegada-serif":NIV_ONDA.serif }}>
          <style>{`
            .chegada-cena { min-width:0; display:grid; grid-template-columns:minmax(0,1fr); }
            .chegada-cena * { box-sizing:border-box; }
            .chegada-cena .chegada-saldos { grid-column:1/-1; display:grid; position:relative; z-index:2;
              grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:8px 12px;
              padding:12px 16px; border-bottom:1px solid var(--chegada-line); align-items:center; }
            .chegada-cena .chegada-saldo { min-width:0; }
            .chegada-cena .chegada-label { display:flex; align-items:center; gap:6px;
              font-size:12px; line-height:16px; color:var(--chegada-muted); }
            .chegada-cena .chegada-num { font-size:16px; line-height:22px; font-weight:500;
              font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }
            .chegada-cena .chegada-recursos { min-width:0; }
            .chegada-cena .chegada-recursos > summary {
              display:flex; align-items:center; min-height:44px; cursor:pointer;
              font-size:12px; line-height:16px; color:var(--chegada-gold); list-style:none; }
            .chegada-cena .chegada-recursos > summary::-webkit-details-marker { display:none; }
            .chegada-cena .chegada-recursos[open] > summary { text-decoration:underline; text-underline-offset:4px; }
            .chegada-cena .chegada-detalhes { position:absolute; top:100%; left:16px; right:16px;
              display:flex; flex-wrap:wrap; gap:12px 28px; padding:16px;
              background:var(--chegada-ink); border:1px solid var(--chegada-line); }
            /* UMA linha, como a decisao (a) manda: Recursos a' esquerda e
               sino + Loja a' direita. A 1a versao trazia os rotulos longos
               do aria-label do cabecalho antigo e, a 390px, os dois BOTOES
               empilharam-se: 108px de altura para duas accoes.
               ATENCAO: este comentario vive DENTRO de um template literal
               de JS. Uma crase aqui FECHA-O e o ficheiro deixa de compilar
               -- foi exactamente o que aconteceu na 1a tentativa. */
            .chegada-cena .chegada-acessos { grid-column:1/-1; display:flex;
              align-items:center; gap:8px; padding:0 16px 10px; position:relative; }
            .chegada-cena .chegada-acessos .chegada-acesso:first-child { margin-left:auto; }
            .chegada-cena .chegada-acesso { display:inline-flex; align-items:center; gap:7px;
              min-height:44px; padding:0 12px; background:none; color:var(--chegada-muted);
              border:1px solid var(--chegada-line); border-radius:4px; cursor:pointer;
              font:inherit; font-size:13px; line-height:18px; }
            .chegada-cena .chegada-conta { min-width:18px; height:18px; padding:0 5px;
              display:inline-grid; place-items:center; border-radius:9px;
              background:var(--chegada-gold); color:var(--chegada-ink);
              font-size:11px; font-weight:600; font-variant-numeric:tabular-nums; }
            .chegada-cena .chegada-palco { position:relative; isolation:isolate; overflow:hidden;
              min-width:0; display:flex; flex-direction:column; }
            .chegada-cena .chegada-identidade { position:relative; z-index:1; padding:16px 16px 0; }
            .chegada-cena .chegada-nome { margin:0; font-family:var(--chegada-serif);
              font-size:44px; line-height:46px; font-weight:400; letter-spacing:-.025em; overflow-wrap:anywhere; }
            .chegada-cena .chegada-nome--toca { display:block; width:100%; text-align:left;
              background:none; border:none; padding:0; color:inherit; cursor:pointer; }
            .chegada-cena .chegada-reino { margin-top:6px; display:flex; flex-wrap:wrap; gap:2px 10px;
              font-size:13px; line-height:20px; color:var(--chegada-gold); }
            .chegada-cena .chegada-estado { margin:8px 0 0; font-size:14px; line-height:20px; }
            .chegada-cena .chegada-figura { position:relative; z-index:1; flex:1; min-height:128px;
              display:flex; align-items:center; justify-content:center; pointer-events:none; }
            .chegada-cena .chegada-faixas { position:relative; z-index:1; padding:0 16px 12px; }
            .chegada-cena .chegada-vitais { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
            .chegada-cena .chegada-vitais .chegada-label { font-family:var(--chegada-label);
              font-size:11px; letter-spacing:.12em; text-transform:uppercase; }
            .chegada-cena .chegada-nota { margin:2px 0 0; font-size:12px; line-height:18px; color:var(--chegada-muted); }
            .chegada-cena .chegada-avanco { margin-top:12px; padding-top:10px; border-top:1px solid var(--chegada-line); }
            .chegada-cena .chegada-avanco-topo { display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; gap:4px 12px; }
            .chegada-cena .chegada-avanco h3 { margin:0; font-family:var(--chegada-serif);
              font-size:24px; line-height:28px; font-weight:500; }
            .chegada-cena .chegada-agir { min-width:0; min-height:112px; padding:12px 16px 16px; }
            .chegada-cena .chegada-atalhos { grid-column:1/-1; display:grid;
              grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; padding:0 16px 16px; }
            .chegada-cena .chegada-portas { grid-column:1/-1; padding:0 16px 12px; }
            .chegada-cena .chegada-portas-btn { display:flex; align-items:center; gap:10px;
              width:100%; min-height:44px; padding:0 12px; cursor:pointer; font:inherit;
              text-align:left; color:var(--chegada-paper); border-radius:6px;
              background:var(--chegada-wash); border:1px solid var(--chegada-line); }
            .chegada-cena .chegada-portas-rot { flex-shrink:0; font-family:var(--chegada-label);
              font-size:9px; letter-spacing:.14em; text-transform:uppercase; color:var(--chegada-gold); }
            .chegada-cena .chegada-portas-nomes { flex:1; min-width:0; font-size:12px; line-height:16px;
              color:var(--chegada-muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
            .chegada-cena .chegada-portas-seta { flex-shrink:0; font-size:17px; line-height:1;
              color:var(--chegada-gold); }
            .chegada-cena :focus-visible { outline:2px solid var(--chegada-gold); outline-offset:4px; }
            .chegada-cena.chegada-cena--wide { grid-template-columns:minmax(0,1.8fr) minmax(280px,1fr); column-gap:28px; }
            .chegada-cena--wide .chegada-saldos { grid-template-columns:minmax(160px,220px) minmax(160px,220px);
              justify-content:end; padding:12px 24px; }
            .chegada-cena--wide .chegada-palco { min-height:600px; }
            .chegada-cena--wide .chegada-identidade { padding:28px 28px 0; }
            .chegada-cena--wide .chegada-nome { font-size:60px; line-height:60px; }
            .chegada-cena--wide .chegada-figura { min-height:240px; justify-content:flex-end; padding-right:24px; }
            .chegada-cena--wide .chegada-faixas { padding:0 28px 24px; }
            .chegada-cena--wide .chegada-agir { padding:28px 24px 24px 0; }
            @media (prefers-reduced-motion:reduce) {
              .chegada-cena *, .chegada-cena *::before, .chegada-cena *::after {
                animation:none !important; transition:none !important; scroll-behavior:auto !important;
              }
            }
          `}</style>

          <div className="chegada-saldos">
            {balances.map(balance => (
              <div className="chegada-saldo" key={balance.mark}>
                <span className="chegada-label"><Mark name={balance.mark} size={16} />{balance.label}</span>
                <div className="chegada-num">{fmtFull(balance.value ?? 0)}</div>
              </div>
            ))}
          </div>

          {/* 至 A SEGUNDA LINHA DA ZONA 1 — decisao (a) do Astra:
              *"primeira linha com os dois saldos nomeados; segunda com
              **Recursos** a' esquerda e **sino + Loja** a' direita"*.
              🔴 Ela existe porque a chegada RECOLHE o `PlayerHeader`: sem estes
              dois botoes, recolher o cabecalho trocava uma duplicacao por uma
              PERDA — o jogador ficava sem notificacoes e sem Loja.
              ⚠️ Cada um leva PALAVRA, nao so' marca: *"o sino conserva contador
              e nome acessivel; Loja conserva rotulo"*. E os alvos sao de 44px,
              que e' o minimo que a [016] fixa. */}
          {(onSino || onLoja) && (
            <div className="chegada-acessos">
              {/* Recursos a' ESQUERDA, sino e Loja a' direita, na MESMA linha —
                  e' a letra da decisao (a). A 1a versao deixou-o numa linha
                  propria acima e custou mais 44px por nada. */}
              <details className="chegada-recursos">
                <summary>{w.resources}</summary>
                <div className="chegada-detalhes">
                  <div><span className="chegada-label"><Mark name="shard" size={16} />{w.fragments}</span>
                    <div className="chegada-num">{fmtFull(player.celestial_fragments ?? 0)}</div></div>
                  {power != null && <div><span className="chegada-label">{t("battle_power")}</span>
                    <div className="chegada-num">{fmtFull(power)}</div></div>}
                </div>
              </details>
              {onSino && (
                <button type="button" className="chegada-acesso" onClick={onSino}>
                  <Mark name="bell" size={16} />
                  <span>{t("chegada_avisos")}</span>
                  {Number(notifCount) > 0 && (
                    <span className="chegada-conta">{Number(notifCount) > 99 ? "99+" : notifCount}</span>
                  )}
                </button>
              )}
              {onLoja && (
                <button type="button" className="chegada-acesso" onClick={onLoja}>
                  <Mark name="jade" size={16} />
                  <span>{t("chegada_loja")}</span>
                </button>
              )}
            </div>
          )}

          <div className="chegada-palco">
            <RealmBackdrop key={realm} realm={realm} wide={wide} fill />
            <header className="chegada-identidade">
              {onPerfil ? (
                /* 至 *"raiz espiritual no **Perfil**, aberto pelo nome/retrato
                   na cena. Conservar ai' o indicador de karma e o acesso ao
                   Perfil"* — decisao (a). Sem isto, recolher o cabecalho
                   levava a raiz espiritual e o karma com ele. */
                <button type="button" className="chegada-nome chegada-nome--toca"
                        onClick={onPerfil}>{nomeDoJogador}</button>
              ) : (
                <h2 className="chegada-nome">{nomeDoJogador}</h2>
              )}
              <div className="chegada-reino">
                <span>{realmLabel}</span>
                <span style={{ color:NIV_ONDA.muted }}>{t("onda_realm_layer", { realm, sub:subLayer })}</span>
              </div>
              <p className="chegada-estado">{state}<span style={{ color:NIV_ONDA.muted }}> · {healthState}</span></p>
            </header>
            <div className="chegada-figura" aria-hidden="true">
              <CultivatorFigure realm={realm} meditating={meditating} gender={player.gender}
                size={wide ? 304 : 144} plain />
            </div>
            <div className="chegada-faixas">
              <div className="chegada-vitais">
                {bands.map(band => (
                  <div key={band.label}>
                    <span className="chegada-label">{band.label}</span>
                    <div className="chegada-num">{fmtFull(band.value)}</div>
                    <div role={band.max > 0 ? "meter" : "group"} aria-label={band.label}
                      aria-valuemin={band.max > 0 ? 0 : undefined} aria-valuemax={band.max > 0 ? band.max : undefined}
                      aria-valuenow={band.max > 0 ? Math.min(band.value, band.max) : undefined}
                      aria-valuetext={band.max > 0 ? fmtFull(band.value) + " / " + fmtFull(band.max) : undefined}>
                      <CultFio pct={band.max > 0 ? band.value / band.max * 100 : 0}
                        color={band.color} over={band.max > 0 && band.value > band.max} />
                    </div>
                    {band.max > 0 && band.value > band.max && <p className="chegada-nota">{w.over}</p>}
                  </div>
                ))}
              </div>
              <div className="chegada-avanco">
                <div className="chegada-avanco-topo">
                  <h3>{w.next}</h3>
                  {!atCeiling && threshold > 0 && <span className="chegada-num">{fmtFull(Math.floor(cbPct))}%</span>}
                </div>
                {atCeiling ? <p className="chegada-nota">{t("cena_ceiling_title")} · {w.ceiling}</p> : (
                  <React.Fragment>
                    {threshold > 0 && <CultFio pct={cbPct} color={NIV_ONDA.gold} />}
                    <p className="chegada-nota">{threshold > 0
                      ? (cb >= threshold ? t("onda_cb_reached") : t("onda_cb_left", { n:fmtFull(threshold - cb) }))
                      : t("onda_cb_label") + " · " + fmtFull(cb)}</p>
                  </React.Fragment>
                )}
              </div>
            </div>
          </div>
          <div className="chegada-agir">{onAgir}</div>
          {/* 至 A MACANETA. Ordem do owner, 2026-09-23, textual: *"como vou
              encontrar corpo etc. (...) tenho que clicar 2 vezes no eu pra abrir
              o menuzinho pra ver o corpo"*.
              🔴 MEDIDO antes de escrever: o selector dos sete destinos do Eu so'
              abre ao RETOCAR `SELF` ja' estando na chegada (`tabs.js`, o ramo
              `tab === h.landing`) — e a chegada nao tinha **uma unica palavra**
              a dizer que ele existe. Corpo, Celestial, Parceiro, Conquistas:
              quatro destinos sem nome em lado nenhum do ecra.
              ⚠️ E NAO e' a pilha de portas de volta ([016] §1 matou-a, 2.397px
              -> 415px). E' UMA linha de 44px que NOMEIA o que ha' e diz quantos
              faltam; quem abre continua a ser a sobreposicao. Os nomes vem de
              fora, do mesmo array que ela abre — a cena APRESENTA, nao decide
              nem navega (a mesma lei do `onAgir` e dos `atalhos`). */}
          {/* ⚠️ SO' NA COMPOSICAO ESTREITA. Medido a 1440x900 a OLHAR: no PC a
              lateral (P5) ja' nomeia os sete destinos, e a linha punha-os uma
              SEGUNDA vez no mesmo ecra — exactamente a duplicacao de
              identidade que o Astra mandou matar. Uma declaracao por
              composicao: estreita ⇒ a linha; larga ⇒ a lateral. */}
          {(!wide && portas && portas.length && onPortas) ? (
            <div className="chegada-portas">
              <button type="button" onClick={onPortas} className="chegada-portas-btn">
                <span className="chegada-portas-rot">{t("chegada_portas_rotulo")}</span>
                <span className="chegada-portas-nomes">
                  {portas.slice(0, 3).join(" · ")}
                  {portas.length > 3 ? " · " + t("chegada_portas_mais", { n: portas.length - 3 }) : ""}
                </span>
                <span className="chegada-portas-seta" aria-hidden="true">›</span>
              </button>
            </div>
          ) : null}
          {/* 至 A zona dos ATALHOS ([016] §1): *"Dois, Técnicas e Equipamento:
              imagem do item equipado e nome"*. Entram montados de fora, como o
              `onAgir` — a cena APRESENTA, não decide nem navega. */}
          {atalhos ? <div className="chegada-atalhos">{atalhos}</div> : null}
        </section>
      );
    }

    // ═══════════════════════════════════════════════════════════════════════
    // 武 2.2 — O COMBATE É UMA CENA
    // ═══════════════════════════════════════════════════════════════════════
    //
    // O desenho é do Astra (`Olho/Astra/2026-09-16-o-jogo-deixa-de-ser-texto.md`
    // §2): *"A luta é uma cena de confronto. Dois lados identificados, distância
    // entre eles, rodada e estado claros. Não é tabuleiro (…). As técnicas são
    // peças ilustradas de escolha sob essa cena."*
    //
    // 🔴 O QUE ESTA CENA **NÃO** INVENTA, e é metade do desenho. O contrato do
    // duelo é **rodada simultânea**: escolher uma arte, confirmar, esperar os
    // dois lados. Não há casas, deslocamento, escolha de alvo, compra de cartas
    // nem combo — e por isso nada disso se desenha. Uma fila temporal ("você
    // ataca, depois ele") seria uma regra NOVA pintada como se já existisse.
    //
    // ⚠️ ELA APRESENTA, NÃO DECIDE. Mesma lei da `ChegadaCena`: o relógio, o
    // envio, a rendição, o `pickEfetivo` e os blocos de consequência do fim
    // continuam a viver no `DuelArenaModal`, que é o dono do estado. Aqui entra
    // tudo por `props`. Foi assim que a onda 1 não perdeu nenhuma das quatro
    // consequências condicionais (gruta, tributo, coração-demônio, proibido).
    //
    // ⚠️ ZERO EMOJI. A catraca do §15 está em 1300/1300 no `tabs.js` e 23 no
    // `ui.js` — **sem folga**. Cada glifo desta cena é uma `<Mark>` vectorial ou
    // a arte da peça; o único emoji que aparece vem do PAYLOAD (`tech.emoji`,
    // uma variável) e serve de último recurso dentro da chapa.

    // 印 O EMBLEMA DE CADA LADO — e porque é um emblema e não um retrato.
    //
    // 🔴 MEDIDO a 2026-09-23 (`A_CHEGADA.md §7.3`), lendo o servidor:
    // `duel_state.opponent` traz `telegram_id · dao_name · hp · hp_max ·
    // combat_qi · combat_qi_max · submitted`. **Não há retrato, nem chave de
    // arte, nem reino, nem género.** Logo: emblema + nome, como o Astra decidiu
    // — *"não vestir adversário humano com uma besta arbitrária"*.
    //
    // Para PvE há `npc_archetype`, e aí o arquétipo é identidade LEGÍTIMA: a
    // luta é contra um Bandido, e dizê-lo é dizer a verdade.
    //
    // ⚠️ UMA TABELA, UM DONO. A marca e a palavra de cada arquétipo saem daqui
    // e de mais nenhum sítio — a alternativa era um `switch` na cena e outro no
    // relato, que é a Lei 0 §2 na letra.
    var CENA_EMBLEMAS = {
      bandit:        { mark:"sword",  key:"cena_arq_bandit" },
      sect_disciple: { mark:"robe",   key:"cena_arq_sect_disciple" },
      beast:         { mark:"paw",    key:"cena_arq_beast" },
      demon:         { mark:"stance", key:"cena_arq_demon" },
      boss:          { mark:"dragon", key:"cena_arq_boss" },
      elder:         { mark:"robe",   key:"cena_arq_elder" },
    };

    // O emblema de um lado, resolvido. `voce` ⇒ a figura sentada (a mesma
    // identidade que a chegada usa). Um arquétipo que eu não conheça cai no
    // combatente genérico com a palavra "Adversário" — nunca num emblema
    // errado, e nunca em nada.
    function cenaEmblemaDe(lado, arquetipo) {
      if (lado === "voce") return { mark:"seated", papel:t("cena_voce") };
      var e = arquetipo && CENA_EMBLEMAS[arquetipo];
      if (e) return { mark:e.mark, papel:t(e.key) };
      return { mark:"stance", papel:t("cena_adversario") };
    }

    // 地 DE ONDE VEM A LUTA — e **não** onde ela acontece.
    //
    // 🔴 `duel_state` tem `pve_source` e **não tem campo de lugar nem de reino**
    // (medido, `A_CHEGADA.md §7.4`). Pela regra do Astra — *"o lugar só é
    // ilustrado quando conhecido, senão tinta neutra"* — a cena nasce em tinta
    // neutra, e a palavra diz o que se SABE: a fonte. Dizer "Masmorra" é
    // verdade; pintar um corredor de masmorra seria invenção.
    // 🔴 05/10 — AS CHAVES SÃO AS DO SERVIDOR, e só elas (`duel_engine.PVE_SOURCES`,
    // a fonte única das origens PvE). Esta tabela nasceu à mão com seis chaves:
    // quatro certas e DUAS que nenhum duelo alguma vez teve (`npc_combat`,
    // `arena` — o servidor grava `arena_npc_fallback`). Resultado medido no
    // Beta, o único mundo onde a cena se desenha: 582 de 4.520 duelos PvE — a
    // ARENA inteira (292), a exploração (131), o desafio a um cultivador
    // (130), a emboscada, as duas provas — diziam "Duelo" no vão. O duelo do
    // report do [jogador] (03/10, `arena_npc_fallback`) era um deles. A §10 do
    // `_test_relatos_0814.py` lê o tuplo do servidor e exige estas chaves, todas e
    // só estas.
    var CENA_FONTES = {
      arena_npc_fallback: "cena_fonte_arena",
      dungeon_boss:       "cena_fonte_masmorra",
      exploration:        "cena_fonte_exploracao",
      heart_demon:        "cena_fonte_demonio",
      hidden_rite:        "cena_fonte_sucessao",
      jianghu_ambush:     "cena_fonte_emboscada",
      legacy_cave:        "cena_fonte_gruta",
      npc_cultivator:     "cena_fonte_desafio",
      npc_hunt:           "cena_fonte_caca",
      sect_trial:         "cena_fonte_prova_seita",
    };
    function cenaFonte(state) {
      var k = state && state.pve_source && CENA_FONTES[state.pve_source];
      return k ? t(k) : t("cena_fonte_duelo");
    }

    // 效 O QUE A ARTE FAZ, EM PALAVRAS — só o que o contrato entrega.
    //
    // ⚠️ *"Somente os efeitos disponíveis no contrato podem ser descritos como
    // efeito mecânico. Nome da técnica não é previsão de dano."* O payload traz
    // `effect_type` + `effect_value` (+ `effect_round`); um `effect_type` que eu
    // não saiba nomear devolve `null` e a tela mostra só o custo — que é
    // verdade. Inventar a frase seria prometer um efeito que ninguém mediu.
    function cenaEfeito(tech) {
      if (!tech || !tech.effect_type) return null;
      var k = "cena_efeito_" + tech.effect_type;
      var v = Number(tech.effect_value) || 0;
      var s = typeof safeT === "function"
        ? safeT(k, { n: Math.round(v * 100) / 100 }, "")
        : "";
      return s && s !== k ? s : null;
    }

    // 選 O QUE ESTÁ ESCOLHIDO, E QUANTO CUSTA — num sítio só.
    //
    // ⚠️ Isto existe porque a confirmação MUDOU DE CASA. Ela desenha-se no
    // rodapé da janela (sempre à vista) e o detalhe desenha-se no corpo da cena
    // — dois sítios, a mesma pergunta. Derivar "qual a arte e quanto custa" em
    // cada um seria a Lei 0 §2 na letra: duas ligações à mão divergem sempre, e
    // a divergente aqui escreveria um custo no rodapé e outro no detalhe.
    //
    // ⚠️ `pick` é o **efectivo**, já derivado pelo modal: uma arte escolhida na
    // ronda passada pode ter deixado de ser pagável nesta, e o que se mostra
    // tem de ser o que se ENVIA.
    function cenaEscolha(state, pick) {
      const you = (state && state.you) || {};
      const techs = (you.techniques || []).filter(tt => !!tt && tt.qi_cost !== undefined);
      const tech = pick === 0 ? null : techs.filter(tt => tt.id === pick)[0] || null;
      return {
        techs: techs,
        tech: tech,
        nome: tech ? tech.name : t("duel_tech_basic"),
        custo: tech ? t("cena_custo", { n: fmtFull(tech.qi_cost || 0) })
                    : t("cena_custo_zero"),
        paga: !tech || (Number(you.combat_qi) || 0) >= (Number(tech.qi_cost) || 0),
      };
    }

    // 結 A FAIXA DE CONFIRMAÇÃO — e ela vive no RODAPÉ da janela.
    //
    // *"Confirmação | mínimo 80 | Resumo 'arte · custo'; botão de 52px,
    // confirmação explícita."* O Astra escreveu-a como faixa de uma tela cheia;
    // numa janela da casa a faixa que está sempre à vista é o rodapé, e a
    // 1ª versão (dentro do corpo que rola) deixava **Render** fixo no pé e o
    // golpe abaixo da dobra — visto a olho, a 390px.
    //
    // ⚠️ A rendção entra aqui ao lado, e com a pele da onda: o `ActionBtn`
    // clássico punha um botão azul do painel antigo debaixo de uma cena de
    // tinta — e "a inconsistência é pior do que a ausência".
    function CenaConfirmacao({ resumo, enviado, busy, onConfirmar, onRender, acabou, onFechar }) {
      const P = NIV_ONDA;
      const base = {
        minHeight: 52, cursor: "pointer", fontFamily: P.label, fontSize: 13,
        letterSpacing: 1.4, textTransform: "uppercase", padding: "0 14px",
      };
      if (acabou) {
        return (
          <button type="button" onClick={onFechar} style={{
            ...base, width: "100%", border: "1px solid " + P.gold,
            background: P.gold, color: P.ink,
          }}>{t("btn_close")}</button>
        );
      }
      return (
        <div style={{ display: "grid", gap: 8, minHeight: 80, alignContent: "end" }}>
          <span style={{
            fontFamily: P.label, fontSize: 10, letterSpacing: 1.2,
            textTransform: "uppercase", color: P.muted, textAlign: "center",
            overflowWrap: "anywhere",
          }}>{resumo}</span>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" onClick={onRender} disabled={!!busy} style={{
              ...base, flex: 1, minWidth: 0, border: "1px solid " + P.edge,
              background: "transparent", color: P.paper, fontSize: 11,
            }}>{t("duel_btn_forfeit")}</button>
            <button type="button" onClick={onConfirmar} disabled={!!busy || !!enviado}
                    style={{
                      ...base, flex: 1.8, minWidth: 0,
                      border: "1px solid " + (enviado || busy ? P.line : P.gold),
                      background: enviado || busy ? "transparent" : P.gold,
                      color: enviado || busy ? P.muted : P.ink,
                      cursor: enviado || busy ? "default" : "pointer",
                    }}>
              {enviado ? t("duel_waiting_opp") : t("duel_btn_submit")}
            </button>
          </div>
        </div>
      );
    }

    // 版 A CHAPA DE ARTE DA CENA — o dono único de *"mostra-me esta peça"* aqui.
    //
    // ⚠️ REGRA §4.3, textual: *"A arte pode faltar e o botão tem de funcionar na
    // mesma — caixa igual, desenho neutro, nome legível. Nunca outra técnica,
    // imagem aleatória ou emoji."* Os três estados desta chapa:
    //   · `src` carrega  ⇒ a arte
    //   · `src` falha    ⇒ a marca neutra, MESMA caixa (pelo `onError`)
    //   · sem `src`      ⇒ a marca neutra, MESMA caixa
    // O emoji do catálogo entra como ÚLTIMO recurso e só quando não há marca —
    // nunca como identidade.
    //
    // ⚠️ O ESTILO É INLINE DE PROPÓSITO. A 1ª versão declarava `.cena-chapa`
    // dentro do `<style>` da cena E dentro do da entrada — a mesma chapa com
    // duas folhas, que divergem no primeiro acerto. Um componente, um dono.
    function CenaChapa({ src, marca, emoji, alta, acento, plena }) {
      // ⚠️ POR DENTRO É O `CardArt`, e não uma segunda chapa — a guarda F-7 (B)
      // apanhou-me a escrever a SEXTA. Dele vem o verso honesto (anéis de
      // tinta), o `onError`, o `lazy` e a entrada suave; daqui vem apenas a
      // ALTURA fixa e a marca vectorial no lugar do glifo.
      //
      // 🔴 A guarda estava certa e a lição já é velha: o verso honesto
      // duplicou-se TRÊS vezes nesta casa, e de cada vez uma família de peças
      // ficou dias atrás (a correcção de 07/09 fez um caminho próprio para as
      // bestas e o artefacto e a pílula ficaram três dias para trás). Um prop
      // novo no dono é barato; um segundo desenhador custa a mesma correcção
      // duas vezes — e a segunda esquece-se.
      //
      // A marca entra como `glyph`: o `CardArt` desenha o glifo por BAIXO da
      // arte, sempre, e uma `<Mark>` é um nó como qualquer outro. Sem marca (o
      // destaque da resolução) cai no emoji do catálogo — ÚLTIMO recurso,
      // nunca identidade.
      // `dissolve={100}` desliga o pé dissolvido: num recorte de 62–96px o
      // degradê comeria a peça inteira (a mesma razão do `PieceIcon`).
      const h = alta || 84;
      return (
        <div style={{ position:"relative", width:"100%",
                      height: plena ? "100%" : h, overflow:"hidden" }}>
          <CardArt fill src={src || null} accent={acento || NIV_ONDA.muted}
                   focus="50% 38%" dissolve={100}
                   glyphSize={Math.round(h * .30)}
                   glyph={marca && NIV_MARKS[marca]
                     ? <Mark name={marca} size={Math.max(18, Math.round(h * .40))} />
                     : (emoji || undefined)} />
        </div>
      );
    }

    // 牌 UMA OPÇÃO DA RODADA — arte reconhecível ANTES da escolha.
    //
    // *"Uma imagem por opção equipada/disponível. A arte é reconhecível antes da
    // escolha, em recorte de cerca de 72–96 px, com **nome fora da área mais
    // movimentada da imagem**."* Por isso o nome vive numa faixa de tinta SOB a
    // chapa, e não por cima da pintura.
    //
    // 🔴 `art_key`, NÃO `name`. O nome vem TRADUZIDO — e desde 2026-09-23 também
    // dentro do duelo (`_tech_lido` no `duel_engine`) — e o slug de "Passo do
    // Trovão" não está no índice. A chave é o nome canónico, e é ela que
    // encontra a arte nas três línguas.
    function CenaOpcao({ tech, basico, selecionada, pagavel, onEscolher, nome, custo, alta }) {
      const src = basico ? null
        : pieceArt("technique", tech && tech.name, tech && tech.art_key);
      const cls = "cena-opcao"
        + (selecionada ? " cena-opcao--escolhida" : "")
        + (pagavel ? "" : " cena-opcao--presa");
      return (
        <button type="button" className={cls}
                aria-pressed={selecionada ? "true" : "false"}
                disabled={!pagavel}
                onClick={() => { if (pagavel && onEscolher) onEscolher(); }}>
          <CenaChapa src={src} marca={basico ? "stance" : "sword"}
                     emoji={tech && tech.emoji} alta={alta || 84}
                     acento={selecionada ? NIV_ONDA.gold : NIV_ONDA.muted} />
          <span className="cena-opcao-nome">{nome}</span>
          <span className="cena-opcao-custo" style={_ONDA_TNUM}>{custo}</span>
        </button>
      );
    }

    // 武 A CENA — as faixas da geometria do Astra, por esta ordem.
    //
    //   (cabeçalho)          a JANELA já o desenha: voltar/×, título, subtítulo
    //   Confronto    176px   dois emblemas de 72px, nomes, Vida dos dois lados,
    //                        Qi do jogador; a DISTÂNCIA entre eles é vazio
    //   Última rodada 48-64  uma linha por lado + o relato completo
    //   Decisão      ≥200px  até quatro opções ilustradas em duas colunas
    //   Confirmação   ≥80px  "arte · custo" + um alvo de 52px
    //
    // ⚠️ A faixa 1 NÃO se desenha aqui. O `Modal` já tem o título, o subtítulo
    // (rodada · relógio) e o × que o teclado alcança, com o portal da prévia.
    // Repeti-lo punha dois cabeçalhos no mesmo ecrã — a duplicação de
    // identidade que a chegada matou a 16/09 (181px de cromo → 12px).
    function CenaDuelo({ state, remaining, pick, caiu, onEscolher, onConfirmar,
                         busy, enviado, wide, resultado, aviso }) {
      const P = NIV_ONDA;
      const you = (state && state.you) || {};
      const opp = (state && state.opponent) || {};
      const acabou = !!state && (state.state === "finished" || state.state === "forfeited");
      // Só artes com custo LIDO existem como opção: um `undefined` em `qi_cost`
      // não é 0 — é uma leitura que falhou, e um botão sem preço mente.
      const techs = (you.techniques || []).filter(tt => !!tt && tt.qi_cost !== undefined);

      // ── o destaque da resolução ────────────────────────────────────────────
      // *"A arte da técnica usada pode ganhar destaque breve no lado do autor do
      // golpe, **somente quando o evento identificar a técnica**. Até um
      // destaque por lado a cada resolução de rodada, apresentados juntos."*
      //
      // 🔴 E o evento IDENTIFICA-A: `action_log[].a.tech = {id, name, emoji}` —
      // e `null` quando o alvo esquiva (medido, `A_CHEGADA.md §7.2`). Logo o
      // destaque é legítimo; a esquiva não tem destaque nenhum, que é o estado
      // honesto: sem arte, sem pintura.
      const [destaque, setDestaque] = useState(null);
      const ultima = useRef(null);
      const log = (state && state.action_log) || [];
      let linha = null;
      for (let i = log.length - 1; i >= 0; i--) {
        if (log[i] && log[i].round && (log[i].a || log[i].b)) { linha = log[i]; break; }
      }
      const ladoVoce = (state && state.you_side) === "b" ? "b" : "a";
      const ladoOpp = ladoVoce === "a" ? "b" : "a";
      const actVoce = linha ? linha[ladoVoce] : null;
      const actOpp = linha ? linha[ladoOpp] : null;
      const rondaLog = linha ? linha.round : null;
      useEffect(() => {
        if (rondaLog == null || rondaLog === ultima.current) return undefined;
        ultima.current = rondaLog;
        const a = actVoce && actVoce.tech ? actVoce.tech : null;
        const b = actOpp && actOpp.tech ? actOpp.tech : null;
        if (!a && !b) return undefined;       // esquiva dos dois: nada a destacar
        setDestaque({ voce:a, opp:b });
        const id = setTimeout(() => setDestaque(null), 900);
        return () => clearTimeout(id);
      }, [rondaLog]);

      // ── a escolha ──────────────────────────────────────────────────────────
      // Até quatro mosaicos, o básico incluído. *"A quantidade de técnicas é
      // variável; a interface não inventa quatro quando houver menos nem elimina
      // as excedentes."* As excedentes entram na SELECÇÃO VERTICAL, em baixo, na
      // mesma janela — e a ESCOLHA é preservada: se a arte escolhida estiver
      // fora das três primeiras, ela passa à frente para continuar à vista.
      const [tudo, setTudo] = useState(false);
      const VISIVEIS = 3;
      let visiveis = techs.slice(0, VISIVEIS);
      if (pick !== 0 && !visiveis.some(tt => tt.id === pick)) {
        const esc = techs.filter(tt => tt.id === pick)[0];
        if (esc) visiveis = [esc].concat(techs.filter(tt => tt.id !== pick).slice(0, VISIVEIS - 1));
      }
      const qi = Number(you.combat_qi) || 0;
      const paga = tt => qi >= (Number(tt.qi_cost) || 0);
      // ⚠️ pelo DONO ÚNICO: o rodapé da janela escreve o mesmo resumo, e duas
      // derivações da mesma pergunta divergem sempre.
      const esc = cenaEscolha(state, pick);
      const escolhida = esc.tech;
      const nomeEscolhida = esc.nome;
      const custoEscolhida = esc.custo;

      const opcaoBasico = alta => (
        <CenaOpcao key="b0" basico selecionada={pick === 0} pagavel alta={alta}
                   nome={t("duel_tech_basic")} custo={t("cena_custo_zero")}
                   onEscolher={() => { if (onEscolher) onEscolher(0); }} />
      );
      const opcaoTec = (tt, alta) => (
        <CenaOpcao key={tt.id} tech={tt} selecionada={pick === tt.id}
                   pagavel={paga(tt)} nome={tt.name} alta={alta}
                   custo={paga(tt) ? t("cena_custo", { n: fmtFull(tt.qi_cost || 0) })
                                   : t("cena_sem_qi")}
                   onEscolher={() => { if (onEscolher) onEscolher(tt.id); }} />
      );

      // ── uma barra NOMEADA ──────────────────────────────────────────────────
      // Nunca um número sem nome, e nunca uma percentagem sozinha: o valor
      // INTEIRO e o máximo, pelo `fmtFull` (o HP de produção tem 12 dígitos e
      // `158.98B` não diz a um jogador quanto ele tem).
      function faixa(rot, v, max, cor, dir) {
        const vv = Math.max(0, Number(v) || 0);
        const mm = Math.max(0, Number(max) || 0);
        const pct = mm > 0 ? Math.max(0, Math.min(100, (vv / mm) * 100)) : 0;
        // 🔴 TRES LINHAS, E NAO UMA — corrigido a OLHAR, a 390px.
        //
        // A 1a versao punha `158.977.287.826 / 201.000.000.000` numa linha com
        // `white-space:nowrap`. O HP de PRODUCAO tem 12 digitos (medido), e o
        // par inteiro nao cabe em metade de um telemovel: a coluna esticou, o
        // adversario saiu do ecra pela direita e o emblema dele ficou cortado.
        // 1070 guardas verdes, e o transbordo estava a um screenshot de
        // distancia.
        //
        // ⚠️ E a correccao NAO e' abreviar. O numero inteiro e' regra da onda
        // (`158.98B` nao diz a um jogador quanto ele tem). E' a mesma solucao da
        // onda 1: o ATUAL e o MAXIMO em linhas separadas, e a linha quebra onde
        // precisar em vez de empurrar a coluna.
        // 🔴 05/10 — O REPORT DO [jogador] (03/10): *"in PvE arena, popup of combat
        // shows opponent's hp out of bound on screen."* O comentário de baixo
        // PROMETIA "quebram sozinhos" e o CSS dizia `white-space:nowrap` no
        // par inteiro: o espaço entre o valor e o "de" nunca foi um ponto de
        // quebra. Com o adversário a 10 dígitos (o NPC da arena na produção) e
        // 88px por lado a 390, o lado direito saía do ecrã 20px — número e
        // barra. O arnês encenava o adversário com 7 dígitos; ninguém o viu.
        //
        // Agora são DUAS unidades que fluem: o valor e "de máx", cada uma
        // inteira (`inline-block`), separadas por um espaço de verdade. Cabem
        // juntas → uma linha; não cabem → "de máx" desce. E se uma unidade
        // sozinha não couber, quebra entre grupos de milhar (`fmtFullQuebra`) e
        // continua no ecrã. Medido a 320/360/375/390/412/1440 com 13 dígitos
        // dos dois lados (`scripts/_test_cena_cabe.py`).
        const deMax = t("cena_de_max", { n: "\u0001" });
        const corte = deMax.indexOf("\u0001");
        // ⚠️ O NÚMERO ENCOLHE, NÃO PARTE (a regra da §28: `158.977.287.8` / `26`
        // lê-se como OUTRO número). A largura dele em `em` sai dos próprios
        // caracteres — dígito tabular ≈ .58em, separador ≈ .24em, texto ≈ .55em
        // (medido no Noto Sans a 12px: 13 dígitos = 100,4px) — e o CSS faz
        // min(tamanho cheio, coluna ÷ largura), com piso. A 390 nada encolhe;
        // a 360/320 o HP de 13 dígitos fica numa linha, menor. Os `<wbr>` do
        // `fmtFullQuebra` ficam só para um browser sem container queries.
        const emDe = s => {
          let d = 0, o = 0;
          for (let i = 0; i < s.length; i++) {
            const c = s.charAt(i);
            if (c >= "0" && c <= "9") d++; else o++;
          }
          return d * 0.58 + o * 0.24;
        };
        const emVal = emDe(fmtFull(vv));
        const emMax = emDe(fmtFull(mm))
          + (corte >= 0 ? (deMax.length - 1) * 0.55 : 1.65);
        return (
          <div className={"cena-faixa" + (dir ? " cena-faixa--dir" : "")}>
            <span className="cena-faixa-rot">{rot}</span>
            {/* ⚠️ UMA linha que FLUI, nao duas fixas. O valor e o máximo vêm
                juntos e quebram sozinhos quando o número é grande — o de
                produção tem 12 dígitos. Três linhas fixas por barra davam 323px
                de confronto (o Astra pediu 176) e empurravam a DECISÃO para
                fora do ecrã, que é o principal da tela. Medido a 390px. */}
            <span className="cena-faixa-num" style={_ONDA_TNUM}>
              <span className="cena-faixa-val"
                    style={{ "--cena-em": emVal.toFixed(2) }}>{fmtFullQuebra(vv)}</span>
              {" "}
              <span className="cena-faixa-max"
                    style={{ "--cena-em": emMax.toFixed(2) }}>
                {/* o número do máximo é a SUA unidade: se não couber depois do
                    "de", desce inteiro — a quebra gulosa enchia a linha até ao
                    último `<wbr>` e partia-o (visto a 320: "de 1.146.050.083." /
                    "754"). */}
                {corte >= 0
                  ? <>{deMax.slice(0, corte)}<span className="cena-faixa-maxn">{fmtFullQuebra(mm)}</span>{deMax.slice(corte + 1)}</>
                  : t("cena_de_max", { n: fmtFull(mm) })}
              </span>
            </span>
            <div className="cena-faixa-trilho">
              <i style={{ width: pct + "%", background: cor }} />
            </div>
          </div>
        );
      }

      function ladoCena(quem, nome, arq, hp, hpMax, pronto, tecDestaque) {
        const emb = cenaEmblemaDe(quem, arq);
        const voce = quem === "voce";
        return (
          <div className={"cena-lado cena-lado--" + (voce ? "voce" : "opp")}>
            <div className="cena-emblema" style={{ color: voce ? P.gold : P.seal }}>
              <Mark name={emb.mark} size={38} />
              {/* o destaque: a pintura POR CIMA do emblema, do lado do autor do
                  golpe. `pointer-events:none` — decorativo, nunca no caminho do
                  toque, e some sozinho em 900ms. */}
              {tecDestaque ? (
                <span className="cena-destaque" aria-hidden="true">
                  <CenaChapa plena src={pieceArt("technique", tecDestaque.name,
                                                 tecDestaque.art_key)}
                             marca={null} emoji={tecDestaque.emoji}
                             alta={72} acento={voce ? P.gold : P.seal} />
                </span>
              ) : null}
            </div>
            <span className="cena-papel">{emb.papel}</span>
            <strong className="cena-nome">{nome || "—"}</strong>
            {!acabou ? (
              <span className="cena-estado">
                {pronto ? t("cena_lado_pronto") : t("cena_lado_escolhe")}
              </span>
            ) : null}
            {faixa(t("cena_vida"), hp, hpMax, P.seal, !voce)}
            {/* ⚠️ O Qi do JOGADOR vive AQUI, dentro do lado dele — a faixa do
                Astra diz *"Vida identificada dos dois lados; **Qi do
                jogador**"*, uma faixa só. A 1ª versão pô-lo numa banda própria
                por baixo: ficava órfão (um número sem dono visível) e roubava
                ~64px à decisão, que é o principal da tela.
                O adversário não o mostra: o `combat_qi` dele chega no payload,
                mas ler o que o OUTRO pode pagar seria uma regra que este duelo
                não tem. */}
            {voce ? faixa(t("cena_qi"), you.combat_qi, you.combat_qi_max, P.gold)
                  : null}
          </div>
        );
      }

      function consequencia(act) {
        if (!act) return null;
        if (act.evaded) return t("duel_log_evaded");
        if (act.dodged) return t("duel_log_dodged");
        return t("cena_dano", { n: fmtFull(act.damage || 0) });
      }

      return (
        <section className={"cena-duelo" + (wide ? " cena-duelo--wide" : "")}
                 style={{
                   color: P.paper, fontFamily: P.body,
                   "--cena-ink": P.ink, "--cena-paper": P.paper, "--cena-gold": P.gold,
                   "--cena-seal": P.seal, "--cena-muted": P.muted, "--cena-line": P.line,
                   "--cena-wash": P.wash, "--cena-edge": P.edge, "--cena-serif": P.serif,
                   "--cena-label": P.label,
                 }}>
          <style>{`
            .cena-duelo { min-width:0; display:grid; gap:8px; }
            .cena-duelo * { box-sizing:border-box; }

            /* ── a faixa do CONFRONTO. O fundo e' TINTA NEUTRA: o contrato nao
                  diz o lugar (A_CHEGADA 7.4), e por isso nao ha' paisagem
                  nenhuma — nem decoracao que pareca obstaculo jogavel. */
            /* 05/10 (report do [jogador]) - o vao era uma trilha AUTO, e numa grelha a
               trilha auto CRESCE ate ao seu max-content (112px) ANTES de as 1fr
               receberem um pixel: a 390 sobravam 88px por lado e o numero de
               12 digitos do jogador (90px) ja nao cabia. O comentario do vao
               dizia "encolhe primeiro" e a grelha fazia o contrario. Agora o
               vao cresce no maximo ate 64px (ou a sua palavra mais longa, que
               nunca transborda) e o resto e dos dois lados: 113px a 390. No PC
               (cena-duelo--wide) a trilha continua auto - la ha largura. */
            .cena-duelo .cena-confronto { position:relative; isolation:isolate;
              display:grid; grid-template-columns:minmax(0,1fr) fit-content(64px) minmax(0,1fr);
              align-items:start; gap:6px; padding:10px 9px 9px;
              min-height:176px; border:1px solid var(--cena-line);
              background:
                radial-gradient(120% 90% at 50% 8%, rgba(236,229,216,.06), transparent 62%),
                var(--cena-ink); }
            .cena-duelo .cena-lado { min-width:0; display:grid; gap:2px;
              justify-items:start; text-align:left; }
            .cena-duelo .cena-lado > * { max-width:100%; min-width:0; }
            .cena-duelo .cena-lado--opp { justify-items:end; text-align:right; }
            .cena-duelo .cena-emblema { position:relative; width:64px; height:64px;
              display:grid; place-items:center; border:1px solid var(--cena-line);
              background:var(--cena-wash); margin-bottom:2px; }
            .cena-duelo .cena-destaque { position:absolute; inset:0; overflow:hidden;
              pointer-events:none; animation:cena-lampo .9s ease forwards; }
            @keyframes cena-lampo { 0%{opacity:0} 18%{opacity:.92} 100%{opacity:0} }
            .cena-duelo .cena-papel { font-family:var(--cena-label); font-size:9.5px;
              letter-spacing:1.3px; text-transform:uppercase; color:var(--cena-muted); }
            .cena-duelo .cena-nome { font-family:var(--cena-serif); font-size:18px;
              line-height:21px; font-weight:500; color:var(--cena-paper);
              max-width:100%; overflow-wrap:anywhere; }
            .cena-duelo .cena-estado { font-size:10px; line-height:13px;
              color:var(--cena-muted); }
            /* ⚠️ min-width:0 em TODA a coluna e no que ela contem — e SEM
               crases neste comentario: ele vive dentro de um template
               literal, e uma crase aqui FECHA a string e parte o build.
               Sem o min-width, uma grelha de 1fr nao encolhe abaixo do
               conteudo e o numero de 12 digitos empurra o adversario
               para fora do ecra. */
            .cena-duelo .cena-faixa { width:100%; min-width:0; margin-top:4px;
              display:grid; gap:0; }
            .cena-duelo .cena-faixa-rot { font-family:var(--cena-label); font-size:9px;
              letter-spacing:1.2px; text-transform:uppercase; color:var(--cena-muted); }
            /* 05/10 - o par NAO e nowrap: o espaco entre o valor e o "de" e o
               ponto de quebra. Cada metade e uma unidade inteira (inline-block):
               cabe na linha ou desce inteira; e so se sozinha nao couber na
               coluna (a largura de um inline-block nunca passa da do pai)
               quebra entre grupos de milhar, nos wbr do fmtFullQuebra. */
            .cena-duelo .cena-faixa-num { font-size:12px; line-height:16px;
              color:var(--cena-paper); letter-spacing:-.1px; }
            .cena-duelo .cena-faixa-val,
            .cena-duelo .cena-faixa-max,
            .cena-duelo .cena-faixa-maxn { display:inline-block; }
            .cena-duelo .cena-faixa-max { font-size:9.5px; color:var(--cena-muted); }
            /* O NUMERO ENCOLHE PARA CABER, NUNCA PARTE (a regra da s28: um numero
               partido le-se como OUTRO numero). A coluna e um container; o
               tamanho e min(cheio, coluna / largura-em do numero), que o
               componente escreve em --cena-em. Piso de 8px (7.5 no "de max").
               Dentro de supports porque com var() um browser sem container
               queries nao cai na regra de cima - perdia o tamanho inteiro. */
            @supports (container-type:inline-size) {
              .cena-duelo .cena-faixa { container-type:inline-size; }
              .cena-duelo .cena-faixa-val {
                font-size:max(8px, min(12px, calc(98cqi / var(--cena-em, 1)))); }
              .cena-duelo .cena-faixa-max {
                font-size:max(7.5px, min(9.5px, calc(98cqi / var(--cena-em, 1)))); }
            }
            .cena-duelo .cena-faixa-trilho { margin-top:4px; }
            .cena-duelo .cena-faixa-trilho { height:5px; background:var(--cena-wash);
              overflow:hidden; }
            .cena-duelo .cena-faixa--dir .cena-faixa-trilho > i { margin-left:auto; }
            .cena-duelo .cena-faixa-trilho > i { display:block; height:100%;
              transition:width .4s ease; }

            /* ── a DISTANCIA entre os dois lados. E' VAZIO, de proposito: um fio
                  vertical e a rodada ao meio. Nada de casas nem de setas — este
                  contrato nao tem movimento espacial nenhum para desenhar. */
            /* o vao e' AR: encolhe primeiro, para os dois lados nunca sairem
               do ecra. Era um min-width de 66px fixo e roubava largura aos nomes.
               05/10 - SEM min-width:0: com ele a trilha podia ficar mais estreita
               do que a palavra mais longa do vao (EXPLORACAO, Exploration), e a
               palavra transbordava para cima do lado. O minimo e a palavra.
               E overflow-wrap:normal porque a janela (scroll-area) herda
               anywhere a tudo o que tem dentro: com ele o minimo da palavra
               desaparecia e a trilha de 64px partia "EXPLORATI" / "ON" - medido
               e visto a 320 e a 390. */
            .cena-duelo .cena-vao { display:grid; gap:6px; justify-items:center;
              align-content:start; max-width:112px; padding-top:6px;
              overflow-wrap:normal; }
            /* 05/10 - com o vao a 64px no telefone, "Rodada 2 de 10" partia-se em
               "Rodada 2 de" / "10" (o numero orfao). Linhas EQUILIBRADAS: "Rodada
               2" / "de 10". Um browser sem text-wrap cai na quebra de sempre,
               que continua dentro do vao - nunca fora dele. */
            .cena-duelo .cena-vao > span { text-wrap:balance; }
            .cena-duelo .cena-vao-fonte { font-family:var(--cena-label); font-size:9px;
              letter-spacing:1.4px; text-transform:uppercase; color:var(--cena-gold);
              text-align:center; }
            .cena-duelo .cena-vao-ronda { font-family:var(--cena-serif); font-size:13px;
              color:var(--cena-muted); text-align:center; }
            .cena-duelo .cena-vao-fio { width:1px; height:30px; justify-self:center;
              background:linear-gradient(180deg,transparent,var(--cena-line),transparent); }
            .cena-duelo .cena-relogio { font-family:var(--cena-label); font-size:10px;
              letter-spacing:.8px; color:var(--cena-paper); text-align:center; }
            .cena-duelo .cena-relogio--urgente { color:var(--cena-seal); }

            /* ── a ULTIMA RODADA: uma linha por lado, com a consequencia. */
            .cena-duelo .cena-ultima { border:1px solid var(--cena-line);
              padding:8px 11px; display:grid; gap:4px; }
            .cena-duelo .cena-rot { font-family:var(--cena-label); font-size:9.5px;
              letter-spacing:1.4px; text-transform:uppercase; color:var(--cena-muted); }
            .cena-duelo .cena-ultima-linha { display:flex; gap:8px; font-size:12px;
              line-height:17px; align-items:baseline; flex-wrap:wrap; }
            .cena-duelo .cena-ultima-quem { font-family:var(--cena-label); font-size:9.5px;
              letter-spacing:1.2px; text-transform:uppercase; flex-shrink:0;
              min-width:78px; }
            .cena-duelo .cena-ultima-tec { color:var(--cena-paper); }
            .cena-duelo .cena-ultima-cons { color:var(--cena-muted); }
            .cena-duelo .cena-vazia { font-size:11.5px; color:var(--cena-muted);
              font-style:italic; }

            /* ── a DECISAO: duas colunas, ate' quatro mosaicos. */
            .cena-duelo .cena-decisao { display:grid; gap:9px; min-height:200px;
              align-content:start; }
            .cena-duelo .cena-grelha { display:grid; gap:9px;
              grid-template-columns:minmax(0,1fr) minmax(0,1fr); }
            /* a SELECCAO VERTICAL das excedentes: uma coluna, na mesma janela,
               com a escolha preservada. Nunca um trilho horizontal sem
               indicacao — ordem do Astra. */
            .cena-duelo .cena-grelha--vertical { grid-template-columns:minmax(0,1fr); }
            .cena-duelo .cena-opcao { min-width:0; display:grid; padding:0 0 8px;
              text-align:left; cursor:pointer; background:var(--cena-ink);
              color:var(--cena-paper); border:1px solid var(--cena-line);
              font-family:inherit; transition:border-color .18s ease, background .18s ease; }
            .cena-duelo .cena-opcao--escolhida { border-color:var(--cena-gold);
              background:rgba(201,144,58,.10); }
            .cena-duelo .cena-opcao--presa { cursor:not-allowed; opacity:.55; }
            .cena-duelo .cena-opcao:focus-visible { outline:2px solid var(--cena-gold);
              outline-offset:2px; }
            .cena-duelo .cena-opcao-nome { display:block; padding:7px 9px 0;
              font-family:var(--cena-serif); font-size:15px; line-height:19px;
              color:var(--cena-paper); overflow-wrap:anywhere; }
            .cena-duelo .cena-opcao-custo { display:block; padding:3px 9px 0;
              font-size:10.5px; color:var(--cena-muted); }
            .cena-duelo .cena-opcao--presa .cena-opcao-custo { color:var(--cena-seal); }

            /* ── o detalhe da escolhida e a CONFIRMACAO. */
            .cena-duelo .cena-detalhe { display:grid; gap:3px; padding:9px 11px;
              border:1px solid var(--cena-line); background:var(--cena-wash); }
            .cena-duelo .cena-detalhe-nome { font-family:var(--cena-serif);
              font-size:17px; line-height:21px; color:var(--cena-paper); }
            .cena-duelo .cena-detalhe-linha { font-size:11.5px; line-height:17px;
              color:var(--cena-muted); }
            .cena-duelo .cena-aviso { font-size:11.5px; line-height:17px;
              color:var(--cena-gold); }
            /* a faixa de confirmacao MUDOU-SE para o rodape da janela e vive
               agora no componente CenaConfirmacao (estilo proprio, inline);
               saiu daqui junto com ela: regra morta e' divida, e a proxima
               pessoa acreditaria que esta cena ainda desenha um botao de
               enviar. */
            .cena-duelo .cena-mais { min-height:44px; width:100%; cursor:pointer;
              background:transparent; color:var(--cena-paper);
              border:1px solid var(--cena-edge); font-family:var(--cena-label);
              font-size:11px; letter-spacing:1.2px; text-transform:uppercase; }
            .cena-duelo .cena-mais:focus-visible { outline:2px solid var(--cena-gold);
              outline-offset:2px; }

            .cena-duelo--wide .cena-confronto { min-height:208px; padding:20px 20px 22px;
              grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); }
            .cena-duelo--wide .cena-emblema { width:80px; height:80px; }
            .cena-duelo--wide .cena-nome { font-size:23px; line-height:27px; }
            .cena-duelo--wide .cena-vao { min-width:96px; }
            .cena-duelo--wide .cena-grelha { grid-template-columns:repeat(4,minmax(0,1fr)); }
            .cena-duelo--wide .cena-grelha--vertical {
              grid-template-columns:minmax(0,1fr) minmax(0,1fr); }

            @media (prefers-reduced-motion:reduce) {
              .cena-duelo *, .cena-duelo *::before, .cena-duelo *::after {
                animation:none !important; transition:none !important; }
              /* movimento reduzido elimina o LAMPO, nunca a informacao: o dano
                 continua escrito na faixa da ultima rodada. */
              .cena-duelo .cena-destaque { display:none; }
            }
          `}</style>

          {/* ── O CONFRONTO ────────────────────────────────────────────────── */}
          <div className="cena-confronto">
            {ladoCena("voce", you.dao_name, null, you.hp, you.hp_max,
                      !!you.pending, destaque && destaque.voce)}
            <div className="cena-vao">
              <span className="cena-vao-fonte">{cenaFonte(state)}</span>
              <span className="cena-vao-fio" aria-hidden="true" />
              <span className="cena-vao-ronda">
                {t("cena_ronda", { n: state && state.round_idx,
                                   max: state && state.max_rounds })}
              </span>
              {state && state.sudden_death ? (
                <span className="cena-vao-fonte" style={{ color: P.seal }}>
                  {t("duel_sudden_death")}
                </span>
              ) : null}
              {/* o relógio REAL, e a regra que ele já cumpre: ao terminar o prazo
                  o jogo envia golpe básico. Dizê-lo AO LADO do relógio é ordem do
                  Astra — é a diferença entre um prazo e uma surpresa. */}
              {remaining != null && !acabou ? (
                <span className={"cena-relogio"
                                 + (remaining <= 5 ? " cena-relogio--urgente" : "")}
                      style={_ONDA_TNUM}>
                  {t("cena_relogio", { n: remaining })}
                </span>
              ) : null}
              {remaining != null && remaining <= 5 && !enviado && !acabou ? (
                <span className="cena-vao-ronda" style={{ fontSize:10 }}>
                  {t("duel_auto_hint")}
                </span>
              ) : null}
            </div>
            {ladoCena("opp", opp.dao_name, state && state.npc_archetype,
                      opp.hp, opp.hp_max, !!opp.submitted, destaque && destaque.opp)}
          </div>

          {/* ── A ÚLTIMA RODADA ───────────────────────────────────────────── */}
          <div className="cena-ultima">
            <span className="cena-rot">{t("cena_ultima_titulo")}</span>
            {linha ? (
              <>
                <div className="cena-ultima-linha">
                  <span className="cena-ultima-quem" style={{ color: P.gold }}>
                    {t("cena_voce")}
                  </span>
                  <span className="cena-ultima-tec">
                    {actVoce && actVoce.tech ? actVoce.tech.name : t("duel_tech_basic")}
                  </span>
                  <span className="cena-ultima-cons">{consequencia(actVoce)}</span>
                </div>
                <div className="cena-ultima-linha">
                  <span className="cena-ultima-quem" style={{ color: P.seal }}>
                    {cenaEmblemaDe("opp", state && state.npc_archetype).papel}
                  </span>
                  <span className="cena-ultima-tec">
                    {actOpp && actOpp.tech ? actOpp.tech.name : t("duel_tech_basic")}
                  </span>
                  <span className="cena-ultima-cons">{consequencia(actOpp)}</span>
                </div>
              </>
            ) : (
              <span className="cena-vazia">{t("cena_ultima_vazia")}</span>
            )}
          </div>

          {/* o resultado, montado de FORA: são as quatro consequências
              condicionais do duelo (gruta, tributo, coração-demônio, custo
              proibido) e elas continuam a viver no modal, que é o dono. */}
          {resultado || null}

          {/* ── A DECISÃO ─────────────────────────────────────────────────── */}
          {!acabou ? (
            <div className="cena-decisao">
              <span className="cena-rot">{t("cena_decisao_titulo")}</span>
              {/* a escolha CAIU e a tela diz porquê — nunca troca em silêncio. */}
              {caiu ? <span className="cena-aviso">{t("duel_tech_dropped")}</span> : null}
              <div className={"cena-grelha" + (tudo ? " cena-grelha--vertical" : "")}>
                {opcaoBasico(tudo ? 96 : 72)}
                {(tudo ? techs : visiveis).map(tt => opcaoTec(tt, tudo ? 96 : 72))}
              </div>
              {techs.length > VISIVEIS ? (
                <button type="button" className="cena-mais"
                        onClick={() => setTudo(!tudo)}>
                  {tudo ? t("cena_menos") : t("cena_todas", { n: techs.length + 1 })}
                </button>
              ) : null}

              {/* o detalhe da escolhida: custo, função e impedimento em PALAVRAS.
                  Só o que o contrato entrega. */}
              <div className="cena-detalhe">
                <span className="cena-detalhe-nome">{nomeEscolhida}</span>
                <span className="cena-detalhe-linha">{custoEscolhida}</span>
                {escolhida ? (
                  <>
                    {cenaEfeito(escolhida) ? (
                      <span className="cena-detalhe-linha">{cenaEfeito(escolhida)}</span>
                    ) : null}
                    {Number(escolhida.effect_round) > 0 ? (
                      <span className="cena-detalhe-linha">
                        {t("cena_ronda_efeito", { n: escolhida.effect_round })}
                      </span>
                    ) : null}
                    {escolhida.grade_mult ? (
                      <span className="cena-detalhe-linha">
                        {t("cena_compreensao", { mult: escolhida.grade_mult })}
                      </span>
                    ) : null}
                    {!paga(escolhida) ? (
                      <span className="cena-detalhe-linha" style={{ color: P.seal }}>
                        {t("cena_sem_qi")}
                      </span>
                    ) : null}
                  </>
                ) : (
                  <span className="cena-detalhe-linha">{t("cena_basico_funcao")}</span>
                )}
              </div>

              {/* 🔴 A CONFIRMAÇÃO NÃO VIVE AQUI — corrigido a OLHAR, a 390px.
                  A 1ª versão desenhava-a como última faixa do CORPO, e o corpo
                  ROLA: o que ficava fixo no pé da janela era **Render**, e a
                  acção principal caia abaixo da dobra. Ter a desistência sempre
                  à vista e o golpe escondido é o contrário do que a tela quer.
                  O Astra desenhou a confirmação como faixa de ≥80px de uma TELA
                  CHEIA; numa janela da casa, a faixa que está SEMPRE à vista é o
                  RODAPÉ — e é lá que ela passou a estar (`DuelArenaModal`), com o
                  resumo "arte · custo" por cima do alvo de 52px. */}
            </div>
          ) : null}

          {aviso || null}
        </section>
      );
    }

    // 武 A ENTRADA DO COMBATE — *"a aba Combate também tem que convidar a jogar"*.
    //
    // *"`CombatTab` ganha uma composição de aproximadamente 280 px no telefone:
    // imagem da técnica realmente equipada à direita, título/estado à esquerda e
    // botão **Escolher adversário** de 52 px abaixo. Esse botão abre o segmento
    // NPC e reutiliza `CombatNPCPanel`; **não inicia luta**. Sem técnica
    // equipada, usar o emblema neutro e oferecer **Preparar técnicas**."*
    //
    // ⚠️ Nenhum modo com custo ou PvP começa ao tocar na ilustração — a
    // ilustração não é um botão de luta, é a preparação a ver-se.
    function CenaEntradaCombate({ tecnica, usados, max, onEscolher, onPreparar, wide,
                                  explicacoes, onRefresh }) {
      const P = NIV_ONDA;
      const tem = !!tecnica;
      return (
        <section className={"cena-entrada" + (wide ? " cena-entrada--wide" : "")}
                 style={{
                   color: P.paper, fontFamily: P.body,
                   "--cena-ink": P.ink, "--cena-paper": P.paper, "--cena-gold": P.gold,
                   "--cena-muted": P.muted, "--cena-line": P.line, "--cena-wash": P.wash,
                   "--cena-edge": P.edge, "--cena-serif": P.serif, "--cena-label": P.label,
                 }}>
          <style>{`
            .cena-entrada { min-width:0; display:grid; gap:12px; padding:14px 13px 13px;
              border:1px solid var(--cena-line); margin-bottom:11px; background:
                radial-gradient(120% 90% at 84% 10%, rgba(236,229,216,.06), transparent 60%),
                var(--cena-ink); }
            .cena-entrada * { box-sizing:border-box; }
            .cena-entrada .cena-ent-topo { display:grid; gap:12px;
              grid-template-columns:minmax(0,1fr) 108px; align-items:start; }
            .cena-entrada .cena-ent-rot { display:block; font-family:var(--cena-label);
              font-size:9.5px; letter-spacing:1.4px; text-transform:uppercase;
              color:var(--cena-muted); }
            .cena-entrada .cena-ent-titulo { display:block; margin:2px 0 0;
              font-family:var(--cena-serif); font-size:26px; line-height:30px;
              font-weight:500; color:var(--cena-paper); }
            .cena-entrada .cena-ent-estado { display:block; margin-top:6px;
              font-size:12px; line-height:18px; color:var(--cena-muted); }
            .cena-entrada .cena-ent-tec { display:block; margin-top:8px;
              font-family:var(--cena-serif); font-size:17px; line-height:21px;
              color:var(--cena-gold); overflow-wrap:anywhere; }
            .cena-entrada .cena-ent-acao { min-height:52px; width:100%; cursor:pointer;
              border:1px solid var(--cena-gold); background:var(--cena-gold);
              color:var(--cena-ink); font-family:var(--cena-label); font-size:13px;
              letter-spacing:1.4px; text-transform:uppercase; }
            .cena-entrada .cena-ent-acao:focus-visible { outline:2px solid var(--cena-paper);
              outline-offset:2px; }
            .cena-entrada--wide { padding:20px 20px 18px; }
            .cena-entrada--wide .cena-ent-topo { grid-template-columns:minmax(0,1fr) 168px; }
            .cena-entrada--wide .cena-ent-titulo { font-size:34px; line-height:38px; }
            @media (prefers-reduced-motion:reduce) {
              .cena-entrada *, .cena-entrada *::before, .cena-entrada *::after {
                animation:none !important; transition:none !important; }
            }
          `}</style>
          <div className="cena-ent-topo">
            <div style={{ minWidth:0 }}>
              <span className="cena-ent-rot">{t("tab_combat")}</span>
              <strong className="cena-ent-titulo">{t("cena_entrada_titulo")}</strong>
              {/* 減 P7 — as duas frases NÃO são da mesma natureza. "Você ainda
                  não equipou nenhuma arte" é ESTADO (a única palavra a dizer que
                  o lugar está vazio) e fica sempre; "Sua arte está pronta" é a
                  explicação que o nome da arte, logo abaixo, já prova — é essa
                  que recolhe, depois de um equip confirmado. */}
              <span className="cena-ent-estado">
                {tem ? (
                  <Explica sistema="equipar" estados={explicacoes} onRefresh={onRefresh}>
                    {t("cena_entrada_com")}
                  </Explica>
                ) : t("cena_entrada_sem")}
              </span>
              {tem ? <span className="cena-ent-tec">{tecnica.name}</span> : null}
              {max != null ? (
                <span className="cena-ent-estado" style={_ONDA_TNUM}>
                  {t("cena_entrada_lugares", { n: usados || 0, max: max })}
                </span>
              ) : null}
            </div>
            {/* 🔴 A ARTE VEM PELA CHAVE. `tecnica.art_key` é o nome canónico que
                o servidor passou a mandar a 2026-09-23; antes disso esta chapa
                caía no verso em `pt` e em `es` — 129 artes por língua, com a
                guarda de 14/09 verde por cima. */}
            <CenaChapa src={tem ? pieceArt("technique", tecnica.name, tecnica.art_key) : null}
                       marca={tem ? "sword" : "stance"}
                       emoji={tem ? tecnica.emoji : null}
                       alta={wide ? 168 : 108}
                       acento={tem ? P.gold : P.muted} />
          </div>
          <button type="button" className="cena-ent-acao"
                  onClick={tem ? onEscolher : onPreparar}>
            {tem ? t("cena_entrada_escolher") : t("cena_entrada_preparar")}
          </button>
        </section>
      );
    }

    // 備 O PREPARO — *com o que você vai lutar*, antes de pagar o Qi.
    //
    // 🔴 O BURACO QUE ISTO TAPA FOI MEDIDO NO CÓDIGO, não suposto. O
    // `CombatNPCPanel` calcula `combatTechs` (as artes de combate equipadas) na
    // linha 20848 e **nunca o usa** — é código morto desde que o selector de
    // foco saiu, na v15.1.4. Ou seja: o jogador escolhe uma dificuldade, paga
    // entre 10 e 100 de Qi e entra numa luta **sem ver com o que vai lutar**.
    //
    // ⚠️ NÃO É UM SELECTOR. A escolha da arte é por RODADA, dentro do duelo —
    // foi isso que a v15.1.4 decidiu, e ressuscitar um "foco" aqui seria
    // reabrir uma decisão fechada. Isto só RESPONDE, e a resposta é a
    // preparação a ver-se: *"aqui a pintura da técnica equipa visualmente a
    // preparação"* (Astra, §2).
    //
    // ⚠️ E as artes vêm de `learned[]`, a lista que até 2026-09-23 mandava o
    // nome traduzido sem `art_key` — 129 peças por língua ao verso. Esta tira
    // só existe porque essa ligação passou a existir.
    function CenaPreparo({ techs, max, wide }) {
      const P = NIV_ONDA;
      const lista = (techs || []).filter(tt => !!tt);
      return (
        <section className={"cena-preparo" + (wide ? " cena-preparo--wide" : "")}
                 style={{
                   color: P.paper, fontFamily: P.body,
                   "--cena-ink": P.ink, "--cena-paper": P.paper, "--cena-gold": P.gold,
                   "--cena-muted": P.muted, "--cena-line": P.line, "--cena-wash": P.wash,
                   "--cena-serif": P.serif, "--cena-label": P.label,
                 }}>
          <style>{`
            .cena-preparo { min-width:0; display:grid; gap:9px; margin-bottom:10px;
              padding:12px 12px 13px; border:1px solid var(--cena-line);
              background:var(--cena-ink); }
            .cena-preparo * { box-sizing:border-box; }
            .cena-preparo .cena-prep-rot { display:flex; justify-content:space-between;
              gap:10px; align-items:baseline; font-family:var(--cena-label);
              font-size:9.5px; letter-spacing:1.4px; text-transform:uppercase;
              color:var(--cena-muted); }
            .cena-preparo .cena-prep-grelha { display:grid; gap:8px;
              grid-template-columns:repeat(auto-fill, minmax(78px, 1fr)); }
            .cena-preparo .cena-prep-peca { min-width:0; display:grid;
              border:1px solid var(--cena-line); background:var(--cena-wash);
              padding-bottom:6px; }
            .cena-preparo .cena-prep-nome { display:block; padding:5px 7px 0;
              font-family:var(--cena-serif); font-size:12.5px; line-height:16px;
              color:var(--cena-paper); overflow-wrap:anywhere; }
            .cena-preparo .cena-prep-custo { display:block; padding:2px 7px 0;
              font-size:10px; color:var(--cena-muted); }
            .cena-preparo .cena-prep-vazio { font-size:11.5px; line-height:17px;
              color:var(--cena-muted); font-style:italic; }
            .cena-preparo--wide .cena-prep-grelha {
              grid-template-columns:repeat(auto-fill, minmax(112px, 1fr)); }
            @media (prefers-reduced-motion:reduce) {
              .cena-preparo *, .cena-preparo *::before, .cena-preparo *::after {
                animation:none !important; transition:none !important; }
            }
          `}</style>
          <div className="cena-prep-rot">
            <span>{t("cena_preparo_titulo")}</span>
            {max != null ? (
              <span style={_ONDA_TNUM}>
                {t("cena_entrada_lugares", { n: lista.length, max: max })}
              </span>
            ) : null}
          </div>
          {lista.length ? (
            <div className="cena-prep-grelha">
              {lista.map(tt => (
                <div className="cena-prep-peca" key={tt.id}>
                  {/* 🔴 pela CHAVE, nunca pelo nome: `pieceArt(kind, name, artKey)`
                      prefere `artKey`, e é ele que está no índice. */}
                  <CenaChapa src={pieceArt("technique", tt.name, tt.art_key)}
                             marca="sword" emoji={tt.emoji}
                             alta={wide ? 84 : 62} acento={P.gold} />
                  <span className="cena-prep-nome">{tt.name}</span>
                  <span className="cena-prep-custo" style={_ONDA_TNUM}>
                    {t("cena_custo", { n: fmtFull(tt.qi_cost || 0) })}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            /* Lei §1 — o vazio DIZ o que fazer, e não fica calado. A porta é a
               aba Técnicas, que está a dois toques na mesma faixa de segmentos. */
            <span className="cena-prep-vazio">{t("cena_entrada_sem")}</span>
          )}
        </section>
      );
    }
