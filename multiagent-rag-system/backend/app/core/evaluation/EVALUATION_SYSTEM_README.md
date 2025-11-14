# 평가 시스템 (Evaluation System)

Multi-Agent RAG 시스템의 보고서 품질을 평가하는 종합 평가 시스템입니다.

## 핵심 특징

- **3-Model Ensemble AI Judge**: Gemini + Claude + GPT-4o 앙상블 평가
- **7개 KPI 종합 평가**: 작업 성공률, 품질, 완성도, 환각, 효율성, 출처 품질, 콘텐츠
- **JSON 기반 평가 지표**: 확장 가능하고 객관적인 평가 기준
- **상세한 결과 저장**: CSV, JSON, 시각화 차트 자동 생성
- **시간별 폴더 관리**: 평가 결과를 시간 기준으로 정리

## 파일 구조

```
evaluation/
├── ensemble_ai_judge.py           # 3-Model Ensemble AI Judge (핵심)
├── evaluation_criteria.json       # 평가 지표 정의 (JSON)
├── detailed_results_exporter.py   # 결과 저장 및 시각화
├── report_evaluator.py            # 평가 오케스트레이터
├── report_evaluation_benchmark.py # 벤치마크 러너
├── automated_evaluator.py         # 자동 평가 (KPI 1,3,5,6,7)
├── ai_judge_evaluator.py          # 단일 모델 AI Judge (레거시)
├── evaluation_models.py           # 데이터 모델
├── visualize_results.py           # 시각화 도구
└── evaluation_queries.txt         # 테스트 쿼리
```

## 주요 컴포넌트

### 1. Ensemble AI Judge (`ensemble_ai_judge.py`)

3개 LLM 모델의 앙상블 평가로 편향을 줄이고 신뢰도를 높입니다.

| 모델 | 버전 | 가중치 | 강점 |
|------|------|--------|------|
| Gemini | 2.0-flash-exp | 34% | 사실 정확도, 인용 검증 |
| Claude | 3.5-sonnet-20241022 | 33% | 논리적 일관성, 요구사항 분석 |
| GPT | 4o | 33% | 종합 품질, 객관적 평가 |

**사용 예시:**
```python
from app.core.evaluation.ensemble_ai_judge import EnsembleAIJudge

judge = EnsembleAIJudge()
result = judge.evaluate_output_quality(query, report, sources)
print(f"종합 품질: {result.overall_quality_score}/10")
print(f"개별 모델 점수: {result.individual_scores}")
```

### 2. 평가 지표 JSON (`evaluation_criteria.json`)

모든 평가 기준을 JSON으로 정의하여 확장성과 명확성을 확보합니다.

**주요 섹션:**
- `evaluation_models`: 3개 모델 설정 (API 키, 가중치, 강점)
- `kpi_metrics`: 7개 KPI 상세 정의
- `evaluation_requirements`: 필수/선택 요구사항
- `ai_judge_prompts`: AI Judge 프롬프트 템플릿
- `ensemble_config`: 앙상블 집계 방법
- `grading_scale`: 등급 기준 (A+~F)

**평가 지표 수정 방법:**
```json
{
  "kpi_metrics": {
    "task_success_rate": {
      "weight": 0.25,
      "evaluation_elements": {
        "new_element": {
          "weight": 0.20,
          "criteria": ["기준 1", "기준 2"]
        }
      }
    }
  }
}
```

### 3. 상세 결과 저장 (`detailed_results_exporter.py`)

평가 결과를 시간별 폴더에 저장하고 시각화합니다.

**저장 구조:**
```
evaluation_results/
└── 20251114_153000/              # 평가 시간 기준
    ├── charts/                   # 시각화 차트 (8개)
    │   ├── 01_score_distribution.png
    │   ├── 02_grade_distribution.png
    │   ├── 03_team_comparison.png
    │   ├── 04_time_vs_score.png
    │   ├── 05_hallucination_analysis.png
    │   ├── 06_kpi_radar.png
    │   ├── 07_source_analysis.png
    │   └── 08_dashboard.png
    ├── csv/                      # 상세 CSV (6개)
    │   ├── 01_all_results.csv    # 전체 결과
    │   ├── 02_scores_detail.csv  # 점수 상세
    │   ├── 03_ai_judge_reasoning.csv  # AI Judge 평가 근거
    │   ├── 04_feedback_detail.csv     # 강점/약점/추천
    │   ├── 05_team_summary.csv   # 팀별 요약
    │   └── 06_grade_distribution.csv  # 등급 분포
    ├── json/                     # JSON 결과 (2개)
    │   ├── full_results.json     # 전체 raw data
    │   └── summary_stats.json    # 요약 통계
    └── SUMMARY.md                # 요약 보고서
```

### 4. 벤치마크 러너 (`report_evaluation_benchmark.py`)

API를 통해 보고서를 생성하고 실시간으로 평가합니다.

**사용 방법:**
```python
from app.core.evaluation.report_evaluation_benchmark import ReportEvaluationBenchmark

# 초기화
benchmark = ReportEvaluationBenchmark(
    base_url="http://localhost:8000",
    use_ai_judge=True,
    use_ensemble=True  # 3-Model Ensemble 사용
)

# 실행
results = await benchmark.run_benchmark()

# 요약 출력
benchmark.print_summary(results['summary'])
```

## 사용 가이드

### 1. 단일 보고서 평가

```python
from app.core.evaluation import ReportEvaluator

# Ensemble AI Judge로 평가 (권장)
evaluator = ReportEvaluator(use_ai_judge=True, use_ensemble=True)

# 평가 실행
result = evaluator.evaluate_report(
    query="2024년 대체육 시장 동향 보고서를 작성해주세요",
    state=state,
    team_type="marketing"
)

# 결과 확인
print(f"종합 점수: {result.overall_score}/10")
print(f"등급: {result.grade}")
print(f"품질: {result.output_quality.overall_quality_score}/10")
print(f"환각: {result.hallucination.hallucination_count}건")
```

### 2. 벤치마크 실행

```bash
# Python 스크립트 실행
cd /root/workspace/crowdworks/crowdworks-multiagent-system/multiagent-rag-system/backend
python -m app.core.evaluation.report_evaluation_benchmark
```

또는

```python
import asyncio
from app.core.evaluation.report_evaluation_benchmark import ReportEvaluationBenchmark

async def main():
    benchmark = ReportEvaluationBenchmark(
        base_url="http://localhost:8000",
        use_ai_judge=True,
        use_ensemble=True
    )

    results = await benchmark.run_benchmark()
    benchmark.print_summary(results['summary'])

asyncio.run(main())
```

### 3. 평가 지표 커스터마이즈

`evaluation_criteria.json` 파일을 수정하여 평가 지표를 추가/변경:

```json
{
  "kpi_metrics": {
    "custom_metric": {
      "name": "커스텀 메트릭",
      "weight": 0.05,
      "description": "새로운 평가 지표",
      "measurement_type": "automatic",
      "evaluation_elements": {
        "element1": {
          "description": "평가 요소 1",
          "weight": 0.50,
          "criteria": ["기준 1", "기준 2"]
        }
      }
    }
  }
}
```

## 평가 프로세스

1. **자동 평가 수행** (KPI 1,3,5,6,7)
   - 작업 성공률: 요구사항 충족도
   - 완성도: 섹션 완성률
   - 효율성: 실행 시간, API 호출, 토큰 사용량
   - 출처 품질: 신뢰도 + 다양성
   - 콘텐츠: 단어 수, 섹션 수, 차트 수

2. **AI Judge 평가 수행** (KPI 2,4)
   - 3개 모델이 병렬로 평가
   - 각 모델이 JSON 형식으로 점수 + 근거 반환
   - 가중 평균으로 앙상블 집계
   - 점수 차이 3점 이상 시 중앙값 사용

3. **종합 점수 계산**
   ```
   Overall Score =
       (Task Success × 0.25) +
       (Quality × 0.25) +
       (Completeness × 0.20) +
       ((10 - Hallucination × 2) × 0.15) +
       (Efficiency × 0.10) +
       (Source Quality × 0.05)
   ```

4. **결과 저장**
   - CSV: 상세한 평가 지표와 근거
   - JSON: 전체 raw data
   - Charts: 8개 시각화 차트
   - Markdown: 요약 보고서

## 환경 변수

`.env` 파일에 평가용 API 키 설정:

```bash
# Gemini (기존 키 사용)
GEMINI_API_KEY_1=your-gemini-api-key

# Claude (평가용)
EVALUATION_CLAUDE_API_KEY=your-claude-api-key

# OpenAI (평가용)
EVALUATION_OPENAI_API_KEY=your-openai-api-key
```

## 성능 및 비용

### 평가 시간
- 단일 보고서: 약 10-15초 (Ensemble AI Judge 사용 시)
- 15개 보고서 벤치마크: 약 30-40분 (보고서 생성 포함)

### API 비용 (15개 보고서 기준)
- Gemini 2.5 Flash: 약 $0.50
- Claude 3.5 Sonnet: 약 $2.00
- GPT-4o: 약 $1.50
- **총 비용: 약 $4.00**

## 트러블슈팅

### 1. API 키 오류
```
ValueError: EVALUATION_CLAUDE_API_KEY 환경변수가 설정되지 않았습니다.
```
→ `.env` 파일에 `EVALUATION_CLAUDE_API_KEY` 추가

### 2. JSON 파싱 오류
```
⚠ claude JSON 파싱 실패
```
→ 정상 동작 (fallback 메커니즘으로 점수 추출)

### 3. 메모리 부족
→ `use_ensemble=False`로 단일 모델만 사용

### 4. 한글 폰트 오류
```
UserWarning: Glyph ... missing from current font
```
→ NanumGothic 폰트 설치:
```bash
apt-get install fonts-nanum
```

## 참고 자료

- [평가 지표 정의](./evaluation_criteria.json)
- [성능 평가 보고서](../../../../../docs/evaluation/PERFORMANCE_EVALUATION_REPORT.md)
- [기존 README](./README.md)

---

**작성일:** 2025-11-14
**버전:** 2.0 (3-Model Ensemble)
