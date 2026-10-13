import time
from gpiozero import LED 

#placeholder

heart = LED(26)



def blink_led():
    print("LED blink")
    heart.on()
    time.sleep(0.1)
    heart.off()
