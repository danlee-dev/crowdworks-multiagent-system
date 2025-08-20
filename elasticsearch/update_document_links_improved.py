import json
import os
import glob
import re
from pathlib import Path

def load_reference_urls():
    """referenceURL.json 파일에서 보고서 제목과 URL 매핑을 로드합니다."""
    with open('referenceURL.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def normalize_title(title):
    """제목을 정규화하여 매칭을 개선합니다."""
    # 소문자로 변환
    title = title.lower()
    
    # 특수문자 제거 (하이픈, 언더스코어, 괄호 등)
    title = re.sub(r'[^\w\s가-힣]', ' ', title)
    
    # 연속된 공백을 하나로 변환
    title = re.sub(r'\s+', ' ', title).strip()
    
    return title

def find_matching_url(document_title, reference_urls):
    """document_title과 가장 잘 매칭되는 URL을 찾습니다."""
    # 1. 정확한 매칭 시도
    if document_title in reference_urls:
        return reference_urls[document_title]
    
    # 2. 확장자 제거 후 매칭
    title_without_ext = document_title.replace('.pdf', '').replace('.PDF', '')
    for ref_title, url in reference_urls.items():
        ref_title_without_ext = ref_title.replace('.pdf', '').replace('.PDF', '')
        if title_without_ext == ref_title_without_ext:
            return url
    
    # 3. 정규화된 제목으로 매칭
    normalized_doc_title = normalize_title(document_title)
    for ref_title, url in reference_urls.items():
        normalized_ref_title = normalize_title(ref_title)
        if normalized_doc_title == normalized_ref_title:
            return url
    
    # 4. 부분 매칭 (한쪽이 다른 쪽에 포함)
    for ref_title, url in reference_urls.items():
        ref_title_clean = ref_title.replace('.pdf', '').replace('.PDF', '').replace('[', '').replace(']', '')
        title_clean = document_title.replace('[', '').replace(']', '')
        
        if ref_title_clean in title_clean or title_clean in ref_title_clean:
            return url
    
    # 5. 시장분석형 제목 특별 처리
    if '(시장분석형)' in document_title:
        # 시장분석형 제목에서 핵심 키워드 추출
        core_title = document_title.replace('(시장분석형)', '').strip()
        normalized_core = normalize_title(core_title)
        
        for ref_title, url in reference_urls.items():
            normalized_ref = normalize_title(ref_title)
            # 핵심 키워드가 참조 제목에 포함되는지 확인
            if normalized_core in normalized_ref or normalized_ref in normalized_core:
                return url
    
    # 6. 연도와 국가명 기반 매칭
    year_match = re.search(r'(\d{4})', document_title)
    if year_match:
        year = year_match.group(1)
        # 연도가 포함된 참조 제목 찾기
        for ref_title, url in reference_urls.items():
            if year in ref_title:
                # 추가 키워드 매칭 확인
                doc_keywords = set(normalize_title(document_title).split())
                ref_keywords = set(normalize_title(ref_title).split())
                common_keywords = doc_keywords.intersection(ref_keywords)
                if len(common_keywords) >= 2:  # 최소 2개 이상의 공통 키워드
                    return url
    
    # 7. 국가명 기반 매칭
    countries = ['한국', '중국', '일본', '미국', '유럽', '영국', '프랑스', '독일', '호주', '인도네시아', '태국', '베트남', '싱가포르', '홍콩', '대만', '쿠바', '우크라이나', '러시아']
    for country in countries:
        if country in document_title:
            for ref_title, url in reference_urls.items():
                if country in ref_title:
                    # 국가명이 일치하는 경우 추가 키워드 확인
                    doc_words = set(normalize_title(document_title).split())
                    ref_words = set(normalize_title(ref_title).split())
                    common_words = doc_words.intersection(ref_words)
                    if len(common_words) >= 1:  # 최소 1개 이상의 공통 단어
                        return url
    
    return None

def update_embedded_file(file_path, reference_urls):
    """임베딩 파일을 업데이트하여 document_link를 추가합니다."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        updated = False
        unmatched_titles = set()
        
        for item in data:
            if 'meta_data' in item and 'document_title' in item['meta_data']:
                document_title = item['meta_data']['document_title']
                matching_url = find_matching_url(document_title, reference_urls)
                
                if matching_url:
                    # document_link가 이미 있는지 확인
                    if 'document_link' not in item['meta_data'] or not item['meta_data']['document_link']:
                        item['meta_data']['document_link'] = matching_url
                        updated = True
                        print(f"  - {document_title} -> {matching_url}")
                    else:
                        print(f"  - {document_title} (이미 document_link 존재)")
                else:
                    print(f"  - {document_title} (매칭되는 URL 없음)")
                    unmatched_titles.add(document_title)
        
        if updated:
            # 원본 파일 업데이트
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"  ✓ 파일 업데이트 완료: {file_path}")
            return True, unmatched_titles
        else:
            print(f"  - 업데이트할 내용 없음: {file_path}")
            return False, unmatched_titles
            
    except Exception as e:
        print(f"  ✗ 오류 발생: {file_path} - {str(e)}")
        return False, set()

def analyze_unmatched_titles():
    """매칭되지 않은 제목들을 분석합니다."""
    print("=== 매칭되지 않은 제목 분석 ===")
    
    reference_urls = load_reference_urls()
    unmatched_titles = set()
    
    json_files = glob.glob('embedding_datas/*_embedded.json')
    
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for item in data:
                if 'meta_data' in item and 'document_title' in item['meta_data']:
                    document_title = item['meta_data']['document_title']
                    if 'document_link' not in item['meta_data'] or not item['meta_data']['document_link']:
                        matching_url = find_matching_url(document_title, reference_urls)
                        if not matching_url:
                            unmatched_titles.add(document_title)
        except Exception as e:
            print(f"파일 읽기 오류: {file_path} - {str(e)}")
    
    print(f"매칭되지 않은 고유 제목 수: {len(unmatched_titles)}")
    print("매칭되지 않은 제목들:")
    for title in sorted(unmatched_titles):
        print(f"  - {title}")
    
    return unmatched_titles

def main():
    """메인 함수"""
    print("=== 개선된 문서 링크 업데이트 시작 ===")
    
    # referenceURL.json 로드
    print("1. referenceURL.json 로드 중...")
    try:
        reference_urls = load_reference_urls()
        print(f"   ✓ {len(reference_urls)}개의 URL 매핑 로드 완료")
    except Exception as e:
        print(f"   ✗ referenceURL.json 로드 실패: {str(e)}")
        return
    
    # embedding_datas 폴더의 모든 JSON 파일 찾기
    print("2. embedding_datas 폴더의 JSON 파일 검색 중...")
    json_files = glob.glob('embedding_datas/*_embedded.json')
    print(f"   ✓ {len(json_files)}개의 임베딩 파일 발견")
    
    # 각 파일 업데이트
    print("3. 파일 업데이트 시작...")
    updated_count = 0
    total_count = len(json_files)
    unmatched_titles = set()
    
    for i, file_path in enumerate(json_files, 1):
        print(f"\n[{i}/{total_count}] 처리 중: {os.path.basename(file_path)}")
        file_updated, file_unmatched = update_embedded_file(file_path, reference_urls)
        if file_updated:
            updated_count += 1
        unmatched_titles.update(file_unmatched)
    
    print(f"\n=== 업데이트 완료 ===")
    print(f"총 파일 수: {total_count}")
    print(f"업데이트된 파일 수: {updated_count}")
    print(f"업데이트되지 않은 파일 수: {total_count - updated_count}")
    
    # 매칭되지 않은 제목들 출력
    if unmatched_titles:
        print(f"\n=== 매칭되지 않은 문서 제목들 ({len(unmatched_titles)}개) ===")
        for title in sorted(unmatched_titles):
            print(f"  - {title}")
    else:
        print("\n=== 모든 문서가 성공적으로 매칭되었습니다! ===")

if __name__ == "__main__":
    main() 