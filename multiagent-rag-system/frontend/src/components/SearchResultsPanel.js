import React from 'react';
import '../app/globals.css';

const SearchResultsPanel = ({ searchResults, isVisible, onToggle }) => {
  if (!searchResults || searchResults.length === 0) return null;

  return (
    <div className="search-results-panel">
      <button className="search-results-toggle" onClick={onToggle}>
        <svg
          className={`toggle-arrow ${isVisible ? 'open' : ''}`}
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
        <span className="search-label">
          🔍 검색 중: {searchResults.length}개 소스 검토
        </span>
      </button>
      
      {isVisible && (
        <div className="search-results-content">
          {searchResults.map((result, idx) => (
            <div key={idx} className="search-result-item">
              <div className="result-header">
                <span className="result-index">{idx + 1}</span>
                <span className="result-title">{result.title || result.source || '제목 없음'}</span>
                {result.score && (
                  <span className="result-score">
                    관련도: {(result.score * 100).toFixed(1)}%
                  </span>
                )}
              </div>
              {result.snippet && (
                <div className="result-snippet">{result.snippet}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SearchResultsPanel;