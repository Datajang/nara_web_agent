from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_model_name: str = "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct"
    secret_key: str = "dev-secret-key"
    access_token_expire_minutes: int = 480
    db_path: str = "/data/nara.db"
    nara_api_key: str = ""
    nara_prespec_api_key: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
