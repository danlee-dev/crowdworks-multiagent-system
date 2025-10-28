import { conversationAPI } from '../utils/api';

export const useStreamingEvents = ({
  conversationId,
  setConversationId,
  setStatusMessage,
  addMessageStatus,
  setFullDataDict,
  setSourcesData,
  setCurrentConversation,
  setConversationSearchResults,
  setCurrentSearchResults,
  setSearchResultsVisible,
  setSectionDataDicts,
  completeMessageState,
  getMessageState,
  setIsStreaming,
  conversations,
  saveConversations,
  fullDataDict,
  sectionDataDicts,
  // 🆕 RunId 관련 props 추가
  handleRunIdInit,
  saveCheckpointData,
  setStreamProgress,
  setCanAbort
}) => {

  const generateChartId = (chartData) => {
    let sampleData = "";
    if (chartData.data) {
      if (Array.isArray(chartData.data)) {
        sampleData = JSON.stringify(chartData.data.slice(0, 2));
      } else {
        sampleData = JSON.stringify(chartData.data);
      }
    }

    const chartKey = JSON.stringify({
      type: chartData.type || "",
      title: chartData.title || "",
      data_sample: sampleData,
    });

    return chartKey;
  };

  const handleStreamingEvent = async (data, assistantMessage, finalContent, finalCharts, processedChartIds, currentQuery) => {
    switch (data.type) {
      // 🆕 새로운 이벤트 타입들
      case "init":
        if (data.run_id) {
          console.log("🚀 RunId 초기화:", data.run_id);
          handleRunIdInit(data.run_id);
        }
        break;

      case "abort":
        console.log("🛑 스트리밍 중단됨:", data.run_id);
        setStatusMessage(data.message || "작업이 중단되었습니다");
        setCanAbort(false);
        setIsStreaming(false);
        break;

      case "status":
        const statusMessage = data.data?.message || data.message || "처리 중...";
        setStatusMessage(statusMessage);
        addMessageStatus(assistantMessage.id, statusMessage);
        
        // 진행률 업데이트
        if (data.step && data.total) {
          setStreamProgress({ current: data.step, total: data.total });
        }
        break;

      case "full_data_dict":
        const dataDict = data.data_dict;
        if (dataDict) {
          setFullDataDict(dataDict);
          setSourcesData(dataDict);
          
          setCurrentConversation((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessage.id
                ? { 
                    ...msg, 
                    fullDataDict: dataDict,
                    // 🔑 핵심: 소스 데이터도 메시지 객체에 설정
                    sources: dataDict
                  }
                : msg
            )
          );
        }
        break;

      case "chart":
        if (data.chart_data) {
          finalCharts.push(data.chart_data);
          
          // 🆕 차트 체크포인트 저장
          saveCheckpointData('chart', data.chart_data);
          
          setCurrentConversation((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessage.id
                ? { ...msg, charts: [...finalCharts] }
                : msg
            )
          );
        }
        break;

      case "search_results":
        const searchResultData = {
          step: data.step,
          tool_name: data.tool_name || "unknown",
          query: data.query || "",
          results: data.results,
          timestamp: new Date().toISOString(),
          conversationId: conversationId || data.session_id || Date.now().toString(),
          messageId: data.message_id || assistantMessage.id,
          isIntermediateSearch: data.is_intermediate_search || false,
          sectionContext: data.section_context || null
        };

        // 🆕 검색 결과 체크포인트 저장
        saveCheckpointData('sources', {
          tool_name: data.tool_name,
          query: data.query,
          results: data.results
        });

        const currentConvId = conversationId || data.session_id || Date.now().toString();

        setConversationSearchResults(prev => {
          const newResults = {
            ...prev,
            [currentConvId]: [...(prev[currentConvId] || []), searchResultData]
          };
          localStorage.setItem("conversationSearchResults", JSON.stringify(newResults));
          return newResults;
        });

        setCurrentSearchResults(prev => {
          const newResults = [...prev, searchResultData];
          localStorage.setItem("currentSearchResults", JSON.stringify(newResults));

          setCurrentConversation(prevMessages => {
            return prevMessages.map(msg => {
              if (msg.id === assistantMessage.id && msg.type === "assistant") {
                const messageSearchResults = newResults.filter(result => {
                  const resultMsgId = String(result.messageId);
                  const assistantMsgId = String(assistantMessage.id);
                  return resultMsgId === assistantMsgId;
                });
                return {
                  ...msg,
                  searchResults: messageSearchResults
                };
              }
              return msg;
            });
          });

          return newResults;
        });
        break;

      case "section_mapping":
        const sectionKey = `${conversationId || data.session_id || Date.now()}-${data.section_title}`;
        setSectionDataDicts(prev => ({
          ...prev,
          [sectionKey]: {
            dataDict: data.section_data_dict,
            indexes: data.section_indexes,
            title: data.section_title
          }
        }));
        break;

      case "content":
        finalContent.current += data.chunk;
        setCurrentConversation((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessage.id
              ? { ...msg, content: finalContent.current, isStreaming: true }
              : msg
          )
        );
        break;

      case "complete":
      case "final_complete":
        setStatusMessage("");
        setCanAbort(false); // 🆕 완료 시 중단 불가
        completeMessageState(assistantMessage.id);

        setCurrentConversation((prevConversation) => {
          const newConversation = prevConversation.map((msg) => {
            if (msg.id === assistantMessage.id) {
              const messageState = getMessageState(assistantMessage.id);
              
              return {
                ...msg,
                charts: finalCharts,
                isStreaming: false,
                fullDataDict: msg.fullDataDict || fullDataDict,
                sectionDataDicts: sectionDataDicts,
                messageState: messageState,
                // 🔑 핵심: statusHistory를 메시지 객체에 직접 설정
                statusHistory: messageState?.statusHistory || [],
                // 🔑 핵심: sources 데이터 유지 (이미 설정된 경우)
                sources: msg.sources || fullDataDict
              };
            }
            return msg;
          });

          // 제목 자동 생성 및 대화 저장
          const handleTitleAndSave = async () => {
            let generatedTitle = currentQuery.slice(0, 30) + (currentQuery.length > 30 ? "..." : "");
            
            try {
              const titleResponse = await conversationAPI.generateTitle(currentQuery);
              if (titleResponse && titleResponse.title) {
                generatedTitle = titleResponse.title;
              }
            } catch (error) {
              console.warn("제목 자동 생성 실패, 기본 제목 사용:", error);
            }

            // 기존 대화 정보 가져오기
            const existingConversation = conversations.find(c => c.id === conversationId);
            
            const conversationData = {
              id: conversationId || Date.now().toString(),
              title: generatedTitle,
              messages: newConversation,
              lastUpdated: new Date().toISOString(),
              // 기존 project_id 유지 (없으면 null 또는 undefined)
              project_id: existingConversation?.project_id !== undefined 
                ? existingConversation.project_id 
                : null,
            };

            const updatedConversations = conversations.filter((c) => c.id !== conversationData.id);
            updatedConversations.unshift(conversationData);
            saveConversations(updatedConversations.slice(0, 50));
          };

          handleTitleAndSave();
          localStorage.removeItem('currentStreamingConversation');
          return newConversation;
        });

        setIsStreaming(false);
        break;

      case "error":
        setStatusMessage(`오류: ${data.message}`);
        setCanAbort(false); // 🆕 에러 시 중단 불가
        setIsStreaming(false);
        localStorage.removeItem('currentStreamingConversation');
        break;

      default:
        break;
    }

    if (data.session_id && !conversationId) {
      setConversationId(data.session_id);
    }
  };

  return { handleStreamingEvent, generateChartId };
};