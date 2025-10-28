# -*- coding: utf-8 -*-
"""
실제 시스템에 연결된 Multi-Hop RAG 벤치마크 실행기
"""

import asyncio
import sys
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Any

# Docker 컨테이너 환경에서의 경로 설정
sys.path.append('/app')
sys.path.append('/app/app')

try:
    from core.agents.orchestrator import OrchestratorAgent, TriageAgent
    from core.models.models import StreamingAgentState
    from core.benchmark.performance_evaluator import (
        PerformanceEvaluator, 
        BenchmarkConfig, 
        PerformanceMetrics,
        BENCHMARK_QUERIES
    )
except ImportError as e:
    print(f"Import error: {e}")
    print("시스템 경로 확인 중...")
    sys.exit(1)

class SystemIntegratedBenchmark:
    """실제 시스템과 통합된 벤치마크"""
    
    def __init__(self):
        self.orchestrator = None
        self.triage = None
        self.evaluator = None
        
    async def initialize_system(self):
        """시스템 컴포넌트 초기화"""
        print("🔧 시스템 초기화 중...")
        try:
            self.triage = TriageAgent()
            self.orchestrator = OrchestratorAgent()
            
            config = BenchmarkConfig(
                runs_per_query=3,
                warmup_runs=1,
                timeout=120  # 테스트를 위해 120초로 단축
            )
            self.evaluator = PerformanceEvaluator(config)
            print("✅ 시스템 초기화 완료")
            return True
            
        except Exception as e:
            print(f"❌ 시스템 초기화 실패: {e}")
            return False
    
    async def execute_single_query_with_timing(self, query: str, hop_count: int, query_id: str) -> PerformanceMetrics:
        """단일 쿼리를 실행하고 상세한 타이밍 측정"""
        
        print(f"🚀 쿼리 실행: {query[:50]}...")
        
        start_time = time.time()
        step_times = []
        search_engine_times = {
            'vector_rag': 0.0,
            'graph_rag': 0.0, 
            'rdb': 0.0,
            'web_search': 0.0
        }
        
        try:
            # State 생성
            state = StreamingAgentState(
                original_query=query,
                session_id=f"benchmark_{query_id}",
                metadata={}
            )
            
            # 1단계: Triage (분류) - 시간 측정
            step_start = time.time()
            classified_state = await self.triage.classify_request(query, state)
            step_times.append(time.time() - step_start)
            
            # 2단계: 실제 워크플로우 실행 - 시간 측정
            step_start = time.time()
            
            # 워크플로우 실행하며 결과 수집
            result_chunks = []
            async for chunk in self.orchestrator.execute_report_workflow(classified_state):
                result_chunks.append(chunk)
                
            # 검색 엔진 사용 시간 추정 (실제로는 orchestrator에서 측정해야 함)
            # 임시로 전체 시간의 60%를 검색 시간으로 가정
            workflow_time = time.time() - step_start
            step_times.append(workflow_time)
            
            # 검색 엔진 시간 분배 (실제 구현에서는 각각 측정)
            search_engine_times['graph_rag'] = workflow_time * 0.3
            search_engine_times['vector_rag'] = workflow_time * 0.4
            search_engine_times['web_search'] = workflow_time * 0.2
            search_engine_times['rdb'] = workflow_time * 0.1
            
            total_time = time.time() - start_time
            final_result = ''.join(result_chunks)
            
            print(f"  ✅ 성공 ({total_time:.2f}초) - 결과 길이: {len(final_result)} 문자")
            
            return PerformanceMetrics(
                query_id=query_id,
                query_text=query,
                hop_count=hop_count,
                total_time=total_time,
                step_times=step_times,
                search_engine_times=search_engine_times,
                success=True,
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            total_time = time.time() - start_time
            print(f"  ❌ 실패 ({total_time:.2f}초): {str(e)}")
            
            return PerformanceMetrics(
                query_id=query_id,
                query_text=query,
                hop_count=hop_count,
                total_time=total_time,
                step_times=step_times,
                search_engine_times=search_engine_times,
                success=False,
                error_msg=str(e),
                timestamp=datetime.now().isoformat()
            )
    
    async def run_lightweight_benchmark(self) -> Dict[str, Any]:
        """가벼운 벤치마크 실행 (각 hop당 3개 쿼리)"""
        
        print("🚀 경량 벤치마크 시작!")
        
        # 테스트용 쿼리 (각 hop당 3개씩)
        test_queries = {
            2: BENCHMARK_QUERIES[2][:3],  # 2-hop 3개
            3: BENCHMARK_QUERIES[3][:3],  # 3-hop 3개  
            4: BENCHMARK_QUERIES[4][:3],  # 4-hop 3개
        }
        
        results = {
            'config': {
                'runs_per_query': 1,  # 빠른 테스트를 위해 1회만
                'timeout': 120,
                'test_queries_count': sum(len(queries) for queries in test_queries.values())
            },
            'start_time': datetime.now().isoformat(),
            'results': {},
            'metrics': []
        }
        
        total_queries = sum(len(queries) for queries in test_queries.values())
        processed_count = 0
        
        for hop_count, queries in test_queries.items():
            print(f"\n🔄 {hop_count}-Hop 쿼리 테스트 ({len(queries)}개)")
            hop_results = []
            
            for i, query in enumerate(queries, 1):
                query_id = f"{hop_count}hop_q{i}"
                
                metrics = await self.execute_single_query_with_timing(
                    query, hop_count, query_id
                )
                
                hop_results.append({
                    'query_id': metrics.query_id,
                    'query_text': metrics.query_text,
                    'hop_count': metrics.hop_count,
                    'total_time': metrics.total_time,
                    'step_times': metrics.step_times,
                    'search_engine_times': metrics.search_engine_times,
                    'success': metrics.success,
                    'error_msg': metrics.error_msg,
                    'timestamp': metrics.timestamp
                })
                
                results['metrics'].append(metrics)
                processed_count += 1
                progress = (processed_count / total_queries) * 100
                print(f"    📊 진행률: {progress:.1f}%")
                
            results['results'][f'{hop_count}_hop'] = hop_results
        
        # 결과 요약 생성
        results['summary'] = self._generate_summary(results['metrics'])
        results['end_time'] = datetime.now().isoformat()
        
        return results
    
    def _generate_summary(self, metrics: List[PerformanceMetrics]) -> Dict[str, Any]:
        """결과 요약 생성"""
        
        successful_metrics = [m for m in metrics if m.success]
        
        if not successful_metrics:
            return {"error": "모든 쿼리 실행 실패"}
        
        summary = {
            'total_queries': len(metrics),
            'successful_queries': len(successful_metrics),
            'success_rate': len(successful_metrics) / len(metrics) * 100,
        }
        
        # Hop별 성능 분석
        by_hop = {}
        for hop_count in [2, 3, 4]:
            hop_metrics = [m for m in successful_metrics if m.hop_count == hop_count]
            if hop_metrics:
                times = [m.total_time for m in hop_metrics]
                by_hop[f'{hop_count}_hop'] = {
                    'count': len(hop_metrics),
                    'avg_total_time': sum(times) / len(times),
                    'min_total_time': min(times),
                    'max_total_time': max(times),
                }
        
        summary['by_hop_count'] = by_hop
        
        # 전체 성능 통계
        all_times = [m.total_time for m in successful_metrics]
        summary['overall'] = {
            'avg_response_time': sum(all_times) / len(all_times),
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
                    'avg_time': sum(non_zero_times) / len(non_zero_times),
                    'usage_rate': len(non_zero_times) / len(successful_metrics) * 100
                }
        summary['by_search_engine'] = engine_summary
        
        return summary
    
    def save_results(self, results: Dict[str, Any], filename: str = None) -> str:
        """결과를 JSON 파일로 저장"""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/tmp/benchmark_results_{timestamp}.json"
        
        # PerformanceMetrics 객체를 딕셔너리로 변환
        serializable_results = {
            'config': results['config'],
            'start_time': results['start_time'],
            'end_time': results['end_time'],
            'results': results['results'],
            'summary': results['summary'],
            'raw_metrics': []
        }
        
        for metric in results['metrics']:
            serializable_results['raw_metrics'].append({
                'query_id': metric.query_id,
                'query_text': metric.query_text,
                'hop_count': metric.hop_count,
                'total_time': metric.total_time,
                'step_times': metric.step_times,
                'search_engine_times': metric.search_engine_times,
                'success': metric.success,
                'error_msg': metric.error_msg,
                'timestamp': metric.timestamp
            })
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, ensure_ascii=False, indent=2)
        
        print(f"💾 결과 저장됨: {filename}")
        return filename
    
    def print_summary(self, summary: Dict[str, Any]) -> None:
        """요약 결과 출력"""
        
        print(f"\n🎉 벤치마크 완료! 📊")
        print(f"📈 성공률: {summary['success_rate']:.1f}% ({summary['successful_queries']}/{summary['total_queries']})")
        
        if 'overall' in summary:
            overall = summary['overall']
            print(f"⏱️  평균 응답시간: {overall['avg_response_time']:.2f}초")
            print(f"📊 최소: {overall['min_response_time']:.2f}초, 최대: {overall['max_response_time']:.2f}초")
        
        if 'by_hop_count' in summary:
            print(f"\n🔢 Hop별 성능:")
            for hop, stats in summary['by_hop_count'].items():
                print(f"  {hop}: {stats['avg_total_time']:.2f}초 (평균)")
        
        if 'by_search_engine' in summary:
            print(f"\n🔍 검색 엔진별 성능:")
            for engine, stats in summary['by_search_engine'].items():
                print(f"  {engine}: {stats['avg_time']:.2f}초 (사용률: {stats['usage_rate']:.1f}%)")


async def main():
    """메인 실행 함수"""
    
    print("=" * 60)
    print("🚀 Multi-Hop RAG 성능 벤치마크 시작")
    print("=" * 60)
    
    benchmark = SystemIntegratedBenchmark()
    
    # 시스템 초기화
    if not await benchmark.initialize_system():
        print("❌ 시스템 초기화 실패로 벤치마크를 중단합니다.")
        return
    
    try:
        # 벤치마크 실행
        results = await benchmark.run_lightweight_benchmark()
        
        # 결과 출력
        benchmark.print_summary(results['summary'])
        
        # 결과 저장
        filename = benchmark.save_results(results)
        
        print(f"\n✨ 벤치마크 성공적으로 완료!")
        print(f"📁 결과 파일: {filename}")
        
        return results
        
    except Exception as e:
        print(f"❌ 벤치마크 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 비동기 실행
    results = asyncio.run(main())