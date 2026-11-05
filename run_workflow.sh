#!/usr/bin/env bash
# Run the published workflow from the repository root. Usage: ./run_workflow.sh [RUN_ID]
set -euo pipefail
cd "$(dirname "$0")"
RUN="${1:-run}"
PY="${PYTHON:-python}"
ENTRY="processed"; [ -f data/regional/external/nation.gpkg ] && ENTRY="raw"
"$PY" code/01_data_preparation.py --run-id "$RUN" --entry "$ENTRY"
"$PY" code/01b_deduplication.py --run-id "$RUN"
"$PY" code/02_data_processing.py --run-id "$RUN"
"$PY" code/03_AHP_analysis.py --run-id "$RUN"
"$PY" code/04_sensitivity_analysis.py --run-id "$RUN"
"$PY" code/05_figures.py --run-id "$RUN"
"$PY" code/test_no_obsolete_performance_ratio.py --run-id "$RUN"
"$PY" code/validate_results.py --run-id "$RUN"
