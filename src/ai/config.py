from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

config = {
    "chat_name": {
        "provider": "openai",
        "model": "gpt-4.1-nano",
        "max_tokens": 30,
        "max_retries": 2,
    },
    "chat": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "max_retries": 2,
    },
}


@lru_cache(maxsize=2)
def get_llm(purpose: str):
    model_config = config[purpose]
    provider = model_config["provider"]

    providers = {
        "openai": ChatOpenAI,
        "anthropic": ChatAnthropic,
        "google": ChatGoogleGenerativeAI,
    }

    if provider not in providers:
        raise ValueError(f"Invalid provider: {provider}")

    llm_class = providers[provider]
    params = {
        "model": model_config["model"],
        "max_tokens": model_config.get("max_tokens", None),
        "max_retries": model_config.get("max_retries", 2),
    }

    return llm_class(**params)
