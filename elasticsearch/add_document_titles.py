import json
import os
import glob

def add_document_titles():
    """document_title이 없는 파일들에 파일명을 기반으로 document_title을 추가합니다."""
    print("=== document_title 추가 시작 ===")
    
    json_files = glob.glob('embedding_datas/*_embedded.json')
    
    updated_count = 0
    total_count = len(json_files)
    updated_files = []
    
    for i, file_path in enumerate(json_files, 1):
        filename = os.path.basename(file_path)
        print(f"[{i}/{total_count}] 처리 중: {filename}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 파일명에서 document_title 추출 (파일명에서 _embedded.json 제거)
            document_title = filename.replace('_embedded.json', '')
            
            file_updated = False
            
            for item in data:
                if 'meta_data' in item:
                    # document_title이 없거나 비어있는 경우에만 추가
                    if 'document_title' not in item['meta_data'] or not item['meta_data']['document_title']:
                        item['meta_data']['document_title'] = document_title
                        file_updated = True
                        print(f"  - document_title 추가: {document_title}")
            
            if file_updated:
                # 파일 업데이트
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                print(f"  ✓ 파일 업데이트 완료: {file_path}")
                updated_count += 1
                updated_files.append(filename)
            else:
                print(f"  - 업데이트할 내용 없음: {file_path}")
                
        except Exception as e:
            print(f"  ✗ 오류 발생: {file_path} - {str(e)}")
    
    print(f"\n=== 업데이트 완료 ===")
    print(f"총 파일 수: {total_count}")
    print(f"업데이트된 파일 수: {updated_count}")
    print(f"업데이트되지 않은 파일 수: {total_count - updated_count}")
    
    if updated_files:
        print(f"\n=== document_title이 추가된 파일들 ({len(updated_files)}개) ===")
        for filename in sorted(updated_files):
            print(f"  - {filename}")
    else:
        print("\n=== document_title이 추가된 파일이 없습니다 ===")

if __name__ == "__main__":
    add_document_titles() 