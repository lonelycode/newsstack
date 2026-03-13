from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "NEWSSTACK_"}

    # Embedding server
    embedding_url: str = "http://localhost:9097/v1/embeddings"
    embedding_model: str = "nomic-embed-text-v1.5"
    embedding_dim: int = 768
    embedding_max_chars: int = 1500  # truncate input text to fit server's token batch limit

    # LLM server
    llm_url: str = "http://localhost:9096/v1/chat/completions"
    llm_model: str = "qwen3.5"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"

    # SQLite
    db_path: str = "newsstack.db"

    # Server
    host: str = "0.0.0.0"
    port: int = 8080

    # Data retention
    retention_days: int = 180

    # Scheduling intervals (seconds)
    rss_interval: int = 300
    gdelt_interval: int = 600
    clustering_interval: int = 900

    # Clustering
    hdbscan_min_cluster_size: int = 3

    # Dedup thresholds
    simhash_threshold: int = 3  # max hamming distance
    vector_dedup_threshold: float = 0.95
