"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import SourcesPanel from "../components/SourcesPanel";
import ConversationSidebar from "../components/ConversationSidebar";
import MessageInput from "../components/MessageInput";
import { useConversation } from "../hooks/useConversation";
import { useMessageState } from "../hooks/useMessageState";
import { useStreaming } from "../hooks/useStreaming";
import { useWebSocket } from "../hooks/useWebSocket";
import MessageContent from "../components/MessageContent";
import { conversationAPI, projectAPI, messageAPI, hybridStorage, localStorageBackup } from "../utils/api";
import "./globals.css";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://49.50.128.6:8000";

export default function Home() {
  // 다크 모드 상태 관리
  const [darkMode, setDarkMode] = useState(null); // null = 시스템 따라가기
  const [isDarkTheme, setIsDarkTheme] = useState(false); // 실제 테마 상태

  // 대화 관련 상태를 커스텀 훅으로 대체
  const {
    conversations,
    setConversations,
    currentConversation,
    setCurrentConversation,
    conversationId,
    setConversationId,
    availableTeams,
    selectedTeam,
    setSelectedTeam,
    saveConversations,
    startNewChat,
    loadConversation,
    deleteConversation,
  } = useConversation();

  // 메시지 상태 관리를 커스텀 훅으로 대체
  const {
    statusToggleOpen,
    setStatusToggleOpen,
    initializeMessageState,
    addMessageStatus,
    completeMessageState,
    getMessageState,
    formatElapsedTime,
    restoreMessageStatesFromConversation,
  } = useMessageState();

  // 스트리밍 관련 상태를 커스텀 훅으로 대체
  const {
    isStreaming,
    setIsStreaming,
    statusMessage,
    setStatusMessage,
    currentStreamingMessage,
    setCurrentStreamingMessage,
    currentStreamingCharts,
    setCurrentStreamingCharts,
    stopGeneration,
    // 🆕 RunId 관련 기능들
    activeRunId,
    canAbort,
    streamProgress,
    savedSources,
    savedCharts,
    resumeAfterRefresh,
    handleRunIdInit,
    saveCheckpointData,
  } = useStreaming();

  // 🆕 WebSocket 연결 관리
  const {
    isConnected,
    connectionStatus,
    sendMessage,
    requestStatus,
    requestAbort,
    connect,
    disconnect
  } = useWebSocket(conversationId);

  const [query, setQuery] = useState("");
  const [isIMEComposing, setIsIMEComposing] = useState(false);

  // 사이드바 관련 상태
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarViewMode, setSidebarViewMode] = useState('main'); // 'main' or 'project-detail'
  const [selectedProjectForView, setSelectedProjectForView] = useState(null);

  // 프로젝트 관련 상태
  const [projects, setProjects] = useState([]);
  const [currentProjectId, setCurrentProjectId] = useState(null);

  // 출처 패널 관련 상태 추가
  const [sourcesData, setSourcesData] = useState(null);
  const [sourcesPanelVisible, setSourcesPanelVisible] = useState(false);

  // Claude 스타일 실시간 검색 결과 상태
  const [currentSearchResults, setCurrentSearchResults] = useState([]);
  const [searchResultsVisible, setSearchResultsVisible] = useState({});
  const [conversationSearchResults, setConversationSearchResults] = useState({});

  // >> 핵심 추가: 데이터 딕셔너리 상태들
  const [fullDataDict, setFullDataDict] = useState({}); // 전체 데이터 딕셔너리
  const [sectionDataDicts, setSectionDataDicts] = useState({}); // 섹션별 데이터 딕셔너리

  // 제목 타이핑 효과 상태
  const [titleGenerating, setTitleGenerating] = useState(false);
  const [generatedTitle, setGeneratedTitle] = useState("");

  // 메시지별 상태 관리는 useMessageState 훅에서 제공

  // 자동 스크롤 제어 상태
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true); // 자동 스크롤 활성화 여부

  // 팀 선택 관련 상태 (selectedTeam, availableTeams는 useConversation 훅에서 제공)
  const [teamSectionExpanded, setTeamSectionExpanded] = useState(false); // 팀 섹션 확장 상태
  const [aiAutoEnabled, setAiAutoEnabled] = useState(true); // AI 자동 선택 활성화 상태
  const [teamDropupOpen, setTeamDropupOpen] = useState(false); // 팀 선택 드롭업 상태
  const [abortController, setAbortController] = useState(null); // 스트리밍 중단용

  // currentSearchResults 설정 함수
  const setCurrentSearchResultsDebug = (newResults) => {
    setCurrentSearchResults(newResults);
  };

  // 스크롤 관리
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const textareaRef = useRef(null);
  const hasRecoveredRef = useRef(false); // 복구 중복 방지용 ref
  const lastConversationIdRef = useRef(null); // 이전 conversationId 추적용

  // 차트 중복 방지를 위한 ID 추적
  const processedChartIds = useRef(new Set());

  // 메시지 끝으로 스크롤 (자동 스크롤이 활성화된 경우에만)
  const scrollToBottom = useCallback(() => {
    if (autoScrollEnabled) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [autoScrollEnabled]);

  // 스크롤 위치가 하단에 있는지 확인하는 함수
  const isScrolledToBottom = useCallback(() => {
    if (!messagesContainerRef.current) return true;

    const container = messagesContainerRef.current;
    const threshold = 100; // 하단에서 100px 이내면 하단으로 간주

    return container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
  }, []);

  // 스크롤 이벤트 핸들러
  const handleScroll = useCallback(() => {
    if (!messagesContainerRef.current) return;

    const scrolledToBottom = isScrolledToBottom();

    // 사용자가 하단으로 스크롤하면 자동 스크롤 재개
    if (scrolledToBottom && !autoScrollEnabled) {
      setAutoScrollEnabled(true);
    }
    // 사용자가 하단에서 벗어나면 자동 스크롤 일시정지
    else if (!scrolledToBottom && autoScrollEnabled) {
      setAutoScrollEnabled(false);
    }
  }, [autoScrollEnabled, isScrolledToBottom]);

  // 스크롤 이벤트 리스너 등록
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    container.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      container.removeEventListener('scroll', handleScroll);
    };
  }, [handleScroll]);

  // 다크 모드 초기화 및 관리
  useEffect(() => {
    // 초기 로드 시 저장된 모드 설정 불러오기
    const savedMode = localStorage.getItem('darkMode');

    if (savedMode !== null) {
      // 저장된 설정이 있으면 사용
      const isDark = savedMode === 'true';
      setDarkMode(isDark);
      applyDarkMode(isDark);
    } else {
      // 저장된 설정이 없으면 시스템 설정 따라가기
      const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      applyDarkMode(systemPrefersDark);
      setIsDarkTheme(systemPrefersDark);
    }

    // 시스템 다크 모드 변경 감지
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleSystemThemeChange = (e) => {
      if (darkMode === null) { // 시스템 따라가기 모드일 때만
        applyDarkMode(e.matches);
      }
    };

    mediaQuery.addEventListener('change', handleSystemThemeChange);
    return () => mediaQuery.removeEventListener('change', handleSystemThemeChange);
  }, [darkMode]);

  // 🆕 대화 로드 완료 시 소스 패널용 데이터 초기화 (메시지별 독립 처리)
  useEffect(() => {
    // 대화가 로드되면 소스 패널 관련 전역 상태 초기화
    if (currentConversation && currentConversation.length > 0) {
      console.log("📊 대화 로드 완료, 소스 패널 초기화, 메시지 개수:", currentConversation.length);

      // 각 메시지는 독립적인 fullDataDict를 가지므로 전역 상태는 초기화만
      setSourcesData(null);
      setSourcesPanelVisible(false);
    }
  }, [currentConversation]);

  // 🆕 페이지 로드 시 스트리밍 복구 로직
  useEffect(() => {
    const attemptStreamingRecovery = async () => {
      // 이미 복구가 완료되었으면 스킵
      if (hasRecoveredRef.current) {
        console.log("⏭️ 이미 복구 완료됨 - 스킵");
        return;
      }

      console.log("🔄 페이지 로드 - 스트리밍 복구 시도");

      if (conversationId) {
        const recovered = await resumeAfterRefresh(conversationId);
        if (recovered) {
          console.log("✅ 스트리밍 상태 복구 완료");
          hasRecoveredRef.current = true; // 복구 완료 표시
          setIsStreaming(true);

          // 복구된 컨텐츠를 현재 메시지에 설정
          if (currentStreamingMessage) {
            console.log("📝 복구된 컨텐츠:", currentStreamingMessage);

            // 대화 업데이트는 별도의 useEffect에서 처리
            setCurrentConversation(prev => {
              const newConversation = [...prev];
              const lastMessage = newConversation[newConversation.length - 1];
              if (lastMessage && lastMessage.role === 'assistant') {
                lastMessage.content = currentStreamingMessage;
              }
              return newConversation;
            });
          }

          // 복구된 출처 정보가 있으면 설정
          if (savedSources && savedSources.length > 0) {
            console.log("📚 복구된 출처:", savedSources);
            // setDisplayedSources가 정의되지 않았으므로 일단 주석처리
            // TODO: 출처 표시 로직 추가 필요
          }
        } else {
          console.log("ℹ️ 복구할 스트리밍 없음");
        }
      }
    };

    // conversationId가 실제로 변경될 때만 복구 상태 리셋
    if (conversationId && conversationId !== lastConversationIdRef.current) {
      console.log(`🔄 대화 ID 변경됨: ${lastConversationIdRef.current} → ${conversationId}`);
      hasRecoveredRef.current = false;
      lastConversationIdRef.current = conversationId;
    }

    // 컴포넌트 마운트 후 약간의 지연을 두고 복구 시도
    const timer = setTimeout(attemptStreamingRecovery, 500);

    return () => clearTimeout(timer);
  }, [conversationId, resumeAfterRefresh, currentStreamingMessage, savedSources]); // 필요한 dependency 추가

  // 🆕 WebSocket 실시간 이벤트 리스너
  useEffect(() => {
    const handleStatusResponse = (event) => {
      const { run_id, status } = event.detail;
      console.log("📡 WebSocket 상태 응답:", { run_id, status });

      if (run_id === activeRunId) {
        if (status === "completed") {
          setIsStreaming(false);
          setStatusMessage("");
        } else if (status === "aborted") {
          setIsStreaming(false);
          setStatusMessage("작업이 중단되었습니다");
        }
      }
    };

    const handleAbortResponse = (event) => {
      const { run_id, success } = event.detail;
      console.log("📡 WebSocket 중단 응답:", { run_id, success });

      if (run_id === activeRunId && success) {
        setIsStreaming(false);
        setStatusMessage("작업이 중단되었습니다");
      }
    };

    const handleAbortNotification = (event) => {
      const { run_id, reason } = event.detail;
      console.log("📡 WebSocket 중단 알림:", { run_id, reason });

      if (run_id === activeRunId) {
        setIsStreaming(false);
        setStatusMessage(`작업이 중단되었습니다: ${reason}`);
      }
    };

    const handleCompletionNotification = (event) => {
      const { run_id, summary } = event.detail;
      console.log("📡 WebSocket 완료 알림:", { run_id, summary });

      if (run_id === activeRunId) {
        setIsStreaming(false);
        setStatusMessage("");
      }
    };

    const handleStatusUpdate = (event) => {
      const { run_id, data } = event.detail;
      console.log("📡 WebSocket 상태 업데이트:", { run_id, data });

      if (run_id === activeRunId && data.message) {
        setStatusMessage(data.message);
      }
    };

    // 이벤트 리스너 등록
    window.addEventListener('websocket_status_response', handleStatusResponse);
    window.addEventListener('websocket_abort_response', handleAbortResponse);
    window.addEventListener('websocket_abort_notification', handleAbortNotification);
    window.addEventListener('websocket_completion_notification', handleCompletionNotification);
    window.addEventListener('websocket_status_update', handleStatusUpdate);

    return () => {
      // 이벤트 리스너 제거
      window.removeEventListener('websocket_status_response', handleStatusResponse);
      window.removeEventListener('websocket_abort_response', handleAbortResponse);
      window.removeEventListener('websocket_abort_notification', handleAbortNotification);
      window.removeEventListener('websocket_completion_notification', handleCompletionNotification);
      window.removeEventListener('websocket_status_update', handleStatusUpdate);
    };
  }, [activeRunId, setIsStreaming, setStatusMessage]);

  // 다크 모드 적용 함수
  const applyDarkMode = (isDark) => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    setIsDarkTheme(isDark);
  };

  // 다크 모드 토글 함수
  const toggleDarkMode = () => {
    const newMode = darkMode === null
      ? !document.documentElement.classList.contains('dark')  // 현재 상태의 반대로
      : !darkMode;  // 설정된 값의 반대로

    setDarkMode(newMode);
    localStorage.setItem('darkMode', newMode.toString());
    applyDarkMode(newMode);
  };

  // 메시지나 스트리밍 내용이 변경될 때 자동 스크롤
  useEffect(() => {
    scrollToBottom();
  }, [currentConversation, currentStreamingMessage, currentStreamingCharts, scrollToBottom]);


  // 드롭업 외부 클릭 시 닫기
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!event.target.closest('.team-tag-container')) {
        setTeamDropupOpen(false);
      }
    };

    if (teamDropupOpen) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [teamDropupOpen]);

  // 스트리밍 시작 시 드롭업 닫기
  useEffect(() => {
    if (isStreaming) {
      setTeamDropupOpen(false);
    }
  }, [isStreaming]);

  // 로컬 스토리지에서 검색 결과와 상태 데이터만 로드 (대화는 useConversation 훅에서 로드)
  useEffect(() => {
    // 현재 대화가 로드된 후 검색 결과 복원
    if (currentConversation.length > 0) {
      const restoredSearchResults = [];
      currentConversation.forEach(message => {
        if (message.searchResults && Array.isArray(message.searchResults)) {
          message.searchResults.forEach(result => {
            restoredSearchResults.push({
              ...result,
              messageId: String(message.id)
            });
          });
        }
      });
      if (restoredSearchResults.length > 0) {
        setCurrentSearchResultsDebug(restoredSearchResults);
      }
    }

    // 메시지 상태는 useMessageState 훅에서 자동으로 로드됨

    const savedCurrentSearchResults = localStorage.getItem("currentSearchResults");
    if (savedCurrentSearchResults) {
      try {
        const parsedSearchResults = JSON.parse(savedCurrentSearchResults);
        if (Array.isArray(parsedSearchResults) && parsedSearchResults.length > 0) {
          setCurrentSearchResultsDebug(parsedSearchResults);
          // console.log(`페이지 로드 시 localStorage에서 검색 결과 복원: ${parsedSearchResults.length}개`);
        }
      } catch (error) {
        // console.error("검색 결과 복원 오류:", error);
      }
    }

    const savedSearchVisible = localStorage.getItem("searchResultsVisible");
    if (savedSearchVisible) {
      try {
        setSearchResultsVisible(JSON.parse(savedSearchVisible));
      } catch (error) {
        // console.error("검색 결과 표시 상태 로드 오류:", error);
      }
    }

    const savedConversationSearchResults = localStorage.getItem("conversationSearchResults");
    if (savedConversationSearchResults) {
      try {
        setConversationSearchResults(JSON.parse(savedConversationSearchResults));
        // console.log("대화별 검색 결과 복원 완료");
      } catch (error) {
        // console.error("대화별 검색 결과 로드 오류:", error);
      }
    }

    const savedStreamingConversation = localStorage.getItem("currentStreamingConversation");
    if (savedStreamingConversation) {
      try {
        const { messages, isStreaming } = JSON.parse(savedStreamingConversation);
        if (isStreaming && Array.isArray(messages) && messages.length > 0) {
          setCurrentConversation(messages);
          setIsStreaming(true);
          // console.log("스트리밍 중이던 대화 복원됨:", messages.length, "개 메시지");
        }
      } catch (error) {
        console.error("스트리밍 대화 복원 오류:", error);
        localStorage.removeItem("currentStreamingConversation");
      }
    }
  }, []);

  // 대화 히스토리 저장


  // 새 채팅 시작 (훅 함수를 래핑하여 UI 상태 초기화 추가)
  const handleStartNewChat = () => {
    // 스트리밍 중인 경우 현재 진행상황을 저장
    if (isStreaming) {
      console.log("🔄 새 채팅 시작 - 스트리밍 중인 내용 저장");
      saveStreamingProgress();

      // 스트리밍 중단
      if (abortController) {
        abortController.abort();
        setAbortController(null);
      }
    }

    // 🔑 핵심: 스트리밍 상태 먼저 해제
    setIsStreaming(false);

    // 훅에서 제공하는 startNewChat 호출 - 프로젝트 ID 없이 (미분류)
    startNewChat(null);
    setCurrentProjectId(null); // 현재 프로젝트 ID도 초기화

    // UI 상태 초기화
    setCurrentStreamingMessage("");
    setCurrentStreamingCharts([]);
    processedChartIds.current.clear();
    setQuery("");
    setSourcesData(null);
    setSourcesPanelVisible(false);
    setCurrentSearchResultsDebug([]);
    setSearchResultsVisible({});
    setConversationSearchResults({});

    // >> 데이터 딕셔너리 초기화
    setFullDataDict({});
    setSectionDataDicts({});

    // 제목 생성 상태 초기화
    setTitleGenerating(false);
    setGeneratedTitle("");

    // 메시지 상태 초기화 (훅에서 관리하므로 setStatusToggleOpen만 호출)
    setStatusToggleOpen({});
    setStatusMessage("");
    localStorage.removeItem('messageStates');

    localStorage.removeItem("currentSearchResults");
    localStorage.removeItem("searchResultsVisible");
    localStorage.removeItem("conversationSearchResults");

    // AI 자동 선택을 기본값으로 설정
    setAiAutoEnabled(true);
    if (availableTeams.length > 0) {
      const autoSelectTeam = availableTeams.find(team => team.id === "AI_AUTO");
      if (autoSelectTeam) {
        setSelectedTeam(autoSelectTeam);
        console.log("🤖 새 채팅 시작 - AI 자동 선택이 기본값으로 설정되었습니다");
      }
    }

    console.log("새 채팅이 시작되었습니다. 스트리밍 상태:", false);
  };

  // 기존 대화 로드 (훅 함수를 래핑하여 UI 상태 복원 추가)
  const handleLoadConversation = async (conv) => {
    // 스트리밍 중인 경우 현재 진행상황을 저장
    if (isStreaming) {
      console.log("🔄 스트리밍 중 대화 전환 - 현재 진행상황 저장");
      saveStreamingProgress();

      // 스트리밍 중단
      if (abortController) {
        abortController.abort();
        setAbortController(null);
      }
      setIsStreaming(false);
      setStatusMessage("");
    }

    // 훅에서 제공하는 loadConversation 호출 (비동기로 대기)
    await loadConversation(conv);

    // 대화의 프로젝트 소속에 따라 currentProjectId 설정
    if (conv.project_id) {
      // 프로젝트에 속한 대화인 경우
      setCurrentProjectId(conv.project_id);
    } else {
      // 미분류 대화인 경우
      setCurrentProjectId(null);
    }

    // UI 상태 초기화 및 복원
    setCurrentStreamingMessage("");
    setCurrentStreamingCharts([]);
    processedChartIds.current.clear();
    setQuery("");
    setSourcesData(null);
    setSourcesPanelVisible(false);

    // 로드 완료 후 currentConversation 사용하여 데이터 딕셔너리 복원
    // (loadConversation이 완료되면 currentConversation이 업데이트됨)
    setTimeout(() => {
      const loadedMessages = currentConversation;

      // >> 데이터 딕셔너리 복원
      if (loadedMessages && loadedMessages.length > 0) {
        console.log("📊 데이터 딕셔너리 복원 시작, 메시지 개수:", loadedMessages.length);

        // 메시지 복사본으로 작업 (원본 수정 방지)
        const messagesCopy = [...loadedMessages];

        // 디버깅: 모든 메시지 확인
        messagesCopy.forEach((msg, idx) => {
          console.log(`메시지 ${idx}:`, {
            id: msg.id,
            type: msg.type,
            hasFullDataDict: !!msg.fullDataDict,
            fullDataDictKeys: msg.fullDataDict ? Object.keys(msg.fullDataDict).length : 0
          });
        });

        // 가장 큰 fullDataDict를 가진 assistant 메시지 찾기
        const assistantMessages = messagesCopy
          .filter(msg => msg.type === "assistant" && !msg.isStreaming && msg.fullDataDict);

        console.log("📊 assistant 메시지 중 fullDataDict 있는 메시지:", assistantMessages.length);

        let bestMessage = null;
        let maxDataDictSize = 0;

        for (const msg of assistantMessages) {
          const dictSize = msg.fullDataDict ? Object.keys(msg.fullDataDict).length : 0;
          if (dictSize > maxDataDictSize) {
            maxDataDictSize = dictSize;
            bestMessage = msg;
          }
        }

        if (bestMessage) {
          if (bestMessage.fullDataDict && Object.keys(bestMessage.fullDataDict).length > 0) {
            setFullDataDict(bestMessage.fullDataDict);
            setSourcesData(bestMessage.fullDataDict); // 소스패널용 데이터도 설정
            console.log(`전체 데이터 딕셔너리 복원 (메시지 ID: ${bestMessage.id}):`, Object.keys(bestMessage.fullDataDict).length, "개");
          } else {
            console.log("⚠️ fullDataDict가 비어있음:", bestMessage.fullDataDict);
          }
          if (bestMessage.sectionDataDicts && Object.keys(bestMessage.sectionDataDicts).length > 0) {
            setSectionDataDicts(bestMessage.sectionDataDicts);
            console.log("섹션 데이터 딕셔너리 복원:", Object.keys(bestMessage.sectionDataDicts).length, "개");
          } else {
            console.log("⚠️ sectionDataDicts가 비어있음:", bestMessage.sectionDataDicts);
          }
        } else {
          console.log("⚠️ fullDataDict를 가진 assistant 메시지를 찾을 수 없음");
        }

        // 메시지 상태 복원
        restoreMessageStatesFromConversation(conv.messages);
      }

      const restoredSearchResults = [];
      if (conv.messages) {
        conv.messages.forEach(message => {
          if (message.searchResults && Array.isArray(message.searchResults)) {
            message.searchResults.forEach(result => {
              restoredSearchResults.push({
                ...result,
                messageId: String(message.id)
              });
            });
          }
        });
      }

      setCurrentSearchResultsDebug(restoredSearchResults);
      console.log(`대화 ${conv.id} 로드 완료 - 검색 결과 ${restoredSearchResults.length}개 복원`);
      setSearchResultsVisible({});
    }, 100);// 100ms 후 실행 (state 업데이트 대기)
  };

  // 출처 패널 토글
  const toggleSourcesPanel = () => {
    setSourcesPanelVisible(!sourcesPanelVisible);
  };

  // 스트리밍 저장 throttling을 위한 ref
  const saveThrottleRef = useRef(null);
  const lastSaveTimeRef = useRef(0);

  // 스트리밍 중 실시간 저장 함수 (throttled)
  const saveStreamingProgress = useCallback(() => {
    if (!isStreaming || !conversationId) return;

    const now = Date.now();
    const timeSinceLastSave = now - lastSaveTimeRef.current;

    // 1초에 한 번만 저장하도록 throttling
    if (timeSinceLastSave < 1000) {
      // 기존 타이머가 있으면 클리어하고 새로 설정
      if (saveThrottleRef.current) {
        clearTimeout(saveThrottleRef.current);
      }

      saveThrottleRef.current = setTimeout(() => {
        performSave();
      }, 1000 - timeSinceLastSave);
      return;
    }

    performSave();

    async function performSave() {
      try {
        lastSaveTimeRef.current = Date.now();

        const currentConv = conversations.find(c => c.id === conversationId);
        if (!currentConv) return;

        // 현재 대화 내용을 실시간으로 저장
        const updatedConversation = {
          ...currentConv,
          messages: currentConversation, // 원본 메시지들 그대로 사용 (saved_to_db 플래그 제거)
          lastUpdated: new Date().toISOString(),
          isStreaming: true, // 스트리밍 중임을 표시
        };

        console.log("💾 스트리밍 중 실시간 저장:", {
          id: conversationId,
          messageCount: currentConversation.length,
          lastMessage: currentConversation[currentConversation.length - 1]?.content?.slice(0, 50) + "...",
          messagesWithContent: currentConversation.filter(m => m.content && m.content.length > 0).length
        });

        // 대화 목록 업데이트
        const updatedConversations = conversations.map(conv =>
          conv.id === conversationId ? updatedConversation : conv
        );

        // localStorage에 즉시 저장
        localStorageBackup.save("chatConversations", updatedConversations);

        // 백엔드에도 저장
        await hybridStorage.saveConversation(updatedConversation);

      } catch (error) {
        console.warn("스트리밍 중 저장 실패:", error);
      }
    }
  }, [isStreaming, conversationId, conversations, currentConversation]);

  // 대화 제목 업데이트 및 저장
  const updateConversationTitle = useCallback(async (newTitle) => {
    try {
      // 대화 목록에서 제목 업데이트
      const updatedConversations = conversations.map(conv =>
        conv.id === conversationId
          ? { ...conv, title: newTitle, lastUpdated: new Date().toISOString(), messages: currentConversation }
          : conv
      );

      console.log("🏷️ 제목 업데이트 및 저장:", newTitle);

      // 상태 업데이트 (DB 저장 건너뛰기 - 중복 방지)
      setConversations(updatedConversations);

      // 직접 DB 저장 (한 번만)
      const currentConv = updatedConversations.find(c => c.id === conversationId);
      if (currentConv) {
        await hybridStorage.saveConversation(currentConv);
      }

    } catch (error) {
      console.warn("제목 업데이트 저장 실패:", error);
    }
  }, [conversationId, conversations, currentConversation]);

  // === 프로젝트 관련 함수 ===
  const loadProjects = useCallback(async () => {
    console.log('🔄 loadProjects() 시작');
    try {
      const loadedProjects = await projectAPI.getAll();
      console.log('📦 로드된 프로젝트:', loadedProjects);

      if (loadedProjects && Array.isArray(loadedProjects)) {
        setProjects(loadedProjects);
        console.log('✅ 프로젝트 state 업데이트 완료');
      } else {
        console.warn('⚠️ 프로젝트 데이터가 배열이 아님:', loadedProjects);
        setProjects([]); // 빈 배열로 초기화
      }
    } catch (error) {
      console.error('❌ 프로젝트 로드 실패:', error);
      // 실패해도 빈 배열로 초기화해서 UI가 깨지지 않도록
      setProjects([]);

      // 잠시 후 재시도
      setTimeout(() => {
        console.log('🔄 프로젝트 로드 재시도...');
        loadProjects();
      }, 2000);
    }
  }, []);

  const handleProjectCreate = useCallback(async (title, description, projectId) => {
    try {
      const newProject = await projectAPI.create(title, description, null, projectId);
      setProjects(prev => [newProject, ...prev]);
      setCurrentProjectId(newProject.id);
      return newProject;
    } catch (error) {
      console.error('프로젝트 생성 실패:', error);
      throw error;
    }
  }, []);

  const handleProjectUpdate = useCallback(async (projectId, title, description) => {
    try {
      const updatedProject = await projectAPI.update(projectId, title, description);
      setProjects(prev => prev.map(p => p.id === projectId ? updatedProject : p));
      return updatedProject;
    } catch (error) {
      console.error('프로젝트 수정 실패:', error);
      throw error;
    }
  }, []);

  const handleProjectDelete = useCallback(async (projectId) => {
    try {
      await projectAPI.delete(projectId);
      setProjects(prev => prev.filter(p => p.id !== projectId));
      if (currentProjectId === projectId) {
        setCurrentProjectId(null);
      }
    } catch (error) {
      console.error('프로젝트 삭제 실패:', error);
      throw error;
    }
  }, [currentProjectId]);

  const handleProjectSelect = useCallback((projectId) => {
    setCurrentProjectId(projectId);
  }, []);

  const handleNewConversationInProject = useCallback((projectId) => {
    console.log('🆕 프로젝트 내 새 대화 생성:', projectId);
    setCurrentProjectId(projectId);

    // startNewChat 훅을 사용하여 프로젝트 ID와 함께 새 대화 생성
    const newChatId = startNewChat(projectId);

    // UI 상태 초기화
    setQuery("");
    setStatusMessage("");
    setIsStreaming(false);
    setFullDataDict({});
    setSourcesData(null);
    setCurrentSearchResultsDebug([]);
    setConversationSearchResults({});
    setSearchResultsVisible({});
    setAbortController(null);
    setSectionDataDicts({});
    setGeneratedTitle("");
    setTitleGenerating(false);

    console.log('✅ 프로젝트 내 새 대화 설정 완료:', { newChatId, projectId });
  }, [startNewChat]);


  // 컴포넌트 마운트 시 프로젝트 로드
  useEffect(() => {
    console.log('🎯 useEffect: 컴포넌트 마운트, 프로젝트 로드 시작');
    loadProjects();
  }, [loadProjects]);

  // 대화 목록 로드 후 이전 상태 복원
  useEffect(() => {
    if (conversations.length > 0 && projects.length > 0) {
      const savedState = localStorage.getItem('chatAppState');
      if (savedState) {
        try {
          const {
            projectId,
            conversationId: savedConvId,
            sidebarViewMode: savedViewMode,
            selectedProjectForView: savedSelectedProject
          } = JSON.parse(savedState);
          console.log('🔄 이전 상태 복원 시도:', { projectId, conversationId: savedConvId, sidebarViewMode: savedViewMode });

          if (projectId && !currentProjectId) {
            setCurrentProjectId(projectId);
          }

          if (savedConvId && !conversationId) {
            const conv = conversations.find(c => c.id === savedConvId);
            if (conv) {
              console.log('✅ 이전 채팅방 복원:', savedConvId);
              loadConversation(conv);
            }
          }

          // 사이드바 뷰 모드 복원
          if (savedViewMode) {
            setSidebarViewMode(savedViewMode);
            if (savedViewMode === 'project-detail' && savedSelectedProject) {
              const project = projects.find(p => p.id === savedSelectedProject.id);
              if (project) {
                setSelectedProjectForView(project);
                console.log('✅ 사이드바 프로젝트 뷰 복원:', project.title);
              }
            }
          }
        } catch (error) {
          console.error('상태 복원 실패:', error);
        }
      }
    }
  }, [conversations, projects, loadConversation]);

  // 현재 상태를 localStorage에 저장
  useEffect(() => {
    if (currentProjectId || conversationId || sidebarViewMode !== 'main') {
      const state = {
        projectId: currentProjectId,
        conversationId: conversationId,
        sidebarViewMode: sidebarViewMode,
        selectedProjectForView: selectedProjectForView
      };
      localStorage.setItem('chatAppState', JSON.stringify(state));
      console.log('💾 현재 상태 저장:', state);
    }
  }, [currentProjectId, conversationId, sidebarViewMode, selectedProjectForView]);

  // 사이드바 뷰 모드 변경 시 프로젝트 선택 상태 관리
  useEffect(() => {
    if (sidebarViewMode === 'main') {
      // 메인 뷰로 돌아왔을 때 현재 대화가 미분류면 프로젝트 선택 해제
      if (conversationId) {
        const currentConv = conversations.find(c => c.id === conversationId);
        if (!currentConv || !currentConv.project_id) {
          setCurrentProjectId(null);
        }
      } else {
        // 선택된 대화가 없으면 프로젝트 선택 해제
        setCurrentProjectId(null);
      }
    }
  }, [sidebarViewMode, conversationId, conversations]);

  // 제목 생성 및 타이핑 효과 적용
  const generateAndSetTitle = async (query) => {
    setTitleGenerating(true);
    setGeneratedTitle("");

    try {
      console.log("🏷️ 제목 생성 시작:", query);
      const titleResponse = await conversationAPI.generateTitle(query);

      if (titleResponse && titleResponse.title) {
        const newTitle = titleResponse.title;
        console.log("✅ 제목 생성 완료:", newTitle);

        // 타이핑 효과로 제목 표시
        let currentIndex = 0;
        const typeTitle = () => {
          if (currentIndex <= newTitle.length) {
            setGeneratedTitle(newTitle.slice(0, currentIndex));
            currentIndex++;
            setTimeout(typeTitle, 50); // 50ms 간격으로 타이핑
          } else {
            setTitleGenerating(false);
            // 대화 목록의 제목 업데이트 및 DB 저장
            updateConversationTitle(newTitle);
          }
        };
        typeTitle();

        // generatedTitle 상태를 유지하기 위해 저장
        window.lastGeneratedTitle = newTitle;
      } else {
        // 제목 생성 실패 시 기본 제목 사용
        const fallbackTitle = query.slice(0, 30) + (query.length > 30 ? "..." : "");
        setGeneratedTitle(fallbackTitle);
        setTitleGenerating(false);
        updateConversationTitle(fallbackTitle);
      }
    } catch (error) {
      console.warn("제목 생성 실패:", error);
      const fallbackTitle = query.slice(0, 30) + (query.length > 30 ? "..." : "");
      setGeneratedTitle(fallbackTitle);
      setTitleGenerating(false);
      setConversations(prev => prev.map(conv =>
        conv.id === conversationId
          ? { ...conv, title: fallbackTitle, lastUpdated: new Date().toISOString() }
          : conv
      ));
    }
  };

  // 경과 시간 포맷 함수

  // 스트리밍 중단 함수 (훅 함수를 래핑하여 추가 로직 포함)
  const handleStopGeneration = async () => {
    // 🆕 RunId 기반 stopGeneration 호출 (비동기)
    const wasStopped = stopGeneration();

    // 🆕 WebSocket으로 중단 요청 전송 (우선순위)
    if (activeRunId && isConnected) {
      console.log("🔌 WebSocket으로 중단 요청 전송:", activeRunId);
      requestAbort(activeRunId, "user_requested");
    }

    if (abortController) {
      console.log("🛑 사용자가 생성을 중단했습니다");
      try {
        abortController.abort();
      } catch (error) {
        // AbortController.abort() 호출 시 발생할 수 있는 에러를 무시
        // 이는 정상적인 중단 동작이므로 에러로 처리하지 않음
      }
      setAbortController(null);

      // 현재 스트리밍 중인 메시지 상태 업데이트
      if (currentConversation.length > 0) {
        const lastMessage = currentConversation[currentConversation.length - 1];
        if (lastMessage && lastMessage.type === "assistant" && lastMessage.isStreaming) {
          // 메시지 상태 완료 처리 (타이머 중단) - 중단 상태로 표시
          completeMessageState(lastMessage.id, true);

          // 백엔드에 중단 시간 정보 업데이트 전송 (IIFE로 async 처리)
          (async () => {
            const messageState = getMessageState(lastMessage.id);
            if (messageState && messageState.startTime && messageState.endTime) {
              try {
                await messageAPI.update(lastMessage.id, {
                  status: "aborted",
                  start_time: new Date(messageState.startTime).toISOString(),
                  end_time: new Date(messageState.endTime).toISOString(),
                  duration_ms: messageState.endTime - messageState.startTime,
                  was_aborted: true,
                  message_state: messageState,
                  status_history: messageState.statusHistory || []
                });
                console.log(`⏰ 중단된 메시지 시간 정보 백엔드 저장 완료: ${lastMessage.id}`);
              } catch (error) {
                console.error(`⚠️ 중단된 메시지 시간 정보 백엔드 저장 실패:`, error);
              }
            }
          })();

          const updatedConversation = currentConversation.map(msg =>
            msg.id === lastMessage.id
              ? { ...msg, isStreaming: false, wasAborted: true, content: currentStreamingMessage || msg.content }
              : msg
          );

          setCurrentConversation(updatedConversation);

          // 중단된 대화도 DB에 저장
          const currentConv = conversations.find(c => c.id === conversationId);
          if (currentConv || conversationId) {
            const conversationData = {
              id: conversationId || Date.now().toString(),
              title: currentConv?.title || window.lastGeneratedTitle || generatedTitle || "중단된 대화",
              project_id: currentProjectId,
              messages: updatedConversation,
              lastUpdated: new Date().toISOString(),
            };

            // conversations 상태 업데이트 및 DB 저장
            const updatedConversations = conversations.filter((c) => c.id !== conversationData.id);
            updatedConversations.unshift(conversationData);
            setConversations(updatedConversations.slice(0, 50));

            // DB에 저장
            hybridStorage.saveConversation(conversationData)
              .then(() => {
                console.log("💾 중단된 대화 저장 완료:", conversationData.id);
              })
              .catch((error) => {
                console.error("💾 중단된 대화 저장 실패:", error);
              });

            console.log("🛑 중단된 대화 저장 처리 완료:", conversationData.id);
          }

          // 스트리밍 상태 초기화
          setIsStreaming(false);
          setCurrentStreamingMessage("");
          setCurrentStreamingCharts([]);
          setStatusMessage("");

          // 임시 스트리밍 데이터 정리
          localStorage.removeItem('currentStreamingConversation');
        }
      }
    }

    return wasStopped;
  };



  // 차트 고유 ID 생성 함수
  const generateChartId = (chartData) => {
    let sampleData = "";
    if (chartData.data) {
      if (Array.isArray(chartData.data)) {
        sampleData = JSON.stringify(chartData.data.slice(0, 2));
      } else {
        sampleData = JSON.stringify(chartData.data);
      }
    }

    const chartKey = JSON.stringify({
      type: chartData.type || "",
      title: chartData.title || "",
      data_sample: sampleData,
    });

    return chartKey;
  };

  // 메시지 전송
  const handleSubmit = async () => {
    console.log("handleSubmit 호출됨, query:", query, "isStreaming:", isStreaming);

    if (!query.trim() || isStreaming) {
      console.log("조건 불만족으로 반환:", {
        queryTrimmed: query.trim(),
        isStreaming: isStreaming
      });
      return;
    }

    console.log("API 요청 시작...");

    // conversationId가 없거나 빈 문자열인 경우 새로 생성
    let currentConversationId = conversationId;
    let isNewConversation = false;
    if (!currentConversationId || currentConversationId.trim() === '') {
      currentConversationId = `chat_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
      setConversationId(currentConversationId);
      isNewConversation = true;
      console.log('🆕 새 대화 ID 생성:', currentConversationId, '프로젝트:', currentProjectId);

      // 새 대화를 conversations 배열에 즉시 추가
      // 현재 conversations에서 이미 있는 대화인지 확인 (startNewChat으로 생성된 경우)
      const existingNewChat = conversations.find(c => c.id === currentConversationId);
      const newConversation = {
        id: currentConversationId,
        title: "", // 빈 제목으로 시작
        project_id: existingNewChat?.project_id || null, // 기존 대화의 project_id 사용, 없으면 null (미분류)
        messages: [],
        lastUpdated: new Date().toISOString(),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        isStreaming: false,
      };

      const updatedConversations = [newConversation, ...conversations];
      setConversations(updatedConversations);
      console.log("🆕 대화 생성 및 배열 추가 완료:", { id: currentConversationId, project_id: currentProjectId, currentProjectId });
    }

    const userMessage = {
      id: Date.now(),
      type: "user",
      content: query.trim(),
      timestamp: new Date().toISOString(),
    };

    setCurrentConversation((prev) => [...prev, userMessage]);
    const currentQuery = query.trim();

    // IME 상태 고려하여 입력란 초기화
    setQuery("");
    if (textareaRef.current) {
      textareaRef.current.value = "";
      textareaRef.current.blur();
      setTimeout(() => textareaRef.current.focus(), 0);
    }

    setIsStreaming(true);
    setCurrentStreamingMessage("");
    setCurrentStreamingCharts([]);
    processedChartIds.current.clear();
    setStatusMessage("생각하는 중...");
    setSourcesData(null);

    // 새 대화인 경우 (제목이 비어있으면) 제목 생성 시작
    let currentConv = conversations.find(c => c.id === currentConversationId);
    console.log("🔍 제목 생성 체크:", {
      conversationId: currentConversationId,
      isNewConversation: isNewConversation,
      conversationsLength: conversations.length,
      currentConv: currentConv ? { id: currentConv.id, title: currentConv.title, project_id: currentConv.project_id } : null,
      shouldGenerate: isNewConversation || !currentConv || (!currentConv.title || currentConv.title === "")
    });

    // 새 대화이거나 제목이 없으면 제목 생성
    if (isNewConversation || !currentConv || (!currentConv.title || currentConv.title === "")) {
      generateAndSetTitle(currentQuery);
    }

    setCurrentSearchResultsDebug([]);
    console.log("🔄 새 질문 시작: 검색 결과 초기화 (세션별 관리)");

    const assistantMessage = {
      id: Date.now() + 1,
      type: "assistant",
      content: "",
      charts: [],
      timestamp: new Date().toISOString(),
      isStreaming: true,
      sources: null,
      statusHistory: [], // 상태 히스토리 초기화
    };

    // 메시지 상태 초기화
    const messageStartTime = initializeMessageState(assistantMessage.id);

    console.log("🕐 메시지 상태 초기화:", {
      messageId: assistantMessage.id,
      startTime: messageStartTime
    });

    setCurrentConversation((prev) => [...prev, assistantMessage]);

    const tempConversationWithNewMessages = [...currentConversation, userMessage, assistantMessage];
    // 현재 대화의 project_id 가져오기
    const currentConvForProject = conversations.find(c => c.id === currentConversationId);
    const tempConversationData = {
      id: currentConversationId,
      title: currentQuery.slice(0, 30) + (currentQuery.length > 30 ? "..." : ""),
      project_id: currentConvForProject?.project_id || null, // 현재 대화의 project_id 사용
      messages: tempConversationWithNewMessages,
      lastUpdated: new Date().toISOString(),
      isStreaming: true,
    };

    localStorage.setItem("currentStreamingConversation", JSON.stringify(tempConversationData));
    console.log("🔄 스트리밍 중 대화 상태 저장:", tempConversationData.id);

    try {
      console.log("API_BASE_URL 값:", API_BASE_URL);
      console.log("API 요청 URL:", `${API_BASE_URL}/query/stream`);
      console.log("🎭 팀 선택 상태:", {
        selectedTeam: selectedTeam,
        selectedTeamId: selectedTeam?.id,
        selectedTeamName: selectedTeam?.name,
      });

      // AbortController 생성
      const controller = new AbortController();
      setAbortController(controller);

      // 메모리 기능: 현재 채팅방의 최근 대화 히스토리 준비
      const currentChatMessages = currentConversation.filter(msg =>
        // 현재 메시지 제외 (아직 추가되지 않은 새 사용자 메시지와 어시스턴트 메시지)
        msg.id !== userMessage.id && msg.id !== assistantMessage.id
      );

      const recentMessages = currentChatMessages
        .slice(-6)  // 최근 6개 메시지 (현재 채팅방에서만)
        .map(msg => ({
          type: msg.type,
          content: msg.content ? msg.content.substring(0, 500) : '', // 길이 제한
          timestamp: msg.timestamp
        }));

      console.log("🧠 채팅방별 메모리 컨텍스트 준비:", {
        conversationId: currentConversationId,
        totalMessagesInChat: currentChatMessages.length,
        recentMessagesCount: recentMessages.length,
        memoryEnabled: recentMessages.length > 0
      });

      // AI 자동 선택이 활성화된 경우 적절한 팀 추천받기
      let finalTeamId = null;

      if (aiAutoEnabled) {
        finalTeamId = "AI_AUTO";
      } else if (selectedTeam && selectedTeam.id !== "AI_AUTO") {
        finalTeamId = selectedTeam.id;
      }

      if (aiAutoEnabled || finalTeamId === "AI_AUTO") {
        console.log("🤖 AI 자동 선택 활성화 - 적절한 팀 추천 요청", {
          reason: !selectedTeam ? "팀 선택 없음" : "AI_AUTO 선택됨",
          selectedTeam: selectedTeam?.name || "없음"
        });

        // 사용자가 팀을 선택하지 않은 경우 AI 자동 선택으로 UI 업데이트
        if (!selectedTeam) {
          const autoSelectTeam = availableTeams.find(team => team.id === "AI_AUTO");
          if (autoSelectTeam) {
            setSelectedTeam(autoSelectTeam);
            console.log("🎯 프론트엔드 UI를 AI 자동 선택으로 업데이트");
          }
        }

        try {
          const suggestResponse = await fetch(`${API_BASE_URL}/teams/suggest`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              query: currentQuery
            }),
          });

          const suggestData = await suggestResponse.json();
          finalTeamId = suggestData.suggested_team || null;
          console.log("🤖 AI 추천 결과:", finalTeamId);

          // UI에 추천된 팀 표시 (옵션)
          if (finalTeamId && finalTeamId !== "기본") {
            console.log(`🎯 AI가 "${finalTeamId}" 팀을 추천했습니다`);
          }
        } catch (suggestError) {
          console.error("팀 추천 API 오류:", suggestError);
          finalTeamId = null; // 오류 시 팀 선택 없음으로 처리
        }
      }

      console.log("📤 최종 요청 데이터:", {
        query: currentQuery,
        session_id: currentConversationId,
        message_id: assistantMessage.id,
        team_id: finalTeamId,
        conversation_history: recentMessages,
        memoryEnabled: recentMessages.length > 0
      });

      console.log("fetch 요청 시작!");

      const res = await fetch(`${API_BASE_URL}/query/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        },
        signal: controller.signal, // AbortController 시그널 추가
        body: JSON.stringify({
          query: currentQuery,
          session_id: currentConversationId,
          message_id: String(assistantMessage.id),
          team_id: finalTeamId, // AI 자동 선택 고려한 최종 팀 ID
          conversation_history: recentMessages, // 메모리 히스토리 추가
        }),
      }).catch(error => {
        console.error("fetch 요청 자체가 실패:", error);
        throw new Error(`Network request failed: ${error.message}`);
      });

      console.log("fetch 응답 받음:", res.status, res.statusText);
      console.log("응답 헤더:", res.headers);

      if (!res.ok) {
        console.error("HTTP 오류 응답:", res.status, res.statusText);
        const errorText = await res.text();
        console.error("오류 내용:", errorText);
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      if (!res.body) {
        console.error("Response body is null");
        throw new Error("Response body is null");
      }

      console.log("스트리밍 시작...");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalContent = "";
      let finalCharts = [];
      let currentStep = 0;
      let totalSteps = 0;

      while (true) {
        // console.log("스트리밍 청크 읽기 시도...");
        const { done, value } = await reader.read();
        // console.log("청크 읽기 결과:", { done, valueLength: value?.length });

        if (done) {
          // console.log("스트리밍 완료");
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        // console.log("디코딩된 청크:", chunk.substring(0, 100) + (chunk.length > 100 ? '...' : ''));
        buffer += chunk;

        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const eventText of events) {
          if (!eventText.trim()) continue;

          if (eventText.startsWith("data: ")) {
            try {
              const data = JSON.parse(eventText.slice(6));
              // console.log(">> 받은 스트리밍 데이터:", data.type, data);

              if (data.session_id && !conversationId) {
                setConversationId(data.session_id);
              }

              switch (data.type) {
                // 🆕 RunId 관련 이벤트들
                case "init":
                  if (data.run_id) {
                    console.log("🚀 RunId 초기화:", data.run_id);
                    handleRunIdInit(data.run_id);
                  }
                  break;

                case "abort":
                  console.log("🛑 스트리밍 중단됨:", data.run_id);
                  setStatusMessage(data.message || "작업이 중단되었습니다");
                  setIsStreaming(false);
                  break;

                case "status":
                  // 안전한 접근: data.data.message 또는 data.message
                  const statusMessage = data.data?.message || data.message || "처리 중...";
                  setStatusMessage(statusMessage);

                  // 메시지 상태에 상태 추가
                  addMessageStatus(assistantMessage.id, statusMessage);

                  // 메시지 객체에 상태 히스토리 즉시 추가
                  setCurrentConversation((prev) =>
                    prev.map((msg) => {
                      if (msg.id === assistantMessage.id) {
                        const currentTime = Date.now();
                        let elapsedSeconds = 0;

                        // 기존 상태 히스토리에서 첫 번째 상태의 타임스탬프를 기준으로 계산
                        const existingHistory = msg.statusHistory || [];
                        if (existingHistory.length > 0) {
                          // 첫 번째 상태 타임스탬프 기준으로 경과 시간 계산
                          const firstStatusTime = existingHistory[0].timestamp;
                          elapsedSeconds = Math.floor((currentTime - firstStatusTime) / 1000);
                        } else {
                          // 첫 번째 상태인 경우, 메시지 상태의 startTime 사용
                          const messageState = getMessageState(assistantMessage.id);
                          const startTime = messageState?.startTime || currentTime;
                          elapsedSeconds = Math.floor((currentTime - startTime) / 1000);
                        }

                        const newStatus = {
                          id: Date.now() + Math.random(),
                          message: statusMessage,
                          timestamp: currentTime,
                          elapsedSeconds: elapsedSeconds
                        };
                        const updatedHistory = [...(msg.statusHistory || []), newStatus];
                        console.log(`📝 상태 추가됨: "${statusMessage}", 총 ${updatedHistory.length}개 상태`);
                        return {
                          ...msg,
                          statusHistory: updatedHistory
                        };
                      }
                      return msg;
                    })
                  );
                  break;

                // >> 새로운 이벤트 타입: 전체 데이터 딕셔너리
                case "full_data_dict":
                  console.log("🎯 full_data_dict 이벤트 받음, data 구조:", data);
                  // main.py에서 data를 펼쳐서 보내므로 data.data_dict로 직접 접근
                  const dataDict = data.data_dict;  // 두 가지 경우 모두 처리
                  if (dataDict) {
                    console.log("✅ 전체 데이터 딕셔너리 받음:", Object.keys(dataDict).length, "개");
                    console.log("📊 데이터 딕셔너리 키들:", Object.keys(dataDict));

                    setFullDataDict(dataDict);

                    // dataDict를 sourcesData에도 직접 설정
                    setSourcesData(dataDict);
                    // console.log("✅ setSourcesData에도 dataDict 설정 완료");

                    // 즉시 현재 메시지에도 저장
                    setCurrentConversation((prev) =>
                      prev.map((msg) =>
                        msg.id === assistantMessage.id
                          ? { ...msg, fullDataDict: dataDict }
                          : msg
                      )
                    );
                    // console.log("✅ 현재 메시지에도 fullDataDict 저장 완료");

                    // 중요한 데이터가 업데이트되었으므로 저장
                    saveStreamingProgress();
                  } else {
                    // console.error("❌ 데이터 딕셔너리를 찾을 수 없음, data 구조:", JSON.stringify(data, null, 2));
                  }
                  break;

                case "chart":
                  if (data.chart_data) {
                    finalCharts.push(data.chart_data);

                    // 🆕 차트 체크포인트 저장
                    saveCheckpointData('chart', data.chart_data);

                    setCurrentConversation((prev) =>
                      prev.map((msg) =>
                        msg.id === assistantMessage.id
                          ? {
                              ...msg,
                              charts: [...finalCharts],
                            }
                          : msg
                      )
                    );

                    // 차트가 추가되었으므로 저장
                    saveStreamingProgress();
                  }
                  break;

                case "plan":
                  totalSteps = data.total_steps || data.data?.plan?.steps?.length || data.plan?.steps?.length || 0;
                  setStatusMessage(`실행 계획: ${totalSteps}개 단계`);
                  console.log("실행 계획:", data.data?.plan || data.plan);
                  break;

                case "step_start":
                  currentStep = data.step || data.data?.step;

                  let statusText = `단계 ${currentStep}/${totalSteps}: ${data.description || data.data?.description || "처리 중"}`;
                  if ((data.tool || data.data?.tool) && (data.query || data.data?.query)) {
                    const tool = data.tool || data.data?.tool;
                    const query = data.query || data.data?.query;
                    const status = data.status || data.data?.status;

                    if (status === "searching") {
                      statusText = `${tool}로 검색 중: "${query}"`;
                    } else if (data.status === "processing") {
                      statusText = `${data.tool}로 처리 중`;
                    }
                  }

                  setStatusMessage(statusText);
                  break;

                case "search_results":
                  console.log("검색 결과 받음:", data);

                  const isIntermediateSearch = data.is_intermediate_search || false;
                  const sectionContext = data.section_context || null;

                  if (isIntermediateSearch && sectionContext) {
                    console.log("중간 검색 감지:", sectionContext);
                  }

                  const searchResultData = {
                    step: data.step,
                    tool_name: data.tool_name || "unknown",
                    query: data.query || "",
                    results: data.results,
                    timestamp: new Date().toISOString(),
                    conversationId: conversationId || data.session_id || Date.now().toString(),
                    messageId: data.message_id || assistantMessage.id,
                    isIntermediateSearch: isIntermediateSearch,
                    sectionContext: sectionContext
                  };

                  // 🆕 검색 결과 체크포인트 저장
                  saveCheckpointData('sources', {
                    tool_name: data.tool_name,
                    query: data.query,
                    results: data.results
                  });
                  // console.log("처리된 검색 데이터:", searchResultData);

                  const currentConvId = conversationId || data.session_id || Date.now().toString();

                  setConversationSearchResults(prev => {
                    const newResults = {
                      ...prev,
                      [currentConvId]: [...(prev[currentConvId] || []), searchResultData]
                    };
                    localStorage.setItem("conversationSearchResults", JSON.stringify(newResults));
                    return newResults;
                  });

                  setCurrentSearchResultsDebug(prev => {
                    const newResults = [...prev, searchResultData];

                    localStorage.setItem("currentSearchResults", JSON.stringify(newResults));
                    // console.log(`🔍 검색 결과 추가 (총 ${newResults.length}개):`, searchResultData);

                    setCurrentConversation(prevMessages => {
                      return prevMessages.map(msg => {
                        if (msg.id === assistantMessage.id && msg.type === "assistant") {
                          const messageSearchResults = newResults.filter(result => {
                            const resultMsgId = String(result.messageId);
                            const assistantMsgId = String(assistantMessage.id);
                            const match = resultMsgId === assistantMsgId;
                            // console.log(`🔍 검색 결과 매칭 확인:`, {
                            //   resultMessageId: result.messageId,
                            //   resultMsgIdString: resultMsgId,
                            //   assistantMessageId: assistantMessage.id,
                            //   assistantMsgIdString: assistantMsgId,
                            //   match: match
                            // });
                            return match;
                          });
                          // console.log(`🔍 메시지 ${assistantMessage.id}에 검색 결과 저장: ${messageSearchResults.length}개`);
                          // console.log(`🔍 전체 검색 결과:`, newResults.map(r => ({ messageId: r.messageId, query: r.query })));
                          return {
                            ...msg,
                            searchResults: messageSearchResults
                          };
                        }
                        return msg;
                      });
                    });

                    return newResults;
                  });

                  setSearchResultsVisible(prev => {
                    const newVisible = {
                      ...prev,
                      [`${data.step}-latest`]: true
                    };
                    localStorage.setItem("searchResultsVisible", JSON.stringify(newVisible));
                    return newVisible;
                  });

                  const tempSources = {
                    total_count: data.results.length,
                    sources: data.results.map((result, index) => ({
                      id: `temp_${data.step}_${index}`,
                      title: result.title,
                      content: result.content_preview,
                      url: result.url,
                      source_type: result.source,
                      score: result.score,
                      document_type: result.document_type
                    }))
                  };

                  setSourcesData(tempSources);
                  break;

                case "section_mapping":
                  // console.log("섹션 매핑 정보 받음:", data);
                  // console.log("섹션 제목:", data.section_title);
                  // console.log("섹션 데이터 딕셔너리:", data.section_data_dict);
                  // console.log("사용된 인덱스:", data.section_indexes);

                  const sectionKey = `${conversationId || data.session_id || Date.now()}-${data.section_title}`;
                  // console.log("생성된 섹션 키:", sectionKey);

                  setSectionDataDicts(prev => {
                    const newSectionDicts = {
                      ...prev,
                      [sectionKey]: {
                        dataDict: data.section_data_dict,
                        indexes: data.section_indexes,
                        title: data.section_title
                      }
                    };
                    // console.log("업데이트된 섹션 딕셔너리:", newSectionDicts);
                    return newSectionDicts;
                  });
                  break;

                case "section_header":
                  setCurrentConversation((prev) => {
                    const updated = [...prev];
                    if (updated.length > 0 && updated[updated.length - 1].id === assistantMessage.id) {
                      const lastMessage = updated[updated.length - 1];
                      if (!lastMessage.sectionHeaders) {
                        lastMessage.sectionHeaders = [];
                      }
                      lastMessage.sectionHeaders.push({
                        id: `header-${Date.now()}-${Math.random()}`,
                        title: data.title,
                        timestamp: Date.now()
                      });
                      return updated.map((msg) =>
                        msg.id === assistantMessage.id
                          ? { ...msg, content: finalContent }
                          : msg
                      );
                    }
                    return updated;
                  });
                  break;

                case "sources":
                  // sources 이벤트는 더 이상 사용하지 않음 (full_data_dict만 사용)
                  // console.log("⚠️ sources 이벤트 수신 (무시됨):", data);
                  break;

                case "section_start":
                  const sectionHeader = `\n\n## ${data.title}\n\n`;
                  finalContent += sectionHeader;
                  setCurrentConversation((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMessage.id
                        ? {
                            ...msg,
                            content: (msg.content || "") + sectionHeader,
                            isStreaming: true
                          }
                        : msg
                    )
                  );
                  break;

                case "content":
                  finalContent += data.chunk;
                  setCurrentConversation((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMessage.id
                        ? {
                            ...msg,
                            content: finalContent,
                            isStreaming: true
                          }
                        : msg
                    )
                  );

                  // 스트리밍 중 실시간 저장 (throttled)
                  saveStreamingProgress();
                  break;

                case "section_end":
                  const sectionEnd = "\n\n";
                  finalContent += sectionEnd;
                  setCurrentConversation((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMessage.id
                        ? {
                            ...msg,
                            content: (msg.content || "") + sectionEnd,
                            isStreaming: true
                          }
                        : msg
                    )
                  );
                  break;

                case "step_complete":
                  setStatusMessage(
                    `단계 ${data.step} 완료 (${data.step}/${totalSteps})`
                  );
                  break;

                case "chart":
                  const chartId = generateChartId(data.chart_data);
                  if (!processedChartIds.current.has(chartId)) {
                    processedChartIds.current.add(chartId);
                    finalCharts.push(data.chart_data);
                    const chartIndex = processedChartIds.current.size - 1;
                    const chartPlaceholder = `\n\n[CHART-PLACEHOLDER-${chartIndex}]\n\n`;
                    finalContent += chartPlaceholder;

                    setCurrentConversation((prev) =>
                      prev.map((msg) =>
                        msg.id === assistantMessage.id
                          ? {
                              ...msg,
                              content: (msg.content || "") + chartPlaceholder,
                              charts: [...finalCharts],
                              isStreaming: true
                            }
                          : msg
                      )
                    );
                  }
                  break;

                case "complete":
                  setStatusMessage("완료");
                  // console.log("complete 이벤트 수신, 현재 fullDataDict 상태:", {
                  //   hasFullDataDict: !!fullDataDict,
                  //   fullDataDictSize: Object.keys(fullDataDict || {}).length
                  // });
                  break;

                case "final_complete":
                  setStatusMessage("");

                  // 메시지 상태 완료 처리
                  completeMessageState(assistantMessage.id);

                  // 백엔드에 시간 정보 업데이트 전송 (IIFE로 async 처리)
                  (async () => {
                    const messageState = getMessageState(assistantMessage.id);
                    if (messageState && messageState.startTime && messageState.endTime) {
                      try {
                        await messageAPI.update(assistantMessage.id, {
                          status: "completed",
                          start_time: new Date(messageState.startTime).toISOString(),
                          end_time: new Date(messageState.endTime).toISOString(),
                          duration_ms: messageState.endTime - messageState.startTime,
                          message_state: messageState,
                          status_history: messageState.statusHistory || []
                        });
                        console.log(`⏰ 메시지 시간 정보 백엔드 저장 완료: ${assistantMessage.id}`);
                      } catch (error) {
                        console.error(`⚠️ 메시지 시간 정보 백엔드 저장 실패:`, error);
                      }
                    }
                  })();

                  // 메시지에 상태 저장
                  setCurrentConversation((prevConversation) => {
                    const newConversation = prevConversation.map((msg) => {
                      if (msg.id === assistantMessage.id) {
                        const messageState = getMessageState(assistantMessage.id);

                        // 현재 메시지의 statusHistory 확인
                        console.log(`🔍 final_complete 시 메시지 상태:`, {
                          id: msg.id,
                          currentStatusHistoryLength: msg.statusHistory?.length || 0,
                          messageStateHistoryLength: messageState?.statusHistory?.length || 0
                        });

                        const updatedMessage = {
                          ...msg,
                          charts: finalCharts,
                          isStreaming: false,
                          fullDataDict: msg.fullDataDict || fullDataDict,
                          sourcesData: msg.sourcesData || sourcesData, // 출처 데이터도 저장
                          sectionDataDicts: sectionDataDicts,
                          // 메시지 상태 저장
                          messageState: messageState,
                          // 기존 statusHistory 우선 유지 (status 이벤트에서 업데이트된 것)
                          statusHistory: msg.statusHistory || messageState?.statusHistory || [],
                          saved_to_db: false // 저장 전이므로 false로 설정
                        };

                        return updatedMessage;
                      }
                      return msg;
                    });

                    // 대화 저장 (제목은 이미 실시간으로 생성됨)
                    const currentConv = conversations.find(c => c.id === conversationId);

                    // 디버깅: 저장 직전 assistant 메시지의 statusHistory 확인
                    const assistantMsg = newConversation.find(m => m.id === assistantMessage.id);
                    console.log(`💾 final_complete 저장 전 상태:`, {
                      assistantMsgId: assistantMsg?.id,
                      statusHistoryLength: assistantMsg?.statusHistory?.length || 0,
                      statusHistory: assistantMsg?.statusHistory
                    });

                    const conversationData = {
                      id: conversationId || Date.now().toString(),
                      title: currentConv?.title || window.lastGeneratedTitle || generatedTitle || currentQuery.slice(0, 30) + (currentQuery.length > 30 ? "..." : ""),
                      project_id: currentProjectId, // 현재 선택된 프로젝트 ID 추가
                      messages: newConversation, // 원본 메시지들 그대로 사용 (saved_to_db 플래그는 hybridStorage에서 설정)
                      lastUpdated: new Date().toISOString(),
                    };

                    const updatedConversations = conversations.filter((c) => c.id !== conversationData.id);
                    updatedConversations.unshift(conversationData);

                    // 대화를 conversations 상태에 즉시 반영하고 DB에 저장
                    setConversations(updatedConversations.slice(0, 50));

                    // hybridStorage를 통해 직접 DB에 저장
                    hybridStorage.saveConversation(conversationData)
                      .then(() => {
                        console.log("💾 final_complete 대화 저장 완료:", conversationData.id);
                      })
                      .catch((error) => {
                        console.error("💾 final_complete 대화 저장 실패:", error);
                      });

                    localStorage.removeItem('currentStreamingConversation');

                    return newConversation;
                  });

                  setIsStreaming(false);
                  break;

                case "error":
                  setStatusMessage(`오류: ${data.message}`);
                  setIsStreaming(false);
                  localStorage.removeItem('currentStreamingConversation');
                  return;

                case "result":
                  // console.log("처리 결과:", data.data);
                  break;

                default:
                  console.log("알 수 없는 이벤트 타입:", data.type, data);
                  break;
              }
            } catch (parseError) {
              console.error("JSON 파싱 오류:", parseError);
            }
          }
        }
      }
    } catch (error) {
      // AbortError는 사용자가 의도적으로 중단한 것이므로 오류 로그 출력하지 않음
      if (error.name === 'AbortError') {
        console.log("🛑 요청이 중단되었습니다");
        setStatusMessage(""); // 중단 시에는 상태 메시지를 비움 (에러가 아니므로)
        return; // 에러 로그를 남기지 않고 조용히 종료
      } else {
        // AbortError가 아닌 실제 오류인 경우에만 로그 출력
        console.error("=== API 오류 상세 정보 ===");
        console.error("오류 타입:", error.name);
        console.error("오류 메시지:", error.message);
        console.error("오류 스택:", error.stack);
        console.error("========================");
        setStatusMessage(`오류: ${error.message}`);
      }

      setIsStreaming(false);
      setAbortController(null);
      localStorage.removeItem('currentStreamingConversation');
    }
  };

  // Enter 키 처리 (IME 고려)
  const handleKeyPress = (e) => {
    // IME 입력 중일 때는 Enter 처리하지 않음
    if (e.key === "Enter" && !e.shiftKey && !isIMEComposing) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // IME 상태 핸들러들
  const handleCompositionStart = () => {
    setIsIMEComposing(true);
  };

  const handleCompositionEnd = () => {
    setIsIMEComposing(false);
  };


  // 메시지 컨텐츠 렌더링을 새로운 컴포넌트로 대체
  const renderMessageContent = (message) => {
    return (
      <MessageContent
        message={message}
        isStreaming={isStreaming}
        fullDataDict={fullDataDict}
        sourcesData={sourcesData}
      />
    );
  };

  // textarea 자동 높이 조절
  const adjustTextareaHeight = useCallback(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 120) + "px";
    }
  }, []);

  useEffect(() => {
    adjustTextareaHeight();
  }, [query, adjustTextareaHeight]);

  // 페이지 벗어날 때 스트리밍 중인 내용 저장
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (isStreaming) {
        console.log("🔄 페이지 벗어남 - 스트리밍 중인 내용 저장");
        saveStreamingProgress();

        // 브라우저에 경고 표시
        e.preventDefault();
        e.returnValue = '현재 답변을 생성 중입니다. 페이지를 벗어나면 생성 중인 내용이 저장됩니다.';
        return e.returnValue;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [isStreaming, saveStreamingProgress]);


  return (
    <div className="chat-app">
      <ConversationSidebar
        sidebarOpen={sidebarOpen}
        setSidebarOpen={setSidebarOpen}
        conversations={conversations}
        conversationId={conversationId}
        isStreaming={isStreaming}
        onNewChat={handleStartNewChat}
        onLoadConversation={handleLoadConversation}
        projects={projects}
        currentProjectId={currentProjectId}
        onProjectSelect={handleProjectSelect}
        onProjectCreate={handleProjectCreate}
        onProjectUpdate={handleProjectUpdate}
        onProjectDelete={handleProjectDelete}
        onNewConversationInProject={handleNewConversationInProject}
        onDeleteConversation={deleteConversation}
        titleGenerating={titleGenerating}
        generatedTitle={generatedTitle}
        viewMode={sidebarViewMode}
        setViewMode={setSidebarViewMode}
        selectedProjectForView={selectedProjectForView}
        setSelectedProjectForView={setSelectedProjectForView}
      />

      {/* 메인 채팅 영역 */}
      <div className={`chat-main ${sourcesPanelVisible ? "chat-main-with-sources" : ""} ${!sidebarOpen ? "chat-main-sidebar-closed" : ""}`}>
        {/* 채팅방 제목 헤더 */}
        {conversationId && (
          <div className="chat-header">
            <div className="chat-title">
              {(() => {
                const currentConv = conversations.find(c => c.id === conversationId);
                if (titleGenerating && (!currentConv?.title || currentConv?.title === "")) {
                  return (
                    <>
                      {generatedTitle}
                      <span className="typing-cursor">|</span>
                    </>
                  );
                }
                return currentConv?.title || "새 대화";
              })()}
            </div>
            <div className="connection-status">
              <div className={`connection-indicator ${connectionStatus}`} title={`WebSocket: ${connectionStatus}`}>
                <div className="connection-dot"></div>
              </div>
            </div>
          </div>
        )}

        {/* 메시지 영역 */}
        <div className="messages-container" ref={messagesContainerRef}>
          {currentConversation.length === 0 ? (
            <div className="welcome-screen">
              <div className="welcome-content">
                <h1>안녕하세요!</h1>
                <p>무엇을 도와드릴까요?</p>
              </div>
            </div>
          ) : (
            <>
              {currentConversation.map((message) => (
                <div key={message.id}>
                  <div className={`message-wrapper ${message.type}`}>
                    {message.type === "assistant" && (
                      <div className="assistant-avatar">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <path fillRule="evenodd" clipRule="evenodd" d="M17.3951 21.0001C16.6131 21.0001 15.7351 20.8311 14.7791 20.5051C13.8091 20.1651 12.8771 19.7241 11.9991 19.1891C11.1207 19.7274 10.1874 20.1706 9.21509 20.5111C8.25909 20.8371 7.38209 21.0001 6.60509 21.0001C5.50309 21.0001 4.59709 20.6741 3.96209 20.0381C2.87009 18.9471 2.70209 17.0791 3.48909 14.7781C3.83109 13.8081 4.27409 12.8771 4.81109 12.0001C4.27369 11.1226 3.83057 10.1908 3.48909 9.2201C2.70209 6.9151 2.87009 5.0531 3.96209 3.9611C5.05209 2.8701 6.92009 2.7011 9.22209 3.4891C10.1321 3.7991 11.0661 4.2491 12.0001 4.8111C12.9341 4.2481 13.8671 3.7981 14.7791 3.4891C17.0791 2.7011 18.9471 2.8701 20.0391 3.9611C21.1291 5.0531 21.2991 6.9211 20.5111 9.2211C20.1691 10.1911 19.7261 11.1231 19.1891 12.0001C19.7521 12.9341 20.2011 13.8671 20.5111 14.7781C21.2981 17.0851 21.1301 18.9471 20.0381 20.0381C19.4031 20.6741 18.4971 20.9941 17.3951 20.9941V21.0001ZM15.7181 15.7121C14.5951 16.8448 13.3479 17.8471 12.0001 18.7001C10.6517 17.8507 9.4043 16.8506 8.28209 15.7191C7.10009 14.5371 6.08809 13.2701 5.30009 12.0001C6.08809 10.7231 7.10009 9.4571 8.28209 8.2761C9.46309 7.0951 10.7231 6.0821 11.9951 5.2941C13.2711 6.0821 14.5371 7.0941 15.7181 8.2761C16.9001 9.4571 17.9121 10.7231 18.7001 12.0001C17.85 13.3465 16.8496 14.5918 15.7181 15.7121ZM16.0111 16.0111C14.9161 17.1149 13.705 18.0973 12.3991 18.9411C13.1958 19.4167 14.0384 19.8106 14.9141 20.1171C17.0511 20.8481 18.7731 20.7191 19.7461 19.7461C20.7191 18.7721 20.8481 17.0561 20.1171 14.9081C19.8106 14.0324 19.4166 13.1898 18.9411 12.3931C18.0995 13.7022 17.117 14.9161 16.0111 16.0111ZM7.98909 16.0101C6.88493 14.9132 5.90256 13.7001 5.05909 12.3921C4.58443 13.191 4.19049 14.0352 3.88309 14.9121C3.15209 17.0501 3.28109 18.7721 4.25409 19.7451C5.22709 20.7181 6.94309 20.8471 9.08609 20.1151C9.90709 19.8351 10.7561 19.4411 11.6011 18.9401C10.2951 18.0963 9.08413 17.1139 7.98909 16.0101ZM7.98909 7.9881C6.88562 9.08319 5.9036 10.2942 5.06009 11.6001C4.58579 10.8031 4.19186 9.96099 3.88409 9.0861C3.15309 6.9431 3.28209 5.2271 4.25509 4.2481C4.81809 3.6971 5.61609 3.4101 6.60609 3.4101C7.33809 3.4101 8.17609 3.5681 9.08709 3.8831C9.96209 4.18889 10.8046 4.58081 11.6021 5.0531C10.2959 5.89881 9.08482 6.88319 7.99009 7.9891M16.0121 7.9891C14.9158 6.8829 13.7031 5.89851 12.3951 5.0531C13.194 4.57844 14.0381 4.1845 14.9151 3.8771C15.7109 3.58785 16.5486 3.43012 17.3951 3.4101C18.3851 3.4101 19.1901 3.6911 19.7471 4.2541C20.7201 5.2271 20.8491 6.9431 20.1181 9.0861C19.8129 9.96202 19.4188 10.8044 18.9421 11.6001C18.0998 10.2948 17.1191 9.08408 16.0171 7.9891H16.0121ZM7.50009 11.9991C11.9211 11.3641 11.9551 7.4991 11.9551 7.4991V7.5451C12.0462 8.70737 12.5581 9.79651 13.3948 10.6084C14.2315 11.4202 15.3356 11.899 16.5001 11.9551V12.0001C12.0791 12.6351 12.0451 16.5001 12.0451 16.5001V16.4551C11.4041 12.0781 7.50009 12.0451 7.50009 12.0451V11.9991Z" fill="#10a37f" stroke="#10a37f" strokeWidth="0.5" />
                        </svg>
                      </div>
                    )}
                    <div className="message-content">
                      {/* 어시스턴트 메시지에서 상태 표시 */}
                      {message.type === "assistant" && (() => {
                        // 현재 스트리밍 중이거나 완료된 메시지의 상태가 있는 경우 표시
                        const messageState = getMessageState(message.id);
                        const storedMessageState = message.messageState;
                        const hasStatusHistory = message.statusHistory && message.statusHistory.length > 0;
                        const hasState = messageState || storedMessageState || hasStatusHistory;

                        return hasState;
                      })() && (
                        <div className="thinking-stream">
                          <div
                            className="thinking-stream-header"
                            onClick={() => setStatusToggleOpen(prev => ({
                              ...prev,
                              [message.id]: !prev[message.id]
                            }))}
                          >
                            <div className="thinking-stream-title">
                              <div className="pulse-dot"></div>
                              <span>
                                {(() => {
                                  const messageState = getMessageState(message.id) || message.messageState;
                                  const isCurrentStreaming = message.isStreaming && isStreaming;

                                  let displayTime = 0;
                                  if (messageState) {
                                    // 복원된 총 소요시간이 있으면 우선 사용
                                    if (messageState.totalElapsedSeconds) {
                                      displayTime = messageState.totalElapsedSeconds;
                                    }
                                    // 스트리밍 중인 경우 elapsedSeconds 사용
                                    else if (messageState.elapsedSeconds) {
                                      displayTime = messageState.elapsedSeconds;
                                    }
                                    // 완료된 경우 startTime과 endTime으로 계산
                                    else if (messageState.startTime && messageState.endTime) {
                                      displayTime = Math.floor((messageState.endTime - messageState.startTime) / 1000);
                                    }
                                  }
                                  // messageState가 없거나 displayTime이 0인 경우 statusHistory 직접 확인
                                  if (displayTime === 0 && message.statusHistory && message.statusHistory.length > 0) {
                                    const lastStatus = message.statusHistory[message.statusHistory.length - 1];
                                    displayTime = lastStatus.elapsedSeconds || 0;
                                  }

                                  if (statusToggleOpen[message.id]) {
                                    return isCurrentStreaming ? `생각하는 중...` : `생각 과정`;
                                  } else {
                                    return isCurrentStreaming ?
                                      `생각하는 중... (${formatElapsedTime(displayTime)})` :
                                      `생각 완료 (${formatElapsedTime(displayTime)})`;
                                  }
                                })()}
                              </span>
                            </div>
                            <div className="thinking-stream-toggle">
                              {statusToggleOpen[message.id] ? '▼' : '▶'}
                            </div>
                          </div>

                          {statusToggleOpen[message.id] && (
                            <div className="thinking-stream-content">
                              {(() => {
                                const messageState = getMessageState(message.id) || message.messageState;
                                // 메시지에 직접 저장된 statusHistory를 우선 사용 (DB에서 로드된 경우)
                                const statusHistory = message.statusHistory || messageState?.statusHistory || [];

                                console.log(`🔍 상태 박스 렌더링:`, {
                                  messageId: message.id,
                                  messageStatusHistoryLength: message.statusHistory?.length || 0,
                                  messageStateHistoryLength: messageState?.statusHistory?.length || 0,
                                  finalStatusHistoryLength: statusHistory.length
                                });

                                return statusHistory.map((status, index) => (
                                  <div
                                    key={status.id || `status-${index}-${status.timestamp}`}
                                    className={`thinking-step ${status.isCompleted ? 'completed' : ''}`}
                                  >
                                    <div className="step-indicator">
                                      {status.isCompleted ? '✓' : '●'}
                                    </div>
                                    <div className="step-content">
                                      <span className="step-message">{status.message}</span>
                                      <span className="step-time">
                                        {formatElapsedTime(status.elapsedSeconds || 0)}
                                      </span>
                                    </div>
                                  </div>
                                ));
                              })()}
                            </div>
                          )}
                        </div>
                      )}

                      {/* 완료된 어시스턴트 메시지 위에 해당 검색 결과 먼저 표시 */}
                      {message.type === "assistant" && !message.isStreaming && message.searchResults && message.searchResults.length > 0 && (
                        <div className="claude-search-results">
                          {/* {console.log("렌더링 중인 완료된 메시지 검색 결과:", message.searchResults)} */}
                          {message.searchResults.map((searchData, index) => (
                            <div key={`search-${searchData.step}-${index}`} className={`search-result-section ${searchData.isIntermediateSearch ? 'intermediate-search' : ''}`}>
                              <div
                                className="search-result-header"
                                onClick={() => setSearchResultsVisible(prev => {
                                  const newVisible = {
                                    ...prev,
                                    [`${message.id}-${searchData.step}-${index}`]: !prev[`${message.id}-${searchData.step}-${index}`]
                                  };
                                  localStorage.setItem("searchResultsVisible", JSON.stringify(newVisible));
                                  return newVisible;
                                })}
                              >
                                <div className="search-info">
                                  <span className="search-tool">{searchData.tool_name}</span>
                                  {searchData.isIntermediateSearch && searchData.sectionContext && (
                                    <span className="intermediate-badge">
                                      📊 {searchData.sectionContext.section_title}
                                    </span>
                                  )}
                                  {searchData.query && (
                                    <span className="search-query">
                                      "{searchResultsVisible[`${message.id}-${searchData.step}-${index}`]
                                        ? searchData.query
                                        : (searchData.query.length > 50 ? searchData.query.substring(0, 50) + '...' : searchData.query)}"
                                    </span>
                                  )}
                                  <span className="result-count">{searchData.results.length}개 결과</span>
                                  {searchData.isIntermediateSearch && searchData.sectionContext && (
                                    <span className="search-reason">
                                      {searchData.sectionContext.search_reason}
                                    </span>
                                  )}
                                </div>
                                <div className="toggle-icon">
                                  {searchResultsVisible[`${message.id}-${searchData.step}-${index}`] ? '▼' : '▶'}
                                </div>
                              </div>

                              {searchResultsVisible[`${message.id}-${searchData.step}-${index}`] && (
                                <div className="search-result-list">
                                  {searchData.results.map((result, resultIndex) => (
                                    <div key={resultIndex} className="search-result-item">
                                      <div className="result-header">
                                        <span className="result-title">{result.title}</span>
                                        <span className="result-source">{result.source}</span>
                                      </div>
                                      <div className="result-preview">{result.content_preview}</div>
                                      {result.url && (
                                        <div className="result-url">
                                          <a href={result.url} target="_blank" rel="noopener noreferrer">
                                            {result.url}
                                          </a>
                                        </div>
                                      )}
                                      <div className="result-meta">
                                        <span>관련성: {((result.score || result.relevance_score || 0) * 100).toFixed(0)}%</span>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* 현재 스트리밍 중인 메시지에서만 실시간 검색 결과 표시 */}
                      {message.type === "assistant" && message.isStreaming && isStreaming && currentSearchResults.length > 0 && (
                        <div className="claude-search-results">
                          {currentSearchResults.map((searchData, index) => (
                            <div key={`search-${searchData.step}-${index}`} className={`search-result-section ${searchData.isIntermediateSearch ? 'intermediate-search' : ''}`}>
                              <div
                                className="search-result-header"
                                onClick={() => setSearchResultsVisible(prev => {
                                  const newVisible = {
                                    ...prev,
                                    [`current-${searchData.step}-${index}`]: !prev[`current-${searchData.step}-${index}`]
                                  };
                                  localStorage.setItem("searchResultsVisible", JSON.stringify(newVisible));
                                  return newVisible;
                                })}
                              >
                                <div className="search-info">
                                  <span className="search-tool">{searchData.tool_name}</span>
                                  {searchData.isIntermediateSearch && searchData.sectionContext && (
                                    <span className="intermediate-badge">
                                      {searchData.sectionContext.section_title}
                                    </span>
                                  )}
                                  {searchData.query && (
                                    <span className="search-query">
                                      "{searchResultsVisible[`${message.id}-${searchData.step}-${index}`]
                                        ? searchData.query
                                        : (searchData.query.length > 50 ? searchData.query.substring(0, 50) + '...' : searchData.query)}"
                                    </span>
                                  )}
                                  <span className="result-count">{searchData.results.length}개 결과</span>
                                  {searchData.isIntermediateSearch && searchData.sectionContext && (
                                    <span className="search-reason">
                                      {searchData.sectionContext.search_reason}
                                    </span>
                                  )}
                                </div>
                                <div className="toggle-icon">
                                  {searchResultsVisible[`current-${searchData.step}-${index}`] ? '▼' : '▶'}
                                </div>
                              </div>

                              {searchResultsVisible[`current-${searchData.step}-${index}`] && (
                                <div className="search-result-list">
                                  {searchData.results.map((result, resultIndex) => (
                                    <div key={resultIndex} className="search-result-item">
                                      <div className="result-header">
                                        <span className="result-title">{result.title}</span>
                                        <span className="result-source">{result.source}</span>
                                      </div>
                                      <div className="result-preview">{result.content_preview}</div>
                                      {result.url && (
                                        <div className="result-url">
                                          <a href={result.url} target="_blank" rel="noopener noreferrer">
                                            {result.url}
                                          </a>
                                        </div>
                                      )}
                                      <div className="result-meta">
                                        <span>관련성: {((result.score || result.relevance_score || 0) * 100).toFixed(0)}%</span>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* 그 다음에 메시지 콘텐츠(보고서) 표시 */}
                      {renderMessageContent(message)}

                      {/* 출처 보기 버튼 - 완료된 메시지에만 표시 */}
                      {message.type === "assistant" && !message.isStreaming && message.fullDataDict && Object.keys(message.fullDataDict).length > 0 && (
                        <div className="message-actions">
                          <button
                            className="sources-simple-btn"
                            onClick={() => {
                              console.log(`소스 패널 토글 (메시지 ${message.id}), fullDataDict:`, Object.keys(message.fullDataDict).length, '개');
                              setFullDataDict(message.fullDataDict); // 해당 메시지의 데이터 사용
                              setSourcesData(message.fullDataDict); // 소스패널용 데이터도 설정
                              setSourcesPanelVisible(true); // 패널 열기
                            }}
                          >
                            {`${Object.keys(message.fullDataDict).length}개 출처 보기`}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {/* 스트리밍 중일 때만 상태 표시 */}
              {isStreaming && (
                <div className="streaming-status">
                  <div className="status-content">
                    <div className="pulse-dot"></div>
                    <span>{statusMessage || "처리 중..."}</span>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        <MessageInput
          query={query}
          setQuery={setQuery}
          isStreaming={isStreaming}
          selectedTeam={selectedTeam}
          availableTeams={availableTeams}
          setSelectedTeam={setSelectedTeam}
          aiAutoEnabled={aiAutoEnabled}
          setAiAutoEnabled={setAiAutoEnabled}
          teamDropupOpen={teamDropupOpen}
          setTeamDropupOpen={setTeamDropupOpen}
          textareaRef={textareaRef}
          onSubmit={handleSubmit}
          onStopGeneration={handleStopGeneration}
          onKeyPress={handleKeyPress}
          onCompositionStart={handleCompositionStart}
          onCompositionEnd={handleCompositionEnd}
          // 🆕 RunId 관련 props 추가
          canAbort={canAbort}
          streamProgress={streamProgress}
        />
      </div>

      {/* 출처 패널 */}
      <SourcesPanel
        sources={sourcesData}
        isVisible={sourcesPanelVisible}
        onToggle={toggleSourcesPanel}
        dataDict={fullDataDict} // >> 전체 데이터 딕셔너리 전달
      />

      {/* 다크 모드 토글 버튼 */}
      <button
        className="dark-mode-toggle"
        onClick={toggleDarkMode}
        title={isDarkTheme ? "라이트 모드로 전환" : "다크 모드로 전환"}
        aria-label="다크 모드 토글"
      >
        {isDarkTheme ? (
          // 달 아이콘 (다크 모드에서 표시)
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
            <path d="M21.64 13a1 1 0 0 0-1.05-.14 8.05 8.05 0 0 1-3.37.73 8.15 8.15 0 0 1-8.14-8.1 8.59 8.59 0 0 1 .25-2A1 1 0 0 0 8 2.36a10.14 10.14 0 1 0 14 11.69 1 1 0 0 0-.36-1.05zm-9.5 6.69A8.14 8.14 0 0 1 7.08 5.22v.27a10.15 10.15 0 0 0 10.14 10.14 9.79 9.79 0 0 0 2.1-.22 8.11 8.11 0 0 1-7.18 4.32z"/>
          </svg>
        ) : (
          // 해 아이콘 (라이트 모드에서 표시)
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="2"/>
            <path d="M12 2V6" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            <path d="M12 18V22" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            <path d="M4.22 4.22L6.34 6.34" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            <path d="M17.66 17.66L19.78 19.78" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            <path d="M2 12H6" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            <path d="M18 12H22" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            <path d="M4.22 19.78L6.34 17.66" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            <path d="M17.66 6.34L19.78 4.22" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        )}
      </button>
    </div>
  );
}
