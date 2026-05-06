# Product

## Register

product

## Users

Two primary personas sharing the same interface:

**Active traders** scan pre-market, run screens, and make position decisions in minutes. They need speed: fast scanning, instant signal recognition, one-click drill-down. Their primary screens are the AI Stock Screener and Sector Rotation Scanner.

**Quant analysts** research sector trends, build strategies, and run backtests over hours or days. They need depth: parameter control, optimization workflows, rich visualizations. Their primary screen is QuantGen Strategy Builder.

Both personas overlap — a trader reviewing a screen result may jump into QuantGen to backtest the idea. The interface must support quick-scan and deep-research modes without friction.

## Product Purpose

TradeCraft combines three trading workflows (stock screening, sector rotation analysis, and quantitative strategy building) into one platform backed by a PostgreSQL market database. It exists because traders and analysts currently juggle multiple tools to go from idea to backtested strategy. Success means someone moves from "I wonder if this pattern works" to a validated backtest in a single session.

## Brand Personality

Crafted power. The product feels built by people who understand markets deeply and care about the tool as much as the output. Three words: precise, fluid, assured.

It projects competence without arrogance. The interface is opinionated about data presentation but flexible about workflow. It never feels like enterprise software, never feels like a toy.

Voice: direct and knowledgeable. No marketing superlatives. No hand-holding. Trust that the user is competent and give them leverage.

## Anti-references

- **Yahoo Finance** — cluttered, ad-choked, information chaos with no visual hierarchy. Tab overload. The opposite of crafted.
- **Bloomberg Terminal** — monospace density as aesthetic, not as choice. Legacy density that confuses complexity with sophistication.
- **Generic SaaS dashboards** — identical card grids, hero metrics with gradient accents, glassmorphism defaults. The AI slop test.
- **Robinhood** — consumer gamification. Chunky cards, oversized padding, confetti. Treats trading as entertainment.

## Design Principles

1. **Information density with intention.** Dense data is fine when every number earns its place. The crime is chaos, not quantity. Use whitespace deliberately, not as filler.

2. **Speed respects expertise.** Interactions for expert users: keyboard shortcuts, instant scan triggers, no unnecessary confirmations. Don't slow down traders who know what they're doing.

3. **One surface, two modes.** The same interface must serve quick-scan (trader at 6am, low light, fast decisions) and deep-research (analyst at 2pm, exploratory, iterative). Design for the transition between these modes.

4. **Clarity over chrome.** The interface disappears behind the data. No decorative elements that don't serve understanding. Every visual element must justify itself against the question: "does this help someone make a better trading decision?"

5. **Technical beauty.** TradingView-level visual craft. Charts that feel native and precise. Typography that reads like a financial document designed by Apple. The tool should feel like it was built by people who understand both markets and design.

## Accessibility & Inclusion

Practical baseline: strong contrast ratios (minimum 4.5:1 for body text), readable typography at all sizes, focus states on interactive elements. Full WCAG AA not required at this stage, but the design system should not preclude it. Dark mode is the default (traders work early mornings and late nights); light mode must be equally usable, not an afterthought.
