"""Pick a GPIO pin factory that works on this machine.

On a Raspberry Pi gpiozero finds lgpio by itself. Anywhere else (the laptop)
there are no pins, so fall back to mock pins that support PWM - TonalBuzzer
needs PWM even when mocked. Call this BEFORE importing a gpio module.
"""
import os


def on_raspberry_pi():
    try:
        with open("/proc/device-tree/model") as f:
            return "Raspberry Pi" in f.read()
    except OSError:
        return False


def ensure_pin_factory():
    if on_raspberry_pi():
        return
    os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")
    if os.environ["GPIOZERO_PIN_FACTORY"] == "mock":
        os.environ.setdefault("GPIOZERO_MOCK_PIN_CLASS", "mockpwmpin")
