# 보고서 평가 시스템 가이드

## 목차
1. [개요](#개요)
2. [평가 지표 (KPI)](#평가-지표-kpi)
3. [자동 평가 vs AI 심판 평가](#자동-평가-vs-ai-심판-평가)
4. [종합 점수 계산](#종합-점수-계산)
5. [평가 실행 방법](#평가-실행-방법)
6. [평가 결과 해석](#평가-결과-해석)
7. [출력 파일 구조](#출력-파일-구조)

---

## 개요

Multi-Agent RAG 시스템에서 생성된 보고서의 품질을 객관적으로 측정하는 종합 평가 시스템입니다.

### 평가 방식
- **자동 평가**: 규칙 기반으로 측정 가능한 메트릭 (응답 시간, 섹션 개수, 토큰 사용량 등)
- **AI 심판 평가**: Gemini 2.5 Flash LLM을 사용한 품질/정확도/환각 현상 평가

### 평가 목적
1. 보고서 생성 품질의 정량적 측정
2. 시스템 개선 포인트 파악
3. 다양한 페르소나별 성능 비교
4. 환각(Hallucination) 및 인용 정확성 검증

---

## 평가 지표 (KPI)

### 1. 작업 성공률 (Task Success) - 가중치 25%

보고서 생성 작업이 성공적으로 완료되었는지 평가합니다.

**측정 항목**:
- `success_level`: 성공 수준 (COMPLETE_SUCCESS / PARTIAL_SUCCESS / FAILURE)
- `success_rate`: 성공률 (0.0 ~ 1.0)
- `completion_percentage`: 완성도 퍼센트 (0 ~ 100%)
- `is_task_completed`: 작업 완료 여부 (boolean)
- `missing_requirements`: 누락된 요구사항 목록

**평가 기준**:
- 보고서 텍스트가 100자 이상 생성되었는가?
- 요구된 섹션이 모두 포함되었는가?
- 실행 로그에 오류가 없는가?

**점수 산출**:
```
작업 점수 = success_rate × 10
```

---

### 2. 출력 품질 (Output Quality) - 가중치 25%

보고서의 사실 정확도, 논리성, 요구사항 부합도를 평가합니다.

**측정 항목** (AI 심판 평가):
- `factual_accuracy_score`: 사실 정확도 (0 ~ 10점)
- `logical_coherence_score`: 논리적 일관성 (0 ~ 10점)
- `relevance_score`: 요구사항 부합도 (0 ~ 10점)
- `overall_quality_score`: 전체 품질 점수 (0 ~ 10점)
- `has_clear_structure`: 명확한 구조 보유 여부
- `has_proper_citations`: 적절한 인용 포함 여부
- `language_quality`: 언어 품질 (poor/fair/good/excellent)
- `reasoning`: 평가 근거 (상세 설명)

**AI 심판 평가 프롬프트 요소**:
```
1. 사실 정확도: 출처에서 제공된 정보가 정확하게 반영되었는가?
2. 논리적 일관성: 주장과 근거가 논리적으로 연결되는가?
3. 요구사항 부합도: 사용자 질문에 적절히 답변했는가?
4. 구조 명확성: 보고서가 체계적으로 구성되었는가?
5. 인용 적절성: 출처가 명확히 인용되었는가?
```

**점수 산출**:
```
품질 점수 = overall_quality_score (AI 심판이 직접 0-10 점수 부여)
AI 심판 미사용 시 기본값 = 7.0
```

---

### 3. 완성도 (Completeness) - 가중치 20%

보고서에 필요한 섹션과 정보가 완전히 포함되었는지 평가합니다.

**측정 항목** (자동 평가):
- `required_sections_completed`: 완료된 필수 섹션 수
- `total_required_sections`: 총 필수 섹션 수
- `completeness_rate`: 완성도 비율 (0.0 ~ 1.0)
- `missing_sections`: 누락된 섹션 목록
- `incomplete_sections`: 불완전한 섹션 목록
- `schema_completeness_rate`: 스키마 완성도 (0.0 ~ 1.0)

**평가 방식**:

**방식 1: 마크다운 헤더 개수 기반 (기본)**
```python
# 보고서에서 마크다운 헤더 찾기
markdown_headers = re.findall(r'^#+\s+.+', report_text, re.MULTILINE)
total_sections_found = len(markdown_headers)

# 기준: 최소 3개, 최적 6개 섹션
if total_sections_found >= 6:
    completeness_rate = 1.0  # 100%
elif total_sections_found >= 3:
    completeness_rate = total_sections_found / 6  # 50-83%
else:
    completeness_rate = total_sections_found / 3 * 0.5  # 0-50%
```

**방식 2: 섹션 이름 매칭 (선택적)**
```python
# required_sections 제공 시
required = ["요약", "분석", "결론", "권장사항"]
found = [s for s in required if s in report_text]
completeness_rate = len(found) / len(required)
```

**점수 산출**:
```
완성도 점수 = completeness_rate × 10
```

---

### 4. 환각 현상 및 인용 정확성 (Hallucination) - 가중치 15% (역점수)

생성된 보고서에 근거 없는 주장이나 부정확한 인용이 있는지 검증합니다.

**측정 항목** (AI 심판 평가):
- `hallucination_detected`: 환각 현상 감지 여부 (boolean)
- `hallucination_count`: 감지된 환각 현상 개수
- `hallucination_rate`: 환각 현상 비율 (0.0 ~ 1.0)
- `hallucination_examples`: 환각 현상 사례 목록 (statement, reason)
- `unverified_claims`: 검증되지 않은 주장 목록
- `contradictions`: 모순되는 내용 목록
- `citation_accuracy`: **인용 정확도** (0.0 ~ 1.0) - 핵심 지표
- `confidence_score`: 내용 신뢰도 점수 (0.0 ~ 1.0)
- `reasoning`: 평가 근거 (인용 검증 과정 포함)

**환각 현상 유형**:

**1. 인용 부정확성 (Citation Inaccuracy)**
- `[SOURCE:N]` 태그가 붙은 문장이 실제 SOURCE N의 내용과 불일치
- 예: [SOURCE:1]에 "시장 규모 500억"이라는 정보가 없는데 보고서에서 [SOURCE:1] 태그로 인용

**2. 근거 없는 주장 (Unfounded Claims)**
- 제공된 출처 어디에도 없는 정보를 사실처럼 작성
- 예: 출처에 없는 통계 수치나 연구 결과를 임의로 생성

**3. 과장 또는 왜곡 (Exaggeration/Distortion)**
- 출처 내용을 부정확하게 해석하거나 과장
- 예: "소폭 증가"를 "급격한 성장"으로 과장

**AI 심판 평가 프로세스**:

1. **출처 전체 내용 제공**
```python
# 보고서 생성 LLM과 동일한 전체 content 제공
for i, source in enumerate(sources[:10], 1):
    title = source.get('title', f'출처 {i}')
    content = source.get('content', '')  # 전체 내용 (제한 없음)
    url = source.get('url', 'N/A')
```

2. **인용 검증 지시**
```
**평가 방법:**
1. [SOURCE:N] 태그가 있는 모든 문장을 찾으세요
2. 각 문장을 해당 SOURCE N의 실제 내용과 정확히 대조하세요
3. 불일치하거나 출처에 없는 내용은 환각으로 판정하세요
4. 왜 환각인지 구체적인 이유를 명시하세요
```

3. **응답 형식**
```json
{
  "detected": true/false,
  "count": 환각_현상_개수,
  "rate": 환각_비율,
  "examples": [
    {
      "statement": "문제가 되는 문장",
      "reason": "왜 환각인지 상세 설명"
    }
  ],
  "citation_accuracy": 0.0-1.0,  // 인용 정확도
  "reasoning": "평가 근거 상세 설명"
}
```

**점수 산출** (역점수):
```
환각 점수 = (1 - hallucination_rate) × 10
즉, 환각이 많을수록 점수 감점
```

---

### 5. 효율성 (Efficiency) - 가중치 10%

보고서 생성 과정의 시간, 비용, 리소스 효율성을 평가합니다.

**측정 항목** (자동 평가):
- `total_execution_time`: 총 실행 시간 (초)
- `average_step_time`: 평균 단계별 시간 (초)
- `time_to_first_response`: 첫 응답까지 시간 (초)
- `total_tokens_used`: 총 사용 토큰 수
- `total_api_calls`: 총 API 호출 횟수
- `estimated_cost`: 추정 비용 (USD)
- `total_steps`: 총 단계 수
- `redundant_steps`: 중복/불필요한 단계 수
- `efficiency_score`: 효율성 점수 (0 ~ 10)

**효율성 점수 계산**:
```python
# 실행 시간 기반 점수 (30초 기준)
time_score = max(0, 10 - (total_execution_time - 30) / 10)

# API 호출 기반 점수 (10회 기준)
api_score = max(0, 10 - (total_api_calls - 10) / 2)

# 토큰 사용 기반 점수 (10,000 토큰 기준)
token_score = max(0, 10 - (total_tokens_used - 10000) / 2000)

# 가중 평균
efficiency_score = (time_score × 0.4 + api_score × 0.3 + token_score × 0.3)
```

**점수 산출**:
```
효율성 점수 = efficiency_score (자동 계산)
```

---

### 6. 출처 품질 (Source Quality) - 가중치 5%

사용된 출처의 신뢰성과 다양성을 평가합니다.

**측정 항목** (자동 평가):
- `total_sources`: 총 출처 개수
- `reliable_sources`: 신뢰할 수 있는 출처 개수
- `source_diversity`: 출처 다양성 (고유 출처 타입 수)
- `average_source_reliability`: 평균 출처 신뢰도 (0.0 ~ 1.0)
- `citation_accuracy`: 인용 정확도 (0.0 ~ 1.0)
- `source_types`: 사용된 출처 타입 목록
- `unreliable_sources`: 신뢰도 낮은 출처 목록

**출처 신뢰도 기준**:
```python
reliability_scores = {
    'elasticsearch': 0.9,  # 내부 DB
    'neo4j': 0.9,          # 내부 지식 그래프
    'web_search': 0.6,     # 웹 검색 (도메인에 따라 변동)
    'news': 0.7,           # 뉴스
    'academic': 1.0,       # 학술 자료
    'gov': 0.95,           # 정부 기관
}
```

**점수 산출**:
```
출처 품질 점수 = average_source_reliability × 10
```

---

### 7. 콘텐츠 메트릭 (Content Metrics) - 참고용

보고서의 구조적 특성을 측정합니다 (점수에 직접 반영되지 않음).

**측정 항목** (자동 평가):
- `total_word_count`: 총 단어 수
- `total_char_count`: 총 문자 수
- `section_count`: 섹션 개수
- `chart_count`: 차트 개수
- `table_count`: 테이블 개수
- `citation_count`: 인용 개수
- `has_executive_summary`: 요약 포함 여부
- `has_methodology`: 방법론 포함 여부
- `has_conclusion`: 결론 포함 여부

**측정 방식**:
```python
# 단어 수 (한글 + 영문)
korean_words = len(re.findall(r'[\u3131-\u3163\uac00-\ud7a3]+', text))
english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
total_word_count = korean_words + english_words

# 섹션 개수 (마크다운 헤더)
section_count = len(re.findall(r'^#+\s+', text, re.MULTILINE))

# 차트 개수
chart_count = text.count('```mermaid')

# 인용 개수
citation_count = len(re.findall(r'\[SOURCE:\d+\]', text))
```

---

## 자동 평가 vs AI 심판 평가

### 자동 평가 (Automated Evaluation)

**특징**:
- 규칙 기반으로 즉시 측정 가능
- LLM 호출 없이 빠르게 평가
- 비용 없음

**평가 항목**:
- 작업 성공률
- 완성도 (섹션 개수, 스키마 매칭)
- 효율성 (시간, 토큰, API 호출)
- 출처 품질 (출처 타입, 개수)
- 콘텐츠 메트릭 (단어 수, 차트 수)

**장점**:
- 즉각적인 결과
- 객관적 측정
- 재현 가능

**단점**:
- 품질/정확도는 측정 불가
- 환각 현상 탐지 불가
- 의미론적 평가 불가

### AI 심판 평가 (AI Judge Evaluation)

**특징**:
- Gemini 2.5 Flash LLM 사용
- 의미론적 품질 평가
- 출처 대조를 통한 환각 탐지

**평가 항목**:
- 출력 품질 (사실 정확도, 논리성, 부합도)
- 환각 현상 (인용 정확성, 근거 없는 주장)

**장점**:
- 사람과 유사한 품질 판단
- 환각 현상 정밀 탐지
- 상세한 평가 근거 제공

**단점**:
- API 호출 비용 발생
- 평가 시간 추가 (보고서당 ~10초)
- 결과에 약간의 변동성 존재

**비용 예상**:
```
모델: gemini-2.5-flash
입력 토큰 비용: $0.075 / 1M tokens
출력 토큰 비용: $0.30 / 1M tokens

보고서당 평균:
- 입력: ~15,000 tokens (보고서 + 출처 전체 내용)
- 출력: ~500 tokens (평가 결과)
- 비용: ~$0.0015 (약 2원)

벤치마크 9개 보고서: ~$0.014 (약 18원)
```

---

## 종합 점수 계산

### 가중치 적용 공식

```python
종합 점수 = (
    작업_성공률_점수 × 0.25 +
    출력_품질_점수 × 0.25 +
    완성도_점수 × 0.20 +
    환각_역점수 × 0.15 +
    효율성_점수 × 0.10 +
    출처_품질_점수 × 0.05
)
```

### 각 항목 점수 계산

```python
작업_성공률_점수 = task_success.success_rate × 10  # 0-10
출력_품질_점수 = output_quality.overall_quality_score  # 0-10 (AI 심판)
완성도_점수 = completeness.completeness_rate × 10  # 0-10
환각_역점수 = (1 - hallucination.hallucination_rate) × 10  # 0-10 (환각 많을수록 감점)
효율성_점수 = efficiency.efficiency_score  # 0-10
출처_품질_점수 = source_quality.average_source_reliability × 10  # 0-10
```

### 등급 산정

```python
if overall_score >= 9.5:
    grade = "A+"
elif overall_score >= 9.0:
    grade = "A"
elif overall_score >= 8.5:
    grade = "B+"
elif overall_score >= 8.0:
    grade = "B"
elif overall_score >= 7.5:
    grade = "C+"
elif overall_score >= 7.0:
    grade = "C"
elif overall_score >= 6.0:
    grade = "D"
else:
    grade = "F"
```

### 예시 계산

```
작업 성공률: 100% → 10.0 × 0.25 = 2.50
출력 품질: 7.0/10 → 7.0 × 0.25 = 1.75
완성도: 83% → 8.3 × 0.20 = 1.66
환각 역점수: 0% 환각 → 10.0 × 0.15 = 1.50
효율성: 8.5/10 → 8.5 × 0.10 = 0.85
출처 품질: 0.69 → 6.9 × 0.05 = 0.35

종합 점수 = 2.50 + 1.75 + 1.66 + 1.50 + 0.85 + 0.35 = 8.61
등급 = B+
```

---

## 평가 실행 방법

### 1. 기본 벤치마크 (자동 평가만)

```bash
docker exec -e PYTHONPATH=/app multiagent-backend python /app/app/core/evaluation/report_evaluation_benchmark.py
```

**특징**:
- AI 심판 미사용
- 빠른 실행 (~5분, 보고서 9개)
- 비용 없음
- 출력 품질/환각 점수는 기본값 사용

### 2. AI 심판 포함 벤치마크

```bash
docker exec -e PYTHONPATH=/app multiagent-backend python /app/app/core/evaluation/report_evaluation_benchmark.py --ai-judge
```

**특징**:
- AI 심판 활성화
- 정밀한 품질/환각 평가
- 실행 시간 증가 (~10분, 보고서 9개)
- API 비용 발생 (~$0.014)

### 3. 쿼리 파일 사용

```bash
docker exec -e PYTHONPATH=/app multiagent-backend python /app/app/core/evaluation/report_evaluation_benchmark.py \
  --ai-judge \
  --queries-file /app/app/core/evaluation/evaluation_queries.txt
```

**쿼리 파일 형식** (`evaluation_queries.txt`):
```
[marketing]
2024년 대체육 시장 동향 및 소비자 선호도 분석 보고서를 작성해주세요
밀키트 산업의 성장 전략과 마케팅 방안 보고서를 작성해주세요

[procurement]
국내 농산물 가격 변동 추이 및 구매 최적화 전략 보고서를 작성해주세요

[기본]
식품 안전 규제 동향 및 컴플라이언스 대응 방안 보고서를 작성해주세요
```

**규칙**:
- `[team_type]`: 팀 타입 헤더 (페르소나)
- 한 줄당 하나의 쿼리
- 빈 줄로 구분

### 4. Python 스크립트에서 직접 사용

```python
from app.core.evaluation.report_evaluator import ReportEvaluator

# 평가기 초기화
evaluator = ReportEvaluator(use_ai_judge=True)

# 단일 보고서 평가
evaluation_result = evaluator.evaluate_report(
    state=state,  # StreamingAgentState
    report_text=report_text,
    query="보고서 요청 내용",
    sources=sources  # 출처 리스트
)

print(f"종합 점수: {evaluation_result.overall_score}/10")
print(f"등급: {evaluation_result.grade}")
```

---

## 평가 결과 해석

### 점수 구간별 해석

| 점수 | 등급 | 해석 |
|------|------|------|
| 9.5-10.0 | A+ | 탁월한 품질. 모든 항목에서 우수한 성과 |
| 9.0-9.4 | A | 매우 우수. 대부분의 항목에서 높은 품질 |
| 8.5-8.9 | B+ | 우수. 일부 개선 여지 있음 |
| 8.0-8.4 | B | 양호. 기본 품질 충족 |
| 7.5-7.9 | C+ | 보통. 여러 개선 필요 |
| 7.0-7.4 | C | 미흡. 주요 개선 필요 |
| 6.0-6.9 | D | 불량. 대대적 개선 필요 |
| 0-5.9 | F | 실패. 재작성 권장 |

### 주요 체크 포인트

**1. 작업 성공률 < 80%**
- 보고서 생성 실패 또는 불완전
- 시스템 오류 또는 데이터 부족 가능성
- 실행 로그 확인 필요

**2. 완성도 < 60%**
- 필수 섹션 누락
- 보고서 구조 미흡
- 요구사항 미충족

**3. 환각 현상 > 20%**
- 근거 없는 주장 다수
- 인용 부정확성 심각
- 출처 데이터 품질 검토 필요
- `evaluation_details/` 폴더에서 AI 평가 근거 확인

**4. 효율성 < 5.0**
- 실행 시간 과다 (>60초)
- API 호출 과다 (>20회)
- 토큰 사용 과다 (>20,000)
- 시스템 최적화 필요

**5. 출처 품질 < 0.5**
- 신뢰도 낮은 출처 다수
- 출처 다양성 부족
- 데이터 수집 전략 재검토

### 강점/약점/권장사항 해석

**강점 (Strengths)**:
```python
if completeness_rate > 0.9:
    strengths.append("완성도 우수 (90% 이상)")
if hallucination_rate < 0.1:
    strengths.append("환각 현상 최소화 (10% 미만)")
if efficiency_score > 8.0:
    strengths.append("효율적인 실행 (8.0/10 이상)")
```

**약점 (Weaknesses)**:
```python
if completeness_rate < 0.7:
    weaknesses.append("완성도 미흡 (70% 미만)")
if hallucination_rate > 0.2:
    weaknesses.append("환각 현상 우려 (20% 이상)")
if efficiency_score < 5.0:
    weaknesses.append("효율성 개선 필요 (5.0/10 미만)")
```

**권장사항 (Recommendations)**:
```python
if missing_sections:
    recommendations.append(f"누락 섹션 추가: {missing_sections}")
if hallucination.citation_accuracy < 0.8:
    recommendations.append("인용 정확성 검증 강화 필요")
if total_execution_time > 60:
    recommendations.append("실행 시간 최적화 (현재 {time}초)")
```

---

## 출력 파일 구조

### 생성되는 파일 및 폴더

```
evaluation_results/
└── YYYYMMDD_HHMMSS/                 # 평가 실행 시각 폴더
    ├── benchmark_results.csv         # CSV 형식 결과 (Excel 호환)
    ├── benchmark_results.xlsx        # Excel 형식 결과 (다중 시트)
    ├── benchmark_results.json        # JSON 형식 원본 데이터
    ├── benchmark_summary.md          # 마크다운 요약 보고서
    ├── evaluation_details/           # 개별 보고서 AI 평가 상세
    │   ├── report_0_quality.json     # 보고서 0 품질 평가
    │   ├── report_0_hallucination.json  # 보고서 0 환각 평가
    │   ├── report_1_quality.json
    │   └── ...
    └── charts/                       # 시각화 차트
        ├── score_distribution.png    # 점수 분포 히스토그램
        ├── grade_distribution.png    # 등급 분포 파이 차트
        ├── metrics_heatmap.png       # 메트릭 히트맵
        ├── execution_time.png        # 실행 시간 막대 그래프
        ├── hallucination_rate.png    # 환각 비율 차트
        └── efficiency_comparison.png # 효율성 비교 차트
```

### CSV 파일 구조

**benchmark_results.csv**:
```csv
team_type,query,overall_score,grade,success_rate,completeness,hallucination_rate,citation_accuracy,execution_time,total_tokens,estimated_cost
marketing,"대체육 시장 분석",8.2,B,1.0,0.83,0.0,1.0,54.29,12500,0.0015
marketing,"밀키트 전략",9.1,A,1.0,1.0,0.0,1.0,42.45,10200,0.0012
...
```

**주요 컬럼**:
- `team_type`: 팀 타입 (페르소나)
- `query`: 원본 쿼리 (축약)
- `overall_score`: 종합 점수 (0-10)
- `grade`: 등급 (A+/A/B+/B/C+/C/D/F)
- `success_rate`: 작업 성공률 (0.0-1.0)
- `completeness`: 완성도 (0.0-1.0)
- `hallucination_rate`: 환각 비율 (0.0-1.0)
- `citation_accuracy`: 인용 정확도 (0.0-1.0)
- `execution_time`: 실행 시간 (초)
- `total_tokens`: 총 토큰 수
- `estimated_cost`: 추정 비용 (USD)

### Excel 파일 구조

**benchmark_results.xlsx** (다중 시트):

**Sheet 1: Summary**
```
벤치마크 요약
- 총 평가 개수: 9
- 평균 점수: 8.27/10
- 성공률: 100%
- 평균 환각 비율: 0.0%
- 총 실행 시간: 450.2초
- 총 비용: $0.014
```

**Sheet 2: Detailed Results**
```
| Team Type | Query | Score | Grade | Success | Completeness | Hallucination | Citation Accuracy | Time |
|-----------|-------|-------|-------|---------|--------------|---------------|-------------------|------|
| marketing | ... | 8.2 | B | 100% | 83% | 0% | 100% | 54.3s |
```

**Sheet 3: Metrics Breakdown**
```
| Metric | Avg | Min | Max | Std Dev |
|--------|-----|-----|-----|---------|
| Overall Score | 8.27 | 7.5 | 9.1 | 0.52 |
| Completeness | 0.98 | 0.83 | 1.0 | 0.06 |
| Efficiency | 8.45 | 7.0 | 10.0 | 0.98 |
```

**Sheet 4: AI Judge Evaluations**
```
| Report | Quality Score | Factual Accuracy | Logical Coherence | Relevance | Hallucination Count |
|--------|---------------|------------------|-------------------|-----------|---------------------|
| 0 | 7.0/10 | 7/10 | 7/10 | 8/10 | 0 |
```

### JSON 파일 구조

**benchmark_results.json**:
```json
{
  "benchmark_id": "bench_20250110_143022",
  "benchmark_timestamp": "2025-01-10T14:30:22",
  "total_evaluations": 9,
  "evaluation_results": [
    {
      "evaluation_id": "eval_001",
      "query": "2024년 대체육 시장 동향...",
      "overall_score": 8.2,
      "grade": "B",
      "task_success": {
        "success_level": "complete_success",
        "success_rate": 1.0,
        "completion_percentage": 100.0
      },
      "output_quality": {
        "factual_accuracy_score": 7.0,
        "logical_coherence_score": 7.0,
        "relevance_score": 8.0,
        "overall_quality_score": 7.0,
        "reasoning": "보고서는 대체육 시장의 주요 동향을 잘 요약했으나..."
      },
      "hallucination": {
        "hallucination_detected": false,
        "hallucination_count": 0,
        "hallucination_rate": 0.0,
        "citation_accuracy": 1.0,
        "reasoning": "모든 [SOURCE:N] 태그가 해당 출처 내용과 정확히 일치..."
      }
    }
  ],
  "average_scores": {
    "overall_score": 8.27,
    "completeness": 0.98,
    "hallucination_rate": 0.0
  }
}
```

### Markdown 요약 보고서

**benchmark_summary.md**:
```markdown
# 보고서 평가 벤치마크 요약

**실행 시각**: 2025-01-10 14:30:22
**벤치마크 ID**: bench_20250110_143022

## 전체 통계

- 총 평가 개수: 9개
- 평균 점수: 8.27/10
- 성공률: 100%
- 평균 환각 비율: 0.0%
- 평균 실행 시간: 50.0초
- 총 비용: $0.014

## 등급 분포

| 등급 | 개수 | 비율 |
|------|------|------|
| A | 1 | 11% |
| B+ | 2 | 22% |
| B | 3 | 33% |
| C+ | 2 | 22% |
| C | 1 | 11% |

## 개별 결과

### 1. [marketing] 대체육 시장 분석
- 점수: 8.2/10 (B)
- 성공률: 100%
- 완성도: 83%
- 환각: 0%
- 실행 시간: 54.3초

**강점**:
- 환각 현상 없음
- 효율적인 실행

**약점**:
- 완성도 소폭 미흡 (83%)

**권장사항**:
- 섹션 구조 강화
```

### AI 평가 상세 파일

**evaluation_details/report_0_quality.json**:
```json
{
  "report_id": "0",
  "evaluation_type": "quality",
  "query": "2024년 대체육 시장 동향 및 소비자 선호도 분석 보고서를 작성해주세요",
  "ai_judge_model": "gemini-2.5-flash",
  "evaluation_timestamp": "2025-01-10T14:35:10",
  "result": {
    "factual_accuracy": 7.0,
    "logical_coherence": 7.0,
    "relevance": 8.0,
    "overall_quality": 7.0,
    "has_clear_structure": true,
    "has_proper_citations": true,
    "language_quality": "good",
    "reasoning": "보고서는 대체육 시장의 주요 동향을 다루고 있으며, 논리적으로 구성되어 있습니다. 다만 일부 통계 수치에 대한 출처가 명확하지 않아 사실 정확도에서 소폭 감점했습니다. 전반적으로 요구사항을 잘 충족하는 보고서입니다."
  },
  "raw_response": "AI Judge 원본 응답..."
}
```

**evaluation_details/report_0_hallucination.json**:
```json
{
  "report_id": "0",
  "evaluation_type": "hallucination",
  "query": "2024년 대체육 시장 동향...",
  "ai_judge_model": "gemini-2.5-flash",
  "sources_provided": 20,
  "evaluation_timestamp": "2025-01-10T14:35:15",
  "result": {
    "detected": false,
    "count": 0,
    "rate": 0.0,
    "examples": [],
    "unverified_claims": [],
    "contradictions": [],
    "citation_accuracy": 1.0,
    "confidence_score": 0.9,
    "reasoning": "보고서의 모든 [SOURCE:N] 태그를 검증한 결과, 각 인용이 해당 출처의 실제 내용과 정확히 일치합니다. SOURCE 1에서 인용된 '2024년 대체육 시장 규모 1조원 돌파' 내용은 SOURCE 1의 3번째 문단에 명시되어 있으며, SOURCE 5에서 인용된 'MZ세대 소비자 선호도 증가' 내용도 SOURCE 5의 제목과 본문에서 확인됩니다. 근거 없는 주장이나 과장된 표현은 발견되지 않았습니다."
  },
  "raw_response": "AI Judge 원본 응답..."
}
```

### 차트 설명

**1. score_distribution.png**
- 종합 점수 분포 히스토그램
- X축: 점수 구간 (0-10)
- Y축: 보고서 개수

**2. grade_distribution.png**
- 등급 분포 파이 차트
- 각 등급별 비율 표시

**3. metrics_heatmap.png**
- 보고서별 메트릭 히트맵
- 행: 보고서 (0-8)
- 열: 메트릭 (성공률, 완성도, 환각 비율 등)
- 색상: 값 (빨강=낮음, 초록=높음)

**4. execution_time.png**
- 보고서별 실행 시간 막대 그래프
- X축: 보고서 인덱스
- Y축: 실행 시간 (초)

**5. hallucination_rate.png**
- 보고서별 환각 비율 선 그래프
- X축: 보고서 인덱스
- Y축: 환각 비율 (0.0-1.0)

**6. efficiency_comparison.png**
- 효율성 지표 비교 (실행 시간, API 호출, 토큰)
- 여러 보고서 간 효율성 비교

---

## 평가 시스템 아키텍처

### 주요 컴포넌트

```
report_evaluation_benchmark.py
├── ReportBenchmark
│   ├── test_single_report()        # 단일 보고서 테스트
│   ├── run_benchmark()              # 전체 벤치마크 실행
│   └── save_results()               # 결과 저장
│
├── ReportEvaluator
│   ├── evaluate_report()            # 종합 평가
│   ├── _calculate_overall_score()  # 점수 계산
│   └── _analyze_results()           # 강점/약점 분석
│
├── AutomatedEvaluator
│   ├── evaluate_task_success()      # 작업 성공률
│   ├── evaluate_completeness()      # 완성도
│   ├── evaluate_efficiency()        # 효율성
│   ├── evaluate_source_quality()    # 출처 품질
│   └── extract_content_metrics()    # 콘텐츠 메트릭
│
└── AIJudgeEvaluator
    ├── evaluate_output_quality()    # 출력 품질 (AI)
    └── evaluate_hallucination()     # 환각 현상 (AI)
```

### 평가 흐름

```
1. 보고서 생성 요청
   └── API: POST /api/v1/report/stream-to-completion
   └── 응답: state (StreamingAgentState)

2. 자동 평가 수행
   ├── 작업 성공률 측정
   ├── 완성도 계산
   ├── 효율성 측정
   ├── 출처 품질 측정
   └── 콘텐츠 메트릭 추출

3. AI 심판 평가 수행 (선택)
   ├── Gemini API 호출 (품질 평가)
   │   └── 프롬프트: 보고서 + 출처 미리보기
   │   └── 응답: 사실 정확도, 논리성, 부합도
   ├── Gemini API 호출 (환각 평가)
   │   └── 프롬프트: 보고서 + 출처 전체 내용
   │   └── 응답: 환각 사례, 인용 정확도, 상세 근거
   └── AI 평가 상세 저장 (evaluation_details/)

4. 종합 점수 계산
   └── 가중 평균: 성공률(25%) + 품질(25%) + 완성도(20%) + 환각(15%) + 효율성(10%) + 출처(5%)

5. 결과 저장 및 시각화
   ├── CSV/Excel/JSON 생성
   ├── Markdown 요약 생성
   ├── 차트 6개 생성
   └── 호스트 volume에 자동 저장
```

---

## 문제 해결 (Troubleshooting)

### 문제 1: 완성도 0%

**증상**: 모든 보고서에서 completeness_rate = 0.0

**원인**:
- 하드코딩된 섹션 이름 ("요약", "분석" 등)이 실제 생성된 섹션과 불일치
- 보고서는 동적으로 섹션 제목을 생성하므로 매칭 실패

**해결**:
```python
# 기존 (섹션 이름 매칭)
required_sections = ["요약", "분석", "결론", "권장사항"]
found = [s for s in required_sections if s in report_text]

# 개선 (마크다운 헤더 개수 기반)
markdown_headers = re.findall(r'^#+\s+.+', report_text, re.MULTILINE)
total_sections = len(markdown_headers)
completeness_rate = min(1.0, total_sections / 6)  # 6개 섹션 최적
```

**결과**: 완성도 0% → 83-100%

### 문제 2: 인용 정확성 검증 안됨

**증상**: citation_accuracy가 항상 1.0 (기본값)

**원인**:
- AI Judge가 출처 내용을 일부만 봄 (200자 제한)
- 보고서 생성 LLM은 전체 내용을 보므로 불공정한 검증

**해결**:
```python
# 기존 (200자 제한)
content = source.get('content', '')[:200]

# 개선 (전체 내용)
content = source.get('content', '')  # 제한 없음
```

**효과**: 보고서 생성 LLM과 동일한 정보로 정확한 인용 검증 가능

### 문제 3: AI 심판 평가 실패

**증상**: "평가 실패 (안전 필터 차단)"

**원인**: Gemini 안전 필터가 프롬프트를 차단

**해결**:
```python
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
```

### 문제 4: 평가 결과 파일이 호스트에 보이지 않음

**증상**: Docker 컨테이너 내에서만 결과 확인 가능

**원인**: volume mount 미설정

**해결**:
```yaml
# docker-compose.yml
services:
  backend:
    volumes:
      - ./evaluation_results:/app/evaluation_results
```

```bash
docker-compose down && docker-compose up -d
```

### 문제 5: 환각 비율이 과도하게 높음

**증상**: hallucination_rate > 50%

**점검 사항**:
1. AI Judge 프롬프트가 너무 엄격한가?
2. 출처 데이터 품질이 낮은가?
3. [SOURCE:N] 태그와 실제 출처 번호가 일치하는가?
4. `evaluation_details/` 폴더에서 AI 평가 근거 확인

**디버깅**:
```python
# hallucination 상세 출력
print(f"환각 사례 개수: {len(hallucination.hallucination_examples)}")
for example in hallucination.hallucination_examples:
    print(f"문제 문장: {example['statement']}")
    print(f"이유: {example['reason']}")
```

---

## 향후 개선 방향

### 1. 인간 평가 통합
- 전문가 평가와 AI 평가 비교
- 일치도 (Inter-rater Reliability) 측정
- AI 평가 신뢰도 검증

### 2. 다국어 지원
- 영어 보고서 평가
- 언어별 메트릭 조정

### 3. 도메인별 평가 기준
- 마케팅 보고서: 창의성, 설득력 추가
- 기술 보고서: 기술 정확도, 구현 가능성 추가
- 재무 보고서: 수치 정확도, 규제 준수 추가

### 4. 실시간 평가 대시보드
- Streamlit 또는 Gradio UI
- 실시간 점수 모니터링
- 히스토리 비교

### 5. A/B 테스트 지원
- 모델 비교 (GPT-4 vs Claude vs Gemini)
- 프롬프트 전략 비교
- 파라미터 튜닝

---

## 참고 자료

### 관련 파일
- [evaluation_models.py](./evaluation_models.py) - 평가 모델 정의
- [report_evaluator.py](./report_evaluator.py) - 종합 평가기
- [automated_evaluator.py](./automated_evaluator.py) - 자동 평가기
- [ai_judge_evaluator.py](./ai_judge_evaluator.py) - AI 심판 평가기
- [report_evaluation_benchmark.py](./report_evaluation_benchmark.py) - 벤치마크 실행
- [evaluation_queries.txt](./evaluation_queries.txt) - 테스트 쿼리

### 외부 참고
- [Gemini API 문서](https://ai.google.dev/gemini-api/docs)
- [RAG 평가 Best Practices](https://arxiv.org/abs/2404.16130)
- [LLM Hallucination Detection](https://arxiv.org/abs/2311.05232)

---

**마지막 업데이트**: 2025-01-10
**버전**: 1.0.0
**작성자**: AI Evaluation System Team
