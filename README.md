# depx-dashboard

This Streamlit dashboard visualizes cryptocurrency market data retrieved from the
`topvlad/market-pulse` repository on GitHub. It displays open interest, funding
rates, liquidations, OHLCV tables and GPT digests for several assets in an easy
web interface.

## Running locally

1. Install the Python requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Create `.streamlit/secrets.toml` and add your GitHub token so the app can
   fetch the remote data:
   ```toml
  GITHUB_TOKEN = "<your token>"
  ```
   You can also configure alert thresholds:
   ```toml
   [thresholds]
   liquidation_percentile = 95  # percentile for liquidation spikes
   funding_rate = 0.01          # funding rate alert level

   [asset_multipliers]
   BTCUSDT = 1.0                # per-asset multiplier for liquidation alerts
   ```
   All of these values can also be adjusted from the sidebar once the app is running.
3. Start the application:
   ```bash
   streamlit run app.py
   ```
   The dashboard will open in your browser at http://localhost:8501.


## Running tests

Install the development requirements and run the test suite:

```bash
pip install -r requirements-dev.txt
pytest
```
