import { useState, useCallback, useEffect } from 'react';
import { conversationAPI, hybridStorage, localStorageBackup } from '../utils/api';

export const useConversation = () => {
  const [conversations, setConversations] = useState([]);
  const [currentConversation, setCurrentConversation] = useState([]);
  const [conversationId, setConversationId] = useState("");
  const [availableTeams, setAvailableTeams] = useState([]);
  const [selectedTeam, setSelectedTeam] = useState(null);

  const loadConversations = useCallback(async () => {
    try {
      const loadedConversations = await hybridStorage.loadConversations();
      if (loadedConversations && Array.isArray(loadedConversations)) {
        setConversations(loadedConversations);
        localStorageBackup.save("chatConversations", loadedConversations);
      }
    } catch (error) {
      console.error("대화 목록 로딩 실패:", error);
      const fallback = localStorageBackup.load("chatConversations");
      if (fallback) {
        setConversations(fallback);
      }
    }
  }, []);

  const saveConversations = useCallback(async (newConversations, skipDbSave = false) => {
    try {
      setConversations(newConversations);
      localStorageBackup.save("chatConversations", newConversations);
      
      // DB 저장은 필요한 경우에만 (중복 방지)
      if (!skipDbSave) {
        const currentConv = newConversations.find((c) => c.id === conversationId);
        if (currentConv) {
          console.log("💾 대화 저장 (제목 포함):", currentConv.title);
          await hybridStorage.saveConversation(currentConv);
        }
      }
    } catch (error) {
      console.error("대화 저장 실패:", error);
    }
  }, [conversationId]);

  const startNewChat = useCallback((projectId = null) => {
    const newId = `chat_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
    setConversationId(newId);
    setCurrentConversation([]);
    setSelectedTeam(null);
    
    const newChat = {
      id: newId,
      title: "", // 빈 제목으로 시작, 첫 쿼리 시 자동 생성
      messages: [],
      lastUpdated: new Date().toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      isStreaming: false,
      project_id: projectId, // 프로젝트 ID 설정
    };
    
    const updatedConversations = [newChat, ...conversations];
    setConversations(updatedConversations);
    localStorageBackup.save("chatConversations", updatedConversations);
    
    console.log('🆕 새 대화 생성:', { id: newId, project_id: projectId });
    
    return newId;
  }, [conversations]);

  const loadConversation = useCallback(async (conv) => {
    try {
      console.log(`📂 대화 로드 시도:`, conv.id);
      
      const loadedConversation = await hybridStorage.loadConversation(conv.id);
      
      if (loadedConversation && loadedConversation.messages) {
        console.log(`✅ DB에서 대화 로드 성공: ${conv.id}, 메시지 ${loadedConversation.messages.length}개`);
        
        // 메시지 중복 제거
        const uniqueMessages = [];
        const seenIds = new Set();
        
        loadedConversation.messages.forEach(msg => {
          if (!seenIds.has(msg.id)) {
            seenIds.add(msg.id);
            uniqueMessages.push(msg);
          } else {
            console.warn("🔍 대화 로드 시 중복 메시지 제거:", msg.id);
          }
        });
        
        if (uniqueMessages.length !== loadedConversation.messages.length) {
          console.log(`🧹 중복 메시지 정리: ${loadedConversation.messages.length} → ${uniqueMessages.length}`);
        }
        
        setConversationId(loadedConversation.id);
        setCurrentConversation(uniqueMessages);
        
        const lastAssistantMessage = [...loadedConversation.messages]
          .reverse()
          .find(msg => msg.type === 'assistant');
        
        if (lastAssistantMessage?.team_id) {
          const team = availableTeams.find(t => t.id === lastAssistantMessage.team_id);
          if (team) {
            setSelectedTeam(team);
          }
        }
      } else {
        console.log(`⚠️ DB에 대화 없음, 로컬 데이터 사용: ${conv.id}`);
        
        // 로컬 데이터도 중복 제거
        const messages = conv.messages || [];
        const uniqueMessages = [];
        const seenIds = new Set();
        
        messages.forEach(msg => {
          if (!seenIds.has(msg.id)) {
            seenIds.add(msg.id);
            uniqueMessages.push(msg);
          } else {
            console.warn("🔍 로컬 데이터 로드 시 중복 메시지 제거:", msg.id);
          }
        });
        
        if (uniqueMessages.length !== messages.length) {
          console.log(`🧹 로컬 중복 메시지 정리: ${messages.length} → ${uniqueMessages.length}`);
        }
        
        setConversationId(conv.id);
        setCurrentConversation(uniqueMessages);
      }
    } catch (error) {
      console.error("대화 로드 실패:", error);
      
      // 오류 발생시에도 중복 제거
      const messages = conv.messages || [];
      const uniqueMessages = [];
      const seenIds = new Set();
      
      messages.forEach(msg => {
        if (!seenIds.has(msg.id)) {
          seenIds.add(msg.id);
          uniqueMessages.push(msg);
        } else {
          console.warn("🔍 오류 처리 시 중복 메시지 제거:", msg.id);
        }
      });
      
      if (uniqueMessages.length !== messages.length) {
        console.log(`🧹 오류 처리 시 중복 메시지 정리: ${messages.length} → ${uniqueMessages.length}`);
      }
      
      setConversationId(conv.id);
      setCurrentConversation(uniqueMessages);
    }
  }, [availableTeams]);

  const deleteConversation = useCallback(async (convId) => {
    try {
      await hybridStorage.deleteConversation(convId);
      
      const updatedConversations = conversations.filter((c) => c.id !== convId);
      setConversations(updatedConversations);
      localStorageBackup.save("chatConversations", updatedConversations);
      
      if (convId === conversationId) {
        // 다른 대화가 있으면 가장 최근 대화로 이동, 없으면 새 채팅 시작
        if (updatedConversations.length > 0) {
          const mostRecentConversation = updatedConversations.sort((a, b) => 
            new Date(b.lastUpdated || b.updated_at) - new Date(a.lastUpdated || a.updated_at)
          )[0];
          loadConversation(mostRecentConversation);
        } else {
          startNewChat();
        }
      }
    } catch (error) {
      console.error("대화 삭제 실패:", error);
    }
  }, [conversations, conversationId, startNewChat, loadConversation]);

  const loadAvailableTeams = useCallback(async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://49.50.128.6:8000"}/teams`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      const teams = data.teams || data; // teams 프로퍼티가 있으면 사용, 없으면 data 자체 사용
      
      if (teams && Array.isArray(teams) && teams.length > 0) {
        // AI 자동 선택 옵션 추가
        const teamsWithAuto = [
          {
            id: "AI_AUTO",
            name: "AI 자동 선택",
            description: "AI가 질문을 분석하여 가장 적합한 전문가를 자동으로 선택합니다"
          },
          ...teams
        ];
        
        setAvailableTeams(teamsWithAuto);
        
        // AI 자동 선택을 기본값으로 설정
        const autoSelectTeam = teamsWithAuto.find(team => team.id === "AI_AUTO");
        if (autoSelectTeam) {
          setSelectedTeam(autoSelectTeam);
        } else {
          setSelectedTeam(teamsWithAuto[0]);
        }
      }
    } catch (error) {
      console.error("팀 목록 로딩 실패:", error);
      
      const fallbackTeams = [
        {
          id: "AI_AUTO",
          name: "AI 자동 선택",
          description: "AI가 질문을 분석하여 가장 적합한 전문가를 자동으로 선택합니다"
        },
        {
          id: "general",
          name: "일반 상담팀",
          description: "일반적인 문의사항을 처리합니다",
          emoji: "💬",
          color: "#6B7280",
        },
      ];
      
      setAvailableTeams(fallbackTeams);
      setSelectedTeam(fallbackTeams[0]);
    }
  }, []);

  useEffect(() => {
    loadAvailableTeams();
    loadConversations();
  }, []);

  return {
    conversations,
    setConversations,
    currentConversation,
    setCurrentConversation,
    conversationId,
    setConversationId,
    availableTeams,
    selectedTeam,
    setSelectedTeam,
    loadConversations,
    saveConversations,
    startNewChat,
    loadConversation,
    deleteConversation,
  };
};