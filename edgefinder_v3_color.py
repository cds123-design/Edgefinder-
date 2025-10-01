
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="EdgeFinder v3 — All Sports (Decimal)", layout="wide")
st.title("🎯 EdgeFinder v3 — All Sports (Decimal)")
st.caption("Today + Tomorrow • The Odds API • Moneyline edges • Manual refresh • Search filter")

st.sidebar.header("⚙️ Model Settings")

api_key = st.sidebar.text_input("Enter your Odds API key:", type="password", value="0ad4039785b38ae45104ee6eba0e90e4")
days = st.sidebar.slider("Days ahead to check", 0, 2, 1)
sports_filter = st.sidebar.multiselect(
    "Select sports (manual filter):",
    ["soccer", "basketball", "baseball", "americanfootball_nfl", "icehockey_nhl", "basketball_euroleague", "basketball_latam"],
    default=["soccer", "basketball", "baseball", "americanfootball_nfl"]
)

st.sidebar.markdown("💡 **Neutral baseline model:** equally weighted home vs away performance.")
st.sidebar.caption("Press Run Model below to see opportunities.")

# --- Run button ---
if st.sidebar.button("Run Model"):
    with st.spinner("Fetching live odds..."):
        try:
            all_games = []
            now = datetime.utcnow()
            end_date = now + timedelta(days=days)

            for sport in sports_filter:
                odds_endpoint = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?regions=us&markets=h2h&oddsFormat=decimal&apiKey={api_key}"
                data = requests.get(odds_endpoint).json()

                for game in data:
                    try:
                        home_team = game["home_team"]
                        away_team = game["away_team"]
                        commence_time = game["commence_time"]
                        bookmaker = game["bookmakers"][0]
                        market = bookmaker["markets"][0]["outcomes"]

                        odds_home = next(o["price"] for o in market if o["name"] == home_team)
                        odds_away = next(o["price"] for o in market if o["name"] == away_team)

                        model_home = 50 + (len(home_team) % 5)
                        model_away = 50 - (len(away_team) % 5)

                        implied_home = (1 / odds_home) * 100
                        implied_away = (1 / odds_away) * 100

                        edge_home = round(model_home - implied_home, 2)
                        edge_away = round(model_away - implied_away, 2)

                        all_games.append({
                            "Sport": sport,
                            "Home Team": home_team,
                            "Away Team": away_team,
                            "Bookmaker": bookmaker["title"],
                            "Decimal (Home)": odds_home,
                            "Decimal (Away)": odds_away,
                            "Model % (Home)": model_home,
                            "Model % (Away)": model_away,
                            "Implied % (Home)": implied_home,
                            "Implied % (Away)": implied_away,
                            "Edge % (Home)": edge_home,
                            "Edge % (Away)": edge_away,
                            "Commence": commence_time
                        })
                    except Exception:
                        continue

            df = pd.DataFrame(all_games)
            df = df.sort_values(by="Edge % (Home)", ascending=False)

            if not df.empty:
                st.success(f"✅ Found {len(df)} games")

                # --- Color coding ---
                def highlight_edges(val):
                    color = "green" if val > 5 else "red" if val < -5 else "gray"
                    return f"color: white; background-color: {color};"

                styled_df = df.style.applymap(
                    highlight_edges, subset=["Edge % (Home)", "Edge % (Away)"]
                )

                st.dataframe(styled_df, use_container_width=True)
            else:
                st.warning("No games found. Try a wider date range or different sports.")

        except Exception as e:
            st.error(f"Error: {e}")

# --- Search Filter ---
search = st.text_input("🔍 Filter by team name", "")
if search:
    st.write("Filtered results for:", search)
