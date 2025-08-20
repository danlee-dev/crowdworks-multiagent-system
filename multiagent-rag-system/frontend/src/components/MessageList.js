import React from 'react';
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { ChartComponent } from "./ChartComponent";
import SearchResultsPanel from "./SearchResultsPanel";
import '../app/globals.css';

const MessageList = ({
  currentConversation,
  conversationSearchResults,
  searchResultsVisible,
  toggleSearchResults,
  messageStates,
  formatElapsedTime,
  renderMessageContent,
  messagesContainerRef,
  handleScroll,
  messagesEndRef,
  autoScrollEnabled,
  setAutoScrollEnabled,
  userScrolledRef,
  currentStreamingMessage,
  currentStreamingCharts,
  isStreaming,
  statusMessage,
  stopGeneration
}) => {
  return (
    <div
      className="messages-container"
      ref={messagesContainerRef}
      onScroll={handleScroll}
    >
      {currentConversation.map((message, index) => (
        <div key={index} className={`message ${message.type}`}>
          <div className="message-content">
            {message.type === "user" ? (
              <div className="user-message-wrapper">
                <div className="user-avatar">U</div>
                <div className="user-message-text">{message.content}</div>
              </div>
            ) : (
              <div className="assistant-message-wrapper">
                <div className="assistant-avatar">
                  {message.team_id ? (
                    <span className="team-badge">
                      {message.team_emoji || "🤖"} {message.team_name || message.team_id}
                    </span>
                  ) : (
                    "AI"
                  )}
                </div>
                <div className="assistant-message-content">
                  {conversationSearchResults[message.id] && conversationSearchResults[message.id].length > 0 && (
                    <SearchResultsPanel
                      searchResults={conversationSearchResults[message.id]}
                      isVisible={searchResultsVisible[message.id] || false}
                      onToggle={() => toggleSearchResults(message.id)}
                    />
                  )}

                  <div className="message-text">
                    {renderMessageContent ? renderMessageContent(message) : (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeRaw]}
                        components={{
                          a: ({ node, ...props }) => (
                            <a {...props} target="_blank" rel="noopener noreferrer" />
                          ),
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    )}
                  </div>

                  {message.charts && message.charts.length > 0 && (
                    <div className="charts-container">
                      {message.charts.map((chart, chartIndex) => (
                        <ChartComponent key={chartIndex} chartData={chart} />
                      ))}
                    </div>
                  )}

                  {messageStates[message.id] && (
                    <div className="message-status">
                      {messageStates[message.id].status === "streaming" ? (
                        <span className="status-streaming">
                          ⏳ 생성 중... ({formatElapsedTime((Date.now() - messageStates[message.id].startTime) / 1000)})
                        </span>
                      ) : messageStates[message.id].status === "completed" ? (
                        <span className="status-completed">
                          완료 ({formatElapsedTime((messageStates[message.id].endTime - messageStates[message.id].startTime) / 1000)})
                        </span>
                      ) : messageStates[message.id].status === "aborted" ? (
                        <span className="status-aborted">
                          중단됨 ({formatElapsedTime((messageStates[message.id].endTime - messageStates[message.id].startTime) / 1000)})
                        </span>
                      ) : null}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      ))}

      {isStreaming && (
        <div className="message assistant streaming">
          <div className="message-content">
            <div className="assistant-message-wrapper">
              <div className="assistant-avatar">AI</div>
              <div className="assistant-message-content">
                {currentStreamingMessage ? (
                  <>
                    <div className="message-text">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeRaw]}
                        components={{
                          a: ({ node, ...props }) => (
                            <a {...props} target="_blank" rel="noopener noreferrer" />
                          ),
                        }}
                      >
                        {currentStreamingMessage}
                      </ReactMarkdown>
                    </div>
                    {currentStreamingCharts.length > 0 && (
                      <div className="charts-container">
                        {currentStreamingCharts.map((chart, index) => (
                          <ChartComponent key={index} chartData={chart} />
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="loading-indicator">
                    <div className="loading-spinner"></div>
                    {statusMessage && (
                      <div className="status-message">{statusMessage}</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />

      {!autoScrollEnabled && (
        <button
          className="scroll-to-bottom"
          onClick={() => {
            userScrolledRef.current = false;
            setAutoScrollEnabled(true);
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
          }}
        >
          ↓ 최신 메시지로
        </button>
      )}
    </div>
  );
};

export default MessageList;
