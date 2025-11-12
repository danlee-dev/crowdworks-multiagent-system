"""
보고서 평가 모델 정의
Report Evaluation Models

핵심 성과지표(KPI) 기반 평가 시스템
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional, Literal
from datetime import datetime
from enum import Enum


class EvaluationCategory(str, Enum):
    """평가 카테고리"""
    EFFECTIVENESS = "effectiveness"  # 효과성 지표
    EFFICIENCY = "efficiency"  # 효율성 지표
    QUALITY = "quality"  # 품질 지표


class TaskSuccessLevel(str, Enum):
    """작업 성공 수준"""
    COMPLETE_SUCCESS = "complete_success"  # 완전 성공
    PARTIAL_SUCCESS = "partial_success"  # 부분 성공
    FAILURE = "failure"  # 실패


class TaskSuccessMetrics(BaseModel):
    """작업 성공률 평가 메트릭"""
    success_level: TaskSuccessLevel = Field(description="작업 성공 수준")
    success_rate: float = Field(ge=0.0, le=1.0, description="성공률 (0.0 ~ 1.0)")
    completion_percentage: float = Field(ge=0.0, le=100.0, description="완성도 퍼센트")
    is_task_completed: bool = Field(description="작업 완료 여부")
    missing_requirements: List[str] = Field(default_factory=list, description="누락된 요구사항")
    reasoning: str = Field(default="", description="평가 근거")


class OutputQualityMetrics(BaseModel):
    """출력 품질 및 정확도 평가 메트릭"""
    factual_accuracy_score: float = Field(ge=0.0, le=10.0, description="사실 정확도 점수 (0~10)")
    logical_coherence_score: float = Field(ge=0.0, le=10.0, description="논리적 일관성 점수 (0~10)")
    relevance_score: float = Field(ge=0.0, le=10.0, description="요구사항 부합도 점수 (0~10)")
    overall_quality_score: float = Field(ge=0.0, le=10.0, description="전체 품질 점수 (0~10)")

    # 세부 평가 항목
    has_clear_structure: bool = Field(description="명확한 구조 보유")
    has_proper_citations: bool = Field(description="적절한 인용 포함")
    language_quality: str = Field(default="good", description="언어 품질 (poor/fair/good/excellent)")
    reasoning: str = Field(default="", description="평가 근거")


class CompletenessMetrics(BaseModel):
    """완성도 평가 메트릭"""
    required_sections_completed: int = Field(ge=0, description="완료된 필수 섹션 수")
    total_required_sections: int = Field(ge=0, description="총 필수 섹션 수")
    completeness_rate: float = Field(ge=0.0, le=1.0, description="완성도 비율")

    missing_sections: List[str] = Field(default_factory=list, description="누락된 섹션")
    incomplete_sections: List[str] = Field(default_factory=list, description="불완전한 섹션")

    # 스키마 요구사항 검증
    schema_fields_filled: int = Field(ge=0, description="채워진 스키마 필드 수")
    total_schema_fields: int = Field(ge=0, description="총 스키마 필드 수")
    schema_completeness_rate: float = Field(ge=0.0, le=1.0, description="스키마 완성도")

    reasoning: str = Field(default="", description="평가 근거")


class HallucinationMetrics(BaseModel):
    """환각 현상 평가 메트릭"""
    hallucination_detected: bool = Field(description="환각 현상 감지 여부")
    hallucination_count: int = Field(ge=0, description="감지된 환각 현상 개수")
    hallucination_rate: float = Field(ge=0.0, le=1.0, description="환각 현상 비율")

    hallucination_examples: List[Dict[str, str]] = Field(
        default_factory=list,
        description="환각 현상 사례 (statement, reason)"
    )

    # 신뢰도 검증
    unverified_claims: List[str] = Field(default_factory=list, description="검증되지 않은 주장")
    contradictions: List[str] = Field(default_factory=list, description="모순되는 내용")

    # 인용 정확성
    citation_accuracy: float = Field(default=1.0, ge=0.0, le=1.0, description="인용 정확도 (출처 내용과 일치율)")

    confidence_score: float = Field(ge=0.0, le=1.0, description="내용 신뢰도 점수")
    reasoning: str = Field(default="", description="평가 근거 (인용 검증 과정 포함)")


class EfficiencyMetrics(BaseModel):
    """효율성 평가 메트릭"""
    # 응답 시간 / 지연 시간
    total_execution_time: float = Field(ge=0.0, description="총 실행 시간 (초)")
    average_step_time: float = Field(ge=0.0, description="평균 단계별 시간 (초)")
    time_to_first_response: Optional[float] = Field(default=None, description="첫 응답까지 시간 (초)")

    # 리소스 사용량
    total_tokens_used: int = Field(ge=0, description="총 사용 토큰 수")
    total_api_calls: int = Field(ge=0, description="총 API 호출 횟수")
    estimated_cost: float = Field(ge=0.0, description="추정 비용 (USD)")

    # 단계 수
    total_steps: int = Field(ge=0, description="총 단계 수")
    redundant_steps: int = Field(ge=0, description="중복/불필요한 단계 수")
    efficiency_score: float = Field(ge=0.0, le=10.0, description="효율성 점수 (0~10)")

    # 세부 분석
    step_breakdown: Dict[str, float] = Field(default_factory=dict, description="단계별 시간 분석")
    tool_usage_stats: Dict[str, int] = Field(default_factory=dict, description="도구 사용 통계")

    reasoning: str = Field(default="", description="평가 근거")


class SourceQualityMetrics(BaseModel):
    """출처 품질 평가 메트릭"""
    total_sources: int = Field(ge=0, description="총 출처 개수")
    reliable_sources: int = Field(ge=0, description="신뢰할 수 있는 출처 개수")
    source_diversity: int = Field(ge=0, description="출처 다양성 (고유 출처 타입 수)")

    average_source_reliability: float = Field(ge=0.0, le=1.0, description="평균 출처 신뢰도")
    citation_accuracy: float = Field(ge=0.0, le=1.0, description="인용 정확도")

    source_types: List[str] = Field(default_factory=list, description="사용된 출처 타입")
    unreliable_sources: List[str] = Field(default_factory=list, description="신뢰도 낮은 출처")


class ContentMetrics(BaseModel):
    """콘텐츠 메트릭"""
    total_word_count: int = Field(ge=0, description="총 단어 수")
    total_char_count: int = Field(ge=0, description="총 문자 수")

    expected_word_count: Optional[int] = Field(default=None, description="기대 단어 수")
    word_count_deviation: Optional[float] = Field(default=None, description="단어 수 편차 (%)")

    section_count: int = Field(ge=0, description="섹션 개수")
    chart_count: int = Field(ge=0, description="차트 개수")
    table_count: int = Field(ge=0, description="테이블 개수")
    citation_count: int = Field(ge=0, description="인용 개수")

    has_executive_summary: bool = Field(default=False, description="요약 포함 여부")
    has_methodology: bool = Field(default=False, description="방법론 포함 여부")
    has_conclusion: bool = Field(default=False, description="결론 포함 여부")


class EvaluationResult(BaseModel):
    """종합 평가 결과"""
    evaluation_id: str = Field(description="평가 ID")
    report_id: str = Field(description="보고서 ID")
    evaluation_timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="평가 시각"
    )

    # 메타데이터
    query: str = Field(description="원본 쿼리")
    team_type: Optional[str] = Field(default=None, description="팀 타입")
    report_type: Optional[str] = Field(default=None, description="보고서 타입")

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
    overall_score: float = Field(ge=0.0, le=10.0, description="종합 점수 (0~10)")
    grade: str = Field(description="등급 (A+/A/B+/B/C+/C/D/F)")

    # 상세 분석
    strengths: List[str] = Field(default_factory=list, description="강점")
    weaknesses: List[str] = Field(default_factory=list, description="약점")
    recommendations: List[str] = Field(default_factory=list, description="개선 권장사항")

    # AI 심판 평가 (선택)
    ai_judge_evaluation: Optional[Dict[str, Any]] = Field(default=None, description="AI 심판 평가")

    # 원본 데이터
    raw_state: Optional[Dict[str, Any]] = Field(default=None, description="원본 상태 데이터")
    raw_report: Optional[str] = Field(default=None, description="원본 보고서")


class BenchmarkResult(BaseModel):
    """벤치마크 결과 - 여러 평가 결과 비교"""
    benchmark_id: str = Field(description="벤치마크 ID")
    benchmark_name: str = Field(description="벤치마크 이름")
    benchmark_timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="벤치마크 실행 시각"
    )

    total_evaluations: int = Field(ge=0, description="총 평가 개수")
    evaluation_results: List[EvaluationResult] = Field(
        default_factory=list,
        description="개별 평가 결과들"
    )

    # 집계 통계
    average_scores: Dict[str, float] = Field(default_factory=dict, description="평균 점수")
    score_distribution: Dict[str, int] = Field(default_factory=dict, description="점수 분포")

    success_rate: float = Field(ge=0.0, le=1.0, description="전체 성공률")
    average_hallucination_rate: float = Field(ge=0.0, le=1.0, description="평균 환각 현상 비율")
    average_execution_time: float = Field(ge=0.0, description="평균 실행 시간")
    total_cost: float = Field(ge=0.0, description="총 비용")

    # 비교 분석
    best_performing_config: Optional[Dict[str, Any]] = Field(default=None, description="최고 성능 설정")
    worst_performing_config: Optional[Dict[str, Any]] = Field(default=None, description="최저 성능 설정")

    summary: str = Field(default="", description="벤치마크 요약")


class HumanEvaluation(BaseModel):
    """전문가/인간 평가"""
    evaluator_id: str = Field(description="평가자 ID")
    evaluator_expertise: str = Field(description="평가자 전문성 (e.g., 마케팅 전문가, 개발자)")
    evaluation_id: str = Field(description="평가 ID (EvaluationResult와 연결)")

    # 인간 평가 점수
    human_quality_score: float = Field(ge=0.0, le=10.0, description="인간 평가 품질 점수")
    human_accuracy_score: float = Field(ge=0.0, le=10.0, description="인간 평가 정확도 점수")
    human_usefulness_score: float = Field(ge=0.0, le=10.0, description="인간 평가 유용성 점수")

    # 정성 평가
    qualitative_feedback: str = Field(description="정성적 피드백")
    identified_errors: List[str] = Field(default_factory=list, description="발견된 오류")
    suggested_improvements: List[str] = Field(default_factory=list, description="개선 제안")

    # AI 평가와의 일치도
    agreement_with_ai: float = Field(ge=0.0, le=1.0, description="AI 평가와의 일치도")

    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="평가 시각"
    )


__all__ = [
    "EvaluationCategory",
    "TaskSuccessLevel",
    "TaskSuccessMetrics",
    "OutputQualityMetrics",
    "CompletenessMetrics",
    "HallucinationMetrics",
    "EfficiencyMetrics",
    "SourceQualityMetrics",
    "ContentMetrics",
    "EvaluationResult",
    "BenchmarkResult",
    "HumanEvaluation",
]
