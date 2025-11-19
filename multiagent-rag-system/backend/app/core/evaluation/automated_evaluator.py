"""
자동화된 보고서 평가기
Automated Report Evaluator

자동으로 계산 가능한 메트릭들을 측정합니다.
"""

import re
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.evaluation.evaluation_models import (
    TaskSuccessMetrics,
    TaskSuccessLevel,
    CompletenessMetrics,
    EfficiencyMetrics,
    SourceQualityMetrics,
    ContentMetrics,
)
from app.core.models.models import StreamingAgentState, SearchResult


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """
    간단한 비용 계산 함수

    Args:
        model_name: 모델 이름
        input_tokens: 입력 토큰 수
        output_tokens: 출력 토큰 수

    Returns:
        estimated_cost: 예상 비용 (USD)
    """
    # 모델별 가격 (per 1M tokens)
    pricing = {
        "gemini-2.5-flash": {"input": 0.075, "output": 0.30},  # $0.075 / $0.30 per 1M tokens
        "gemini-2.0-flash-exp": {"input": 0.0, "output": 0.0},  # Free tier
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.150, "output": 0.600},
    }

    # 기본값
    default_pricing = {"input": 1.0, "output": 3.0}

    # 모델 이름에서 키 추출
    model_key = model_name.lower()
    for key in pricing.keys():
        if key in model_key:
            model_key = key
            break

    price = pricing.get(model_key, default_pricing)

    # 비용 계산
    input_cost = (input_tokens / 1_000_000) * price["input"]
    output_cost = (output_tokens / 1_000_000) * price["output"]

    return input_cost + output_cost


class AutomatedEvaluator:
    """자동화된 평가 수행 클래스"""

    def __init__(self):
        """초기화"""
        # 의미론적 유사도 계산을 위한 임베딩 모델
        # 경량 모델 사용 (multilingual 지원)
        try:
            self.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            self.use_semantic_similarity = True
        except Exception as e:
            print(f"⚠️  임베딩 모델 로드 실패: {e}")
            print("   문자열 매칭으로 대체합니다.")
            self.embedding_model = None
            self.use_semantic_similarity = False

    def evaluate_task_success(
        self,
        state: Dict[str, Any],
        expected_requirements: Optional[List[str]] = None
    ) -> TaskSuccessMetrics:
        """
        작업 성공률 평가 (자동)

        Args:
            state: StreamingAgentState
            expected_requirements: 기대 요구사항 리스트
        """
        final_answer = state.get('final_answer', '')
        execution_log = state.get('execution_log', [])

        # 기본 완성 여부 확인
        is_completed = bool(final_answer and len(final_answer) > 100)

        # 요구사항 검증
        missing_requirements = []
        if expected_requirements:
            for req in expected_requirements:
                if req.lower() not in final_answer.lower():
                    missing_requirements.append(req)

        # 완성도 계산
        if expected_requirements:
            completion_percentage = (
                (len(expected_requirements) - len(missing_requirements))
                / len(expected_requirements) * 100
            )
        else:
            # 요구사항이 없으면 기본 체크
            completion_percentage = 100.0 if is_completed else 0.0

        # 성공 수준 결정
        if completion_percentage >= 90:
            success_level = TaskSuccessLevel.COMPLETE_SUCCESS
        elif completion_percentage >= 50:
            success_level = TaskSuccessLevel.PARTIAL_SUCCESS
        else:
            success_level = TaskSuccessLevel.FAILURE

        success_rate = completion_percentage / 100.0

        reasoning = f"보고서 생성 완료. {len(execution_log)}개 단계 실행."
        if missing_requirements:
            reasoning += f" 누락된 요구사항: {len(missing_requirements)}개"

        return TaskSuccessMetrics(
            success_level=success_level,
            success_rate=success_rate,
            completion_percentage=completion_percentage,
            is_task_completed=is_completed,
            missing_requirements=missing_requirements,
            reasoning=reasoning
        )

    def evaluate_completeness(
        self,
        report_text: str,
        required_sections: Optional[List[str]] = None,
        expected_schema: Optional[Dict[str, Any]] = None,
        team_type: str = "general"
    ) -> CompletenessMetrics:
        """
        완성도 평가 (자동) - 개선된 버전

        Args:
            report_text: 보고서 텍스트
            required_sections: 필수 섹션 리스트 (예: ["요약", "분석", "결론"])
            expected_schema: 기대 스키마 (필드명과 타입)
            team_type: 팀 타입 (스키마 자동 추출용)
        """
        # 마크다운 헤더로 섹션 개수 확인 (자동 생성 보고서용)
        markdown_headers = re.findall(r'^#+\s+.+$', report_text, re.MULTILINE)
        total_sections_found = len(markdown_headers)

        missing_sections = []
        incomplete_sections = []

        if required_sections is None:
            # 섹션 이름 검증 없이 개수만 확인
            # 최소 3개, 최적 6개 섹션 기준
            min_sections = 3
            optimal_sections = 6

            if total_sections_found >= optimal_sections:
                completeness_rate = 1.0
            elif total_sections_found >= min_sections:
                completeness_rate = total_sections_found / optimal_sections
            else:
                completeness_rate = total_sections_found / min_sections * 0.5

            completed_sections = total_sections_found
            total_required = optimal_sections
        else:
            # 특정 섹션 검증 (사용자 지정 시)
            completed_sections = 0
            for section in required_sections:
                section_pattern = re.compile(
                    rf'#+\s*{re.escape(section)}|^{re.escape(section)}$',
                    re.IGNORECASE | re.MULTILINE
                )

                if section_pattern.search(report_text):
                    completed_sections += 1
                    section_content = self._extract_section_content(report_text, section)
                    if len(section_content) < 50:
                        incomplete_sections.append(section)
                else:
                    missing_sections.append(section)

            total_required = len(required_sections)
            completeness_rate = completed_sections / total_required if total_required > 0 else 0.0

        # 스키마 완성도 확인 (개선된 로직)
        schema_fields_filled = 0
        total_schema_fields = 0
        schema_completeness_rate = 1.0

        if expected_schema:
            # 사용자 제공 스키마 사용
            total_schema_fields = len(expected_schema)
            for field_name in expected_schema.keys():
                if field_name.lower() in report_text.lower():
                    schema_fields_filled += 1

            schema_completeness_rate = (
                schema_fields_filled / total_schema_fields
                if total_schema_fields > 0 else 0.0
            )
        else:
            # 팀 타입별 자동 스키마 추출 및 검증
            extracted_schema = self.extract_schema_from_report(report_text, team_type)
            total_schema_fields = len(extracted_schema)
            schema_fields_filled = sum(1 for v in extracted_schema.values() if v)

            schema_completeness_rate = (
                schema_fields_filled / total_schema_fields
                if total_schema_fields > 0 else 0.0
            )

        reasoning = f"{completed_sections}/{total_required} 섹션 완료"
        if schema_fields_filled > 0:
            reasoning += f", 스키마 {schema_fields_filled}/{total_schema_fields} 필드 완성"
        if missing_sections:
            reasoning += f", 누락: {', '.join(missing_sections[:3])}"
        if incomplete_sections:
            reasoning += f", 불완전: {', '.join(incomplete_sections[:3])}"

        return CompletenessMetrics(
            required_sections_completed=completed_sections,
            total_required_sections=total_required,
            completeness_rate=completeness_rate,
            missing_sections=missing_sections,
            incomplete_sections=incomplete_sections,
            schema_fields_filled=schema_fields_filled,
            total_schema_fields=total_schema_fields,
            schema_completeness_rate=schema_completeness_rate,
            reasoning=reasoning
        )

    def evaluate_efficiency(
        self,
        state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        model_name: str = "gemini-2.5-flash"
    ) -> EfficiencyMetrics:
        """
        효율성 평가 (자동) - 개선된 버전

        Args:
            state: StreamingAgentState
            metadata: 메타데이터 (실행 시간, 토큰 사용량 등)
            model_name: 사용된 모델 이름 (비용 계산용)
        """
        # 실행 시간 계산
        start_time_str = state.get('start_time', '')
        execution_log = state.get('execution_log', [])
        step_results = state.get('step_results', [])

        total_execution_time = 0.0
        if metadata and 'total_execution_time' in metadata:
            total_execution_time = metadata['total_execution_time']
        elif start_time_str:
            try:
                start_time = datetime.fromisoformat(start_time_str)
                total_execution_time = (datetime.now() - start_time).total_seconds()
            except:
                total_execution_time = 0.0

        # Planning JSON에서 실제 단계 수 추출
        planned_steps, step_descriptions = self.extract_plan_steps(state)

        # 평균 단계 시간
        average_step_time = total_execution_time / planned_steps if planned_steps > 0 else 0.0

        # 토큰 사용량 (메타데이터에서 추출)
        total_tokens_used = metadata.get('total_tokens', 0) if metadata else 0
        input_tokens = metadata.get('input_tokens', 0) if metadata else 0
        output_tokens = metadata.get('output_tokens', 0) if metadata else 0

        # 토큰 정보가 분리되지 않았으면 추정 (input:output = 3:1 비율)
        if total_tokens_used > 0 and (input_tokens == 0 and output_tokens == 0):
            input_tokens = int(total_tokens_used * 0.75)
            output_tokens = int(total_tokens_used * 0.25)

        # API 호출 횟수 추출
        total_api_calls = metadata.get('total_api_calls', 0) if metadata else 0

        # API 호출 횟수가 없으면 step 수로 추정
        if total_api_calls == 0:
            # 각 step마다 최소 1회 LLM 호출 + 검색 도구 호출
            total_api_calls = planned_steps * 2  # Planning + Generation per step

        # 비용 추정 (정확한 모델 가격 사용)
        estimated_cost = calculate_cost(model_name, input_tokens, output_tokens)

        # 중복 단계 감지 (개선된 로직)
        redundant_steps, redundant_descriptions = self.detect_redundant_steps(state)

        # 단계별 시간 분석
        step_breakdown = self.calculate_step_times(state, total_execution_time)

        # 도구 사용 통계
        tool_usage_stats = {}
        for result in step_results:
            if isinstance(result, dict) and 'source' in result:
                source = result['source']
                tool_usage_stats[source] = tool_usage_stats.get(source, 0) + 1

        # TTFR (Time To First Response)
        time_to_first_response = metadata.get('time_to_first_response') if metadata else None

        # 효율성 점수 계산 (0~10)
        efficiency_score = 10.0

        # 실행 시간 패널티
        if total_execution_time > 120:
            efficiency_score -= 3.0
        elif total_execution_time > 60:
            efficiency_score -= 1.5

        # 중복 단계 패널티
        if redundant_steps > 5:
            efficiency_score -= 2.0
        elif redundant_steps > 2:
            efficiency_score -= 1.0

        # 토큰 사용량 패널티
        if total_tokens_used > 100000:
            efficiency_score -= 2.0
        elif total_tokens_used > 50000:
            efficiency_score -= 1.0

        # 비용 패널티
        if estimated_cost > 1.0:  # $1 이상
            efficiency_score -= 2.0
        elif estimated_cost > 0.5:  # $0.5 이상
            efficiency_score -= 1.0

        efficiency_score = max(0.0, min(10.0, efficiency_score))

        reasoning = f"총 {planned_steps}단계, {total_execution_time:.1f}초 실행"
        if total_tokens_used > 0:
            reasoning += f", {total_tokens_used:,} 토큰 사용"
        if estimated_cost > 0:
            reasoning += f", 비용 ${estimated_cost:.4f}"
        if redundant_steps > 0:
            reasoning += f", {redundant_steps}개 중복 단계"

        return EfficiencyMetrics(
            total_execution_time=total_execution_time,
            average_step_time=average_step_time,
            time_to_first_response=time_to_first_response,
            total_tokens_used=total_tokens_used,
            total_api_calls=total_api_calls,
            estimated_cost=estimated_cost,
            total_steps=planned_steps,
            redundant_steps=redundant_steps,
            efficiency_score=efficiency_score,
            step_breakdown=step_breakdown,
            tool_usage_stats=tool_usage_stats,
            reasoning=reasoning
        )

    def evaluate_source_quality(
        self,
        state: Dict[str, Any],
        report_text: str
    ) -> SourceQualityMetrics:
        """
        출처 품질 평가 (자동)

        Args:
            state: StreamingAgentState
            report_text: 보고서 텍스트
        """
        step_results = state.get('step_results', [])

        # 출처 수집
        sources = []
        for result in step_results:
            if isinstance(result, dict):
                sources.append(result)

        total_sources = len(sources)

        # 신뢰도 분석
        reliable_sources = 0
        reliability_scores = []
        source_types = set()
        unreliable_sources = []

        for source in sources:
            source_name = source.get('source', 'unknown')
            score = source.get('score', 0.5)

            reliability_scores.append(score)
            source_types.add(source_name)

            if score >= 0.7:
                reliable_sources += 1
            else:
                unreliable_sources.append(source_name)

        average_source_reliability = (
            sum(reliability_scores) / len(reliability_scores)
            if reliability_scores else 0.0
        )

        source_diversity = len(source_types)

        # 인용 정확도 계산
        # [SOURCE:N] 패턴으로 인용했는지 확인
        citation_pattern = re.compile(r'\[SOURCE:\d+\]')
        citations_in_text = citation_pattern.findall(report_text)
        citation_count = len(citations_in_text)

        # 인용 정확도: 인용된 수 / 총 출처 수
        citation_accuracy = min(1.0, citation_count / total_sources) if total_sources > 0 else 0.0

        return SourceQualityMetrics(
            total_sources=total_sources,
            reliable_sources=reliable_sources,
            source_diversity=source_diversity,
            average_source_reliability=average_source_reliability,
            citation_accuracy=citation_accuracy,
            source_types=list(source_types),
            unreliable_sources=unreliable_sources
        )

    def evaluate_content_metrics(
        self,
        report_text: str,
        expected_word_count: Optional[int] = None
    ) -> ContentMetrics:
        """
        콘텐츠 메트릭 평가 (자동)

        Args:
            report_text: 보고서 텍스트
            expected_word_count: 기대 단어 수
        """
        # 단어 수 계산 (한글/영어 혼합)
        # 한글: 공백 기준, 영어: 단어 기준
        korean_pattern = re.compile(r'[가-힣]+')
        english_pattern = re.compile(r'[a-zA-Z]+')

        korean_chars = len(korean_pattern.findall(report_text))
        english_words = len(english_pattern.findall(report_text))

        # 한글은 대략 2-3자가 1단어
        total_word_count = korean_chars // 2 + english_words
        total_char_count = len(report_text)

        # 단어 수 편차
        word_count_deviation = None
        if expected_word_count:
            word_count_deviation = (
                (total_word_count - expected_word_count) / expected_word_count * 100
            )

        # 섹션 수 계산 (마크다운 헤더 기준)
        section_pattern = re.compile(r'^#+\s+', re.MULTILINE)
        section_count = len(section_pattern.findall(report_text))

        # 차트 수 계산
        chart_pattern = re.compile(r'```(?:chart|mermaid|plotly)', re.IGNORECASE)
        chart_count = len(chart_pattern.findall(report_text))

        # 테이블 수 계산
        table_pattern = re.compile(r'\|.*\|.*\|', re.MULTILINE)
        table_count = len(table_pattern.findall(report_text)) // 2  # 헤더와 구분선 제외

        # 인용 수 계산
        citation_pattern = re.compile(r'\[SOURCE:\d+\]')
        citation_count = len(citation_pattern.findall(report_text))

        # 구조 확인
        has_executive_summary = bool(
            re.search(r'executive summary|요약|개요', report_text, re.IGNORECASE)
        )
        has_methodology = bool(
            re.search(r'methodology|방법론|연구방법', report_text, re.IGNORECASE)
        )
        has_conclusion = bool(
            re.search(r'conclusion|결론|맺음말', report_text, re.IGNORECASE)
        )

        return ContentMetrics(
            total_word_count=total_word_count,
            total_char_count=total_char_count,
            expected_word_count=expected_word_count,
            word_count_deviation=word_count_deviation,
            section_count=section_count,
            chart_count=chart_count,
            table_count=table_count,
            citation_count=citation_count,
            has_executive_summary=has_executive_summary,
            has_methodology=has_methodology,
            has_conclusion=has_conclusion
        )

    def _extract_section_content(self, text: str, section_name: str) -> str:
        """특정 섹션의 내용 추출"""
        pattern = re.compile(
            rf'#+\s*{re.escape(section_name)}(.*?)(?=#+\s|\Z)',
            re.IGNORECASE | re.DOTALL
        )
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        return ""

    def extract_plan_steps(self, state: Dict[str, Any]) -> Tuple[int, List[str]]:
        """
        Planning JSON에서 실제 단계 수 추출

        Args:
            state: StreamingAgentState

        Returns:
            (total_steps, step_descriptions)
        """
        plan = state.get('plan', {})

        if not plan:
            # plan이 없으면 step_results로 추정
            return len(state.get('step_results', [])), []

        execution_steps = plan.get('execution_steps', [])
        step_descriptions = []

        for step in execution_steps:
            if isinstance(step, dict):
                title = step.get('title', step.get('step', '알 수 없는 단계'))
                step_descriptions.append(title)

        return len(execution_steps), step_descriptions

    def detect_redundant_steps(self, state: Dict[str, Any]) -> Tuple[int, List[str]]:
        """
        중복/불필요한 단계 감지

        Args:
            state: StreamingAgentState

        Returns:
            (redundant_count, redundant_descriptions)
        """
        step_results = state.get('step_results', [])
        execution_log = state.get('execution_log', [])

        redundant_count = 0
        redundant_descriptions = []

        # 1. 동일한 검색 쿼리 반복 감지
        search_queries = []
        for result in step_results:
            if isinstance(result, dict) and 'content' in result:
                query_hash = hash(result.get('content', '')[:100])
                if query_hash in search_queries:
                    redundant_count += 1
                    redundant_descriptions.append(f"중복 검색: {result.get('source', 'unknown')}")
                else:
                    search_queries.append(query_hash)

        # 2. 동일한 로그 메시지 반복 감지
        if execution_log:
            log_texts = [log for log in execution_log if isinstance(log, str)]
            unique_logs = set(log_texts)
            log_redundancy = len(log_texts) - len(unique_logs)
            if log_redundancy > 0:
                redundant_count += log_redundancy
                redundant_descriptions.append(f"중복 로그 메시지: {log_redundancy}개")

        return redundant_count, redundant_descriptions

    def calculate_step_times(self, state: Dict[str, Any], total_time: float) -> Dict[str, float]:
        """
        단계별 시간 분석

        Args:
            state: StreamingAgentState
            total_time: 총 실행 시간

        Returns:
            step_breakdown: 단계별 시간 딕셔너리
        """
        step_breakdown = {}

        # 메타데이터에서 단계별 시간 정보가 있으면 사용
        metadata = state.get('metadata', {})
        if 'step_times' in metadata:
            return metadata['step_times']

        # 없으면 추정
        plan = state.get('plan', {})
        execution_steps = plan.get('execution_steps', [])

        if execution_steps:
            # 각 단계에 균등 배분 (실제로는 더 정교하게 측정 필요)
            avg_time = total_time / len(execution_steps)
            for i, step in enumerate(execution_steps):
                step_name = step.get('title', f'Step {i+1}') if isinstance(step, dict) else f'Step {i+1}'
                step_breakdown[step_name] = avg_time

        return step_breakdown

    def extract_schema_from_report(self, report_text: str, team_type: str) -> Dict[str, Any]:
        """
        보고서에서 스키마 추출 및 검증 (의미론적 유사도 기반)

        Args:
            report_text: 보고서 텍스트
            team_type: 팀 타입

        Returns:
            extracted_schema: 추출된 스키마 정보
        """
        # 팀 타입별 기대 스키마 정의
        expected_schemas = {
            # 영문 팀 타입 (하위 호환성)
            "marketing": {
                "market_analysis": "시장 분석",
                "target_audience": "타겟 고객",
                "strategy": "전략",
                "implementation": "실행 방안",
                "metrics": "성과 지표",
                "conclusion": "결론"
            },
            "purchasing": {
                "price_analysis": "가격 분석",
                "supplier_info": "공급업체 정보",
                "risk_assessment": "리스크 평가",
                "recommendation": "추천 사항",
                "cost_benefit": "비용 편익",
                "conclusion": "결론"
            },
            "general": {
                "overview": "개요",
                "analysis": "분석",
                "findings": "발견사항",
                "recommendation": "권장사항",
                "conclusion": "결론"
            },
            # 한글 팀 타입
            "구매 담당자": {
                "price_analysis": "가격 분석",
                "supplier_info": "공급업체 정보",
                "risk_assessment": "리스크 평가",
                "recommendation": "구매 추천",
                "cost_benefit": "비용 편익",
                "conclusion": "결론"
            },
            "급식 운영 담당자": {
                "current_status": "현황 분석",
                "menu_management": "메뉴 구성",
                "nutrition": "영양 관리",
                "cost_reduction": "원가 절감",
                "operation_improvement": "운영 개선",
                "satisfaction": "만족도 향상",
                "conclusion": "결론"
            },
            "마케팅 담당자": {
                "market_analysis": "시장 분석",
                "target_audience": "타겟 고객",
                "strategy": "마케팅 전략",
                "implementation": "실행 방안",
                "metrics": "성과 지표",
                "conclusion": "결론"
            },
            "제품 개발 연구원": {
                "tech_trend": "기술 트렌드",
                "research_status": "연구 동향",
                "development_direction": "제품 개발",
                "application": "적용 방안",
                "technical_recommendation": "기술적 권장사항",
                "conclusion": "결론"
            },
            "기본": {
                "overview": "개요",
                "analysis": "분석",
                "findings": "발견사항",
                "recommendation": "권장사항",
                "conclusion": "결론"
            }
        }

        expected_schema = expected_schemas.get(team_type, expected_schemas.get("기본", expected_schemas["general"]))

        # 의미론적 유사도 기반 매칭
        if self.use_semantic_similarity and self.embedding_model:
            extracted_schema = self._extract_schema_semantic(report_text, expected_schema)
        else:
            # fallback: 문자열 매칭
            extracted_schema = self._extract_schema_string_matching(report_text, expected_schema)

        return extracted_schema

    def _extract_schema_semantic(self, report_text: str, expected_schema: Dict[str, str]) -> Dict[str, bool]:
        """
        의미론적 유사도 기반 스키마 추출

        Args:
            report_text: 보고서 텍스트
            expected_schema: 기대 스키마 {field_key: field_name_kr}

        Returns:
            extracted_schema: {field_key: bool}
        """
        # 1. 보고서에서 마크다운 헤더 추출
        markdown_headers = re.findall(r'^#+\s+(.+)$', report_text, re.MULTILINE)

        if not markdown_headers:
            # 헤더가 없으면 문자열 매칭으로 대체
            return self._extract_schema_string_matching(report_text, expected_schema)

        # 2. 헤더들의 임베딩 계산
        header_embeddings = self.embedding_model.encode(markdown_headers, convert_to_numpy=True)

        # 3. 기대 스키마 필드들의 임베딩 계산
        expected_fields = list(expected_schema.values())
        field_embeddings = self.embedding_model.encode(expected_fields, convert_to_numpy=True)

        # 4. 각 기대 필드에 대해 가장 유사한 헤더 찾기
        extracted_schema = {}
        similarity_threshold = 0.65  # 유사도 임계값 (조정 가능)

        for idx, (field_key, field_name) in enumerate(expected_schema.items()):
            field_embedding = field_embeddings[idx]

            # 모든 헤더와의 유사도 계산 (코사인 유사도)
            similarities = np.dot(header_embeddings, field_embedding) / (
                np.linalg.norm(header_embeddings, axis=1) * np.linalg.norm(field_embedding)
            )

            max_similarity = np.max(similarities)

            # threshold 이상이면 해당 필드가 존재한다고 판단
            extracted_schema[field_key] = bool(max_similarity >= similarity_threshold)

        return extracted_schema

    def _extract_schema_string_matching(self, report_text: str, expected_schema: Dict[str, str]) -> Dict[str, bool]:
        """
        문자열 매칭 기반 스키마 추출 (fallback)

        Args:
            report_text: 보고서 텍스트
            expected_schema: 기대 스키마

        Returns:
            extracted_schema: {field_key: bool}
        """
        synonym_map = {
            "시장 분석": ["시장", "마켓", "시장 현황", "시장 동향", "market"],
            "타겟 고객": ["타겟", "고객", "소비자", "target", "customer"],
            "전략": ["전략", "방안", "계획", "strategy"],
            "마케팅 전략": ["마케팅", "전략", "방안", "계획", "marketing"],
            "실행 방안": ["실행", "방안", "계획", "구현", "implementation"],
            "성과 지표": ["성과", "지표", "KPI", "metrics", "측정"],
            "가격 분석": ["가격", "price", "pricing", "비용", "원가"],
            "공급업체 정보": ["공급업체", "공급자", "supplier", "vendor", "업체"],
            "리스크 평가": ["리스크", "위험", "risk", "평가"],
            "추천 사항": ["추천", "권장", "제안", "recommendation"],
            "구매 추천": ["구매", "추천", "권장", "제안"],
            "비용 편익": ["비용", "편익", "효과", "cost", "benefit"],
            "개요": ["개요", "요약", "overview", "summary"],
            "분석": ["분석", "analysis"],
            "발견사항": ["발견", "결과", "findings"],
            "권장사항": ["권장", "제안", "추천", "recommendation"],
            "결론": ["결론", "맺음말", "conclusion"],
            "현황 분석": ["현황", "분석", "상황", "실태"],
            "메뉴 구성": ["메뉴", "구성", "식단", "menu"],
            "영양 관리": ["영양", "관리", "nutrition", "건강"],
            "원가 절감": ["원가", "절감", "비용", "cost"],
            "운영 개선": ["운영", "개선", "효율", "operation"],
            "만족도 향상": ["만족도", "향상", "개선", "satisfaction"],
            "기술 트렌드": ["기술", "트렌드", "동향", "tech", "technology"],
            "연구 동향": ["연구", "동향", "현황", "research"],
            "제품 개발": ["제품", "개발", "product", "development"],
            "적용 방안": ["적용", "방안", "활용", "application"],
            "기술적 권장사항": ["기술", "권장", "제안", "technical"]
        }

        extracted_schema = {}
        for field_key, field_name_kr in expected_schema.items():
            # 정확한 매칭
            if field_name_kr in report_text:
                extracted_schema[field_key] = True
                continue

            # 유사 표현 매칭
            synonyms = synonym_map.get(field_name_kr, [])
            found = False
            for synonym in synonyms:
                if synonym in report_text or synonym.lower() in report_text.lower():
                    found = True
                    break

            extracted_schema[field_key] = found

        return extracted_schema

    def check_citation_coverage(self, report_text: str, sources: List[Dict[str, Any]]) -> Tuple[float, List[str]]:
        """
        자동 팩트 체킹: 인용 커버리지 확인

        Args:
            report_text: 보고서 텍스트
            sources: 출처 리스트

        Returns:
            (coverage_rate, uncited_claims): 인용 커버리지율, 미인용 주장 리스트
        """
        # [SOURCE:N] 패턴 찾기
        citation_pattern = re.compile(r'\[SOURCE:(\d+)\]')
        cited_sources = set(citation_pattern.findall(report_text))

        # 문장 단위로 분리
        sentences = re.split(r'[.!?]\s+', report_text)

        uncited_claims = []
        total_factual_sentences = 0

        for sentence in sentences:
            # 사실 주장이 있는지 확인 (숫자, 통계, 인용 등)
            has_numbers = bool(re.search(r'\d+%|\d+\$|\d+년|\d+개|\d+명', sentence))
            has_statistics = any(word in sentence for word in ['증가', '감소', '상승', '하락', '점유율', '비율'])

            if (has_numbers or has_statistics) and len(sentence) > 20:
                total_factual_sentences += 1

                # 인용이 있는지 확인
                if not citation_pattern.search(sentence):
                    uncited_claims.append(sentence[:100])  # 처음 100자만

        # 커버리지율 계산
        coverage_rate = 1.0 - (len(uncited_claims) / total_factual_sentences) if total_factual_sentences > 0 else 1.0

        return coverage_rate, uncited_claims[:5]  # 최대 5개만 반환


__all__ = ["AutomatedEvaluator"]
