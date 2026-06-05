# ==============================================================================
# FILE: src/schema/legal_schema.py
# DESCRIPTION: Pydantic schemas for LLM structured output and data validation.
#              Acts as the Data Transfer Object (DTO) for the Repository Layer.
# ==============================================================================

from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# ------------------------------------------------------------------------------
# 1. NODE SCHEMAS (ENTITIES)
# ------------------------------------------------------------------------------

class ChunkNode(BaseModel):
    """Represents the smallest unit of text (Clause, Point, or Split Text) for vector embedding."""
    chunk_id: str = Field(..., description="Unique ID (e.g., Luat_04_2017_Dieu_4_Khoan_1)")
    chunk_type: Literal["Clause", "Point", "Text_Split"] = Field(
        ..., 
        description="Categorization of the chunk. Use 'Text_Split' if an Article lacks Clauses but is too long."
    )
    chunk_index: str = Field(..., description="Index or symbol (e.g., '1', '2', 'a', 'b', or 'split_1')")
    text: str = Field(..., description="Original raw text content intended for Vector Embedding.")

class ArticleNode(BaseModel):
    """Represents a complete legal Article (Điều)."""
    article_id: str = Field(..., description="Unique ID (e.g., Luat_04_2017_Dieu_4)")
    number: str = Field(..., description="Article enumeration (e.g., Điều 4)")
    title: Optional[str] = Field(None, description="Official title of the Article, if provided.")
    
    # Versioning properties (Quản lý trạng thái hiệu lực)
    status: Literal["Đang có hiệu lực", "Hết hiệu lực", "Hết hiệu lực một phần", "Chưa có hiệu lực"] = Field(
        default="Đang có hiệu lực", 
        description="Current operational status of the Article."
    )
    effective_date: Optional[str] = Field(None, description="Effective date in YYYY-MM-DD format.")
    
    chunks: List[ChunkNode] = Field(
        default_factory=list, 
        description="Sequential list of text chunks contained within this Article."
    )

class ChapterNode(BaseModel):
    """Represents a Chapter or Section (Chương/Phần) within a legal document."""
    chapter_id: str = Field(..., description="Unique ID (e.g., Luat_04_2017_Chuong_2)")
    name: str = Field(..., description="Chapter enumeration (e.g., Chương II)")
    title: str = Field(..., description="Official title of the Chapter.")
    articles: List[ArticleNode] = Field(
        default_factory=list, 
        description="List of Articles encompassed by this Chapter."
    )

# ------------------------------------------------------------------------------
# 2. RELATIONSHIP SCHEMAS (EDGES)
# ------------------------------------------------------------------------------

class LegalRelationship(BaseModel):
    """Represents a directed legal graph edge (cross-reference or version modification)."""
    source_chunk_id: str = Field(..., description="ID of the originating component (usually a Chunk).")
    target_article_id: str = Field(..., description="ID of the referenced or modified Article.")
    
    # Các loại quan hệ pháp lý chuẩn
    relation_type: Literal["CITES", "GUIDES", "AMENDS", "SUPPLEMENTS", "ABROGATES"] = Field(
        ..., 
        description="Strictly defined relationship type ensuring schema compliance."
    )
    evidence_text: str = Field(..., description="Exact textual excerpt demonstrating this relationship.")

# ------------------------------------------------------------------------------
# 3. ROOT SCHEMA (DATA TRANSFER OBJECT)
# ------------------------------------------------------------------------------

class LegalDocumentExtraction(BaseModel):
    """Root extraction schema. This is the explicit format required from the LLM."""
    document_id: str = Field(..., description="Official document code (e.g., 04/2017/QH14)")
    document_type: Literal["Luật", "Nghị định", "Thông tư", "Quyết định", "Hiến pháp"] = Field(
        ..., description="Legal classification of the document."
    )
    document_title: str = Field(..., description="Full, formal title of the legal document.")
    
    chapters: List[ChapterNode] = Field(
        default_factory=list, 
        description="Hierarchical structural breakdown of the document."
    )
    relationships: List[LegalRelationship] = Field(
        default_factory=list, 
        description="Array of all identified legal cross-references and version modifiers."
    )