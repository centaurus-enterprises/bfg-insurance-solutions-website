import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    """
    Opens and returns a new PostgreSQL connection.
    Uses DATABASE_URL (Render) if set, otherwise falls back to
    individual DB_HOST/PORT/NAME/USER/PASSWORD vars (local dev).
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        conn = psycopg2.connect(database_url)
    else:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
    return conn