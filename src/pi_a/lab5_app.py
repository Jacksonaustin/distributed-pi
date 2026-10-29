"""Lab 5 entry point for pi-a - kept so the old command still works.
New: python -m node --name pi-a (pins from the cluster file).

Run from src/:  python -m pi_a.lab5_app
"""
from common.webapp import run_node

# Only used if the cluster file has no hardware entry for pi-a (Lab 5 wiring).
LAB5_LED = {"type": "led", "pin": 25, "ground_pin": 24}

if __name__ == "__main__":
    run_node("pi-a", legacy_hardware=LAB5_LED)
