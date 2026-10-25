# Nivrael Miniapp UI Kit

High-fidelity recreation of the Nivrael Telegram Mini App.

## Structure

| File | Description |
|---|---|
| `index.html` | Full interactive prototype — phone frame + sidebar |
| `Components.jsx` | Shared components: PlayerHeader, BottomNav, Card, Orb, Badge, etc. |
| `Screens.jsx` | Tab screens: CultivationTab, SectTab, WorldBossTab, LeaderboardTab, InventoryTab, QuestsTab, AnnouncementsTab |
| `styles.css` | Shared CSS: vars, animations, resets |

## Usage

Open `index.html` in a browser. Click tab items in the left sidebar to switch between screens. The Cultivation tab orb is interactive — click the meditation type buttons to toggle the meditating state (animated rings + qi particles).

## Design Width

375px (phone) — rendered inside a 375×720 phone frame with scrollable content.

## Components

- `PlayerHeader` — top bar with Dao Name, realm pill, currencies, spirit root
- `BottomNav` — 7-tab bottom navigation with gold active glow
- `Card` / `CardTitle` — translucent navy card with Cinzel uppercase title
- `StatGrid` — 2-column stat cells
- `ProgressBar` — cult/qi/hp variants
- `Badge` — jade/warn/red/gold semantic variants
- `CultivationOrb` — animated breathing orb, realm-tinted, meditating rings + qi particles
- `SegControl` — gold segmented selector
- `LeaderRow` — ranked list row with gold/silver/bronze + "you" highlight
- `Loading` — shimmer glyph spinner

## Mock Data

All data is local mock (no real API calls). The `MOCK_PLAYER`, `MOCK_CULT`, `MOCK_SECT`, etc. objects mirror the real API data shapes exactly.
