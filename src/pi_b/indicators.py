"""pi-b buzzer patterns for Lab 5 (passive buzzer -> TonalBuzzer from gpio.py).

  became LEADER     -> two short beeps
  LEADER + quorum   -> one short chirp every 5 seconds
  FOLLOWER          -> silent
  became CANDIDATE  -> one short beep
  lost quorum       -> three short beeps

on_change only queues sounds (the node calls it while holding its lock);
buzzer_loop plays them and handles the 5 s leader chirp.
"""
import queue
import time

from gpiozero.tones import Tone

from pi_b.gpio import buzzer

BEEP = Tone("A4")             # 440 Hz
CHIRP = Tone("E5")            # 659 Hz, higher so it's easy to tell apart
WARN = Tone("C4")             # 262 Hz, low for lost quorum
CHIRP_EVERY = 5.0

sounds = queue.Queue()


def beep(times, tone=BEEP, on=0.1, off=0.1):
    for _ in range(times):
        buzzer.play(tone)
        time.sleep(on)
        buzzer.stop()
        time.sleep(off)


def on_change(event, status):
    if event == "leader":
        print("BUZZER: two beeps (became leader)")
        sounds.put((2, BEEP))
    elif event == "candidate":
        print("BUZZER: one beep (candidate)")
        sounds.put((1, BEEP))
    elif event == "lost_quorum":
        print("BUZZER: three beeps (lost quorum)")
        sounds.put((3, WARN))
    elif event == "follower":
        print("BUZZER: silent (follower)")


def buzzer_loop(get_status):
    last_chirp = time.monotonic()
    while True:
        try:
            times, tone = sounds.get(timeout=0.1)
            beep(times, tone)
            last_chirp = time.monotonic()
        except queue.Empty:
            s = get_status()
            if (s["state"] == "LEADER" and s["has_quorum"]
                    and time.monotonic() - last_chirp >= CHIRP_EVERY):
                print("BUZZER: chirp (leader with quorum)")
                beep(1, CHIRP, on=0.05)
                last_chirp = time.monotonic()
