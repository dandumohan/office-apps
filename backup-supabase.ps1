# Supabase (Free plan) database backup for Windows PowerShell
#
# Setup (one time):
#   1. Install PostgreSQL client tools (pg_dump / pg_restore) and make sure they are on PATH.
#   2. In Supabase: Settings > Database > Connection string, copy the URI.
#      - Try the Direct connection first.
#      - If pg_dump says it cannot connect / host not found, copy the Session pooler
#        string (port 5432) instead. The direct host is IPv6-only unless you buy the
#        IPv4 add-on, and many home ISPs do not support IPv6.
#   3. Store it in an environment variable so the password is not saved in this file:
#        setx SUPABASE_DB_URL "postgresql://postgres:YOUR_PASSWORD@db.YOUR_REF.supabase.co:5432/postgres"
#      Then open a NEW PowerShell window.
#
# Run:  powershell -ExecutionPolicy Bypass -File .\backup-supabase.ps1

$ErrorActionPreference = "Stop"

$dbUrl = $env:SUPABASE_DB_URL
if (-not $dbUrl) { throw "Set the SUPABASE_DB_URL environment variable first (see setup notes at the top)." }

foreach ($tool in @("pg_dump", "pg_restore")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool not found. Install PostgreSQL client tools and add them to PATH."
    }
}

$backupDir = Join-Path $PSScriptRoot "supabase-backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$file  = Join-Path $backupDir "supabase_$stamp.dump"

Write-Host "Backing up to $file ..."
pg_dump --format=custom --no-owner --no-privileges --file="$file" "$dbUrl"
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed (exit code $LASTEXITCODE)." }

# Verify the dump is readable (fails if the file is corrupt or truncated)
pg_restore --list "$file" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Backup file failed verification." }

$sizeMb = [math]::Round((Get-Item $file).Length / 1MB, 2)
Write-Host "Backup OK: $file ($sizeMb MB)"

# Keep only the last 14 days of backups
Get-ChildItem $backupDir -Filter "supabase_*.dump" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force

Write-Host "Done."
