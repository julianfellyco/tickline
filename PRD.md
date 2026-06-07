# tick/line — Product Requirements (Plain-English Edition)

| | |
|---|---|
| **Product** | tick/line — a "where is the market moving?" tool |
| **Owner** | Julian Fellyco |
| **Status** | Two products live: a **Simple Board** (for anyone) and a **Research Engine** (for tinkering) |
| **Live at** | tickline-bay.vercel.app/simple/ (simple board) · tickline-bay.vercel.app/ (research board) |
| **Last updated** | 2026-06-07 |

> **The one rule for this document:** no jargon without a plain explanation. If your aunt couldn't follow it, it's rewritten.

---

## 1. What is this, in one breath?

The stock market has "themes" — groups of related companies: chip makers, gold miners, nuclear, banks, bitcoin, defense, and so on. At any moment, money is flowing *into* some themes and *out* of others.

**tick/line shows you which themes are heating up and which are cooling down — and whether regular people have noticed yet.** That's it.

There are two versions:

- 🟢 **The Simple Board** *(new)* — a one-screen page of colored cards. Green = going up and popular. Red = going down and ignored. A beginner gets it in 10 seconds.
- 🔬 **The Research Engine** — the full toolkit (37 themes, backtests, a data pipeline) for someone who wants to dig in.

---

## 2. The problem it solves

1. **"Trend alerts" online are useless.** They ping you *after* something already jumped — by then you've missed it.
2. **The action rotates.** Within "AI" alone, the lead passes around: chips → networking → power → cooling → memory. Knowing *which part is hot right now* is the hard bit.
3. **What people shout about isn't always what's actually going up.** Sometimes a theme is all over the news *while its price is falling* (a trap). A good tool shows you the gap between the talk and the price.

---

## 3. Who is it for?

- 🟢 **Simple Board:** a beginner or busy person who wants a quick, honest read — "is this thing trending, and do people care?" — without learning finance jargon.
- 🔬 **Research Engine:** a hobbyist trader (the owner) who wants to test ideas with real data and refuses to fool themselves.

---

## 4. How the Simple Board decides (the whole logic)

For each theme it asks **two plain questions**, using a ready-made fund (an "ETF" — a single ticker that holds the whole basket, e.g. `SMH` = chip makers):

**Question 1 — Is the price trending UP?**
- Is it above its **200-day average price**? (A simple, time-tested "is it in an uptrend" check.)
- Is it **beating the S&P 500** (the overall US market) over the last 3 months?
- Both yes → **up**. Both no → **down**. Mixed → **sideways**.

**Question 2 — Is the CROWD paying attention?**
- How much **recent news** is there about this theme compared to the others?
- More than average → **loud**. Less → **quiet**.

**Put them together → a color:**

| | Crowd quiet | Crowd loud |
|---|---|---|
| **Price up** | 🔵 **Early** — moving before people noticed *(the best spot)* | 🟢 **Confirmed** — up and everyone agrees |
| **Price down** | 🔴 **Dead** — falling and ignored | 🟡 **Hype trap** — loud but falling, be careful |
| **Sideways** | ⚪ no clear trend yet | ⚪ no clear trend yet |

Each card also shows one plain sentence, e.g. *"Quietly trending up before the crowd noticed — the early ones."*

**Why this is honest, not dumbed-down:** "price above its 200-day average" is one of the few simple rules that has actually held up over decades. We're not pretending it predicts the future — just describing what's happening right now, in plain words.

---

## 5. What the Research Engine adds

The full system ranks **37 themes** (not just 18 ETFs), builds baskets from individual stocks, and runs **backtests** — i.e. it replays history to check "if I had followed this rule, would I have made money?"

This is where we learned the most important lesson (next section).

---

## 6. What we tested — and the humbling result

We asked: *"Does picking the strongest themes and avoiding the weakest actually beat the market?"* We replayed ~6 years of real data, **including trading costs** (because a test that ignores fees is fiction).

Here's the scoreboard. Two terms first, in plain words:
- **Return/yr** = how much it grew per year.
- **"Sharpe"** = return *for the risk taken* — higher is better; above 1 is good. (A high return with terrifying swings is worse than a steady one.)
- **Worst drop** = the biggest fall from a peak — how much pain you'd have stomached.

| Strategy | Return/yr | Sharpe (risk-adjusted) | Worst drop |
|---|---|---|---|
| Buy strong themes, **short** weak ones (full set) | +31% | 0.34 *(bad)* | **−96%** *(wiped out)* |
| Buy the top 3 strongest themes only | +114% | 1.43 | −45% |
| **Just buy ALL the themes equally** | +47% | **1.54** *(best!)* | −30% |
| Just buy the S&P 500 (do nothing clever) | +16% | 1.12 | −22% |

**What this means in plain English:**
1. **Betting *against* weak themes ("shorting") nearly wiped the account out (−96%).** Don't do it.
2. The "+114% per year" from picking the top 3 looks amazing — **but it's not real.** We picked those 37 themes *because we already knew they did well*. That's like betting on yesterday's race. (The fancy term is "survivorship bias.")
3. **The killer test:** simply buying *all* the themes equally did **better on a risk-adjusted basis (1.54)** than cleverly picking the top ones (1.43). Being clever *lost* to being simple.

**Bottom line:** the smart-looking strategy didn't actually beat just owning a basket. So tick/line is honestly positioned as a **map of where money is moving — a research starting point — not a money-making machine.**

---

## 7. What's real vs. what isn't

| ✅ Real | ❌ Not proven |
|---|---|
| It correctly shows which themes are strong/weak right now | That following it makes money in the future |
| "Above the 200-day line" is a genuinely useful trend check | The eye-popping +114% backtest number |
| Owning a spread of strong themes roughly tracked the market+ | Any edge from "cleverly" picking among them |

---

## 8. What it's made of (the simple version)

- **Free price data** from Yahoo Finance (slightly delayed; can be wrong).
- **Free news counts** from Google News (a rough "buzz" gauge).
- A small script turns that into the colored board.
- A plain web page anyone can open. It refreshes itself each trading day.

No accounts, no fees, no AI making decisions. (We deliberately left out any "self-improving" trading AI — those tend to overfit to noise and talk themselves into bad trades. The board is plain, checkable math.)

---

## 9. What's next

- **Done ✅:** Simple Board is live on the web (tickline-bay.vercel.app/simple/). A daily auto-refresh is wired up (it rebuilds *both* boards) — it switches on once a Vercel access key is added and the change is merged.
- **Note on "real-time":** the boards refresh *daily/intraday at best*, not second-by-second. Data is ~15 minutes delayed and the signal is a 3-month trend, so live ticks would just be noise. "Fresh each trading day" is the right speed.
- **The real research question (maybe never profitable, and that's fine):** redo the backtest *without* cheating — only let it pick from stocks that looked relevant *at the time*, not with hindsight. That's the only way to get a number worth trusting. It might show there's no edge — which would be the honest answer.

---

## 10. The honest bottom line

The most valuable thing we learned building this: **a simple, diversified approach beat being clever — and even that "win" was partly hindsight.** So the product leads with the simple, honest board, and treats any "strategy" claim with suspicion until it survives a fair test.

*Use it to spot where attention and money are flowing. Do your own homework before risking a cent. This is not financial advice.*
