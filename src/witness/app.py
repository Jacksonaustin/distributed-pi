"""Witness voter - votes and acks heartbeats, never leads.

The same shared app as the Pis (python -m node --name witness does the same);
this entry point just defaults the name to "witness".

Run from src/:  python -m witness.app [--name witness-2]
"""
from common.webapp import run_node

if __name__ == "__main__":
    run_node("witness")
