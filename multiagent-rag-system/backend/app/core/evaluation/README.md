# 보고서 평가 시스템

생성된 보고서의 품질을 종합적으로 평가하는 시스템입니다.

## 📋 목차

- [개요](#개요)
- [핵심 성과지표 (KPI)](#핵심-성과지표-kpi)
- [시스템 구성](#시스템-구성)
- [설치 및 사용법](#설치-및-사용법)
- [평가 메트릭 상세](#평가-메트릭-상세)
- [API 레퍼런스](#api-레퍼런스)
- [예시](#예시)

## 개요

이 평가 시스템은 멀티 에이전트 시스템이 생성한 보고서를 다음과 같이 평가합니다:

1. **자동 평가**: 정량적 메트릭 자동 계산
2. **AI 심판 평가**: LLM을 활용한 정성적 평가
3. **종합 평가**: 자동 + AI 평가 통합

## 핵심 성과지표 (KPI)

### 1. 효과성 지표 (Effectiveness)

#### (1) 작업 성공률 (Task Success Rate)
- 에이전트가 부여된 리서치 작업을 완전히 올바르게 완료한 비율
- 측정: `success_rate` (0.0 ~ 1.0)
- 기준:
  - **완전 성공**: 90% 이상
  - **부분 성공**: 50% ~ 90%
  - **실패**: 50% 미만

#### (2) 출력 품질 및 정확도 (Output Quality and Accuracy)
- **사실 정확도** (`factual_accuracy_score`): 생성된 내용의 사실 일치 정도
- **논리적 일관성** (`logical_coherence_score`): 논리적 흐름과 일관성
- **요구사항 부합도** (`relevance_score`): 사용자 의도 부합 정도
- 측정: 0~10 점수 (AI 심판 평가)

#### (3) 완성도 (Completeness)
- 요청된 정보나 보고서 스키마의 모든 필드가 누락 없이 채워졌는지 평가
- 측정: `completeness_rate` (0.0 ~ 1.0)
- 검증 항목:
  - 필수 섹션 포함 여부
  - 스키마 필드 완성도
  - 불완전한 섹션 감지

#### (4) 환각 현상 비율 (Hallucination Rate)
- 부정확하거나 존재하지 않는 정보를 사실처럼 생성하는 빈도
- 측정: `hallucination_rate` (0.0 ~ 1.0)
- 감지 방법:
  - 출처와 불일치하는 내용
  - 검증 불가능한 주장
  - 내부 모순
  - AI 심판을 통한 환각 탐지

### 2. 효율성 지표 (Efficiency)

#### 응답 시간 / 지연 시간
- **총 실행 시간** (`total_execution_time`): 전체 작업 소요 시간
- **평균 단계 시간** (`average_step_time`): 단계별 평균 시간
- **첫 응답 시간** (`time_to_first_response`): 첫 응답까지 시간

#### 리소스 사용량
- **토큰 사용량** (`total_tokens_used`): LLM API 호출 토큰 수
- **API 호출 횟수** (`total_api_calls`): 총 API 호출 수
- **추정 비용** (`estimated_cost`): 예상 실행 비용 (USD)

#### 단계 수 (Step Count)
- **총 단계 수** (`total_steps`): 실행된 총 단계
- **중복 단계** (`redundant_steps`): 불필요한 반복 단계
- **효율성 점수** (`efficiency_score`): 종합 효율성 (0~10)

### 3. 품질 지표 (Quality)

#### 출처 품질
- **총 출처 수** (`total_sources`)
- **신뢰 출처 수** (`reliable_sources`): 신뢰도 ≥ 0.7
- **출처 다양성** (`source_diversity`): 고유 출처 타입 수
- **평균 출처 신뢰도** (`average_source_reliability`)
- **인용 정확도** (`citation_accuracy`): 출처 인용 비율

#### 콘텐츠 메트릭
- 단어 수, 문자 수
- 섹션 수, 차트 수, 테이블 수
- 인용 수
- 구조적 요소 (요약, 방법론, 결론) 포함 여부

## 시스템 구성

### 파일 구조

```
app/core/evaluation/
├── __init__.py                  # 패키지 초기화
├── evaluation_models.py         # 평가 모델 정의 (Pydantic)
├── automated_evaluator.py       # 자동 평가기
├── ai_judge_evaluator.py        # AI 심판 평가기
├── report_evaluator.py          # 종합 평가 오케스트레이터
├── evaluate_report_cli.py       # CLI 도구
├── example_usage.py             # 사용 예시
└── README.md                    # 이 문서
```

### 주요 클래스

1. **`AutomatedEvaluator`**: 자동으로 측정 가능한 메트릭 계산
2. **`AIJudgeEvaluator`**: LLM을 사용한 정성적 평가
3. **`ReportEvaluator`**: 전체 평가 프로세스 관리

## 설치 및 사용법

### 환경 설정

```bash
# OpenAI API 키 설정 (AI 심판 사용 시 필수)
export OPENAI_API_KEY="your-api-key"
```

### CLI 사용법

#### 1. 상태 파일로 평가

```bash
python -m app.core.evaluation.evaluate_report_cli \
  --state state.json \
  --output evaluation_result.json
```

#### 2. 보고서 파일로 평가

```bash
python -m app.core.evaluation.evaluate_report_cli \
  --query "2024년 AI 시장 동향 분석" \
  --report report.md \
  --output evaluation_result.json
```

#### 3. AI 심판 없이 빠른 평가

```bash
python -m app.core.evaluation.evaluate_report_cli \
  --state state.json \
  --no-ai-judge
```

#### 4. 커스텀 요구사항 지정

```bash
python -m app.core.evaluation.evaluate_report_cli \
  --state state.json \
  --expected-requirements "시장 규모" "트렌드" "예측" \
  --expected-sections "요약" "분석" "결론" \
  --expected-word-count 1500
```

### Python API 사용법

```python
from app.core.evaluation import ReportEvaluator

# 평가기 생성
evaluator = ReportEvaluator(
    use_ai_judge=True,  # AI 심판 사용
    ai_model="gpt-4o-mini"  # 사용할 모델
)

# 보고서 평가
result = evaluator.evaluate_report(
    query="원본 질문",
    state=streaming_agent_state,
    expected_requirements=["요구사항1", "요구사항2"],
    expected_sections=["섹션1", "섹션2"],
    expected_word_count=1000
)

# 결과 확인
print(f"종합 점수: {result.overall_score}/10")
print(f"등급: {result.grade}")
print(f"성공률: {result.task_success.success_rate:.2%}")
print(f"환각 현상: {result.hallucination.hallucination_count}건")

# 강점/약점/권장사항
for strength in result.strengths:
    print(f"✓ {strength}")

for weakness in result.weaknesses:
    print(f"✗ {weakness}")

for rec in result.recommendations:
    print(f"→ {rec}")
```

## 평가 메트릭 상세

### 종합 점수 계산 (Overall Score)

종합 점수는 다음 가중치로 계산됩니다:

```
Overall Score =
  작업 성공률 × 25% +
  출력 품질 × 25% +
  완성도 × 20% +
  환각 방지 × 15% +
  효율성 × 10% +
  출처 품질 × 5%
```

### 등급 (Grade)

| 점수 범위 | 등급 |
|---------|------|
| 9.5~10.0 | A+ |
| 9.0~9.5 | A |
| 8.5~9.0 | B+ |
| 8.0~8.5 | B |
| 7.5~8.0 | C+ |
| 7.0~7.5 | C |
| 6.0~7.0 | D |
| < 6.0 | F |

### 자동 평가 vs AI 심판 평가

| 평가 항목 | 자동 평가 | AI 심판 |
|---------|----------|---------|
| 작업 성공률 | ✓ | |
| 완성도 | ✓ | |
| 효율성 | ✓ | |
| 출처 품질 | ✓ | |
| 콘텐츠 메트릭 | ✓ | |
| 출력 품질 | | ✓ |
| 환각 현상 | | ✓ |
| 정성적 분석 | | ✓ |

**권장 사항**:
- 빠른 평가가 필요할 때: 자동 평가만 사용 (`use_ai_judge=False`)
- 정확한 평가가 필요할 때: AI 심판 포함 (`use_ai_judge=True`)

## API 레퍼런스

### `ReportEvaluator`

```python
class ReportEvaluator:
    def __init__(
        self,
        use_ai_judge: bool = True,
        ai_model: str = "gpt-4o-mini"
    ):
        """
        Args:
            use_ai_judge: AI 심판 사용 여부
            ai_model: AI 심판에 사용할 모델
        """

    def evaluate_report(
        self,
        query: str,
        state: Dict[str, Any],
        report_text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expected_requirements: Optional[List[str]] = None,
        expected_sections: Optional[List[str]] = None,
        expected_word_count: Optional[int] = None,
    ) -> EvaluationResult:
        """
        보고서 종합 평가

        Args:
            query: 원본 질문/요청
            state: StreamingAgentState
            report_text: 생성된 보고서 (없으면 state에서 추출)
            metadata: 메타데이터 (실행 시간, 토큰 사용량 등)
            expected_requirements: 기대 요구사항
            expected_sections: 필수 섹션
            expected_word_count: 기대 단어 수

        Returns:
            EvaluationResult: 종합 평가 결과
        """
```

### `EvaluationResult`

```python
class EvaluationResult(BaseModel):
    evaluation_id: str
    report_id: str
    evaluation_timestamp: str

    # 메타데이터
    query: str
    team_type: Optional[str]
    report_type: Optional[str]

    # 핵심 성과지표
    task_success: TaskSuccessMetrics
    output_quality: OutputQualityMetrics
    completeness: CompletenessMetrics
    hallucination: HallucinationMetrics

    # 효율성 지표
    efficiency: EfficiencyMetrics

    # 추가 메트릭
    source_quality: SourceQualityMetrics
    content_metrics: ContentMetrics

    # 종합 점수
    overall_score: float  # 0~10
    grade: str  # A+/A/B+/B/C+/C/D/F

    # 상세 분석
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]

    # AI 심판 평가
    ai_judge_evaluation: Optional[Dict[str, Any]]
```

## 예시

### 예시 1: 기본 사용

```python
from app.core.evaluation import ReportEvaluator

# 평가기 생성
evaluator = ReportEvaluator(use_ai_judge=True)

# 상태 데이터 준비
state = {
    'original_query': '2024 AI 시장 동향',
    'final_answer': '# 보고서 내용...',
    'step_results': [...],
    'execution_log': [...],
}

# 평가 실행
result = evaluator.evaluate_report(
    query=state['original_query'],
    state=state
)

# 결과 출력
print(f"점수: {result.overall_score}/10")
```

### 예시 2: 배치 평가

```python
from app.core.evaluation import ReportEvaluator

evaluator = ReportEvaluator(use_ai_judge=False)  # 빠른 평가

reports = [state1, state2, state3]
results = []

for state in reports:
    result = evaluator.evaluate_report(
        query=state['original_query'],
        state=state
    )
    results.append(result)

# 통계
avg_score = sum(r.overall_score for r in results) / len(results)
print(f"평균 점수: {avg_score:.2f}")
```

### 예시 3: 결과 저장

```python
import json
from app.core.evaluation import ReportEvaluator

evaluator = ReportEvaluator()
result = evaluator.evaluate_report(query="...", state=state)

# JSON으로 저장
with open('evaluation.json', 'w') as f:
    json.dump(result.model_dump(), f, indent=2)
```

## 벤치마크

### 성능 벤치마크

| 평가 모드 | 평균 실행 시간 | 비용 |
|----------|--------------|------|
| 자동 평가만 | ~1초 | 무료 |
| AI 심판 포함 (gpt-4o-mini) | ~5-10초 | ~$0.01 |
| AI 심판 포함 (gpt-4o) | ~10-20초 | ~$0.05 |

### 정확도 벤치마크

인간 평가와의 일치도:
- 자동 평가: ~70%
- AI 심판 포함: ~85%

## 확장 및 커스터마이징

### 커스텀 메트릭 추가

```python
from app.core.evaluation.automated_evaluator import AutomatedEvaluator

class CustomEvaluator(AutomatedEvaluator):
    def evaluate_custom_metric(self, report_text: str) -> float:
        # 커스텀 로직
        score = custom_calculation(report_text)
        return score
```

### 커스텀 AI 프롬프트

```python
from app.core.evaluation.ai_judge_evaluator import AIJudgeEvaluator

class CustomAIJudge(AIJudgeEvaluator):
    def _build_quality_evaluation_prompt(self, query, report_text, sources):
        # 커스텀 프롬프트
        return f"Custom prompt: {query} {report_text}"
```

## 문제 해결

### Q: AI 심판 평가가 실패합니다
A: `OPENAI_API_KEY` 환경변수가 설정되었는지 확인하세요.

### Q: 평가가 너무 느립니다
A: `use_ai_judge=False`로 설정하여 자동 평가만 사용하세요.

### Q: 환각 현상이 감지되지 않습니다
A: AI 심판 평가를 활성화하고, 더 강력한 모델(gpt-4o)을 사용하세요.

## 라이선스 및 기여

이 프로젝트는 Crowdworks 멀티 에이전트 시스템의 일부입니다.

## 참고 자료

- [BLEU Score](https://en.wikipedia.org/wiki/BLEU)
- [Mind2Web Benchmark](https://arxiv.org/abs/2306.06070)
- [LLM as a Judge](https://arxiv.org/abs/2306.05685)

---

**Last Updated**: 2024-01-15
