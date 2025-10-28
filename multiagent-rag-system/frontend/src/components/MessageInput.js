import React from 'react';

const MessageInput = ({
  query,
  setQuery,
  isStreaming,
  selectedTeam,
  availableTeams,
  setSelectedTeam,
  aiAutoEnabled,
  setAiAutoEnabled,
  teamDropupOpen,
  setTeamDropupOpen,
  textareaRef,
  onSubmit,
  onStopGeneration,
  onKeyPress,
  onCompositionStart,
  onCompositionEnd,
  // 🆕 RunId 관련 props
  canAbort,
  streamProgress
}) => {
  return (
    <div className="input-area">
      <div className="input-container">
        <div className="textarea-container">
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyPress}
            onCompositionStart={onCompositionStart}
            onCompositionEnd={onCompositionEnd}
            placeholder={isStreaming ? "답변 생성 중... (미리 다음 질문을 입력해보세요)" : "메시지 보내기..."}
            className="message-input"
            rows={1}
          />
          {isStreaming ? (
            <div className="streaming-controls">
              {/* 🆕 진행률 표시 */}
              {streamProgress && streamProgress.total > 0 && (
                <div className="progress-indicator" title={`${streamProgress.current}/${streamProgress.total} 단계`}>
                  <span className="progress-text">{streamProgress.current}/{streamProgress.total}</span>
                </div>
              )}
              
              <button
                onClick={onStopGeneration}
                className={`stop-button ${canAbort ? 'can-abort' : 'disabled'}`}
                disabled={!canAbort}
                title={canAbort ? "생성 중단" : "중단할 수 없음"}
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
              </button>
            </div>
          ) : (
            <button
              onClick={onSubmit}
              disabled={!query.trim()}
              className="send-button"
              title="메시지 전송"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22,2 15,22 11,13 2,9 22,2" />
              </svg>
            </button>
          )}
        </div>

        {/* AI 자동 선택 및 담당자 선택 - 통합된 드롭다운 */}
        <div className="input-controls">
          <div className="team-selector-container">
            <button
              className={`team-selector-button ${isStreaming ? 'disabled' : ''}`}
              onClick={() => {
                if (isStreaming) return;
                setTeamDropupOpen(!teamDropupOpen);
              }}
              disabled={isStreaming}
              title={isStreaming ? "보고서 생성 중에는 변경할 수 없습니다" : "AI 모드 및 담당자 선택"}
            >
              <div className="team-selector-content">
                {aiAutoEnabled ? (
                  <span className="team-selector-tag ai-auto">AI 자동</span>
                ) : selectedTeam && selectedTeam.id !== "AI_AUTO" ? (
                  <span className="team-selector-tag persona">{selectedTeam.name}</span>
                ) : (
                  <span className="team-selector-tag none">담당자 미선택</span>
                )}
                <svg className="dropup-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="18,15 12,9 6,15" />
                </svg>
              </div>
            </button>

            {/* 드롭업 메뉴 */}
            {teamDropupOpen && !isStreaming && (
              <div className="team-dropup-menu">
                {availableTeams.map((team, index) => (
                  <button
                    key={team.id}
                    className={`team-dropup-item ${
                      team.id === 'AI_AUTO' ? (aiAutoEnabled ? 'active' : '') :
                      (selectedTeam?.id === team.id ? 'active' : '')
                    }`}
                    onClick={() => {
                      if (team.id === 'AI_AUTO') {
                        setAiAutoEnabled(true);
                        setSelectedTeam(team);
                      } else {
                        setAiAutoEnabled(false);
                        setSelectedTeam(team);
                      }
                      setTeamDropupOpen(false);
                      console.log("드롭업에서 팀 선택:", team.name);
                    }}
                    style={{
                      animationDelay: `${index * 50}ms`
                    }}
                  >
                    <div className="team-dropup-content">
                      <span className="team-dropup-name">{team.name}</span>
                      {team.description && (
                        <span className="team-dropup-desc">{team.description}</span>
                      )}
                    </div>
                    {((team.id === 'AI_AUTO' && aiAutoEnabled) || (team.id !== 'AI_AUTO' && selectedTeam?.id === team.id)) && (
                      <svg className="team-dropup-check" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="20,6 9,17 4,12" />
                      </svg>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default MessageInput;
