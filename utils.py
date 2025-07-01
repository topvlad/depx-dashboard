import json
import requests


def fetch_json_from_url(url, timeout=None):
    """Fetch JSON data from a URL.

    Returns an empty dict on error.
    """
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        print(f"Error fetching {url}: {exc}")
        return {}


def parse_snapshot_timestamp(snapshot):
    """Convert snapshot identifier like '20240501_1500' to a pandas Timestamp."""
    import pandas as pd
    return pd.to_datetime(snapshot, format="%Y%m%d_%H%M")


def liquidation_threshold(series):
    """Return alert threshold as mean + 3 * std for a numeric sequence."""
    import pandas as pd
    s = pd.Series(series, dtype=float)
    return s.mean() + 3 * s.std()
