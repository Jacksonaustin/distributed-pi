"""Leader election logic shared by pi-a, pi-b and the witness.

One Node object per process. Flask routes call the handle_* methods;
background threads call tick() and the leader heartbeat loop.

Thread safety: one lock around all fields. NEVER hold it during a network
call - snapshot what you need, release, send, re-acquire, then re-check that
term/state haven't changed before acting on the reply.
"""

FOLLOWER = "FOLLOWER"
CANDIDATE = "CANDIDATE"
LEADER = "LEADER"


class Node:
    def __init__(self, name, can_lead, event_log, on_change=None):
        """Set up the node.

        TODO fields:
          name, can_lead (False for witness), peers (config.peers_of(name))
          lock
          current_term, voted_for  <- loaded from storage (state/<name>.json)
          state = FOLLOWER, leader = None
          election_deadline (randomized, see _reset_election_timer)
          votes_received = set()
          last_ack = {}            # peer -> time.monotonic() of last successful heartbeat ack
          quorum_lost_warned = False
          event_log, on_change     # on_change(event, node_status) drives LED/buzzer
        """
        raise NotImplementedError

    # ---------------------------------------------------------------- startup

    def start(self):
        """TODO: start the tick thread, and (if can_lead) the leader heartbeat thread. Both daemon."""
        raise NotImplementedError

    # --------------------------------------------------------- incoming RPCs

    def handle_heartbeat(self, msg):
        """POST /heartbeat  msg = {term, leader}  ->  {term, success}

        TODO:
          - validate fields (bad -> success False)
          - term < mine  -> log REJECTED_OLD_TERM, return {term: mine, success: False}
          - term > mine  -> _observe_newer_term(...)
          - same term & I'm CANDIDATE -> become FOLLOWER (someone else won)
          - record leader (log LEADER_CHANGED if different), reset election timer
          - return {term: mine, success: True}
        """
        raise NotImplementedError

    def handle_request_vote(self, msg):
        """POST /request-vote  msg = {term, candidate}  ->  {term, vote_granted}

        TODO:
          - validate fields
          - term < mine  -> log REJECTED_OLD_TERM, deny
          - term > mine  -> _observe_newer_term(...)
          - grant if voted_for is None or voted_for == candidate
              (same candidate asking twice gets "yes" again - that's the duplicate test)
          - on grant: voted_for = candidate, SAVE, reset election timer, log VOTE_GRANTED
          - on deny: log VOTE_DENIED with the reason
        """
        raise NotImplementedError

    # ------------------------------------------------------------ term rules

    def _observe_newer_term(self, term, reason):
        """Rule 0 - call with the lock held, for requests AND responses.

        TODO: current_term = term, voted_for = None, SAVE, become FOLLOWER (if not already),
              log STEPPED_DOWN / TERM_UPDATED with the reason.
        """
        raise NotImplementedError

    # ---------------------------------------------------------------- timers

    def _reset_election_timer(self):
        """TODO: election_deadline = now + random.uniform(ELECTION_TIMEOUT_MIN, ELECTION_TIMEOUT_MAX)"""
        raise NotImplementedError

    def _tick_loop(self):
        """TODO: forever: self.tick(); sleep(TICK_INTERVAL)"""
        raise NotImplementedError

    def tick(self):
        """Check the clock and change state if a timer expired.

        TODO:
          - FOLLOWER/CANDIDATE, can_lead, past election_deadline -> _start_election()
          - LEADER: seconds since newest ack
              > QUORUM_WARNING (first time) -> log QUORUM_LOST, on_change("lost_quorum")
              > QUORUM_TIMEOUT              -> step down to FOLLOWER, log STEPPED_DOWN
        Remember: don't call _start_election while holding the lock if it does network calls.
        """
        raise NotImplementedError

    # -------------------------------------------------------------- election

    def _start_election(self):
        """Become candidate and ask for votes.

        TODO:
          1. (lock) term += 1, state = CANDIDATE, voted_for = me, SAVE,
             votes_received = {me}, reset timer, log ELECTION_STARTED, on_change("candidate")
             snapshot the term you're campaigning in
          2. (no lock) post_json each peer's /request-vote with {term, candidate}
             - parallel threads are nicer, sequential with 0.5s timeouts also works
          3. (lock) for each reply:
               - reply None -> skip
               - reply term > mine -> _observe_newer_term, stop
               - still CANDIDATE in the same term and vote_granted -> votes_received.add(peer)
          4. len(votes_received) >= MAJORITY -> _become_leader()
        """
        raise NotImplementedError

    def _become_leader(self):
        """TODO (lock held): state = LEADER, leader = me, last_ack = {now for each peer}
        so you start with quorum, log BECAME_LEADER (term + vote count), on_change("leader")."""
        raise NotImplementedError

    # ---------------------------------------------------------------- leader

    def _leader_loop(self):
        """Every HEARTBEAT_INTERVAL while LEADER, send heartbeats.

        TODO:
          - (lock) if not LEADER -> just sleep and continue; else snapshot term
          - (no lock) post_json each peer's /heartbeat with {term, leader: me}
          - (lock) for each reply:
               - None -> no ack
               - reply term > mine -> _observe_newer_term (step down)
               - success -> last_ack[peer] = now; if we had lost quorum, log QUORUM_RESTORED
          - sleep the remainder of the interval (same trick as Lab 4)
        """
        raise NotImplementedError

    def has_quorum(self):
        """TODO: LEADER and any peer acked within QUORUM_WARNING (self + 1 ack = 2 of 3)."""
        raise NotImplementedError

    # ---------------------------------------------------------------- status

    def status(self):
        """TODO: {node, state, term, voted_for, leader, has_quorum, can_lead,
                  seconds_since_heartbeat / last_ack, recent_events}"""
        raise NotImplementedError
