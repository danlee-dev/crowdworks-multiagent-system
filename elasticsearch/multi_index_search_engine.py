# -*- coding: utf-8 -*-
"""
멀티 인덱스 RAG 검색 엔진
- documents_text, documents_table 두 인덱스를 각각 검색 후 결과를 합쳐서 스코어 기준 정렬
- improved_search_engine.py와 동일한 검색/임베딩/출력 방식
"""
import sys
import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from elasticsearch import Elasticsearch
import openai
from datetime import datetime
import re
from rag_config import RAGConfig
from sentence_transformers import SentenceTransformer

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')

class MultiIndexRAGSearchEngine:
    def __init__(self, openai_api_key: str = None, es_host: str = None, es_user: str = None, es_password: str = None, config: RAGConfig = None):
        if config is None:
            config = RAGConfig()
        api_key = openai_api_key or config.OPENAI_API_KEY
        if api_key == "your-openai-api-key-here":
            raise ValueError("OpenAI API 키를 설정해주세요 (rag_config.py 또는 초기화 파라미터)")
        self.client = openai.OpenAI(api_key=api_key)
        self.es = Elasticsearch(
            es_host or config.ELASTICSEARCH_HOST,
            basic_auth=(es_user or config.ELASTICSEARCH_USER, es_password or config.ELASTICSEARCH_PASSWORD)
        )
        # Hugging Face 임베딩 모델 로드
        self.hf_model = SentenceTransformer("dragonkue/bge-m3-ko")
        self.TEXT_INDEX = "bge_text"
        self.TABLE_INDEX = "bge_table"
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

    def embed_text(self, text: str) -> List[float]:
        try:
            safe_text = text.encode('utf-8', errors='ignore').decode('utf-8')
            # Hugging Face 모델로 임베딩 생성
            embedding = self.hf_model.encode(safe_text)
            return embedding.tolist()
        except Exception as e:
            print(f"임베딩 생성 오류: {e}")
            return []

    def query_enhancement_hyde_text(self, query: str) -> str:
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
            enhanced_query = f"{query} {hypothetical_doc}"
            return enhanced_query
        except Exception as e:
            print(f"HyDE(text) 처리 중 오류: {e}")
            return query

    def query_enhancement_hyde_table(self, query: str) -> str:
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
            enhanced_query = f"{query} {hypothetical_doc}"
            return enhanced_query
        except Exception as e:
            print(f"HyDE(table) 처리 중 오류: {e}")
            return query

    def dense_retrieval(self, query: str, top_k: int = 100) -> List[Dict]:
        vector = self.embed_text(query)
        if not vector:
            return []
        results = []
        for index in [self.TEXT_INDEX, self.TABLE_INDEX]:
            body = {
                "size": top_k,
                "knn": {
                    "field": "embedding",
                    "query_vector": vector,
                    "k": top_k,
                    "num_candidates": min(top_k * 2, 200)
                },
                "_source": ["page_content", "name", "meta_data"]
            }
            try:
                response = self.es.search(index=index, body=body)
                hits = response.get("hits", {}).get("hits", [])
                for hit in hits:
                    source = hit["_source"]
                    results.append({
                        "score": hit["_score"],
                        "page_content": source.get("page_content", ""),
                        "name": source.get("name", ""),
                        "meta_data": source.get("meta_data", {}),
                        "search_type": "dense",
                        "_index": index
                    })
            except Exception as e:
                print(f"Dense 검색 오류({index}): {e}")
        return results

    def sparse_retrieval(self, query: str, top_k: int = 100) -> List[Dict]:
        results = []
        for index in [self.TEXT_INDEX, self.TABLE_INDEX]:
            search_query = {
                "size": top_k,
                "query": {
                    "bool": {
                        "should": [
                            {"match_phrase": {"page_content": {"query": query, "boost": 5.0}}},
                            {"match": {"name": {"query": query, "boost": 4.0}}},
                            {"match": {"page_content": {"query": query, "boost": 2.0}}},
                            {"match": {"page_content.ngram": {"query": query, "boost": 1.0}}}
                        ],
                        "minimum_should_match": 1
                    }
                },
                "_source": ["page_content", "name", "meta_data"]
            }
            try:
                response = self.es.search(index=index, body=search_query)
                hits = response.get("hits", {}).get("hits", [])
                for hit in hits:
                    source = hit["_source"]
                    results.append({
                        "score": hit["_score"],
                        "page_content": source.get("page_content", ""),
                        "name": source.get("name", ""),
                        "meta_data": source.get("meta_data", {}),
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
        score_range = max_score - min_score
        for result in results:
            original_score = result[score_field]
            normalized_score = (original_score - min_score) / score_range
            result[f"normalized_{score_field}"] = normalized_score
        return results

    def hybrid_search(self, query: str, alpha: float = None, top_k: int = 100, enhanced_query_text: str = None, enhanced_query_table: str = None) -> List[Dict]:
        if alpha is None:
            alpha = self.HYBRID_ALPHA
        # HyDE 쿼리 분리
        if self.USE_HYDE and enhanced_query_text and enhanced_query_table:
            print("📝 HyDE 쿼리 개선 중 (text/table 분리)...")
        else:
            enhanced_query_text = query
            enhanced_query_table = query
        dense_results = []
        sparse_results = []
        # text 인덱스
        dense_results += self.dense_retrieval_index(enhanced_query_text, self.TEXT_INDEX, top_k)
        sparse_results += self.sparse_retrieval_index(enhanced_query_text, self.TEXT_INDEX, top_k)
        # table 인덱스
        dense_results += self.dense_retrieval_index(enhanced_query_table, self.TABLE_INDEX, top_k)
        sparse_results += self.sparse_retrieval_index(enhanced_query_table, self.TABLE_INDEX, top_k)
        dense_results = self.normalize_scores(dense_results)
        sparse_results = self.normalize_scores(sparse_results)
        doc_scores = {}
        for result in dense_results:
            doc_id = self._get_doc_id(result)
            dense_score = result.get("normalized_score", 0)
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "doc": result,
                    "dense_score": dense_score,
                    "sparse_score": 0.0
                }
            else:
                doc_scores[doc_id]["dense_score"] = dense_score
        for result in sparse_results:
            doc_id = self._get_doc_id(result)
            sparse_score = result.get("normalized_score", 0)
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "doc": result,
                    "dense_score": 0.0,
                    "sparse_score": sparse_score
                }
            else:
                doc_scores[doc_id]["sparse_score"] = sparse_score
        hybrid_results = []
        for doc_id, scores in doc_scores.items():
            hybrid_score = alpha * scores["sparse_score"] + (1 - alpha) * scores["dense_score"]
            result = scores["doc"].copy()
            result["hybrid_score"] = hybrid_score
            result["dense_component"] = scores["dense_score"]
            result["sparse_component"] = scores["sparse_score"]
            result["search_type"] = "hybrid"
            hybrid_results.append(result)
        hybrid_results.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return hybrid_results[:top_k]

    def dense_retrieval_index(self, query: str, index: str, top_k: int = 100) -> List[Dict]:
        vector = self.embed_text(query)
        if not vector:
            return []
        results = []
        body = {
            "size": top_k,
            "knn": {
                "field": "embedding",
                "query_vector": vector,
                "k": top_k,
                "num_candidates": min(top_k * 2, 200)
            },
            "_source": ["page_content", "name", "meta_data"]
        }
        try:
            response = self.es.search(index=index, body=body)
            hits = response.get("hits", {}).get("hits", [])
            for hit in hits:
                source = hit["_source"]
                results.append({
                    "score": hit["_score"],
                    "page_content": source.get("page_content", ""),
                    "name": source.get("name", ""),
                    "meta_data": source.get("meta_data", {}),
                    "search_type": "dense",
                    "_index": index
                })
        except Exception as e:
            print(f"Dense 검색 오류({index}): {e}")
        return results

    def sparse_retrieval_index(self, query: str, index: str, top_k: int = 100) -> List[Dict]:
        results = []
        search_query = {
            "size": top_k,
            "query": {
                "bool": {
                    "should": [
                        {"match_phrase": {"page_content": {"query": query, "boost": 5.0}}},
                        {"match": {"name": {"query": query, "boost": 4.0}}},
                        {"match": {"page_content": {"query": query, "boost": 2.0}}},
                        {"match": {"page_content.ngram": {"query": query, "boost": 1.0}}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "_source": ["page_content", "name", "meta_data"]
        }
        try:
            response = self.es.search(index=index, body=search_query)
            hits = response.get("hits", {}).get("hits", [])
            for hit in hits:
                source = hit["_source"]
                results.append({
                    "score": hit["_score"],
                    "page_content": source.get("page_content", ""),
                    "name": source.get("name", ""),
                    "meta_data": source.get("meta_data", {}),
                    "search_type": "sparse",
                    "_index": index
                })
        except Exception as e:
            print(f"Sparse 검색 오류({index}): {e}")
        return results

    def _get_doc_id(self, result: Dict) -> str:
        meta_data = result.get("meta_data", {})
        chunk_id = meta_data.get("chunk_id", "")
        name = result.get("name", "")
        page_content_hash = str(hash(result.get("page_content", "")))
        return f"{chunk_id}_{name}_{page_content_hash}"

    def simple_reranking(self, results: List[Dict], query: str, top_k: int = 20) -> List[Dict]:
        reranked_results = []
        for result in results[:top_k]:
            page_content = result.get("page_content", "")
            name = result.get("name", "")
            query_terms = query.lower().split()
            content_lower = page_content.lower()
            name_lower = name.lower()
            content_matches = sum(content_lower.count(term) for term in query_terms)
            name_matches = sum(name_lower.count(term) for term in query_terms)
            original_score = result.get("hybrid_score", result.get("score", 0))
            rerank_bonus = (content_matches * 0.1) + (name_matches * 0.2)
            rerank_score = original_score + rerank_bonus
            result["rerank_score"] = rerank_score
            result["rerank_bonus"] = rerank_bonus
            reranked_results.append(result)
        reranked_results.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked_results

    def document_summarization(self, results: List[Dict], query: str) -> List[Dict]:
        summarized_results = []
        for result in results:
            page_content = result.get("page_content", "")
            if len(page_content) > 500:
                try:
                    prompt = f"""
다음 문서를 주어진 질문과 관련된 핵심 내용 위주로 요약해주세요.\n요약 길이: 원본의 {self.SUMMARIZATION_RATIO}% 정도\n질문: {query}\n문서 내용:\n{page_content}\n요약:"""
                    response = self.client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=self.SUMMARIZATION_MAX_TOKENS,
                        temperature=0.3
                    )
                    summary = response.choices[0].message.content.strip()
                    result["summarized_content"] = summary
                    result["original_length"] = len(page_content)
                    result["summary_length"] = len(summary)
                except Exception as e:
                    print(f"요약 처리 오류: {e}")
                    result["summarized_content"] = page_content
            else:
                result["summarized_content"] = page_content
            summarized_results.append(result)
        return summarized_results

    def advanced_rag_search(self, query: str) -> Dict:
        print(f"🚀 고급 RAG 검색 시작: '{query}'")
        start_time = datetime.now()
        # HyDE 쿼리 분리
        if self.USE_HYDE:
            print("📝 HyDE 쿼리 개선 중 (text/table 분리)...")
            enhanced_query_text = self.query_enhancement_hyde_text(query)
            enhanced_query_table = self.query_enhancement_hyde_table(query)
        else:
            enhanced_query_text = query
            enhanced_query_table = query
        print("🔍 하이브리드 검색 실행...")
        hybrid_results = self.hybrid_search(query, top_k=self.TOP_K_RETRIEVAL, enhanced_query_text=enhanced_query_text, enhanced_query_table=enhanced_query_table)
        reranked_results = hybrid_results
        if self.USE_RERANKING and len(hybrid_results) > 5:
            reranked_results = self.simple_reranking(
                hybrid_results, query, top_k=self.TOP_K_RERANK
            )
        final_results = reranked_results[:self.TOP_K_FINAL]
        if self.USE_SUMMARIZATION:
            final_results = self.document_summarization(final_results, query)
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        query_for_result = query if query else (enhanced_query_text if enhanced_query_text else "N/A")
        return {
            "query": query_for_result,
            "enhanced_query": {
                "text": enhanced_query_text,
                "table": enhanced_query_table
            },
            "results": final_results,
            "total_candidates": len(hybrid_results),
            "final_count": len(final_results),
            "processing_time": duration,
            "config": {
                "hybrid_alpha": self.HYBRID_ALPHA,
                "use_hyde": self.USE_HYDE,
                "use_reranking": self.USE_RERANKING,
                "use_summarization": self.USE_SUMMARIZATION
            }
        }

    def save_results_to_html(self, results_data: Dict, filename: str = "rag_search_results.html") -> str:
        results = results_data.get('results', [])
        enhanced_query = results_data.get('enhanced_query', {})
        enhanced_query_text = enhanced_query.get('text', '') if isinstance(enhanced_query, dict) else enhanced_query
        enhanced_query_table = enhanced_query.get('table', '') if isinstance(enhanced_query, dict) else enhanced_query
        html = [f"""<!DOCTYPE html>
<html lang='ko'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>RAG 멀티 인덱스 검색 결과</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; padding-top: 180px; }}
.sticky-header {{ position: fixed; top: 0; left: 50%; transform: translateX(-50%); width: 100%; max-width: 1200px; z-index: 1000; background: #f5f5f5; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
.header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 20px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); position: relative; }}
.search-term {{ font-size: 1.8em; font-weight: bold; margin-bottom: 10px; }}
.meta-info {{ font-size: 0.9em; opacity: 0.9; }}
.results-summary {{ background: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }}
.result-item {{ background: white; border-radius: 10px; padding: 25px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 5px solid #667eea; }}
.result-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #f0f0f0; }}
.score {{ color: white; padding: 8px 15px; border-radius: 20px; font-weight: bold; font-size: 0.9em; background: linear-gradient(45deg, #4CAF50, #45a049); }}
.type-badge {{ background: #2196F3; color: white; padding: 5px 12px; border-radius: 15px; font-size: 0.8em; margin-right: 10px; }}
.page-info {{ color: #666; font-size: 0.9em; }}
.content-title {{ color: #333; font-size: 1.2em; font-weight: bold; margin: 15px 0; }}
.content-section {{ border-left: 5px solid #667eea; padding: 20px; background: #ffffff; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(102,126,234,0.1); }}
.content-text {{ white-space: pre-line; line-height: 1.9; font-size: 16px; color: #2c3e50; font-family: 'Malgun Gothic', sans-serif; letter-spacing: 0.3px; }}
.html-table {{ white-space: pre-wrap; word-break: break-all; font-size: 14px; color: #333; background-color: #f9f9f9; padding: 10px; border: 1px solid #ddd; border-radius: 5px; overflow-x: auto; }}
.text-content {{ white-space: pre-line; line-height: 1.9; font-size: 16px; color: #2c3e50; font-family: 'Malgun Gothic', sans-serif; letter-spacing: 0.3px; }}
.toggle-btn {{ background: #667eea; color: white; border: none; border-radius: 5px; padding: 6px 16px; font-size: 0.95em; cursor: pointer; margin-left: 16px; transition: background 0.2s; }}
.toggle-btn:hover {{ background: #4b5fc0; }}
.header-toggle-btn {{ position: absolute; top: 18px; right: 24px; background: #fff; color: #764ba2; border: none; border-radius: 5px; padding: 6px 16px; font-size: 1em; font-weight: bold; cursor: pointer; box-shadow: 0 2px 6px rgba(0,0,0,0.08); transition: background 0.2s; }}
.header-toggle-btn:hover {{ background: #e0e0ff; }}
#header-show-btn {{ position: fixed; top: 24px; left: 50%; transform: translateX(-50%); z-index: 2000; background: #fff; color: #764ba2; border: none; border-radius: 5px; padding: 8px 24px; font-size: 1.1em; font-weight: bold; cursor: pointer; box-shadow: 0 2px 6px rgba(0,0,0,0.08); display: none; }}
#header-show-btn:hover {{ background: #e0e0ff; }}
</style>
<script>
function toggleContent(id) {{
  var el = document.getElementById(id);
  if (el.style.display === 'none') {{ el.style.display = ''; }}
  else {{ el.style.display = 'none'; }}
}}
function toggleHeader() {{
  var meta = document.querySelector('.sticky-header .meta-info');
  var showBtn = document.getElementById('header-show-btn');
  if (meta.style.display === 'none') {{
    meta.style.display = '';
    showBtn.style.display = 'none';
  }} else {{
    meta.style.display = 'none';
    showBtn.style.display = '';
  }}
}}
</script>
</head>
<body>
<button id='header-show-btn' onclick='toggleHeader()'>헤더 펼치기</button>
<div class='sticky-header' id='sticky-header'>
<div class='header'>
<button class='header-toggle-btn' onclick='toggleHeader()'>헤더 접기</button>
<div class='search-term'>🎯 멀티 인덱스 RAG 검색 결과</div>
<div class='meta-info'>
<span>🔍 검색어: "{results_data.get('query', '')}"</span> |
<span>📝 개선된 쿼리 (text): "{enhanced_query_text}"</span> |
<span>📝 개선된 쿼리 (table): "{enhanced_query_table}"</span> |
<span>⏱️ 처리시간: {results_data.get('processing_time', 0):.2f}초</span>
</div></div></div>
<div class='results-summary'>
총 후보: {results_data.get('total_candidates', 0)}개 → 최종: {results_data.get('final_count', 0)}개
</div>
"""]
        for i, result in enumerate(results[:20], 1):
            meta_data = result.get('meta_data', {})
            doc_title = meta_data.get('document_title', 'N/A')
            name = result.get('name', 'N/A')
            page_num = meta_data.get('page_number', 'N/A')
            hybrid_score = result.get('hybrid_score', 0)
            dense_comp = result.get('dense_component', 0)
            sparse_comp = result.get('sparse_component', 0)
            rerank_score = result.get('rerank_score', 0)
            content_id = f'result-content-{i}'
            html.append(f"<div class='result-item'>")
            html.append(f"<div class='result-header'>")
            html.append(f"<div><span class='type-badge'>📋 {meta_data.get('chunk_id', 'document')}</span> <span style='color:#1976d2; font-weight:bold; margin-left:8px;'>[{meta_data.get('item_label', 'N/A')}]</span> <span class='page-info'>📄 페이지: {page_num}</span> <span class='page-info'> | 📖 {doc_title}</span></div>")
            html.append(f"<div><button class='toggle-btn' onclick=\"toggleContent('{content_id}')\">접기/펼치기</button></div>")
            html.append(f"</div>")
            # 분기: table index에서 온 merged
            if result.get('_index') == 'documents_table' and meta_data.get('item_label') == 'merged':
                html.append(f"<div id='{content_id}' class='content-section'><div class='content-title'>{name}</div>")
                for child in meta_data.get('merged_children', []):
                    if child.get('item_label') == 'table':
                        html.append(f"<div class='html-table'>{child.get('content', '')}</div>")
                    elif child.get('item_label') == 'text':
                        html.append(f"<div class='text-content'>{child.get('content', '')}</div>")
                html.append("</div>")
            else:
                # 기존 방식: page_content/요약 출력
                html.append(f"<div id='{content_id}' class='content-section'><div class='content-text'>{result.get('summarized_content', result.get('page_content', ''))}</div></div>")
            html.append("</div>")
        html.append("</body></html>")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('\n'.join(html))
        return filename

def main():
    print("🎯 멀티 인덱스 RAG 검색 엔진")
    print("=" * 50)
    try:
        config = RAGConfig()
        if config.OPENAI_API_KEY == "your-openai-api-key-here":
            print("⚠️ rag_config.py에서 OpenAI API 키가 설정되지 않았습니다.")
            api_key = input("OpenAI API 키를 입력하세요 (또는 Enter로 스킵): ").strip()
            if not api_key:
                print("❌ API 키 없이는 테스트할 수 없습니다.")
                return
        else:
            api_key = config.OPENAI_API_KEY
            print("✅ rag_config.py에서 API 키를 가져왔습니다.")
        search_engine = MultiIndexRAGSearchEngine(openai_api_key=api_key, config=config)
        print(f"\n📋 현재 설정:")
        print(f"  🔧 하이브리드 가중치 α: {config.HYBRID_ALPHA}")
        print(f"  🔧 HyDE 사용: {config.USE_HYDE}")
        print(f"  🔧 재순위화 사용: {config.USE_RERANKING}")
        print(f"  🔧 요약 사용: {config.USE_SUMMARIZATION}")
        print(f"  📊 최종 결과 수: {config.TOP_K_FINAL}")
        query = input("\n검색어를 입력하세요: ").strip()
        if not query:
            print("검색어가 입력되지 않았습니다.")
            return
        save_html = input("결과를 HTML 파일로 저장하시겠습니까? (y/N): ").strip().lower() in ['y', 'yes', '예']
        print("\n🚀 검색 실행 중...")
        results = search_engine.advanced_rag_search(query)
        print(f"\n✅ 검색 완료!")
        print(f"🔍 원본 쿼리: {results['query']}")
        print(f"📝 개선된 쿼리 (text): {results['enhanced_query']['text']}")
        print(f"📝 개선된 쿼리 (table): {results['enhanced_query']['table']}")
        print(f"⏱️ 처리 시간: {results['processing_time']:.2f}초")
        print(f"📊 총 후보: {results['total_candidates']}개 → 최종: {results['final_count']}개")
        print(f"\n📋 검색 결과:")
        print("-" * 60)
        for i, result in enumerate(results['results'], 1):
            name = result.get('name', 'N/A')
            meta_data = result.get('meta_data', {})
            page_num = meta_data.get('page_number', 'N/A')
            doc_title = meta_data.get('document_title', 'N/A')
            hybrid_score = result.get('hybrid_score', 0)
            dense_comp = result.get('dense_component', 0)
            sparse_comp = result.get('sparse_component', 0)
            rerank_score = result.get('rerank_score', 0)
            print(f"\n{i}. 📄 {name}")
            print(f"   📖 문서: {doc_title} (페이지: {page_num})")
            print(f"   📊 하이브리드 점수: {hybrid_score:.4f}")
            print(f"   📊 Dense: {dense_comp:.3f} | Sparse: {sparse_comp:.3f}")
            if rerank_score > 0:
                print(f"   🔄 재순위화 점수: {rerank_score:.4f}")
            content = result.get('summarized_content', result.get('page_content', ''))
            print(f"   📝 내용: {content}")
            if result.get('summary_length'):
                compression_ratio = result['summary_length'] / result['original_length'] * 100
                print(f"   📄 압축률: {compression_ratio:.1f}% ({result['original_length']} → {result['summary_length']} 문자)")
        if save_html:
            filename = "result.html"
            saved_file = search_engine.save_results_to_html(results, filename=filename)
            if saved_file:
                print(f"\n💾 검색 결과가 HTML로 저장되었습니다: {saved_file}")
                print(f"   🌐 브라우저에서 열어보세요!")
    except KeyboardInterrupt:
        print("\n\n🛑 검색이 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 