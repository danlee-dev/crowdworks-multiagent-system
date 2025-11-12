# atfis_playwright_market_segment_last30d.py

from playwright.sync_api import sync_playwright
import os
import urllib.parse
import requests
from datetime import datetime, timedelta
import json
from pathlib import Path

BASE_LIST_URL = "https://www.atfis.or.kr/home/board/FB0027.do?subSkinYn=N&bcaId=0&pageIndex={page}"
DOWNLOAD_DIR = Path("ReportPDF")
REFERENCE_PATH = Path("/elasticsearch/referenceURL.json")

DOWNLOAD_DIR.mkdir(exist_ok=True)
REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

# 기존 referenceURL.json 로딩
if REFERENCE_PATH.exists():
    with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
        reference_data = json.load(f)
else:
    reference_data = {}

threshold_date = datetime.now() - timedelta(days=30)

def download_pdf_from_detail(page, api, detail_url):
    page.goto(detail_url)
    page.wait_for_selector("div.boardFile ul li", timeout=5000)

    # — 작성일 체크 —
    date_el = page.query_selector('ul.boardWriteInfo li[title="작성일"]')
    if not date_el:
        print("    ⚠️ 작성일 요소를 찾을 수 없음 → 스킵")
        return True

    date_text = date_el.inner_text().strip().split("T")[0]
    try:
        published = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        print(f"    ⚠️ 날짜 파싱 실패 ({date_text}) → 스킵")
        return True

    if published < threshold_date:
        print(f"    ⚠️ 게시일 {published.date()} (< {threshold_date.date()}) → 전체 종료")
        return False

    # — 다운로드 정보 추출 —
    span = page.query_selector("div.boardFile ul li span.fileName")
    real_filename = span.inner_text().strip() if span else None

    link = page.query_selector("div.boardFile ul li a.btn")
    if not link:
        print("    ⚠️ 다운로드 버튼을 찾을 수 없음 → 스킵")
        return True

    href = link.get_attribute("href")
    pdf_url = urllib.parse.urljoin(detail_url, href)
    print("    ▶ 다운로드 URL:", pdf_url)

    # 다운로드 실행
    return download_pdf(api, pdf_url, real_filename, detail_url)

def download_pdf(session, pdf_url, filename, detail_url):
    if filename and filename.lower().endswith('.pdf'):
        save_name = filename
    else:
        save_name = filename or os.path.basename(urllib.parse.urlparse(pdf_url).path)

    safe_name = save_name.replace("/", "_")
    out_path = DOWNLOAD_DIR / safe_name

    if out_path.exists():
        print(f"    · 이미 존재: {safe_name} → 건너뜁니다.")
        return True


    res = session.get(pdf_url)
    if not res.ok:
        print(f"    ✖ 다운로드 실패: {pdf_url} - {res.status_code}")
        return True  # 실패 시에도 전체 종료는 아님

    with open(out_path, "wb") as f:
        f.write(res.body())
    print(f"    ✔ 저장됨: {safe_name}")

    if safe_name in reference_data:
        print(f"    · referenceURL.json에 이미 있음: {safe_name} → 건너뜁니다.")
        return True

    # referenceURL.json에 기록
    reference_data[safe_name] = detail_url
    with open(REFERENCE_PATH, "w", encoding="utf-8") as f:
        json.dump(reference_data, f, ensure_ascii=False, indent=2)
    print(f"    📝 referenceURL.json에 추가됨: {safe_name}")

    return True

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        api = page.request

        for idx in range(1, 14):
            list_url = BASE_LIST_URL.format(page=idx)
            print(f"\n◾ 페이지 {idx}: {list_url}")
            page.goto(list_url)
            page.wait_for_selector("ul.galleryList li a", timeout=5000)

            anchors = page.query_selector_all("ul.galleryList li a")
            detail_urls = [
                urllib.parse.urljoin(list_url, a.get_attribute("href"))
                for a in anchors if a.get_attribute("href")
            ]

            for detail_url in detail_urls:
                print(" ▶ 상세페이지:", detail_url)
                ok = download_pdf_from_detail(page, api, detail_url)
                if not ok:
                    print("⛔ 기준일 이전 문서 발견 → 전체 종료")
                    browser.close()
                    return

        browser.close()
        print("\n🎉 모든 PDF 다운로드 및 referenceURL 저장 완료!")

if __name__ == "__main__":
    run()
