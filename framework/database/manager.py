from .mysql_driver import MySQLDriver
from .redis_driver import RedisDriver

class DatabaseManager:
    _instance = None

    def __init__(self, settings):
        self.mysql = MySQLDriver(settings.DATABASE_URL)
        self.redis = RedisDriver(settings.REDIS_URL)

    @classmethod
    def get_instance(cls, settings=None):
        if cls._instance is None:
            if settings is None:
                from framework.config import settings as app_settings
                settings = app_settings
            cls._instance = cls(settings)
        return cls._instance