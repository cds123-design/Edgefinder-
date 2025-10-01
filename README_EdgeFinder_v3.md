
# EdgeFinder v3 (All Sports + Search + Manual Refresh + Color Highlighting)

This Streamlit app aggregates **NBA, NFL, MLB, NHL, and major Soccer leagues**,
pulls **moneyline decimal odds** (DraftKings & FanDuel) from **The Odds API**, and
computes a simple model vs implied probability to show **Edge %**.

## Features
- Today + Tomorrow fixtures (UTC)
- Decimal odds only
- Combined multi-sport dashboard
- Search bar to filter by team
- Manual refresh (run button)
- Color highlighting (green ≥ threshold, red for negative edge)
- Sidebar controls: API key, home advantage nudge, roster delta, edge threshold

## Run locally
```bash
pip install streamlit requests pandas
streamlit run edgefinder_streamlit.py
```

## Deploy (Streamlit Cloud)
1. Upload `edgefinder_streamlit.py` to your GitHub repo
2. Create app in Streamlit Cloud:
   - Repository: your_user/your_repo
   - Branch: main
   - File path: edgefinder_streamlit.py
3. Open the app, adjust the sidebar settings, press **Run Model**.
