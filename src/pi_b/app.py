import os
import threading
import time
from datetime import datetime

from flask import Flask, request, render_template

from pi_b.gpio import warning_pattern, two_beeps

# --- Config ---
NODE_NAME = "pi-b"
PORT = int(os.environ.get("PORT", 5002))
TIMEOUT_SECONDS = 5
CHECK_INTERVAL = 0.25
EVENT_LOG_FILE = os.environ.get("EVENT_LOG_FILE", "events.log")

app = Flask(__name__, template_folder="../templates")

# --- Shared state ---
state_lock = threading.Lock()
state = {
    "node": NODE_NAME,
    "role": "monitor",
    "started_at": time.time(),
    "pi_a_status": "UNKNOWN",        # UNKNOWN -> AVAILABLE <-> UNAVAILABLE
    "last_heartbeat_at": None,       # wall clock, for humans
    "last_heartbeat_mono": None,     # monotonic, for the timeout math
    "last_seq": None,
    "heartbeats_received": 0,
    "missed_seqs": 0,
    "last_delay_seconds": None,
    "recovery_beeps_pending": False,
}
events = []

def log_event(event_type, details):
    """Call this while holding state_lock."""
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "event": event_type,
        "details": details,
    }
    events.append(entry)
    print(f'[{entry["time"]}] {event_type}: {details}')
    with open(EVENT_LOG_FILE, "a") as f:
        f.write(f'{entry["time"]} {event_type} {details}\n')

# --- Receive heartbeats ---
@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    msg = request.get_json(silent=True)
    if not msg or not all(k in msg for k in ("node", "seq", "timestamp")):
        return {"error": "heartbeat needs node, seq, timestamp"}, 400

    now_wall = time.time()
    now_mono = time.monotonic()
    seq = msg["seq"]

    with state_lock:
        last_seq = state["last_seq"]

        # Sequence checks: lost messages or a restart
        if last_seq is not None:
            if seq <= last_seq:
                log_event("SEQ_RESET", f'{msg["node"]} seq went {last_seq} -> {seq} (likely restart)')
            elif seq > last_seq + 1:
                missed = seq - last_seq - 1
                state["missed_seqs"] += missed
                log_event("GAP", f"missed {missed} heartbeat(s) between seq {last_seq} and {seq}")

        # State transitions
        if state["pi_a_status"] == "UNAVAILABLE":
            down_for = now_mono - state["last_heartbeat_mono"]
            log_event("RECOVERY", f'{msg["node"]} back after {down_for:.1f}s (seq {seq})')
            state["recovery_beeps_pending"] = True
        elif state["pi_a_status"] == "UNKNOWN":
            log_event("FIRST_CONTACT", f'first heartbeat from {msg["node"]} (seq {seq})')

        state["pi_a_status"] = "AVAILABLE"
        state["last_heartbeat_at"] = now_wall
        state["last_heartbeat_mono"] = now_mono
        state["last_seq"] = seq
        state["heartbeats_received"] += 1
        state["last_delay_seconds"] = round(now_wall - msg["timestamp"], 3)

    return {"ok": True, "received_seq": seq}

# --- Watch for silence ---
def monitor_loop():
    while True:
        with state_lock:
            if state["pi_a_status"] == "AVAILABLE":
                silent_for = time.monotonic() - state["last_heartbeat_mono"]
                if silent_for > TIMEOUT_SECONDS:
                    state["pi_a_status"] = "UNAVAILABLE"
                    log_event("FAILURE", f'no heartbeat for {silent_for:.1f}s (last seq {state["last_seq"]})')
        time.sleep(CHECK_INTERVAL)

# --- Drive the buzzer from state ---
def buzzer_loop():
    while True:
        with state_lock:
            status = state["pi_a_status"]
            play_recovery = state["recovery_beeps_pending"]
            state["recovery_beeps_pending"] = False

        if play_recovery:
            two_beeps()
        elif status == "UNAVAILABLE":
            warning_pattern()   # one cycle, then re-check state
        else:
            time.sleep(0.1)

# --- Status ---
@app.route("/status")
def status():
    with state_lock:
        snapshot = {k: v for k, v in state.items()
                    if k not in ("last_heartbeat_mono", "recovery_beeps_pending")}
        if state["last_heartbeat_mono"] is not None:
            snapshot["seconds_since_last_heartbeat"] = round(
                time.monotonic() - state["last_heartbeat_mono"], 1)
        snapshot["recent_events"] = events[-20:]
    snapshot["uptime_seconds"] = round(time.time() - snapshot["started_at"], 1)
    return snapshot

#display web page 
@app.route("/")
def index():
    return render_template("pib.html")

if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    threading.Thread(target=buzzer_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)

