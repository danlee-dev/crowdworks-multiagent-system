import os
from typing import List
import requests
import json
# import asyncio  # 사용하지 않음
# import concurrent.futures  # 사용하지 않음
import io
from pypdf import PdfReader

# 각 RAG 툴의 메인 함수를 import
from ..database.postgres_rag_tool import postgres_rdb_search
from ..database.neo4j_rag_tool import neo4j_search_sync
from ..database.elasticsearch.elastic_search_rag_tool import MultiIndexRAGSearchEngine, RAGConfig


from ...core.models.models import ScrapeInput



from playwright.sync_api import sync_playwright
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 세션별 로그 시스템 import
from ...utils.session_logger import print_session_separated, session_print




# --------------------------------------------------
# Tool Definitions
# --------------------------------------------------

@tool
def debug_web_search(query: str) -> str:
    """
    내부 데이터베이스(RDB, Vector, Graph)에 없는 최신 정보나 일반적인 지식을 실제 웹(구글)에서 검색합니다.
    - 사용 시점:
      1. '오늘', '현재', '실시간' 등 내부 DB에 아직 반영되지 않았을 수 있는 최신 정보가 필요할 때 (예: '오늘자 A기업 주가', '현재 서울 날씨')
      2. 내부 DB의 주제(농업/식품)를 벗어나는 일반적인 질문일 때 (예: '대한민국의 수도는 어디야?')
      3. 특정 인물, 사건, 제품에 대한 최신 뉴스와 같이 시의성이 매우 중요한 정보를 찾을 때
    - 주의: 농산물 시세, 영양 정보, 문서 내용 분석, 데이터 관계 분석 등 내부 DB로 해결 가능한 질문에는 절대 사용하지 마세요. 최후의 수단으로 사용해야 합니다.
    """
    session_print("WebSearch", f"Web 검색 실행: {query}")
    try:
        api_key = os.environ.get("SERPER_API_KEY")
        if not api_key:
            return "SERPER_API_KEY가 설정되지 않았습니다."

        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        payload = {"q": query, "num": 5, "gl": "kr", "hl": "ko"}  # 결과 수 증가
        response = requests.post(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()
            results = []

            # Answer box 우선 처리
            if "answerBox" in data:
                answer = data["answerBox"].get("answer", "")
                if answer:
                    results.append({
                        "title": "Direct Answer",
                        "snippet": answer,
                        "link": "google_answer_box",
                        "source": "google_answer_box"
                    })

            # Organic 결과 처리
            if "organic" in data and data["organic"]:
                for result in data["organic"][:5]:  # 상위 5개
                    link = result.get("link", "")
                    title = result.get("title", "No title")
                    snippet = result.get("snippet", "No snippet")

                    # 유효한 URL인지 확인
                    if link and link.startswith(('http://', 'https://')):
                        # PDF 파일인 경우 제목 수정
                        if link.endswith('.pdf'):
                            title = f"PDF: {title}"

                        results.append({
                            "title": title,
                            "snippet": snippet,
                            "link": link,
                            "source": "web_search"
                        })
                    else:
                        print(f"- 유효하지 않은 URL 스킵: {link}")

            if results:
                # 텍스트 형태로 반환 (ReAct 에이전트용)
                result_text = f"웹 검색 결과 (검색어: {query}):\n\n"
                for i, result in enumerate(results):
                    result_text += f"{i+1}. {result['title']}\n"
                    result_text += f"   출처 링크: {result['link']}\n"
                    result_text += f"   요약: {result['snippet']}\n\n"

                session_print("WebSearch", f"유효한 검색 결과: {len(results)}개")
                return result_text
            else:
                return f"'{query}'에 대한 유효한 웹 검색 결과를 찾을 수 없습니다."
        else:
            return f"API 오류: {response.status_code}, {response.text}"
    except Exception as e:
        return f"웹 검색 중 예외 발생: {str(e)}"


@tool
def scrape_and_extract_content(action_input: str) -> str:
    """
    주어진 URL의 웹페이지 또는 PDF에 접속하여 본문 내용을 추출하고, 사용자의 원래 질문과 관련된 핵심 정보를 요약합니다.
    Action Input은 반드시 '{"url": "...", "query": "..."}' 형태의 JSON(딕셔너리) 문자열이어야 합니다.
    """
    try:
        input_data = json.loads(action_input)
        url = input_data['url']
        query = input_data['query']
        session_print("Scraper", f"Scraping 시작 (URL: {url}, Query: {query})")

    except (json.JSONDecodeError, KeyError) as e:
        return f"입력값 파싱 오류: Action Input은 '{{\"url\": \"...\", \"query\": \"...\"}}' 형태여야 합니다. 오류: {e}"

    # URL이 PDF로 끝나는지에 따라 다른 처리 함수를 호출
    if url.lower().endswith('.pdf'):
        return _scrape_pdf_content(url, query)
    else:
        return _scrape_html_content(url, query)


def _scrape_pdf_content(url: str, query: str) -> str:
    """PDF URL에서 텍스트를 추출하고 요약합니다."""
    print(f"  → PDF 처리 모드 시작: {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status() # HTTP 오류가 있으면 예외 발생

        with io.BytesIO(response.content) as f:
            reader = PdfReader(f)
            text = "".join(page.extract_text() for page in reader.pages if page.extract_text())

        if not text:
            return "PDF에서 텍스트를 추출할 수 없었습니다."

        print(f"  ✓ PDF 텍스트 추출 완료 ({len(text)}자)")
        return _extract_key_info(text, query)

    except Exception as e:
        return f"PDF 처리 중 오류 발생: {e}"


def _scrape_html_content(url: str, query: str) -> str:
    """HTML 웹페이지에서 텍스트를 추출하고 요약합니다."""
    print(f"  → HTML 처리 모드 시작: {url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000) # 타임아웃 증가

            # 더 견고한 방식으로 본문 탐색 (article -> main -> body 순서)
            locators = ['article', 'main', '[role="main"]']
            content = ""
            for loc in locators:
                try:
                    # 해당 선택자의 첫 번째 요소만 선택
                    content = page.locator(loc).first.inner_text(timeout=2000)
                    if len(content) > 100:
                        print(f"  ✓ '{loc}' 선택자에서 본문 발견")
                        break
                except Exception:
                    continue

            # 위에서 못 찾으면 body 전체를 최후의 수단으로 사용
            if not content:
                content = page.locator('body').inner_text(timeout=2000)
                print("  ✓ 최후의 수단으로 'body' 선택자 사용")

            browser.close()

            if not content:
                return "웹페이지에서 내용을 추출할 수 없었습니다."

            print(f"  ✓ HTML 텍스트 추출 완료 ({len(content)}자)")
            return _extract_key_info(content, query)

    except Exception as e:
        return f"웹페이지 스크래핑 중 오류 발생: {e}"


def _extract_key_info(content: str, query: str) -> str:
    """추출된 전체 텍스트에서 LLM을 이용해 핵심 정보를 다시 추출합니다."""
    print(f"  → LLM 분석 시작...")
    try:
        # Gemini 2.5 Flash-Lite로 변경 (빠른 정보 추출)
        extractor_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
        prompt = ChatPromptTemplate.from_template(
            """당신은 유능한 데이터 분석가입니다. 아래 원본 텍스트에서 사용자의 질문과 가장 관련 있는 핵심 정보, 특히 수치 데이터, 통계, 주요 사실들을 정확하게 추출하고 요약해주세요.

            사용자 질문: "{user_query}"

            원본 텍스트 (최대 15000자):
            {web_content}

            핵심 정보 요약:"""
        )
        chain = prompt | extractor_llm | StrOutputParser()

        extracted_info = chain.invoke({
            "user_query": query,
            "web_content": content[:15000]
        })

        print(f"  ✓ LLM 분석 완료")
        return extracted_info
    except Exception as e:
        return f"LLM 분석 중 오류 발생: {e}"


@tool
def rdb_search(query: str) -> str:
    """
    # PostgreSQL DB에 저장된 식자재 관련 정형 데이터를 조회합니다.

    ## 포함된 데이터:
    1. 식자재 영양소 정보 (단백질, 탄수화물, 지방, 비타민, 미네랄 등의 상세 영양 성분)
    2. 농산물/수산물 시세 데이터 (매일 크롤링으로 업데이트되는 최신 가격 정보)

    ### 검색 전략 - 결과가 만족스럽지 않으면 다른 키워드로 재시도하세요:

    1차 시도: 구체적인 식품명으로 검색
    - 예: "유기농 채소" (not "organic vegetables")
    - 예: "친환경 농산물" (not "eco-friendly agricultural products")

    2차 시도: 더 넓은 카테고리로 검색
    - 예: "채소류", "과일류", "곡물류"

    3차 시도: 관련 키워드로 검색
    - 예: "농산물 영양", "식품 성분"

    ## 검색 결과 평가 기준:
    - 결과가 질문과 관련 없으면 → 다른 키워드로 재시도
    - 영양성분만 나오는데 생산/소비 정보가 필요하면 → vector_db나 graph_db 사용
    - 가격 정보만 나오는데 다른 정보가 필요하면 → 다른 키워드로 재시도 후 다른 DB 활용

    사용 시점:
    1. 특정 식자재의 영양 성분을 정확히 알고 싶을 때
    2. 농산물/수산물의 현재 시세나 가격 변동을 확인하고 싶을 때
    3. 특정 지역/품종별 가격 비교가 필요할 때
    4. 영양소 기준으로 식자재를 비교/분석하고 싶을 때

    ## 검색 팁:
    - 반드시 한국어로 검색 (예: "유기농" not "organic")
    - 첫 검색 결과가 원하는 정보가 아니면 키워드를 바꿔서 2-3회 더 시도
    - 구체적인 식품명 → 카테고리명 → 관련 키워드 순으로 점진적 확장
    - 생산량/소비량 통계가 필요하면 이 DB로는 한계가 있으니 다른 DB 활용

    예시 검색 시퀀스:
    1. "유기농 채소" → 관련 없는 결과 →
    2. "채소류 영양" → 일부 관련 결과 →
    3. "친환경 농산물" → 원하는 결과 또는 다른 DB로 전환

    주의: 시세 데이터는 매일 업데이트되므로 '오늘', '현재' 가격 질문에 적합합니다.
    """

    session_print("RDB", f"PostgreSQL 검색 시작: {query}")
    try:
        result = postgres_rdb_search(query)
        # print(f"- 검색 결과: {result}")
        return result
    except Exception as e:
        error_msg = f"PostgreSQL 연결 오류: {str(e)}"
        print(f">> {error_msg}")
        return error_msg



@tool
def vector_db_search(query: str, top_k = 20) -> List:
    """
    Elasticsearch에 저장된 뉴스 기사 본문, 논문, 보고서 전문에서 '의미 기반'으로 유사한 내용을 검색합니다.
    """
    try:
        config = RAGConfig()
        print(">> Vector DB 검색 초기화 중...")

        # Google API Key 사용 (OpenAI가 아님)
        google_api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

        search_engine = MultiIndexRAGSearchEngine(google_api_key=google_api_key, config=config)

        session_print("VectorDB", f"Vector DB 검색 시작: {query}")
        results = search_engine.advanced_rag_search(query)
        top_results = results.get('results', [])[:top_k]

        session_print("VectorDB", f"검색된 문서 수: {len(top_results)}개")

        if not top_results:
            print(">> Vector DB 검색 완료: 관련 문서 없음")
            return []

        # ReAct가 판단하기 쉬운 핵심 정보만 추출
        processed_docs = []
        for i, doc in enumerate(top_results):
            # 핵심 필드 추출
            title = doc.get('name', doc.get('title', f'Document {i+1}'))
            content = doc.get('page_content', doc.get('content', ''))
            metadata = doc.get('meta_data', doc.get('metadata', {}))
            similarity = doc.get('score', doc.get('similarity_score', 0.7))
            relavance = doc.get('relevance_score', similarity)  # relevance_score가 없으면 similarity로 대체
            rerank_score = doc.get('rerank_score', 0.0)
            # 출처 정보 더 명확히 포함
            source_info = metadata.get('document_link', 'Vector DB')
            page_number = metadata.get('page_number', 'N/A')

            formatted_result = {
                "content": content,
                "title": title,
                "document_id": f"doc_{i+1}",
                "similarity_score": similarity,
                "metadata": metadata,
                "source_url": source_info,  # 출처 정보 추가
                "page_number": page_number,  # 페이지 번호 추가
                "relevance_score": relavance,
                "score": rerank_score
            }
            processed_docs.append(formatted_result)

        return processed_docs

    except Exception as e:
        print(f"Vector DB 검색 오류: {e}")


@tool
def graph_db_search(query: str) -> str:
    """
    상위 레벨 도구 진입점:
    - 실행중 이벤트 루프가 있으면 ThreadPool에서 동기 함수 실행
    - 없으면 동기 실행
    """
    session_print("GraphDB", f"Graph DB search called: {query}")
    try:
        # 이벤트 루프 상태와 관계없이 직접 동기 호출로 통일
        print("Using direct sync call for Graph DB")
        return neo4j_search_sync(query)
    except Exception as e:
        print(f"graph_db_search error: {e}")
        return f"Graph DB 검색 중 오류: {e}"


@tool
def arxiv_search(query: str, max_results: int = 10) -> str:
    """
    # arXiv 학술 논문 검색 - 식품과학/AI/생명공학 분야 최신 연구
    
    ## 사용 목적:
    - 신제품 개발을 위한 최신 과학적 연구 동향 파악
    - 식품 공학, 영양학, 생명공학 관련 학술적 근거 확보
    - AI/ML 기반 식품 분석 및 예측 모델 연구
    - 대체 식품, 기능성 원료, 신소재 개발 연구
    
    ## 주요 검색 분야:
    1. **식품과학**: food science, nutrition, fermentation, food engineering
    2. **생명공학**: biotechnology, synthetic biology, protein engineering  
    3. **농업기술**: agriculture, crop science, precision farming
    4. **AI/데이터**: machine learning for food, predictive analytics
    5. **지속가능성**: sustainable food, alternative protein, food waste
    
    ## 검색 전략:
    - 영문 키워드 필수 (arXiv는 영문 논문만 제공)
    - 구체적인 기술명이나 방법론 포함 시 정확도 향상
    - 최신순 정렬로 최근 연구 트렌드 파악
    
    ## 활용 예시:
    - "대체육 개발을 위한 식물성 단백질 연구" 
    - "발효 기술을 활용한 기능성 식품 개발"
    - "AI 기반 식품 품질 예측 모델"
    - "지속가능한 식품 포장재 개발"
    
    주의: 학술 논문이므로 실무 적용 시 검증 필요
    """
    import urllib.parse
    import urllib.request
    import xml.etree.ElementTree as ET
    from datetime import datetime
    
    session_print("arXiv", f"arXiv 논문 검색 시작: {query}")
    
    try:
        # 검색 쿼리 URL 인코딩
        base_url = "http://export.arxiv.org/api/query?"
        
        # 식품/농업 관련 카테고리 추가 (q-bio, cs.AI, physics.bio-ph 등)
        search_query = urllib.parse.quote(query)
        
        # arXiv API 파라미터
        params = {
            'search_query': f'all:{search_query}',
            'start': 0,
            'max_results': max_results,
            'sortBy': 'lastUpdatedDate',  # 최신순 정렬
            'sortOrder': 'descending'
        }
        
        # URL 생성
        url = base_url + urllib.parse.urlencode(params)
        print(f"  - API URL: {url}")
        
        # API 호출
        response = urllib.request.urlopen(url, timeout=10)
        data = response.read().decode('utf-8')
        
        # XML 파싱
        root = ET.fromstring(data)
        
        # 네임스페이스 정의
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }
        
        # 결과 파싱
        entries = root.findall('atom:entry', ns)
        
        if not entries:
            return f"'{query}'에 대한 arXiv 논문을 찾을 수 없습니다. 영문 키워드로 다시 검색해보세요."
        
        results = []
        for i, entry in enumerate(entries[:max_results], 1):
            # 논문 정보 추출
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            
            # 저자 정보
            authors = entry.findall('atom:author', ns)
            author_names = [author.find('atom:name', ns).text for author in authors]
            author_str = ', '.join(author_names[:3])  # 처음 3명만
            if len(author_names) > 3:
                author_str += f' 외 {len(author_names)-3}명'
            
            # 초록
            summary = entry.find('atom:summary', ns).text.strip()
            # 초록을 300자로 제한
            if len(summary) > 300:
                summary = summary[:297] + "..."
            
            # 발행일
            published = entry.find('atom:published', ns).text
            pub_date = datetime.strptime(published[:10], '%Y-%m-%d').strftime('%Y년 %m월 %d일')
            
            # 카테고리
            categories = entry.findall('atom:category', ns)
            cat_list = [cat.get('term') for cat in categories]
            categories_str = ', '.join(cat_list[:3])
            
            # 논문 링크
            pdf_link = None
            for link in entry.findall('atom:link', ns):
                if link.get('type') == 'application/pdf':
                    pdf_link = link.get('href')
                    break
            
            if not pdf_link:
                pdf_link = entry.find('atom:id', ns).text.replace('abs', 'pdf')
            
            # 결과 포맷팅
            result_text = f"{i}. 📄 {title}\n"
            result_text += f"   저자: {author_str}\n"
            result_text += f"   발행일: {pub_date}\n"
            result_text += f"   분야: {categories_str}\n"
            result_text += f"   PDF: {pdf_link}\n"
            result_text += f"   초록: {summary}\n"
            
            results.append(result_text)
        
        # 최종 결과 반환
        result_text = f"arXiv 논문 검색 결과 (검색어: {query}):\n"
        result_text += f"총 {len(results)}개 논문 발견\n\n"
        result_text += "\n".join(results)
        
        session_print("arXiv", f"arXiv 검색 완료: {len(results)}개 논문")
        return result_text
        
    except Exception as e:
        error_msg = f"arXiv 검색 중 오류 발생: {str(e)}"
        print(f"  - {error_msg}")
        return error_msg
