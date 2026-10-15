"""pi-a LED patterns for Lab 5.

  FOLLOWER        -> off
  CANDIDATE       -> slow blink
  LEADER + quorum -> solid
  lost quorum     -> fast blink

Reuse the LED object from gpio.py (`from pi_a.gpio import heart`) - creating a
second LED(26) fails because the pin is already in use.

Tip: gpiozero's led.blink(on_time, off_time) runs in the background by itself,
so these can be one-liners and you don't need your own blink thread.
"""


def show_follower():
    """TODO: LED off."""
    raise NotImplementedError


def show_candidate():
    """TODO: slow blink (e.g. 0.5s on / 0.5s off)."""
    raise NotImplementedError


def show_leader():
    """TODO: solid on."""
    raise NotImplementedError


def show_lost_quorum():
    """TODO: fast blink (e.g. 0.1s on / 0.1s off)."""
    raise NotImplementedError


def on_change(event, status):
    """Node calls this on every state change. TODO: map event -> one of the functions above.
    events: "follower", "candidate", "leader", "lost_quorum", "quorum_restored"
    """
    raise NotImplementedError
