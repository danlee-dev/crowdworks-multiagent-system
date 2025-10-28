import React from 'react';
import '../app/globals.css';

const StatusPanel = ({ 
  statusToggleOpen, 
  setStatusToggleOpen, 
  messageStates, 
  formatElapsedTime,
  // 🆕 RunId 관련 props 추가
  activeRunId,
  canAbort,
  streamProgress,
  onStopGeneration
}) => {
  const activeStreamingMessages = Object.entries(messageStates).filter(
    ([_, state]) => state.status === "streaming"
  );

  const hasActiveStreaming = activeStreamingMessages.length > 0;

  if (!hasActiveStreaming) return null;

  return (
    <div className="status-panel">
      <button
        className="status-toggle"
        onClick={() => setStatusToggleOpen(!statusToggleOpen)}
      >
        <span className="status-indicator streaming"></span>
        <span>
          처리 중...
          {/* 🆕 RunId와 진행률 표시 */}
          {activeRunId && (
            <span className="run-info"> (Run: {activeRunId.slice(-6)})</span>
          )}
          {streamProgress && streamProgress.total > 0 && (
            <span className="progress-info"> {streamProgress.current}/{streamProgress.total}</span>
          )}
        </span>
        <svg
          className={`toggle-icon ${statusToggleOpen ? "open" : ""}`}
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M3 5L6 8L9 5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {statusToggleOpen && (
        <div className="status-content">
          {activeStreamingMessages.map(([messageId, state]) => {
            const currentTime = Date.now();
            const startTime = state.startTime;
            const elapsedTime = startTime ? (currentTime - startTime) / 1000 : 0;
            const latestStatus = state.statusHistory[state.statusHistory.length - 1];
            
            // 디버깅용 로그
            console.log('StatusPanel Debug:', {
              messageId,
              currentTime,
              startTime,
              elapsedTime,
              state
            });

            return (
              <div key={messageId} className="status-item">
                <div className="status-header">
                  <span className="status-time">
                    {formatElapsedTime(elapsedTime)} 경과
                  </span>
                </div>
                {latestStatus && (
                  <div className="status-message">
                    {latestStatus.message}
                  </div>
                )}
                {state.statusHistory.length > 1 && (
                  <details className="status-history">
                    <summary>이전 상태 ({state.statusHistory.length - 1})</summary>
                    <div className="history-list">
                      {state.statusHistory.slice(0, -1).map((item, index) => (
                        <div key={index} className="history-item">
                          <span className="history-time">
                            {new Date(item.timestamp).toLocaleTimeString()}
                          </span>
                          <span className="history-message">{item.message}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            );
          })}
          
          {/* 🆕 Abort 버튼 추가 */}
          {activeRunId && (
            <div className="status-controls">
              <button
                onClick={onStopGeneration}
                className={`abort-button ${canAbort ? 'can-abort' : 'disabled'}`}
                disabled={!canAbort}
                title={canAbort ? "작업 중단" : "중단할 수 없음"}
              >
                🛑 작업 중단
              </button>
              <div className="run-id-info">
                Run ID: {activeRunId}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default StatusPanel;