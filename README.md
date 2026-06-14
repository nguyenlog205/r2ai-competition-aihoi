# r2ai-competition-aihoi

>This repository houses the development and deployment framework for an advanced MLOps-driven AI Agent system, built specifically by team `AI hỏi` for the `ROAD TO AI` competition. Designed with scalability and production-readiness in mind, the project integrates a robust Retrieval-Augmented Generation (RAG) pipeline with complex multi-agent workflows. The entire repository is architected to transition seamlessly from a local development environment to a cloud-native infrastructure, incorporating robust CI/CD pipelines, containerization, and comprehensive MLOps monitoring to ensure reliable performance throughout the competition and beyond.



## 

### 1. Crawling and preprocessing

#### a. Crawling


#### b. Preprocessing & database loading
```bash
python -m src.pipelines.preprocessing.main

python -m src.database.loaders.load_to_postgres

python -m src.database.loaders.compute_embeddings
```



```bash
python -m src.pipelines.evaluation.retrieve_candidates \
    --test-questions data/test/R2AIStage1DATA.json \
    --output data/test/retrieved_chunks.json \
    --top-k 5 \
    --rerank
```

```bash
python -m src.pipelines.evaluation.generate_answers \
    --input retrieved_chunks.json \
    --output results.json \
    --answer-strategy top_chunk

```