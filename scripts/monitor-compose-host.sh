#!/usr/bin/env bash
# Live logs + host/container performance for a Compose Odysseus host.
# Designed to be opened from a desktop SSH client:
#   ssh -t HOST "bash ~/odysseus/scripts/monitor-compose-host.sh"
set -euo pipefail

SELF="$(readlink -f "$0")"
ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"
cd "$ROOT"

SESSION="${ODYSSEUS_MONITOR_SESSION:-ody-mon}"
CMD="${1:-attach}"

logs_follow() {
  echo "Compose logs (all services). Ctrl-b d detaches; session keeps running."
  echo
  docker compose logs -f --timestamps --since 2h --tail=80
}

dashboard_loop() {
  export TERM="${TERM:-tmux-256color}"
  while true; do
    stats="$(docker compose stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' 2>/dev/null || true)"
    services="$(docker compose ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || true)"
    clear || printf '\033[2J\033[H'
    echo "$(hostname)  $(date -u +'%H:%M:%SZ')"
    echo "load $(cut -d' ' -f1-3 /proc/loadavg)"
    echo "mem $(free -h | awk '/Mem:/{print $3 "/" $2}')  disk $(df -h / | awk 'NR==2{print $5}')"
    echo
    printf '%s\n' "$stats"
    echo
    printf '%s\n' "$services"
    echo
    if ss -ltn | grep -q ':7000 '; then
      echo "7000 open"
    else
      echo "7000 DOWN"
    fi
    tailscale serve status 2>/dev/null | head -n 2 || echo "(tailscale serve not running)"
    echo
    echo "errors:"
    if [ -f data/logs/app.log ]; then
      grep -E ' - ERROR - | - CRITICAL - ' data/logs/app.log \
        | tail -n 3 \
        | cut -c1-88 \
        || echo "(none)"
    else
      echo "(no app.log)"
    fi
    sleep 5
  done
}

perf_follow() {
  echo "perf.jsonl (skips thread.work noise). Samples every ~30s plus HTTP/tasks."
  echo
  python3 -u - <<'PY'
import json
import time
from pathlib import Path

path = Path("data/logs/perf.jsonl")
skip = ("thread.work",)


def keep(event):
    name = str(event.get("event") or "")
    if name.startswith(skip):
        return False
    if name == "process.attributed":
        try:
            return float(event.get("cpu_pct") or 0) >= 5.0
        except (TypeError, ValueError):
            return False
    return True


def fmt(event):
    ts = str(event.get("ts") or "")
    if "T" in ts:
        ts = ts.split("T", 1)[1][:8]
    parts = [ts, str(event.get("event") or "?")]
    if event.get("cpu_pct") is not None:
        parts.append("cpu=%s" % event["cpu_pct"])
    if event.get("rss_mb") is not None:
        parts.append("rss=%sMB" % event["rss_mb"])
    elif event.get("mem_pct") is not None:
        parts.append("mem=%s%%" % event["mem_pct"])
    if event.get("duration_ms") is not None:
        parts.append("%sms" % event["duration_ms"])
    if event.get("status") not in (None, "ok"):
        parts.append(str(event["status"]))
    if event.get("method") and event.get("path"):
        parts.append("%s %s" % (event["method"], event["path"]))
    if event.get("task_name"):
        phase = event.get("phase") or event.get("action") or ""
        parts.append(("%s %s" % (phase, event["task_name"])).strip())
    if event.get("name") and event.get("event") == "process.attributed":
        parts.append(str(event["name"])[:32])
    return " ".join(str(p) for p in parts)


def replay_tail():
    if not path.exists():
        print("(waiting for data/logs/perf.jsonl)", flush=True)
        return
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 512_000))
        handle.readline()
        rows = []
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if keep(event):
                rows.append(fmt(event))
        for row in rows[-30:]:
            print(row, flush=True)


replay_tail()
while not path.exists():
    time.sleep(1)
with path.open("r", encoding="utf-8", errors="replace") as handle:
    handle.seek(0, 2)
    while True:
        line = handle.readline()
        if not line:
            time.sleep(0.25)
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if keep(event):
            print(fmt(event), flush=True)
PY
}

create_session() {
  tmux new-session -d -s "$SESSION" -x 200 -y 50 -c "$ROOT" -n monitor "bash '$SELF' logs"
  tmux split-window -h -t "$SESSION":0 -l 40% -c "$ROOT" "bash '$SELF' dashboard"
  tmux split-window -v -t "$SESSION":0.1 -l 30% -c "$ROOT" "bash '$SELF' perf"
  tmux select-pane -t "$SESSION":0.0
  tmux set-option -t "$SESSION" mouse on
  tmux set-option -t "$SESSION" history-limit 20000
  tmux set-option -t "$SESSION" status on
  tmux set-option -t "$SESSION" status-left " Odysseus "
  tmux set-option -t "$SESSION" status-right " #{host} %H:%M "
}

case "$CMD" in
  logs)
    logs_follow
    ;;
  dashboard)
    dashboard_loop
    ;;
  perf)
    perf_follow
    ;;
  create)
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    create_session
    echo "created tmux session $SESSION"
    ;;
  reset)
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    create_session
    exec tmux attach -t "$SESSION"
    ;;
  attach)
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
      create_session
    fi
    exec tmux attach -t "$SESSION"
    ;;
  *)
    echo "usage: $0 [attach|reset|create|logs|dashboard|perf]" >&2
    exit 2
    ;;
esac
