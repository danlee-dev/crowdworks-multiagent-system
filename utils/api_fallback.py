# api_fallback.py
"""
3개 API 키 순차 시도 및 fallback 로직을 통합 관리하는 유틸리티
모든 프로젝트 파일에서 이 클래스를 import해서 사용
"""
import os
from typing import Optional, Any, List, Union
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
import google.generativeai as genai
from openai import OpenAI


class UnifiedAPIManager:
    """
    통합 API 키 관리 및 fallback 시스템
    GEMINI_KEY_1 -> GEMINI_KEY_2 -> GOOGLE_API_KEY -> OPENAI_API_KEY 순으로 시도
    """
    
    def __init__(self):
        # 모든 API 키를 환경변수에서 로드
        self.gemini_key_1 = os.getenv("GEMINI_API_KEY_1")
        self.gemini_key_2 = os.getenv("GEMINI_API_KEY_2") 
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # 사용 가능한 API 키 순서 정의
        self.api_keys = [
            ("GEMINI_1", self.gemini_key_1),
            ("GEMINI_2", self.gemini_key_2),
            ("GOOGLE", self.google_api_key),
            ("OPENAI", self.openai_api_key)
        ]
        
        # 로그를 위한 설정
        self.last_successful_api = None
        self.api_usage_count = {
            "GEMINI_1": 0,
            "GEMINI_2": 0, 
            "GOOGLE": 0,
            "OPENAI": 0
        }
    
    def get_available_apis(self) -> List[str]:
        """사용 가능한 API 키 목록 반환"""
        return [name for name, key in self.api_keys if key]
    
    def create_langchain_model(self, model_name: str = "gemini-2.5-flash", **kwargs) -> Any:
        """
        LangChain 모델을 3개 키 + OpenAI fallback으로 생성
        """
        # Gemini/Google API 키들 시도
        for api_name, api_key in self.api_keys[:3]:  # 처음 3개는 Google 계열
            if api_key:
                try:
                    model = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=api_key,
                        **kwargs
                    )
                    self.last_successful_api = api_name
                    self.api_usage_count[api_name] += 1
                    print(f"✅ {api_name} API로 LangChain 모델 생성 성공: {model_name}")
                    return model
                except Exception as e:
                    print(f"❌ {api_name} API 실패: {e}")
                    continue
        
        # OpenAI fallback
        if self.openai_api_key:
            try:
                # Gemini 모델명을 OpenAI 모델명으로 매핑
                openai_model_map = {
                    "gemini-2.5-pro": "gpt-4o",
                    "gemini-2.5-flash": "gpt-4o-mini",
                    "gemini-2.5-flash-lite": "gpt-3.5-turbo",
                    "gemini-1.5-pro": "gpt-4o"
                }
                openai_model = openai_model_map.get(model_name, "gpt-4o-mini")
                
                model = ChatOpenAI(
                    model=openai_model,
                    openai_api_key=self.openai_api_key,
                    **kwargs
                )
                self.last_successful_api = "OPENAI"
                self.api_usage_count["OPENAI"] += 1
                print(f"✅ OpenAI fallback 성공: {openai_model} (원래 요청: {model_name})")
                return model
            except Exception as e:
                print(f"❌ OpenAI fallback 실패: {e}")
        
        raise Exception("🚨 모든 API 키 실패: Gemini 3개 + OpenAI 모두 사용 불가")
    
    def invoke_with_fallback(self, prompt: str, model_name: str = "gemini-2.5-flash", **kwargs) -> str:
        """
        프롬프트를 3개 키 + OpenAI fallback으로 실행
        """
        # Google 계열 API들 시도
        for api_name, api_key in self.api_keys[:3]:
            if api_key:
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    
                    self.last_successful_api = api_name
                    self.api_usage_count[api_name] += 1
                    print(f"✅ {api_name} API 직접 호출 성공: {model_name}")
                    return response.text
                except Exception as e:
                    print(f"❌ {api_name} API 실패: {e}")
                    continue
        
        # OpenAI fallback
        if self.openai_api_key:
            try:
                client = OpenAI(api_key=self.openai_api_key)
                
                # Gemini 모델명을 OpenAI로 변환
                openai_model_map = {
                    "gemini-2.5-pro": "gpt-4o",
                    "gemini-2.5-flash": "gpt-4o-mini", 
                    "gemini-2.5-flash-lite": "gpt-3.5-turbo",
                    "gemini-1.5-pro": "gpt-4o"
                }
                openai_model = openai_model_map.get(model_name, "gpt-4o-mini")
                
                response = client.chat.completions.create(
                    model=openai_model,
                    messages=[{"role": "user", "content": prompt}],
                    **kwargs
                )
                
                self.last_successful_api = "OPENAI"
                self.api_usage_count["OPENAI"] += 1
                print(f"✅ OpenAI fallback 성공: {openai_model}")
                return response.choices[0].message.content
            except Exception as e:
                print(f"❌ OpenAI fallback 실패: {e}")
        
        raise Exception("🚨 모든 API 키 실패: Gemini 3개 + OpenAI 모두 사용 불가")
    
    def get_status_report(self) -> dict:
        """API 사용 현황 리포트"""
        return {
            "available_apis": self.get_available_apis(),
            "last_successful": self.last_successful_api,
            "usage_count": self.api_usage_count,
            "total_requests": sum(self.api_usage_count.values())
        }
    
    def test_all_apis(self) -> dict:
        """모든 API 키 테스트"""
        results = {}
        test_prompt = "Hello, test message"
        
        for api_name, api_key in self.api_keys:
            if not api_key:
                results[api_name] = {"status": "missing", "error": "API key not found"}
                continue
                
            try:
                if api_name == "OPENAI":
                    client = OpenAI(api_key=api_key)
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": test_prompt}],
                        max_tokens=10
                    )
                    results[api_name] = {"status": "success", "response_length": len(response.choices[0].message.content)}
                else:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    response = model.generate_content(test_prompt)
                    results[api_name] = {"status": "success", "response_length": len(response.text)}
                    
            except Exception as e:
                results[api_name] = {"status": "error", "error": str(e)}
        
        return results


# 전역 인스턴스 생성 (싱글톤 패턴)
api_manager = UnifiedAPIManager()

# 편의 함수들
def create_model(model_name: str = "gemini-2.5-flash", **kwargs):
    """빠른 모델 생성"""
    return api_manager.create_langchain_model(model_name, **kwargs)

def invoke_prompt(prompt: str, model_name: str = "gemini-2.5-flash", **kwargs) -> str:
    """빠른 프롬프트 실행"""
    return api_manager.invoke_with_fallback(prompt, model_name, **kwargs)

def get_api_status() -> dict:
    """API 상태 확인"""
    return api_manager.get_status_report()

def test_apis() -> dict:
    """모든 API 테스트"""
    return api_manager.test_all_apis()


if __name__ == "__main__":
    # 테스트 실행
    print("🚀 API Fallback Manager 테스트")
    print("=" * 50)
    
    print("\n📊 사용 가능한 API:")
    available = api_manager.get_available_apis()
    print(f"  {available}")
    
    print("\n🧪 API 테스트 결과:")
    test_results = test_apis()
    for api_name, result in test_results.items():
        status_icon = "✅" if result["status"] == "success" else "❌"
        print(f"  {status_icon} {api_name}: {result['status']}")
        if result["status"] == "error":
            print(f"    오류: {result['error']}")
    
    print("\n💬 간단 테스트:")
    try:
        response = invoke_prompt("안녕하세요", "gemini-2.5-flash")
        print(f"  응답: {response[:100]}...")
        print(f"\n📈 사용 현황: {get_api_status()}")
    except Exception as e:
        print(f"  실패: {e}")