from openai import OpenAI
import os

def transcribe_audio(client, audio_file_path):
    """
    Transcribes audio file using OpenAI Whisper model.
    """
    if not client:
        return "OpenAI Client not initialized."
        
    with open(audio_file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file,
            response_format="text"
        )
    return transcript

def summarize_text(client, text, type="meeting"):
    """
    Summarizes text using GPT-4o.
    """
    if not client:
        return "OpenAI Client not initialized."

    system_prompt = "あなたは優秀な書記です。入力されたテキストを要約し、以下のフォーマットで議事録を作成してください。\n\n## 議題\n## 決定事項\n## ネクストアクション"
    if type == "morning_assembly":
        system_prompt = "あなたは就労移行支援事業所の職員です。朝会の音声認識テキストから、本日の重要連絡事項と各スタッフの予定を箇条書きでまとめてください。"

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content
