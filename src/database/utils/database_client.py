import logging
import time
import os
from typing import Optional
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

from src.utils.config_loader import get_config

logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self, env: Optional[str] = None):
        self.env = env or os.getenv("NEO4J_ENV", "development")
        
        full_config = get_config()          # từ config/deployment/system.yml + .env
        # Lấy phần neo4j theo môi trường
        neo4j_section = full_config.get("neo4j", {})
        if not neo4j_section:
            # fallback config phẳng (không có key neo4j)
            db_config = full_config
        else:
            db_config = neo4j_section.get(self.env)
            if not db_config:
                raise ValueError(f"Missing neo4j config for environment '{self.env}'")
        
        self.uri = db_config.get("uri")
        self.user = db_config.get("user")
        self.password = db_config.get("password")
        
        if not all([self.uri, self.user, self.password]):
            raise ValueError(f"Missing uri/user/password in neo4j config for env '{self.env}'")
        
        self.driver = self._init_driver()
        logger.info(f"Neo4jClient initialized for env: {self.env} (uri={self.uri})")

    def _init_driver(self):
        try:
            driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            logger.debug("Neo4j driver created")
            return driver
        except Exception as e:
            raise RuntimeError(f"Failed to init Neo4j driver: {e}") from e

    def verify_connection(self, retries: int = 3, delay: float = 1.0) -> bool:
        for attempt in range(1, retries + 1):
            try:
                self.driver.verify_connectivity()
                logger.info(f"Connected to Neo4j (env={self.env})")
                return True
            except (ServiceUnavailable, AuthError) as e:
                logger.warning(f"Attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(delay)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return False
        return False

    def close(self):
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get_driver(self):
        return self.driver