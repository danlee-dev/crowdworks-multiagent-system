import { useState, useRef, useCallback, useEffect } from 'react';

export const useAutoScroll = () => {
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const userScrolledRef = useRef(false);

  const scrollToBottom = useCallback(() => {
    if (messagesEndRef.current && autoScrollEnabled && !userScrolledRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [autoScrollEnabled]);

  const handleScroll = useCallback(() => {
    if (messagesContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 100;
      
      if (!isAtBottom) {
        userScrolledRef.current = true;
        setAutoScrollEnabled(false);
      } else {
        userScrolledRef.current = false;
        setAutoScrollEnabled(true);
      }
    }
  }, []);

  const resetScroll = useCallback(() => {
    userScrolledRef.current = false;
    setAutoScrollEnabled(true);
    scrollToBottom();
  }, [scrollToBottom]);

  return {
    autoScrollEnabled,
    setAutoScrollEnabled,
    messagesEndRef,
    messagesContainerRef,
    userScrolledRef,
    scrollToBottom,
    handleScroll,
    resetScroll,
  };
};