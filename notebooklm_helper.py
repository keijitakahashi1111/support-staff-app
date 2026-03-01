# -*- coding: utf-8 -*-
"""
NotebookLM 連携ヘルパー
Google Gemini API を使って社内ナレッジを検索し、回答を取得する。
NotebookLMと同じGeminiモデルを使い、アップロード済みドキュメントに基づいて回答。
"""

import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ----- 設定 -----
NOTEBOOK_ID = "3c8cb884-3b8e-4eac-9964-dc1bbb0fcd45"
DOCS_DIR = Path(__file__).parent / "knowledge_docs"
CACHE_FILE = Path(__file__).parent / ".gemini_files_cache.json"


def _get_gemini_client():
    """Gemini クライアントを初期化"""
    try:
        import google.generativeai as genai
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return None
        genai.configure(api_key=api_key)
        return genai
    except ImportError:
        logger.warning("google-generativeai not installed")
        return None


def _load_file_cache() -> dict:
    """アップロード済みファイルのキャッシュを読み込み"""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_file_cache(cache: dict):
    """ファイルキャッシュを保存"""
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def upload_documents(file_paths: list = None) -> list:
    """
    ドキュメントをGemini File APIにアップロード。
    既にアップロード済みのファイルはスキップ。

    Args:
        file_paths: アップロードするファイルパスのリスト。
                   Noneの場合はknowledge_docsディレクトリ内の全ファイルをアップロード。

    Returns:
        list: アップロード済みファイルのURI一覧
    """
    genai = _get_gemini_client()
    if not genai:
        return []

    # デフォルト: knowledge_docs ディレクトリ配下のファイル
    if file_paths is None:
        if not DOCS_DIR.exists():
            DOCS_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created {DOCS_DIR} — place your documents here")
            return []
        file_paths = [str(f) for f in DOCS_DIR.iterdir() if f.is_file()]

    cache = _load_file_cache()
    uploaded = []

    for fp in file_paths:
        fp_str = str(fp)
        if fp_str in cache:
            logger.info(f"Skipping (already uploaded): {fp_str}")
            uploaded.append(cache[fp_str])
            continue

        try:
            result = genai.upload_file(fp_str)
            cache[fp_str] = {
                "name": result.name,
                "uri": result.uri,
                "display_name": result.display_name,
            }
            uploaded.append(cache[fp_str])
            logger.info(f"Uploaded: {fp_str} -> {result.name}")
        except Exception as e:
            logger.warning(f"Failed to upload {fp_str}: {e}")

    _save_file_cache(cache)
    return uploaded


def get_uploaded_files() -> list:
    """キャッシュからアップロード済みファイル一覧を取得"""
    return list(_load_file_cache().values())


def query_knowledge(question: str) -> dict:
    """
    Gemini APIにアップロード済みドキュメントを参照しつつ質問を送信。
    NotebookLMと同じGeminiモデルを使用。

    Returns:
        dict: {
            "answer": str,      # Geminiの回答テキスト
            "sources": list,    # 参照されたファイル名一覧
            "success": bool,    # 成功/失敗
            "error": str|None,  # エラーメッセージ
        }
    """
    genai = _get_gemini_client()
    if not genai:
        return {
            "answer": "",
            "sources": [],
            "success": False,
            "error": "Gemini API key not configured",
        }

    try:
        # Get uploaded files
        cache = _load_file_cache()
        file_refs = []
        source_names = []

        for fp, info in cache.items():
            try:
                file_ref = genai.get_file(info["name"])
                file_refs.append(file_ref)
                source_names.append(info.get("display_name", Path(fp).name))
            except Exception as e:
                logger.warning(f"File {info['name']} not accessible: {e}")

        # Build prompt
        system_instruction = """あなたは就労移行支援事業所の社内ナレッジアシスタントです。
提供されたドキュメント（就業規則PDF・社内マニュアル・研修資料等）の内容に基づいて、
質問に正確に回答してください。

## ルール
1. ドキュメントに記載されている情報のみに基づいて回答
2. 該当する箇所を具体的に引用・参照
3. ドキュメントに情報がない場合は「この件については社内資料に記載がありません」と回答
4. 簡潔かつ正確に回答"""

        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=system_instruction
        )

        # Build content with file references
        content_parts = []
        for ref in file_refs:
            content_parts.append(ref)
        content_parts.append(f"\n\n質問: {question}")

        response = model.generate_content(content_parts)

        return {
            "answer": response.text,
            "sources": source_names,
            "success": True,
            "error": None,
        }

    except Exception as e:
        logger.warning(f"Gemini query failed: {e}")
        return {
            "answer": "",
            "sources": [],
            "success": False,
            "error": str(e),
        }


# ========================================
# 後方互換: app.pyからの呼び出し用
# ========================================

def query_notebooklm(question: str, notebook_id: str = NOTEBOOK_ID) -> dict:
    """query_knowledge のエイリアス（後方互換）"""
    return query_knowledge(question)


def is_authenticated() -> bool:
    """Gemini API キーが設定されているかチェック"""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return True
    # Also check if there are uploaded docs in cache (even without env var, sidebar might set it)
    return False


def get_status() -> dict:
    """現在の状態を取得"""
    has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    cache = _load_file_cache()
    return {
        "api_key_configured": has_key,
        "uploaded_files_count": len(cache),
        "uploaded_files": [info.get("display_name", "?") for info in cache.values()],
    }
