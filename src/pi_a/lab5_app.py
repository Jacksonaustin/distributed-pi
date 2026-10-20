"""pi-a Lab 5 app: election node + LED indicators.

Run from src/:  python -m pi_a.lab5_app
"""
from common.hw import ensure_pin_factory

ensure_pin_factory()          # must run before pi_a.gpio creates the LED

from common.webapp import run_node   # noqa: E402
from pi_a import indicators          # noqa: E402

if __name__ == "__main__":
    run_node("pi-a", on_change=indicators.on_change,
             setup=lambda node: indicators.show_follower())
