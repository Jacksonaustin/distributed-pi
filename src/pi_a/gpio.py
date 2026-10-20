import os
import time

from gpiozero import LED, DigitalOutputDevice

# The LED is wired between two GPIO pins (BCM numbers): LED_PIN drives it and
# LED_GROUND_PIN is held low so it acts as ground. If the LED never lights it's
# in backwards - swap them: LED_PIN=24 LED_GROUND_PIN=25.
# If the LED's other leg goes to a real GND pin instead, set LED_GROUND_PIN="".
LED_PIN = int(os.environ.get("LED_PIN", "25"))
LED_GROUND_PIN = os.environ.get("LED_GROUND_PIN", "24")

heart = LED(LED_PIN)
led_ground = (DigitalOutputDevice(int(LED_GROUND_PIN), initial_value=False)
              if LED_GROUND_PIN else None)


def blink_led():
    print("LED blink")
    heart.on()
    time.sleep(0.1)
    heart.off()
