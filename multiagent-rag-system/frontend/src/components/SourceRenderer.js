import React, { useMemo, memo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import './SourceRenderer.css';

// Memoized text part component
const TextPart = memo(({ content, hasTable, isPureSourcePattern }) => {
  if (isPureSourcePattern) {
    return <span>{content}</span>;
  }

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw]}
      components={{
        p: ({ children }) => {
          return hasTable ? <div>{children}</div> : <div style={{ display: 'inline' }}>{children}</div>;
        },
        div: ({ children }) => <div>{children}</div>,
        li: ({ children, ...props }) => (
          <li {...props}>
            <span>{children}</span>
          </li>
        ),
        table: ({ node, ...props }) => (
          <div className="table-container">
            <table {...props} />
          </div>
        ),
        img: () => null,
      }}
    >
      {content}
    </ReactMarkdown>
  );
});

TextPart.displayName = 'TextPart';

const SourceRenderer = ({ content, sources = [], isStreaming = false, dataDict = {} }) => {

  // 디버깅 정보 (개발 환경에서만)
  // if (process.env.NODE_ENV === 'development') {
  //   console.log("SourceRenderer:", {
  //     contentLength: content?.length || 0,
  //     sourcesCount: sources?.length || 0,
  //     isStreaming,
  //     dataDictSize: Object.keys(dataDict || {}).length
  //   });
  // }

  // 불완전한 SOURCE 패턴 처리 (스트리밍용)
  const handleIncompletePattern = (text) => {
    const incompletePattern = /\[SOURCE:[^\]]*$/;
    if (incompletePattern.test(text)) {
      // if (process.env.NODE_ENV === 'development') {
      //   console.log("🔄 불완전한 SOURCE 패턴 감지");
      // }
      return text.replace(incompletePattern, '');
    }
    return text;
  };

  // SOURCE 번호들을 파싱
  const parseSourceNumbers = (numbersString) => {
    return numbersString
      .split(',')
      .map(num => parseInt(num.trim()))
      .filter(num => !isNaN(num));
  };

  // 데이터 딕셔너리에서 출처 데이터 찾기
  const findSourceData = (sourceNumber) => {
    if (!dataDict) return null;

    // 숫자 키 또는 문자열 키로 시도
    const sourceData = dataDict[sourceNumber] || dataDict[String(sourceNumber)];

    if (!sourceData && sources?.length > 0) {
      // fallback: sources 배열에서 시도
      const arrayIndex = sourceNumber - 1;
      return (arrayIndex >= 0 && arrayIndex < sources.length) ? sources[arrayIndex] : null;
    }

    return sourceData;
  };

  // 텍스트에 테이블이 포함되어 있는지 확인
  const hasTable = (text) => {
    return text && text.includes('|') && text.includes('---');
  };

  // 메인 파싱 함수
  const parseContentWithSources = (text) => {
    if (!text) return [{ type: 'text', content: '' }];

    // 스트리밍 중 불완전한 패턴 처리
    if (isStreaming) {
      text = handleIncompletePattern(text);
    }

    const sourcePattern = /\[SOURCE:(\s*\d+(?:\s*,\s*\d+)*\s*)\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = sourcePattern.exec(text)) !== null) {
      // 이전 텍스트 추가
      if (match.index > lastIndex) {
        const textContent = text.slice(lastIndex, match.index);
        parts.push({
          type: 'text',
          content: textContent,
          hasTable: hasTable(textContent)
        });
      }

      // 번호들 파싱
      const sourceNumbers = parseSourceNumbers(match[1]);

      // if (process.env.NODE_ENV === 'development') {
      //   console.log(`🔍 SOURCE: "${match[0]}" → [${sourceNumbers.join(', ')}]`);
      // }

      // 각 번호에 대해 개별 버튼 생성
      sourceNumbers.forEach((sourceNumber, index) => {
        const sourceData = findSourceData(sourceNumber);

        // 버튼 생성
        parts.push({
          type: 'source',
          sourceNumber,
          sourceData,
          isLoading: !sourceData && isStreaming
        });

        // 버튼 사이 간격
        if (index < sourceNumbers.length - 1) {
          parts.push({ type: 'text', content: ' ' });
        }
      });

      lastIndex = match.index + match[0].length;
    }

    // 마지막 남은 텍스트 추가
    if (lastIndex < text.length) {
      const textContent = text.slice(lastIndex);
      parts.push({
        type: 'text',
        content: textContent,
        hasTable: hasTable(textContent)
      });
    }

    return parts;
  };

  const parts = useMemo(() => parseContentWithSources(content), [content]);

  // 순수 SOURCE 패턴만 있는지 확인 (마크다운 요소 없음)
  const isPureSourcePattern = parts.length <= 3 &&
    !content.includes('**') && !content.includes('#') && !content.includes('---') &&
    !content.includes('|') && content.trim().length < 100;

  return (
    <span className="source-renderer">
      {parts.map((part, index) => {
        if (part.type === 'text') {
          return (
            <TextPart
              key={`text-${index}`}
              content={part.content}
              hasTable={part.hasTable}
              isPureSourcePattern={isPureSourcePattern}
            />
          );
        } else if (part.type === 'source') {
          return (
            <SourceButton
              key={index}
              part={part}
              index={index}
            />
          );
        }
        return null;
      })}
    </span>
  );
};

// 개별 소스 버튼 컴포넌트 - CSS 기반 hover로 단순화
const SourceButton = memo(({ part, index }) => {
  const handleClick = useCallback(() => {
    if (part.sourceData?.url || part.sourceData?.source_url) {
      window.open(part.sourceData.url || part.sourceData.source_url, '_blank');
    }
  }, [part.sourceData?.url, part.sourceData?.source_url]);

  return (
    <span className="source-container">
      <button
        className={`source-button ${part.isLoading ? 'loading' : ''} ${!part.sourceData ? 'no-data' : ''}`}
        onClick={handleClick}
        disabled={!part.sourceData}
        title={part.isLoading ? '출처 로딩 중...' : (part.sourceData?.title || '출처 정보 없음')}
      >
        {part.sourceNumber}
      </button>

      {part.sourceData && (
        <SourceTooltip sourceData={part.sourceData} />
      )}
    </span>
  );
}, (prevProps, nextProps) => {
  // Simple comparison - only re-render if part data changes
  return (
    prevProps.part.sourceNumber === nextProps.part.sourceNumber &&
    prevProps.part.isLoading === nextProps.part.isLoading &&
    prevProps.part.sourceData === nextProps.part.sourceData
  );
});

SourceButton.displayName = 'SourceButton';

// 툴팁 컴포넌트
const SourceTooltip = memo(({ sourceData }) => {
  const getSourceTypeLabel = (sourceType) => {
    const typeMap = {
      'web_search': '웹 검색',
      'vector_db': '문서',
      'rdb_search': '데이터베이스',
      'graph_db': '그래프 DB'
    };
    return typeMap[sourceType] || sourceData.source || '출처';
  };

  const formatUrl = (url) => url?.replace(/^https?:\/\//, '');

  const truncateContent = (content) => {
    return content && content.length > 150
      ? content.substring(0, 150) + '...'
      : content;
  };

  return (
    <div className="source-tooltip">
      {/* 제목 */}
      <div style={{
        fontWeight: 'bold',
        marginBottom: '6px',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        fontSize: '13px'
      }}>
        {sourceData.title}
      </div>

      {/* URL */}
      {/* {(sourceData.url || sourceData.source_url) && (
        <div style={{
          fontSize: '10px',
          color: '#888',
          marginBottom: '8px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap'
        }}>
          {formatUrl(sourceData.url || sourceData.source_url)}
        </div>
      )} */}

      {/* 내용 */}
      {/* <div style={{
        fontSize: '11px',
        maxHeight: '80px',
        overflow: 'hidden',
        marginBottom: '8px',
        lineHeight: '1.4',
        color: '#ccc'
      }}>
        {truncateContent(sourceData.content)}
      </div> */}

      {/* 하단 정보 */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontSize: '10px',
        marginTop: '6px'
      }}>
        <span style={{ color: '#666' }}>
          {getSourceTypeLabel(sourceData.source_type)}
        </span>
        {(sourceData.url || sourceData.source_url) && (
          <a
            href={sourceData.url || sourceData.source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: '#4a9eff',
              textDecoration: 'none',
              fontSize: '10px'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            링크 열기 →
          </a>
        )}
      </div>
    </div>
  );
});

SourceTooltip.displayName = 'SourceTooltip';

export default SourceRenderer;
