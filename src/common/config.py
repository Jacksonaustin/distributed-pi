"""Cluster configuration: which cluster file to use, and the timing constants.

The members live in a cluster file (JSON), not in code. It is the starting
member list; members can also join and leave at runtime (common/membership.py),
and each node rewrites its copy of the file when the list changes.
Pick the file with the CLUSTER env var:

    CLUSTER=cluster.local.json   -> everything on the laptop (localhost ports)
    (unset)                      -> cluster.json, the real Pis + laptop witness

Relative paths are resolved against src/, so it works from any folder.
"""
import os

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve(path):
    return path if os.path.isabs(path) else os.path.join(SRC_DIR, path)


# The member list itself is read and kept up to date by common/membership.py,
# because members can join and leave while the cluster runs.
CLUSTER_FILE = _resolve(os.environ.get("CLUSTER", "cluster.json"))

# --- Timing (seconds) ---
HEARTBEAT_INTERVAL = 1.0                 # leader sends heartbeats this often
QUORUM_WARNING = 2.0                     # leader: too few acks this long -> "lost quorum" indicator
QUORUM_TIMEOUT = 5.0                     # leader: too few acks this long -> step down (lab requirement)
REQUEST_TIMEOUT = 0.5                    # HTTP timeout for every peer request
TICK_INTERVAL = 0.1                      # how often the tick loop checks timers

# Safety requirement: only one authorized leader at a time. A new leader needs a
# vote from a voter that has not heard the old leader for ELECTION_TIMEOUT_MIN
# (see LEADER_LEASE in election.py). The old leader's newest ack is then at least
# ELECTION_TIMEOUT_MIN - REQUEST_TIMEOUT old, so it has already stepped down after
# QUORUM_TIMEOUT. That only holds if MIN > QUORUM_TIMEOUT + REQUEST_TIMEOUT + TICK_INTERVAL.
ELECTION_TIMEOUT_MIN = 6.0               # follower waits a random time in [min, max]
ELECTION_TIMEOUT_MAX = 9.0               #   before starting an election
assert ELECTION_TIMEOUT_MIN > QUORUM_TIMEOUT + REQUEST_TIMEOUT + TICK_INTERVAL

STATE_DIR = _resolve(os.environ.get("STATE_DIR", "state"))   # where <node>.json is persisted
LOG_DIR = _resolve(os.environ.get("LOG_DIR", "logs"))        # where <node>_events.log goes

