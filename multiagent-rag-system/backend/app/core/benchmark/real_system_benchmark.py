# -*- coding: utf-8 -*-
"""
실제 시스템 성능 측정 도구
HTTP API를 통해 실제 Multi-Hop RAG 시스템의 성능을 측정
"""

import asyncio
import aiohttp
import time
import json
import statistics
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass
class RealPerformanceMetrics:
    """실제 시스템 성능 측정 결과"""
    query_id: str
    query_text: str
    hop_count: int
    total_time: float
    response_time: float  # HTTP 응답 시간
    content_length: int
    search_tools_used: List[str]
    sources_found: int
    success: bool = True
    error_msg: Optional[str] = None
    timestamp: str = ""
    session_id: str = ""

class RealSystemBenchmark:
    """실제 시스템 HTTP API를 통한 성능 벤치마크"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[RealPerformanceMetrics] = []
        
        # Multi-Hop 테스트 쿼리
        self.test_queries = {
            2: [
                "제주도 감귤의 주요 수출국은?",
                "강원도 감자의 영양성분은?", 
                "한우의 대체 단백질 식품은?",
                "김치에 포함된 주요 비타민은?",
                "유기농 쌀의 평균 가격은?"
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

    async def test_single_query(self, session: aiohttp.ClientSession, 
                               query: str, hop_count: int, query_id: str) -> RealPerformanceMetrics:
        """단일 쿼리를 실제 시스템에서 테스트"""
        
        print(f"  🚀 테스트 중: {query[:50]}...")
        
        start_time = time.time()
        session_id = f"benchmark_{query_id}_{int(time.time())}"
        
        # API 요청 준비
        payload = {
            "query": query,
            "conversation_id": session_id
        }
        
        search_tools_used = []
        sources_found = 0
        content_chunks = []
        
        try:
            # 실제 API 호출
            async with session.post(
                f"{self.base_url}/query/stream",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)  # 2분 타임아웃
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")
                
                # 스트리밍 응답 처리
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    
                    if line.startswith('data: '):
                        try:
                            data = json.loads(line[6:])  # 'data: ' 제거
                            
                            # 검색 도구 사용 추적
                            if data.get('type') == 'search_results':
                                tool_name = data.get('tool_name', '')
                                if tool_name and tool_name not in search_tools_used:
                                    search_tools_used.append(tool_name)
                                
                                results = data.get('results', [])
                                sources_found += len(results)
                            
                            # 콘텐츠 수집
                            elif data.get('type') == 'content':
                                chunk = data.get('chunk', '')
                                content_chunks.append(chunk)
                                
                            elif data.get('type') == 'final_complete':
                                break
                                
                        except json.JSONDecodeError:
                            continue  # JSON이 아닌 라인은 무시
                
                response_time = time.time() - start_time
                final_content = ''.join(content_chunks)
                
                print(f"    ✅ 성공 ({response_time:.2f}초) - 도구: {search_tools_used}, 소스: {sources_found}개")
                
                return RealPerformanceMetrics(
                    query_id=query_id,
                    query_text=query,
                    hop_count=hop_count,
                    total_time=response_time,
                    response_time=response_time,
                    content_length=len(final_content),
                    search_tools_used=search_tools_used,
                    sources_found=sources_found,
                    success=True,
                    session_id=session_id,
                    timestamp=datetime.now().isoformat()
                )
                
        except Exception as e:
            response_time = time.time() - start_time
            print(f"    ❌ 실패 ({response_time:.2f}초): {str(e)}")
            
            return RealPerformanceMetrics(
                query_id=query_id,
                query_text=query,
                hop_count=hop_count,
                total_time=response_time,
                response_time=response_time,
                content_length=0,
                search_tools_used=search_tools_used,
                sources_found=sources_found,
                success=False,
                error_msg=str(e),
                session_id=session_id,
                timestamp=datetime.now().isoformat()
            )

    async def run_benchmark(self) -> Dict[str, Any]:
        """전체 벤치마크 실행"""
        
        print("🚀 실제 Multi-Hop RAG 시스템 성능 벤치마크 시작")
        print(f"🌐 대상 시스템: {self.base_url}")
        print(f"📊 총 {sum(len(queries) for queries in self.test_queries.values())}개 쿼리 테스트\n")
        
        # 시스템 상태 확인
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        health_data = await response.json()
                        print(f"✅ 시스템 상태: {health_data.get('status', 'unknown')}")
                    else:
                        print(f"⚠️ 시스템 응답: HTTP {response.status}")
            except Exception as e:
                print(f"❌ 시스템 연결 실패: {e}")
                return {"error": "시스템 연결 불가"}
        
        results = {
            'config': {
                'target_system': self.base_url,
                'total_queries': sum(len(queries) for queries in self.test_queries.values()),
                'queries_per_hop': {str(hop): len(queries) for hop, queries in self.test_queries.items()}
            },
            'start_time': datetime.now().isoformat(),
            'results': {},
            'raw_metrics': []
        }
        
        # HTTP 세션 생성하여 연결 재사용
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=10, limit_per_host=5)
        ) as session:
            
            for hop_count, queries in self.test_queries.items():
                print(f"🔄 {hop_count}-Hop 쿼리 테스트 ({len(queries)}개)")
                hop_results = []
                
                for i, query in enumerate(queries, 1):
                    query_id = f"{hop_count}hop_q{i:02d}"
                    
                    # 개별 쿼리 테스트
                    metrics = await self.test_single_query(session, query, hop_count, query_id)
                    hop_results.append(self._metrics_to_dict(metrics))
                    self.results.append(metrics)
                    
                    # 쿼리 간 간격 (시스템 부하 방지)
                    await asyncio.sleep(1)
                
                results['results'][f'{hop_count}_hop'] = hop_results
                print()  # 빈 줄 추가
        
        # 결과 요약 생성
        results['summary'] = self._generate_summary()
        results['raw_metrics'] = [self._metrics_to_dict(m) for m in self.results]
        results['end_time'] = datetime.now().isoformat()
        
        return results
    
    def _metrics_to_dict(self, metrics: RealPerformanceMetrics) -> Dict[str, Any]:
        """메트릭스를 딕셔너리로 변환"""
        return {
            'query_id': metrics.query_id,
            'query_text': metrics.query_text,
            'hop_count': metrics.hop_count,
            'total_time': round(metrics.total_time, 3),
            'response_time': round(metrics.response_time, 3),
            'content_length': metrics.content_length,
            'search_tools_used': metrics.search_tools_used,
            'sources_found': metrics.sources_found,
            'success': metrics.success,
            'error_msg': metrics.error_msg,
            'session_id': metrics.session_id,
            'timestamp': metrics.timestamp
        }
    
    def _generate_summary(self) -> Dict[str, Any]:
        """벤치마크 결과 요약 생성"""
        
        successful_metrics = [m for m in self.results if m.success]
        
        summary = {
            'total_queries': len(self.results),
            'successful_queries': len(successful_metrics),
            'success_rate': len(successful_metrics) / len(self.results) * 100 if self.results else 0,
        }
        
        if successful_metrics:
            # Hop별 성능 분석
            by_hop = {}
            for hop_count in [2, 3, 4]:
                hop_metrics = [m for m in successful_metrics if m.hop_count == hop_count]
                if hop_metrics:
                    times = [m.total_time for m in hop_metrics]
                    sources = [m.sources_found for m in hop_metrics]
                    content_lengths = [m.content_length for m in hop_metrics]
                    
                    by_hop[f'{hop_count}_hop'] = {
                        'count': len(hop_metrics),
                        'avg_response_time': statistics.mean(times),
                        'min_response_time': min(times),
                        'max_response_time': max(times),
                        'median_response_time': statistics.median(times),
                        'std_response_time': statistics.stdev(times) if len(times) > 1 else 0,
                        'avg_sources_found': statistics.mean(sources),
                        'avg_content_length': statistics.mean(content_lengths),
                        'total_time': sum(times)
                    }
            
            summary['by_hop_count'] = by_hop
            
            # 전체 성능 통계
            all_times = [m.total_time for m in successful_metrics]
            all_sources = [m.sources_found for m in successful_metrics]
            all_content_lengths = [m.content_length for m in successful_metrics]
            
            summary['overall'] = {
                'avg_response_time': statistics.mean(all_times),
                'median_response_time': statistics.median(all_times),
                'min_response_time': min(all_times),
                'max_response_time': max(all_times),
                'std_response_time': statistics.stdev(all_times) if len(all_times) > 1 else 0,
                'total_test_time': sum(all_times),
                'avg_sources_per_query': statistics.mean(all_sources),
                'avg_content_length': statistics.mean(all_content_lengths)
            }
            
            # 검색 도구 사용 빈도 분석
            all_tools = []
            for m in successful_metrics:
                all_tools.extend(m.search_tools_used)
            
            tool_frequency = {}
            for tool in all_tools:
                tool_frequency[tool] = tool_frequency.get(tool, 0) + 1
            
            summary['search_tools_usage'] = {
                'frequency': tool_frequency,
                'unique_tools': list(set(all_tools)),
                'avg_tools_per_query': len(all_tools) / len(successful_metrics) if successful_metrics else 0
            }
            
            # 성능 분류
            fast_queries = [m for m in successful_metrics if m.total_time < 3.0]
            medium_queries = [m for m in successful_metrics if 3.0 <= m.total_time < 8.0]
            slow_queries = [m for m in successful_metrics if m.total_time >= 8.0]
            
            summary['performance_distribution'] = {
                'fast_queries': {'count': len(fast_queries), 'percentage': len(fast_queries) / len(successful_metrics) * 100},
                'medium_queries': {'count': len(medium_queries), 'percentage': len(medium_queries) / len(successful_metrics) * 100},
                'slow_queries': {'count': len(slow_queries), 'percentage': len(slow_queries) / len(successful_metrics) * 100}
            }
            
        return summary
    
    def print_detailed_summary(self, summary: Dict[str, Any]) -> None:
        """상세 요약 결과 출력"""
        
        print("\n" + "="*80)
        print("🎉 실제 Multi-Hop RAG 시스템 성능 벤치마크 결과")
        print("="*80)
        
        print(f"📊 전체 성공률: {summary['success_rate']:.1f}% ({summary['successful_queries']}/{summary['total_queries']})")
        
        if 'overall' in summary:
            overall = summary['overall']
            print(f"\n⚡ 전체 성능 지표:")
            print(f"   • 평균 응답시간: {overall['avg_response_time']:.2f}초")
            print(f"   • 중앙값: {overall['median_response_time']:.2f}초")
            print(f"   • 최소/최대: {overall['min_response_time']:.2f}초 / {overall['max_response_time']:.2f}초")
            print(f"   • 표준편차: {overall['std_response_time']:.2f}초")
            print(f"   • 평균 소스 개수: {overall['avg_sources_per_query']:.1f}개")
            print(f"   • 평균 응답 길이: {overall['avg_content_length']:.0f}자")
        
        if 'by_hop_count' in summary:
            print(f"\n🔢 Hop별 상세 성능:")
            for hop, stats in summary['by_hop_count'].items():
                print(f"   📋 {hop}:")
                print(f"      - 평균 시간: {stats['avg_response_time']:.2f}초 (±{stats['std_response_time']:.2f})")
                print(f"      - 중앙값: {stats['median_response_time']:.2f}초")
                print(f"      - 범위: {stats['min_response_time']:.2f}~{stats['max_response_time']:.2f}초")
                print(f"      - 평균 소스: {stats['avg_sources_found']:.1f}개")
        
        if 'search_tools_usage' in summary:
            tools_usage = summary['search_tools_usage']
            print(f"\n🔍 검색 도구 사용 현황:")
            print(f"   • 사용된 도구: {', '.join(tools_usage['unique_tools'])}")
            print(f"   • 쿼리당 평균 도구 수: {tools_usage['avg_tools_per_query']:.1f}개")
            print(f"   • 도구별 사용 빈도:")
            for tool, count in tools_usage['frequency'].items():
                print(f"     - {tool}: {count}회")
        
        if 'performance_distribution' in summary:
            perf_dist = summary['performance_distribution']
            print(f"\n📈 성능 분포:")
            print(f"   • 빠름 (<3초): {perf_dist['fast_queries']['count']}개 ({perf_dist['fast_queries']['percentage']:.1f}%)")
            print(f"   • 보통 (3-8초): {perf_dist['medium_queries']['count']}개 ({perf_dist['medium_queries']['percentage']:.1f}%)")
            print(f"   • 느림 (>8초): {perf_dist['slow_queries']['count']}개 ({perf_dist['slow_queries']['percentage']:.1f}%)")
    
    def save_results(self, results: Dict[str, Any], filename: str = None) -> str:
        """결과를 JSON 파일로 저장"""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/tmp/real_multihop_benchmark_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"💾 벤치마크 결과 저장: {filename}")
        return filename


async def main():
    """메인 실행 함수"""
    
    print("🚀 실제 Multi-Hop RAG 시스템 성능 측정 시작")
    print("📝 HTTP API를 통해 실제 시스템 성능을 측정합니다\n")
    
    # 벤치마크 실행
    benchmark = RealSystemBenchmark()
    results = await benchmark.run_benchmark()
    
    if 'error' in results:
        print(f"❌ 벤치마크 실행 실패: {results['error']}")
        return
    
    # 상세 요약 출력
    benchmark.print_detailed_summary(results['summary'])
    
    # 결과 저장
    filename = benchmark.save_results(results)
    
    print(f"\n✨ 실제 시스템 벤치마크 완료!")
    print(f"📁 결과 파일: {filename}")
    print(f"\n📈 이 실제 데이터를 논문에 활용하여 Multi-Hop RAG 시스템의 성능을 입증할 수 있습니다.")
    
    return results, filename


if __name__ == "__main__":
    results, filename = asyncio.run(main())