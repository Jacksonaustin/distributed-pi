import time
from gpiozero import  Buzzer 

buzzer = Buzzer(17)

def warning_pattern():
    """One cycle of the warning. The caller repeats it while pi-a is down."""
    print("BUZZER: BEEP-BEEP-BEEP (pi-a unavailable)")
    buzzer.on()
    time.sleep(.1)
    buzzer.off()
    time.sleep(0.1)
    buzzer.on()
    time.sleep(.1)
    buzzer.off()
    time.sleep(0.1)
    buzzer.on()
    time.sleep(.1)
    buzzer.off()
    time.sleep(1)

def two_beeps():
    print("BUZZER: beep beep (pi-a recovered)")
    buzzer.on()
    time.sleep(.1)
    buzzer.off()
    time.sleep(0.1)
    buzzer.on()
    time.sleep(.1)
    buzzer.off()
    time.sleep(0.4)