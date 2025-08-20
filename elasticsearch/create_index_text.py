from elasticsearch import Elasticsearch

# text, chunked_text, merged(text-only) 전용 인덱스 생성
ES_INDEX = "page_text"

es = Elasticsearch(
    "http://localhost:9200",
    basic_auth=("elastic", "changeme")
)

# 인덱스가 이미 존재하면 삭제 (테스트 목적)
if es.indices.exists(index=ES_INDEX):
    es.indices.delete(index=ES_INDEX)
    print(f"기존 {ES_INDEX} 인덱스를 삭제했습니다.")

# mapping 정의 (text/merged(text-only)용)
documents_text_mapping = {
    "mappings": {
        "properties": {
            "page_content": {
                "type": "text",
                "analyzer": "korean_content_analyzer",
                "search_analyzer": "korean_search_analyzer",
                "fields": {
                    "domain": {
                        "type": "text", 
                        "analyzer": "korean_domain_analyzer",
                        "search_analyzer": "korean_domain_search_analyzer"
                    },
                    "ngram": {
                        "type": "text",
                        "analyzer": "korean_ngram_analyzer",
                        "search_analyzer": "korean_search_analyzer"
                    },
                    "exact": {
                        "type": "text",
                        "analyzer": "keyword"
                    }
                }
            },
            "name": {
                "type": "text",
                "analyzer": "korean_title_analyzer",
                "search_analyzer": "korean_search_analyzer",
                "fields": {
                    "keyword": {"type": "keyword"},
                    "standard": {
                        "type": "text",
                        "analyzer": "standard"
                    }
                }
            },
            "embedding": {
                "type": "dense_vector", 
                "dims": 1024, 
                "index": True, 
                "similarity": "cosine"
            },
            "meta_data": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "item_label": {
                        "type": "keyword",
                        "null_value": "unknown"
                    },
                    "hierarchy": {
                        "type": "keyword", 
                        "null_value": "NULL"
                    },
                    "page_number": {"type": "integer"},
                    "index": {"type": "integer"},
                    "document_id": {"type": "keyword"},
                    "summary": {
                        "type": "text",
                        "analyzer": "korean_content_analyzer",
                        "search_analyzer": "korean_search_analyzer"
                    },
                    "published_date": {
                        "type": "date", 
                        "format": "yyyy-MM-dd"
                    },
                    "source": {"type": "keyword"},
                    "document_type": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "document_file_path": {"type": "keyword"},
                    "document_title": {
                        "type": "text",
                        "analyzer": "korean_title_analyzer",
                        "search_analyzer": "korean_search_analyzer"
                    },
                    "document_link": {
                        "type": "keyword"
                    },
                    "original_page_content": {
                        "type": "text",
                        "index": False,
                        "store": True
                    },
                    "merged_children": {
                        "type": "nested",
                        "properties": {
                            "item_label": {"type": "keyword"},
                            "chunk_id": {"type": "keyword"},
                            "content": {
                                "type": "text", 
                                "index": False,
                                "store": True
                            },
                            "summary": {
                                "type": "text",
                                "analyzer": "korean_content_analyzer",
                                "search_analyzer": "korean_search_analyzer"
                            }
                        }
                    },
                    "merged_count": {"type": "integer"}
                }
            }
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "max_result_window": 10000,
        "analysis": {
            "char_filter": {
                "korean_normalize_filter": {
                    "type": "mapping",
                    "mappings": [
                        "＃ => #",
                        "（ => (",
                        "） => )",
                        "［ => [",
                        "］ => ]",
                        "｜ => |",
                        "－ => -",
                        "～ => ~"
                    ]
                }
            },
            "tokenizer": {
                "korean_nori_tokenizer": {
                    "type": "nori_tokenizer",
                    "decompound_mode": "mixed"
                },
                "korean_keyword_tokenizer": {
                    "type": "keyword"
                }
            },
            "filter": {
                "korean_lowercase": {
                    "type": "lowercase"
                },
                "korean_stop": {
                    "type": "stop",
                    "stopwords": [
                        "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", 
                        "로", "으로", "에서", "부터", "까지", "만", "도", "라도", 
                        "이나", "나", "든지", "거나"
                    ]
                },

                "korean_edge_ngram": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 10
                },
                "korean_ngram": {
                    "type": "ngram",
                    "min_gram": 2,
                    "max_gram": 3
                }
            },
            "analyzer": {
                "korean_content_analyzer": {
                    "type": "custom",
                    "char_filter": ["korean_normalize_filter"],
                    "tokenizer": "korean_nori_tokenizer",
                    "filter": [
                        "korean_lowercase",
                        "korean_stop"
                    ]
                },
                "korean_title_analyzer": {
                    "type": "custom",
                    "char_filter": ["korean_normalize_filter"],
                    "tokenizer": "korean_keyword_tokenizer",  # 제목은 전체를 하나로
                    "filter": ["korean_lowercase"]
                },
                "korean_search_analyzer": {
                    "type": "custom",
                    "char_filter": ["korean_normalize_filter"],
                    "tokenizer": "korean_nori_tokenizer",
                    "filter": [
                        "korean_lowercase"
                    ]
                },
                "korean_suggest_analyzer": {
                    "type": "custom",
                    "char_filter": ["korean_normalize_filter"],
                    "tokenizer": "korean_nori_tokenizer",
                    "filter": [
                        "korean_lowercase",
                        "korean_edge_ngram"
                    ]
                },
                "korean_domain_analyzer": {
                    "type": "custom",
                    "char_filter": ["korean_normalize_filter"],
                    "tokenizer": "korean_nori_tokenizer",
                    "filter": [
                        "korean_lowercase",
                        "korean_stop"
                    ]
                },
                "korean_domain_search_analyzer": {
                    "type": "custom",
                    "char_filter": ["korean_normalize_filter"],
                    "tokenizer": "korean_nori_tokenizer",
                    "filter": [
                        "korean_lowercase"
                    ]
                },
                "korean_ngram_analyzer": {
                    "type": "custom",
                    "char_filter": ["korean_normalize_filter"],
                    "tokenizer": "korean_nori_tokenizer",
                    "filter": [
                        "korean_lowercase",
                        "korean_ngram"
                    ]
                }
            }
        }
    }
}

# 인덱스 생성
es.indices.create(index=ES_INDEX, body=documents_text_mapping)
print(f"✅ {ES_INDEX} 인덱스가 성공적으로 생성되었습니다! (text/merged(text-only) 전용)") 