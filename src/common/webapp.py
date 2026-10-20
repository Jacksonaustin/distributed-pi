"""Shared Flask app for every voter: election endpoints, status, and dashboard.

pi-a, pi-b, witnesses and any extra candidates all run this same app; only the
name and the hardware hooks differ. Whether a voter can lead comes from
can_lead in the cluster file.
"""
import argparse
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, render_template, request

from common.config import CLUSTER_FILE, LOG_DIR, MAJORITY, SRC_DIR, VOTERS, port_of
from common.election import Node
from common.event_log import EventLog
from common.rpc import get_json, post_json

TEMPLATE_DIR = os.path.join(SRC_DIR, "templates")
TEST_KINDS = ("heartbeat", "request-vote")


def create_app(node):
    app = Flask(__name__, template_folder=TEMPLATE_DIR)
    status_pool = ThreadPoolExecutor(max_workers=max(1, len(VOTERS)))

    @app.route("/heartbeat", methods=["POST"])
    def heartbeat():
        return node.handle_heartbeat(request.get_json(silent=True) or {})

    @app.route("/request-vote", methods=["POST"])
    def request_vote():
        return node.handle_request_vote(request.get_json(silent=True) or {})

    @app.route("/status")
    def status():
        return node.status()

    @app.route("/cluster")
    def cluster():
        """Every voter's /status, fetched here so the page only talks to one origin."""
        def fetch(item):
            name, url = item
            if name == node.name:
                return node.status()
            return get_json(url + "/status", timeout=0.8) or {"node": name, "state": "UNREACHABLE"}

        return {
            "self": node.name,
            "majority": MAJORITY,
            "urls": VOTERS,
            "voters": list(status_pool.map(fetch, VOTERS.items())),
        }

    @app.route("/test/send", methods=["POST"])
    def test_send():
        """Dashboard test panel: send a hand-made heartbeat or vote request to any voter."""
        body = request.get_json(silent=True) or {}
        target, kind, payload = body.get("target"), body.get("kind"), body.get("payload")
        if target not in VOTERS or kind not in TEST_KINDS or not isinstance(payload, dict):
            return {"error": "need target (a voter), kind (heartbeat / request-vote), payload"}, 400
        reply = post_json(VOTERS[target] + "/" + kind, payload, timeout=1.0)
        node.event_log.log("TEST_SENT", payload.get("term"), f"{kind} to {target}: {payload} -> {reply}")
        return {"target": target, "kind": kind, "sent": payload, "reply": reply}

    @app.route("/")
    def index():
        return render_template("lab5.html", name=node.name)

    return app


def run_node(default_name, on_change=None, setup=None):
    """Start one voter.

    --name picks which cluster-file entry this process is (default_name otherwise),
    so the same entry point can run witness, witness-2, pi-c, ...
    setup(node) runs after the node exists but before its threads start.
    """
    parser = argparse.ArgumentParser(description="Run one Lab 5 voter.")
    parser.add_argument("--name", default=os.environ.get("NODE_NAME", default_name),
                        help="voter name from the cluster file")
    parser.add_argument("--port", type=int, default=None,
                        help="override the port from the cluster file")
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)
    event_log = EventLog(os.path.join(LOG_DIR, f"{args.name}_events.log"))
    node = Node(args.name, event_log, on_change=on_change)
    if setup:
        setup(node)
    node.start()

    port = args.port or port_of(args.name)
    role = "candidate" if node.can_lead else "witness"
    print(f"{args.name} ({role}) on port {port} | cluster {os.path.basename(CLUSTER_FILE)} | "
          f"majority {MAJORITY} of {len(VOTERS)} | dashboard http://localhost:{port}/", flush=True)
    # one line per heartbeat request would bury the election events
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    create_app(node).run(host="0.0.0.0", port=port, use_reloader=False)
