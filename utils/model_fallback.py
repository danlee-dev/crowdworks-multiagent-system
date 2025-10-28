# model_fallback.py
import os
from typing import Optional, Any, Callable
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

class ModelFallbackManager:
    """
    Gemini API 키 2개를 순차적으로 시도하고, 실패 시 OpenAI로 fallback하는 매니저
    """

    # Gemini API 키들 (환경변수에서 로드)
    GEMINI_KEY_1 = os.getenv("GEMINI_API_KEY_1")
    GEMINI_KEY_2 = os.getenv("GEMINI_API_KEY_2")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # 3번째 fallback

    @classmethod
    def create_gemini_model(cls, model_name: str = "gemini-2.5-flash", **kwargs) -> Optional[ChatGoogleGenerativeAI]:
        """
        Gemini 모델을 생성합니다. 3개 키를 순차적으로 시도
        """
        # 첫 번째 Gemini 키 시도
        if cls.GEMINI_KEY_1:
            try:
                return ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=cls.GEMINI_KEY_1,
                    **kwargs
                )
            except Exception as e:
                print(f"Gemini 키 1 실패: {e}")

        # 두 번째 Gemini 키 시도
        if cls.GEMINI_KEY_2:
            try:
                return ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=cls.GEMINI_KEY_2,
                    **kwargs
                )
            except Exception as e:
                print(f"Gemini 키 2 실패: {e}")

        # 세 번째 Google API 키 시도
        if cls.GOOGLE_API_KEY:
            try:
                return ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=cls.GOOGLE_API_KEY,
                    **kwargs
                )
            except Exception as e:
                print(f"Google API 키 실패: {e}")

        return None

    @classmethod
    def create_openai_model(cls, model_name: str = "gpt-4o-mini", **kwargs) -> Optional[ChatOpenAI]:
        """
        OpenAI 모델을 생성합니다.
        """
        try:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                print("OPENAI_API_KEY가 설정되지 않음")
                return None

            return ChatOpenAI(
                model=model_name,
                openai_api_key=openai_api_key,
                **kwargs
            )
        except Exception as e:
            print(f"OpenAI 모델 생성 실패: {e}")
            return None

    @classmethod
    def create_fallback_model(cls, gemini_model: str = "gemini-2.5-flash", openai_model: str = "gpt-4o-mini", **kwargs):
        """
        Gemini -> OpenAI 순으로 fallback 모델을 생성
        """
        # Gemini 시도
        model = cls.create_gemini_model(gemini_model, **kwargs)
        if model:
            print(f"Gemini 모델 생성 성공: {gemini_model}")
            return model

        # OpenAI 시도
        model = cls.create_openai_model(openai_model, **kwargs)
        if model:
            print(f"OpenAI fallback 모델 생성 성공: {openai_model}")
            return model

        raise Exception("모든 모델 생성 실패: Gemini 키 2개와 OpenAI 모두 실패")

    @classmethod
    def try_invoke_with_fallback(cls, prompt: str, gemini_model: str = "gemini-1.5-flash", openai_model: str = "gpt-4o-mini", **kwargs) -> str:
        """
        Gemini 키 2개 -> OpenAI 순으로 invoke 시도
        """
        # Gemini 키 1 시도
        try:
            model = ChatGoogleGenerativeAI(
                model=gemini_model,
                google_api_key=cls.GEMINI_KEY_1,
                **kwargs
            )
            result = model.invoke(prompt)
            print(f"Gemini 키 1 성공: {gemini_model}")
            return result.content
        except Exception as e:
            print(f"Gemini 키 1 실패: {e}")

        # Gemini 키 2 시도
        try:
            model = ChatGoogleGenerativeAI(
                model=gemini_model,
                google_api_key=cls.GEMINI_KEY_2,
                **kwargs
            )
            result = model.invoke(prompt)
            print(f"Gemini 키 2 성공: {gemini_model}")
            return result.content
        except Exception as e:
            print(f"Gemini 키 2 실패: {e}")

        # OpenAI 시도
        try:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise Exception("OPENAI_API_KEY가 설정되지 않음")

            model = ChatOpenAI(
                model=openai_model,
                openai_api_key=openai_api_key,
                **kwargs
            )
            result = model.invoke(prompt)
            print(f"OpenAI fallback 성공: {openai_model}")
            return result.content
        except Exception as e:
            print(f"OpenAI fallback 실패: {e}")
            raise Exception(f"모든 모델 시도 실패: Gemini 키 2개와 OpenAI 모두 실패")


# OpenAI Client를 위한 Fallback Manager (OpenAI SDK 직접 사용하는 경우)
from openai import OpenAI
from google.generativeai import GenerativeModel
import google.generativeai as genai

class OpenAIClientFallbackManager:
    """
    OpenAI SDK를 직접 사용하는 코드를 위한 Fallback Manager
    """

    # Gemini API 키들
    GEMINI_KEY_1 = os.getenv("GEMINI_API_KEY_1")
    GEMINI_KEY_2 = os.getenv("GEMINI_API_KEY_2")

    @classmethod
    def chat_completions_create_with_fallback(cls, model: str, messages: list, **kwargs) -> str:
        """
        OpenAI의 client.chat.completions.create()를 Gemini fallback으로 대체
        """
        # Gemini 모델명이 직접 전달된 경우 그대로 사용
        if model.startswith("gemini-"):
            gemini_model = model
        else:
            # GPT 모델명을 Gemini로 매핑
            gemini_model_map = {
                # 고성능 작업 - 2.5 Pro (최신 성능, 1M context)
                "gpt-4": "gemini-2.5-pro",
                "gpt-4o": "gemini-2.5-pro",

                # 중간 작업 - 2.5 Flash (균형, 1M context)
                "gpt-4o-mini": "gemini-2.5-flash",

                # 가벼운 작업 - 2.5 Flash Lite (빠름, 1M context)
                "gpt-3.5-turbo": "gemini-2.5-flash-lite",
                "gpt-4.1-nano": "gemini-2.5-flash-lite",  # 잘못된 모델명 수정

                # 대용량 문서 처리 - 2.5 Pro (2M context)
                "gpt-4-long-context": "gemini-2.5-pro",
                "document-analysis": "gemini-2.5-pro"
            }
            gemini_model = gemini_model_map.get(model, "gemini-2.5-flash")

        # 메시지를 텍스트로 변환
        if isinstance(messages, list) and len(messages) > 0:
            # 마지막 메시지의 content를 사용
            prompt = messages[-1].get("content", "") if isinstance(messages[-1], dict) else str(messages[-1])
        else:
            prompt = str(messages)

        # Gemini 키 1 시도
        try:
            genai.configure(api_key=cls.GEMINI_KEY_1)
            model_instance = GenerativeModel(gemini_model)
            response = model_instance.generate_content(prompt)
            print(f"Gemini 키 1 성공: {gemini_model}")
            return response.text
        except Exception as e:
            print(f"Gemini 키 1 실패: {e}")

        # Gemini 키 2 시도
        try:
            genai.configure(api_key=cls.GEMINI_KEY_2)
            model_instance = GenerativeModel(gemini_model)
            response = model_instance.generate_content(prompt)
            print(f"Gemini 키 2 성공: {gemini_model}")
            return response.text
        except Exception as e:
            print(f"Gemini 키 2 실패: {e}")

        # OpenAI 시도
        try:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise Exception("OPENAI_API_KEY가 설정되지 않음")

            client = OpenAI(api_key=openai_api_key)
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                **kwargs
            )
            print(f"OpenAI fallback 성공: {model}")
            return response.choices[0].message.content
        except Exception as e:
            print(f"OpenAI fallback 실패: {e}")
            raise Exception(f"모든 모델 시도 실패: Gemini 키 2개와 OpenAI 모두 실패")
