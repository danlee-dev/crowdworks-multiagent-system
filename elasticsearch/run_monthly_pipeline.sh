#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/root/workspace/crowdworks/elasticsearch"
LOG_DIR="$WORKDIR/logs"
TIMESTAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
LOG_FILE="$LOG_DIR/monthly_pipeline_$TIMESTAMP.log"
LOCK_FILE="$WORKDIR/.monthly_pipeline.lock"

mkdir -p "$LOG_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
	echo "[$(date '+%F %T')] 다른 실행이 진행 중이어서 종료합니다." | tee -a "$LOG_FILE"
	exit 0
fi

cd "$WORKDIR"

if [ -x "$WORKDIR/venv/bin/python" ]; then
	PYTHON="$WORKDIR/venv/bin/python"
else
	PYTHON="/usr/bin/python3"
fi

run() {
	echo "[$(date '+%F %T')] ▶ $*" | tee -a "$LOG_FILE"
	"$PYTHON" "$@" 2>&1 | tee -a "$LOG_FILE"
}

run page_chunking.py
run embedding.py
run insert.py

echo "[$(date '+%F %T')] ✅ 모든 작업 완료" | tee -a "$LOG_FILE" 