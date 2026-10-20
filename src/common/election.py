import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from common.config import (
    ACKS_NEEDED, CAN_LEAD, CLUSTER_FILE, ELECTION_TIMEOUT_MAX, ELECTION_TIMEOUT_MIN,
    HEARTBEAT_INTERVAL, MAJORITY, QUORUM_TIMEOUT, QUORUM_WARNING, REQUEST_TIMEOUT,
    STATE_DIR, TICK_INTERVAL, VOTERS, peers_of,
)
from common.rpc import post_json
from common.storage import load_state, save_state

FOLLOWER = "FOLLOWER"
CANDIDATE = "CANDIDATE"
LEADER = "LEADER"


class Node:
    def __init__(self, name, event_log, on_change=None, can_lead=None):
        if name not in VOTERS:
            raise SystemExit(f"'{name}' is not a voter in {CLUSTER_FILE} "
                             f"(voters: {', '.join(VOTERS)})")
        self.name = name
        self.can_lead = CAN_LEAD[name] if can_lead is None else can_lead
        self.event_log = event_log
        self.on_change = on_change
        self.peers = peers_of(name)
        self.lock = threading.Lock()
        # one worker per peer so every request in a round goes out at once
        self.pool = ThreadPoolExecutor(max_workers=max(1, 2 * len(self.peers)))
        self.state_file = os.path.join(STATE_DIR, name + ".json")

        saved = load_state(self.state_file)
        self.current_term = saved["current_term"]
        self.voted_for = saved["voted_for"]

        self.state = FOLLOWER
        self.leader = None
        self.last_heartbeat = None
        self.votes_received = set()
        self.last_ack = {}
        self.quorum_lost = False
        self._reset_election_timer()

        self._log("STARTUP", f"loaded term {self.current_term}, voted_for {self.voted_for}")

    # ---------------------------------------------------------------- helpers

    def _log(self, event, details):
        self.event_log.log(event, self.current_term, details)

    def _save(self):
        """(lock held)"""
        save_state(self.state_file, self.current_term, self.voted_for)

    def _notify(self, event):
        """(lock held) on_change must return immediately - no sleeping in it."""
        if self.on_change:
            self.on_change(event, self._status_unlocked())

    def _reset_election_timer(self):
        """(lock held)"""
        self.election_deadline = time.monotonic() + random.uniform(
            ELECTION_TIMEOUT_MIN, ELECTION_TIMEOUT_MAX)

    def _become_follower(self, reason):
        """(lock held)"""
        was = self.state
        self.state = FOLLOWER
        self.votes_received = set()
        self.quorum_lost = False
        self._reset_election_timer()
        if was != FOLLOWER:
            self._log("STEPPED_DOWN", f"{was} -> FOLLOWER: {reason}")
            self._notify("follower")

    def _broadcast(self, path, payload):
        """POST payload to every peer in parallel. Yields (peer, reply) as replies
        arrive; reply is None when the peer didn't answer. Call WITHOUT the lock."""
        futures = {self.pool.submit(post_json, url + path, payload, REQUEST_TIMEOUT): peer
                   for peer, url in self.peers.items()}
        for future in as_completed(futures):
            yield futures[future], future.result()

    def _acks_within(self, window, now):
        """(lock held) how many peers acked a heartbeat in the last `window` seconds."""
        return sum(1 for t in self.last_ack.values() if now - t <= window)

    def _observe_newer_term(self, term, source):
        """Rule 0 (lock held): a newer term always wins."""
        self._log("TERM_UPDATED", f"{self.current_term} -> {term} (from {source})")
        self.current_term = term
        self.voted_for = None
        self.leader = None
        self._save()
        self._become_follower(f"newer term {term} from {source}")

    # ---------------------------------------------------------------- startup

    def start(self):
        threading.Thread(target=self._tick_loop, daemon=True).start()
        if self.can_lead:
            threading.Thread(target=self._leader_loop, daemon=True).start()

    # --------------------------------------------------------- incoming RPCs

    def handle_heartbeat(self, msg):
        term = msg.get("term")
        leader = msg.get("leader")
        if not isinstance(term, int) or not leader:
            with self.lock:
                return {"term": self.current_term, "success": False}

        with self.lock:
            if term < self.current_term:
                self._log("REJECTED_OLD_TERM",
                          f"heartbeat from {leader} term {term} < {self.current_term}")
                return {"term": self.current_term, "success": False}

            if term > self.current_term:
                self._observe_newer_term(term, leader)

            if self.state == LEADER:
                self._log("SPLIT_BRAIN", f"{leader} also claims leadership of term {term}")
                return {"term": self.current_term, "success": False}

            if self.state == CANDIDATE:
                self._become_follower(f"{leader} won term {term}")

            if self.leader != leader:
                self._log("LEADER_CHANGED", f"leader is now {leader}")
                self.leader = leader

            self.last_heartbeat = time.monotonic()
            self._reset_election_timer()
            return {"term": self.current_term, "success": True}

    def handle_request_vote(self, msg):
        term = msg.get("term")
        candidate = msg.get("candidate")
        if not isinstance(term, int) or not candidate:
            with self.lock:
                return {"term": self.current_term, "vote_granted": False}

        with self.lock:
            if term < self.current_term:
                self._log("REJECTED_OLD_TERM",
                          f"vote request from {candidate} term {term} < {self.current_term}")
                return {"term": self.current_term, "vote_granted": False}

            if term > self.current_term:
                self._observe_newer_term(term, candidate)

            if self.voted_for is None:
                self.voted_for = candidate
                self._save()                      # persist BEFORE replying
                self._log("VOTE_GRANTED", f"to {candidate}")
                self._reset_election_timer()
                return {"term": self.current_term, "vote_granted": True}

            if self.voted_for == candidate:
                self._log("VOTE_REPEATED", f"{candidate} asked again, same answer")
                self._reset_election_timer()
                return {"term": self.current_term, "vote_granted": True}

            self._log("VOTE_DENIED", f"{candidate}: already voted for {self.voted_for}")
            return {"term": self.current_term, "vote_granted": False}

    # ---------------------------------------------------------------- timers

    def _tick_loop(self):
        while True:
            self.tick()
            time.sleep(TICK_INTERVAL)

    def tick(self):
        should_elect = False
        with self.lock:
            now = time.monotonic()
            if self.state in (FOLLOWER, CANDIDATE):
                if self.can_lead and now > self.election_deadline:
                    should_elect = True
            elif self.state == LEADER:
                if self._acks_within(QUORUM_TIMEOUT, now) < ACKS_NEEDED:
                    self._log("QUORUM_TIMEOUT",
                              f"fewer than {ACKS_NEEDED} ack(s) for {QUORUM_TIMEOUT:.0f}s")
                    self.leader = None
                    self._become_follower("lost quorum")
                elif (self._acks_within(QUORUM_WARNING, now) < ACKS_NEEDED
                      and not self.quorum_lost):
                    self.quorum_lost = True
                    self._log("QUORUM_LOST",
                              f"fewer than {ACKS_NEEDED} ack(s) in {QUORUM_WARNING:.0f}s")
                    self._notify("lost_quorum")

        if should_elect:                 # outside the lock: it does network calls
            self._start_election()

    # -------------------------------------------------------------- election

    def _start_election(self):
        with self.lock:
            self.current_term += 1
            self.state = CANDIDATE
            self.voted_for = self.name
            self.leader = None
            self._save()
            self.votes_received = {self.name}
            self._reset_election_timer()
            my_term = self.current_term
            self._log("ELECTION_STARTED", "voted for self")
            self._notify("candidate")

        payload = {"term": my_term, "candidate": self.name}
        for peer, reply in self._broadcast("/request-vote", payload):
            with self.lock:
                if reply is None:
                    self._log("VOTE_NO_REPLY", peer)
                    continue
                if reply.get("term", 0) > self.current_term:
                    self._observe_newer_term(reply["term"], peer)
                    return
                if self.state != CANDIDATE or self.current_term != my_term:
                    return
                if reply.get("vote_granted"):
                    self.votes_received.add(peer)
                    self._log("VOTE_RECEIVED",
                              f"from {peer} ({len(self.votes_received)} of {len(VOTERS)})")
                    if len(self.votes_received) >= MAJORITY:
                        self._become_leader()
                        return
                else:
                    self._log("VOTE_REFUSED", peer)

    def _become_leader(self):
        """(lock held)"""
        self.state = LEADER
        self.leader = self.name
        now = time.monotonic()
        self.last_ack = {peer: now for peer in self.peers}
        self.quorum_lost = False
        self._log("BECAME_LEADER",
                  f"{len(self.votes_received)} votes: {sorted(self.votes_received)}")
        self._notify("leader")

    # ---------------------------------------------------------------- leader

    def _leader_loop(self):
        while True:
            start = time.monotonic()
            with self.lock:
                is_leader = self.state == LEADER
                my_term = self.current_term

            if is_leader:
                payload = {"term": my_term, "leader": self.name}
                for peer, reply in self._broadcast("/heartbeat", payload):
                    with self.lock:
                        if reply is None:
                            continue
                        if reply.get("term", 0) > self.current_term:
                            self._observe_newer_term(reply["term"], peer)
                            break
                        if self.state != LEADER or self.current_term != my_term:
                            break
                        if reply.get("success"):
                            now = time.monotonic()
                            self.last_ack[peer] = now
                            if (self.quorum_lost
                                    and self._acks_within(QUORUM_WARNING, now) >= ACKS_NEEDED):
                                self.quorum_lost = False
                                self._log("QUORUM_RESTORED", f"ack from {peer}")
                                self._notify("quorum_restored")

            time.sleep(max(0, HEARTBEAT_INTERVAL - (time.monotonic() - start)))

    def _has_quorum_unlocked(self):
        """(lock held)"""
        if self.state != LEADER:
            return False
        return self._acks_within(QUORUM_WARNING, time.monotonic()) >= ACKS_NEEDED

    def has_quorum(self):
        with self.lock:
            return self._has_quorum_unlocked()

    # ---------------------------------------------------------------- status

    def _status_unlocked(self):
        """(lock held)"""
        now = time.monotonic()
        return {
            "node": self.name,
            "role": "candidate" if self.can_lead else "witness",
            "can_lead": self.can_lead,
            "state": self.state,
            "term": self.current_term,
            "voted_for": self.voted_for,
            "leader": self.leader,
            "has_quorum": self._has_quorum_unlocked(),
            "voters": len(VOTERS),
            "majority": MAJORITY,
            "acks_needed": ACKS_NEEDED,
            "votes_received": sorted(self.votes_received),
            "seconds_since_heartbeat": (round(now - self.last_heartbeat, 1)
                                        if self.last_heartbeat is not None else None),
            "ack_ages": {p: round(now - t, 1) for p, t in self.last_ack.items()},
            "recent_events": self.event_log.recent(),
        }

    def status(self):
        with self.lock:
            return self._status_unlocked()
