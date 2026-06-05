# ==============================================================================
# FILE: src/database/graph_repository.py
# DESCRIPTION: Repository layer to handle CRUD operations and Vector Search for Legal Graph
# ==============================================================================

import logging
from typing import List, Dict, Any, Optional, Set
from src.database.utils.database_client import Neo4jClient

logger = logging.getLogger(__name__)

# Whitelist các loại quan hệ hợp lệ để tránh Cypher injection
ALLOWED_RELATION_TYPES: Set[str] = {
    "REFERENCES", "AMENDS", "CITES", "SUPERSEDES", "INTERPRETS", "EXCEPTIONS"
}

class LegalGraphRepository:
    """
    Data Access Layer (DAL) xử lý các thao tác đồ thị.
    Tách biệt logic nghiệp vụ khỏi các câu lệnh Cypher.
    Phiên bản tối ưu: batch write, whitelist, xử lý lỗi.
    """
    def __init__(self, db_client: Neo4jClient):
        self.driver = db_client.driver

    # -------------------------------------------------------------------------
    # 1. HÀM INGEST DỮ LIỆU (CREATE/MERGE) - TỐI ƯU BATCH
    # -------------------------------------------------------------------------
    def ingest_full_document(self, doc_data: Any) -> bool:
        """Nạp toàn bộ cấu trúc văn bản vào Neo4j bằng batch UNWIND."""
        # Convert sang dict (hỗ trợ Pydantic model hoặc dict)
        if hasattr(doc_data, 'model_dump'):
            data_dict = doc_data.model_dump()
        elif hasattr(doc_data, 'dict'):
            data_dict = doc_data.dict()
        else:
            data_dict = doc_data

        # Validate dữ liệu cơ bản
        if 'document_id' not in data_dict:
            logger.error("Thiếu document_id trong dữ liệu đầu vào")
            return False

        try:
            with self.driver.session() as session:
                session.execute_write(self._tx_ingest_document_tree_batch, data_dict)
            logger.info(f"Đã nạp thành công tài liệu: {data_dict.get('document_id')}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi nạp tài liệu {data_dict.get('document_id')}: {e}", exc_info=True)
            return False

    @staticmethod
    def _tx_ingest_document_tree_batch(tx, data: Dict[str, Any]):
        # 1. Tạo Document
        tx.run("""
            MERGE (d:Document {document_id: $doc_id})
            SET d.title = $title, d.type = $type
        """, doc_id=data['document_id'], title=data.get('document_title', ''), 
               type=data.get('document_type', 'unknown'))

        # 2. Chuẩn bị dữ liệu batch cho Chapters và Articles
        chapters_list = []
        articles_list = []
        chunks_list = []
        
        for chapter in data.get('chapters', []):
            # Chapter
            chap_id = chapter['chapter_id']
            chapters_list.append({
                'chap_id': chap_id,
                'name': chapter.get('name', ''),
                'title': chapter.get('title', ''),
                'doc_id': data['document_id']
            })
            
            for article in chapter.get('articles', []):
                art_id = article['article_id']
                articles_list.append({
                    'art_id': art_id,
                    'number': article.get('number', ''),
                    'title': article.get('title', ''),
                    'status': 'Đang có hiệu lực',
                    'chap_id': chap_id
                })
                
                for chunk in article.get('chunks', []):
                    chunks_list.append({
                        'chunk_id': chunk['chunk_id'],
                        'chunk_type': chunk.get('chunk_type', 'text'),
                        'chunk_index': chunk.get('chunk_index', 0),
                        'text': chunk.get('text', ''),
                        'embedding': chunk.get('embedding'),
                        'art_id': art_id
                    })
        
        # Batch tạo Chapters
        if chapters_list:
            tx.run("""
                UNWIND $chapters AS ch
                MATCH (d:Document {document_id: ch.doc_id})
                MERGE (c:Chapter {chapter_id: ch.chap_id})
                SET c.name = ch.name, c.title = ch.title
                MERGE (d)-[:HAS_CHAPTER]->(c)
            """, chapters=chapters_list)
        
        # Batch tạo Articles
        if articles_list:
            tx.run("""
                UNWIND $articles AS art
                MATCH (c:Chapter {chapter_id: art.chap_id})
                MERGE (a:Article {article_id: art.art_id})
                SET a.number = art.number, a.title = art.title, a.status = art.status
                MERGE (c)-[:HAS_ARTICLE]->(a)
            """, articles=articles_list)
        
        # Batch tạo Chunks (có embedding)
        if chunks_list:
            tx.run("""
                UNWIND $chunks AS chk
                MATCH (a:Article {article_id: chk.art_id})
                MERGE (c:Chunk {chunk_id: chk.chunk_id})
                SET c.chunk_type = chk.chunk_type,
                    c.chunk_index = chk.chunk_index,
                    c.text = chk.text,
                    c.embedding = chk.embedding
                MERGE (a)-[:HAS_CHUNK]->(c)
            """, chunks=chunks_list)

        # 3. Batch tạo Relationships (có whitelist)
        relationships_list = []
        for rel in data.get('relationships', []):
            rel_type = rel.get('relation_type', '').upper()
            if rel_type not in ALLOWED_RELATION_TYPES:
                logger.warning(f"Bỏ qua quan hệ không hợp lệ: {rel_type}")
                continue
            relationships_list.append({
                'src_id': rel['source_chunk_id'],
                'tgt_id': rel['target_article_id'],
                'rel_type': rel_type,
                'evidence': rel.get('evidence_text', '')
            })
        
        if relationships_list:
            # Sử dụng APOC nếu có, nếu không dùng Cypher động nhưng đã whitelist
            # Cách an toàn: dùng CASE để chọn loại quan hệ
            for rel in relationships_list:
                # Vì đã whitelist, nhưng vẫn dùng tham số cho tên quan hệ là không được.
                # Giải pháp: dùng cypher với tên quan hệ là hằng số, nhưng mỗi loại là một câu lệnh riêng.
                # Tối ưu hơn: dùng apoc.merge.relationship nếu có APOC.
                # Dưới đây là cách dùng truyền thống an toàn (mỗi loại một câu, nhưng ít loại nên chấp nhận)
                tx.run(f"""
                    MATCH (source:Chunk {{chunk_id: $src_id}})
                    MATCH (target:Article {{article_id: $tgt_id}})
                    MERGE (source)-[r:{rel['rel_type']}]->(target)
                    SET r.evidence_text = $evidence
                """, src_id=rel['src_id'], tgt_id=rel['tgt_id'], evidence=rel['evidence'])

    # -------------------------------------------------------------------------
    # 2. HÀM TRUY VẤN (VECTOR SEARCH + THÔNG TIN)
    # -------------------------------------------------------------------------
    def vector_search(self, query_vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """Tìm kiếm ngữ nghĩa (RAG Query) - trả về chunk và article liên quan."""
        query = """
        CALL db.index.vector.queryNodes('legal_text_embedding_local', $limit, $query_vector)
        YIELD node, score
        MATCH (node)-[:HAS_CHUNK]->(a:Article)  // Chunk luôn có quan hệ với Article
        RETURN node.chunk_id AS chunk_id, node.text AS text, a.article_id AS article_id, score
        ORDER BY score DESC
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, limit=limit, query_vector=query_vector).data()
                return result
        except Exception as e:
            logger.error(f"Lỗi khi vector search: {e}")
            return []

    def get_article_by_id(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin article kèm theo nội dung các chunk."""
        query = """
        MATCH (a:Article {article_id: $art_id})
        OPTIONAL MATCH (a)-[:HAS_CHUNK]->(c:Chunk)
        RETURN a.article_id AS article_id, a.number AS number, a.title AS title, a.status AS status,
               collect({chunk_id: c.chunk_id, text: c.text, chunk_type: c.chunk_type}) AS chunks
        """
        with self.driver.session() as session:
            result = session.run(query, art_id=article_id).single()
            return dict(result) if result else None

    def get_chunks_by_article(self, article_id: str) -> List[Dict[str, Any]]:
        """Lấy danh sách chunk của một article (có thứ tự)."""
        query = """
        MATCH (a:Article {article_id: $art_id})-[:HAS_CHUNK]->(c:Chunk)
        RETURN c.chunk_id AS chunk_id, c.text AS text, c.chunk_index AS index, c.chunk_type AS type
        ORDER BY c.chunk_index
        """
        with self.driver.session() as session:
            result = session.run(query, art_id=article_id).data()
            return result

    def get_related_articles(self, source_chunk_id: str, relation_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Tìm các article có quan hệ với một chunk (ví dụ REFERENCES)."""
        if relation_type and relation_type.upper() not in ALLOWED_RELATION_TYPES:
            logger.warning(f"Loại quan hệ {relation_type} không được phép")
            return []
        
        rel_filter = f":{relation_type.upper()}" if relation_type else ""
        query = f"""
        MATCH (c:Chunk {{chunk_id: $chunk_id}})-[r{rel_filter}]->(a:Article)
        RETURN a.article_id AS article_id, a.number AS number, a.title AS title,
               type(r) AS relation_type, r.evidence_text AS evidence
        """
        with self.driver.session() as session:
            result = session.run(query, chunk_id=source_chunk_id).data()
            return result

    # -------------------------------------------------------------------------
    # 3. HÀM QUẢN TRỊ (INDEX, COUNT, DELETE)
    # -------------------------------------------------------------------------
    def create_vector_index(self):
        """Khởi tạo Vector Index (chỉ chạy một lần)."""
        query = """
        CREATE VECTOR INDEX legal_text_embedding_local IF NOT EXISTS
        FOR (c:Chunk)
        ON (c.embedding)
        OPTIONS { indexConfig: { `vector.dimensions`: 768, `vector.similarity_function`: 'cosine' } }
        """
        with self.driver.session() as session:
            session.run(query)
            logger.info("Vector Index đã sẵn sàng (hoặc đã tồn tại).")

    def count_embedded_chunks(self) -> int:
        """Đếm số lượng chunk đã có vector (quản lý tiến độ embedding)."""
        query = "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) as count"
        with self.driver.session() as session:
            result = session.run(query).single()
            return result["count"] if result else 0

    def delete_document_cascade(self, document_id: str) -> bool:
        """
        Xóa toàn bộ Document và tất cả các node liên quan (Chapter, Article, Chunk).
        """
        query = """
        MATCH (d:Document {document_id: $doc_id})
        OPTIONAL MATCH (d)-[:HAS_CHAPTER]->(c:Chapter)
        OPTIONAL MATCH (c)-[:HAS_ARTICLE]->(a:Article)
        OPTIONAL MATCH (a)-[:HAS_CHUNK]->(ch:Chunk)
        DETACH DELETE d, c, a, ch
        """
        try:
            with self.driver.session() as session:
                session.run(query, doc_id=document_id)
                logger.info(f"Đã xóa cascade document {document_id}")
                return True
        except Exception as e:
            logger.error(f"Lỗi khi xóa cascade document {document_id}: {e}")
            return False

    # -------------------------------------------------------------------------
    # 4. TIỆN ÍCH BỔ SUNG
    # -------------------------------------------------------------------------
    def get_document_info(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin cơ bản của document kèm số lượng chapter/article."""
        query = """
        MATCH (d:Document {document_id: $doc_id})
        OPTIONAL MATCH (d)-[:HAS_CHAPTER]->(c:Chapter)
        OPTIONAL MATCH (c)-[:HAS_ARTICLE]->(a:Article)
        RETURN d.document_id AS document_id, d.title AS title, d.type AS type,
               COUNT(DISTINCT c) AS chapter_count, COUNT(DISTINCT a) AS article_count
        """
        with self.driver.session() as session:
            result = session.run(query, doc_id=document_id).single()
            return dict(result) if result else None