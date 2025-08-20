-- SQLite 데이터베이스 스키마
-- 채팅 시스템을 위한 테이블 구조

-- 1. 대화 테이블
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT, -- 추후 사용자 관리 시 사용
    is_deleted BOOLEAN DEFAULT 0
);

-- 2. 메시지 테이블
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('user', 'assistant')),
    content TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- assistant 메시지 전용 필드
    is_streaming BOOLEAN DEFAULT 0,
    was_aborted BOOLEAN DEFAULT 0,
    team_id TEXT,
    
    -- 관계
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- 3. 메시지 상태 테이블
CREATE TABLE IF NOT EXISTS message_states (
    message_id INTEGER PRIMARY KEY,
    status TEXT CHECK(status IN ('streaming', 'completed', 'aborted')),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_ms INTEGER,
    
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

-- 4. 상태 히스토리 테이블 (상태 스트리밍 박스)
CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    status_message TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    step_number INTEGER,
    total_steps INTEGER,
    
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

-- 5. 차트 데이터 테이블
CREATE TABLE IF NOT EXISTS charts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    chart_type TEXT NOT NULL,
    chart_data JSON NOT NULL, -- JSON 형태로 차트 설정 저장
    position INTEGER NOT NULL, -- 메시지 내 차트 순서
    
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

-- 6. 검색 결과 테이블
CREATE TABLE IF NOT EXISTS search_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    results JSON NOT NULL, -- JSON 배열로 결과 저장
    is_visible BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

-- 7. 출처 데이터 테이블
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    title TEXT,
    content TEXT,
    metadata JSON, -- 추가 메타데이터
    relevance_score REAL,
    position INTEGER, -- 출처 순서
    
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

-- 8. 스트리밍 세션 테이블 (임시 데이터)
CREATE TABLE IF NOT EXISTS streaming_sessions (
    conversation_id TEXT PRIMARY KEY,
    current_message TEXT,
    current_charts JSON,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_status_history_message ON status_history(message_id);
CREATE INDEX IF NOT EXISTS idx_charts_message ON charts(message_id);
CREATE INDEX IF NOT EXISTS idx_search_results_message ON search_results(message_id);
CREATE INDEX IF NOT EXISTS idx_sources_message ON sources(message_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at);

-- 트리거: conversations 업데이트 시 updated_at 자동 갱신
DROP TRIGGER IF EXISTS update_conversation_timestamp;
CREATE TRIGGER update_conversation_timestamp 
AFTER UPDATE ON conversations
BEGIN
    UPDATE conversations 
    SET updated_at = CURRENT_TIMESTAMP 
    WHERE id = NEW.id;
END;

-- 트리거: 메시지 추가/수정 시 대화 updated_at 갱신
DROP TRIGGER IF EXISTS update_conversation_on_message;
CREATE TRIGGER update_conversation_on_message 
AFTER INSERT ON messages
BEGIN
    UPDATE conversations 
    SET updated_at = CURRENT_TIMESTAMP 
    WHERE id = NEW.conversation_id;
END;