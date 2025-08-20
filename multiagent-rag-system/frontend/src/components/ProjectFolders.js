import React, { useState, useEffect } from 'react';
import { projectAPI, conversationAPI } from '../utils/api';

const ProjectFolders = ({
  projects,
  conversations,
  currentProjectId,
  onProjectSelect,
  onProjectCreate,
  onProjectUpdate,
  onProjectDelete,
  onConversationSelect,
  onConversationDelete,
  onNewConversation
}) => {
  const [isCreating, setIsCreating] = useState(false);
  const [editingProject, setEditingProject] = useState(null);
  const [newProjectTitle, setNewProjectTitle] = useState('');
  // 토글 기능 제거

  const handleCreateProject = async () => {
    if (!newProjectTitle.trim()) return;

    try {
      const projectId = `project_${Date.now()}_${Math.random().toString(36).substr(2, 8)}`;
      await onProjectCreate(newProjectTitle.trim(), '', projectId);
      setNewProjectTitle('');
      setIsCreating(false);
    } catch (error) {
      console.error('프로젝트 생성 실패:', error);
      alert('프로젝트 생성에 실패했습니다.');
    }
  };

  const handleUpdateProject = async (projectId, title) => {
    if (!title.trim()) return;

    try {
      await onProjectUpdate(projectId, title.trim());
      setEditingProject(null);
    } catch (error) {
      console.error('프로젝트 수정 실패:', error);
      alert('프로젝트 수정에 실패했습니다.');
    }
  };

  const handleDeleteProject = async (projectId) => {
    try {
      await onProjectDelete(projectId);
    } catch (error) {
      console.error('프로젝트 삭제 실패:', error);
      alert('프로젝트 삭제에 실패했습니다.');
    }
  };

  // 토글 기능 제거됨

  const getProjectConversations = (projectId) => {
    return conversations.filter(conv => conv.project_id === projectId);
  };

  const getUnassignedConversations = () => {
    console.log('🔍 모든 대화:', conversations.map(c => ({ id: c.id, title: c.title, project_id: c.project_id })));
    const unassigned = conversations.filter(conv => {
      const hasNoProjectId = !conv.project_id || conv.project_id === null || conv.project_id === undefined || conv.project_id === '';
      return hasNoProjectId;
    });
    console.log('📂 미분류 대화:', unassigned.map(c => ({ id: c.id, title: c.title, project_id: c.project_id })));
    return unassigned;
  };

  return (
    <div className="project-folders">
      <div className="project-folders-header">
        <h3>프로젝트</h3>
        <button
          className="create-project-btn"
          onClick={() => setIsCreating(true)}
          title="새 프로젝트 만들기"
        >
          +
        </button>
      </div>

      {/* 새 프로젝트 생성 폼 */}
      {isCreating && (
        <div className="project-create-form">
          <input
            type="text"
            value={newProjectTitle}
            onChange={(e) => setNewProjectTitle(e.target.value)}
            placeholder="프로젝트 이름"
            autoFocus
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                handleCreateProject();
              } else if (e.key === 'Escape') {
                setIsCreating(false);
                setNewProjectTitle('');
              }
            }}
          />
          <div className="project-create-buttons">
            <button onClick={handleCreateProject}>생성</button>
            <button onClick={() => {
              setIsCreating(false);
              setNewProjectTitle('');
            }}>취소</button>
          </div>
        </div>
      )}

      {/* 프로젝트 목록 */}
      <div className="project-list">
        {projects.map(project => {
          const projectConversations = getProjectConversations(project.id);
          const isEditing = editingProject === project.id;

          return (
            <div key={project.id} className={`project-item ${currentProjectId === project.id ? 'active' : ''}`}>
              <div className="project-header">
                <div
                  className="project-title-area"
                  onClick={() => {
                    onProjectSelect(project);
                  }}
                >
                  <span className="project-icon">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2Z"/>
                      <path d="M8 5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2H8V5Z"/>
                    </svg>
                  </span>

                  {isEditing ? (
                    <input
                      type="text"
                      className="project-edit-input"
                      defaultValue={project.title}
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') {
                          handleUpdateProject(project.id, e.target.value);
                        } else if (e.key === 'Escape') {
                          setEditingProject(null);
                        }
                      }}
                      onBlur={(e) => {
                        handleUpdateProject(project.id, e.target.value);
                      }}
                    />
                  ) : (
                    <span
                      className="project-title"
                      onDoubleClick={(e) => {
                        e.stopPropagation();
                        setEditingProject(project.id);
                      }}
                    >
                      {project.title}
                    </span>
                  )}

                  <span className="conversation-count">({projectConversations.length})</span>
                </div>

                <div className="project-actions">
                  <button
                    className="new-conversation-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onNewConversation(project.id);
                    }}
                    title="새 대화"
                  >
                    +
                  </button>
                  <button
                    className="edit-project-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingProject(project.id);
                    }}
                    title="프로젝트 이름 수정"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="m18 2 4 4-14 14H4v-4L18 2Z"/>
                    </svg>
                  </button>
                  <button
                    className="delete-project-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteProject(project.id);
                    }}
                    title="프로젝트 삭제"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="m3 6 18 0"/>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                      <line x1="10" y1="11" x2="10" y2="17"/>
                      <line x1="14" y1="11" x2="14" y2="17"/>
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {/* 미분류 대화들을 프로젝트 목록 아래에 배치 */}
        {getUnassignedConversations().length > 0 && (
          <div className="unassigned-conversations">
            <div className="unassigned-header">
              <h4>미분류 대화</h4>
            </div>
            {getUnassignedConversations().map(conversation => (
              <div
                key={conversation.id}
                className="conversation-item unassigned"
                onClick={() => onConversationSelect(conversation)}
              >
                <div className="conversation-content">
                  <span className="conversation-title">{conversation.title || "새 대화"}</span>
                  <span className="conversation-date">
                    {new Date(conversation.lastUpdated || conversation.updated_at).toLocaleDateString()}
                  </span>
                </div>
                <button
                  className="delete-conversation-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onConversationDelete && onConversationDelete(conversation.id);
                  }}
                  title="대화 삭제"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="m3 6 18 0"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    <line x1="10" y1="11" x2="10" y2="17"/>
                    <line x1="14" y1="11" x2="14" y2="17"/>
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ProjectFolders;
