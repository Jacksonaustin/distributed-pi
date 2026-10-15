"""Lab 5 cluster configuration: who the voters are, and the timing constants.

URLs come from environment variables so the same code runs on the laptop
(all localhost, different ports) and on the real Pis (.local hostnames / IPs).
These are BASE urls - append "/heartbeat" or "/request-vote" when sending.
"""
import os

VOTERS = {
    "pi-a": os.environ.get("PI_A_URL", "http://pi-a.local:5001"),
    "pi-b": os.environ.get("PI_B_URL", "http://pi-b.local:5002"),
    # TODO: on the Pis, set WITNESS_URL to your laptop's IP, e.g. http://192.168.1.50:5003
    "witness": os.environ.get("WITNESS_URL", "http://localhost:5003"),
}

MAJORITY = len(VOTERS) // 2 + 1          # 3 voters -> 2

# --- Timing (seconds) ---
HEARTBEAT_INTERVAL = 1.0                 # leader sends heartbeats this often
ELECTION_TIMEOUT_MIN = 3.0               # follower waits a random time in [min, max]
ELECTION_TIMEOUT_MAX = 6.0               #   before starting an election
QUORUM_WARNING = 2.0                     # leader: no ack this long -> "lost quorum" indicator
QUORUM_TIMEOUT = 5.0                     # leader: no ack this long -> step down (lab requirement)
REQUEST_TIMEOUT = 0.5                    # HTTP timeout for every peer request
TICK_INTERVAL = 0.1                      # how often the tick loop checks timers

STATE_DIR = os.environ.get("STATE_DIR", "state")   # where <node>.json is persisted


def peers_of(name):
    """Return {peer_name: base_url} for every voter except `name`."""
    # TODO
    raise NotImplementedError
