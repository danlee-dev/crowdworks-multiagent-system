# 고려대학교 산학협력 프로젝트

<div align="center">
<h1>CrowdWorks Multi-Agent RAG System</h1>
<p>식품산업 분석 전문 AI 에이전트 시스템</p>
</div>

> 개발기간: 2025.07 ~ 2025.11
>
> 협력기업: 크라우드웍스(CrowdWorks)
>
> Built with Python, FastAPI, Next.js, LangGraph

## 프로젝트 개요

식품산업 종사자들이 직면하는 정보 분산화와 복잡한 데이터 분석 문제를 해결하기 위해 개발된 차세대 멀티에이전트 RAG(Retrieval-Augmented Generation) 시스템입니다.

KAMIS(한국농수산물유통정보), 농림축산식품부, 농촌진흥청, 식품의약품안전처 등 여러 기관의 분산된 데이터를 통합하고, Graph RAG와 Vector RAG를 결합한 하이브리드 검색 시스템을 통해 전문적인 시장 분석과 의사결정을 지원합니다.

CrowdWorks의 AI 전처리 솔루션 Alpy를 활용한 Knowledge Compiler 시스템으로 비정형 문서를 구조화하고, 동적 멀티홉 계획(Dynamic Multi-Hop Planning)을 통해 복잡한 다단계 질의에 대한 정확한 답변을 제공합니다.

## 서비스 화면

### Web Application

식품산업 데이터의 조회, 분석, 시각화 및 리포트 생성이 가능한 AI 에이전트 웹 애플리케이션입니다.

연구자, 분석가, 식품산업 종사자가 복잡한 시장 데이터를 쉽게 이해하고 의사결정에 활용할 수 있도록 개발되었습니다.

> 접속 주소 : http://49.50.128.6:3000/

![Service UI Mockup](images/service-ui-mockup.png)

## 시스템 아키텍처

![System Architecture](images/system-architecture-diagram.png)

### 주요 구성 요소

**Data Ingestion Pipeline**
- Python Crawler (KAMIS API, 농업 데이터)
- Playwright Scraper (웹 스크래핑)
- PDF Parser (pypdf)

**Hybrid RAG System**
- Graph DB (Neo4j 5, APOC, GDS, Fulltext Index)
- Relational DB (PostgreSQL 14, psycopg2)
- Vector DB (Elasticsearch 8.11, Nori Analyzer, Sentence Transformers)

**AI Agent Layer**
- Orchestrator Agent (계획 수립)
- DataGatherer Agent (데이터 수집)
- Processor Agent (데이터 처리)
- LLM & Tools (Gemini 2.5, GPT-4, LangChain 0.3, Playwright)

**API Gateway & Orchestration**
- FastAPI, LangGraph, Uvicorn

**Frontend Layer**
- Web UI (Next.js 15.3, React 19, TypeScript 5, Tailwind CSS 4, Chart.js 4.5, React-Markdown)

**Infrastructure**
- Docker Compose
- Kibana 8.11 (Monitoring)
- Volume Mounts (Persistence)

**External APIs**
- KAMIS API
- arXiv API
- SERPER API
- PubMed API

## 사용자 플로우

![User Flow](images/user-flow-diagram.png)

### 질의 처리 과정

1. **User Query**: 사용자가 자연어로 복잡한 질문 입력
2. **LangGraph Workflow 실행**: Orchestrator Agent가 계획 수립
3. **3단계 병렬 처리**:
   - **Precheck 단계**: Neo4j 그래프 DB에서 엔터티 세트 생성 및 정합성 검증
   - **Graph-to-Vector 단계**: Precheck 결과를 활용한 벡터 검색 쿼리 최적화
   - **RDB Auto-SQL 단계**: 자연어를 SQL로 자동 변환하여 정형 데이터 조회
4. **DataGatherer Agent**: 내부/외부 데이터 수집
5. **Processor Agent**: 수집된 데이터 통합 및 분석
6. **결과 생성**: 사용자 친화적 차트 + 상세 텍스트 + PDF 변환 가능

![Detailed System Flow](images/detailed-system-flow.png)

## 핵심 기술

### 1. 지능형 데이터 전처리 (Knowledge Compiler 시스템)

비정형 PDF 문서를 구조화된 데이터로 변환하는 3단계 데이터 처리 파이프라인입니다.

**1단계 - PDF 문서 자동 구조 분석**
- Knowledge Compiler로 PDF → JSON 자동 변환
- OCR 기반으로 텍스트, 표, 그래프를 자동 인식 및 분리
- 표 제목-표 관계를 유지하는 계층적 메타데이터 자동 부여

**2단계 - 멀티모달 데이터 분리 및 재청킹**
- 페이지 단위로 텍스트와 표를 개별 청크로 분리
- 각 청크에 문서 제목 자동 삽입 (컨텍스트 보완)
- 메타데이터: 문서명, 출처, 페이지, 데이터 타입

**3단계 - 데이터 타입별 멀티 인덱싱**
- ElasticSearch에서 텍스트 인덱스와 표 인덱스를 분리 구축
- Hybrid Search (Sparse 0.5 + Dense 0.5)
- bge-reranker-v2-m3-ko Cross-Encoder를 통한 정밀도 향상

**청크 구조 예시**
```json
{
  "chunk_id": "doc_001_p3_table_2",
  "content": "표 데이터...",
  "metadata": {
    "doc_title": "2024 농산물 수급",
    "page": 3,
    "type": "table",
    "source": "농림부"
  }
}
```

※ Knowledge Compiler는 CrowdWorks의 AI 전처리 솔루션 Alpy를 적용
https://www.crowdworks.ai/agent/alpykc

### 2. Graph-to-Vector 증강 검색

그래프 데이터베이스의 관계 정보를 활용하여 벡터 검색의 정확도를 향상시키는 하이브리드 검색 기술입니다.

**1단계 - 관계 정보 자동 추출**
- 문서 내 엔터티와 관계(docrels) 자동 추출
- 주요 관계 예시:
  - `isfrom`: 품목-지역 생산 정보 (aTFIS 데이터)
  - `nutrients`: 품목-영양소 정보 (식약처 DB)
  - `docrels`: 문서 간 연관 정보 (예: "토마토 → 항산화 효능", 농진청 보고서)

**2단계 - Graph-To-Vector 쿼리 증강**
- GraphRAG 검색으로 관련 증거(k=50)를 선별
- LLM Prompt Engineering을 통해 VectorDB용 쿼리 재작성
- 숨겨진 연관 정보까지 자동 탐색

**3단계 - 통합 검색 구조**
```
Graph DB (Neo4j) → 관계 기반 쿼리 증강
                 ↓
Vector DB (ElasticSearch) → 의미 기반 벡터 검색
                 ↓
           풍부한 답변 생성
```

**쿼리 최적화 예시**
- Original: "토마토 영양성분과 효능"
- Graph Evidence: ["충남 생산", "비타민C", "라이코펜", "항산화"]
- Optimized: "충남 지역 토마토 비타민C 라이코펜 항산화 효능 농진청"

### 3. 동적 멀티홉 계획 (Dynamic Multi-Hop Planning)

서브쿼리 간 의존성을 분석하여 병렬 처리와 순차 처리를 자동으로 최적화하는 쿼리 실행 계획 시스템입니다.

**1단계 - 동적 멀티홉 계획**
- 서브쿼리 간 의존성 분석
- 독립 쿼리는 병렬 처리, 의존 쿼리는 순차 처리

**2단계 - 컨텍스트 치환 (Context Substitution)**
- 이전 검색 결과를 다음 단계의 입력으로 자동 변환
- 복잡한 다단계 질의에서도 컨텍스트 유지

**3단계 - Graph Pre-Check**
- 그래프 DB에서 데이터의 위치를 사전 확인
- 불필요한 검색 방지 → 속도 및 비용 최적화

**Pre-Check 결과 예시**
```json
{
  "docrels": ["충남 - 호우피해", "전남 - 침수피해", "경북 - 농작물피해"],
  "isfrom": [],
  "nutrients": [],
  "found_evidence": true,
  "precheck_disabled": false
}
```

**4단계 - Multi-Agent 협업 구조**
- Orchestrator Agent: 전체 계획 수립
- DataGatherer Agent: 병렬 검색
- Processor Agent: 데이터 처리
- Report Generator: 결과 보고서 생성

## 주요 기능

### 멀티에이전트 협업 시스템
- **Triage Agent**: 질의 유형 자동 분류 (단순 조회 vs 복잡한 분석)
- **Orchestrator Agent**: 복잡한 보고서 생성 및 시장 분석
- **Simple Answerer Agent**: 빠른 질의응답 (특정 농산물 가격 조회)
- **Worker Agents**: 전문 작업 수행 (데이터 시각화, 통계 분석)

### 하이브리드 RAG 시스템
- **Vector Search**: Elasticsearch 기반 의미론적 문서 검색
- **Graph Search**: Neo4j 기반 농산물-지역-시기-가격 관계 분석
- **SQL Query Generation**: 자연어를 SQL로 자동 변환

### 실시간 데이터 수집
- **통합 크롤러 시스템**: KAMIS API 연동으로 실시간 농수산물 가격 정보
- **실시간 스케줄링**: Neo4j Scheduler로 자동화된 데이터 수집
- **다중 데이터베이스 통합**: PostgreSQL(정형), Elasticsearch(비정형), Neo4j(관계형)

### 사용자 인터페이스
- **실시간 스트리밍**: WebSocket 기반 응답 스트리밍
- **데이터 시각화**: Chart.js 기반 인터랙티브 차트
- **PDF 리포트 생성**: 분석 결과 다운로드

## 프로젝트 구조

```
crowdworks-multiagent-system/
├── multiagent-rag-system/          # 메인 AI 애플리케이션
│   ├── backend/                    # FastAPI 서버
│   │   └── app/
│   │       ├── core/               # AI Agent 로직
│   │       │   ├── agents/         # Orchestrator, Worker Agents
│   │       │   ├── graphs/         # LangGraph Workflow
│   │       │   └── models/         # 데이터 모델
│   │       ├── services/           # 비즈니스 로직
│   │       │   ├── database/       # DB 연동 (Neo4j, Elasticsearch, PostgreSQL)
│   │       │   ├── search/         # 검색 도구
│   │       │   └── charts/         # 차트 생성
│   │       └── utils/              # 유틸리티
│   └── frontend/                   # Next.js 프론트엔드
│       └── src/
│           ├── components/         # React 컴포넌트
│           ├── hooks/              # 커스텀 훅
│           └── utils/              # 유틸리티
├── crawler_rdb/                    # 데이터 수집 크롤러
│   ├── crawler/                    # 크롤러 스크립트
│   └── services/                   # 크롤러 서비스
├── elasticsearch/                  # Vector DB 설정
│   ├── embedding.py                # 임베딩 생성
│   └── multi_index_search_engine.py
├── Neo4J/                          # Graph DB 설정
│   ├── scheduler.py                # 데이터 수집 스케줄러
│   └── graph_extract2.py           # 그래프 추출
├── utils/                          # 공통 유틸리티
│   ├── model_fallback.py           # API 폴백 시스템
│   └── api_fallback.py
└── docker-compose.yml              # 전체 시스템 통합
```

## 기술 스택

### Backend
- **Framework**: FastAPI, LangGraph 0.3
- **AI/ML**: LangChain, Sentence Transformers
- **LLM**: Google Gemini 2.5 시리즈, GPT-4

### Frontend
- **Framework**: Next.js 15.3 (App Router)
- **Language**: TypeScript 5
- **Styling**: Tailwind CSS 4
- **Visualization**: Chart.js 4.5, React-Markdown

### Database
- **Graph DB**: Neo4j 5 (APOC, GDS, Fulltext Index)
- **Vector DB**: Elasticsearch 8.11 (Nori Analyzer)
- **Relational DB**: PostgreSQL 14

### Infrastructure
- **Deployment**: Naver Cloud Platform
- **Containerization**: Docker, Docker Compose
- **Monitoring**: Kibana 8.11
- **Web Scraping**: Playwright

### External APIs
- KAMIS API (농수산물 가격 정보)
- arXiv API (학술 논문)
- SERPER API (웹 검색)
- PubMed API (의학 문헌)

## 시작하기

### 환경 변수 설정

`.env` 파일을 프로젝트 루트에 생성하고 다음 변수들을 설정하세요:

```bash
# API Keys
OPENAI_API_KEY=your-openai-api-key
GEMINI_API_KEY_1=your-gemini-api-key-1
GEMINI_API_KEY_2=your-gemini-api-key-2
GOOGLE_API_KEY=your-google-api-key
SERPER_API_KEY=your-serper-api-key
LANGSMITH_API_KEY=your-langsmith-api-key

# Database Configuration
POSTGRES_DB=crowdworks_db
POSTGRES_USER=crowdworks_user
POSTGRES_PASSWORD=your-password
POSTGRES_HOST=localhost
POSTGRES_PORT=5433

ELASTICSEARCH_HOST=http://localhost:9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=changeme

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password

# Frontend Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Docker Compose로 실행

```bash
# 전체 시스템 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 시스템 종료
docker-compose down
```

### 개별 서비스 실행

**Backend (FastAPI)**
```bash
cd multiagent-rag-system/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend (Next.js)**
```bash
cd multiagent-rag-system/frontend
npm install
npm run dev
```

**Crawler**
```bash
cd crawler_rdb
python main.py
```

## 성능 평가 및 벤치마크

### 실험 조건
- **테스트 데이터**: Multi-Hop(2~4) 200개 쿼리
- **비교 항목**: Pre-check, Graph-to-vector 적용 여부
- **평가 지표**:
  - 검색 품질: nDCG@3 (0: 관련없음 ~ 3: 매우 관련됨)
  - 검색 효율성: 쿼리 분해에 따른 검색 Hops(steps) 및 재검색률
  - 처리 속도: 검색에서 보고서 구조 생성까지 소요 시간(초)

### Graph Pre-Check 도입 효과 (Graph-to-Vector ON 기준)

**검색 속도**
- Pre-check OFF: 평균 44.79초
- Pre-check ON: 평균 38.85초
- **개선율: 22.6% 속도 향상**

**검색 정확도 (nDCG@3)**
- **5.8% 향상**

**검색 효율성**
- 평균 Hops(steps): 2.2 → 2.4로 증가 (체계적인 Query Decompose 수행)
- 재검색률: 54% → 38%로 감소 (16%p 감소)

### 하이브리드 검색 시스템 성능 비교

| Method | Avg Response Time | Search Count | Plan Steps | Re-search Rate | nDCG@3 |
|--------|-------------------|--------------|------------|----------------|--------|
| Graph-to-Vector ON + Pre-check OFF | 44.79s | 7.2 | 2.2 | 54.0% | N/A |
| Graph-to-Vector OFF + Pre-check OFF | 31.92s | 7.2 | 2.1 | 40.0% | 0.310603 |
| Graph-to-Vector OFF + Pre-check ON | 41.25s | 7.3 | 2.4 | 44.0% | 0.328667 |
| **Graph-to-Vector ON + Pre-check ON** | **38.85s** | **7.1** | **2.4** | **38.0%** | **0.340703** |

**최적 구성 (Graph-to-Vector ON + Pre-check ON)**
- 가장 높은 검색 정확도 (nDCG@3: 0.340703)
- 가장 낮은 재검색률 (38.0%)
- 효율적인 검색 속도 (38.85초)
- 체계적인 쿼리 분해 (평균 2.4 steps)

## 팀 구성 및 역할

| 김민재 (팀장)                                                                                  | 강민선                                                                                         |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| <img src="https://avatars.githubusercontent.com/kmj200392" width="160px" alt="Minjae Kim" />  | <img src="https://avatars.githubusercontent.com/KangMinSun" width="160px" alt="Minsun Kang" /> |
| [GitHub: @kmj200392](https://github.com/kmj200392)                                            | [GitHub: @KangMinSun](https://github.com/KangMinSun)                                          |
| 데이터 전처리 및 임베딩 설계<br>Vector RAG 구축                                               | 크롤러 및 데이터 수집 파이프라인 개발<br>페르소나 관리체계 설계 및 Prompt Engineering        |
| 고려대학교 컴퓨터학과                                                                          | 고려대학교 컴퓨터학과                                                                          |

| 김희은                                                                                        | 이동영                                                                                          |
| --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| <img src="https://avatars.githubusercontent.com/heeeun-kim" width="160px" alt="Heeun Kim" /> | <img src="https://avatars.githubusercontent.com/GBEdge01" width="160px" alt="Dongyoung Lee" /> |
| [GitHub: @heeeun-kim](https://github.com/heeeun-kim)                                         | [GitHub: @GBEdge01](https://github.com/GBEdge01)                                               |
| Graph RAG 구축<br>성능 실험 및 평가 시스템 구축                                              | 크롤러 및 데이터 수집 파이프라인 개발<br>Vector RAG 구축                                       |
| 고려대학교 컴퓨터학과                                                                         | 고려대학교 컴퓨터학과                                                                           |

| 이성민                                                                                          |
| ----------------------------------------------------------------------------------------------- |
| <img src="https://avatars.githubusercontent.com/danlee-dev" width="160px" alt="Seongmin Lee" /> |
| [GitHub: @danlee-dev](https://github.com/danlee-dev)                                            |
| Agentic RAG System 개발<br>FastAPI 서버 구축 및 웹 프론트엔드 개발<br>문서 관리 및 형상 관리   |
| 고려대학교 컴퓨터학과                                                                           |

## 협력 기업

**크라우드웍스 (CrowdWorks)**

본 프로젝트는 크라우드웍스의 AI 전처리 솔루션 Alpy를 활용하여 개발되었습니다.

- 웹사이트: https://www.crowdworks.ai
- Alpy 소개: https://www.crowdworks.ai/agent/alpykc

## 라이선스

본 프로젝트는 고려대학교 산학협력 프로젝트로 개발되었습니다.

## 문의

프로젝트 관련 문의사항은 GitHub Issues를 통해 남겨주시기 바랍니다.

## 참고 자료

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Neo4j Documentation](https://neo4j.com/docs/)
- [Elasticsearch Documentation](https://www.elastic.co/guide/index.html)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)

---

## Project Tech Stack

### Environment
![Visual Studio Code](https://img.shields.io/badge/Visual%20Studio%20Code-007ACC?style=for-the-badge&logo=visualstudiocode&logoColor=white)
![Git](https://img.shields.io/badge/Git-F05032?style=for-the-badge&logo=git&logoColor=white)
![GitHub](https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white)

### Backend & AI
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-121212?style=for-the-badge&logo=chainlink&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=for-the-badge&logo=graphql&logoColor=white)

### Frontend
![Next.js](https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)
![Chart.js](https://img.shields.io/badge/Chart.js-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white)

### Database
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-008CC1?style=for-the-badge&logo=neo4j&logoColor=white)
![Elasticsearch](https://img.shields.io/badge/Elasticsearch-005571?style=for-the-badge&logo=elasticsearch&logoColor=white)

### Infrastructure & Deployment
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Naver Cloud Platform](https://img.shields.io/badge/Naver%20Cloud%20Platform-03C75A?style=for-the-badge&logo=naver&logoColor=white)
![Kibana](https://img.shields.io/badge/Kibana-005571?style=for-the-badge&logo=kibana&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)

### AI Models & APIs
![Google Gemini](https://img.shields.io/badge/Google%20Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-412991?style=for-the-badge&logo=openai&logoColor=white)
