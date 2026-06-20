"""테스트 격리 — LLM을 항상 '템플릿 모드'로 고정.

단위 테스트는 오프라인·결정적이어야 한다. .env 나 환경에 LLM_PROVIDER=gpt-5.5 /
OPENAI_API_KEY 가 설정돼 있어도, 테스트가 실제 OpenAI API를 호출하면 안 된다
(느림·과금·비결정적). pytest 수집 전에 환경을 고정하고 settings 싱글톤도 덮어쓴다.
"""
import os

os.environ["LLM_PROVIDER"] = "template"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

try:  # config 가 이미 임포트됐다면 싱글톤도 강제 정정
    import config
    config.settings.llm_provider = "template"
    config.settings.openai_api_key = ""
except Exception:
    pass
