import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Read Database Connection URI from environment variable
# Falls back to local sqlite during local development/tests if Postgres URI is not provided
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local_temp_db.db")

# SQLite needs 'check_same_thread=False' parameter, Postgres does not.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get db session per request, closed automatically
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
