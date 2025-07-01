import json
from unittest.mock import Mock, patch

import utils


def test_get_data_file_list():
    expected = [{"name": "file1.json"}, {"name": "file2.json"}]
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = expected
    with patch("utils.requests.get", return_value=mock_resp) as mock_get:
        result = utils.get_data_file_list(
            "user", "repo", "branch", "data", {"Authorization": "token"}
        )
        assert result == expected
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/user/repo/contents/data?ref=branch",
            headers={"Authorization": "token"},
        )
        mock_resp.raise_for_status.assert_called_once()


def test_fetch_json_from_url():
    data = {"a": 1}
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.text = json.dumps(data)
    with patch("utils.requests.get", return_value=mock_resp) as mock_get:
        result = utils.fetch_json_from_url(
            "https://example.com/data.json", {"Authorization": "token"}
        )
        assert result == data
        mock_get.assert_called_once_with(
            "https://example.com/data.json", headers={"Authorization": "token"}
        )
        mock_resp.raise_for_status.assert_called_once()
