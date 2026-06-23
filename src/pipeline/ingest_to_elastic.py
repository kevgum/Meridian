from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import pandas as pd
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ElasticsearchIngestor:
    def __init__(self, host: str = "http://localhost:9200", password: str = "meridian123"):
        self.es = Elasticsearch(
            host,
            basic_auth=("elastic", password),
            verify_certs=False  # Required for local docker 8.x without cert setup
        )
        # Check connection
        if not self.es.ping():
            logger.error("Could not connect to Elasticsearch at %s", host)
            raise ConnectionError(f"Could not connect to Elasticsearch at {host}")
        logger.info("Connected to Elasticsearch.")

    def create_index(self, index_name: str = "meridian-transactions-raw"):
        """Creates the index with specific mappings if it does not already exist."""
        mapping = {
            "mappings": {
                "properties": {
                    "amount": {"type": "float"},
                    "channel": {"type": "keyword"},
                    "customer_id_hash": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "is_fraud": {"type": "boolean"},
                    "step": {"type": "integer"}
                }
            }
        }
        
        if not self.es.indices.exists(index=index_name):
            self.es.indices.create(index=index_name, body=mapping)
            logger.info(f"Created index {index_name}")
        else:
            logger.info(f"Index {index_name} already exists.")

    def ingest_data(self, df: pd.DataFrame, index_name: str = "meridian-transactions-raw", chunk_size: int = 1000):
        """Bulk ingests pandas DataFrame into the specified Elasticsearch index."""
        logger.info(f"Preparing {len(df)} records for ingestion to {index_name}")
        
        def generate_actions(dataframe: pd.DataFrame) -> List[Dict[str, Any]]:
            for _, row in dataframe.iterrows():
                doc = {
                    "amount": float(row.get("amount", 0.0)),
                    "channel": str(row.get("type", "UNKNOWN")),
                    "customer_id_hash": str(row.get("nameOrig", "UNKNOWN")),
                    "is_fraud": bool(row.get("isFraud", False)),
                    "step": int(row.get("step", 0)),
                    # Mock timestamp from step (assuming step is an hour from 2024-01-01)
                    "timestamp": (pd.Timestamp("2024-01-01") + pd.Timedelta(hours=int(row.get("step", 0)))).isoformat()
                }
                yield {
                    "_index": index_name,
                    "_source": doc
                }

        success, failed = bulk(self.es, generate_actions(df), chunk_size=chunk_size, stats_only=True)
        logger.info(f"Successfully ingested {success} records.")
        if failed:
            logger.error(f"Failed to ingest {failed} records.")
