"""Persist current_term and voted_for so a restart can't cause a double vote.

File format (state/<node>.json):  {"current_term": 3, "voted_for": "pi-a"}
"""


def load_state(path):
    """Return {"current_term": int, "voted_for": str | None}.

    TODO:
      - if the file doesn't exist, return term 0 and voted_for None
      - otherwise read and return the JSON
    """
    raise NotImplementedError


def save_state(path, current_term, voted_for):
    """Write term and vote to disk *atomically*.

    TODO:
      - make sure the folder exists (os.makedirs(..., exist_ok=True))
      - write JSON to a temp file next to `path` (e.g. path + ".tmp")
      - os.replace(tmp, path) so a crash never leaves a half-written file
    Call this BEFORE replying to anyone with the new term/vote.
    """
    raise NotImplementedError
