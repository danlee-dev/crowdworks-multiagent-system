# Multi-Agent RAG 시스템 평가 체계

> **작성일**: 2025-11-14
> **버전**: 2.0
> **평가 시스템**: 3-Model Ensemble AI Judge (Gemini 2.5 Flash + Claude Haiku 4.5 + GPT-4o)

---

## 목차

1. [평가 지표 정의](#1-평가-지표-정의)
2. [평가 데이터 구성](#2-평가-데이터-구성)
3. [평가 방법](#3-평가-방법)
4. [평가 결과 및 논의](#4-평가-결과-및-논의)

---

## 1. 평가 지표 정의

### 1.1 평가 지표 개요

Multi-Agent RAG 시스템이 생성한 보고서의 품질을 측정하기 위해 6개의 핵심 지표를 정의합니다.

| 지표 | 가중치 | 측정 방식 | 점수 범위 |
|------|--------|----------|-----------|
| 작업 성공률 | 25% | 자동 평가 | 0~10점 |
| 출력 품질 | 25% | AI Judge (3-Model Ensemble) | 0~10점 |
| 완성도 | 20% | 자동 평가 | 0~10점 |
| 환각 점수 | 15% | AI Judge (3-Model Ensemble) | 0~10점 (역점수) |
| 효율성 | 10% | 자동 평가 | 0~10점 |
| 출처 품질 | 5% | 자동 평가 | 0~10점 |

**종합 점수 계산식:**
```
종합 점수 = Σ(각 지표 점수 × 가중치)
```

### 1.2 작업 성공률 (Task Success Rate)

**정의**: 사용자가 요청한 작업을 얼마나 성공적으로 완수했는지 측정

**평가 요소:**
- **보고서 생성 완료 (30%)**: 정상적으로 생성되었으며 최소 길이 요구사항(100자 이상) 충족
- **필수 섹션 포함 (40%)**: 서론/개요, 본문 분석, 결론/요약, 출처 목록 포함
- **요구사항 충족 (30%)**: 쿼리에서 요청한 모든 항목을 다루고 요구된 형식 준수

**계산 방식:**
```python
completion_percentage = (충족된_요구사항_수 / 전체_요구사항_수) × 100

if completion_percentage >= 90:
    success_level = "COMPLETE_SUCCESS"
elif completion_percentage >= 50:
    success_level = "PARTIAL_SUCCESS"
else:
    success_level = "FAILURE"

score = completion_percentage / 10  # 0~10점 변환
```

### 1.3 출력 품질 (Output Quality)

**정의**: AI Judge가 평가하는 보고서의 종합적 품질

**평가 요소:**

#### 1.3.1 사실 정확도 (Factual Accuracy) - 40%
- 제시된 통계와 수치가 출처와 일치하는지
- 모든 주장에 적절한 출처가 인용되었는지
- `[SOURCE:N]` 태그가 실제 출처 N과 일치하는지

#### 1.3.2 논리적 일관성 (Logical Coherence) - 30%
- 주장과 근거가 논리적으로 연결되는지
- 섹션 간 연결이 자연스러운지
- 결론이 본문 내용에서 자연스럽게 도출되는지

#### 1.3.3 요구사항 부합도 (Relevance) - 30%
- 사용자가 요청한 주제를 정확히 다루는지
- 요청한 형식(보고서/분석/전략 등)으로 작성되었는지
- 구체적 사례와 실행 가능한 제언을 제공하는지

**계산 방식:**
```python
factual_accuracy_score = ensemble_evaluate("사실 정확도")
logical_coherence_score = ensemble_evaluate("논리적 일관성")
relevance_score = ensemble_evaluate("요구사항 부합도")

output_quality_score = (
    factual_accuracy_score × 0.40 +
    logical_coherence_score × 0.30 +
    relevance_score × 0.30
)
```

### 1.4 완성도 (Completeness)

**정의**: 보고서 구조 및 내용의 완성도

**평가 요소:**

#### 1.4.1 섹션 완성도 (60%)
- 마크다운 헤더(#, ##, ###)가 적절히 사용되었는지
- 각 섹션이 완전한 문장으로 종료되는지
- 미완성 표시(..., 문장 중간 끊김)가 없는지

**계산 방식:**
```python
total_sections_found = count_markdown_headers(report_text)

min_sections = 3      # 최소 3개 섹션
optimal_sections = 6  # 최적 6개 섹션

if total_sections_found >= optimal_sections:
    completeness_rate = 1.0
elif total_sections_found >= min_sections:
    completeness_rate = total_sections_found / optimal_sections
else:
    completeness_rate = total_sections_found / min_sections × 0.5
```

#### 1.4.2 스키마 완성도 (40%)
팀 타입별로 기대되는 섹션 구조를 정의하고 **의미론적 유사도 기반**으로 검증합니다.

**평가 방식:**
보고서의 마크다운 헤더를 추출하고, 기대 스키마 필드와의 임베딩 유사도를 계산하여 threshold(0.65) 이상이면 해당 필드가 존재한다고 판단합니다.

**구매 담당자:**
- price_analysis: 가격 분석
- supplier_info: 공급업체 정보
- risk_assessment: 리스크 평가
- recommendation: 구매 추천
- cost_benefit: 비용 편익
- conclusion: 결론

**급식 운영 담당자:**
- current_status: 현황 분석
- menu_management: 메뉴 구성
- nutrition: 영양 관리
- cost_reduction: 원가 절감
- operation_improvement: 운영 개선
- satisfaction: 만족도 향상
- conclusion: 결론

**마케팅 담당자:**
- market_analysis: 시장 분석
- target_audience: 타겟 고객
- strategy: 마케팅 전략
- implementation: 실행 방안
- metrics: 성과 지표
- conclusion: 결론

**제품 개발 연구원:**
- tech_trend: 기술 트렌드
- research_status: 연구 동향
- development_direction: 제품 개발
- application: 적용 방안
- technical_recommendation: 기술적 권장사항
- conclusion: 결론

**기본:**
- overview: 개요
- analysis: 분석
- findings: 발견사항
- recommendation: 권장사항
- conclusion: 결론

**계산 방식:**
```python
# 1. 보고서에서 마크다운 헤더 추출
markdown_headers = extract_headers(report_text)

# 2. 임베딩 모델로 헤더와 기대 필드의 유사도 계산
for expected_field in expected_schema:
    similarities = calculate_cosine_similarity(markdown_headers, expected_field)
    max_similarity = max(similarities)

    # threshold 이상이면 매칭
    if max_similarity >= 0.65:
        schema_fields_filled += 1

schema_completeness_rate = schema_fields_filled / len(expected_schema)

completeness_score = (
    completeness_rate × 0.60 +
    schema_completeness_rate × 0.40
) × 10
```

**임베딩 모델:** `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers)

**예시:**
- 기대: "시장 분석"
- 실제 헤더: "시장 현황 및 트렌드 분석" → 유사도 0.82 → 매칭 ✓
- 실제 헤더: "경쟁사 분석" → 유사도 0.54 → 매칭 ✗

### 1.5 환각 점수 (Hallucination Score)

**정의**: 출처에 없는 정보, 과장, 왜곡을 탐지하여 역점수로 환산 (환각이 적을수록 높은 점수)

**환각 유형 정의:**

| 유형 | 심각도 | 설명 |
|------|--------|------|
| 인용 부정확성 | 2 | [SOURCE:N] 태그가 실제 출처와 불일치 |
| 근거 없는 주장 | 2 | 출처에 없는 정보를 사실처럼 제시 |
| 과장 또는 왜곡 | 1 | 사실을 과장하거나 왜곡하여 표현 |

**탐지 기준:**

**인용 부정확성:**
- [SOURCE:N] 태그가 가리키는 출처 번호가 실제 출처 목록에 없음
- 인용된 내용이 해당 출처에 존재하지 않음
- 출처 내용을 왜곡하거나 과장함

**근거 없는 주장:**
- 출처에 없는 통계나 수치를 마치 확인된 것처럼 제시
- 출처에서 언급되지 않은 사건이나 사실을 주장
- 추론이나 추측을 사실로 단정

**과장 또는 왜곡:**
- 출처의 표현을 더 강하게 과장 (예: '증가' → '급증')
- 부분적 사실을 전체인 것처럼 일반화
- 맥락을 무시하고 일부만 선택적으로 인용

**계산 방식:**
```python
# 3개 모델이 각각 평가
hallucination_count = median([gemini_count, claude_count, gpt_count])
citation_accuracy = min([gemini_accuracy, claude_accuracy, gpt_accuracy])

# 환각 비율 = 1 - 인용 정확도
hallucination_rate = 1.0 - citation_accuracy

# 역점수 (환각이 적을수록 높은 점수)
hallucination_score = (1 - hallucination_rate) × 10
```

### 1.6 효율성 (Efficiency)

**정의**: 보고서 생성 시 소요된 시간과 리소스의 효율성

**평가 방식**: 기본 10점에서 패널티 차감

**패널티 항목:**

#### 1.6.1 실행 시간 패널티
| 실행 시간 | 패널티 |
|----------|--------|
| 60초 이하 | 0점 |
| 60~120초 | -1.5점 |
| 120초 이상 | -3.0점 |

#### 1.6.2 중복 단계 패널티
| 중복 단계 수 | 패널티 |
|-------------|--------|
| 0~2개 | 0점 |
| 3~5개 | -1.0점 |
| 6개 이상 | -2.0점 |

**중복 단계 탐지:**
- 동일한 검색 쿼리 반복 실행
- 동일한 로그 메시지 반복 출력

#### 1.6.3 토큰 사용량 패널티
| 토큰 사용량 | 패널티 |
|------------|--------|
| 50,000 이하 | 0점 |
| 50,000~100,000 | -1.0점 |
| 100,000 이상 | -2.0점 |

#### 1.6.4 비용 패널티
| 비용 | 패널티 |
|------|--------|
| $0.50 이하 | 0점 |
| $0.50~$1.00 | -1.0점 |
| $1.00 이상 | -2.0점 |

**비용 계산:**
```python
pricing = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},  # per 1M tokens
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "gpt-4o": {"input": 2.50, "output": 10.00}
}

input_cost = (input_tokens / 1_000_000) × pricing[model]["input"]
output_cost = (output_tokens / 1_000_000) × pricing[model]["output"]
estimated_cost = input_cost + output_cost
```

**최종 점수:**
```python
efficiency_score = 10.0 - 시간패널티 - 중복패널티 - 토큰패널티 - 비용패널티
efficiency_score = max(0.0, min(10.0, efficiency_score))
```

### 1.7 출처 품질 (Source Quality)

**정의**: 사용된 출처의 신뢰도와 다양성

**평가 요소:**

#### 1.7.1 출처 신뢰도 (50%)
각 출처는 검색 도구가 반환한 `score` 필드를 가지며, 이는 검색 결과와 쿼리의 관련성 점수입니다.

**신뢰도 등급:**
- 0.7~1.0: 높은 신뢰도
- 0.5~0.7: 중간 신뢰도
- 0.0~0.5: 낮은 신뢰도

**계산:**
```python
average_source_reliability = sum(source_scores) / len(sources)
credibility_score = average_source_reliability × 10
```

#### 1.7.2 출처 다양성 (50%)
사용된 검색 도구와 출처 유형의 다양성을 측정합니다.

**다양성 등급:**
- 5개 이상: 높은 다양성
- 3~4개: 중간 다양성
- 1~2개: 낮은 다양성

**계산:**
```python
source_diversity = len(unique_source_types)
max_diversity = 8  # 시스템에서 사용 가능한 최대 출처 유형 수
diversity_score = min(source_diversity / max_diversity, 1.0) × 10
```

**종합 점수:**
```python
source_quality_score = (credibility_score × 0.50) + (diversity_score × 0.50)
```

### 1.8 등급 체계

| 등급 | 점수 범위 | 설명 |
|------|----------|------|
| A+ | 9.5~10.0 | 탁월함 |
| A | 9.0~9.4 | 우수함 |
| B+ | 8.5~8.9 | 양호함 |
| B | 8.0~8.4 | 보통 |
| C+ | 7.5~7.9 | 미흡 |
| C | 7.0~7.4 | 부족 |
| D | 6.0~6.9 | 불량 |
| F | 0.0~5.9 | 실패 |

---

## 2. 평가 데이터 구성

### 2.1 벤치마크 데이터셋

평가에 사용되는 쿼리는 5개 팀 타입별로 구성됩니다. (총 15개 쿼리)

#### 2.1.1 구매 담당자 쿼리
**특징**: 가격 비교, 구매 결정, 공급업체 분석

**벤치마크 쿼리:**
1. "국내 농산물 가격 변동 추이 및 구매 최적화 전략 보고서를 작성해주세요"
2. "글로벌 식자재 공급망 리스크 관리 방안 보고서를 작성해주세요"
3. "친환경 유기농 식재료 소싱 가이드 보고서를 작성해주세요"

**기대 요구사항:**
- 가격 분석
- 공급업체 정보
- 리스크 평가
- 구매 추천
- 비용 편익 분석
- 결론

#### 2.1.2 급식 운영 담당자 쿼리
**특징**: 급식 메뉴, 식자재 관리, 운영 효율화

**벤치마크 쿼리:**
1. "사내 급식 메뉴 다양화 및 영양 균형 개선 방안 보고서를 작성해주세요"
2. "계절별 식자재 원가 절감 및 대체 식재료 활용 전략 보고서를 작성해주세요"
3. "직원 만족도 향상을 위한 급식 운영 개선 방안 보고서를 작성해주세요"

**기대 요구사항:**
- 현황 분석
- 메뉴 구성 및 영양 관리
- 원가 절감 방안
- 운영 개선 전략
- 만족도 향상 방안
- 결론

#### 2.1.3 마케팅 담당자 쿼리
**특징**: 시장 분석, 마케팅 전략, 성장 방안

**벤치마크 쿼리:**
1. "2024년 대체육 시장 동향 및 소비자 선호도 분석 보고서를 작성해주세요"
2. "밀키트 산업의 성장 전략과 마케팅 방안 보고서를 작성해주세요"
3. "MZ세대 타겟 건강기능식품 시장 진입 전략 보고서를 작성해주세요"

**기대 요구사항:**
- 시장 현황 분석
- 타겟 고객 정의
- 마케팅 전략
- 실행 방안
- 성과 측정 지표
- 결론

#### 2.1.4 제품 개발 연구원 쿼리
**특징**: 기술 동향, 제품 개발, 연구 분석

**벤치마크 쿼리:**
1. "기능성 식품 원료 트렌드 및 신소재 연구 동향 보고서를 작성해주세요"
2. "식물성 단백질 기반 대체육 제품 개발 기술 분석 보고서를 작성해주세요"
3. "프로바이오틱스 효능 연구 및 제품 적용 방안 보고서를 작성해주세요"

**기대 요구사항:**
- 기술 트렌드 분석
- 연구 동향 조사
- 제품 개발 방향
- 적용 방안
- 기술적 권장사항
- 결론

#### 2.1.5 기본 쿼리
**특징**: 일반적인 정보 요청, 분석, 조사

**벤치마크 쿼리:**
1. "식품 안전 규제 동향 및 컴플라이언스 대응 방안 보고서를 작성해주세요"
2. "푸드테크 산업의 AI 활용 사례 분석 보고서를 작성해주세요"
3. "탄소중립을 위한 식품 산업의 ESG 경영 전략 보고서를 작성해주세요"

**기대 요구사항:**
- 주제에 대한 개요
- 데이터 기반 분석
- 발견사항 및 인사이트
- 권장사항
- 결론

### 2.2 평가 데이터 수집

**수집 항목:**

#### 2.2.1 입력 데이터
- 원본 쿼리 (query)
- 팀 타입 (team_type)
- 기대 요구사항 목록 (expected_requirements)

#### 2.2.2 출력 데이터
- 생성된 보고서 전문 (final_answer)
- 실행 로그 (execution_log)
- 단계별 결과 (step_results)
- 사용된 출처 목록 (sources)

#### 2.2.3 메타데이터
- 총 실행 시간 (total_execution_time)
- 총 토큰 사용량 (total_tokens)
  - 입력 토큰 (input_tokens)
  - 출력 토큰 (output_tokens)
- API 호출 횟수 (total_api_calls)
- 예상 비용 (estimated_cost)
- 사용 모델 (model_name)

---

## 3. 평가 방법

### 3.1 3-Model Ensemble AI Judge

#### 3.1.1 모델 구성

AI 심판 평가는 3개의 최신 LLM을 앙상블하여 수행합니다.

**중요**: 3개 모델은 **동일한 평가 기준**으로 독립적으로 평가하며, 역할 분담이 없습니다. 모두 사실 정확도, 논리적 일관성, 요구사항 부합도, 환각 탐지를 동일하게 수행합니다.

| 모델 | 버전 | 가중치 | API Key |
|------|------|--------|---------|
| Gemini | gemini-2.5-flash | 34% | `GEMINI_API_KEY_1` |
| Claude | claude-haiku-4-5-20251001 | 33% | `EVALUATION_CLAUDE_API_KEY` |
| GPT | gpt-4o | 33% | `EVALUATION_OPENAI_API_KEY` |

**공통 설정:**
```json
{
  "temperature": 0.2,
  "max_tokens": 4096
}
```

#### 3.1.2 앙상블 사용 이유

1. **편향 제거**: 단일 모델의 편향성 최소화
2. **신뢰성 향상**: 3개 모델의 합의로 더 신뢰할 수 있는 평가
3. **불일치 탐지**: 모델 간 점수 차이가 3점 이상일 경우 중앙값 사용하여 이상값 제거
4. **다양성 확보**: 서로 다른 모델이 동일 기준으로 평가하여 객관성 극대화

### 3.2 평가 프롬프트

#### 3.2.1 사실 정확도 프롬프트

```
다음 보고서의 사실 정확도를 0~10점으로 평가하세요.

평가 기준:
1. 데이터 정확성: 제시된 통계와 수치가 출처와 일치하는가?
2. 사실 검증: 모든 주장에 적절한 출처가 인용되었는가?
3. 인용 정확성: [SOURCE:N] 태그가 실제 출처와 일치하는가?

각 [SOURCE:N] 태그를 실제 출처 내용과 비교하여 검증하세요.

보고서:
{report}

출처 목록:
{sources}

평가 결과를 다음 JSON 형식으로 반환하세요:
{
  "score": 0-10,
  "reasoning": "상세한 평가 근거",
  "issues": ["발견된 문제점들"]
}
```

#### 3.2.2 논리적 일관성 프롬프트

```
다음 보고서의 논리적 일관성을 0~10점으로 평가하세요.

평가 기준:
1. 논증 구조: 주장과 근거가 논리적으로 연결되는가?
2. 흐름과 전환: 섹션 간 연결이 자연스러운가?
3. 결론 타당성: 결론이 본문에서 자연스럽게 도출되는가?

보고서:
{report}

평가 결과를 다음 JSON 형식으로 반환하세요:
{
  "score": 0-10,
  "reasoning": "상세한 평가 근거",
  "strengths": ["강점들"],
  "weaknesses": ["약점들"]
}
```

#### 3.2.3 요구사항 부합도 프롬프트

```
다음 보고서가 원본 쿼리의 요구사항을 얼마나 잘 충족하는지 0~10점으로 평가하세요.

원본 쿼리:
{query}

보고서:
{report}

평가 기준:
1. 쿼리 의도 파악: 사용자가 요청한 주제를 정확히 다루는가?
2. 형식 준수: 요청한 형식(보고서/분석/전략 등)으로 작성되었는가?
3. 구체성: 구체적 사례와 실행 가능한 제언을 제공하는가?

평가 결과를 다음 JSON 형식으로 반환하세요:
{
  "score": 0-10,
  "reasoning": "상세한 평가 근거",
  "fulfilled_requirements": ["충족된 요구사항들"],
  "missing_requirements": ["누락된 요구사항들"]
}
```

#### 3.2.4 환각 탐지 프롬프트

```
다음 보고서에서 환각(출처에 없는 정보, 과장, 왜곡)을 탐지하세요.

보고서:
{report}

전체 출처 내용:
{sources}

환각 유형:
1. 인용 부정확성: [SOURCE:N] 태그가 실제 출처와 불일치
2. 근거 없는 주장: 출처에 없는 정보를 사실처럼 제시
3. 과장/왜곡: 사실을 과장하거나 왜곡하여 표현

각 [SOURCE:N]을 실제 출처와 비교하여 검증하세요.

평가 결과를 다음 JSON 형식으로 반환하세요:
{
  "hallucination_count": 0,
  "hallucinations": [
    {
      "type": "citation_inaccuracy | unfounded_claims | exaggeration",
      "location": "보고서 내 위치",
      "description": "환각 내용",
      "severity": 1-2
    }
  ],
  "citation_accuracy": 0.0-1.0
}
```

### 3.3 앙상블 집계 방법

#### 3.3.1 기본 집계: 가중 평균

3개 모델의 점수를 가중치에 따라 평균합니다.

```python
weights = {
    "gemini": 0.34,
    "claude": 0.33,
    "gpt": 0.33
}

ensemble_score = (
    gemini_score × 0.34 +
    claude_score × 0.33 +
    gpt_score × 0.33
)
```

#### 3.3.2 불일치 처리: 중앙값

모델 간 점수 차이가 3점 이상일 경우, 가중 평균 대신 중앙값을 사용합니다.

```python
raw_scores = [gemini_score, claude_score, gpt_score]
score_range = max(raw_scores) - min(raw_scores)

if score_range >= 3.0:
    ensemble_score = median(raw_scores)
    disagreement = True
else:
    ensemble_score = weighted_average(raw_scores, weights)
    disagreement = False
```

#### 3.3.3 환각 평가 특수 집계

**환각 건수: 중앙값**
```python
hallucination_counts = [gemini_count, claude_count, gpt_count]
ensemble_count = median(hallucination_counts)
```

**인용 정확도: 최소값**
```python
citation_accuracies = [gemini_accuracy, claude_accuracy, gpt_accuracy]
ensemble_citation_accuracy = min(citation_accuracies)
```

**환각 비율: 1 - 인용 정확도**
```python
hallucination_rate = 1.0 - ensemble_citation_accuracy
hallucination_score = (1 - hallucination_rate) × 10
```

**환각 사례 병합**
```python
all_hallucinations = []
all_unverified_claims = []
all_contradictions = []

for model in [gemini, claude, gpt]:
    all_hallucinations.extend(model.hallucinations)
    all_unverified_claims.extend(model.unverified_claims)
    all_contradictions.extend(model.contradictions)

# 중복 제거 및 최대 10개로 제한
```

### 3.4 자동 평가 방법

#### 3.4.1 작업 성공률 자동 평가

```python
# 요구사항 검증
missing_requirements = []
for req in expected_requirements:
    if req.lower() not in final_answer.lower():
        missing_requirements.append(req)

# 완성도 계산
completion_percentage = (
    (len(expected_requirements) - len(missing_requirements))
    / len(expected_requirements) × 100
)

success_rate = completion_percentage / 100
```

#### 3.4.2 완성도 자동 평가

```python
# 섹션 완성도
markdown_headers = re.findall(r'^#+\s+.+$', report_text, re.MULTILINE)
total_sections = len(markdown_headers)

# 스키마 완성도
for field_key, field_name_kr in expected_schema.items():
    # 정확한 매칭
    if field_name_kr in report_text:
        schema_fields_filled += 1
        continue

    # 유사 표현 매칭
    for synonym in synonym_map.get(field_name_kr, []):
        if synonym in report_text or synonym.lower() in report_text.lower():
            schema_fields_filled += 1
            break

schema_completeness_rate = schema_fields_filled / len(expected_schema)
```

#### 3.4.3 효율성 자동 평가

```python
efficiency_score = 10.0

# 실행 시간 패널티
if total_execution_time > 120:
    efficiency_score -= 3.0
elif total_execution_time > 60:
    efficiency_score -= 1.5

# 중복 단계 패널티
if redundant_steps > 5:
    efficiency_score -= 2.0
elif redundant_steps > 2:
    efficiency_score -= 1.0

# 토큰 사용량 패널티
if total_tokens > 100000:
    efficiency_score -= 2.0
elif total_tokens > 50000:
    efficiency_score -= 1.0

# 비용 패널티
if estimated_cost > 1.0:
    efficiency_score -= 2.0
elif estimated_cost > 0.5:
    efficiency_score -= 1.0

efficiency_score = max(0.0, min(10.0, efficiency_score))
```

#### 3.4.4 출처 품질 자동 평가

```python
# 신뢰도 계산
reliability_scores = [source.get('score', 0.5) for source in sources]
average_source_reliability = sum(reliability_scores) / len(reliability_scores)

# 다양성 계산
source_types = set(source.get('source', 'unknown') for source in sources)
source_diversity = len(source_types)

# 종합 점수
credibility_score = average_source_reliability × 10
diversity_score = min(source_diversity / 8, 1.0) × 10
source_quality_score = (credibility_score × 0.50) + (diversity_score × 0.50)
```

### 3.5 종합 점수 계산

```python
overall_score = (
    task_success_score × 0.25 +
    output_quality_score × 0.25 +
    completeness_score × 0.20 +
    hallucination_score × 0.15 +
    efficiency_score × 0.10 +
    source_quality_score × 0.05
)

grade = calculate_grade(overall_score)
```

---

## 4. 평가 결과 및 논의

### 4.1 평가 결과 출력 형식

#### 4.1.1 개별 지표 점수
각 평가 지표별 점수와 세부 메트릭을 출력합니다.

**작업 성공률:**
- 성공 수준 (COMPLETE_SUCCESS / PARTIAL_SUCCESS / FAILURE)
- 성공률 (%)
- 누락된 요구사항 목록

**출력 품질:**
- 사실 정확도 점수
- 논리적 일관성 점수
- 요구사항 부합도 점수
- 종합 품질 점수

**완성도:**
- 섹션 완성도 (%)
- 스키마 완성도 (%)
- 누락된 섹션 목록

**환각 점수:**
- 환각 건수
- 환각 비율 (%)
- 환각 사례 목록
- 인용 정확도

**효율성:**
- 총 실행 시간 (초)
- 총 토큰 사용량
- API 호출 횟수
- 예상 비용 ($)
- 중복 단계 수

**출처 품질:**
- 총 출처 수
- 평균 신뢰도
- 출처 다양성 (유형 수)
- 출처 유형 목록

#### 4.1.2 종합 평가
- 종합 점수 (0~10)
- 등급 (A+~F)
- 강점 (최대 5개)
- 약점 (최대 5개)
- 개선 권장사항 (최대 5개)

### 4.2 결과 분석

#### 4.2.1 강점 분석
자동 평가와 AI Judge 평가를 종합하여 보고서의 강점을 도출합니다.

**자동 평가 기반:**
- 작업 성공률 >= 90% → "작업을 성공적으로 완료했습니다"
- 완성도 >= 90% → "보고서가 완성도 높게 작성되었습니다"
- 환각 건수 = 0 → "환각 현상이 감지되지 않았습니다"
- 출처 다양성 >= 3 → "다양한 출처를 활용했습니다"
- 효율성 >= 8.0 → "효율적으로 작업을 수행했습니다"

**AI Judge 기반:**
- AI Judge가 평가한 강점 목록 (최대 3개)

#### 4.2.2 약점 분석

**자동 평가 기반:**
- 작업 성공률 < 70% → "작업 완료율이 낮습니다"
- 누락된 섹션 존재 → "필수 섹션 누락: [섹션 목록]"
- 출력 품질 < 6.0 → "보고서 품질이 기대에 미치지 못합니다"
- 환각 건수 > 0 → "환각 현상 감지: N건"
- 출처 신뢰도 < 0.6 → "출처 신뢰도가 낮습니다"
- 중복 단계 > 3 → "불필요한 중복 단계: N개"

**AI Judge 기반:**
- AI Judge가 평가한 약점 목록 (최대 3개)

#### 4.2.3 개선 권장사항

**자동 평가 기반:**
- 누락된 섹션 존재 → "누락된 섹션을 추가하세요"
- 검증되지 않은 주장 존재 → "검증되지 않은 주장에 출처를 추가하세요"
- 출처 수 < 5 → "더 많은 출처를 활용하세요"
- 효율성 < 7.0 → "워크플로우 최적화를 고려하세요"
- 인용 수 = 0 → "출처 인용을 추가하세요"
- 결론 없음 → "결론 섹션을 추가하세요"

**AI Judge 기반:**
- AI Judge가 제안한 개선사항 목록 (최대 3개)

### 4.3 평가 결과 해석

#### 4.3.1 점수 해석 가이드

**9.0 이상 (A 등급 이상)**
- 매우 높은 품질의 보고서
- 대부분의 요구사항을 충족하며 사실 정확도와 논리성이 우수
- 환각 현상이 거의 없거나 매우 적음
- 현재 수준 유지 및 미세 조정 권장

**8.0~8.9 (B 등급)**
- 높은 품질의 보고서
- 기본 요구사항을 충족하며 일부 개선 가능한 부분 존재
- 출력 품질 개선, 환각 감소, 효율성 향상 권장

**7.0~7.9 (C 등급)**
- 수용 가능한 품질이나 개선 필요
- 기본은 충족하나 완성도나 품질 향상 필요
- 완성도 강화, 요구사항 재확인, 출처 보강 권장

**6.9 이하 (D, F 등급)**
- 품질이 낮거나 사용 불가능
- 전면적인 재검토 및 수정 필요
- 요구사항 재확인, 기본 구조 작성, 사실 확인 필수

#### 4.3.2 지표별 해석

**작업 성공률이 낮은 경우:**
- 쿼리 의도를 정확히 파악하지 못함
- 필수 요구사항을 누락
- 요청한 형식을 준수하지 않음

**출력 품질이 낮은 경우:**
- 사실 정확도: 출처와 일치하지 않는 정보 포함
- 논리적 일관성: 논리 비약, 모순된 내용 존재
- 요구사항 부합도: 쿼리와 무관한 내용 포함

**완성도가 낮은 경우:**
- 필수 섹션 누락 (서론, 결론 등)
- 문장 미완성 또는 구조적 결함
- 팀 타입에 맞지 않는 스키마

**환각 점수가 낮은 경우:**
- 출처 없는 통계나 수치 제시
- 인용 부정확 또는 출처 왜곡
- 추측을 사실로 단정

**효율성이 낮은 경우:**
- 실행 시간 과다 (2분 이상)
- 불필요한 중복 검색 실행
- 토큰 사용량 과다 또는 비용 초과

**출처 품질이 낮은 경우:**
- 쿼리와 관련성 낮은 출처 사용
- 출처 유형의 다양성 부족
- 단일 데이터베이스에만 의존

### 4.4 평가 시스템의 한계 및 개선 방향

#### 4.4.1 현재 한계점

**자동 평가의 한계:**
- 문자열 매칭 기반으로 의미론적 유사성을 완벽히 포착하지 못함
- 유사 표현 매핑이 사전 정의된 목록에 의존
- 맥락을 고려하지 않은 기계적 평가

**AI Judge의 한계:**
- 모델별 편향이 완전히 제거되지 않을 수 있음
- 프롬프트 설계에 따라 평가 결과가 달라질 수 있음
- 긴 보고서의 경우 일부 내용을 놓칠 가능성

**환각 탐지의 한계:**
- 미묘한 왜곡이나 과장을 탐지하기 어려움
- 출처에 있는 내용이지만 맥락이 다른 경우 탐지 어려움
- 암묵적 환각 (독자가 잘못 해석할 수 있는 모호한 표현) 탐지 불가

#### 4.4.2 개선 방향

**자동 평가 개선:**
- 의미론적 유사도 기반 매칭 도입 (임베딩 벡터 사용)
- 동적 유사 표현 학습 (평가 결과 피드백 활용)
- 맥락을 고려한 평가 알고리즘 개발

**AI Judge 개선:**
- 더 많은 모델 추가 (5-Model Ensemble)
- 프롬프트 자동 최적화 시스템 도입
- Chain-of-Thought 방식의 평가 프로세스 적용

**환각 탐지 개선:**
- 출처와 보고서의 의미론적 유사도 비교
- 문맥 기반 환각 탐지 모델 개발
- 인간 평가자의 피드백을 통한 모델 개선

**종합 시스템 개선:**
- 실시간 평가 피드백 시스템 구축
- 평가 결과 기반 자동 보고서 개선 제안
- 평가 지표 가중치 동적 조정 (도메인별, 쿼리 유형별)

---

## 부록

### A. 코드 위치

| 컴포넌트 | 파일 경로 |
|----------|----------|
| 평가 기준 정의 | `backend/app/core/evaluation/evaluation_criteria.json` |
| 자동 평가기 | `backend/app/core/evaluation/automated_evaluator.py` |
| 3-Model Ensemble AI Judge | `backend/app/core/evaluation/ensemble_ai_judge.py` |
| 평가 오케스트레이터 | `backend/app/core/evaluation/report_evaluator.py` |
| 평가 모델 정의 | `backend/app/core/evaluation/evaluation_models.py` |
| 벤치마크 실행 | `backend/app/run_evaluation.py` |

### B. 환경 변수

| 변수명 | 설명 | 필수 여부 |
|--------|------|-----------|
| `GEMINI_API_KEY_1` | Gemini API 키 | 필수 |
| `EVALUATION_CLAUDE_API_KEY` | Claude API 키 (평가 전용) | 필수 |
| `EVALUATION_OPENAI_API_KEY` | OpenAI API 키 (평가 전용) | 필수 |

### C. 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|-----------|
| 2025-11-14 | 2.0 | • 3-Model Ensemble 도입<br>• 환각 비율 계산 개선<br>• 유사 표현 매칭 추가<br>• 평가 문서 재구성 |
| 2025-11-09 | 1.5 | • Gemini 2.5 Flash 적용<br>• 평가 기준 JSON 분리 |
| 2025-11-08 | 1.0 | • 초기 평가 시스템 구축 |

---

**문서 작성**: Claude Code
**최종 검토**: 2025-11-14
**문의**: 평가 시스템 관련 질문은 이슈로 등록해주세요.


