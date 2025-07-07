import json
import requests


def fetch_json_from_url(url, timeout=None, headers=None, on_error=None):
    """Fetch JSON data from a URL with optional timeout and headers.

    If ``on_error`` is provided it will be called with any error message,
    otherwise the message is printed. An empty dict is returned on error.
    """
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        msg = f"Request failed: {exc}"
    except (json.JSONDecodeError, ValueError) as exc:
        msg = f"JSON decode failed: {exc}"
    if on_error:
        on_error(msg)
    else:
        print(msg)
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
