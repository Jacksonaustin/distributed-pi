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

1. Add an entry to the cluster file, on **every** machine, with a unique name and port. Use `"can_lead": false` for a witness and `true` for a candidate.
2. Start it with `python -m witness.app --name <its name>`. That entry point works for any voter without hardware.
3. Restart the other voters so they read the new list.

The majority (`voters // 2 + 1`) and the number of acks a leader needs (`majority - 1`) are recalculated automatically. With 5 voters, a leader needs 3 votes and acks from 2 peers. Odd numbers of voters are best, since a 4th voter raises the majority without letting the cluster survive any more failures.

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
