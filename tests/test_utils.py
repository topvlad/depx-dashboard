import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import requests
from unittest.mock import Mock, patch

from utils import fetch_json_from_url


def test_fetch_json_success():
    mock_resp = Mock()
    mock_resp.json.return_value = {"foo": "bar"}
    mock_resp.raise_for_status.return_value = None
    with patch('requests.get', return_value=mock_resp) as mock_get:
        data = fetch_json_from_url('http://example.com')
        mock_get.assert_called_once_with('http://example.com', headers=None, timeout=None)
        mock_resp.json.assert_called_once()
        assert data == {"foo": "bar"}


def test_fetch_json_http_error():
    mock_resp = Mock()
    mock_resp.raise_for_status.side_effect = requests.HTTPError('boom')
    with patch('requests.get', return_value=mock_resp):
        on_err = Mock()
        data = fetch_json_from_url('http://bad', on_error=on_err)
        on_err.assert_called_once()
        assert 'Request failed' in on_err.call_args.args[0]
        assert data == {}
