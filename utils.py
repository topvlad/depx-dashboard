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
