export const formatElapsedTime = (seconds) => {
  if (seconds < 60) {
    return `${Math.floor(seconds)}초`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes}분 ${remainingSeconds}초`;
};

export const generateChartId = (chartData) => {
  const dataString = JSON.stringify(chartData.data);
  let hash = 0;
  for (let i = 0; i < dataString.length; i++) {
    const char = dataString.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return `chart_${Math.abs(hash)}_${Date.now()}`;
};

export const generateMessageId = () => {
  return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
};

export const generateConversationId = () => {
  return `chat_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
};