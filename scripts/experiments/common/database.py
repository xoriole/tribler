from pathlib import Path

import pony
from dotenv import load_dotenv
from pydantic import BaseSettings


ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(ENV_FILE)


class DatabaseSettings(BaseSettings):
    provider: str = 'sqlite'
    host: str = 'localhost'
    user: str = 'user'
    password: str = None
    database: str = 'experiment'
    filename: str = 'database.sqlite'

    class Config:
        env_prefix = 'EXP_DB_'

    def get_connection(self):
        if self.provider == 'sqlite':
            return self.dict(include={'provider', 'filename'})
        else:
            return self.dict(include={'provider', 'host', 'user', 'password', 'database'})


class Database(pony.orm.Database):
    
    def __init__(self, *args, **kwargs):
        super(Database, self).__init__(*args, **kwargs)

        # Connection info for database database
        connection = DatabaseSettings().get_connection()
        self.bind(**connection)


_db = Database()


def get_database():
    return _db

