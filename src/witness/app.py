import os

from flask import Flask, request

from common.election import Node
from common.event_log import EventLog

NODE_NAME = "witness"
PORT = int(os.environ.get("PORT", 5003))

app = Flask(__name__)
event_log = EventLog("witness_events.log")
node = Node(NODE_NAME, can_lead=False, event_log=event_log)


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
    node.start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
