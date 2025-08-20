import os
import re
import base64
from datetime import datetime
from typing import Dict, List, Any, Optional
from io import BytesIO
import markdown
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration


class PDFGenerator:
    """보고서를 PDF로 변환하는 서비스"""
    
    def __init__(self):
        self.font_config = FontConfiguration()
        
    def generate_pdf(
        self, 
        content: str, 
        charts: List[Dict], 
        sources: List[Dict], 
        title: str = "분석 보고서",
        preview_mode: bool = False
    ) -> bytes:
        """
        마크다운 보고서를 PDF로 변환
        
        Args:
            content: 마크다운 형식의 보고서 내용
            charts: 차트 데이터 목록
            sources: 출처 데이터 목록
            title: 보고서 제목
            preview_mode: True면 HTML 반환, False면 PDF 반환
            
        Returns:
            PDF 바이트 데이터 또는 HTML 문자열
        """
        try:
            # 1. 마크다운을 HTML로 변환
            html_content = self._markdown_to_html(content)
            
            # 2. 차트 처리 (이미지로 변환 또는 플레이스홀더)
            html_content = self._process_charts(html_content, charts)
            
            # 3. 출처 섹션 생성
            sources_html = self._generate_sources_section(sources)
            
            # 4. 전체 HTML 문서 구성
            full_html = self._create_full_html(title, html_content, sources_html)
            
            if preview_mode:
                return full_html.encode('utf-8')
            
            # 5. HTML을 PDF로 변환
            pdf_bytes = self._html_to_pdf(full_html)
            return pdf_bytes
            
        except Exception as e:
            print(f"PDF 생성 오류: {e}")
            raise
    
    def _markdown_to_html(self, content: str) -> str:
        """마크다운을 HTML로 변환"""
        # SOURCE 패턴 처리 (마크다운 변환 전에)
        content = self._process_source_patterns(content)
        
        # 마크다운 → HTML 변환
        md = markdown.Markdown(extensions=[
            'tables',
            'fenced_code',
            'nl2br',
            'toc'
        ])
        html = md.convert(content)
        
        return html
    
    def _process_source_patterns(self, content: str) -> str:
        """SOURCE 패턴을 각주 링크로 변환"""
        def replace_source(match):
            numbers = match.group(1)
            # 여러 번호 처리 (예: "1, 3, 5")
            nums = [n.strip() for n in numbers.split(',')]
            links = []
            for num in nums:
                if num.isdigit():
                    links.append(f'<sup><a href="#ref-{num}">[{num}]</a></sup>')
            return ''.join(links)
        
        # [SOURCE:1,2,3] → <sup><a href="#ref-1">[1]</a></sup><sup><a href="#ref-2">[2]</a></sup>
        pattern = r'\[SOURCE:([0-9,\s]+)\]'
        content = re.sub(pattern, replace_source, content)
        
        return content
    
    def _process_charts(self, html: str, charts: List[Dict]) -> str:
        """차트 플레이스홀더를 실제 이미지 또는 개선된 설명으로 교체"""
        def replace_chart(match):
            chart_index = int(match.group(1))
            if chart_index < len(charts):
                chart = charts[chart_index]
                chart_type = chart.get('type', 'unknown')
                chart_title = chart.get('title', f'Chart {chart_index + 1}')
                
                # base64 이미지가 있는 경우 사용
                if 'image' in chart and chart['image']:
                    image_data = chart['image']
                    if not image_data.startswith('data:image'):
                        image_data = f"data:image/png;base64,{image_data}"
                    
                    return f"""
                    <div class="chart-container">
                        <h4 class="chart-title">📊 {chart_title}</h4>
                        <img src="{image_data}" alt="{chart_title}" class="chart-image" />
                    </div>
                    """
                else:
                    # 이미지가 없는 경우 개선된 플레이스홀더
                    chart_data = chart.get('data', {})
                    description = self._generate_chart_description(chart_type, chart_data)
                    
                    return f"""
                    <div class="chart-placeholder-modern">
                        <div class="chart-header">
                            <h4 class="chart-title">📊 {chart_title}</h4>
                            <span class="chart-type-badge">{chart_type.upper()}</span>
                        </div>
                        <div class="chart-description">
                            {description}
                        </div>
                        <div class="chart-note">
                            <small>💡 Interactive charts are available in the web version</small>
                        </div>
                    </div>
                    """
            return match.group(0)
        
        # [CHART-PLACEHOLDER-0] 패턴 찾아서 교체
        pattern = r'\[CHART-PLACEHOLDER-(\d+)\]'
        html = re.sub(pattern, replace_chart, html)
        
        return html
    
    def _generate_chart_description(self, chart_type: str, chart_data: Dict) -> str:
        """차트 데이터를 기반으로 설명 생성"""
        if not chart_data:
            return "<p>차트 데이터가 없습니다.</p>"
        
        labels = chart_data.get('labels', [])
        datasets = chart_data.get('datasets', [])
        
        if not labels or not datasets:
            return "<p>차트 데이터를 표시할 수 없습니다.</p>"
        
        description = f"<p><strong>데이터 범주:</strong> {', '.join(labels[:5])}"
        if len(labels) > 5:
            description += f" 외 {len(labels) - 5}개"
        description += "</p>"
        
        if datasets:
            description += "<p><strong>데이터 시리즈:</strong></p><ul>"
            for dataset in datasets[:3]:  # 최대 3개 시리즈만 표시
                label = dataset.get('label', 'Unknown')
                data = dataset.get('data', [])
                if data:
                    avg_value = sum(data) / len(data) if isinstance(data[0], (int, float)) else 'N/A'
                    description += f"<li>{label}: 평균값 {avg_value:.2f}" if avg_value != 'N/A' else f"<li>{label}"
                    description += "</li>"
            description += "</ul>"
        
        return description
    
    def _generate_sources_section(self, sources: List[Dict]) -> str:
        """출처 섹션 HTML 생성"""
        if not sources:
            return ""
        
        sources_html = """
        <div class="page-break sources-section">
            <h1>참고문헌</h1>
        """
        
        # 출처 타입별로 분류
        source_by_type = {}
        for i, source in enumerate(sources):
            source_type = source.get('source', source.get('type', 'unknown'))
            if source_type not in source_by_type:
                source_by_type[source_type] = []
            source_by_type[source_type].append((i + 1, source))
        
        # 타입별로 출력
        type_names = {
            'web_search': '웹 검색 자료',
            'vector_db': '문서 데이터베이스',
            'rdb_search': '관계형 데이터베이스',
            'graph_db': '그래프 데이터베이스',
            'elasticsearch': 'Elasticsearch',
            'neo4j': 'Neo4j 그래프 DB'
        }
        
        for source_type, source_list in source_by_type.items():
            type_name = type_names.get(source_type, source_type)
            sources_html += f"""<h2 class="source-type-header">{type_name}</h2>"""
            sources_html += """<div class="source-list">"""
            
            for index, source in source_list:
                title = source.get('title', source.get('name', '제목 없음'))
                url = source.get('url') or source.get('source_url', '')
                content = source.get('content', source.get('snippet', ''))
                metadata = source.get('metadata', {})
                score = source.get('score')
                
                # 메타데이터에서 추가 정보 추출
                author = metadata.get('author', '')
                date = metadata.get('date', metadata.get('created_at', ''))
                
                # 내용 요약 (첫 300자)
                summary = content[:300] + "..." if len(content) > 300 else content
                
                sources_html += f"""
                <div class="source-item" id="ref-{index}">
                    <div class="source-number">[{index}]</div>
                    <div class="source-content">
                        <div class="source-title">{title}</div>
                """
                
                if author:
                    sources_html += f"""<div class="source-author">저자: {author}</div>"""
                if date:
                    sources_html += f"""<div class="source-date">날짜: {date}</div>"""
                if url:
                    sources_html += f"""<div class="source-url"><a href="{url}" target="_blank">{url}</a></div>"""
                if score:
                    sources_html += f"""<div class="source-score">관련도: {score:.2f}</div>"""
                if summary:
                    sources_html += f"""<div class="source-summary">{summary}</div>"""
                    
                sources_html += """
                    </div>
                </div>
                """
            
            sources_html += "</div>\n"
        
        sources_html += "</div>"
        return sources_html
    
    def _create_full_html(self, title: str, content: str, sources: str) -> str:
        """전체 HTML 문서 생성"""
        current_time = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
        
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                {self._get_pdf_styles()}
            </style>
        </head>
        <body>
            <!-- Cover Page -->
            <div class="cover-page">
                <div class="cover-content">
                    <h1 class="cover-title">{title}</h1>
                    <div class="cover-info">
                        <div class="cover-meta">
                            <p><strong>생성자:</strong> CrowdWorks</p>
                            <p><strong>생성 일시:</strong> {current_time}</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Main Content -->
            <div class="main-content">
                {content}
            </div>
            
            <!-- Sources -->
            {sources}
        </body>
        </html>
        """
    
    def _get_pdf_styles(self) -> str:
        """PDF 스타일시트"""
        return """
        @page {
            margin: 1.5cm;
            @bottom-center {
                content: counter(page);
                font-size: 9pt;
                color: #888;
            }
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.5;
            color: #2c3e50;
            margin: 0;
            padding: 0;
        }
        
        /* 표지 스타일 */
        .cover-page {
            page-break-after: always;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: left;
            background: white;
            color: #1f2937;
            padding: 3cm;
        }
        
        .cover-content {
            width: 100%;
            max-width: 600px;
        }
        
        .cover-title {
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 3em;
            letter-spacing: -0.5px;
            line-height: 1.3;
            color: #111827;
            border-bottom: 3px solid #10b981;
            padding-bottom: 1em;
        }
        
        .cover-info {
            margin-top: 4em;
        }
        
        .cover-meta p {
            font-size: 1.1em;
            margin: 0.8em 0;
            color: #4b5563;
            line-height: 1.6;
        }
        
        .cover-meta strong {
            color: #1f2937;
            font-weight: 600;
            display: inline-block;
            min-width: 120px;
        }
        
        /* 본문 스타일 */
        .main-content {
            margin-top: 1.5em;
        }
        
        h1, h2, h3, h4, h5, h6 {
            color: #1f2937;
            margin-top: 2em;
            margin-bottom: 0.8em;
            font-weight: 600;
            letter-spacing: -0.25px;
        }
        
        h1 { 
            font-size: 1.6em; 
            border-bottom: 2px solid #10b981; 
            padding-bottom: 0.5em;
            margin-top: 1.5em;
        }
        h2 { 
            font-size: 1.3em; 
            border-bottom: 1px solid #e5e7eb; 
            padding-bottom: 0.3em;
            color: #374151;
        }
        h3 { 
            font-size: 1.1em; 
            color: #4b5563;
            margin-top: 1.5em;
        }
        h4 { 
            font-size: 1em; 
            color: #6b7280;
            margin-top: 1.2em;
        }
        
        /* 표 스타일 */
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 1.5em 0;
            font-size: 9pt;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            border-radius: 6px;
            overflow: hidden;
        }
        
        th, td {
            border: none;
            padding: 10px 12px;
            text-align: left;
            vertical-align: top;
            border-bottom: 1px solid #f3f4f6;
        }
        
        th {
            background-color: #f9fafb;
            font-weight: 600;
            color: #374151;
            font-size: 9pt;
        }
        
        tr:nth-child(even) td {
            background-color: #fafafa;
        }
        
        tr:hover td {
            background-color: #f3f4f6;
        }
        
        /* 리스트 스타일 */
        ul, ol {
            margin: 1em 0;
            padding-left: 2em;
        }
        
        li {
            margin: 0.3em 0;
        }
        
        /* 인용 블록 */
        blockquote {
            border-left: 4px solid #3498db;
            margin: 1em 0;
            padding: 0.5em 1em;
            background-color: #f8f9fa;
            font-style: italic;
        }
        
        /* 코드 블록 */
        code {
            background-color: #f1f1f1;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }
        
        pre {
            background-color: #f8f8f8;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 1em;
            overflow-x: auto;
            font-size: 0.9em;
        }
        
        /* 차트 컨테이너 */
        .chart-container {
            margin: 2em 0;
            text-align: center;
            page-break-inside: avoid;
        }
        
        .chart-image {
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            margin: 1em 0;
        }
        
        .chart-title {
            color: #374151;
            font-size: 1.1em;
            margin-bottom: 1em;
            font-weight: 600;
        }
        
        /* 현대적인 차트 플레이스홀더 */
        .chart-placeholder-modern {
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 1.5em;
            margin: 2em 0;
            background: #f9fafb;
            page-break-inside: avoid;
        }
        
        .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1em;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 0.5em;
        }
        
        .chart-type-badge {
            background: #10b981;
            color: white;
            padding: 0.3em 0.6em;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: 500;
        }
        
        .chart-description {
            color: #4b5563;
            line-height: 1.6;
            margin-bottom: 1em;
        }
        
        .chart-description ul {
            margin: 0.5em 0;
            padding-left: 1.5em;
        }
        
        .chart-description li {
            margin: 0.3em 0;
        }
        
        .chart-note {
            background: #fef3c7;
            border: 1px solid #f59e0b;
            border-radius: 6px;
            padding: 0.8em;
            text-align: center;
            color: #92400e;
        }
        
        /* 각주 링크 */
        sup a {
            color: #10b981;
            text-decoration: none;
            font-weight: bold;
        }
        
        sup a:hover {
            text-decoration: underline;
        }
        
        /* 페이지 나누기 */
        .page-break {
            page-break-before: always;
        }
        
        /* 출처 섹션 */
        .sources-section {
            page-break-before: always;
            margin-top: 2em;
        }
        
        .sources-section h1 {
            font-size: 1.8em;
            color: #1f2937;
            border-bottom: 3px solid #10b981;
            padding-bottom: 0.5em;
            margin-bottom: 1.5em;
        }
        
        .source-type-header {
            font-size: 1.3em;
            color: #374151;
            margin-top: 2em;
            margin-bottom: 1em;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 0.3em;
        }
        
        .source-list {
            margin-bottom: 2em;
        }
        
        .source-item {
            display: flex;
            margin: 1.2em 0;
            padding: 1em;
            background-color: #f9fafb;
            border-radius: 8px;
            border-left: 3px solid #10b981;
        }
        
        .source-number {
            font-weight: 600;
            color: #10b981;
            margin-right: 1em;
            min-width: 30px;
        }
        
        .source-content {
            flex: 1;
        }
        
        .source-title {
            font-weight: 600;
            color: #1f2937;
            font-size: 1.05em;
            margin-bottom: 0.5em;
        }
        
        .source-author,
        .source-date,
        .source-score {
            font-size: 0.9em;
            color: #6b7280;
            margin: 0.2em 0;
        }
        
        .source-url {
            margin: 0.3em 0;
        }
        
        .source-url a {
            color: #10b981;
            text-decoration: none;
            word-break: break-all;
            font-size: 0.9em;
        }
        
        .source-url a:hover {
            text-decoration: underline;
        }
        
        .source-summary {
            margin-top: 0.8em;
            padding-top: 0.8em;
            border-top: 1px solid #e5e7eb;
            color: #4b5563;
            font-size: 0.95em;
            line-height: 1.6;
        }
        """
    
    def _html_to_pdf(self, html: str) -> bytes:
        """HTML을 PDF로 변환"""
        # WeasyPrint로 PDF 생성
        pdf_buffer = BytesIO()
        
        html_doc = HTML(string=html)
        css = CSS(string=self._get_pdf_styles())
        
        html_doc.write_pdf(
            pdf_buffer,
            stylesheets=[css],
            font_config=self.font_config
        )
        
        pdf_buffer.seek(0)
        return pdf_buffer.read()