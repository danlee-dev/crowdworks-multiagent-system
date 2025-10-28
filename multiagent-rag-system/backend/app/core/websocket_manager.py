import asyncio
import json
from typing import Dict, List, Set
from fastapi import WebSocket, WebSocketDisconnect


class WebSocketManager:
    """WebSocket 연결 관리 및 실시간 상태 동기화"""
    
    def __init__(self):
        # conversation_id -> WebSocket 연결 리스트
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # run_id -> conversation_id 매핑
        self.run_to_conversation: Dict[str, str] = {}
        # 전체 연결된 클라이언트 집합
        self.all_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket, conversation_id: str):
        """새 WebSocket 연결 수락 및 등록"""
        await websocket.accept()
        
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = []
        
        self.active_connections[conversation_id].append(websocket)
        self.all_connections.add(websocket)
        
        print(f"🔌 WebSocket 연결됨: {conversation_id} (총 {len(self.all_connections)}개 연결)")
    
    def disconnect(self, websocket: WebSocket, conversation_id: str):
        """WebSocket 연결 해제 및 정리"""
        if conversation_id in self.active_connections:
            if websocket in self.active_connections[conversation_id]:
                self.active_connections[conversation_id].remove(websocket)
            
            # 해당 대화방에 연결이 없으면 제거
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]
        
        self.all_connections.discard(websocket)
        print(f"🔌 WebSocket 연결 해제: {conversation_id} (총 {len(self.all_connections)}개 연결)")
    
    def register_run(self, run_id: str, conversation_id: str):
        """runId와 conversation_id 매핑 등록"""
        self.run_to_conversation[run_id] = conversation_id
        print(f"📝 RunId 매핑 등록: {run_id} -> {conversation_id}")
    
    def unregister_run(self, run_id: str):
        """runId 매핑 해제"""
        if run_id in self.run_to_conversation:
            conversation_id = self.run_to_conversation[run_id]
            del self.run_to_conversation[run_id]
            print(f"📝 RunId 매핑 해제: {run_id} -> {conversation_id}")
    
    async def send_to_conversation(self, conversation_id: str, message: dict):
        """특정 대화방의 모든 클라이언트에게 메시지 전송"""
        if conversation_id not in self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections[conversation_id]:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                print(f"⚠️ WebSocket 전송 오류: {e}")
                disconnected.append(connection)
        
        # 끊어진 연결 정리
        for conn in disconnected:
            self.disconnect(conn, conversation_id)
    
    async def send_to_run(self, run_id: str, message: dict):
        """특정 runId의 대화방에 메시지 전송"""
        if run_id in self.run_to_conversation:
            conversation_id = self.run_to_conversation[run_id]
            await self.send_to_conversation(conversation_id, message)
    
    async def broadcast_status_update(self, run_id: str, status_data: dict):
        """상태 업데이트를 해당 대화방에 브로드캐스트"""
        message = {
            "type": "status_update",
            "run_id": run_id,
            "data": status_data,
            "timestamp": asyncio.get_event_loop().time()
        }
        await self.send_to_run(run_id, message)
    
    async def broadcast_abort_notification(self, run_id: str, reason: str):
        """중단 알림을 해당 대화방에 브로드캐스트"""
        message = {
            "type": "abort_notification", 
            "run_id": run_id,
            "reason": reason,
            "timestamp": asyncio.get_event_loop().time()
        }
        await self.send_to_run(run_id, message)
    
    async def broadcast_completion_notification(self, run_id: str, result_summary: dict):
        """완료 알림을 해당 대화방에 브로드캐스트"""
        message = {
            "type": "completion_notification",
            "run_id": run_id,
            "summary": result_summary,
            "timestamp": asyncio.get_event_loop().time()
        }
        await self.send_to_run(run_id, message)
    
    def get_conversation_connection_count(self, conversation_id: str) -> int:
        """특정 대화방의 연결 수 반환"""
        return len(self.active_connections.get(conversation_id, []))
    
    def get_total_connections(self) -> int:
        """전체 연결 수 반환"""
        return len(self.all_connections)


# 전역 WebSocket 관리자 인스턴스
websocket_manager = WebSocketManager()