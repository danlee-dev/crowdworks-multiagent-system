#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rename.py
- 목적: 'preprocessed_datas' 디렉터리 내 모든 JSON 파일의 파일명 맨 앞에 '凸' 접두사를 붙여 재처리를 방지.
- 기본 대상 경로: /root/workspace/crowdworks/elasticsearch/preprocessed_datas
- 기능: 드라이런(--dry-run) 옵션, 처리 요약 출력
"""

from pathlib import Path
import argparse
import sys


def rename_files(datas_dir: Path, dry_run: bool = False) -> None:
    if not datas_dir.is_dir():
        print(f"❌ 대상 디렉터리가 존재하지 않습니다: {datas_dir}", file=sys.stderr)
        sys.exit(1)

    total = 0
    prefixed_already = 0
    renamed = 0
    conflicts = 0

    for src in sorted(datas_dir.glob("*.json")):
        total += 1
        fname = src.name

        # 이미 '凸'로 시작하면 건너뜀
        if fname.startswith("凸"):
            prefixed_already += 1
            continue

        dest = src.with_name(f"凸{fname}")
        if dest.exists():
            conflicts += 1
            print(f"[SKIP] 대상 경로가 이미 존재합니다: {dest}")
            continue

        if dry_run:
            print(f"[DRY] {src} -> {dest}")
        else:
            src.rename(dest)
            print(f"[OK]  {src.name} -> {dest.name}")
        renamed += 1

    print("\n== 요약 ==")
    print(f"- 전체 검사 파일: {total}")
    print(f"- 이미 '凸' 접두사라 건너뜀: {prefixed_already}")
    print(f"- 리네임 완료: {renamed}{' (드라이런)' if dry_run else ''}")
    print(f"- 경로 충돌로 건너뜀: {conflicts}")


def main() -> None:
    parser = argparse.ArgumentParser(description="preprocessed_datas의 모든 JSON 파일 앞에 '凸' 접두사 부여")
    parser.add_argument(
        "--datas-dir",
        type=Path,
        default=Path("/root/workspace/crowdworks/elasticsearch/preprocessed_datas"),
        help="대상 디렉터리 (기본: /root/workspace/crowdworks/elasticsearch/preprocessed_datas)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 변경 없이 예정된 리네임만 출력",
    )
    args = parser.parse_args()

    rename_files(args.datas_dir, args.dry_run)


if __name__ == "__main__":
    main() 