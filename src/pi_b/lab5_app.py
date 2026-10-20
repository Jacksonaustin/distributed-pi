"""pi-b Lab 5 app: election node + buzzer indicators.

Run from src/:  python -m pi_b.lab5_app
"""
import threading

from common.hw import ensure_pin_factory

ensure_pin_factory()          # must run before pi_b.gpio creates the buzzer

from common.webapp import run_node   # noqa: E402
from pi_b import indicators          # noqa: E402


def start_buzzer(node):
    threading.Thread(target=indicators.buzzer_loop, args=(node.status,), daemon=True).start()


if __name__ == "__main__":
    run_node("pi-b", on_change=indicators.on_change, setup=start_buzzer)
