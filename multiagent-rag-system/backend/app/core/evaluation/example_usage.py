"""
보고서 평가 시스템 사용 예시
Example Usage of Report Evaluation System
"""

import json
from app.core.evaluation import ReportEvaluator
from app.core.workflows.state import RAGState


def example_1_basic_evaluation():
    """예시 1: 기본 평가"""
    print("\n" + "="*80)
    print("예시 1: 기본 평가 (자동 평가 + AI 심판)")
    print("="*80)

    # 샘플 상태 데이터
    state = {
        'original_query': '2024년 AI 시장 동향 분석 보고서를 작성해주세요',
        'final_answer': """
# 2024년 AI 시장 동향 분석 보고서

## 요약
2024년 AI 시장은 급격한 성장세를 보이고 있으며, 특히 생성형 AI 분야에서 혁신적인 발전이 이루어지고 있습니다.

## 시장 규모
글로벌 AI 시장 규모는 2024년 약 $500B에 달할 것으로 예상됩니다 [SOURCE:1].
전년 대비 25% 성장한 수치입니다 [SOURCE:2].

## 주요 트렌드
### 생성형 AI의 부상
- ChatGPT, Claude 등 대규모 언어 모델의 상용화
- 이미지 생성 AI (DALL-E, Midjourney)의 발전
- 멀티모달 AI의 등장

### 엔터프라이즈 AI 도입 확대
기업들의 AI 도입이 가속화되고 있습니다 [SOURCE:3].

## 결론
2024년은 AI가 일상과 비즈니스에 본격적으로 통합되는 원년이 될 것입니다.
        """,
        'step_results': [
            {
                'source': 'web_search',
                'content': 'AI market size 2024 is estimated at $500B',
                'score': 0.9,
                'title': 'AI Market Report 2024'
            },
            {
                'source': 'vector_db',
                'content': 'Year-over-year growth is 25%',
                'score': 0.85,
                'title': 'AI Growth Statistics'
            },
            {
                'source': 'web_search',
                'content': 'Enterprise AI adoption is accelerating',
                'score': 0.8,
                'title': 'Enterprise AI Trends'
            }
        ],
        'execution_log': [
            'Planning started',
            'Data gathering from web',
            'Data gathering from vector DB',
            'Processing report',
            'Report completed'
        ],
        'start_time': '2024-01-15T10:00:00',
        'metadata': {
            'team_type': 'marketing',
            'report_type': 'standard'
        }
    }

    # 평가기 생성
    evaluator = ReportEvaluator(use_ai_judge=True)

    # 평가 실행
    result = evaluator.evaluate_report(
        query=state['original_query'],
        state=state,
        expected_requirements=['시장 규모', '트렌드', '결론'],
        expected_sections=['요약', '분석', '결론'],
        expected_word_count=300
    )

    # 결과 출력
    print(f"\n종합 점수: {result.overall_score}/10 (등급: {result.grade})")
    print(f"작업 성공률: {result.task_success.success_rate:.2%}")
    print(f"품질 점수: {result.output_quality.overall_quality_score}/10")
    print(f"환각 현상: {result.hallucination.hallucination_count}건")
    print(f"실행 시간: {result.efficiency.total_execution_time:.2f}초")

    print(f"\n강점:")
    for strength in result.strengths:
        print(f"  - {strength}")

    print(f"\n약점:")
    for weakness in result.weaknesses:
        print(f"  - {weakness}")

    return result


def example_2_fast_evaluation():
    """예시 2: 빠른 평가 (AI 심판 없이)"""
    print("\n" + "="*80)
    print("예시 2: 빠른 평가 (자동 평가만)")
    print("="*80)

    state = {
        'original_query': '간단한 보고서 테스트',
        'final_answer': '테스트 보고서 내용입니다.',
        'step_results': [],
        'execution_log': ['Test'],
        'start_time': '2024-01-15T10:00:00',
        'metadata': {}
    }

    # AI 심판 비활성화
    evaluator = ReportEvaluator(use_ai_judge=False)

    result = evaluator.evaluate_report(
        query=state['original_query'],
        state=state
    )

    print(f"\n종합 점수: {result.overall_score}/10 (등급: {result.grade})")
    print("(AI 심판 평가는 수행되지 않았습니다)")

    return result


def example_3_batch_evaluation():
    """예시 3: 배치 평가 (여러 보고서 동시 평가)"""
    print("\n" + "="*80)
    print("예시 3: 배치 평가")
    print("="*80)

    # 여러 보고서 준비
    test_cases = [
        {
            'query': '테스트 1',
            'report': '짧은 보고서',
        },
        {
            'query': '테스트 2',
            'report': '중간 길이의 보고서입니다. 여러 문장이 있습니다.',
        },
        {
            'query': '테스트 3',
            'report': '긴 보고서입니다. ' * 50,
        }
    ]

    evaluator = ReportEvaluator(use_ai_judge=False)  # 빠른 평가
    results = []

    for i, test_case in enumerate(test_cases, 1):
        state = {
            'original_query': test_case['query'],
            'final_answer': test_case['report'],
            'step_results': [],
            'execution_log': [],
            'start_time': '2024-01-15T10:00:00',
            'metadata': {}
        }

        result = evaluator.evaluate_report(
            query=test_case['query'],
            state=state
        )

        results.append(result)
        print(f"\n보고서 {i}: 점수 {result.overall_score}/10 (등급: {result.grade})")

    # 통계 계산
    avg_score = sum(r.overall_score for r in results) / len(results)
    print(f"\n평균 점수: {avg_score:.2f}/10")

    return results


def example_4_save_and_load():
    """예시 4: 평가 결과 저장 및 로드"""
    print("\n" + "="*80)
    print("예시 4: 평가 결과 저장 및 로드")
    print("="*80)

    state = {
        'original_query': '테스트 보고서',
        'final_answer': '테스트 내용입니다.',
        'step_results': [],
        'execution_log': [],
        'start_time': '2024-01-15T10:00:00',
        'metadata': {}
    }

    evaluator = ReportEvaluator(use_ai_judge=False)

    # 평가 실행
    result = evaluator.evaluate_report(
        query=state['original_query'],
        state=state
    )

    # 결과 저장
    output_file = '/tmp/evaluation_result.json'
    result_dict = result.model_dump()

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=2)

    print(f"\n평가 결과 저장: {output_file}")

    # 결과 로드
    with open(output_file, 'r', encoding='utf-8') as f:
        loaded_dict = json.load(f)

    print(f"평가 결과 로드 성공")
    print(f"  - 평가 ID: {loaded_dict['evaluation_id']}")
    print(f"  - 종합 점수: {loaded_dict['overall_score']}/10")

    return loaded_dict


def example_5_custom_requirements():
    """예시 5: 커스텀 요구사항 평가"""
    print("\n" + "="*80)
    print("예시 5: 커스텀 요구사항 평가")
    print("="*80)

    state = {
        'original_query': '마케팅 캠페인 보고서',
        'final_answer': """
# 마케팅 캠페인 보고서

## 개요
Q1 마케팅 캠페인 결과를 분석합니다.

## 주요 지표
- CTR: 3.5%
- 전환율: 2.1%
- ROI: 250%

## 성과 분석
목표를 초과 달성했습니다.

## 개선 사항
다음 캠페인에서는 타겟팅을 더 세밀하게 할 예정입니다.

## 결론
성공적인 캠페인이었습니다.
        """,
        'step_results': [
            {'source': 'rdb', 'content': 'Campaign metrics', 'score': 0.95},
            {'source': 'vector_db', 'content': 'Historical data', 'score': 0.85}
        ],
        'execution_log': ['Data gathering', 'Analysis', 'Report generation'],
        'start_time': '2024-01-15T10:00:00',
        'metadata': {
            'team_type': 'marketing',
            'report_type': 'detailed'
        }
    }

    evaluator = ReportEvaluator(use_ai_judge=True)

    # 커스텀 요구사항 정의
    custom_requirements = [
        'CTR',
        'ROI',
        '성과 분석',
        '개선 사항',
        '결론'
    ]

    custom_sections = [
        '개요',
        '주요 지표',
        '성과 분석',
        '개선 사항',
        '결론'
    ]

    result = evaluator.evaluate_report(
        query=state['original_query'],
        state=state,
        expected_requirements=custom_requirements,
        expected_sections=custom_sections,
        expected_word_count=200
    )

    print(f"\n요구사항 충족률: {result.task_success.success_rate:.2%}")
    print(f"완성도: {result.completeness.completeness_rate:.2%}")
    print(f"종합 점수: {result.overall_score}/10")

    if result.task_success.missing_requirements:
        print(f"\n누락된 요구사항:")
        for req in result.task_success.missing_requirements:
            print(f"  - {req}")

    if result.completeness.missing_sections:
        print(f"\n누락된 섹션:")
        for section in result.completeness.missing_sections:
            print(f"  - {section}")

    return result


def main():
    """모든 예시 실행"""
    print("\n" + "="*80)
    print("보고서 평가 시스템 사용 예시")
    print("="*80)

    # 예시 1: 기본 평가
    try:
        example_1_basic_evaluation()
    except Exception as e:
        print(f"예시 1 실패: {e}")

    # 예시 2: 빠른 평가
    try:
        example_2_fast_evaluation()
    except Exception as e:
        print(f"예시 2 실패: {e}")

    # 예시 3: 배치 평가
    try:
        example_3_batch_evaluation()
    except Exception as e:
        print(f"예시 3 실패: {e}")

    # 예시 4: 저장/로드
    try:
        example_4_save_and_load()
    except Exception as e:
        print(f"예시 4 실패: {e}")

    # 예시 5: 커스텀 요구사항
    try:
        example_5_custom_requirements()
    except Exception as e:
        print(f"예시 5 실패: {e}")

    print("\n" + "="*80)
    print("모든 예시 실행 완료!")
    print("="*80)


if __name__ == '__main__':
    main()
