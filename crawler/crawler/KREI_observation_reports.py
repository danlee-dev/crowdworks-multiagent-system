from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import requests
from pathlib import Path
from urllib.parse import urljoin
import time, re, json

BASE_URL = "https://www.nongnet.or.kr/front/M000000100/board/list.do"
DOWNLOAD_DIR = Path("ReportPDF")
REFERENCE_PATH = Path("/elasticsearch/referenceURL.json")

DOWNLOAD_DIR.mkdir(exist_ok=True)
REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

# referenceURL.json 로드
if REFERENCE_PATH.exists():
    with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
        reference_data = json.load(f)
else:
    reference_data = {}

def save_reference(filename: str):
    if filename in reference_data:
        print(f"      · referenceURL.json에 이미 있음: {filename} → 건너뜁니다.")
        return
    reference_data[filename] = BASE_URL
    with open(REFERENCE_PATH, "w", encoding="utf-8") as f:
        json.dump(reference_data, f, ensure_ascii=False, indent=2)
    print(f"      📝 referenceURL.json에 추가됨: {filename}")

def fetch_with_retry(url, retries=3, backoff=1):
    for i in range(1, retries+1):
        try:
            r = session.get(url, stream=True, timeout=30)
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"    ⚠️ 시도 {i} 실패: {e}")
            time.sleep(backoff)
    raise RuntimeError("다운로드 실패")

def download_all_pdfs_on_page(page):
    rows = page.query_selector_all("div.boardList table tbody tr")
    if not rows:
        print("    · 다운로드 대상 행이 없습니다.")
    for row in rows:
        subj_td = row.query_selector("td.subject.notice")
        title = subj_td.inner_text().strip() if subj_td else "unknown"

        link = row.query_selector("td.writer a")
        if not link:
            print(f"    · [{title}] PDF 링크 없음, 스킵")
            continue

        href = link.get_attribute("href")
        pdf_url = href if href.startswith("http") else urljoin(BASE_URL, href)

        safe = re.sub(r'[\\/:*?"<>|]', "_", f"{title}.pdf")
        out = DOWNLOAD_DIR / safe
        if out.exists():
            print(f"    · 이미 존재: {safe}")
            continue

        print(f"    ↓ [{title}] 다운로드 시작")
        try:
            resp = fetch_with_retry(pdf_url)
            with open(out, "wb") as f:
                for chunk in resp.iter_content(1024):
                    if chunk:
                        f.write(chunk)
            print(f"    ✅ 저장됨: {safe}")
            save_reference(safe)
        except Exception as e:
            print(f"    ❌ 다운로드 실패: {e}")

def wait_for_load(page, timeout=30000):
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded")

def set_radio_and_trigger(page, selector_id):
    page.evaluate(f'''
        const el = document.getElementById("{selector_id}");
        if (el) {{
            el.checked = true;
            el.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}
    ''')

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL, wait_until="domcontentloaded")
        time.sleep(1)

        # 당월 필터 클릭
        page.click('label[for="curntMonth"]')
        page.click("p.btnFilter button")
        wait_for_load(page)
        time.sleep(0.5)

        # 부류/품목 순회
        category_ids = page.eval_on_selector_all(
            "ul#el_category li input[type=radio]",
            "nodes => nodes.map(n => n.id)"
        )
        for cid in category_ids:
            print("🔸 부류 선택:", cid)
            set_radio_and_trigger(page, cid)
            time.sleep(0.3)

            product_ids = page.eval_on_selector_all(
                "ul#el_pdlt li input[type=radio]",
                "nodes => nodes.map(n => n.id)"
            )
            for pid in product_ids:
                print("  ▶ 품목 선택:", pid)
                set_radio_and_trigger(page, pid)
                time.sleep(0.2)

                page.click("p.btnFilter button")
                wait_for_load(page)
                time.sleep(0.5)
                download_all_pdfs_on_page(page)

        browser.close()
        print("\n🎉 모든 PDF 다운로드 완료!")

if __name__ == "__main__":
    main()
