"""
보고서 평가 CLI 도구
Report Evaluation CLI Tool

생성된 보고서를 평가하는 명령줄 도구
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.evaluation.report_evaluator import ReportEvaluator
from app.core.evaluation.evaluation_models import EvaluationResult


def load_state_from_file(file_path: str) -> Dict[str, Any]:
    """파일에서 상태 로드"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_evaluation_result(result: EvaluationResult, output_path: str):
    """평가 결과 저장"""
    result_dict = result.model_dump()

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=2)

    print(f"\n평가 결과가 저장되었습니다: {output_path}")


def print_evaluation_summary(result: EvaluationResult):
    """평가 결과 요약 출력"""
    print("\n" + "=" * 80)
    print("보고서 평가 결과")
    print("=" * 80)

    print(f"\n평가 ID: {result.evaluation_id}")
    print(f"보고서 ID: {result.report_id}")
    print(f"평가 시각: {result.evaluation_timestamp}")
    print(f"원본 쿼리: {result.query[:100]}...")

    print(f"\n{'─' * 80}")
    print("📊 종합 점수")
    print(f"{'─' * 80}")
    print(f"  종합 점수: {result.overall_score:.2f}/10.0")
    print(f"  등급: {result.grade}")

    print(f"\n{'─' * 80}")
    print("✅ 작업 성공률")
    print(f"{'─' * 80}")
    print(f"  성공 수준: {result.task_success.success_level.value}")
    print(f"  성공률: {result.task_success.success_rate:.2%}")
    print(f"  완성도: {result.task_success.completion_percentage:.1f}%")
    if result.task_success.missing_requirements:
        print(f"  누락 요구사항: {', '.join(result.task_success.missing_requirements[:3])}")

    print(f"\n{'─' * 80}")
    print("📝 출력 품질")
    print(f"{'─' * 80}")
    print(f"  사실 정확도: {result.output_quality.factual_accuracy_score:.1f}/10")
    print(f"  논리적 일관성: {result.output_quality.logical_coherence_score:.1f}/10")
    print(f"  요구사항 부합도: {result.output_quality.relevance_score:.1f}/10")
    print(f"  전체 품질: {result.output_quality.overall_quality_score:.1f}/10")
    print(f"  언어 품질: {result.output_quality.language_quality}")

    print(f"\n{'─' * 80}")
    print("📋 완성도")
    print(f"{'─' * 80}")
    print(f"  섹션 완성률: {result.completeness.completeness_rate:.2%} "
          f"({result.completeness.required_sections_completed}/{result.completeness.total_required_sections})")
    if result.completeness.missing_sections:
        print(f"  누락 섹션: {', '.join(result.completeness.missing_sections[:3])}")
    if result.completeness.incomplete_sections:
        print(f"  불완전 섹션: {', '.join(result.completeness.incomplete_sections[:3])}")

    print(f"\n{'─' * 80}")
    print("🔍 환각 현상")
    print(f"{'─' * 80}")
    print(f"  환각 감지: {'예' if result.hallucination.hallucination_detected else '아니오'}")
    print(f"  환각 건수: {result.hallucination.hallucination_count}건")
    print(f"  환각 비율: {result.hallucination.hallucination_rate:.2%}")
    print(f"  신뢰도 점수: {result.hallucination.confidence_score:.2f}")
    if result.hallucination.hallucination_examples:
        print(f"  주요 사례:")
        for i, example in enumerate(result.hallucination.hallucination_examples[:3], 1):
            print(f"    {i}. {example.get('statement', '')[:50]}...")

    print(f"\n{'─' * 80}")
    print("⚡ 효율성")
    print(f"{'─' * 80}")
    print(f"  총 실행 시간: {result.efficiency.total_execution_time:.2f}초")
    print(f"  평균 단계 시간: {result.efficiency.average_step_time:.2f}초")
    print(f"  총 단계 수: {result.efficiency.total_steps}개")
    print(f"  중복 단계: {result.efficiency.redundant_steps}개")
    print(f"  총 토큰 사용: {result.efficiency.total_tokens_used:,}개")
    print(f"  추정 비용: ${result.efficiency.estimated_cost:.4f}")
    print(f"  효율성 점수: {result.efficiency.efficiency_score:.1f}/10")

    print(f"\n{'─' * 80}")
    print("📚 출처 품질")
    print(f"{'─' * 80}")
    print(f"  총 출처: {result.source_quality.total_sources}개")
    print(f"  신뢰 출처: {result.source_quality.reliable_sources}개")
    print(f"  출처 다양성: {result.source_quality.source_diversity}개 타입")
    print(f"  평균 신뢰도: {result.source_quality.average_source_reliability:.2f}")
    print(f"  인용 정확도: {result.source_quality.citation_accuracy:.2%}")
    if result.source_quality.source_types:
        print(f"  출처 타입: {', '.join(result.source_quality.source_types)}")

    print(f"\n{'─' * 80}")
    print("📄 콘텐츠 메트릭")
    print(f"{'─' * 80}")
    print(f"  총 단어 수: {result.content_metrics.total_word_count:,}단어")
    print(f"  총 문자 수: {result.content_metrics.total_char_count:,}자")
    print(f"  섹션 수: {result.content_metrics.section_count}개")
    print(f"  차트 수: {result.content_metrics.chart_count}개")
    print(f"  테이블 수: {result.content_metrics.table_count}개")
    print(f"  인용 수: {result.content_metrics.citation_count}개")
    print(f"  요약 포함: {'예' if result.content_metrics.has_executive_summary else '아니오'}")
    print(f"  방법론 포함: {'예' if result.content_metrics.has_methodology else '아니오'}")
    print(f"  결론 포함: {'예' if result.content_metrics.has_conclusion else '아니오'}")

    print(f"\n{'─' * 80}")
    print("💪 강점")
    print(f"{'─' * 80}")
    if result.strengths:
        for i, strength in enumerate(result.strengths, 1):
            print(f"  {i}. {strength}")
    else:
        print("  (없음)")

    print(f"\n{'─' * 80}")
    print("⚠️  약점")
    print(f"{'─' * 80}")
    if result.weaknesses:
        for i, weakness in enumerate(result.weaknesses, 1):
            print(f"  {i}. {weakness}")
    else:
        print("  (없음)")

    print(f"\n{'─' * 80}")
    print("💡 개선 권장사항")
    print(f"{'─' * 80}")
    if result.recommendations:
        for i, rec in enumerate(result.recommendations, 1):
            print(f"  {i}. {rec}")
    else:
        print("  (없음)")

    print("\n" + "=" * 80)


def main():
    """CLI 메인 함수"""
    parser = argparse.ArgumentParser(
        description="생성된 보고서를 평가합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 상태 파일로부터 평가
  python -m app.core.evaluation.evaluate_report_cli --state state.json

  # 보고서 텍스트 직접 제공
  python -m app.core.evaluation.evaluate_report_cli --query "질문" --report report.md

  # AI 심판 없이 평가 (빠름)
  python -m app.core.evaluation.evaluate_report_cli --state state.json --no-ai-judge

  # 평가 결과 저장
  python -m app.core.evaluation.evaluate_report_cli --state state.json --output evaluation.json
        """
    )

    # 입력 옵션
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--state',
        type=str,
        help='StreamingAgentState JSON 파일 경로'
    )
    input_group.add_argument(
        '--report',
        type=str,
        help='보고서 텍스트 파일 경로 (--query와 함께 사용)'
    )

    parser.add_argument(
        '--query',
        type=str,
        help='원본 질문/요청 (--report 사용 시 필수)'
    )

    # 평가 옵션
    parser.add_argument(
        '--no-ai-judge',
        action='store_true',
        help='AI 심판 평가 비활성화 (빠른 평가)'
    )

    parser.add_argument(
        '--ai-model',
        type=str,
        default='gpt-4o-mini',
        help='AI 심판에 사용할 모델 (기본: gpt-4o-mini)'
    )

    # 기대값 옵션
    parser.add_argument(
        '--expected-requirements',
        type=str,
        nargs='+',
        help='기대 요구사항 리스트'
    )

    parser.add_argument(
        '--expected-sections',
        type=str,
        nargs='+',
        help='필수 섹션 리스트'
    )

    parser.add_argument(
        '--expected-word-count',
        type=int,
        help='기대 단어 수'
    )

    # 출력 옵션
    parser.add_argument(
        '--output',
        type=str,
        help='평가 결과 저장 경로 (JSON)'
    )

    parser.add_argument(
        '--summary-only',
        action='store_true',
        help='요약만 출력'
    )

    args = parser.parse_args()

    # 입력 데이터 준비
    state = None
    query = None
    report_text = None

    if args.state:
        # 상태 파일에서 로드
        print(f"상태 파일 로딩 중: {args.state}")
        state = load_state_from_file(args.state)
        query = state.get('original_query', '')
        report_text = state.get('final_answer', '')

    elif args.report:
        # 보고서 파일에서 로드
        if not args.query:
            parser.error("--report 사용 시 --query가 필요합니다")

        print(f"보고서 파일 로딩 중: {args.report}")
        with open(args.report, 'r', encoding='utf-8') as f:
            report_text = f.read()

        query = args.query
        # 최소 상태 생성
        state = {
            'original_query': query,
            'final_answer': report_text,
            'step_results': [],
            'execution_log': [],
            'metadata': {}
        }

    # 평가기 초기화
    print(f"\n평가기 초기화 중...")
    print(f"  AI 심판: {'비활성화' if args.no_ai_judge else '활성화'}")
    if not args.no_ai_judge:
        print(f"  AI 모델: {args.ai_model}")

    evaluator = ReportEvaluator(
        use_ai_judge=not args.no_ai_judge,
        ai_model=args.ai_model
    )

    # 평가 실행
    print(f"\n평가 시작...")
    try:
        result = evaluator.evaluate_report(
            query=query,
            state=state,
            report_text=report_text,
            expected_requirements=args.expected_requirements,
            expected_sections=args.expected_sections,
            expected_word_count=args.expected_word_count
        )

        # 결과 출력
        print_evaluation_summary(result)

        # 결과 저장
        if args.output:
            save_evaluation_result(result, args.output)

        print(f"\n✅ 평가 완료!")
        return 0

    except Exception as e:
        print(f"\n❌ 평가 실패: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
