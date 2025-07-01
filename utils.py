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
