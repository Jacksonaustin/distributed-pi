"""pi-a LED patterns for Lab 5.

  FOLLOWER        -> off
  CANDIDATE       -> slow blink
  LEADER + quorum -> solid
  lost quorum     -> fast blink

led.blink() runs in the background by itself, so on_change returns immediately.
"""
from pi_a.gpio import heart


def show_follower():
    print("LED: off (follower)")
    heart.off()


def show_candidate():
    print("LED: slow blink (candidate)")
    heart.blink(on_time=0.5, off_time=0.5)


def show_leader():
    print("LED: solid (leader with quorum)")
    heart.on()


def show_lost_quorum():
    print("LED: fast blink (lost quorum)")
    heart.blink(on_time=0.1, off_time=0.1)


def on_change(event, status):
    if event == "follower":
        show_follower()
    elif event == "candidate":
        show_candidate()
    elif event in ("leader", "quorum_restored"):
        show_leader()
    elif event == "lost_quorum":
        show_lost_quorum()
