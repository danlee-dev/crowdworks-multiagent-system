import { useState, useRef, useCallback } from 'react';

export const useStreaming = () => {
  const [isStreaming, setIsStreaming] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [currentStreamingMessage, setCurrentStreamingMessage] = useState("");
  const [currentStreamingCharts, setCurrentStreamingCharts] = useState([]);
  const eventSourceRef = useRef(null);
  const streamingAbortedRef = useRef(false);

  const stopGeneration = useCallback(() => {
    console.log("🛑 생성 중지 요청");
    
    if (eventSourceRef.current) {
      streamingAbortedRef.current = true;
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      
      setIsStreaming(false);
      setStatusMessage("생성이 중지되었습니다");
      
      setTimeout(() => {
        setStatusMessage("");
      }, 2000);
      
      return true;
    }
    
    return false;
  }, []);

  const resetStreamingState = useCallback(() => {
    setCurrentStreamingMessage("");
    setCurrentStreamingCharts([]);
    setStatusMessage("");
    streamingAbortedRef.current = false;
  }, []);

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
  };
};