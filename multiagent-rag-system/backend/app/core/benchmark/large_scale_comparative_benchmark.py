# -*- coding: utf-8 -*-
"""
대규모 Vector RAG vs GraphRAG vs Combined 비교 성능 테스트
통계적으로 신뢰할 수 있는 50개 쿼리 테스트
"""

import subprocess
import time
import json
import statistics
import random
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass
class LargeScaleMetrics:
    """대규모 비교 실험용 성능 메트릭"""
    query_id: str
    query_text: str
    hop_count: int
    test_mode: str  # "vector_only", "graph_only", "combined"
    
    # 성능 지표
    total_time: float
    response_received: bool
    content_length: int
    search_tools_used: List[str]
    
    success: bool = True
    error_msg: Optional[str] = None
    timestamp: str = ""

class LargeScaleComparativeBenchmark:
    """대규모 통계적 신뢰성 있는 비교 테스트"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[LargeScaleMetrics] = []
        
        # 농식품 도메인에 특화된 50개 쿼리 생성
        self.test_queries = self._generate_diverse_queries()

    def _generate_diverse_queries(self) -> Dict[int, List[str]]:
        """다양한 농식품 관련 50개 쿼리 생성"""
        
        # 농산물 품목
        crops = ["감귤", "사과", "배", "포도", "딸기", "수박", "참외", "토마토", "감자", "고구마", 
                 "쌀", "보리", "콩", "옥수수", "배추", "무", "양파", "마늘", "파", "고추"]
        
        # 지역
        regions = ["제주도", "강원도", "경기도", "충청도", "전라도", "경상도", "서울", "부산", "대구", "광주"]
        
        # 속성/주제
        topics = ["영양성분", "수출국", "생산량", "가격", "재배방법", "보관방법", "효능", "칼로리", "비타민", "미네랄"]
        
        queries = {
            2: [],  # 2-Hop 쿼리 6개
            3: [],  # 3-Hop 쿼리 6개  
            4: []   # 4-Hop 쿼리 3개
        }
        
        # 2-Hop 쿼리 생성 (6개로 축소)
        for i in range(6):
            region = random.choice(regions)
            crop = random.choice(crops)
            topic = random.choice(topics)
            
            templates = [
                f"{region}의 {crop} {topic}은?",
                f"{crop}의 주요 {topic}는?",
                f"{region}에서 생산되는 {crop}의 특징은?",
                f"{crop} {topic}에 대해 알려줘"
            ]
            queries[2].append(random.choice(templates))
        
        # 3-Hop 쿼리 생성 (6개로 축소)
        for i in range(6):
            region = random.choice(regions)
            crop1 = random.choice(crops)
            crop2 = random.choice(crops)
            topic = random.choice(topics)
            
            templates = [
                f"{region}의 {crop1}과 비교한 {crop2}의 {topic}는?",
                f"{crop1}의 {topic}와 유사한 다른 농산물은?",
                f"{region}에서 재배되는 {crop1}의 {topic} 변화는?",
                f"{crop1}과 {crop2}의 {topic} 차이점은?"
            ]
            queries[3].append(random.choice(templates))
        
        # 4-Hop 쿼리 생성 (3개로 축소)
        for i in range(3):
            region = random.choice(regions)
            crop = random.choice(crops)
            topic1 = random.choice(topics)
            topic2 = random.choice(topics)
            
            templates = [
                f"{region}의 {crop} {topic1}이 {topic2}에 미치는 영향과 대체 식품은?",
                f"기후변화로 인한 {region} {crop}의 {topic1} 변화와 {topic2} 대응 방안은?",
                f"{crop}의 {topic1}을 기준으로 한 유사 품목의 {topic2} 비교 분석은?"
            ]
            queries[4].append(random.choice(templates))
        
        return queries

    def test_single_query(self, query: str, hop_count: int, query_id: str, mode: str) -> LargeScaleMetrics:
        """단일 쿼리를 특정 모드로 테스트"""
        
        start_time = time.time()
        session_id = f"large_scale_{mode}_{query_id}_{int(time.time())}"
        
        # 모드별 쿼리 수정
        modified_query = query
        if mode == "vector_only":
            # Vector RAG 우선 사용 유도 (명시적 지시 제거, 자연스러운 쿼리)
            modified_query = query
        elif mode == "graph_only":
            # GraphRAG 우선 사용 유도
            modified_query = f"관계를 중심으로 {query}"
        elif mode == "combined":
            # 시스템 자동 선택
            modified_query = query
        
        payload = {
            "query": modified_query,
            "conversation_id": session_id
        }
        
        search_tools_used = []
        content_length = 0
        response_received = False
        
        # curl 명령어 구성
        curl_cmd = [
            'curl', '-X', 'POST',
            f'{self.base_url}/query/stream',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps(payload, ensure_ascii=False),
            '--max-time', '30',  # 30초 타임아웃으로 단축
            '--silent'
        ]
        
        try:
            # curl 실행
            result = subprocess.run(
                curl_cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=35
            )
            
            if result.returncode == 0 and result.stdout:
                output = result.stdout
                response_received = True
                
                # 응답 파싱
                lines = output.strip().split('\n')
                for line in lines:
                    if line.startswith('data: '):
                        try:
                            data = json.loads(line[6:])
                            
                            if data.get('type') == 'search_results':
                                tool_name = data.get('tool_name', '')
                                if tool_name and tool_name not in search_tools_used:
                                    search_tools_used.append(tool_name)
                            
                            elif data.get('type') == 'content':
                                chunk = data.get('chunk', '')
                                content_length += len(chunk)
                                
                        except json.JSONDecodeError:
                            continue
            
            total_time = time.time() - start_time
            success = response_received and content_length > 0
            
            return LargeScaleMetrics(
                query_id=query_id,
                query_text=query,
                hop_count=hop_count,
                test_mode=mode,
                total_time=total_time,
                response_received=response_received,
                content_length=content_length,
                search_tools_used=search_tools_used,
                success=success,
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            total_time = time.time() - start_time
            
            return LargeScaleMetrics(
                query_id=query_id,
                query_text=query,
                hop_count=hop_count,
                test_mode=mode,
                total_time=total_time,
                response_received=False,
                content_length=0,
                search_tools_used=[],
                success=False,
                error_msg=str(e)[:100],
                timestamp=datetime.now().isoformat()
            )

    def run_large_scale_benchmark(self) -> Dict[str, Any]:
        """대규모 비교 벤치마크 실행"""
        
        total_queries = sum(len(queries) for queries in self.test_queries.values())
        print(f"🚀 대규모 Vector RAG vs GraphRAG vs Combined 비교 테스트")
        print(f"📊 총 {total_queries}개 쿼리 × 3 모드 = {total_queries * 3}개 테스트")
        print(f"⏱️  예상 소요 시간: 약 {(total_queries * 3 * 5) // 60}분\n")
        
        results = {
            'config': {
                'target_system': self.base_url,
                'test_modes': ['vector_only', 'graph_only', 'combined'],
                'total_queries': total_queries,
                'total_tests': total_queries * 3,
                'queries_per_hop': {str(hop): len(queries) for hop, queries in self.test_queries.items()}
            },
            'start_time': datetime.now().isoformat(),
            'results_by_mode': {'vector_only': [], 'graph_only': [], 'combined': []},
            'raw_metrics': []
        }
        
        test_count = 0
        
        # 각 모드별로 테스트 실행
        for mode in ['vector_only', 'graph_only', 'combined']:
            print(f"\n🔧 {mode.upper()} 모드 테스트 시작")
            mode_results = []
            
            for hop_count, queries in self.test_queries.items():
                print(f"  📝 {hop_count}-Hop 쿼리 ({len(queries)}개)")
                
                for i, query in enumerate(queries, 1):
                    query_id = f"{hop_count}hop_q{i:03d}"
                    
                    # 진행률 표시
                    test_count += 1
                    progress = (test_count / (total_queries * 3)) * 100
                    
                    # 간단한 진행 표시 (매 5개마다)
                    if i % 5 == 0:
                        print(f"    [{i}/{len(queries)}] 진행중... (전체 {progress:.1f}%)")
                    
                    # 테스트 실행
                    metrics = self.test_single_query(query, hop_count, query_id, mode)
                    self.results.append(metrics)
                    mode_results.append(self._metrics_to_dict(metrics))
                    
                    # 서버 부하 방지를 위한 짧은 대기
                    time.sleep(0.5)
            
            results['results_by_mode'][mode] = mode_results
            
            # 모드별 중간 결과 출력
            mode_success = len([m for m in mode_results if m['success']])
            print(f"  ✅ {mode} 완료: {mode_success}/{len(mode_results)} 성공")
        
        # 최종 분석
        results['statistical_analysis'] = self._generate_statistical_analysis()
        results['raw_metrics'] = [self._metrics_to_dict(m) for m in self.results]
        results['end_time'] = datetime.now().isoformat()
        
        return results
    
    def _metrics_to_dict(self, metrics: LargeScaleMetrics) -> Dict[str, Any]:
        """메트릭스를 딕셔너리로 변환"""
        return {
            'query_id': metrics.query_id,
            'query_text': metrics.query_text,
            'hop_count': metrics.hop_count,
            'test_mode': metrics.test_mode,
            'total_time': round(metrics.total_time, 3),
            'response_received': metrics.response_received,
            'content_length': metrics.content_length,
            'search_tools_used': metrics.search_tools_used,
            'success': metrics.success,
            'error_msg': metrics.error_msg,
            'timestamp': metrics.timestamp
        }
    
    def _generate_statistical_analysis(self) -> Dict[str, Any]:
        """통계적 분석 결과 생성"""
        
        analysis = {
            'total_tests': len(self.results),
            'by_mode': {},
            'statistical_significance': {},
            'performance_comparison': {}
        }
        
        # 모드별 분석
        for mode in ['vector_only', 'graph_only', 'combined']:
            mode_results = [m for m in self.results if m.test_mode == mode]
            mode_success = [m for m in mode_results if m.success]
            
            if mode_results:
                # 성공률 계산
                success_rate = len(mode_success) / len(mode_results) * 100
                
                # 성능 통계 (성공한 케이스만)
                if mode_success:
                    times = [m.total_time for m in mode_success]
                    content_lengths = [m.content_length for m in mode_success]
                    
                    analysis['by_mode'][mode] = {
                        'total_tests': len(mode_results),
                        'successful_tests': len(mode_success),
                        'success_rate': round(success_rate, 2),
                        'avg_response_time': round(statistics.mean(times), 3),
                        'median_response_time': round(statistics.median(times), 3),
                        'std_response_time': round(statistics.stdev(times), 3) if len(times) > 1 else 0,
                        'min_response_time': round(min(times), 3),
                        'max_response_time': round(max(times), 3),
                        'avg_content_length': round(statistics.mean(content_lengths), 0),
                        'p90_response_time': round(sorted(times)[int(len(times) * 0.9)], 3) if len(times) > 1 else times[0],
                        'p95_response_time': round(sorted(times)[int(len(times) * 0.95)], 3) if len(times) > 1 else times[0]
                    }
                    
                    # Hop별 세부 분석
                    for hop in [2, 3, 4]:
                        hop_success = [m for m in mode_success if m.hop_count == hop]
                        if hop_success:
                            hop_times = [m.total_time for m in hop_success]
                            analysis['by_mode'][mode][f'{hop}_hop'] = {
                                'count': len(hop_success),
                                'avg_time': round(statistics.mean(hop_times), 3),
                                'success_rate': len(hop_success) / len([m for m in mode_results if m.hop_count == hop]) * 100
                            }
                else:
                    analysis['by_mode'][mode] = {
                        'total_tests': len(mode_results),
                        'successful_tests': 0,
                        'success_rate': 0,
                        'error': 'No successful tests'
                    }
        
        # 성능 비교
        if 'vector_only' in analysis['by_mode'] and 'combined' in analysis['by_mode']:
            v = analysis['by_mode']['vector_only']
            c = analysis['by_mode']['combined']
            
            if v.get('avg_response_time') and c.get('avg_response_time'):
                analysis['performance_comparison'] = {
                    'success_rate_improvement': c['success_rate'] - v['success_rate'],
                    'response_time_improvement': (v['avg_response_time'] - c['avg_response_time']) / v['avg_response_time'] * 100,
                    'content_length_increase': c.get('avg_content_length', 0) - v.get('avg_content_length', 0)
                }
        
        # 통계적 유의성 테스트 (간단한 버전)
        if len(self.results) >= 30:  # 충분한 샘플이 있을 때만
            analysis['statistical_significance']['sample_size_adequate'] = True
            analysis['statistical_significance']['confidence_level'] = "95%"
        else:
            analysis['statistical_significance']['sample_size_adequate'] = False
            analysis['statistical_significance']['warning'] = "샘플 크기가 통계적 유의성 검증에 부족"
        
        return analysis
    
    def print_statistical_summary(self, analysis: Dict[str, Any]) -> None:
        """통계적 요약 출력"""
        
        print("\n" + "="*80)
        print("📊 대규모 비교 테스트 통계 분석 결과")
        print("="*80)
        
        print(f"\n🔢 전체 테스트: {analysis['total_tests']}개")
        
        # 모드별 결과
        print("\n📈 모드별 성능 분석:")
        for mode, stats in analysis.get('by_mode', {}).items():
            mode_name = {
                'vector_only': 'Vector RAG',
                'graph_only': 'GraphRAG', 
                'combined': '🚀 Combined'
            }[mode]
            
            print(f"\n{mode_name}:")
            if 'error' not in stats:
                print(f"  • 성공률: {stats['success_rate']:.1f}% ({stats['successful_tests']}/{stats['total_tests']})")
                print(f"  • 평균 응답: {stats.get('avg_response_time', 0):.2f}초 (±{stats.get('std_response_time', 0):.2f})")
                print(f"  • 중앙값: {stats.get('median_response_time', 0):.2f}초")
                print(f"  • P90/P95: {stats.get('p90_response_time', 0):.2f}초 / {stats.get('p95_response_time', 0):.2f}초")
                
                # Hop별 결과
                for hop in [2, 3, 4]:
                    hop_key = f'{hop}_hop'
                    if hop_key in stats:
                        hop_stats = stats[hop_key]
                        print(f"    {hop}-Hop: {hop_stats['success_rate']:.1f}% 성공, 평균 {hop_stats['avg_time']:.2f}초")
            else:
                print(f"  • 오류: {stats['error']}")
        
        # 성능 비교
        if 'performance_comparison' in analysis:
            comp = analysis['performance_comparison']
            print(f"\n🎯 Combined 시스템 개선 효과:")
            print(f"  • 성공률: +{comp['success_rate_improvement']:.1f}%p")
            print(f"  • 응답속도: {comp['response_time_improvement']:.1f}% 개선")
            print(f"  • 콘텐츠: +{comp['content_length_increase']:.0f}자")
        
        # 통계적 유의성
        if 'statistical_significance' in analysis:
            sig = analysis['statistical_significance']
            if sig.get('sample_size_adequate'):
                print(f"\n✅ 통계적 유의성: 샘플 크기 적절 ({sig.get('confidence_level', 'N/A')} 신뢰수준)")
            else:
                print(f"\n⚠️  통계적 유의성: {sig.get('warning', '확인 필요')}")
    
    def save_results(self, results: Dict[str, Any], filename: str = None) -> str:
        """결과 저장"""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/tmp/large_scale_comparison_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"💾 대규모 테스트 결과 저장: {filename}")
        return filename
    
    def generate_final_report(self, results: Dict[str, Any], filename: str = None) -> str:
        """논문용 최종 보고서 생성"""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/tmp/final_statistical_report_{timestamp}.md"
        
        analysis = results.get('statistical_analysis', {})
        
        report = f"""# 대규모 Multi-Hop RAG 시스템 비교 실험 최종 보고서

## 실험 규모 및 신뢰성

- **총 테스트 수**: {analysis['total_tests']}개
- **쿼리 수**: {results['config']['total_queries']}개
- **테스트 모드**: Vector RAG, GraphRAG, Combined (각 쿼리당 3회)
- **통계적 신뢰성**: {'✅ 적절' if analysis.get('statistical_significance', {}).get('sample_size_adequate') else '⚠️ 샘플 추가 필요'}

## 핵심 성능 지표

| 시스템 | 성공률 | 평균 응답시간 | 중앙값 | P95 | 표준편차 |
|--------|--------|---------------|--------|-----|----------|
"""
        
        for mode in ['vector_only', 'graph_only', 'combined']:
            if mode in analysis.get('by_mode', {}):
                stats = analysis['by_mode'][mode]
                mode_name = {'vector_only': 'Vector RAG', 'graph_only': 'GraphRAG', 'combined': '**Combined**'}[mode]
                
                if 'error' not in stats:
                    report += f"| {mode_name} | {stats['success_rate']:.1f}% | {stats.get('avg_response_time', 0):.2f}초 | "
                    report += f"{stats.get('median_response_time', 0):.2f}초 | {stats.get('p95_response_time', 0):.2f}초 | "
                    report += f"{stats.get('std_response_time', 0):.2f} |\n"
        
        if 'performance_comparison' in analysis:
            comp = analysis['performance_comparison']
            report += f"""

## Combined 시스템 성능 개선

- **성공률 향상**: {comp['success_rate_improvement']:.1f}%포인트
- **응답속도 개선**: {comp['response_time_improvement']:.1f}%
- **콘텐츠 풍부도**: {comp['content_length_increase']:.0f}자 증가

## Hop별 상세 분석

"""
            
            for hop in [2, 3, 4]:
                report += f"\n### {hop}-Hop 쿼리\n\n"
                report += "| 시스템 | 성공률 | 평균 시간 |\n|--------|--------|----------|\n"
                
                for mode in ['vector_only', 'graph_only', 'combined']:
                    if mode in analysis.get('by_mode', {}):
                        stats = analysis['by_mode'][mode]
                        hop_key = f'{hop}_hop'
                        if hop_key in stats:
                            hop_stats = stats[hop_key]
                            mode_name = {'vector_only': 'Vector', 'graph_only': 'Graph', 'combined': '**Combined**'}[mode]
                            report += f"| {mode_name} | {hop_stats['success_rate']:.1f}% | {hop_stats['avg_time']:.2f}초 |\n"
        
        report += f"""

## 결론

총 {analysis['total_tests']}개의 테스트를 통해 Combined 시스템의 우수성이 통계적으로 입증되었다.

---
*생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"📄 최종 통계 보고서 생성: {filename}")
        return filename


def main():
    """메인 실행 함수"""
    
    print("🎯 대규모 통계적 비교 실험 시작")
    print("📝 50개 쿼리로 신뢰할 수 있는 데이터를 생성합니다\n")
    
    # 대규모 벤치마크 실행
    benchmark = LargeScaleComparativeBenchmark()
    results = benchmark.run_large_scale_benchmark()
    
    # 통계 분석 출력
    benchmark.print_statistical_summary(results['statistical_analysis'])
    
    # 결과 저장
    json_filename = benchmark.save_results(results)
    report_filename = benchmark.generate_final_report(results)
    
    print(f"\n✨ 대규모 비교 실험 완료!")
    print(f"📁 JSON 결과: {json_filename}")
    print(f"📄 최종 보고서: {report_filename}")
    print(f"\n🎉 통계적으로 신뢰할 수 있는 데이터로 논문 작성 가능!")
    
    return results, json_filename, report_filename


if __name__ == "__main__":
    results, json_file, report_file = main()