# Running Lab 5

Every voter runs the same Flask app (`common/webapp.py`). The only differences are its name, whether it can lead (from the cluster file), and pi-a's LED or pi-b's buzzer.

| Voter | Command (from `src/`) | Hardware |
|---|---|---|
| pi-a | `python -m pi_a.lab5_app` | LED on GPIO26 |
| pi-b | `python -m pi_b.lab5_app` | passive buzzer (TonalBuzzer) on GPIO6 |
| witness, or any voter without hardware | `python -m witness.app [--name NAME]` | none |

Each voter's port comes from its URL in the cluster file. Its dashboard is at `http://<host>:<port>/`.

## Cluster files

The voters are listed in a JSON file, not in code:

```json
{"voters": [
  {"name": "pi-a",    "url": "http://pi-a.local:5001", "can_lead": true},
  {"name": "pi-b",    "url": "http://pi-b.local:5002", "can_lead": true},
  {"name": "witness", "url": "http://Jacksons-MacBook-Air-2.local:5003", "can_lead": false}
]}
```

| File | Used for |
|---|---|
| `src/cluster.json` | the real Pis plus the laptop witness (the default) |
| `src/cluster.local.json` | all voters on the laptop, at localhost |

Pick one with `CLUSTER=<file>`. **Every voter must use the same list.**

### Adding a witness or candidate

On the `lab6` branch, members can join and leave while the cluster runs. See **Dynamic membership** below. On `main` (Lab 5), add an entry to the cluster file on every machine and restart the voters.

The majority (`voters // 2 + 1`) and the number of acks a leader needs (`majority - 1`) are recalculated automatically. With 5 voters, a leader needs 3 votes and acks from 2 peers. Odd numbers of voters are best, since a 4th voter raises the majority without letting the cluster survive any more failures.

## Dynamic membership (`lab6` branch)

### Roles

| Role | Votes | Can lead | Counts toward the majority |
|---|---|---|---|
| `candidate` | yes | yes | yes |
| `witness` | yes | no | yes |
| `follower` | no | no | no: receives heartbeats and knows the leader, nothing more |

### Join a running cluster

Start the new device with `--join` pointing at **any** running member. It fetches the current member list, starts its app, then asks to be added. Requests are forwarded to the leader.

```bash
cd src && ../venv/bin/python -m witness.app --name pi-c --role candidate --port 5004 --join http://10.0.0.11:5001
```

- **`--role`:** `candidate`, `witness` or `follower` (default `follower`).
- **`--port`:** the port this device listens on (default 5000).
- **`--url`:** the address others should use, e.g. `http://10.0.0.13:5004`. If you leave it out, it's detected from the network interface that reaches the `--join` address.
- **Entry point:** use `pi_a.lab5_app` or `pi_b.lab5_app` instead of `witness.app` if the device has that LED or buzzer.

**Done when** its log shows `JOINED_CLUSTER` and every dashboard lists it. You can also add a device from any dashboard (**Members → Add member**), but it must already be running.

### Leave

Use a member card's **Remove** button, or:

```bash
curl -X POST http://<any member>/leave -H "Content-Type: application/json" -d '{"name": "pi-c"}'
```

The removed node logs `REMOVED_FROM_CLUSTER` and stops voting and running for leader. The current **leader** can't be removed; stop it first so another member takes over, then remove it.

### Change a member's address

Restart it with `--join` and its new `--url` (or `--port`). The leader records the new address and every member picks it up (`MEMBER_UPDATED`).

### Rules that keep it safe

1. **Only the leader changes the list.** Each version has an id `(term, counter)`, shown as `v1.3`. It travels in every heartbeat, and members save the newest one into their own cluster file.
2. **One voter change at a time.** After adding or removing a candidate or witness, the leader refuses the next voter change until a majority of the **new** voters have acknowledged the new list (`MEMBERSHIP_COMMITTED`). The dashboard shows "being confirmed" while it waits. With one change at a time, the old and new majorities always share a voter, so two leaders can't be elected under different lists. Followers can be added or removed at any time.
3. **A voter must answer `/status` before it's added.** Adding a dead voter would raise the majority with no one to fill it.
4. **Voters refuse candidates with an older member list**, so a new leader always knows the latest members.
5. **A joining node waits until it's actually in the list** and asks again if not. An accepted join can be lost if the leader changes before most voters have it.

### Your copy of `cluster.json` changes

Each node **rewrites its own `src/cluster.json`** whenever the list changes, in a new format with `config_term`, `config_version` and a `members` list that uses `role` instead of `can_lead`. The old Lab 5 format is still read.

Because the file is in git, `git pull` on a Pi may complain that it was changed. Keep the Pi's version with `git stash` → `git pull` → `git stash pop`, or throw it away with `git checkout src/cluster.json`.

If you edit the file by hand while the cluster runs, the leader's list wins whenever its id is newer. To force a hand edit, stop every member, make the same edit on all machines, and raise `config_version` by one.

## On the laptop

Run each command in its own terminal, from `src/`. No GPIO setting is needed: off the Pi, the apps switch to mock pins automatically.

```bash
cd ~/Projects/distributed-pi/src && CLUSTER=cluster.local.json ../venv/bin/python -m witness.app
```

```bash
cd ~/Projects/distributed-pi/src && CLUSTER=cluster.local.json ../venv/bin/python -m pi_a.lab5_app
```

```bash
cd ~/Projects/distributed-pi/src && CLUSTER=cluster.local.json ../venv/bin/python -m pi_b.lab5_app
```

Then open http://localhost:5003/ (or 5001, 5002). Each page shows every voter.

## On the Pis

### 1. One-time setup on each Pi

```bash
git clone <your repo url> ~/distributed-pi && cd ~/distributed-pi
```

```bash
sudo apt update && sudo apt install -y python3-venv python3-lgpio
```

```bash
python3 -m venv --system-site-packages venv && venv/bin/pip install -r requirements.txt
```

**Hostnames must match the cluster file.** Run `hostname` on each Pi; it should print `pi-a` or `pi-b`. To change it: `sudo raspi-config` → System Options → Hostname, then reboot.

### 2. The witness on the laptop

- `cluster.json` lists the witness as `http://Jacksons-MacBook-Air-2.local:5003`, your Mac's Bonjour name. Check it from a Pi with `ping Jacksons-MacBook-Air-2.local`. If that fails, use the Mac's IP address instead (`ipconfig getifaddr en0`) and update `cluster.json` on all three machines.
- **macOS firewall:** if it's on, allow incoming connections for Python when macOS asks, or the Pis can't reach the witness.
- Start the witness with the default cluster file:

```bash
cd ~/Projects/distributed-pi/src && ../venv/bin/python -m witness.app
```

### 3. Start the Pis

On pi-a:

```bash
cd ~/distributed-pi/src && ../venv/bin/python -m pi_a.lab5_app
```

On pi-b:

```bash
cd ~/distributed-pi/src && ../venv/bin/python -m pi_b.lab5_app
```

The dashboards are at http://pi-a.local:5001/, http://pi-b.local:5002/ and http://localhost:5003/ (on the laptop).

### 4. Optional: start at boot

```bash
sudo deploy/install_service.sh pi_a
```

Run that from the repo root on pi-a, and use `pi_b` on pi-b. Then `sudo systemctl stop lab5-pi-a` and `sudo systemctl start lab5-pi-a` are the "stop" and "restart" commands for the tests, and `journalctl -u lab5-pi-a -f` shows the output.

### If the Pis can't reach each other

Campus Wi-Fi often blocks device-to-device traffic. Test it with `ping pi-b.local` from pi-a. If that fails, use a phone hotspot or a router where all three machines are on the same network.

## State, logs and resetting

| What | Where |
|---|---|
| Saved term and vote | `src/state/<name>.json` |
| Event log | `src/logs/<name>_events.log`, also shown on the dashboard |

To start over at term 0, stop the voter and delete both folders:

```bash
cd ~/distributed-pi/src && rm -rf state logs
```

**Don't** delete them between the "restart a voter after it has already voted" steps; that test depends on the saved vote.

## Dashboard features for the tests

- **Cards** show every voter's state, term, vote and leader, plus what pi-a's LED and pi-b's buzzer should be doing.
- **Banner:** green when there's one leader with quorum, amber with no leader or lost quorum, red when two voters both think they're leader (the split-brain failure the lab mentions).
- **Event log:** all voters merged in time order, or this node only. Screenshot it for the report.
- **Test messages:** send a hand-made vote request or heartbeat to any voter.
  - "Old term" fills in the target's term minus one, for the old-term heartbeat test.
  - "Send twice" sends the same vote request twice, for the duplicate vote test.
  - A vote request for a *higher* term is rejected with `REJECTED_LEADER_ALIVE` while the target has heard from a leader in the last 6s. This leader lease is what keeps two leaders from overlapping. Once no leader has been heard from for 6s, a higher term is adopted as normal.
  - Messages naming the witness (or an unknown voter) as the leader or candidate are rejected with `REJECTED_INVALID`, because the witness can't lead.
