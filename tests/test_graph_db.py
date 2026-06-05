# ==============================================================================
# FILE: tests/test_graph_db.py
# DESCRIPTION: Integration tests for Neo4j Database configuration and repository
# ==============================================================================

import pytest
import os
import sys
from pathlib import Path

# Đảm bảo Python nhận diện được thư mục src/ khi chạy test
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.database.utils.database_client import Neo4jClient
from src.database.utils.graph_repository import LegalGraphRepository
from src.schema.legal_schema import (
    LegalDocumentExtraction, 
    ChapterNode, 
    ArticleNode, 
    ChunkNode,
    LegalRelationship
)

# ==============================================================================
# FIXTURES (DỮ LIỆU VÀ MÔI TRƯỜNG MẪU DÙNG CHUNG CHO CÁC TEST)
# ==============================================================================

@pytest.fixture(scope="module")
def db_client():
    """Khởi tạo connection một lần duy nhất cho toàn bộ file test."""
    config_path = PROJECT_ROOT / "config" / "deployment" / "system.yml"
    client = Neo4jClient(config_path=str(config_path))
    yield client
    # Clean up: Đóng kết nối sau khi tất cả các test chạy xong
    client.close()

@pytest.fixture(scope="module")
def repo(db_client):
    """Khởi tạo Repository."""
    return LegalGraphRepository(db_client)

@pytest.fixture
def sample_document():
    """Tạo một văn bản pháp luật giả lập chuẩn Pydantic để test."""
    chunk1 = ChunkNode(
        chunk_id="TEST_01_Dieu1_Khoan1",
        chunk_type="Clause",
        chunk_index="1",
        text="Đây là nội dung khoản 1 điều 1 để test."
    )
    chunk2 = ChunkNode(
        chunk_id="TEST_01_Dieu2_Khoan1",
        chunk_type="Clause",
        chunk_index="1",
        text="Đây là nội dung khoản 1 điều 2 để test. Theo quy định tại Khoản 1 Điều 1..."
    )
    
    article1 = ArticleNode(
        article_id="TEST_01_Dieu1",
        number="Điều 1",
        title="Phạm vi điều chỉnh",
        chunks=[chunk1]
    )
    article2 = ArticleNode(
        article_id="TEST_01_Dieu2",
        number="Điều 2",
        title="Đối tượng áp dụng",
        chunks=[chunk2]
    )
    
    chapter1 = ChapterNode(
        chapter_id="TEST_01_Chuong1",
        name="Chương I",
        title="Quy định chung",
        articles=[article1, article2]
    )
    
    # Giả lập Điều 2 dẫn chiếu tới Điều 1
    relationship = LegalRelationship(
        source_chunk_id="TEST_01_Dieu2_Khoan1",
        target_article_id="TEST_01_Dieu1",
        relation_type="CITES",
        evidence_text="Theo quy định tại Khoản 1 Điều 1..."
    )

    return LegalDocumentExtraction(
        document_id="TEST_DOC_001",
        document_type="Luật",
        document_title="Luật Kiểm Thử Phần Mềm 2026",
        chapters=[chapter1],
        relationships=[relationship]
    )

# ==============================================================================
# TEST CASES
# ==============================================================================

def test_database_connection(db_client):
    """TEST 1: Kiểm tra xem có kết nối được tới Docker Neo4j không."""
    assert db_client.verify_connection() is True

def test_ingest_document(repo, sample_document):
    """TEST 2: Kiểm tra chức năng ghi dữ liệu vào Neo4j."""
    # 1. Đảm bảo DB sạch sẽ (xóa doc test nếu có từ trước)
    repo.delete_document_cascade(sample_document.document_id)
    
    # 2. Thực thi hàm ghi
    success = repo.ingest_full_document(sample_document)
    assert success is True, "Hàm ingest_full_document trả về False"

    # 3. Query ngược lại Database để xác minh Node đã được tạo
    query_verify = "MATCH (d:Document {document_id: $doc_id}) RETURN d.title AS title"
    with repo.driver.session() as session:
        result = session.run(query_verify, doc_id=sample_document.document_id)
        record = result.single()
        assert record is not None, "Không tìm thấy Document trong DB"
        assert record["title"] == "Luật Kiểm Thử Phần Mềm 2026"

def test_relationship_creation(repo, sample_document):
    """TEST 3: Kiểm tra xem mũi tên CITES có được vẽ đúng không."""
    query_rel = """
    MATCH (c:Chunk {chunk_id: 'TEST_01_Dieu2_Khoan1'})-[r:CITES]->(a:Article {article_id: 'TEST_01_Dieu1'})
    RETURN r.evidence_text AS evidence
    """
    with repo.driver.session() as session:
        result = session.run(query_rel)
        record = result.single()
        assert record is not None, "Mũi tên CITES không được tạo thành công"
        assert record["evidence"] == "Theo quy định tại Khoản 1 Điều 1..."

def test_delete_cascade(repo, sample_document):
    """TEST 4: Kiểm tra chức năng xóa phân tầng (Clean up)."""
    success = repo.delete_document_cascade(sample_document.document_id)
    assert success is True
    
    query_verify = "MATCH (c:Chunk {chunk_id: 'TEST_01_Dieu1_Khoan1'}) RETURN c"
    with repo.driver.session() as session:
        result = session.run(query_verify)
        record = result.single()
        assert record is None, "Node Chunk vẫn còn tồn tại sau khi xóa Document! Lỗi Cascade."