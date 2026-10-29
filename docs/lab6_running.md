# Running Lab 6: multi-team cluster with monitoring

Four Raspberry Pis (two teams) and one witness on the laptop, all running the same app: `python -m node`. Prometheus and Grafana run on the same laptop.

- **5 voters, so 3 votes** are needed to become leader. Never fewer than 3, whatever the member count (`min_votes`).
- **Only one authorized leader at any time:** the 6 s leader lease, the 6–9 s election timeout, and the 5 s quorum step-down.
- **Names, addresses, ports and LED/buzzer pins live in `src/cluster.json`,** never in the Python code.

## 1. Before the lab (with internet)

1. **Every Pi:** clone the repo, check out `lab6`, and create the venv (see `lab5_running.md` → *One-time setup*).
2. **Laptop:** download Prometheus and Grafana. See [`monitoring/README.md`](../monitoring/README.md) (`docker compose pull` or `brew install prometheus grafana`).
3. **Agree with the other team** on four unique Pi names and each Pi's LED or buzzer pins.

## 2. The router and addresses

- Connect all four Pis and the laptop to the instructor's router.
- In the router's admin page, add a **DHCP reservation** for each device, so it gets the same address every time.
- Run `hostname -I` on each Pi and `ipconfig getifaddr en0` on the Mac to read the addresses.

## 3. The cluster file

Start from [`src/cluster.lab6.example.json`](../src/cluster.lab6.example.json). Fill in the real addresses and pins, set `config_term` and `config_version` to 0, and copy the **same file** to `src/cluster.json` on all five machines:

```json
{
  "config_term": 0,
  "config_version": 0,
  "min_votes": 3,
  "members": [
    {"name": "pi-a", "url": "http://192.168.0.11:5001", "role": "candidate", "hardware": {"type": "led", "pin": 25, "ground_pin": 24}},
    {"name": "pi-b", "url": "http://192.168.0.12:5002", "role": "candidate", "hardware": {"type": "buzzer", "pin": 6, "passive": true}},
    {"name": "pi-c", "url": "http://192.168.0.13:5001", "role": "candidate", "hardware": {"type": "led", "pin": 17}},
    {"name": "pi-d", "url": "http://192.168.0.14:5002", "role": "candidate", "hardware": {"type": "buzzer", "pin": 18, "passive": true}},
    {"name": "witness", "url": "http://192.168.0.10:5003", "role": "witness"}
  ]
}
```

Hardware forms: `{"type": "led", "pin": N}`, `{"type": "led", "pin": N, "ground_pin": M}`, `{"type": "buzzer", "pin": N, "passive": true}` (TonalBuzzer), or `{"type": "buzzer", "pin": N, "passive": false}` (active buzzer). Pins are GPIO numbers.

On a fresh start, clear the old state on every machine (in `src/`):

```bash
rm -rf state logs
```

## 4. Start everything

**Each Pi** (from `src/`; use that Pi's name):

```bash
../venv/bin/python -m node --name pi-a
```

**The laptop:** the witness in one tab, then the monitoring.

```bash
cd ~/Projects/distributed-pi/src && ../venv/bin/python -m node --name witness
```

```bash
cd ~/Projects/distributed-pi/monitoring && python3 make_targets.py --from http://localhost:5003 --docker --watch 5
```

```bash
cd ~/Projects/distributed-pi/monitoring && docker compose up -d
```

**Done when:**
- Grafana (http://localhost:3000) shows **ONE LEADER**, **QUORUM**, and all five nodes **UP**.
- The dashboard at http://localhost:5003/ says "5 voters, majority 3".

## 5. Tests

For each test, record: predicted result, observed result, elected leader, term, quorum status, hardware behavior, Grafana result, and event-log entries. Grafana's **State over time** panel and the event logs give you the timing.

| # | Test | How | Predicted result | Grafana should show |
|---|---|---|---|---|
| 1 | Start all four Pis and the witness | section 4 | One Pi elected with ≥ 3 votes about 6–9 s after start (`BECAME_LEADER 3+ votes`) | ONE LEADER, QUORUM, 5 × UP, term 1 |
| 2 | Stop the current leader | Ctrl+C on the leader (or `sudo systemctl stop election-<name>`) | New leader 6–9 s later with 3 of the 4 remaining votes; term + 1 | leader node DOWN; NO LEADER for about 6–9 s, then ONE LEADER; Leader changes + 1 |
| 3 | Restart the former leader | start it again | It loads its saved term, sees the newer term, and stays FOLLOWER | node UP, state FOLLOWER; no new election |
| 4 | Stop one follower | Ctrl+C on a follower Pi | Leader keeps quorum (needs 2 acks, still has 3) | that node DOWN; still ONE LEADER, QUORUM |
| 5 | Stop the witness | Ctrl+C on the witness | Leader keeps quorum through the Pis | witness DOWN; still ONE LEADER, QUORUM (Prometheus keeps running) |
| 6 | Disconnect two voters | unplug or `sudo ip link set wlan0 down` on two members | 3 of 5 left = still a majority, so quorum remains. If the leader was one of the two, a new one is elected among the 3 | two nodes DOWN; QUORUM. Disconnecting a 3rd voter gives NO QUORUM, NO LEADER |
| 7 | Change one Pi's address using only the config file | give the Pi a new address (change its reservation or port); stop all members; edit that member's `url` in `cluster.json` on **all** machines, raise `config_version` by 1; restart everything | Cluster re-forms with the new address; no code change | targets update automatically (`make_targets.py --watch`); all UP |
| 8 | Stop Prometheus or Grafana | `docker compose stop` (or Ctrl+C) | Elections continue: stop the leader meanwhile and a new one is still elected | nothing while stopped; after `docker compose start`, the gap and the election are visible |
| 9 | Create a no-leader condition | stop 3 of the 5 voters (e.g. two Pis + witness) | 2 voters can't reach 3 votes: the leader steps down after 5 s, and the remaining candidates retry elections with rising terms | **NO LEADER** (red), **NO QUORUM**, terms climbing |

**About "multiple leaders":** the code is designed so two leaders can never exist at once. The leader lease plus the step-down timing rule this out, and simulated network failures never produced two. So demonstrate the **no-leader** case in test 9. The **Leader check** panel would show **MULTIPLE LEADERS** if two members ever reported themselves as leader. Say so in the report.

**Test 7 alternative while running:** restart the moved Pi with `--join http://<any member> --url http://<new address>:<port>`. The leader records the new address and every member rewrites its own `cluster.json`.

## 6. Collect for the report

- **Screenshots:** the Grafana dashboard after each test, and Prometheus → Status → Targets.
- **Event logs:** `src/logs/<name>_events.log` from all five machines.
- **Config files:** the monitoring folder (`prometheus.yml`, the provisioning files, the dashboard JSON) and your final `cluster.json`.
