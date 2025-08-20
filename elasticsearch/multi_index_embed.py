import json
import glob
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from sentence_transformers import SentenceTransformer

# Elasticsearch 설정
es = Elasticsearch(
    "http://localhost:9200",
    basic_auth=(os.getenv("ELASTICSEARCH_USER"), os.getenv("ELASTICSEARCH_PASSWORD"))
)

TEXT_INDEX = "bge_text"
TABLE_INDEX = "bge_table"
BATCH_SIZE = 20
MAX_WORKERS = 20
DELAY_BETWEEN_BATCHES = 1.5

# Hugging Face 임베딩 모델 로드
hf_model = SentenceTransformer("dragonkue/bge-m3-ko")

# merged가 text-only인지 table포함인지 판별
def is_text_only_merged(doc):
    if doc['meta_data']['item_label'] != 'merged':
        return False
    children = doc['meta_data'].get('merged_children', [])
    return all(child['item_label'] != 'table' for child in children)

def is_table_merged(doc):
    if doc['meta_data']['item_label'] != 'merged':
        return False
    return any(child['item_label'] == 'table' for child in doc['meta_data'].get('merged_children', []))

# Hugging Face 모델로 임베딩 생성
def embed_text(text: str) -> list:
    # model.encode는 numpy array를 반환하므로 .tolist()로 변환
    return hf_model.encode(text).tolist()

def embed_text_with_retry(text_data, max_retries=3):
    text, index = text_data
    for attempt in range(max_retries):
        try:
            embedding = embed_text(text)
            return index, embedding, None
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"❌ 임베딩 실패 (인덱스 {index}): {str(e)}")
                return index, None, str(e)
            else:
                print(f"⚠️ 임베딩 재시도 {attempt + 1}/{max_retries} (인덱스 {index})")
                time.sleep(2 ** attempt)

def parallel_embed_batch(text_data_list):
    results = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_index = {
            executor.submit(embed_text_with_retry, text_data): text_data[1]
            for text_data in text_data_list
        }
        for future in as_completed(future_to_index):
            index, embedding, error = future.result()
            if error:
                errors[index] = error
            else:
                results[index] = embedding
    return results, errors

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def get_embedding_text(item):
    return item.get("page_content", "")

def prepare_documents_batch(data_batch, start_index, index_type):
    documents = []
    text_data_list = []
    for i, item in enumerate(data_batch):
        doc_index = start_index + i
        embedding_text = get_embedding_text(item)
        doc = item.copy()
        documents.append((doc_index, doc))
        text_data_list.append((embedding_text, doc_index))
    return documents, text_data_list

def bulk_index_documents(documents_with_embeddings, es_index):
    actions = []
    for doc_index, doc, embedding in documents_with_embeddings:
        doc['embedding'] = embedding
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

def classify_docs(docs):
    text_docs = []
    table_docs = []
    for doc in docs:
        label = doc['meta_data']['item_label']
        if label in ['text', 'chunked_text'] or is_text_only_merged(doc):
            text_docs.append(doc)
        elif label == 'table' or is_table_merged(doc):
            table_docs.append(doc)
    return text_docs, table_docs

def process_file(file_path):
    with open(file_path, encoding="utf-8") as f:
        docs = json.load(f)
    print(f"\n📂 파일 처리 시작: {file_path} (총 {len(docs)}개 문서)")
    text_docs, table_docs = classify_docs(docs)

    for index_type, doc_list, es_index in [
        ("text", text_docs, TEXT_INDEX),
        ("table", table_docs, TABLE_INDEX)
    ]:
        if not doc_list:
            continue
        print(f"  ▶️ {index_type} 인덱스 대상 문서: {len(doc_list)}개")
        total_processed = total_errors = batch_count = 0

        for batch_data in chunks(doc_list, BATCH_SIZE):
            batch_count += 1
            batch_start_time = time.time()
            start_index = total_processed
            documents, text_data_list = prepare_documents_batch(batch_data, start_index, index_type)

            print(f"    📦 배치 {batch_count} ({len(batch_data)}개) 임베딩 중...")
            embeddings, errors = parallel_embed_batch(text_data_list)

            documents_with_embeddings = []
            for doc_index, doc in documents:
                if doc_index in embeddings:
                    documents_with_embeddings.append((doc_index, doc, embeddings[doc_index]))
                else:
                    total_errors += 1

            if documents_with_embeddings:
                print(f"    💾 Elasticsearch bulk insert 중... ({len(documents_with_embeddings)}개)")
                success_count, failed = bulk_index_documents(documents_with_embeddings, es_index)
                total_errors += len(failed) if failed else 0

            total_processed += len(batch_data)
            batch_time = time.time() - batch_start_time
            print(f"    ✅ 배치 {batch_count} 완료: "
                  f"{len(documents_with_embeddings)}개 성공, {len(errors)}개 실패, {batch_time:.1f}초")

            if batch_count * BATCH_SIZE < len(doc_list):
                print(f"    ⏳ {DELAY_BETWEEN_BATCHES}초 대기 중... (rate limit 방지)")
                time.sleep(DELAY_BETWEEN_BATCHES)

        print(f"  ▶️ {index_type} 인덱스 최종 결과: "
              f"{total_processed - total_errors}개 성공, {total_errors}개 실패")

    print(f"📁 파일 처리 완료: {file_path}")

def main():
    file_list = sorted(glob.glob("preprocessed_data*.json"))
    if not file_list:
        print("❌ 처리할 preprocessed_data*.json 파일이 없습니다.")
        return

    print(f"🚀 멀티 인덱스 병렬 임베딩 시작 (총 {len(file_list)}개 파일)")
    for file_path in file_list:
        process_file(file_path)

    print("\n🎉 모든 파일 임베딩 및 색인 완료!")
    print(f"📊 Elasticsearch 인덱스: {TEXT_INDEX}, {TABLE_INDEX}")

if __name__ == "__main__":
    main()
