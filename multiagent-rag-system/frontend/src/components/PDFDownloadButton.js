import React, { useState } from 'react';
import './PDFDownloadButton.css';

const PDFDownloadButton = ({ 
  content, 
  charts = [], 
  sources = [], 
  title = "분석 보고서",
  messageId 
}) => {
  // sources가 배열이 아닌 경우 처리
  const processedSources = React.useMemo(() => {
    if (Array.isArray(sources)) {
      return sources;
    } else if (sources && typeof sources === 'object') {
      // sources가 {sources: [...]} 형태인 경우
      if (Array.isArray(sources.sources)) {
        return sources.sources;
      }
      // sources가 단일 객체인 경우
      return [sources];
    }
    return [];
  }, [sources]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [previewContent, setPreviewContent] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages] = useState(1); // PDF 미리보기는 HTML이므로 1페이지로 처리

  const handleDownloadPDF = async () => {
    setIsGenerating(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://49.50.128.6:8000";
      const response = await fetch(`${apiUrl}/api/pdf/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content,
          charts,
          sources: processedSources,
          title,
          preview: false
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // PDF 파일 다운로드
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `${title}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
    } catch (error) {
      console.error('PDF 다운로드 실패:', error);
      alert('PDF 다운로드 중 오류가 발생했습니다.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handlePreview = async () => {
    setIsGenerating(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://49.50.128.6:8000";
      
      // 실제 PDF를 생성하되 미리보기용으로 처리
      const response = await fetch(`${apiUrl}/api/pdf/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content,
          charts,
          sources: processedSources,
          title,
          preview: false  // 실제 PDF 생성
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // PDF를 blob으로 받아서 object URL 생성
      const blob = await response.blob();
      const pdfUrl = window.URL.createObjectURL(blob);
      
      // iframe에서 PDF를 직접 표시
      setPreviewContent(pdfUrl);
      setShowPreview(true);
      
    } catch (error) {
      console.error('PDF 미리보기 실패:', error);
      alert('PDF 미리보기 중 오류가 발생했습니다.');
    } finally {
      setIsGenerating(false);
    }
  };

  const closePreview = () => {
    // Object URL 정리
    if (previewContent && previewContent.startsWith('blob:')) {
      window.URL.revokeObjectURL(previewContent);
    }
    setShowPreview(false);
    setPreviewContent('');
    setCurrentPage(1);
  };

  const goToNextPage = () => {
    if (currentPage < totalPages) {
      setCurrentPage(prev => prev + 1);
    }
  };

  const goToPrevPage = () => {
    if (currentPage > 1) {
      setCurrentPage(prev => prev - 1);
    }
  };

  return (
    <>
      <div className="pdf-download-container">
        <div className="pdf-buttons">
          <button 
            className="pdf-preview-btn"
            onClick={handlePreview}
            disabled={isGenerating}
            title="PDF 미리보기"
          >
            {isGenerating ? (
              <span className="loading-spinner"></span>
            ) : null}
            미리보기
          </button>
          
          <button 
            className="pdf-download-btn"
            onClick={handleDownloadPDF}
            disabled={isGenerating}
            title="PDF 다운로드"
          >
            {isGenerating ? (
              <span className="loading-spinner"></span>
            ) : null}
            PDF 다운로드
          </button>
        </div>
      </div>

      {/* PDF 미리보기 모달 */}
      {showPreview && (
        <div className="pdf-preview-modal">
          <div className="pdf-preview-content">
            <div className="pdf-preview-header">
              <h3>PDF 미리보기</h3>
              <div className="page-navigation">
                <button 
                  className="page-nav-btn" 
                  onClick={goToPrevPage}
                  disabled={currentPage <= 1}
                >
                  ◀
                </button>
                <span className="page-info">
                  {currentPage} / {totalPages}
                </span>
                <button 
                  className="page-nav-btn" 
                  onClick={goToNextPage}
                  disabled={currentPage >= totalPages}
                >
                  ▶
                </button>
              </div>
              <button className="close-preview" onClick={closePreview}>
                ×
              </button>
            </div>
            <div className="pdf-preview-body">
              {previewContent && (
                <iframe
                  src={previewContent.startsWith('blob:') ? previewContent : undefined}
                  srcDoc={!previewContent.startsWith('blob:') ? previewContent : undefined}
                  width="100%"
                  height="100%"
                  style={{border: 'none', background: 'white'}}
                  title="PDF 미리보기"
                />
              )}
            </div>
            <div className="pdf-preview-footer">
              <button className="download-from-preview" onClick={handleDownloadPDF}>
                PDF 다운로드
              </button>
              <button className="close-preview-btn" onClick={closePreview}>
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default PDFDownloadButton;