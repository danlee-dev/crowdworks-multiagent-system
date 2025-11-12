#!/usr/bin/env python3
import sys
from pathlib import Path
import shutil

def archive_reportpdf(src_dir: str = "ReportPDF", dst_dir: str = "ReferencePDF"):
    src = Path(src_dir)
    dst = Path(dst_dir)

    # 원본 디렉토리 검사
    if not src.exists():
        print(f"Error: '{src_dir}' 폴더를 찾을 수 없습니다.", file=sys.stderr)
        return
    if not src.is_dir():
        print(f"Error: '{src_dir}' 는 폴더가 아닙니다.", file=sys.stderr)
        return

    # 대상 디렉토리 생성
    dst.mkdir(parents=True, exist_ok=True)

    moved = 0
    for file in src.iterdir():
        if file.is_file():
            try:
                shutil.move(str(file), dst / file.name)
                moved += 1
            except Exception as e:
                print(f"Failed to move {file.name}: {e}", file=sys.stderr)

    print(f"아카이브 완료: {moved}개 파일을 '{dst_dir}' 로 이동했습니다.")

if __name__ == "__main__":
    # 인자를 주지 않으면 기본 폴더 사용
    archive_reportpdf("ReportPDF", "ReferencePDF")
