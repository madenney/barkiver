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

# cron has a minimal PATH — yt-dlp lives in ~/.local/bin, node under nvm.
export PATH="$HOME/.local/bin:$HOME/.nvm/versions/node/v25.2.1/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin"

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

BATCH=15               # videos attempted per drip (small: a walled batch wastes few requests)
QUOTA=120              # max completed videos per rolling window
WINDOW=43200           # 12 h rolling window  -> ~240/day, well under the ~208-in-one-burst wall
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

# Downloader still working? leave it be.
pgrep -x yt-dlp >/dev/null 2>&1 && bail

now=$(date +%s)
next_at=0; stall=0; last_done=0; win_start=0; win_base=0
if [ -f "$STATE" ]; then
  read -r next_at stall last_done win_start win_base < "$STATE" 2>/dev/null || true
fi
: "${next_at:=0}"; : "${stall:=0}"; : "${last_done:=0}"; : "${win_start:=0}"; : "${win_base:=0}"

[ "$now" -lt "$next_at" ] && bail   # cooling off

touch "$DEAD"
done_now=$(grep -c . "$ARCHIVE" 2>/dev/null || echo 0)

# --- harvest permanently-dead ids from the last batch's log ---
# "try again later" is the THROTTLE message, not a dead video. Exclude it.
fmt_err=0; bot_err=0
if [ -f "$LNK/download.log" ]; then
  grep '^ERROR' "$LNK/download.log" 2>/dev/null \
    | grep -v 'try again later' \
    | grep -iE 'no longer available because the YouTube account|This video is private|Private video|removed by the uploader|blocked due to the claimed content|Video unavailable' \
    | grep -oE '\[youtube\] [A-Za-z0-9_-]{11}' | awk '{print $2}' >> "$DEAD"
  sort -u -o "$DEAD" "$DEAD"
  fmt_err=$(grep -c 'Requested format is not available' "$LNK/download.log" 2>/dev/null || echo 0)
  bot_err=$(grep -ciE "not a bot|try again later" "$LNK/download.log" 2>/dev/null || echo 0)
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
else
  if [ $((fmt_err + bot_err)) -ge "$THROTTLE_HITS" ]; then
    # Unmistakably throttled: jump straight to a long cooldown rather than
    # doubling up from 15 min (which would just keep poking the wall).
    [ "$stall" -lt 3 ] && stall=3 || stall=$((stall + 1))
    log "THROTTLED (fmt_err=$fmt_err bot_err=$bot_err, 0 downloads) — escalating backoff"
  else
    stall=$((stall + 1))
  fi
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
remaining=$(grep -c . "$tmp/remaining" || echo 0)

if [ "$remaining" -eq 0 ]; then
  log "COMPLETE: $done_now downloaded, $(grep -c . "$DEAD") dead, nothing left."
  echo "$now $stall $done_now $win_start $win_base" > "$STATE"
  bail
fi

head -n "$BATCH" "$tmp/remaining" | sed 's#^#https://www.youtube.com/watch?v=#' > "$BATCHFILE"
mv -f "$LNK/download.log" "$LNK/download.log.old" 2>/dev/null || true

log "batch $BATCH | done=$done_now remaining=$remaining dead=$(grep -c . "$DEAD") \
window=$((done_now - win_base))/$QUOTA stall=$stall next_delay=${delay}s"
echo "$((now + delay)) $stall $done_now $win_start $win_base" > "$STATE"

# Drop the lock BEFORE spawning long-lived children (see header).
release_lock
start_pot_server
start_status_page

# player_client=default keeps yt-dlp off the `web_creator` client, whose format
# ladder is crippled. Sleeps are deliberately generous: spreading requests is the
# single most effective defence against the volume wall.
setsid --fork yt-dlp \
  -a "$BATCHFILE" \
  -P "$LNK" \
  --cookies-from-browser firefox \
  --extractor-args "youtube:player_client=default" \
  -f 'bv*+ba/b' -S 'res,br,ext:mp4:m4a' \
  --merge-output-format mp4 \
  -o '%(id)s.%(ext)s' \
  --download-archive "$ARCHIVE" \
  --no-overwrites --continue --ignore-errors --no-warnings --newline \
  --retries 10 --fragment-retries 20 --file-access-retries 10 \
  --concurrent-fragments 3 \
  --sleep-requests 3 --sleep-interval 20 --max-sleep-interval 60 \
  > "$LNK/download.log" 2>&1 </dev/null &
echo $! > "$PIDFILE"
