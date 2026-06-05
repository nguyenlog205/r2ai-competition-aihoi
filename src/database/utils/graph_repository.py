# ==============================================================================
# FILE: src/database/graph_repository.py
# DESCRIPTION: Repository layer to handle CRUD operations for Legal Graph
# ==============================================================================

import logging
from src.database.utils.database_client import Neo4jClient
from src.schema.legal_schema import LegalDocumentExtraction

logger = logging.getLogger(__name__)

class LegalGraphRepository:
    """
    Wrapper thao tác với dữ liệu (Data Access Layer).
    Tách biệt hoàn toàn logic nghiệp vụ (Python) khỏi logic truy vấn (Cypher).
    """
    def __init__(self, db_client: Neo4jClient):
        # Nhận vào connection đã được khởi tạo
        self.driver = db_client.driver

    # -------------------------------------------------------------------------
    # 1. HÀM THÊM MỚI (CREATE/MERGE) TỪ KẾT QUẢ CỦA LLM
    # -------------------------------------------------------------------------
    def ingest_full_document(self, doc_data) -> bool:
        """
        Nạp toàn bộ 1 văn bản (Luật, Điều, Chunk, Quan hệ) vào DB trong 1 Transaction duy nhất.
        doc_data: Object của class LegalDocumentExtraction (Pydantic)
        """
        # Chuyển Pydantic model thành Dictionary để dễ truyền vào Cypher
        data_dict = doc_data.model_dump() if hasattr(doc_data, 'model_dump') else doc_data.dict()

        try:
            # Sử dụng session.execute_write để đảm bảo tính ACID (Transaction)
            with self.driver.session() as session:
                session.execute_write(self._tx_ingest_document_tree, data_dict)
            
            logger.info(f"✅ Đã lưu thành công văn bản: {data_dict['document_id']}")
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi khi lưu văn bản {data_dict.get('document_id')}: {e}")
            return False

    @staticmethod
    def _tx_ingest_document_tree(tx, data: dict):
        """Hàm nội bộ thực thi các lệnh Cypher (chạy trong Transaction)"""
        
        # 1. MERGE Document (Tạo mới nếu chưa có, nếu có rồi thì cập nhật)
        query_doc = """
        MERGE (d:Document {document_id: $doc_id})
        SET d.title = $title, d.type = $type
        """
        tx.run(query_doc, doc_id=data['document_id'], title=data['document_title'], type=data['document_type'])

        # 2. Xử lý các Chương (Chapters) và Điều (Articles)
        for chapter in data.get('chapters', []):
            query_chapter = """
            MATCH (d:Document {document_id: $doc_id})
            MERGE (c:Chapter {chapter_id: $chap_id})
            SET c.name = $name, c.title = $title
            MERGE (d)-[:HAS_CHAPTER]->(c)
            """
            tx.run(query_chapter, doc_id=data['document_id'], chap_id=chapter['chapter_id'], 
                   name=chapter['name'], title=chapter['title'])

            for article in chapter.get('articles', []):
                query_article = """
                MATCH (c:Chapter {chapter_id: $chap_id})
                MERGE (a:Article {article_id: $art_id})
                SET a.number = $number, a.title = $title, a.status = 'Đang có hiệu lực'
                MERGE (c)-[:HAS_ARTICLE]->(a)
                """
                tx.run(query_article, chap_id=chapter['chapter_id'], art_id=article['article_id'], 
                       number=article['number'], title=article.get('title', ''))

                # 3. Xử lý Chunks (Khoản/Điểm) kèm Vector (Giả định Vector được sinh ở bước trước)
                for chunk in article.get('chunks', []):
                    query_chunk = """
                    MATCH (a:Article {article_id: $art_id})
                    MERGE (ch:Chunk {chunk_id: $chunk_id})
                    SET ch.chunk_type = $type, ch.chunk_index = $index, ch.text = $text
                    // NẾU CÓ VECTOR THÌ SET VÀO ĐÂY: ch.embedding = $embedding
                    MERGE (a)-[:HAS_CHUNK]->(ch)
                    """
                    tx.run(query_chunk, art_id=article['article_id'], chunk_id=chunk['chunk_id'],
                           type=chunk['chunk_type'], index=chunk['chunk_index'], text=chunk['text'])

        # 4. Tạo các mối quan hệ dẫn chiếu/phiên bản (CITES, GUIDES, AMENDS...)
        for rel in data.get('relationships', []):
            query_rel = f"""
            MATCH (source {{chunk_id: $src_id}}) // Nguồn thường là Chunk
            MATCH (target:Article {{article_id: $tgt_id}}) // Đích thường là Article
            MERGE (source)-[r:{rel['relation_type']}]->(target)
            SET r.evidence_text = $evidence
            """
            # Lưu ý: Trong môi trường production, KHÔNG ĐƯỢC dùng f-string cho label hoặc type 
            # nếu dữ liệu từ user (để chống Cypher Injection). Nhưng ở đây relation_type đã bị ép 
            # bởi Pydantic Literal ("CITES", "GUIDES") nên an toàn.
            try:
                tx.run(query_rel, src_id=rel['source_chunk_id'], tgt_id=rel['target_article_id'], evidence=rel['evidence_text'])
            except Exception as e:
                logger.warning(f"Bỏ qua Relationship {rel['source_chunk_id']} -> {rel['target_article_id']}: Node đích có thể chưa tồn tại trong DB.")

    # -------------------------------------------------------------------------
    # 2. CÁC HÀM XÓA / CHỈNH SỬA (DELETE / UPDATE)
    # -------------------------------------------------------------------------
    def delete_document_cascade(self, document_id: str) -> bool:
        """Xóa 1 văn bản và TOÀN BỘ các Chương, Điều, Chunk thuộc về nó (Xóa phân tầng)"""
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
            logger.info(f"Đã xóa toàn bộ dữ liệu của văn bản {document_id}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi xóa văn bản {document_id}: {e}")
            return False

    def update_article_status(self, article_id: str, new_status: str) -> bool:
        """Đổi trạng thái của 1 điều luật (VD: 'Đang có hiệu lực' -> 'Hết hiệu lực')"""
        query = "MATCH (a:Article {article_id: $art_id}) SET a.status = $status RETURN a"
        try:
            with self.driver.session() as session:
                result = session.run(query, art_id=article_id, status=new_status)
                if result.single():
                    logger.info(f"Đã cập nhật trạng thái của {article_id} thành {new_status}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Lỗi cập nhật trạng thái: {e}")
            return False