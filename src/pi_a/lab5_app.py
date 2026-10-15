"""pi-a Lab 5 app: election node + LED indicators. Lab 4's app.py is untouched.

Run from src/:  python -m pi_a.lab5_app
"""
import os

from flask import Flask, request, render_template

from common.election import Node
from common.event_log import EventLog
from pi_a import indicators

NODE_NAME = "pi-a"
PORT = int(os.environ.get("PORT", 5001))

app = Flask(__name__, template_folder="../templates")

# TODO: event_log = EventLog("pi_a_events.log")
# TODO: node = Node(NODE_NAME, can_lead=True, event_log=event_log, on_change=indicators.on_change)


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    # TODO: return node.handle_heartbeat(...)
    raise NotImplementedError


@app.route("/request-vote", methods=["POST"])
def request_vote():
    # TODO: return node.handle_request_vote(...)
    raise NotImplementedError


@app.route("/status")
def status():
    # TODO: return node.status()
    raise NotImplementedError


# TODO (optional): @app.route("/") dashboard - new template showing state/term/leader/quorum


if __name__ == "__main__":
    # TODO: indicators.show_follower(); node.start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
