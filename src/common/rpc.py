"""Send JSON to a peer. Used for both heartbeats and vote requests."""


def post_json(url, payload, timeout):
    """POST payload to url. Return the response dict, or None on any failure.

    TODO:
      - requests.post(url, json=payload, timeout=timeout)
      - non-200 or any RequestException -> None
      - success -> r.json()
    Similar to Lab 4's send_heartbeat, but returns the reply body because
    the caller needs the peer's term and vote_granted / success.
    """
    raise NotImplementedError
