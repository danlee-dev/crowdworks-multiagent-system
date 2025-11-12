import os
import asyncio
import aiohttp
import requests
from pathlib import Path
import json
from urllib.parse import unquote

API_BASE   = "https://kc-ku.crowdworks.ai/v1"
API_KEY    = os.getenv("CROWD_API_KEY")
HEADERS    = {"x-api-key": API_KEY}

UPLOAD_DIR = Path("/ReportPDF")
OUTPUT_DIR = Path("/datas")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

POLL_DELAY = 1
DOC_TIMEOUT = 20 * 3600  # 20 hours


def _sync_upload_with_requests(pdf_path: Path) -> str:
    """
    동기 requests로 업로드만 수행.
    - files=("file", (filename, fileobj, content_type)) 형태로 전달
    - 한글 파일명에 대해 requests가 filename*을 자동으로 셋업
    - 추가로 document_title 필드에 원본 파일명(한글)을 명시적으로 전달
    """
    url = f"{API_BASE}/documents/"
    with pdf_path.open("rb") as f:
        files = {
            "file": (pdf_path.name, f, "application/pdf"),
        }
        data = {
            "llm_metadata_extraction_target": "false",
            "document_title": pdf_path.name,  # 서버가 이 값을 제목으로 사용하도록
        }
        r = requests.post(url, headers=HEADERS, files=files, data=data, timeout=60)
        r.raise_for_status()
        body = r.json()
        return body["uuid"]


async def upload_and_process(session: aiohttp.ClientSession, pdf_path: Path):
    name = pdf_path.name
    try:
        print(f"[{name}] → 시작")
        print(f"[{name}] • 업로드 준비")
        # 동기 업로드를 스레드에서 실행하여 비동기 파이프라인 유지
        doc_id = await asyncio.to_thread(_sync_upload_with_requests, pdf_path)
        print(f"[{name}] • 문서 ID: {doc_id}")
        print(f"[{name}] • 처리 대기 및 다운로드")

        await asyncio.wait_for(
            _wait_and_download(session, doc_id, pdf_path.stem),
            timeout=DOC_TIMEOUT
        )
        print(f"[{name}] • 완료")

    except asyncio.TimeoutError:
        print(f"❌ [{name}] 타임아웃({DOC_TIMEOUT}s)")
    except Exception as e:
        print(f"❌ [{name}] 오류: {e}")


async def _wait_and_download(session: aiohttp.ClientSession, doc_id: str, stem: str):
    status_url   = f"{API_BASE}/documents/{doc_id}/status"
    download_url = f"{API_BASE}/documents/{doc_id}/json"

    # 상태 폴링
    while True:
        async with session.get(status_url) as resp:
            resp.raise_for_status()
            status = (await resp.json()).get("status")
        if status == "SUCCESS":
            break
        if status == "ERROR":
            raise RuntimeError("문서 처리 중 ERROR")
        await asyncio.sleep(POLL_DELAY)

    # JSON 원문 그대로 받아 쓰기
    async with session.get(download_url) as resp:
        resp.raise_for_status()
        data = await resp.json()   # dict

    # 과도기 방어 로직: 서버가 퍼센트인코딩된 제목을 줄 경우 복원
    if isinstance(data, dict) and isinstance(data.get("document_title"), str):
        data["document_title"] = unquote(data["document_title"])

    out_path = OUTPUT_DIR / f"{stem}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ [{stem}] 정렬된 JSON 저장됨 → {out_path}")


async def main():
    if not API_KEY:
        print("⚠️ 환경변수 CROWD_API_KEY가 설정되어 있지 않습니다.")
        return

    pdfs = list(UPLOAD_DIR.glob("*.pdf"))
    if not pdfs:
        print("⚠️ 업로드할 PDF가 없습니다.")
        return

    timeout = aiohttp.ClientTimeout(total=None)
    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
        await asyncio.gather(*(upload_and_process(session, pdf) for pdf in pdfs))


if __name__ == "__main__":
    asyncio.run(main())
