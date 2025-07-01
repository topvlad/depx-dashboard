import json
import requests

def get_data_file_list(user, repo, branch, data_dir, headers):
    api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{data_dir}?ref={branch}"
    r = requests.get(api_url, headers=headers)
    r.raise_for_status()
    return r.json()

def fetch_json_from_url(url, headers):
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return json.loads(r.text)
