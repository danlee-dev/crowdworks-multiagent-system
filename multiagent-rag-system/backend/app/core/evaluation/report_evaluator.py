"""
보고서 평가 오케스트레이터
Report Evaluator Orchestrator

자동 평가와 AI 심판 평가를 통합하여 종합 평가를 수행합니다.
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.evaluation.evaluation_models import (
    EvaluationResult,
    TaskSuccessMetrics,
    OutputQualityMetrics,
    CompletenessMetrics,
    HallucinationMetrics,
    EfficiencyMetrics,
    SourceQualityMetrics,
    ContentMetrics,
)
from app.core.evaluation.automated_evaluator import AutomatedEvaluator
from app.core.evaluation.ai_judge_evaluator import AIJudgeEvaluator
from app.core.evaluation.ensemble_ai_judge import EnsembleAIJudge


class ReportEvaluator:
    """종합 보고서 평가기"""

    def __init__(
        self,
        use_ai_judge: bool = True,
        ai_model: str = "gemini-2.5-flash",
        use_ensemble: bool = True
    ):
        """
        초기화

        Args:
            use_ai_judge: AI 심판 사용 여부
            ai_model: AI 심판에 사용할 모델 (단일 모델 사용 시)
            use_ensemble: 3-Model Ensemble 사용 여부 (True 권장)
        """
        self.automated_evaluator = AutomatedEvaluator()

        # Ensemble AI Judge 또는 단일 모델 선택
        if use_ai_judge:
            if use_ensemble:
                print("✅ 3-Model Ensemble AI Judge 초기화 (Gemini + Claude + GPT-4o)")
                self.ai_judge_evaluator = EnsembleAIJudge()
            else:
                print(f"✅ 단일 모델 AI Judge 초기화 ({ai_model})")
                self.ai_judge_evaluator = AIJudgeEvaluator(model=ai_model)
        else:
            self.ai_judge_evaluator = None

        self.use_ai_judge = use_ai_judge
        self.use_ensemble = use_ensemble

    def evaluate_report(
        self,
        query: str,
        state: Dict[str, Any],
        report_text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expected_requirements: Optional[List[str]] = None,
        expected_sections: Optional[List[str]] = None,
        expected_word_count: Optional[int] = None,
        team_type: str = "general",
        model_name: str = "gemini-2.5-flash"
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
        # 보고서 텍스트 추출
        if report_text is None:
            report_text = state.get('final_answer', '')

        if not report_text:
            raise ValueError("보고서 텍스트가 비어있습니다.")

        # 메타데이터 추출
        if metadata is None:
            metadata = state.get('metadata', {})

        # 평가 ID 생성
        evaluation_id = str(uuid.uuid4())
        report_id = state.get('conversation_id', str(uuid.uuid4()))

        # 1. 자동 평가 수행
        print("\n=== 자동 평가 수행 중... ===")

        # 1.1 작업 성공률
        task_success = self.automated_evaluator.evaluate_task_success(
            state=state,
            expected_requirements=expected_requirements
        )
        print(f"✓ 작업 성공률: {task_success.success_rate:.2%}")

        # 1.2 완성도
        completeness = self.automated_evaluator.evaluate_completeness(
            report_text=report_text,
            required_sections=expected_sections,
            expected_schema=None,
            team_type=team_type
        )
        print(f"✓ 완성도: {completeness.completeness_rate:.2%} (스키마: {completeness.schema_completeness_rate:.2%})")

        # 1.3 효율성
        efficiency = self.automated_evaluator.evaluate_efficiency(
            state=state,
            metadata=metadata,
            model_name=model_name
        )
        print(f"✓ 효율성 점수: {efficiency.efficiency_score:.1f}/10")
        if efficiency.total_tokens_used > 0:
            print(f"  - 토큰: {efficiency.total_tokens_used:,}, API 호출: {efficiency.total_api_calls}, 비용: ${efficiency.estimated_cost:.4f}")

        # 1.4 출처 품질
        source_quality = self.automated_evaluator.evaluate_source_quality(
            state=state,
            report_text=report_text
        )
        print(f"✓ 출처 품질: {source_quality.total_sources}개 출처, "
              f"평균 신뢰도 {source_quality.average_source_reliability:.2f}")

        # 1.5 콘텐츠 메트릭
        content_metrics = self.automated_evaluator.evaluate_content_metrics(
            report_text=report_text,
            expected_word_count=expected_word_count
        )
        print(f"✓ 콘텐츠: {content_metrics.total_word_count}단어, "
              f"{content_metrics.section_count}섹션")

        # 2. AI 심판 평가 수행
        output_quality = None
        hallucination = None
        ai_judge_evaluation = None

        if self.use_ai_judge and self.ai_judge_evaluator:
            print("\n=== AI 심판 평가 수행 중... ===")

            try:
                # 출처 정보 추출
                sources = state.get('step_results', [])

                # 2.1 출력 품질 평가
                output_quality = self.ai_judge_evaluator.evaluate_output_quality(
                    query=query,
                    report_text=report_text,
                    sources=sources
                )
                print(f"✓ AI 품질 평가: {output_quality.overall_quality_score:.1f}/10")

                # 2.2 환각 현상 평가
                hallucination = self.ai_judge_evaluator.evaluate_hallucination(
                    query=query,
                    report_text=report_text,
                    sources=sources
                )
                print(f"✓ 환각 현상 감지: {hallucination.hallucination_count}건 "
                      f"(비율: {hallucination.hallucination_rate:.2%})")

                # 2.3 종합 평가
                ai_judge_evaluation = self.ai_judge_evaluator.evaluate_comprehensive(
                    query=query,
                    report_text=report_text,
                    sources=sources,
                    expected_requirements=expected_requirements
                )
                print(f"✓ AI 종합 평가 완료")

            except Exception as e:
                print(f"⚠ AI 심판 평가 실패: {str(e)}")
                # AI 평가 실패 시 기본값 사용
                output_quality = OutputQualityMetrics(
                    factual_accuracy_score=7.0,
                    logical_coherence_score=7.0,
                    relevance_score=7.0,
                    overall_quality_score=7.0,
                    has_clear_structure=True,
                    has_proper_citations=True,
                    language_quality="good",
                    reasoning="AI 평가 실패, 기본값 사용"
                )
                hallucination = HallucinationMetrics(
                    hallucination_detected=False,
                    hallucination_count=0,
                    hallucination_rate=0.0,
                    hallucination_examples=[],
                    unverified_claims=[],
                    contradictions=[],
                    confidence_score=0.5,
                    reasoning="AI 평가 실패"
                )
        else:
            # AI 심판 미사용 시 기본값
            output_quality = OutputQualityMetrics(
                factual_accuracy_score=7.0,
                logical_coherence_score=7.0,
                relevance_score=7.0,
                overall_quality_score=7.0,
                has_clear_structure=True,
                has_proper_citations=True,
                language_quality="good",
                reasoning="AI 심판 미사용"
            )
            hallucination = HallucinationMetrics(
                hallucination_detected=False,
                hallucination_count=0,
                hallucination_rate=0.0,
                hallucination_examples=[],
                unverified_claims=[],
                contradictions=[],
                confidence_score=0.5,
                reasoning="AI 심판 미사용"
            )

        # 3. 종합 점수 계산
        overall_score = self._calculate_overall_score(
            task_success=task_success,
            output_quality=output_quality,
            completeness=completeness,
            hallucination=hallucination,
            efficiency=efficiency,
            source_quality=source_quality
        )

        # 등급 계산
        grade = self._calculate_grade(overall_score)

        # 4. 강점/약점/권장사항 추출
        strengths, weaknesses, recommendations = self._analyze_results(
            task_success=task_success,
            output_quality=output_quality,
            completeness=completeness,
            hallucination=hallucination,
            efficiency=efficiency,
            source_quality=source_quality,
            content_metrics=content_metrics,
            ai_judge_evaluation=ai_judge_evaluation
        )

        print(f"\n=== 평가 완료 ===")
        print(f"종합 점수: {overall_score:.1f}/10 (등급: {grade})")

        # 5. 평가 결과 생성
        evaluation_result = EvaluationResult(
            evaluation_id=evaluation_id,
            report_id=report_id,
            evaluation_timestamp=datetime.now().isoformat(),
            query=query,
            team_type=state.get('metadata', {}).get('team_type'),
            report_type=state.get('metadata', {}).get('report_type'),
            task_success=task_success,
            output_quality=output_quality,
            completeness=completeness,
            hallucination=hallucination,
            efficiency=efficiency,
            source_quality=source_quality,
            content_metrics=content_metrics,
            overall_score=overall_score,
            grade=grade,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations,
            ai_judge_evaluation=ai_judge_evaluation,
            raw_state=state,
            raw_report=report_text
        )

        return evaluation_result

    def _calculate_overall_score(
        self,
        task_success: TaskSuccessMetrics,
        output_quality: OutputQualityMetrics,
        completeness: CompletenessMetrics,
        hallucination: HallucinationMetrics,
        efficiency: EfficiencyMetrics,
        source_quality: SourceQualityMetrics
    ) -> float:
        """
        종합 점수 계산

        가중치:
        - 작업 성공률: 25%
        - 출력 품질: 25%
        - 완성도: 20%
        - 환각 현상 (역): 15%
        - 효율성: 10%
        - 출처 품질: 5%
        """
        # 각 항목을 0-10 스케일로 정규화
        task_score = task_success.success_rate * 10
        quality_score = output_quality.overall_quality_score
        completeness_score = completeness.completeness_rate * 10
        hallucination_score = (1 - hallucination.hallucination_rate) * 10
        efficiency_score = efficiency.efficiency_score
        source_score = source_quality.average_source_reliability * 10

        # 가중 평균
        overall_score = (
            task_score * 0.25 +
            quality_score * 0.25 +
            completeness_score * 0.20 +
            hallucination_score * 0.15 +
            efficiency_score * 0.10 +
            source_score * 0.05
        )

        return round(overall_score, 2)

    def _calculate_grade(self, score: float) -> str:
        """점수를 등급으로 변환"""
        if score >= 9.5:
            return "A+"
        elif score >= 9.0:
            return "A"
        elif score >= 8.5:
            return "B+"
        elif score >= 8.0:
            return "B"
        elif score >= 7.5:
            return "C+"
        elif score >= 7.0:
            return "C"
        elif score >= 6.0:
            return "D"
        else:
            return "F"

    def _analyze_results(
        self,
        task_success: TaskSuccessMetrics,
        output_quality: OutputQualityMetrics,
        completeness: CompletenessMetrics,
        hallucination: HallucinationMetrics,
        efficiency: EfficiencyMetrics,
        source_quality: SourceQualityMetrics,
        content_metrics: ContentMetrics,
        ai_judge_evaluation: Optional[Dict[str, Any]]
    ) -> tuple[List[str], List[str], List[str]]:
        """강점, 약점, 권장사항 분석"""

        strengths = []
        weaknesses = []
        recommendations = []

        # AI 심판 평가 결과 우선 사용
        if ai_judge_evaluation:
            strengths.extend(ai_judge_evaluation.get('strengths', [])[:3])
            weaknesses.extend(ai_judge_evaluation.get('weaknesses', [])[:3])
            recommendations.extend(ai_judge_evaluation.get('recommendations', [])[:3])

        # 자동 평가 기반 분석 추가
        # 강점
        if task_success.success_rate >= 0.9:
            strengths.append("작업을 성공적으로 완료했습니다")
        if completeness.completeness_rate >= 0.9:
            strengths.append("보고서가 완성도 높게 작성되었습니다")
        if output_quality.overall_quality_score >= 8.0:
            strengths.append("높은 품질의 보고서입니다")
        if hallucination.hallucination_count == 0:
            strengths.append("환각 현상이 감지되지 않았습니다")
        if source_quality.source_diversity >= 3:
            strengths.append("다양한 출처를 활용했습니다")
        if efficiency.efficiency_score >= 8.0:
            strengths.append("효율적으로 작업을 수행했습니다")

        # 약점
        if task_success.success_rate < 0.7:
            weaknesses.append("작업 완료율이 낮습니다")
        if completeness.missing_sections:
            weaknesses.append(f"필수 섹션 누락: {', '.join(completeness.missing_sections[:3])}")
        if output_quality.overall_quality_score < 6.0:
            weaknesses.append("보고서 품질이 기대에 미치지 못합니다")
        if hallucination.hallucination_count > 0:
            weaknesses.append(f"환각 현상 감지: {hallucination.hallucination_count}건")
        if source_quality.average_source_reliability < 0.6:
            weaknesses.append("출처 신뢰도가 낮습니다")
        if efficiency.redundant_steps > 3:
            weaknesses.append(f"불필요한 중복 단계: {efficiency.redundant_steps}개")

        # 권장사항
        if completeness.missing_sections:
            recommendations.append("누락된 섹션을 추가하세요")
        if hallucination.unverified_claims:
            recommendations.append("검증되지 않은 주장에 출처를 추가하세요")
        if source_quality.total_sources < 5:
            recommendations.append("더 많은 출처를 활용하세요")
        if efficiency.efficiency_score < 7.0:
            recommendations.append("워크플로우 최적화를 고려하세요")
        if content_metrics.citation_count == 0:
            recommendations.append("출처 인용을 추가하세요")
        if not content_metrics.has_conclusion:
            recommendations.append("결론 섹션을 추가하세요")

        # 중복 제거
        strengths = list(dict.fromkeys(strengths))
        weaknesses = list(dict.fromkeys(weaknesses))
        recommendations = list(dict.fromkeys(recommendations))

        return strengths[:5], weaknesses[:5], recommendations[:5]


__all__ = ["ReportEvaluator"]
