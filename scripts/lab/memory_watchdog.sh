#!/bin/bash
# Lab server watchdog (2026-11-08). Once a minute, kills our processes that hold more than MIN_GB of memory and whose
# working folder is a deleted SWE-bench sandbox. On 2026-11-08 scripts written by an agent kept running after their
# command timeout and after their sandbox was deleted, used all 1 TB of memory, and stalled the server for 16.5 hours.
#   nohup setsid bash memory_watchdog.sh </dev/null >/dev/null 2>&1 &    (a second copy exits at once)
#   DRY=1 ONCE=1 MIN_GB=0 bash memory_watchdog.sh                        (lists what it would kill, kills nothing)
set -u
E=<workdir>/swe-env
LOG=${LOG:-$E/memory_watchdog.log}
MIN_GB=${MIN_GB:-20}
EVERY=${EVERY:-60}
DRY=${DRY:-0}
ONCE=${ONCE:-0}
say() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

if [ "$ONCE" != 1 ]; then
    exec 9> "$E/memory_watchdog.lock"
    flock -n 9 || exit 0
    say "start pid=$$ min_gb=$MIN_GB every=${EVERY}s"
fi

while :; do
    ps -u "$(id -un)" -o pid=,rss= | while read -r pid rss; do
        [ "$rss" -gt $((MIN_GB * 1048576)) ] || continue
        [ "$(readlink "/proc/$pid/cwd" 2>/dev/null)" = "/testbed (deleted)" ] || continue
        cmd=$(tr '\0\n' '  ' < "/proc/$pid/cmdline" 2>/dev/null | cut -c1-200)
        if [ "$DRY" = 1 ]; then
            say "would kill pid=$pid rss_gb=$((rss / 1048576)) cmd=$cmd"
        else
            kill -KILL "$pid" && say "killed pid=$pid rss_gb=$((rss / 1048576)) cmd=$cmd"
        fi
    done
    [ "$ONCE" = 1 ] && exit 0
    sleep "$EVERY"
done
