import json
import glob
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from sentence_transformers import SentenceTransformer

# Hugging Face 임베딩 모델 로드
hf_model = SentenceTransformer("dragonkue/bge-m3-ko")

BATCH_SIZE = 20
MAX_WORKERS = 20
DELAY_BETWEEN_BATCHES = 1.5

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

def prepare_documents_batch(data_batch, start_index):
    documents = []
    text_data_list = []
    for i, item in enumerate(data_batch):
        doc_index = start_index + i
        embedding_text = get_embedding_text(item)
        doc = item.copy()
        documents.append((doc_index, doc))
        text_data_list.append((embedding_text, doc_index))
    return documents, text_data_list

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
    
    # 모든 문서를 하나의 리스트로 처리 (text/table 구분 없이)
    all_docs = docs.copy()
    print(f"  ▶️ 전체 문서 임베딩 대상: {len(all_docs)}개")
    
    total_processed = 0
    total_errors = 0
    batch_count = 0
    processed_docs = []
    
    for batch_data in chunks(all_docs, BATCH_SIZE):
        batch_count += 1
        batch_start_time = time.time()
        start_index = total_processed
        documents, text_data_list = prepare_documents_batch(batch_data, start_index)
        
        print(f"    📦 배치 {batch_count} ({len(batch_data)}개) 임베딩 중...")
        embeddings, errors = parallel_embed_batch(text_data_list)
        
        # 임베딩 결과를 문서에 추가
        for doc_index, doc in documents:
            if doc_index in embeddings:
                doc['embedding'] = embeddings[doc_index]
                processed_docs.append(doc)
            else:
                total_errors += 1
                print(f"    ⚠️ 임베딩 실패로 인한 문서 제외: 인덱스 {doc_index}")
        
        total_processed += len(batch_data)
        batch_time = time.time() - batch_start_time
        print(f"    ✅ 배치 {batch_count} 완료: "
              f"{len(embeddings)}개 성공, {len(errors)}개 실패, {batch_time:.1f}초")
        
        if batch_count * BATCH_SIZE < len(all_docs):
            print(f"    ⏳ {DELAY_BETWEEN_BATCHES}초 대기 중... (rate limit 방지)")
            time.sleep(DELAY_BETWEEN_BATCHES)
    
    print(f"  ▶️ 최종 결과: {len(processed_docs)}개 성공, {total_errors}개 실패")
    print(f"📁 파일 처리 완료: {file_path}")
    
    return processed_docs

def main():
    import os
    
    # 입력/출력 디렉토리 설정
    INPUT_DIR = "preprocessed_datas"
    OUTPUT_DIR = "embedding_datas"
    
    # 입력 디렉토리 확인
    if not os.path.exists(INPUT_DIR):
        print(f"❌ 입력 디렉토리가 존재하지 않습니다: {INPUT_DIR}")
        return
    
    # 출력 디렉토리 생성 (비우지 않음)
    if not os.path.exists(OUTPUT_DIR):
        print(f"📁 출력 디렉토리 생성: {OUTPUT_DIR}")
        os.makedirs(OUTPUT_DIR)
    
    # preprocessed_datas 폴더의 모든 JSON 파일 찾기 (이미 '凸'로 시작하는 파일은 제외)
    file_list_all = sorted(glob.glob(os.path.join(INPUT_DIR, "*_preprocessed.json")))
    file_list = [f for f in file_list_all if not os.path.basename(f).startswith('凸')]
    if not file_list:
        print(f"❌ {INPUT_DIR} 폴더에 처리할 *_preprocessed.json 파일이 없습니다. (이미 '凸' 처리된 파일만 존재)")
        return
    
    print(f"🚀 임베딩 생성 시작 (총 {len(file_list)}개 파일)")
    
    for file_path in file_list:
        # 파일명에서 확장자 제거
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        # preprocessed를 embedded로 변경
        output_file_name = base_name.replace("_preprocessed", "_embedded") + ".json"
        output_file_path = os.path.join(OUTPUT_DIR, output_file_name)
        
        print(f"\n📂 처리 중: {os.path.basename(file_path)} → {output_file_name}")
        
        # 파일 임베딩 처리
        processed_docs = process_file(file_path)
        
        # 결과를 embedding_datas 폴더에 저장
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(processed_docs, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 저장 완료: {output_file_path}")
        
        # 입력 파일에 '凸' 접두사 부여하여 재처리 방지
        try:
            src_dir = os.path.dirname(file_path)
            src_base = os.path.basename(file_path)
            if not src_base.startswith('凸'):
                new_src_path = os.path.join(src_dir, f"凸{src_base}")
                os.rename(file_path, new_src_path)
                print(f"🔒 재처리 방지: {src_base} → 凸{src_base}")
        except Exception as e:
            print(f"⚠️ 입력 파일 이름 변경 실패: {file_path} ({e})")
    
    print(f"\n🎉 모든 파일 임베딩 완료!")
    print(f"📊 처리된 파일 수: {len(file_list)}개")
    print(f"📁 결과 저장 위치: {OUTPUT_DIR}/")

if __name__ == "__main__":
    main() 