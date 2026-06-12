"""
create_agent.py
---------------
Run this script once from the terminal to create an agent account.

Usage:
    python create_agent.py

This will prompt you for the agent's details and insert a new
row into the agents table with a securely hashed password.
"""

import psycopg2
import hashlib
import os
import secrets
from dotenv import load_dotenv

load_dotenv()


def hash_password(password: str) -> str:
    """
    Hashes a password using SHA-256 with a random salt.
    Stored format: salt:hash
    """
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


def agent_exists(cur, username: str, email: str) -> bool:
    cur.execute(
        "SELECT id FROM agents WHERE username = %s OR email = %s",
        (username, email)
    )
    return cur.fetchone() is not None


def create_agent():
    print("\n── Brown Financial Group: Create Agent ──────────────────────")
    print("This script creates a new agent account in the database.")
    print("────────────────────────────────────────────────────\n")

    full_name = input("Full name:  ").strip()
    email     = input("Email:      ").strip().lower()
    username  = input("Username:   ").strip().lower()
    password  = input("Password:   ").strip()

    is_admin_input = input("Admin account? (y/n): ").strip().lower()
    is_admin = is_admin_input == 'y'

    notify_input = input("Receive new lead email notifications? (y/n): ").strip().lower()
    notify = notify_input == 'y'

    if not all([full_name, email, username, password]):
        print("\n✗ All fields are required. Exiting.")
        return

    password_hash = hash_password(password)

    try:
        conn = get_connection()
        cur  = conn.cursor()

        if agent_exists(cur, username, email):
            print(f"\n✗ An agent with username '{username}' or email '{email}' already exists.")
            cur.close()
            conn.close()
            return

        cur.execute("""
            INSERT INTO agents (full_name, email, username, password_hash, is_admin, notify_on_lead, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
        """, (full_name, email, username, password_hash, is_admin, notify))

        conn.commit()
        cur.close()
        conn.close()

        print(f"\n✓ Agent '{full_name}' created successfully.")
        print(f"  Username:  {username}")
        print(f"  Email:     {email}")
        print(f"  Admin:     {'Yes' if is_admin else 'No'}")
        print(f"  Notify:    {'Yes' if notify else 'No'}")
        print("\nYou can now log in at http://localhost:5000/login\n")

    except Exception as e:
        print(f"\n✗ Error creating agent: {e}")


if __name__ == "__main__":
    create_agent()