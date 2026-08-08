#!/usr/bin/env bash
# Deploy the Theia bundle to the Hermes server — ADDITIVE and SAFE.
#   ./deploy.sh            # DRY RUN: print the plan, change nothing
#   ./deploy.sh --apply    # do it (with timestamped backups of every file touched)
#
# What it does under --apply:
#   1. rsync repo root (mcp, compute, profile, cron) -> ~/.hermes/theia/
#   2. copy skills/theia-* -> ~/.hermes/skills/
#   3. per MCP server: create .venv + pip install requirements
#   4. append MISSING keys to ~/.hermes/.env from local .secret (backup first)
#   5. merge cron jobs into ~/.hermes/cron/jobs.json (backup first; jobs stay DISABLED)
# What it does NOT do automatically (prints instructions instead — needs your eyes):
#   - register MCP servers in ~/.hermes/config.yaml  (run `hermes mcp install <dir>` or paste)
#   - set the Theia profile identity from profile/IDENTITY.md
#   - enable cron jobs (do it only after per-layer smoke tests)
set -euo pipefail

HOST="${HERMES_SSH:-hermes}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"          # project-theia/
SECRET_FILE="$LOCAL_DIR/.secret"                          # project-theia/.secret
APPLY=0; [[ "${1:-}" == "--apply" ]] && APPLY=1
TS="$(date +%Y%m%d_%H%M%S)"
say() { printf '  %s\n' "$*"; }
run() { if [[ $APPLY -eq 1 ]]; then ssh "$HOST" "$*"; else echo "    [dry] ssh $HOST $*"; fi; }

echo "== Theia deploy to '$HOST'  (apply=$APPLY) =="

echo "[1/5] rsync bundle -> ~/.hermes/theia/"
if [[ $APPLY -eq 1 ]]; then
  rsync -az --delete --exclude '.venv' --exclude '__pycache__' --exclude 'tests' \
    "$LOCAL_DIR/mcp" "$LOCAL_DIR/compute" "$LOCAL_DIR/profile" "$LOCAL_DIR/cron" \
    -e ssh "$HOST:~/.hermes/theia/"
else
  rsync -az --dry-run --exclude '.venv' --exclude '__pycache__' \
    "$LOCAL_DIR/mcp" "$LOCAL_DIR/compute" -e ssh "$HOST:~/.hermes/theia/" | sed 's/^/    [dry] /' | head
fi

echo "[2/5] copy skills -> ~/.hermes/skills/"
for d in "$LOCAL_DIR"/skills/*/; do
  name="$(basename "$d")"; say "skill: $name"
  [[ $APPLY -eq 1 ]] && rsync -az "$d" -e ssh "$HOST:~/.hermes/skills/$name/"
done

echo "[3/5] build MCP venvs"
for d in "$LOCAL_DIR"/mcp/theia-*/; do
  name="$(basename "$d")"; say "venv: $name"
  run "cd ~/.hermes/theia/mcp/$name && python3 -m venv .venv && .venv/bin/pip -q install -r requirements.txt"
done

echo "[4/5] add MISSING keys to ~/.hermes/.env (values from local .secret, never printed)"
while read -r key; do
  [[ -z "$key" || "$key" == \#* ]] && continue
  val="$(grep -E "^${key}=" "$SECRET_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  if [[ -z "$val" ]]; then say "SKIP $key (not in local .secret)"; continue; fi
  if [[ $APPLY -eq 1 ]]; then
    ssh "$HOST" "grep -q '^${key}=' ~/.hermes/.env 2>/dev/null || (cp -n ~/.hermes/.env ~/.hermes/.env.bak.$TS; printf '%s=%s\n' '$key' '$val' >> ~/.hermes/.env)"
    say "ensured $key in server .env"
  else
    say "[dry] would ensure $key in server .env"
  fi
done < "$LOCAL_DIR/deploy/env.additions"

echo "[5/5] merge cron jobs into ~/.hermes/cron/jobs.json (backup first; jobs stay DISABLED)"
if [[ $APPLY -eq 1 ]]; then
  scp -q "$LOCAL_DIR/cron/theia-jobs.json" "$HOST:/tmp/theia-jobs.json"
  ssh "$HOST" 'python3 - <<PY
import json,shutil,time
base="/home/hermes/.hermes/cron/jobs.json"; add="/tmp/theia-jobs.json"
shutil.copy(base, base+".bak."+time.strftime("%Y%m%d_%H%M%S"))
d=json.load(open(base)); have={j["id"] for j in d.get("jobs",[])}
new=[j for j in json.load(open(add))["jobs"] if j["id"] not in have]
d["jobs"]=d.get("jobs",[])+new
json.dump(d, open(base,"w"), indent=1)
print(f"  merged {len(new)} theia jobs (disabled); existing untouched")
PY'
else
  say "[dry] would append theia jobs to jobs.json (disabled), with a backup"
fi

cat <<EOF

== NEXT (manual, needs your review) ==
  a) Register MCP servers in config.yaml (per manifest). Try:
       ssh $HOST 'for m in theia-store theia-chainrpc theia-dexdata theia-birdeye theia-security; do hermes mcp install ~/.hermes/theia/mcp/\$m; done'
     (or paste the mcp_servers.<name> blocks; each = command ~/.hermes/theia/mcp/<name>/.venv/bin/python, args server.py)
  b) Set the Theia profile identity from profile/IDENTITY.md.
  c) Smoke-test each layer (MCP probe, compute tests, one dry learn->screen->backtest cycle).
  d) THEN enable cron jobs one at a time in ~/.hermes/cron/jobs.json.
EOF
