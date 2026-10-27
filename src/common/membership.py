"""Cluster membership: who is in the cluster, and what role each member has.

Roles
  candidate  votes, and can become leader              (pi-a, pi-b)
  witness    votes, never becomes leader               (the laptop)
  follower   non-voting: receives heartbeats and acks them, but never votes,
             never runs for leader, and doesn't count toward the majority

The member list lives in the cluster file (cluster.json). Each node rewrites
its own copy whenever the list changes, so the file is always the current list.

Every version of the list has an id: (config_term, config_version) - the term
of the leader that made the change, plus a counter. A higher id is newer.
Only one leader exists per term, so two different lists never share an id.

Not thread-safe by itself: Node only touches it while holding its lock.
"""
import json
import os
import re
import tempfile
from urllib.parse import urlparse

ROLES = ("candidate", "witness", "follower")
VOTING_ROLES = ("candidate", "witness")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def validate_member(name, url, role):
    """Return an error message for a bad join request, or None if it's fine."""
    if not isinstance(name, str) or not NAME_RE.match(name):
        return "name must be lowercase letters, digits and dashes (e.g. pi-c)"
    if role not in ROLES:
        return f"role must be one of {', '.join(ROLES)}"
    parsed = urlparse(url) if isinstance(url, str) else None
    if not parsed or parsed.scheme != "http" or not parsed.hostname or not parsed.port \
            or parsed.path not in ("", "/"):
        return "url must look like http://<ip or host>:<port>"
    return None


def _role_of(entry):
    """Lab 5 files used can_lead true/false instead of a role."""
    if "role" in entry:
        return entry["role"]
    return "candidate" if entry.get("can_lead") else "witness"


def _parse(data):
    members = {}
    for entry in data.get("members", data.get("voters", [])):
        members[entry["name"]] = {"url": entry["url"].rstrip("/"), "role": _role_of(entry)}
    config_id = (int(data.get("config_term", 0)), int(data.get("config_version", 0)))
    return config_id, members


def write_if_newer(path, snapshot):
    """Save a member list fetched from the cluster, unless the file already has
    the same or a newer one. Used by a node that is about to join."""
    try:
        current = Membership(path)
    except (OSError, ValueError, KeyError):
        current = Membership.empty(path)
    if _parse(snapshot)[0] > current.config_id:
        current.replace(snapshot)


class Membership:
    def __init__(self, path):
        self.path = path
        with open(path) as f:
            self.config_id, self.members = _parse(json.load(f))

    @classmethod
    def empty(cls, path):
        m = cls.__new__(cls)
        m.path, m.config_id, m.members = path, (-1, -1), {}
        return m

    # ------------------------------------------------------------- queries

    def has(self, name):
        return name in self.members

    def url(self, name):
        return self.members[name]["url"]

    def role(self, name):
        return self.members[name]["role"]

    def is_candidate(self, name):
        return name in self.members and self.role(name) == "candidate"

    def is_voter(self, name):
        return name in self.members and self.role(name) in VOTING_ROLES

    def voters(self):
        return [n for n in self.members if self.role(n) in VOTING_ROLES]

    def majority(self):
        return len(self.voters()) // 2 + 1        # 3 voters -> 2, 5 voters -> 3

    def acks_needed(self):
        return self.majority() - 1                # leader's own vote + this many acks

    def peers_of(self, name):
        """Every other member (heartbeats go to followers too)."""
        return {n: m["url"] for n, m in self.members.items() if n != name}

    def voter_peers_of(self, name):
        """Every other voter (only voters get vote requests)."""
        return {n: m["url"] for n, m in self.members.items()
                if n != name and m["role"] in VOTING_ROLES}

    def port_of(self, name):
        return urlparse(self.url(name)).port or 80

    def snapshot(self):
        """The list as sent in heartbeats and saved to the cluster file."""
        return {
            "config_term": self.config_id[0],
            "config_version": self.config_id[1],
            "members": [{"name": n, "url": m["url"], "role": m["role"]}
                        for n, m in self.members.items()],
        }

    # ------------------------------------------------------------- changes

    def replace(self, snapshot):
        """Adopt a newer list received from the leader. Returns a summary of what changed."""
        new_id, new_members = _parse(snapshot)
        added = [n for n in new_members if n not in self.members]
        removed = [n for n in self.members if n not in new_members]
        moved = [n for n in new_members
                 if n in self.members and new_members[n] != self.members[n]]
        self.config_id, self.members = new_id, new_members
        self.save()
        parts = ([f"+{n} ({new_members[n]['role']})" for n in added]
                 + [f"-{n}" for n in removed]
                 + [f"{n} now {new_members[n]['url']}" for n in moved])
        return ", ".join(parts) or "no member changes"

    def set_member(self, term, name, url, role):
        """Leader only: add a member or change its address."""
        self.members[name] = {"url": url.rstrip("/"), "role": role}
        self._bump(term)

    def remove(self, term, name):
        """Leader only: remove a member."""
        del self.members[name]
        self._bump(term)

    def _bump(self, term):
        self.config_id = (term, self.config_id[1] + 1)
        self.save()

    def save(self):
        """Rewrite the cluster file atomically - but never with an older list than
        the file already holds (several local test nodes can share one file)."""
        try:
            with open(self.path) as f:
                on_disk, _ = _parse(json.load(f))
            if on_disk > self.config_id:
                return
        except (OSError, ValueError, KeyError):
            pass
        snap = self.snapshot()
        lines = ["{",
                 f'  "config_term": {snap["config_term"]},',
                 f'  "config_version": {snap["config_version"]},',
                 '  "members": [']
        entries = [f"    {json.dumps(m)}" for m in snap["members"]]
        lines.append(",\n".join(entries))
        lines += ["  ]", "}"]
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path) or ".",
                                   prefix=os.path.basename(self.path) + ".", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, self.path)
