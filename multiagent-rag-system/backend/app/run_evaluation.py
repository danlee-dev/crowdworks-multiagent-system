#!/usr/bin/env python
"""
평가 벤치마크 실행 스크립트
Run Evaluation Benchmark
"""

import asyncio
import sys
from pathlib import Path

# 경로 설정 (Docker 컨테이너 내부)
sys.path.insert(0, '/app')

from app.core.evaluation.report_evaluation_benchmark import ReportEvaluationBenchmark


async def main():
    """메인 실행 함수"""

    print("=" * 80)
    print("Multi-Agent RAG 시스템 평가 벤치마크")
    print("=" * 80)
    print()

    # 설정
    base_url = "http://localhost:8000"
    use_ai_judge = True
    use_ensemble = True  # 3-Model Ensemble (Gemini + Claude + GPT-4o)

    print(f"API 서버: {base_url}")
    print(f"AI Judge: {'활성화' if use_ai_judge else '비활성화'}")
    print(f"평가 방식: {'3-Model Ensemble' if use_ensemble else '단일 모델'}")
    print()

    # 벤치마크 초기화
    benchmark = ReportEvaluationBenchmark(
        base_url=base_url,
        use_ai_judge=use_ai_judge,
        use_ensemble=use_ensemble
    )

    # 실행
    print("벤치마크 시작...")
    print()

    try:
        results = await benchmark.run_benchmark()

        # 요약 출력
        benchmark.print_summary(results['summary'])

        print("\n" + "=" * 80)
        print("평가 완료!")
        print("=" * 80)
        print(f"\n결과 저장 위치: evaluation_results/")
        print("  - CSV 파일: evaluation_results/YYYYMMDD_HHMMSS/csv/")
        print("  - 차트: evaluation_results/YYYYMMDD_HHMMSS/charts/")
        print("  - JSON: evaluation_results/YYYYMMDD_HHMMSS/json/")
        print("  - 요약: evaluation_results/YYYYMMDD_HHMMSS/SUMMARY.md")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
