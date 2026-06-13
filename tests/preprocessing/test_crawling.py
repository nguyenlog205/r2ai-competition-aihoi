"""
Unit tests for the VBPL crawler output format.
Only unit tests – no network, no real browser, no integration.
"""

import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import tempfile
from unittest.mock import MagicMock

import pytest

from src.pipelines.crawling.main import DataIngestionTool, merge_json_files


# ----------------------------------------------------------------------
# Helper
# ----------------------------------------------------------------------
def validate_record_format(record: dict) -> bool:
    """Check that a single record contains at least 'url' and 'nội dung'."""
    required = {"url", "nội dung"}
    return required.issubset(record.keys())


def validate_json_file(file_path: str) -> bool:
    """Load a JSON file and validate all records."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return False
    return all(validate_record_format(rec) for rec in data)


# ----------------------------------------------------------------------
# Unit tests
# ----------------------------------------------------------------------
def test_save_to_json_format():
    """Test that _save_to_json writes correct JSON with expected fields."""
    dummy_data = [
        {
            "Tên văn bản": "Luật Đất đai 2024",
            "Số hiệu": "31/2024/QH15",
            "Cơ quan ban hành": "Quốc hội",
            "Ngày ban hành": "18/01/2024",
            "Ngày hiệu lực": "01/01/2025",
            "Trạng thái": "Còn hiệu lực",
            "url": "https://vbpl.vn/doc1",
            "nội dung": "Nội dung luật...",
        },
        {
            "Tên văn bản": "Nghị định 123",
            "Số hiệu": "123/2024/NĐ-CP",
            "Cơ quan ban hành": "Chính phủ",
            "Ngày ban hành": "10/02/2024",
            "Ngày hiệu lực": "01/03/2024",
            "Trạng thái": "Còn hiệu lực",
            "url": "https://vbpl.vn/doc2",
            "nội dung": "Nội dung nghị định...",
        },
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tool = DataIngestionTool(web_link="https://example.com")
        tool.driver = MagicMock()   # mock to avoid real driver

        keyword = "test"
        tool._save_to_json(dummy_data, keyword, tmpdir)

        json_path = Path(tmpdir) / f"metadata_law_{keyword}.json"
        assert json_path.exists()
        assert validate_json_file(str(json_path))


def test_validate_record_format():
    """Sanity check for the validator itself."""
    good = {
        "url": "http://example.com",
        "nội dung": "text",
        "Tên văn bản": "Law",
        "Số hiệu": "123",
        "Cơ quan ban hành": "Gov",
        "Ngày ban hành": "2024",
        "Ngày hiệu lực": "2025",
        "Trạng thái": "active",
    }
    assert validate_record_format(good)

    missing_content = {"url": "http://example.com"}
    assert not validate_record_format(missing_content)


def test_merge_preserves_format():
    """Test that merge_json_files writes correctly formatted JSON."""
    rec1 = {
        "url": "http://a.com",
        "nội dung": "text1",
        "Tên văn bản": "Law A",
        "Số hiệu": "001",
        "Cơ quan ban hành": "Gov",
        "Ngày ban hành": "2024",
        "Ngày hiệu lực": "2025",
        "Trạng thái": "active",
    }
    rec2 = {
        "url": "http://b.com",
        "nội dung": "text2",
        "Tên văn bản": "Law B",
        "Số hiệu": "002",
        "Cơ quan ban hành": "Gov",
        "Ngày ban hành": "2024",
        "Ngày hiệu lực": "2025",
        "Trạng thái": "active",
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        file1 = Path(tmpdir) / "metadata_law_keyword1.json"
        file2 = Path(tmpdir) / "metadata_law_keyword2.json"
        with open(file1, "w", encoding="utf-8") as f:
            json.dump([rec1], f, ensure_ascii=False, indent=4)
        with open(file2, "w", encoding="utf-8") as f:
            json.dump([rec2], f, ensure_ascii=False, indent=4)

        merged_path = Path(tmpdir) / "merged.json"
        merge_json_files([str(file1), str(file2)], str(merged_path))

        assert validate_json_file(str(merged_path))
        with open(merged_path, "r", encoding="utf-8") as f:
            merged_data = json.load(f)
        assert len(merged_data) == 2