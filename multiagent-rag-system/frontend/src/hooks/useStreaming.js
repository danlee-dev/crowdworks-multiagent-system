import { useState, useRef, useCallback } from 'react';

export const useStreaming = () => {
  const [isStreaming, setIsStreaming] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [currentStreamingMessage, setCurrentStreamingMessage] = useState("");
  const [currentStreamingCharts, setCurrentStreamingCharts] = useState([]);
  const eventSourceRef = useRef(null);
  const streamingAbortedRef = useRef(false);
  
  // 🆕 RunId 추적 상태
  const [activeRunId, setActiveRunId] = useState(null);
  const [canAbort, setCanAbort] = useState(false);
  const [streamProgress, setStreamProgress] = useState({ current: 0, total: 0 });
  const [savedSources, setSavedSources] = useState([]);
  const [savedCharts, setSavedCharts] = useState([]);

  const stopGeneration = useCallback(async () => {
    console.log("🛑 생성 중지 요청");
    
    // 1. RunId 기반 Abort API 호출
    if (activeRunId) {
      try {
        const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://49.50.128.6:8000";
        const response = await fetch(`${API_BASE_URL}/api/chat/abort/${activeRunId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: 'user_requested' })
        });
        
        if (response.ok) {
          console.log(`✅ Abort 요청 성공: ${activeRunId}`);
        } else {
          console.warn(`⚠️ Abort 요청 실패: ${response.status}`);
        }
      } catch (error) {
        console.error("❌ Abort API 호출 오류:", error);
      }
    }
    
    // 2. 기존 EventSource 정리
    if (eventSourceRef.current) {
      streamingAbortedRef.current = true;
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      
      setIsStreaming(false);
      setCanAbort(false);
      setStatusMessage("생성이 중지되었습니다");
      
      setTimeout(() => {
        setStatusMessage("");
      }, 2000);
      
      return true;
    }
    
    return false;
  }, [activeRunId]);

  const resetStreamingState = useCallback(() => {
    setCurrentStreamingMessage("");
    setCurrentStreamingCharts([]);
    setStatusMessage("");
    streamingAbortedRef.current = false;
    
    // 🆕 RunId 관련 상태 초기화
    setActiveRunId(null);
    setCanAbort(false);
    setStreamProgress({ current: 0, total: 0 });
    setSavedSources([]);
    setSavedCharts([]);
  }, []);

  // 🆕 새로고침 후 복구 함수
  const resumeAfterRefresh = useCallback(async (conversationId) => {
    if (!conversationId) {
      console.log("❌ resumeAfterRefresh: conversationId 없음");
      return false;
    }
    
    try {
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://49.50.128.6:8000";
      const url = `${API_BASE_URL}/api/chat/resume/${conversationId}`;
      console.log("🔍 Resume API 요청:", url);
      
      const response = await fetch(url);
      console.log("📡 Resume API 응답 상태:", response.status, response.statusText);
      
      const data = await response.json();
      console.log("📥 Resume API 응답 데이터:", data);
      
      if (data.has_active_stream) {
        console.log("✅ 활성 스트리밍 발견! 복구 시작:", data);
        
        setActiveRunId(data.run_id);
        setCanAbort(true);
        setCurrentStreamingMessage(data.current_content || "");
        setStreamProgress(data.progress || { current: 0, total: 0 });
        setSavedSources(data.sources || []);
        setSavedCharts(data.charts || []);
        
        setStatusMessage("이전 작업을 복구했습니다");
        setTimeout(() => setStatusMessage(""), 3000);
        
        console.log("🎉 스트리밍 복구 완료! runId:", data.run_id);
        return true;
      } else {
        console.log("📭 활성 스트리밍 없음:", data);
      }
      
      return false;
    } catch (error) {
      console.error("❌ 스트리밍 복구 오류:", error);
      return false;
    }
  }, []);

  // 🆕 RunId 초기화 처리
  const handleRunIdInit = useCallback((runId) => {
    console.log("🚀 새 실행 시작:", runId);
    setActiveRunId(runId);
    setCanAbort(true);
    setStreamProgress({ current: 0, total: 0 });
    setSavedSources([]);
    setSavedCharts([]);
  }, []);

  // 🆕 체크포인트 데이터 저장
  const saveCheckpointData = useCallback((type, data) => {
    if (type === 'sources') {
      setSavedSources(prev => [...prev, data]);
      // 로컬 스토리지에도 저장
      if (activeRunId) {
        localStorage.setItem(`sources_${activeRunId}`, JSON.stringify([...savedSources, data]));
      }
    } else if (type === 'chart') {
      setSavedCharts(prev => [...prev, data]);
      if (activeRunId) {
        localStorage.setItem(`charts_${activeRunId}`, JSON.stringify([...savedCharts, data]));
      }
    }
  }, [activeRunId, savedSources, savedCharts]);

  return {
    isStreaming,
    setIsStreaming,
    statusMessage,
    setStatusMessage,
    currentStreamingMessage,
    setCurrentStreamingMessage,
    currentStreamingCharts,
    setCurrentStreamingCharts,
    eventSourceRef,
    streamingAbortedRef,
    stopGeneration,
    resetStreamingState,
    
    // 🆕 RunId 관련 기능들
    activeRunId,
    setActiveRunId,
    canAbort,
    setCanAbort,
    streamProgress,
    setStreamProgress,
    savedSources,
    setSavedSources,
    savedCharts,
    setSavedCharts,
    resumeAfterRefresh,
    handleRunIdInit,
    saveCheckpointData,
  };
};