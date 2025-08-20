import json
import glob
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# Elasticsearch 설정
es = Elasticsearch(
    "http://localhost:9200",
    basic_auth=("elastic", "changeme")
)

TEXT_INDEX = "page_text"
TABLE_INDEX = "page_table"

def is_text_only_merged(doc):
    """merged가 text-only인지 판별"""
    if doc['meta_data']['item_label'] != 'merged':
        return False
    children = doc['meta_data'].get('merged_children', [])
    return all(child['item_label'] != 'table' for child in children)

def is_table_merged(doc):
    """merged가 table을 포함하는지 판별"""
    if doc['meta_data']['item_label'] != 'merged':
        return False
    return any(child['item_label'] == 'table' for child in doc['meta_data'].get('merged_children', []))

def classify_docs(docs):
    """문서들을 text와 table로 분류"""
    text_docs = []
    table_docs = []
    for doc in docs:
        label = doc['meta_data']['item_label']
        if label in ['text', 'chunked_text'] or is_text_only_merged(doc):
            text_docs.append(doc)
        elif label == 'table' or is_table_merged(doc):
            table_docs.append(doc)
    return text_docs, table_docs

def bulk_index_documents(documents, es_index):
    """문서들을 Elasticsearch에 bulk insert"""
    actions = []
    for doc_index, doc in documents:
        actions.append({
            "_index": es_index,
            "_id": doc_index,
            "_source": doc
        })
    
    if not actions:
        return 0, []
    
    try:
        success_count, failed = bulk(es, actions, chunk_size=len(actions))
        return success_count, failed
    except Exception as e:
        print(f"❌ Bulk insert 실패: {e}")
        return 0, [{"error": str(e)}]

def process_file(file_path, start_index=0):
    """단일 파일을 처리하여 Elasticsearch에 삽입"""
    try:
        with open(file_path, encoding="utf-8") as f:
            docs = json.load(f)
    except Exception as e:
        print(f"❌ 파일 읽기 실패 {file_path}: {e}")
        return 0, 0
    
    print(f"\n📂 파일 처리 시작: {file_path} (총 {len(docs)}개 문서)")
    text_docs, table_docs = classify_docs(docs)
    
    total_success = 0
    total_errors = 0
    
    for index_type, doc_list, es_index in [
        ("text", text_docs, TEXT_INDEX),
        ("table", table_docs, TABLE_INDEX)
    ]:
        if not doc_list:
            continue
            
        print(f"  ▶️ {index_type} 인덱스 대상 문서: {len(doc_list)}개")
        
        # 문서에 인덱스 부여
        documents = []
        for i, doc in enumerate(doc_list):
            doc_index = start_index + total_success + i
            documents.append((doc_index, doc))
        
        print(f"    📦 전체 {len(doc_list)}개 문서 Elasticsearch bulk insert 중...")
        start_time = time.time()
        
        success_count, failed = bulk_index_documents(documents, es_index)
        errors_count = len(failed) if failed else 0
        
        total_success += success_count
        total_errors += errors_count
        
        process_time = time.time() - start_time
        print(f"    ✅ {index_type} 인덱스 완료: "
              f"{success_count}개 성공, {errors_count}개 실패, {process_time:.1f}초")
    
    print(f"📁 파일 처리 완료: {file_path}")
    return total_success, total_errors

def main():
    """메인 함수"""
    # embedding_datas 폴더 확인
    if not os.path.exists("embedding_datas"):
        print("❌ embedding_datas 폴더가 존재하지 않습니다.")
        return
    
    # JSON 파일 목록 가져오기 (이미 '凸'로 시작하는 파일은 제외)
    file_pattern = os.path.join("embedding_datas", "*.json")
    # file_list = sorted(glob.glob(file_pattern))
    file_list_all = sorted(glob.glob(file_pattern))
    file_list = [p for p in file_list_all if not os.path.basename(p).startswith('凸')]
    
    if not file_list:
        print("❌ embedding_datas 폴더에 처리할 JSON 파일이 없습니다.")
        return
    
    print(f"🚀 embedding_datas 폴더 파일 삽입 시작 (총 {len(file_list)}개 파일)")
    
    total_success = 0
    total_errors = 0
    start_index = 0
    
    for file_path in file_list:
        success, errors = process_file(file_path, start_index)
        total_success += success
        total_errors += errors
        start_index += success + errors
        
        # 입력 파일에 '凸' 접두사 부여하여 재삽입 방지
        try:
            src_dir = os.path.dirname(file_path)
            src_base = os.path.basename(file_path)
            if not src_base.startswith('凸'):
                new_src_path = os.path.join(src_dir, f"凸{src_base}")
                os.rename(file_path, new_src_path)
                print(f"🔒 재삽입 방지: {src_base} → 凸{src_base}")
        except Exception as e:
            print(f"⚠️ 파일 이름 변경 실패: {file_path} ({e})")
    
    print(f"\n🎉 모든 파일 삽입 완료!")
    print(f"📊 최종 결과: {total_success}개 성공, {total_errors}개 실패")
    print(f"📊 Elasticsearch 인덱스: {TEXT_INDEX}, {TABLE_INDEX}")

if __name__ == "__main__":
    main() 