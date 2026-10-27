import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from common.config import (
    CLUSTER_FILE, ELECTION_TIMEOUT_MAX, ELECTION_TIMEOUT_MIN, HEARTBEAT_INTERVAL,
    QUORUM_TIMEOUT, QUORUM_WARNING, REQUEST_TIMEOUT, STATE_DIR, TICK_INTERVAL,
)
from common.membership import VOTING_ROLES, Membership, validate_member
from common.rpc import get_json, post_json
from common.storage import load_state, save_state

FOLLOWER = "FOLLOWER"
CANDIDATE = "CANDIDATE"
LEADER = "LEADER"

# After a valid heartbeat (or at startup) a voter refuses to help elect a new
# leader for this long - the current leader may still be acting as leader.
# This is what guarantees only one authorized leader at a time (see config.py).
LEADER_LEASE = ELECTION_TIMEOUT_MIN


class Node:
    def __init__(self, name, event_log, on_change=None, role=None):
        """`role` is only used while this node is waiting to join; once it is
        in the member list, its role comes from there."""
        self.members = Membership(CLUSTER_FILE)
        if not self.members.has(name) and role is None:
            raise SystemExit(f"'{name}' is not in {CLUSTER_FILE} "
                             f"(members: {', '.join(self.members.members)}). "
                             f"Use --join to ask the cluster to add it.")
        self.name = name
        self.join_role = role
        self.event_log = event_log
        self.on_change = on_change
        self.lock = threading.Lock()
        # enough workers for one round of requests to every member at once
        self.pool = ThreadPoolExecutor(max_workers=16)
        self.state_file = os.path.join(STATE_DIR, name + ".json")

        saved = load_state(self.state_file)
        self.current_term = saved["current_term"]
        self.voted_for = saved["voted_for"]

        self.state = FOLLOWER
        self.leader = None
        self.last_heartbeat = None
        self.votes_received = set()
        self.last_ack = {}
        self.peer_config = {}       # peer -> member-list id it last acked (leader only)
        self.pending_change = None  # voter change not yet acked by a majority (leader only)
        self.quorum_lost = False
        # a restarted voter can't know whether a leader is alive, so it assumes one is
        self.lease_until = time.monotonic() + LEADER_LEASE
        self._reset_election_timer()

        self._log("STARTUP", f"loaded term {self.current_term}, voted_for {self.voted_for}, "
                             f"role {self.role}, member list v{self._config_label()}")

    # ---------------------------------------------------------------- helpers

    @property
    def active(self):
        """(lock held) True once this node is in the member list."""
        return self.members.has(self.name)

    @property
    def role(self):
        """(lock held)"""
        return self.members.role(self.name) if self.active else self.join_role

    @property
    def can_lead(self):
        """(lock held) Only an active candidate may run for leader."""
        return self.active and self.role == "candidate"

    def _config_label(self):
        """(lock held) e.g. "3.7" for config_term 3, config_version 7."""
        return "{}.{}".format(*self.members.config_id)

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

    def _broadcast(self, path, payload, targets):
        """POST payload to every target {name: url} in parallel. Yields (name, reply)
        as replies arrive; reply is None when the peer didn't answer. Call WITHOUT the lock."""
        futures = {self.pool.submit(post_json, url + path, payload, REQUEST_TIMEOUT): peer
                   for peer, url in targets.items()}
        for future in as_completed(futures):
            yield futures[future], future.result()

    def _acks_within(self, window, now):
        """(lock held) how many VOTERS acked a heartbeat in the last `window` seconds.
        Followers' acks don't count - they aren't part of the majority."""
        return sum(1 for peer, t in self.last_ack.items()
                   if self.members.is_voter(peer) and now - t <= window)

    def _observe_newer_term(self, term, source):
        """Rule 0 (lock held): a newer term always wins."""
        self._log("TERM_UPDATED", f"{self.current_term} -> {term} (from {source})")
        self.current_term = term
        self.voted_for = None
        self.leader = None
        self._save()
        self._become_follower(f"newer term {term} from {source}")

    def _adopt_member_list(self, snapshot, source):
        """(lock held) Take a newer member list from the leader's heartbeat."""
        try:
            new_id = (int(snapshot["config_term"]), int(snapshot["config_version"]))
            names = [m["name"] for m in snapshot["members"]]
        except (KeyError, TypeError, ValueError):
            return
        if new_id <= self.members.config_id:
            return
        was_active = self.active
        summary = self.members.replace(snapshot)
        self._log("MEMBERSHIP_UPDATED", f"member list v{self._config_label()} from {source}: "
                                        f"{summary}; majority now {self.members.majority()}")
        if self.name not in names and was_active:
            self._log("REMOVED_FROM_CLUSTER", "this node was removed; it will no longer "
                                              "vote or run for leader")
            self.leader = None
            self._become_follower("removed from the cluster")
        elif self.name in names and not was_active:
            self._log("JOINED_CLUSTER", f"joined as {self.role}")

    # ---------------------------------------------------------------- startup

    def start(self):
        threading.Thread(target=self._tick_loop, daemon=True).start()
        threading.Thread(target=self._leader_loop, daemon=True).start()

    # --------------------------------------------------------- incoming RPCs

    def _invalid(self, kind, msg, reason, reply_key):
        """Reject a malformed message (or one from a member that may not send it)."""
        with self.lock:
            self._log("REJECTED_INVALID", f"{kind} {msg}: {reason}")
            return {"term": self.current_term, reply_key: False}

    def _grant_lease(self):
        """(lock held) After voting, back that candidate as if it were leader.
        A new leader counts its voters as fresh contact for QUORUM_TIMEOUT, so each
        of those voters must refuse to help elect anyone else for at least that long -
        even if the new leader is cut off before its first heartbeat arrives."""
        self.lease_until = time.monotonic() + LEADER_LEASE
        self._reset_election_timer()

    def _leader_alive(self, now):
        """(lock held) True while this voter believes a leader may still be acting."""
        return self.state == LEADER or now < self.lease_until

    def _reply_config(self):
        """(lock held) Sent back with every ack so the leader knows which list we have."""
        return {"config_term": self.members.config_id[0],
                "config_version": self.members.config_id[1]}

    def handle_heartbeat(self, msg):
        term = msg.get("term")
        leader = msg.get("leader")
        if not isinstance(term, int) or isinstance(term, bool) or term < 0:
            return self._invalid("heartbeat", msg, "term must be a whole number", "success")
        if not isinstance(leader, str) or leader == self.name:
            return self._invalid("heartbeat", msg, f"{leader!r} cannot be leader", "success")

        with self.lock:
            if term < self.current_term:
                self._log("REJECTED_OLD_TERM",
                          f"heartbeat from {leader} term {term} < {self.current_term}")
                return {"term": self.current_term, "success": False, **self._reply_config()}

            # The leader's member list comes first: it may add the leader itself,
            # or remove this node.
            config = msg.get("config")
            if isinstance(config, dict):
                self._adopt_member_list(config, leader)
            if not self.members.is_candidate(leader):
                self._log("REJECTED_INVALID", f"heartbeat from {leader}: not a candidate "
                                              f"in member list v{self._config_label()}")
                return {"term": self.current_term, "success": False, **self._reply_config()}

            if term > self.current_term:
                self._observe_newer_term(term, leader)

            if self.state == LEADER:
                self._log("SPLIT_BRAIN", f"{leader} also claims leadership of term {term}")
                return {"term": self.current_term, "success": False, **self._reply_config()}

            if self.state == CANDIDATE:
                self._become_follower(f"{leader} won term {term}")

            if self.leader != leader:
                self._log("LEADER_CHANGED", f"leader is now {leader}")
                self.leader = leader

            now = time.monotonic()
            self.last_heartbeat = now
            self.lease_until = now + LEADER_LEASE
            self._reset_election_timer()
            return {"term": self.current_term, "success": True, **self._reply_config()}

    def handle_request_vote(self, msg):
        term = msg.get("term")
        candidate = msg.get("candidate")
        if not isinstance(term, int) or isinstance(term, bool) or term < 0:
            return self._invalid("vote request", msg, "term must be a whole number", "vote_granted")
        if not isinstance(candidate, str) or candidate == self.name:
            return self._invalid("vote request", msg, f"{candidate!r} cannot be leader",
                                 "vote_granted")
        try:
            candidate_config = (int(msg.get("config_term", 0)), int(msg.get("config_version", 0)))
        except (TypeError, ValueError):
            return self._invalid("vote request", msg, "bad member-list version", "vote_granted")

        with self.lock:
            if not self.active or self.role not in VOTING_ROLES:
                self._log("REJECTED_NOT_VOTER", f"vote request from {candidate}: this node is "
                                                f"a {self.role or 'non-member'} and doesn't vote")
                return {"term": self.current_term, "vote_granted": False}

            if term < self.current_term:
                self._log("REJECTED_OLD_TERM",
                          f"vote request from {candidate} term {term} < {self.current_term}")
                return {"term": self.current_term, "vote_granted": False}

            if not self.members.is_candidate(candidate):
                self._log("REJECTED_INVALID", f"vote request from {candidate}: not a candidate "
                                              f"in member list v{self._config_label()}")
                return {"term": self.current_term, "vote_granted": False}

            # Safety: while a leader may still be acting, a request to start a new
            # term is not a valid message - adopting its term would let a second
            # leader be elected before the first one has stepped down.
            now = time.monotonic()
            if term > self.current_term and candidate != self.leader and self._leader_alive(now):
                who = self.name if self.state == LEADER else (self.leader or "a leader")
                self._log("REJECTED_LEADER_ALIVE",
                          f"vote request from {candidate} term {term}: {who} may still be "
                          f"leading (lease {max(0.0, self.lease_until - now):.1f}s left)")
                return {"term": self.current_term, "vote_granted": False}

            if term > self.current_term:
                self._observe_newer_term(term, candidate)

            # A new leader must know the newest member list, or it could undo a
            # change a majority already has.
            if candidate_config < self.members.config_id:
                self._log("VOTE_DENIED", "{}: its member list v{}.{} is older than v{}".format(
                    candidate, *candidate_config, self._config_label()))
                return {"term": self.current_term, "vote_granted": False}

            if self.voted_for is None:
                self.voted_for = candidate
                self._save()                      # persist BEFORE replying
                self._log("VOTE_GRANTED", f"to {candidate}")
                self._grant_lease()
                return {"term": self.current_term, "vote_granted": True}

            if self.voted_for == candidate:
                # same request again: same answer, and it is still only one vote
                self._log("VOTE_REPEATED", f"{candidate} asked again in term {term}; "
                                           f"vote already counted, not voting twice")
                self._grant_lease()
                return {"term": self.current_term, "vote_granted": True}

            self._log("VOTE_DENIED", f"{candidate}: already voted for {self.voted_for} "
                                     f"in term {self.current_term}")
            return {"term": self.current_term, "vote_granted": False}

    # ------------------------------------------------------ membership changes

    def _not_leader_reply(self):
        """(lock held)"""
        leader = self.leader
        return 409, {"error": "not the leader", "leader": leader,
                     "leader_url": self.members.url(leader) if self.members.has(leader) else None}

    def join(self, name, url, role):
        """POST /join on the leader. Adds a member, or updates a member's address.
        Returns (http_status, reply)."""
        error = validate_member(name, url, role)
        if error:
            return 400, {"error": error}
        url = url.rstrip("/")

        with self.lock:
            if self.state != LEADER:
                return self._not_leader_reply()
            if self.members.has(name):
                current = self.members.members[name]
                if current["role"] != role:
                    return 400, {"error": f"{name} is already a {current['role']}; "
                                          f"remove it before joining with another role"}
                if current["url"] == url:
                    return 200, {"ok": True, "detail": f"{name} is already a member",
                                 "config": self.members.snapshot()}
            taken = [n for n, m in self.members.members.items() if m["url"] == url and n != name]
            if taken:
                return 400, {"error": f"{url} already belongs to {taken[0]}"}
            if role in VOTING_ROLES and not self.members.has(name) and self.pending_change:
                return 409, {"error": "another voter change is still being confirmed by a "
                                      "majority; try again in a few seconds"}

        # The new member must already be running, or adding a voter could leave
        # the cluster without a majority.
        status = get_json(url + "/status", timeout=1.5)
        if not status or status.get("node") != name:
            return 400, {"error": f"can't reach {name} at {url}/status - start it first"}

        with self.lock:
            if self.state != LEADER:          # lost leadership while we checked
                return self._not_leader_reply()
            is_new = not self.members.has(name)
            if role in VOTING_ROLES and is_new and self.pending_change:
                return 409, {"error": "another voter change is still being confirmed; try again"}
            self.members.set_member(self.current_term, name, url, role)
            if is_new:
                self._log("MEMBER_JOINED", f"{name} joined as {role} at {url}; member list "
                                           f"v{self._config_label()}, majority now "
                                           f"{self.members.majority()}")
            else:
                self._log("MEMBER_UPDATED", f"{name} moved to {url}; member list "
                                            f"v{self._config_label()}")
            if role in VOTING_ROLES and is_new:
                self.pending_change = self.members.config_id
            return 200, {"ok": True, "config": self.members.snapshot(),
                         "majority": self.members.majority()}

    def leave(self, name):
        """POST /leave on the leader. Returns (http_status, reply)."""
        with self.lock:
            if self.state != LEADER:
                return self._not_leader_reply()
            if not self.members.has(name):
                return 404, {"error": f"{name} is not a member"}
            if name == self.name:
                return 400, {"error": f"{name} is the leader; stop it so another node takes "
                                      f"over, then remove it from the new leader"}
            role = self.members.role(name)
            if role in VOTING_ROLES:
                if self.pending_change:
                    return 409, {"error": "another voter change is still being confirmed by a "
                                          "majority; try again in a few seconds"}
                if len(self.members.voters()) <= 1:
                    return 400, {"error": "can't remove the last voter"}
            url = self.members.url(name)
            self.members.remove(self.current_term, name)
            self.last_ack.pop(name, None)
            self.peer_config.pop(name, None)
            if role in VOTING_ROLES:
                self.pending_change = self.members.config_id
            self._log("MEMBER_REMOVED", f"{name} ({role}) removed; member list "
                                        f"v{self._config_label()}, majority now "
                                        f"{self.members.majority()}")
            # Tell the removed node once, so it stops voting and running for leader.
            goodbye = {"term": self.current_term, "leader": self.name,
                       "config": self.members.snapshot()}
            self.pool.submit(post_json, url + "/heartbeat", goodbye, REQUEST_TIMEOUT)
            return 200, {"ok": True, "config": self.members.snapshot(),
                         "majority": self.members.majority()}

    def _check_change_committed(self):
        """(lock held, leader) A voter change is confirmed once a majority of the
        NEW voters (counting the leader) have acked a heartbeat carrying it."""
        if not self.pending_change:
            return
        have_it = 1 + sum(1 for peer in self.members.voter_peers_of(self.name)
                          if self.peer_config.get(peer, (0, 0)) >= self.pending_change)
        if have_it >= self.members.majority():
            self._log("MEMBERSHIP_COMMITTED", "member list v{}.{} confirmed by {} of {} "
                      "voters".format(*self.pending_change, have_it, len(self.members.voters())))
            self.pending_change = None

    # ---------------------------------------------------------------- timers

    def _guarded(self, what, fn):
        """Run one loop round; log an unexpected error instead of letting it kill the thread."""
        try:
            fn()
        except Exception as e:                     # noqa: BLE001 - keep the node alive
            self._log("LOOP_ERROR", f"{what}: {type(e).__name__}: {e}")

    def _tick_loop(self):
        while True:
            self._guarded("tick", self.tick)
            time.sleep(TICK_INTERVAL)

    def tick(self):
        should_elect = False
        with self.lock:
            now = time.monotonic()
            needed = self.members.acks_needed()
            if self.state in (FOLLOWER, CANDIDATE):
                if self.can_lead and now > self.election_deadline:
                    should_elect = True
            elif self.state == LEADER:
                if self._acks_within(QUORUM_TIMEOUT, now) < needed:
                    self._log("QUORUM_TIMEOUT",
                              f"fewer than {needed} ack(s) for {QUORUM_TIMEOUT:.0f}s")
                    self.leader = None
                    self._become_follower("lost quorum")
                elif self._acks_within(QUORUM_WARNING, now) < needed and not self.quorum_lost:
                    self.quorum_lost = True
                    self._log("QUORUM_LOST",
                              f"fewer than {needed} ack(s) in {QUORUM_WARNING:.0f}s")
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
            voters = self.members.voter_peers_of(self.name)
            majority = self.members.majority()
            total = len(self.members.voters())
            payload = {"term": my_term, "candidate": self.name, **self._reply_config()}
            self._log("ELECTION_STARTED", f"voted for self; need {majority} of {total} votes")
            self._notify("candidate")

        if len(self.votes_received) >= majority:          # a one-voter cluster
            with self.lock:
                if self.state == CANDIDATE and self.current_term == my_term:
                    self._become_leader()
            return

        for peer, reply in self._broadcast("/request-vote", payload, voters):
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
                              f"from {peer} ({len(self.votes_received)} of {total})")
                    if len(self.votes_received) >= majority:
                        self._become_leader()
                        return
                else:
                    self._log("VOTE_REFUSED", peer)

    def _become_leader(self):
        """(lock held)"""
        self.state = LEADER
        self.leader = self.name
        now = time.monotonic()
        # the voters that just granted votes count as fresh contact; nobody else does
        self.last_ack = {peer: now for peer in self.votes_received if peer != self.name}
        self.peer_config = {}
        # A new leader can't tell whether its member list reached a majority yet,
        # so it treats it as unconfirmed until enough voters ack it.
        self.pending_change = self.members.config_id
        self.quorum_lost = False
        self._log("BECAME_LEADER",
                  f"{len(self.votes_received)} votes: {sorted(self.votes_received)}")
        self._notify("leader")

    # ---------------------------------------------------------------- leader

    def _leader_loop(self):
        while True:
            start = time.monotonic()
            self._guarded("heartbeat round", self._heartbeat_round)
            time.sleep(max(0, HEARTBEAT_INTERVAL - (time.monotonic() - start)))

    def _heartbeat_round(self):
        """One round of heartbeats, if this node is the leader."""
        with self.lock:
            is_leader = self.state == LEADER
            my_term = self.current_term
            targets = self.members.peers_of(self.name)
            payload = {"term": my_term, "leader": self.name,
                       "config": self.members.snapshot()}

        if is_leader:
            for peer, reply in self._broadcast("/heartbeat", payload, targets):
                with self.lock:
                    if reply is None:
                        continue
                    if reply.get("term", 0) > self.current_term:
                        self._observe_newer_term(reply["term"], peer)
                        break
                    if self.state != LEADER or self.current_term != my_term:
                        break
                    if not self.members.has(peer):        # removed meanwhile
                        continue
                    if reply.get("success"):
                        now = time.monotonic()
                        self.last_ack[peer] = now
                        self.peer_config[peer] = (int(reply.get("config_term", 0)),
                                                  int(reply.get("config_version", 0)))
                        self._check_change_committed()
                        if (self.quorum_lost and self._acks_within(QUORUM_WARNING, now)
                                >= self.members.acks_needed()):
                            self.quorum_lost = False
                            self._log("QUORUM_RESTORED", f"ack from {peer}")
                            self._notify("quorum_restored")

    def _has_quorum_unlocked(self):
        """(lock held)"""
        if self.state != LEADER:
            return False
        return self._acks_within(QUORUM_WARNING, time.monotonic()) >= self.members.acks_needed()

    def has_quorum(self):
        with self.lock:
            return self._has_quorum_unlocked()

    # ---------------------------------------------------------------- status

    def _status_unlocked(self):
        """(lock held)"""
        now = time.monotonic()
        has_quorum = self._has_quorum_unlocked()
        if self.state == LEADER:
            quorum_status = "HAS_QUORUM" if has_quorum else "LOST_QUORUM"
        else:
            quorum_status = "NOT_LEADER"
        return {
            "node": self.name,
            "role": self.role,
            "active": self.active,
            "can_lead": self.can_lead,
            "state": self.state,
            "term": self.current_term,
            "voted_for": self.voted_for,
            "leader": self.leader,
            "has_quorum": has_quorum,
            "quorum_status": quorum_status,
            "leader_lease_seconds": round(max(0.0, self.lease_until - now), 1),
            "member_list_version": self._config_label(),
            "pending_change": ("{}.{}".format(*self.pending_change)
                               if self.pending_change else None),
            "members": self.members.snapshot()["members"],
            "voters": len(self.members.voters()),
            "majority": self.members.majority(),
            "acks_needed": self.members.acks_needed(),
            "votes_received": sorted(self.votes_received),
            "seconds_since_heartbeat": (round(now - self.last_heartbeat, 1)
                                        if self.last_heartbeat is not None else None),
            "ack_ages": {p: round(now - t, 1) for p, t in self.last_ack.items()},
            "recent_events": self.event_log.recent(),
        }

    def status(self):
        with self.lock:
            return self._status_unlocked()

    def adopt_member_list(self, snapshot, source):
        """Take the member list returned by the leader when our join was accepted."""
        with self.lock:
            self._adopt_member_list(snapshot, source)

    def member_urls(self):
        """{name: url} for every member, for the dashboard."""
        with self.lock:
            return {n: m["url"] for n, m in self.members.members.items()}

    def member_list(self):
        """GET /members: the current list plus who the leader is."""
        with self.lock:
            return {**self.members.snapshot(), "leader": self.leader,
                    "leader_url": (self.members.url(self.leader)
                                   if self.leader and self.members.has(self.leader) else None)}
