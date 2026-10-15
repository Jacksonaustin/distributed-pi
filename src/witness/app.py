"""Witness voter - runs on the laptop. Votes and acks heartbeats; never leads.

Run from src/:  python -m witness.app
"""
import os

from flask import Flask, request

from common.election import Node
from common.event_log import EventLog

NODE_NAME = "witness"
PORT = int(os.environ.get("PORT", 5003))

app = Flask(__name__)

# TODO: event_log = EventLog("witness_events.log")
# TODO: node = Node(NODE_NAME, can_lead=False, event_log=event_log)


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    # TODO: return node.handle_heartbeat(request.get_json(silent=True) or {})
    raise NotImplementedError


@app.route("/request-vote", methods=["POST"])
def request_vote():
    # TODO: return node.handle_request_vote(request.get_json(silent=True) or {})
    raise NotImplementedError


@app.route("/status")
def status():
    # TODO: return node.status()
    raise NotImplementedError


if __name__ == "__main__":
    # TODO: node.start()  (witness has no election timer, but start() should handle can_lead=False)
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
