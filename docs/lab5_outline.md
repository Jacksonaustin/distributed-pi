# Lab 5 Outline: Leader Election with a Witness

Lab 4 code is left untouched (commit `d0b857f`). Lab 5 lives in new files next to it.

## Architecture

Three voters. Both Pis run the same election logic and differ only in hardware.

| Voter | Can lead? | Hardware | Entry point | Port |
|---|---|---|---|---|
| pi-a | yes | LED (GPIO26) | `python -m pi_a.lab5_app` | 5001 |
| pi-b | yes | buzzer (GPIO17) | `python -m pi_b.lab5_app` | 5002 |
| witness | no, only votes | none | `python -m witness.app` | 5003 |

Majority = 3 // 2 + 1 = **2**.

## File map

| File | Purpose |
|---|---|
| `src/common/config.py` | voter names and URLs, majority, all timing constants |
| `src/common/election.py` | `Node` class: state, term rules, voting, elections, leader heartbeats, quorum |
| `src/common/storage.py` | save and load `current_term` and `voted_for` to disk |
| `src/common/event_log.py` | shared event log (file and in memory) |
| `src/common/rpc.py` | `post_json()` helper for heartbeats and vote requests |
| `src/pi_a/lab5_app.py` | Flask routes and wiring the LED to state changes |
| `src/pi_a/indicators.py` | LED patterns: off / slow blink / solid / fast blink |
| `src/pi_b/lab5_app.py` | Flask routes and wiring the buzzer to state changes |
| `src/pi_b/indicators.py` | buzzer patterns: beeps, chirps, silence |
| `src/witness/app.py` | Flask routes; a `Node` that can never lead |

## Node state

**Persisted** (`state/<node>.json`):
- `current_term`
- `voted_for`

**In memory**:
- `state` (FOLLOWER / CANDIDATE / LEADER), always FOLLOWER at startup
- `leader`
- `last_heartbeat` (follower), `election_deadline` (randomized)
- `votes_received` (a set of voter names, so duplicates can't count twice)
- `last_ack[peer]` (leader)

## Messages

| Endpoint | Request | Response |
|---|---|---|
| `POST /heartbeat` | `{term, leader}` | `{term, success}`, which counts as the ack |
| `POST /request-vote` | `{term, candidate}` | `{term, vote_granted}` |
| `GET /status` | – | `{node, state, term, voted_for, leader, has_quorum, ...events}` |

## Rules checklist

- [ ] **Rule 0, newer term** (any request *or response*): adopt it, clear `voted_for`, become FOLLOWER, save.
- [ ] **Older term**: reject, log `REJECTED_OLD_TERM`, reply with my term.
- [ ] **Follower**: valid heartbeat → record leader, reset the election timer, ack.
- [ ] **Election timeout**: `term += 1`, CANDIDATE, vote for self, save, request votes from the other two.
- [ ] **Votes ≥ 2** → LEADER and send heartbeats right away.
- [ ] **Candidate sees a heartbeat with term ≥ mine** → FOLLOWER.
- [ ] **Grant a vote** only if the term is OK and `voted_for` is empty or the same candidate. Save before replying.
- [ ] **Leader**: heartbeat every 1s and record acks.
- [ ] **Leader with no ack for `QUORUM_WARNING`** → lost-quorum indicator (still leader).
- [ ] **Leader with no ack for 5s** → step down to FOLLOWER.
- [ ] Never hold the lock during network calls; re-check term and state after each reply.

## Timing (see `config.py`)

- Heartbeat interval: 1s
- Election timeout: random between 6 and 9s, new value on every reset (prevents repeated split votes)
- Quorum warning: 2s with no ack (*our choice; state it in the report*)
- Quorum loss → step down: 5s (required by the lab)
- HTTP request timeout: 0.5s
- Leader lease: after a valid heartbeat (or at startup), a voter refuses vote requests for a **new** term for 6s, logged as `REJECTED_LEADER_ALIVE`.

### Why the election timeout is 6–9s and not shorter (the safety requirement)

The handout requires that *"only one Raspberry Pi may be the authorized leader at a time."* A cut-off leader keeps acting as leader for up to 5s, until its quorum check fails. If the other Pi could be elected sooner than that, both would be leader at once. So:

1. A new leader needs a vote from a voter that hasn't heard the old leader for at least 6s (the lease).
2. That means the old leader hasn't received an ack from that voter for at least 6 − 0.5 = 5.5s, longer than its 5s quorum timeout.
3. So the old leader has always stepped down **before** the new one can be elected.

`config.py` checks this with `assert ELECTION_TIMEOUT_MIN > QUORUM_TIMEOUT + REQUEST_TIMEOUT + TICK_INTERVAL`. A simulated test with partial cuts, an isolated leader and reconnection found no moment with two leaders.

## Hardware mapping

| State / event | pi-a LED | pi-b buzzer |
|---|---|---|
| FOLLOWER | off | silent |
| became CANDIDATE | slow blink | one short beep |
| became LEADER | solid | two short beeps |
| LEADER with quorum | solid | one chirp every 5s |
| LEADER, lost quorum | fast blink | three short beeps |

LED solid **and** buzzer chirping at the same time means both Pis think they're leader, which is a failure to investigate.

## Build order

1. [ ] `config.py` values and `peers_of()`
2. [ ] `storage.py`, then test save/load by hand
3. [ ] `event_log.py` (move the Lab 4 `log_event` idea here)
4. [ ] `rpc.py` `post_json()`
5. [ ] `election.py`: term rules → vote handler → heartbeat handler → tick loop → elections → leader loop → quorum
6. [ ] `witness/app.py`, then test `/request-vote` with curl
7. [ ] Both `lab5_app.py` files, with indicators as `print()` only
8. [ ] Run all three on the laptop (mock GPIO) and get an election working
9. [ ] Real indicators, deploy to the Pis, run the tests below

## Running it

See [lab5_running.md](lab5_running.md) for laptop and Pi commands, cluster files, adding voters, and the dashboard.

## Test plan

Record for each test: predicted result, observed result, elected leader, term, votes received, time to elect, LED and buzzer behavior, and event-log entries.

| # | Test | Prediction | Observed | Leader | Term | Votes | Time to elect |
|---|---|---|---|---|---|---|---|
| 1 | Start all three voters | One Pi wins with 2–3 votes, about 6–9s after startup | | | | | |
| 2 | Start both Pis together | Possible split vote; random timeouts settle it | | | | | |
| 3 | Stop the follower | Leader keeps quorum through the witness; no election | | | | | |
| 4 | Stop the leader | Follower wins (self + witness), term + 1, about 6–9s after the stop | | | | | |
| 5 | Restart the former leader | Loads its term, stays FOLLOWER | | | | | |
| 6 | Stop the witness | Leader keeps quorum through the other Pi | | | | | |
| 7 | Isolate one Pi | Isolated **leader**: fast blink / 3 beeps at 2s, steps down at 5s, then the other Pi wins (no overlap). Isolated **follower**: its vote requests get `REJECTED_LEADER_ALIVE`; the leader stays leader. The isolated Pi's term keeps rising | | | | | |
| 8 | Restore the isolated Pi | Its higher term reaches the leader in a heartbeat reply, so the leader steps down and a new election runs | | | | | |
| 9 | Duplicate vote request | Same answer both times; counted once (`VOTE_REPEATED` or `VOTE_DENIED`) | | | | | |
| 10 | Old-term heartbeat | Rejected and logged (`REJECTED_OLD_TERM`); reply has the current term | | | | | |
| 11 | Restart a voter after voting | Reloads `voted_for`; refuses another candidate this term | | | | | |

Manual messages for tests 9 and 10:

```bash
curl -X POST http://localhost:5003/request-vote -H "Content-Type: application/json" -d '{"term": 5, "candidate": "pi-a"}'
```

```bash
curl -X POST http://localhost:5002/heartbeat -H "Content-Type: application/json" -d '{"term": 1, "leader": "pi-a"}'
```

## Report checklist

Required by the handout (page 3):

- [ ] All Flask application and witness source code
- [ ] LaTeX-generated PDF listing your name, lab information, date and class
- [ ] **State-transition diagram** (FOLLOWER → CANDIDATE → LEADER, and every way back to FOLLOWER)
- [ ] **Diagram of the two Pis and the witness** (heartbeats, vote requests, acks)
- [ ] Detailed image of the final hardware setup
- [ ] Table of predicted and observed results for each test
- [ ] Event-log entries showing elections and recovery
- [ ] **Comparison of Lab 4's heartbeat system and Lab 5's election system**
- [ ] **Discussion of what happens when a majority is unavailable**

Points worth making:

- [ ] Lab 4 vs Lab 5: Lab 4 only *detected* that pi-a failed (fixed roles, alarm); Lab 5 *recovers* by electing a new leader, and uses terms so stale messages are rejected
- [ ] No majority: no candidate can get 2 votes, so there's no leader. A leader without acks steps down after 5s. Candidates keep retrying with rising terms. It's safe (never two leaders), but nothing is in charge until a majority is back
- [ ] Why two leaders can't share a term (one vote per term; any two majorities overlap)
- [ ] Why two leaders can't overlap at all here (the leader lease and the 6s minimum election timeout)
- [ ] Why the witness is needed (with 2 voters, losing either one leaves no majority)
- [ ] Randomized timeouts and split votes
- [ ] Disruptive rejoin after isolation (term inflation; Raft's pre-vote would prevent it)
- [ ] The 2s quorum-warning threshold you chose
