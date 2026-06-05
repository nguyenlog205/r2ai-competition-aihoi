import pytest
import sys
import numpy as np
from pathlib import Path

# Cấu hình đường dẫn
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.database.utils.database_client import Neo4jClient
from src.database.utils.graph_repository import LegalGraphRepository
from src.pipelines.embedding.utils.vector_engine import VectorEngine

@pytest.fixture(scope="module")
def vector_engine():
    """Khởi tạo engine với cấu hình từ file YAML."""
    # Đảm bảo đường dẫn config trỏ đúng tới config/deployment/system.yml
    return VectorEngine(config_path=str(PROJECT_ROOT / "config" / "deployment" / "system.yml"))

@pytest.fixture(scope="module")
def db_repo():
    """Khởi tạo repository."""
    config_path = PROJECT_ROOT / "config" / "deployment" / "system.yml"
    client = Neo4jClient(config_path=str(config_path))
    repo = LegalGraphRepository(client)
    repo.create_vector_index()
    yield repo
    client.close()

def test_ensemble_vector_generation(vector_engine):
    """Test 1: Kiểm tra vector sau khi ensemble vẫn đúng chiều (mặc định 768)."""
    text = "Kiểm thử phần mềm là quy trình bắt buộc."
    vector = vector_engine.embed_text(text)
    
    assert isinstance(vector, list)
    # Với strategy 'mean' và các model cùng dimension 768, kết quả phải là 768
    assert len(vector) == 768
    assert all(isinstance(x, float) for x in vector[:10])

def test_ensemble_strategy_logic(vector_engine):
    """Test 2: Kiểm tra logic tính toán của ensemble (ví dụ: trung bình cộng)."""
    text = "Test logic ensemble."
    
    # Giả lập logic tính tay
    vectors = [model.encode(text) for model in vector_engine.models]
    expected_mean = np.mean(vectors, axis=0).tolist()
    
    actual_vector = vector_engine.embed_text(text)
    
    # Kiểm tra sai số cho phép (floating point precision)
    assert np.allclose(actual_vector, expected_mean, atol=1e-6)

def test_vector_storage_with_ensemble(db_repo, vector_engine):
    """Test 3: Kiểm tra việc lưu vector đã ensemble vào Neo4j."""
    test_text = "Quy định về bảo mật."
    vector = vector_engine.embed_text(test_text)
    
    chunk_id = "TEST_ENSEMBLE_001"
    
    # Lưu vào database
    with db_repo.driver.session() as session:
        session.run("""
            MERGE (c:Chunk {chunk_id: $id})
            SET c.embedding = $vector
        """, id=chunk_id, vector=vector)
    
    # Xác thực bằng cách query lại
    with db_repo.driver.session() as session:
        result = session.run("MATCH (c:Chunk {chunk_id: $id}) RETURN c.embedding AS vec", id=chunk_id)
        record = result.single()
        assert record is not None
        assert len(record["vec"]) == 768

    # =========================================   
    # Dọn dẹp
    # =========================================
    with db_repo.driver.session() as session:
        session.run("MATCH (c:Chunk {chunk_id: $id}) DETACH DELETE c", id=chunk_id)