"""LED and buzzer indicators for any Pi, configured from the cluster file.

Each member may have a "hardware" entry - its pins live in config, not in code:

    {"type": "led",    "pin": 25, "ground_pin": 24}   LED; ground_pin is optional
                                                      (a GPIO held low as ground)
    {"type": "buzzer", "pin": 6,  "passive": true}    passive buzzer (TonalBuzzer)
    {"type": "buzzer", "pin": 6,  "passive": false}   active buzzer (plain Buzzer)

On the command line the same thing is written  led:25:24  led:17  buzzer:6
buzzer:6:active. Pin numbers are GPIO (BCM) numbers, not physical pin positions.

Lab 5 patterns, unchanged:
  LED     follower off | candidate slow blink | leader solid | lost quorum fast blink
  buzzer  follower silent | candidate 1 beep | became leader 2 beeps |
          leader with quorum 1 chirp every 5 s | lost quorum 3 beeps
"""
import queue
import time

from common.hw import ensure_pin_factory

HARDWARE_TYPES = ("led", "buzzer")


def validate_hardware(hw):
    """Return an error message for a bad hardware entry, or None (None = no hardware)."""
    if hw is None:
        return None
    if not isinstance(hw, dict) or hw.get("type") not in HARDWARE_TYPES:
        return 'hardware must be {"type": "led" or "buzzer", "pin": N, ...}'
    pins = [hw.get("pin")] + ([hw["ground_pin"]] if hw.get("ground_pin") is not None else [])
    if not all(isinstance(p, int) and not isinstance(p, bool) and 0 <= p <= 27 for p in pins):
        return "pins must be GPIO numbers 0-27"
    if len(set(pins)) != len(pins):
        return "pin and ground_pin must be different"
    return None


def parse_spec(text):
    """'led:25:24' / 'led:17' / 'buzzer:6' / 'buzzer:6:active' / 'none' -> dict or None."""
    parts = text.strip().lower().split(":")
    try:
        if parts == ["none"]:
            return None
        if parts[0] == "led" and len(parts) in (2, 3):
            hw = {"type": "led", "pin": int(parts[1])}
            if len(parts) == 3:
                hw["ground_pin"] = int(parts[2])
        elif parts[0] == "buzzer" and len(parts) in (2, 3):
            if len(parts) == 3 and parts[2] not in ("active", "passive"):
                raise ValueError
            hw = {"type": "buzzer", "pin": int(parts[1]),
                  "passive": len(parts) == 2 or parts[2] == "passive"}
        else:
            raise ValueError
    except ValueError:
        raise SystemExit(f"--hardware {text!r}: use led:PIN, led:PIN:GROUND_PIN, buzzer:PIN, "
                         f"buzzer:PIN:active or none")
    error = validate_hardware(hw)
    if error:
        raise SystemExit(f"--hardware {text!r}: {error}")
    return hw


def describe(hw):
    if not hw:
        return "no hardware"
    if hw["type"] == "led":
        ground = f", GPIO{hw['ground_pin']} as ground" if hw.get("ground_pin") is not None else ""
        return f"LED on GPIO{hw['pin']}{ground}"
    return f"{'passive' if hw.get('passive', True) else 'active'} buzzer on GPIO{hw['pin']}"


class NoIndicator:
    """For the witness and any Pi without an LED or buzzer."""

    def on_change(self, event, status):
        pass

    def start(self, get_status):
        pass


class LedIndicator(NoIndicator):
    def __init__(self, pin, ground_pin=None):
        from gpiozero import LED, DigitalOutputDevice
        self.led = LED(pin)
        # an LED wired between two GPIOs: hold the other one low so it acts as ground
        self.ground = (DigitalOutputDevice(ground_pin, initial_value=False)
                       if ground_pin is not None else None)

    def start(self, get_status):
        self.show("off (follower)", self.led.off)

    def show(self, label, action, *args, **kwargs):
        print(f"LED: {label}")
        action(*args, **kwargs)

    def on_change(self, event, status):
        # led.blink() runs in the background by itself, so this returns immediately
        if event == "follower":
            self.show("off (follower)", self.led.off)
        elif event == "candidate":
            self.show("slow blink (candidate)", self.led.blink, on_time=0.5, off_time=0.5)
        elif event in ("leader", "quorum_restored"):
            self.show("solid (leader with quorum)", self.led.on)
        elif event == "lost_quorum":
            self.show("fast blink (lost quorum)", self.led.blink, on_time=0.1, off_time=0.1)


class BuzzerIndicator(NoIndicator):
    """on_change only queues sounds (the node calls it while holding its lock);
    a background thread plays them and handles the 5 s leader chirp."""
    CHIRP_EVERY = 5.0

    def __init__(self, pin, passive=True):
        from gpiozero import Buzzer, TonalBuzzer
        from gpiozero.tones import Tone
        self.passive = passive
        self.buzzer = TonalBuzzer(pin) if passive else Buzzer(pin)
        self.beep_tone, self.chirp_tone, self.warn_tone = Tone("A4"), Tone("E5"), Tone("C4")
        self.sounds = queue.Queue()

    def _on(self, tone):
        if self.passive:
            self.buzzer.play(tone)
        else:
            self.buzzer.on()                 # an active buzzer has one fixed pitch

    def _off(self):
        if self.passive:
            self.buzzer.stop()
        else:
            self.buzzer.off()

    def beep(self, times, tone, on=0.1, off=0.1):
        for _ in range(times):
            self._on(tone)
            time.sleep(on)
            self._off()
            time.sleep(off)

    def on_change(self, event, status):
        if event == "leader":
            print("BUZZER: two beeps (became leader)")
            self.sounds.put((2, self.beep_tone))
        elif event == "candidate":
            print("BUZZER: one beep (candidate)")
            self.sounds.put((1, self.beep_tone))
        elif event == "lost_quorum":
            print("BUZZER: three beeps (lost quorum)")
            self.sounds.put((3, self.warn_tone))
        elif event == "follower":
            print("BUZZER: silent (follower)")

    def start(self, get_status):
        import threading
        threading.Thread(target=self._loop, args=(get_status,), daemon=True).start()

    def _loop(self, get_status):
        last_chirp = time.monotonic()
        while True:
            try:
                times, tone = self.sounds.get(timeout=0.1)
                self.beep(times, tone)
                last_chirp = time.monotonic()
            except queue.Empty:
                s = get_status()
                if (s["state"] == "LEADER" and s["has_quorum"]
                        and time.monotonic() - last_chirp >= self.CHIRP_EVERY):
                    print("BUZZER: chirp (leader with quorum)")
                    self.beep(1, self.chirp_tone, on=0.05)
                    last_chirp = time.monotonic()


def make_indicator(hw):
    """Build the indicator for this node's hardware entry (None -> no hardware)."""
    if not hw:
        return NoIndicator()
    ensure_pin_factory()                     # mock pins when not on a Pi
    if hw["type"] == "led":
        return LedIndicator(hw["pin"], hw.get("ground_pin"))
    return BuzzerIndicator(hw["pin"], hw.get("passive", True))
