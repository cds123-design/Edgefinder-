
# EdgeFinder v3.1 — Multi-Sport (Manual Refresh)

**New**
- Color-coded edges (green = value, red = overpriced, grey = neutral)
- Auto-sort by highest Edge first
- Positive edge toggle
- League filter (multiselect)
- Search bar (team filter)

**Leagues covered**
NBA, NFL, MLB, NHL; Soccer: EPL, La Liga, Serie A, Bundesliga, Ligue 1, UCL, UEL, UECL;
European hoops (EuroLeague, EuroCup, ACB, Lega A, BBL, LNB);
Latin America hoops (Argentina, Brazil) and FIBA World (best-effort).

Some league keys may not be available on all plans/times; the app skips leagues that error out.

## Run locally
```bash
pip install streamlit requests pandas
streamlit run edgefinder_streamlit.py
```

## Deploy (Streamlit Cloud)
Repository: your_user/Edgefinder-
Branch: main
Main file path: edgefinder_streamlit.py
