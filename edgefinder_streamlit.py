
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import math

# ---------------------------
# CONFIG
# ---------------------------
API_KEY = "0ad4039785b38ae45104ee6eba0e90e4"  # prefilled; editable in sidebar
BASE = "https://api.the-odds-api.com/v4/sports"
REGIONS = "us"
ODDS_FORMAT = "decimal"
BOOKMAKERS = "draftkings,fan_duel"   # show both if available
MARKETS = "h2h"                      # moneyline only (spreads/totals later)

# Sports to aggregate
SPORTS = {
    "NBA": "basketball_nba",
    "NFL": "americanfootball_nfl",
    "MLB": "baseball_mlb",
    "NHL": "icehockey_nhl",
    # Major soccer comps
    "EPL": "soccer_epl",
    "UCL": "soccer_uefa_champs_league",
    "La Liga": "soccer_spain_la_liga",
    "Serie A": "soccer_italy_serie_a",
    "Bundesliga": "soccer_germany_bundesliga",
    "Ligue 1": "soccer_france_ligue_one",
    "UECL": "soccer_uefa_europa_conference_league",
    "UEL": "soccer_uefa_europa_league",
}

# ---------------------------
# UTILS / MODEL
# ---------------------------
def implied_from_decimal(d: float) -> float:
    return 1.0/float(d) if d and float(d) > 0 else 0.0

def logistic(x: float) -> float:
    return 1.0/(1.0+math.exp(-x))

def compute_model_probs(home_team: str, away_team: str, is_soccer: bool=False,
                        home_adv: float=0.10, roster_delta: float=0.0):
    \"\"\"
    Minimal, robust model (no /scores; avoids 422 issues):
      - Start 50/50
      - Home advantage nudge (default +10% via logistic scaling)
      - Optional roster delta slider (+/-) favoring HOME side
      - Soccer: allocate small draw prob (10%), renormalize
    \"\"\"
    raw = (home_adv) + roster_delta  # positive favors HOME team
    p_home = 1.0/(1.0+math.exp(-(raw*2.0)))
    p_away = 1.0 - p_home
    p_draw = 0.0
    if is_soccer:
        p_draw = 0.10
        p_home *= 0.90
        p_away *= 0.90
    return p_home, p_draw, p_away

def fetch_odds_board(sport_key: str, api_key: str):
    url = f\"{BASE}/{sport_key}/odds\"
    params = {
        \"apiKey\": api_key,
        \"regions\": REGIONS,
        \"markets\": MARKETS,
        \"bookmakers\": BOOKMAKERS,
        \"oddsFormat\": ODDS_FORMAT,
        \"dateFormat\": \"iso\"
    }
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def within_today_tomorrow(commence_iso: str, tz=timezone.utc):
    try:
        t = datetime.fromisoformat(commence_iso.replace(\"Z\",\"+00:00\")).astimezone(tz)
    except Exception:
        return False, None
    now = datetime.now(tz)
    end = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (now <= t < end), t

def outcome_rows_for_game(game):
    \"\"\"Extract DK/FD decimal prices for ML outcomes.\"\"\"
    rows = []
    for bm in game.get(\"bookmakers\", []):
        book = bm.get(\"key\",\"{}\").replace(\"_\",\" \").title()
        if book == \"Fan Duel\":
            book = \"FanDuel\"
        for mk in bm.get(\"markets\", []):
            if mk.get(\"key\") != \"h2h\":
                continue
            for o in mk.get(\"outcomes\", []):
                name = o.get(\"name\"); price = o.get(\"price\")
                if not (name and price):
                    continue
                rows.append({\"book\": book, \"team_name\": name, \"decimal\": float(price)})
    return rows

# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title=\"EdgeFinder v3 — All Sports\", page_icon=\"🎯\", layout=\"wide\")
st.title(\"🎯 EdgeFinder v3 — All Sports (Decimal)\")
st.caption(\"Today + Tomorrow • The Odds API • Moneyline edges • Manual refresh • Search filter\")

# Sidebar controls
with st.sidebar:
    api_key = st.text_input(\"The Odds API Key\", value=API_KEY, type=\"password\")
    home_adv = st.slider(\"Home advantage nudge\", 0.00, 0.20, 0.10, 0.01)
    roster_delta = st.slider(\"Roster Δ (favor HOME)\", -0.30, 0.30, 0.00, 0.01)
    edge_thresh = st.slider(\"Highlight edge ≥ (%)\", 0.0, 20.0, 5.0, 0.5)
    st.caption(\"Tip: Roster Δ is a manual adjustment when key injuries/suspensions exist.\")
    run = st.button(\"Run Model\")

# Search bar (applies after results)
search_query = st.text_input(\"🔎 Filter by team (e.g., 'Yankees', 'Arsenal', 'Lakers')\", value=\"\", help=\"Partial match allowed\")

if run:
    if not api_key:
        st.error(\"Please paste your The Odds API key in the sidebar.\")
        st.stop()

    tz = timezone.utc
    combined = []

    for sport_label, sport_key in SPORTS.items():
        try:
            board = fetch_odds_board(sport_key, api_key)
        except Exception:
            continue  # skip leagues that fail

        for g in board:
            ok, t = within_today_tomorrow(g.get(\"commence_time\",\"\"), tz)
            if not ok:
                continue

            home = g.get(\"home_team\")
            away = g.get(\"away_team\")
            is_soccer = sport_key.startswith(\"soccer_\")

            # Model probs (home/away perspective)
            p_home, p_draw, p_away = compute_model_probs(home, away, is_soccer=is_soccer,
                                                         home_adv=home_adv, roster_delta=roster_delta)

            # Collect bookmaker prices (DK/FD)
            outs = outcome_rows_for_game(g)
            if not outs:
                continue

            # Helper to map book outcomes to model sides by fuzzy containment
            def is_team(name, target):
                if not (name and target):
                    return False
                n = name.lower(); t = target.lower()
                return t in n or n in t

            for o in outs:
                if is_team(o[\"team_name\"], home):
                    model_p = p_home
                    side = \"Home\"
                elif is_team(o[\"team_name\"], away):
                    model_p = p_away
                    side = \"Away\"
                elif o[\"team_name\"].strip().lower() == \"draw\":
                    model_p = p_draw
                    side = \"Draw\"
                else:
                    continue

                implied_p = implied_from_decimal(o[\"decimal\"])
                edge = (model_p - implied_p) * 100.0

                combined.append({
                    \"Sport\": sport_label,
                    \"Start (UTC)\": t.strftime(\"%Y-%m-%d %H:%M\"),
                    \"Home\": home,
                    \"Away\": away,
                    \"Side\": side,
                    \"Book\": o[\"book\"],
                    \"Decimal\": round(o[\"decimal\"], 3),
                    \"Model %\": round(model_p*100.0, 2),
                    \"Implied %\": round(implied_p*100.0, 2),
                    \"Edge %\": round(edge, 2),
                })

    if not combined:
        st.info(\"No fixtures found for today/tomorrow with posted ML odds.\")
        st.stop()

    df = pd.DataFrame(combined)

    # Apply search filter
    if search_query.strip():
        q = search_query.strip().lower()
        mask = (
            df[\"Home\"].str.lower().str.contains(q) |
            df[\"Away\"].str.lower().str.contains(q)
        )
        df = df[mask]

    # Sort by edge desc
    df = df.sort_values(by=[\"Edge %\",\"Model %\"], ascending=[False, False])

    # Color highlighting: green if Edge ≥ threshold, red if Edge < 0
    def color_edges(val):
        try:
            v = float(val)
        except:
            return \"\"
        if v >= edge_thresh:
            return \"background-color: #e8ffe8\"  # light green
        if v < 0:
            return \"background-color: #ffecec\"  # light red
        return \"\"

    styled = df[[\"Sport\",\"Start (UTC)\",\"Home\",\"Away\",\"Side\",\"Book\",\"Decimal\",\"Model %\",\"Implied %\",\"Edge %\"]].style.applymap(color_edges, subset=[\"Edge %\"])

    st.dataframe(styled, use_container_width=True)

    st.caption(\"Note: Model is a neutral baseline with home/roster nudges (soccer includes small draw). Spreads/totals model coming next.\")
else:
    st.info(\"Set your key & sliders in the sidebar, then press **Run Model**.\")
