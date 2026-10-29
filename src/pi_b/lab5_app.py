"""Lab 5 entry point for pi-b - kept so the old command still works.
New: python -m node --name pi-b (pins from the cluster file).

Run from src/:  python -m pi_b.lab5_app
"""
from common.webapp import run_node

# Only used if the cluster file has no hardware entry for pi-b (Lab 5 wiring).
LAB5_BUZZER = {"type": "buzzer", "pin": 6, "passive": True}

if __name__ == "__main__":
    run_node("pi-b", legacy_hardware=LAB5_BUZZER)
