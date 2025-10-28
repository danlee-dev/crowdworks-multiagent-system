import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
import os

class ChatDatabase:
    def __init__(self, db_path: str = "chat_history.db"):
        self.db_path = db_path
        self.init_database()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def init_database(self):
        """데이터베이스 초기화 및 테이블 생성"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 기존 테이블 확인
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'")
            table_exists = cursor.fetchone()

            # 기존 테이블에 새 컬럼들 추가 (기존 데이터 보존)
            if table_exists:
                try:
                    # projects 테이블 생성 (없는 경우만)
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
                    if not cursor.fetchone():
                        cursor.execute("""CREATE TABLE IF NOT EXISTS projects (
                            id TEXT PRIMARY KEY,
                            title TEXT NOT NULL,
                            description TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            user_id TEXT,
                            is_deleted BOOLEAN DEFAULT 0
                        )""")
                        print("✅ projects 테이블 생성")

                    # conversations 테이블에 project_id 컬럼 추가
                    cursor.execute("PRAGMA table_info(conversations)")
                    conv_columns = [col[1] for col in cursor.fetchall()]

                    if "project_id" not in conv_columns:
                        cursor.execute("ALTER TABLE conversations ADD COLUMN project_id TEXT")
                        print("✅ conversations 테이블에 project_id 컬럼 추가")

                    # messages 테이블에 새 컬럼들 확인 및 추가
                    cursor.execute("PRAGMA table_info(messages)")
                    columns = [col[1] for col in cursor.fetchall()]

                    new_columns = [
                        ("charts", "JSON"),
                        ("search_results", "JSON"),
                        ("sources", "JSON"),
                        ("full_data_dict", "JSON"),
                        ("section_data_dicts", "JSON"),
                        ("message_state", "JSON"),
                        ("section_headers", "JSON"),
                        ("status_history", "JSON"),
                        ("run_id", "TEXT"),
                        ("streaming_status", "TEXT CHECK(streaming_status IN ('running', 'aborted', 'completed', 'error'))"),
                        ("abort_requested", "BOOLEAN DEFAULT 0"),
                        ("abort_reason", "TEXT"),
                        ("parent_message_id", "INTEGER"),
                        ("message_pair_id", "TEXT"),
                        ("tokens_used", "INTEGER"),
                        ("processing_time_ms", "INTEGER"),
                        ("last_checkpoint", "TEXT")
                    ]

                    for col_name, col_type in new_columns:
                        if col_name not in columns:
                            cursor.execute(f"ALTER TABLE messages ADD COLUMN {col_name} {col_type}")
                            print(f"✅ messages 테이블에 {col_name} 컬럼 추가")

                except Exception as e:
                    print(f"⚠️ 테이블 스키마 업데이트 중 오류: {e}")

            if not table_exists:
                print("🔧 SQLite 데이터베이스 초기화 중...")

                # 테이블 생성 SQL들을 개별적으로 실행
                tables_sql = [
                    """CREATE TABLE IF NOT EXISTS projects (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        user_id TEXT,
                        is_deleted BOOLEAN DEFAULT 0
                    )""",

                    """CREATE TABLE IF NOT EXISTS conversations (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        project_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        user_id TEXT,
                        is_deleted BOOLEAN DEFAULT 0,
                        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
                    )""",

                    """CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id TEXT NOT NULL,
                        type TEXT NOT NULL CHECK(type IN ('user', 'assistant')),
                        content TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_streaming BOOLEAN DEFAULT 0,
                        was_aborted BOOLEAN DEFAULT 0,
                        team_id TEXT,
                        charts JSON,
                        search_results JSON,
                        sources JSON,
                        full_data_dict JSON,
                        section_data_dicts JSON,
                        message_state JSON,
                        section_headers JSON,
                        status_history JSON,
                        run_id TEXT,
                        streaming_status TEXT CHECK(streaming_status IN ('running', 'aborted', 'completed', 'error')),
                        abort_requested BOOLEAN DEFAULT 0,
                        abort_reason TEXT,
                        parent_message_id INTEGER,
                        message_pair_id TEXT,
                        tokens_used INTEGER,
                        processing_time_ms INTEGER,
                        last_checkpoint TEXT,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                    )""",

                    """CREATE TABLE IF NOT EXISTS message_states (
                        message_id INTEGER PRIMARY KEY,
                        status TEXT CHECK(status IN ('streaming', 'completed', 'aborted')),
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        duration_ms INTEGER,
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    )""",

                    """CREATE TABLE IF NOT EXISTS status_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id INTEGER NOT NULL,
                        status_message TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        step_number INTEGER,
                        total_steps INTEGER,
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    )""",

                    """CREATE TABLE IF NOT EXISTS charts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id INTEGER NOT NULL,
                        chart_type TEXT NOT NULL,
                        chart_data JSON NOT NULL,
                        position INTEGER NOT NULL,
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    )""",

                    """CREATE TABLE IF NOT EXISTS search_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id INTEGER NOT NULL,
                        query TEXT NOT NULL,
                        results JSON NOT NULL,
                        is_visible BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    )""",

                    """CREATE TABLE IF NOT EXISTS sources (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id INTEGER NOT NULL,
                        source_type TEXT NOT NULL,
                        title TEXT,
                        content TEXT,
                        metadata JSON,
                        relevance_score REAL,
                        position INTEGER,
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    )""",

                    """CREATE TABLE IF NOT EXISTS streaming_sessions (
                        conversation_id TEXT PRIMARY KEY,
                        current_message TEXT,
                        current_charts JSON,
                        status TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        run_id TEXT,
                        can_abort BOOLEAN DEFAULT 1,
                        abort_requested BOOLEAN DEFAULT 0,
                        current_step INTEGER DEFAULT 0,
                        total_steps INTEGER DEFAULT 0,
                        step_results JSON,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                    )""",

                    """CREATE TABLE IF NOT EXISTS streaming_checkpoints (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL,
                        conversation_id TEXT NOT NULL,
                        checkpoint_type TEXT NOT NULL,
                        checkpoint_data JSON NOT NULL,
                        step_number INTEGER,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                    )""",

                    """CREATE TABLE IF NOT EXISTS execution_contexts (
                        run_id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        original_query TEXT NOT NULL,
                        flow_type TEXT CHECK(flow_type IN ('chat', 'task')),
                        plan JSON,
                        current_state JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status TEXT CHECK(status IN ('running', 'completed', 'aborted', 'error')),
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                    )"""
                ]

                # 인덱스 생성
                indexes_sql = [
                    "CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at)",
                    "CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project_id)",
                    "CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at)",
                    "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)",
                    "CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_messages_run_id ON messages(run_id)",
                    "CREATE INDEX IF NOT EXISTS idx_messages_streaming_status ON messages(streaming_status)",
                    "CREATE INDEX IF NOT EXISTS idx_status_history_message ON status_history(message_id)",
                    "CREATE INDEX IF NOT EXISTS idx_charts_message ON charts(message_id)",
                    "CREATE INDEX IF NOT EXISTS idx_search_results_message ON search_results(message_id)",
                    "CREATE INDEX IF NOT EXISTS idx_sources_message ON sources(message_id)",
                    "CREATE INDEX IF NOT EXISTS idx_streaming_sessions_run_id ON streaming_sessions(run_id)",
                    "CREATE INDEX IF NOT EXISTS idx_checkpoints_run_id ON streaming_checkpoints(run_id)",
                    "CREATE INDEX IF NOT EXISTS idx_checkpoints_timestamp ON streaming_checkpoints(timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_execution_contexts_status ON execution_contexts(status)",
                    "CREATE INDEX IF NOT EXISTS idx_execution_contexts_conversation ON execution_contexts(conversation_id)"
                ]

                # 테이블 생성
                for sql in tables_sql:
                    cursor.execute(sql)

                # 인덱스 생성
                for sql in indexes_sql:
                    cursor.execute(sql)

                print("✅ SQLite 데이터베이스 초기화 완료")
            else:
                print("📊 기존 SQLite 데이터베이스 사용")

    # === Projects ===
    def create_project(self, project_id: str, title: str, description: Optional[str] = None, user_id: Optional[str] = None) -> Dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 먼저 프로젝트가 이미 존재하는지 확인
            cursor.execute("""
                SELECT id, title, description, created_at, updated_at FROM projects
                WHERE id = ? AND is_deleted = 0
            """, (project_id,))

            existing = cursor.fetchone()
            if existing:
                return dict(existing)

            # 존재하지 않으면 새로 생성
            cursor.execute("""
                INSERT INTO projects (id, title, description, user_id)
                VALUES (?, ?, ?, ?)
            """, (project_id, title, description, user_id))

            return {
                "id": project_id,
                "title": title,
                "description": description,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

    def get_project(self, project_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM projects
                WHERE id = ? AND is_deleted = 0
            """, (project_id,))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_all_projects(self, user_id: Optional[str] = None) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if user_id:
                cursor.execute("""
                    SELECT p.*, COUNT(c.id) as conversation_count
                    FROM projects p
                    LEFT JOIN conversations c ON p.id = c.project_id AND c.is_deleted = 0
                    WHERE p.user_id = ? AND p.is_deleted = 0
                    GROUP BY p.id
                    ORDER BY p.updated_at DESC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT p.*, COUNT(c.id) as conversation_count
                    FROM projects p
                    LEFT JOIN conversations c ON p.id = c.project_id AND c.is_deleted = 0
                    WHERE p.is_deleted = 0
                    GROUP BY p.id
                    ORDER BY p.updated_at DESC
                """)

            return [dict(row) for row in cursor.fetchall()]

    def update_project_title(self, project_id: str, title: str, description: Optional[str] = None) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if description is not None:
                cursor.execute("""
                    UPDATE projects
                    SET title = ?, description = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (title, description, project_id))
            else:
                cursor.execute("""
                    UPDATE projects
                    SET title = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (title, project_id))

            return cursor.rowcount > 0

    def delete_project(self, project_id: str, soft_delete: bool = True) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if soft_delete:
                cursor.execute("""
                    UPDATE projects
                    SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (project_id,))
            else:
                cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))

            return cursor.rowcount > 0

    # === Conversations ===
    def create_conversation(self, conversation_id: str, title: str, user_id: Optional[str] = None, project_id: Optional[str] = None) -> Dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 먼저 대화가 이미 존재하는지 확인
            cursor.execute("""
                SELECT id, title, project_id, created_at, updated_at FROM conversations
                WHERE id = ? AND is_deleted = 0
            """, (conversation_id,))

            existing = cursor.fetchone()
            if existing:
                # 이미 존재하면 기존 대화 정보 반환
                return dict(existing)

            # 존재하지 않으면 새로 생성
            cursor.execute("""
                INSERT INTO conversations (id, title, user_id, project_id)
                VALUES (?, ?, ?, ?)
            """, (conversation_id, title, user_id, project_id))

            return {
                "id": conversation_id,
                "title": title,
                "project_id": project_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

    def get_conversation(self, conversation_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM conversations
                WHERE id = ? AND is_deleted = 0
            """, (conversation_id,))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_all_conversations(self, user_id: Optional[str] = None, project_id: Optional[str] = None) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 조건에 따른 쿼리 구성
            conditions = ["is_deleted = 0"]
            params = []

            if user_id:
                conditions.append("user_id = ?")
                params.append(user_id)

            if project_id:
                conditions.append("project_id = ?")
                params.append(project_id)

            where_clause = " AND ".join(conditions)

            cursor.execute(f"""
                SELECT * FROM conversations
                WHERE {where_clause}
                ORDER BY updated_at DESC
            """, params)

            return [dict(row) for row in cursor.fetchall()]

    def get_conversations_by_project(self, project_id: str, user_id: Optional[str] = None) -> List[Dict]:
        """특정 프로젝트의 대화 목록 조회"""
        return self.get_all_conversations(user_id=user_id, project_id=project_id)

    def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE conversations
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (title, conversation_id))

            return cursor.rowcount > 0

    def delete_conversation(self, conversation_id: str, soft_delete: bool = True) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if soft_delete:
                cursor.execute("""
                    UPDATE conversations
                    SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (conversation_id,))
            else:
                cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

            return cursor.rowcount > 0

    # === Messages ===
    def create_message(self, conversation_id: str, message_data: Dict) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            print(f"💾 DB 메시지 저장 시작: {conversation_id}")
            
            # full_data_dict 디버깅
            full_data_dict = message_data.get("full_data_dict")
            if full_data_dict:
                print(f"📊 full_data_dict 저장: {len(full_data_dict)} 개 키")
            else:
                print(f"⚠️ full_data_dict가 비어있거나 None")

            # 메시지 기본 정보 저장
            try:
                cursor.execute("""
                    INSERT INTO messages (
                        conversation_id, type, content, timestamp,
                        is_streaming, was_aborted, team_id,
                        charts, search_results, sources,
                        full_data_dict, section_data_dicts, message_state, section_headers, status_history
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    conversation_id,
                    message_data.get("type"),
                    message_data.get("content", ""),
                    message_data.get("timestamp", datetime.now().isoformat()),
                    message_data.get("is_streaming", False),
                    message_data.get("was_aborted", False),
                    message_data.get("team_id"),
                    json.dumps(message_data.get("charts")) if message_data.get("charts") else None,
                    json.dumps(message_data.get("search_results")) if message_data.get("search_results") else None,
                    json.dumps(message_data.get("sources")) if message_data.get("sources") else None,
                    json.dumps(message_data.get("full_data_dict")) if message_data.get("full_data_dict") else None,
                    json.dumps(message_data.get("section_data_dicts")) if message_data.get("section_data_dicts") else None,
                    json.dumps(message_data.get("message_state")) if message_data.get("message_state") else None,
                    json.dumps(message_data.get("section_headers")) if message_data.get("section_headers") else None,
                    json.dumps(message_data.get("status_history")) if message_data.get("status_history") else None
                ))
                print(f"✅ 메시지 기본 정보 저장 완료")
            except Exception as e:
                print(f"❌ 메시지 기본 정보 저장 실패: {e}")
                raise

            message_id = cursor.lastrowid

            # 메시지 상태 저장 (기존 테이블도 유지)
            if "status" in message_data:
                self._save_message_state(conn, message_id, message_data)

            return message_id

    def get_messages(self, conversation_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 메시지 기본 정보 조회
            cursor.execute("""
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """, (conversation_id,))

            messages = []
            for row in cursor.fetchall():
                message = dict(row)
                message_id = message["id"]

                # JSON 필드들 파싱
                try:
                    if message.get("charts"):
                        message["charts"] = json.loads(message["charts"])
                    else:
                        message["charts"] = []

                    if message.get("search_results"):
                        message["search_results"] = json.loads(message["search_results"])
                    else:
                        message["search_results"] = []

                    if message.get("sources"):
                        message["sources"] = json.loads(message["sources"])
                    else:
                        message["sources"] = None

                    if message.get("full_data_dict"):
                        parsed_data = json.loads(message["full_data_dict"])
                        message["full_data_dict"] = parsed_data
                        print(f"📊 메시지 {message_id}: full_data_dict 로드 - {len(parsed_data)} 개 키")
                    else:
                        message["full_data_dict"] = {}
                        print(f"⚠️ 메시지 {message_id}: full_data_dict가 비어있음")

                    if message.get("section_data_dicts"):
                        message["section_data_dicts"] = json.loads(message["section_data_dicts"])
                    else:
                        message["section_data_dicts"] = {}

                    if message.get("message_state"):
                        message["message_state"] = json.loads(message["message_state"])
                    else:
                        message["message_state"] = None

                    if message.get("section_headers"):
                        message["section_headers"] = json.loads(message["section_headers"])
                    else:
                        message["section_headers"] = []

                    if message.get("status_history"):
                        message["status_history"] = json.loads(message["status_history"])
                    else:
                        message["status_history"] = []

                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON 파싱 오류 (메시지 {message_id}): {e}")
                    # 파싱 실패 시 기본값 설정
                    message["charts"] = []
                    message["search_results"] = []
                    message["sources"] = None
                    message["full_data_dict"] = {}
                    message["section_data_dicts"] = {}
                    message["message_state"] = None
                    message["section_headers"] = []

                # 메시지 상태 조회 (기존 테이블도 유지)
                cursor.execute("SELECT * FROM message_states WHERE message_id = ?", (message_id,))
                state_row = cursor.fetchone()
                if state_row:
                    message["state"] = dict(state_row)

                # 상태 히스토리 조회 (JSON 필드가 비어있으면 기존 테이블에서)
                if not message["status_history"]:
                    cursor.execute("""
                        SELECT * FROM status_history
                        WHERE message_id = ?
                        ORDER BY timestamp ASC
                    """, (message_id,))
                    status_history_from_table = [dict(row) for row in cursor.fetchall()]
                    if status_history_from_table:
                        message["status_history"] = status_history_from_table

                # 기존 별도 테이블 데이터가 있으면 병합 (하위 호환성)
                # 검색 결과 조회 (JSON 필드가 비어있으면 기존 테이블에서)
                if not message["search_results"]:
                    cursor.execute("SELECT * FROM search_results WHERE message_id = ?", (message_id,))
                    search_results = []
                    for sr_row in cursor.fetchall():
                        sr = dict(sr_row)
                        sr["results"] = json.loads(sr["results"])
                        search_results.append(sr)
                    if search_results:
                        message["search_results"] = search_results

                # 출처 조회 (JSON 필드가 비어있으면 기존 테이블에서)
                if not message["sources"]:
                    cursor.execute("""
                        SELECT * FROM sources
                        WHERE message_id = ?
                        ORDER BY position ASC
                    """, (message_id,))
                    sources = []
                    for source_row in cursor.fetchall():
                        source = dict(source_row)
                        if source["metadata"]:
                            source["metadata"] = json.loads(source["metadata"])
                        sources.append(source)
                    if sources:
                        message["sources"] = sources

                messages.append(message)

            return messages

    def update_message(self, message_id: int, updates: Dict) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 메시지 기본 정보 업데이트
            if "content" in updates or "was_aborted" in updates:
                cursor.execute("""
                    UPDATE messages
                    SET content = COALESCE(?, content),
                        was_aborted = COALESCE(?, was_aborted),
                        is_streaming = ?
                    WHERE id = ?
                """, (
                    updates.get("content"),
                    updates.get("was_aborted"),
                    updates.get("is_streaming", False),
                    message_id
                ))

            # 메시지 상태 업데이트
            if "status" in updates:
                self._update_message_state(conn, message_id, updates)

            return cursor.rowcount > 0

    # === Streaming Sessions ===
    def save_streaming_session(self, conversation_id: str, session_data: Dict) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO streaming_sessions (
                    conversation_id, current_message, current_charts, status
                ) VALUES (?, ?, ?, ?)
            """, (
                conversation_id,
                session_data.get("current_message", ""),
                json.dumps(session_data.get("current_charts", [])),
                session_data.get("status", "streaming")
            ))

            return cursor.rowcount > 0

    def get_streaming_session(self, conversation_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM streaming_sessions
                WHERE conversation_id = ?
            """, (conversation_id,))

            row = cursor.fetchone()
            if row:
                session = dict(row)
                session["current_charts"] = json.loads(session["current_charts"])
                return session
            return None

    def delete_streaming_session(self, conversation_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM streaming_sessions WHERE conversation_id = ?", (conversation_id,))
            return cursor.rowcount > 0

    # === Helper Methods ===
    def _save_message_state(self, conn, message_id: int, message_data: Dict):
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO message_states (
                message_id, status, start_time, end_time, duration_ms
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            message_id,
            message_data.get("status", "completed"),
            message_data.get("start_time"),
            message_data.get("end_time"),
            message_data.get("duration_ms")
        ))

    def _update_message_state(self, conn, message_id: int, updates: Dict):
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE message_states
            SET status = ?, end_time = ?, duration_ms = ?
            WHERE message_id = ?
        """, (
            updates.get("status"),
            updates.get("end_time"),
            updates.get("duration_ms"),
            message_id
        ))

    def _save_charts(self, conn, message_id: int, charts: List):
        cursor = conn.cursor()
        for idx, chart in enumerate(charts):
            cursor.execute("""
                INSERT INTO charts (message_id, chart_type, chart_data, position)
                VALUES (?, ?, ?, ?)
            """, (
                message_id,
                chart.get("type", "unknown"),
                json.dumps(chart),
                idx
            ))

    def _save_search_results(self, conn, message_id: int, search_results: List):
        cursor = conn.cursor()
        for result in search_results:
            cursor.execute("""
                INSERT INTO search_results (message_id, query, results, is_visible)
                VALUES (?, ?, ?, ?)
            """, (
                message_id,
                result.get("query", ""),
                json.dumps(result.get("results", [])),
                result.get("is_visible", True)
            ))

    def _save_sources(self, conn, message_id: int, sources: Any):
        cursor = conn.cursor()

        # sources는 dict 또는 list일 수 있음
        if isinstance(sources, dict):
            # dict 형태의 sources를 list로 변환
            source_list = []
            for key, value in sources.items():
                if isinstance(value, dict):
                    source_list.append({
                        "type": key,
                        "title": value.get("title", key),
                        "content": value.get("content", ""),
                        "metadata": value
                    })
        else:
            source_list = sources if isinstance(sources, list) else []

        for idx, source in enumerate(source_list):
            cursor.execute("""
                INSERT INTO sources (
                    message_id, source_type, title, content,
                    metadata, relevance_score, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                message_id,
                source.get("type", "unknown"),
                source.get("title"),
                source.get("content"),
                json.dumps(source.get("metadata")) if source.get("metadata") else None,
                source.get("relevance_score"),
                idx
            ))

    def add_status_history(self, message_id: int, status_message: str,
                          step_number: Optional[int] = None,
                          total_steps: Optional[int] = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO status_history (
                    message_id, status_message, step_number, total_steps
                ) VALUES (?, ?, ?, ?)
            """, (message_id, status_message, step_number, total_steps))

            return cursor.lastrowid
