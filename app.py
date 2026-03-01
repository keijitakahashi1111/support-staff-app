import streamlit as st

st.set_page_config(page_title="テスト", layout="wide")
st.title("🎉 デプロイ成功！")
st.write("Streamlit Cloud に接続できました。")

# Test database connection
try:
    from db_config import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM staff")
    count = cur.fetchone()[0]
    conn.close()
    st.success(f"✅ データベース接続OK！ スタッフ数: {count}")
except Exception as e:
    st.error(f"❌ データベースエラー: {e}")

st.info("テストページです。本番アプリは準備中...")
