# ==========================================
# FILE: src/utils/log.py
# MỤC ĐÍCH: Cấu hình hệ thống ghi log tập trung
# ==========================================

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Tạo thư mục 'logs' ở thư mục gốc của project nếu chưa tồn tại
LOG_DIR = os.path.join(os.getcwd(), "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def get_logger(logger_name: str, log_level=logging.INFO) -> logging.Logger:
    """
    Khởi tạo và cấu hình một logger.
    
    Args:
        logger_name (str): Tên của module gọi log (thường dùng __name__)
        log_level (int): Mức độ log (mặc định là INFO)
        
    Returns:
        logging.Logger: Đối tượng logger đã cấu hình
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)

    # Nếu logger đã có handler rồi thì không thêm nữa (Tránh in log ra 2, 3 lần)
    if logger.hasHandlers():
        return logger

    # Định dạng (Format) chuẩn cho log: [Thời gian] | [Mức độ] | [Tên File] | Thông báo
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Handler: In log ra màn hình Terminal
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File Handler: Lưu log ra file
    # Dùng RotatingFileHandler: Khi file app.log đạt 5MB, nó sẽ tự đổi tên thành app.log.1 và tạo file app.log mới.
    # Giữ tối đa 3 file backup để không làm đầy ổ đĩa.
    log_file_path = os.path.join(LOG_DIR, "app.log")
    file_handler = RotatingFileHandler(
        log_file_path, 
        maxBytes=5 * 1024 * 1024, # 5 MB
        backupCount=3, 
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger