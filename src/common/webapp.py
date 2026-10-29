"""Shared Flask app for every member: election endpoints, membership, status, dashboard.

pi-a, pi-b, witnesses, followers and any extra candidates all run this same app;
only the name and the hardware hooks differ. A member's role (candidate,
witness or follower) comes from the cluster file, or from --role when joining.
"""
import argparse
import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from flask import Flask, render_template, request

from common.config import CLUSTER_FILE, LOG_DIR, SRC_DIR
from common.election import Node
from common.event_log import EventLog
from common.hardware import describe, make_indicator, parse_spec
from common.membership import ROLES, Membership, write_if_newer
from common.rpc import get_json, post_json, post_json_status

TEMPLATE_DIR = os.path.join(SRC_DIR, "templates")
TEST_KINDS = ("heartbeat", "request-vote")
DEFAULT_JOIN_PORT = 5000


def create_app(node):
    app = Flask(__name__, template_folder=TEMPLATE_DIR)
    status_pool = ThreadPoolExecutor(max_workers=16)

    @app.route("/heartbeat", methods=["POST"])
    def heartbeat():
        return node.handle_heartbeat(request.get_json(silent=True) or {})

    @app.route("/request-vote", methods=["POST"])
    def request_vote():
        return node.handle_request_vote(request.get_json(silent=True) or {})

    @app.route("/status")
    def status():
        return node.status()

    @app.route("/members")
    def members():
        return node.member_list()

    def change_membership(kind, body, apply):
        """Run a join/leave here if this node is the leader, otherwise forward it
        to the leader once. Any member can be asked."""
        status_code, reply = apply()
        if status_code == 409 and reply.get("error") == "not the leader":
            if body.get("forwarded") or not reply.get("leader_url"):
                return {"error": "no leader right now; try again in a few seconds"}, 503
            status_code, reply = post_json_status(reply["leader_url"] + "/" + kind,
                                                  {**body, "forwarded": True}, timeout=5.0)
            if status_code is None:
                return {"error": f"leader {reply_leader(reply)} did not answer"}, 503
        return reply, status_code

    def reply_leader(reply):
        return (reply or {}).get("leader") or "?"

    @app.route("/join", methods=["POST"])
    def join():
        body = request.get_json(silent=True) or {}
        return change_membership(
            "join", body, lambda: node.join(body.get("name"), body.get("url"), body.get("role"),
                                            body.get("hardware")))

    @app.route("/leave", methods=["POST"])
    def leave():
        body = request.get_json(silent=True) or {}
        return change_membership("leave", body, lambda: node.leave(body.get("name")))

    @app.route("/cluster")
    def cluster():
        """Every member's /status, fetched here so the page only talks to one origin."""
        urls = node.member_urls()
        me = node.status()

        def fetch(item):
            name, url = item
            if name == node.name:
                return me
            return get_json(url + "/status", timeout=0.8) or {"node": name, "state": "UNREACHABLE"}

        voters = list(status_pool.map(fetch, urls.items()))
        if node.name not in urls:                  # still waiting to join
            voters.append(me)
        return {
            "self": node.name,
            "majority": me["majority"],
            "member_list_version": me["member_list_version"],
            "pending_change": me["pending_change"],
            "roles": {m["name"]: m["role"] for m in me["members"]},
            "urls": urls,
            "voters": voters,
        }

    @app.route("/test/send", methods=["POST"])
    def test_send():
        """Dashboard test panel: send a hand-made heartbeat or vote request to any member."""
        body = request.get_json(silent=True) or {}
        target, kind, payload = body.get("target"), body.get("kind"), body.get("payload")
        urls = node.member_urls()
        if target not in urls or kind not in TEST_KINDS or not isinstance(payload, dict):
            return {"error": "need target (a member), kind (heartbeat / request-vote), payload"}, 400
        reply = post_json(urls[target] + "/" + kind, payload, timeout=1.0)
        node.event_log.log("TEST_SENT", payload.get("term"), f"{kind} to {target}: {payload} -> {reply}")
        return {"target": target, "kind": kind, "sent": payload, "reply": reply}

    @app.route("/")
    def index():
        return render_template("lab5.html", name=node.name)

    return app


def _ip_toward(url):
    """The local address used to reach `url` (no packets are sent - a UDP
    connect just picks a route). None if there's no route."""
    target = urlparse(url)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((target.hostname, target.port or 80))
            return s.getsockname()[0]
    except OSError:
        return None


def _my_ip(join_url, members):
    """The address other members can reach this machine on. Joining via
    localhost would give 127.0.0.1, which means "itself" to every other machine -
    so prefer the route toward a member that lives on another machine."""
    for url in [join_url] + [m["url"] for m in members.members.values()]:
        ip = _ip_toward(url)
        if ip and not ip.startswith("127."):
            return ip
    return _ip_toward(join_url) or "127.0.0.1"   # everything is on this machine


def _same_address(listed_url, detected_url):
    """True if both URLs point at this machine on the same port, even if one says
    localhost and the other an IP - so a restart doesn't count as a move."""
    a, b = urlparse(listed_url), urlparse(detected_url)
    if a.port != b.port:
        return False
    try:
        ip_a = socket.gethostbyname(a.hostname)
    except OSError:
        return False
    local = {b.hostname, "127.0.0.1"}
    return ip_a in local or ip_a.startswith("127.")


def _ask_to_join(node, event_log, join_url, my_url, role, hardware):
    """Background thread: keep asking until the cluster's leader is sending us a
    member list with our name and address in it. An accepted join can still be
    lost if that leader is replaced before a majority has the new list - so a
    "yes" alone isn't enough, we wait to see it arrive and ask again if it doesn't."""
    time.sleep(1.0)                                  # let Flask start first
    payload = {"name": node.name, "url": my_url, "role": role, "hardware": hardware}

    def joined():
        s = node.status()
        return s["active"] and any(m["name"] == node.name and m["url"] == my_url
                                   and m.get("hardware") == hardware for m in s["members"])

    while not joined():
        status_code, reply = post_json_status(join_url + "/join", payload, timeout=6.0)
        if status_code == 200:
            event_log.log("JOIN_ACCEPTED", node.status()["term"], f"as {role} at {my_url}")
            # wait up to 10s for a heartbeat that carries the new list
            for _ in range(100):
                if joined():
                    return
                time.sleep(0.1)
            event_log.log("JOIN_RETRY", node.status()["term"],
                          "accepted, but no heartbeat with us in the member list yet; asking again")
            continue
        reason = (reply or {}).get("error", "no answer")
        if status_code == 400:                        # our request itself is wrong
            event_log.log("JOIN_FAILED", node.status()["term"], f"{join_url}/join: {reason}")
            return
        event_log.log("JOIN_RETRY", node.status()["term"], f"{join_url}/join: {reason}; retrying in 3s")
        time.sleep(3.0)


def run_node(default_name=None, legacy_hardware=None):
    """Start one member. Every Pi and the witness run this same code.

    The node's name defaults to this machine's hostname (pi-a, pi-b, ...); its
    role, address and LED/buzzer pins come from its entry in the cluster file.
    --join asks a running cluster to add this node, or to record a new address
    or hardware for it. legacy_hardware only keeps the old Lab 5 entry points
    working when the cluster file has no hardware entry for that Pi.
    """
    parser = argparse.ArgumentParser(description="Run one cluster member.")
    parser.add_argument("--name", default=os.environ.get("NODE_NAME") or default_name
                        or socket.gethostname().split(".")[0].lower(),
                        help="member name (default: this machine's hostname)")
    parser.add_argument("--port", type=int, default=None,
                        help="override the port from the cluster file")
    parser.add_argument("--join", metavar="URL", default=None,
                        help="any running member, e.g. http://10.0.0.11:5001 - ask the cluster "
                             "to add this node (or record its new address / hardware)")
    parser.add_argument("--role", choices=ROLES, default=None,
                        help="role to join as (default: follower)")
    parser.add_argument("--url", default=None,
                        help="this node's address for the others (default: detected)")
    parser.add_argument("--hardware", default=None, metavar="SPEC",
                        help="this Pi's indicator: led:PIN, led:PIN:GROUND_PIN, buzzer:PIN, "
                             "buzzer:PIN:active or none (default: from the cluster file)")
    args = parser.parse_args()
    join_url = args.join.rstrip("/") if args.join else None

    # A joining node starts from the cluster's current member list.
    if join_url:
        current = get_json(join_url + "/members", timeout=3.0)
        if not current:
            raise SystemExit(f"can't reach {join_url}/members - is that member running?")
        write_if_newer(CLUSTER_FILE, current)

    members = Membership(CLUSTER_FILE)
    is_member = members.has(args.name)
    if not is_member and not join_url:
        raise SystemExit(f"'{args.name}' is not in {CLUSTER_FILE}; "
                         f"start it with --join <url of any member> to add it, or pass --name")

    if is_member:
        port = args.port or members.port_of(args.name)
        role = members.role(args.name)
    else:
        port = args.port or DEFAULT_JOIN_PORT
        role = args.role or "follower"
    listed_hardware = members.hardware(args.name)
    hardware = parse_spec(args.hardware) if args.hardware else (listed_hardware or legacy_hardware)
    my_url = args.url.rstrip("/") if args.url else (
        f"http://{_my_ip(join_url, members)}:{port}" if join_url else members.url(args.name))
    if is_member and not args.url and _same_address(members.url(args.name), my_url):
        my_url = members.url(args.name)        # unchanged - keep it exactly as listed
    # ask the leader if we're new, or if our address or hardware changed
    changed = not is_member or my_url != members.url(args.name) or hardware != listed_hardware
    needs_join = bool(join_url) and changed
    if changed and is_member and not join_url and args.hardware:
        print(f"note: --hardware is used on this Pi, but the cluster file still lists "
              f"{describe(listed_hardware)}; add --join <any member> to record it", flush=True)

    os.makedirs(LOG_DIR, exist_ok=True)
    event_log = EventLog(os.path.join(LOG_DIR, f"{args.name}_events.log"))
    indicator = make_indicator(hardware)
    node = Node(args.name, event_log, on_change=indicator.on_change,
                role=None if is_member else role)
    indicator.start(node.status)
    node.start()
    if needs_join:
        threading.Thread(target=_ask_to_join,
                         args=(node, event_log, join_url, my_url, role, hardware),
                         daemon=True).start()

    s = node.status()
    joining = f" | joining via {join_url} as {my_url}" if needs_join else ""
    print(f"{args.name} ({role}, {describe(hardware)}) on port {port} | cluster "
          f"{os.path.basename(CLUSTER_FILE)} v{s['member_list_version']} | majority "
          f"{s['majority']} of {s['voters']}{joining} | dashboard http://localhost:{port}/",
          flush=True)
    # one line per heartbeat request would bury the election events
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    create_app(node).run(host="0.0.0.0", port=port, use_reloader=False)
