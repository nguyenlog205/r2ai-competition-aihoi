import logging
import yaml
from typing import List, Dict
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class VectorEngine:
    def __init__(self, config_path: str = "config/deployment/system.yml"):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.strategy = self.config['embedding'].get('strategy', 'mean')
        self.models = []
        
        # Load các model được kích hoạt
        for m_cfg in self.config['embedding']['models']:
            if m_cfg['enabled']:
                logger.info(f"Loading model: {m_cfg['name']}")
                self.models.append(SentenceTransformer(m_cfg['name']))

    def embed_text(self, text: str) -> List[float]:
        """Tạo vector ensemble từ chuỗi các model."""
        vectors = [model.encode(text) for model in self.models]
        
        if self.strategy == "mean":
            # Trung bình cộng các vector
            ensemble_vector = np.mean(vectors, axis=0)
        elif self.strategy == "concatenate":
            # Nối các vector (lưu ý: phải cập nhật dimension trong Neo4j nếu dùng cái này)
            ensemble_vector = np.concatenate(vectors)
        else:
            ensemble_vector = vectors[0]
            
        return ensemble_vector.tolist()