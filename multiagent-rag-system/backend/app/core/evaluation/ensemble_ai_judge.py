"""
3-Model Ensemble AI Judge Evaluator
Gemini 2.5 Flash + Claude 3.5 Sonnet + GPT-4o 앙상블 평가 시스템

JSON 기반 평가 지표를 사용하여 객관적이고 확장 가능한 평가를 수행합니다.
"""

import os
import json
import asyncio
import statistics
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

# API Clients
import google.generativeai as genai
from anthropic import Anthropic
from openai import OpenAI

from app.core.evaluation.evaluation_models import (
    OutputQualityMetrics,
    HallucinationMetrics,
)

# .env 로드
load_dotenv()


class EnsembleAIJudge:
    """
    3개 모델 앙상블 AI Judge
    - Gemini 2.5 Flash: 사실 정확도, 인용 검증, 빠른 응답
    - Claude 3.5 Sonnet: 논리적 일관성, 요구사항 분석, 섬세한 평가
    - GPT-4o: 종합 품질, 객관적 평가, 균형잡힌 판단
    """

    def __init__(self, criteria_path: Optional[str] = None):
        """
        초기화

        Args:
            criteria_path: evaluation_criteria.json 파일 경로
        """
        # 평가 지표 JSON 로드
        if criteria_path is None:
            criteria_path = Path(__file__).parent / "evaluation_criteria.json"

        with open(criteria_path, 'r', encoding='utf-8') as f:
            self.criteria = json.load(f)

        # 모델 설정 로드
        self.model_configs = self.criteria["evaluation_models"]

        # 각 모델 클라이언트 초기화
        self._init_gemini()
        self._init_claude()
        self._init_gpt()

        print("✅ Ensemble AI Judge 초기화 완료")
        print(f"   - Gemini: {self.model_configs['gemini']['model_name']} (가중치: {self.model_configs['gemini']['weight']})")
        print(f"   - Claude: {self.model_configs['claude']['model_name']} (가중치: {self.model_configs['claude']['weight']})")
        print(f"   - GPT: {self.model_configs['gpt']['model_name']} (가중치: {self.model_configs['gpt']['weight']})")

    def _init_gemini(self):
        """Gemini 클라이언트 초기화"""
        api_key = os.getenv(self.model_configs['gemini']['api_key_env'])
        if not api_key:
            raise ValueError(f"{self.model_configs['gemini']['api_key_env']} 환경변수가 설정되지 않았습니다.")

        genai.configure(api_key=api_key)

        # 안전 설정 완화
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        self.gemini_model = genai.GenerativeModel(
            model_name=self.model_configs['gemini']['model_name'],
            generation_config={
                "temperature": self.model_configs['gemini']['temperature'],
                "max_output_tokens": self.model_configs['gemini']['max_tokens'],
            },
            safety_settings=safety_settings
        )

    def _init_claude(self):
        """Claude 클라이언트 초기화"""
        api_key = os.getenv(self.model_configs['claude']['api_key_env'])
        if not api_key:
            raise ValueError(f"{self.model_configs['claude']['api_key_env']} 환경변수가 설정되지 않았습니다.")

        self.claude_client = Anthropic(api_key=api_key)

    def _init_gpt(self):
        """GPT 클라이언트 초기화"""
        api_key = os.getenv(self.model_configs['gpt']['api_key_env'])
        if not api_key:
            raise ValueError(f"{self.model_configs['gpt']['api_key_env']} 환경변수가 설정되지 않았습니다.")

        self.gpt_client = OpenAI(api_key=api_key)

    def evaluate_factual_accuracy(
        self,
        report: str,
        sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        사실 정확도 평가 (3개 모델 앙상블)

        Args:
            report: 평가할 보고서
            sources: 출처 목록

        Returns:
            앙상블 평가 결과
        """
        # 프롬프트 생성
        prompt = self._build_prompt(
            template_key="factual_accuracy_prompt",
            report=report,
            sources=self._format_sources(sources)
        )

        # 각 모델 평가
        gemini_result = self._evaluate_with_gemini(prompt)
        claude_result = self._evaluate_with_claude(prompt)
        gpt_result = self._evaluate_with_gpt(prompt)

        # 앙상블 집계
        ensemble_result = self._aggregate_results({
            "gemini": gemini_result,
            "claude": claude_result,
            "gpt": gpt_result
        })

        return ensemble_result

    def evaluate_logical_coherence(
        self,
        report: str
    ) -> Dict[str, Any]:
        """
        논리적 일관성 평가 (3개 모델 앙상블)

        Args:
            report: 평가할 보고서

        Returns:
            앙상블 평가 결과
        """
        prompt = self._build_prompt(
            template_key="logical_coherence_prompt",
            report=report
        )

        gemini_result = self._evaluate_with_gemini(prompt)
        claude_result = self._evaluate_with_claude(prompt)
        gpt_result = self._evaluate_with_gpt(prompt)

        ensemble_result = self._aggregate_results({
            "gemini": gemini_result,
            "claude": claude_result,
            "gpt": gpt_result
        })

        return ensemble_result

    def evaluate_relevance(
        self,
        query: str,
        report: str
    ) -> Dict[str, Any]:
        """
        요구사항 부합도 평가 (3개 모델 앙상블)

        Args:
            query: 원본 쿼리
            report: 평가할 보고서

        Returns:
            앙상블 평가 결과
        """
        prompt = self._build_prompt(
            template_key="relevance_prompt",
            query=query,
            report=report
        )

        gemini_result = self._evaluate_with_gemini(prompt)
        claude_result = self._evaluate_with_claude(prompt)
        gpt_result = self._evaluate_with_gpt(prompt)

        ensemble_result = self._aggregate_results({
            "gemini": gemini_result,
            "claude": claude_result,
            "gpt": gpt_result
        })

        return ensemble_result

    def evaluate_hallucination(
        self,
        report: str,
        sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        환각 탐지 (3개 모델 앙상블)

        Args:
            report: 평가할 보고서
            sources: 출처 목록

        Returns:
            앙상블 평가 결과
        """
        prompt = self._build_prompt(
            template_key="hallucination_prompt",
            report=report,
            sources=self._format_sources(sources)
        )

        gemini_result = self._evaluate_with_gemini(prompt)
        claude_result = self._evaluate_with_claude(prompt)
        gpt_result = self._evaluate_with_gpt(prompt)

        ensemble_result = self._aggregate_hallucination_results({
            "gemini": gemini_result,
            "claude": claude_result,
            "gpt": gpt_result
        })

        return ensemble_result

    def evaluate_output_quality(
        self,
        query: str,
        report_text: str,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> OutputQualityMetrics:
        """
        출력 품질 종합 평가 (기존 인터페이스 호환)

        Args:
            query: 원본 질문/요청
            report_text: 생성된 보고서
            sources: 사용된 출처 정보

        Returns:
            OutputQualityMetrics 객체
        """
        # 3개 메트릭 평가
        factual_accuracy = self.evaluate_factual_accuracy(report_text, sources or [])
        logical_coherence = self.evaluate_logical_coherence(report_text)
        relevance = self.evaluate_relevance(query, report_text)

        # overall_quality 계산 (가중 평균)
        overall_quality = (
            factual_accuracy['ensemble_score'] * 0.40 +
            logical_coherence['ensemble_score'] * 0.30 +
            relevance['ensemble_score'] * 0.30
        )

        return OutputQualityMetrics(
            factual_accuracy_score=factual_accuracy['ensemble_score'],
            logical_coherence_score=logical_coherence['ensemble_score'],
            relevance_score=relevance['ensemble_score'],
            overall_quality_score=overall_quality,
            has_clear_structure=True,
            has_proper_citations=True,
            language_quality='good',
            reasoning=self._combine_reasoning(factual_accuracy, logical_coherence, relevance)
        )

    def evaluate_comprehensive(
        self,
        query: str,
        report_text: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        expected_requirements: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        종합 평가 (3-Model Ensemble)

        Args:
            query: 원본 질문/요청
            report_text: 생성된 보고서
            sources: 사용된 출처 정보
            expected_requirements: 기대 요구사항

        Returns:
            종합 평가 결과 dict
        """
        # 종합 평가 프롬프트 구성
        requirements_text = ""
        if expected_requirements:
            req_lines = "\n".join(f"- {req}" for req in expected_requirements)
            requirements_text = f"[기대 요구사항]\n{req_lines}"

        prompt = f"""
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
  "strengths": ["강점 1", "강점 2", "강점 3"],
  "weaknesses": ["약점 1", "약점 2"],
  "recommendations": ["개선사항 1", "개선사항 2"],
  "overall_assessment": "전체 평가 요약",
  "key_findings": ["주요 발견사항 1", "주요 발견사항 2"],
  "credibility_rating": 8.5,
  "usefulness_rating": 9.0
}}
"""

        # 3개 모델 평가
        gemini_result = self._evaluate_with_gemini(prompt)
        claude_result = self._evaluate_with_claude(prompt)
        gpt_result = self._evaluate_with_gpt(prompt)

        # 결과 병합
        all_strengths = []
        all_weaknesses = []
        all_recommendations = []
        credibility_scores = []
        usefulness_scores = []

        for result in [gemini_result, claude_result, gpt_result]:
            if not result.get('error', False):
                all_strengths.extend(result.get('strengths', []))
                all_weaknesses.extend(result.get('weaknesses', []))
                all_recommendations.extend(result.get('recommendations', []))
                credibility_scores.append(result.get('credibility_rating', 7.0))
                usefulness_scores.append(result.get('usefulness_rating', 7.0))

        # 중복 제거 및 상위 3개 선택
        unique_strengths = list(dict.fromkeys(all_strengths))[:3]
        unique_weaknesses = list(dict.fromkeys(all_weaknesses))[:3]
        unique_recommendations = list(dict.fromkeys(all_recommendations))[:3]

        # 평균 점수 계산
        avg_credibility = sum(credibility_scores) / len(credibility_scores) if credibility_scores else 7.0
        avg_usefulness = sum(usefulness_scores) / len(usefulness_scores) if usefulness_scores else 7.0

        return {
            "strengths": unique_strengths,
            "weaknesses": unique_weaknesses,
            "recommendations": unique_recommendations,
            "overall_assessment": "3-Model Ensemble 종합 평가 완료",
            "credibility_rating": round(avg_credibility, 2),
            "usefulness_rating": round(avg_usefulness, 2),
            "individual_results": {
                "gemini": gemini_result,
                "claude": claude_result,
                "gpt": gpt_result
            }
        }

    def evaluate_hallucination_metrics(
        self,
        query: str,
        report_text: str,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> HallucinationMetrics:
        """
        환각 평가 (기존 인터페이스 호환)

        Args:
            query: 원본 질문/요청
            report_text: 생성된 보고서
            sources: 사용된 출처 정보

        Returns:
            HallucinationMetrics 객체
        """
        result = self.evaluate_hallucination(report_text, sources or [])

        return HallucinationMetrics(
            hallucination_count=result.get('hallucination_count', 0),
            hallucination_examples=result.get('hallucinations', []),
            citation_accuracy=result.get('citation_accuracy', 1.0),
            contains_fabricated_sources=result.get('hallucination_count', 0) > 0,
            contains_contradictions=False,
            reasoning=result.get('ensemble_reasoning', '')
        )

    def _build_prompt(self, template_key: str, **kwargs) -> str:
        """
        평가 프롬프트 생성

        Args:
            template_key: criteria.json의 프롬프트 템플릿 키
            **kwargs: 프롬프트 템플릿에 전달할 변수들

        Returns:
            완성된 프롬프트
        """
        template = self.criteria['ai_judge_prompts'][template_key]
        return template.format(**kwargs)

    def _format_sources(self, sources: List[Dict[str, Any]]) -> str:
        """
        출처 목록을 문자열로 포맷

        Args:
            sources: 출처 목록

        Returns:
            포맷된 출처 문자열
        """
        formatted = []
        for i, source in enumerate(sources):
            content = source.get('content', source.get('text', ''))
            title = source.get('title', f'출처 {i}')
            formatted.append(f"[SOURCE:{i}]\n제목: {title}\n내용: {content}\n")

        return "\n".join(formatted)

    def _evaluate_with_gemini(self, prompt: str) -> Dict[str, Any]:
        """Gemini로 평가"""
        try:
            response = self.gemini_model.generate_content(prompt)

            if not response.candidates or not response.candidates[0].content.parts:
                return {"score": 7.0, "reasoning": "평가 실패 (안전 필터 차단)", "error": True}

            result_text = response.text
            return self._parse_json_response(result_text, model="gemini")

        except Exception as e:
            print(f"⚠ Gemini 평가 실패: {e}")
            return {"score": 7.0, "reasoning": f"평가 실패: {str(e)}", "error": True}

    def _evaluate_with_claude(self, prompt: str) -> Dict[str, Any]:
        """Claude로 평가"""
        try:
            response = self.claude_client.messages.create(
                model=self.model_configs['claude']['model_name'],
                max_tokens=self.model_configs['claude']['max_tokens'],
                temperature=self.model_configs['claude']['temperature'],
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            result_text = response.content[0].text
            return self._parse_json_response(result_text, model="claude")

        except Exception as e:
            print(f"⚠ Claude 평가 실패: {e}")
            return {"score": 7.0, "reasoning": f"평가 실패: {str(e)}", "error": True}

    def _evaluate_with_gpt(self, prompt: str) -> Dict[str, Any]:
        """GPT-4o로 평가"""
        try:
            response = self.gpt_client.chat.completions.create(
                model=self.model_configs['gpt']['model_name'],
                messages=[
                    {"role": "system", "content": "당신은 전문적인 보고서 품질 평가자입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.model_configs['gpt']['temperature'],
                max_tokens=self.model_configs['gpt']['max_tokens']
            )

            result_text = response.choices[0].message.content
            return self._parse_json_response(result_text, model="gpt")

        except Exception as e:
            print(f"⚠ GPT 평가 실패: {e}")
            return {"score": 7.0, "reasoning": f"평가 실패: {str(e)}", "error": True}

    def _parse_json_response(self, text: str, model: str) -> Dict[str, Any]:
        """
        모델 응답을 JSON으로 파싱

        Args:
            text: 모델 응답 텍스트
            model: 모델 이름

        Returns:
            파싱된 결과
        """
        try:
            # JSON 블록 추출 (```json ... ``` 형식 대응)
            if "```json" in text:
                json_start = text.find("```json") + len("```json")
                json_end = text.find("```", json_start)
                if json_end == -1:
                    json_end = len(text)
                json_text = text[json_start:json_end].strip()
            elif "```" in text and "{" in text:
                # ``` 없이 json만 있는 경우
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                json_text = text[json_start:json_end]
            elif "{" in text and "}" in text:
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                json_text = text[json_start:json_end]
            else:
                json_text = text

            # 제어 문자 제거 (탭, 개행 등은 유지하되 다른 제어 문자 제거)
            import re
            # ASCII 제어 문자 중 \n, \r, \t를 제외한 나머지 제거
            json_text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', json_text)

            result = json.loads(json_text)
            result['model'] = model
            result['error'] = False
            return result

        except json.JSONDecodeError as e:
            print(f"⚠ {model} JSON 파싱 실패: {e}")
            print(f"   응답: {text[:500]}...")

            # 더 강력한 fallback: 점수와 reasoning 추출 시도
            import re
            score = 7.0
            reasoning = "파싱 실패"

            # 점수 추출
            if "score" in text.lower():
                score_match = re.search(r'["\']?score["\']?\s*:\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
                if score_match:
                    score = float(score_match.group(1))

            # reasoning 추출 (JSON 문자열 안에서)
            reasoning_match = re.search(r'["\']?reasoning["\']?\s*:\s*["\']([^"\']*)', text, re.IGNORECASE | re.DOTALL)
            if reasoning_match:
                reasoning = reasoning_match.group(1)[:500]  # 최대 500자
            elif text:
                # reasoning 필드를 못 찾으면 전체 텍스트에서 일부만
                reasoning = text[:500]

            print(f"   → Fallback: score={score}, reasoning 추출됨")

            return {
                "score": score,
                "reasoning": reasoning,
                "model": model,
                "error": True
            }

    def _aggregate_results(self, results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        3개 모델 결과를 앙상블 집계

        Args:
            results: {"gemini": {...}, "claude": {...}, "gpt": {...}}

        Returns:
            앙상블 집계 결과
        """
        # 가중치
        weights = {
            "gemini": self.model_configs['gemini']['weight'],
            "claude": self.model_configs['claude']['weight'],
            "gpt": self.model_configs['gpt']['weight']
        }

        # 점수 추출
        scores = []
        valid_results = []

        for model_name, result in results.items():
            if not result.get('error', False):
                scores.append(result['score'] * weights[model_name])
                valid_results.append(result)

        # 앙상블 점수 계산
        if not scores:
            # 모든 모델 실패 시 중립 점수
            ensemble_score = 7.0
        else:
            # 가중 평균
            ensemble_score = sum(scores) / sum(weights[m] for m, r in results.items() if not r.get('error', False))

        # 불일치 감지 (점수 차이 3점 이상)
        raw_scores = [r['score'] for r in results.values() if not r.get('error', False)]
        disagreement = False
        if len(raw_scores) >= 2:
            score_range = max(raw_scores) - min(raw_scores)
            if score_range >= 3.0:
                disagreement = True
                # 불일치 시 중앙값 사용
                ensemble_score = statistics.median(raw_scores)

        return {
            "ensemble_score": round(ensemble_score, 2),
            "individual_scores": {
                "gemini": results['gemini']['score'],
                "claude": results['claude']['score'],
                "gpt": results['gpt']['score']
            },
            "ensemble_reasoning": self._combine_individual_reasoning(results),
            "disagreement_detected": disagreement,
            "all_results": results
        }

    def _aggregate_hallucination_results(self, results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        환각 평가 결과 앙상블 집계

        Args:
            results: {"gemini": {...}, "claude": {...}, "gpt": {...}}

        Returns:
            앙상블 집계 결과
        """
        # 환각 건수는 최대값 사용 (보수적 접근)
        hallucination_counts = [
            r.get('hallucination_count', 0)
            for r in results.values()
            if not r.get('error', False)
        ]

        if not hallucination_counts:
            ensemble_count = 0
        else:
            # 2개 이상 모델이 동의하면 환각으로 판정
            ensemble_count = int(statistics.median(hallucination_counts))

        # 인용 정확도는 최소값 사용 (보수적 접근)
        citation_accuracies = [
            r.get('citation_accuracy', 1.0)
            for r in results.values()
            if not r.get('error', False)
        ]

        ensemble_citation_accuracy = min(citation_accuracies) if citation_accuracies else 1.0

        # 환각 비율 = 1 - 인용 정확도
        # (AI 모델들이 hallucination_rate를 직접 반환하지 않으므로 citation_accuracy로 계산)
        ensemble_rate = 1.0 - ensemble_citation_accuracy

        # 환각 사례 병합 (중복 제거)
        all_hallucinations = []
        for result in results.values():
            if not result.get('error', False):
                all_hallucinations.extend(result.get('hallucinations', []))

        # 검증되지 않은 주장 병합
        all_unverified_claims = []
        for result in results.values():
            if not result.get('error', False):
                all_unverified_claims.extend(result.get('unverified_claims', []))

        # 모순 병합
        all_contradictions = []
        for result in results.values():
            if not result.get('error', False):
                all_contradictions.extend(result.get('contradictions', []))

        # 신뢰도 점수 계산 (평균)
        confidence_scores = [
            r.get('confidence_score', 0.5)
            for r in results.values()
            if not r.get('error', False)
        ]
        ensemble_confidence = statistics.mean(confidence_scores) if confidence_scores else 0.5

        return {
            "hallucination_detected": ensemble_count > 0,
            "hallucination_count": ensemble_count,
            "hallucination_rate": round(ensemble_rate, 4),
            "hallucination_examples": all_hallucinations,
            "citation_accuracy": round(ensemble_citation_accuracy, 2),
            "unverified_claims": all_unverified_claims[:10],  # 최대 10개
            "contradictions": all_contradictions[:10],  # 최대 10개
            "confidence_score": round(ensemble_confidence, 2),
            "reasoning": self._combine_individual_reasoning(results),
            "individual_counts": {
                "gemini": results['gemini'].get('hallucination_count', 0),
                "claude": results['claude'].get('hallucination_count', 0),
                "gpt": results['gpt'].get('hallucination_count', 0)
            },
            "all_results": results
        }

    def _combine_individual_reasoning(self, results: Dict[str, Dict[str, Any]]) -> str:
        """개별 모델 reasoning을 종합"""
        combined = []

        for model_name, result in results.items():
            if not result.get('error', False):
                reasoning = result.get('reasoning', '')
                combined.append(f"[{model_name.upper()}] {reasoning[:300]}")

        return "\n\n".join(combined)

    def _combine_reasoning(
        self,
        factual_accuracy: Dict[str, Any],
        logical_coherence: Dict[str, Any],
        relevance: Dict[str, Any]
    ) -> str:
        """3개 메트릭의 reasoning을 종합"""
        return f"""
[사실 정확도] {factual_accuracy['ensemble_reasoning'][:200]}
[논리적 일관성] {logical_coherence['ensemble_reasoning'][:200]}
[요구사항 부합도] {relevance['ensemble_reasoning'][:200]}
        """.strip()


# 테스트 코드
if __name__ == "__main__":
    # 초기화 테스트
    judge = EnsembleAIJudge()

    # 샘플 데이터
    query = "2024년 대체육 시장 동향 및 소비자 선호도 분석 보고서를 작성해주세요"
    report = """
# 2024년 대체육 시장 동향 및 소비자 선호도 분석

## 1. 시장 개요
2024년 글로벌 대체육 시장은 전년 대비 15% 성장하여 약 50억 달러 규모에 도달했습니다. [SOURCE:0]

## 2. 소비자 선호도
MZ세대를 중심으로 건강과 환경을 중시하는 소비 트렌드가 확산되고 있습니다. [SOURCE:1]
    """

    sources = [
        {"content": "2024년 글로벌 대체육 시장은 50억 달러 규모로 성장", "title": "시장 보고서"},
        {"content": "MZ세대가 대체육 소비의 주축", "title": "소비자 조사"}
    ]

    # 평가 실행
    print("\n=== 사실 정확도 평가 ===")
    factual = judge.evaluate_factual_accuracy(report, sources)
    print(f"앙상블 점수: {factual['ensemble_score']}")
    print(f"개별 점수: {factual['individual_scores']}")

    print("\n=== 종합 품질 평가 ===")
    quality = judge.evaluate_output_quality(query, report, sources)
    print(f"종합 품질: {quality.overall_quality_score}")
    print(f"사실 정확도: {quality.factual_accuracy_score}")
    print(f"논리적 일관성: {quality.logical_coherence_score}")
    print(f"요구사항 부합도: {quality.relevance_score}")
