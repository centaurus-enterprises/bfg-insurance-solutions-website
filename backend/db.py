import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    """
    Opens and returns a new PostgreSQL connection using
    credentials from the .env file.
    """
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )
    return conn