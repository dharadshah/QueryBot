from groq import Groq
from openai import OpenAI
from app.config import settings


def get_llm_client():
    if settings.llm_provider == "openai":
        return OpenAI(api_key=settings.openai_api_key)
    return Groq(api_key=settings.groq_api_key)