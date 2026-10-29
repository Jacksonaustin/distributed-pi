# Monitoring: Prometheus + Grafana

Prometheus reads every member's `GET /metrics` every 2 s. Grafana shows the **Election cluster** dashboard built from that data. Neither takes part in elections, and stopping either has no effect on the cluster.

| File | What it is |
|---|---|
| `prometheus.yml` | Prometheus config; scrape targets come from `targets/*.json` |
| `make_targets.py` | writes `targets/election.json` from the member list (the cluster file or a running member) |
| `grafana/provisioning/` | creates the Prometheus data source and loads the dashboard at startup |
| `grafana/dashboards/election-cluster.json` | the dashboard |
| `docker-compose.yml` | runs Prometheus and Grafana in Docker |

## Before the lab (needs internet)

The lab router has no internet, so download everything in advance.

**Docker:**

```bash
cd ~/Projects/distributed-pi/monitoring && docker compose pull
```

**Or Homebrew:**

```bash
brew install prometheus grafana
```

## Run it (Docker)

**1. Keep the target list up to date.** Leave this running in its own tab. It follows joins, leaves and address changes. `localhost:5003` is the witness on this Mac; any member works.

```bash
cd ~/Projects/distributed-pi/monitoring && python3 make_targets.py --from http://localhost:5003 --docker --watch 5
```

**2. Start Prometheus and Grafana:**

```bash
cd ~/Projects/distributed-pi/monitoring && docker compose up -d
```

- **Prometheus:** http://localhost:9090. Under **Status → Targets**, every member should show **UP**.
- **Grafana:** http://localhost:3000. The *Election cluster* dashboard opens as the home page; log in as admin / admin to edit it.

**3. Stop them** (this is lab test 8):

```bash
cd ~/Projects/distributed-pi/monitoring && docker compose stop
```

## Run it (Homebrew)

```bash
cd ~/Projects/distributed-pi/monitoring && python3 make_targets.py --from http://localhost:5003 --watch 5
```

Then, in a second tab, start Prometheus:

```bash
cd ~/Projects/distributed-pi/monitoring && prometheus --config.file=prometheus.yml --storage.tsdb.path=/tmp/prometheus-data
```

And in a third tab, start Grafana:

```bash
cd ~/Projects/distributed-pi/monitoring && PROMETHEUS_URL=http://localhost:9090 DASHBOARDS_DIR="$PWD/grafana/dashboards" GF_PATHS_PROVISIONING="$PWD/grafana/provisioning" grafana server --homepath "$(brew --prefix grafana)/share/grafana"
```

Stop each with Ctrl+C.

## What `/metrics` reports

Every series has `node="<name>"`; Prometheus adds `role` from the targets file.

| Metric | Meaning |
|---|---|
| `election_state{state}` / `election_state_code` | current state (1 for the active state) / 0 follower, 1 candidate, 2 leader |
| `election_is_leader` | 1 on the leader |
| `election_term` | current term |
| `election_has_quorum` | 1 if leader and hearing from enough voters |
| `election_leader_heartbeat_age_seconds` | time since the last valid leader heartbeat (0 on the leader, NaN if never) |
| `election_known_leader{leader}` | which leader this node believes in |
| `election_voters`, `election_votes_needed` | voters in the member list, votes needed to lead |
| `election_elections_total` | elections this node started |
| `election_became_leader_total` | times this node became leader |
| `election_leader_changes_total` | times this node saw the leader change |
| `election_votes_rejected_total{reason}` | vote requests this node refused: `old_term`, `leader_alive`, `already_voted`, `stale_member_list`, `not_voter`, `invalid` |
| `election_messages_rejected_total{reason}` | heartbeats and vote requests rejected |
| `election_quorum_lost_total`, `election_stepped_down_total` | quorum losses, returns to follower |
| `election_events_total{event}` | every event-log entry type |
| `up` (added by Prometheus) | 1 if Prometheus could read the member's `/metrics` |

Counters restart at 0 when a member's app restarts; Grafana's `increase()` accounts for that.

Check any member by hand:

```bash
curl http://localhost:5003/metrics
```
