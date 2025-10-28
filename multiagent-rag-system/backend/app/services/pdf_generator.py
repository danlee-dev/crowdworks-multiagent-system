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
        references: List[Dict] = None,
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
            
            # 3. 출처 섹션 생성 (기존)
            sources_html = self._generate_sources_section(sources)
            
            # 4. 참고문헌 섹션 생성 (새로 추가)
            references_html = self._generate_references_section(references or [])
            
            # 5. 전체 HTML 문서 구성
            full_html = self._create_full_html(title, html_content, sources_html, references_html)
            
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
                        <h4 class="chart-title">{chart_title}</h4>
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
                            <h4 class="chart-title">{chart_title}</h4>
                            <span class="chart-type-badge">{chart_type.upper()}</span>
                        </div>
                        <div class="chart-description">
                            {description}
                        </div>
                        <div class="chart-note">
                            <small>Interactive charts are available in the web version</small>
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
    
    def _generate_references_section(self, references: List[Dict]) -> str:
        """참고문헌 섹션 HTML 생성 (fullDataDict 기반)"""
        if not references:
            return ""
        
        references_html = """
        <div class="page-break references-section">
            <h1>참고문헌</h1>
        """
        
        # 참고문헌을 번호순으로 정렬
        sorted_refs = sorted(references, key=lambda x: x.get('number', 0))
        
        for ref in sorted_refs:
            number = ref.get('number', '?')
            title = ref.get('title', 'Unknown Title')
            content = ref.get('content', '')
            url = ref.get('url', '')
            source_type = ref.get('source_type', '출처')
            search_query = ref.get('search_query', '')
            
            # 내용 요약 (첫 200자)
            summary = content[:200] + "..." if len(content) > 200 else content
            
            references_html += f"""
            <div class="reference-item" id="ref-{number}">
                <div class="reference-number">[{number}]</div>
                <div class="reference-content">
                    <div class="reference-title">{title}</div>
                    <div class="reference-type">유형: {source_type}</div>
            """
            
            if url:
                references_html += f"""<div class="reference-url"><a href="{url}" target="_blank">{url}</a></div>"""
            if search_query:
                references_html += f"""<div class="reference-query">검색어: {search_query}</div>"""
            if summary:
                references_html += f"""<div class="reference-summary">{summary}</div>"""
                
            references_html += """
                </div>
            </div>
            """
        
        references_html += "</div>"
        return references_html
    
    def _create_full_html(self, title: str, content: str, sources: str, references: str = "") -> str:
        """전체 HTML 문서 생성"""
        current_time = datetime.now().strftime("%Y년 %m월 %d일")
        current_date_en = datetime.now().strftime("%Y-%m-%d")
        
        return f"""
        <!DOCTYPE html>
        <html lang="ko">
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
                <!-- 상단 헤더 -->
                <div class="cover-top">
                    <div class="report-type">AI Analysis Report</div>
                    <div class="report-date">{current_date_en}</div>
                </div>
                
                <!-- 브랜딩 섹션 -->
                <div class="cover-brand">
                    <div class="brand-line"></div>
                    <div class="brand-text">CrowdWorks AI Platform</div>
                </div>
                
                <!-- 메인 제목 -->
                <h1 class="cover-title">{title}</h1>
                
                <!-- 하단 구분선 -->
                <div class="cover-bottom-line"></div>
                
                <!-- 하단 발행 정보 -->
                <div class="cover-footer">
                    <div class="publisher-info">
                        <div class="publisher-label">발행처</div>
                        <div class="publisher-name">CROWDWORKS</div>
                        <div class="publisher-date">{current_time}</div>
                    </div>
                </div>
            </div>
            
            <!-- Main Content -->
            <div class="main-content">
                {content}
            </div>
            
            <!-- Sources -->
            {sources}
            
            <!-- References (fullDataDict 기반) -->
            {references}
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
            font-family: 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.6;
            color: #2d3748;
            margin: 0;
            padding: 0;
            background-color: #ffffff;
            letter-spacing: -0.02em;
        }
        
        /* 표지 스타일 */
        .cover-page {
            page-break-after: always;
            height: 100vh;
            background: #ffffff;
            padding: 2.5cm 3cm;
            box-sizing: border-box;
            position: relative;
        }
        
        /* 상단 헤더 라인 */
        .cover-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 3em;
            font-size: 0.9em;
            color: #666;
        }
        
        .report-type {
            font-weight: 400;
        }
        
        .report-date {
            font-weight: 400;
        }
        
        /* 브랜딩 섹션 */
        .cover-brand {
            margin-bottom: 2.5em;
        }
        
        .brand-line {
            width: 100%;
            height: 3px;
            background-color: #10b981;
            margin-bottom: 0.8em;
        }
        
        .brand-text {
            font-size: 0.95em;
            color: #666;
            font-weight: 400;
            letter-spacing: -0.02em;
        }
        
        /* 메인 제목 */
        .cover-title {
            font-size: 2.8em;
            font-weight: 700;
            line-height: 1.3;
            color: #2d3748;
            margin: 2em 0;
            letter-spacing: -0.6px;
            text-align: left;
        }
        
        /* 하단 구분선 */
        .cover-bottom-line {
            width: 100%;
            height: 2px;
            background-color: #10b981;
            margin: 2em 0 1em 0;
        }
        
        /* 하단 정보 섹션 */
        .cover-footer {
            position: absolute;
            bottom: 3.2cm;
            left: 3cm;
            right: 3cm;
            display: flex;
            justify-content: flex-start;
            align-items: flex-start;
        }
        
        .publisher-info {
            text-align: left;
            line-height: 1.4;
        }
        
        .publisher-label {
            font-size: 0.85em;
            color: #10b981;
            font-weight: 600;
            margin-bottom: 0.4em;
            display: block;
        }
        
        .publisher-name {
            font-size: 0.95em;
            color: #2d3748;
            font-weight: 600;
            display: block;
            margin-bottom: 0.3em;
        }
        
        .publisher-date {
            font-size: 0.85em;
            color: #666;
            display: block;
            white-space: nowrap;
        }
        
        /* 본문 스타일 */
        .main-content {
            margin-top: 2em;
            padding: 0 1em;
        }
        
        h1, h2, h3, h4, h5, h6 {
            color: #2d3748;
            margin-top: 2.5em;
            margin-bottom: 1.2em;
            font-weight: 700;
            letter-spacing: -0.04em;
            font-family: 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
        }
        
        h1 { 
            font-size: 1.8em; 
            border-bottom: 3px solid #10b981; 
            padding-bottom: 0.8em;
            margin-top: 2em;
            color: #1a202c;
            font-weight: 800;
        }
        h2 { 
            font-size: 1.5em; 
            border-bottom: 2px solid #e2e8f0; 
            padding-bottom: 0.5em;
            color: #2d3748;
            margin-top: 2.2em;
            position: relative;
        }
        h2::before {
            content: '';
            position: absolute;
            left: 0;
            bottom: -2px;
            width: 60px;
            height: 2px;
            background-color: #10b981;
        }
        h3 { 
            font-size: 1.25em; 
            color: #4a5568;
            margin-top: 2em;
            font-weight: 650;
        }
        h4 { 
            font-size: 1em; 
            color: #6b7280;
            margin-top: 1.2em;
        }
        
        /* 문단 스타일 */
        p {
            margin: 1.2em 0;
            text-align: justify;
            orphans: 2;
            widows: 2;
            line-height: 1.6;
            letter-spacing: -0.01em;
            color: #374151;
            word-spacing: 0.05em;
            font-size: 10pt;
        }
        
        /* 표 스타일 */
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 2em 0;
            font-size: 10pt;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            border-radius: 8px;
            overflow: hidden;
            background-color: #ffffff;
        }
        
        th, td {
            border: none;
            padding: 14px 16px;
            text-align: left;
            vertical-align: top;
            border-bottom: 1px solid #e2e8f0;
            line-height: 1.6;
        }
        
        th {
            background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
            font-weight: 700;
            color: #2d3748;
            font-size: 10.5pt;
            letter-spacing: -0.02em;
            border-bottom: 2px solid #cbd5e0;
        }
        
        tr:nth-child(even) td {
            background-color: #f8fafc;
        }
        
        tr:last-child td {
            border-bottom: none;
        }
        
        /* 리스트 스타일 */
        ul, ol {
            margin: 1.5em 0;
            padding-left: 2.5em;
            line-height: 1.7;
        }
        
        li {
            margin: 0.8em 0;
            color: #374151;
            line-height: 1.7;
        }
        
        ul li {
            list-style-type: none;
            position: relative;
        }
        
        ul li::before {
            content: '•';
            color: #10b981;
            font-weight: bold;
            position: absolute;
            left: -1.5em;
            font-size: 1.2em;
        }
        
        ol li {
            padding-left: 0.5em;
        }
        
        /* 구분선 숨김 (제목의 border-bottom과 중복 방지) */
        hr {
            display: none;
        }
        
        /* 인용 블록 */
        blockquote {
            border-left: 5px solid #10b981;
            margin: 2em 0;
            padding: 1.5em 2em;
            background: linear-gradient(135deg, #f0fdf4 0%, #f7fee7 100%);
            font-style: italic;
            border-radius: 0 8px 8px 0;
            box-shadow: 0 2px 4px rgba(16, 185, 129, 0.1);
            color: #374151;
            font-size: 10.5pt;
            line-height: 1.8;
            position: relative;
        }
        
        blockquote::before {
            content: '"';
            font-size: 3em;
            color: #10b981;
            opacity: 0.3;
            position: absolute;
            top: -0.2em;
            left: 0.3em;
            font-family: Georgia, serif;
        }
        
        /* 코드 블록 */
        code {
            background-color: #f1f5f9;
            padding: 3px 6px;
            border-radius: 4px;
            font-family: 'JetBrains Mono', 'Fira Code', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 9.5pt;
            color: #e53e3e;
            border: 1px solid #e2e8f0;
            letter-spacing: 0;
        }
        
        pre {
            background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
            padding: 1.5em;
            border-radius: 8px;
            overflow-x: auto;
            margin: 2em 0;
            border-left: 4px solid #10b981;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border: 1px solid #e2e8f0;
        }
        
        pre code {
            background: none;
            padding: 0;
            font-size: 9pt;
            color: #2d3748;
            border: none;
            line-height: 1.6;
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
        
        /* 참고문헌 스타일 */
        .references-section {
            margin-top: 2em;
        }
        
        .references-section h1 {
            color: #1f2937;
            border-bottom: 2px solid #10b981;
            padding-bottom: 0.5em;
            margin-bottom: 1.5em;
        }
        
        .reference-item {
            display: flex;
            margin-bottom: 1.5em;
            padding-bottom: 1em;
            border-bottom: 1px solid #f3f4f6;
            page-break-inside: avoid;
        }
        
        .reference-number {
            color: #10b981;
            font-weight: 600;
            margin-right: 1em;
            flex-shrink: 0;
            font-size: 1em;
        }
        
        .reference-content {
            flex: 1;
        }
        
        .reference-title {
            font-weight: 600;
            color: #1f2937;
            font-size: 1.05em;
            margin-bottom: 0.5em;
        }
        
        .reference-type {
            font-size: 0.9em;
            color: #6b7280;
            margin: 0.2em 0;
        }
        
        .reference-query {
            font-size: 0.9em;
            color: #6b7280;
            margin: 0.2em 0;
            font-style: italic;
        }
        
        .reference-url {
            margin: 0.3em 0;
        }
        
        .reference-url a {
            color: #10b981;
            text-decoration: none;
            word-break: break-all;
            font-size: 0.9em;
        }
        
        .reference-url a:hover {
            text-decoration: underline;
        }
        
        .reference-summary {
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