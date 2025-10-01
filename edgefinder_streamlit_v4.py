
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import math

# ==============================
# EdgeFinder v4 — Best Edge + Play/Pass (Manual Refresh)
# ==============================

API_KEY_DEFAULT = "0ad4039785b38ae45104ee6eba0e90e4"  # editable in sidebar
BASE = "https://api.the-odds-api.com/v4/sports"
REGIONS = "us"
ODDS_FORMAT = "decimal"
BOOKMAKERS = "draftkings,fan_duel"
MARKETS = "h2h"  # moneyline only

SPORTS = {
    "🏀 NBA": "basketball_nba",
    "🏈 NFL": "americanfootball_nfl",
    "⚾ MLB": "baseball_mlb",
    "🏒 NHL": "icehockey_nhl",
    # Soccer majors
    "⚽ EPL": "soccer_epl",
    "⚽ La Liga": "soccer_spain_la_liga",
    "⚽ Serie A": "soccer_italy_serie_a",
    "⚽ Bundesliga": "soccer_germany_bundesliga",
    "⚽ Ligue 1": "soccer_france_ligue_one",
    "⚽ UCL": "soccer_uefa_champs_league",
    "⚽ UEL": "soccer_uefa_europa_league",
    "⚽ UECL": "soccer_uefa_europa_conference_league",
    # Euro / World hoops
    "🏀 EuroLeague": "basketball_euroleague",
    "🏀 EuroCup": "basketball_eurocup",
    "🏀 Spain ACB": "basketball_spain_liga_acb",
    "🏀 Italy Lega A": "basketball_italy_lega_a",
    "🏀 Germany BBL": "basketball_germany_bbl",
    "🏀 France LNB": "basketball_france_lnb",
    # Latin America (best effort)
    "🏀 Argentina Liga Nacional": "basketball_argentina_liga_nacional",
    "🏀 Brazil NBB": "basketball_brazil_nbb",
}

def implied_from_decimal(d: float) -> float:
    return 1.0/float(d) if d and float(d) > 0 else 0.0

def logistic(x: float) -> float:
    return 1.0/(1.0+math.exp(-x))

def compute_model_probs(is_soccer: bool=False, home_adv: float=0.10, roster_delta: float=0.0):
    """
    Neutral baseline model with home/roster nudges.
    Soccer includes small draw probability.
    """
    raw = home_adv + roster_delta
    p_home = logistic(raw * 2.0)
    p_away = 1.0 - p_home
    p_draw = 0.0
    if is_soccer:
        p_draw = 0.10
        p_home *= 0.90
        p_away *= 0.90
    return p_home, p_draw, p_away

def fetch_odds_board(sport_key: str, api_key: str):
    url = f"{BASE}/{sport_key}/odds"
    params = dict(
        apiKey=api_key, regions=REGIONS, markets=MARKETS,
        bookmakers=BOOKMAKERS, oddsFormat=ODDS_FORMAT, dateFormat="iso"
    )
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def within_today_tomorrow(commence_iso: str, tz=timezone.utc):
    try:
        t = datetime.fromisoformat(commence_iso.replace("Z","+00:00")).astimezone(tz)
    except Exception:
        return False, None
    now = datetime.now(tz)
    end = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (now <= t < end), t

def extract_prices(game):
    rows = []
    for bm in game.get("bookmakers", []):
        book = bm.get("key","").replace("_"," ").title()
        if book == "Fan Duel": book = "FanDuel"
        for mk in bm.get("markets", []):
            if mk.get("key") != "h2h": continue
            for o in mk.get("outcomes", []):
                name = o.get("name"); price = o.get("price")
                if name is None or price is None: continue
                rows.append({"book": book, "label": name, "decimal": float(price)})
    return rows

# ---------------- UI ----------------
st.set_page_config(page_title="EdgeFinder v4 — Best Edge", page_icon="🎯", layout="wide")
st.title("🎯 EdgeFinder v4 — Best Edge (Decimal)")
st.caption("Today + Tomorrow • DK/FD Moneyline • Manual refresh • Play/Pass recommendations")

with st.sidebar:
    api_key = st.text_input("The Odds API Key", value=API_KEY_DEFAULT, type="password")
    leagues = st.multiselect("Leagues", list(SPORTS.keys()), default=list(SPORTS.keys()))
    home_adv = st.slider("Home advantage nudge", 0.00, 0.20, 0.10, 0.01)
    roster_delta = st.slider("Roster Δ (favor HOME)", -0.30, 0.30, 0.00, 0.01)
    play_thresh = st.slider("Play threshold (Edge % ≥)", 0.0, 20.0, 5.0, 0.5)
    run = st.button("Run Model")

search = st.text_input("🔎 Filter by team (partial OK)", "")

if run:
    if not api_key:
        st.error("Please paste your The Odds API key in the sidebar.")
        st.stop()

    tz = timezone.utc
    results = []

    for league in leagues:
        key = SPORTS[league]
        try:
            board = fetch_odds_board(key, api_key)
        except Exception:
            continue

        for g in board:
            ok, t = within_today_tomorrow(g.get("commence_time",""), tz)
            if not ok: continue

            home = g.get("home_team",""); away = g.get("away_team","")
            is_soccer = key.startswith("soccer_")
            p_home, p_draw, p_away = compute_model_probs(is_soccer, home_adv, roster_delta)

            prices = extract_prices(g)
            if not prices: continue

            def is_team(name, target):
                n = (name or "").lower(); tname = (target or "").lower()
                return tname in n or n in tname

            candidates = []
            for p in prices:
                if is_team(p["label"], home):
                    model_p = p_home; pick = "Home"
                elif is_team(p["label"], away):
                    model_p = p_away; pick = "Away"
                elif p["label"].strip().lower() == "draw":
                    model_p = p_draw; pick = "Draw"
                else:
                    continue
                implied = 1.0/float(p["decimal"])
                edge = (model_p - implied) * 100.0
                candidates.append({
                    "pick": pick, "decimal": p["decimal"], "book": p["book"],
                    "model_pct": model_p*100.0, "implied_pct": implied*100.0, "edge_pct": edge
                })

            if not candidates: continue
            best = max(candidates, key=lambda x: x["edge_pct"])
            rec = "Play" if best["edge_pct"] >= play_thresh else "Pass"

            results.append({
                "League": league,
                "Start (UTC)": t.strftime("%Y-%m-%d %H:%M"),
                "Game": f"{away} @ {home}",
                "Pick": best["pick"],
                "Book": best["book"],
                "Decimal": round(best["decimal"], 3),
                "Model %": round(best["model_pct"], 2),
                "Implied %": round(best["implied_pct"], 2),
                "Best Edge %": round(best["edge_pct"], 2),
                "Recommendation": rec
            })

    if not results:
        st.info("No fixtures found or no odds available yet for the selected leagues.")
        st.stop()

    df = pd.DataFrame(results)

    if search.strip():
        q = search.strip().lower()
        df = df[ df["Game"].str.lower().str.contains(q) ]

    df = df.sort_values(by=["Best Edge %","Model %"], ascending=[False, False]).reset_index(drop=True)

    def style_rec(val):
        if val == "Play":
            return "background-color:#e8ffe8; color:#0a4; font-weight:bold;"
        return "background-color:#f2f2f2; color:#555;"

    def style_edge(val):
        try:
            v = float(val)
        except:
            return ""
        if v >= play_thresh:
            return "background-color:#e8ffe8;"
        if v < 0:
            return "background-color:#ffecec;"
        return ""

    styled = df[["League","Start (UTC)","Game","Pick","Book","Decimal","Model %","Implied %","Best Edge %","Recommendation"]]\
        .style.applymap(style_rec, subset=["Recommendation"])\
        .applymap(style_edge, subset=["Best Edge %"])

    st.dataframe(styled, use_container_width=True)
else:
    st.info("Set your key and sliders in the sidebar, then press **Run Model**.")
