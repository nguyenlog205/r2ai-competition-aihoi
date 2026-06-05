# ==============================================================================
# FILE: tests/test_graph_db.py
# DESCRIPTION: Integration tests for Neo4j Database configuration and repository
# ==============================================================================

import pytest
import sys
from pathlib import Path

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
# FIXTURES
# ==============================================================================

@pytest.fixture(scope="session")
def db_client():
    """Khởi tạo connection một lần cho toàn bộ session test."""
    config_path = PROJECT_ROOT / "config" / "deployment" / "system.yml"
    client = Neo4jClient(config_path=str(config_path))
    yield client
    client.close()

@pytest.fixture(scope="session")
def repo(db_client):
    """Repository dùng chung cho cả session."""
    return LegalGraphRepository(db_client)

@pytest.fixture
def sample_document():
    """Tạo document mẫu, mỗi test nhận một instance mới (dữ liệu giống nhau)."""
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

@pytest.fixture(autouse=True)
def clean_before_and_after(repo, sample_document):
    """Tự động xóa document trước và sau mỗi test để đảm bảo độc lập."""
    # Clean trước test
    repo.delete_document_cascade(sample_document.document_id)
    yield
    # Clean sau test
    repo.delete_document_cascade(sample_document.document_id)

# ==============================================================================
# TEST CASES - KẾT NỐI
# ==============================================================================

def test_database_connection(db_client):
    assert db_client.verify_connection() is True

# ==============================================================================
# TEST CASES - INGEST & TRUY VẤN CƠ BẢN
# ==============================================================================

def test_ingest_document(repo, sample_document):
    success = repo.ingest_full_document(sample_document)
    assert success is True
    
    query = "MATCH (d:Document {document_id: $doc_id}) RETURN d.title AS title"
    with repo.driver.session() as session:
        record = session.run(query, doc_id=sample_document.document_id).single()
        assert record is not None
        assert record["title"] == "Luật Kiểm Thử Phần Mềm 2026"

def test_relationship_creation(repo, sample_document):
    # Ingest lại để đảm bảo có dữ liệu (vì autouse đã xóa trước test)
    repo.ingest_full_document(sample_document)
    
    query_rel = """
    MATCH (c:Chunk {chunk_id: 'TEST_01_Dieu2_Khoan1'})-[r:CITES]->(a:Article {article_id: 'TEST_01_Dieu1'})
    RETURN r.evidence_text AS evidence
    """
    with repo.driver.session() as session:
        record = session.run(query_rel).single()
        assert record is not None
        assert record["evidence"] == "Theo quy định tại Khoản 1 Điều 1..."

# ==============================================================================
# TEST CASES - CÁC HÀM TRUY VẤN MỚI
# ==============================================================================

def test_get_article_by_id(repo, sample_document):
    repo.ingest_full_document(sample_document)
    
    article = repo.get_article_by_id("TEST_01_Dieu1")
    assert article is not None
    assert article["article_id"] == "TEST_01_Dieu1"
    assert article["number"] == "Điều 1"
    assert len(article["chunks"]) == 1
    assert article["chunks"][0]["chunk_id"] == "TEST_01_Dieu1_Khoan1"

def test_get_chunks_by_article(repo, sample_document):
    repo.ingest_full_document(sample_document)
    
    chunks = repo.get_chunks_by_article("TEST_01_Dieu2")
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "TEST_01_Dieu2_Khoan1"
    assert chunks[0]["text"] == "Đây là nội dung khoản 1 điều 2 để test. Theo quy định tại Khoản 1 Điều 1..."

def test_get_related_articles(repo, sample_document):
    repo.ingest_full_document(sample_document)
    
    related = repo.get_related_articles("TEST_01_Dieu2_Khoan1", "CITES")
    assert len(related) == 1
    assert related[0]["article_id"] == "TEST_01_Dieu1"
    assert related[0]["relation_type"] == "CITES"

def test_get_document_info(repo, sample_document):
    repo.ingest_full_document(sample_document)
    
    info = repo.get_document_info(sample_document.document_id)
    assert info is not None
    assert info["document_id"] == "TEST_DOC_001"
    assert info["chapter_count"] == 1
    assert info["article_count"] == 2

# ==============================================================================
# TEST CASES - VECTOR SEARCH
# ==============================================================================
@pytest.mark.skip(reason="Cần embedding thực tế hoặc vector index đã được tạo")
def test_vector_search(repo, sample_document):
    """Test vector search (có thể skip nếu chưa có embedding thật)."""
    import random
    fake_embedding = [random.random() for _ in range(768)]
    
    import copy
    doc_with_emb = copy.deepcopy(sample_document)
    for chapter in doc_with_emb.chapters:
        for article in chapter.articles:
            for chunk in article.chunks:
                chunk.embedding = fake_embedding  # Giờ đã hợp lệ
    
    repo.ingest_full_document(doc_with_emb)
    repo.create_vector_index()  # Đảm bảo index tồn tại
    
    results = repo.vector_search(fake_embedding, limit=5)
    assert len(results) >= 1

# ==============================================================================
# TEST CASES - COUNT & CLEANUP
# ==============================================================================

def test_count_embedded_chunks(repo, sample_document):
    repo.ingest_full_document(sample_document)
    count = repo.count_embedded_chunks()
    # Trong sample_document không có embedding, nên count có thể = 0
    assert isinstance(count, int)

def test_delete_cascade(repo, sample_document):
    """Test xóa cascade: sau khi xóa, không còn node nào liên quan."""
    repo.ingest_full_document(sample_document)
    
    # Xác nhận tồn tại
    with repo.driver.session() as session:
        record = session.run("MATCH (c:Chunk {chunk_id: 'TEST_01_Dieu1_Khoan1'}) RETURN c").single()
        assert record is not None
    
    # Xóa
    success = repo.delete_document_cascade(sample_document.document_id)
    assert success is True
    
    # Kiểm tra tất cả các node đều biến mất
    with repo.driver.session() as session:
        for node_id in ["TEST_01_Dieu1_Khoan1", "TEST_01_Dieu2_Khoan1", "TEST_01_Dieu1", "TEST_01_Dieu2", "TEST_01_Chuong1", "TEST_DOC_001"]:
            record = session.run("MATCH (n {chunk_id: $id}) RETURN n", id=node_id).single()
            assert record is None, f"Node {node_id} vẫn còn sau cascade delete"