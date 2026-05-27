from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    mssql_server: str
    mssql_database: str
    mssql_username: str
    mssql_password: str
    mssql_driver: str = "ODBC Driver 17 for SQL Server"
    mssql_use_windows_auth: bool = False


    # OpenAI
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"

    # Groq
    groq_api_key: str
    groq_chat_model: str = "llama-3.3-70b-versatile"

    # RAG
    chroma_persist_path: str = "chroma_store"
    chroma_collection_name: str = "ecommerce_schema"
    top_k_chunks: int = 5

    # Agent
    max_retries: int = 3
    max_rows: int = 20

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    model_config = {"env_file": ".env"}

    @property
    def db_connection_string(self) -> str:
        if self.mssql_use_windows_auth:
            return (
                f"mssql+pyodbc://{self.mssql_server}/{self.mssql_database}"
                f"?driver={self.mssql_driver.replace(' ', '+')}"
                f"&trusted_connection=yes"
                f"&TrustServerCertificate=yes"
            )
        return (
            f"mssql+pyodbc://{self.mssql_username}:{self.mssql_password}"
            f"@{self.mssql_server}/{self.mssql_database}"
            f"?driver={self.mssql_driver.replace(' ', '+')}"
            f"&TrustServerCertificate=yes"
        )


settings = Settings()