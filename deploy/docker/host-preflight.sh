#!/usr/bin/env bash
# Run in Git Bash from any directory. PowerShell performs the host-native probes.
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo 'Usage: bash deploy/docker/host-preflight.sh data/host-preflight-NAME [PowerShell options]' >&2
  exit 2
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$script_dir/../.." && pwd)"
output="$1"
shift
if [[ "$output" != /* && ! "$output" =~ ^[A-Za-z]: ]]; then
  output="$repo/$output"
fi
if ! command -v cygpath >/dev/null 2>&1; then
  echo 'Git Bash cygpath is required; no report was created.' >&2
  exit 2
fi
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$script_dir/host-preflight.ps1")" -OutputDir "$(cygpath -w "$output")" "$@"
