import json
import os
import glob

# JSON 파일들이 들어있는 폴더 경로
folder_path = "./preprocessed_datas"  # 예: "C:/data/json_files"
# 결과 저장 폴더
output_folder = "./report_data"
os.makedirs(output_folder, exist_ok=True)

# 폴더 안 모든 JSON 파일 경로 가져오기 (정렬)
json_files = sorted(glob.glob(os.path.join(folder_path, "*.json")))

for json_file_path in json_files:
    with open(json_file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)  # 리스트 형태
        except json.JSONDecodeError:
            print(f"⚠️ JSON 형식 오류: {json_file_path}")
            continue

    page_contents_processed = []
    for idx, item in enumerate(data):
        content = item.get("page_content", "").strip()
        if idx == 0:
            # 첫 항목은 제목 포함
            page_contents_processed.append(content)
        else:
            # 이후 항목은 제목 제거
            if "\n\n" in content:
                content = content.split("\n\n", 1)[1].strip()
            page_contents_processed.append(content)

    # 파일 하나의 모든 내용을 문자열로 합침
    file_text = "\n\n".join(page_contents_processed)

    # 결과 저장 파일 경로 (확장자 .txt로 변경)
    base_name = os.path.splitext(os.path.basename(json_file_path))[0]
    output_path = os.path.join(output_folder, base_name + ".txt")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(file_text)

    print(f"✅ 저장 완료: {output_path}")

print(f"총 {len(json_files)}개의 JSON 파일 처리 완료")
