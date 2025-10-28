import { useState, useCallback, useEffect } from 'react';
import { localStorageBackup } from '../utils/api';

export const useMessageState = () => {
  const [messageStates, setMessageStates] = useState({});
  const [statusToggleOpen, setStatusToggleOpen] = useState({});

  const initializeMessageState = useCallback((messageId) => {
    if (!messageStates[messageId]) {
      const newState = {
        status: "streaming",
        startTime: Date.now(),
        endTime: null,
        statusHistory: [],
      };

      setMessageStates(prev => ({
        ...prev,
        [messageId]: newState,
      }));

      localStorageBackup.save("messageStates", {
        ...messageStates,
        [messageId]: newState,
      });

      return newState;
    }
    return messageStates[messageId];
  }, [messageStates]);

  const addMessageStatus = useCallback((messageId, statusMessage) => {
    setMessageStates(prev => {
      const currentState = prev[messageId] || initializeMessageState(messageId);

      const updatedState = {
        ...currentState,
        statusHistory: [
          ...currentState.statusHistory,
          {
            id: Date.now() + Math.random(),
            message: statusMessage,
            timestamp: Date.now(),
          },
        ],
      };

      const newStates = {
        ...prev,
        [messageId]: updatedState,
      };

      localStorageBackup.save("messageStates", newStates);

      return newStates;
    });
  }, [initializeMessageState]);

  const completeMessageState = useCallback((messageId, wasAborted = false) => {
    setMessageStates(prev => {
      const currentState = prev[messageId];
      if (!currentState) return prev;

      const updatedState = {
        ...currentState,
        status: wasAborted ? "aborted" : "completed",
        endTime: Date.now(),
      };

      const newStates = {
        ...prev,
        [messageId]: updatedState,
      };

      localStorageBackup.save("messageStates", newStates);

      return newStates;
    });
  }, []);

  const getMessageState = useCallback((messageId) => {
    return messageStates[messageId] || null;
  }, [messageStates]);

  const formatElapsedTime = useCallback((seconds) => {
    if (seconds < 60) {
      return `${Math.floor(seconds)}초`;
    }
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}분 ${remainingSeconds}초`;
  }, []);

  // 실시간 경과 시간 업데이트 (1초마다)
  useEffect(() => {
    const interval = setInterval(() => {
      setMessageStates(prev => {
        const newStates = { ...prev };
        let hasActiveStreaming = false;

        Object.keys(newStates).forEach(messageId => {
          const state = newStates[messageId];
          if (state && state.status === "streaming" && !state.endTime) {
            hasActiveStreaming = true;
            const now = Date.now();
            const elapsedSeconds = Math.floor((now - state.startTime) / 1000);

            // statusHistory의 각 항목에 대해서도 elapsedSeconds 업데이트
            const updatedHistory = state.statusHistory.map(statusItem => ({
              ...statusItem,
              elapsedSeconds: Math.floor((statusItem.timestamp - state.startTime) / 1000)
            }));

            newStates[messageId] = {
              ...state,
              elapsedSeconds,
              statusHistory: updatedHistory
            };
          }
        });

        if (hasActiveStreaming) {
          localStorageBackup.save("messageStates", newStates);
        }

        return newStates;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const savedMessageStates = localStorageBackup.load("messageStates");
    if (savedMessageStates) {
      setMessageStates(savedMessageStates);
    }
  }, []);

  // 백엔드에서 로드한 메시지 상태를 복원하는 함수
  const restoreMessageStatesFromConversation = useCallback((messages) => {
    const restoredStates = {};

    messages.forEach(message => {
      if (message.type === "assistant") {
        // messageState가 있거나 statusHistory가 있는 경우 모두 복원
        if (message.messageState || message.statusHistory) {
          const statusHistory = message.statusHistory || message.messageState?.statusHistory || [];
          
          // startTime과 endTime 복원
          let startTime = message.messageState?.startTime;
          let endTime = message.messageState?.endTime;
          
          // startTime이 없으면 첫 번째 status의 timestamp 사용
          if (!startTime && statusHistory.length > 0) {
            startTime = statusHistory[0].timestamp;
          }
          
          // endTime이 없으면 마지막 status의 timestamp 사용
          if (!endTime && statusHistory.length > 0) {
            endTime = statusHistory[statusHistory.length - 1].timestamp;
          }
          
          // 총 소요시간 계산 (마지막 status의 elapsedSeconds 사용)
          let totalElapsedSeconds = 0;
          if (statusHistory.length > 0) {
            const lastStatus = statusHistory[statusHistory.length - 1];
            totalElapsedSeconds = lastStatus.elapsedSeconds || 0;
          }
          
          restoredStates[message.id] = {
            ...message.messageState,
            statusHistory,
            status: "completed", // 백엔드에서 로드한 것은 모두 완료된 상태
            startTime,
            endTime,
            totalElapsedSeconds // 총 소요시간 저장
          };
        }
      }
    });

    if (Object.keys(restoredStates).length > 0) {
      setMessageStates(prev => ({
        ...prev,
        ...restoredStates
      }));
      localStorageBackup.save("messageStates", {
        ...messageStates,
        ...restoredStates
      });
      console.log(`📊 메시지 상태 복원: ${Object.keys(restoredStates).length}개`);
    }
  }, [messageStates]);

  return {
    messageStates,
    statusToggleOpen,
    setStatusToggleOpen,
    initializeMessageState,
    addMessageStatus,
    completeMessageState,
    getMessageState,
    formatElapsedTime,
    restoreMessageStatesFromConversation,
  };
};
