
import streamlit as st
import requests, math
from dateutil import parser as dateparser
from datetime import datetime, timedelta

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

SPORT_KEYS = {
    "⚾ MLB": "baseball_mlb",
    "🏀 NBA": "basketball_nba",
    "🏀 EuroLeague": "basketball_euroleague",
    "🏀 EuroCup": "basketball_eurocup",
    "🏒 NHL": "icehockey_nhl",
    "⚽ UCL": "soccer_uefa_champs_league",
    "⚽ UEL": "soccer_uefa_europa_league",
    "⚽ UECL": "soccer_uefa_europa_conference_league",
    "⚽ EPL": "soccer_epl",
    "⚽ Serie A": "soccer_italy_serie_a",
    "⚽ La Liga": "soccer_spain_la_liga",
    "⚽ Ligue 1": "soccer_france_ligue_one",
    "⚽ Bundesliga": "soccer_germany_bundesliga",
}

def get_api_key():
    return st.session_state.get("api_key_input") or None

def fetch_odds(sport_key, api_key):
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds"
    params = {"apiKey": api_key, "regions": "us", "markets": "h2h", "bookmakers": "draftkings", "oddsFormat": "decimal"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_scores(sport_key, api_key):
    url = f"{ODDS_API_BASE}/sports/{sport_key}/scores"
    params = {"apiKey": api_key, "daysFrom": 365}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def normalize(name): return name.strip().lower() if name else ""
def logistic(x): return 1/(1+math.exp(-x))

def compute_model(teamA, teamB, scores, w_form):
    def team_games(team):
        return [g for g in scores if normalize(team) in (normalize(g.get('home_team')), normalize(g.get('away_team')))]
    def win_rate(team, games):
        wins, total = 0, 0
        for g in games[:5]:
            sc = g.get('scores') or []
            if len(sc) >= 2:
                s = {normalize(x['name']): float(x['score']) for x in sc if 'name' in x}
                home, away = normalize(g.get('home_team')), normalize(g.get('away_team'))
                if normalize(team) == home:
                    my, opp = s.get(home), s.get(away)
                else:
                    my, opp = s.get(away), s.get(home)
                if my is not None and opp is not None:
                    total += 1
                    if my > opp: wins += 1
        return wins/total if total>0 else 0.5

    Awr, Bwr = win_rate(teamA, team_games(teamA)), win_rate(teamB, team_games(teamB))
    raw = w_form * (Awr - Bwr)
    pA = logistic(raw * 2)
    return pA, 1-pA

def main():
    st.title("🎯 EdgeFinder")
    st.caption("Compare model vs DraftKings odds (via The Odds API)")

    with st.sidebar:
        api_key = st.text_input("The Odds API Key", type="password", key="api_key_input")
        sport = st.selectbox("Sport/League", list(SPORT_KEYS.keys()))
        w_form = st.slider("Recent Form Weight", 0.0, 1.0, 0.4, 0.01)
        edge_thresh = st.slider("Min Edge (%)", 0.0, 10.0, 2.0, 0.1)

    col1, col2 = st.columns(2)
    teamA = col1.text_input("Team A (Home)")
    teamB = col2.text_input("Team B (Away)")

    if st.button("Run Model"):
        if not api_key:
            st.error("Enter your The Odds API key in the sidebar.")
            return
        try:
            odds = fetch_odds(SPORT_KEYS[sport], api_key)
            scores = fetch_scores(SPORT_KEYS[sport], api_key)
        except Exception as e:
            st.error(str(e)); return
        pA, pB = compute_model(teamA, teamB, scores, w_form)
        st.write(f"**{teamA} win prob:** {pA*100:.2f}% (fair odds {1/pA:.2f})")
        st.write(f"**{teamB} win prob:** {pB*100:.2f}% (fair odds {1/pB:.2f})")
        st.info("Compare manually with DraftKings odds to check +EV value.")

if __name__ == "__main__":
    main()
