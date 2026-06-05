# ==============================================================================
# FILE: database_client.py
# DESCRIPTION: Connection management module for the Neo4j database instance.
# ==============================================================================

import yaml
import logging
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

# Initialize logger for this module
logger = logging.getLogger(__name__)

class Neo4jClient:
    """
    A client class responsible for establishing and managing connections 
    to the Neo4j graph database using configuration settings.
    """
    
    def __init__(self, config_path: str = "system_config.yaml"):
        """
        Initializes the Neo4j client by loading configurations and establishing the driver.
        
        Args:
            config_path (str): The file path to the system configuration YAML.
        """
        self.config = self._load_config(config_path)
        self.driver = self._init_driver()

    def _load_config(self, filepath: str) -> dict:
        """
        Loads and parses the YAML configuration file.
        
        Raises:
            FileNotFoundError: If the specified configuration file does not exist.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            error_msg = f"Configuration file not found at: {filepath}"
            logger.critical(error_msg)
            raise FileNotFoundError(error_msg)

    def _init_driver(self):
        """
        Initializes the Neo4j database driver based on active environment settings.
        
        Raises:
            ValueError: If database configurations are missing.
            RuntimeError: If driver initialization fails.
        """
        env = self.config.get('environment', 'development')
        db_config = self.config.get('neo4j', {}).get(env)

        if not db_config:
            error_msg = f"Neo4j configuration missing or invalid for environment: {env}"
            logger.critical(error_msg)
            raise ValueError(error_msg)

        uri = db_config.get('uri')
        user = db_config.get('user')
        password = db_config.get('password')
        pool_size = db_config.get('max_connection_pool_size', 50)

        try:
            # Establish connection utilizing Connection Pooling for optimized throughput
            driver = GraphDatabase.driver(
                uri, 
                auth=(user, password), 
                max_connection_pool_size=pool_size
            )
            return driver
        except Exception as e:
            error_msg = f"Failed to initialize Neo4j driver: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def verify_connection(self) -> bool:
        """
        Verifies the connectivity to the Neo4j database instance.
        
        Returns:
            bool: True if the connection is successful, False otherwise.
        """
        try:
            self.driver.verify_connectivity()
            env = self.config.get('environment', 'UNKNOWN').upper()
            logger.info(f"Successfully connected to Neo4j database (Environment: {env}).")
            return True
        except ServiceUnavailable:
            logger.error("Connection failed: Service unavailable. Please verify the URI and database operational status.")
            return False
        except Exception as e:
            logger.error(f"Authentication or persistent connection error: {e}")
            return False

    def close(self) -> None:
        """
        Safely terminates the Neo4j database driver connection and releases resources.
        """
        if self.driver:
            self.driver.close()
            logger.info("Neo4j database connection closed safely.")

# ==============================================================================
# MODULE EXECUTION BLOCK FOR CONNECTIVITY TESTING
# ==============================================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    )
    
    try:
        db_client = Neo4jClient("config/system.yml")
        is_connected = db_client.verify_connection()
        db_client.close()
        
    except Exception as ex:
        logger.critical(f"System execution halted due to initialization failure: {ex}")