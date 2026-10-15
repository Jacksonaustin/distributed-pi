import time
from gpiozero import TonalBuzzer 

buzzer = TonalBuzzer(6)

def warning_pattern():
    """One cycle of the warning. The caller repeats it while pi-a is down."""
    print("BUZZER: BEEP-BEEP-BEEP (pi-a unavailable)")
    buzzer.play(69)
    time.sleep(.1)
    buzzer.stop()
    time.sleep(0.1)
    buzzer.play(69)
    time.sleep(.1)
    buzzer.stop()
    time.sleep(0.1)
    buzzer.play(69)
    time.sleep(.1)
    buzzer.stop()
    time.sleep(1)

def two_beeps():
    print("BUZZER: beep beep (pi-a recovered)")
    buzzer.play(69)
    time.sleep(.1)
    buzzer.stop()
    time.sleep(0.1)
    buzzer.play(69)
    time.sleep(0.1)
    buzzer.stop()
    time.sleep(0.4)
