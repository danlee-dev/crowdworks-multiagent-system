"""
RAG 검색 엔진 설정 파일
논문 "Searching for Best Practices in Retrieval-Augmented Generation" 기반
"""

import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class RAGConfig:
    """RAG 시스템 설정"""
    
    # ========== 기본 설정 ==========
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")
    ELASTICSEARCH_HOST = "http://localhost:9200"
    ELASTICSEARCH_USER = os.getenv("ELASTICSEARCH_USER")
    ELASTICSEARCH_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD")
    
    # ========== 하이브리드 검색 설정 (논문 베스트 프랙티스) ==========
    
    # 논문 권장 하이브리드 가중치 (Table 8 기준)
    HYBRID_ALPHA = 0.5  # BM25 30% + Dense 70%
    
    # 대안 가중치들 (도메인별 튜닝 가능)
    ALPHA_BALANCED = 0.5      # 균형형  
    ALPHA_DENSE_HEAVY = 0.1   # Dense 중심 (90%)
    ALPHA_SPARSE_HEAVY = 0.7  # Sparse 중심 (70%)
    
    # ========== 검색 단계별 설정 ==========
    
    # 1. 초기 검색 (Retrieval)
    TOP_K_RETRIEVAL = 100     # 논문 권장: 충분한 후보 확보
    KNN_NUM_CANDIDATES = 200  # Dense retrieval 후보
    
    # 2. 재순위화 (Reranking) 
    TOP_K_RERANK = 100        # 50개 최종 결과를 위한 재순위화 후보
    USE_RERANKING = True
    
    # 3. 최종 결과
    TOP_K_FINAL = 50          # 사용자에게 보여줄 결과
    
    # ========== 쿼리 개선 설정 ==========
    
    # HyDE 설정 (논문 Table 7 기준)
    USE_HYDE = False  # HyDE 비활성화
    HYDE_MAX_TOKENS = 500  # 충분한 길이의 개선 쿼리 생성
    HYDE_TEMPERATURE = 0.3
    HYDE_MODEL = "gpt-4o-mini"  # 실제로는 더 큰 모델 권장
    
    # Query Rewriting
    USE_QUERY_REWRITING = False  # 논문에서 효과 제한적
    QUERY_REWRITE_MAX_TOKENS = 100
    
    # ========== 임베딩 모델 설정 ==========
    
    # 논문 권장: LLM-Embedder (성능 vs 크기 균형)
    EMBEDDING_MODEL = "text-embedding-ada-002"  # OpenAI
    # 실제 사용시 권장: "LLM-Embedder" 또는 "BAAI/bge-large-en"
    
    EMBEDDING_DIMENSION = 1536  # OpenAI ada-002
    
    # ========== 재순위화 모델 설정 ==========
    
    # 논문 Table 9 기준 권장 모델들
    RERANKER_OPTIONS = {
        "balanced": "monoT5",      # 성능 vs 속도 균형 (논문 권장)
        "performance": "RankLLaMA", # 최고 성능
        "speed": "TILDEv2"         # 최고 속도 (0.02초/쿼리)
    }
    
    DEFAULT_RERANKER = "balanced"
    
    # ========== 문서 처리 설정 ==========
    
    # 청킹 전략 (논문 Table 4 기준)
    CHUNKING_STRATEGY = "small2big"  # 논문 권장
    # 대안: "sliding_window", "fixed_size"
    
    CHUNK_SIZE = 512          # 토큰 단위
    CHUNK_OVERLAP = 50        # 겹침 크기
    
    # 요약 설정 (논문 Table 10 기준)
    USE_SUMMARIZATION = False
    SUMMARIZATION_METHOD = "recomp_abstractive"  # 논문 최고 성능
    SUMMARIZATION_RATIO = 0.4  # 원본의 40%로 압축
    SUMMARIZATION_MAX_TOKENS = 200
    
    # ========== 벡터 데이터베이스 설정 ==========
    
    # 논문 Table 5 기준 - Milvus 권장
    VECTOR_DB = "elasticsearch"  # 현재 사용중
    # 권장 업그레이드: "milvus" (모든 기준 충족)
    
    # ========== 평가 설정 ==========
    
    # 논문 권장 평가 지표들
    EVALUATION_METRICS = [
        "faithfulness",      # 사실 일치성
        "context_relevancy", # 문맥 관련성  
        "answer_relevancy",  # 답변 관련성
        "answer_correctness" # 답변 정확성
    ]
    
    # ========== 성능 최적화 설정 ==========
    
    # 병렬 처리
    MAX_WORKERS = 4
    
    # 캐싱
    USE_EMBEDDING_CACHE = True
    CACHE_SIZE = 1000
    
    # 배치 처리
    BATCH_SIZE = 32
    
    # ========== 도메인별 설정 ==========
    
    # 농업 도메인 특화 (현재 시스템)
    DOMAIN_KEYWORDS = [
        "농업", "농산물", "식품", "수출", "생산", 
        "통계", "현황", "품목", "시장", "가격"
    ]
    
    DOMAIN_BOOST = 0.5  # 도메인 키워드 부스트
    
    # ========== 응답 생성 설정 ==========
    
    # LLM 설정
    GENERATOR_MODEL = "gpt-3.5-turbo"  # 실제로는 더 큰 모델 권장
    GENERATOR_MAX_TOKENS = 500
    GENERATOR_TEMPERATURE = 0.3
    
    # RAG 프롬프트 템플릿
    RAG_PROMPT_TEMPLATE = """
다음 검색된 문서들을 바탕으로 질문에 답변해주세요.
답변은 검색된 내용을 기반으로 정확하고 구체적으로 작성해주세요.

질문: {query}

검색된 문서들:
{retrieved_documents}

답변:"""

    # ========== 로깅 및 모니터링 ==========
    
    LOG_LEVEL = "INFO"
    LOG_FILE = "rag_search.log"
    
    # 성능 모니터링
    TRACK_PERFORMANCE = True
    PERFORMANCE_LOG_FILE = "rag_performance.log"
    
    # ========== 실험 설정 ==========
    
    # A/B 테스트를 위한 설정들
    EXPERIMENT_CONFIGS = {
        "baseline": {
            "hybrid_alpha": 0.0,  # Dense only
            "use_hyde": False,
            "use_reranking": False,
            "use_summarization": False
        },
        "hybrid_only": {
            "hybrid_alpha": 0.3,
            "use_hyde": False, 
            "use_reranking": False,
            "use_summarization": False
        },
        "full_rag": {
            "hybrid_alpha": 0.3,
            "use_hyde": True,
            "use_reranking": True,
            "use_summarization": True
        }
    }


# ========== 논문 베스트 프랙티스 요약 ==========

class PaperBestPractices:
    """논문에서 권장하는 베스트 프랙티스 요약"""
    
    RECOMMENDATIONS = {
        "chunking": {
            "best": "small2big",
            "reason": "작은 청크로 검색, 큰 청크로 생성 - 균형적 성능"
        },
        "embedding": {
            "best": "LLM-Embedder",
            "reason": "성능 대비 크기 최적화, BAAI/bge-large-en의 1/3 크기"
        },
        "vector_db": {
            "best": "Milvus", 
            "reason": "모든 평가 기준 충족 (인덱스, 스케일, 하이브리드, 클라우드)"
        },
        "retrieval": {
            "best": "HyDE + Hybrid Search (α=0.3)",
            "reason": "최고 성능, 적당한 레이턴시"
        },
        "reranking": {
            "balanced": "monoT5 (4.5초/쿼리)",
            "performance": "RankLLaMA (82.4초/쿼리)", 
            "speed": "TILDEv2 (0.02초/쿼리)"
        },
        "summarization": {
            "best": "Recomp (Abstractive)",
            "reason": "최고 F1 스코어 (33.68), 적절한 압축률"
        },
        "hybrid_weight": {
            "best": "α = 0.3",
            "reason": "BM25 30% + Dense 70% = 최적 성능"
        }
    }
    
    PERFORMANCE_COMPARISON = {
        "TREC_DL_2019": {
            "BM25_only": {"mAP": 30.13, "nDCG@10": 50.58},
            "LLM_Embedder": {"mAP": 44.66, "nDCG@10": 70.20},
            "Hybrid_Search": {"mAP": 47.14, "nDCG@10": 72.50},
            "HyDE_Hybrid": {"mAP": 52.13, "nDCG@10": 73.34}
        }
    }


def get_config_for_scenario(scenario: str) -> dict:
    """시나리오별 최적 설정 반환"""
    
    configs = {
        "production_balanced": {
            "hybrid_alpha": RAGConfig.HYBRID_ALPHA,
            "use_hyde": True,
            "use_reranking": True, 
            "reranker": "monoT5",
            "use_summarization": True,
            "top_k_final": 5
        },
        "production_fast": {
            "hybrid_alpha": RAGConfig.HYBRID_ALPHA,
            "use_hyde": False,  # 속도 우선
            "use_reranking": True,
            "reranker": "TILDEv2",
            "use_summarization": False,
            "top_k_final": 3
        },
        "research_best": {
            "hybrid_alpha": RAGConfig.HYBRID_ALPHA,
            "use_hyde": True,
            "use_reranking": True,
            "reranker": "RankLLaMA", 
            "use_summarization": True,
            "top_k_final": 10
        },
        "demo": {
            "hybrid_alpha": RAGConfig.HYBRID_ALPHA,
            "use_hyde": True,
            "use_reranking": False,  # 단순화
            "use_summarization": True,
            "top_k_final": 3
        }
    }
    
    return configs.get(scenario, configs["production_balanced"])


if __name__ == "__main__":
    # 설정 확인 및 테스트
    print("📋 RAG 검색 엔진 설정")
    print("=" * 40)
    print(f"하이브리드 가중치: α = {RAGConfig.HYBRID_ALPHA}")
    print(f"최종 결과 수: {RAGConfig.TOP_K_FINAL}")
    print(f"HyDE 사용: {RAGConfig.USE_HYDE}")
    print(f"재순위화 사용: {RAGConfig.USE_RERANKING}")
    print(f"요약 사용: {RAGConfig.USE_SUMMARIZATION}")
    
    print("\n🏆 논문 베스트 프랙티스:")
    for component, recommendation in PaperBestPractices.RECOMMENDATIONS.items():
        print(f"  {component}: {recommendation['best']}")
        print(f"    이유: {recommendation['reason']}") 