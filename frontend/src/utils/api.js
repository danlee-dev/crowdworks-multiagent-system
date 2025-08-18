// API 유틸리티 함수들

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

// API 호출 기본 함수
async function apiCall(endpoint, options = {}) {
  const fullUrl = `${API_BASE_URL}${endpoint}`;
  console.log(`🌐 API_BASE_URL: ${API_BASE_URL}`);
  console.log(`🔗 전체 URL: ${fullUrl}`);
  
  try {
    const response = await fetch(fullUrl, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });
    
    console.log(`📡 응답 상태: ${response.status} ${response.statusText}`);

    if (!response.ok) {
      const error = new Error(`API 호출 실패: ${response.status} ${response.statusText}`);
      error.status = response.status;
      error.statusText = response.statusText;
      throw error;
    }

    return await response.json();
  } catch (error) {
    // 404 오류는 정상적인 상황이므로 간단하게 로그
    if (error.status === 404) {
      console.log(`ℹ️ 리소스 없음 [${endpoint}]: ${error.message}`);
    } else {
      // 404가 아닌 실제 오류들만 상세 로그
      console.error(`💥 네트워크 오류 상세 정보:`);
      console.error(`  🔗 URL: ${fullUrl}`);
      console.error(`  🚨 오류 타입: ${error.name}`);
      console.error(`  📝 오류 메시지: ${error.message}`);
      console.error(`  🔍 전체 오류 객체:`, error);
      console.error(`❌ API 호출 오류 [${endpoint}]:`, error);
    }
    throw error;
  }
}

// === 프로젝트 관련 API ===
export const projectAPI = {
  // 새 프로젝트 생성
  async create(title, description = null, userId = null, projectId = null) {
    const payload = { title, description, user_id: userId };
    if (projectId) {
      payload.id = projectId;
    }
    
    return await apiCall('/api/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // 모든 프로젝트 조회
  async getAll(userId = null) {
    console.log('🚀 projectAPI.getAll() 호출됨');
    const params = userId ? `?user_id=${userId}` : '';
    console.log(`📡 API 호출: /api/projects${params}`);
    const result = await apiCall(`/api/projects${params}`);
    console.log('✅ projectAPI.getAll() 결과:', result);
    return result;
  },

  // 특정 프로젝트 조회
  async get(projectId) {
    try {
      const result = await apiCall(`/api/projects/${projectId}`);
      return result;
    } catch (error) {
      if (error.status === 404 || error.message.includes('404') || error.message.includes('Not Found')) {
        return null;
      }
      console.error(`❌ 예상치 못한 프로젝트 조회 오류: ${projectId}`, error);
      throw error;
    }
  },

  // 프로젝트 제목/설명 수정
  async update(projectId, title, description = null) {
    const payload = {};
    if (title !== null) payload.title = title;
    if (description !== null) payload.description = description;
    
    return await apiCall(`/api/projects/${projectId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },

  // 프로젝트 삭제
  async delete(projectId, hardDelete = false) {
    const params = hardDelete ? '?hard_delete=true' : '';
    return await apiCall(`/api/projects/${projectId}${params}`, {
      method: 'DELETE',
    });
  },

  // 프로젝트의 대화 목록 조회
  async getConversations(projectId, userId = null) {
    const params = userId ? `?user_id=${userId}` : '';
    return await apiCall(`/api/projects/${projectId}/conversations${params}`);
  },
};

// === 대화 관련 API ===
export const conversationAPI = {
  // 새 대화 생성
  async create(title, userId = null, conversationId = null, projectId = null) {
    const payload = { title, user_id: userId };
    if (conversationId) {
      payload.id = conversationId;
    }
    if (projectId) {
      payload.project_id = projectId;
    }
    
    return await apiCall('/api/conversations', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // 모든 대화 조회
  async getAll(userId = null, projectId = null) {
    const params = new URLSearchParams();
    if (userId) params.append('user_id', userId);
    if (projectId) params.append('project_id', projectId);
    
    const queryString = params.toString();
    return await apiCall(`/api/conversations${queryString ? '?' + queryString : ''}`);
  },

  // 특정 대화 조회 (메시지 포함)
  async get(conversationId) {
    try {
      const result = await apiCall(`/api/conversations/${conversationId}`);
      return result;
    } catch (error) {
      if (error.status === 404 || error.message.includes('404') || error.message.includes('Not Found')) {
        // 대화가 존재하지 않는 경우 null 반환
        return null;
      }
      console.error(`❌ 예상치 못한 대화 조회 오류: ${conversationId}`, error);
      throw error; // 다른 오류는 재던지기
    }
  },

  // 대화 제목 수정
  async updateTitle(conversationId, title) {
    return await apiCall(`/api/conversations/${conversationId}/title`, {
      method: 'PUT',
      body: JSON.stringify({ title }),
    });
  },

  // 대화 삭제
  async delete(conversationId, hardDelete = false) {
    const params = hardDelete ? '?hard_delete=true' : '';
    return await apiCall(`/api/conversations/${conversationId}${params}`, {
      method: 'DELETE',
    });
  },

  // LLM으로 제목 자동 생성
  async generateTitle(query) {
    return await apiCall('/chat/generate-title', {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
  },
};

// === 메시지 관련 API ===
export const messageAPI = {
  // 새 메시지 생성
  async create(messageData) {
    return await apiCall('/api/messages', {
      method: 'POST',
      body: JSON.stringify(messageData),
    });
  },

  // 대화의 모든 메시지 조회
  async getByConversation(conversationId) {
    return await apiCall(`/api/conversations/${conversationId}/messages`);
  },

  // 메시지 업데이트
  async update(messageId, updates) {
    return await apiCall(`/api/messages/${messageId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  },

  // 메시지 상태 히스토리 추가
  async addStatusHistory(messageId, statusMessage, stepNumber = null, totalSteps = null) {
    return await apiCall(`/api/messages/${messageId}/status`, {
      method: 'POST',
      body: JSON.stringify({
        status_message: statusMessage,
        step_number: stepNumber,
        total_steps: totalSteps,
      }),
    });
  },
};

// === 스트리밍 세션 관련 API ===
export const streamingAPI = {
  // 스트리밍 세션 저장
  async save(conversationId, sessionData) {
    return await apiCall(`/api/streaming-sessions/${conversationId}`, {
      method: 'POST',
      body: JSON.stringify(sessionData),
    });
  },

  // 스트리밍 세션 조회
  async get(conversationId) {
    try {
      return await apiCall(`/api/streaming-sessions/${conversationId}`);
    } catch (error) {
      if (error.message.includes('404')) {
        return null; // 세션이 없는 경우
      }
      throw error;
    }
  },

  // 스트리밍 세션 삭제
  async delete(conversationId) {
    try {
      return await apiCall(`/api/streaming-sessions/${conversationId}`, {
        method: 'DELETE',
      });
    } catch (error) {
      if (error.message.includes('404')) {
        // 스트리밍 세션이 없는 경우 정상 처리 (이미 삭제됨)
        console.log('스트리밍 세션이 존재하지 않음 (이미 삭제됨):', conversationId);
        return { message: '스트리밍 세션이 이미 삭제됨' };
      }
      throw error; // 다른 오류는 재던지기
    }
  },
};

// === localStorage 백업 (오프라인/에러 처리) ===
export const localStorageBackup = {
  // localStorage에 임시 저장
  save(key, data) {
    try {
      localStorage.setItem(key, JSON.stringify(data));
    } catch (error) {
      console.warn('localStorage 저장 실패:', error);
    }
  },

  // localStorage에서 불러오기
  load(key) {
    try {
      const data = localStorage.getItem(key);
      return data ? JSON.parse(data) : null;
    } catch (error) {
      console.warn('localStorage 로드 실패:', error);
      return null;
    }
  },

  // localStorage에서 제거
  remove(key) {
    try {
      localStorage.removeItem(key);
    } catch (error) {
      console.warn('localStorage 제거 실패:', error);
    }
  },

  // 모든 백업 데이터 제거
  clearAll() {
    try {
      const backupKeys = [
        'backup_conversations',
        'backup_current_conversation',
        'backup_streaming_session',
      ];
      backupKeys.forEach(key => localStorage.removeItem(key));
    } catch (error) {
      console.warn('localStorage 전체 제거 실패:', error);
    }
  },
};

// === 하이브리드 저장 (API + localStorage 백업) ===

// 중복 저장 방지를 위한 캐시
const saveCache = new Map();
const SAVE_DEBOUNCE_TIME = 1000; // 1초 내 중복 저장 방지
export const hybridStorage = {
  // 대화 저장 (API 우선, 실패 시 localStorage)
  async saveConversation(conversation) {
    try {
      if (!conversation.id || !conversation.title) {
        console.warn('대화 ID 또는 제목이 없음:', conversation);
        return;
      }
      
      // 중복 저장 방지 체크
      const now = Date.now();
      const cacheKey = `${conversation.id}_${conversation.messages?.length || 0}_${conversation.title}`;
      const lastSaveTime = saveCache.get(cacheKey);
      
      if (lastSaveTime && (now - lastSaveTime) < SAVE_DEBOUNCE_TIME) {
        console.log(`⏭️ 중복 저장 방지: ${conversation.id} (마지막 저장 ${now - lastSaveTime}ms 전)`);
        return;
      }
      
      saveCache.set(cacheKey, now);
      console.log(`💾 대화 저장 시도: ${conversation.id}, 제목: "${conversation.title}", 메시지 ${conversation.messages?.length || 0}개`);

      // 1. 대화가 DB에 존재하는지 확인 (404 에러를 정상 처리)
      let existingConversation = null;
      let conversationExists = false;
      try {
        existingConversation = await conversationAPI.get(conversation.id);
        conversationExists = existingConversation !== null;
      } catch (error) {
        // 404는 대화가 존재하지 않음을 의미하므로 정상 처리
        if (error.status === 404) {
          console.log(`📂 대화 없음 확인: ${conversation.id} (정상)`);
          conversationExists = false;
        } else {
          // 다른 에러는 재발생
          throw error;
        }
      }

      // 2. 대화가 없으면 생성, 있으면 제목 업데이트
      if (!conversationExists) {
        console.log(`🆕 새 대화 생성: ${conversation.id}, 제목: "${conversation.title}"`);
        const created = await conversationAPI.create(conversation.title, null, conversation.id, conversation.project_id);
        console.log(`✅ 대화 생성 완료:`, created);
        // 🔑 핵심: 대화 생성 후 잠시 대기 (DB 커밋 완료 확인)
        await new Promise(resolve => setTimeout(resolve, 100));
      } else {
        console.log(`📝 기존 대화 제목 업데이트: ${conversation.id}`);
        await conversationAPI.updateTitle(conversation.id, conversation.title);
      }
      
      // 3. 메시지들 저장 (대화 생성 완료 후)
      if (conversation.messages && Array.isArray(conversation.messages)) {
        for (const message of conversation.messages) {
          if (!message.saved_to_db) {
            console.log(`💬 메시지 저장 시작: ${message.id} (${message.type}), 내용: "${message.content?.slice(0, 30)}..."`, {
              hasStatusHistory: !!message.statusHistory,
              statusHistoryLength: message.statusHistory?.length || 0
            });
            
            const messageData = {
              conversation_id: conversation.id,
              type: message.type || "user", // 기본값 설정
              content: message.content || "", // 기본값 설정
              timestamp: message.timestamp || new Date().toISOString(),
              team_id: message.team_id || null,
              charts: message.charts || null,
              search_results: message.searchResults || null, // 백엔드와 맞춤
              sources: message.sources || null,
              // 스트리밍 관련 필드 추가
              is_streaming: message.isStreaming || false,
              was_aborted: message.wasAborted || false,
              // 추가 데이터 저장
              full_data_dict: message.fullDataDict || null,
              section_data_dicts: message.sectionDataDicts || null,
              message_state: message.messageState || null,
              section_headers: message.sectionHeaders || null,
              // 상태 히스토리 정보 추가
              status_history: message.statusHistory || null
            };
            
            try {
              console.log(`📤 백엔드로 전송할 메시지 데이터:`, {
                id: message.id,
                statusHistory: messageData.status_history,
                statusHistoryLength: messageData.status_history?.length || 0
              });
              await messageAPI.create(messageData);
              message.saved_to_db = true; // 성공적으로 저장된 후에만 플래그 설정
              console.log(`✅ 메시지 저장 성공: ${message.id}`);
            } catch (messageError) {
              console.error(`❌ 메시지 저장 실패: ${message.id}`, messageError);
              
              // 422 오류인 경우 필드 검증
              if (messageError.message?.includes('422')) {
                console.log('🔍 422 오류 상세:', {
                  messageData,
                  error: messageError.message
                });
              }
              
              // 개별 메시지 저장 실패해도 계속 진행
              continue;
            }
          }
        }
      }
    } catch (error) {
      console.warn('API 저장 실패, localStorage 백업:', error);
      localStorageBackup.save('backup_conversations', [conversation]);
    }
  },

  // 스트리밍 세션 저장
  async saveStreamingSession(conversationId, sessionData) {
    try {
      await streamingAPI.save(conversationId, sessionData);
    } catch (error) {
      console.warn('스트리밍 세션 API 저장 실패, localStorage 백업:', error);
      localStorageBackup.save('backup_streaming_session', {
        conversationId,
        ...sessionData,
      });
    }
  },

  // 대화 로드 (API 우선, 실패 시 localStorage)
  async loadConversations() {
    try {
      const conversations = await conversationAPI.getAll();
      
      // API 응답을 프론트엔드 형식으로 변환
      const formattedConversations = conversations.map(conv => ({
        id: conv.id,
        title: conv.title,
        project_id: conv.project_id, // 프로젝트 ID 포함
        lastUpdated: conv.updated_at || conv.created_at, // 🔑 핵심: API 필드를 프론트엔드 형식으로 변환
        created_at: conv.created_at,
        updated_at: conv.updated_at,
        messages: conv.messages || [],
        isStreaming: false
      }));
      
      // 🔑 핵심: 최신순 정렬 적용
      return formattedConversations.sort((a, b) => {
        const dateA = new Date(a.lastUpdated || 0);
        const dateB = new Date(b.lastUpdated || 0);
        return dateB.getTime() - dateA.getTime(); // 최신순 정렬
      });
    } catch (error) {
      console.warn('API 로드 실패, localStorage에서 복원:', error);
      return localStorageBackup.load('backup_conversations') || [];
    }
  },

  // 특정 대화 로드
  async loadConversation(conversationId) {
    try {
      const conversation = await conversationAPI.get(conversationId);
      if (conversation) {
        // API 응답을 프론트엔드 형식으로 변환
        const formattedConversation = {
          id: conversation.id,
          title: conversation.title,
          project_id: conversation.project_id, // 프로젝트 ID 포함
          lastUpdated: conversation.updated_at || conversation.created_at,
          created_at: conversation.created_at,
          updated_at: conversation.updated_at,
          isStreaming: false,
          messages: []
        };
        
        if (conversation.messages && Array.isArray(conversation.messages)) {
          // 메시지 중복 제거 (ID와 타입, 타임스탬프 기준)
          const uniqueMessages = [];
          const seenKeys = new Set();
          
          conversation.messages.forEach(msg => {
            const key = `${msg.id}-${msg.type}-${msg.timestamp}`;
            if (!seenKeys.has(key)) {
              seenKeys.add(key);
              uniqueMessages.push(msg);
            } else {
              console.warn("🔍 중복 메시지 발견 및 제거:", {
                id: msg.id,
                type: msg.type,
                timestamp: msg.timestamp
              });
            }
          });
          
          formattedConversation.messages = uniqueMessages.map(msg => {
            // 디버깅: assistant 메시지의 상태 정보 확인
            if (msg.type === 'assistant') {
              console.log(`🔍 Assistant 메시지 상태 정보:`, {
                id: msg.id,
                has_message_state: !!msg.message_state,
                has_status_history: !!msg.status_history,
                status_history_length: msg.status_history?.length || 0,
                message_state: msg.message_state,
                status_history: msg.status_history
              });
            }
            
            return {
              id: msg.id,
              type: msg.type,
              content: msg.content,
              timestamp: msg.timestamp,
              team_id: msg.team_id,
              charts: msg.charts || [],
              searchResults: msg.search_results || [], // API에서는 search_results
              sources: msg.sources,
              isStreaming: false,
              saved_to_db: true, // DB에서 가져온 것이므로 true
              // 추가 데이터 복원
              fullDataDict: msg.full_data_dict || {},
              sectionDataDicts: msg.section_data_dicts || {},
              messageState: msg.message_state || null,
              sectionHeaders: msg.section_headers || [],
              // 상태 히스토리 복원
              statusHistory: msg.status_history || []
            };
          });
        }
        
        console.log(`📥 대화 로드 완료: ${conversationId}, 메시지 ${formattedConversation.messages.length}개`);
        if (formattedConversation.messages.length === 0) {
          console.log(`⚠️ 빈 대화 감지: ${conversationId} - 메시지가 전혀 없음`);
        }
        return formattedConversation;
      }
      return null;
    } catch (error) {
      console.warn('대화 로드 실패:', conversationId, error.message);
      return null;
    }
  },

  // 대화 삭제 (API 우선, 실패 시 localStorage에서만 제거)
  async deleteConversation(conversationId) {
    try {
      console.log(`🗑️ DB에서 대화 삭제 시도: ${conversationId}`);
      await conversationAPI.delete(conversationId);
      console.log(`✅ DB에서 대화 삭제 성공: ${conversationId}`);
      
      // 스트리밍 세션도 함께 삭제
      try {
        await streamingAPI.delete(conversationId);
        console.log(`🧹 스트리밍 세션 삭제 완료: ${conversationId}`);
      } catch (streamError) {
        console.log(`ℹ️ 스트리밍 세션 삭제 시도 (없을 수 있음): ${conversationId}`);
      }
      
    } catch (error) {
      console.warn(`⚠️ API 삭제 실패, localStorage 백업에서만 제거: ${conversationId}`, error);
      // API 실패 시에도 localStorage에서는 제거
      const backupConversations = localStorageBackup.load('backup_conversations') || [];
      const updatedBackup = backupConversations.filter(conv => conv.id !== conversationId);
      localStorageBackup.save('backup_conversations', updatedBackup);
      throw error; // 오류를 다시 던져서 호출자가 처리할 수 있도록
    }
  },
};