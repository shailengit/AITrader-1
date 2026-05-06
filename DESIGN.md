---
name: TradeCraft
description: Unified trading platform combining AI stock screening, sector rotation analysis, and quantitative strategy building.
colors:
  primary: "#10B981"
  primary-light: "#34D399"
  primary-dark: "#059669"
  canvas-dark: "#050505"
  canvas-light: "#f5f5f7"
  surface-dark: "#0a0a0a"
  surface-raised-dark: "#111111"
  surface-overlay-dark: "#171717"
  surface-light: "#ffffff"
  surface-raised-light: "#fafafc"
  surface-overlay-light: "#ededf2"
  foreground-dark: "#ffffff"
  foreground-light: "#1d1d1f"
  muted-dark: "rgba(255,255,255,0.7)"
  muted-light: "rgba(0,0,0,0.8)"
  subtle-dark: "rgba(255,255,255,0.4)"
  subtle-light: "rgba(0,0,0,0.48)"
  disabled-dark: "rgba(255,255,255,0.2)"
  border-dark: "rgba(255,255,255,0.08)"
  border-hover-dark: "rgba(255,255,255,0.15)"
  border-light: "rgba(0,0,0,0.04)"
  border-hover-light: "rgba(0,0,0,0.1)"
typography:
  display:
    fontFamily: "Inter, SF Pro Display, Helvetica Neue, sans-serif"
    fontWeight: 600
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.47
    letterSpacing: "-0.022em"
  label:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    letterSpacing: "0.15em"
    textTransform: "uppercase"
  mono:
    fontFamily: "JetBrains Mono, Fira Code, monospace"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  micro: "6px"
  std: "10px"
  comfort: "14px"
  large: "20px"
  xl: "24px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  2xl: "48px"
  3xl: "64px"
  4xl: "96px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#000000"
    rounded: "{rounded.pill}"
    padding: "18px 42px"
  button-primary-hover:
    backgroundColor: "{colors.primary-light}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.foreground-dark}"
    rounded: "{rounded.comfort}"
    padding: "8px 16px"
  card-base:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.foreground-dark}"
    rounded: "{rounded.xl}"
    padding: "32px"
  card-raised:
    backgroundColor: "{colors.surface-raised-dark}"
    textColor: "{colors.foreground-dark}"
    rounded: "{rounded.xl}"
    padding: "32px"
  input:
    backgroundColor: "{colors.canvas-dark}"
    textColor: "{colors.foreground-dark}"
    rounded: "{rounded.comfort}"
    padding: "16px"
  chip:
    backgroundColor: "{colors.surface-overlay-dark}"
    textColor: "{colors.primary}"
    rounded: "{rounded.pill}"
    padding: "8px 20px"
  status-badge-connected:
    backgroundColor: "rgba(16,185,129,0.15)"
    textColor: "{colors.primary-light}"
    rounded: "{rounded.pill}"
    padding: "6px 16px"
---

# Design System: TradeCraft

## 1. Overview

**Creative North Star: "The Precision Instrument"**

TradeCraft's interface is a precision instrument for financial decision-making. Every surface, number, and chart feels machined — dark, cool, and exact. The tool disappears behind the data; what remains is clarity and the confidence to act. This is software built by people who understand that milliseconds and basis points matter, and that the interface should never be the thing you're thinking about when you're thinking about a trade.

The system is dark by default. Traders and analysts work early mornings and late nights, often in dim rooms facing large displays. The canvas recedes — a near-black (#050505) substrate that lets charts and numbers hold the visual field. Execution Green (#10B981) is the sole accent color: it signals positive momentum, confirmed breakouts, and actionable insight. Its rarity is its power. When you see green, it means something.

This system explicitly rejects the clutter and chaos of Yahoo Finance (ad-choked, no visual hierarchy), the consumer gamification of Robinhood (confetti, oversized padding), and the generic SaaS dashboard template (identical card grids with gradient accents). It is a tool for experts, and it looks like one.

**Key Characteristics:**
- Dark-first, precision-oriented. The canvas recedes; data advances.
- Single accent (Execution Green) used sparingly. Color = signal, not decoration.
- High information density with deliberate whitespace. Density is never chaos.
- Tactile, assured components. Buttons commit. Cards have physical presence.
- Native-quality charts and data visualization. TradingView-level craft.

## 2. Colors

Execution Green on a near-black substrate. One accent, one canvas family, one neutral text ramp. No secondary palette — the restraint is the statement.

### Primary
- **Execution Green** (#10B981): The sole accent. Used for positive signals (confirmed breakout, momentum, successful backtest), primary action buttons, selected states, focus rings. Appears on less than 5% of any screen at rest. Its rarity makes it meaningful.
- **Execution Green Light** (#34D399): Hover states on primary buttons, active indicators, pulse animations.
- **Execution Green Dark** (#059669): Pressed states, deep accent backgrounds.

### Neutral
- **Abyss** (#050505): Dark mode canvas. The deepest background — behind all content, scrollbars, page chrome.
- **Void** (#0a0a0a): Dark mode default surface. Cards at rest, panel backgrounds.
- **Basalt** (#111111): Dark mode raised surface. Elevated cards, modal backdrops, section dividers.
- **Shadow** (#171717): Dark mode overlay surface. Dropdowns, tooltips, highest elevation layer.
- **Chalk** (#ffffff): Dark mode foreground text, light mode surface.
- **Graphite** (rgba(255,255,255,0.7)): Muted body text on dark. Secondary information, descriptions, timestamps.
- **Slate** (rgba(255,255,255,0.4)): Subtle text on dark. Placeholder copy, disabled labels, tertiary metadata.
- **Smoke** (rgba(255,255,255,0.08)): Default borders on dark. Hairlines between cards, input strokes, divider lines.
- **Frost** (rgba(255,255,255,0.15)): Hover borders on dark. Interactive element boundaries on hover.

### Named Rules
**The Signal Rule.** Execution Green is never decorative. It appears only where it communicates a positive signal: breakout confirmed, scan passed, backtest profitable, action available. If a green element doesn't mean "go," it shouldn't be green.

**The Abyss Rule.** The canvas (#050505) is intentionally darker than the surfaces that sit on it. This creates ambient lift without shadows — surfaces advance by being slightly lighter than the void behind them. Never set a card background to the canvas color.

## 3. Typography

**Display Font:** Inter (with SF Pro Display, Helvetica Neue fallback)
**Body Font:** Inter (with SF Pro Text, Helvetica Neue fallback)
**Mono Font:** JetBrains Mono (with Fira Code fallback)

**Character:** Inter is the reliable choice for financial interfaces — highly legible at small sizes, neutral in character, with excellent tabular numerals for data alignment. The single-family approach (Inter at all weights) keeps the system cohesive. JetBrains Mono enters for code, tickers, and quantitative output — the analyst's native tongue.

### Hierarchy
- **Display** (600 weight, clamp(40px, 5vw, 56px), 1.07 line-height): Hero page titles. Appears once per view — the primary heading that orients the user.
- **Headline** (600 weight, 28-32px, 1.14 line-height): Section headers within pages. Divides major content areas.
- **Title** (600 weight, 21px, 1.19 line-height): Card titles, modal headers, panel labels.
- **Body** (400 weight, 17px, 1.47 line-height): Primary reading text. Descriptions, analysis copy, report content. Max line length 70ch.
- **Body Emphasis** (600 weight, 17px, 1.24): Key values, emphasized statements within body text.
- **Caption** (400 weight, 14px, 1.29): Secondary information, chart labels, metadata rows.
- **Micro** (600 weight, 12px, 1.33, 0.15em letter-spacing, uppercase): Labels, badges, category markers, filter names.
- **Nano** (400 weight, 10px, 1.47): Legal, timestamps, tertiary metadata. Smallest permitted size.
- **Mono** (400 weight, 14px, 1.5): Code blocks, ticker symbols, numerical output, strategy parameters.

### Named Rules
**The Tabular Rule.** Any column of numbers must use `font-variant-numeric: tabular-nums`. Aligned digits are non-negotiable in a financial interface.

**The Two-Mode Rule.** Body text max-width is 70ch for reading comfort (reports, analysis). Data tables and ticker grids ignore this limit — they fill available width. Never apply reading-length constraints to tabular data.

## 4. Elevation

Ambient lift. Surfaces float above the canvas with soft, diffuse shadows — not harsh drop shadows, but a gentle physicality that suggests depth without calling attention to itself. The canvas (#050505) is darker than the lowest surface (#0a0a0a), creating a tonal foundation. Surfaces then step up through raised (#111111) and overlay (#171717) for modals, dropdowns, and tooltips.

Shadows are ambient, not structural. They create atmosphere rather than hard boundaries. On hover, elements lift subtly (translateY -2px) with an intensified shadow — this is the primary micro-interaction pattern.

### Shadow Vocabulary
- **Ambient Card** (`box-shadow: rgba(0,0,0,0.4) 0px 8px 32px 0px`): Default card shadow on dark mode. Soft, diffuse, atmospheric.
- **Elevated** (`box-shadow: 0 20px 60px rgba(0,0,0,0.5), 0 0 100px rgba(16,185,129,0.1)`): Modals and highest-level overlays. Deeper shadow with subtle Execution Green glow.
- **Hover Lift** (`transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,0,0,0.3)`): Interactive card hover. Lift + shadow intensification.

### Named Rules
**The Flat-By-Default Rule.** Interactive elements are flat at rest. Shadows appear on hover, focus, or elevated state — they signal interactivity, not decoration. A card with a shadow but no hover response is a broken promise.

## 5. Components

### Buttons
- **Shape:** Fully rounded (999px / pill). No hard corners on primary actions.
- **Primary:** Execution Green (#10B981) background, black (#000) text, 18px 42px padding. Bold (600 weight), 18px. Inset highlight gradient on top for material depth.
- **Hover:** Execution Green Light (#34D399), intensified glow shadow, translateY -2px lift.
- **Active:** Execution Green Dark (#059669), pressed state, translateY 0.
- **Ghost:** Transparent background, foreground text, comfort radius (14px), sm-md padding. Hover: 5-10% white overlay background.
- **Disabled:** Smoke background, Slate text, no interaction. Never use muted + cursor-not-allowed alone — remove the background color so the button visually recedes.

### Cards
- **Corner Style:** Large (20px) for content cards. XL (24px) for feature cards and stat displays.
- **Background:** Void (#0a0a0a) at rest. Basalt (#111111) when raised/elevated.
- **Shadow Strategy:** Ambient Card shadow at rest. Elevated shadow for selected/active cards.
- **Border:** Smoke (rgba(255,255,255,0.08)) stroke. Selected cards get Execution Green border (30-50% opacity).
- **Internal Padding:** 32px (lg) standard. 48px (2xl) for stat cards.

### Inputs / Fields
- **Style:** Near-black (#000) background, Smoke border, comfort radius (14px). Monospace or body font depending on context.
- **Focus:** Execution Green border (50% opacity), subtle green glow (0 0 20px rgba(16,185,129,0.15)).
- **Placeholder:** Slate text at 20% opacity. Dim, not absent.
- **Error:** Red border (#EF4444), no background shift.

### Chips / Tags
- **Style:** Pill shape, Shadow (#171717) background, Execution Green text, Smoke border.
- **Active/Selected:** Execution Green at 10% background, Execution Green border at 30%, Execution Green text.
- **Inactive:** White at 5% background, Zinc text, minimal border.

### Navigation
- **Top Bar:** Void or Basalt background, 64px height (standard), 120px height (Sector page with expanded context). Bottom hairline border (Smoke).
- **Items:** No sidebar (current architecture). Top bar is the primary navigation surface.
- **Active Indicator:** Execution Green underline or dot. No background shift on nav items.

### Status Badge
- **Connected:** Execution Green at 15% background, Execution Green Light (#34D399) text, pill shape. Green pulsing dot.
- **Disconnected:** Amber/warning style — amber at 15% background, amber text.
- **Typography:** Micro style (12px, 600 weight, uppercase, 0.15em tracking).

### Modals
- **Backdrop:** Black at 85% opacity with blur. Heavy, immersive — this is a focus-forcing layer.
- **Container:** Shadow (#171717) at 95% opacity, XL radius (24px), Elevated shadow with green glow.
- **Header:** Title typography, close button (circle, ghost style).
- **Max Width:** 560px (standard), 90vw (chart modals).

## 6. Do's and Don'ts

### Do:
- **Do** use Execution Green only for positive signals and primary actions. It means "go."
- **Do** use the tonal surface ramp (Void → Basalt → Shadow) for depth instead of multiple shadows on the same element.
- **Do** use tabular-nums on every column of numbers. Always.
- **Do** maintain 4.5:1 minimum contrast on body text. White on Abyss passes. Graphite on Abyss does not — reserve Graphite for 17px+ text.
- **Do** let data fill available width. Reading-length constraints (70ch) apply to prose, not tables.
- **Do** use 8px as the base spacing unit. Every gap should be a multiple of 8.
- **Do** animate only transform and opacity. Never animate layout properties (width, height, top, left).

### Don't:
- **Don't** use border-left or border-right greater than 1px as a colored accent stripe. Use full borders, background tints, or nothing.
- **Don't** use gradient text (background-clip: text). Use a single solid color from the neutral ramp.
- **Don't** use glassmorphism (backdrop-filter blur) as a default surface treatment. It's acceptable on modals and chart overlays only.
- **Don't** nest cards inside cards. If you're about to, one of them isn't a card.
- **Don't** use Yahoo Finance-style clutter — multiple ad-sized cards, competing CTAs, information with no hierarchy.
- **Don't** use identical card grids with icon + heading + text repeated. Vary card design by content type.
- **Don't** wrap content in unnecessary containers. Most things don't need a max-width wrapper — the layout component handles that.
- **Don't** use Execution Green on negative signals or destructive actions. Red (#EF4444) for errors, losses, and deletes.
- **Don't** use em dashes. Commas, colons, semicolons, or periods instead.
