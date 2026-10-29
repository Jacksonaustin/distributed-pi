"""The one shared election app - run this same command on every Raspberry Pi.

Run from src/:
    python -m node                      name = this machine's hostname
    python -m node --name pi-c          or pick the name
    python -m node --name pi-c --role candidate --hardware led:17 --join http://<any member>

Role, address and LED/buzzer pins come from this node's entry in the cluster
file (see common/hardware.py), so nothing about a particular Pi is in the code.
"""
from common.webapp import run_node

if __name__ == "__main__":
    run_node()
