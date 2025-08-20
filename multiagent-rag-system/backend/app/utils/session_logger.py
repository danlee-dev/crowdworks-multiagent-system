"""
세션별 로그 분리 시스템
각 사용자 세션마다 독립적인 로그 출력 제공
"""
import uuid
import threading
from typing import Dict, List, Optional
from datetime import datetime
import sys


class SessionLogger:
    """세션별로 독립적인 로그를 관리하는 클래스"""
    
    def __init__(self):
        self._session_logs: Dict[str, List[Dict]] = {}
        self._lock = threading.Lock()
    
    def log(self, session_id: str, message: str, level: str = "INFO", component: str = "System"):
        """세션별 로그 추가"""
        with self._lock:
            if session_id not in self._session_logs:
                self._session_logs[session_id] = []
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "component": component,
                "message": message,
                "session_id": session_id
            }
            
            self._session_logs[session_id].append(log_entry)
            
            # 콘솔에 세션 구분자와 함께 출력
            session_prefix = f"[{session_id[:8]}] {component}"
            print(f"{session_prefix}: {message}")
    
    def get_session_logs(self, session_id: str) -> List[Dict]:
        """특정 세션의 모든 로그 반환"""
        with self._lock:
            return self._session_logs.get(session_id, [])
    
    def clear_session_logs(self, session_id: str):
        """특정 세션의 로그 삭제"""
        with self._lock:
            if session_id in self._session_logs:
                del self._session_logs[session_id]
    
    def get_all_sessions(self) -> List[str]:
        """모든 활성 세션 ID 반환"""
        with self._lock:
            return list(self._session_logs.keys())
    
    def cleanup_old_sessions(self, max_sessions: int = 50):
        """오래된 세션 로그 정리 (메모리 절약)"""
        with self._lock:
            if len(self._session_logs) > max_sessions:
                # 가장 오래된 세션부터 삭제
                sessions_to_remove = list(self._session_logs.keys())[:-max_sessions]
                for session_id in sessions_to_remove:
                    del self._session_logs[session_id]


# 전역 세션 로거 인스턴스
session_logger = SessionLogger()


class SessionContextLogger:
    """특정 세션에 바인딩된 로거 클래스"""
    
    def __init__(self, session_id: str, component: str = "System"):
        self.session_id = session_id
        self.component = component
    
    def info(self, message: str):
        """정보 레벨 로그"""
        session_logger.log(self.session_id, message, "INFO", self.component)
    
    def error(self, message: str):
        """에러 레벨 로그"""
        session_logger.log(self.session_id, message, "ERROR", self.component)
    
    def warning(self, message: str):
        """경고 레벨 로그"""
        session_logger.log(self.session_id, message, "WARNING", self.component)
    
    def debug(self, message: str):
        """디버그 레벨 로그"""
        session_logger.log(self.session_id, message, "DEBUG", self.component)


def get_session_logger(session_id: str, component: str = "System") -> SessionContextLogger:
    """세션별 로거 인스턴스 생성"""
    return SessionContextLogger(session_id, component)


def print_session_separated(session_id: str, component: str, message: str):
    """세션 구분 print 함수 (기존 print 대체용)"""
    session_prefix = f"[{session_id[:8]}] {component}"
    print(f"{session_prefix}: {message}")


# 현재 실행 중인 세션 컨텍스트를 저장하는 스레드 로컬 저장소
import threading
_thread_local = threading.local()

def set_current_session(session_id: str):
    """현재 스레드의 세션 ID 설정"""
    _thread_local.session_id = session_id

def get_current_session() -> str:
    """현재 스레드의 세션 ID 가져오기"""
    return getattr(_thread_local, 'session_id', 'unknown')

def session_print(component: str, message: str):
    """현재 세션의 로그 출력 (session_id가 자동으로 설정됨)"""
    session_id = get_current_session()
    print_session_separated(session_id, component, message)