import React from 'react';
import ProjectFolders from './ProjectFolders';

const ConversationSidebar = ({
  sidebarOpen,
  setSidebarOpen,
  conversations,
  conversationId,
  isStreaming,
  onNewChat,
  onLoadConversation,
  onDeleteConversation,
  titleGenerating,
  generatedTitle,
  // 프로젝트 관련 props
  projects = [],
  currentProjectId,
  onProjectSelect,
  onProjectCreate,
  onProjectUpdate,
  onProjectDelete,
  onNewConversationInProject,
  // 뷰 상태 props (외부에서 관리)
  viewMode,
  setViewMode,
  selectedProjectForView,
  setSelectedProjectForView
}) => {

  const handleProjectSelectForView = (project) => {
    setSelectedProjectForView(project);
    setViewMode('project-detail');
    if (onProjectSelect) {
      onProjectSelect(project.id);
    }
  };

  const handleBackToProjects = () => {
    setSelectedProjectForView(null);
    setViewMode('main');
  };
  return (
    <div
      className={`sidebar ${sidebarOpen ? "sidebar-open" : "sidebar-closed"}`}
    >
      <div className="sidebar-header">
        <button
          className="sidebar-toggle"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          title={sidebarOpen ? "사이드바 닫기" : "사이드바 열기"}
        >
          {sidebarOpen ? (
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <line x1="9" y1="9" x2="15" y2="15" />
              <line x1="15" y1="9" x2="9" y2="15" />
            </svg>
          ) : (
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          )}
        </button>
        {sidebarOpen && (
          <div className="sidebar-header-actions">
            {viewMode === 'project-detail' ? (
              <div className="project-detail-header">
                <div className="project-detail-left">
                  <button className="back-btn" onClick={handleBackToProjects}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="m15 18-6-6 6-6"/>
                    </svg>
                  </button>
                  <span className="project-detail-title">{selectedProjectForView?.title}</span>
                </div>
                <button 
                  className="new-chat-btn small" 
                  onClick={() => onNewConversationInProject && onNewConversationInProject(selectedProjectForView?.id)}
                  title="새 대화"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </button>
              </div>
            ) : (
              <button className="new-chat-btn" onClick={onNewChat}>
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                새 채팅
              </button>
            )}
          </div>
        )}
      </div>


      {sidebarOpen && (
        <div className="sidebar-content">
          {viewMode === 'main' ? (
            <ProjectFolders
              projects={projects}
              conversations={conversations}
              currentProjectId={currentProjectId}
              onProjectSelect={handleProjectSelectForView}
              onProjectCreate={onProjectCreate}
              onProjectUpdate={onProjectUpdate}
              onProjectDelete={onProjectDelete}
              onConversationSelect={onLoadConversation}
              onConversationDelete={onDeleteConversation}
              onNewConversation={(projectId) => onNewConversationInProject && onNewConversationInProject(projectId)}
              conversationId={conversationId}
              titleGenerating={titleGenerating}
              generatedTitle={generatedTitle}
            />
          ) : viewMode === 'project-detail' ? (
            <div className="project-conversations-view">
              {conversations
                .filter(conv => conv.project_id === selectedProjectForView?.id)
                .map((conv) => (
                  <div
                    key={conv.id}
                    className={`conversation-item ${
                      conversationId === conv.id ? "active" : ""
                    }`}
                    onClick={() => {
                      console.log('프로젝트 상세 뷰에서 대화 클릭:', conv);
                      onLoadConversation(conv);
                    }}
                  >
                    <div className="conversation-content">
                      <div className="conversation-title">
                        {conv.id === conversationId && titleGenerating && (!conv.title || conv.title === "") ? (
                          <>
                            {generatedTitle}
                            <span className="typing-cursor">|</span>
                          </>
                        ) : (
                          conv.title || "새 대화"
                        )}
                      </div>
                      <div className="conversation-date">
                        {new Date(conv.lastUpdated || conv.updated_at).toLocaleDateString("ko-KR")}
                      </div>
                    </div>
                    <button
                      className="delete-conversation"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteConversation(conv.id);
                      }}
                      title="대화 삭제"
                    >
                      <svg
                        width="12"
                        height="12"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <path d="m3 6 18 0"/>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                        <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        <line x1="10" y1="11" x2="10" y2="17"/>
                        <line x1="14" y1="11" x2="14" y2="17"/>
                      </svg>
                    </button>
                  </div>
                ))
              }
              {conversations.filter(conv => conv.project_id === selectedProjectForView?.id).length === 0 && (
                <div className="no-conversations">
                  <p>이 프로젝트에 대화가 없습니다</p>
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
};

export default ConversationSidebar;