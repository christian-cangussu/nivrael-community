---
name: nivrael-design
description: Use this skill to generate well-branded interfaces and assets for Nivrael — Caminho da Imortalidade, a Wuxia/Xianxia idle RPG played inside Telegram. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping or production use.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out of `assets/` and `ui_kits/miniapp/` and create static HTML files for the user to view. Use the components from `ui_kits/miniapp/Components.jsx` and `Screens.jsx` as building blocks. Import `colors_and_type.css` for all CSS tokens.

If working on production code, read `README.md` fully, import `colors_and_type.css` for token definitions, and use the component patterns from the UI kit as reference for styling decisions.

## Quick Reference

**Fonts:** Cinzel (display/headings) + Noto Serif SC (Chinese decorative) + Noto Sans (body/UI)
**Key Colors:** `#06080f` bg · `#c9903a` gold · `#f5c97a` gold-light · `#3ecf7e` jade · `#e2eaff` text
**Card pattern:** `background: linear-gradient(180deg, rgba(17,29,53,.85), rgba(13,20,34,.85)); border: 1px solid #1e3060; border-radius: 14px`
**Animation:** Everything uses fade-up entrance (0.35s ease), breathe loops (4s), shimmer on gold
**Icons:** Emoji-first (☯️🏯🐉🏆🎒🎯📜) + Chinese glyphs (道仙氣劍龍) as decoration
**Language:** PT-BR primary, EN + ES via STRINGS{} i18n dict

## Assets Available
- `assets/hero-bg.webp` — atmospheric mountainscape with floating temples
- `assets/clouds-divider.webp` — decorative cloud band with gold/teal qi trails
- `assets/alchemy-art.webp` — jade cauldron with qi flame
- `assets/realm-*.webp` — 11 realm illustrations (mortal → true-immortal)

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.
