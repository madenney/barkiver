#!/usr/bin/env bash
# Self-healing, rate-limited watchdog for the pool-clipper bulk download.
# Cron runs this every ~15 min. Goal: acquire ALL ~900 videos at max quality,
# without tripping YouTube's volume throttle.
#
# Hard-won facts this design encodes:
#   * A continuous sprint got ~208 videos before YouTube walled the IP. When
#     throttled *with cookies* the refusal reads "Requested format is not
#     available" (NOT "not a bot"), which is easy to misdiagnose as a format bug.
#   * Once walled, churning the rest of the list keeps the wall up. So we drip a
#     bounded BATCH, detect the throttle signature, and back off hard.
#   * ~67 videos are permanently gone. They live in dead_ids.txt and are never
#     retried (the throttle message also says "Video unavailable", so dead-video
#     detection deliberately excludes "try again later").
#   * The flock MUST be released before spawning anything long-lived — a child
#     (even the subshell wrapping it) inherits fd 9 and holds it. The status page
#     once held it for 14h, silently deadlocking every later run.
#
# Quality: no resolution cap. `-S res,br,ext:mp4:m4a` = highest resolution, then
# highest bitrate (YouTube's AV1 1080p is ~half the bitrate of its h264 1080p),
# then mp4/m4a container.

set -u

# cron has a minimal PATH. Three things must be reachable:
#   yt-dlp  (~/.local/bin)
#   node    (nvm)              — runs the bgutil PO-token server
#   deno    (~/.deno/bin)      — LOAD-BEARING: yt-dlp needs a JS runtime to solve
#                                YouTube's signature (nsig) challenge for the web
#                                client. Without it, format URLs can't be built and
#                                yt-dlp reports the misleading "Requested format is
#                                not available". Omitting deno here silently broke
#                                every cron batch while manual runs worked fine.
export PATH="$HOME/.local/bin:$HOME/.deno/bin:$HOME/.nvm/versions/node/v25.2.1/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin"

PROJECT=/home/matt/Projects/pool-clipper
LNK="$PROJECT/new_library"
URLS="$LNK/yt_urls.txt"
ARCHIVE="$LNK/archive.txt"
DEAD="$LNK/dead_ids.txt"
PIDFILE="$LNK/download.pid"
STATE="$LNK/.watchdog_state"   # "<next_at> <stall> <last_done> <win_start> <win_base>"
LOG="$LNK/watchdog.log"
LOCK="$LNK/.watchdog.lock"
BATCHFILE="$LNK/.batch_urls.txt"
STATUS_URL="http://127.0.0.1:8802/api/status"

# bgutil Proof-of-Origin token server (borrowed from clipmine). Without a PO
# token YouTube refuses the web client's formats.
POT_SERVER=/home/matt/Projects/clipmine/.bgutil-pot/server/build/main.js
POT_PORT=4416

# Pin the Firefox profile explicitly. There are TWO profiles with the same name:
#   ~/.mozilla/firefox/guyvx12c.default-release   -> 71 cookies, NO youtube login
#   ~/snap/firefox/.../guyvx12c.default-release   -> 2316 cookies, logged in
# yt-dlp's bare `firefox` prefers the ~/.mozilla one, which silently sends an
# unauthenticated session and gets "Sign in to confirm you're not a bot".
COOKIE_PROFILE="$HOME/snap/firefox/common/.mozilla/firefox/guyvx12c.default-release"
COOKIE_ARG="firefox:$COOKIE_PROFILE"
[ -f "$COOKIE_PROFILE/cookies.sqlite" ] || COOKIE_ARG="firefox"

# grep -c prints "0" and exits 1 when there are no matches. Piping that through
# `|| echo 0` appended a SECOND "0", producing "0\n0" — which broke the backoff
# arithmetic and left stall stuck at 0, so a walled watchdog never backed off.
count() {  # count <grep-args...> ; always prints exactly one integer
  local n
  n=$(grep -c "$@" 2>/dev/null) || true
  [ -n "${n:-}" ] || n=0
  printf '%s' "$n"
}

BATCH=15               # videos attempted per drip (small: a walled batch wastes few requests)
QUOTA=100             # max completed videos per rolling window (raised from 60 -> ~200/day)
WINDOW=43200           # 12 h rolling window -> QUOTA*2/day. Kept bounded because the
                       # sibling clipmine project downloads from this same IP, and
                       # two concurrent downloaders is what provokes the wall.
YIELD_FILE="$LNK/.yield_count"
MAX_YIELDS=12          # after ~3h of yielding, go anyway so we never starve
BASE_DELAY=900         # 15 min, doubled per stall
MAX_DELAY=28800        # cap backoff at 8 h
THROTTLE_HITS=3        # this many format/bot errors with zero progress == walled

ts() { date '+%F %T'; }
log() { echo "[$(ts)] $*" >> "$LOG"; }

exec 9>"$LOCK" || exit 0
flock -n 9 || exit 0
release_lock() { flock -u 9 2>/dev/null || true; exec 9>&-; }

status_down=0
curl -s -o /dev/null --max-time 5 "$STATUS_URL" 2>/dev/null || status_down=1
pot_down=0
(exec 3<>/dev/tcp/127.0.0.1/$POT_PORT) 2>/dev/null || pot_down=1

start_status_page() {
  [ "$status_down" -eq 1 ] || return 0
  setsid --fork bash -c 'cd "$1" && exec python3 scripts/download_status.py --port 8802' \
    _ "$PROJECT" >/dev/null 2>&1 </dev/null
  log "status page was down; restarted it"
}
start_pot_server() {
  [ "$pot_down" -eq 1 ] || return 0
  [ -f "$POT_SERVER" ] || { log "WARN: PO-token server missing at $POT_SERVER"; return 0; }
  setsid --fork node "$POT_SERVER" >/dev/null 2>&1 </dev/null
  sleep 3
  log "PO-token server was down; restarted it on :$POT_PORT"
}
bail() { release_lock; start_pot_server; start_status_page; exit 0; }

# Is OUR downloader still working? Match the batch file, not the binary name:
# the sibling clipmine project runs its own `yt-dlp` from this machine, and a
# bare `pgrep -x yt-dlp` matches that too — which made this watchdog bail every
# time clipmine was acquiring. Never kill or block on another project's yt-dlp.
pgrep -f 'yt-dlp .*\.batch_urls\.txt' >/dev/null 2>&1 && bail

# Be a good neighbour: if ANOTHER project's yt-dlp (e.g. clipmine's `source
# acquire`) is downloading from this IP right now, sit this cycle out rather than
# compete — concurrent downloaders are what provoke YouTube's wall. But don't
# starve: after MAX_YIELDS consecutive skips (~3h) go ahead anyway.
yields=0
[ -f "$YIELD_FILE" ] && { read -r yields < "$YIELD_FILE" 2>/dev/null || true; }
: "${yields:=0}"
if pgrep -x yt-dlp >/dev/null 2>&1; then
  if [ "$yields" -lt "$MAX_YIELDS" ]; then
    echo $((yields + 1)) > "$YIELD_FILE"
    [ "$yields" -eq 0 ] && log "yielding: another project's yt-dlp is downloading"
    bail
  fi
  log "yielded $yields cycles; proceeding anyway so we don't starve"
fi
echo 0 > "$YIELD_FILE"

now=$(date +%s)
next_at=0; stall=0; last_done=0; win_start=0; win_base=0
if [ -f "$STATE" ]; then
  read -r next_at stall last_done win_start win_base < "$STATE" 2>/dev/null || true
fi
: "${next_at:=0}"; : "${stall:=0}"; : "${last_done:=0}"; : "${win_start:=0}"; : "${win_base:=0}"

[ "$now" -lt "$next_at" ] && bail   # cooling off

touch "$DEAD"
done_now=$(count . "$ARCHIVE")

# --- harvest permanently-dead ids from the last batch's log ---
# "try again later" is the THROTTLE message, not a dead video. Exclude it.
fmt_err=0; bot_err=0; auth_err=0
if [ -f "$LNK/download.log" ]; then
  grep '^ERROR' "$LNK/download.log" 2>/dev/null \
    | grep -v 'try again later' \
    | grep -iE 'no longer available because the YouTube account|This video is private|Private video|removed by the uploader|blocked due to the claimed content|Video unavailable' \
    | grep -oE '\[youtube\] [A-Za-z0-9_-]{11}' | awk '{print $2}' >> "$DEAD"
  sort -u -o "$DEAD" "$DEAD"
  fmt_err=$(count 'Requested format is not available' "$LNK/download.log")
  bot_err=$(count -i 'try again later' "$LNK/download.log")
  # "not a bot" means the cookies are unauthenticated — an auth bug, NOT the
  # volume throttle. Backing off won't fix it; the profile must be corrected.
  auth_err=$(count -i 'not a bot' "$LNK/download.log")
fi

# --- rolling quota: never exceed QUOTA completions per WINDOW ---
if [ "$win_start" -eq 0 ] || [ $((now - win_start)) -ge "$WINDOW" ]; then
  win_start=$now; win_base=$done_now
fi
if [ $((done_now - win_base)) -ge "$QUOTA" ]; then
  resume=$((win_start + WINDOW))
  log "quota reached ($((done_now - win_base))/$QUOTA this window) — pausing until $(date -d @$resume '+%F %H:%M')"
  echo "$resume $stall $done_now $win_start $win_base" > "$STATE"
  bail
fi

# --- evaluate the previous batch: progress, or walled? ---
progress=$((done_now - last_done))
if [ "$progress" -gt 0 ]; then
  stall=0
elif [ "$auth_err" -ge "$THROTTLE_HITS" ]; then
  # Unauthenticated cookies. Retrying is pointless and just burns requests, so
  # sit out a long cooldown and say loudly what is actually wrong.
  stall=5
  log "AUTH FAILURE ($auth_err x 'not a bot'): cookies are not logged in. \
Check profile: $COOKIE_ARG — retrying is futile until this is fixed."
elif [ $((fmt_err + bot_err)) -ge "$THROTTLE_HITS" ]; then
  # Unmistakably throttled: jump straight to a long cooldown rather than
  # doubling up from 15 min (which would just keep poking the wall).
  if [ "$stall" -lt 3 ]; then stall=3; else stall=$((stall + 1)); fi
  log "THROTTLED (fmt_err=$fmt_err bot_err=$bot_err, 0 downloads) — escalating backoff"
else
  stall=$((stall + 1))
fi
delay=0
if [ "$stall" -gt 0 ]; then
  s=$stall; [ "$s" -gt 5 ] && s=5
  delay=$((BASE_DELAY * (1 << s)))
  [ "$delay" -gt "$MAX_DELAY" ] && delay=$MAX_DELAY
fi

# --- remaining = all ids - archived - dead ---
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
grep -oE '[A-Za-z0-9_-]{11}$' "$URLS" | sort -u > "$tmp/all"
awk '{print $2}' "$ARCHIVE" 2>/dev/null | sort -u > "$tmp/arch"
sort -u "$DEAD" > "$tmp/dead"
comm -23 "$tmp/all" "$tmp/arch" | comm -23 - "$tmp/dead" > "$tmp/remaining"
remaining=$(count . "$tmp/remaining")

if [ "$remaining" -eq 0 ]; then
  log "COMPLETE: $done_now downloaded, $(count . "$DEAD") dead, nothing left."
  echo "$now $stall $done_now $win_start $win_base" > "$STATE"
  bail
fi

head -n "$BATCH" "$tmp/remaining" | sed 's#^#https://www.youtube.com/watch?v=#' > "$BATCHFILE"
mv -f "$LNK/download.log" "$LNK/download.log.old" 2>/dev/null || true

log "batch $BATCH | done=$done_now remaining=$remaining dead=$(count . "$DEAD") \
window=$((done_now - win_base))/$QUOTA stall=$stall next_delay=${delay}s"
echo "$((now + delay)) $stall $done_now $win_start $win_base" > "$STATE"

# Drop the lock BEFORE spawning long-lived children (see header).
release_lock
start_pot_server
start_status_page

# `android` is kept as a fallback client: it needs no JS signature challenge, so
# it still works if deno ever goes missing from PATH. Quality is unaffected —
# `-S res,br` sorts across every client's formats and picks the best overall.
# Sleeps are deliberately generous: spreading requests is the single most
# effective defence against the volume wall.
setsid --fork yt-dlp \
  -a "$BATCHFILE" \
  -P "$LNK" \
  --cookies-from-browser "$COOKIE_ARG" \
  --extractor-args "youtube:player_client=default,android" \
  -f 'bv*+ba/b' -S 'res,br,ext:mp4:m4a' \
  --merge-output-format mp4 \
  -o '%(id)s.%(ext)s' \
  --download-archive "$ARCHIVE" \
  --no-overwrites --continue --ignore-errors --no-warnings --newline \
  --retries 10 --fragment-retries 20 --file-access-retries 10 \
  --concurrent-fragments 2 \
  --sleep-requests 4 --sleep-interval 30 --max-sleep-interval 90 \
  > "$LNK/download.log" 2>&1 </dev/null &
echo $! > "$PIDFILE"
