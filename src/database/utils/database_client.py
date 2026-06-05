# ==============================================================================
# FILE: database_client.py
# DESCRIPTION: Connection management module for the Neo4j database instance.
# ==============================================================================

import yaml
import logging
import time
from typing import Optional
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

# Initialize logger for this module
logger = logging.getLogger(__name__)

class Neo4jClient:
    """
    A client class responsible for establishing and managing connections 
    to the Neo4j graph database using configuration settings.
    
    Supports context manager (with statement) for automatic resource cleanup.
    """
    
    def __init__(self, config_path: str = "system_config.yaml"):
        """
        Initializes the Neo4j client by loading configurations and establishing the driver.
        
        Args:
            config_path (str): The file path to the system configuration YAML.
        
        Raises:
            FileNotFoundError: If configuration file not found.
            ValueError: If Neo4j configuration is incomplete.
            RuntimeError: If driver initialization fails.
        """
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self._validate_config()
        self.driver = self._init_driver()
        logger.info(f"Neo4jClient initialized with config: {config_path}")

    def _load_config(self, filepath: str) -> dict:
        """
        Loads and parses the YAML configuration file.
        
        Raises:
            FileNotFoundError: If the specified configuration file does not exist.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                logger.debug(f"Loaded configuration from {filepath}")
                return config
        except FileNotFoundError:
            error_msg = f"Configuration file not found at: {filepath}"
            logger.critical(error_msg)
            raise FileNotFoundError(error_msg)
        except yaml.YAMLError as e:
            error_msg = f"Invalid YAML in configuration file {filepath}: {e}"
            logger.critical(error_msg)
            raise ValueError(error_msg)

    def _validate_config(self) -> None:
        """
        Validates that Neo4j configuration for the current environment is complete.
        
        Raises:
            ValueError: If any required field (uri, user, password) is missing.
        """
        env = self.config.get('environment', 'development')
        db_config = self.config.get('neo4j', {}).get(env)
        
        if not db_config:
            error_msg = f"Neo4j configuration missing for environment: {env}"
            logger.critical(error_msg)
            raise ValueError(error_msg)
        
        required_fields = ['uri', 'user', 'password']
        for field in required_fields:
            if not db_config.get(field):
                error_msg = f"Missing '{field}' in Neo4j configuration for environment: {env}"
                logger.critical(error_msg)
                raise ValueError(error_msg)
        
        logger.info(f"Neo4j configuration validated for environment: {env}")

    def _init_driver(self):
        """
        Initializes the Neo4j database driver.
        
        Note: Connection pooling is handled automatically by the driver.
        Custom pool size is not explicitly set to use driver defaults.
        
        Returns:
            neo4j.Driver: The database driver instance.
        
        Raises:
            RuntimeError: If driver initialization fails.
        """
        env = self.config.get('environment', 'development')
        db_config = self.config['neo4j'][env]
        uri = db_config['uri']
        user = db_config['user']
        password = db_config['password']
        
        try:
            # Driver uses internal connection pool; no need to set pool size explicitly
            driver = GraphDatabase.driver(uri, auth=(user, password))
            logger.debug(f"Neo4j driver created for {uri}")
            return driver
        except Exception as e:
            error_msg = f"Failed to initialize Neo4j driver: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def verify_connection(self, retries: int = 3, delay: float = 1.0) -> bool:
        """
        Verifies the connectivity to the Neo4j database instance with optional retry.
        
        Args:
            retries (int): Number of retry attempts on failure.
            delay (float): Seconds to wait between retries.
        
        Returns:
            bool: True if connection is successful, False otherwise.
        """
        for attempt in range(1, retries + 1):
            try:
                self.driver.verify_connectivity()
                env = self.config.get('environment', 'UNKNOWN').upper()
                logger.info(f"Successfully connected to Neo4j database (Environment: {env}).")
                return True
            except (ServiceUnavailable, AuthError) as e:
                logger.warning(f"Connection attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(delay)
                else:
                    logger.error("All connection attempts failed.")
                    return False
            except Exception as e:
                logger.error(f"Unexpected error during connection verification: {e}")
                return False
        return False

    def close(self) -> None:
        """
        Safely terminates the Neo4j database driver connection and releases resources.
        """
        if self.driver:
            self.driver.close()
            logger.info("Neo4j database connection closed safely.")

    def __enter__(self):
        """Support for context manager (with statement)."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatically close connection when exiting context."""
        self.close()

    def get_driver(self):
        """Return the underlying driver instance (for advanced usage)."""
        return self.driver


# ==============================================================================
# MODULE EXECUTION BLOCK FOR CONNECTIVITY TESTING
# ==============================================================================
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    )
    
    # Allow config path to be passed as command-line argument
    config_path = sys.argv[1] if len(sys.argv) > 1 else "system_config.yaml"
    
    try:
        with Neo4jClient(config_path) as db_client:
            is_connected = db_client.verify_connection(retries=2)
            if is_connected:
                logger.info("Connection test passed.")
            else:
                logger.error("Connection test failed.")
    except Exception as ex:
        logger.critical(f"System execution halted due to initialization failure: {ex}")
        sys.exit(1)