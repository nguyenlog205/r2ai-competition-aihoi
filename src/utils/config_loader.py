import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def get_config(config_path="config/deployment/system.yml"):
    project_root = Path(__file__).resolve().parent.parent.parent
    full_path = project_root / config_path
    
    # ---------------------------------------------------------------------
    # Đọc file YAML mặc định
    with open(full_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    # ---------------------------------------------------------------------
    # Tự động override bằng ENV (Logic đệ quy)
    # Ví dụ: ENV 'LLM_API_KEY' sẽ tự tìm vào config['llm']['api_key']
    def override_with_env(d, prefix=""):
        for k, v in d.items():
            env_key = (prefix + "_" + k).upper()
            if isinstance(v, dict):
                override_with_env(v, env_key)
            else:
                if os.getenv(env_key):
                    d[k] = os.getenv(env_key)
        return d

    return override_with_env(config, "APP") 