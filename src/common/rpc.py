"""Talk to peers. post_json for heartbeats and vote requests, get_json for dashboards,
post_json_status when the caller needs the HTTP status too (join/leave forwarding)."""
import requests


def post_json(url, payload, timeout):
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except (requests.exceptions.RequestException, ValueError):
        return None


def post_json_status(url, payload, timeout):
    """Return (status_code, body dict). (None, None) if the peer didn't answer."""
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        try:
            body = r.json()
        except ValueError:
            body = {"error": r.text[:200]}
        return r.status_code, body
    except requests.exceptions.RequestException:
        return None, None


def get_json(url, timeout):
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except (requests.exceptions.RequestException, ValueError):
        return None
