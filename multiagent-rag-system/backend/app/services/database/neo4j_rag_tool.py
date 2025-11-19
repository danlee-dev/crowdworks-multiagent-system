# neo4j_rag_tool.py
import os
import re
import json
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase, basic_auth
from neo4j.exceptions import ClientError
from langchain_google_genai import ChatGoogleGenerativeAI


# =========================
# Config & Constants
# =========================
DEFAULT_NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# 분리된 풀텍스트 인덱스 이름들
ORIGIN_INDEX   = "origin_idx"    # (Ingredient)-[isFrom]->(Origin) 축 대상
NUTRIENT_INDEX = "nutrient_idx"  # (Food)-[hasNutrient]->(Nutrient) 축 대상
DOC_INDEX      = "doc_idx"       # (:Entity)-[relation]-(:Document) 축 대상
REL_INDEX      = "rel_idx"


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

        # Neo4j 비동기 드라이버 연결 설정 최적화
        self._driver = AsyncGraphDatabase.driver(
            uri, 
            auth=basic_auth(user, password),
            max_connection_lifetime=30,  # 연결 수명 30초
            max_connection_pool_size=50,  # 최대 연결 풀 크기
            connection_acquisition_timeout=10,  # 연결 획득 타임아웃 10초
            connection_timeout=5,  # 연결 타임아웃 5초
            keep_alive=True,  # 연결 유지
            max_transaction_retry_time=5  # 트랜잭션 재시도 시간 5초
        )
        _debug(f"Connected Neo4j (uri={uri})")

    async def close(self):
        try:
            await self._driver.close()
            _debug("Driver closed")
        except Exception:
            pass

    async def run(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        async with self._driver.session(
            database="neo4j",  # 명시적 데이터베이스 지정
            default_access_mode="READ"  # 읽기 전용 모드
        ) as session:
            try:
                res = await session.run(query, params or {}, timeout=20)  # 20초 타임아웃
                return [r.data() async for r in res]
            except Exception as e:
                _debug(f"Neo4j query error: {e}")
                raise


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
        CALL db.index.fulltext.queryNodes('search_idx', $kw)
        YIELD node AS n, score
        MATCH (n)-[r0]-(m)
        RETURN n, r, m, score
        ORDER BY score DESC
    - 관계 가공:
        * isFrom      -> 원산지 정보 (r.count => 농장수)
        * hasNutrient -> 영양성분 정보 (r.value[+unit] => 양)
        * relation    -> 문서 정보 (r.type => 문서 타입)
    """

    def _build_indexed_query(self, index_name: str) -> str:
        return f"""
        CALL db.index.fulltext.queryNodes('{index_name}', $kw)
        YIELD node AS n, score
        MATCH (n)-[r]-(m)
        RETURN n, r, m, score,
               type(r) AS rel_type,
               startNode(r) AS s,
               endNode(r)   AS e
        ORDER BY score DESC
        LIMIT 50
        """
    
    def _build_rel_indexed_query(self, index_name: str) -> str:
        return f"""
        CALL db.index.fulltext.queryRelationships('{index_name}', $kw)
        YIELD relationship AS r, score
        MATCH (s)-[r]-(e)
        RETURN s AS n, r, e AS m, score,
               type(r) AS rel_type,
               startNode(r) AS s,
               endNode(r) AS e
        ORDER BY score DESC
        LIMIT 50
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
            
        tasks = [
            self._run_indexed_query(ORIGIN_INDEX,   lucene),
            self._run_indexed_query(NUTRIENT_INDEX, lucene),
            self._run_indexed_query(DOC_INDEX,      lucene),
            self._run_rel_indexed_query(REL_INDEX,    lucene),
        ]
        res_origin, res_nutrient, res_doc, res_rel = await asyncio.gather(*tasks, return_exceptions=False)
        rows = (res_origin or []) + (res_nutrient or []) + (res_doc or []) + (res_rel or [])
        _debug(f"Retrieved raw results - origin:{len(res_origin)} / nutrient:{len(res_nutrient)} / doc:{len(res_doc)}/ rel:{len(res_rel)} / total:{len(rows)}")

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

    async def close(self):
        await self.client.close()

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

    # ---------- Indexed fulltext runner ----------
    async def _run_indexed_query(self, index_name: str, lucene_query: str) -> List[Dict[str, Any]]:
        q = self._build_indexed_query(index_name)
        return await self._run_async(q, {"kw": lucene_query})
    
    async def _run_rel_indexed_query(self, index_name: str, lucene_query: str) -> List[Dict[str, Any]]:
        q = self._build_rel_indexed_query(index_name)
        return await self._run_async(q, {"kw": lucene_query})

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
            s_node   = r.get("s")
            e_node   = r.get("e")
            rt     = str(r.get("rel_type") or "").lower()

            # n 노드 점수만 유지(기존 로직 그대로)
            n_fmt = self._format_node(n, score)
            node_bucket[n_fmt["id"]] = self._keep_max_score(node_bucket.get(n_fmt["id"]), n_fmt)

            # 관계/상대 노드 없으면 패스
            if not m or not rel or not s_node or not e_node:
                continue

            # 관계 속성
            try:
                rel_props = dict(rel)
            except Exception:
                rel_props = {}

            # 표시 이름(스킵 방지용으로 보강)
            def node_display(node) -> str:
                try:
                    p = dict(node)
                    # 우선순위 키
                    for k in ("name","product","food","ingredient","title","city","region","koName","enName","id","uuid"):
                        v = p.get(k)
                        if isinstance(v, str) and v.strip():
                            return v.strip()
                    # 아무 문자열 속성이나 하나
                    for v in p.values():
                        if isinstance(v, str) and v.strip():
                            return v.strip()
                except Exception:
                    pass
                # 마지막 폴백: element id
                try:
                    return getattr(node, "element_id", "") or "UNKNOWN"
                except Exception:
                    return "UNKNOWN"

            # === 버킷/방향 확정 매핑 ===
            # === 관계 타입/방향 기반 확정 분기 ===
            if rt == "isfrom":
                item_name   = node_display(s_node)  # s=Ingredient
                origin_name = node_display(e_node)  # e=Origin
                isfrom_list.append({
                    "item": item_name,
                    "origin": origin_name,
                    "count": rel_props.get("count"),
                    "farm": rel_props.get("farm"),
                    "category": rel_props.get("category"),
                    "fishState": rel_props.get("fishState"),
                })
            elif rt == "hasnutrient":
                item_name     = node_display(s_node)              # s=Food
                nutrient_name = dict(e_node).get("name") if e_node else None
                nutrient_name = nutrient_name or node_display(e_node)  # e=Nutrient
                nutrients_list.append({
                    "item": item_name,
                    "nutrient": nutrient_name,
                    "value": rel_props.get("value"),
                })
            elif rt == "relation":
                src_name = node_display(s_node)  # s=source entity
                tgt_name = node_display(e_node)  # e=target entity
                
                # 관계 타입: 속성의 type이 있으면 사용, 없으면 관계타입(rt) 사용
                actual_rel_type = rel_props.get("type") or rt
                
                # 문서 정보: doc 또는 document 속성 확인
                doc_info = rel_props.get("doc") or rel_props.get("document")
                
                docrels_list.append({
                    "source": src_name,
                    "target": tgt_name,
                    "rel_type": actual_rel_type,
                    "doc": doc_info,
                })

    # ---------- Helpers ----------
    async def _run_async(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return await self.client.run(query, params or {})

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
        if t == "Ingredient":
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
- 그래프 데이터 특성: (품목)-[:isFrom]->(원산지), (품목)-[:hasNutrient]->(영양소), (키워드)-[:relation]->(키워드)
- 꼭 필요한 엔티티와 관계만 남기고, 한국어로 간결히.
- 예시: "사과의 원산지", "오렌지의 영양소", "오렌지의 원산지와 영양소", "충북 예산의 특산품"
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
    max_retries = 3
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        svc = None
        try:
            svc = GraphDBSearchService()
            
            # 기존 이벤트 루프가 있는지 확인
            try:
                asyncio.get_running_loop()
                # 이미 실행 중인 루프가 있으면 ThreadPool에서 실행
                _debug(f"Found running loop, using ThreadPoolExecutor (attempt {attempt + 1})")
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(_run_search_in_new_loop, svc, query)
                    return future.result(timeout=30)  # 30초 타임아웃 추가
            except RuntimeError:
                # 실행 중인 루프가 없으면 새 루프 생성
                _debug(f"No running loop, creating new event loop (attempt {attempt + 1})")
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    return loop.run_until_complete(svc.search(query))
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
                    
        except (BlockingIOError, OSError, ConnectionError, TimeoutError) as e:
            _debug(f"Neo4j connection error on attempt {attempt + 1}: {e}")
            if svc:
                try:
                    svc.close()
                except:
                    pass
            
            if attempt < max_retries - 1:
                _debug(f"Retrying in {retry_delay} seconds...")
                import time
                time.sleep(retry_delay)
                retry_delay *= 2  # 지수 백오프
                continue
            else:
                _debug(f"All {max_retries} attempts failed")
                return f"Neo4j 연결 오류 (재시도 {max_retries}회 실패): {e}"
                
        except Exception as e:
            _debug(f"Unexpected error on attempt {attempt + 1}: {e}")
            if svc:
                try:
                    svc.close()
                except:
                    pass
            return f"Neo4j 동기 검색 오류: {e}"
        finally:
            if svc:
                try:
                    svc.close()
                except:
                    pass


def _run_search_in_new_loop(svc: 'GraphDBSearchService', query: str) -> str:
    """새로운 이벤트 루프에서 검색 실행"""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        # 타임아웃과 함께 실행
        task = svc.search(query)
        return loop.run_until_complete(asyncio.wait_for(task, timeout=25))
    except asyncio.TimeoutError:
        _debug("Neo4j search timed out after 25 seconds")
        raise TimeoutError("Neo4j search timeout")
    except Exception as e:
        _debug(f"Error in new loop search: {e}")
        raise
    finally:
        try:
            # 모든 태스크 취소 및 정리
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception as cleanup_error:
            _debug(f"Error during loop cleanup: {cleanup_error}")
        finally:
            loop.close()
            asyncio.set_event_loop(None)


async def neo4j_graph_search(query: str) -> str:
    """에이전트에서 직접 await할 수 있는 비동기 진입점"""
    svc = GraphDBSearchService()
    try:
        return await svc.search(query)
    finally:
        await svc.close()
