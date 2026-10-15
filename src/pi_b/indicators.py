"""pi-b buzzer patterns for Lab 5.

  became LEADER     -> two short beeps
  LEADER + quorum   -> one short chirp every 5 seconds (continuous)
  FOLLOWER          -> silent
  became CANDIDATE  -> one short beep
  lost quorum       -> three short beeps

One-shot sounds come from events; the 5s chirp comes from the current state,
so it needs its own loop (same idea as Lab 4's buzzer_loop). Never play sounds
inside on_change directly - it's called from Node threads, and sleeping there
would stall elections. Set a flag / queue, and let the buzzer thread play it.

Reuse the buzzer object from gpio.py (`from pi_b.gpio import buzzer`).
"""


def beep(times, on=0.1, off=0.1):
    """TODO: buzzer on/off `times` times, with a gap between beeps."""
    raise NotImplementedError


def on_change(event, status):
    """Node calls this on state changes. TODO: queue the right one-shot sound.
    events: "follower", "candidate", "leader", "lost_quorum", "quorum_restored"
    """
    raise NotImplementedError


def buzzer_loop(get_status):
    """Background thread.

    TODO forever:
      - play any queued one-shot sound
      - if get_status() says LEADER with quorum and 5s since last chirp -> chirp
      - else sleep briefly
    """
    raise NotImplementedError
