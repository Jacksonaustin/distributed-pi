"""GET /metrics - this node's state in Prometheus text format.

Prometheus scrapes every member every few seconds. Scraping only reads a
snapshot of the node, so stopping Prometheus or Grafana never affects elections.

Written by hand (no extra package to install on the Pis). Format reference:
    # HELP <name> <text>
    # TYPE <name> gauge|counter
    <name>{label="value",...} <number>
Every series carries node="<name>". Prometheus adds job, instance and the
target labels (node, role) from monitoring/targets/*.json.
"""
import math

STATES = ("FOLLOWER", "CANDIDATE", "LEADER")
STATE_CODES = {"FOLLOWER": 0, "CANDIDATE": 1, "LEADER": 2}
VOTE_REFUSAL_REASONS = ("old_term", "leader_alive", "already_voted", "stale_member_list",
                        "not_voter", "invalid")
REJECTED_MESSAGE_EVENTS = {             # log event -> reason label
    "REJECTED_OLD_TERM": "old_term",
    "REJECTED_LEADER_ALIVE": "leader_alive",
    "REJECTED_INVALID": "invalid",
    "REJECTED_NOT_VOTER": "not_voter",
}
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def _labels(**labels):
    def esc(v):
        return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return "{" + ",".join(f'{k}="{esc(v)}"' for k, v in labels.items()) + "}"


def _num(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NaN"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return repr(round(value, 3))
    return str(value)


def render(snapshot):
    """Turn Node.metrics_snapshot() into the /metrics text."""
    s = snapshot["status"]
    events = snapshot["events"]
    node = s["node"]
    lines = []

    def metric(name, kind, help_text, samples):
        """samples: list of (extra_labels dict, value)."""
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {kind}")
        for extra, value in samples:
            lines.append(f"{name}{_labels(node=node, **extra)} {_num(value)}")

    # --- current state (gauges) ---
    metric("election_info", "gauge", "Constant 1; labels describe this member.",
           [({"role": s["role"] or "none",
              "hardware": (s.get("hardware") or {}).get("type", "none")}, 1)])
    metric("election_state", "gauge", "1 for the state this node is in now, 0 for the others.",
           [({"state": st}, s["state"] == st) for st in STATES])
    metric("election_state_code", "gauge", "Current state as a number: 0 follower, 1 candidate, 2 leader.",
           [({}, STATE_CODES[s["state"]])])
    metric("election_is_leader", "gauge", "1 if this node is the leader.",
           [({}, s["state"] == "LEADER")])
    metric("election_term", "gauge", "Current election term.", [({}, s["term"])])
    metric("election_has_quorum", "gauge",
           "1 if this node is leader AND has heard from enough voters (quorum).",
           [({}, s["has_quorum"])])
    metric("election_leader_heartbeat_age_seconds", "gauge",
           "Seconds since the last valid leader heartbeat (0 on the leader, NaN if never).",
           [({}, snapshot["heartbeat_age"])])
    metric("election_known_leader", "gauge", "1, labelled with the leader this node believes in.",
           [({"leader": s["leader"]}, 1)] if s["leader"] else [])
    metric("election_voters", "gauge", "Voters (candidates + witnesses) in this node's member list.",
           [({}, s["voters"])])
    metric("election_votes_needed", "gauge", "Votes needed to become leader.", [({}, s["majority"])])
    metric("election_member_list_version", "gauge", "Version counter of this node's member list.",
           [({}, int(s["member_list_version"].split(".")[1]))])
    metric("election_active_member", "gauge", "1 if this node is in its own member list.",
           [({}, s["active"])])

    # --- totals since this app started (counters) ---
    metric("election_elections_total", "counter", "Elections this node started.",
           [({}, events.get("ELECTION_STARTED", 0))])
    metric("election_became_leader_total", "counter", "Times this node won an election.",
           [({}, events.get("BECAME_LEADER", 0))])
    metric("election_leader_changes_total", "counter",
           "Times this node saw the leader change (including becoming leader itself).",
           [({}, events.get("LEADER_CHANGED", 0) + events.get("BECAME_LEADER", 0))])
    metric("election_votes_granted_total", "counter", "Votes this node granted.",
           [({}, events.get("VOTE_GRANTED", 0))])
    metric("election_votes_rejected_total", "counter", "Vote requests this node refused, by reason.",
           [({"reason": r}, snapshot["votes_refused"].get(r, 0)) for r in VOTE_REFUSAL_REASONS])
    metric("election_votes_refused_by_peers_total", "counter",
           "Votes other voters refused this node while it was a candidate.",
           [({}, events.get("VOTE_REFUSED", 0))])
    metric("election_messages_rejected_total", "counter",
           "Heartbeats and vote requests rejected, by reason.",
           [({"reason": reason}, events.get(event, 0))
            for event, reason in REJECTED_MESSAGE_EVENTS.items()])
    metric("election_quorum_lost_total", "counter", "Times this node, as leader, lost quorum.",
           [({}, events.get("QUORUM_LOST", 0))])
    metric("election_stepped_down_total", "counter", "Times this node went back to FOLLOWER.",
           [({}, events.get("STEPPED_DOWN", 0))])
    metric("election_events_total", "counter", "Every event type written to this node's event log.",
           [({"event": e}, n) for e, n in sorted(events.items())])
    return "\n".join(lines) + "\n"
