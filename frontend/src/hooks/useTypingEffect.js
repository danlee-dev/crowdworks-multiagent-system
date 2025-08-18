import { useState, useEffect, useRef } from 'react';

export const useTypingEffect = (finalText, isActive, speed = 20) => {
  const [displayText, setDisplayText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const timeoutRef = useRef(null);

  useEffect(() => {
    if (!isActive) {
      // 스트리밍이 아닐 때는 전체 텍스트 즉시 표시
      setDisplayText(finalText || '');
      setIsTyping(false);
      return;
    }

    if (!finalText) {
      setDisplayText('');
      setIsTyping(false);
      return;
    }

    // 새로운 텍스트가 더 길어졌을 때만 타이핑 이펙트 적용
    setDisplayText(prev => {
      if (finalText.length > prev.length) {
        setIsTyping(true);
        
        const currentLength = prev.length;
        const targetLength = finalText.length;
        let currentIndex = currentLength;

        const typeNextChar = () => {
          if (currentIndex < targetLength) {
            setDisplayText(finalText.slice(0, currentIndex + 1));
            currentIndex++;
            timeoutRef.current = setTimeout(typeNextChar, speed);
          } else {
            setIsTyping(false);
          }
        };

        // 즉시 첫 글자부터 타이핑 시작
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
        }
        typeNextChar();
        
        return prev; // 현재는 변경하지 않음, typeNextChar에서 업데이트
      } else {
        // 텍스트가 줄어들거나 같으면 즉시 업데이트
        setIsTyping(false);
        return finalText;
      }
    });

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [finalText, isActive, speed]); // displayText.length 제거

  // 컴포넌트 언마운트 시 정리
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return { displayText, isTyping };
};