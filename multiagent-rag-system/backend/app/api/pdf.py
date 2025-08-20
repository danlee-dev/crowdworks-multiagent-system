from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import traceback

from ..services.pdf_generator import PDFGenerator

router = APIRouter()

class PDFRequest(BaseModel):
    content: str
    charts: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    title: str = "Analysis Report"
    preview: bool = False

@router.post("/generate")
async def generate_pdf(request: PDFRequest):
    """
    보고서 PDF 생성 또는 미리보기
    
    Args:
        request: PDF 생성 요청 데이터
        
    Returns:
        PDF 파일 (application/pdf) 또는 HTML 미리보기 (text/html)
    """
    try:
        generator = PDFGenerator()
        
        # PDF 또는 HTML 생성
        result = generator.generate_pdf(
            content=request.content,
            charts=request.charts,
            sources=request.sources,
            title=request.title,
            preview_mode=request.preview
        )
        
        if request.preview:
            # HTML 미리보기 반환
            return Response(
                content=result,
                media_type="text/html",
                headers={
                    "Content-Disposition": "inline; filename=preview.html"
                }
            )
        else:
            # PDF 파일 반환 - 한글 파일명 URL 인코딩 처리
            import urllib.parse
            encoded_filename = urllib.parse.quote(f"{request.title}.pdf", safe='')
            return Response(
                content=result,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                }
            )
            
    except Exception as e:
        print(f"PDF 생성 오류: {e}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"PDF 생성 중 오류가 발생했습니다: {str(e)}"
        )

@router.get("/test")
async def test_pdf():
    """PDF 생성 기능 테스트"""
    test_content = """# Test Report

## Overview
This is a PDF generation test.

## Data Analysis
Main results [SOURCE:1]:

| Item | Value |
|------|-------|
| Revenue | 100M |
| Customers | 1000 |

[CHART-PLACEHOLDER-0]
"""
    
    test_sources = [
        {
            "title": "Sales Database",
            "url": "https://example.com/sales",
            "content": "Sales data analysis results",
            "source": "rdb_search"
        }
    ]
    
    test_charts = [
        {
            "type": "bar",
            "title": "Monthly Sales",
            "data": {"labels": ["Jan", "Feb", "Mar"], "datasets": []}
        }
    ]
    
    try:
        generator = PDFGenerator()
        pdf_bytes = generator.generate_pdf(
            content=test_content,
            charts=test_charts,
            sources=test_sources,
            title="Test Report"
        )
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=test_report.pdf"
            }
        )
        
    except Exception as e:
        import traceback
        return JSONResponse(
            status_code=500,
            content={"error": f"Test failed: {str(e)}", "traceback": traceback.format_exc()}
        )