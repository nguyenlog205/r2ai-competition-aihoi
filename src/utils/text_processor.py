import re
import unicodedata

def normalize_unicode(text: str) -> str:
    """Chuẩn hóa Unicode về dạng tổ hợp (NFC) để tránh lỗi ký tự."""
    return unicodedata.normalize('NFC', text)

def clean_whitespace(text: str) -> str:
    """Thay thế nhiều khoảng trắng, tab, newline bằng một khoảng trắng."""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def remove_special_characters(text: str, keep_dots: bool = True) -> str:
    """
    Loại bỏ các ký tự đặc biệt nhưng giữ lại chữ cái, số, dấu câu cơ bản.
    Nếu keep_dots=True, giữ dấu chấm, phẩy, hai chấm, chấm phẩy.
    """
    if keep_dots:
        # Giữ chữ, số, khoảng trắng, dấu câu cơ bản
        text = re.sub(r'[^\w\s.,;:?!\-]', '', text)
    else:
        text = re.sub(r'[^\w\s]', '', text)
    return text

def preprocess_text(text: str, normalize: bool = True, clean_ws: bool = True, remove_special: bool = True) -> str:
    """Pipeline tiền xử lý tổng hợp."""
    if not text:
        return ""
    if normalize:
        text = normalize_unicode(text)
    if remove_special:
        text = remove_special_characters(text, keep_dots=True)
    if clean_ws:
        text = clean_whitespace(text)
    return text