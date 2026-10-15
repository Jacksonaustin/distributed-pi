"""pi-a Lab 5 app: election node + LED indicators.

Run from src/:  python -m pi_a.lab5_app
"""
import os

from flask import Flask, request

from common.election import Node
from common.event_log import EventLog
from pi_a import indicators

NODE_NAME = "pi-a"
PORT = int(os.environ.get("PORT", 5001))

app = Flask(__name__)
event_log = EventLog("pi_a_events.log")
node = Node(NODE_NAME, can_lead=True, event_log=event_log, on_change=indicators.on_change)


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    return node.handle_heartbeat(request.get_json(silent=True) or {})


@app.route("/request-vote", methods=["POST"])
def request_vote():
    return node.handle_request_vote(request.get_json(silent=True) or {})


@app.route("/status")
def status():
    return node.status()


if __name__ == "__main__":
    indicators.show_follower()
    node.start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
