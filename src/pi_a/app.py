import os
import threading
import time

from flask import Flask, render_template

from common.heartbeat import build_heartbeat
from common.network import send_heartbeat
from pi_a.gpio import blink_led

# Values set at startup 
NODE_NAME = "pi-a"
PI_B_URL = os.environ.get("PI_B_URL", "http://pi-b.local:5002/heartbeat")
PORT = int(os.environ.get("PORT", 5001))
HEARTBEAT_INTERVAL = 1

app = Flask(__name__, template_folder="../templates")

state_lock = threading.Lock()
state = {
    "node": NODE_NAME,
    "role": "monitored",
    "target": PI_B_URL,
    "interval_seconds": HEARTBEAT_INTERVAL,
    "started_at": time.time(),
    "seq": 0,
    "last_sent_at": None,
    "last_send_ok": None,
    "sent_ok": 0,
    "send_failures": 0,
    "consecutive_failures": 0,
    "last_error": None,
}



# Sender thread updates state on every loop 
def heartbeat_loop():
    while True:
        loop_start = time.monotonic()

        with state_lock:
            state["seq"] += 1
            seq = state["seq"]

        message = build_heartbeat(NODE_NAME, seq)
        ok, error = send_heartbeat(PI_B_URL, message)
        blink_led()

        with state_lock:
            state["last_sent_at"] = message["timestamp"]
            state["last_send_ok"] = ok
            if ok:
                state["sent_ok"] += 1
                state["consecutive_failures"] = 0
            else:
                state["send_failures"] += 1
                state["consecutive_failures"] += 1
                state["last_error"] = error

        # sleep only for the time left, so each loop stays about 1s long
        elapsed = time.monotonic() - loop_start
        time.sleep(max(0, HEARTBEAT_INTERVAL - elapsed))

#/status only reads state 
@app.route("/status")
def status():
    with state_lock:
        snapshot = dict(state)
    # --- 2. Calculated when requested ---
    snapshot["uptime_seconds"] = round(time.time() - snapshot["started_at"], 1)
    return snapshot

#display web page
@app.route("/")
def index():
    return render_template("pia.html")

if __name__ == "__main__":
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)


