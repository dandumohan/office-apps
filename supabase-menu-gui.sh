#!/usr/bin/env bash
# Graphical menu (zenity) for Supabase backup tasks on Ubuntu
# Dropdown: Backup | Restore | Crontab job | Crontab list
#
# One-time:  sudo apt install -y zenity postgresql-client
# Run:       chmod +x supabase-menu-gui.sh && ./supabase-menu-gui.sh

BASE_DIR="/home/tharun/Downloads/msource2026"
BACKUP_SCRIPT="$BASE_DIR/backup-supabase.sh"
BACKUP_DIR="$BASE_DIR/supabase-backups"
LOG_FILE="$BACKUP_DIR/backup.log"
URL_FILE="$HOME/.config/supabase_db_url"
TITLE="Supabase Backup Manager"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT

if ! command -v zenity >/dev/null 2>&1; then
  echo "zenity not installed. Run: sudo apt install -y zenity" >&2
  exit 1
fi

info()  { zenity --info  --title="$TITLE" --width=380 --text="$1"; }
error() { zenity --error --title="$TITLE" --width=380 --text="$1"; }
show_output() {  # show contents of $OUT in a scrollable window
  zenity --text-info --title="$1" --filename="$OUT" --width=760 --height=480 --font="monospace 10"
}

# Run a command with a busy animation; output captured in $OUT; returns its exit code
run_with_progress() {  # message, command...
  local msg="$1"; shift
  : > "$OUT"
  "$@" > "$OUT" 2>&1 &
  local pid=$!
  ( while kill -0 "$pid" 2>/dev/null; do echo "# $msg"; sleep 1; done ) |
    zenity --progress --title="$TITLE" --pulsate --auto-close --no-cancel --width=380 --text="$msg"
  wait "$pid"
}

PW=""
ask_sudo_password() {
  [ -n "$PW" ] && return 0
  PW="$(zenity --password --title="$TITLE" --text="Enter your Ubuntu password (needed to restore into local PostgreSQL)")" || return 1
}
psudo() { printf '%s\n' "$PW" | sudo -S -p '' -u postgres "$@"; }

# The database URL (contains the password) is never stored in this script.
# It is read from $URL_FILE (chmod 600); if missing, you are asked once and it is saved there.
ensure_db_url() {
  mkdir -p "$(dirname "$URL_FILE")"
  if [ -s "$URL_FILE" ]; then chmod 600 "$URL_FILE"; return 0; fi
  local url
  url="$(zenity --entry --hide-text --title="$TITLE" --width=520 \
        --text="Enter your Supabase database URL (postgresql://postgres:PASSWORD@db.xxxx.supabase.co:5432/postgres).\nIt is saved only on this computer in $URL_FILE")" || return 1
  [[ "$url" =~ ^postgres(ql)?:// ]] || { error "That does not look like a postgresql:// URL."; return 1; }
  ( umask 077; printf '%s\n' "$url" > "$URL_FILE" )
}

# ---------- Backup ----------
do_backup() {
  mkdir -p "$BACKUP_DIR"
  ensure_db_url || return
  [ -f "$BACKUP_SCRIPT" ] || { error "Cannot find:\n$BACKUP_SCRIPT"; return; }
  chmod +x "$BACKUP_SCRIPT"
  run_with_progress "Backing up Supabase database... please wait" "$BACKUP_SCRIPT"
  local rc=$?
  if [ $rc -eq 0 ]; then
    info "<b>Backup completed.</b>\n\n$(tail -n 3 "$OUT")"
  else
    show_output "Backup FAILED"
  fi
}

# ---------- Restore ----------
do_restore() {
  local file target
  file="$(zenity --file-selection --title="Choose a backup (.dump) to restore" \
          --filename="$BACKUP_DIR/" --file-filter='Dump files | *.dump')" || return
  target="$(zenity --entry --title="$TITLE" --text="Local database name to restore into:" --entry-text="testdb")" || return
  if [[ ! "$target" =~ ^[A-Za-z0-9_]+$ ]]; then
    error "Database name may contain only letters, numbers and underscore."; return
  fi
  zenity --question --title="Confirm restore" --width=420 --ok-label="Restore" --cancel-label="Cancel" \
    --text="Restore <b>$(basename "$file")</b>\ninto LOCAL database <b>$target</b> (public schema only)?\n\nIf <b>$target</b> exists it will be <b>dropped</b> and recreated." || return
  ask_sudo_password || return
  local tmp="/tmp/$(basename "$file")"
  cp "$file" "$tmp" && chmod 644 "$tmp"
  restore_job() {
    psudo dropdb --if-exists "$target" &&
    psudo createdb "$target" &&
    psudo pg_restore --no-owner --no-privileges -n public --dbname="$target" "$tmp"
    local rc=$?
    echo; echo "--- Tables in $target ---"
    psudo psql -d "$target" -c '\dt public.*'
    return $rc
  }
  run_with_progress "Restoring into '$target'..." restore_job
  rm -f "$tmp"
  show_output "Restore result"
}

# ---------- Crontab ----------
valid_field() {  # value min max
  local v="$1" min="$2" max="$3" n
  [[ "$v" =~ ^(\*|\*/[0-9]+|[0-9]+(-[0-9]+)?(/[0-9]+)?(,[0-9]+(-[0-9]+)?(/[0-9]+)?)*)$ ]] || return 1
  [[ "$v" == \*/* ]] && return 0
  for n in $(grep -oE '[0-9]+' <<< "$v"); do
    [ "$n" -ge "$min" ] && [ "$n" -le "$max" ] || return 1
  done
}

do_cron_job() {
  local res minute hour dom month dow bad
  while true; do
    res="$(zenity --forms --title="Backup schedule (crontab)" --width=420 \
      --text="Leave * for 'every'. Examples: 5 | */10 | 1-5 | 1,15" \
      --separator='|' \
      --add-entry="Minute (0-59)" \
      --add-entry="Hour (0-23)" \
      --add-entry="Day of month (1-31)" \
      --add-entry="Month (1-12)" \
      --add-entry="Day of week (0-7, 0=Sun)")" || return
    IFS='|' read -r minute hour dom month dow <<< "$res"
    minute="${minute:-0}"; hour="${hour:-2}"; dom="${dom:-*}"; month="${month:-*}"; dow="${dow:-*}"
    bad=""
    valid_field "$minute" 0 59 || bad="Minute"
    valid_field "$hour"   0 23 || bad="Hour"
    valid_field "$dom"    1 31 || bad="Day of month"
    valid_field "$month"  1 12 || bad="Month"
    valid_field "$dow"    0 7  || bad="Day of week"
    [ -z "$bad" ] && break
    error "Invalid value in: <b>$bad</b>\nAllowed: * , */5 , 7 , 1-5 , 1,15"
  done
  local line="$minute $hour $dom $month $dow $BACKUP_SCRIPT >> $LOG_FILE 2>&1"
  zenity --question --title="Confirm cron job" --width=560 --ok-label="Apply" --cancel-label="Cancel" \
    --text="Add this entry to your crontab?\n(Replaces any existing backup-supabase entry)\n\n<tt>$line</tt>" || return
  mkdir -p "$BACKUP_DIR"
  ( crontab -l 2>/dev/null | grep -vF "$BACKUP_SCRIPT"; echo "$line" ) | crontab -
  crontab -l > "$OUT" 2>&1
  show_output "Crontab updated - current entries"
}

do_cron_list() {
  if ! crontab -l > "$OUT" 2>/dev/null; then echo "(no crontab for $USER)" > "$OUT"; fi
  show_output "crontab -l"
}

# ---------- Main: dropdown ----------
while true; do
  choice="$(zenity --forms --title="$TITLE" --width=420 \
    --text="Choose an action and press OK" \
    --add-combo="Action" --combo-values="Backup|Restore|Crontab job|Crontab list")" || exit 0
  case "$choice" in
    "Backup")       do_backup ;;
    "Restore")      do_restore ;;
    "Crontab job")  do_cron_job ;;
    "Crontab list") do_cron_list ;;
    *)              error "Please select an action from the dropdown." ;;
  esac
done
