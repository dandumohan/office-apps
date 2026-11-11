#!/usr/bin/env bash
# Supabase (Free plan) database backup for Ubuntu/Linux
#
# Setup (one time):
#   1. sudo apt update && sudo apt install -y postgresql-client
#      (Supabase runs a recent Postgres; if pg_dump complains about a version
#       mismatch, install a newer client from https://www.postgresql.org/download/linux/ubuntu/)
#   2. Supabase > Settings > Database > Connection string > copy the URI.
#      - Try the Direct connection first.
#      - If it says "host not found"/"network unreachable", use the Session pooler
#        string (port 5432). Direct is IPv6-only on the Free plan.
#   3. Save it in a private file (not in this script):
#        mkdir -p ~/.config && echo 'postgresql://postgres:YOUR_PASSWORD@db.YOUR_REF.supabase.co:5432/postgres' > ~/.config/supabase_db_url
#        chmod 600 ~/.config/supabase_db_url
#      (or export SUPABASE_DB_URL in your environment instead)
#   4. chmod +x backup-supabase.sh
#
# Run:  ./backup-supabase.sh
# Cron (daily 2:00 AM):  crontab -e  ->  0 2 * * * /full/path/backup-supabase.sh >> /full/path/supabase-backups/backup.log 2>&1

set -euo pipefail

DB_URL="${SUPABASE_DB_URL:-}"
if [ -z "$DB_URL" ] && [ -f "$HOME/.config/supabase_db_url" ]; then
  DB_URL="$(< "$HOME/.config/supabase_db_url")"
fi
if [ -z "$DB_URL" ]; then
  echo "Set SUPABASE_DB_URL or create ~/.config/supabase_db_url (see setup notes at top)." >&2
  exit 1
fi

for tool in pg_dump pg_restore; do
  command -v "$tool" >/dev/null 2>&1 || { echo "$tool not found. Run: sudo apt install postgresql-client" >&2; exit 1; }
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/supabase-backups"
mkdir -p "$BACKUP_DIR"

STAMP="$(date +%Y-%m-%d_%H%M)"
FILE="$BACKUP_DIR/supabase_$STAMP.dump"

echo "Backing up to $FILE ..."
if ! pg_dump --format=custom --no-owner --no-privileges --file="$FILE" "$DB_URL"; then
  rm -f "$FILE"
  echo "pg_dump failed." >&2
  exit 1
fi

# Verify the dump is readable
if ! pg_restore --list "$FILE" >/dev/null; then
  echo "Backup file failed verification." >&2
  exit 1
fi

echo "Backup OK: $FILE ($(du -h "$FILE" | cut -f1))"

# Keep only the last 14 days
find "$BACKUP_DIR" -name 'supabase_*.dump' -mtime +14 -delete

echo "Done."
