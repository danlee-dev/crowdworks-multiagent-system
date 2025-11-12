# atfis_playwright_reports_last30d.py

from playwright.sync_api import sync_playwright
import requests
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime, timedelta
import json

BASE_LIST_URL = "https://www.atfis.or.kr/home/board/FB0032.do"
DOWNLOAD_DIR = Path("ReportPDF")
DOWNLOAD_DIR.mkdir(exist_ok=True)

REFERENCE_PATH = Path("/elasticsearch/referenceURL.json")
REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

# JSON 로드 또는 초기화
if REFERENCE_PATH.exists():
    with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
        reference_data = json.load(f)
else:
    reference_data = {}

# 30일 전 기준 날짜 계산
threshold_date = datetime.now() - timedelta(days=30)

def process_detail(page, detail_url):
    page.goto(detail_url, wait_until="networkidle")

    date_el = page.query_selector('ul.boardWriteInfo li[title="작성일"]')
    if not date_el:
        print("  ⚠️ 작성일 요소를 찾을 수 없음 → 이 페이지만 스킵")
        return True

    date_text = date_el.inner_text().split("T")[0]
    try:
        published = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        print(f"  ⚠️ 날짜 파싱 실패 ({date_text}) → 이 페이지만 스킵")
        return True

    if published < threshold_date:
        print(f"  ⚠️ 게시일 {published.date()} (< {threshold_date.date()}) → 전체 종료")
        return False

    for li in page.query_selector_all("div.boardFile ul li"):
        name = li.query_selector("span.fileName")
        btn  = li.query_selector("a.btn")
        if not (name and btn):
            continue

        filename = name.inner_text().strip() or "unknown.pdf"
        href     = btn.get_attribute("href")
        if not href:
            continue

        url      = urljoin(detail_url, href)
        safe     = filename.replace("/", "_")
        out_path = DOWNLOAD_DIR / safe

        if out_path.exists():
            print(f"    · 이미 존재: {safe}")
        else:
            print(f"    ↓ 다운로드 중: {safe}")
            try:
                res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=30)
                if res.status_code != 200:
                    print(f"      [WARN] HTTP {res.status_code} - 스킵")
                    continue

                with open(out_path, "wb") as f:
                    for chunk in res.iter_content(1024):
                        f.write(chunk)
                print(f"      ✅ 저장됨: {safe}")
            except Exception as e:
                print(f"      ❌ 다운로드 실패: {e}")
                continue

        # 📌 JSON에 저장
        if safe not in reference_data:
            reference_data[safe] = detail_url
            with open(REFERENCE_PATH, "w", encoding="utf-8") as f:
                json.dump(reference_data, f, ensure_ascii=False, indent=2)
            print(f"      📝 referenceURL.json에 추가됨: {safe}")
        else:
            print(f"      ℹ️ referenceURL.json에 이미 있음: {safe}")

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
                print(f"✅ Page {page_idx}: 링크 없음 → 종료")
                break

            detail_urls = [
                urljoin(list_url, a.get_attribute("href"))
                for a in anchors
                if a.get_attribute("href")
            ]

            print(f"\n◾ 페이지 {page_idx}: {len(detail_urls)}개 상세페이지 처리 시작")
            for url in detail_urls:
                print(f" ▶ 상세페이지: {url}")
                if not process_detail(page, url):
                    browser.close()
                    print("\n⛔ 기준일 이전 문서 발견 → 전체 종료")
                    return

            page_idx += 1

        browser.close()
        print("\n🎉 모든 PDF 다운로드 및 referenceURL 저장 완료!")

if __name__ == "__main__":
    main()
