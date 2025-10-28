import uuid
import json
from datetime import datetime
from typing import Dict, Optional, List, Any
from ..database import ChatDatabase
from .models.models import StreamingAgentState


class RunManager:
    """스트리밍 실행 생명주기 관리 및 runId 추적"""

    def __init__(self, db: ChatDatabase, websocket_manager=None):
        self.db = db
        self.websocket_manager = websocket_manager
        self.active_runs: Dict[str, StreamingAgentState] = {}

    def create_run(self, conversation_id: str, query: str, flow_type: str = "chat") -> str:
        """새 실행 생성 및 runId 반환"""
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        current_time = datetime.now().isoformat()

        # 초기 상태 생성
        initial_state: StreamingAgentState = {
            "original_query": query,
            "conversation_id": conversation_id,
            "user_id": "default_user",  # TODO: 실제 사용자 ID로 변경
            "start_time": current_time,
            "flow_type": flow_type,
            "plan": None,
            "current_step_index": 0,
            "step_results": [],
            "execution_log": [],
            "needs_replan": False,
            "replan_feedback": None,
            "final_answer": None,
            "session_id": conversation_id,
            "metadata": {
                "run_id": run_id,
                "status": "running",
                "created_at": current_time
            }
        }

        # 메모리에 저장
        self.active_runs[run_id] = initial_state

        # DB에 실행 컨텍스트 저장
        self._save_execution_context(run_id, initial_state)

        # WebSocket에 runId 매핑 등록
        if self.websocket_manager:
            self.websocket_manager.register_run(run_id, conversation_id)

        print(f"🚀 새 실행 생성: {run_id} (대화: {conversation_id})")
        return run_id

    def get_run_state(self, run_id: str) -> Optional[StreamingAgentState]:
        """runId로 현재 상태 조회 (메모리 우선, DB 폴백)"""

        # 1. 메모리에서 먼저 찾기
        if run_id in self.active_runs:
            return self.active_runs[run_id]

        # 2. DB에서 복구 시도
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM execution_contexts WHERE run_id = ?
                """, (run_id,))

                row = cursor.fetchone()
                if row:
                    context = dict(row)
                    if context["current_state"]:
                        state = json.loads(context["current_state"])
                        self.active_runs[run_id] = state  # 메모리에 다시 로드
                        print(f"🔄 실행 상태 DB에서 복구: {run_id}")
                        return state

        except Exception as e:
            print(f"⚠️ 실행 상태 복구 실패 ({run_id}): {e}")

        return None

    def update_run_state(self, run_id: str, updates: Dict[str, Any]) -> bool:
        """실행 상태 업데이트"""
        if run_id not in self.active_runs:
            print(f"⚠️ 실행을 찾을 수 없음: {run_id}")
            return False

        # 메모리 업데이트
        state = self.active_runs[run_id]
        for key, value in updates.items():
            if key in state:
                state[key] = value
            elif key in state.get("metadata", {}):
                state["metadata"][key] = value

        # DB 업데이트
        self._save_execution_context(run_id, state)

        return True

    def save_checkpoint(self, run_id: str, checkpoint_type: str, data: Dict[str, Any], step_number: Optional[int] = None):
        """중간 체크포인트 저장"""
        print(f"📍 체크포인트 저장 시도: run_id={run_id}, type={checkpoint_type}, data_keys={list(data.keys())}")

        state = self.get_run_state(run_id)
        if not state:
            print(f"⚠️ 체크포인트 저장 실패 - 실행 없음: {run_id}")
            return

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO streaming_checkpoints (
                        run_id, conversation_id, checkpoint_type,
                        checkpoint_data, step_number
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    run_id,
                    state["conversation_id"],
                    checkpoint_type,
                    json.dumps(data),
                    step_number
                ))

            print(f"📍 체크포인트 저장: {run_id} - {checkpoint_type}")

        except Exception as e:
            print(f"⚠️ 체크포인트 저장 오류: {e}")

    def request_abort(self, run_id: str, reason: str = "user_requested") -> bool:
        """중단 요청"""
        state = self.get_run_state(run_id)
        if not state:
            print(f"⚠️ 중단 요청 실패 - 실행 없음: {run_id}")
            return False

        # 상태 업데이트
        self.update_run_state(run_id, {
            "metadata": {
                **state.get("metadata", {}),
                "status": "aborted",
                "abort_reason": reason,
                "abort_time": datetime.now().isoformat()
            }
        })

        # 스트리밍 세션도 업데이트
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE streaming_sessions
                    SET abort_requested = 1, status = 'aborted'
                    WHERE run_id = ?
                """, (run_id,))

        except Exception as e:
            print(f"⚠️ 스트리밍 세션 중단 업데이트 오류: {e}")

        # WebSocket으로 중단 알림 전송
        if self.websocket_manager:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(
                    self.websocket_manager.broadcast_abort_notification(run_id, reason)
                )
            except Exception as e:
                print(f"⚠️ WebSocket 중단 알림 전송 실패: {e}")

        print(f"🛑 실행 중단 요청: {run_id} (사유: {reason})")
        return True

    def is_abort_requested(self, run_id: str) -> bool:
        """중단이 요청되었는지 확인"""
        state = self.get_run_state(run_id)
        if not state:
            return False

        status = state.get("metadata", {}).get("status")
        return status == "aborted"

    def mark_completed(self, run_id: str, final_answer: str) -> bool:
        """실행 완료 처리"""
        return self.update_run_state(run_id, {
            "final_answer": final_answer,
            "metadata": {
                "status": "completed",
                "completed_at": datetime.now().isoformat()
            }
        })

    def mark_error(self, run_id: str, error_message: str) -> bool:
        """실행 오류 처리"""
        return self.update_run_state(run_id, {
            "metadata": {
                "status": "error",
                "error_message": error_message,
                "error_at": datetime.now().isoformat()
            }
        })

    def cleanup_run(self, run_id: str):
        """실행 완료/중단 후 정리"""
        # WebSocket 매핑 해제
        if self.websocket_manager:
            self.websocket_manager.unregister_run(run_id)

        # 메모리에서 제거 (DB는 유지)
        if run_id in self.active_runs:
            del self.active_runs[run_id]
            print(f"🧹 실행 메모리 정리: {run_id}")

    def find_active_run(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """대화에서 진행 중인 실행 찾기"""
        try:
            print(f"🔍 find_active_run 호출: conversation_id={conversation_id}")

            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # 먼저 해당 대화의 모든 실행 조회
                cursor.execute("""
                    SELECT run_id, status, created_at FROM execution_contexts
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC
                """, (conversation_id,))

                all_runs = cursor.fetchall()
                print(f"📊 대화 {conversation_id}의 모든 실행: {[dict(row) for row in all_runs]}")

                # running 상태인 실행 찾기
                cursor.execute("""
                    SELECT * FROM execution_contexts
                    WHERE conversation_id = ? AND status = 'running'
                    ORDER BY created_at DESC LIMIT 1
                """, (conversation_id,))

                row = cursor.fetchone()
                if row:
                    result = dict(row)
                    # print(f"✅ 활성 실행 발견: {result}")
                    return result
                else:
                    print(f"❌ 활성 실행 없음")

        except Exception as e:
            print(f"⚠️ 활성 실행 조회 오류: {e}")

        return None

    def get_checkpoints(self, run_id: str, checkpoint_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """체크포인트 조회"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                if checkpoint_type:
                    cursor.execute("""
                        SELECT * FROM streaming_checkpoints
                        WHERE run_id = ? AND checkpoint_type = ?
                        ORDER BY timestamp ASC
                    """, (run_id, checkpoint_type))
                else:
                    cursor.execute("""
                        SELECT * FROM streaming_checkpoints
                        WHERE run_id = ?
                        ORDER BY timestamp ASC
                    """, (run_id,))

                checkpoints = []
                for row in cursor.fetchall():
                    checkpoint = dict(row)
                    checkpoint["checkpoint_data"] = json.loads(checkpoint["checkpoint_data"])
                    checkpoints.append(checkpoint)

                return checkpoints

        except Exception as e:
            print(f"⚠️ 체크포인트 조회 오류: {e}")
            return []

    def _save_execution_context(self, run_id: str, state: StreamingAgentState):
        """실행 컨텍스트를 DB에 저장"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO execution_contexts (
                        run_id, conversation_id, original_query, flow_type,
                        plan, current_state, updated_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id,
                    state["conversation_id"],
                    state["original_query"],
                    state.get("flow_type"),
                    json.dumps(state.get("plan")) if state.get("plan") else None,
                    json.dumps(state),
                    datetime.now().isoformat(),
                    state.get("metadata", {}).get("status", "running")
                ))

        except Exception as e:
            print(f"⚠️ 실행 컨텍스트 저장 오류: {e}")


# 전역 인스턴스 (싱글톤 패턴)
_run_manager_instance: Optional[RunManager] = None

def get_run_manager(db: ChatDatabase) -> RunManager:
    """RunManager 싱글톤 인스턴스 반환"""
    global _run_manager_instance
    if _run_manager_instance is None:
        _run_manager_instance = RunManager(db)
    return _run_manager_instance
