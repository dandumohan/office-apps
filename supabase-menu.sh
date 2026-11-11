#!/usr/bin/env bash
# Menu for Supabase backup tasks (Ubuntu)
# Options: Backup | Restore | Crontab job | Crontab list | Quit
# Run:  chmod +x supabase-menu.sh && ./supabase-menu.sh

BASE_DIR="/home/tharun/Downloads/msource2026"
BACKUP_SCRIPT="$BASE_DIR/backup-supabase.sh"
BACKUP_DIR="$BASE_DIR/supabase-backups"
LOG_FILE="$BACKUP_DIR/backup.log"
URL_FILE="$HOME/.config/supabase_db_url"
DB_URL='postgresql://postgres:DanduTahrun@db.ewnrcnfyiulrjritaeam.supabase.co:5432/postgres'

do_backup() {
  mkdir -p "$HOME/.config" "$BACKUP_DIR"
  echo "$DB_URL" > "$URL_FILE"
  chmod 600 "$URL_FILE"
  echo "Saved connection string to $URL_FILE"
  if [ ! -x "$BACKUP_SCRIPT" ]; then
    chmod +x "$BACKUP_SCRIPT" 2>/dev/null || { echo "Cannot find $BACKUP_SCRIPT"; return 1; }
  fi
  "$BACKUP_SCRIPT"
}

do_restore() {
  shopt -s nullglob
  local files=("$BACKUP_DIR"/supabase_*.dump)
  shopt -u nullglob
  if [ ${#files[@]} -eq 0 ]; then
    echo "No .dump files found in $BACKUP_DIR. Run Backup first."
    return 1
  fi
  echo "Choose the backup file to restore:"
  local f
  select f in "${files[@]}" "Cancel"; do
    [ "$f" = "Cancel" ] && return 0
    [ -n "$f" ] && break
    echo "Invalid choice."
  done
  read -r -p "Local database name to restore into [testdb]: " target
  target="${target:-testdb}"
  if [[ ! "$target" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "Database name may contain only letters, numbers and underscore."
    return 1
  fi
  # Copy where the postgres user can read it
  local tmp="/tmp/$(basename "$f")"
  cp "$f" "$tmp" && chmod 644 "$tmp"
  echo "This restores only the 'public' schema into the LOCAL database '$target'."
  read -r -p "If '$target' exists it will be DROPPED and recreated. Continue? [y/N]: " ok
  [[ "$ok" =~ ^[Yy]$ ]] || { echo "Cancelled."; rm -f "$tmp"; return 0; }
  sudo -u postgres dropdb --if-exists "$target"
  sudo -u postgres createdb "$target" || { rm -f "$tmp"; return 1; }
  sudo -u postgres pg_restore --no-owner --no-privileges -n public --dbname="$target" "$tmp"
  rm -f "$tmp"
  echo "Tables restored into '$target':"
  sudo -u postgres psql -d "$target" -c '\dt public.*'
}

# Ask for a cron field and validate it (number, *, */n, ranges, lists)
ask_field() {  # prompt default regex-min regex-max -> echoes value
  local prompt="$1" def="$2" min="$3" max="$4" v
  while true; do
    read -r -p "$prompt [$def]: " v
    v="${v:-$def}"
    if [[ "$v" =~ ^(\*|\*/[0-9]+|[0-9]+(-[0-9]+)?(/[0-9]+)?(,[0-9]+(-[0-9]+)?(/[0-9]+)?)*)$ ]]; then
      # numeric bounds check on plain numbers
      local ok=1 n
      for n in $(echo "$v" | grep -oE '[0-9]+' ); do
        if [[ "$v" == \*/* ]]; then continue; fi
        if [ "$n" -lt "$min" ] || [ "$n" -gt "$max" ]; then ok=0; fi
      done
      [ $ok -eq 1 ] && { echo "$v"; return; }
    fi
    echo "  Invalid. Allowed: * , */5 , 7 , 1-5 , 1,15 (range $min-$max)." >&2
  done
}

do_cron_job() {
  echo "Enter the schedule (press Enter to accept the default shown)."
  local minute hour dom month dow
  minute=$(ask_field "Minute        (0-59)" "0" 0 59)
  hour=$(ask_field   "Hour          (0-23)" "2" 0 23)
  dom=$(ask_field    "Day of month  (1-31)" "*" 1 31)
  month=$(ask_field  "Month         (1-12)" "*" 1 12)
  dow=$(ask_field    "Day of week   (0-7, 0/7=Sunday)" "*" 0 7)
  local line="$minute $hour $dom $month $dow $BACKUP_SCRIPT >> $LOG_FILE 2>&1"
  echo
  echo "Cron entry:"
  echo "  $line"
  read -r -p "Apply to your crontab? (replaces any existing backup-supabase entry) [y/N]: " ok
  [[ "$ok" =~ ^[Yy]$ ]] || { echo "Cancelled."; return 0; }
  mkdir -p "$BACKUP_DIR"
  ( crontab -l 2>/dev/null | grep -vF "$BACKUP_SCRIPT"; echo "$line" ) | crontab -
  echo "Crontab updated. Current crontab:"
  crontab -l
}

do_cron_list() {
  if ! crontab -l 2>/dev/null; then
    echo "(no crontab for $USER)"
  fi
}

echo "=== Supabase backup menu ==="
PS3="Select an option number: "
select choice in "Backup" "Restore" "Crontab job" "Crontab list" "Quit"; do
  case "$choice" in
    "Backup")       do_backup ;;
    "Restore")      do_restore ;;
    "Crontab job")  do_cron_job ;;
    "Crontab list") do_cron_list ;;
    "Quit")         echo "Bye."; break ;;
    *)              echo "Invalid choice." ;;
  esac
  echo
done
