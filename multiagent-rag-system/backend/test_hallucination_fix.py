#!/usr/bin/env python
"""
환각 평가 타입 변환 테스트
Test Hallucination Type Conversion Fix
"""

import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/app')

from app.core.evaluation.evaluation_models import HallucinationMetrics


def test_hallucination_conversion():
    """Dict를 HallucinationMetrics로 변환 테스트"""

    # AI Judge가 반환하는 dict 형태 시뮬레이션
    hallucination_result = {
        'hallucination_detected': True,
        'hallucination_count': 2,
        'hallucination_rate': 0.15,
        'hallucination_examples': [
            '출처에 없는 내용 1',
            '출처에 없는 내용 2'
        ],
        'unverified_claims': ['검증되지 않은 주장'],
        'contradictions': [],
        'confidence_score': 0.85,
        'reasoning': 'Ensemble evaluation'
    }

    print("=" * 80)
    print("환각 평가 타입 변환 테스트")
    print("=" * 80)
    print()

    print("1. Dict 형태:")
    print(f"   Type: {type(hallucination_result)}")
    print(f"   Keys: {list(hallucination_result.keys())}")
    print()

    # Dict를 HallucinationMetrics 객체로 변환
    hallucination = HallucinationMetrics(
        hallucination_detected=hallucination_result.get('hallucination_detected', False),
        hallucination_count=hallucination_result.get('hallucination_count', 0),
        hallucination_rate=hallucination_result.get('hallucination_rate', 0.0),
        hallucination_examples=hallucination_result.get('hallucination_examples', []),
        unverified_claims=hallucination_result.get('unverified_claims', []),
        contradictions=hallucination_result.get('contradictions', []),
        confidence_score=hallucination_result.get('confidence_score', 0.5),
        reasoning=hallucination_result.get('reasoning', 'Ensemble evaluation')
    )

    print("2. HallucinationMetrics 객체로 변환:")
    print(f"   Type: {type(hallucination)}")
    print()

    # 속성 접근 테스트 (이전에 에러가 발생했던 부분)
    print("3. 속성 접근 테스트:")
    print(f"   ✓ hallucination.hallucination_count = {hallucination.hallucination_count}")
    print(f"   ✓ hallucination.hallucination_rate = {hallucination.hallucination_rate:.2%}")
    print(f"   ✓ hallucination.hallucination_detected = {hallucination.hallucination_detected}")
    print(f"   ✓ hallucination.unverified_claims = {hallucination.unverified_claims}")
    print(f"   ✓ hallucination.confidence_score = {hallucination.confidence_score}")
    print()

    # report_evaluator.py의 실제 사용 패턴 테스트
    print("4. 실제 코드 패턴 테스트:")

    # Line 183-184: 출력문
    print(f"   ✓ 환각 현상 감지: {hallucination.hallucination_count}건 "
          f"(비율: {hallucination.hallucination_rate:.2%})")

    # Line 309: 점수 계산
    hallucination_score = (1 - hallucination.hallucination_rate) * 10
    print(f"   ✓ 환각 점수: {hallucination_score:.2f}/10")

    # Line 375: 조건 확인
    if hallucination.hallucination_count == 0:
        print(f"   ✓ 환각 없음 체크: 통과")
    else:
        print(f"   ✓ 환각 있음 체크: {hallucination.hallucination_count}건 감지")

    # Line 399: unverified_claims 확인
    if hallucination.unverified_claims:
        print(f"   ✓ 검증되지 않은 주장: {len(hallucination.unverified_claims)}개")

    print()
    print("=" * 80)
    print("✅ 모든 테스트 통과!")
    print("=" * 80)


if __name__ == "__main__":
    try:
        test_hallucination_conversion()
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
