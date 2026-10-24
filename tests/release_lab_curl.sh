#!/usr/bin/env bash
# Test-only transport for unpublished candidates; installer hashes stay enforced.
set -euo pipefail
prefix=https://raw.githubusercontent.com/Elegying/Hysteria2-panel/lab-candidate/
source_path='' destination='' previous=''
for argument in "$@"; do
  [[ "${previous}" != -o ]] || destination="${argument}"
  if [[ "${argument}" == "${prefix}"* ]]; then
    source_path="${argument#"${prefix}"}"
  fi
  previous="${argument}"
done
if [[ -n "${source_path}" ]]; then
  [[ "${container:-}" == docker && -f /workspace/.release-lab ]]
  [[ -n "${destination}" ]]
  case "${source_path}" in
    hysteria2_panel.py|offsite_backup.py|qrcodegen.py|tcp_probe.py|node_agent.py|hy2panel/*.py) ;;
    *) echo 'Candidate transport rejected unexpected path' >&2; exit 22 ;;
  esac
  [[ "${source_path}" != *..* && -f "/workspace/${source_path}" ]]
  cp -- "/workspace/${source_path}" "${destination}"
  exit 0
fi
exec /usr/bin/curl "$@"
