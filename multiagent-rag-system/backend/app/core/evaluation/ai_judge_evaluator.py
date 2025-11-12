"""
LLM 기반 AI 심판 평가기
AI Judge Evaluator using LLM

LLM을 사용하여 보고서의 품질, 정확도, 환각 현상 등을 평가합니다.
"""

import os
import json
from typing import Dict, Any, List, Optional
import google.generativeai as genai

from app.core.evaluation.evaluation_models import (
    OutputQualityMetrics,
    HallucinationMetrics,
)


class AIJudgeEvaluator:
    """AI 심판 평가기 - LLM을 사용한 품질 평가"""

    def __init__(self, model: str = "gemini-2.5-flash", temperature: float = 0.1):
        """
        초기화

        Args:
            model: 사용할 LLM 모델
            temperature: 생성 온도 (낮을수록 일관성 높음)
        """
        # 환경변수에서 Gemini API 키 가져오기
        api_key = os.getenv("GEMINI_API_KEY_1")
        if not api_key:
            raise ValueError("GEMINI_API_KEY_1 환경변수가 설정되지 않았습니다.")

        genai.configure(api_key=api_key)

        # 안전 설정 완화 (평가 목적)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        self.model = genai.GenerativeModel(
            model_name=model,
            generation_config={
                "temperature": temperature,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            },
            safety_settings=safety_settings
        )
        self.temperature = temperature

    def evaluate_output_quality(
        self,
        query: str,
        report_text: str,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> OutputQualityMetrics:
        """
        출력 품질 및 정확도 평가

        Args:
            query: 원본 질문/요청
            report_text: 생성된 보고서
            sources: 사용된 출처 정보
        """
        # 평가 프롬프트 구성
        evaluation_prompt = self._build_quality_evaluation_prompt(
            query, report_text, sources
        )

        # LLM 호출 (Gemini)
        system_instruction = "당신은 전문적인 보고서 품질 평가자입니다. 보고서의 사실 정확도, 논리적 일관성, 요구사항 부합도를 객관적으로 평가합니다."
        full_prompt = f"{system_instruction}\n\n{evaluation_prompt}"

        response = self.model.generate_content(full_prompt)

        # 응답 파싱 (안전 필터 체크)
        if not response.candidates or not response.candidates[0].content.parts:
            evaluation_text = "평가 실패 (안전 필터 차단)"
        else:
            evaluation_text = response.text
        quality_scores = self._parse_quality_scores(evaluation_text)

        return OutputQualityMetrics(
            factual_accuracy_score=quality_scores.get('factual_accuracy', 7.0),
            logical_coherence_score=quality_scores.get('logical_coherence', 7.0),
            relevance_score=quality_scores.get('relevance', 7.0),
            overall_quality_score=quality_scores.get('overall_quality', 7.0),
            has_clear_structure=quality_scores.get('has_clear_structure', True),
            has_proper_citations=quality_scores.get('has_proper_citations', True),
            language_quality=quality_scores.get('language_quality', 'good'),
            reasoning=quality_scores.get('reasoning', evaluation_text[:500])
        )

    def evaluate_hallucination(
        self,
        query: str,
        report_text: str,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> HallucinationMetrics:
        """
        환각 현상 평가

        Args:
            query: 원본 질문/요청
            report_text: 생성된 보고서
            sources: 사용된 출처 정보
        """
        # 평가 프롬프트 구성
        evaluation_prompt = self._build_hallucination_evaluation_prompt(
            query, report_text, sources
        )

        # LLM 호출 (Gemini)
        system_instruction = "당신은 AI 환각 현상(hallucination) 탐지 전문가입니다. 보고서에서 검증되지 않은 정보, 사실이 아닌 내용, 모순되는 정보를 찾아냅니다."
        full_prompt = f"{system_instruction}\n\n{evaluation_prompt}"

        response = self.model.generate_content(full_prompt)

        # 응답 파싱 (안전 필터 체크)
        if not response.candidates or not response.candidates[0].content.parts:
            evaluation_text = "평가 실패 (안전 필터 차단)"
        else:
            evaluation_text = response.text
        hallucination_results = self._parse_hallucination_results(evaluation_text)

        return HallucinationMetrics(
            hallucination_detected=hallucination_results.get('detected', False),
            hallucination_count=hallucination_results.get('count', 0),
            hallucination_rate=hallucination_results.get('rate', 0.0),
            hallucination_examples=hallucination_results.get('examples', []),
            unverified_claims=hallucination_results.get('unverified_claims', []),
            contradictions=hallucination_results.get('contradictions', []),
            citation_accuracy=hallucination_results.get('citation_accuracy', 1.0),
            confidence_score=hallucination_results.get('confidence_score', 0.8),
            reasoning=hallucination_results.get('reasoning', evaluation_text[:500])
        )

    def evaluate_comprehensive(
        self,
        query: str,
        report_text: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        expected_requirements: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        종합 평가 (품질 + 환각 + 추가 분석)

        Args:
            query: 원본 질문/요청
            report_text: 생성된 보고서
            sources: 사용된 출처 정보
            expected_requirements: 기대 요구사항
        """
        # 종합 평가 프롬프트
        requirements_text = ""
        if expected_requirements:
            req_lines = "\n".join(f"- {req}" for req in expected_requirements)
            requirements_text = f"[기대 요구사항]\n{req_lines}"

        evaluation_prompt = f"""
다음 보고서를 종합적으로 평가해주세요.

[원본 요청]
{query}

[생성된 보고서]
{report_text[:3000]}...

[사용된 출처 수]
{len(sources) if sources else 0}개

{requirements_text}

다음 항목들을 JSON 형식으로 평가해주세요:

{{
  "strengths": ["강점 1", "강점 2", ...],
  "weaknesses": ["약점 1", "약점 2", ...],
  "recommendations": ["개선사항 1", "개선사항 2", ...],
  "overall_assessment": "전체 평가 요약",
  "key_findings": ["주요 발견사항 1", "주요 발견사항 2", ...],
  "credibility_rating": 0-10 점수,
  "usefulness_rating": 0-10 점수
}}
"""

        # LLM 호출 (Gemini)
        system_instruction = "당신은 경험이 풍부한 보고서 평가 전문가입니다."
        full_prompt = f"{system_instruction}\n\n{evaluation_prompt}"

        response = self.model.generate_content(full_prompt)

        evaluation_text = response.text

        # JSON 파싱 시도
        import re

        # JSON 블록 추출
        json_match = re.search(r'\{[\s\S]*\}', evaluation_text)
        if json_match:
            try:
                result = json.loads(json_match.group(0))
                return result
            except json.JSONDecodeError:
                pass

        # 파싱 실패 시 기본값 반환
        return {
            "strengths": ["보고서가 생성되었습니다"],
            "weaknesses": ["자동 평가 실패"],
            "recommendations": ["수동 검토 필요"],
            "overall_assessment": evaluation_text[:200],
            "key_findings": [],
            "credibility_rating": 5.0,
            "usefulness_rating": 5.0
        }

    def _build_quality_evaluation_prompt(
        self,
        query: str,
        report_text: str,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """품질 평가 프롬프트 생성"""
        source_info = f"\n[사용된 출처 수]: {len(sources)}개" if sources else ""

        prompt = f"""
다음 보고서의 품질을 평가해주세요.

[원본 요청]
{query}

[생성된 보고서]
{report_text[:2500]}...
{source_info}

다음 항목들을 0-10 점수로 평가하고, JSON 형식으로 답변해주세요:

{{
  "factual_accuracy": 0-10 (사실 정확도),
  "logical_coherence": 0-10 (논리적 일관성),
  "relevance": 0-10 (요구사항 부합도),
  "overall_quality": 0-10 (전체 품질),
  "has_clear_structure": true/false (명확한 구조),
  "has_proper_citations": true/false (적절한 인용),
  "language_quality": "poor/fair/good/excellent" (언어 품질),
  "reasoning": "평가 근거 설명"
}}

객관적이고 엄격하게 평가해주세요.
"""
        return prompt

    def _build_hallucination_evaluation_prompt(
        self,
        query: str,
        report_text: str,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """환각 현상 및 인용 정확성 평가 프롬프트 생성"""

        # 출처 전체 내용 제공 (최대 10개, 전체 내용 - 보고서 생성 LLM과 동일)
        source_details = ""
        if sources:
            source_details = "\n[출처 전체 내용 - 인용 검증용]\n"
            for i, source in enumerate(sources[:10], 1):
                title = source.get('title', f'출처 {i}')
                content = source.get('content', '')  # 전체 content 제공
                url = source.get('url', 'N/A')
                source_details += f"\n--- SOURCE {i}: {title} ---\n"
                source_details += f"URL: {url}\n"
                source_details += f"내용:\n{content}\n"

        prompt = f"""
다음 보고서에서 **환각 현상(hallucination)**과 **인용 부정확성**을 탐지해주세요.

**평가 항목:**
1. **인용 검증**: [SOURCE:N] 태그가 붙은 문장이 실제 SOURCE N의 내용과 일치하는지
2. **근거 없는 주장**: 출처에 전혀 없는 정보를 사실처럼 작성했는지
3. **과장 또는 왜곡**: 출처 내용을 부정확하게 해석하거나 과장했는지

[원본 요청]
{query}

[생성된 보고서 - 전체]
{report_text}

{source_details}

**평가 방법:**
1. [SOURCE:N] 태그가 있는 모든 문장을 찾으세요
2. 각 문장을 해당 SOURCE N의 실제 내용과 **정확히 대조**하세요
3. 불일치하거나 출처에 없는 내용은 환각으로 판정하세요
4. **왜 환각인지 구체적인 이유를 명시**하세요

다음 항목들을 JSON 형식으로 평가해주세요:

{{
  "detected": true/false (환각 현상 감지 여부),
  "count": 숫자 (감지된 환각 현상 개수),
  "rate": 0.0-1.0 (환각 현상 비율),
  "examples": [
    {{
      "statement": "[SOURCE:N]이 붙은 문장 또는 근거 없는 주장",
      "reason": "SOURCE N의 내용: '실제 내용 요약'. 문제: 출처에 없는 정보 / 출처 내용과 불일치 / 과장됨"
    }},
    ...
  ],
  "unverified_claims": ["출처 없이 작성된 구체적 주장 1", ...],
  "contradictions": ["SOURCE X와 SOURCE Y가 모순되는 내용 1", ...],
  "citation_accuracy": 0.0-1.0 (인용 정확도 - [SOURCE:N] 태그와 실제 출처 내용 일치율),
  "confidence_score": 0.0-1.0 (평가 신뢰도),
  "reasoning": "평가 근거 상세 설명 - 특히 인용 태그와 출처 내용을 어떻게 비교했는지"
}}

**매우 엄격하게 검증하되, 근거를 반드시 명시하세요.**
"""
        return prompt

    def _parse_quality_scores(self, evaluation_text: str) -> Dict[str, Any]:
        """품질 평가 결과 파싱"""
        import json
        import re

        # JSON 블록 추출
        json_match = re.search(r'\{[\s\S]*\}', evaluation_text)
        if json_match:
            try:
                scores = json.loads(json_match.group(0))
                return scores
            except json.JSONDecodeError:
                pass

        # 파싱 실패 시 기본값
        return {
            'factual_accuracy': 7.0,
            'logical_coherence': 7.0,
            'relevance': 7.0,
            'overall_quality': 7.0,
            'has_clear_structure': True,
            'has_proper_citations': True,
            'language_quality': 'good',
            'reasoning': evaluation_text[:300]
        }

    def _parse_hallucination_results(self, evaluation_text: str) -> Dict[str, Any]:
        """환각 현상 평가 결과 파싱"""
        import json
        import re

        # JSON 블록 추출
        json_match = re.search(r'\{[\s\S]*\}', evaluation_text)
        if json_match:
            try:
                results = json.loads(json_match.group(0))
                return results
            except json.JSONDecodeError:
                pass

        # 파싱 실패 시 기본값
        return {
            'detected': False,
            'count': 0,
            'rate': 0.0,
            'examples': [],
            'unverified_claims': [],
            'contradictions': [],
            'citation_accuracy': 1.0,
            'confidence_score': 0.5,
            'reasoning': evaluation_text[:300]
        }


__all__ = ["AIJudgeEvaluator"]
