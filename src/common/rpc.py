"""Talk to peers. post_json for heartbeats and vote requests, get_json for dashboards."""
import requests


def post_json(url, payload, timeout):
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except (requests.exceptions.RequestException, ValueError):
        return None


def get_json(url, timeout):
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except (requests.exceptions.RequestException, ValueError):
        return None
