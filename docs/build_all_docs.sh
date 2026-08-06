#!/usr/bin/env bash
# Build Sphinx HTML (and pyreverse UML, where a package defines it) for every
# documented package in the repo. Run from anywhere — paths resolve against the
# repo root, computed from this script's location.
#
#   ./docs/build_all_docs.sh          # html + uml for everything
#   ./docs/build_all_docs.sh --html   # html only
#   ./docs/build_all_docs.sh --uml    # uml only
#
# Requires sphinx-build (+ furo) on PATH; UML additionally needs pyreverse (pylint).
# Exits non-zero if any build fails.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Every package with a docs/ dir. rxnbench/docs is the combined entry point
# (backend client + frontend); the rest are per-package. Keep this list in sync
# when adding a new device or package with its own docs/.
# Driver packages (devices/<name>/driver/backend/) don't have Sphinx docs set
# up yet - only the capability packages do.
DOC_DIRS=(
  rxnbench/docs
  rxnbench/frontend/docs
  rxnbench/backend/client/docs
  devices/gantry/capability/backend/docs
  devices/ph_sensor/capability/backend/docs
  devices/camera/capability/backend/docs
  devices/device_template/capability/backend/docs
)

do_html=1
do_uml=1
case "${1:-}" in
  --html) do_uml=0 ;;
  --uml)  do_html=0 ;;
  "")     ;;
  *)      echo "usage: $0 [--html|--uml]" >&2; exit 2 ;;
esac

log="$(mktemp)"
trap 'rm -f "$log"' EXIT
fail=0

run() {  # run <target> <dir>
  local target="$1" dir="$2"
  grep -qE "^${target}:" "$dir/Makefile" || return 0
  if make -C "$dir" "$target" >"$log" 2>&1; then
    printf '  %-4s ✓  %s\n' "$target" "$dir"
  else
    printf '  %-4s ✗  %s\n' "$target" "$dir"
    sed 's/^/         /' "$log" | tail -6
    fail=1
  fi
}

for d in "${DOC_DIRS[@]}"; do
  [ -d "$d" ] || { echo "  ---  ⚠  $d (missing, skipped)"; continue; }
  [ "$do_html" = 1 ] && run html "$d"
  [ "$do_uml" = 1 ] && run uml "$d"
done

echo
if [ "$fail" = 0 ]; then
  echo "All docs built. HTML: <package>/docs/_build/html/index.html   UML: <package>/docs/_uml/*.png"
else
  echo "Some builds failed (see above)." >&2
fi
exit "$fail"
