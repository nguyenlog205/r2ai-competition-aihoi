import pytest
from src.database.utils.database_client import Neo4jClient

@pytest.fixture(scope="session")
def db_client():
    client = Neo4jClient(env="development")
    yield client
    client.close()

def test_neo4j_connection(db_client):
    """Kiểm tra kết nối tới Neo4j có thành công không."""
    assert db_client.verify_connection() is True, "Không thể kết nối tới Neo4j"