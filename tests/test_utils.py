diff --git a/tests/test_utils.py b/tests/test_utils.py
index 05f9cae0186ac004bf69ff0c18c4548bf91efe2c..7089e2f380ac5a84ecb92602c225cf653ddf17d1 100644
--- a/tests/test_utils.py
+++ b/tests/test_utils.py
@@ -1,25 +1,58 @@
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
-        data = fetch_json_from_url('http://example.com')
-        mock_get.assert_called_once_with('http://example.com', timeout=None)
+        headers = {"X-Test": "1"}
+        data = fetch_json_from_url('http://example.com', timeout=5, headers=headers)
+        mock_get.assert_called_once_with('http://example.com', headers=headers, timeout=5)
         mock_resp.json.assert_called_once()
         assert data == {"foo": "bar"}
 
 
 def test_fetch_json_http_error():
     mock_resp = Mock()
     mock_resp.raise_for_status.side_effect = requests.HTTPError('boom')
+    messages = []
+
     with patch('requests.get', return_value=mock_resp):
-        data = fetch_json_from_url('http://bad')
+        data = fetch_json_from_url('http://bad', on_error=messages.append)
         assert data == {}
+
+    assert messages and messages[0].startswith('Request failed:')
+
+
+def test_fetch_json_json_error():
+    mock_resp = Mock()
+    mock_resp.raise_for_status.return_value = None
+    mock_resp.json.side_effect = ValueError('invalid')
+    collected = []
+
+    with patch('requests.get', return_value=mock_resp):
+        data = fetch_json_from_url('http://bad-json', on_error=collected.append)
+        assert data == {}
+
+    assert collected and collected[0].startswith('JSON decode failed:')
+
+import pandas as pd
+from utils import parse_snapshot_timestamp, liquidation_threshold
+
+
+def test_parse_snapshot_timestamp():
+    ts = parse_snapshot_timestamp('20240102_1530')
+    assert ts == pd.Timestamp('2024-01-02 15:30')
+
+
+def test_liquidation_threshold():
+    data = [1, 2, 3, 4, 5]
+    expected = pd.Series(data, dtype=float).mean() + 3 * pd.Series(data, dtype=float).std()
+    thresh = liquidation_threshold(data)
+    assert thresh == expected
