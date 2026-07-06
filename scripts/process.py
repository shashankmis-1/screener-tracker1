#!/usr/bin/env python3
"""
Screener list tracker.

Reads every daily Screener export in data/lists/ (files named YYYY-MM-DD.csv),
merges them into a history, computes persistence (how many days each stock has
appeared, first/last seen, status), optionally follows up on dropped names via
Yahoo Finance, and writes docs/data.json which the dashboard renders.

Run locally:  python scripts/process.py
In CI it is run by .github/workflows/daily.yml
"""
import csv, json, os, glob, re, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTS_DIR = os.path.join(ROOT, "data", "lists")
SYMBOLS_CSV = os.path.join(ROOT, "data", "symbols.csv")
OUT = os.path.join(ROOT, "docs", "data.json")

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def field_of(h):
    """Map a Screener column header to a canonical key (order matters)."""
    h = h.lower().strip()
    if "name" in h: return "name"
    if "symbol" in h or "ticker" in h or "nse code" in h: return "symbol"
    if "ind" in h and "pe" in h: return "indpe"
    if "peg" in h: return "peg"
    if "p/e" in h or h == "pe": return "pe"
    if "bv" in h: return "cmpbv"
    if "cmp" in h or "price" in h: return "cmp"
    if "cap" in h: return "mcap"
    if "avg" in h and "vol" in h: return "avgvol"
    if "vol" in h: return "vol"
    if "roce" in h: return "roce"
    if "roe" in h: return "roe"
    if "opm" in h: return "opm"
    if "sales" in h and ("qtr" in h or "quarter" in h or "yoy" in h): return "qsales"
    if "sales" in h and "3" in h: return "sales3"
    if "sales" in h: return "sales5"
    if "profit" in h and "3" in h: return "profit3"
    if "profit" in h: return "profit5"
    if "down" in h: return "down"
    if "dma" in h and "200" in h: return "dma200"
    if "dma" in h: return "dma50"
    if "1mth" in h or ("mth" in h and "1" in h): return "r1m"
    if "3mth" in h or ("mth" in h and "3" in h): return "r3m"
    if "6mth" in h or ("mth" in h and "6" in h): return "r6m"
    if "wk" in h: return "r1w"
    if "day" in h: return "r1d"
    if "1yr" in h or "yr" in h: return "r1y"
    if "piot" in h: return "piotroski"
    if "rsi" in h: return "rsi"
    if "debt" in h: return "debt"
    if "prom" in h: return "promchg"
    if "fii" in h: return "fii"
    if "dii" in h: return "dii"
    return None


def num(v):
    if v is None: return None
    s = str(v).replace(",", "").replace("%", "").strip()
    if s in ("", "-"): return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_file(path):
    m = DATE_RE.search(os.path.basename(path))
    date = m.group(1) if m else None
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.readline()
        f.seek(0)
        delim = "\t" if "\t" in sample else ","
        reader = csv.reader(f, delimiter=delim)
        fieldmap = None
        for cells in reader:
            if not cells:
                continue
            joined = " ".join(cells).lower()
            if fieldmap is None and "name" in joined:
                fieldmap = [field_of(h) for h in cells]
                continue
            if fieldmap is None:
                continue
            if "name" in joined and "cmp" in joined:
                continue  # repeated footer header
            rec = {}
            for i, key in enumerate(fieldmap):
                if key and i < len(cells):
                    rec[key] = cells[i].strip() if key in ("name", "symbol") else num(cells[i])
            nm = rec.get("name")
            if not nm or re.match(r"^s\.?no", str(nm).lower()):
                continue
            rows.append(rec)
    return date, rows


def load_symbols():
    m = {}
    if os.path.exists(SYMBOLS_CSV):
        with open(SYMBOLS_CSV, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                nm = (r.get("name") or "").strip()
                sy = (r.get("symbol") or "").strip()
                if nm and sy:
                    m[nm] = sy
    return m


def follow_up(dropped_names, symbols):
    """Best-effort current price for dropped names via Yahoo Finance."""
    follow = {}
    tickers = {nm: symbols[nm] for nm in dropped_names if nm in symbols}
    if not tickers:
        return follow
    try:
        import yfinance as yf
        data = yf.download(list(tickers.values()), period="5d", progress=False, group_by="ticker")
        for nm, tk in tickers.items():
            try:
                closes = data[tk]["Close"].dropna() if tk in data else data["Close"].dropna()
                follow[nm] = float(closes.iloc[-1])
            except Exception:
                pass
    except Exception as ex:
        print("yfinance follow-up skipped:", ex)
    return follow


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    files = sorted(glob.glob(os.path.join(LISTS_DIR, "*.csv")))
    if not files:
        json.dump({"generated": datetime.datetime.utcnow().isoformat() + "Z", "today": None, "rows": []},
                  open(OUT, "w"), indent=2)
        print("No list files found in data/lists/. Wrote empty data.json.")
        return

    seen = {}          # name -> {dates:set, latest:rec, latest_date:str}
    all_dates = []
    for path in files:
        date, rows = parse_file(path)
        if not date:
            print("Skipping (no YYYY-MM-DD in filename):", path)
            continue
        all_dates.append(date)
        for rec in rows:
            nm = rec["name"]
            e = seen.setdefault(nm, {"dates": set(), "latest": None, "latest_date": None})
            e["dates"].add(date)
            if e["latest_date"] is None or date >= e["latest_date"]:
                e["latest"], e["latest_date"] = rec, date

    if not all_dates:
        print("No dated files parsed.")
        return
    today = max(all_dates)

    symbols = load_symbols()
    dropped = [nm for nm, e in seen.items() if e["latest_date"] < today]
    follow = follow_up(dropped, symbols) if dropped else {}

    out_rows = []
    for nm, e in seen.items():
        rec = dict(e["latest"])
        cnt = len(e["dates"])
        first, last = min(e["dates"]), max(e["dates"])
        if last < today:
            status = "dropped"
        elif first == today:
            status = "new"
        elif cnt >= 3:
            status = "persistent"
        else:
            status = "current"
        rec.update({"_daysOnList": cnt, "_firstSeen": first, "_lastSeen": last, "_status": status})
        if nm in follow:
            rec["_followPrice"] = round(follow[nm], 2)
            if rec.get("cmp"):
                rec["_sinceLast"] = round((follow[nm] / rec["cmp"] - 1) * 100, 1)
        out_rows.append(rec)

    json.dump({"generated": datetime.datetime.utcnow().isoformat() + "Z",
               "today": today, "rows": out_rows}, open(OUT, "w"), indent=2)
    print(f"Wrote {len(out_rows)} tracked stocks (today={today}) -> {OUT}")


if __name__ == "__main__":
    main()
