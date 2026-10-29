#!/usr/bin/env python3
"""Write Prometheus's scrape targets from the cluster's member list.

Prometheus reads monitoring/targets/election.json (file_sd_configs in
prometheus.yml) and re-reads it whenever it changes - so members that join,
leave or change address show up in Prometheus without editing prometheus.yml.

    python3 monitoring/make_targets.py                       from src/cluster.json
    python3 monitoring/make_targets.py --from http://localhost:5003
                                                             from a running member's /members
    python3 monitoring/make_targets.py --from http://localhost:5003 --watch 5
                                                             keep it up to date every 5 s
    add --docker when Prometheus runs in Docker: localhost becomes host.docker.internal

Standard library only - runs with any python3.
"""
import argparse
import json
import os
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CLUSTER = os.path.join(HERE, "..", "src", "cluster.json")
DEFAULT_OUT = os.path.join(HERE, "targets", "election.json")


def load_members(source):
    if source.startswith("http://"):
        with urllib.request.urlopen(source.rstrip("/") + "/members", timeout=3) as r:
            data = json.load(r)
    else:
        with open(source) as f:
            data = json.load(f)
    entries = data.get("members", data.get("voters", []))
    members = []
    for e in entries:
        role = e.get("role") or ("candidate" if e.get("can_lead") else "witness")
        members.append({"name": e["name"], "url": e["url"], "role": role})
    return members


def to_targets(members, docker):
    """One target group per member, so each keeps its own node/role labels."""
    groups = []
    for m in members:
        url = urlparse(m["url"])
        host = url.hostname
        if docker and host in ("localhost", "127.0.0.1"):
            host = "host.docker.internal"       # the Mac, as seen from inside Docker
        groups.append({"targets": [f"{host}:{url.port or 80}"],
                       "labels": {"node": m["name"], "role": m["role"]}})
    return groups


def write_atomically(path, groups):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(groups, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)          # Prometheus never sees a half-written file


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--from", dest="source", default=DEFAULT_CLUSTER,
                        help="cluster.json path, or a member's URL (default: src/cluster.json)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="targets file Prometheus reads")
    parser.add_argument("--docker", action="store_true",
                        help="rewrite localhost to host.docker.internal")
    parser.add_argument("--watch", type=float, default=0, metavar="SECONDS",
                        help="keep refreshing every N seconds")
    args = parser.parse_args()

    last = None
    while True:
        try:
            groups = to_targets(load_members(args.source), args.docker)
            if groups != last:
                write_atomically(args.out, groups)
                names = ", ".join(f"{g['labels']['node']}={g['targets'][0]}" for g in groups)
                print(f"{time.strftime('%H:%M:%S')} wrote {len(groups)} targets: {names}", flush=True)
                last = groups
        except (OSError, ValueError, KeyError) as e:
            print(f"{time.strftime('%H:%M:%S')} couldn't read members from {args.source}: {e}",
                  file=sys.stderr, flush=True)
            if not args.watch:
                sys.exit(1)
        if not args.watch:
            return
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
