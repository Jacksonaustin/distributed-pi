"""Shared event log for all three voters (same idea as Lab 4's log_event).

Events to record: ELECTION_STARTED, VOTE_GRANTED, VOTE_DENIED, VOTE_RECEIVED,
BECAME_LEADER, STEPPED_DOWN, LEADER_CHANGED, REJECTED_OLD_TERM, QUORUM_LOST, ...
Include the term in every entry - the report asks for it.
"""


class EventLog:
    def __init__(self, path):
        """TODO: store the path, keep an in-memory list of entries, and a lock."""
        raise NotImplementedError

    def log(self, event_type, term, details):
        """TODO: build {time, event, term, details}, append, print, write a line to the file."""
        raise NotImplementedError

    def recent(self, n=20):
        """TODO: return the last n entries (for /status and the dashboard)."""
        raise NotImplementedError
