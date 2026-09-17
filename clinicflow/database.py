from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def create_database(database_url):
    engine_options = {"future": True}
    if database_url.startswith("sqlite"):
        engine_options["connect_args"] = {"timeout": 5}

    engine = create_engine(database_url, **engine_options)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite_connection(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.close()

    return engine, sessionmaker(bind=engine, expire_on_commit=False)