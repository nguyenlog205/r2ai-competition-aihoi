#!/bin/bash
set -e

echo "=== Unit Tests (Crawler) ==="
pytest tests/preprocessing/test_crawling.py -v

echo "=== Cleaning up any container using port 7687 ==="
CONTAINER_ID=$(docker ps --filter "publish=7687" -q)
if [ -n "$CONTAINER_ID" ]; then
    echo "Stopping and removing container $CONTAINER_ID (uses port 7687)"
    docker stop $CONTAINER_ID
    docker rm $CONTAINER_ID
fi

echo "=== Removing old neo4j-ci container (if exists) ==="
docker rm -f neo4j-ci 2>/dev/null || true

if ss -tlnp | grep -q ':7687'; then
    echo "Port 7687 is occupied by a non-Docker process. Will use port 7688 instead."
    NEO4J_PORT=7688
else
    NEO4J_PORT=7687
fi

echo "=== Start Neo4j container on port $NEO4J_PORT ==="
docker run -d --name neo4j-ci -p $NEO4J_PORT:7687 \
  -e NEO4J_AUTH=neo4j/your_local_password \
  -e NEO4J_PLUGINS='["apoc"]' \
  neo4j:5.15.0

echo "Waiting for Neo4j to be ready..."
sleep 15

echo "=== Integration Tests (using port $NEO4J_PORT) ==="
export NEO4J_PORT
PYTHONPATH=. pytest tests/test_graph_db.py -v

echo "=== Clean up ==="
docker stop neo4j-ci
docker rm neo4j-ci

echo "All tests passed locally."
