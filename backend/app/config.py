from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "CoachOS"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Supabase (Free Tier Database & Auth)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = "" # Enforces true cryptographic signature decoding

    # Stripe
    STRIPE_API_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # LLM (Using LiteLLM to route to free-tier models like Gemini 1.5 Flash)
    GEMINI_API_KEY: str = ""

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
