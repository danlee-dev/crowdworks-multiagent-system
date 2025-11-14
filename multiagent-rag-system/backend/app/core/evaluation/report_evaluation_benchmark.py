"""
보고서 평가 벤치마크
Report Evaluation Benchmark via API

HTTP API를 통해 보고서를 생성하고 실시간으로 평가합니다.
"""

import asyncio
import aiohttp
import time
import json
import statistics
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

import pandas as pd

from app.core.evaluation import ReportEvaluator
from app.core.evaluation.detailed_results_exporter import DetailedResultsExporter


@dataclass
class ReportBenchmarkResult:
    """보고서 평가 벤치마크 결과"""
    query_id: str
    query_text: str
    team_type: Optional[str]

    # 실행 시간
    total_time: float
    response_time: float

    # 생성 결과
    report_length: int
    sources_count: int
    search_tools_used: List[str]

    # 평가 점수
    overall_score: float
    grade: str
    success_rate: float
    quality_score: float
    completeness_rate: float
    hallucination_count: int
    efficiency_score: float
    citation_accuracy: float = 1.0

    # AI 평가 근거
    quality_reasoning: str = ""
    hallucination_reasoning: str = ""
    hallucination_examples: List[str] = None
    strengths: List[str] = None
    weaknesses: List[str] = None
    recommendations: List[str] = None

    # 상태
    success: bool = True
    error_msg: Optional[str] = None
    timestamp: str = ""
    session_id: str = ""

    def __post_init__(self):
        if self.hallucination_examples is None:
            self.hallucination_examples = []
        if self.strengths is None:
            self.strengths = []
        if self.weaknesses is None:
            self.weaknesses = []
        if self.recommendations is None:
            self.recommendations = []


class ReportEvaluationBenchmark:
    """API를 통한 보고서 생성 및 평가 벤치마크"""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        queries_file: str = None,
        use_ai_judge: bool = True,
        use_ensemble: bool = True
    ):
        """
        초기화

        Args:
            base_url: API 서버 주소
            queries_file: 쿼리 파일 경로
            use_ai_judge: AI Judge 사용 여부
            use_ensemble: 3-Model Ensemble 사용 여부 (True 권장)
        """
        self.base_url = base_url
        self.results: List[ReportBenchmarkResult] = []

        # Ensemble AI Judge로 평가 (Gemini + Claude + GPT-4o)
        self.evaluator = ReportEvaluator(
            use_ai_judge=use_ai_judge,
            use_ensemble=use_ensemble
        )

        # 쿼리 파일에서 로드 또는 기본값 사용
        if queries_file and os.path.exists(queries_file):
            self.test_queries = self._load_queries_from_file(queries_file)
            print(f"쿼리 파일 로드: {queries_file}")
        else:
            # 기본 테스트 쿼리 (식품 도메인)
            self.test_queries = {
                "marketing": [
                    "2024년 대체육 시장 동향 및 소비자 선호도 분석 보고서를 작성해주세요",
                    "밀키트 산업의 성장 전략과 마케팅 방안 보고서를 작성해주세요",
                    "MZ세대 타겟 건강기능식품 시장 진입 전략 보고서를 작성해주세요",
                ],
                "purchasing": [
                    "국내 농산물 가격 변동 추이 및 구매 최적화 전략 보고서를 작성해주세요",
                    "글로벌 식자재 공급망 리스크 관리 방안 보고서를 작성해주세요",
                    "친환경 유기농 식재료 소싱 가이드 보고서를 작성해주세요",
                ],
                "general": [
                    "식품 안전 규제 동향 및 컴플라이언스 대응 방안 보고서를 작성해주세요",
                    "푸드테크 산업의 AI 활용 사례 분석 보고서를 작성해주세요",
                    "탄소중립을 위한 식품 산업의 ESG 경영 전략 보고서를 작성해주세요",
                ]
            }

    def _load_queries_from_file(self, file_path: str) -> Dict[str, List[str]]:
        """
        텍스트 파일에서 쿼리 로드

        포맷:
        [marketing]
        쿼리1

        쿼리2

        [purchasing]
        쿼리3
        """
        queries = {}
        current_team = None

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # 빈 줄 무시
                if not line:
                    continue

                # 팀 타입 헤더 [team_type]
                if line.startswith('[') and line.endswith(']'):
                    current_team = line[1:-1].strip()
                    if current_team not in queries:
                        queries[current_team] = []
                # 쿼리
                elif current_team:
                    queries[current_team].append(line)

        return queries

    async def test_single_report(
        self,
        session: aiohttp.ClientSession,
        query: str,
        team_type: str,
        query_id: str
    ) -> ReportBenchmarkResult:
        """단일 보고서 생성 및 평가"""

        print(f"  테스트: [{team_type}] {query[:40]}...")

        start_time = time.time()
        session_id = f"eval_benchmark_{query_id}_{int(time.time())}"

        # API 요청 준비
        payload = {
            "query": query,
            "session_id": session_id,
            "team_id": team_type
        }

        # 수집 데이터
        search_tools_used = []
        sources_count = 0
        report_chunks = []
        sources_data = []
        step_results = []
        execution_log = []

        try:
            # API 호출 (대용량 응답을 위한 큰 버퍼 설정)
            async with session.post(
                f"{self.base_url}/query/stream",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180),  # 3분 타임아웃
                max_line_size=100*1024*1024,  # 100MB 버퍼
                max_field_size=100*1024*1024  # 100MB 버퍼
            ) as response:

                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")

                # 스트리밍 응답 처리 (대용량 청크 대응)
                buffer = b""
                async for chunk in response.content.iter_chunked(1024 * 1024):  # 1MB 청크씩 읽기
                    buffer += chunk

                    # 줄바꿈으로 분리
                    while b'\n' in buffer:
                        line_bytes, buffer = buffer.split(b'\n', 1)
                        line = line_bytes.decode('utf-8', errors='ignore').strip()

                        if line.startswith('data: '):
                            try:
                                data = json.loads(line[6:])
                                event_type = data.get('type')

                                # 검색 결과 수집
                                if event_type == 'search_results':
                                    tool_name = data.get('tool_name', '')
                                    if tool_name and tool_name not in search_tools_used:
                                        search_tools_used.append(tool_name)

                                    results = data.get('results', [])
                                    sources_count += len(results)

                                    # step_results에 추가
                                    for result in results:
                                        step_results.append({
                                            'source': tool_name,
                                            'content': result.get('content', ''),
                                            'score': result.get('score', 0.7),
                                            'title': result.get('title', '')
                                        })

                                    execution_log.append(f"Search: {tool_name}")

                                # 콘텐츠 수집
                                elif event_type == 'content':
                                    chunk = data.get('chunk', '')
                                    report_chunks.append(chunk)

                                elif event_type == 'content_chunk':
                                    chunk = data.get('chunk', '')
                                    report_chunks.append(chunk)

                                # 상태 로그
                                elif event_type == 'status':
                                    message = data.get('message', '')
                                    execution_log.append(message)

                                # 출처 정보
                                elif event_type == 'complete':
                                    sources = data.get('sources', {})
                                    if sources:
                                        sources_data = sources.get('sources', [])
                                    break

                                elif event_type == 'final_complete':
                                    break

                            except json.JSONDecodeError:
                                continue

                response_time = time.time() - start_time
                final_report = ''.join(report_chunks)

                # State 생성 (평가용)
                state = {
                    'original_query': query,
                    'final_answer': final_report,
                    'step_results': step_results,
                    'execution_log': execution_log,
                    'start_time': datetime.fromtimestamp(start_time).isoformat(),
                    'conversation_id': session_id,
                    'user_id': 'benchmark',
                    'session_id': session_id,
                    'metadata': {
                        'team_type': team_type,
                        'total_execution_time': response_time,
                        'end_time': datetime.now().isoformat(),
                        'sources': sources_data
                    }
                }

                # 평가 실행
                print(f"    평가 중...")
                eval_result = self.evaluator.evaluate_report(
                    query=query,
                    state=state,
                    expected_requirements=None,  # 자동 평가
                    expected_sections=None,  # 섹션 이름은 자동 생성되므로 검증 안 함
                    team_type=team_type,
                    model_name="gemini-2.5-flash"
                )

                print(f"    완료 ({response_time:.2f}초) - 점수: {eval_result.overall_score:.1f}/10 ({eval_result.grade})")

                return ReportBenchmarkResult(
                    query_id=query_id,
                    query_text=query,
                    team_type=team_type,
                    total_time=response_time,
                    response_time=response_time,
                    report_length=len(final_report),
                    sources_count=sources_count,
                    search_tools_used=search_tools_used,
                    overall_score=eval_result.overall_score,
                    grade=eval_result.grade,
                    success_rate=eval_result.task_success.success_rate,
                    quality_score=eval_result.output_quality.overall_quality_score,
                    completeness_rate=eval_result.completeness.completeness_rate,
                    hallucination_count=eval_result.hallucination.hallucination_count,
                    efficiency_score=eval_result.efficiency.efficiency_score,
                    citation_accuracy=eval_result.hallucination.citation_accuracy,
                    # AI 평가 근거
                    quality_reasoning=eval_result.output_quality.reasoning,
                    hallucination_reasoning=eval_result.hallucination.reasoning,
                    hallucination_examples=eval_result.hallucination.hallucination_examples,
                    strengths=eval_result.strengths,
                    weaknesses=eval_result.weaknesses,
                    recommendations=eval_result.recommendations,
                    success=True,
                    session_id=session_id,
                    timestamp=datetime.now().isoformat()
                )

        except Exception as e:
            response_time = time.time() - start_time
            import traceback
            print(f"    실패 ({response_time:.2f}초): {str(e)}")
            print(f"       상세: {traceback.format_exc()}")

            return ReportBenchmarkResult(
                query_id=query_id,
                query_text=query,
                team_type=team_type,
                total_time=response_time,
                response_time=response_time,
                report_length=0,
                sources_count=0,
                search_tools_used=[],
                overall_score=0.0,
                grade="F",
                success_rate=0.0,
                quality_score=0.0,
                completeness_rate=0.0,
                hallucination_count=0,
                efficiency_score=0.0,
                success=False,
                error_msg=str(e),
                session_id=session_id,
                timestamp=datetime.now().isoformat()
            )

    async def run_benchmark(self, use_ai_judge: bool = False) -> Dict[str, Any]:
        """전체 벤치마크 실행"""

        print("-" * 80)
        print("보고서 평가 벤치마크 시작")
        print("-" * 80)
        print(f"대상 시스템: {self.base_url}")
        print(f"AI 심판: {'활성화' if use_ai_judge else '비활성화 (빠른 평가)'}")
        print(f"총 {sum(len(queries) for queries in self.test_queries.values())}개 보고서 생성 및 평가")
        print()

        # AI 심판 설정
        self.evaluator = ReportEvaluator(use_ai_judge=use_ai_judge)

        # 시스템 상태 확인
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        health_data = await response.json()
                        print(f"시스템 상태: {health_data.get('status', 'unknown')}\n")
                    else:
                        print(f"시스템 응답: HTTP {response.status}\n")
            except Exception as e:
                print(f"시스템 연결 실패: {e}")
                return {"error": "시스템 연결 불가"}

        results = {
            'config': {
                'target_system': self.base_url,
                'use_ai_judge': use_ai_judge,
                'total_queries': sum(len(queries) for queries in self.test_queries.values()),
                'queries_per_team': {team: len(queries) for team, queries in self.test_queries.items()}
            },
            'start_time': datetime.now().isoformat(),
            'results': {},
            'raw_results': []
        }

        # HTTP 세션 생성 (대용량 보고서를 위한 큰 버퍼 설정)
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=5, limit_per_host=3),
            timeout=aiohttp.ClientTimeout(total=600, sock_read=300),
            max_line_size=100*1024*1024,  # 100MB (기본 8KB)
            max_field_size=100*1024*1024  # 100MB (기본 8KB)
        ) as session:

            for team_type, queries in self.test_queries.items():
                print(f"[{team_type}] 팀 보고서 테스트 ({len(queries)}개)")
                team_results = []

                for i, query in enumerate(queries, 1):
                    query_id = f"{team_type}_q{i:02d}"

                    # 개별 보고서 테스트
                    result = await self.test_single_report(session, query, team_type, query_id)
                    team_results.append(asdict(result))
                    self.results.append(result)

                    # 쿼리 간 간격 (시스템 부하 방지)
                    await asyncio.sleep(2)

                results['results'][team_type] = team_results
                print()

        # 결과 요약 생성
        results['summary'] = self._generate_summary()
        results['raw_results'] = [asdict(r) for r in self.results]
        results['end_time'] = datetime.now().isoformat()

        # 상세 결과 저장 (CSV + Charts + JSON)
        print("\n=== 평가 결과 저장 중... ===")
        exporter = DetailedResultsExporter(output_dir="evaluation_results")
        exporter.export_detailed_results(
            results=results['raw_results'],
            summary_stats=results['summary']
        )

        return results

    def _generate_summary(self) -> Dict[str, Any]:
        """벤치마크 결과 요약 생성"""

        successful_results = [r for r in self.results if r.success]

        summary = {
            'total_reports': len(self.results),
            'successful_reports': len(successful_results),
            'success_rate': len(successful_results) / len(self.results) * 100 if self.results else 0,
        }

        if successful_results:
            # 점수 통계
            scores = [r.overall_score for r in successful_results]
            quality_scores = [r.quality_score for r in successful_results]
            success_rates = [r.success_rate for r in successful_results]
            completeness_rates = [r.completeness_rate for r in successful_results]

            summary['scores'] = {
                'avg_overall_score': statistics.mean(scores),
                'median_overall_score': statistics.median(scores),
                'min_score': min(scores),
                'max_score': max(scores),
                'std_score': statistics.stdev(scores) if len(scores) > 1 else 0,
                'avg_quality_score': statistics.mean(quality_scores),
                'avg_success_rate': statistics.mean(success_rates),
                'avg_completeness': statistics.mean(completeness_rates)
            }

            # 등급 분포
            grades = [r.grade for r in successful_results]
            grade_dist = {}
            for grade in grades:
                grade_dist[grade] = grade_dist.get(grade, 0) + 1
            summary['grade_distribution'] = grade_dist

            # 실행 시간
            times = [r.total_time for r in successful_results]
            summary['performance'] = {
                'avg_time': statistics.mean(times),
                'median_time': statistics.median(times),
                'min_time': min(times),
                'max_time': max(times),
                'std_time': statistics.stdev(times) if len(times) > 1 else 0
            }

            # 콘텐츠 메트릭
            lengths = [r.report_length for r in successful_results]
            sources = [r.sources_count for r in successful_results]

            summary['content'] = {
                'avg_report_length': statistics.mean(lengths),
                'avg_sources_count': statistics.mean(sources)
            }

            # 팀별 성능
            by_team = {}
            for team_type in self.test_queries.keys():
                team_results = [r for r in successful_results if r.team_type == team_type]
                if team_results:
                    team_scores = [r.overall_score for r in team_results]
                    team_times = [r.total_time for r in team_results]

                    by_team[team_type] = {
                        'count': len(team_results),
                        'avg_score': statistics.mean(team_scores),
                        'avg_time': statistics.mean(team_times),
                        'avg_quality': statistics.mean([r.quality_score for r in team_results]),
                        'avg_hallucination': statistics.mean([r.hallucination_count for r in team_results])
                    }

            summary['by_team'] = by_team

            # 환각 현상 통계
            hallucinations = [r.hallucination_count for r in successful_results]
            summary['hallucination'] = {
                'avg_count': statistics.mean(hallucinations),
                'max_count': max(hallucinations),
                'reports_with_hallucination': len([h for h in hallucinations if h > 0]),
                'hallucination_rate': len([h for h in hallucinations if h > 0]) / len(successful_results) * 100
            }

        return summary

    def print_summary(self, summary: Dict[str, Any]) -> None:
        """요약 결과 출력"""

        print("\n" + "=" * 80)
        print("보고서 평가 벤치마크 결과")
        print("-" * 80)

        print(f"\n전체 성공률: {summary['success_rate']:.1f}% ({summary['successful_reports']}/{summary['total_reports']})")

        if 'scores' in summary:
            scores = summary['scores']
            print(f"\n평가 점수:")
            print(f"   • 평균 점수: {scores['avg_overall_score']:.2f}/10")
            print(f"   • 중앙값: {scores['median_overall_score']:.2f}/10")
            print(f"   • 범위: {scores['min_score']:.2f} ~ {scores['max_score']:.2f}")
            print(f"   • 표준편차: {scores['std_score']:.2f}")
            print(f"   • 평균 품질: {scores['avg_quality_score']:.2f}/10")
            print(f"   • 평균 완성도: {scores['avg_completeness']:.1%}")

        if 'grade_distribution' in summary:
            print(f"\n등급 분포:")
            for grade, count in sorted(summary['grade_distribution'].items()):
                print(f"   • {grade}: {count}개")

        if 'performance' in summary:
            perf = summary['performance']
            print(f"\n실행 시간:")
            print(f"   • 평균: {perf['avg_time']:.2f}초")
            print(f"   • 중앙값: {perf['median_time']:.2f}초")
            print(f"   • 범위: {perf['min_time']:.2f} ~ {perf['max_time']:.2f}초")

        if 'by_team' in summary:
            print(f"\n팀별 성능:")
            for team, stats in summary['by_team'].items():
                print(f"   [{team}]:")
                print(f"      - 평균 점수: {stats['avg_score']:.2f}/10")
                print(f"      - 평균 시간: {stats['avg_time']:.2f}초")
                print(f"      - 평균 품질: {stats['avg_quality']:.2f}/10")
                print(f"      - 평균 환각: {stats['avg_hallucination']:.1f}건")

        if 'hallucination' in summary:
            hall = summary['hallucination']
            print(f"\n환각 현상 분석:")
            print(f"   • 평균 환각 개수: {hall['avg_count']:.2f}건")
            print(f"   • 최대 환각 개수: {hall['max_count']}건")
            print(f"   • 환각 발생률: {hall['hallucination_rate']:.1f}%")

        if 'content' in summary:
            content = summary['content']
            print(f"\n콘텐츠 메트릭:")
            print(f"   • 평균 보고서 길이: {content['avg_report_length']:.0f}자")
            print(f"   • 평균 출처 개수: {content['avg_sources_count']:.1f}개")

    def save_results(self, results: Dict[str, Any], output_dir: str = None) -> Dict[str, str]:
        """결과 저장 - JSON, CSV, Excel, Markdown, 시각화 차트 자동 생성"""

        # 출력 디렉토리 설정
        if output_dir is None:
            # 호스트에서 볼 수 있는 경로 사용
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = f"/app/evaluation_results/{timestamp}"

        os.makedirs(output_dir, exist_ok=True)

        saved_files = {}

        # 1. JSON 결과 저장
        json_path = os.path.join(output_dir, "benchmark_results.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        saved_files['json'] = json_path

        # 1-1. AI 평가 상세 근거 저장
        evaluation_details_dir = os.path.join(output_dir, "evaluation_details")
        os.makedirs(evaluation_details_dir, exist_ok=True)

        for result in results.get('raw_results', []):
            query_id = result.get('query_id', 'unknown')
            detail_path = os.path.join(evaluation_details_dir, f"{query_id}_evaluation.txt")

            with open(detail_path, 'w', encoding='utf-8') as f:
                f.write(f"=== 보고서 평가 상세 내역 ===\n\n")
                f.write(f"Query ID: {query_id}\n")
                f.write(f"Query: {result.get('query_text', 'N/A')}\n")
                f.write(f"Team Type: {result.get('team_type', 'N/A')}\n")
                f.write(f"Timestamp: {result.get('timestamp', 'N/A')}\n\n")

                f.write(f"--- 종합 평가 ---\n")
                f.write(f"Overall Score: {result.get('overall_score', 0):.2f}/10\n")
                f.write(f"Grade: {result.get('grade', 'N/A')}\n")
                f.write(f"Success: {result.get('success', False)}\n\n")

                f.write(f"--- 세부 점수 ---\n")
                f.write(f"Success Rate: {result.get('success_rate', 0):.2%}\n")
                f.write(f"Quality Score: {result.get('quality_score', 0):.1f}/10\n")
                f.write(f"Completeness: {result.get('completeness_rate', 0):.2%}\n")
                f.write(f"Hallucination Count: {result.get('hallucination_count', 0)}\n")
                f.write(f"Efficiency Score: {result.get('efficiency_score', 0):.1f}/10\n\n")

                f.write(f"--- 실행 정보 ---\n")
                f.write(f"Total Time: {result.get('total_time', 0):.2f}s\n")
                f.write(f"Report Length: {result.get('report_length', 0)} chars\n")
                f.write(f"Sources Count: {result.get('sources_count', 0)}\n")
                f.write(f"Search Tools: {', '.join(result.get('search_tools_used', []))}\n\n")

                if result.get('error_msg'):
                    f.write(f"--- 오류 ---\n")
                    f.write(f"{result.get('error_msg')}\n\n")

                # AI 평가 근거 상세 기록
                f.write(f"--- AI 품질 평가 근거 ---\n")
                f.write(f"{result.get('quality_reasoning', '근거 없음')}\n\n")

                f.write(f"--- AI 환각 평가 근거 ---\n")
                f.write(f"{result.get('hallucination_reasoning', '근거 없음')}\n\n")

                hallucination_examples = result.get('hallucination_examples', [])
                if hallucination_examples:
                    f.write(f"--- 환각 사례 ---\n")
                    for i, example in enumerate(hallucination_examples, 1):
                        f.write(f"{i}. {example}\n")
                    f.write(f"\n")

                strengths = result.get('strengths', [])
                if strengths:
                    f.write(f"--- 강점 ---\n")
                    for strength in strengths:
                        f.write(f"- {strength}\n")
                    f.write(f"\n")

                weaknesses = result.get('weaknesses', [])
                if weaknesses:
                    f.write(f"--- 약점 ---\n")
                    for weakness in weaknesses:
                        f.write(f"- {weakness}\n")
                    f.write(f"\n")

                recommendations = result.get('recommendations', [])
                if recommendations:
                    f.write(f"--- 개선 권장사항 ---\n")
                    for rec in recommendations:
                        f.write(f"- {rec}\n")
                    f.write(f"\n")

                f.write(f"\n{'='*60}\n")

        saved_files['evaluation_details'] = evaluation_details_dir

        # 2. CSV 저장
        csv_path = os.path.join(output_dir, "benchmark_results.csv")
        df = pd.DataFrame(results['raw_results'])
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        saved_files['csv'] = csv_path

        # 3. Excel 저장 (팀별 시트)
        excel_path = os.path.join(output_dir, "benchmark_results.xlsx")
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # 전체 결과
            df.to_excel(writer, sheet_name='전체결과', index=False)

            # 팀별 시트
            for team_type in df['team_type'].unique():
                df_team = df[df['team_type'] == team_type]
                df_team.to_excel(writer, sheet_name=f'{team_type}팀', index=False)
        saved_files['excel'] = excel_path

        # 4. Markdown 요약 저장
        md_path = os.path.join(output_dir, "benchmark_summary.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(self._generate_markdown_report(results))
        saved_files['markdown'] = md_path

        # 5. 시각화 차트 생성
        charts_dir = os.path.join(output_dir, "charts")
        os.makedirs(charts_dir, exist_ok=True)
        chart_files = self._create_visualizations(df, charts_dir)
        saved_files['charts'] = chart_files

        print(f"\n저장된 파일:")
        print(f"  - JSON: {json_path}")
        print(f"  - CSV: {csv_path}")
        print(f"  - Excel: {excel_path}")
        print(f"  - Markdown: {md_path}")
        print(f"  - 차트: {len(chart_files)}개 생성됨")

        return saved_files

    def _generate_markdown_report(self, results: Dict[str, Any]) -> str:
        """Markdown 형식 보고서 생성"""

        summary = results.get('summary', {})
        config = results.get('config', {})

        md = f"""# 보고서 평가 벤치마크 결과

## 실행 정보

- 실행 시간: {results.get('start_time', 'N/A')} ~ {results.get('end_time', 'N/A')}
- 대상 시스템: {config.get('target_system', 'N/A')}
- AI 심판: {'활성화' if config.get('use_ai_judge') else '비활성화'}
- 총 쿼리 수: {config.get('total_queries', 0)}개

## 전체 성능

- 성공률: {summary.get('success_rate', 0):.1f}% ({summary.get('successful_reports', 0)}/{summary.get('total_reports', 0)})
"""

        if 'scores' in summary:
            scores = summary['scores']
            md += f"""
## 평가 점수

| 메트릭 | 값 |
|--------|-----|
| 평균 점수 | {scores['avg_overall_score']:.2f}/10 |
| 중앙값 | {scores['median_overall_score']:.2f}/10 |
| 최소-최대 | {scores['min_score']:.2f} - {scores['max_score']:.2f} |
| 표준편차 | {scores['std_score']:.2f} |
| 평균 품질 | {scores['avg_quality_score']:.2f}/10 |
| 평균 완성도 | {scores['avg_completeness']:.1%} |
"""

        if 'grade_distribution' in summary:
            md += "\n## 등급 분포\n\n"
            for grade, count in sorted(summary['grade_distribution'].items()):
                md += f"- {grade}: {count}개\n"

        if 'by_team' in summary:
            md += "\n## 팀별 성능\n\n"
            md += "| 팀 | 평균 점수 | 평균 시간 | 평균 품질 | 평균 환각 |\n"
            md += "|-----|-----------|-----------|-----------|----------|\n"
            for team, stats in summary['by_team'].items():
                md += f"| {team} | {stats['avg_score']:.2f} | {stats['avg_time']:.2f}초 | {stats['avg_quality']:.2f} | {stats['avg_hallucination']:.1f}건 |\n"

        if 'hallucination' in summary:
            hall = summary['hallucination']
            md += f"""
## 환각 현상 분석

- 평균 환각 개수: {hall['avg_count']:.2f}건
- 최대 환각 개수: {hall['max_count']}건
- 환각 발생률: {hall['hallucination_rate']:.1f}%
"""

        if 'performance' in summary:
            perf = summary['performance']
            md += f"""
## 실행 시간

- 평균: {perf['avg_time']:.2f}초
- 중앙값: {perf['median_time']:.2f}초
- 범위: {perf['min_time']:.2f} - {perf['max_time']:.2f}초
"""

        return md

    def _create_visualizations(self, df: pd.DataFrame, output_dir: str) -> List[str]:
        """시각화 차트 생성"""

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        import warnings
        warnings.filterwarnings('ignore', category=UserWarning)

        # 한글 폰트 설정
        plt.rcParams['axes.unicode_minus'] = False

        # 시스템에서 사용 가능한 한글 폰트 찾기
        try:
            # Linux 환경에서 일반적으로 사용 가능한 한글 폰트들 시도
            font_candidates = [
                'NanumGothic', 'NanumBarunGothic', 'Noto Sans CJK KR',
                'Malgun Gothic', 'AppleGothic', 'UnDotum', 'Nanum Gothic'
            ]

            available_fonts = [f.name for f in fm.fontManager.ttflist]
            korean_font = None

            for font in font_candidates:
                if font in available_fonts:
                    korean_font = font
                    break

            if korean_font:
                plt.rcParams['font.family'] = korean_font
            else:
                # 폰트를 찾지 못한 경우 DejaVu Sans 사용 (한글은 표시 안됨)
                plt.rcParams['font.family'] = 'DejaVu Sans'
                print("⚠️  한글 폰트를 찾을 수 없습니다. 영문 레이블로 대체합니다.")
        except Exception as e:
            print(f"⚠️  폰트 설정 실패: {e}")
            plt.rcParams['font.family'] = 'DejaVu Sans'

        chart_files = []

        # 1. 점수 분포 히스토그램
        plt.figure(figsize=(10, 6))
        plt.hist(df['overall_score'], bins=20, color='#4ECDC4', edgecolor='black', alpha=0.7)
        plt.xlabel('Overall Score', fontsize=12)
        plt.ylabel('Frequency', fontsize=12)
        plt.title('Score Distribution', fontsize=14, fontweight='bold')
        plt.grid(axis='y', alpha=0.3)
        chart_path = os.path.join(output_dir, "score_distribution.png")
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        chart_files.append(chart_path)

        # 2. 팀별 평균 점수 비교
        plt.figure(figsize=(10, 6))
        team_scores = df.groupby('team_type')['overall_score'].mean().sort_values(ascending=False)
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
        team_scores.plot(kind='bar', color=colors[:len(team_scores)], edgecolor='black', alpha=0.8)
        plt.xlabel('Team Type', fontsize=12)
        plt.ylabel('Average Score', fontsize=12)
        plt.title('Team Performance Comparison', fontsize=14, fontweight='bold')
        plt.xticks(rotation=0)
        plt.grid(axis='y', alpha=0.3)
        chart_path = os.path.join(output_dir, "team_comparison.png")
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        chart_files.append(chart_path)

        # 3. 실행 시간 vs 점수 산점도
        plt.figure(figsize=(10, 6))
        for team_type in df['team_type'].unique():
            team_data = df[df['team_type'] == team_type]
            plt.scatter(team_data['total_time'], team_data['overall_score'],
                       label=team_type, alpha=0.7, s=100)
        plt.xlabel('Execution Time (seconds)', fontsize=12)
        plt.ylabel('Overall Score', fontsize=12)
        plt.title('Execution Time vs Score', fontsize=14, fontweight='bold')
        plt.legend()
        plt.grid(alpha=0.3)
        chart_path = os.path.join(output_dir, "time_vs_score.png")
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        chart_files.append(chart_path)

        # 4. 등급 분포 파이 차트
        plt.figure(figsize=(10, 8))
        grade_counts = df['grade'].value_counts()
        colors_pie = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#95E1D3', '#F38181']
        plt.pie(grade_counts.values, labels=grade_counts.index, autopct='%1.1f%%',
               colors=colors_pie[:len(grade_counts)], startangle=90)
        plt.title('Grade Distribution', fontsize=14, fontweight='bold')
        chart_path = os.path.join(output_dir, "grade_distribution.png")
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        chart_files.append(chart_path)

        # 5. 환각 분석
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

        # 환각 개수 분포
        ax1.hist(df['hallucination_count'], bins=15, color='#FF6B6B', edgecolor='black', alpha=0.7)
        ax1.set_xlabel('Hallucination Count', fontsize=12)
        ax1.set_ylabel('Frequency', fontsize=12)
        ax1.set_title('Hallucination Distribution', fontsize=14, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)

        # 팀별 평균 환각
        team_hall = df.groupby('team_type')['hallucination_count'].mean().sort_values(ascending=False)
        team_hall.plot(kind='bar', ax=ax2, color='#FF6B6B', edgecolor='black', alpha=0.8)
        ax2.set_xlabel('Team Type', fontsize=12)
        ax2.set_ylabel('Average Hallucination Count', fontsize=12)
        ax2.set_title('Hallucinations by Team', fontsize=14, fontweight='bold')
        ax2.tick_params(axis='x', rotation=0)
        ax2.grid(axis='y', alpha=0.3)

        chart_path = os.path.join(output_dir, "hallucination_analysis.png")
        plt.tight_layout()
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        chart_files.append(chart_path)

        # 6. 종합 대시보드
        fig = plt.figure(figsize=(20, 12))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

        # 점수 분포
        ax1 = fig.add_subplot(gs[0, :2])
        ax1.hist(df['overall_score'], bins=20, color='#4ECDC4', edgecolor='black', alpha=0.7)
        ax1.set_title('Score Distribution', fontsize=12, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)

        # 등급 분포
        ax2 = fig.add_subplot(gs[0, 2])
        grade_counts.plot(kind='pie', ax=ax2, autopct='%1.1f%%',
                         colors=colors_pie[:len(grade_counts)])
        ax2.set_title('Grade Distribution', fontsize=12, fontweight='bold')

        # 팀별 점수
        ax3 = fig.add_subplot(gs[1, 0])
        team_scores.plot(kind='bar', ax=ax3, color=colors[:len(team_scores)],
                        edgecolor='black', alpha=0.8)
        ax3.set_title('Team Scores', fontsize=12, fontweight='bold')
        ax3.tick_params(axis='x', rotation=0)
        ax3.grid(axis='y', alpha=0.3)

        # 시간 vs 점수
        ax4 = fig.add_subplot(gs[1, 1:])
        for team_type in df['team_type'].unique():
            team_data = df[df['team_type'] == team_type]
            ax4.scatter(team_data['total_time'], team_data['overall_score'],
                       label=team_type, alpha=0.7, s=100)
        ax4.set_title('Time vs Score', fontsize=12, fontweight='bold')
        ax4.legend()
        ax4.grid(alpha=0.3)

        # 환각 분포
        ax5 = fig.add_subplot(gs[2, 0])
        ax5.hist(df['hallucination_count'], bins=15, color='#FF6B6B',
                edgecolor='black', alpha=0.7)
        ax5.set_title('Hallucination Distribution', fontsize=12, fontweight='bold')
        ax5.grid(axis='y', alpha=0.3)

        # 팀별 환각
        ax6 = fig.add_subplot(gs[2, 1])
        team_hall.plot(kind='bar', ax=ax6, color='#FF6B6B', edgecolor='black', alpha=0.8)
        ax6.set_title('Hallucinations by Team', fontsize=12, fontweight='bold')
        ax6.tick_params(axis='x', rotation=0)
        ax6.grid(axis='y', alpha=0.3)

        # 메트릭 요약 테이블
        ax7 = fig.add_subplot(gs[2, 2])
        ax7.axis('off')
        summary_text = f"""Performance Summary

Total Reports: {len(df)}
Avg Score: {df['overall_score'].mean():.2f}
Avg Time: {df['total_time'].mean():.1f}s
Avg Quality: {df['quality_score'].mean():.2f}
Avg Hallucinations: {df['hallucination_count'].mean():.1f}
Success Rate: {(df['success'].sum()/len(df)*100):.1f}%
        """
        ax7.text(0.1, 0.5, summary_text, fontsize=11,
                verticalalignment='center', family='monospace')

        chart_path = os.path.join(output_dir, "dashboard.png")
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        chart_files.append(chart_path)

        return chart_files


async def main():
    """메인 실행 함수"""

    import argparse

    parser = argparse.ArgumentParser(description="보고서 평가 벤치마크")
    parser.add_argument('--url', default='http://localhost:8000', help='API URL')
    parser.add_argument('--ai-judge', action='store_true', help='AI 심판 활성화 (느림)')
    parser.add_argument('--output', help='결과 저장 경로')
    parser.add_argument('--queries', help='쿼리 텍스트 파일 경로')

    args = parser.parse_args()

    # 벤치마크 실행
    benchmark = ReportEvaluationBenchmark(base_url=args.url, queries_file=args.queries)
    results = await benchmark.run_benchmark(use_ai_judge=args.ai_judge)

    if 'error' in results:
        print(f"❌ 벤치마크 실패: {results['error']}")
        return

    # 요약 출력
    benchmark.print_summary(results['summary'])

    # 결과 저장 (모든 파일 자동 생성)
    saved_files = benchmark.save_results(results, args.output)

    print(f"\n벤치마크 완료!")
    print(f"결과 디렉토리: {args.output if args.output else '/app/evaluation_results/'}")

    return results, saved_files


if __name__ == "__main__":
    asyncio.run(main())
