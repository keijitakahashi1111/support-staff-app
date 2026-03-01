"""
Database configuration for Supabase PostgreSQL.
Reads DATABASE_URL from environment / Streamlit secrets.
"""
import os
import psycopg2
import psycopg2.extras


def get_database_url():
    """Get database URL from Streamlit secrets or environment variable."""
    # 1. Try Streamlit secrets first (for Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass

    # 2. Fall back to environment variable
    return os.environ.get("DATABASE_URL", "")


def get_connection():
    """Return a psycopg2 connection to Supabase PostgreSQL."""
    url = get_database_url()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Set it as a Streamlit secret or environment variable."
        )
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn
