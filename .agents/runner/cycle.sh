#!/usr/bin/env bash
# One turn of the wheel: sync, then up to MAX_STEPS steps chosen by `status.py next`
# (merge pending branches > run the next approved task > plan the next scope > weekly review > idle),
# each a fresh headless session (= /clear) stopped at its first result by step.py, then STATUS.md.
#
# Usage: .agents/runner/cycle.sh [--dry-run]        (from anywhere; works in the dev_agent worktree)
# Env:   STOP_AT=85 (session window %), WEEK_MAX=90 (week %), MAX_STEPS=6, MODEL=sonnet
# Each step starts only if its expected cost (runner/cost.py: median of measured steps of that kind, seeds until
# then) keeps the session window under STOP_AT and the week under WEEK_MAX; the real cost is recorded after it.
# Stops on: worktree not clean / not on dev_agent, a /usage threshold, budget.py STOP or DISABLE, a usage limit,
#           a step that makes no progress, or a sync conflict. Never pushes anything but dev_agent and agent branches
#           (the commands' own rules), never touches `dev` except the fast-forward mirror in sync_branches.sh.
set -u
W=$(cd "$(dirname "$0")/../.." && pwd); cd "$W" || exit 2
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
STOP_AT=${STOP_AT:-85}; WEEK_MAX=${WEEK_MAX:-90}; MAX_STEPS=${MAX_STEPS:-6}; MODEL=${MODEL:-sonnet}
eval "$(python3 -c "import tomllib;print(tomllib.load(open('.agents/profile.toml','rb'))['tools'].get('env',''))")"
RUNS=$(git rev-parse --path-format=absolute --git-common-dir)/agent-runs; mkdir -p "$RUNS"
STAMP=$(date -u +%Y%m%dT%H%M%SZ); LOGDIR=$RUNS/cycles/$STAMP; mkdir -p "$LOGDIR"
exec 9>"$RUNS/cycle.lock"; flock -n 9 || { echo "another cycle is running"; exit 0; }
log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOGDIR/cycle.log"; }
unset CLAUDE_CODE_SESSION_ID CLAUDE_CODE_CHILD_SESSION

clean() { [ "$(git branch --show-current)" = dev_agent ] && [ -z "$(git status --porcelain)" ]; }
reading() { timeout 120 claude -p "/usage" 2>&1 | grep -E "Current (session|week)" | tr '\n' ' '; }
pct() { echo "$1" | sed -nE "s/.*Current $2[^:]*: ([0-9]+)%.*/\1/p"; }
guard() {
  clean || { log "STOP: worktree not clean or not on dev_agent: $(git branch --show-current) $(git status --porcelain | head -3 | tr '\n' ' ')"; return 1; }
  python3 .agents/scripts/budget.py disable-check >/dev/null || { log "STOP: budget.py disable-check: $(python3 .agents/scripts/budget.py disable-check)"; return 1; }
  [ $DRY -eq 1 ] && return 0
  local u; u=$(reading); S=$(pct "$u" session); W_=$(pct "$u" week); log "usage: $u"
  [ -n "$S" ] && [ -n "$W_" ] || { log "STOP: could not read /usage"; return 1; }
  [ "$S" -ge "$STOP_AT" ] && { log "STOP: session window $S% >= $STOP_AT%"; return 1; }
  [ "$W_" -ge "$WEEK_MAX" ] && { log "STOP: week $W_% >= $WEEK_MAX%"; return 1; }
  return 0
}
publish() {  # regenerate STATUS.md and push it with whatever the step left committed
  python3 .agents/scripts/status.py --write >/dev/null
  if [ -n "$(git status --porcelain -- .agents/STATUS.md)" ]; then
    git add .agents/STATUS.md && git commit -q -m "Status after $1 [skip ci]" && git push -q origin dev_agent && log "STATUS.md pushed"
  fi
}

log "cycle $STAMP (dry-run=$DRY, STOP_AT=$STOP_AT, WEEK_MAX=$WEEK_MAX, MAX_STEPS=$MAX_STEPS) in $W"
guard || exit 0
if [ $DRY -eq 0 ]; then
  bash .agents/scripts/sync_branches.sh > "$LOGDIR/sync.txt" 2>&1 || { log "STOP: sync failed (see $LOGDIR/sync.txt)"; exit 1; }
  log "synced dev and tags from upstream, dev merged into dev_agent"
fi
for i in $(seq 1 "$MAX_STEPS"); do
  next=$(python3 .agents/scripts/status.py next); rows=$(wc -l < .agents/ledger.jsonl)
  log "step $i: $next"
  set -- $next
  case "$1" in
    merge)  prompt="/optimize-merge" ;;
    run)    prompt="/optimize-run $2 The task is in $3 (read any correction note at the top of the plan first)." ;;
    plan)   prompt="/optimize-plan $2" ;;
    review) prompt="/optimize-review" ;;
    idle)   log "idle: nothing to do"; break ;;
    *)      log "STOP: unknown next step '$next'"; break ;;
  esac
  units=1; [ "$1" = merge ] && units=$(python3 .agents/scripts/status.py pending | wc -l)
  if [ $DRY -eq 1 ]; then log "dry-run: would run: $prompt (expected cost: $(python3 .agents/runner/cost.py estimate "$1" --units "$units"))"; break; fi
  [ "$i" -gt 1 ] && { guard || break; }
  fit=$(python3 .agents/runner/cost.py fits "$1" --units "$units" --session "$S" --week "$W_" --stop-at "$STOP_AT" --week-max "$WEEK_MAX"); fok=$?
  log "  $fit"; [ $fok -eq 0 ] || { log "STOP: next step would not fit the quota"; break; }
  S0=$S; W0=$W_
  python3 .agents/runner/step.py --model "$MODEL" --out "$LOGDIR/$i-$1.txt" -- "$prompt" >> "$LOGDIR/steps.jsonl"; rc=$?
  log "  exit $rc, log $LOGDIR/$i-$1.txt"
  u=$(reading); S=$(pct "$u" session); W_=$(pct "$u" week)
  [ -n "$S" ] && [ -n "$W_" ] && python3 .agents/runner/cost.py record "$1" "$units" "$S0" "$W0" "$S" "$W_" && log "  cost: session +$((S - S0))%, week +$((W_ - W0))% (after: $u)"
  [ $rc -eq 3 ] && { log "STOP: usage limit hit"; publish "$next (limit)"; break; }
  clean || { log "STOP: the step left the worktree dirty or off dev_agent"; break; }
  publish "$next"
  last=$(tail -1 .agents/ledger.jsonl | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('outcome'))")
  [ "$(wc -l < .agents/ledger.jsonl)" -eq "$rows" ] && { log "STOP: the step logged nothing (no progress)"; break; }
  case "$last" in budget|limit|failed) log "STOP: last run ended '$last'"; break ;; esac
  [ "$(python3 .agents/scripts/status.py next)" = "$next" ] && { log "STOP: '$next' again, no progress"; break; }
done
log "cycle done; next: $(python3 .agents/scripts/status.py next)"
