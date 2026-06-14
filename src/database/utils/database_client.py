# ==============================================================================
# FILE: src/database/utils/database_client.py
# DESCRIPTION: PostgreSQL connection manager.
# ==============================================================================

import os
import logging
from typing import Optional
from contextlib import contextmanager

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor

from src.utils.config_loader import get_config

logger = logging.getLogger(__name__)


class DatabaseClient:
    """
    Minimal PostgreSQL client: manages connection pool and provides cursors.
    Schema creation is handled separately (e.g., by running schema.sql).
    """

    def __init__(self, env: Optional[str] = None):
        """
        Initialise the database client from configuration.
        
        Args:
            env: Environment ('development' or 'production'). Defaults to 
                 environment variable NEO4J_ENV or 'development'.
        """
        self.env = env or os.getenv("NEO4J_ENV", "development")
        full_config = get_config()

        # Look for PostgreSQL configuration
        if "postgresql" in full_config:
            db_config = full_config["postgresql"].get(self.env)
            if not db_config:
                raise ValueError(f"Missing PostgreSQL config for environment '{self.env}'")
        else:
            db_config = full_config   # flat config

        self.host = db_config.get("host", "localhost")
        self.port = db_config.get("port", 5432)
        self.database = db_config.get("database", "legal_db")
        self.user = db_config.get("user")
        self.password = db_config.get("password")

        if not all([self.user, self.password]):
            raise ValueError("Missing database credentials (user/password) in config")

        self._pool = None
        self._init_pool()

        logger.info(f"DatabaseClient ready (env={self.env}, db={self.database}@{self.host}:{self.port})")

    def _init_pool(self, minconn: int = 1, maxconn: int = 10):
        """Create a connection pool."""
        try:
            self._pool = SimpleConnectionPool(
                minconn, maxconn,
                host=self.host,
                port=self.port,
                dbname=self.database,
                user=self.user,
                password=self.password
            )
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool. Automatically returns it after use."""
        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
        finally:
            if conn:
                self._pool.putconn(conn)

    @contextmanager
    def cursor(self, commit: bool = False, dict_cursor: bool = False):
        """
        Get a cursor from a pooled connection.
        
        Args:
            commit: If True, commit the transaction after the block.
            dict_cursor: If True, use RealDictCursor (rows as dicts).
        """
        with self.get_connection() as conn:
            cursor_class = RealDictCursor if dict_cursor else None
            cur = conn.cursor(cursor_factory=cursor_class)
            try:
                yield cur
                if commit:
                    conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

    def close(self):
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            logger.info("Database connection pool closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == '__main__': 
    try:
        db = DatabaseClient(env="development")
        with db.cursor() as cur:
            cur.execute("SELECT 1")
        print("Connection successful!")
        db.close()
    except Exception as e:
        print(f"Connection failed: {e}")