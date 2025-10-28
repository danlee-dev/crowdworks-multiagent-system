import { useState, useCallback, useEffect } from 'react';
import { localStorageBackup } from '../utils/api';

export const useSearchResults = () => {
  const [currentSearchResults, setCurrentSearchResults] = useState([]);
  const [searchResultsVisible, setSearchResultsVisible] = useState({});
  const [conversationSearchResults, setConversationSearchResults] = useState({});

  const setCurrentSearchResultsDebug = useCallback((newResults) => {
    console.log("📊 검색 결과 업데이트:", {
      이전_결과_수: currentSearchResults.length,
      새_결과_수: newResults.length,
      새_결과_내용: newResults,
    });
    setCurrentSearchResults(newResults);
  }, [currentSearchResults]);

  const saveSearchResults = useCallback((searchResults, visibleState) => {
    localStorageBackup.save("conversationSearchResults", searchResults);
    localStorageBackup.save("searchResultsVisible", visibleState);
  }, []);

  const toggleSearchResults = useCallback((messageId) => {
    setSearchResultsVisible(prev => {
      const newState = {
        ...prev,
        [messageId]: !prev[messageId]
      };
      localStorageBackup.save("searchResultsVisible", newState);
      return newState;
    });
  }, []);

  useEffect(() => {
    const savedSearchVisible = localStorageBackup.load("searchResultsVisible");
    if (savedSearchVisible) {
      setSearchResultsVisible(savedSearchVisible);
    }

    const savedSearchResults = localStorageBackup.load("conversationSearchResults");
    if (savedSearchResults) {
      setConversationSearchResults(savedSearchResults);
    }
  }, []);

  return {
    currentSearchResults,
    setCurrentSearchResults: setCurrentSearchResultsDebug,
    searchResultsVisible,
    setSearchResultsVisible,
    conversationSearchResults,
    setConversationSearchResults,
    saveSearchResults,
    toggleSearchResults,
  };
};