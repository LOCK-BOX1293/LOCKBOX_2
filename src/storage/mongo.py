from pymongo import MongoClient
from pymongo.database import Database
from src.core.config import settings
from src.core.config import logger

class MongoManager:
    _instance = None
    _client: MongoClient = None
    _db: Database = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoManager, cls).__new__(cls)
            cls._instance.connect()
        return cls._instance

    def connect(self):
        if not self._client:
            logger.info("Connecting to MongoDB", uri=settings.mongodb_uri, db=settings.mongodb_db)
            self._client = MongoClient(settings.mongodb_uri)
            self._db = self._client[settings.mongodb_db]

    def get_db(self) -> Database:
        return self._db

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
            logger.info("Closed MongoDB connection")

def get_db() -> Database:
    return MongoManager().get_db()
