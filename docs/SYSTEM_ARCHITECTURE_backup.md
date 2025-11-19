# Multi-Agent RAG 시스템 아키텍처 및 구현 상세

## 목차
1. [AI 에이전트 구성](#1-ai-에이전트-구성)
2. [에이전트 Workflow 최적화 방법](#2-에이전트-workflow-최적화-방법)
3. [에이전트 구성요소별 개발 상세](#3-에이전트-구성요소별-개발-상세)
4. [페르소나 기반 보고서 생성](#4-페르소나-기반-보고서-생성)
5. [리서치 리포트 구조생성 및 출처관리](#5-리서치-리포트-구조생성-및-출처관리)
6. [외부 도구 및 Multi-RAG 연동 APIs](#6-외부-도구-및-multi-rag-연동-apis)

---

## 1. AI 에이전트 구성

### 1.1 에이전트 아키텍처 개요

본 시스템은 **4개의 전문화된 AI 에이전트**로 구성된 Multi-Agent 아키텍처를 채택하고 있습니다:

- **TriageAgent**: 사용자 요청을 분석하여 'chat' 또는 'task' 플로우로 분류
- **OrchestratorAgent**: 전체 워크플로우를 관리하고 실행 계획을 수립
- **DataGathererAgent**: Multi-RAG 방식으로 다양한 데이터 소스에서 정보를 수집
- **ProcessorAgent**: 수집된 데이터를 기반으로 고품질 보고서를 생성

### 1.2 데이터 흐름도

```
사용자 요청
   ↓
[TriageAgent] → 'chat' or 'task' 분류
   ↓
[OrchestratorAgent]
   ├─ 계획 수립 (generate_plan)
   ├─ Graph DB 프리체크 (_probe_graph_data_locations)
   └─ 워크플로우 실행 (execute_report_workflow)
       ↓
[DataGathererAgent] → Multi-RAG 병렬 검색
   ├─ Web Search
   ├─ Vector DB (Elasticsearch)
   ├─ Graph DB (Neo4j)
   ├─ RDB (PostgreSQL)
   ├─ PubMed
   └─ Arxiv
       ↓
[ProcessorAgent] → 보고서 생성
   ├─ 구조 설계 (_design_report_structure)
   ├─ 섹션 생성 (generate_section_streaming)
   └─ 차트 생성 (_create_charts)
       ↓
사용자에게 스트리밍 전송 (SSE)
```

---

## 2. 에이전트 Workflow 최적화 방법

### 2.1 Planning Agent의 동적 워크플로우 설정

#### 2.1.1 지능형 단계별 계획 수립 (Orchestrator Agent)

**OrchestratorAgent**는 사용자 요청을 분석하여 **의존성을 고려한 최적의 실행 계획**을 동적으로 생성합니다.

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:468-769

async def generate_plan(self, state: StreamingAgentState) -> StreamingAgentState:
    """페르소나 관점과 의존성을 반영하여 단계별 실행 계획(Hybrid Model)을 수립합니다."""
    print(f"\n>> Orchestrator: 지능형 단계별 계획 수립 시작")
    query = state["original_query"]
    kst = pytz.timezone('Asia/Seoul')
    current_date_str = datetime.now(kst).strftime("%Y년 %m월 %d일")

    # 페르소나 정보 추출
    persona_name = state.get("persona", "기본")
    persona_info = self.personas.get(persona_name, {})
    persona_description = persona_info.get("description", "일반적인 분석가")
    print(f"  - 계획 수립에 '{persona_name}' 페르소나 관점 적용")

    # Graph 프리-체크 결과를 플래닝 프롬프트에 주입
    graph_probe = state.get("metadata", {}).get("graph_probe", {}) or {}
    gp_isfrom = graph_probe.get("has_isfrom", False)
    gp_nutr = graph_probe.get("has_nutrients", False)
    gp_doc = graph_probe.get("has_docrels", False)
    gp_docrels_preview = ""
    for d in graph_probe.get("docrels", [])[:3]:
        gp_docrels_preview += f"- {d.get('source','?')} - {d.get('target','?')}" \
                              f"{' (type:'+d.get('rel_type','')+')' if d.get('rel_type') else ''}" \
                              f"{' [doc:'+d.get('doc','')+']' if d.get('doc') else ''}\n"

    # 방대한 계획 수립 프롬프트 (약 280줄)
    planning_prompt = f"""
당신은 **'{persona_name}'의 유능한 AI 수석 보좌관**이자 **실행 계획 설계 전문가**입니다.
당신의 임무는 사용자의 요청을 **있는 그대로** 분석하고, **'{persona_name}'의 전문성을 활용하여 가장 효율적인 데이터 수집 계획**을 수립하는 것입니다.

**### Strict Adherence Mandate (엄격한 준수 명령) ###**
**1. 절대 사용자 요청을 확장하거나 추측하지 마세요.** 사용자가 "A와 B를 알려줘"라고 했다면, 오직 A와 B에 대한 정보만 수집해야 합니다. 관련될 수 있는 C(예: 시장 규모, 소비자 선호도)를 묻지 않았다면 절대 계획에 포함하지 마세요.
**2. 페르소나는 '어떻게(How)' 데이터를 수집하고 분석할지에 대한 관점이지, '무엇을(What)' 수집할지를 결정하는 역할이 아닙니다.** 페르소나의 관심사를 이유로 사용자가 묻지 않은 새로운 주제를 추가해서는 안 됩니다.
**3. 최종 목표는 사용자의 질문에 대한 '직접적인 답변'을 찾는 것입니다.** 광범위한 배경 조사를 하는 것이 아닙니다.
**4. 논리적 계획 수립 (How to ask): 하위 질문들의 선후 관계를 분석하여, 의존성이 있는 작업은 순차적으로, 없는 작업은 병렬로 처리하는 최적의 실행 단계를 설계하세요.

**사용자 원본 요청**: "{query}"
**현재 날짜**: {current_date_str}

---
**## 보유 도구 명세서 및 선택 가이드**

**1. rdb_search (PostgreSQL) - 1순위 활용**
   - **데이터 종류**: 정형 데이터 (테이블 기반: 식자재 **영양성분**, 농·축·수산물 **시세/가격/거래량** 등 수치 데이터).
   - **사용 시점**: 영양성분, 현재가격, 시세변동, 가격비교, 순위/평균/합계 등 **정확한 수치 연산**이 필요할 때.
   - **특징**: 날짜·지역·품목 컬럼으로 **필터/집계** 최적화. 다중 조건(where)과 group by, order by를 통한 **통계/랭킹** 질의에 적합.
   - **예시 질의**: "사과 비타민C 함량", "지난달 제주 감귤 평균가", "전복 가격 추이"

**2. vector_db_search (Elasticsearch) - 1순위 활용**
   - **데이터 종류**: 비정형 데이터 (뉴스기사, 논문, 보고서 전문).
   - **사용 시점**: 정책문서, 배경정보, 실무가이드 등 서술형 정보나 분석이 필요할 때.
   - **특징**: 의미기반 검색으로 질문의 맥락과 가장 관련성 높은 문서를 찾아줌.

**3. graph_db_search (Neo4j) - 1순위 활용**
   - **데이터 종류**: **관계형(그래프) 데이터**. 노드: 품목, **Origin(원산지)**, **Nutrient(영양소)**.
     관계: `(Ingredient)-[:isFrom]->(Origin)`, `(Food)-[:hasNutrient]->(Nutrient)`.
   - **사용 시점**: **품목 ↔ 원산지**, **품목 ↔ 영양소**처럼 **엔티티 간 연결**이 핵심일 때.
   - **특징**: 지식그래프 경로 탐색에 최적화. 질문은 **"A의 원산지", "A의 영양소"**처럼 **관계를 명시**할수록 정확도 상승.
   - **예시 질의**: "사과의 원산지", "오렌지의 영양소", "제주도의 감귤 원산지"

**4. pubmed_search - 1순위 활용 (학술 연구 필요시)**
   - **데이터 종류**: 최신 학술 논문 (pubmed 논문).
   - **사용 시점**: 신제품 개발, 과학적 근거, 최신 연구 동향, 대체식품 연구가 필요할 때.
   - **특징**: **반드시 쿼리를 영어로 번역 후 검색 필수.**
   - **예시 질의**: "Plant-based alternative meat development papers"

**5. web_search - 최신 정보 필수 시 우선 사용**
   - **데이터 종류**: 실시간 최신 정보, 시사 정보, 재해/재난 정보, 최근 뉴스.
   - **필수 사용**: 2025년 특정 월/일, 최근, 현재, 기상이변, 집중폭우, 재해 등이 포함된 질문
   - **예시 질의**: "2025년 7월 집중폭우 피해지역", "기상이변 농업 피해"

**도구 선택 우선순위:**
1. **⭐ 최신 정보/시사** → `web_search` **[최우선]**
2. **수치/통계 데이터** → `rdb_search`
3. **관계/분류 정보** → `graph_db_search`
4. **분석/연구 문서** → `vector_db_search`
5. **학술 논문/연구** → `pubmed_search`

**### Graph DB 사전 점검 결과(프리-체크 신호) — 반드시 계획에 반영하세요**
- isFrom(원산지) 관계 존재: {gp_isfrom}
- hasNutrient(영양성분) 관계 존재: {gp_nutr}
- 문서 관계(relation + doc) 존재: {gp_doc}
{('**docrels 예시**:' + gp_docrels_preview) if gp_docrels_preview else ''}

**반영 규칙(강제)**
1) {gp_isfrom} 이면: **원산지/특산품** 관련 하위질문은 `graph_db_search`를 포함할 것.
2) {gp_nutr} 이면: **정량(함량/순위)**가 필요하면 `rdb_search`, **연결(어떤 영양소)**만 볼 때는 `graph_db_search` 사용.
3) {gp_doc} 이면: **vector_db_search** 하위질문을 최소 1개 포함하되, docrels 키워드를 반영할 것.
4) 불필요한 도구는 추가하지 말 것. 프리-체크에서 False인 신호에 의존한 단계는 만들지 말 것.

---
**## 계획 수립을 위한 단계별 사고 프로세스 (반드시 준수할 것)**

**1단계: 사용자 요청 분해 (Decomposition)**
- 사용자의 원본 요청을 의미적, 논리적 단위로 나눕니다. 각 단위는 사용자가 명시적으로 요구한 하나의 정보 조각이어야 합니다.
- 예: "대체식품의 유형을 원료에 따라 구분하고, 미생물 발효 식품의 연구개발 현황을 분석해줘."
  - 단위 1: "대체식품의 유형을 원료에 따라 구분하여 정리"
  - 단위 2: "미생물 발효 식품의 연구개발 현황 분석 및 정리"

**2단계: 각 단위에 대한 하위 질문 생성**
- 1단계에서 분해된 각 단위를 해결하기 위해 필요한 구체적인 질문들을 생성합니다.
- 이 질문들은 페르소나의 전문성을 반영해야 합니다.
- 각각 완결된 형태의 구체적인 질문으로 분해합니다.
- 생성된 모든 하위 질문은 원본 요청의 핵심 맥락을 반드시 포함해야 합니다.

**3단계: 질문 간 의존성 분석 (가장 중요한 단계)**
- 분해된 질문들 간의 선후 관계를 분석합니다.
- **"어떤 질문이 다른 질문의 결과를 반드시 알아야만 제대로 수행될 수 있는가?"**를 판단합니다.

**4단계: 실행 단계 그룹화 (Grouping)**
- **Step 1**: 서로 의존성이 없는, 가장 먼저 수행되어야 할 병렬 실행 가능한 질문들을 배치합니다.
- **Step 2 이후**: 이전 단계의 결과(`[step-X의 결과]` 플레이스홀더 사용)를 입력으로 사용하는 의존성 있는 질문들을 배치합니다.

**5단계: 각 질문에 대한 최적 도구 선택 전략**
- '보유 도구 명세서'를 참고하여 각 하위 질문에 가장 적합한 도구를 **단 하나만** 신중하게 선택합니다.
- **중요**: 질문의 복잡성을 분석하여 **필요한 도구만 선택**합니다:
  * **단순 질문** → 1개 도구로 충분 (예: "사과 영양성분" → `rdb_search`)
  * **복합 질문** → 여러 도구 조합 필요
    - **"성분", "영양", "시세", "가격"** 포함 → `rdb_search`
    - **"원산지", "관계", "특산품"** 포함 → `graph_db_search`
    - **"분석", "연구", "보고서"** 포함 → `vector_db_search`
    - **"학술", "대체식품", "발효 기술"** 포함 → `pubmed_search`
    - **"최신", "2025년", "재해", "재난"** 포함 → `web_search`

**6단계: 최종 JSON 형식화**
- 위에서 결정된 모든 내용을 아래 '최종 출력 포맷'에 맞춰 JSON으로 작성합니다.
- **중요**: `sub_questions` 키는 반드시 `execution_steps` 배열의 각 요소 안에만 존재해야 합니다.

---
**## 계획 수립 예시**

**[예시 1: 단순 조회]**
**요청**: "사과의 영양성분과 칼로리 정보를 알려줘."
{{
    "title": "사과 영양성분 및 칼로리 정보",
    "reasoning": "RDB에서 직접 조회가 가능하므로, rdb_search 도구를 사용한 단일 단계 계획을 수립합니다.",
    "execution_steps": [
        {{
            "step": 1,
            "reasoning": "영양성분과 칼로리는 RDB에 정형화된 데이터이므로 rdb_search만으로 해결 가능합니다.",
            "sub_questions": [
                {{"question": "사과의 상세 영양성분 정보 및 칼로리", "tool": "rdb_search"}}
            ]
        }}
    ]
}}

**[예시 2: 병렬 조회]**
**요청**: "대체식품의 유형을 원료에 따라 구분하여 정리하고 이중에서 미생물 발효 식품의 연구개발 현황을 분석하고 정리해줘."
**페르소나**: "제품 개발 연구원"
{{
  "title": "원료별 대체식품 유형 및 미생물 발효 식품 R&D 현황 분석",
  "reasoning": "두 주제는 의존성이 없으므로 단일 단계에서 병렬로 정보를 수집하는 것이 가장 효율적입니다.",
  "execution_steps": [
    {{
      "step": 1,
      "reasoning": "대체식품의 기술적 분류와 미생물 발효 식품의 연구 동향에 대한 기반 정보를 병렬로 수집합니다.",
      "sub_questions": [
        {{
          "question": "원료(식물, 곤충, 배양육, 균류 등)에 따른 대체식품의 기술적 유형 분류 및 정의",
          "tool": "vector_db_search"
        }},
        {{
          "question": "microbial fermentation for alternative protein or food ingredients latest research papers",
          "tool": "pubmed_search"
        }},
        {{
          "question": "국내외 미생물 발효 기술 기반 대체식품 연구 개발 프로젝트 또는 상용화 사례",
          "tool": "vector_db_search"
        }}
      ]
    }}
  ]
}}

**[예시 3: 순차(의존성) 조회]**
**요청**: "2025년 7월과 8월의 집중폭우 피해지역에서 생산되는 주요 식재료들 목록과 생산지를 표로 정리해줘"
{{
    "title": "2025년 여름 집중폭우 피해지역의 주요 식재료 및 생산지 분석",
    "reasoning": "먼저 '피해 지역'을 특정하고(Step 1), 그 지역의 '주요 식재료와 생산지'를 찾아(Step 2) 최종적으로 종합 분석(Step 3)하는 순차적인 계획이 필요합니다.",
    "execution_steps": [
        {{
            "step": 1,
            "reasoning": "가장 먼저 최신 재해 정보를 통해 '집중폭우 피해 지역'을 명확히 특정해야 합니다.",
            "sub_questions": [
                {{"question": "2025년 7월 8월 대한민국 집중호우 피해 심각 지역 목록", "tool": "web_search"}}
            ]
        }},
        {{
            "step": 2,
            "reasoning": "Step 1에서 식별된 피해 지역을 바탕으로 해당 지역에서 주로 생산되는 식재료 정보를 수집합니다.",
            "sub_questions": [
                {{"question": "[step-1의 결과]로 확인된 피해 지역들 각각의 주요 생산 농축수산물(특산품) 목록", "tool": "graph_db_search"}},
                {{"question": "[step-1의 결과]로 확인된 피해 지역들의 농업 피해 현황 분석 보고서", "tool": "vector_db_search"}}
            ]
        }},
        {{
            "step": 3,
            "reasoning": "Step 2까지 수집된 정보를 종합하여, 사용자가 최종적으로 요청한 '피해 지역별 주요 식재료 및 생산지' 목록을 완성합니다.",
            "sub_questions": [
                {{"question": "[step-2의 결과]를 바탕으로, 집중호우 피해 지역과 해당 지역의 주요 식재료 및 생산지를 연결하여 표 형태로 요약", "tool": "vector_db_search"}}
            ]
        }}
    ]
}}

---
**## 최종 출력 포맷**

**중요 규칙**:
- **질문 복잡성에 따라 적절한 도구 개수 선택**: 단순하면 1개, 복합적이면 필요한 만큼만
- **pubmed_search 주의**: 영어로 쿼리를 번역한 후 question에 넣어야 함
- 반드시 아래 JSON 형식으로만 응답해야 합니다.

{{
    "title": "분석 보고서의 전체 제목",
    "reasoning": "이러한 단계별 계획을 수립한 핵심적인 이유.",
    "execution_steps": [
        {{
            "step": 1,
            "reasoning": "1단계 계획에 대한 설명. 병렬 실행될 작업들을 기술.",
            "sub_questions": [
                {{
                    "question": "1단계에서 병렬로 실행할 첫 번째 하위 질문",
                    "tool": "선택된 도구 이름"
                }},
                {{
                    "question": "1단계에서 병렬로 실행할 두 번째 하위 질문",
                    "tool": "선택된 도구 이름"
                }}
            ]
        }},
        {{
            "step": 2,
            "reasoning": "2단계 계획에 대한 설명. 1단계 결과에 의존함을 명시.",
            "sub_questions": [
                {{
                    "question": "2단계에서 실행할 하위 질문 (필요시 '[step-1의 결과]' 포함)",
                    "tool": "선택된 도구 이름"
                }}
            ]
        }}
    ]
}}
"""

    # LLM 호출 및 응답 처리
    try:
        response = await self.llm.ainvoke(planning_prompt)
        content = response.content.strip()

        # JSON 추출
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{.*\}', content, re.DOTALL)

        if json_match:
            json_str = json_match.group(1) if '```' in json_match.group(0) else json_match.group(0)
            plan = json.loads(json_str)
        else:
            raise ValueError("Valid JSON plan not found in response")

        print(f"  - 지능형 단계별 계획 생성 완료: {plan.get('title', '제목 없음')}")
        print("  - 계획 JSON:")
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        state["plan"] = plan

    except Exception as e:
        print(f"  - 지능형 계획 생성 실패, 단일 단계로 직접 검색 실행: {e}")
        # Fallback 계획
        state["plan"] = {
            "title": f"{query} 분석",
            "reasoning": "지능형 단계별 계획 수립에 실패하여, 사용자 원본 쿼리로 직접 검색을 실행합니다.",
            "execution_steps": [{
                "step": 1,
                "reasoning": "Fallback 실행",
                "sub_questions": [{"question": query, "tool": "vector_db_search"}]
            }]
        }

    return state
```

generate_plan 메서드는 사용자 요청을 분석하여 최적의 데이터 수집 계획을 동적으로 생성하는 핵심 로직입니다.

사용자가 선택한 페르소나(구매 담당자, 급식 운영 담당자, 마케팅 담당자, 제품 개발 연구원, 기본)에 따라 계획의 관점과 우선순위가 달라집니다. 예를 들어, 구매 담당자 페르소나는 원가와 시세 데이터에 집중하고, 제품 개발 연구원은 학술 논문과 성분 데이터를 우선시합니다.

Graph DB 프리체크 메커니즘은 본격적인 데이터 수집 전에 Graph DB를 사전 조회하여 원산지 관계, 영양성분 관계, 문서 관계 정보의 존재 여부를 파악합니다. 이 정보는 계획 수립 프롬프트에 주입되어 불필요한 검색을 배제하고 필요한 검색만 포함하도록 최적화합니다.

6단계 사고 프로세스는 체계적인 계획 수립을 보장합니다: (1) 사용자 요청을 의미적, 논리적 단위로 분해 → (2) 각 단위에 대한 구체적인 하위 질문 생성 → (3) 질문 간 의존성 분석 → (4) 병렬 실행 가능 여부에 따라 실행 단계 그룹화 → (5) 각 질문에 최적 도구 선택 → (6) JSON 형식화. 이를 통해 복잡한 요청도 논리적이고 효율적으로 처리할 수 있습니다.

#### 2.1.2 Graph DB 프리체크 메커니즘

계획 수립 전에 Graph DB를 사전 조회하여 **데이터 존재 여부를 미리 파악**합니다.

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:149-172

async def _probe_graph_data_locations(self, query: str) -> dict:
    """
    - neo4j_rag_tool.neo4j_graph_search()를 직접 호출하여
      '데이터가 그래프에 있는가'만 빠르게 확인 (문자열 리포트 기반)
    - 반환: {has_isfrom, has_nutrients, has_docrels, docrels(list), raw_report(str)}
    """
    try:
        report = await neo4j_graph_search(query)
        text = str(report) if report else ""
        low = text.lower()
        has_isfrom = ("원산지 관계" in text) or ("isfrom" in low)
        has_nutrients = ("영양성분 관계" in text) or ("hasnutrient" in low) or ("nutrient" in low)
        has_docrels = ("문서 관계 정보" in text) or ("relation" in low)
        docrels = self._parse_docrels_from_graph_report(text)[:5]
        return {
            "has_isfrom": bool(has_isfrom),
            "has_nutrients": bool(has_nutrients),
            "has_docrels": bool(has_docrels),
            "docrels": docrels,
            "raw_report": text[:8000],
        }
    except Exception as e:
        return {
            "error": str(e),
            "has_isfrom": False,
            "has_nutrients": False,
            "has_docrels": False,
            "docrels": [],
            "raw_report": ""
        }
```

_probe_graph_data_locations 메서드는 Graph DB 프리체크를 수행하여 데이터 위치 신호를 생성합니다.

이 메서드는 neo4j_graph_search 함수를 직접 호출하여 사용자 쿼리와 관련된 그래프 정보가 존재하는지 확인합니다. 반환된 리포트 텍스트에서 "원산지 관계", "영양성분 관계", "문서 관계 정보" 등의 키워드를 찾아 데이터 유무를 판단하고, 발견된 문서 관계(docrels)의 경우 최대 5개까지 추출하여 반환합니다.

프리체크 결과는 has_isfrom, has_nutrients, has_docrels 플래그로 반환되며, 이 정보는 generate_plan 메서드의 프롬프트에 주입됩니다. 환경변수 `DISABLE_PRECHECK=true`를 설정하여 프리체크를 비활성화할 수 있으며, 이 경우 모든 플래그가 False로 설정됩니다.

#### 2.1.3 의존성 주입 및 플레이스홀더 교체

이전 단계의 결과를 다음 단계의 입력으로 사용하는 **의존성 주입 메커니즘**을 구현했습니다.

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:457-467

def _inject_context_into_query(self, query: str, context: Dict[int, str]) -> str:
    """'[step-X의 결과]' 플레이스홀더를 실제 컨텍스트로 교체하는 헬퍼 함수"""
    match = re.search(r"\[step-(\d+)의 결과\]", query)
    if match:
        step_index = int(match.group(1))
        if step_index in context:
            print(f"  - {step_index}단계 컨텍스트 주입: '{context[step_index][:]}...'")
            # 플레이스홀더를 이전 단계의 요약 결과로 치환
            return query.replace(match.group(0), f"이전 단계 분석 결과: '{context[step_index]}'")
    return query
```

_inject_context_into_query 메서드는 의존성이 있는 질문들을 순차적으로 실행하기 위한 컨텍스트 주입 메커니즘을 제공합니다.

이 메서드는 쿼리 문자열에서 `[step-X의 결과]` 형식의 플레이스홀더를 찾아 실제 이전 단계의 실행 결과로 치환합니다. 정규표현식을 사용하여 플레이스홀더의 step 번호를 추출하고, context 딕셔너리에서 해당 step의 요약 결과를 가져와 "이전 단계 분석 결과: '{내용}'" 형식으로 교체합니다.

이를 통해 복잡한 다단계 분석 작업을 논리적 순서로 실행할 수 있습니다. 예를 들어, "집중폭우 피해지역을 먼저 찾고 → 그 지역의 주요 식재료를 조사하고 → 최종적으로 표로 정리"와 같은 순차적 워크플로우가 가능합니다.

#### 2.1.4 페르소나 기반 계획 커스터마이징

5가지 페르소나에 따라 계획과 보고서 스타일이 달라집니다.

```json
// 파일 위치: multiagent-rag-system/backend/app/core/agents/prompts/persona_prompts.json:1-27

{
  "구매 담당자": {
    "description": "식자재 구매 담당자로서, 원가, 시세, 수급 안정성에 중점을 둡니다. 신중하고 데이터 기반의 의사결정을 선호합니다.",
    "report_prompt": "당신은 식품 회사의 구매팀을 이끌고 있는 '이현우 과장'의 전문 AI 어시스턴트입니다. 다음 가이드라인에 따라 구매 담당자의 관점에서 정보를 분석하고 보고서 섹션을 작성하세요:\n1. **데이터 기반 분석**: 모든 주장은 구체적인 수치(시세, 가격 변동, 거래량)에 기반하여 논리적으로 전개하세요.\n2. **전문 용어 활용**: '산지', '경매가', '도매가', '수급 동향' 등 전문 용어를 사용하여 분석의 깊이를 더하세요.\n3. **리스크 및 전망 제시**: 현재 데이터에 기반하여 발생 가능한 리스크를 언급하고, 향후 수급 상황을 신중하게 전망하세요.\n4. **실행 가능한 요약**: 답변 마지막에는 항상 핵심 내용을 1~2줄로 요약하여 명확한 의사결정을 도와주세요.",
    "chart_prompt": "당신은 '구매 담당자'의 관점에서 데이터를 시각화하는 차트 생성 전문가입니다. **원가, 시세 변동, 거래량, 재고 수준** 등 구매 결정에 직접적인 영향을 미치는 데이터를 시각화하는 데 집중하세요. **시간에 따른 가격 추이**를 보여주는 **라인 차트**나 **지역별/품목별 가격 비교**를 위한 **막대 차트**가 가장 유용합니다."
  },
  "급식 운영 담당자": {
    "description": "급식 운영 담당자로서, 메뉴의 영양 균형, 원가, 직원 만족도를 중요하게 생각합니다. 실용적이고 친절한 해결책을 찾습니다.",
    "report_prompt": "당신은 사내 식당을 책임지는 급식 운영 전문가 '김소연 대리'의 전문 AI 어시스턴트입니다. 다음 가이드라인에 따라 급식 운영 담당자의 관점에서 정보를 분석하고 보고서 섹션을 작성하세요:\n1. **솔루션 중심 제안**: 문제나 질문에 대해 항상 구체적이고 실행 가능한 해결책을 제시하세요.\n2. **대체재 및 원가 분석**: 특정 식자재의 가격이 비싸거나 수급이 어려울 경우, 영양과 맛을 고려한 현실적인 대체재를 반드시 제안하고 원가 변화를 함께 분석해주세요.\n3. **영양 정보 기반 구성**: 답변에는 칼로리, 단백질, 비타민 등 주요 영양 정보를 포함하여 제안의 전문성을 높이세요.\n4. **구조화된 정보 제공**: 가능한 경우, 제안하는 내용을 주간 식단표나 레시피 카드 형식으로 구조화하여 이해를 도우세요.",
    "chart_prompt": "당신은 '급식 운영 담당자'의 관점에서 데이터를 시각화하는 차트 생성 전문가입니다. **메뉴별 영양 성분 비율(탄수화물, 단백질, 지방)**, **식자재별 원가 비교**, **월별 식자재 비용 추이** 등 예산 관리와 영양 균형에 도움이 되는 데이터를 시각화하세요."
  },
  "마케팅 담당자": {
    "description": "마케팅 담당자로서, 시장 트렌드, 소비자 데이터, 경쟁사 분석에 민감합니다. 창의적이고 설득력 있는 커뮤니케이션을 구사합니다.",
    "report_prompt": "당신은 시장을 선도하는 마케터 '정하진 팀장'의 전문 AI 어시스턴트입니다. 다음 가이드라인에 따라 마케팅 담당자의 관점에서 정보를 분석하고 보고서 섹션을 작성하세요:\n1. **인사이트 중심의 어조**: 단순 정보 나열이 아닌, 데이터가 의미하는 바와 숨겨진 기회를 발견하여 설득력 있게 전달하세요.\n2. **소비자 데이터 분석**: 모든 데이터를 소비자 행동(SNS 버즈량, 검색 트렌드, 구매 후기)과 연결하여 해석하세요.\n3. **전략적 제안**: 분석으로 끝나지 않고, 구체적인 마케팅 액션 아이템을 제안하며 마무리하세요.",
    "chart_prompt": "당신은 '마케팅 담당자'의 관점에서 데이터를 시각화하는 차트 생성 전문가입니다. **시장 트렌드 변화, 소비자 관심도, 연령대별 선호도, 경쟁사 시장 점유율** 등 마케팅 전략 수립에 영감을 주는 데이터를 시각화하세요."
  },
  "제품 개발 연구원": {
    "description": "제품 개발 연구원으로서, 새로운 원료, 기술, 과학적 근거에 기반한 제품 개발에 집중합니다. 정확하고 객관적인 정보를 추구합니다.",
    "report_prompt": "당신은 신제품 개발을 책임지는 R&D 전문가 '장도윤 연구원'의 전문 AI 어시스턴트입니다. 다음 가이드라인에 따라 제품 개발 연구원의 관점에서 정보를 분석하고 보고서 섹션을 작성하세요:\n1. **객관적 사실 전달**: 감정이나 추측을 배제하고, '논문에 따르면', '실험 결과', '성분 분석에 의하면' 등 과학적 사실과 데이터만을 전달하세요.\n2. **정확한 데이터 제시**: 원료의 성분, 함량, 기능성 데이터 등을 정확한 수치와 단위(mg, %, g 등)를 사용하여 정량적으로 제시하세요.\n3. **참고 문헌 기반**: 정보의 신뢰도를 높이기 위해, 가능하다면 참고한 논문, 특허, R&D 보고서 등의 출처를 명시적으로 언급해주세요.",
    "chart_prompt": "당신은 '제품 개발 연구원'의 관점에서 데이터를 시각화하는 차트 생성 전문가입니다. **원료별 성분 함량 비교, 제품별 영양성분 데이터, 실험 결과 데이터** 등 과학적 사실을 명확하게 보여주는 데이터를 시각화하세요."
  },
  "기본": {
    "description": "특정 역할이 지정되지 않았을 때 사용되는 AI 어시스턴트입니다. 데이터에 기반하여 명확하고 구조화된 답변을 제공합니다.",
    "report_prompt": "당신은 사용자의 요청을 명확하게 분석하고, 데이터를 기반으로 객관적인 정보를 전달하는 전문 AI 어시스턴트입니다. 답변 시 다음 가이드라인을 따라주세요:\n1. **명확성과 객관성**: 추측이나 주관적인 의견을 배제하고, 주어진 데이터를 바탕으로 사실에 입각하여 답변하세요.\n2. **논리적 구조**: 정보를 효과적으로 전달하기 위해 글머리 기호(-), 번호 매기기, **굵은 글씨** 등 마크다운을 사용하여 내용을 명확하게 구조화하세요.\n3. **전문적인 톤앤매너**: 친절하지만 전문적인 어조를 유지하며, 사용자가 이해하기 쉬운 용어를 사용하세요.",
    "chart_prompt": "당신은 데이터 시각화 전문가입니다. 주어진 데이터의 특징을 가장 잘 나타낼 수 있는 명확하고 이해하기 쉬운 차트를 생성하세요. 데이터 간의 **비교, 추이, 비율** 등을 효과적으로 보여주는 **막대, 라인, 파이 차트** 등을 활용하여 가장 적절한 시각화를 제공해주세요."
  }
}
```

persona_prompts.json 파일은 5가지 페르소나의 특성과 작성 지침을 정의합니다.

각 페르소나는 description, report_prompt, chart_prompt 3가지 속성으로 구성됩니다. description은 페르소나의 역할과 관심사를 정의하고, report_prompt는 보고서 섹션 작성 시 적용할 가이드라인을 제공하며, chart_prompt는 차트 생성 시 중점을 둘 데이터 유형을 명시합니다.

예를 들어, 구매 담당자는 원가, 시세, 거래량 데이터를 중시하며 데이터 기반 분석과 리스크 전망을 제시하는 보고서를 작성합니다. 반면 마케팅 담당자는 소비자 행동, 시장 트렌드, 경쟁사 분석에 집중하며 인사이트 중심의 설득력 있는 보고서를 작성합니다. 이처럼 같은 데이터라도 페르소나에 따라 전혀 다른 관점과 스타일의 보고서가 생성됩니다.

---

### 2.2 비동기 병렬 처리 최적화

#### 2.2.1 Multi-RAG 병렬 검색 (DataGatherer Agent)

**DataGathererAgent**는 여러 데이터 소스를 **동시에 병렬로 검색**하여 처리 시간을 획기적으로 단축합니다.

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:892-1011

async def execute_parallel(self, tasks: List[Dict[str, Any]], state: Dict[str, Any] = None) -> Dict[str, List[SearchResult]]:
    """여러 데이터 수집 작업을 병렬로 실행합니다."""

    # Graph-to-Vector 설정 확인
    import os
    disable_graph_to_vector = os.environ.get("DISABLE_GRAPH_TO_VECTOR", "false").lower() == "true"

    # 작업 분류
    vector_tasks = [task for task in tasks if task.get("tool") == "vector_db_search"]
    graph_tasks = [task for task in tasks if task.get("tool") == "graph_db_search"]
    other_tasks = [task for task in tasks if task.get("tool") not in ["vector_db_search", "graph_db_search"]]

    if not disable_graph_to_vector and vector_tasks:
        # Graph-to-Vector 순차 실행 모드
        print(f"\n>> DataGatherer: Graph-to-Vector 활성화 - 순차 실행 모드")

        # 1단계: Graph 검색 실행
        graph_coroutines = [self.execute(task.get("tool"), task.get("inputs", {}), state) for task in graph_tasks]
        graph_results = await asyncio.gather(*graph_coroutines, return_exceptions=True)

        # 2단계: Vector 검색 실행 (Graph 정보 반영)
        vector_coroutines = [self.execute(task.get("tool"), task.get("inputs", {}), state) for task in vector_tasks]
        vector_results = await asyncio.gather(*vector_coroutines, return_exceptions=True)

        # 3단계: 기타 검색 병렬 실행
        other_coroutines = [self.execute(task.get("tool"), task.get("inputs", {}), state) for task in other_tasks]
        other_results = await asyncio.gather(*other_coroutines, return_exceptions=True)

        # ... (결과 정리 코드 중략) ...
    else:
        # 기존 병렬 실행 모드
        print(f"\n>> DataGatherer: {len(tasks)}개 작업 병렬 실행 시작")

        # 각 작업에 대해 execute 코루틴을 생성
        coroutines = [self.execute(task.get("tool"), task.get("inputs", {}), state) for task in tasks]

        # asyncio.gather를 사용하여 모든 작업을 동시에 실행
        results = await asyncio.gather(*coroutines, return_exceptions=True)

    # 결과 정리
    organized_results = {}
    for i, task in enumerate(tasks):
        tool_name = task.get("tool", f"unknown_tool_{i}")
        result = results[i]

        if isinstance(result, Exception):
            print(f"  - {tool_name} 병렬 실행 오류: {result}")
            organized_results[f"{tool_name}_{i}"] = []
        else:
            search_results, optimized_query = result
            organized_results[f"{tool_name}_{i}"] = search_results

    return organized_results
```

DataGathererAgent의 execute_parallel 메서드는 여러 데이터 수집 작업을 효율적으로 병렬 실행합니다.

asyncio.gather를 활용하여 모든 검색 작업을 동시에 실행하고 I/O 대기 시간을 최소화합니다. return_exceptions=True 옵션을 사용하여 개별 도구의 실패가 전체 검색을 중단시키지 않도록 예외를 격리합니다.

환경변수 DISABLE_GRAPH_TO_VECTOR로 제어되는 Graph-to-Vector 모드를 지원합니다. 이 모드가 활성화되면 Graph 검색을 먼저 실행하고, 그 결과를 Vector 검색에 반영한 후, 나머지 도구들을 병렬로 실행하는 3단계 순차-병렬 하이브리드 방식으로 동작합니다. 이를 통해 Graph에서 발견된 키워드와 관계 정보를 Vector 검색에 활용하여 검색 품질을 향상시킬 수 있습니다.

#### 2.2.2 ThreadPoolExecutor를 통한 비동기 실행

Blocking I/O 작업(Web Scraping, 외부 API 호출 등)을 위해 **ThreadPoolExecutor**를 활용합니다.

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:38-39

from concurrent.futures import ThreadPoolExecutor

# 전역 ThreadPoolExecutor 생성 (재사용으로 성능 향상)
_global_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="search_worker")
```

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:1113-1125

async def _web_search(self, query: str) -> List[SearchResult]:
    """웹 검색 실행 - 안정성 강화"""
    try:
        print(f"  - 웹 검색 실행 쿼리: {query}")

        # 전역 ThreadPoolExecutor 사용하여 병렬 처리
        loop = asyncio.get_event_loop()
        result_text = await loop.run_in_executor(
            _global_executor,  # 전역 executor 사용
            debug_web_search,
            query
        )

        # ... (결과 파싱 및 SearchResult 변환 코드 중략) ...

        return search_results
    except Exception as e:
        print(f"Web search 오류: {e}")
        return []
```

ThreadPoolExecutor는 Blocking I/O 작업을 비동기 환경에서 효율적으로 처리하기 위해 사용됩니다.

worker_agents.py 파일의 전역 스코프에서 _global_executor를 생성하여 앱 전체에서 하나의 ThreadPoolExecutor를 공유합니다. max_workers=16으로 설정하여 동시에 최대 16개의 검색 작업을 병렬로 처리할 수 있습니다.

_web_search, _arxiv_search, _pubmed_search 등의 메서드에서는 loop.run_in_executor를 통해 동기 함수(debug_web_search, arxiv_search_fn 등)를 비동기로 실행합니다. 전역 executor를 재사용함으로써 스레드를 매번 생성/파괴하는 오버헤드를 줄이고, 리소스를 효율적으로 관리할 수 있습니다.

#### 2.2.3 보고서 섹션별 병렬 생성 (Processor Agent)

모든 섹션을 **Producer-Consumer 패턴으로 동시 생성**하되, 사용자에게는 **순차적으로 스트리밍**합니다.

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:1219-1338

# Producer-Consumer 패턴을 위한 Queue 생성
section_queues = [asyncio.Queue() for _ in range(len(structure))]
producer_tasks = []

# Producer: 각 섹션을 병렬로 생성하는 내부 함수
async def _produce_section_content(section_index: int):
    """각 섹션을 독립적으로 생성하고 Queue에 넣기"""
    section_info = structure[section_index]
    q = section_queues[section_index]
    use_contents = section_info.get("use_contents", [])

    try:
        # ProcessorAgent의 스트리밍 생성기 호출
        async for chunk in self.processor.generate_section_streaming(
            section_info, full_data_dict, query, use_contents,
            awareness_context=awareness_context,
            state=state
        ):
            # Abort 체크
            if run_manager and run_manager.is_abort_requested(state.get("metadata", {}).get("run_id")):
                await q.put(None)  # 스트림 종료
                return

            await q.put(chunk)  # 받은 청크를 큐에 넣음
    except Exception as e:
        # 오류 발생 시 에러 메시지를 큐에 넣음
        error_message = f"*'{section_info.get('section_title', '')}' 섹션 생성 중 오류가 발생했습니다: {str(e)}*\n\n"
        await q.put(error_message)
        print(f">> 섹션 생성(Producer) 오류: {error_message}")
    finally:
        # 스트림이 끝나면 None을 넣어 종료를 알림
        await q.put(None)

# 모든 섹션에 대한 Producer Task를 생성하고 실행
for i in range(len(structure)):
    task = asyncio.create_task(_produce_section_content(i))
    producer_tasks.append(task)

# Consumer: 순차적으로 Queue에서 결과를 꺼내 스트리밍
for i, section in enumerate(structure):
    section_title = section.get('section_title', f'섹션 {i+1}')
    use_contents = section.get("use_contents", [])

    yield self._create_status_event("GENERATING", "GENERATE_SECTION_START", f"'{section_title}' 섹션 생성 중...", details={
        "section_index": i, "section_title": section_title, "using_indices": use_contents
    })

    buffer = ""
    section_full_content = ""

    # 해당 섹션의 Queue에서 결과가 나올 때까지 대기
    while True:
        chunk = await section_queues[i].get()

        # None을 받으면 해당 섹션 스트리밍이 끝난 것
        if chunk is None:
            break

        buffer += chunk
        section_full_content += chunk

        # 차트 생성 마커가 있는지 확인
        if "[GENERATE_CHART]" in buffer:
            parts = buffer.split("[GENERATE_CHART]", 1)

            if parts[0]:
                yield {"type": "content", "data": {"chunk": parts[0]}}

            buffer = parts[1]

            yield self._create_status_event("GENERATING", "GENERATE_CHART_START", f"'{section_title}' 차트 생성 중...")

            # 차트 생성 (이전까지 생성된 context를 차트 생성에 전달)
            chart_context = {
                "previous_sections": accumulated_context["generated_sections"],
                "previous_charts": accumulated_context["chart_data"],
                "current_section_content": buffer
            }
            state['chart_context'] = chart_context

            chart_data = None
            async for result in self.processor.process("create_chart_data", section_data_list, section_title, buffer, "", chart_yield_callback, state=state):
                if result.get("type") == "chart":
                    chart_data = result.get("data")
                    accumulated_context["chart_data"].append({"section": section_title, "chart": chart_data})
                    break

            if chart_data and "error" not in chart_data:
                current_chart_index = state.get('chart_counter', 0)
                chart_placeholder = f"\n\n[CHART-PLACEHOLDER-{current_chart_index}]\n\n"
                yield {"type": "content", "data": {"chunk": chart_placeholder}}
                yield {"type": "chart", "data": chart_data}
                state['chart_counter'] = current_chart_index + 1
            else:
                yield {"type": "content", "data": {"chunk": "\n\n*[데이터 부족으로 차트 표시가 제한됩니다]*\n\n"}}

        else:
            # 텍스트 스트리밍을 위한 버퍼 관리
            potential_chart_marker = "[GENERATE_CHART]"
            # 버퍼 끝에 마커 일부가 걸쳐있는지 확인
            has_partial_marker = any(potential_chart_marker.startswith(buffer[-j:])
                for j in range(1, min(len(buffer) + 1, len(potential_chart_marker) + 1)))

            # 부분 마커가 없으면 버퍼를 전송
            if not has_partial_marker:
                yield {"type": "content", "data": {"chunk": buffer}}
                buffer = ""
```

이 구현은 **Producer-Consumer 패턴**을 활용하여 보고서의 여러 섹션을 효율적으로 생성하고 전송합니다. asyncio.Queue를 사용하여 섹션을 생성하는 Producer와 이를 순차적으로 전송하는 Consumer를 분리함으로써, 모든 섹션을 asyncio.create_task로 동시에 생성하면서도 사용자에게는 순서대로 전달되어 자연스러운 읽기 경험을 제공합니다.

각 섹션은 독립적으로 생성되므로 하나의 섹션에서 오류가 발생하더라도 전체 보고서 생성에 영향을 주지 않습니다. Producer는 생성한 청크를 각 섹션의 Queue에 넣고, Consumer는 섹션 순서대로 Queue에서 청크를 꺼내 사용자에게 전송합니다. 이 과정에서 `[GENERATE_CHART]` 마커를 감지하여 적절한 시점에 차트를 생성하며, 마커가 청크 경계에 걸치는 경우를 처리하기 위한 부분 마커 감지 로직도 포함되어 있습니다.

중단 요청이 들어오면 Producer에서 즉시 이를 감지하여 None을 Queue에 넣어 스트림을 종료하며, 섹션 생성 중 예외가 발생하면 에러 메시지를 Queue에 넣어 사용자에게 알립니다.

---

### 2.3 스트리밍 최적화

#### 2.3.1 Server-Sent Events (SSE) 점진적 전송

FastAPI를 통해 **SSE(Server-Sent Events)** 방식으로 실시간 스트리밍을 구현했습니다.

```python
# 파일 위치: multiagent-rag-system/backend/app/main.py:640-648

def server_sent_event(event_type: str, data: dict) -> str:
    """Server-Sent Events (SSE) 형식에 맞는 문자열을 생성합니다."""
    import json

    json_data = json.dumps(data, ensure_ascii=False)
    sse_message = f"event: {event_type}\ndata: {json_data}\n\n"
    return sse_message
```

```python
# 파일 위치: multiagent-rag-system/backend/app/main.py:332-495

@app.post("/research")
async def research_endpoint(request: ResearchRequest):
    """보고서 생성 엔드포인트 (SSE 스트리밍)"""

    async def event_generator():
        async for event in orchestrator.execute_report_workflow(state):
            if event["type"] == "content":
                # 콘텐츠 청크를 SSE 형식으로 전송
                yield server_sent_event("content", {
                    "chunk": event["data"]["chunk"],
                    "session_id": state.session_id
                })
            elif event["type"] == "status":
                # 상태 업데이트 전송
                yield server_sent_event("status", event["data"])

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

SSE 프로토콜은 `event: {type}\ndata: {json}\n\n` 형식을 사용하여 데이터를 전송하며, 데이터가 생성되는 즉시 사용자에게 전달됩니다. 이를 통해 사용자는 보고서 생성이 완료되기를 기다리지 않고 생성되는 내용을 실시간으로 확인할 수 있습니다. 프론트엔드는 이러한 청크를 받는 즉시 화면에 렌더링하여 점진적으로 보고서를 표시합니다.

#### 2.3.2 Abort 메커니즘 (중단 처리)

사용자가 요청을 취소할 수 있는 **Abort 메커니즘**을 구현했습니다.

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:1013-1016

for i, step_info in enumerate(execution_steps):
    # Abort 체크
    if run_manager and run_manager.is_abort_requested(state.get("metadata", {}).get("run_id")):
        yield {"type": "abort", "data": {"message": "작업이 중단되었습니다"}}
        return
```

시스템은 각 단계 실행 전에 중단 요청 여부를 확인하여, 사용자가 요청을 취소하면 즉시 워크플로우를 종료하고 사용자에게 알립니다. 이를 통해 불필요한 계산과 API 호출을 방지하여 리소스를 절약합니다. run_manager는 외부에서 실행 상태를 관리하는 매니저 객체로, 이를 통해 중단 요청을 감지합니다.

---

### 2.4 캐싱 및 리소스 재사용

#### 2.4.1 모델 Lazy Loading & 캐싱

AI 모델을 **한 번만 로드**하고 전역적으로 재사용합니다.

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:116-121

class OrchestratorAgent:
    def __init__(self, model: str = "gemini-2.5-flash-lite", temperature: float = 0.2):
        # 모델 한 번만 초기화
        self.llm = ChatGoogleGenerativeAI(model=model, temperature=temperature)
        self.llm_openai_mini = ChatOpenAI(model="gpt-4o-mini", temperature=temperature)

        # Worker Agents도 한 번만 생성
        self.data_gatherer = DataGathererAgent()
        self.processor = ProcessorAgent()
```

AI 모델은 앱 시작 시 한 번만 로드되며, 이후 모든 요청에서 캐시된 모델을 재사용합니다. 이를 통해 1.8GB의 메모리를 효율적으로 사용하며, DataGathererAgent와 ProcessorAgent도 한 번만 생성하여 재사용합니다.

---

## 3. 에이전트 구성요소별 개발 상세

### 3.1 Triage Agent (요청 분류)

**위치**: [orchestrator.py:37-110](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L37-L110)

**역할**: 사용자 요청을 분석하여 `chat` 또는 `task`로 분류합니다.

**구현 코드**:

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:37-110

class TriageAgent:
    """요청 분류 및 라우팅 담당 Agent"""

    def __init__(self, model: str = "gemini-2.5-flash-lite", temperature: float = 0.1):
        self.llm = ChatGoogleGenerativeAI(model=model, temperature=temperature)

    async def classify_request(self, query: str, state: StreamingAgentState) -> StreamingAgentState:
        """요청을 분석하여 flow_type 결정"""
        session_id = state.get("session_id", "unknown")
        logger = get_session_logger(session_id, "TriageAgent")
        logger.info(f"요청 분류 시작 - '{query}'")

        classification_prompt = f"""
사용자 요청을 분석하여 적절한 처리 방식을 결정하세요:

사용자 요청: {query}

분류 기준:
1. **chat**: 간단한 질문, 일반적인 대화, Web Search나 vector db 조회로 답변 가능한 경우
   - 예: "안녕하세요", "최근 ~ 시세 알려줘", "이 링크 내용이 뭐야?"

2. **task**: 복합적인 분석, 데이터 수집, 리포트 생성이 필요한 경우
   - 예: "~를 분석해줘", "보고서 작성", "상세한 분석 보고서 생성해줘"

JSON으로 응답:
{{
    "flow_type": "chat" 또는 "task",
    "reasoning": "분류 근거 설명"
}}
        """

        try:
            response = await self.llm.ainvoke(classification_prompt)
            response_content = response.content.strip()

            # JSON 응답 추출
            classification = json.loads(response_content)

            # state 업데이트
            state["flow_type"] = classification["flow_type"]
            state["metadata"].update({
                "triage_reasoning": classification["reasoning"],
                "classified_at": datetime.now().isoformat()
            })

            logger.info(f"분류 결과: {classification['flow_type']}")

        except Exception as e:
            logger.error(f"분류 실패, 기본값(task) 적용: {e}")
            state["flow_type"] = "task"  # 기본값

        return state
```

TriageAgent는 사용자 요청을 'chat' 또는 'task' 플로우로 분류하는 중요한 역할을 담당합니다.

Temperature 파라미터를 0.1로 낮게 설정하여 일관된 분류 결과를 보장합니다. LLM 응답을 JSON 형식으로 요청하여 파싱 안정성을 높이고, 필수 필드(flow_type, reasoning)가 누락된 경우를 검증합니다.

분류 실패 시에는 기본값으로 'task'를 설정하여 복잡한 요청이 단순 응답으로 처리되는 것을 방지합니다. 이는 시스템의 안정성과 사용자 경험을 보장하기 위한 설계입니다.

---

### 3.2 Orchestrator Agent (계획 수립 & 조율)

**위치**: [orchestrator.py:113-2051](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L113-L2051)

**역할**:
- 리서치 계획 수립
- DataGatherer & Processor 조율
- 워크플로우 실행

#### 3.2.1 워크플로우 실행 (execute_report_workflow)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:916-1115

async def execute_report_workflow(self, state: StreamingAgentState, run_manager=None) -> AsyncGenerator[str, None]:
    """단계별 계획에 따라 순차적, 병렬적으로 데이터 수집 및 보고서 생성"""
    query = state["original_query"]

    # 0. 메모리 컨텍스트 추출 및 요약 생성
    conversation_history = state.get("metadata", {}).get("conversation_history", [])
    conversation_id = state.get("conversation_id", "unknown")
    memory_summary = self._generate_memory_summary_for_report(conversation_history, query)

    if memory_summary:
        print(f"🧠 채팅방 {conversation_id}: 보고서에 메모리 요약 포함 ({len(conversation_history)}개 메시지)")
    else:
        print(f"🧠 채팅방 {conversation_id}: 메모리 없음 (새 대화 또는 연속성 없음)")

    # 페르소나 확인 및 상태 알림
    selected_persona = state.get("persona")
    if not selected_persona or selected_persona not in self.personas:
        print(f"경고: 유효하지 않거나 지정되지 않은 페르소나 ('{selected_persona}'). '기본'으로 설정합니다.")
        selected_persona = "기본"
        state["persona"] = selected_persona

    yield self._create_status_event("PLANNING", "PERSONA_CONFIRMED", f"'{selected_persona}' 페르소나로 보고서 생성을 시작합니다.")

    # 차트 카운터 및 누적 context 초기화
    state['chart_counter'] = 0
    accumulated_context = {
        "generated_sections": [],  # 생성된 섹션 내용들
        "chart_data": [],  # 생성된 차트 데이터들
        "insights": [],  # 각 섹션의 주요 인사이트
        "persona": selected_persona  # 선택된 페르소나
    }
    state['accumulated_context'] = accumulated_context

    # 1. Graph DB 프리-체크 (환경변수로 제어)
    disable_precheck = os.environ.get("DISABLE_PRECHECK", "false").lower() == "true"

    if disable_precheck:
        # 프리-체크 비활성화
        yield self._create_status_event("PLANNING", "GRAPH_PROBE_DISABLED", "그래프 프리-체크 비활성화됨")
        graph_probe = {
            "has_isfrom": False,
            "has_nutrients": False,
            "has_docrels": False,
            "docrels": [],
            "raw_report": "프리-체크 비활성화됨",
            "precheck_disabled": True
        }
    else:
        # 프리-체크 활성화: 실제 그래프 조회
        yield self._create_status_event("PLANNING", "GRAPH_PROBE_START", "그래프에서 데이터 위치 사전 점검 중...")
        graph_probe = await self._probe_graph_data_locations(query)
        graph_probe["precheck_disabled"] = False

        if graph_probe.get("error"):
            yield self._create_status_event("PLANNING", "GRAPH_PROBE_ERROR", f"그래프 프리-체크 실패: {graph_probe['error']}")
        else:
            # 사용자 친화적인 메시지로 변환
            isfrom_status = "발견됨" if graph_probe['has_isfrom'] else "없음"
            nutrient_status = "발견됨" if graph_probe['has_nutrients'] else "없음"
            docrel_status = "발견됨" if graph_probe['has_docrels'] else "없음"
            msg = f"Pre-Check 완료 - 원산지: {isfrom_status} / 영양성분: {nutrient_status} / 문서: {docrel_status}"
            yield self._create_status_event("PLANNING", "GRAPH_PROBE_COMPLETE", msg)

    state.setdefault("metadata", {}).update({"graph_probe": graph_probe})

    # 2. 계획 수립 (그래프 신호를 프롬프트에 반영)
    yield self._create_status_event("PLANNING", "GENERATE_PLAN_START", "분석 계획 수립 중...")
    state_with_plan = await self.generate_plan(state)
    plan = state_with_plan.get("plan", {})
    yield {"type": "plan", "data": {"plan": plan}}
    yield self._create_status_event("PLANNING", "GENERATE_PLAN_COMPLETE", "분석 계획 수립 완료.", details={
        "plan_title": plan.get('title'),
        "step_count": len(plan.get("execution_steps", []))
    })

    # 3. 단계별 데이터 수집 실행
    execution_steps = plan.get("execution_steps", [])
    final_collected_data: List[SearchResult] = []
    step_results_context: Dict[int, str] = {}
    cumulative_selected_indexes: List[int] = []

    for i, step_info in enumerate(execution_steps):
        current_step_index = step_info["step"]

        # Abort 체크
        if run_manager and run_manager.is_abort_requested(state.get("metadata", {}).get("run_id")):
            yield {"type": "abort", "data": {"message": "작업이 중단되었습니다"}}
            return

        yield self._create_status_event("GATHERING", "STEP_START", f"데이터 수집 ({i + 1}/{len(execution_steps)}) 시작.")

        # 의존성 주입
        tasks_for_this_step = []
        for sq in step_info.get("sub_questions", []):
            injected_query = self._inject_context_into_query(sq["question"], step_results_context)
            tasks_for_this_step.append({"tool": sq["tool"], "inputs": {"query": injected_query}})

        # 병렬 데이터 수집
        step_collected_data: List[SearchResult] = []
        async for event in self.data_gatherer.execute_parallel_streaming(tasks_for_this_step, state=state):
            if event["type"] == "search_results":
                yield event
            elif event["type"] == "collection_complete":
                collected_dicts = event["data"]["collected_data"]
                step_collected_data = [SearchResult(**data_dict) for data_dict in collected_dicts]

        # 컨텍스트 저장 (다음 단계를 위해)
        summary_of_step = " ".join([res.content for res in step_collected_data])
        step_results_context[current_step_index] = summary_of_step[:2000]
        final_collected_data.extend(step_collected_data)

        # 데이터 선별
        if len(final_collected_data) > 0:
            yield self._create_status_event("PROCESSING", "FILTER_DATA_START", "수집 데이터 선별 중...")
            selected_indexes = await self._select_relevant_data_for_step(step_info, final_collected_data, state["original_query"])
            yield self._create_status_event("PROCESSING", "FILTER_DATA_COMPLETE", f"핵심 데이터 {len(selected_indexes)}개 선별 완료.")
            cumulative_selected_indexes = sorted(list(set(cumulative_selected_indexes + selected_indexes)))

    # 4. 전체 데이터 딕셔너리 생성 및 전송
    print(f"\n>> 전체 데이터 딕셔너리 생성 및 전송")
    full_data_dict = {}
    for idx, data in enumerate(final_collected_data):
        full_data_dict[idx] = {
            "title": getattr(data, 'title', 'No Title'),
            "content": getattr(data, 'content', ''),
            "source": getattr(data, 'source', 'Unknown'),
            "url": getattr(data, 'url', ''),
            "source_url": getattr(data, 'source_url', ''),
            "score": getattr(data, 'score', 0.0),
            "document_type": getattr(data, 'document_type', 'unknown')
        }

    # 전체 데이터 딕셔너리를 프론트엔드로 전송
    yield {"type": "full_data_dict", "data": {"data_dict": full_data_dict}}

    # 5. 보고서 구조 설계
    yield self._create_status_event("PROCESSING", "DESIGN_STRUCTURE_START", "보고서 구조 설계 중...")
    design = None
    async for result in self.processor.process("design_report_structure", final_collected_data, cumulative_selected_indexes, query, state=state):
        if result.get("type") == "result":
            design = result.get("data")
            break

    if not design or "structure" not in design or not design["structure"]:
        yield {"type": "error", "data": {"message": "보고서 구조 설계에 실패했습니다."}}
        return

    # ... (이후 보고서 생성 로직 중략) ...
```

이 워크플로우는 이전 대화 히스토리를 요약하여 보고서에 메모리 컨텍스트를 통합하고, 선택된 페르소나를 검증하여 사용자에게 알립니다. 생성된 섹션, 차트, 인사이트는 누적 컨텍스트로 관리되며, Graph DB 프리체크는 `DISABLE_PRECHECK` 환경변수로 제어할 수 있습니다. 수집된 모든 데이터는 인덱스 기반 딕셔너리로 변환되어 프론트엔드에 전송됩니다.

전체 워크플로우는 메모리 통합 → 프리체크 → 계획 → 수집 → 구조 설계의 5단계로 진행되며, `[step-1의 결과]` 같은 플레이스홀더를 실제 데이터로 치환하는 의존성 주입을 지원합니다. 각 단계마다 상태를 SSE로 실시간 스트리밍하며, 각 단계 실행 전에 중단 요청을 확인하여 Abort를 지원합니다.

---

### 3.3 DataGatherer Agent (데이터 수집)

**위치**: [worker_agents.py:54-1892](multiagent-rag-system/backend/app/core/agents/worker_agents.py#L54-L1892)

**역할**: Multi-RAG 데이터 수집 및 검색 최적화

**지원 검색 도구 (7개)**:
1. web_search - 최신 정보 및 시사 뉴스
2. vector_db_search - Elasticsearch 기반 문서 검색
3. graph_db_search - Neo4j 기반 관계 탐색
4. rdb_search - PostgreSQL 기반 정형 데이터 조회
5. arxiv_search - 학술 논문 검색
6. pubmed_search - 의학 논문 검색
7. scrape_content - URL 콘텐츠 스크래핑

**핵심 구현**:

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:54-103

class DataGathererAgent:
    """데이터 수집 및 쿼리 최적화 전담 Agent"""

    def __init__(self, model: str = "gemini-2.5-flash-lite", temperature: float = 0):
        self.llm = ChatGoogleGenerativeAI(model=model, temperature=temperature)

        # Fallback 모델들
        self.llm_gemini_backup = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=ModelFallbackManager.GEMINI_KEY_2
        )
        self.llm_openai_mini = ChatOpenAI(model="gpt-4o-mini", temperature=temperature)

        # 도구 매핑 설정
        self.tool_mapping = {
            "web_search": self._web_search,
            "vector_db_search": self._vector_db_search,
            "graph_db_search": self._graph_db_search,
            "arxiv_search": self._arxiv_search,
            "pubmed_search": self._pubmed_search,
            "rdb_search": self._rdb_search,
            "scrape_content": self._scrape_content,
        }
```

DataGathererAgent는 3단계 Fallback 메커니즘(Gemini Key 1 → Gemini Key 2 → OpenAI)을 통해 안정적인 서비스를 제공합니다. 7개의 검색 도구를 하나의 Agent에서 통합 관리하며, 모든 도구는 `List[SearchResult]`를 반환하는 표준화된 인터페이스를 따릅니다. 도구 이름을 메서드와 매핑하여 동적으로 호출할 수 있도록 구성되어 있으며, asyncio.gather를 통해 여러 도구를 병렬로 실행하여 효율적인 데이터 수집이 가능합니다.

---

### 3.4 Processor Agent (보고서 생성)

**위치**: [worker_agents.py:1894-3656](multiagent-rag-system/backend/app/core/agents/worker_agents.py#L1894-L3656)

**역할**:
- 보고서 구조 설계
- 섹션별 내용 생성
- 차트 생성

#### 3.4.1 보고서 구조 설계

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:2064-2100

async def _design_report_structure(self, data: List[SearchResult], selected_indexes: List[int],
                                   query: str, state: Optional[Dict[str, Any]] = None):
    """보고서 구조 설계 + 섹션별 사용할 데이터 인덱스 선택"""

    print(f"\n>> 보고서 구조 설계 시작:")
    print(f"   전체 데이터: {len(data)}개")
    print(f"   선택된 인덱스: {selected_indexes} ({len(selected_indexes)}개)")

    # 페르소나 정보 추출
    persona_name = state.get("persona", "기본") if state else "기본"
    persona_description = self.personas.get(persona_name, {}).get("description", "일반적인 분석가")
    print(f"  - 보고서 구조 설계에 '{persona_name}' 페르소나 관점 적용")

    # 선택된 데이터를 컨텍스트로 포맷팅
    indexed_context = ""
    for idx in selected_indexes:
        if 0 <= idx < len(data):
            res = data[idx]
            indexed_context += f"""
    --- 데이터 인덱스 [{idx}] ---
    출처: {res.source}
    제목: {res.title}
    내용: {res.content}
            """

    # ... (프롬프트 생성 및 LLM 호출 코드 중략) ...

    response = await self._invoke_with_fallback(prompt, self.llm_pro, self.llm_pro_backup, self.llm_openai_4o)
    structure = json.loads(response.content)

    return structure
```

보고서 구조는 선택된 페르소나에 따라 다르게 설계되며, 각 섹션이 사용할 데이터를 인덱스로 명시하여 중복을 방지합니다. 시스템은 데이터 특성을 분석하여 차트 생성이 필요한지 판단하며, 고품질 보고서를 위해 Gemini 2.5 Pro 모델을 사용합니다.

#### 3.4.2 섹션 스트리밍 생성

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:2492-2700+

async def generate_section_streaming(
    self,
    section: Dict[str, Any],
    full_data_dict: Dict[int, Dict],
    original_query: str,
    use_indexes: List[int],
    awareness_context: str = "",
    state: Optional[Dict[str, Any]] = None
) -> AsyncGenerator[str, None]:
    """페르소나, 전체 구조 인지(awareness_context), 섹션 목표(description)를 반영하여 스트리밍 생성"""

    section_title = section.get("section_title", "제목 없음")
    content_type = section.get("content_type", "synthesis")
    description = section.get("description", "이 섹션의 내용을 요약합니다.")

    # 페르소나 정보 추출
    persona_name = state.get("persona", "기본") if state else "기본"
    default_report_prompt = "당신은 전문적인 AI 분석가입니다."
    persona_instruction = self.personas.get(persona_name, {}).get("report_prompt", default_report_prompt)

    # 보고서 제목과 중복되지 않도록 섹션 제목 확인
    report_title = state.get("report_title", "") if state else ""
    is_duplicate_title = (
        report_title and
        (section_title.replace(" ", "").lower() in report_title.replace(" ", "").lower() or
         report_title.replace(" ", "").lower() in section_title.replace(" ", "").lower())
    )

    # 중복되지 않는 경우에만 섹션 헤더 출력
    if not is_duplicate_title:
        section_header = f"\n\n## {section_title}\n\n"
        yield section_header
    else:
        yield "\n\n"  # 중복인 경우 간격만 추가

    # 해당 섹션의 데이터만 선별하여 프롬프트용으로 포맷팅
    section_data_content = ""
    valid_indexes = []
    for actual_index in use_indexes:
        if actual_index in full_data_dict:
            valid_indexes.append(actual_index)
            data_info = full_data_dict[actual_index]
            section_data_content += f"**데이터 {actual_index}: {data_info['source']}**\n"
            section_data_content += f"- **제목**: {data_info['title']}\n"
            section_data_content += f"- **내용**: {data_info['content']}\n\n"

    # 방대한 섹션 생성 프롬프트 (약 140줄)
    prompt_template = """
    {persona_instruction}

    당신은 위의 페르소나 지침을 따르는 전문가 AI입니다. 전체 보고서의 일부인 한 섹션을 작성하는 임무를 받았습니다.

    **사용자의 전체 질문**: "{original_query}"

    ---
    **[매우 중요] 전체 보고서 구조 및 당신의 역할**:
    당신은 아래 구조로 구성된 전체 보고서에서 **오직 '{section_title}' 섹션만**을 책임지고 있습니다.
    다른 전문가들이 나머지 섹션들을 동시에 작성하고 있으므로, **다른 섹션의 주제를 절대 침범하지 말고 당신의 역할에만 집중하세요.**

    {awareness_context}
    ---

    **현재 작성할 섹션 제목**: "{section_title}"
    **이 섹션의 핵심 목표**: "{description}"

    **참고 데이터 (실제 인덱스 번호 포함)**:
    {section_data_content}

    **작성 지침 (매우 중요)**:
    1. **역할 준수**: 위 '전체 보고서 구조'와 '핵심 목표'를 반드시 인지하고, '{section_title}'에 해당하는 내용만 깊이 있게 작성하세요.
    2. **페르소나 역할 유지**: 당신의 역할과 말투, 분석 관점을 반드시 유지하며 작성하세요.
    3. **간결성 유지**: 반드시 1~2 문단 이내로, 가장 핵심적인 내용만 간결하게 요약하여 작성하세요.
    4. **제목 반복 금지**: 주어진 섹션 제목을 절대 반복해서 출력하지 마세요. 바로 본문 내용으로 시작해야 합니다.
    5. **데이터 기반**: 참고 데이터에 있는 구체적인 수치, 사실, 인용구를 적극적으로 활용하여 내용을 구성하세요.
    6. **전문가적 문체**: 명확하고 간결하며 논리적인 전문가의 톤으로 글을 작성하세요.
    7. **⭐ 노션 스타일 마크다운 적극 활용 (매우 중요) - 반드시 지켜야 함**:

    **기본 포맷팅 (필수)**:
    - **핵심 키워드나 중요한 수치**: 반드시 **굵은 글씨**로 강조 (예: **58,000원/10kg**, **전년 대비 81.4% 하락**)
    - *변화나 추세*: 반드시 *기울임체*로 표현 (예: *전년 대비 감소*, *집중호우로 인한 피해*)
    - 문단별로 **반드시 2-3개 이상의 강조** 포함할 것

    **구조화 (필수)**:
    - **중요한 인사이트나 결론**: 반드시 `> **핵심 요약**: 내용` 형태로 블록쿼트 사용
    - **비교 정보가 3개 이상**: 반드시 마크다운 테이블 사용
    - **목록 형태 정보**: 반드시 `-` 불릿 포인트 사용
    - **세부 카테고리가 있으면**: 반드시 `### 소제목` 사용

    **필수 예시 패턴**:
    ```
    **배(Pear)**의 전체 재배면적은 **9,361ha**로 전년 대비 **0.6% 감소**했으며, *집중호우 피해 지역*으로 분류되는 강원 및 호남 지역에서의 변동이 두드러졌습니다. [SOURCE:2, 3]

    | 식재료 | 주요 생산지 | 재배면적 변화 | 주요 원인 |
    | :--- | :--- | :--- | :--- |
    | **배** | 전국 | **-0.6%** (전년 대비) | *전국적 재배면적 감소 추세* [SOURCE:2] |

    > **핵심 결론**: 집중호우 직접 피해는 *미미한 수준*이었으나, 고온이 **품질에 미치는 영향**이 더 컸습니다.
    ```

    **⚠️ 강제 요구사항**: 모든 문단에서 **굵은 글씨** 2개 이상, *기울임체* 1개 이상 반드시 사용

    8. **⭐ 출처 표기 (데이터 인덱스 번호 사용)**: 특정 정보를 참고한 문장 바로 뒤에 [SOURCE:숫자] 형식으로 출처를 표기하세요.

    **SOURCE 번호 사용 규칙**:
    - **반드시 위 "참고 데이터"에 명시된 "[데이터 인덱스 X]"의 X 번호만 사용하세요**
    - 예: "데이터 0", "데이터 3"이 주어졌다면 → [SOURCE:0], [SOURCE:3]만 사용 가능
    - **존재하지 않는 번호는 절대 사용하지 마세요**
    - 여러 출처는 쉼표와 공백으로 구분: [SOURCE:1, 4, 8]
    - SOURCE 태그는 완전한 문장이 끝난 후 바로 붙여서 작성하세요

    ... (이하 추가 지침 및 예시 생략) ...
    """

    # 프롬프트 포맷팅
    prompt = prompt_template.format(
        persona_instruction=persona_instruction,
        original_query=original_query,
        section_title=section_title,
        description=description,
        awareness_context=awareness_context,
        section_data_content=section_data_content
    )

    # 스트리밍 생성
    async for chunk in self.llm_pro.astream(prompt):
        if chunk.content:
            yield chunk.content
```

섹션 생성 시 보고서 제목과 섹션 제목이 유사한 경우 제목 출력을 생략하여 중복을 방지하며, 인덱스 기반 데이터 딕셔너리(full_data_dict)에서 해당 섹션에 할당된 인덱스의 데이터만 추출합니다. 전체 보고서 구조를 프롬프트에 포함하는 Awareness Context를 통해 섹션 간 내용 중복을 방지합니다.

시스템은 노션 스타일 마크다운 지침을 따르도록 강제하여, 모든 문단에 **굵은 글씨** 2개 이상과 *기울임체* 1개 이상을 필수로 포함하고, 비교 정보가 3개 이상일 때는 마크다운 테이블을 사용하며, 핵심 인사이트는 블록쿼트(`>`)로 표시합니다. SOURCE 출처 표기 시스템은 데이터 인덱스 번호를 기반으로 [SOURCE:숫자] 형식을 사용하며, 반드시 할당된 인덱스 번호만 사용하도록 강제하여 존재하지 않는 번호 사용을 금지합니다.

각 페르소나의 report_prompt에 따라 말투와 분석 관점을 유지하며, Gemini 2.5 Pro의 astream()을 사용하여 생성되는 즉시 청크 단위로 실시간 스트리밍합니다. 참고 데이터에 명시된 구체적인 수치, 사실, 인용구를 적극 활용하여 데이터 기반으로 섹션을 생성합니다.

---

## 4. 페르소나 기반 보고서 생성

### 4.1 페르소나 정의

**파일 위치**: [persona_prompts.json](multiagent-rag-system/backend/app/core/agents/prompts/persona_prompts.json)

5가지 페르소나가 정의되어 있으며, 각 페르소나는 `description`, `report_prompt`, `chart_prompt` 3가지 속성을 가집니다:

1. **구매 담당자**: 원가, 시세, 수급 안정성 중점
2. **급식 운영 담당자**: 영양 균형, 원가, 직원 만족도 중점
3. **마케팅 담당자**: 시장 트렌드, 소비자 데이터, 경쟁사 분석
4. **제품 개발 연구원**: 새로운 원료, 기술, 과학적 근거
5. **기본**: 명확성과 객관성, 논리적 구조

### 4.2 페르소나 활용 지점

1. **계획 수립 단계**: 페르소나에 따라 질문 분해 및 도구 선택이 달라짐
2. **보고서 구조 설계**: 페르소나 관점에서 섹션 구성
3. **섹션 내용 생성**: 페르소나의 톤앤매너로 작성
4. **차트 생성**: 페르소나가 중요하게 생각하는 데이터 시각화

---

## 5. 리서치 리포트 구조생성 및 출처관리

### 5.1 SearchResult 모델 (출처 관리)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/models/models.py:39-52

class SearchResult(BaseModel):
    """검색 결과 표준 형태"""
    source: str  # 데이터 소스 이름(graph_db, vector_db, web_search 등)
    content: str  # 검색 결과 내용
    search_query: str = ""  # 검색한 쿼리
    document_type: str

    # 출처 정보 필드들
    chunk_id: str = Field(default="", description="청크 id")
    title: str = Field(default="", description="문서 제목")
    url: Optional[str] = Field(default=None, description="원본 URL")
    score: float = Field(default=0.7, description="관련성 점수")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

SearchResult 모델은 모든 검색 도구가 동일한 형식으로 결과를 반환하도록 표준화된 인터페이스를 제공합니다. source, title, url 등을 통해 정보의 출처를 명확히 기록하며, 추가적인 출처 정보는 metadata 필드에 저장합니다.

### 5.2 SourceInfo 모델

```python
# 파일 위치: multiagent-rag-system/backend/app/core/models/models.py:145-172

class SourceInfo(BaseModel):
    """출처 정보 상세 모델"""
    title: str = Field(description="문서 제목")
    url: Optional[str] = Field(default=None, description="원본 URL")
    author: Optional[str] = Field(default=None, description="작성자")
    organization: Optional[str] = Field(default=None, description="기관/회사명")
    published_date: Optional[str] = Field(default=None, description="발행일")
    access_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    document_type: str = Field(default="web", description="문서 타입")
    reliability_score: float = Field(default=0.8, ge=0.0, le=1.0, description="신뢰도 점수")

    def to_citation(self) -> str:
        """출처 인용 형식 자동 생성"""
        citation_parts = []
        if self.author:
            citation_parts.append(f"{self.author}")
        if self.title:
            citation_parts.append(f'"{self.title}"')
        if self.organization:
            citation_parts.append(f"{self.organization}")
        if self.published_date:
            citation_parts.append(f"({self.published_date})")
        if self.url:
            citation_parts.append(f"Retrieved from {self.url}")
        return ", ".join(citation_parts)
```

SourceInfo 모델은 저자, 기관, 발행일, 신뢰도 등 상세한 출처 정보를 기록합니다. `to_citation()` 메서드를 통해 학술적 인용 형식을 자동으로 생성할 수 있으며, 0.0~1.0 범위의 신뢰도 점수를 기록하여 출처의 신뢰성을 평가합니다.

---

## 6. 외부 도구 및 Multi-RAG 연동 APIs

### 6.1 Multi-RAG 아키텍처 개요

본 시스템은 **7개의 이기종 데이터 소스**를 통합하여 검색합니다:

```
사용자 쿼리
    ↓
[DataGathererAgent]
    ├─ Web Search (실시간 정보)
    ├─ Vector DB (Elasticsearch - 문서)
    ├─ Graph DB (Neo4j - 관계)
    ├─ RDB (PostgreSQL - 정형 데이터)
    ├─ PubMed (의학 논문)
    ├─ Arxiv (학술 논문)
    └─ Scraping (URL 콘텐츠)
    ↓
[RRF Fusion] → 통합 결과
    ↓
[Processor Agent] → 보고서 생성
```

**핵심 특징**:
- **병렬 검색**: 모든 데이터 소스를 동시에 쿼리
- **표준화**: 모든 결과를 `SearchResult` 모델로 통일
- **융합 전략**: RRF (Reciprocal Rank Fusion) 알고리즘으로 결과 통합
- **품질 향상**: 중복 제거 및 재순위화

### 6.2 RRF (Reciprocal Rank Fusion) 알고리즘

```python
# 파일 위치: multiagent-rag-system/backend/app/services/database/elasticsearch/elastic_search_rag_tool.py:830-856

def _rrf_fuse(self, ranked_lists: List[Tuple[str, List[Dict]]], id_fn, k: int = 60) -> List[Dict]:
    """
    Reciprocal Rank Fusion 알고리즘
    - Dense(의미 검색) + Sparse(키워드 검색) 결과를 통합

    Args:
        ranked_lists: [(rank_key, list_of_docs), ...] 형태의 순위 리스트들
        id_fn: 문서 고유 ID 생성 함수
        k: RRF K 하이퍼파라미터 (기본값: 60)

    Returns:
        RRF 점수로 정렬된 문서 리스트
    """
    fused = {}

    for rank_key, docs in ranked_lists:
        for d in docs:
            doc_id = id_fn(d)
            rank = d.get(rank_key)
            if not rank:
                continue

            # RRF 공식: 1 / (k + rank)
            contrib = 1.0 / (k + rank)

            if doc_id not in fused:
                fused[doc_id] = d.copy()
                fused[doc_id]["rrf_score"] = 0.0
                fused[doc_id]["rrf_components"] = {}

            fused[doc_id]["rrf_score"] += contrib
            fused[doc_id]["rrf_components"][rank_key] = rank

    # RRF 점수로 정렬
    fused_list = list(fused.values())
    fused_list.sort(key=lambda x: x["rrf_score"], reverse=True)

    return fused_list
```

Hybrid 검색은 Dense(의미 기반) 검색과 Sparse(키워드 기반) 검색 결과를 통합합니다. RRF(Reciprocal Rank Fusion) 공식 `score = Σ 1/(k + rank)`를 사용하여 각 검색 방법의 순위를 조합하며, K 파라미터는 기본값 60으로 설정하여 순위 간 차이를 완화합니다. 여러 검색 방법에서 높은 순위를 받은 문서가 최종적으로 높은 점수를 받게 됩니다.

### 6.3 도구별 연동 인터페이스

모든 검색 도구는 표준화된 인터페이스를 통해 연동됩니다:

```python
# 일반적인 도구 연동 패턴

async def _tool_name_search(self, query: str) -> List[SearchResult]:
    """도구별 검색 메서드"""
    try:
        # ThreadPoolExecutor를 통한 비동기 실행
        loop = asyncio.get_event_loop()
        search_results = await loop.run_in_executor(
            _global_executor,
            tool_function,
            query
        )

        # SearchResult로 변환
        return [SearchResult(**r) for r in search_results]
    except Exception as e:
        print(f"Tool search 오류: {e}")
        return []
```

**통합 전략**:
- **표준화된 반환 형식**: 모든 도구가 `List[SearchResult]` 형식으로 반환
- **비동기 병렬 실행**: `asyncio.gather`로 모든 검색을 동시에 실행
- **예외 격리**: 하나의 도구 실패가 전체 검색을 중단시키지 않음
- **전역 Executor 재사용**: ThreadPoolExecutor를 재사용하여 성능 최적화

---

## 마무리

본 문서는 Multi-Agent RAG 시스템의 핵심 아키텍처와 구현 상세를 다루었습니다.

### 핵심 특징 요약

1. **4개 전문 에이전트**: Triage, Orchestrator, DataGatherer, Processor
2. **동적 워크플로우**: 페르소나 기반 계획 수립 및 의존성 자동 해결
3. **병렬 처리 최적화**: asyncio.gather + ThreadPoolExecutor를 활용한 효율적인 병렬 실행
4. **실시간 스트리밍**: SSE를 통한 점진적 전송 및 Abort 메커니즘
5. **Multi-RAG 통합**: 7개 데이터 소스 통합 및 RRF 기반 결과 융합
6. **페르소나 시스템**: 5가지 역할별 맞춤형 보고서 생성

### 주요 파일 위치

- **Orchestrator Agent**: [orchestrator.py](multiagent-rag-system/backend/app/core/agents/orchestrator.py)
- **Worker Agents**: [worker_agents.py](multiagent-rag-system/backend/app/core/agents/worker_agents.py)
- **Data Models**: [models.py](multiagent-rag-system/backend/app/core/models/models.py)
- **Persona Prompts**: [persona_prompts.json](multiagent-rag-system/backend/app/core/agents/prompts/persona_prompts.json)
- **Main API**: [main.py](multiagent-rag-system/backend/app/main.py)

---

**문서 버전**: 1.0
**최종 업데이트**: 2025-11-14
**작성자**: AI 시스템 아키텍처 팀
