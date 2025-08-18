import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { useTypingEffect } from '../hooks/useTypingEffect';
import SourceRenderer from './SourceRenderer';
import { ChartComponent } from './ChartComponent';

// SOURCE 패턴을 React 컴포넌트로 변환하는 함수
const renderSourcesInText = (text, sources, dataDict) => {
  if (!text || !text.includes('[SOURCE:')) {
    return text;
  }
  
  const parts = [];
  const sourcePattern = /\[SOURCE:(\s*\d+(?:\s*,\s*\d+)*\s*)\]/g;
  let lastIndex = 0;
  let match;

  while ((match = sourcePattern.exec(text)) !== null) {
    // 이전 텍스트 추가 (마크다운 렌더링 유지)
    if (match.index > lastIndex) {
      const textPart = text.slice(lastIndex, match.index);
      parts.push(
        <ReactMarkdown
          key={`text-${lastIndex}`}
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          components={{
            p: ({ children }) => <span>{children}</span>,
            strong: ({ children }) => <strong>{children}</strong>,
            em: ({ children }) => <em>{children}</em>,
            code: ({ children }) => <code>{children}</code>,
            img: () => null,
          }}
        >
          {textPart}
        </ReactMarkdown>
      );
    }
    
    // SOURCE 컴포넌트 추가
    parts.push(
      <SourceRenderer
        key={`inline-source-${match.index}`}
        content={match[0]}
        sources={sources}
        isStreaming={false}
        dataDict={dataDict}
      />
    );
    
    lastIndex = match.index + match[0].length;
  }
  
  // 마지막 남은 텍스트 추가 (마크다운 렌더링 유지)
  if (lastIndex < text.length) {
    const textPart = text.slice(lastIndex);
    parts.push(
      <ReactMarkdown
        key={`text-${lastIndex}`}
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          p: ({ children }) => <span>{children}</span>,
          strong: ({ children }) => <strong>{children}</strong>,
          em: ({ children }) => <em>{children}</em>,
          code: ({ children }) => <code>{children}</code>,
          img: () => null,
        }}
      >
        {textPart}
      </ReactMarkdown>
    );
  }
  
  // 모든 부분을 하나의 인라인 컨테이너로 래핑
  return <span style={{ display: 'inline' }}>{parts}</span>;
};

const MessageContent = ({
  message,
  isStreaming,
  fullDataDict,
  sourcesData
}) => {
  const content = message.content || "";
  const charts = message.charts || [];
  const sectionHeaders = message.sectionHeaders || [];

  // 타이핑 이펙트 적용 (스트리밍 중인 메시지만) - 항상 최상위에서 호출
  const { displayText, isTyping } = useTypingEffect(
    content,
    message.isStreaming && isStreaming,
    0.1 // 타이핑 속도 (ms)
  );

  // 중단된 메시지 처리
  if (message.wasAborted) {
    return (
      <div className="message-content">
        {message.content && (
          <SourceRenderer
            content={message.content}
            sources={[]}
            isStreaming={false}
            dataDict={{}}
          />
        )}
        <div className="generation-stopped">
          <div className="stopped-icon"></div>
          <div className="stopped-content">
            <div className="stopped-title">생성이 중단되었습니다</div>
            <div className="stopped-subtitle">사용자 요청에 의해 응답 생성이 중단되었습니다</div>
          </div>
        </div>
      </div>
    );
  }

  // 전역 상태 우선 사용
  const messageFullDataDict = fullDataDict || message.fullDataDict || {};

  // 실시간 출처 데이터 우선 사용
  let sources = [];
  if (message.sources) {
    if (Array.isArray(message.sources)) {
      sources = message.sources;
    } else if (message.sources.sources && Array.isArray(message.sources.sources)) {
      sources = message.sources.sources;
    }
  } else if (message.isStreaming && sourcesData && sourcesData.sources) {
    sources = sourcesData.sources;
  }

  const headerElements = sectionHeaders.map((header) => (
    <div key={header.id} className="section-header">
      <h2 className="section-title">{header.title}</h2>
    </div>
  ));

  const parts = displayText.split(/(\[CHART-PLACEHOLDER-\d+\])/g);

  const contentElements = parts.map((part, index) => {
    const match = part.match(/\[CHART-PLACEHOLDER-(\d+)\]/);
    if (match) {
      const chartIndex = parseInt(match[1], 10);
      const chartConfig = charts[chartIndex];
      if (chartConfig) {
        const chartKey = `chart-${chartIndex}-${chartConfig.type}-${
          chartConfig.title || "untitled"
        }-${index}`;
        return (
          <div key={chartKey} className="message-chart">
            <ChartComponent chartConfig={chartConfig} />
          </div>
        );
      } else {
        return (
          <div
            key={`chart-loading-${chartIndex}-${index}`}
            className="chart-loading"
          >
            <div className="chart-skeleton">
              <div className="skeleton-title"></div>
              <div className="skeleton-body"></div>
            </div>
            <span className="chart-loading-text">차트 생성 중...</span>
          </div>
        );
      }
    }

    // 테이블이 포함된 경우 SOURCE 패턴과 함께 처리
    const hasTable = part.includes('|') && part.includes('---');
    
    if (part.includes('[SOURCE:') && !hasTable) {
      // 테이블이 없는 경우만 SourceRenderer 사용
      return (
        <SourceRenderer
          key={`source-${index}`}
          content={part}
          sources={sources}
          isStreaming={message.isStreaming}
          dataDict={messageFullDataDict}
        />
      );
    }

    // 일반 마크다운 렌더링 (테이블 + SOURCE 패턴 포함)
    const cleanPart = part;
    if (cleanPart.trim()) {
      return (
        <ReactMarkdown
          key={`md-${index}`}
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          components={{
            table: ({ ...props }) => (
              <div className="table-container">
                <table {...props} />
              </div>
            ),
            // 테이블 셀 내 텍스트에서 SOURCE 패턴 처리
            td: ({ children, ...props }) => {
              const processedChildren = React.Children.map(children, (child) => {
                if (typeof child === 'string') {
                  return renderSourcesInText(child, sources, messageFullDataDict);
                }
                return child;
              });
              return <td {...props}>{processedChildren}</td>;
            },
            // 리스트 아이템 내 텍스트에서 SOURCE 패턴 처리 (간단 처리)
            li: ({ children, ...props }) => {
              const processedChildren = React.Children.map(children, (child) => {
                if (typeof child === 'string') {
                  // 리스트에서는 ReactMarkdown 이중 처리 방지를 위해 SourceRenderer만 사용
                  const parts = [];
                  const sourcePattern = /\[SOURCE:(\s*\d+(?:\s*,\s*\d+)*\s*)\]/g;
                  let lastIndex = 0;
                  let match;

                  while ((match = sourcePattern.exec(child)) !== null) {
                    // 이전 텍스트 추가 (마크다운 없이 순수 텍스트)
                    if (match.index > lastIndex) {
                      parts.push(child.slice(lastIndex, match.index));
                    }
                    
                    // SOURCE 컴포넌트 추가
                    parts.push(
                      <SourceRenderer
                        key={`li-source-${match.index}`}
                        content={match[0]}
                        sources={sources}
                        isStreaming={false}
                        dataDict={messageFullDataDict}
                      />
                    );
                    
                    lastIndex = match.index + match[0].length;
                  }
                  
                  // 마지막 남은 텍스트 추가
                  if (lastIndex < child.length) {
                    parts.push(child.slice(lastIndex));
                  }
                  
                  return parts.length > 1 ? <span style={{ display: 'inline' }}>{parts}</span> : child;
                }
                return child;
              });
              return <li {...props}>{processedChildren}</li>;
            },
            // 일반 문단에서 SOURCE 패턴 처리
            p: ({ children, ...props }) => {
              const processedChildren = React.Children.map(children, (child) => {
                if (typeof child === 'string') {
                  return renderSourcesInText(child, sources, messageFullDataDict);
                }
                return child;
              });
              // div로 변경하되 인라인 유지 (HTML nesting violation 방지 + 줄바꿈 방지)
              return <div {...props} style={{ display: 'inline', marginBottom: '1em', lineHeight: '1.6' }}>{processedChildren}</div>;
            },
            img: () => null,
          }}
        >
          {cleanPart}
        </ReactMarkdown>
      );
    }
    return null;
  }).filter(Boolean);

  return (
    <div className="message-content-wrapper">
      {headerElements}
      {contentElements}
      {isTyping && (
        <span className="typing-cursor">|</span>
      )}
    </div>
  );
};

export default MessageContent;
