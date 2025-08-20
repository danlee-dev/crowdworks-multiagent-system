# atfis_playwright_reports_related_last30d.py

from playwright.sync_api import sync_playwright
import requests
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime, timedelta
import json

BASE_LIST_URL = "https://www.atfis.or.kr/home/board/FB0003.do"
DOWNLOAD_DIR = Path("ReportPDF")
DOWNLOAD_DIR.mkdir(exist_ok=True)

REFERENCE_PATH = Path("/elasticsearch/referenceURL.json")
REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

# referenceURL.json 로딩
if REFERENCE_PATH.exists():
    with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
        reference_data = json.load(f)
else:
    reference_data = {}

threshold_date = datetime.now() - timedelta(days=30)

def process_detail(page, detail_url):
    page.goto(detail_url, wait_until="networkidle")

    date_el = page.query_selector('ul.boardWriteInfo li[title="작성일"]')
    if not date_el:
        print("  [WARN] 작성일 요소를 찾을 수 없음 → 이 페이지만 스킵")
        return True

    date_txt = date_el.inner_text().split("T")[0]
    try:
        published = datetime.strptime(date_txt, "%Y-%m-%d")
    except ValueError:
        print(f"  [WARN] 날짜 파싱 실패 ({date_txt}) → 이 페이지만 스킵")
        return True

    if published < threshold_date:
        print(f"  [WARN] 게시일 {published.date()} (< {threshold_date.date()}) → 전체 종료")
        return False

    for li in page.query_selector_all("div.boardFile ul li"):
        name_tag = li.query_selector("span.fileName")
        btn_tag  = li.query_selector("a.btn")
        if not (name_tag and btn_tag):
            continue

        filename = name_tag.inner_text().strip() or "unknown.pdf"
        href     = btn_tag.get_attribute("href")
        if not href:
            continue

        download_url = urljoin(detail_url, href)
        safe_name = filename.replace("/", "_")
        out_path = DOWNLOAD_DIR / safe_name

        if out_path.exists():
            print(f"    · 이미 존재: {safe_name}")
        else:
            print(f"    ↓ 다운로드 중: {safe_name}")
            try:
                r = requests.get(download_url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=30)
                if r.status_code != 200:
                    print(f"      [WARN] HTTP {r.status_code} - 스킵")
                    continue

                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(1024):
                        if chunk:
                            f.write(chunk)
                print(f"      ✅ 저장됨: {safe_name}")
            except Exception as e:
                print(f"      ❌ 다운로드 실패: {e}")
                continue

        # referenceURL.json에 추가
        if safe_name not in reference_data:
            reference_data[safe_name] = detail_url
            with open(REFERENCE_PATH, "w", encoding="utf-8") as f:
                json.dump(reference_data, f, ensure_ascii=False, indent=2)
            print(f"      📝 referenceURL.json에 추가됨: {safe_name}")
        else:
            print(f"      ℹ️ referenceURL.json에 이미 있음: {safe_name}")

    return True

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
                print(f"✅ Page {page_idx}: 링크 없음 → 크롤링 종료")
                break

            detail_urls = [
                urljoin(list_url, a.get_attribute("href"))
                for a in anchors
                if a.get_attribute("href")
            ]

            print(f"\n◾ 페이지 {page_idx}: {len(detail_urls)}개 상세페이지 처리 시작")
            for detail_url in detail_urls:
                print(f" ▶ 상세페이지: {detail_url}")
                if not process_detail(page, detail_url):
                    browser.close()
                    print("\n⛔ 기준일 이전 문서 발견 → 전체 종료")
                    return

            page_idx += 1

        browser.close()
        print("\n🎉 모든 PDF 다운로드 및 referenceURL 저장 완료!")

if __name__ == "__main__":
    main()
