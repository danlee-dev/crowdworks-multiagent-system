# -*- coding: utf-8 -*-
"""
멀티 인덱스 RAG 검색 엔진 (JSON 결과 버전) with Query-time 동의어 확장
- multi_index_search_engine.py의 모든 로직 포함
- 결과를 HTML 대신 VectorDB.json 파일로 저장
- rag_config.py와 synonyms.json이 같은 디렉토리에 있어야 동작
"""
import sys
import os
import json
import torch
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from elasticsearch import Elasticsearch
import openai
from datetime import datetime
import re
from rag_config import RAGConfig
from sentence_transformers import SentenceTransformer, CrossEncoder
import cohere

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')
    
BGE_RERANKER = CrossEncoder(
    "dragonkue/bge-reranker-v2-m3-ko",
    activation_fn=torch.nn.Sigmoid(),
    device=DEVICE
)

class MultiIndexRAGSearchEngine:
    def __init__(
        self,
        openai_api_key: str = None,
        cohere_api_key: str = None,
        es_host: str = None,
        es_user: str = None,
        es_password: str = None,
        config: RAGConfig = None
    ):
        # 설정 로드
        if config is None:
            config = RAGConfig()
        api_key = openai_api_key or config.OPENAI_API_KEY
        if api_key == "your-openai-api-key-here":
            raise ValueError("OpenAI API 키를 설정해주세요 (rag_config.py 또는 초기화 파라미터)")
        
        # Cohere API 키 설정
        cohere_key = cohere_api_key or os.getenv("COHERE_API_KEY")
        if not cohere_key:
            raise ValueError("Cohere API 키를 설정해주세요 (환경변수 COHERE_API_KEY 또는 초기화 파라미터)")
        
        # OpenAI & Elasticsearch & Cohere 클라이언트 초기화
        self.client = openai.OpenAI(api_key=api_key)
        self.cohere_client = cohere.Client(cohere_key)
        self.es = Elasticsearch(
            es_host or config.ELASTICSEARCH_HOST,
            basic_auth=(es_user or config.ELASTICSEARCH_USER,
                        es_password or config.ELASTICSEARCH_PASSWORD)
        )
        
        # Hugging Face 임베딩 모델 로드
        self.hf_model = SentenceTransformer("dragonkue/bge-m3-ko")
        self.reranker = BGE_RERANKER
        # 인덱스 설정
        self.TEXT_INDEX = "page_text"
        self.TABLE_INDEX = "page_table"
        # Config 파라미터
        self.config = config
        self.HYBRID_ALPHA = config.HYBRID_ALPHA
        self.TOP_K_RETRIEVAL = config.TOP_K_RETRIEVAL
        self.TOP_K_RERANK = config.TOP_K_RERANK
        self.TOP_K_FINAL = config.TOP_K_FINAL
        self.USE_HYDE = config.USE_HYDE
        self.USE_RERANKING = config.USE_RERANKING
        self.USE_SUMMARIZATION = config.USE_SUMMARIZATION
        self.HYDE_MAX_TOKENS = config.HYDE_MAX_TOKENS
        self.HYDE_TEMPERATURE = config.HYDE_TEMPERATURE
        self.HYDE_MODEL = config.HYDE_MODEL
        self.SUMMARIZATION_MAX_TOKENS = config.SUMMARIZATION_MAX_TOKENS
        self.SUMMARIZATION_RATIO = config.SUMMARIZATION_RATIO
        self.DOMAIN_KEYWORDS = config.DOMAIN_KEYWORDS

        # 동의어 사전 로드 (synonyms.json)
        syn_path = os.path.join(os.path.dirname(__file__), "synonyms.json")
        if os.path.exists(syn_path):
            with open(syn_path, encoding='utf-8') as f:
                self.synonym_dict = json.load(f)
        else:
            self.synonym_dict = {}

    def embed_text(self, text: str) -> List[float]:
        try:
            safe_text = text.encode('utf-8', errors='ignore').decode('utf-8')
            embedding = self.hf_model.encode(safe_text)
            return embedding.tolist()
        except Exception as e:
            print(f"임베딩 생성 오류: {e}")
            return []

    def query_enhancement_hyde_text(self, query: str) -> str:
        # ... 기존 HyDE text 로직 그대로 유지 ...
        try:
            prompt = f"""
식품 도메인에 관련된 답변을 작성해주세요.
다음 질문에 대한 상세하고 정확한 답변을 작성해주세요. 
이 답변은 검색을 개선하기 위한 것이므로 가능한 한 구체적이고 전문적으로 작성해주세요.
마크다운 문법을 사용하지 않고 줄글로 써주세요.
최대 {self.HYDE_MAX_TOKENS} 토큰 이내로 답변을 작성하세요.

질문: {query}
답변:"""
            response = self.client.chat.completions.create(
                model=self.HYDE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.HYDE_MAX_TOKENS,
                temperature=self.HYDE_TEMPERATURE
            )
            hypothetical_doc = response.choices[0].message.content.strip()
            return f"{query} {hypothetical_doc}"
        except Exception as e:
            print(f"HyDE(text) 오류: {e}")
            return query

    def query_enhancement_hyde_table(self, query: str) -> str:
        # ... 기존 HyDE table 로직 그대로 유지 ...
        try:
            prompt = f"""
아래 질문에 대해 표 형식의 가상 통계 데이터를 만들어주세요.
- 첫 줄에는 표 제목을 써주세요.
- 두 번째 줄에는 열 이름(헤더)을 공백으로 구분해서 써주세요.
- 그 아래에는 각 행의 데이터를 공백으로 구분해서 **최소 10줄 이상** 써주세요.
- 표는 마크다운, HTML, 파이프(|) 없이, 전처리된 텍스트 표 형식(공백 구분)으로만 작성해주세요.
- 가능한 한 많은 정보를 포함하고, 각 행의 내용도 구체적으로 작성해주세요.

질문: {query}

예시:
표제목: 2024년 식품 통계 주요 항목
항목명 수치 단위 비고
쌀 생산량 370만 톤 전국 기준
밀 수입량 250만 톤 주요 5개국
외식업 매출 120조 원 2024년 기준
식품 수출액 80억 달러 전년 대비 5% 증가

이와 같은 형식으로 답변해주세요.
"""
            response = self.client.chat.completions.create(
                model=self.HYDE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.HYDE_MAX_TOKENS,
                temperature=self.HYDE_TEMPERATURE
            )
            hypothetical_doc = response.choices[0].message.content.strip()
            return f"{query} {hypothetical_doc}"
        except Exception as e:
            print(f"HyDE(table) 오류: {e}")
            return query

    # ========== 동의어 확장 헬퍼 ==========
    def expand_terms(self, tokens: List[str]) -> Dict[str, List[str]]:
        """
        토큰 리스트를 받아서 동의어 사전 기반으로 확장된 variants 딕셔너리 반환
        {원어: [원어, 동의어1, 동의어2, ...], ...}
        """
        expanded: Dict[str, List[str]] = {}
        for t in tokens:
            variants = [t]
            if t in self.synonym_dict:
                variants.extend(self.synonym_dict[t])
            expanded[t] = variants
        return expanded

    def build_synonym_expanded_query(self, query: str, top_k: int) -> Dict[str, Any]:
        """
        원본 쿼리와 동의어 사전을 기반으로 bool should 확장 쿼리 생성
        """
        tokens = query.strip().split()
        expanded = self.expand_terms(tokens)

        # 기본 cross_fields 매칭
        should_clauses: List[Dict[str, Any]] = [
            {
                "multi_match": {
                    "query": query,
                    "type": "cross_fields",
                    "fields": [
                        "page_content^2",
                        "page_content.ngram^1",
                        "name^3",
                        "meta_data.document_title^2"
                    ],
                    "operator": "and"
                }
            }
        ]
        # 각 토큰과 variants로 match/phrase 추가
        for variants in expanded.values():
            for v in variants:
                should_clauses.append({"match": {"name": {"query": v, "boost": 2.5}}})
                should_clauses.append({"match_phrase": {"meta_data.document_title": {"query": v, "boost": 2.0}}})
                should_clauses.append({"match": {"page_content.ngram": {"query": v, "boost": 1.0, "operator": "and"}}})

        bool_query = {"bool": {"should": should_clauses, "minimum_should_match": 1}}
        return {
            "size": top_k,
            "query": bool_query,
            "_source": ["page_content", "name", "meta_data"]
        }

    # ========== Retrieval ==========
    def dense_retrieval(self, query: str, top_k: int = 100) -> List[Dict]:
        # ... 기존 dense_retrieval 로직 유지 (opt: 통합 가능) ...
        vector = self.embed_text(query)
        if not vector:
            return []
        results = []
        for index in [self.TEXT_INDEX, self.TABLE_INDEX]:
            body = {
                "size": top_k,
                "knn": {"field": "embedding", "query_vector": vector, "k": top_k, "num_candidates": min(top_k*2, 200)},
                "_source": ["page_content", "name", "meta_data"]
            }
            try:
                response = self.es.search(index=index, body=body)
                hits = response.get("hits", {}).get("hits", [])
                for hit in hits:
                    src = hit["_source"]
                    results.append({
                        "score": hit["_score"],
                        "page_content": src.get("page_content", ""),
                        "name": src.get("name", ""),
                        "meta_data": src.get("meta_data", {}),
                        "search_type": "dense",
                        "_index": index
                    })
            except Exception as e:
                print(f"Dense 검색 오류({index}): {e}")
        return results

    def sparse_retrieval(self, query: str, top_k: int = 100) -> List[Dict]:
        """
        index별로 query-time 동의어 확장 쿼리를 사용한 sparse 검색
        """
        results = []
        for index in [self.TEXT_INDEX, self.TABLE_INDEX]:
            body = self.build_synonym_expanded_query(query, top_k)
            try:
                response = self.es.search(index=index, body=body)
                hits = response.get("hits", {}).get("hits", [])
                for hit in hits:
                    src = hit["_source"]
                    results.append({
                        "score": hit["_score"],
                        "page_content": src.get("page_content", ""),
                        "name": src.get("name", ""),
                        "meta_data": src.get("meta_data", {}),
                        "search_type": "sparse",
                        "_index": index
                    })
            except Exception as e:
                print(f"Sparse 검색 오류({index}): {e}")
        return results

    def normalize_scores(self, results: List[Dict], score_field: str = "score") -> List[Dict]:
        if not results:
            return results
        scores = [r[score_field] for r in results]
        if not scores or max(scores) == min(scores):
            return results
        min_score, max_score = min(scores), max(scores)
        for r in results:
            orig = r[score_field]
            r[f"normalized_{score_field}"] = (orig - min_score) / (max_score - min_score)
        return results

    def hybrid_search(
        self,
        query: str,
        alpha: float = None,
        top_k: int = 100,
        enhanced_query_text: Optional[str] = None,
        enhanced_query_table: Optional[str] = None
    ) -> List[Dict]:
        # ... 기존 hybrid_search 로직 유지, 내부 sparse_retrieval_index 호출이 synonyms 포함 ...
        if alpha is None:
            alpha = self.HYBRID_ALPHA
        if not (self.USE_HYDE and enhanced_query_text and enhanced_query_table):
            enhanced_query_text = query
            enhanced_query_table = query

        # dense + sparse
        dense_results = self.dense_retrieval_index(enhanced_query_text, self.TEXT_INDEX, top_k)
        sparse_results = self.sparse_retrieval_index(enhanced_query_text, self.TEXT_INDEX, top_k)
        dense_results += self.dense_retrieval_index(enhanced_query_table, self.TABLE_INDEX, top_k)
        sparse_results += self.sparse_retrieval_index(enhanced_query_table, self.TABLE_INDEX, top_k)

        dense_results = self.normalize_scores(dense_results)
        sparse_results = self.normalize_scores(sparse_results)
        # ... score combine 생략 (원본과 동일) ...
        doc_scores: Dict[str, Any] = {}
        for res in dense_results:
            doc_id = self._get_doc_id(res)
            doc_scores.setdefault(doc_id, {"doc": res, "dense_score": 0.0, "sparse_score": 0.0})
            doc_scores[doc_id]["dense_score"] = res.get("normalized_score", 0)
        for res in sparse_results:
            doc_id = self._get_doc_id(res)
            doc_scores.setdefault(doc_id, {"doc": res, "dense_score": 0.0, "sparse_score": 0.0})
            doc_scores[doc_id]["sparse_score"] = res.get("normalized_score", 0)

        hybrid_results: List[Dict] = []
        for doc_id, scores in doc_scores.items():
            hybrid_score = alpha * scores["sparse_score"] + (1 - alpha) * scores["dense_score"]
            r = scores["doc"].copy()
            r.update({
                "hybrid_score": hybrid_score,
                "dense_component": scores["dense_score"],
                "sparse_component": scores["sparse_score"],
                "search_type": "hybrid"
            })
            hybrid_results.append(r)
        hybrid_results.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return hybrid_results[:top_k]

    def dense_retrieval_index(self, query: str, index: str, top_k: int = 100) -> List[Dict]:
        # ... 기존 dense_retrieval_index 로직 그대로 유지 ...
        vector = self.embed_text(query)
        if not vector:
            return []
        results = []
        body = {
            "size": top_k,
            "knn": {"field": "embedding", "query_vector": vector, "k": top_k, "num_candidates": min(top_k*2, 200)},
            "_source": ["page_content", "name", "meta_data"]
        }
        try:
            response = self.es.search(index=index, body=body)
            hits = response.get("hits", {}).get("hits", [])
            for hit in hits:
                src = hit["_source"]
                results.append({
                    "score": hit["_score"],
                    "page_content": src.get("page_content", ""),
                    "name": src.get("name", ""),
                    "meta_data": src.get("meta_data", {}),
                    "search_type": "dense",
                    "_index": index
                })
        except Exception as e:
            print(f"Dense 검색 오류({index}): {e}")
        return results

    def sparse_retrieval_index(self, query: str, index: str, top_k: int = 100) -> List[Dict]:
        # multi-index RAG hybrid_search 내에서 사용되는 sparse 검색
        results = []
        # Query-time 동의어 확장 쿼리
        body = self.build_synonym_expanded_query(query, top_k)
        try:
            response = self.es.search(index=index, body=body)
            hits = response.get("hits", {}).get("hits", [])
            for hit in hits:
                src = hit["_source"]
                results.append({
                    "score": hit["_score"],
                    "page_content": src.get("page_content", ""),
                    "name": src.get("name", ""),
                    "meta_data": src.get("meta_data", {}),
                    "search_type": "sparse",
                    "_index": index
                })
        except Exception as e:
            print(f"Sparse 검색 오류({index}): {e}")
        return results

    def _get_doc_id(self, result: Dict) -> str:
        meta = result.get("meta_data", {})
        chunk_id = meta.get("chunk_id", "")
        name = result.get("name", "")
        content_hash = str(hash(result.get("page_content", "")))
        return f"{chunk_id}_{name}_{content_hash}"

    def cohere_reranking(self, results: List[Dict], query: str, top_k: int = 20) -> List[Dict]:
        """
        Cohere reranker를 사용한 재순위화
        """
        if not results or len(results) == 0:
            return results
            
        try:
            # Cohere reranker에 전달할 문서들 준비
            documents = []
            for r in results[:top_k]:
                content = r.get("page_content", "")
                name = r.get("name", "")
                # 문서 제목과 내용을 결합
                doc_text = f"제목: {name}\n내용: {content}"
                documents.append(doc_text)
            
            if not documents:
                return results
                
            # Cohere reranker 호출
            response = self.cohere_client.rerank(
                query=query,
                documents=documents,
                top_n=len(documents),
                model="rerank-v3.5"  # 최신 다국어 지원 모델
            )
            
            # 결과 재정렬
            reranked_results = []
            for i, result in enumerate(response.results):
                original_index = result.index
                if original_index < len(results):
                    r = results[original_index].copy()
                    r["rerank_score"] = result.relevance_score
                    r["rerank_rank"] = i + 1
                    reranked_results.append(r)
            
            # rerank_score로 정렬
            reranked_results.sort(key=lambda x: x["rerank_score"], reverse=True)
            
            return reranked_results
            
        except Exception as e:
            print(f"Cohere reranker 오류: {e}")
            # 오류 발생시 원본 결과 반환
            return results[:top_k]
    
    
    def BGE_rerank(self, results, query, top_k=20):
        if not results:
            return results

        subset = results[:top_k]
        try: 
            pairs = []
            for r in subset:
                content = r.get("page_content", "") or ""
                name = r.get("name", "") or ""
                doc_text = f"제목: {name}\n내용: {content}".strip()
                pairs.append([query, doc_text if doc_text else content])

            if not pairs:
                return subset

            scores = self.reranker.predict(pairs, batch_size=32)
            
            # minmax 정규화
            min_s = min(scores)
            max_s = max(scores)
            if max_s != min_s:
                scores = [(s - min_s) / (max_s - min_s) for s in scores]
            else:
                scores = [0.0 for _ in scores]
            
            
            reranked = []
            for r, s in zip(subset, scores):
                item = r.copy()
                item["rerank_score"] = float(s)
                reranked.append(item)

            reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
            for i, r in enumerate(reranked, start=1):
                r["rerank_rank"] = i

            return reranked
        
        except Exception as e:
            print(f"Cohere reranker 오류: {e}")
            # 오류 발생시 원본 결과 반환
            return subset

    def simple_reranking(self, results: List[Dict], query: str, top_k: int = 20) -> List[Dict]:
        """
        Cohere reranker를 사용한 재순위화 (기존 simple_reranking 대체)
        """
        with open('VectorDB_Original.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        #return self.cohere_reranking(results, query, top_k)
        return self.BGE_rerank(results, query, top_k)

    def document_summarization(self, results: List[Dict], query: str) -> List[Dict]:
        # ... 기존 document_summarization 로직 유지 ...
        summarized = []
        for r in results:
            content = r.get("page_content", "")
            if len(content) > 500:
                try:
                    prompt = f"""
다음 문서를 주어진 질문과 관련된 핵심 내용 위주로 요약해주세요.
요약 길이: 원본의 {self.SUMMARIZATION_RATIO}% 정도
질문: {query}
문서 내용:
{content}
요약:"""
                    response = self.client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=self.SUMMARIZATION_MAX_TOKENS,
                        temperature=0.3
                    )
                    r["summarized_content"] = response.choices[0].message.content.strip()
                except Exception as e:
                    print(f"요약 오류: {e}")
                    r["summarized_content"] = content
            else:
                r["summarized_content"] = content
            summarized.append(r)
        return summarized

    def advanced_rag_search(self, query: str) -> Dict[str, Any]:
        start = datetime.now()
        if self.USE_HYDE:
            q_text = self.query_enhancement_hyde_text(query)
            q_table = self.query_enhancement_hyde_table(query)
        else:
            q_text, q_table = query, query
        hybrid = self.hybrid_search(query, enhanced_query_text=q_text, enhanced_query_table=q_table)
        reranked = hybrid
        if self.USE_RERANKING and len(hybrid) > 5:
            reranked = self.simple_reranking(hybrid, query, self.TOP_K_RERANK)
        final = reranked[:self.TOP_K_FINAL]
        if self.USE_SUMMARIZATION:
            final = self.document_summarization(final, query)
        duration = (datetime.now() - start).total_seconds()
        return {
            "query": query,
            "enhanced_query": {"text": q_text, "table": q_table},
            "results": final,
            "total_candidates": len(hybrid),
            "final_count": len(final),
            "processing_time": duration,
            "config": {
                "hybrid_alpha": self.HYBRID_ALPHA,
                "use_hyde": self.USE_HYDE,
                "use_reranking": self.USE_RERANKING,
                "use_summarization": self.USE_SUMMARIZATION
            }
        }

def search(query: str, top_k: int = 50) -> Optional[List[Dict]]:
    config = RAGConfig()
    
    # OpenAI API 키 확인
    if config.OPENAI_API_KEY == "your-openai-api-key-here":
        print("⚠️ rag_config.py에서 OpenAI API 키가 설정되지 않았습니다.")
        api_key = input("OpenAI API 키를 입력하세요 (또는 Enter로 스킵): ").strip()
        if not api_key:
            print("❌ OpenAI API 키 없이는 테스트할 수 없습니다.")
            return None
    else:
        api_key = config.OPENAI_API_KEY
    
    # Cohere API 키 확인
    cohere_key = os.getenv("COHERE_API_KEY")
    if not cohere_key:
        print("⚠️ 환경변수에서 Cohere API 키가 설정되지 않았습니다.")
        cohere_key = input("Cohere API 키를 입력하세요 (또는 Enter로 스킵): ").strip()
        if not cohere_key:
            print("❌ Cohere API 키 없이는 reranking을 사용할 수 없습니다.")
            return None
    
    engine = MultiIndexRAGSearchEngine(openai_api_key=api_key, cohere_api_key=cohere_key, config=config)
    if not query:
        print("검색어가 입력되지 않았습니다.")
        return None
    print("검색 실행 중...")
    results = engine.advanced_rag_search(query)
    top_results = results.get('results', [])[:top_k]
    with open('VectorDB.json', 'w', encoding='utf-8') as f:
        json.dump(top_results, f, ensure_ascii=False, indent=2)
    print(f"검색 결과가 VectorDB.json 파일로 저장되었습니다. (총 {len(top_results)}개)")
    return top_results


def main():
    print("🎯 멀티 인덱스 RAG 검색 엔진 (JSON 결과)")
    try:
        query = input("검색어를 입력하세요: ").strip()
        if not query:
            print("검색어가 입력되지 않았습니다.")
            return
        top_k = 50
        top_k_input = input("출력할 결과 개수(기본 50): ").strip()
        if top_k_input.isdigit():
            top_k = int(top_k_input)
        search(query, top_k)
    except KeyboardInterrupt:
        print("\n🛑 검색이 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback; traceback.print_exc()

if __name__ == "__main__":
    main()
