
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import math

# ==============================
# EdgeFinder v3 — All Sports
# ==============================

API_KEY = "0ad4039785b38ae45104ee6eba0e90e4"  # you can change in the sidebar
BASE = "https://api.the-odds-api.com/v4/sports"
REGIONS = "us"
ODDS_FORMAT = "decimal"
BOOKMAKERS = "draftkings,fan_duel"
MARKETS = "h2h"  # moneyline

SPORTS = {
    "NBA": "basketball_nba",
    "NFL": "americanfootball_nfl",
    "MLB": "baseball_mlb",
    "NHL": "icehockey_nhl",
    "EPL": "soccer_epl",
    "UCL": "soccer_uefa_champs_league",
    "La Liga": "soccer_spain_la_liga",
    "Serie A": "soccer_italy_serie_a",
    "Bundesliga": "soccer_germany_bundesliga",
    "Ligue 1": "soccer_france_ligue_one",
    "UECL": "soccer_uefa_europa_conference_league",
    "UEL": "soccer_uefa_europa_league",
}

def implied_from_decimal(d: float) -> float:
    return 1.0 / float(d) if d and float(d) > 0 else 0.0

def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def compute_model_probs(is_soccer: bool=False, home_adv: float=0.10, roster_delta: float=0.0):
    # Neutral baseline with small home advantage + manual roster adjustment
    raw = home_adv + roster_delta  # positive favors HOME
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
    params = {
        "apiKey": api_key,
        "regions": REGIONS,
        "markets": MARKETS,
        "bookmakers": BOOKMAKERS,
        "oddsFormat": ODDS_FORMAT,
        "dateFormat": "iso",
    }
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def parse_time(commence_iso: str, tz=timezone.utc):
    try:
        return datetime.fromisoformat(commence_iso.replace("Z","+00:00")).astimezone(tz)
    except Exception:
        return None

def outcomes_for_game(game):
    rows = []
    for bm in game.get("bookmakers", []):
        book = bm.get("key","").replace("_"," ").title()
        if book == "Fan Duel":
            book = "FanDuel"
        for mk in bm.get("markets", []):
            if mk.get("key") != "h2h":
                continue
            for o in mk.get("outcomes", []):
                name = o.get("name"); price = o.get("price")
                if name is None or price is None:
                    continue
                rows.append({"book": book, "team": name, "decimal": float(price)})
    return rows

# ---------------- UI ----------------
st.set_page_config(page_title="EdgeFinder v3 — All Sports", page_icon="🎯", layout="wide")
st.title("🎯 EdgeFinder v3 — All Sports (Decimal)")
st.caption("Today + Tomorrow • The Odds API • Moneyline edges • Manual refresh • Search filter")

with st.sidebar:
    api_key = st.text_input("The Odds API Key", value=API_KEY, type="password")
    home_adv = st.slider("Home advantage nudge", 0.00, 0.20, 0.10, 0.01)
    roster_delta = st.slider("Roster Δ (favor HOME)", -0.30, 0.30, 0.00, 0.01)
    edge_thresh = st.slider("Highlight edge ≥ (%)", 0.0, 20.0, 5.0, 0.5)
    run = st.button("Run Model")

search_query = st.text_input("🔎 Filter by team name", "")

if run:
    if not api_key:
        st.error("Please paste your The Odds API key in the sidebar.")
        st.stop()

    tz = timezone.utc
    now = datetime.now(tz)
    end = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    master = []

    for sport_label, sport_key in SPORTS.items():
        try:
            board = fetch_odds_board(sport_key, api_key)
        except Exception:
            continue

        for g in board:
            t = parse_time(g.get("commence_time",""), tz)
            if t is None or not (now <= t < end):
                continue

            home = g.get("home_team","")
            away = g.get("away_team","")
            is_soccer = sport_key.startswith("soccer_")
            p_home, p_draw, p_away = compute_model_probs(is_soccer, home_adv, roster_delta)

            outs = outcomes_for_game(g)
            if not outs:
                continue

            def match(name, target):
                n = (name or "").lower()
                tname = (target or "").lower()
                return tname in n or n in tname

            for o in outs:
                if match(o["team"], home):
                    model_p = p_home; side = "Home"
                elif match(o["team"], away):
                    model_p = p_away; side = "Away"
                elif o["team"].strip().lower() == "draw":
                    model_p = p_draw; side = "Draw"
                else:
                    continue

                impl = implied_from_decimal(o["decimal"])
                edge = (model_p - impl) * 100.0

                master.append({
                    "Sport": sport_label,
                    "Start (UTC)": t.strftime("%Y-%m-%d %H:%M"),
                    "Home": home,
                    "Away": away,
                    "Side": side,
                    "Book": o["book"],
                    "Decimal": round(o["decimal"], 3),
                    "Model %": round(model_p*100.0, 2),
                    "Implied %": round(impl*100.0, 2),
                    "Edge %": round(edge, 2),
                })

    if not master:
        st.info("No fixtures found for today/tomorrow with posted ML odds.")
        st.stop()

    df = pd.DataFrame(master)

    if search_query.strip():
        q = search_query.strip().lower()
        df = df[
            df["Home"].str.lower().str.contains(q) |
            df["Away"].str.lower().str.contains(q)
        ]

    # Rank by Model % (as requested)
    df = df.sort_values(by=["Model %", "Edge %"], ascending=[False, False]).reset_index(drop=True)

    def color_edge(v):
        try:
            val = float(v)
        except Exception:
            return ""
        if val >= edge_thresh:
            return "background-color:#e8ffe8"
        if val < 0:
            return "background-color:#ffecec"
        return ""

    styled = df[["Sport","Start (UTC)","Home","Away","Side","Book","Decimal","Model %","Implied %","Edge %"]].style.applymap(color_edge, subset=["Edge %"])
    st.dataframe(styled, use_container_width=True)

else:
    st.info("Set your key & sliders in the sidebar, then press **Run Model**.")
