import { useState, useEffect, useRef, useCallback } from 'react';

export const useWebSocket = (conversationId) => {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const heartbeatIntervalRef = useRef(null);

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://49.50.128.6:8000";
  // HTTP를 WS로, HTTPS를 WSS로 변환
  const WS_URL = API_BASE_URL.replace(/^http/, 'ws');

  // WebSocket 연결 함수
  const connect = useCallback(() => {
    if (!conversationId) {
      console.log('⚠️ WebSocket 연결 건너뜀: conversationId 없음');
      return;
    }

    // 기존 연결이 있으면 닫기
    if (wsRef.current && wsRef.current.readyState === WebSocket.CONNECTING) {
      console.log('⚠️ 기존 WebSocket 연결 중이므로 대기');
      return;
    }

    try {
      const wsUrl = `${WS_URL}/ws/${conversationId}`;
      console.log('🔌 WebSocket 연결 시도:', wsUrl);
      console.log('🔌 API_BASE_URL:', API_BASE_URL);
      console.log('🔌 WS_URL:', WS_URL);
      
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        console.log('✅ WebSocket 연결됨');
        setIsConnected(true);
        setConnectionStatus('connected');

        // 하트비트 시작
        startHeartbeat();
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          handleWebSocketMessage(message);
        } catch (error) {
          console.error('❌ WebSocket 메시지 파싱 오류:', error);
        }
      };

      wsRef.current.onclose = (event) => {
        console.log('🔌 WebSocket 연결 종료:', event.code, event.reason);
        setIsConnected(false);
        setConnectionStatus('disconnected');
        stopHeartbeat();

        // 자동 재연결 (정상 종료가 아닌 경우)
        if (event.code !== 1000) {
          scheduleReconnect();
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('❌ WebSocket 오류:', {
          error,
          url: wsUrl,
          readyState: wsRef.current?.readyState,
          conversationId
        });
        setConnectionStatus('error');
      };

    } catch (error) {
      console.error('❌ WebSocket 연결 생성 실패:', {
        error,
        message: error.message,
        wsUrl: `${WS_URL}/ws/${conversationId}`,
        API_BASE_URL,
        WS_URL
      });
      setConnectionStatus('error');
    }
  }, [conversationId, WS_URL, API_BASE_URL]);

  // WebSocket 연결 해제
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close(1000, 'normal_closure');
      wsRef.current = null;
    }
    stopHeartbeat();
    clearReconnectTimeout();
  }, []);

  // 하트비트 시작
  const startHeartbeat = useCallback(() => {
    heartbeatIntervalRef.current = setInterval(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        sendMessage({ type: 'ping' });
      }
    }, 30000); // 30초마다 ping
  }, []);

  // 하트비트 중지
  const stopHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
  }, []);

  // 재연결 스케줄링
  const scheduleReconnect = useCallback(() => {
    clearReconnectTimeout();
    setConnectionStatus('reconnecting');
    
    reconnectTimeoutRef.current = setTimeout(() => {
      console.log('🔄 WebSocket 재연결 시도');
      connect();
    }, 5000); // 5초 후 재연결 시도
  }, [connect]);

  // 재연결 타이머 정리
  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  // WebSocket 메시지 전송
  const sendMessage = useCallback((message) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
      return true;
    } else {
      console.warn('⚠️ WebSocket이 연결되지 않음, 메시지 전송 실패');
      return false;
    }
  }, []);

  // WebSocket 메시지 처리
  const handleWebSocketMessage = useCallback((message) => {
    console.log('📨 WebSocket 메시지 수신:', message);

    switch (message.type) {
      case 'status_response':
        // 상태 응답 처리
        window.dispatchEvent(new CustomEvent('websocket_status_response', {
          detail: message
        }));
        break;

      case 'abort_response':
        // 중단 응답 처리
        window.dispatchEvent(new CustomEvent('websocket_abort_response', {
          detail: message
        }));
        break;

      case 'abort_notification':
        // 다른 클라이언트의 중단 알림
        window.dispatchEvent(new CustomEvent('websocket_abort_notification', {
          detail: message
        }));
        break;

      case 'completion_notification':
        // 완료 알림
        window.dispatchEvent(new CustomEvent('websocket_completion_notification', {
          detail: message
        }));
        break;

      case 'status_update':
        // 실시간 상태 업데이트
        window.dispatchEvent(new CustomEvent('websocket_status_update', {
          detail: message
        }));
        break;

      case 'pong':
        // 하트비트 응답
        console.log('💓 WebSocket pong 수신');
        break;

      default:
        console.log('❓ 알 수 없는 WebSocket 메시지 타입:', message.type);
    }
  }, []);

  // 상태 확인 요청
  const requestStatus = useCallback((runId) => {
    return sendMessage({
      type: 'status_check',
      run_id: runId
    });
  }, [sendMessage]);

  // 중단 요청
  const requestAbort = useCallback((runId, reason = 'websocket_request') => {
    return sendMessage({
      type: 'abort_request',
      run_id: runId,
      reason: reason
    });
  }, [sendMessage]);

  // conversation ID 변경 시 재연결 (임시 비활성화)
  useEffect(() => {
    if (conversationId) {
      console.log('🔌 WebSocket 연결 비활성화됨 (백엔드 설정 확인 필요)');
      // 임시로 WebSocket 연결을 비활성화
      // const timer = setTimeout(() => {
      //   connect();
      // }, 1000);

      // return () => {
      //   clearTimeout(timer);
      //   disconnect();
      // };
    }

    return () => {
      disconnect();
    };
  }, [conversationId, connect, disconnect]);

  // 컴포넌트 언마운트 시 정리
  useEffect(() => {
    return () => {
      disconnect();
      clearReconnectTimeout();
    };
  }, [disconnect, clearReconnectTimeout]);

  return {
    isConnected,
    connectionStatus,
    sendMessage,
    requestStatus,
    requestAbort,
    connect,
    disconnect
  };
};