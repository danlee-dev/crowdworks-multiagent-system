"""
데이터 중복 제거 유틸리티
각 검색 도구별 고유 ID를 활용한 전역 중복 제거
"""

from typing import List, Dict, Set, Any


class GlobalDeduplicator:
    """전역 중복 제거 관리자"""
    
    def __init__(self):
        self.seen_ids: Set[str] = set()
    
    def deduplicate_results(self, results: List[Dict], source_type: str = "unknown") -> List[Dict]:
        """
        검색 결과에서 중복 제거
        
        Args:
            results: 검색 결과 리스트
            source_type: 검색 소스 타입 (elasticsearch, neo4j, web, etc.)
        
        Returns:
            중복이 제거된 결과 리스트
        """
        unique_results = []
        
        for result in results:
            unique_id = self._extract_unique_id(result, source_type)
            
            if unique_id and unique_id in self.seen_ids:
                print(f"[중복 제거] {source_type}: {unique_id}")
                continue
            
            if unique_id:
                self.seen_ids.add(unique_id)
            
            unique_results.append(result)
        
        print(f"[중복 제거] {source_type}: {len(results)} → {len(unique_results)}")
        return unique_results
    
    def _extract_unique_id(self, result: Dict, source_type: str) -> str:
        """검색 소스별 고유 ID 추출"""
        
        if source_type == "elasticsearch":
            # Elasticsearch: meta_data.chunk_id 사용
            chunk_id = result.get("meta_data", {}).get("chunk_id")
            if chunk_id:
                return f"es_{chunk_id}"
        
        elif source_type == "neo4j":
            # Neo4j: elementId 또는 node ID 사용
            if "elementId" in result:
                return f"neo4j_{result['elementId']}"
            elif "id" in result:
                return f"neo4j_{result['id']}"
        
        elif source_type == "web":
            # Web 검색: URL 사용
            url = result.get("url") or result.get("link")
            if url:
                return f"web_{url}"
        
        elif source_type == "rdb":
            # RDB: 테이블.ID 사용
            table = result.get("table", "")
            record_id = result.get("id", "")
            if table and record_id:
                return f"rdb_{table}_{record_id}"
        
        # 백업: content 해시 사용
        content = result.get("page_content", "") or result.get("content", "")
        if content:
            content_hash = str(hash(content))
            return f"{source_type}_hash_{content_hash}"
        
        return ""
    
    def reset(self):
        """중복 제거 상태 초기화"""
        self.seen_ids.clear()
    
    def get_seen_count(self) -> int:
        """현재까지 본 고유 ID 개수"""
        return len(self.seen_ids)


def create_deduplicator() -> GlobalDeduplicator:
    """새로운 중복 제거기 생성"""
    return GlobalDeduplicator()


def deduplicate_mixed_results(
    elasticsearch_results: List[Dict] = None,
    neo4j_results: List[Dict] = None, 
    web_results: List[Dict] = None,
    rdb_results: List[Dict] = None
) -> Dict[str, List[Dict]]:
    """
    여러 소스의 검색 결과를 통합하여 중복 제거
    
    Returns:
        {
            "elasticsearch": [...],
            "neo4j": [...], 
            "web": [...],
            "rdb": [...],
            "all_unique": [...]  # 모든 결과 통합
        }
    """
    deduplicator = GlobalDeduplicator()
    result = {}
    all_unique = []
    
    # 각 소스별로 중복 제거
    if elasticsearch_results:
        unique_es = deduplicator.deduplicate_results(elasticsearch_results, "elasticsearch")
        result["elasticsearch"] = unique_es
        all_unique.extend(unique_es)
    
    if neo4j_results:
        unique_neo4j = deduplicator.deduplicate_results(neo4j_results, "neo4j")
        result["neo4j"] = unique_neo4j
        all_unique.extend(unique_neo4j)
    
    if web_results:
        unique_web = deduplicator.deduplicate_results(web_results, "web")
        result["web"] = unique_web
        all_unique.extend(unique_web)
    
    if rdb_results:
        unique_rdb = deduplicator.deduplicate_results(rdb_results, "rdb")
        result["rdb"] = unique_rdb
        all_unique.extend(unique_rdb)
    
    result["all_unique"] = all_unique
    
    print(f"[전체 중복 제거] 총 {deduplicator.get_seen_count()}개 고유 문서, {len(all_unique)}개 결과")
    
    return result