# neo4j_rag_tool.py
import os
import re
import json
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from neo4j import GraphDatabase, basic_auth
from neo4j.exceptions import ClientError
from langchain_google_genai import ChatGoogleGenerativeAI


# =========================
# Config & Constants
# =========================
DEFAULT_NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# 단일 풀텍스트 인덱스 이름
FULLTEXT_UNIFIED_INDEX = "product_idx"  # 품목/국가/지역/영양소/기업/문서 등 통합 검색


# =========================
# Utilities
# =========================
def _debug(msg: str):
    print(f"[neo4j-rag] {msg}")


def _load_env():
    # 상위 프로젝트 루트에 .env가 있다면 로드
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


# =========================
# Graph Client
# =========================
class GraphDBClient:
    def __init__(self, uri: str = DEFAULT_NEO4J_URI, user: str = DEFAULT_NEO4J_USER, password: str = DEFAULT_NEO4J_PASSWORD):
        _load_env()
        uri = os.getenv("NEO4J_URI", uri)
        user = os.getenv("NEO4J_USER", user)
        password = os.getenv("NEO4J_PASSWORD", password)

        self._driver = GraphDatabase.driver(uri, auth=basic_auth(user, password))
        _debug(f"Connected Neo4j (uri={uri})")

    def close(self):
        try:
            self._driver.close()
            _debug("Driver closed")
        except Exception:
            pass

    def run(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        with self._driver.session() as session:
            res = session.run(query, params or {})
            return [r.data() for r in res]


# =========================
# LLM Wrapper
# =========================
class LLM:
    def __init__(self, model: str = "gemini-2.5-flash-lite", temperature: float = 0.0):
        self.client = ChatGoogleGenerativeAI(model=model, temperature=temperature)

    async def ainvoke(self, prompt: str) -> str:
        resp = await self.client.ainvoke(prompt)
        return (resp.content or "").strip()

    def invoke(self, prompt: str) -> str:
        resp = self.client.invoke(prompt)
        return (resp.content or "").strip()


# =========================
# Search Service (single-query)
# =========================
class GraphDBSearchService:
    """
    - 키워드 추출(LLM + 폴백) : 구분 없이 단일 리스트
    - DB 호출은 단 하나의 쿼리 형태만 사용:
        CALL db.index.fulltext.queryNodes('product_idx', $kw)
        YIELD node AS n, score
        MATCH (n)-[r0]-(m)
        RETURN n, r, m, score
        ORDER BY score DESC
    - 관계 가공:
        * isFrom      -> 원산지 정보 (r.count => 농장수)
        * hasNutrient -> 영양성분 정보 (r.value[+unit] => 양)
        * relation    -> 문서 정보 (r.type => 문서 타입)
    """

    SINGLE_QUERY = f"""
CALL db.index.fulltext.queryNodes('{FULLTEXT_UNIFIED_INDEX}', $kw)
YIELD node AS n, score
OPTIONAL MATCH (n)-[r]-(m)
RETURN n, r, m, score
ORDER BY score DESC
LIMIT 500
"""

    def __init__(self, client: Optional[GraphDBClient] = None, llm: Optional[LLM] = None):
        self.client = client or GraphDBClient()
        self.llm = llm or LLM()

    # ---------- Public ----------
    async def search(self, user_query: str) -> str:
        _debug(f"Graph search started: '{user_query}'")
        
        # 1. 키워드 추출
        kw = await self._extract_keywords(user_query)
        keywords = kw.get("keywords", [])
        if not keywords:
            return f"'{user_query}'에 사용할 키워드를 찾지 못했습니다. \n더 구체적인 품목명이나 지역명을 입력해주세요."
        
        _debug(f"Extracted keywords: {keywords}")
        
        # 2. Lucene 쿼리 구성 및 실행
        lucene = self._build_fulltext_query(keywords)
        _debug(f"Lucene query: {lucene}")
        
        if not lucene:
            return f"'{user_query}' 검색에 사용할 수 있는 유효한 키워드가 없습니다."
            
        rows = await self._run_single_query(lucene)
        _debug(f"Retrieved {len(rows)} raw results from Neo4j")

        # 3. 결과 처리를 위한 컨테이너 초기화
        node_bucket: Dict[str, Dict[str, Any]] = {}  # elementId -> node dict (최대 score로 유지)
        isfrom_list: List[Dict[str, Any]] = []
        nutrients_list: List[Dict[str, Any]] = []
        docrels_list: List[Dict[str, Any]] = []

        # 4. 결과 파싱 및 관계 분류
        self._parse_rows(rows, node_bucket, isfrom_list, nutrients_list, docrels_list)
        
        _debug(f"Parsed results - nodes: {len(node_bucket)}, origins: {len(isfrom_list)}, nutrients: {len(nutrients_list)}, docs: {len(docrels_list)}")

        # 5. 노드 점수별 정렬
        nodes_sorted = sorted(node_bucket.values(), key=lambda x: x.get("score", 0.0), reverse=True)

        # 6. 관계 데이터 중복 제거 및 정렬
        def uniq(items, keyfunc):
            seen = set(); out = []
            for it in items:
                k = keyfunc(it)
                if k not in seen:
                    seen.add(k); out.append(it)
            return out

        # 중복 제거 및 정렬
        isfrom_list    = uniq(isfrom_list,    lambda r: (r.get("item"), r.get("origin")))
        nutrients_list = uniq(nutrients_list, lambda r: (r.get("item"), r.get("nutrient")))
        docrels_list   = uniq(docrels_list,   lambda r: (r.get("source"), r.get("target"), r.get("rel_type")))
        
        # 원산지 관계를 항목별로 그룹화
        isfrom_list = sorted(isfrom_list, key=lambda x: (x.get("item", ""), x.get("origin", "")))
        # 영양성분 관계를 항목별로 그룹화  
        nutrients_list = sorted(nutrients_list, key=lambda x: (x.get("item", ""), x.get("nutrient", "")))

        # 7. 최종 리포트 생성
        report = self._format_report(user_query, nodes_sorted, isfrom_list, nutrients_list, docrels_list)
        
        _debug(f"Search completed - Final results: nodes={len(nodes_sorted)}, origins={len(isfrom_list)}, nutrients={len(nutrients_list)}, docs={len(docrels_list)}")
        return report

    def close(self):
        self.client.close()

    # ---------- Keyword Extraction ----------
    async def _extract_keywords(self, q: str) -> Dict[str, List[str]]:
        prompt = f"""
다음 질문에서 그래프 검색에 사용할 핵심 키워드를 추출하세요.
- 농산물/수산물/축산물 품목명 (예: 사과, 배추, 고등어)
- 지역/원산지 (예: 제주도, 경상북도, 통영)
- 영양성분 (예: 비타민C, 단백질, 칼슘)
- 기업/조직/브랜드명
- 관련성 높은 핵심 용어만 선별
- JSON 형태로만 응답

질문: "{q}"

JSON 예:
{{ "keywords": ["사과","제주도","비타민C","당도"] }}
"""
        try:
            txt = await self.llm.ainvoke(prompt)
            m = re.search(r"\{[\s\S]*\}", txt)
            if m:
                txt = m.group(0)
            data = json.loads(txt)
            _debug(f"LLM keywords: {data}")
            if "keywords" not in data or not isinstance(data["keywords"], list):
                data["keywords"] = []
            return data
        except Exception as e:
            _debug(f"LLM keyword extraction failed: {e}")
            return self._keyword_fallback(q)

    def _keyword_fallback(self, q: str) -> Dict[str, List[str]]:
        # 농업/식품 관련 불용어 확장
        stop = {
            "의","을","를","이","가","에","에서","로","으로","와","과","도","만","부터","까지",
            "알려줘","검색","찾아","정보","어디","무엇","언제","어떤","어느","얼마","몇",
            "있는","있나","있어","보여줘","말해줘","대해","관한","관련","대한","중에서",
            "뭐야","뭔가","그거","그것","이거","저거","하나","좀","잠깐","그냥","한번"
        }
        
        # 한글, 영문, 숫자만 추출
        words = re.findall(r'[가-힣a-zA-Z0-9]+', q)
        terms = [w for w in words if len(w) > 1 and w not in stop]
        
        # 우선순위: 긴 단어 먼저 (품목명이 보통 2-3글자 이상)
        terms = sorted(terms, key=len, reverse=True)[:8]
        return {"keywords": terms}

    # ---------- Fulltext OR query builder ----------
    def _build_fulltext_query(self, keywords: List[str]) -> str:
        def esc(t: str) -> str:
            # Lucene 특수문자 이스케이프
            t = t.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{t}"'
        
        if not keywords:
            return ""
            
        # 키워드 우선순위 조정: 긴 키워드에 부스트 점수 적용
        boosted_terms = []
        for k in keywords:
            escaped = esc(k)
            # 3글자 이상 키워드는 중요도 부스트
            if len(k) >= 3:
                boosted_terms.append(f"{escaped}^2.0")  
            else:
                boosted_terms.append(escaped)
                
        return " OR ".join(boosted_terms)

    # ---------- Single-query runner ----------
    async def _run_single_query(self, lucene_query: str) -> List[Dict[str, Any]]:
        return await self._run_async(self.SINGLE_QUERY, {"kw": lucene_query})

    # ---------- Row parsing ----------
    def _parse_rows(
        self,
        rows: List[Dict[str, Any]],
        node_bucket: Dict[str, Dict[str, Any]],
        isfrom_list: List[Dict[str, Any]],
        nutrients_list: List[Dict[str, Any]],
        docrels_list: List[Dict[str, Any]],
    ):
        for r in rows:
            n = r["n"]; m = r.get("m"); rel = r.get("r"); score = float(r.get("score", 0.0))

            # n 노드만 점수 반영 (항상 있음)
            n_fmt = self._format_node(n, score)
            node_bucket[n_fmt["id"]] = self._keep_max_score(node_bucket.get(n_fmt["id"]), n_fmt)
            
            # m 또는 rel이 없는 경우 (OPTIONAL MATCH로 인해)
            if not m or not rel:
                continue

            # 관계 분기 및 처리
            rel_type_label = getattr(rel, "type", None) or ""   # isFrom / hasNutrient / relation ...
            try:
                rel_props = dict(rel)  # count, value, unit, type(문서타입) 등
            except Exception:
                rel_props = {}

            def has_label(node, label) -> bool:
                try:
                    if hasattr(node, 'labels'):
                        return label in list(node.labels)
                    elif isinstance(node, dict) and 'labels' in node:
                        return label in node['labels']
                    return False
                except Exception:
                    return False

            def node_display(node) -> str:
                try:
                    p = dict(node)
                except Exception:
                    p = {}
                try:
                    if hasattr(node, 'labels'):
                        labels = list(node.labels)
                    elif isinstance(node, dict) and 'labels' in node:
                        labels = node['labels'] if isinstance(node['labels'], list) else [node['labels']]
                    else:
                        labels = []
                except Exception:
                    labels = []
                
                # 라벨별 특화 처리
                if "Origin" in labels:
                    city = p.get("city","").strip(); region = p.get("region","").strip()
                    if city and city != "." and region and region != ".":
                        return f"{city} ({region})"
                    return city or region or "N/A"
                elif "농산물" in labels or "수산물" in labels or "축산물" in labels:
                    return p.get("product", p.get("name", "N/A"))
                elif "Nutrient" in labels:
                    return p.get("name", p.get("nutrient", "N/A"))
                    
                # 일반적 처리
                for k in ("product","name","title","city","region","id"):
                    val = p.get(k, "").strip() if p.get(k) else ""
                    if val and val != "N/A": 
                        return val
                return "N/A"

            if rel_type_label == "isFrom":
                origin_node, item_node = (n, m) if has_label(n, "Origin") else ((m, n) if has_label(m, "Origin") else (None, None))
                if origin_node and item_node:
                    item_name = node_display(item_node)
                    origin_name = node_display(origin_node)
                    # 중복 제거를 위해 유효한 데이터만 추가
                    if item_name != "N/A" and origin_name != "N/A":
                        isfrom_list.append({
                            "item": item_name,
                            "origin": origin_name,
                            "count": rel_props.get("count"),   # 농장수
                        })

            elif rel_type_label == "hasNutrient":
                nut_node, item_node = (n, m) if has_label(n, "Nutrient") else ((m, n) if has_label(m, "Nutrient") else (None, None))
                if nut_node and item_node:
                    item_name = node_display(item_node)
                    nutrient_name = dict(nut_node).get("name") or node_display(nut_node)
                    # 영양성분 정보가 유효한 경우만 추가
                    if item_name != "N/A" and nutrient_name != "N/A":
                        nutrients_list.append({
                            "item": item_name,
                            "nutrient": nutrient_name,
                            "value": rel_props.get("value"),
                            "unit": rel_props.get("unit"),
                        })

            elif rel_type_label == "relation":
                # 문서 관계 처리 개선
                doc_node, src_node = (n, m) if has_label(n, "Entity") else ((m, n) if has_label(m, "Entity") else (m, n))
                src_name = node_display(src_node)
                doc_name = node_display(doc_node)
                doc_type = rel_props.get("type", "마켓리포트")
                
                # 유효한 문서 관계만 추가
                if src_name != "N/A" and doc_name != "N/A":
                    docrels_list.append({
                        "source": src_name,
                        "target": doc_name,
                        "rel_type": doc_type,  # 문서 타입
                    })

            # 기타 관계 타입은 출력 생략

    # ---------- Helpers ----------
    async def _run_async(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.client.run, query, params or {})

    def _format_node(self, node, score: float) -> Dict[str, Any]:
        try:
            props = dict(node)
        except Exception:
            props = {}
        try:
            if hasattr(node, 'labels'):
                labels = list(node.labels)
            elif isinstance(node, dict) and 'labels' in node:
                labels = node['labels'] if isinstance(node['labels'], list) else [node['labels']]
            else:
                labels = []
        except Exception:
            labels = []
        # elementId 추출
        eid = None
        for attr in ("element_id", "id", "identity"):
            if hasattr(node, attr):
                try:
                    val = getattr(node, attr)
                    eid = str(val) if val is not None else None
                    if eid: break
                except Exception:
                    continue
        ntype = labels[0] if labels else "Node"
        return {
            "id": eid or json.dumps(props, ensure_ascii=False),
            "type": ntype,
            "labels": labels,
            "properties": props,
            "score": score,
            "search_type": "fulltext",  # 본 쿼리는 항상 fulltext
        }

    def _keep_max_score(self, old: Optional[Dict[str, Any]], new: Dict[str, Any]) -> Dict[str, Any]:
        if not old: return new
        return new if new.get("score", 0.0) > old.get("score", 0.0) else old

    def _node_display_for_report(self, n: Dict[str, Any]) -> str:
        t = n.get("type", "")
        p = n.get("properties", {})
        if t in ("농산물","수산물","축산물"):
            return p.get("product", "N/A")
        if t == "Origin":
            city = p.get("city", ""); region = p.get("region", "")
            return f"{city} ({region})" if city and city != "." else (region or city or "N/A")
        for k in ("name","title","product","city","region","id"):
            if p.get(k):
                return str(p[k])
        return "N/A"

    def _format_report(
        self,
        q: str,
        nodes: List[Dict[str, Any]],
        isfrom: List[Dict[str, Any]],
        nutrients: List[Dict[str, Any]],
        docrels: List[Dict[str, Any]],
    ) -> str:
        if not nodes and not isfrom and not nutrients and not docrels:
            return f"'{q}'에 대한 그래프 검색 결과를 찾지 못했습니다."

        lines = []
        lines.append(f"Neo4j Graph 검색 결과 ('{q}')")
        lines.append(f"- 항목 {len(nodes)}개, 원산지 관계 {len(isfrom)}개, 영양성분 관계 {len(nutrients)}개, 문서 관계 {len(docrels)}개\n")

        # 노드들을 카테고리별로 그룹화하고 분석 요약 제공
        if nodes:
            # 카테고리별로 분류
            categories = {}
            for n in nodes:
                node_type = n.get('type', 'Unknown')
                if node_type not in categories:
                    categories[node_type] = []
                categories[node_type].append(n)
            
            lines.append("검색 결과 분석:")
            
            # 카테고리별 요약
            category_summary = []
            for category, category_nodes in categories.items():
                # 카테고리별로 대표 항목들 추출
                top_nodes = sorted(category_nodes, key=lambda x: x.get("score", 0.0), reverse=True)
                representative_names = []
                
                for n in top_nodes:
                    name = self._node_display_for_report(n)
                    if name != "N/A" and name not in representative_names:
                        representative_names.append(name)
                        if len(representative_names) >= 3:  # 각 카테고리에서 최대 3개 대표 항목
                            break
                
                if representative_names:
                    category_summary.append(f"{category}({len(category_nodes)}개): {', '.join(representative_names)}")
                else:
                    category_summary.append(f"{category}: {len(category_nodes)}개 항목")
            
            lines.append(f"주요 카테고리: {'; '.join(category_summary)}")
            lines.append("")

        # 실제 관계 데이터가 있는 경우에만 상세 표시
        if isfrom:
            lines.append(f"원산지 관계 정보 ({len(isfrom)}건):")
            for i, r in enumerate(isfrom, 1):
                suffix = f" (농장수 {int(r['count'])}개)" if r.get("count") is not None else ""
                lines.append(f"  {i}. {r['item']} → {r['origin']}{suffix}")
            lines.append("")

        if nutrients:
            lines.append(f"영양성분 관계 정보 ({len(nutrients)}건):")
            for i, n in enumerate(nutrients, 1):
                amount = ""
                if n.get("value") is not None:
                    amount = f" (양: {n['value']}{n.get('unit','') or ''})"
                lines.append(f"  {i}. {n['item']} - {n['nutrient']}{amount}")
            lines.append("")

        if docrels:
            lines.append(f"문서 관계 정보 ({len(docrels)}건):")
            for i, d in enumerate(docrels, 1):
                rtype = f" (type: {d['rel_type']})" if d.get("rel_type") else ""
                lines.append(f"  {i}. {d['source']} - {d['target']}{rtype}")
            lines.append("")

        # 데이터 한계 및 권장사항 추가
        if not isfrom and not nutrients and not docrels:
            lines.append("※ 주의사항:")
            lines.append("  - 현재 검색에서는 구체적인 관계 정보(원산지-품목 연결, 영양성분 등)를 찾지 못했습니다.")
            lines.append("  - 일반적인 카테고리 노드들만 발견되었습니다.")
            lines.append("  - 더 구체적인 품목명이나 지역명으로 검색하시거나 다른 데이터 소스를 활용하는 것을 권장합니다.")

        return "\n".join(lines)


# =========================
# Query Optimizer (Graph-friendly phrase)
# =========================
class GraphQueryOptimizer:
    """
    사용자 자연어 질문을 그래프 DB 검색에 유리한 '관계 중심 문구'로 단순화.
    예: "사과의 원산지", "오렌지의 영양소", "오렌지의 원산지와 영양소"
    """
    def __init__(self, llm: Optional[LLM] = None):
        self.llm = llm or LLM()

    async def optimize(self, user_query: str) -> str:
        prompt = f"""
다음 사용자 질문을 Graph DB 검색에 가장 효과적인 핵심 관계 중심 문구로 바꾸세요.
- 그래프 데이터 특성: (품목)-[:isFrom]->(원산지), (품목)-[:hasNutrient]->(영양소), (노드)-[:relation]->(문서)
- 꼭 필요한 엔티티와 관계만 남기고, 한국어로 간결히.
- 예시: "사과의 원산지", "오렌지의 영양소", "오렌지의 원산지와 영양소"
- 불필요한 수식/설명 금지. 결과만 한 줄로.

질문: "{user_query}"
답변:
"""
        try:
            txt = await self.llm.ainvoke(prompt)
            return txt.strip().replace("\n", " ")
        except Exception as e:
            _debug(f"optimize failed: {e}")
            return user_query


# =========================
# Public Entrypoints
# =========================
def neo4j_search_sync(query: str) -> str:
    """스레드/프로세스 어디서나 호출 가능한 동기 진입점"""
    svc = GraphDBSearchService()
    try:
        # 기존 이벤트 루프가 있는지 확인
        try:
            asyncio.get_running_loop()
            # 이미 실행 중인 루프가 있으면 ThreadPool에서 실행
            _debug("Found running loop, using ThreadPoolExecutor")
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_run_search_in_new_loop, svc, query)
                return future.result()
        except RuntimeError:
            # 실행 중인 루프가 없으면 새 루프 생성
            _debug("No running loop, creating new event loop")
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(svc.search(query))
            finally:
                loop.close()
                asyncio.set_event_loop(None)
    except Exception as e:
        _debug(f"sync search error: {e}")
        return f"Neo4j 동기 검색 오류: {e}"
    finally:
        svc.close()


def _run_search_in_new_loop(svc: 'GraphDBSearchService', query: str) -> str:
    """새로운 이벤트 루프에서 검색 실행"""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(svc.search(query))
    finally:
        loop.close()
        asyncio.set_event_loop(None)


async def neo4j_graph_search(query: str) -> str:
    """에이전트에서 직접 await할 수 있는 비동기 진입점"""
    svc = GraphDBSearchService()
    try:
        return await svc.search(query)
    finally:
        svc.close()
