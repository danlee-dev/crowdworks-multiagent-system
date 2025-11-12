from playwright.sync_api import sync_playwright
import requests
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime, timedelta
import json

BASE_LIST_URL = "https://www.atfis.or.kr/home/board/FB0002.do"
DOWNLOAD_DIR = Path("ReportPDF")
REFERENCE_PATH = Path("/elasticsearch/referenceURL.json")

DOWNLOAD_DIR.mkdir(exist_ok=True)
REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

# 기존 referenceURL.json 불러오기
if REFERENCE_PATH.exists():
    with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
        reference_data = json.load(f)
else:
    reference_data = {}

threshold_date = datetime.now() - timedelta(days=30)

def save_reference(filename: str, detail_url: str):
    reference_data[filename] = detail_url
    with open(REFERENCE_PATH, "w", encoding="utf-8") as f:
        json.dump(reference_data, f, ensure_ascii=False, indent=2)

    # 저장 확인
    try:
        with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
            confirm_data = json.load(f)
        if filename in confirm_data:
            print(f"      📝 referenceURL.json에 추가됨: {filename}")
        else:
            print(f"      ❗ referenceURL.json에 저장 실패: {filename}")
    except Exception as e:
        print(f"      ❗ referenceURL.json 확인 중 오류 발생: {e}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page_idx = 1
        while True:
            list_url = f"{BASE_LIST_URL}?subSkinYn=N&bcaId=0&pageIndex={page_idx}"
            page.goto(list_url, wait_until="networkidle")
            anchors = page.query_selector_all("ul.galleryList li a")
            if not anchors:
                print(f"✅ Page {page_idx}: 링크 없음 → 종료")
                break

            detail_urls = [
                urljoin(list_url, a.get_attribute("href"))
                for a in anchors if a.get_attribute("href")
            ]

            print(f"\n◾ 페이지 {page_idx}: {len(detail_urls)}개 상세페이지 링크 처리 시작")
            for idx, detail_url in enumerate(detail_urls, start=1):
                print(f" ▶ 상세페이지 [{idx}]: {detail_url}")

                if page_idx == 1 and idx == 1:
                    print("    🔶 1페이지 첫 번째 상세페이지이므로 다운로드 건너뜁니다.")
                    continue

                page.goto(detail_url, wait_until="networkidle")

                date_el = page.query_selector('ul.boardWriteInfo li[title="작성일"]')
                if not date_el:
                    print("    ⚠️ 작성일 요소를 찾을 수 없음 → 스킵")
                    continue

                date_text = date_el.inner_text().strip().split("T")[0]
                try:
                    published = datetime.strptime(date_text, "%Y-%m-%d")
                except ValueError:
                    print(f"    ⚠️ 날짜 파싱 실패 ({date_text}) → 스킵")
                    continue

                if published < threshold_date:
                    print(f"    ⚠️ 게시일 {published.date()} (< {threshold_date.date()}) → 전체 종료")
                    browser.close()
                    return

                items = page.query_selector_all("div.boardFile ul li")
                for li in items:
                    name_tag = li.query_selector("span.fileName")
                    btn_tag  = li.query_selector("a.btn")
                    if not (name_tag and btn_tag):
                        continue

                    filename = name_tag.inner_text().strip() or "unknown.pdf"
                    href     = btn_tag.get_attribute("href")
                    if not href:
                        continue

                    safe = filename.replace("/", "_")
                    out = DOWNLOAD_DIR / safe

                    if out.exists():
                        print(f"    · 이미 존재: {safe}")
                        continue

                    pdf_url = urljoin(detail_url, href)
                    print(f"    ↓ 다운로드 중: {safe}")

                    res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"},
                                       stream=True, timeout=30)
                    if res.status_code != 200:
                        print(f"      [WARN] HTTP {res.status_code} - 스킵")
                        continue

                    with open(out, "wb") as f:
                        for chunk in res.iter_content(chunk_size=1024):
                            if chunk:
                                f.write(chunk)
                    print(f"      ✅ 저장됨: {safe}")

                    if safe in reference_data:
                        print(f"      · referenceURL.json에 이미 있음 → 건너뜁니다.")
                    else:
                        save_reference(safe, detail_url)

            page_idx += 1

        browser.close()
        print("\n🎉 모든 PDF 다운로드 및 referenceURL 저장 완료!")

if __name__ == "__main__":
    main()
