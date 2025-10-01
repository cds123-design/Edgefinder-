
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import math

# ==============================
# EdgeFinder v3.1 — Multi-Sport (Manual Refresh)
# ==============================

API_KEY_DEFAULT = "0ad4039785b38ae45104ee6eba0e90e4"  # editable in sidebar
BASE = "https://api.the-odds-api.com/v4/sports"
REGIONS = "us"
ODDS_FORMAT = "decimal"
BOOKMAKERS = "draftkings,fan_duel"
MARKETS = "h2h"  # moneyline only

# --- Sport keys (some may not always be available; we skip gracefully) ---
SPORTS = {
    # Core US leagues
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

    # European basketball
    "🏀 EuroLeague": "basketball_euroleague",
    "🏀 Spain ACB": "basketball_spain_liga_acb",
    "🏀 Italy Lega A": "basketball_italy_lega_a",
    "🏀 Germany BBL": "basketball_germany_bbl",
    "🏀 France LNB": "basketball_france_lnb",
    "🏀 EuroCup": "basketball_eurocup",

    # Latin American basketball (best-effort keys; skipped if not supported)
    "🏀 Argentina Liga Nacional": "basketball_argentina_liga_nacional",
    "🏀 Brazil NBB": "basketball_brazil_nbb",

    # World / FIBA-level basketball (best-effort keys)
    "🏀 FIBA World": "basketball_fiba_world",
}

def implied_from_decimal(d: float) -> float:
    return 1.0/float(d) if d and float(d) > 0 else 0.0

def logistic(x: float) -> float:
    return 1.0/(1.0+math.exp(-x))

def compute_model_probs(is_soccer: bool=False, home_adv: float=0.10, roster_delta: float=0.0):
    \"\"\"Neutral baseline model:
    - Starts near 50/50
    - Home advantage nudge (slider)
    - Manual roster delta (slider) favors home side if >0
    - Soccer: small fixed draw prob (10%), remaining split
    \"\"\"
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
    url = f\"{BASE}/{sport_key}/odds\"
    params = dict(
        apiKey=api_key, regions=REGIONS, markets=MARKETS,
        bookmakers=BOOKMAKERS, oddsFormat=ODDS_FORMAT, dateFormat=\"iso\"
    )
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

# ---------------- UI ----------------
st.set_page_config(page_title=\"EdgeFinder v3.1 — Multi-Sport\", page_icon=\"🎯\", layout=\"wide\")
st.title(\"🎯 EdgeFinder v3.1 — Multi-Sport (Decimal)\")
st.caption(\"Today + Tomorrow • DK/FD Moneyline • Manual refresh • Filters • Color-coded edges\")

with st.sidebar:
    api_key = st.text_input(\"The Odds API Key\", value=API_KEY_DEFAULT, type=\"password\")
    # Filters
    sport_filter = st.multiselect(\"Filter by leagues\", list(SPORTS.keys()), default=list(SPORTS.keys()))
    positive_only = st.checkbox(\"Show only positive edges\", value=False)
    # Model knobs
    home_adv = st.slider(\"Home advantage nudge\", 0.00, 0.20, 0.10, 0.01)
    roster_delta = st.slider(\"Roster Δ (favor HOME)\", -0.30, 0.30, 0.00, 0.01)
    edge_thresh = st.slider(\"Highlight edge ≥ (%)\", 0.0, 20.0, 5.0, 0.5)
    run = st.button(\"Run Model\")

search_query = st.text_input(\"🔎 Search team\", \"\", help=\"Filter rows by Home/Away team name (partial match ok)\")

if run:
    if not api_key:
        st.error(\"Please paste your The Odds API key in the sidebar.\")
        st.stop()

    tz = timezone.utc
    combined = []

    # Iterate selected leagues only
    for sport_label in sport_filter:
        sport_key = SPORTS.get(sport_label)
        if not sport_key:
            continue
        # Fetch odds; skip league if API returns 4xx/5xx
        try:
            board = fetch_odds_board(sport_key, api_key)
        except Exception:
            continue

        for g in board:
            ok, t = within_today_tomorrow(g.get(\"commence_time\",\"\"), tz)
            if not ok:
                continue

            home = g.get(\"home_team\",\"\");
            away = g.get(\"away_team\",\"\");
            is_soccer = sport_key.startswith(\"soccer_\")

            p_home, p_draw, p_away = compute_model_probs(
                is_soccer=is_soccer, home_adv=home_adv, roster_delta=roster_delta
            )

            outs = outcome_rows_for_game(g)
            if not outs:
                continue

            def is_team(name, target):
                if not (name and target):
                    return False
                n = name.lower(); tname = target.lower()
                return tname in n or n in tname

            for o in outs:
                if is_team(o[\"team_name\"], home):
                    model_p = p_home; side = \"Home\"
                elif is_team(o[\"team_name\"], away):
                    model_p = p_away; side = \"Away\"
                elif o[\"team_name\"].strip().lower() == \"draw\":
                    model_p = p_draw; side = \"Draw\"
                else:
                    continue

                implied_p = implied_from_decimal(o[\"decimal\"])
                edge = (model_p - implied_p) * 100.0

                combined.append({
                    \"League\": sport_label,
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
        st.info(\"No fixtures found for the selected leagues today/tomorrow with posted ML odds.\")
        st.stop()

    df = pd.DataFrame(combined)

    # Search filter
    if search_query.strip():
        q = search_query.strip().lower()
        df = df[ df[\"Home\"].str.lower().str.contains(q) | df[\"Away\"].str.lower().str.contains(q) ]

    # Positive-only filter
    if positive_only:
        df = df[ df[\"Edge %\"] > 0 ]

    if df.empty:
        st.info(\"No rows after filters. Try broadening your search or toggles.\")
        st.stop()

    # Auto-sort by highest edge first; tie-breaker: Model %
    df = df.sort_values(by=[\"Edge %\",\"Model %\"], ascending=[False, False]).reset_index(drop=True)

    # Color coding for Edge column
    def color_edge(val):
        try:
            v = float(val)
        except:
            return \"\"
        if v >= edge_thresh:
            return \"background-color:#e8ffe8\"    # green
        if v < 0:
            return \"background-color:#ffecec\"    # red
        return \"background-color:#f6f6f6\"        # light grey for near zero

    styled = df[[\"League\",\"Start (UTC)\",\"Home\",\"Away\",\"Side\",\"Book\",\"Decimal\",\"Model %\",\"Implied %\",\"Edge %\"]].style.applymap(color_edge, subset=[\"Edge %\"])
    st.dataframe(styled, use_container_width=True)

    st.caption(\"Model: neutral baseline + home/roster nudges (soccer includes small draw). Some leagues may be unavailable at times; they are skipped gracefully.\")
else:
    st.info(\"Set your key, filters and sliders in the sidebar, then press **Run Model**.\")
