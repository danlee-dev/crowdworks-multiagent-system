from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import requests
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime, timedelta
import json

BASE_LIST_URL = "https://www.atfis.or.kr/home/board/FB0028.do"
DOWNLOAD_DIR = Path("ReportPDF")
REFERENCE_PATH = Path("/elasticsearch/referenceURL.json")

DOWNLOAD_DIR.mkdir(exist_ok=True)
REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

# referenceURL.json 불러오기
if REFERENCE_PATH.exists():
    with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
        reference_data = json.load(f)
else:
    reference_data = {}

threshold_date = datetime.now() - timedelta(days=30)

def save_reference(filename: str, detail_url: str):
    if filename in reference_data:
        print(f"      · referenceURL.json에 이미 있음: {filename} → 건너뜁니다.")
        return

    reference_data[filename] = detail_url
    with open(REFERENCE_PATH, "w", encoding="utf-8") as f:
        json.dump(reference_data, f, ensure_ascii=False, indent=2)
    print(f"      📝 referenceURL.json에 추가됨: {filename}")


def process_detail(page, detail_url):
    try:
        page.goto(detail_url, wait_until="networkidle", timeout=60000)
    except PlaywrightTimeoutError:
        print(f"  ⚠️ 네트워크 지연, DOMContentLoaded로 재시도: {detail_url}")
        page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)

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

    items = page.query_selector_all("div.boardFile ul li")
    for li in items:
        name = li.query_selector("span.fileName")
        btn  = li.query_selector("a.btn")
        if not (name and btn):
            continue

        filename = name.inner_text().strip() or "unknown.pdf"
        href     = btn.get_attribute("href")
        if not href:
            continue

        pdf_url = urljoin(detail_url, href)
        safe    = filename.replace("/", "_")
        out     = DOWNLOAD_DIR / safe

        if out.exists():
            print(f"    · 이미 존재: {safe}")
            if safe not in reference_data:
                save_reference(safe, detail_url)
            else:
                print(f"    · referenceURL.json에 이미 있음 → 건너뜁니다.")
            continue

        print(f"    ↓ 다운로드 중: {safe}")
        try:
            r = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=30)
            r.raise_for_status()
            with open(out, "wb") as f:
                for chunk in r.iter_content(1024):
                    if chunk:
                        f.write(chunk)
            print(f"      ✅ 저장됨: {safe}")
            save_reference(safe, detail_url)
        except Exception as e:
            print(f"      [Error] 다운로드 실패: {e}")

    return True

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for page_idx in range(1, 12):
            list_url = f"{BASE_LIST_URL}?subSkinYn=N&bcaId=0&pageIndex={page_idx}"
            page.goto(list_url, wait_until="networkidle")
            anchors = page.query_selector_all("ul.galleryList li a")
            if not anchors:
                print(f"✅ Page {page_idx}: 링크 없음 → 크롤링 종료")
                break

            detail_urls = [
                urljoin(list_url, a.get_attribute("href"))
                for a in anchors if a.get_attribute("href")
            ]

            print(f"\n◾ 페이지 {page_idx}: {len(detail_urls)}개 상세페이지 처리 시작")
            for detail_url in detail_urls:
                print(f" ▶ 상세페이지: {detail_url}")
                ok = process_detail(page, detail_url)
                if not ok:
                    browser.close()
                    return

        browser.close()
        print("\n🎉 모든 PDF 다운로드 및 referenceURL 저장 완료!")

if __name__ == "__main__":
    main()
