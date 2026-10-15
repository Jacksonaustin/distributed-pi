"""Send JSON to a peer. Used for both heartbeats and vote requests."""
import requests


def post_json(url, payload, timeout):
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except (requests.exceptions.RequestException, ValueError):
        return None