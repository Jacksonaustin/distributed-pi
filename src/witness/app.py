"""Witness voter - votes and acks heartbeats, never leads.

Also runs any extra voter that has no hardware (another witness, or an extra
candidate for testing). Its role comes from can_lead in the cluster file.

Run from src/:  python -m witness.app [--name witness-2]
"""
from common.webapp import run_node

if __name__ == "__main__":
    run_node("witness")
