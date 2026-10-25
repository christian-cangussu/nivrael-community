// components/app.js — Phase 2 split (2026-05-02).
// App orchestrator + bootstrap. Loaded last. Mounts <App /> into #root after
// loading the i18n JSON dicts.

    // ─── Sprint 0 (FF-3/FF-4) — Surface Manifest (shared, world-scoped) ────────
    // The mini-app renders its surface from {realm, features} of the ACTIVE world
    // (server-authoritative; api("player").manifest). A feature OFF/absent → its
    // gated tab/panel does NOT draw. Top-level `var`/`function` → global across
    // the eval'd component scripts (same mechanism as TAB_DEFS), so ui.js's
    // BottomNav can read featureEnabled() at render time. Default {realm:"mortal",
    // features:{}} is the deploy-compat fallback: an old client / a pre-manifest
    // payload leaves every gated surface OFF and every ungated one drawing as
    // today (main byte-identical). FF-4: WORLD_MANIFEST.realm is the per-realm
    // shell selector — plumbed now (always "mortal"); shell-switch is a later sprint.
    var WORLD_MANIFEST = { realm: "mortal", features: {} };
    function featureEnabled(key) {
      return !!(WORLD_MANIFEST && WORLD_MANIFEST.features && WORLD_MANIFEST.features[key]);
    }

    // MV-9.5 — a Caravana tem CONJUNÇÃO DURA e o cliente tem de a respeitar.
    // `caravana_on()` no servidor é o AND de três flags; olhar só para
    // `caravana` abria a porta 🐫 num mundo sem `cidades`/`dungeons_regionais`
    // e o modal respondia `crv_locked` — uma porta que não leva a lado nenhum,
    // exatamente o que a Lei §1 proíbe.
    // ⚠️ Isto NÃO é "espelhar o gate" (o anti-padrão que apagou a seita
    // demoníaca): não há regra derivada aqui, é a leitura das MESMAS três
    // flags que o manifesto já entrega. O servidor continua a ser a verdade —
    // isto só evita desenhar a porta.
    function caravanEnabled() {
      return featureEnabled("caravana")
        && featureEnabled("cidades")
        && featureEnabled("dungeons_regionais");
    }

    // ─── App orchestrator ────────────────────────────────────────────────────
    function App() {
      // MA-32b — default landing is the Home hub. The 5 BottomNav tabs
      // (home, cultivation, inventory, crafting, settings) are visible;
      // every other tab is reachable via Home cards or programmatic setTab.
      const [tab, setTab] = useState("home");
      const [player, setPlayer] = useState(null);
      const [error, setError] = useState(null);
      // Multi-Servidor: when api("player") signals needs_world_start, the player
      // has no (separate, zeroed) character in the SECONDARY world they entered.
      // We show a "começar neste servidor" welcome → world/start → reload.
      const [needsWorldStart, setNeedsWorldStart] = useState(false);
      // O NOME DE CULTIVO e do jogador (report do owner 2026-08-26). Ate aqui
      // o servidor derivava-o do first_name — e, para quem entra pelo Google,
      // isso era o e-mail. Agora ele escolhe, e o erro DIZ o que fazer.
      const [wsName, setWsName] = useState("");
      const [wsErr, setWsErr] = useState("");
      // O ecra de criacao tem DOIS caminhos: nascer, ou reconhecer-se. O
      // segundo existe porque quem entrou pelo Google e ja joga no Telegram
      // (ou o contrario) nao quer um personagem novo — quer o dele.
      // ⚠️ E acontece AQUI, antes de existir personagem, que e o que faz o
      // vinculo nunca precisar de apagar nada.
      const [wsMode, setWsMode] = useState("new");   // "new" | "link"
      const [wsCode, setWsCode] = useState("");
      const [wsBusy, setWsBusy] = useState(false);
      // Owner request 2026-05-08 — tapping the jade chip in PlayerHeader
      // opens the Premium Shop as a full-screen modal (Taoist Idle Immortal
      // pattern). Modal preserves the underlying tab context so the user
      // doesn't lose their place; ShopTab is reused unchanged inside.
      const [shopModalOpen, setShopModalOpen] = useState(false);
      // 至 O selector do hub Eu ([017] §3). Vive AQUI e nao no `HubEuScreen`
      // porque quem o abre e' a barra de baixo, que e' irma dele e nao filha.
      const [euSeletor, setEuSeletor] = useState(false);
      // 門 P6 — a consulta de uma porta trancada / «Desbloqueios» de um hub
      // (`{hub, foco}`). Vive AQUI pela mesma razao do selector: quem a abre sao
      // quatro sitios irmaos (a lateral, a faixa, o selector e o Ceu), e o
      // VOLTAR nativo tem de a fechar antes de fechar o webapp.
      const [portaConsulta, setPortaConsulta] = useState(null);
      const abrirPorta = useCallback((hub, foco) => {
        setEuSeletor(false);
        setPortaConsulta({ hub: hub, foco: foco || null });
      }, []);
      // v14.7 Item 4 — Notifications inbox bell.
      const [notifModalOpen, setNotifModalOpen] = useState(false);
      const [notifCount, setNotifCount] = useState(0);
      const [notifReloadKey, setNotifReloadKey] = useState(0);
      // v14.13c Item 2 — Toast popups. Track items already surfaced so a 2nd
      // poll over the same pending state doesn't re-emit the same toast.
      // First poll never emits (would flood owner with N pre-existing items
      // on every app open). Trim to last 100 keys to avoid memory bloat.
      const seenNotifKeysRef = useRef(null);  // null = first-poll sentinel
      // v14.13 MA-45 — global active events feed for the floating banner +
      // drill-in modal. Polled on a slower cadence (90s) — events change on
      // server scheduler ticks, not per-action.
      const [events, setEvents] = useState([]);
      const [eventsModalOpen, setEventsModalOpen] = useState(false);
      // v14.13 MA-47 — Tutorial state. Auto-opens on first launch when
      // server says tutorial_seen===false. Owner can re-open via Settings →
      // "Mostrar tutorial novamente" which sets tutorialOpen=true.
      const [tutorialOpen, setTutorialOpen] = useState(false);
      const tutorialAutoCheckedRef = useRef(false);
      // 2026-05-26 — Profile modal consolidates identity (continent, path,
      // karma, sect). Opens when the player taps the avatar/name area in
      // PlayerHeader. The sub-modals (continent/path/karma) stay; they
      // become drill-in destinations from the ProfileModal identity grid
      // instead of header chips. See GameDesign/profile_modal_spec.md.
      const [profileModalOpen, setProfileModalOpen] = useState(false);
      // Onda R4 (ui_v2, decisão da home) — Conquistas no hub EU. Root-mounted
      // (review R4): estado local num LANDING deixava o modal fora do
      // _anyModalOpen/_handleBack → o back nativo fechava o webapp em vez do
      // modal. OFF nunca seta true (só a grade v2 chama) → byte-idêntico.
      const [achModalOpen, setAchModalOpen] = useState(false);
      // Sistema Multi-Servidor (Fase 2) — root-mounted Lobby + Admin Panel modals.
      const [lobbyModalOpen, setLobbyModalOpen] = useState(false);
      const [adminModalOpen, setAdminModalOpen] = useState(false);
      const [continentModalOpen, setContinentModalOpen] = useState(false);
      const [pathModalOpen, setPathModalOpen] = useState(false);
      const [karmaModalOpen, setKarmaModalOpen] = useState(false);
      // v16.4 — World Sects (Seita de Cultivo). Directory drill-in from ProfileModal;
      // the join-confirm (WorldSectJoinModal) stacks on top of the directory.
      const [worldSectModalOpen, setWorldSectModalOpen] = useState(false);
      const [worldSectJoinTarget, setWorldSectJoinTarget] = useState(null);
      // v16.4c — Sect Hall (members only). Opened from the ProfileModal 🏯 card
      // when the cultivator already belongs to a house (rank/library/quests).
      const [sectHallModalOpen, setSectHallModalOpen] = useState(false);
      // Onda 3 — Heaven's Whispers feed + NPC-cultivator profile/challenge.
      // Both open from the LeaderboardTab (the "world" surface where NPCs live);
      // the NPC modal stacks the combat arena internally.
      const [whispersModalOpen, setWhispersModalOpen] = useState(false);
      // World Pulse Fase 1 — Os Registos Celestiais (the living world chronicle).
      // Opens from Home (global feed) and the PlazaTab strip (continent-scoped).
      const [chronicleModalOpen, setChronicleModalOpen] = useState(false);
      const [chronicleContinent, setChronicleContinent] = useState(null);
      const openChronicle = useCallback((continent) => {
        setChronicleContinent(continent || null);
        setChronicleModalOpen(true);
      }, []);
      // MV-3 — Chronicle→LUGAR: o chip "ver no mapa" fecha o modal e abre a
      // ilha no HubMundoScreen. Nonce = one-shot re-disparável (lição ui_v2:
      // pedir a MESMA ilha duas vezes tem de re-abrir).
      const [mundoIsle, setMundoIsle] = useState(null);
      const [mundoIsleNonce, setMundoIsleNonce] = useState(0);
      const openIsleOnMap = useCallback((continentKey) => {
        haptic("select");
        setChronicleModalOpen(false);
        setMundoIsle(continentKey || null);
        setMundoIsleNonce(n => n + 1);
        setTab("hub_mundo_screen");
      }, []);
      const [npcTarget, setNpcTarget] = useState(null);
      // Onda 4a — Continental Plaza. Its NPC + bounty challenges REUSE the
      // App-root npcTarget modal (already in the back-stack); a bounty target
      // just carries an extra bounty_id. plazaReload bumps the PlazaTab's
      // board/presence after a fight/claim resolves.
      const [plazaReload, setPlazaReload] = useState(0);
      // Onda 4b — Travel between continents. Opened from the PlazaTab header;
      // lifted to the App root so the Telegram/hardware back button closes it
      // (memory feedback-miniapp-nav-state-loss). On travel, onTraveled refreshes
      // the player (continent/stones changed) + bumps the plaza board/presence.
      const [travelModalOpen, setTravelModalOpen] = useState(false);
      // Onda 5 — Reinos Exploráveis. The Explore tab is self-contained, but a
      // rare Hidden-Monster encounter LIFTS the duel to the App root (so the
      // Telegram/hardware back button closes it — like the Onda 3 npcTarget) and
      // reuses DuelArenaModal + the spare/execute fork. exploreReload bumps the
      // tab's scan after a duel settles (depth/bag changed server-side).
      const [exploreReload, setExploreReload] = useState(0);
      const [exploreDuelTarget, setExploreDuelTarget] = useState(null);  // {duelId, npc}
      // MA-39a — P2P Trade. TradeModal lifted to the App root so the Telegram
      // back button closes it (memory feedback-miniapp-nav-state-loss).
      // openTradeWith initiates by dao_name (profile CTA / Market search) and
      // returns the api result so the caller can render inline errors; on ok it
      // opens the modal. The Market pending list opens an existing trade by id
      // (setTradeId directly).
      const [tradeId, setTradeId] = useState(null);
      // MV-5 — Quests VIVAS: o ENCONTRO (diálogo + aceitar/recusar) é um modal
      // root (lição nav-state-loss — abre da PlazaTab E da QuestsTab; o back
      // nativo tem de fechar o modal, não o webapp). styReload bumpa a seção
      // de storylets da QuestsTab depois de aceitar/recusar. OFF nunca seta
      // (só os cards gated chamam) → byte-idêntico.
      const [styOffer, setStyOffer] = useState(null);
      const [styReload, setStyReload] = useState(0);
      // MV-7 — Profissões: a Guilda dos Ofícios é um modal root (lição
      // nav-state-loss — abre do HubMundo E do ProfileModal). OFF nunca seta
      // (entradas gated) → byte-idêntico.
      const [profModalOpen, setProfModalOpen] = useState(false);
      // MV-9.5 — 商队 A Caravana: modal root (lição nav-state-loss — abre da
      // praça E da porta da ilha no mapa v2; sem estar no back-stack o botão
      // "voltar" nativo fecharia o webapp). OFF nunca seta (as duas entradas
      // são gated) → byte-idêntico.
      const [caravanOpen, setCaravanOpen] = useState(false);
      // MV-8 — a EMBOSCADA: modal root porque chega de TRÊS lugares (praça,
      // chegada de viagem, exploração) e porque pode stackar a arena de duelo.
      // OFF nunca seta (o servidor nunca manda a key) → byte-idêntico.
      const [jhAmbush, setJhAmbush] = useState(null);
      // 🐛 2026-09-22 ([jogador]): a hora do último pedido do jogador — a navegação
      // usa-a para não repetir um pedido que acabou de sair.
      const _ultimoPlayerRef = useRef(0);
      const loadPlayer = useCallback(async () => {
        _ultimoPlayerRef.current = Date.now();
        try {
          const data = await api("player");
          // Multi-Servidor: no character in THIS (secondary) world yet — offer to
          // create the zeroed one instead of treating it as an error/black screen.
          if (data && data.ok === false && data.reason === "needs_world_start") {
            setNeedsWorldStart(true);
            setPlayer(null);
            setError(null);
            return;
          }
          setNeedsWorldStart(false);
          // 語 pelo dono unico (`definirLang`): ele actualiza tambem o
          // `<html lang>`, que era o que faltava e convidava o tradutor do
          // browser a reescrever o nome do jogador (bug do [jogador], 23/09).
          if (data?.language) definirLang(data.language);
          // Sprint 0 (FF-3/FF-4) — adopt the active world's Surface Manifest.
          // Fail-safe to the default if a (older) payload omits it, so the UI
          // never crashes and gated surfaces simply stay OFF. setPlayer below
          // re-renders, which re-runs every featureEnabled() read with this state.
          WORLD_MANIFEST = (data && data.manifest && typeof data.manifest === "object")
            ? { realm: data.manifest.realm || "mortal", features: data.manifest.features || {} }
            : { realm: "mortal", features: {} };
          // Onda R1 (ui_v2) — moldura Telegram explícita do Pergaminho Vivo.
          // SÓ quando o manifest emite ui_v2 (flag per-world, graduada no R6) →
          // main nunca muda de moldura. Idempotente (re-aplicar = no-op visual).
          if (featureEnabled("ui_v2") && typeof applyV2Chrome === "function") applyV2Chrome();
          // WEB-D 皮 — a pele quente. Flag PRÓPRIA (`pele_quente`), ortogonal à
          // `ui_v2` (o shell) e à `superficie_desktop` (o layout largo): um mundo
          // tem de poder ficar quente sem ganhar o redesign nem o trilho.
          // Idempotente e depois do `applyV2Chrome` de propósito — a moldura do
          // Telegram é a mesma propriedade, e quem manda na COR é a pele.
          // `main` lê os defaults (OFF) → nenhuma escrita, byte-idêntico.
          if (featureEnabled("pele_quente") && typeof applyWarmSkin === "function") applyWarmSkin();
          setPlayer(data);
          setError(null);
          // First-launch tutorial: only auto-open ONCE per session and only
          // if the server flag is explicitly false. Re-renders / refreshes
          // after dismissal won't re-fire (guarded by ref).
          if (!tutorialAutoCheckedRef.current) {
            tutorialAutoCheckedRef.current = true;
            if (data && data.tutorial_seen === false) {
              setTutorialOpen(true);
            }
          }
        } catch (e) {
          setError(e.message);
        }
      }, []);
      // Multi-Servidor: create the zeroed character in the CURRENT world, then
      // reload (which now finds the fresh character and renders the game).
      const doWorldStart = useCallback(async () => {
        if (wsBusy) return;
        const name = (wsName || "").trim();
        // Validar no cliente com a MESMA regra do servidor: uma ida ao
        // servidor para ouvir o obvio e' uma espera que nao ensina nada.
        // O servidor volta a validar — isto e' conforto, nunca a guarda.
        if (!/^[A-Za-z][A-Za-z0-9]{2,19}$/.test(name)) {
          setWsErr(t("world_start_err_invalid")); haptic("error"); return;
        }
        setWsErr(""); setWsBusy(true); haptic("warning");
        try {
          const res = await api("world/start", { dao_name: name });
          if (res && res.ok) {
            haptic("success");
            setNeedsWorldStart(false);
            await loadPlayer();
          } else {
            haptic("error");
            const why = res && res.reason;
            // Cada recusa diz o que FAZER, e fica ao lado do campo — nao
            // num toast que desaparece antes de a pessoa reler o nome.
            if (why === "dao_name_taken") setWsErr(t("world_start_err_taken"));
            else if (why === "dao_name_invalid") setWsErr(t("world_start_err_invalid"));
            else showToast(t("world_start_error"), "err");
          }
        } catch (e) {
          haptic("error");
          showToast(t("world_start_error"), "err");
        } finally {
          setWsBusy(false);
        }
      }, [wsBusy, wsName, loadPlayer]);

      const doRedeem = useCallback(async () => {
        if (wsBusy) return;
        const code = (wsCode || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
        if (code.length !== 8) { setWsErr(t("link_err_code_invalid")); haptic("error"); return; }
        setWsErr(""); setWsBusy(true);
        try {
          const res = await api("account/redeem", { code });
          if (res && res.ok) {
            haptic("success");
            showToast(t("link_ok"), "ok");
            // ⚠️ O servidor revogou a sessao: a identidade mudou de dono e a
            // sessao antiga ainda aponta ao player_id velho. Recarregar e o
            // que traz a conta certa — e e' honesto, porque foi mesmo uma
            // troca de conta.
            setTimeout(() => { try { window.location.reload(); } catch (e) {} }, 900);
            return;
          }
          haptic("error");
          const why = (res && res.reason) || "";
          const MAP = {
            link_code_invalid: "link_err_code_invalid",
            link_same_account: "link_err_same",
            link_would_orphan: "link_err_orphan",
            link_has_character: "link_err_has_char",
          };
          setWsErr(t(MAP[why] || "world_start_error"));
        } catch (e) {
          haptic("error"); setWsErr(t("world_start_error"));
        } finally { setWsBusy(false); }
      }, [wsBusy, wsCode]);
      // Map inbox type → notification_prefs key. Types not in PREF_KEYS
      // (quest_ready, faction_quest_ready, pvp_*) default to TOAST-ON
      // because they're action-required (player wants to react fast).
      // Keep in sync with `core/notification_prefs.PREF_KEYS`.
      const NOTIF_TOAST_PREF_FOR_TYPE = {
        breakthrough_ready: "breakthrough_ready",
        trib_cooldown_done: "trib_cooldown_done",
        alchemy_full:       "alchemy_energy_full",
        buff_expiring:      "pill_finished",
        // Onda 3 — mirror the server whisper opt-out client-side so a muted
        // player never gets an atmospheric toast (defense-in-depth for Lei §1).
        whisper:            "whisper",
      };
      const loadNotifBadge = useCallback(async () => {
        try {
          const data = await api("notifications/inbox");
          setNotifCount((data && data.count) || 0);

          // v14.13c Item 2 — Diff fresh items vs previously-seen set and emit
          // toasts for newcomers. First poll only seeds the set without
          // emitting (avoid open-app flood). Subsequent polls fire toasts for
          // genuinely new items, gated by per-type notification prefs.
          const items = (data && data.items) || [];
          const prefs = (data && data.prefs) || {};
          const itemKeys = items.map(it => `${it.type}:${it.ref_id || 0}`);

          if (seenNotifKeysRef.current === null) {
            // First poll — just snapshot the current state.
            seenNotifKeysRef.current = new Set(itemKeys);
          } else {
            const seen = seenNotifKeysRef.current;
            items.forEach(it => {
              const key = `${it.type}:${it.ref_id || 0}`;
              if (seen.has(key)) return;
              const prefKey = NOTIF_TOAST_PREF_FOR_TYPE[it.type];
              // prefs explicitly false → respect the opt-out; missing key or
              // type-not-in-map → default ON.
              if (prefKey && prefs[prefKey] === false) return;
              pushNotifToast({
                icon: it.icon,
                title: it.title || it.title_key || "",
                body: it.body || it.body_key || "",
                target_tab: it.target_tab,
                type: it.type,
                onClick: (toast) => {
                  if (toast.target_tab) setTab(toast.target_tab);
                  // Also refresh the bell badge so count drops to 0 if the
                  // user resolves it inside the destination tab.
                  setTimeout(() => loadNotifBadge(), 1500);
                },
              });
              haptic && haptic("light");
            });
            // Update seen set with current item keys; trim to last 100 to
            // bound memory growth across long sessions.
            const merged = [...seen, ...itemKeys];
            seenNotifKeysRef.current = new Set(merged.slice(-100));
          }
        } catch (e) {
          // Don't surface — the bell is best-effort. Header still functions
          // without a badge if the lookup fails (e.g. transient network).
        }
      }, []);
      const loadEvents = useCallback(async () => {
        try {
          const data = await api("events/active");
          setEvents((data && data.events) || []);
        } catch (e) {
          // Best-effort — the banner just stays hidden if the call fails.
        }
      }, []);
      const openTradeWith = useCallback(async (daoName) => {
        if (!daoName) return { ok: false, reason: "trade_target_not_found" };
        if (player && player.dao_name && daoName === player.dao_name) {
          return { ok: false, reason: "trade_self_error" };
        }
        try {
          const r = await api("trade/initiate", { target_dao_name: daoName });
          if (r && r.ok) setTradeId(r.trade_id);
          return r;
        } catch (e) {
          return { ok: false, reason: "generic" };
        }
      }, [player]);
      useEffect(() => { loadPlayer(); }, [loadPlayer]);
      // 🐛 2026-09-22 (report do [jogador]): *"moved and came back to another page…
      // no refresh"*. Mudar de ecrã não voltava a pedir o jogador: a Vida, o Qi
      // e os saldos ficavam com a idade do último poll, e num separador web
      // aberto há horas essa idade podia ser grande. Ir a outro ecrã passa a
      // refrescá-lo — com trava de 10s, para navegar depressa não multiplicar
      // pedidos (o poll de 30s continua a ser a batida de fundo).
      useEffect(() => {
        if (!player) return;
        if (Date.now() - _ultimoPlayerRef.current > 10000) loadPlayer();
      // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [tab]);
      useEffect(() => { loadNotifBadge(); }, [loadNotifBadge]);
      useEffect(() => { loadEvents(); }, [loadEvents]);
      useVisibleInterval(loadPlayer, 30000);
      useVisibleInterval(loadNotifBadge, 60000);
      useVisibleInterval(loadEvents, 90000);

      // 2026-05-26 — Telegram BackButton integration. Owner reported the
      // mini-app sometimes closes back to chat list when navigating
      // (Android back gesture, swipe, etc.). With the BackButton wired,
      // those gestures close the topmost modal instead of the WebApp.
      // Priority (closes one per back press):
      //   1. Sub-modals stacked on ProfileModal (continent/path/karma)
      //   2. ProfileModal itself
      //   3. Other modals (shop, notif, events, tutorial)
      //   4. Tab != home → go to home
      //   5. Else (home with nothing open) → let Telegram handle (closing
      //      confirmation kicks in to ask "close anyway?")
      const _anyModalOpen = profileModalOpen || achModalOpen || continentModalOpen
        || pathModalOpen || karmaModalOpen || shopModalOpen
        || notifModalOpen || eventsModalOpen || tutorialOpen
        || worldSectModalOpen || !!worldSectJoinTarget || sectHallModalOpen
        || whispersModalOpen || chronicleModalOpen || !!npcTarget || travelModalOpen
        || !!exploreDuelTarget || !!tradeId
        || lobbyModalOpen || adminModalOpen || !!styOffer || profModalOpen
        || !!jhAmbush || caravanOpen
        // 至 O selector do hub Eu E' uma sobreposicao, portanto conta como
        // janela aberta. Astra, §0: *"Escape e o primeiro retorno do
        // browser/Telegram fecham a sobreposicao"*. Sem esta linha o VOLTAR
        // nativo fechava o webapp inteiro em vez do selector — o mesmo defeito
        // que o `achModalOpen` ja' tinha sofrido (nota do review R4, acima).
        || euSeletor
        // 門 P6 — a consulta da porta e' uma janela da raiz, como o selector.
        || !!portaConsulta;
      // Onda R2 (ui_v2) — no v2 as raízes são os landings dos hubs (BackButton
      // esconde-se lá; senão ficaria visível mas morto). OFF → home, como sempre.
      const _v2NavOn = featureEnabled("ui_v2") && typeof HUB_DEFS !== "undefined";
      const _canGoBack = _anyModalOpen ||
        (_v2NavOn ? !HUB_DEFS.some(h => h.landing === tab) : tab !== "home");
      const _handleBack = useCallback(() => {
        // Drill order: most-recently-stacked first so back peels them off.
        // Multi-Servidor (Fase 2) — Lobby / Admin are top-level, peel first.
        // 至 O selector do Eu e' o mais superficial de todos: nada stacka
        // nele e ele nao stacka nada. Peel primeiro.
        if (euSeletor) { setEuSeletor(false); return; }
        // 門 P6 — nada stacka na consulta e ela nao stacka nada (o selector
        // fecha-se ao abri-la). Peel logo a seguir ao selector.
        if (portaConsulta) { setPortaConsulta(null); return; }
        if (adminModalOpen) { setAdminModalOpen(false); return; }
        if (lobbyModalOpen) { setLobbyModalOpen(false); return; }
        if (continentModalOpen) { setContinentModalOpen(false); return; }
        if (pathModalOpen) { setPathModalOpen(false); return; }
        if (karmaModalOpen) { setKarmaModalOpen(false); return; }
        // v16.4 — join-confirm stacks on the directory; peel it first.
        if (worldSectJoinTarget) { setWorldSectJoinTarget(null); return; }
        if (worldSectModalOpen) { setWorldSectModalOpen(false); return; }
        // v16.4c — Sect Hall stacks on the ProfileModal; peel it before Profile.
        if (sectHallModalOpen) { setSectHallModalOpen(false); return; }
        // MV-7 — a Guilda dos Ofícios stacka sobre o ProfileModal (linha de
        // ofício tocável); peel ANTES do Profile (lição nav-state-loss).
        if (profModalOpen) { setProfModalOpen(false); return; }
        // MV-9.5 — a Caravana não stacka nada e nada stacka nela; peel junto
        // dos outros modais de serviço (praça / porta da ilha).
        if (caravanOpen) { setCaravanOpen(false); return; }
        if (profileModalOpen) { setProfileModalOpen(false); return; }
        // Onda R4 — Conquistas do hub EU (root-mounted; nunca stacka com outros).
        if (achModalOpen) { setAchModalOpen(false); return; }
        if (shopModalOpen) { setShopModalOpen(false); return; }
        if (notifModalOpen) { setNotifModalOpen(false); loadNotifBadge(); return; }
        if (eventsModalOpen) { setEventsModalOpen(false); return; }
        // Onda 3 — NPC modal (may stack the combat arena) peels before whispers.
        if (npcTarget) { setNpcTarget(null); return; }
        if (whispersModalOpen) { setWhispersModalOpen(false); return; }
        // World Pulse — Chronicle feed (read-only; peels independently).
        if (chronicleModalOpen) { setChronicleModalOpen(false); return; }
        // Onda 5 — Explore Hidden-Monster duel (stacks the arena) — peel it.
        if (exploreDuelTarget) { setExploreDuelTarget(null); return; }
        // MA-39a — P2P Trade modal (lifted to App root).
        if (tradeId) { setTradeId(null); return; }
        // MV-8 — a emboscada do jiānghú (pode stackar a arena); peel primeiro
        // que o storylet/travel. Fechar sem escolher é LIVRE: nenhum dos três
        // ramos foi tomado, então nada aconteceu (Lei §1 — nunca uma perda
        // forçada por um encontro que o jogador não pediu).
        if (jhAmbush) { setJhAmbush(null); return; }
        // MV-5 — o encontro (oferta de storylet); back = fechar sem responder.
        if (styOffer) { setStyOffer(null); return; }
        // Onda 4b — Travel modal (back = cancel; no continent change happened).
        if (travelModalOpen) { setTravelModalOpen(false); return; }
        if (tutorialOpen) { setTutorialOpen(false); loadPlayer(); return; }
        // Onda R2 (ui_v2) — no shell v2 o BackButton nativo espelha a seta do
        // header: volta ao LANDING do hub ativo; num landing, deixa o Telegram
        // fechar (o landing É a raiz do hub). OFF → home, byte-idêntico.
        if (featureEnabled("ui_v2") && typeof HUB_DEFS !== "undefined") {
          const _hub = HUB_DEFS.find(h => h.group.includes(tab));
          if (_hub && tab !== _hub.landing) { setTab(_hub.landing); return; }
          if (!_hub && tab !== "home") { setTab("home"); return; }
          return;
        }
        if (tab !== "home") { setTab("home"); return; }
      }, [
        continentModalOpen, pathModalOpen, karmaModalOpen, profileModalOpen,
        achModalOpen,
        shopModalOpen, notifModalOpen, eventsModalOpen, tutorialOpen, tab,
        worldSectModalOpen, worldSectJoinTarget, sectHallModalOpen,
        whispersModalOpen, chronicleModalOpen, npcTarget, travelModalOpen, exploreDuelTarget,
        tradeId, loadNotifBadge, loadPlayer,
        lobbyModalOpen, adminModalOpen, styOffer, profModalOpen, jhAmbush,
        caravanOpen, euSeletor, portaConsulta,
      ]);
      useTelegramBackButton({ visible: _canGoBack, onBack: _handleBack });

      // Onda R3 (ui_v2) — fullscreen imersivo do MAPA (Bot API 8.0). Entra ao
      // abrir o hub_mundo_screen, sai ao deixá-lo (cleanup). Guards: desktop /
      // clientes <8.0 = no-op; OFF a tab nem existe na nav (e a rota é double-
      // gated), então main nunca chega aqui. O gate vive num BOOLEANO derivado
      // nas deps (review R3): se a flag cair no poll de 30s com o jogador no
      // mapa, ou se o tabs.js cacheado não tiver o componente (mesmo typeof-
      // guard da rota — sem fullscreen sobre tela vazia), o booleano flipa e o
      // cleanup roda o exitFullscreen na hora.
      // ── WEB-C 兩面 — a superfície de agora ──────────────────────────────
      // Três condições em conjunção, e a flag por cima (kill-switch per-world):
      // fora do Telegram + largura >= 1024 + ponteiro fino (ver
      // `isDesktopSurface` em ui.js). Dentro do Telegram isto é SEMPRE false,
      // logo os 248 na sua superfície de sempre não podem sentir nada.
      // `typeof` fail-safe: um cliente cacheado sem o ui.js novo fica no
      // telemóvel em vez de rebentar.
      // WEB-D §1 — a conjunção ("fora do Telegram + largura + ponteiro fino +
      // flag") passou a viver SÓ em `useWideShell` (ui.js), porque as ABAS
      // precisam da mesma resposta: a grelha da Home fazia cartões de 514×514
      // num ecrã de 1920 por assumir 480px de largura. Duas cópias divergiriam
      // no primeiro sprint que mexesse na flag. Aqui sobra o que é só desta
      // casa: o trilho existir. O `typeof` é o fail-safe de um cliente com o
      // ui.js em cache — degrada para o telemóvel INTEIRO, nunca para trilho
      // de desktop com cartões de telemóvel (que seria pior que não degradar).
      const _wideSurface = typeof useWideShell === "function" ? useWideShell() : false;
      const desktop = _wideSurface && typeof SideRail === "function";

      const _mapFullscreen = tab === "hub_mundo_screen" && featureEnabled("ui_v2")
        && typeof HubMundoScreen === "function";
      useEffect(() => {
        if (!_mapFullscreen) return;
        // SÓ mobile (owner 2026-07-07: no PC o tdesktop implementa
        // requestFullscreen e a janela virava tela cheia — indesejado).
        if (!(tg?.platform === "android" || tg?.platform === "ios")) return;
        if (!(tg?.isVersionAtLeast?.("8.0") && tg?.requestFullscreen)) return;
        try { tg.requestFullscreen(); } catch (e) { /* no-op */ }
        return () => { try { tg.exitFullscreen?.(); } catch (e) { /* no-op */ } };
      }, [_mapFullscreen]);

      // 兩面: as telas ANTERIORES ao personagem (criar/aterrar/carregar) ficam
      // sempre em coluna centrada — a porta (`login.html`) também é uma coluna,
      // e esticar "diz como te chamas" por 1920px é o mesmo defeito ao invés.
      const preShellStyle = () => ({ ...shellStyle, flexDirection:"column", maxWidth:480, margin:"0 auto" });
      const shellStyle = {
        height:"100%", display:"flex",
        // 兩面: no desktop o shell passa a ser uma LINHA (trilho | conteúdo).
        // `maxWidth:480` era a coluna de telemóvel centrada num ecrã de 1920 —
        // o mandato do owner em uma linha de CSS.
        flexDirection: desktop ? "row" : "column",
        maxWidth: desktop ? "none" : 480,
        margin: desktop ? 0 : "0 auto",
        position:"relative",
        background:"radial-gradient(circle at 50% 0%, rgba(var(--glow-rgb),.18), transparent 60%), radial-gradient(circle at 50% 100%, rgba(var(--amb-aura-rgb),.12), transparent 65%), var(--bg)",
        // Onda R3 (ui_v2) — as DUAS safe-areas do fullscreen (pesquisa §2.7) no
        // TOPO DO SHELL (protege o PlayerHeader, não só o mapa). Fora do
        // fullscreen as vars valem 0px → layout normal intacto. OFF → sem a
        // propriedade → byte-idêntico.
        ...(featureEnabled("ui_v2")
          ? { paddingTop:"calc(var(--tg-safe-area-inset-top, 0px) + var(--tg-content-safe-area-inset-top, 0px))" }
          : {}),
      };

      if (needsWorldStart) {
        return (
          <div style={preShellStyle()}>
            <AtmoBg />
            <div className="scroll-area" style={{ position:"relative", zIndex:2, flex:1, padding:"12px 14px 90px", overflowY:"auto", display:"flex", flexDirection:"column", justifyContent:"center" }}>
              <Card>
                <div style={{ textAlign:"center", padding:"26px 16px" }}>
                  <div style={{ fontSize:42 }}>🌌</div>
                  <div style={{ fontFamily:"'Cinzel',serif", fontSize:18, color:"var(--gold2)", marginTop:12 }}>{t("world_start_title")}</div>
                  <div style={{ fontSize:12.5, color:"var(--muted)", lineHeight:1.55, marginTop:10 }}>{t("world_start_desc")}</div>

                  {wsMode === "new" ? (
                  <>
                  {/* O PRIMEIRO acto do jogador no mundo e' dizer como se chama. */}
                  <div style={{ textAlign:"left", marginTop:20 }}>
                    <label htmlFor="ws-dao-name" style={{ display:"block", fontSize:10.5, letterSpacing:".16em", textTransform:"uppercase", color:"var(--muted)", marginBottom:6 }}>
                      {t("world_start_name_label")}
                    </label>
                    <input
                      id="ws-dao-name"
                      value={wsName}
                      onChange={(e) => { setWsName(e.target.value); if (wsErr) setWsErr(""); }}
                      onKeyDown={(e) => { if (e.key === "Enter") doWorldStart(); }}
                      placeholder={t("world_start_name_ph")}
                      maxLength={20}
                      autoComplete="off"
                      autoCapitalize="words"
                      spellCheck={false}
                      aria-invalid={wsErr ? "true" : "false"}
                      aria-describedby="ws-dao-rule"
                      style={{ width:"100%", minHeight:46, padding:"10px 13px", fontSize:16,
                               borderRadius:8, background:"rgba(0,0,0,.34)", color:"var(--text)",
                               border:"1px solid " + (wsErr ? "var(--red,var(--red))" : "var(--border)"),
                               fontFamily:"'Cinzel',serif", letterSpacing:".04em" }}
                    />
                    <div id="ws-dao-rule" style={{ fontSize:11.5, lineHeight:1.5, marginTop:7,
                                                  color: wsErr ? "var(--red,var(--red))" : "var(--muted)" }}>
                      {wsErr || t("world_start_name_rule")}
                    </div>
                  </div>
                  <ActionBtn variant="primary" disabled={wsBusy} onClick={doWorldStart} style={{ marginTop:16, width:"100%" }}>
                    {wsBusy ? t("world_start_loading") : t("world_start_btn")}
                  </ActionBtn>
                  </>
                  ) : (
                  <>
                  {/* O outro caminho: esta pessoa JA e' alguem neste mundo. */}
                  <div style={{ textAlign:"left", marginTop:20 }}>
                    <label htmlFor="ws-link-code" style={{ display:"block", fontSize:10.5, letterSpacing:".16em", textTransform:"uppercase", color:"var(--muted)", marginBottom:6 }}>
                      {t("link_code_label")}
                    </label>
                    <input
                      id="ws-link-code"
                      value={wsCode}
                      onChange={(e) => { setWsCode(e.target.value.toUpperCase()); if (wsErr) setWsErr(""); }}
                      onKeyDown={(e) => { if (e.key === "Enter") doRedeem(); }}
                      placeholder="ABCD2345"
                      maxLength={12}
                      autoComplete="one-time-code"
                      autoCapitalize="characters"
                      spellCheck={false}
                      aria-invalid={wsErr ? "true" : "false"}
                      aria-describedby="ws-link-rule"
                      style={{ width:"100%", minHeight:46, padding:"10px 13px", fontSize:18,
                               borderRadius:8, background:"rgba(0,0,0,.34)", color:"var(--gold2)",
                               border:"1px solid " + (wsErr ? "var(--red,var(--red))" : "var(--border)"),
                               fontFamily:"ui-monospace,SFMono-Regular,Menlo,monospace",
                               letterSpacing:".22em", textAlign:"center" }}
                    />
                    <div id="ws-link-rule" style={{ fontSize:11.5, lineHeight:1.5, marginTop:7,
                                                   color: wsErr ? "var(--red,var(--red))" : "var(--muted)" }}>
                      {wsErr || t("link_code_hint")}
                    </div>
                  </div>
                  <ActionBtn variant="primary" disabled={wsBusy} onClick={doRedeem} style={{ marginTop:16, width:"100%" }}>
                    {wsBusy ? t("world_start_loading") : t("link_code_btn")}
                  </ActionBtn>
                  </>
                  )}

                  {/* A troca entre os dois caminhos. Nunca esconde o outro. */}
                  <button
                    onClick={() => { setWsMode(wsMode === "new" ? "link" : "new"); setWsErr(""); }}
                    style={{ background:"none", border:"none", cursor:"pointer", marginTop:14,
                             color:"var(--muted)", fontSize:12, textDecoration:"underline",
                             textUnderlineOffset:3, fontFamily:"inherit" }}>
                    {wsMode === "new" ? t("link_have_account") : t("link_new_instead")}
                  </button>
                </div>
              </Card>
            </div>
          </div>
        );
      }

      // 坐 ONDA 1 / S1 — a CHEGADA QUE FALHA (variantes 3 e 4 do desenho da
      // MESA [011]). O que estava aqui era um beco: o `ErrBanner` escrevia a
      // string crua do servidor — e o 401 do mini-app é `_err("unauthorized",
      // 401)`, portanto quem tinha a sessão expirada lia literalmente
      // **"unauthorized"**, uma palavra em inglês, num jogo em português, num
      // ecrã SEM UM ÚNICO BOTÃO. Para voltar a entrar era preciso adivinhar.
      //
      // ⚠️ **Isto NÃO está atrás da flag da onda, e é decisão, não esquecimento.**
      // Duas razões, e a segunda sozinha bastava:
      //   1. É correção de HONESTIDADE, não desenho novo — a mesma família da
      //      porta da Apple e do nome das expedições, que também chegam a toda
      //      a gente. Não remove nada: o motivo cru continua escrito, em
      //      segundo plano, que é o que se cola num report.
      //   2. **A flag é inalcançável aqui.** `featureEnabled` lê o
      //      `WORLD_MANIFEST`, e o manifesto chega DENTRO do `api("player")`
      //      que acabou de falhar. Um cartão de recuperação atrás desta chave
      //      nunca apareceria na única altura em que é preciso — seria uma
      //      guarda verde sobre o conjunto vazio, com aspecto de feito.
      if (error && !player) {
        return (
          <div style={preShellStyle()}>
            <AtmoBg />
            <div className="scroll-area" style={{ position:"relative", zIndex:2, flex:1, padding:"12px 14px 90px", overflowY:"auto" }}>
              <CultRecovery error={error} onRetry={() => { setError(null); loadPlayer(); }}
                            wide={_wideSurface} />
            </div>
          </div>
        );
      }

      if (!player) {
        return (
          <div style={preShellStyle()}>
            <AtmoBg />
            <div className="scroll-area" style={{ position:"relative", zIndex:2, flex:1, overflowY:"auto" }}><Loading /></div>
          </div>
        );
      }

      return (
        <div style={shellStyle}>
          <AtmoBg />
          {/* 兩面 (WEB-C) — o TRILHO. Só na superfície larga: no telemóvel esta
              linha não renderiza nada e a nav continua a ser a barra de baixo. */}
          {/* 至 P5 — a lateral de HUBS quando a onda esta' ON ([017] §1). Com
              ela OFF fica o `SideRail` de sempre, byte a byte. ⚠️ Uma UNICA
              navegacao global por composicao: os dois nunca coexistem. */}
          {desktop && (
            (typeof ondaCultOn === "function" && ondaCultOn()
             && typeof SideRailHubs === "function")
              ? <SideRailHubs tab={tab} setTab={setTab} player={player} onPorta={abrirPorta} />
              : <SideRail tab={tab} setTab={setTab} />
          )}
          <SurfaceColumn on={desktop}>
          {/* v14.13 MA-45 — Floating banner above the topbar when ≥1 event
              is active. Hidden when events.length===0 so the chrome stays
              clean during quiet periods. */}
          <EventsBanner events={events} onClick={() => setEventsModalOpen(true)} />
          <PlayerHeader player={player} tab={tab}
                        onBack={() => setTab(
                          // Onda R2 (ui_v2) — a seta volta ao LANDING do hub ativo
                          // (não a "home", que não tem slot no v2). OFF → home, como sempre.
                          (featureEnabled("ui_v2") && typeof HUB_DEFS !== "undefined"
                           && (HUB_DEFS.find(h => h.group.includes(tab)) || {}).landing) || "home"
                        )}
                        onJadeClick={() => { haptic("select"); setShopModalOpen(true); }}
                        onBellClick={() => {
                          haptic("select");
                          setNotifModalOpen(true);
                          // Refresh inbox snapshot on open so the list is fresh.
                          setNotifReloadKey(x => x + 1);
                          loadNotifBadge();
                        }}
                        onProfileClick={() => { haptic("select"); setProfileModalOpen(true); }}
                        notifCount={notifCount} />
          {/* Onda R2-fix — Faixa do Domínio (v2): navegação intra-hub sob o header.
              Garante a Lei nº 1 (nenhum destino órfão) até R3/R4 trazerem as telas
              próprias. OFF/cliente-cacheado → nada (typeof-guard). */}
          {featureEnabled("ui_v2") && typeof V2HubStrip === "function" && (
            <V2HubStrip tab={tab} setTab={setTab} player={player} onPorta={abrirPorta} />
          )}
          {/* 兩面: o `100px` de baixo era espaço para a barra de nav do telemóvel
              — sem barra, era um buraco. E a leitura ganha um tecto próprio: uma
              linha de texto a 1600px não se lê, ter ecrã largo não é licença para
              esticar tudo até à borda. */}
          <div className="scroll-area" style={{ position:"relative", zIndex:2, flex:1, overflowY:"auto",
                 padding: desktop ? "20px 32px 40px" : "12px 14px 100px" }}>
            <div style={desktop ? { maxWidth:1080, margin:"0 auto", width:"100%" } : undefined}>
            {/* TabErrorBoundary keyed by tab — a render crash in one tab
                 (e.g. an undefined deref in CraftingTab) shows a recoverable
                 error instead of unmounting the entire app into a black void.
                 The boundary state resets when the player switches tabs. */}
            <TabErrorBoundary tabKey={tab}>
              {tab === "home"          && <HomeTab player={player} setTab={setTab} onPlayerRefresh={loadPlayer}
                                       onOpenChronicle={() => { haptic("select"); openChronicle(null); }}
                                       /* 至 A chegada recolhe o `PlayerHeader` e passa a carregar a
                                          zona 1 inteira — logo o SINO e a LOJA tem de chegar ca'.
                                          Sem isto, a recolha trocava uma duplicacao por uma PERDA. */
                                       notifCount={notifCount}
                                       onSino={() => { haptic("select"); setNotifModalOpen(true); setNotifReloadKey(x => x + 1); loadNotifBadge(); }}
                                       onLoja={() => { haptic("select"); setShopModalOpen(true); }}
                                       onPerfil={() => { haptic("select"); setProfileModalOpen(true); }}
                                       /* 門 P6 — a maçaneta do primeiro ecrã: leva ao hub Eu
                                          com o selector ja' aberto (so' existe com a `ui_v2`,
                                          que e' onde o hub Eu existe). */
                                       onAbrirSeletor={featureEnabled("ui_v2") && typeof HubEuScreen === "function"
                                         ? () => { haptic("select"); setTab("hub_eu_screen"); setEuSeletor(true); }
                                         : undefined} />}
              {tab === "cultivation"   && <CultivationTab player={player} onPlayerRefresh={loadPlayer} setTab={setTab} />}
              {/* 🏯 "Seita" = a Seita de Cultivo (as 9 casas NPC: técnicas, recrutamento, hall).
                  Reusa os modais canónicos (WorldSectDirectoryModal / SectHallModal). A Guilda de
                  jogadores mudou-se para a sua própria aba "guild" abaixo (fix taxonomia 2026-06-24). */}
              {tab === "sect"          && <SeitaCultivoTab player={player}
                                            onOpenDirectory={() => { haptic("select"); setWorldSectModalOpen(true); }}
                                            onOpenHall={() => { haptic("select"); setSectHallModalOpen(true); }}
                                            setTab={setTab} />}
              {tab === "guild"         && <SectTab player={player} onPlayerRefresh={loadPlayer} />}
              {tab === "world_boss"    && <WorldBossTab />}
              {tab === "plaza"         && <PlazaTab
                                            player={player}
                                            setTab={setTab}
                                            reloadSignal={plazaReload}
                                            onOpenWorldSect={() => { (player && player.sect_chip_visible) ? setSectHallModalOpen(true) : setWorldSectModalOpen(true); }}
                                            onOpenTravel={() => { haptic("select"); setTravelModalOpen(true); }}
                                            onOpenNpc={(npc) => { haptic("select"); setNpcTarget(npc); }}
                                            onOpenProfession={featureEnabled("profissoes")
                                              ? () => { haptic("select"); setProfModalOpen(true); }
                                              : null}
                                            onOpenCaravan={caravanEnabled()
                                              ? () => { haptic("select"); setCaravanOpen(true); }
                                              : null}
                                            onProposeTrade={openTradeWith}
                                            onOpenChronicle={(continent) => { haptic("select"); openChronicle(continent); }}
                                            onOpenStorylet={(offer) => { haptic("select"); setStyOffer(offer); }}
                                            onOpenAmbush={(a) => { haptic("warning"); setJhAmbush(a); }}
                                            onOpenBounty={(b) => { haptic("warning"); setNpcTarget({ ...b.npc, bounty_id: b.bounty_id }); }} />}
              {tab === "leaderboard"   && <LeaderboardTab
                                            onOpenWhispers={() => { haptic("select"); setWhispersModalOpen(true); }}
                                            onProposeTrade={openTradeWith}
                                            onOpenNpc={(npc) => { haptic("select"); setNpcTarget(npc); }} />}
              {tab === "explore"       && <ExploreTab
                                            player={player}
                                            setTab={setTab}
                                            reloadSignal={exploreReload}
                                            onPlayerRefresh={loadPlayer}
                                            onOpenAmbush={(a) => { haptic("warning"); setJhAmbush(a); }}
                                            onOpenDuel={(d) => { haptic("warning"); setExploreDuelTarget(d); }} />}
              {tab === "cavern"        && <CavernTab
                                            player={player}
                                            setTab={setTab}
                                            onPlayerRefresh={loadPlayer} />}
              {tab === "inventory"     && <InventoryTab player={player} onPlayerRefresh={loadPlayer} />}
              {tab === "quests"        && <QuestsTab setTab={setTab}
                                            onOpenStorylet={(offer) => { haptic("select"); setStyOffer(offer); }}
                                            styReload={styReload}
                                            onPlayerRefresh={loadPlayer} />}
              {tab === "dungeons"      && <DungeonsTab onOpenTravel={() => { haptic("select"); setTravelModalOpen(true); }} />}
              {tab === "crafting"      && <CraftingTab onPlayerRefresh={loadPlayer} />}
              {tab === "combat"        && <CombatTab player={player} onPlayerRefresh={loadPlayer} />}
              {tab === "beasts"        && <BeastsTab player={player} onPlayerRefresh={loadPlayer} />}
              {tab === "faction"       && <FactionTab player={player} onPlayerRefresh={loadPlayer} />}
              {tab === "celestial"     && <CelestialTab player={player} onPlayerRefresh={loadPlayer} />}
              {tab === "body_tempering"&& <BodyTemperingTab player={player} onPlayerRefresh={loadPlayer} />}
              {tab === "partner"       && <PartnerTab player={player} onPlayerRefresh={loadPlayer} />}
              {tab === "battle_pass"   && <BattlePassTab onPlayerRefresh={loadPlayer} />}
              {tab === "shop"          && <ShopTab onPlayerRefresh={loadPlayer} />}
              {tab === "market"        && <MarketTab onOpenTrade={setTradeId} onProposeTrade={openTradeWith} />}
              {tab === "announcements" && <AnnouncementsTab />}
              {/* Sprint 0 (FF-3) — canary content. Double-gated by featureEnabled
                   so even a programmatic setTab to the canary renders nothing where
                   the flag is OFF (fail-safe; never reachable from the nav on main). */}
              {tab === "__manifest_canary" && featureEnabled("manifest_canary") && (
                <div style={{ padding:24, textAlign:"center", color:"var(--muted)", fontSize:13 }}>
                  🧪 {t("tab_manifest_canary")} · OK
                </div>
              )}
              {/* Onda R2 (ui_v2) — o Orbe da Alma (landing do hub EU). Double-gated
                   como o canary: mesmo um setTab programático renderiza nada onde a
                   flag está OFF (fail-safe; nunca alcançável da nav em main). */}
              {tab === "hub_eu_screen" && featureEnabled("ui_v2") && typeof HubEuScreen === "function" && (
                <HubEuScreen player={player} setTab={setTab}
                             /* 減 P7 — a chegada recolhe perante o /player
                                confirmado: sem isto, a do Eu nao o podia pedir. */
                             onPlayerRefresh={loadPlayer}
                             onOpenProfile={() => { haptic("select"); setProfileModalOpen(true); }}
                             onOpenAchievements={() => { haptic("select"); setAchModalOpen(true); }}
                             /* 至 a chegada carrega a zona 1 inteira: o sino e a
                                Loja tem de chegar ca', como no `home`. */
                             notifCount={notifCount}
                             onSino={() => { haptic("select"); setNotifModalOpen(true); setNotifReloadKey(x => x + 1); loadNotifBadge(); }}
                             onLoja={() => { haptic("select"); setShopModalOpen(true); }}
                             seletorAberto={euSeletor}
                             /* 至 A MACANETA. Ordem do owner 2026-09-23, textual:
                                *"como vou encontrar corpo etc. (...) tenho que
                                clicar 2 vezes no eu pra abrir o menuzinho pra ver
                                o corpo"*. O selector existia e era alcancavel
                                — e a chegada nao tinha UMA palavra a dizer que
                                ele existe. Uma porta que nao se anuncia e' a Lei
                                §1 partida. */
                             onAbrirSeletor={() => { haptic("select"); setEuSeletor(true); }}
                             onFecharSeletor={() => setEuSeletor(false)}
                             onPorta={abrirPorta} />
              )}
              {/* Onda R3 (ui_v2) — o MUNDO como mapa (landing do hub Mundo).
                   Double-gated como o hub_eu_screen: flag + typeof-guard
                   (cliente cacheado fail-safe). Viagem/crônica reusam os modais
                   do App root (o mapa não reimplementa nada). */}
              {tab === "hub_mundo_screen" && featureEnabled("ui_v2") && typeof HubMundoScreen === "function" && (
                <HubMundoScreen player={player} setTab={setTab}
                                onOpenTravel={() => { haptic("select"); setTravelModalOpen(true); }}
                                onOpenChronicle={(c) => { haptic("select"); openChronicle(c); }}
                                onOpenProfession={() => { haptic("select"); setProfModalOpen(true); }}
                                onOpenCaravan={caravanEnabled()
                                  ? () => { haptic("select"); setCaravanOpen(true); }
                                  : null}
                                initialIsle={mundoIsle} isleNonce={mundoIsleNonce}
                                onIsleConsumed={() => setMundoIsle(null)}
                                onPorta={abrirPorta} />
              )}
              {/* Onda R4a (ui_v2) — a CAVERNA como antessala (landing do hub
                   Caverna). Double-gated como o hub_mundo_screen: flag +
                   typeof-guard (cliente cacheado fail-safe). */}
              {tab === "hub_caverna_screen" && featureEnabled("ui_v2") && typeof HubCavernaScreen === "function" && (
                <HubCavernaScreen player={player} setTab={setTab} />
              )}
              {/* Onda R4b (ui_v2) — o PERGAMINHO como daily scroll (landing do
                   hub Pergaminho). Double-gated, mesmo padrão. */}
              {tab === "hub_pergaminho_screen" && featureEnabled("ui_v2") && typeof HubPergaminhoScreen === "function" && (
                <HubPergaminhoScreen player={player} setTab={setTab} />
              )}
              {tab === "settings"      && (
                <SettingsTab onPlayerRefresh={loadPlayer}
                             onReplayTutorial={() => setTutorialOpen(true)}
                             onOpenLobby={() => { haptic("select"); setLobbyModalOpen(true); }}
                             onOpenAdmin={() => { haptic("select"); setAdminModalOpen(true); }}
                             isAdmin={!!(player && player.is_admin)} />
              )}
            </TabErrorBoundary>
            </div>
          </div>
          {/* 兩面: no desktop a navegação vive no trilho — uma barra inferior de
              telemóvel num ecrã de 1920 é exactamente o que o owner apontou. */}
          {!desktop && (
          <>
          {/* Onda R1 (REDESIGN_MASTER.md) — shell v2 gated: com ui_v2 no manifest
              (flag per-world, graduada no R6 — mundo ON = todos) a nav vira os 5
              hubs do Pergaminho Vivo; sem a flag (main) renderiza a nav atual
              byte-idêntica. typeof-guard fail-safe: se o V2BottomNav não existir
              (cliente cacheado), cai na velha. */}
          {(featureEnabled("ui_v2") && typeof V2BottomNav === "function")
            ? <V2BottomNav tab={tab} setTab={setTab}
                             onRetoque={(k) => {
                               // 至 *"mudar de hub limpa o seu estado"*: o retoque
                               // so' alterna no Eu; em qualquer outro hub o
                               // selector fecha-se em vez de ficar pendurado.
                               if (k === "hub_eu") setEuSeletor(v => !v);
                               else setEuSeletor(false);
                             }} />
            : <BottomNav tab={tab} setTab={setTab} />}
          </>
          )}
          </SurfaceColumn>
          {/* Root-mounted modals live OUTSIDE the per-tab TabErrorBoundary, so a
              render crash in one (e.g. the Sect Hall) previously unmounted the
              whole app into a BLACK SCREEN (player report: [jogador], "apertei na
              minha seita anciã e ficou tela preta", 2026-06-17). This boundary
              turns any modal crash into a recoverable card + logs the real error,
              instead of a silent black void (Lei §1). Resets when the open-modal
              set flips (resetKey); the CTA peels the crashed modal via _handleBack.
              ToastHost / NotifToastStack stay OUTSIDE it (must survive a crash). */}
          <ModalErrorBoundary label="root-modal" resetKey={_anyModalOpen} onClose={_handleBack}>
          {/* 門 P6 — a consulta: requisito, valor actual, o que falta e o
              caminho. Uma janela para as duas entradas (porta trancada e
              «Desbloqueios»), dentro da fronteira dos modais da raiz. */}
          {portaConsulta && typeof PortaConsulta === "function" && (
            <PortaConsulta player={player} hubKey={portaConsulta.hub} foco={portaConsulta.foco}
                           onClose={() => setPortaConsulta(null)}
                           onIr={(k) => { setPortaConsulta(null); setTab(k); }} />
          )}
          {/* Sistema Multi-Servidor (Fase 2) — Lobby (every player) + Admin Panel
              (owner only). Entry lives in Settings (no PlayerHeader chip). */}
          {lobbyModalOpen && (
            <LobbyModal
              player={player}
              onClose={() => setLobbyModalOpen(false)}
              onServerChanged={() => {
                // World switched — the middleware re-resolves on the NEXT request,
                // so reset to home + reload the player + bump tab reload signals so
                // the new world's character/state replaces the old one cleanly.
                setLobbyModalOpen(false);
                setTab("home");
                loadPlayer();
                setPlazaReload(x => x + 1);
                setExploreReload(x => x + 1);
                loadNotifBadge();
                loadEvents();
              }}
            />
          )}
          {adminModalOpen && (
            <AdminPanelModal onClose={() => setAdminModalOpen(false)} />
          )}
          {/* MV-5 — o ENCONTRO (oferta de storylet): diálogo + aceitar/recusar.
              Root-mounted (lição nav-state-loss); typeof-guard p/ tabs.js
              cacheado sem o componente. Depois de responder, bumpa a seção da
              QuestsTab + a praça (a oferta saiu de lá). */}
          {styOffer && typeof StoryletOfferModal === "function" && (
            <StoryletOfferModal
              offer={styOffer}
              onClose={() => setStyOffer(null)}
              onDone={() => {
                setStyOffer(null);
                setStyReload(x => x + 1);
                setPlazaReload(x => x + 1);
              }}
            />
          )}
          {/* MV-8 — a EMBOSCADA do jiānghú (⚔️ / 💰 / 🏃 + o fork moral na
              vitória). Root-mounted (lição nav-state-loss + ela stacka a
              arena); typeof-guard p/ tabs.js cacheado. Ao terminar recarrega o
              jogador (pedras/qi mudaram) e bumpa a praça (o caçador saiu). */}
          {jhAmbush && typeof JianghuAmbushModal === "function" && (
            <JianghuAmbushModal
              offer={jhAmbush}
              onClose={() => setJhAmbush(null)}
              onDone={() => {
                loadPlayer();
                setPlazaReload(x => x + 1);
              }}
            />
          )}
          {/* MV-7 — a Guilda dos Ofícios (cerimônia/status/troca/heal de
              aliado). Root-mounted (lição nav-state-loss); typeof-guard p/
              tabs.js cacheado; só monta com a flag ON (o modal tem useApi —
              lição MV-4: OFF nunca seta profModalOpen, e o guard aqui é
              cinto-e-suspensórios). */}
          {profModalOpen && featureEnabled("profissoes") && typeof ProfessionModal === "function" && (
            <ProfessionModal
              onClose={() => setProfModalOpen(false)}
              onPlayerRefresh={loadPlayer}
            />
          )}
          {/* MV-9.5 — 商队 A Caravana (vitrine + escambo + o atlas de onde
              nascem as coisas). Root-mounted (lição nav-state-loss);
              typeof-guard p/ tabs.js cacheado; só monta com a flag ON (o modal
              tem useApi — lição MV-4: OFF nunca seta caravanOpen, e o gate aqui
              é cinto-e-suspensórios). Mandar uma carga debita material e pode
              dar karma → loadPlayer + a praça repinta (o card passa a dizer
              "na estrada"). */}
          {caravanOpen && featureEnabled("caravana") && typeof CaravanModal === "function" && (
            <CaravanModal
              onClose={() => setCaravanOpen(false)}
              onPlayerRefresh={() => { loadPlayer(); setPlazaReload(x => x + 1); }}
            />
          )}
          {shopModalOpen && (
            <ShopOverlayModal
              onClose={() => setShopModalOpen(false)}
              onPlayerRefresh={loadPlayer}
            />
          )}
          {notifModalOpen && (
            <NotificationsModal
              onClose={() => { setNotifModalOpen(false); loadNotifBadge(); }}
              onNavigate={(targetTab) => {
                // A1 ([jogador] 2026-06-16): a notification's target_tab may be a MODAL
                // (whispers / chronicle), not a BottomNav tab. Naively setTab("whispers")
                // matched no content branch → empty screen (Lei §1 violation). Route
                // modal-targets to their modal, real tabs to setTab, and ANY unknown
                // target falls back to "home" — the content area is NEVER left blank.
                if (!targetTab) return;
                setNotifModalOpen(false);
                if (targetTab === "whispers") { setWhispersModalOpen(true); return; }
                if (targetTab === "chronicle") { openChronicle(null); return; }
                // "profile" is the sect-promotion / identity target (world_sects_engine,
                // achievements) — a MODAL, not a tab. Route it so the CTA lands on the
                // ProfileModal instead of the home fallback.
                if (targetTab === "profile") { setProfileModalOpen(true); return; }
                var _validTabs = (typeof TAB_DEFS !== "undefined")
                  ? TAB_DEFS.map(function (d) { return d.key; })
                  : ["home"];
                setTab(_validTabs.indexOf(targetTab) !== -1 ? targetTab : "home");
              }}
              refreshKey={notifReloadKey}
            />
          )}
          {eventsModalOpen && (
            <EventsModal onClose={() => { setEventsModalOpen(false); loadEvents(); }} />
          )}
          {tutorialOpen && (
            <TutorialModal onDismiss={() => {
              setTutorialOpen(false);
              // Refresh player so tutorial_seen flips to true client-side
              // immediately (server already persisted on dismiss).
              loadPlayer();
            }} />
          )}
          {/* ProfileModal mounts FIRST in JSX so its portal renders earlier
              in document.body. Sub-modals (continent/path/karma) mount AFTER
              and stack visually on top — closing them returns to ProfileModal,
              still mounted underneath. (Modal uses Portal to body, so same
              zIndex means last-rendered wins paint order.) */}
          {profileModalOpen && (
            // 2026-05-26 — Consolidated identity surface. Opens when the
            // player taps the avatar/name in PlayerHeader. Identity grid
            // cards drill into the existing Continent/Path/Karma modals
            // STACKED ON TOP (ProfileModal stays mounted underneath).
            // Closing the sub-modal returns to ProfileModal, not to the
            // underlying tab — the cultivator never loses their place.
            // See GameDesign/profile_modal_spec.md.
            <ProfileModal
              player={player}
              setTab={setTab}
              onClose={() => setProfileModalOpen(false)}
              onOpenContinent={() => setContinentModalOpen(true)}
              onOpenPath={() => setPathModalOpen(true)}
              onOpenKarma={() => setKarmaModalOpen(true)}
              onOpenSect={() => setWorldSectModalOpen(true)}
              onOpenHall={() => setSectHallModalOpen(true)}
              onOpenProfession={featureEnabled("profissoes")
                ? () => { haptic("select"); setProfModalOpen(true); }
                : null}
            />
          )}
          {/* Onda R4 (ui_v2) — Conquistas do hub EU, root-mounted (back nativo
              fecha o modal, não o webapp). Equipar título muda o header →
              loadPlayer. OFF nunca abre (só a grade v2 seta true). */}
          {achModalOpen && (
            <AchievementsModal
              onClose={() => setAchModalOpen(false)}
              onPlayerRefresh={loadPlayer}
            />
          )}
          {continentModalOpen && (
            <ContinentModal onClose={() => setContinentModalOpen(false)} />
          )}
          {pathModalOpen && (
            // v16.2.1 (emergent-path pivot) — Always render PathModal (read-only).
            // Path emerges from karma + quest choices + actions; no manual pick.
            // PathPickModal was removed; PathModal handles all states (crystallized
            // or not, pre-R3 or post-R3) with didactic copy.
            <PathModal onClose={() => setPathModalOpen(false)} player={player} />
          )}
          {karmaModalOpen && (
            // v16.3 — Karma silent spine modal. Gauge + recent events log +
            // divergence warning (conditional) + canonical "what changes
            // karma" catalog. Read-only — the only writeable action is the
            // Heart Demon kick-off when divergence is active.
            <KarmaModal onClose={() => setKarmaModalOpen(false)} />
          )}
          {/* v16.4 — World Sect directory (9 NPC houses + per-house affinity).
              Drill-in from the ProfileModal 🏯 card. The join-confirm
              (WorldSectJoinModal) stacks on top via worldSectJoinTarget. */}
          {worldSectModalOpen && (
            <WorldSectDirectoryModal
              player={player}
              onClose={() => setWorldSectModalOpen(false)}
              onSelectJoin={(sect) => setWorldSectJoinTarget(sect)}
            />
          )}
          {worldSectJoinTarget && (
            <WorldSectJoinModal
              sect={worldSectJoinTarget}
              onClose={() => setWorldSectJoinTarget(null)}
              onJoined={() => {
                setWorldSectJoinTarget(null);
                setWorldSectModalOpen(false);
                loadPlayer();
              }}
            />
          )}
          {/* v16.4c — Sect Hall (members). Stacks above the ProfileModal; a
              rank/library/quest change calls loadPlayer() so the header + the
              ProfileModal card reflect the new rank/contribution. */}
          {sectHallModalOpen && (
            <SectHallModal
              player={player}
              onClose={() => setSectHallModalOpen(false)}
              onChanged={loadPlayer}
            />
          )}
          {/* Onda 3 — Heaven's Whispers feed (atmospheric, read-only). */}
          {whispersModalOpen && (
            <WhispersModal onClose={() => setWhispersModalOpen(false)} />
          )}
          {/* World Pulse Fase 1 — Os Registos Celestiais (the living world log).
              MV-3: onOpenIsle SÓ com ui_v2 ON — sem o mapa v2 o chip "ver no
              mapa" não renderiza (no-op honesto, Lei §1). */}
          {chronicleModalOpen && (
            <ChronicleModal continent={chronicleContinent}
                            onClose={() => setChronicleModalOpen(false)}
                            onOpenIsle={featureEnabled("ui_v2") ? openIsleOnMap : null} />
          )}
          {/* Onda 3 — NPC-cultivator profile + challenge (honest 🤖, stacks the
              combat arena; a win → spare/execute moral fork → karma). */}
          {npcTarget && (
            <NpcCultivatorModal
              target={npcTarget}
              onClose={() => setNpcTarget(null)}
              onResolved={() => { loadPlayer(); setPlazaReload(x => x + 1); }}
            />
          )}
          {/* Onda 4b — Travel between continents. A successful trip refreshes the
              player (continent/stones changed → header + plaza follow) and bumps
              the plaza board/presence, then closes. */}
          {travelModalOpen && (
            <TravelModal
              onClose={() => setTravelModalOpen(false)}
              /* MV-8 — o callback DECLARAVA ZERO parâmetros e o `res` que o
                 TravelModal já entregava caía no chão. Qualquer coisa que o
                 servidor passe a mandar na chegada (a emboscada é a primeira)
                 nascia INVISÍVEL no mini-app por causa desta linha. */
              onTraveled={(res) => {
                setTravelModalOpen(false); loadPlayer(); setPlazaReload(x => x + 1);
                if (res && res.jianghu_ambush) setJhAmbush(res.jianghu_ambush);
              }}
            />
          )}
          {/* Onda 5 — Reinos Exploráveis Hidden-Monster duel (lifted to App root,
              reuses DuelArenaModal + the spare/execute fork). On resolve it
              refreshes the player + bumps the Explore tab's scan (depth/bag). */}
          {exploreDuelTarget && (
            <ExploreDuelModal
              target={exploreDuelTarget}
              onClose={() => setExploreDuelTarget(null)}
              onResolved={() => { loadPlayer(); setExploreReload(x => x + 1); }}
            />
          )}
          {/* MA-39a — P2P Trade modal. Lifted to the App root (back-button +
              _handleBack peel). Polls trade/state ~3s; the item-picker is an
              internal sub-modal that does NOT unmount this parent. */}
          {tradeId && (
            <TradeModal
              tradeId={tradeId}
              onClose={() => setTradeId(null)}
              onPlayerRefresh={loadPlayer}
            />
          )}
          </ModalErrorBoundary>
          <ToastHost />
          {/* v14.13c Item 2 — Top-anchored push notifications for new inbox
              items. Mounted at the shell level so it overlays every tab. */}
          <NotifToastStack />
        </div>
      );
    }

    // ─── Bootstrap ───────────────────────────────────────────────────────────
    // Load i18n dicts BEFORE mounting React. Failures fall back to empty dicts
    // (t() then returns raw keys — better than crashing the app).
    // 🔴 2026-09-13 — O ARRANQUE NÃO PODE DEPENDER DE UM PEDIDO QUE NUNCA VOLTA.
    //
    // Achado de uma auditoria externa ao bundle, verificado aqui e CONFIRMADO:
    // o `catch` por língua salvava o 404 e o erro de rede, mas **não salvava o
    // pedido pendurado**. Um `fetch` que não resolve nem rejeita (rede a meio,
    // proxy mudo, túnel do Telegram a cair) deixa o `Promise.all` para sempre
    // pendente, o `.finally()` nunca dispara e o `createRoot(...).render()`
    // nunca corre: **ecrã em branco, sem erro, para sempre.** É o pior beco que
    // existe (Lei §1), porque nem sequer há tela onde escrever o aviso.
    //
    // O relógio resolve-o: ao fim de 6s cada língua desiste e entra vazia. O
    // `t()` já degrada por token, portanto o jogo abre — em pior estado, mas
    // ABRE, e o jogador vê alguma coisa em vez de preto.
    //
    // ⚠️ `AbortController` E o relógio: sem o `abort` o pedido continuava vivo
    // a consumir a ligação depois de já não interessar a ninguém.
    const _I18N_TIMEOUT_MS = 6000;
    async function _loadI18n() {
      const langs = ["pt", "en", "es"];
      const results = await Promise.all(langs.map(async (lc) => {
        const ctrl = (typeof AbortController === "function") ? new AbortController() : null;
        const tm = setTimeout(() => { try { ctrl && ctrl.abort(); } catch (e) {} }, _I18N_TIMEOUT_MS);
        try {
          const r = await fetch(`/miniapp/i18n/${lc}.json`, Object.assign(
            { cache: "no-cache" }, ctrl ? { signal: ctrl.signal } : {}));
          if (!r.ok) throw new Error(`${lc} ${r.status}`);
          return [lc, await r.json()];
        } catch (e) {
          console.warn("i18n load failed", lc, e);
          return [lc, {}];
        } finally {
          clearTimeout(tm);
        }
      }));
      for (const [lc, dict] of results) STRINGS[lc] = dict;
    }
    _loadI18n().finally(() => {
      ReactDOM.createRoot(document.getElementById("root")).render(<App />);
    });
