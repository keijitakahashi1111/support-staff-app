"""
Database configuration for Supabase PostgreSQL.
"""
import os

# Default Supabase connection URL
DEFAULT_DATABASE_URL = (
    "postgresql://postgres.jjzugmzglarbggmddtgp:ZZx4%21akiHmb%243ML"
    "@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
)


def get_database_url():
    """Get database URL from Streamlit secrets, env var, or default."""
    # 1. Try Streamlit secrets
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass

    # 2. Environment variable
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url

    # 3. Default
    return DEFAULT_DATABASE_URL


def get_connection():
    """Return a psycopg2 connection to Supabase PostgreSQL."""
    import psycopg2
    url = get_database_url()
    print(f"[db_config] Connecting to database...", flush=True)
    conn = psycopg2.connect(url, connect_timeout=10)
    conn.autocommit = False
    print(f"[db_config] Connected successfully!", flush=True)
    return conn
