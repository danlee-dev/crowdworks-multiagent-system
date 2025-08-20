import json
import os
import glob
from collections import defaultdict

def load_reference_urls():
    """referenceURL.json 파일에서 보고서 제목과 URL 매핑을 로드합니다."""
    with open('referenceURL.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_files():
    """파일들을 분석하여 업데이트되지 않은 이유를 파악합니다."""
    print("=== 파일 분석 시작 ===")
    
    reference_urls = load_reference_urls()
    json_files = glob.glob('embedding_datas/*_embedded.json')
    
    # 파일별 분석 결과
    file_analysis = {}
    all_unmatched_titles = set()
    files_with_errors = []
    files_all_have_links = []
    files_partial_links = []
    files_no_matching_url = []
    files_no_document_title = []
    
    for file_path in json_files:
        filename = os.path.basename(file_path)
        print(f"분석 중: {filename}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            file_unmatched_titles = set()
            total_items = 0
            items_with_links = 0
            items_without_document_title = 0
            
            for item in data:
                if 'meta_data' in item and 'document_title' in item['meta_data']:
                    total_items += 1
                    document_title = item['meta_data']['document_title']
                    
                    # document_link가 이미 있는지 확인
                    if 'document_link' in item['meta_data'] and item['meta_data']['document_link']:
                        items_with_links += 1
                    else:
                        # 매칭 시도
                        matching_url = None
                        for ref_title, url in reference_urls.items():
                            if document_title == ref_title:
                                matching_url = url
                                break
                        
                        if not matching_url:
                            file_unmatched_titles.add(document_title)
                            all_unmatched_titles.add(document_title)
                else:
                    items_without_document_title += 1
            
            file_analysis[filename] = {
                'total_items': total_items,
                'items_with_links': items_with_links,
                'items_without_document_title': items_without_document_title,
                'unmatched_titles': file_unmatched_titles,
                'all_have_links': items_with_links == total_items and total_items > 0,
                'some_have_links': items_with_links > 0 and items_with_links < total_items,
                'no_document_title': total_items == 0
            }
            
            # 파일 분류 (우선순위 순서대로)
            if total_items == 0:
                files_no_document_title.append(filename)
            elif items_with_links == total_items and total_items > 0:
                files_all_have_links.append(filename)
            elif items_with_links > 0 and items_with_links < total_items:
                files_partial_links.append(filename)
            elif file_unmatched_titles:
                files_no_matching_url.append(filename)
            else:
                # 이 경우는 모든 항목이 매칭되었지만 아직 링크가 없는 경우
                files_partial_links.append(filename)
                
        except Exception as e:
            print(f"  ✗ 오류 발생: {filename} - {str(e)}")
            files_with_errors.append(filename)
    
    # 결과 출력
    print(f"\n=== 분석 결과 ===")
    print(f"총 파일 수: {len(json_files)}")
    print(f"오류 발생 파일 수: {len(files_with_errors)}")
    print(f"document_title이 없는 파일 수: {len(files_no_document_title)}")
    print(f"모든 항목에 링크가 있는 파일 수: {len(files_all_have_links)}")
    print(f"일부 항목에만 링크가 있는 파일 수: {len(files_partial_links)}")
    print(f"매칭되는 URL이 없는 파일 수: {len(files_no_matching_url)}")
    print(f"고유한 매칭되지 않은 제목 수: {len(all_unmatched_titles)}")
    
    # 합계 확인
    total_classified = len(files_with_errors) + len(files_no_document_title) + len(files_all_have_links) + len(files_partial_links) + len(files_no_matching_url)
    print(f"\n=== 분류 합계 확인 ===")
    print(f"분류된 파일 수: {total_classified}")
    print(f"총 파일 수: {len(json_files)}")
    print(f"차이: {len(json_files) - total_classified}")
    
    if files_with_errors:
        print(f"\n=== 오류 발생 파일들 ===")
        for filename in files_with_errors:
            print(f"  - {filename}")
    
    if files_no_document_title:
        print(f"\n=== document_title이 없는 파일들 ===")
        for filename in files_no_document_title:
            analysis = file_analysis[filename]
            print(f"  - {filename} (총 {analysis['total_items']}개 항목, document_title 없음)")
    
    if files_all_have_links:
        print(f"\n=== 모든 항목에 링크가 있는 파일들 (처음 10개) ===")
        for filename in files_all_have_links[:10]:
            analysis = file_analysis[filename]
            print(f"  - {filename} (총 {analysis['total_items']}개 항목, 모두 링크 있음)")
        if len(files_all_have_links) > 10:
            print(f"  ... 외 {len(files_all_have_links) - 10}개 파일")
    
    if files_partial_links:
        print(f"\n=== 일부 항목에만 링크가 있는 파일들 (처음 10개) ===")
        for filename in files_partial_links[:10]:
            analysis = file_analysis[filename]
            print(f"  - {filename} (총 {analysis['total_items']}개 항목, {analysis['items_with_links']}개에 링크 있음)")
        if len(files_partial_links) > 10:
            print(f"  ... 외 {len(files_partial_links) - 10}개 파일")
    
    if files_no_matching_url:
        print(f"\n=== 매칭되는 URL이 없는 파일들 ===")
        for filename in files_no_matching_url:
            analysis = file_analysis[filename]
            print(f"  - {filename}")
            for title in analysis['unmatched_titles']:
                print(f"    * {title}")
    
    print(f"\n=== 모든 매칭되지 않은 제목들 ===")
    for title in sorted(all_unmatched_titles):
        print(f"  - {title}")
    
    # 요약
    print(f"\n=== 요약 ===")
    print(f"성공적으로 매칭된 파일: {len(files_all_have_links)}개")
    print(f"부분적으로 매칭된 파일: {len(files_partial_links)}개")
    print(f"매칭 실패한 파일: {len(files_no_matching_url)}개")
    print(f"document_title 없는 파일: {len(files_no_document_title)}개")
    print(f"오류 발생 파일: {len(files_with_errors)}개")
    
    return file_analysis

if __name__ == "__main__":
    analyze_files() 