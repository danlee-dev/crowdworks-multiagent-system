# -*- coding: utf-8 -*-
"""
Multi-Hop RAG 시스템 성능 평가 도구
- 처리 속도 측정
- 병렬 vs 순차 처리 비교  
- Baseline 시스템과의 성능 비교
"""

import time
import asyncio
import json
import statistics
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

@dataclass
class PerformanceMetrics:
    """성능 측정 지표"""
    query_id: str
    query_text: str
    hop_count: int
    total_time: float
    step_times: List[float]
    search_engine_times: Dict[str, float]  # vector_rag, graph_rag, rdb, web_search
    parallel_time: Optional[float] = None
    sequential_time: Optional[float] = None
    precheck_time: Optional[float] = None
    success: bool = True
    error_msg: Optional[str] = None
    timestamp: str = ""

@dataclass
class BenchmarkConfig:
    """벤치마크 설정"""
    runs_per_query: int = 5  # 각 쿼리당 실행 횟수
    warmup_runs: int = 2     # 워밍업 실행 횟수
    timeout: int = 300       # 타임아웃 (초)
    parallel_enabled: bool = True
    precheck_enabled: bool = True

class PerformanceEvaluator:
    """Multi-Hop RAG 성능 평가기"""
    
    def __init__(self, config: BenchmarkConfig = None):
        self.config = config or BenchmarkConfig()
        self.metrics: List[PerformanceMetrics] = []
        
    async def evaluate_query_performance(self, 
                                       query_text: str,
                                       hop_count: int,
                                       orchestrator_agent,
                                       query_id: str = None) -> PerformanceMetrics:
        """단일 쿼리의 성능을 평가"""
        
        if query_id is None:
            query_id = f"q_{int(time.time() * 1000)}"
            
        # 워밍업 실행
        for _ in range(self.config.warmup_runs):
            try:
                await self._execute_query_with_timeout(query_text, orchestrator_agent)
            except Exception:
                pass  # 워밍업 에러는 무시
                
        # 실제 측정
        run_results = []
        
        for run_idx in range(self.config.runs_per_query):
            try:
                result = await self._measure_single_run(
                    query_text, hop_count, orchestrator_agent, f"{query_id}_run_{run_idx}"
                )
                run_results.append(result)
            except Exception as e:
                # 실패한 실행도 기록
                failed_result = PerformanceMetrics(
                    query_id=f"{query_id}_run_{run_idx}",
                    query_text=query_text,
                    hop_count=hop_count,
                    total_time=0.0,
                    step_times=[],
                    search_engine_times={},
                    success=False,
                    error_msg=str(e),
                    timestamp=datetime.now().isoformat()
                )
                run_results.append(failed_result)
        
        # 성공한 실행들의 평균 계산
        successful_runs = [r for r in run_results if r.success]
        
        if not successful_runs:
            return run_results[0]  # 모두 실패했다면 첫 번째 실패 결과 반환
            
        # 평균 성능 지표 계산
        avg_metrics = self._calculate_average_metrics(successful_runs, query_id, query_text, hop_count)
        self.metrics.append(avg_metrics)
        
        return avg_metrics
    
    async def _measure_single_run(self, query_text: str, hop_count: int, 
                                orchestrator_agent, query_id: str) -> PerformanceMetrics:
        """단일 실행의 성능 측정"""
        
        start_time = time.time()
        step_times = []
        search_engine_times = {
            'vector_rag': 0.0,
            'graph_rag': 0.0, 
            'rdb': 0.0,
            'web_search': 0.0
        }
        
        # 프리체크 시간 측정
        precheck_start = time.time()
        precheck_time = time.time() - precheck_start
        
        try:
            # 실제 쿼리 실행 (시간 측정이 포함된 버전 필요)
            result = await self._execute_query_with_profiling(
                query_text, orchestrator_agent, step_times, search_engine_times
            )
            
            total_time = time.time() - start_time
            
            return PerformanceMetrics(
                query_id=query_id,
                query_text=query_text,
                hop_count=hop_count,
                total_time=total_time,
                step_times=step_times,
                search_engine_times=search_engine_times,
                precheck_time=precheck_time,
                success=True,
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            total_time = time.time() - start_time
            return PerformanceMetrics(
                query_id=query_id,
                query_text=query_text,
                hop_count=hop_count,
                total_time=total_time,
                step_times=step_times,
                search_engine_times=search_engine_times,
                success=False,
                error_msg=str(e),
                timestamp=datetime.now().isoformat()
            )
    
    async def _execute_query_with_profiling(self, query_text: str, orchestrator_agent,
                                          step_times: List[float], 
                                          search_engine_times: Dict[str, float]) -> Any:
        """프로파일링이 포함된 쿼리 실행"""
        
        # 여기서 실제 orchestrator_agent 호출
        # 각 검색 엔진별 시간을 측정하는 로직 필요
        
        # 임시 구현 - 실제로는 orchestrator의 각 단계별 시간을 측정해야 함
        step_start = time.time()
        
        # 실제 쿼리 실행 로직은 orchestrator_agent에 따라 구현
        # 예시: await orchestrator_agent.execute_query(query_text)
        
        step_time = time.time() - step_start
        step_times.append(step_time)
        
        return "query_result"  # 실제 결과 반환
    
    async def _execute_query_with_timeout(self, query_text: str, orchestrator_agent) -> Any:
        """타임아웃이 적용된 쿼리 실행"""
        try:
            return await asyncio.wait_for(
                orchestrator_agent.execute_query(query_text),
                timeout=self.config.timeout
            )
        except asyncio.TimeoutError:
            raise Exception(f"Query timeout after {self.config.timeout} seconds")
    
    def _calculate_average_metrics(self, successful_runs: List[PerformanceMetrics],
                                 query_id: str, query_text: str, hop_count: int) -> PerformanceMetrics:
        """성공한 실행들의 평균 지표 계산"""
        
        avg_total_time = statistics.mean([r.total_time for r in successful_runs])
        
        # 단계별 시간 평균
        max_steps = max(len(r.step_times) for r in successful_runs) if successful_runs else 0
        avg_step_times = []
        
        for step_idx in range(max_steps):
            step_times_for_idx = [
                r.step_times[step_idx] for r in successful_runs 
                if len(r.step_times) > step_idx
            ]
            if step_times_for_idx:
                avg_step_times.append(statistics.mean(step_times_for_idx))
        
        # 검색 엔진별 시간 평균
        avg_search_times = {}
        for engine in ['vector_rag', 'graph_rag', 'rdb', 'web_search']:
            engine_times = [r.search_engine_times.get(engine, 0.0) for r in successful_runs]
            avg_search_times[engine] = statistics.mean(engine_times) if engine_times else 0.0
        
        # 프리체크 시간 평균
        precheck_times = [r.precheck_time for r in successful_runs if r.precheck_time is not None]
        avg_precheck_time = statistics.mean(precheck_times) if precheck_times else None
        
        return PerformanceMetrics(
            query_id=query_id,
            query_text=query_text,
            hop_count=hop_count,
            total_time=avg_total_time,
            step_times=avg_step_times,
            search_engine_times=avg_search_times,
            precheck_time=avg_precheck_time,
            success=True,
            timestamp=datetime.now().isoformat()
        )
    
    async def run_benchmark_suite(self, test_queries: Dict[int, List[str]], 
                                orchestrator_agent) -> Dict[str, Any]:
        """전체 벤치마크 스위트 실행"""
        
        print(f"🚀 Multi-Hop RAG 벤치마크 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        print(f"📊 설정: 쿼리당 {self.config.runs_per_query}회 실행, 워밍업 {self.config.warmup_runs}회")
        
        benchmark_results = {
            'config': asdict(self.config),
            'start_time': datetime.now().isoformat(),
            'results': {},
            'summary': {}
        }
        
        total_queries = sum(len(queries) for queries in test_queries.values())
        processed_count = 0
        
        for hop_count, queries in test_queries.items():
            print(f"\n🔄 {hop_count}-Hop 쿼리 평가 시작 ({len(queries)}개)")
            hop_results = []
            
            for i, query in enumerate(queries, 1):
                print(f"  [{i}/{len(queries)}] 처리 중: {query[:50]}...")
                
                try:
                    metrics = await self.evaluate_query_performance(
                        query_text=query,
                        hop_count=hop_count,
                        orchestrator_agent=orchestrator_agent,
                        query_id=f"{hop_count}hop_q{i}"
                    )
                    hop_results.append(asdict(metrics))
                    
                    processed_count += 1
                    progress = (processed_count / total_queries) * 100
                    print(f"    ✅ 완료 ({progress:.1f}%) - {metrics.total_time:.2f}초")
                    
                except Exception as e:
                    print(f"    ❌ 실패: {str(e)}")
                    processed_count += 1
            
            benchmark_results['results'][f'{hop_count}_hop'] = hop_results
        
        # 결과 요약 계산
        benchmark_results['summary'] = self._generate_summary()
        benchmark_results['end_time'] = datetime.now().isoformat()
        
        print(f"\n🎉 벤치마크 완료! 결과 요약:")
        self._print_summary(benchmark_results['summary'])
        
        return benchmark_results
    
    def _generate_summary(self) -> Dict[str, Any]:
        """벤치마크 결과 요약 생성"""
        
        if not self.metrics:
            return {"error": "No successful measurements"}
        
        successful_metrics = [m for m in self.metrics if m.success]
        
        summary = {
            'total_queries': len(self.metrics),
            'successful_queries': len(successful_metrics),
            'success_rate': len(successful_metrics) / len(self.metrics) * 100,
        }
        
        if successful_metrics:
            # Hop별 성능 분석
            by_hop = {}
            for hop_count in [2, 3, 4]:
                hop_metrics = [m for m in successful_metrics if m.hop_count == hop_count]
                if hop_metrics:
                    by_hop[f'{hop_count}_hop'] = {
                        'count': len(hop_metrics),
                        'avg_total_time': statistics.mean([m.total_time for m in hop_metrics]),
                        'min_total_time': min([m.total_time for m in hop_metrics]),
                        'max_total_time': max([m.total_time for m in hop_metrics]),
                        'std_total_time': statistics.stdev([m.total_time for m in hop_metrics]) if len(hop_metrics) > 1 else 0
                    }
            
            summary['by_hop_count'] = by_hop
            
            # 전체 성능 통계
            all_times = [m.total_time for m in successful_metrics]
            summary['overall'] = {
                'avg_response_time': statistics.mean(all_times),
                'median_response_time': statistics.median(all_times),
                'p95_response_time': sorted(all_times)[int(len(all_times) * 0.95)] if len(all_times) > 1 else all_times[0],
                'min_response_time': min(all_times),
                'max_response_time': max(all_times)
            }
            
            # 검색 엔진별 성능
            engine_summary = {}
            for engine in ['vector_rag', 'graph_rag', 'rdb', 'web_search']:
                engine_times = [m.search_engine_times.get(engine, 0.0) for m in successful_metrics]
                non_zero_times = [t for t in engine_times if t > 0]
                if non_zero_times:
                    engine_summary[engine] = {
                        'avg_time': statistics.mean(non_zero_times),
                        'usage_rate': len(non_zero_times) / len(successful_metrics) * 100
                    }
            summary['by_search_engine'] = engine_summary
            
        return summary
    
    def _print_summary(self, summary: Dict[str, Any]) -> None:
        """요약 결과를 콘솔에 출력"""
        
        print(f"📈 성공률: {summary['success_rate']:.1f}% ({summary['successful_queries']}/{summary['total_queries']})")
        
        if 'overall' in summary:
            overall = summary['overall']
            print(f"⏱️  평균 응답시간: {overall['avg_response_time']:.2f}초")
            print(f"📊 중앙값: {overall['median_response_time']:.2f}초, P95: {overall['p95_response_time']:.2f}초")
        
        if 'by_hop_count' in summary:
            print("\n🔢 Hop별 성능:")
            for hop, stats in summary['by_hop_count'].items():
                print(f"  {hop}: {stats['avg_total_time']:.2f}초 (±{stats['std_total_time']:.2f})")
    
    def save_results(self, results: Dict[str, Any], filename: str = None) -> str:
        """결과를 JSON 파일로 저장"""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_results_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"💾 결과 저장됨: {filename}")
        return filename
    
    def export_to_csv(self, filename: str = None) -> str:
        """결과를 CSV로 내보내기"""
        
        if not self.metrics:
            raise ValueError("No metrics to export")
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  
            filename = f"benchmark_metrics_{timestamp}.csv"
        
        # DataFrame으로 변환
        df_data = []
        for m in self.metrics:
            row = {
                'query_id': m.query_id,
                'query_text': m.query_text,
                'hop_count': m.hop_count,
                'total_time': m.total_time,
                'success': m.success,
                'precheck_time': m.precheck_time,
                'timestamp': m.timestamp
            }
            
            # 검색 엔진별 시간 추가
            for engine, time_val in m.search_engine_times.items():
                row[f'{engine}_time'] = time_val
            
            # 단계별 시간 추가 (최대 10단계까지)
            for i, step_time in enumerate(m.step_times[:10]):
                row[f'step_{i+1}_time'] = step_time
                
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        
        print(f"📊 CSV 내보내기 완료: {filename}")
        return filename


# 사용 예시 및 테스트 쿼리 정의
BENCHMARK_QUERIES = {
    2: [
        "제주도 감귤의 주요 수출국은?",
        "강원도 감자의 영양성분은?", 
        "한우의 대체 단백질 식품은?",
        "유기농 쌀의 평균 가격은?",
        "김치에 포함된 주요 비타민은?"
    ],
    3: [
        "폭염 피해를 받은 지역의 주요 농산물 가격은?",
        "유기농 인증을 받은 제주도 농산물의 수출현황은?", 
        "비타민C가 풍부한 과일의 주요 생산지는?",
        "가뭄 피해지역의 곡물 생산량 변화는?",
        "수출 증가율이 높은 한국 농산물의 특징은?"
    ],
    4: [
        "집중호우 피해지역의 주요 농산물에 포함된 영양성분과 유사한 대체 식품은?",
        "수출이 증가한 한국 농산물의 생산지역별 토양 특성은?",
        "기후변화로 영향받은 작물의 영양성분 변화와 건강 영향은?",
        "유기농 인증 농산물의 지역별 생산현황과 소비자 선호도는?",
        "한국 전통 발효식품의 해외 수출 현황과 현지 적응 전략은?"
    ]
}


# 비동기 실행을 위한 메인 함수
async def main():
    """벤치마크 실행 예시"""
    
    config = BenchmarkConfig(
        runs_per_query=3,
        warmup_runs=1,
        timeout=180
    )
    
    evaluator = PerformanceEvaluator(config)
    
    # 실제 사용 시에는 orchestrator_agent 인스턴스를 전달
    # orchestrator_agent = YourOrchestratorAgent()
    
    # results = await evaluator.run_benchmark_suite(BENCHMARK_QUERIES, orchestrator_agent)
    # evaluator.save_results(results)
    # evaluator.export_to_csv()
    
    print("벤치마크 도구 준비 완료!")


if __name__ == "__main__":
    asyncio.run(main())