#!/usr/bin/env bash
# Syntax-check the plugin QML. Quickshell and qs.Commons are not installed in
# CI, so import/type/property warnings for those modules are disabled.
# --required is disabled too: Qt 6.4 qmllint does not bind host: on
# DashboardWindow once those imports fail, and reports the property missing
# even though every call site sets it. Syntax errors still fail the run.
set -euo pipefail

root=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
qmllint=${QMLLINT:-/usr/lib/qt6/bin/qmllint}
if [[ ! -x $qmllint ]]; then
  echo "qmllint not found at $qmllint" >&2
  exit 1
fi

cd "$root"
"$qmllint" \
  --import disable \
  --type disable \
  --property disable \
  --unqualified disable \
  --alias disable \
  --required disable \
  Panel.qml DockWindow.qml DashboardWindow.qml
