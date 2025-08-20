#!/usr/bin/env bash
set -euo pipefail

LOGFILE="log.out"
# (초기화 구문 삭제 → 기존 로그 유지하며 이어쓰기)

# 순차 실행할 서비스 목록
services=(
  atfis_krei
  atfis_related
  market_segment
  newsletters
  static_reports
  kamis_foreign
  kamis_investigation
  kati_country
  kati_issue
  kati_item
  krei_observation
  kc_processor
  clear_report_pdf
)

# 실행 시작 시각 기록
{
  echo "==============================================="
  echo "▶▶▶ 전체 실행 시작: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "==============================================="
} | tee -a "$LOGFILE"

docker-compose down --volumes

for svc in "${services[@]}"; do
  {
    echo
    echo "==================================================================="
    echo "▶▶▶ Starting service: ${svc} — $(date '+%Y-%m-%d %H:%M:%S')"
    echo "==================================================================="
  } | tee -a "$LOGFILE"

  docker-compose up \
    --no-color \
    --build \
    --abort-on-container-exit \
    --exit-code-from "${svc}" \
    "${svc}" 2>&1 | tee -a "$LOGFILE"
done

# 마무리: 볼륨 포함 다운
docker-compose down --volumes 2>&1 | tee -a "$LOGFILE"

# 전체 완료 시각 기록
{
  echo
  echo "==================================================================="
  echo "🎉 All services completed successfully: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "==================================================================="
} | tee -a "$LOGFILE"
