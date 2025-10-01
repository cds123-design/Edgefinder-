
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# ==============================
# EdgeFinder v4.3 — Pro Model vs Market (Light Mode, DK-only)
# ==============================

API_KEY = "0ad4039785b38ae45104ee6eba0e90e4"
BASE = "https://api.the-odds-api.com/v4/sports"
BOOKMAKER = "draftkings"
MARKET = "h2h"
REGIONS = "us"
ODDS_FORMAT = "decimal"

# Sports map: Label -> Odds API key
SPORTS = {
    "⚽ Soccer - EPL": "soccer_epl",
    "⚽ Soccer - La Liga": "soccer_spain_la_liga",
    "⚽ Soccer - Serie A": "soccer_italy_serie_a",
    "⚽ Soccer - Bundesliga": "soccer_germany_bundesliga",
    "⚽ Soccer - Ligue 1": "soccer_france_ligue_one",
    "⚽ Soccer - UCL": "soccer_uefa_champs_league",
    "⚽ Soccer - UEL": "soccer_uefa_europa_league",
    "🏀 NBA": "basketball_nba",
    "🏈 NFL": "americanfootball_nfl",
    "🏒 NHL": "icehockey_nhl",
    "⚾ MLB": "baseball_mlb",
    "🏀 EuroLeague": "basketball_euroleague",
    "🏀 EuroCup": "basketball_eurocup",
    "🏀 Spain ACB": "basketball_spain_liga_acb",
    "🏀 Italy Lega A": "basketball_italy_lega_a",
    "🏀 Germany BBL": "basketball_germany_bbl",
    "🏀 France LNB": "basketball_france_lnb",
    "🏓 TT Elite Series": "table-tennis_tt-elite-series",
}

SOCCER_PREFIX = "soccer_"  # for 3-way (draw) handling

# ---------------- UI ----------------
st.set_page_config(page_title="EdgeFinder v4.3 — Pro Model vs Market", layout="wide")
st.title("🎯 EdgeFinder v4.3 — Pro Model vs Market (DK-only)")
st.caption("One row per game • DraftKings odds • Market vs Model favorites • Value Pick • Color-coded Play/Pass")

with st.sidebar:
    st.subheader("Filters & Threshold")
    leagues = st.multiselect("Leagues to include", list(SPORTS.keys()), default=list(SPORTS.keys()))
    min_edge = st.slider("Play threshold (Edge % ≥)", 1.0, 10.0, 5.0, 0.5)
    search = st.text_input("Search teams/league/matchup", "")
    st.markdown("---")
    with st.expander("ℹ️ How to Read This Table", True):
        st.write("""
- **Market Fav (DK):** Team implied as favorite by DraftKings (lowest odds).
- **Model Fav:** Team projected as favorite by the model (highest model win %).
- **Pick (Team + Odds):** Side with the greatest value edge — where Model % > Market % (may differ from favorites).
- **Market % (Fav):** Book-implied win probability for the market favorite (1 ÷ DK odds), normalized.
- **Model % (Fav):** Model-calculated win probability for the model's favorite (Fav/Opp shown; Draw appears for soccer only).
- **Edge % (Pick):** Model % (Pick) − Implied % (Pick).
- **Recommendation:** 🟩 Play if Edge ≥ threshold (default 5%). 🟥 Pass if below.
        """)
    run = st.button("Run Model")

def fetch_odds_board(sport_key: str):
    url = f"{BASE}/{sport_key}/odds"
    params = dict(
        apiKey=API_KEY,
        regions=REGIONS,
        markets=MARKET,
        bookmakers=BOOKMAKER,
        oddsFormat=ODDS_FORMAT,
        dateFormat="iso"
    )
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def normalize_probs(prob_map):
    total = sum(prob_map.values())
    if total <= 0:
        return prob_map
    return {k: v/total for k, v in prob_map.items()}

def implied_from_decimal(d):
    try:
        d = float(d)
        if d <= 0: 
            return 0.0
        return 1.0 / d
    except Exception:
        return 0.0

def compute_model_probs(implied_probs: dict, is_soccer: bool, home_key="home", away_key="away", draw_key="draw"):
    """
    Auto-calc model probabilities from implied, with a small, sensible home advantage nudge.
    Then renormalize to 100%.
    """
    probs = implied_probs.copy()
    # Base normalization (remove vig)
    probs = normalize_probs(probs)

    # Apply a modest home advantage nudge (soccer smaller than other sports)
    home_nudge = 0.03 if is_soccer else 0.04
    if home_key in probs and away_key in probs:
        probs[home_key] = max(0.0, probs[home_key] + home_nudge)
        probs[away_key] = max(0.0, probs[away_key] - home_nudge)

    # Renormalize after nudge
    probs = normalize_probs(probs)
    return probs

def within_today_tomorrow(commence_iso: str, tz=timezone.utc):
    try:
        t = datetime.fromisoformat(commence_iso.replace("Z","+00:00")).astimezone(tz)
    except Exception:
        return False, None
    now = datetime.now(tz)
    end = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (now <= t < end), t

def build_row(league_label, game, is_soccer, min_edge):
    home = game.get("home_team", "")
    away = game.get("away_team", "")
    ok, start_dt = within_today_tomorrow(game.get("commence_time",""))
    if not ok:
        return None

    # Extract DraftKings H2H prices
    dk = next((b for b in game.get("bookmakers", []) if b.get("key") == BOOKMAKER), None)
    if not dk:
        return None
    market = next((m for m in dk.get("markets", []) if m.get("key") == "h2h"), None)
    if not market:
        return None

    prices = { "home": None, "away": None, "draw": None }
    for o in market.get("outcomes", []):
        name = (o.get("name") or "").strip()
        price = o.get("price")
        if name.lower() == (home or "").lower():
            prices["home"] = float(price)
        elif name.lower() == (away or "").lower():
            prices["away"] = float(price)
        elif name.lower() == "draw":
            prices["draw"] = float(price)

    # Must have home & away. Draw optional (soccer only).
    if prices["home"] is None or prices["away"] is None:
        return None
    if not is_soccer:
        prices.pop("draw", None)

    # Implied (remove vig via normalization)
    implied = {k: implied_from_decimal(v) for k, v in prices.items() if v}
    implied = normalize_probs(implied)

    # Model probabilities (auto from implied + home nudge)
    model = compute_model_probs(implied, is_soccer)

    # Market favorite = lowest DK odds (among available)
    market_fav_key = min(prices, key=lambda k: prices[k] if prices[k] else 1e9)
    market_fav_team = home if market_fav_key == "home" else (away if market_fav_key == "away" else "Draw")

    # Model favorite = higher of home/away only
    model_fav_key = "home" if model.get("home", 0) >= model.get("away", 0) else "away"
    model_fav_team = home if model_fav_key == "home" else away

    # Pick = outcome (home/away/draw*) with max edge = model - implied
    edges = {}
    for k in implied.keys():
        edges[k] = (model.get(k, 0) - implied.get(k, 0)) * 100.0

    pick_key = max(edges, key=lambda k: edges[k])
    pick_team = {"home": home, "away": away, "draw": "Draw"}[pick_key]
    pick_odds = prices[pick_key]
    pick_implied_pct = implied[pick_key] * 100.0
    pick_model_pct = model[pick_key] * 100.0
    pick_edge = round(pick_model_pct - pick_implied_pct, 2)

    row = {
        "League": league_label,
        "Matchup": f"{home} vs {away}",
        "Market Fav (DK)": market_fav_team,
        "Model Fav": model_fav_team,
        "Pick (Team + Odds)": f"{pick_team} ({pick_odds:.2f})",
        "Market % (Fav)": round(implied["home"]*100.0 if market_fav_key=="home" else (implied["away"]*100.0 if market_fav_key=="away" else implied.get("draw",0)*100.0), 1),
        "Model % (Fav)": round(model[model_fav_key]*100.0, 1),
        "Model % (Opp)": round((model["away"] if model_fav_key=="home" else model["home"])*100.0, 1),
        "Model % (Draw)": round(model.get("draw", 0.0)*100.0, 1) if is_soccer else None,
        "Implied % (Pick)": round(pick_implied_pct, 1),
        "Edge % (Pick)": pick_edge,
        "Recommendation": "Play" if pick_edge >= min_edge else "Pass",
        "Start (UTC)": start_dt.strftime("%Y-%m-%d %H:%M")
    }
    return row

if run:
    results = []
    for label in leagues:
        key = SPORTS[label]
        is_soccer = key.startswith(SOCCER_PREFIX)
        try:
            board = fetch_odds_board(key)
        except Exception:
            continue
        for g in board:
            row = build_row(label, g, is_soccer, min_edge)
            if row is None:
                continue
            # Search filter (match against matchup, pick, favored, league label)
            blob = " ".join([
                row["League"], row["Matchup"], row["Market Fav (DK)"], row["Model Fav"], row["Pick (Team + Odds)"]
            ]).lower()
            if search.strip() and (search.strip().lower() not in blob):
                continue
            results.append(row)

    if not results:
        st.info("No eligible games found (or odds not posted yet) for the selected leagues/time window.")
    else:
        df = pd.DataFrame(results)
        # Sort by Edge desc
        df = df.sort_values(by=["Edge % (Pick)", "Model % (Fav)"], ascending=[False, False]).reset_index(drop=True)

        # Hide Draw column if all values are None
        if "Model % (Draw)" in df.columns and df["Model % (Draw)"].isna().all():
            df = df.drop(columns=["Model % (Draw)"])

        # Color styling
        def style_rec(val):
            return "background-color:#e8ffe8; color:#0a4; font-weight:bold;" if val=="Play" else "background-color:#ffecec; color:#a00; font-weight:bold;"

        def style_edge(val):
            try:
                v = float(val)
            except:
                return ""
            if v >= min_edge:
                return "background-color:#e8ffe8;"
            if v < 0:
                return "background-color:#ffecec;"
            return ""

        styled = df.style.applymap(style_edge, subset=["Edge % (Pick)"])\
                         .applymap(style_rec, subset=["Recommendation"])

        st.dataframe(styled, use_container_width=True, height=700)

else:
    st.info("Set your leagues and threshold, then press **Run Model** to fetch DraftKings lines and compute edges.")
