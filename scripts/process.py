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
    """Map a Screener column header to a canonical key.
    Handles BOTH Screener's long export names ("Return on equity",
    "Return over 1month", "Price to Earning") and the short on-screen
    names ("ROE %", "1mth return %", "P/E"). Order matters."""
    h = h.lower().strip()
    if not h:
        return None
    # identifiers
    if "name" in h: return "name"
    if "nse code" in h or "nse symbol" in h or (("symbol" in h or "ticker" in h) and "isin" not in h):
        return "symbol"
    if "bse code" in h or "isin" in h: return None
    if "industry" in h and "pe" not in h: return "industry"  # "Industry" / "Industry Group"
    # valuation — MUST come before the generic 'price' -> cmp rule
    if "peg" in h: return "peg"
    if "industry pe" in h or "ind pe" in h or "ind. pe" in h: return "indpe"
    if "price to earning" in h or "p/e" in h or h == "pe": return "pe"
    if "price to book" in h or "book value" in h or "cmp / bv" in h or "cmp/bv" in h or h.endswith("bv"):
        return "cmpbv"
    if "price to sales" in h: return None
    # price & size
    if "current price" in h or h == "cmp" or h.startswith("cmp "): return "cmp"
    if "market cap" in h or "mar cap" in h or "capitalization" in h: return "mcap"
    # volume (average first)
    if "vol" in h and ("1week" in h or "1 week" in h or "average" in h or "avg" in h): return "avgvol"
    if "volume" in h or h.startswith("vol"): return "vol"
    # returns — accept "Return over Xmonth", "Xmth return", "Xm%"
    if "1day" in h or "1 day" in h or (("return" in h or "%" in h) and "day" in h): return "r1d"
    if "1week" in h or "1 week" in h or "1wk" in h or (("return" in h or "%" in h) and "wk" in h): return "r1w"
    if "3month" in h or "3 month" in h or "3mth" in h or "3m%" in h: return "r3m"
    if "6month" in h or "6 month" in h or "6mth" in h or "6m%" in h: return "r6m"
    if "1month" in h or "1 month" in h or "1mth" in h or "1m%" in h: return "r1m"
    if "1year" in h or "1 year" in h or "1yr" in h or "1y%" in h or ("return" in h and "year" in h): return "r1y"
    # quality
    if "return on capital" in h or "roce" in h: return "roce"
    if "return on equity" in h or "roe" in h: return "roe"
    if "opm" in h or "operating margin" in h: return "opm"
    # growth
    if "quarterly sales" in h or "qtr sales" in h or ("yoy" in h and "sales" in h): return "qsales"
    if "sales" in h and ("3year" in h or "3 year" in h or "3yrs" in h): return "sales3"
    if "sales" in h and ("growth" in h or "var" in h): return "sales5"
    if "profit" in h and ("3year" in h or "3 year" in h or "3yrs" in h): return "profit3"
    if "profit" in h and ("growth" in h or "var" in h): return "profit5"
    # technical
    if "down from" in h or "down %" in h or h.startswith("down"): return "down"
    if "dma" in h and "200" in h: return "dma200"
    if "dma" in h and "50" in h: return "dma50"
    if "rsi" in h: return "rsi"
    if "piotroski" in h or "piotski" in h or "piot" in h: return "piotroski"
    if "debt to equity" in h or "debt / eq" in h or "debt" in h: return "debt"
    # ownership
    if "promoter" in h and ("change" in h or "chg" in h): return "promchg"
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
 
 
# ---------------------------------------------------------------------------
# Market context (global cues, sector leaders, news) + sector heat from list
# ---------------------------------------------------------------------------
GLOBAL_TICKERS = {"S&P 500": "^GSPC", "Dow": "^DJI", "Nasdaq": "^IXIC", "Nikkei": "^N225", "Hang Seng": "^HSI"}
COMMODITY_TICKERS = {"Brent": "BZ=F", "WTI": "CL=F"}
FOREX_TICKERS = {"USD/INR": "INR=X"}
VIX_TICKERS = {"India VIX": "^INDIAVIX"}
SECTOR_TICKERS = {"Nifty Bank": "^NSEBANK", "Nifty IT": "^CNXIT", "Nifty Auto": "^CNXAUTO",
                  "Nifty Pharma": "^CNXPHARMA", "Nifty FMCG": "^CNXFMCG", "Nifty Metal": "^CNXMETAL",
                  "Nifty Energy": "^CNXENERGY", "Nifty Realty": "^CNXREALTY"}
 
 
def _pct_change(tk):
    import yfinance as yf
    h = yf.Ticker(tk).history(period="7d")
    c = h["Close"].dropna()
    if len(c) >= 2:
        return round((c.iloc[-1] / c.iloc[-2] - 1) * 100, 2)
    return None
 
 
def _group_pct(d):
    out = []
    for name, tk in d.items():
        try:
            p = _pct_change(tk)
            if p is not None:
                out.append({"name": name, "pct": p})
        except Exception:
            pass
    return out
 
 
def fetch_news(n=5):
    """Best-effort market headlines from Google News RSS with a crude tone tag.
    Rough by design — meant as a headline glance, not a real sentiment score."""
    try:
        import urllib.request
        url = ("https://news.google.com/rss/search?q=nifty%20sensex%20indian%20stock%20market%20"
               "when:1d&hl=en-IN&gl=IN&ceid=IN:en")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        xml = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
        titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", xml) or re.findall(r"<title>(.*?)</title>", xml)
        titles = [t for t in titles if "Google News" not in t][:n]
        POS = ["rally", "surge", "gain", "jump", "high", "rise", "bull", "record", "soar", "climb", "boost", "recover", "up "]
        NEG = ["fall", "drop", "slump", "crash", "down", "bear", "loss", "plunge", "cut", "weak", "tumble", "sink", "decline", "sell-off", "selloff"]
        out = []
        for t in titles:
            tl = t.lower()
            p = sum(w in tl for w in POS)
            ng = sum(w in tl for w in NEG)
            out.append({"t": t, "tone": "pos" if p > ng else ("neg" if ng > p else "neu")})
        return out
    except Exception as ex:
        print("news fetch skipped:", ex)
        return []
 
 
def market_context():
    try:
        import yfinance  # noqa: F401
    except Exception as ex:
        print("yfinance unavailable for market context:", ex)
        return None
    ctx = {"generated": datetime.datetime.utcnow().isoformat() + "Z"}
    ctx["indices"] = _group_pct(GLOBAL_TICKERS)
    ctx["commodities"] = _group_pct(COMMODITY_TICKERS)
    ctx["forex"] = _group_pct(FOREX_TICKERS)
    ctx["vix"] = _group_pct(VIX_TICKERS)
    ctx["sectors"] = sorted(_group_pct(SECTOR_TICKERS), key=lambda x: -x["pct"])
    eq = [x["pct"] for x in ctx["indices"]]
    usdinr = next((x["pct"] for x in ctx["forex"] if x["name"] == "USD/INR"), 0) or 0
    score = (sum(eq) / len(eq) if eq else 0) - (usdinr * 0.5 if usdinr > 0 else 0)
    ctx["biasScore"] = round(score, 2)
    ctx["bias"] = "positive" if score > 0.25 else ("negative" if score < -0.25 else "mixed")
    ctx["news"] = fetch_news()
    return ctx
 
 
def sector_heat(rows):
    """Group today's stocks by Industry -> which sector is hot (count + avg 3-mth return)."""
    from collections import defaultdict
    agg = defaultdict(lambda: {"count": 0, "r3": []})
    for r in rows:
        ind = r.get("industry")
        if not ind:
            continue
        agg[ind]["count"] += 1
        if isinstance(r.get("r3m"), (int, float)):
            agg[ind]["r3"].append(r["r3m"])
    out = []
    for ind, a in agg.items():
        avg3 = round(sum(a["r3"]) / len(a["r3"]), 1) if a["r3"] else None
        out.append({"sector": ind, "count": a["count"], "avg3m": avg3})
    out.sort(key=lambda x: (-(x["avg3m"] if x["avg3m"] is not None else -999), -x["count"]))
    return out
 
 
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
 
    today_rows = [r for r in out_rows if r.get("_lastSeen") == today]
    heat = sector_heat(today_rows)
    market = market_context()
 
    json.dump({"generated": datetime.datetime.utcnow().isoformat() + "Z",
               "today": today, "rows": out_rows,
               "sectorHeat": heat, "market": market}, open(OUT, "w"), indent=2)
    print(f"Wrote {len(out_rows)} tracked stocks (today={today}) -> {OUT}")
    if market:
        print(f"Market bias: {market.get('bias')} ({market.get('biasScore')})")
 
 
if __name__ == "__main__":
    main()
 
