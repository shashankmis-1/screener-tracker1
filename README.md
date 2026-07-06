# Screener Tracker

A GitHub-hosted tracker for your daily Screener.in lists. You upload each day's
exported list; it keeps the full history, shows how many days each stock has
persisted, tells you **what to do next** for each, and (optionally) follows up on
stocks that have dropped off the list using Yahoo Finance prices.

The dashboard is a static site served by **GitHub Pages**, rebuilt automatically by
**GitHub Actions** every time you upload a list.

---

## What it does

- **History**: every daily list is kept in `data/lists/`, versioned forever.
- **Persistence**: a `Days` count and `Status` (new / current / persistent ≥3 days / dropped) so one-day noise is easy to tell from a stable, strengthening setup.
- **Triage**: buckets each stock (Shortlist / Extended / Expensive / Weak / Thin), scores it by your chosen profile (Momentum / Balanced / Value), and gives a plain-English **What next** with the exact chart checks.
- **Follow-up (optional)**: for stocks that dropped off, it pulls the latest price from Yahoo Finance to show what happened since (`Since drop%`).

### The one manual step
Screener.in has no free API, so **the daily list is your export** — you paste/upload it.
Everything after that is automated.

---

## One-time setup (≈10 minutes, all in the GitHub website)

1. **Create the repo.** On GitHub: *New repository* → name it e.g. `screener-tracker` → **Public** (required for free Pages) → *Create*.
2. **Upload these files.** On the repo page: *Add file ▸ Upload files* → drag in everything from this folder (keep the folder structure: `scripts/`, `docs/`, `data/`, `.github/`) → *Commit changes*. (Easiest: upload the provided `.zip` after unzipping locally, or drag the whole folder.)
3. **Turn on GitHub Pages.** *Settings ▸ Pages* → under **Source** choose **Deploy from a branch** → Branch: **main**, folder: **/docs** → *Save*. After a minute your dashboard is live at:
   `https://<your-username>.github.io/screener-tracker/`
4. **Actions are already on** for the repo. The first upload (step 2) triggers a build that generates `docs/data.json`. If the sample list is present you'll see data immediately.

That's it. Two sample lists (`2026-07-06.csv` and `2026-07-07.csv`) are included so the dashboard shows data on first load — you'll see persistence in action (KSB & Prudent as `current`/2 days, Endurance as a `new` early-turn, and three names `dropped`). Delete both sample files once you start uploading your own.

---

## Daily use (≈30 seconds)

1. In Screener, run your query and click **EXPORT** (or copy the table).
2. Save it as a CSV named with today's date: **`YYYY-MM-DD.csv`** (e.g. `2026-07-07.csv`).
3. On GitHub: open the `data/lists/` folder → *Add file ▸ Upload files* → drop the CSV in → *Commit changes*.
4. Actions runs automatically (~1 min). Refresh your Pages URL — the new list is tracked, persistence counts update, and dropped names get a follow-up price.

**Column names don't need to match exactly** — the parser recognises common Screener headers (CMP, RSI, 50/200 DMA, returns, PEG, Qtr Sales Var, ΔFII/ΔDII, Piotroski, etc.). Include as many as you have; missing ones are just skipped.

---

## Optional: follow-up prices for dropped stocks

To see what happened to a stock after it left your list, add its NSE symbol to
`data/symbols.csv`:

```
name,symbol
KSB,KSB.NS
Bharat Electron,BEL.NS
```

Use the exact **name** as it appears in your Screener export, and the Yahoo ticker
(**NSE symbol + `.NS`**). Only names you list here get a follow-up price; the rest are
still tracked for persistence.

> Note: Yahoo Finance access via `yfinance` is unofficial and occasionally rate-limited
> from CI. Follow-up prices are best-effort — if a fetch fails, the row just shows "–".

---

## Run it locally (optional)

```bash
pip install -r requirements.txt
python scripts/process.py          # regenerates docs/data.json
# then open docs/index.html in a browser
```

---

## Layout

```
data/lists/YYYY-MM-DD.csv   # your daily Screener exports (you add these)
data/symbols.csv            # optional name -> NSE ticker map for follow-ups
scripts/process.py          # merges lists, computes persistence, writes docs/data.json
docs/index.html             # the dashboard (served by GitHub Pages)
docs/data.json              # generated data (do not edit by hand)
.github/workflows/daily.yml # rebuilds on every upload + a weekday cron
```

Not investment advice — this ranks and tracks candidates to verify on the chart.
