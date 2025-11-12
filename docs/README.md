# Documentation Index

이 디렉토리는 CrowdWorks Multi-Agent RAG System의 기술 문서를 포함합니다.

## 문서 구조

### /evaluation - 성능 평가 및 벤치마크 문서
- **PERFORMANCE_EVALUATION_REPORT.md**: Multi-Agent RAG 시스템 성능평가 보고서
  - 평가 일시: 2025-11-10
  - 평가 대상: 5개 페르소나 × 3개 쿼리 = 15개 보고서
  - AI Judge 기반 자동 평가 (Gemini 2.5 Flash)
  - 7개 KPI 종합 평가 (Task Success, Quality, Completeness, Hallucination, Efficiency, Source Quality, Content)

### /system-architecture - 시스템 아키텍처 문서
- (향후 시스템 설계 문서 추가 예정)

## 평가 결과 데이터

실제 평가 실행 결과 데이터는 `/evaluation_results` 디렉토리에 저장됩니다:
- CSV/Excel/JSON 형식의 벤치마크 결과
- 차트 이미지 (score_distribution.png, grade_distribution.png 등)
- 개별 평가 상세 결과

## 관련 문서

- [프로젝트 README](../README.md): 프로젝트 개요 및 시작 가이드
- [multiagent-rag-system README](../multiagent-rag-system/README.md): 개발자 문서 및 기술 상세
