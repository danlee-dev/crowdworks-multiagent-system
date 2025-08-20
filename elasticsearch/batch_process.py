# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import shutil
from pathlib import Path

# 표준 입출력 인코딩 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def get_unprocessed_files():
    """凸이 없는 미처리 JSON 파일 목록 반환"""
    datas_dir = Path('datas')
    unprocessed_files = []
    
    for file_path in datas_dir.glob('*.json'):
        if not file_path.name.startswith('凸'):
            unprocessed_files.append(file_path.name)
    
    return sorted(unprocessed_files)

def update_input_path(file_name):
    """preprocess_data.py의 INPUT_PATH를 현재 파일로 수정"""
    preprocess_file = Path('preprocess_data.py')
    
    # 파일 읽기
    with open(preprocess_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # INPUT_PATH 라인 찾아서 수정
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.strip().startswith("INPUT_PATH = "):
            lines[i] = f"INPUT_PATH = 'datas/{file_name}'"
            break
    
    # 파일 쓰기
    with open(preprocess_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"📝 INPUT_PATH 업데이트: {file_name}")

def run_preprocessing():
    """전처리 스크립트 실행"""
    print("🔄 전처리 실행 중...")
    print("=" * 50)
    
    # 실시간 출력을 위해 capture_output=False 사용
    result = subprocess.run([sys.executable, 'preprocess_data.py'], 
                          encoding='utf-8')
    
    print("=" * 50)
    if result.returncode != 0:
        raise Exception(f"전처리 실패: 반환 코드 {result.returncode}")
    
    print("✅ 전처리 완료")
    return "preprocess completed"

def run_embedding():
    """임베딩 스크립트 실행 (multi index 구조)"""
    print("🤖 멀티 인덱스 임베딩 실행 중...")
    print("=" * 50)
    
    # multi_index_embed.py 실행
    result = subprocess.run([sys.executable, 'multi_index_embed.py'], 
                          encoding='utf-8')
    
    print("=" * 50)
    if result.returncode != 0:
        raise Exception(f"임베딩 실패: 반환 코드 {result.returncode}")
    
    print("✅ 멀티 인덱스 임베딩 완료")
    return "embedding completed"

def mark_as_processed(file_name):
    """파일명 앞에 凸 추가하여 처리 완료 표시"""
    old_path = Path('datas') / file_name
    new_path = Path('datas') / f"凸{file_name}"
    
    old_path.rename(new_path)
    print(f"🌟 처리 완료 표시: 凸{file_name}")

def cleanup_temp_files():
    """임시 파일들 정리"""
    temp_files = ['preprocessed_data.json']
    
    for temp_file in temp_files:
        if Path(temp_file).exists():
            Path(temp_file).unlink()
            print(f"🗑️  임시 파일 삭제: {temp_file}")

def process_single_file(file_name):
    """단일 파일 처리"""
    print(f"\n{'='*60}")
    print(f"📄 처리 시작: {file_name}")
    print(f"{'='*60}")
    
    try:
        # 1. INPUT_PATH 수정
        update_input_path(file_name)
        
        # 2. 전처리 실행
        preprocess_output = run_preprocessing()
        
        # 3. 임베딩 실행 (multi index)
        embedding_output = run_embedding()
        
        # 4. 처리 완료 표시
        mark_as_processed(file_name)
        
        # 5. 임시 파일 정리
        cleanup_temp_files()
        
        print(f"🎉 {file_name} 처리 완료!")
        return True
        
    except Exception as e:
        print(f"❌ {file_name} 처리 실패: {e}")
        print("📋 오류 상세:")
        print(str(e))
        return False

def show_progress(current, total, file_name):
    """진행 상황 표시"""
    percentage = (current / total) * 100
    bar_length = 40
    filled_length = int(bar_length * current // total)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    
    print(f"\n📊 전체 진행률: [{bar}] {percentage:.1f}% ({current}/{total})")
    print(f"🎯 현재 파일: {file_name}")

def main():
    """메인 배치 처리 함수 (multi index)"""
    print("🚀 농업 데이터 멀티 인덱스 배치 처리 시스템 시작")
    print("="*60)
    
    # 미처리 파일 목록 수집
    unprocessed_files = get_unprocessed_files()
    
    # 50개로 제한
    unprocessed_files = unprocessed_files[:50]
    
    if not unprocessed_files:
        print("🎉 모든 파일이 이미 처리되었습니다! (凸 표시 확인)")
        return
    
    total_files = len(unprocessed_files)
    print(f"📋 처리 대상 파일: {total_files}개")
    print("파일 목록:")
    for i, file_name in enumerate(unprocessed_files, 1):
        print(f"  {i:2d}. {file_name}")
    
    print(f"\n🔄 배치 처리를 시작합니다...")
    
    # 성공/실패 통계
    success_count = 0
    failed_files = []
    
    # 각 파일 순차 처리
    for i, file_name in enumerate(unprocessed_files, 1):
        show_progress(i, total_files, file_name)
        
        if process_single_file(file_name):
            success_count += 1
        else:
            failed_files.append(file_name)
    
    # 최종 결과 출력
    print(f"\n{'='*60}")
    print("🏁 멀티 인덱스 배치 처리 완료!")
    print(f"{'='*60}")
    print(f"✅ 성공: {success_count}개")
    print(f"❌ 실패: {len(failed_files)}개")
    
    if failed_files:
        print("\n📋 실패한 파일들:")
        for file_name in failed_files:
            print(f"  - {file_name}")
        print("\n💡 실패한 파일들은 수동으로 확인이 필요합니다.")
    else:
        print("\n🎉 모든 파일이 성공적으로 처리되었습니다!")
    
    print(f"\n📊 Elasticsearch 상태:")
    print(f"└── documents_text, documents_table 인덱스에 데이터가 추가되었습니다.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  사용자에 의해 중단되었습니다.")
        print("💡 이미 처리된 파일들은 凸 표시로 확인할 수 있습니다.")
    except Exception as e:
        print(f"\n💥 예상치 못한 오류 발생: {e}")
        sys.exit(1) 