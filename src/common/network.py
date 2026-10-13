import requests

def send_heartbeat(url, message, timeout=0.5):
    """Returns (ok, error_name)."""
    try:
        r = requests.post(url, json=message, timeout=timeout)
        if r.status_code == 200:
            return True, None
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.RequestException as e:
        return False, type(e).__name__