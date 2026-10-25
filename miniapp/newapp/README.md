# Nivrael — Caminho da Imortalidade · Design System

## Overview

**Nivrael** is a Wuxia/Xianxia idle RPG cultivation game played inside Telegram (Mini App). Players meditate to accumulate Qi, ascend through 11 realms (Mortal → True Immortal), form sects, fight world bosses, craft alchemical pills, forge celestial artifacts, and face divine tribulations.

- **Open beta:** 250+ active users, monetisation validated (premium jade + battle pass)
- **Platform:** Telegram Mini App (single-page React/Babel app, `nivrael.com`)
- **Languages:** PT-BR (primary) · EN · ES, via `STRINGS{}` i18n dict
- **Tech stack:** React 18 + Babel standalone, Telegram WebApp JS SDK, vanilla CSS, Google Fonts

## Sources

| Resource | Location / Access |
|---|---|
| Miniapp codebase | `miniapp/index.html` (1357 lines, single-file React app) |
| Realm illustrations (11) | `assets/realm-*.webp` |
| Hero background | `assets/hero-bg.webp` |
| Clouds divider | `assets/clouds-divider.webp` |
| Alchemy art | `assets/alchemy-art.webp` |
| Production URL | `https://nivrael.com` (Telegram Mini App) |
| Design Figma | *(not provided)* |

---

## CONTENT FUNDAMENTALS

### Voice & Tone
- **Mythic gravitas** — copy channels ancient Chinese cultivation lore. The world is vast, eternal, dangerous.
- **Second-person imperative** — the player is addressed as a cultivator on a path: "Medita para avançar no Caminho." Commands feel like instructions from a Grand Elder, not a SaaS tooltip.
- **No emojis in narrative text** — emoji appear only as functional icons in UI tabs/quests (🧘, 🐉, 📜) never in prose or card titles.
- **Cinzel for display** — all section headings use Cinzel (small-caps feel). Never use lowercase for card titles: `text-transform: uppercase` + `letter-spacing: 1px` is the standard.
- **Numerals formatted** — large numbers use K/M/B suffixes (e.g. "2.5M", "340K"). Never raw integers.
- **Realm names are sacred** — always use the full realm name in context (e.g. "Alma Nascente — Camada 3"). Never abbreviate in player-facing UI.
- **Wuxia vocabulary** — prefer "Qi", "Dao", "Cultivador", "Seita", "Artefacto Celestial", "Pedras de Espírito", "Jade Espiritual". Avoid "XP", "points", "wallet".

### Casing
- Card titles: `UPPERCASE` + `letter-spacing: 1px`
- Player names: Title Case (Dao Names are sacred, capitalise all)
- Tab labels: Title Case in EN, natural in PT/ES
- Realm names: Title Case
- Button labels: Sentence case

### Examples
- ✅ `"ATRIBUTOS"` not `"Atributos"` (card title)
- ✅ `"Imortal Verdadeiro — Camada 9"` not `"True Imm. 9"`
- ✅ `"A canalizar Qi…"` (loading state — lowercase, ellipsis)
- ✅ `"Termina em 2h 14m"` not `"Ends: 02:14:00"`
- ✅ `"🏯 Seita dos Picos Celestes"` in tab labels only
- ❌ Never: `"XP gained"`, `"Level up!"`, `"Points"`

---

## VISUAL FOUNDATIONS

### Aesthetic Direction
**Ancient mythic Chinese meets dark fantasy.** The palette is deep night sky — near-black blues, starfield blacks — punctuated by aged gold, celestial jade, and imperial purple. Everything breathes; nothing is static. Inspired by Black Myth: Wukong UI, Genshin Impact menus, and Honkai Star Rail loading screens — but with a unique textural identity grounded in parchment, jade tablets, and ink-wash painting.

### Color System
| Token | Value | Usage |
|---|---|---|
| `--bg` | `#06080f` | App background (near-black, blue-tinted) |
| `--card` | `#0d1422` | Card base fill |
| `--panel` | `#111d35` | Panel / elevated surface |
| `--border` | `#1e3060` | Default border (subtle blue-navy) |
| `--border2` | `#253f7a` | Highlighted border |
| `--text` | `#e2eaff` | Primary text (cool blue-white) |
| `--muted` | `#6e89bf` | Secondary / label text |
| `--muted2` | `#3d5a9e` | Inactive tab text |
| `--gold` | `#c9903a` | Primary accent — patinated gold |
| `--gold2` | `#f5c97a` | Light gold — highlight, values |
| `--jade` | `#3ecf7e` | Success / positive / jade green |
| `--red` | `#e5534b` | Danger / HP bar |
| `--warn` | `#f59e0b` | Warning / elder badge |
| `--purple` | `#6b21a8` | Imperial purple (realm 3, 6) |

**Realm Colors** (per-realm accent, applied to orb, pill, glow):
- 0 Mortal: `#9ca3af` (stone grey)
- 1 Qi Condensation: `#60a5fa` (sky blue)
- 2 Foundation: `#fbbf24` (amber)
- 3 Core: `#a855f7` (violet)
- 4 Nascent Soul: `#2dd4bf` (teal)
- 5 Soul Transformation: `#3b82f6` (blue)
- 6 Void Refinement: `#8b5cf6` (indigo)
- 7 Body Integration: `#f59e0b` (gold)
- 8 Mahayana: `#38bdf8` (cosmic cyan)
- 9 Tribulation: `#eab308` (lightning yellow)
- 10 True Immortal: `#f472b6` (rose-gold legendary)

### Typography
| Role | Font | Weight | Size | Notes |
|---|---|---|---|---|
| Display / Headings | Cinzel | 600–700 | 18–24px | Gold gradient, letter-spacing .5–1px |
| Chinese decorative | Noto Serif SC | 500–700 | 11–140px | Used for bg glyphs (道仙氣劍龍), orb glyph, dao-title |
| Body / UI labels | Noto Sans | 300–600 | 10–15px | All functional UI text |
| Card titles | Cinzel | 400 | 12px | UPPERCASE, letter-spacing 1px, color `--muted` |
| Dao name (player) | Cinzel | 700 | 18px | Gold gradient shimmer |
| Numbers / values | Noto Sans | 600 | 15px | color `--text` |

All fonts loaded from Google Fonts CDN. No local font files provided — see `colors_and_type.css` for full import.

### Backgrounds
- **App background:** near-black `#06080f` with two radial gradients — blue at top (realm energy), purple at bottom (cosmic depth)
- **Background glyphs:** Chinese characters (道仙氣劍) positioned absolutely, 90–140px, `rgba(201,144,58,.06)` — very subtle amber, `animation: drift-bg 14s` slow float
- **Hero imagery:** Full-bleed painted fantasy art (mountainscapes, temples, qi spirals). Dark, atmospheric, illustration-style not photo.
- **Cards:** `linear-gradient(180deg, rgba(17,29,53,.85), rgba(13,20,34,.85))` — translucent navy, with 1px `--border` border

### Spacing & Layout
- Mobile-first, `max-width: 480px` centered
- Content padding: `12px 14px 90px` (bottom accounts for tab bar)
- Card margin-bottom: `12px`; card padding: `14px`
- Stat grid: `2-column`, `gap: 8px`
- Inventory grid: `4-column`, `gap: 6px`
- Tab bar height: ~72px + safe area inset

### Border Radius
- Cards: `14px`
- Stats / inner cells: `10px`
- Inventory cells: `8px`
- Pills/badges: `999px` (full round)
- Buttons: `10px`
- Progress bars: `6px`

### Shadows & Glow
- Orb glow: `box-shadow: 0 0 40px rgba(85,140,255,.45), inset 0 0 20px rgba(180,210,255,.35)`
- Meditating orb: `box-shadow: 0 0 60px rgba(168,85,247,.55)` — stronger purple
- Equipped item: `inset 0 0 8px rgba(201,144,58,.3)` gold inner glow
- No external drop shadows on cards — depth comes from layered translucent fills

### Animation System
| Name | Duration | Easing | Usage |
|---|---|---|---|
| `orb-breathe` | 4s (2.6s meditating) | ease-in-out | Orb scale 1→1.045 + brightness pulse |
| `orb-ring-out` | 3s | ease-out | Concentric ring expand + fade (meditating only) |
| `qi-rise` | 3s | ease-out | Particles float up during meditation |
| `fade-up` | 0.35s | ease | Card/item entrance (opacity 0→1, translateY 8px→0) |
| `shimmer` | 2.5–4s | linear | Gold gradient sweep on loading glyph + CB bar |
| `drift-bg` | 14s | ease-in-out | Background glyph slow float + opacity pulse |

**Principles:**
- Everything breathes (scale/opacity pulse on loops)
- Entrances: `fade-up` always — never pop in
- Tap/press: `transform: scale(.97)` — subtle shrink
- No bounce easing — everything is stately and slow
- Haptic feedback on tab change via `tg.HapticFeedback.selectionChanged()`

### Cards (Parchment/Jade Tablet Style)
- Translucent navy gradient fill (not opaque — layers visible)
- 1px solid `--border` (#1e3060) — subtle navy outline
- `border-radius: 14px`
- Title: 12px Cinzel UPPERCASE `--muted` + right-aligned gold value
- Inner rows: 1px dashed rgba border between items
- No drop shadows — glows only on special states (orb, equipped items)

### Badges & Pills
Three semantic states:
- **Jade (success):** `rgba(62,207,126,.18)` bg + `--jade` text + jade border
- **Warn:** `rgba(245,158,11,.16)` bg + `--warn` text
- **Red (danger):** `rgba(229,83,75,.16)` bg + `--red` text
Realm pill: transparent dark bg, colored border + text matching realm color

### Iconography
See ICONOGRAPHY section below.

### Hover / Press States
- Buttons: `transform: scale(.97)` on `:active`
- Tabs: `background: rgba(255,255,255,.04)` on `:active`
- No hover states (mobile-first — no pointer hover in Telegram WebApp)

### Color Vibe of Imagery

> ⚠️ **REWRITTEN 2026-09-04 — this section is the STYLE SEED.** Every piece of
> art generated for Nivrael from now on is prompted from these words, so an
> error here does not cost one image: it costs ~307. The version written on
> 2026-05-01 said *"deep navy, midnight purple, teal/cyan qi energy"* — **cold**
> — and that is now in direct conflict with the visual direction decided by
> WEB-C/WEB-D and written in `Cerebro/Nivrael/GameDesign/LINGUAGEM_VISUAL_WEB_C.md`:
> **warm black** (`--ink #0b0a0c`) with **朱砂 cinnabar** (`#c8442f`) as the
> signature accent. Generating at scale against the old seed would have produced
> hundreds of pieces that fight the app they live in — the "montanha AZUL sobre
> preto quente" that the visual-language doc forbids in text.

Dark, painterly, semi-realistic fantasy illustration — ink-wash (水墨) sensibility
rendered with depth, never flat vector, never photography.

**Ground tones — WARM, not navy.** Warm near-black, charcoal, soot, bistre; the
darkness of ink and lamp-smoke, not of night sky. Where a scene needs cold, it
comes from *material* (jade, stone, mist, snow), never from the ground itself.

**Light sources.** Aged gold and amber lantern-light; ember and hearth. Light is
the warm thing in the frame — it is what the eye is meant to find.

**The accent of last resort.** 朱砂 cinnabar red (`#c8442f`) — the seal, the
talisman, the sash, the blood. Used **once** per composition, never twice: it is
a signature, not a colour scheme.

**Qi.** Qi takes the colour of its REALM (see Realm Colors above), which is the
one axis where cold is correct and intentional — a Qi Condensation cultivator's
qi is sky-blue because `--realm-1` is `#60a5fa`. Realm colour is identity, not
frame, and the warm skin deliberately does not touch it (`Mecanicas/miniapp.md`
§1.6). Everything *around* the qi stays warm.

**Atmosphere.** Fog, smoke, incense, mountain haze, drifting ash. Silhouetted
ridgelines. Depth by layered atmosphere, not by drop shadow.

**Never:** neon; aurora/borealis skies; cyan-teal rivers of energy; flat vectors;
photography; Western high-fantasy armour; bright saturated "mobile-game" candy
palettes. (The last one is the Lei §2 failure mode with a name — *"soa a jogo de
cultivo ou a Candy Crush?"*.)

---

## ICONOGRAPHY

> ⚠️ **REWRITTEN 2026-09-08 (印 OS ÍCONES).** The old text below the line said
> *"iconography in Nivrael is **emoji-first** for functional icons"*. That is no
> longer the direction, by the owner's order (2026-09-07, textual): *"fora orb
> outra coisa nada de icone no game mais. entende? icones genericos bom."*
> Anything that still reads "emoji-first" in this file is history, not guidance.

### Approach — **drawn SVG marks, never a shipped emoji, never a CJK font**

Measured 2026-09-08 in `miniapp/components/{ui,tabs,app}.js`: **194 distinct
emoji, 1638 occurrences**. The flaw is not that they are ugly — it is that
**they are not ours and they change shape**: an emoji is drawn by the *device's*
font, so the pagoda on the Sect tab is three different illustrations on iPhone,
Android and Windows, in three palettes nobody here chose. After WEB-D (the warm
skin), A CARTA and O CULTIVADOR built a language of warm ink and cinnabar, the
navigation was still a set of colourful Apple pictograms — the exact warning
case in `GameDesign/LINGUAGEM_VISUAL_WEB_C.md` (Achado 2).

**The house set lives in one place: `NIV_MARKS` in `miniapp/components/ui.js`.**

- One grid: `viewBox 0 0 24 24`, live area 3–21, `stroke-width 1.6`, round caps
  and joins, `fill:none`. Never more than ~8 drawing pieces — the bottom bar
  renders at 20px and that is the only size that decides.
- `currentColor` always. A mark has **no colour of its own**; it takes the token
  of the place it lives in, exactly as the 朱砂 `SealMark` already did. That is
  what lets `pele_quente` reach them for free.
- **Not a CJK font.** The mini-app loads none, and at 19px the glyph falls back
  to the system face — that would be trading one set of someone else's
  pictograms for another. It is why the seal is already an SVG (§1.8.3 of
  `Mecanicas/miniapp.md`).
- ⚠️ **The four-pointed concave sparkle (✦) is forbidden in the set.** It is the
  glyph the industry has used since 2023 to mean *AI-generated*, and it is why
  the owner killed the orb on 07/09. The heavens are drawn as a **crescent with
  round stars** (`heavens`), never as a sparkle.
- ⚠️ **A mark with no name is worse than an emoji.** Every mark either has a
  visible label beside it (the rail, the cards, the sections) or receives
  `title` → `role="img" aria-label`. The bottom bar writes the label only for
  the *active* slot, so with marks ON its buttons gain `aria-label`.
- **Catalog emoji are NOT chrome and are not touched** (`beast.emoji`,
  `pill.emoji`, …). They are content, and on the card they are the honest back
  of a piece that has no art yet.

Gated by the per-world flag **`iconografia`** (OFF everywhere). With it off,
every site renders today's emoji byte for byte — proved by the DOM rehearsal.

### Tab marks (the 25 destinations — `TAB_DEFS`, which the desktop rail groups)

| Tab | Mark | What it is |
|---|---|---|
| Home | `mountain` | 山 — one mountain, many paths |
| Cultivation | `seated` | 坐 — the seated figure (O CULTIVADOR's identity) |
| Sect | `pagoda` | 宗 — three tiered eaves |
| Guild | `allies` | 盟 — two joined |
| World Boss | `dragon` | 饕餮 — the bronze beast mask |
| Plaza | `city` | 城 — wall, eave, gate |
| Explore | `compass` | 罗盘 — the needle |
| Cavern | `formation` | 阵 — the array |
| Dungeons | `portal` | 门 — the gate within the gate |
| Crafting | `cauldron` | 鼎 — three legs, two ears |
| Combat / weapon slot | `sword` | 劍 — ONE upright blade, never crossed |
| Beasts | `paw` | 爪 |
| Faction | `banner` | 旗 — the swallowtail |
| Celestial | `heavens` | 月 — crescent + two round stars |
| Body | `stance` | 大 — standing, with the tempering bands |
| Partner | `knot` | 雙環 — two interlocking jade rings |
| Battle Pass | `tally` | 牌 — the hanging wooden tablet |
| Ranking | `ranks` | 榜 — the posted list, never a trophy |
| Inventory | `pouch` | 囊 |
| Quests | `notice` | 榜文 — the hanging notice |
| Shop | `jade` | 玉佩 — the bi disc with tassel |
| Market | `coin` | 方孔錢 — the square-holed cash |
| Announcements | `bell` | 鐘 — the temple bell |
| Settings | `brush` | 筆 — **deliberately not a gear** (a cog is every SaaS panel) |
| Achievements (Home card) | `stele` | 碑 — deeds cut in stone |

### Currency marks
- Spirit Jade (premium): `jade` (was 💎)
- Spirit Stones: `stone` (was 🪨)
- Celestial Fragments: `shard` (was ✨)

### State marks
`lock` 鎖 · `incense` 一炷香 (waiting — in wuxia time is measured by a stick of
incense, and the hourglass is somebody else's clock) · `gift` 包袱 · `warn` ·
`check` · `cross`.

### To look at the set
`python scripts/_marks_contact_sheet.py` draws **every** mark at 16/20/28/44/72px
in both skins, plus the bottom bar as it actually ships. It reads `NIV_MARKS`
out of `ui.js` — never a copy, because judging a copy is judging a drawing the
game does not draw.

---

<details><summary>Histórico — a decisão "emoji-first" de 2026-05-01 (superada)</summary>

### Approach
Iconography in Nivrael is **emoji-first for functional icons**, supplemented by Chinese glyphs as decorative elements. No external icon library (no Lucide, no Heroicons, no icon fonts). All icons are either:

1. **Unicode emoji** — used in tab bar (☯️🏯🐉🏆🎒🎯📜), quest icons, currency indicators
2. **Chinese glyphs** — 道 仙 氣 劍 龍 — used as large decorative background elements and orb glyphs
3. **Inline text symbols** — ⚔️🌿⚒️📜💫🛡️ for building/item type indicators

### Tab Icons
| Tab | Emoji |
|---|---|
| Cultivation | ☯️ |
| Sect | 🏯 |
| World Boss | 🐉 |
| Ranking | 🏆 |
| Inventory | 🎒 |
| Quests | 🎯 |
| Announcements | 📜 |

### Currency Icons
- Spirit Jade (premium): 💎
- Spirit Stones: 🪨
- Celestial Fragments: ✨

</details>


### Glyph Decoration
Background glyphs: 道 (Dao/Way) · 仙 (Immortal) · 氣 (Qi) · 劍 (Sword) · 龍 (Dragon)
Orb glyph: 道 (idle) · 氣 (meditating)

### ⚠️ The 14 existing pieces vs. the warm direction (decided 2026-09-04)

The art in `assets/` was generated on 2026-05-01 against the **old, cold** seed.
It was never served by the game — not one byte reached a player. Two categories,
two different answers, and the split follows a precedent that is already written
down rather than a new rule invented here:

| | Verdict | Why |
|---|---|---|
| **`realm-*.webp` (11)** | ✅ **KEEP AS-IS — they are IDENTITY** | A realm's illustration *is* the realm, in exactly the way the 11 `--realm-*` colours are. `Mecanicas/miniapp.md` §1.6 already rules that the warm skin **does not touch** `--realm-*` ("identidade do jogo, não moldura"). `realm-mortal` being a cool blue-grey dusk is consistent with `--realm-0` being stone grey — the cool is the realm's, not the frame's. |
| **`hero-bg` · `clouds-divider`** | ❌ **DO NOT SHIP — regenerate warm** | These are **moldura**. `hero-bg` is a blue-night sky with a green-teal aurora and cyan qi rivers; laid over `--ink #0b0a0c` it is literally the "montanha AZUL sobre preto quente" that WEB-D had to spend 6 dedicated tokens to prevent. |
| **`alchemy-art`** | ⚠️ **Re-look before use** | Jade cauldron with qi flame — plausibly warm enough, but unverified against the warm ground. Not a blocker for anything shipping now. |

⚠️ **The verdict on the realm art is provisional until it is SEEN on the warm
ground.** "Identity survives the skin" is an argument, and this house has been
burned by arguments that were never looked at (WEB-C built the rail, tested it,
never opened it). Whoever first puts realm art on a real screen must look at it
there, at 390×844, with `pele_quente` ON — and if it fights, the decision above
loses to the eyes.

✅ **DISCHARGED 2026-09-05.** It was put on a real screen (the cultivation
scene), served over real HTTP, looked at at 390×844 with `pele_quente` ON. It
does not fight: a realm's colour is identity and the warm skin does not touch
`--realm-*`. The verdict stands, and is no longer an argument — it is a
screenshot.

### Image Assets

⚠️ **There is exactly ONE description of these files, and it is the posture
table in [`assets/`](#assets--served-at-miniappassetsfile-since-2026-09-05)
below.** A short prose list here used to duplicate it and drifted: it repeated
*"(amber tones)"* for a picture that is cyan. Two documents both claiming to
describe the same image is how a caption ends up lying about it.

---

## File Index

| File/Folder | Description |
|---|---|
| `README.md` | This file — full design system documentation |
| `SKILL.md` | Agent skill descriptor for Claude Code / AI agent usage |
| `colors_and_type.css` | CSS custom properties: colors, typography, spacing, animation tokens |
| `assets/` | All visual assets — see table below |
| `preview/` | Design system preview cards (visible in Design System tab) |
| `ui_kits/miniapp/` | Telegram Mini App UI kit — full interactive prototype |
| `screenshots/` | Auto-generated verification screenshots |

### assets/ — served at `/miniapp/assets/<file>` since 2026-09-05

⚠️ **The route and the folder do NOT share a name, and that is deliberate.** The
public route is `/miniapp/assets/` (that is where the game looks for it); the
files live in `miniapp/newapp/assets/` (this design system is where art
belongs, and the 15 preview pages index it as `../assets/`). The bridge is the
`"dir": "newapp/assets"` field of the `assets` rule in `_MINIAPP_SUBDIR_RULES`
(`core/webserver.py`), guarded by `scripts/_test_web_c_superficies.py`.

Cache is **one year, immutable** — the opposite of the JS bundle, which
revalidates. An illustration never changes; if one is regenerated it gets a new
**filename**, never a new body under the old name.

⚠️ **`.webp` is NOT in `_COMPRESSIBLE_SUFFIXES`.** It is already compressed;
gzipping it burns server CPU for ~0% (sometimes it grows). Same for png/jpg/avif.

#### ⚠️ THE POSTURE TABLE — looked at, one by one, 2026-09-05

The prose descriptions below used to be inherited, not verified, and **two of
them were wrong**: `realm-foundation` was documented as *"(amber tones)"* and is
in fact **cyan**; `realm-core` was documented as *"a cultivator seated,
meditating"* and is levitating (corrected 2026-09-04). So before any of these
went under a caption, all eleven were opened and described from the pixels.

**The finding that changed a design:** the eleven are **not** a set of "a
cultivator in state X". They are portraits of a **REALM**, and the posture
varies — **six are seated, five are not.** Captioning any of them with the
player's own state ("you are seated, meditating for 47m") would print a lie over
the picture, and the worst case is realm 10, where **21 of the `main`'s 37
active-30d players (57%)** live: a winged figure in flight under the words *"you
are sitting, waiting"*.

Hence the rule that the cultivation scene follows (`Mecanicas/miniapp.md §1.8`):
**the art says WHERE, the orb and the caption say WHAT.** Nothing on the screen
makes a claim about the painted figure, so none of the eleven can lie.

| File | Realm | What is actually in the frame | Seated? |
|---|---|---|:--:|
| `realm-mortal.webp` | 0 Mortal | terraced valley at dusk, lantern-lit village, a lone traveller **standing** on a cliff path | ✗ |
| `realm-qi.webp` | 1 Qi Condensation | cross-legged on a mossy ledge in a star-roofed cave, cradling a blue qi droplet | ✓ |
| `realm-foundation.webp` | 2 Foundation | a **standing** silhouette + two lantern-bearers before a lotus-crowned temple. ⚠️ **CYAN, not amber** — the old note was wrong | ✗ |
| `realm-core.webp` | 3 Core Formation | cross-legged but **levitating**, arms spread, golden core igniting at the chest, violet spiral in a runic crystal hall | ✓ (airborne) |
| `realm-nascent-soul.webp` | 4 Nascent Soul | seated on a rune dais, incense burning, the nascent spirit floating above the head | ✓ |
| `realm-soul-transformation.webp` | 5 Soul Transformation | seated on a plinth, galaxies and butterflies streaming from the crown | ✓ |
| `realm-void-refinement.webp` | 6 Void Refinement | **mid-combat** — sword drawn, space shattering into shards | ✗ |
| `realm-body-integration.webp` | 7 Body Integration | half-lotus **floating** over a cracking cliff, muscles lit from within, storm overhead | ✓ (airborne) |
| `realm-mahayana.webp` | 8 Mahayana | seated on a peak under a spiral of rune-circles | ✓ |
| `realm-tribulation.webp` | 9 Tribulation | **standing** on a cliff edge, arms raised, scarlet lightning striking a shield-sphere | ✗ |
| `realm-true-immortal.webp` | 10 True Immortal | **flying** — wings of light spread, ascending into a black vortex | ✗ |
| `hero-bg.webp` | — | ❌ **not shipped.** Blue-night sky, teal aurora, cyan qi rivers: the "blue mountain over warm black" the visual-language doc forbids | — |
| `clouds-divider.webp` | — | ❌ **not shipped.** Same cold moldura | — |
| `alchemy-art.webp` | — | ⚠️ jade cauldron with qi flame — not yet used, not yet re-looked on the warm ground | — |

⚠️ **The realm art is now SEEN on the warm ground** (390×844, `pele_quente` ON,
2026-09-05) and the earlier verdict holds: it does not fight the warm skin,
because a realm's colour is its identity and the skin deliberately does not
touch `--realm-*`. The provisional note from 2026-09-04 is discharged.

### preview/ (Design System Tab cards)

| File | Group | Description |
|---|---|---|
| `colors-palette.html` | Colors | Base, surface, text, accent, semantic tokens |
| `colors-realm.html` | Colors | 11 realm accent colors with glyphs |
| `type-scale.html` | Type | Cinzel + Noto Serif SC + Noto Sans — all roles |
| `type-specimens.html` | Type | Live text specimens at each size |
| `spacing-tokens.html` | Spacing | Border radius, spacing scale, progress bars, elevation |
| `spacing-animations.html` | Spacing | shimmer, fade-up, drift, breathe, pulse-glow, press |
| `components-buttons.html` | Components | Default, primary, jade, ghost, danger — all sizes |
| `components-badges.html` | Components | Jade/gold/warn/red badges + realm pills + seg control |
| `components-cards.html` | Components | Stat card, progress card, leaderboard row |
| `components-orb.html` | Components | Cultivation orb — idle, meditating, True Immortal |
| `components-nav.html` | Components | Player header + 7-tab bottom nav bar |
| `components-inventory.html` | Components | Equipped slots (gold glow), spatial ring, items grid |
| `components-boss-quests.html` | Components | World boss card, announcement feed, quest row |
| `brand-realm-art.html` | Brand | All 11 realm artwork thumbnails |
| `brand-illustrations.html` | Brand | Hero background, clouds divider, alchemy art |

### ui_kits/miniapp/

| File | Description |
|---|---|
| `index.html` | Full interactive prototype — phone frame + sidebar nav |
| `Components.jsx` | Shared components: PlayerHeader, BottomNav, Card, Orb, Badge, etc. |
| `Screens.jsx` | All 7 tab screens with mock data |
| `styles.css` | Shared CSS vars + keyframe animations |
| `README.md` | Kit-specific documentation |

---

## UI Kits

| Kit | Path | Description |
|---|---|---|
| Telegram Mini App | `ui_kits/miniapp/index.html` | Full interactive prototype of the 7-tab Nivrael Mini App |
