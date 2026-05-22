# tickline — Brand

## Name

**Stylized:** `tick/line`
**Spoken:** "tickline"
**Slug:** `tickline`

A tick is a single market data point. A line is what they form when plotted honestly across time. The product turns one into the other — with real costs, no lookahead, and no marketing math.

The forward slash is the typographic signature. It echoes file paths, code comments, and the cleavage between input (`tick`) and output (`line`).

## Positioning

A learning-grade quantitative trading framework. Honest backtests. Real costs. Portfolio-ready engineering.

> If your backtest doesn't include slippage + fees + realistic fills, it's fiction.

This is the one-liner. Rigor over hype.

## Voice

| Do | Don't |
|---|---|
| State results plainly: "lost 32% over the year" | "Industry-leading returns" |
| Show drawdowns and losing trades | Hide the bad numbers |
| Use precise numbers (Sharpe 1.4, not "strong") | Use vague superlatives |
| Acknowledge what's untested | Imply production-readiness |
| Sound like a terminal log | Sound like a marketing deck |

Tone is **terminal-honest**: think Bloomberg printout, not Robinhood ad.

## Palette

```
--bg-deep      #07090c   /* terminal black, slight blue tint */
--bg-surface   #0f1419   /* card / panel */
--bg-elevated  #161d26   /* hover / focus surface */
--line         #1c2530   /* hairlines, grid */
--ink          #e8eef5   /* primary text */
--ink-dim      #8b96a5   /* secondary text */
--ink-faint    #5a6573   /* tertiary text, captions */
--signal       #00ff9d   /* primary accent, gains, "up" */
--signal-soft  #0a3d2f   /* gain background tint */
--alert        #ff4d6d   /* losses, warnings, "down" */
--alert-soft   #3d0a18   /* loss background tint */
--amber        #ffb340   /* neutral attention, pending */
```

**Usage rules:**
- `signal` green for positive PnL, "long", confirmed signals, and the brand slash
- `alert` red for negative PnL, "short", warnings
- Never use both at high saturation in the same view — pick one as the hero, soften the other
- `amber` is reserved for "watching" / pending states. Don't decorate with it.

## Typography

| Role | Family | Weight | Use |
|---|---|---|---|
| **Display** | Fraunces (italic) | 300 | Headings, hero, section openers |
| **Body** | Inter / Manrope | 400 | UI, paragraphs |
| **Mono** | JetBrains Mono | 400/500 | Numbers, code, tickers, timestamps, wordmark |

**Numbers are always mono.** A Sharpe of 1.43 in a proportional font looks like marketing. In mono, it looks like data.

## Logo

**Concept:** A frame around an equity curve — the *tickline* itself. The frame is the system that produces it (data, engine, costs). The curve is what the system outputs. The terminating candle stamps the moment of execution. The mark *is* the product.

### Variants

| File | Use |
|---|---|
| `assets/logo.svg` | Primary lockup — mark + wordmark, dark bg |
| `assets/logo-light.svg` | Same lockup for light backgrounds |
| `assets/logo-mark.svg` | Mark only — favicon, app icon, profile |
| `assets/wordmark.svg` | Wordmark only — text-heavy contexts |
| `assets/favicon.svg` | 32×32 optimized mark |
| `assets/social/og-image.svg` | OpenGraph / social card (1200×630) |

### Wordmark rules

- Always lowercase: `tick/line`
- The `/` is always `--signal` green on dark, `#00b770` on light
- Never substitute the slash with `-`, `.`, `:` or whitespace
- Don't capitalize either half ("Tick/Line" is wrong)

### Clearspace

Minimum clearspace around the mark = the height of the inner candle (≈ ¼ of mark height).

### Don't

- Don't recolor the equity curve to anything but `--signal`, `--alert`, or `--ink`
- Don't outline the wordmark
- Don't rotate the mark
- Don't add drop shadows or glows in static contexts

## Iconography

Stay geometric and thin-stroke. 1.5–2px strokes at 24px size. No filled icon sets, no rounded cartoon style. Calipers, not toys.

## Sample lockups

**Header:**
```
[mark]  tick/line
        honest curves from real ticks
```

**CLI banner:**
```
tick/line v0.1.0
honest curves from real ticks
```

**Footer:**
```
tickline — built by julianfellyco · MIT license · not financial advice
```
