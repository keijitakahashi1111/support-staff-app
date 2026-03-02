import streamlit as st
import datetime
import os
import pandas as pd
from openai import OpenAI
import sys

# .env ファイルから環境変数を読み込み（あれば）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import yaml
import streamlit_authenticator as stauth
from pathlib import Path

# Import modules (flat directory structure)
try:
    import db_utils
except Exception as e:
    raise ImportError(f"Failed to import db_utils: {e}")
try:
    import calendar_utils
except Exception:
    calendar_utils = None
try:
    import whisper_utils
except Exception:
    whisper_utils = None
import scenarios as rp_scenarios
import company_rules
import notebooklm_helper
import models

print("[app.py] Page config...", flush=True)
st.set_page_config(page_title="支援員成長プラットフォーム", layout="wide")

# Initialize database (creates tables + demo data if not exists)
print("[app.py] Starting init_db...", flush=True)
try:
    models.init_db()
    print("[app.py] init_db completed!", flush=True)
except Exception as e:
    import traceback
    st.error(f"❌ データベース接続エラー: {e}")
    st.code(traceback.format_exc())
    st.stop()

# --- Authentication ---
def check_password():
    """Authenticate user using streamlit-authenticator."""
    
    config_path = Path(__file__).parent / "auth_config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
    )
    
    # Login widget
    try:
        authenticator.login()
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return False
    
    if st.session_state.get("authentication_status"):
        # Get user info from config
        username = st.session_state.get("username")
        user_data = config['credentials']['usernames'].get(username, {})
        
        # Set session state for the app
        st.session_state["logged_in"] = True
        st.session_state["user_name"] = st.session_state.get("name", username)
        st.session_state["login_role"] = user_data.get("role", "staff")
        
        office_id = user_data.get("office_id")
        if office_id:
            st.session_state["selected_office_id"] = office_id
        
        # Sidebar: user info + logout
        with st.sidebar:
            st.markdown(f"### 👤 {st.session_state['user_name']}")
            role_labels = {"hq": "🏛️ 本部", "staff": "👷 支援員"}
            st.caption(role_labels.get(st.session_state['login_role'], st.session_state['login_role']))
            authenticator.logout("ログアウト", key="logout_btn")
            st.divider()
        
        return True
    
    elif st.session_state.get("authentication_status") is False:
        st.error("ユーザー名またはパスワードが間違っています")
        return False
    
    elif st.session_state.get("authentication_status") is None:
        st.info("ユーザー名とパスワードを入力してください")
        # Show default credentials for testing
        with st.expander("🔑 テスト用アカウント"):
            st.code("""
本部: admin_sato / admin123
支援員: takahashi / staff123
            """)
        return False


# --- Staff Dashboard ---
def staff_dashboard(user, client):
    office_id = st.session_state.get("selected_office_id")
    offices_df = db_utils.get_offices()
    office_name = "未設定"
    if office_id and not offices_df.empty:
        match = offices_df[offices_df['id'] == office_id]
        if not match.empty:
            office_name = match.iloc[0]['name']

    # --- Sidebar Page Switcher ---
    page_mode = st.sidebar.radio(
        "📂 ページ切替",
        ["👤 マイページ", "🏢 事業所ページ"],
        key="staff_page_mode"
    )
    st.sidebar.divider()


    # === 事業所ページ ===
    if page_mode == '🏢 事業所ページ':
        st.info(f"📍 {office_name} | {user['name']} ({user['role']})")
        _render_office_tabs(user, client, office_id, offices_df)

    # === マイページ ===
    else:
        st.title(f"👤 マイページ: {user['name']} さん")
        st.info(f"📍 事業所: {office_name} | 役職: {user['role']}")

        tab5, tab6, tab7, tab8, tab9, tab_org = st.tabs([
            "📝 支援記録", "📚 研修資料", "🗣️ ロープレ", "🌱 1on1",
            "🏢 本部への質問", "📞 組織図・連絡網"
        ])

        # ================================================================
        # Tab 5: 支援記録
        # ================================================================
        with tab5:
            st.header("📝 支援記録")
            st.caption("利用者の支援内容を記録します")

            if not office_id:
                st.warning("事業所が未設定です。")
            else:
                clients_df_sr = db_utils.get_clients(office_id=office_id)
                active_clients_sr = clients_df_sr[clients_df_sr['usage_status'] == '利用者'] if not clients_df_sr.empty else pd.DataFrame()

                if not active_clients_sr.empty:
                    with st.expander("✏️ 新しい支援記録を追加", expanded=True):
                        with st.form("staff_support_record"):
                            sr_col1, sr_col2 = st.columns(2)
                            with sr_col1:
                                sr_client = st.selectbox("利用者", active_clients_sr['id'].tolist(),
                                    format_func=lambda x: active_clients_sr[active_clients_sr['id']==x]['name'].values[0],
                                    key="staff_sr_client")
                                sr_date = st.date_input("記録日", datetime.date.today(), key="staff_sr_date")
                            with sr_col2:
                                sr_svc = st.selectbox("サービス種別", ["通所", "欠席時対応", "施設外支援", "体験"], key="staff_sr_svc")
                                sr_condition = st.selectbox("体調", ["良好", "やや不調", "不調", "休憩あり"], key="staff_sr_cond")

                            sr_content = st.text_area("支援内容", height=150, key="staff_sr_content",
                                placeholder="・本日のプログラム参加状況\n・面談内容\n・行動観察\n・特記事項")
                            sr_goal = st.text_area("目標に対する進捗", height=80, key="staff_sr_goal",
                                placeholder="個別支援計画の目標に対する進捗状況")
                            sr_file = st.file_uploader("📎 ファイル添付", type=["pdf", "xlsx", "csv", "png", "jpg", "docx"], key="staff_sr_file")

                            if st.form_submit_button("📝 支援記録を保存", type="primary"):
                                file_note = f"\n📎 添付: {sr_file.name}" if sr_file else ""
                                db_utils.add_support_record(sr_client, str(sr_date), sr_svc,
                                    sr_content + file_note, sr_condition, sr_goal, user['id'], user['name'])
                                st.success("支援記録を保存しました！")
                                st.rerun()
                else:
                    st.info("この事業所に利用者が登録されていません。")

                # Record history
                st.divider()
                st.subheader("📜 支援記録一覧")
                sr_filter_col1, sr_filter_col2 = st.columns(2)
                sr_from = sr_filter_col1.date_input("開始日", datetime.date.today() - datetime.timedelta(days=30), key="staff_sr_from")
                sr_to = sr_filter_col2.date_input("終了日", datetime.date.today(), key="staff_sr_to")

                records = db_utils.get_support_records(date_from=str(sr_from), date_to=str(sr_to))
                if not records.empty:
                    for _, rec in records.iterrows():
                        with st.expander(f"📄 {rec['record_date']} — {rec['client_name']} [{rec['service_type']}]"):
                            st.write(f"**体調:** {rec['client_condition']}")
                            st.write(f"**支援内容:** {rec['support_content']}")
                            if rec['goal_progress']:
                                st.write(f"**目標進捗:** {rec['goal_progress']}")
                            st.caption(f"記録者: {rec['staff_name']}")
                else:
                    st.info("指定期間の記録はありません。")

        # ================================================================
        # Tab 6: 研修資料
        # ================================================================
        with tab6:
            st.header("📚 研修資料ライブラリ")
            st.caption("業務に必要な研修資料を確認できます")

            training_category = st.selectbox("カテゴリ選択", [
                "すべて", "🏢 事業所運営", "👥 利用者支援", "🤝 外交・営業",
                "📋 行政・制度", "🧠 障害理解・支援技法"
            ])

            materials = {
                "🏢 事業所運営": [
                    {"title": "朝礼・終礼の進め方マニュアル", "desc": "毎日の朝礼・終礼で確認すべき項目と進行手順。", "level": "初級"},
                    {"title": "KPI管理と運営数値の見方", "desc": "通所率、定着率、転換率など事業所運営KPIの意味と目標値。", "level": "中級"},
                    {"title": "加算の知識（基礎）", "desc": "欠席時対応加算、移行準備体制加算、初期加算等の概要。", "level": "初級"},
                    {"title": "knowbe操作マニュアル", "desc": "支援記録入力、実績記録確認、請求書出力。", "level": "初級"},
                ],
                "👥 利用者支援": [
                    {"title": "インテーク面談ガイド", "desc": "初回面談の流れ、ヒアリングポイント、アセスメントシート。", "level": "初級"},
                    {"title": "個別支援計画の作成方法", "desc": "アセスメント→計画→ケース会議→提示の流れ。", "level": "中級"},
                    {"title": "週次面談の進め方", "desc": "定期面談の確認事項、動機づけ面接法の基本。", "level": "初級"},
                    {"title": "就労定着支援の基礎", "desc": "就職後の定着支援、企業連携、定着率計算。", "level": "上級"},
                ],
                "🤝 外交・営業": [
                    {"title": "ハローワーク訪問マニュアル", "desc": "担当者との関係構築、求人情報収集、連携のポイント。", "level": "初級"},
                    {"title": "行政機関への営業ガイド", "desc": "障害福祉課、相談支援事業所へのアプローチ方法。", "level": "中級"},
                    {"title": "企業開拓（実習先・就職先）", "desc": "企業研究→アポ→訪問→フォローの流れ。", "level": "上級"},
                ],
                "📋 行政・制度": [
                    {"title": "障害福祉サービスの制度概要", "desc": "就労移行支援の法的位置づけ、利用期間、負担額。", "level": "初級"},
                    {"title": "受給者証の取得フロー", "desc": "相談支援→計画→申請→決定の流れ。", "level": "初級"},
                    {"title": "国保連請求の基礎", "desc": "月次請求の流れ、算定日数、加算の請求方法。", "level": "上級"},
                ],
                "🧠 障害理解・支援技法": [
                    {"title": "精神障害の基礎知識", "desc": "うつ、双極性障害、統合失調症、発達障害の特性と配慮。", "level": "初級"},
                    {"title": "合理的配慮の考え方", "desc": "障害者差別解消法、配慮の提供義務と具体例。", "level": "中級"},
                    {"title": "動機づけ面接法（MI）入門", "desc": "内発的動機づけを引き出す対話技法。", "level": "中級"},
                ],
            }

            for cat, items in materials.items():
                if training_category == "すべて" or training_category == cat:
                    st.subheader(cat)
                    for m in items:
                        lvl = {"初級": "🟢", "中級": "🟡", "上級": "🔴"}.get(m['level'], "⚪")
                        with st.expander(f"{lvl} {m['title']}  [{m['level']}]"):
                            st.write(m['desc'])
                            st.caption("※詳細はGoogleドライブの研修フォルダをご確認ください")

        # ================================================================
        # Tab 7: ロープレ・ケーススタディ（強化版）
        # ================================================================
        with tab7:
            st.header("🎭 ロープレ練習モード")
            st.caption("AIが相手役を演じ、実践的なロールプレイで支援スキルを磨きます")

            # --- Session state keys ---
            RP_MSGS = "rp_messages"
            RP_SCENARIO = "rp_active_scenario"
            RP_FEEDBACK = "rp_last_feedback"
            RP_ENDED = "rp_session_ended"
            if RP_MSGS not in st.session_state:
                st.session_state[RP_MSGS] = []
            if RP_SCENARIO not in st.session_state:
                st.session_state[RP_SCENARIO] = None
            if RP_ENDED not in st.session_state:
                st.session_state[RP_ENDED] = False

            # --- Scenario Selection Panel ---
            active_scenario = st.session_state[RP_SCENARIO]
            is_in_session = len(st.session_state[RP_MSGS]) > 0

            if not is_in_session:
                # === カテゴリ選択 ===
                sel_cat_label = st.radio(
                    "カテゴリ",
                    ["🤝 外交活動ロープレ", "👥 利用者獲得ロープレ"],
                    horizontal=True,
                    key="rp_cat_radio",
                )
                sel_cat = "外交活動" if "外交" in sel_cat_label else "利用者獲得"

                # === 難易度フィルター ===
                diff_cols = st.columns(3)
                difficulties = rp_scenarios.get_difficulties()
                sel_diff = None
                for i, d in enumerate(difficulties):
                    icon = rp_scenarios.get_difficulty_icon(d)
                    with diff_cols[i]:
                        if st.button(f"{icon} {d}", key=f"rp_diff_{d}", use_container_width=True):
                            st.session_state["rp_sel_difficulty"] = d
                sel_diff = st.session_state.get("rp_sel_difficulty", "初級")

                # === シナリオカード一覧 ===
                filtered = rp_scenarios.get_scenarios_by_difficulty(sel_diff, category=sel_cat)

                st.divider()
                st.subheader(f"{rp_scenarios.get_difficulty_icon(sel_diff)} {sel_diff}レベル — {sel_cat}")

                for sc in filtered:
                    with st.container(border=True):
                        sc_col1, sc_col2 = st.columns([3, 1])
                        with sc_col1:
                            st.markdown(f"#### {sc['title']}")
                            st.markdown(f"**相手:** {sc['character_name']} — {sc['character_summary']}")
                            st.caption(sc["situation"])
                        with sc_col2:
                            if st.button("🎬 開始", key=f"rp_start_{sc['id']}", type="primary", use_container_width=True):
                                st.session_state[RP_SCENARIO] = sc
                                st.session_state[RP_MSGS] = [
                                    {"role": "system", "content": sc["system_prompt"]},
                                    {"role": "assistant", "content": sc["opening_line"]},
                                ]
                                st.session_state[RP_ENDED] = False
                                st.session_state[RP_FEEDBACK] = None
                                st.rerun()

            # --- Active Roleplay Session ---
            else:
                sc = active_scenario
                if sc is None:
                    st.warning("シナリオ情報が見つかりません。リセットしてください。")
                    if st.button("🔄 リセット"):
                        st.session_state[RP_MSGS] = []
                        st.session_state[RP_SCENARIO] = None
                        st.session_state[RP_ENDED] = False
                        st.rerun()
                else:
                    # --- Info bar + Controls ---
                    info_col, ctrl_col = st.columns([3, 1])
                    with info_col:
                        diff_icon = rp_scenarios.get_difficulty_icon(sc["difficulty"])
                        st.markdown(
                            f"**{diff_icon} {sc['difficulty']}** | 🏷️ {sc['category']} | "
                            f"🎭 {sc['character_name']}（{sc['character_summary']}）"
                        )
                        st.caption(f"📋 {sc['title']}")
                    with ctrl_col:
                        if st.button("🔄 リセット", use_container_width=True, key="rp_reset_active"):
                            st.session_state[RP_MSGS] = []
                            st.session_state[RP_SCENARIO] = None
                            st.session_state[RP_ENDED] = False
                            st.session_state[RP_FEEDBACK] = None
                            st.rerun()

                    # --- Scenario detail expander ---
                    with st.expander("📖 シナリオ詳細・評価基準", expanded=False):
                        st.markdown(f"**状況設定:** {sc['situation']}")
                        st.markdown("**評価基準（各10点）:**")
                        for cr in sc["evaluation_criteria"]:
                            st.markdown(f"- **{cr['name']}**: {cr['description']}")

                    st.divider()

                    # --- Chat history ---
                    chat_container = st.container(height=450)
                    with chat_container:
                        for msg in st.session_state[RP_MSGS]:
                            if msg["role"] == "system":
                                continue
                            if msg["role"] == "assistant":
                                with st.chat_message("assistant", avatar="🎭"):
                                    st.markdown(msg["content"])
                            else:
                                with st.chat_message("user", avatar="👷"):
                                    st.markdown(msg["content"])

                    # --- Chat input (only if session not ended) ---
                    if not st.session_state[RP_ENDED]:
                        rp_input = st.chat_input("あなたの対応を入力してください…", key="rp_chat_input")
                        if rp_input and client:
                            st.session_state[RP_MSGS].append({"role": "user", "content": rp_input})
                            with chat_container:
                                with st.chat_message("user", avatar="👷"):
                                    st.markdown(rp_input)
                                with st.chat_message("assistant", avatar="🎭"):
                                    stream = client.chat.completions.create(
                                        model="gpt-4o",
                                        messages=st.session_state[RP_MSGS],
                                        stream=True,
                                    )
                                    response = st.write_stream(stream)
                            st.session_state[RP_MSGS].append({"role": "assistant", "content": response})
                        elif rp_input and not client:
                            st.warning("サイドバーから OpenAI API Key を入力してください。")

                    # --- Feedback & Save (at least 2 user messages) ---
                    user_msg_count = sum(1 for m in st.session_state[RP_MSGS] if m["role"] == "user")
                    if user_msg_count >= 2:
                        st.divider()
                        fb_col1, fb_col2, fb_col3 = st.columns(3)

                        # End session button
                        with fb_col1:
                            if not st.session_state[RP_ENDED]:
                                if st.button("🏁 ロープレ終了", use_container_width=True, type="secondary"):
                                    st.session_state[RP_ENDED] = True
                                    st.rerun()

                        # Evaluation button
                        with fb_col2:
                            if st.button("📊 AI評価をもらう", use_container_width=True, type="primary"):
                                if client:
                                    eval_prompt = rp_scenarios.build_evaluation_prompt(sc)
                                    eval_msgs = st.session_state[RP_MSGS] + [
                                        {"role": "user", "content": eval_prompt}
                                    ]
                                    with st.spinner("AIが評価を作成中..."):
                                        fb_resp = client.chat.completions.create(
                                            model="gpt-4o", messages=eval_msgs
                                        )
                                        fb_text = fb_resp.choices[0].message.content
                                        st.session_state[RP_FEEDBACK] = fb_text
                                        st.session_state[RP_ENDED] = True
                                        st.rerun()
                                else:
                                    st.warning("サイドバーから OpenAI API Key を入力してください。")

                        # Save button
                        with fb_col3:
                            if st.button("💾 記録を保存", use_container_width=True):
                                cat = sc["category"]
                                fb_saved = st.session_state.get(RP_FEEDBACK, "")
                                conv = [m for m in st.session_state[RP_MSGS] if m["role"] != "system"]
                                learning = st.session_state.get("rp_learning_note", "")
                                db_utils.save_roleplay_record(
                                    user["id"], user["name"], sc["title"], cat, conv,
                                    fb_saved if fb_saved else "", learning,
                                )
                                st.success("✅ ロープレ記録を保存しました！")

                        # Show feedback if available
                        if st.session_state.get(RP_FEEDBACK):
                            st.divider()
                            st.subheader("📊 評価結果")
                            st.markdown(st.session_state[RP_FEEDBACK])

                        # Learning notes
                        st.text_area(
                            "📖 学んだこと・気付きメモ",
                            key="rp_learning_note",
                            placeholder="このロープレで学んだことを記録してください…",
                        )

            # --- Roleplay History ---
            st.divider()
            st.subheader("📚 過去のロープレ記録")
            rp_history = db_utils.get_roleplay_records(user["id"])
            if not rp_history.empty:
                for _, rec in rp_history.iterrows():
                    with st.expander(f"🗓 {rec['created_at']} — {rec['scenario']}"):
                        st.write(f"**カテゴリ:** {rec['category']}")
                        if rec.get("learning_notes"):
                            st.info(f"📖 学んだこと: {rec['learning_notes']}")
                        if rec.get("ai_feedback"):
                            st.markdown(f"**AIフィードバック:**")
                            st.markdown(rec["ai_feedback"])
            else:
                st.info("まだロープレ記録がありません。シナリオを選んで練習してみましょう！")

        # ================================================================
        # Tab 8: 1on1 メンタリング
        # ================================================================
        with tab8:
            st.header("🌱 1on1")

            # Top-level: choose between supervisor 1on1 vs client 1on1 vs action mgmt vs AI mentor
            oo_mode = st.radio(
                "モード",
                ["👔 上司との1on1", "🧑‍🦱 利用者さんとの1on1", "✅ アクション管理", "💬 AIメンター"],
                horizontal=True, key="oo_mode_radio"
            )

            # ========================================
            # Supervisor 1on1
            # ========================================
            if oo_mode == "👔 上司との1on1":
                st.subheader("👔 上司との1on1 議事録")

                s_col1, s_col2 = st.columns(2)
                with s_col1:
                    oo_date = st.date_input("面談日", datetime.date.today(), key="oo_sup_date")
                    staff_list = db_utils.get_staff_list()
                    managers = staff_list[staff_list['role'] == 'manager']
                    mgr_options = {f"{r['name']}": r['id'] for _, r in managers.iterrows()} if not managers.empty else {"管理者未登録": 0}
                    mgr_name = st.selectbox("面談相手（上司）", list(mgr_options.keys()), key="oo_sup_mgr")
                with s_col2:
                    next_date = st.date_input("次回1on1予定日", key="oo_sup_next")

                minutes = st.text_area("議事録（話した内容）", height=180, key="oo_sup_min",
                                       placeholder="・相談した内容\n・上司からのフィードバック\n・今後の目標")

                st.markdown("**アクションアイテム（任意）**")
                ac1, ac2 = st.columns(2)
                with ac1:
                    action1 = st.text_input("アクション①", key="oo_sup_a1")
                    action1_due = st.date_input("期限①", key="oo_sup_a1d")
                with ac2:
                    action2 = st.text_input("アクション②", key="oo_sup_a2")
                    action2_due = st.date_input("期限②", key="oo_sup_a2d")

                if st.button("💾 議事録を保存", type="primary", key="oo_sup_save"):
                    mgr_id = mgr_options.get(mgr_name, 0)
                    rec_id = db_utils.save_oneonone_record(
                        mgr_id, mgr_name, user['id'], user['name'],
                        str(oo_date), minutes, str(next_date),
                        meeting_type='supervisor'
                    )
                    if action1.strip():
                        db_utils.add_oneonone_action(rec_id, user['id'], action1, str(action1_due))
                    if action2.strip():
                        db_utils.add_oneonone_action(rec_id, user['id'], action2, str(action2_due))
                    st.success("上司との1on1 議事録を保存しました！")
                    st.rerun()

                st.divider()
                st.subheader("📜 上司との1on1 履歴")
                sup_history = db_utils.get_oneonone_records(staff_id=user['id'], meeting_type='supervisor')
                if not sup_history.empty:
                    for _, rec in sup_history.iterrows():
                        with st.expander(f"🗓 {rec['meeting_date']} — 👔 {rec['manager_name']}"):
                            st.markdown(rec['minutes'])
                            if rec.get('next_meeting_date'):
                                st.caption(f"次回: {rec['next_meeting_date']}")
                            actions = db_utils.get_oneonone_actions(record_id=rec['id'])
                            if not actions.empty:
                                st.markdown("**アクションアイテム:**")
                                for _, a in actions.iterrows():
                                    status_icon = "✅" if a['status'] == 'done' else "⬜"
                                    st.write(f"{status_icon} {a['action_text']} (期限: {a['due_date']})")
                else:
                    st.info("まだ上司との1on1記録がありません。")

            # ========================================
            # Client 1on1
            # ========================================
            elif oo_mode == "🧑‍🦱 利用者さんとの1on1":
                st.subheader("🧑‍🦱 利用者さんとの1on1 議事録")

                c_col1, c_col2 = st.columns(2)
                with c_col1:
                    oo_c_date = st.date_input("面談日", datetime.date.today(), key="oo_cli_date")
                    # Get clients for this office
                    clients_df = db_utils.get_clients(office_id=office_id)
                    if not clients_df.empty:
                        cli_options = {f"{r['name']}": r['id'] for _, r in clients_df.iterrows()}
                    else:
                        cli_options = {"利用者未登録": 0}
                    cli_name = st.selectbox("面談相手（利用者さん）", list(cli_options.keys()), key="oo_cli_name")
                with c_col2:
                    oo_c_next = st.date_input("次回面談予定日", key="oo_cli_next")
                    oo_c_topic = st.selectbox("面談種別", [
                        "定期面談", "個別相談", "就労準備アセスメント",
                        "目標設定", "振り返り", "その他"
                    ], key="oo_cli_topic")

                c_minutes = st.text_area("面談記録", height=180, key="oo_cli_min",
                                         placeholder="・利用者さんの様子\n・話した内容\n・今後のサポート方針")

                st.markdown("**フォローアップ項目（任意）**")
                fc1, fc2 = st.columns(2)
                with fc1:
                    c_action1 = st.text_input("フォロー①", key="oo_cli_a1")
                    c_action1_due = st.date_input("期限①", key="oo_cli_a1d")
                with fc2:
                    c_action2 = st.text_input("フォロー②", key="oo_cli_a2")
                    c_action2_due = st.date_input("期限②", key="oo_cli_a2d")

                if st.button("💾 面談記録を保存", type="primary", key="oo_cli_save"):
                    cli_id = cli_options.get(cli_name, 0)
                    full_minutes = f"【{oo_c_topic}】\n{c_minutes}"
                    rec_id = db_utils.save_oneonone_record(
                        0, '', user['id'], user['name'],
                        str(oo_c_date), full_minutes, str(oo_c_next),
                        meeting_type='client', client_id=cli_id, client_name=cli_name
                    )
                    if c_action1.strip():
                        db_utils.add_oneonone_action(rec_id, user['id'], c_action1, str(c_action1_due))
                    if c_action2.strip():
                        db_utils.add_oneonone_action(rec_id, user['id'], c_action2, str(c_action2_due))
                    st.success("利用者さんとの面談記録を保存しました！")
                    st.rerun()

                st.divider()
                st.subheader("📜 利用者さんとの1on1 履歴")
                cli_history = db_utils.get_oneonone_records(staff_id=user['id'], meeting_type='client')
                if not cli_history.empty:
                    for _, rec in cli_history.iterrows():
                        label = rec.get('client_name') or '利用者'
                        with st.expander(f"🗓 {rec['meeting_date']} — 🧑‍🦱 {label}"):
                            st.markdown(rec['minutes'])
                            if rec.get('next_meeting_date'):
                                st.caption(f"次回: {rec['next_meeting_date']}")
                            actions = db_utils.get_oneonone_actions(record_id=rec['id'])
                            if not actions.empty:
                                st.markdown("**フォローアップ:**")
                                for _, a in actions.iterrows():
                                    status_icon = "✅" if a['status'] == 'done' else "⬜"
                                    st.write(f"{status_icon} {a['action_text']} (期限: {a['due_date']})")
                else:
                    st.info("まだ利用者さんとの1on1記録がありません。")

            # ========================================
            # Action Management (shared)
            # ========================================
            elif oo_mode == "✅ アクション管理":
                st.subheader("アクションアイテム管理")
                actions = db_utils.get_oneonone_actions(staff_id=user['id'])
                if not actions.empty:
                    pending = actions[actions['status'] == 'pending']
                    done = actions[actions['status'] == 'done']

                    if not pending.empty:
                        st.markdown("### ⬜ 未完了")
                        for _, a in pending.iterrows():
                            st.write(f"📌 **{a['action_text']}** (期限: {a['due_date']})")
                            comp_note = st.text_input("完了メモ", key=f"comp_{a['id']}")
                            if st.button("✅ 完了にする", key=f"done_{a['id']}"):
                                db_utils.complete_oneonone_action(a['id'], comp_note)
                                st.success("完了しました！")
                                st.rerun()
                            st.markdown("---")

                    if not done.empty:
                        st.markdown("### ✅ 完了済み")
                        for _, a in done.iterrows():
                            st.write(f"✅ ~~{a['action_text']}~~ — {a['completion_notes'] or ''}")
                else:
                    st.info("アクションアイテムはありません。")

            # ========================================
            # AI Mentor (shared)
            # ========================================
            else:
                st.subheader("AIメンター相談室")
                if "mentor_messages" not in st.session_state:
                    st.session_state.mentor_messages = [{"role": "system", "content": "あなたは経験豊富なキャリアカウンセラー兼メンタルコーチです。"}]
                    st.session_state.mentor_messages.append({"role": "assistant", "content": "お疲れ様です。今日は何か気になることや、モヤモヤしていることはありますか？"})

                for msg in st.session_state.mentor_messages:
                    if msg["role"] != "system":
                        with st.chat_message(msg["role"], avatar="🌱" if msg["role"] == "assistant" else None):
                            st.write(msg["content"])

                mentor_input = st.chat_input("相談内容を入力...", key="mentor_chat")
                if mentor_input and client:
                    st.session_state.mentor_messages.append({"role": "user", "content": mentor_input})
                    with st.chat_message("user"):
                        st.write(mentor_input)
                    with st.chat_message("assistant", avatar="🌱"):
                        stream = client.chat.completions.create(
                            model="gpt-4o",
                            messages=st.session_state.mentor_messages,
                            stream=True,
                        )
                        response = st.write_stream(stream)
                    st.session_state.mentor_messages.append({"role": "assistant", "content": response})

        # ================================================================
        # Tab 9: 本部への質問（AI一次対応）
        # ================================================================
        with tab9:
            st.header("🏢 本部への質問")
            st.caption("就業規則・社内制度について、AIアシスタントが一次対応します。深刻な相談は専門窓口をご案内します。")

            # NotebookLM (Gemini) status
            nlm_ok = notebooklm_helper.is_authenticated()
            nlm_status = notebooklm_helper.get_status()

            if nlm_ok and nlm_status["uploaded_files_count"] > 0:
                st.success(
                    f"📚 NotebookLM連携中 — {nlm_status['uploaded_files_count']}件の社内資料を元に回答します",
                    icon="✅"
                )
            elif nlm_ok:
                st.info("📚 Gemini API接続済み。右の「📎 資料管理」から社内資料をアップロードすると、それを元に回答できます。")
            else:
                st.info("💡 サイドバーから Gemini API Key を入力すると、社内資料を元にAIが回答できます。")

            # --- Session state ---
            HQ_MSGS = "hq_messages"
            if HQ_MSGS not in st.session_state:
                st.session_state[HQ_MSGS] = []

            # --- FAQ Quick Buttons ---
            st.markdown("#### 💡 よくある質問")
            faq_cols = st.columns(4)
            faqs = company_rules.get_faq_suggestions()
            for i, faq in enumerate(faqs):
                with faq_cols[i % 4]:
                    if st.button(faq, key=f"hq_faq_{i}", use_container_width=True):
                        st.session_state["hq_pending_question"] = faq

            st.divider()

            # --- Chat UI ---
            hq_col1, hq_col2 = st.columns([3, 1])

            with hq_col2:
                st.markdown("#### 📞 直接相談窓口")
                with st.container(border=True):
                    st.markdown("**人事部**: 03-XXXX-XXXX")
                    st.markdown("**総務部**: 03-XXXX-XXXX")
                    st.markdown("**EAP相談**: 0120-XXX-XXX")
                    st.caption("24時間対応・匿名OK")

                # Document upload for NotebookLM/Gemini
                if nlm_ok:
                    st.markdown("#### 📎 社内資料管理")
                    uploaded_files = st.file_uploader(
                        "資料をアップロード",
                        type=["pdf", "txt", "md", "docx", "csv"],
                        accept_multiple_files=True,
                        key="hq_doc_upload",
                        label_visibility="collapsed",
                    )
                    if uploaded_files:
                        import tempfile
                        for uf in uploaded_files:
                            # Save temp and upload to Gemini
                            tmp_path = os.path.join(tempfile.gettempdir(), uf.name)
                            with open(tmp_path, "wb") as f:
                                f.write(uf.getbuffer())
                            with st.spinner(f"📤 {uf.name} をアップロード中…"):
                                result = notebooklm_helper.upload_documents([tmp_path])
                                if result:
                                    st.success(f"✅ {uf.name}")

                    # Show uploaded files count
                    if nlm_status["uploaded_files_count"] > 0:
                        with st.expander(f"📂 登録済み資料 ({nlm_status['uploaded_files_count']}件)"):
                            for fname in nlm_status["uploaded_files"]:
                                st.caption(f"📄 {fname}")

                if st.button("🔄 チャットリセット", use_container_width=True):
                    st.session_state[HQ_MSGS] = []
                    st.session_state.pop("hq_pending_question", None)
                    st.rerun()

            with hq_col1:
                # Chat container
                chat_box = st.container(height=420)
                with chat_box:
                    if not st.session_state[HQ_MSGS]:
                        st.info("👋 こんにちは！就業規則や社内制度について、何でもお気軽にご質問ください。")

                    for msg in st.session_state[HQ_MSGS]:
                        if msg["role"] == "system":
                            continue
                        if msg["role"] == "assistant":
                            with st.chat_message("assistant", avatar="🏢"):
                                st.markdown(msg["content"])
                        else:
                            with st.chat_message("user", avatar="👷"):
                                st.markdown(msg["content"])

                # Chat input
                pending_q = st.session_state.pop("hq_pending_question", None)
                hq_input = st.chat_input("質問を入力してください…", key="hq_chat_input")
                question = pending_q or hq_input

                if question:
                    # 1) Escalation check
                    needs_escalation, matched_kw, esc_category = company_rules.check_escalation(question)

                    # 2) Query NotebookLM for relevant knowledge
                    nlm_context = ""
                    nlm_result = None
                    if nlm_ok:
                        with st.spinner("📚 社内資料を検索中…"):
                            nlm_result = notebooklm_helper.query_notebooklm(question)
                            if nlm_result["success"] and nlm_result["answer"]:
                                nlm_context = nlm_result["answer"]

                    # 3) Initialize system prompt (refresh each time with NLM context)
                    system_prompt = company_rules.build_system_prompt(notebooklm_context=nlm_context)
                    # Update or insert system prompt
                    if st.session_state[HQ_MSGS] and st.session_state[HQ_MSGS][0]["role"] == "system":
                        st.session_state[HQ_MSGS][0]["content"] = system_prompt
                    else:
                        st.session_state[HQ_MSGS].insert(0, {
                            "role": "system",
                            "content": system_prompt
                        })

                    # 4) Add user message
                    st.session_state[HQ_MSGS].append({"role": "user", "content": question})

                    # 5) Show escalation warning if needed
                    if needs_escalation:
                        with chat_box:
                            with st.chat_message("user", avatar="👷"):
                                st.markdown(question)
                            with st.chat_message("assistant", avatar="🚨"):
                                esc_contact = company_rules.ESCALATION_CONTACTS.get(
                                    esc_category, "📞 本部: 03-XXXX-XXXX"
                                )
                                escalation_msg = f"""⚠️ **この内容は専門の窓口へのご相談をお勧めします。**

    **相談カテゴリ:** {esc_category}

    **連絡先:**
    {esc_contact}

    ---
    *AIでの回答も行いますが、必ず上記の窓口にもご連絡ください。
    あなたのことを大切に思っています。一人で抱え込まないでくださいね。* 🤝"""
                                st.markdown(escalation_msg)
                        st.session_state[HQ_MSGS].append({
                            "role": "assistant", "content": escalation_msg
                        })

                    # 6) Get AI response (GPT-4o with NotebookLM knowledge)
                    if client:
                        with chat_box:
                            if not needs_escalation:
                                with st.chat_message("user", avatar="👷"):
                                    st.markdown(question)
                            with st.chat_message("assistant", avatar="🏢"):
                                # Show NLM source badge if context was used
                                if nlm_context:
                                    st.caption("📚 NotebookLM の社内資料を参照して回答しています")
                                stream = client.chat.completions.create(
                                    model="gpt-4o",
                                    messages=st.session_state[HQ_MSGS],
                                    stream=True,
                                )
                                ai_response = st.write_stream(stream)
                        st.session_state[HQ_MSGS].append({
                            "role": "assistant", "content": ai_response
                        })

                        # 7) Save to DB
                        db_utils.save_hq_question(
                            staff_id=user["id"],
                            staff_name=user["name"],
                            office_id=office_id,
                            question=question,
                            ai_answer=ai_response,
                            is_escalated=needs_escalation,
                            escalation_category=esc_category,
                        )
                    else:
                        st.warning("サイドバーから OpenAI API Key を入力してください。")

            # --- Question History ---
            st.divider()
            st.subheader("📜 質問履歴")
            hq_history = db_utils.get_hq_questions(staff_id=user["id"])
            if not hq_history.empty:
                for _, rec in hq_history.head(20).iterrows():
                    esc_badge = "🚨 エスカレーション" if rec.get("is_escalated") else ""
                    with st.expander(f"🗓 {rec['created_at']} — {rec['question'][:50]}… {esc_badge}"):
                        st.markdown(f"**質問:** {rec['question']}")
                        st.markdown(f"**AI回答:** {rec['ai_answer']}")
                        if rec.get("is_escalated"):
                            st.warning(f"エスカレーション: {rec.get('escalation_category', '未分類')}")
            else:
                st.info("まだ質問履歴がありません。")


    # --- Manager Dashboard ---
        with tab_org:
            st.header("📞 組織図＆緊急連絡網")
            if not office_id:
                st.warning("事業所が未設定です。")
            else:
                ec_mode = st.radio("表示", ["👷 職員連絡網", "🎓 利用者連絡先", "🏢 組織図"], horizontal=True, key="staff_ec_mode")

                if ec_mode == "👷 職員連絡網":
                    contacts_df = db_utils.get_emergency_contacts(person_type="staff", office_id=office_id)
                    if not contacts_df.empty:
                        st.dataframe(contacts_df[['person_name', 'phone', 'email', 'relationship', 'notes']], 
                                     use_container_width=True, hide_index=True)
                    else:
                        st.info("職員の連絡先が登録されていません")
                    
                    with st.expander("➕ 職員連絡先を追加"):
                        with st.form("add_staff_contact_mypage"):
                            ec_name = st.text_input("氏名")
                            ec_phone = st.text_input("電話番号")
                            ec_email = st.text_input("メール")
                            ec_rel = st.text_input("役職/関係")
                            if st.form_submit_button("追加"):
                                if ec_name:
                                    db_utils.add_emergency_contact(person_type="staff", person_name=ec_name, 
                                                                    phone=ec_phone, email=ec_email, relationship=ec_rel,
                                                                    office_id=office_id)
                                    st.success("追加しました")
                                    st.rerun()

                elif ec_mode == "🎓 利用者連絡先":
                    contacts_df = db_utils.get_emergency_contacts(person_type="client", office_id=office_id)
                    if not contacts_df.empty:
                        st.dataframe(contacts_df[['person_name', 'phone', 'email', 'relationship', 'notes']], 
                                     use_container_width=True, hide_index=True)
                    else:
                        st.info("利用者の緊急連絡先が登録されていません")

                else:
                    st.subheader("🏢 組織図")
                    st.markdown("""
                    ```
                    ┌─────────────────────────────┐
                    │        📍 事業所長           │
                    │    サービス管理責任者         │
                    └──────────┬──────────────────┘
                               │
                    ┌──────────┴──────────────────┐
                    │                             │
                ┌───┴───┐                    ┌────┴────┐
                │ 支援員A │                    │ 支援員B │
                └───┬───┘                    └────┬────┘
                    │                             │
                ┌───┴──────┐              ┌───────┴───┐
                │ 利用者1-5 │              │ 利用者6-10│
                └──────────┘              └───────────┘
                    ```
                    """)
                    
                    staff_df = db_utils.get_staff_list(office_id=office_id)
                    if not staff_df.empty:
                        st.subheader("📋 所属スタッフ一覧")
                        st.dataframe(staff_df[['name', 'role']], use_container_width=True, hide_index=True)


def hq_dashboard(user, client):
    """本部ダッシュボード - 全事業所横断管理"""
    _manager_dashboard_internal(user, client, mode="hq")

def office_dashboard(user, client):
    """事業所ダッシュボード - 事業所単位管理"""
    _manager_dashboard_internal(user, client, mode="office")

def _manager_dashboard_internal(user, client, mode="hq"):
    if mode == "hq":
        st.title("🏛️ 本部ダッシュボード")
    else:
        st.title("🏢 事業所ダッシュボード")

    # --- Sidebar: Office Filter ---
    offices_df = db_utils.get_offices()
    if mode == "hq":
        # 本部は全事業所選択可能
        if not offices_df.empty:
            office_options = [(None, "🌐 全事業所")] + [
                (row['id'], f"📍 {row['name']}") for _, row in offices_df.iterrows()
            ]
            selected = st.sidebar.selectbox(
                "📍 表示事業所",
                options=[o[0] for o in office_options],
                format_func=lambda x: dict(office_options).get(x, "全事業所"),
                key="office_filter"
            )
            st.session_state["selected_office_id"] = selected
        else:
            st.session_state["selected_office_id"] = None
    else:
        # 事業所モードはログイン時の事業所固定
        pass

    current_office_id = st.session_state.get("selected_office_id")
    office_label = "全事業所"
    if current_office_id and not offices_df.empty:
        match = offices_df[offices_df['id'] == current_office_id]
        if not match.empty:
            office_label = match.iloc[0]['name']

    role_label = "本部" if mode == "hq" else "事業所"
    st.info(f"ログイン: {user['name']} ({role_label}) | 📍 {office_label}")

    if mode == "hq":
        _render_hq_tabs(user, client, current_office_id, offices_df)
    else:
        _render_office_tabs(user, client, current_office_id, offices_df)


def _render_hq_tabs(user, client, current_office_id, offices_df):
    """本部用タブをレンダリング"""
    tab0, tab2 = st.tabs([
        "🏢 全事業所P&L", "📊 営業KPI"
    ])

    with tab0:
        st.header("🏢 事業所別 P&L・KPI 良実管理")
        
        fin_col1, fin_col2 = st.columns(2)
        fin_year = fin_col1.number_input("年", value=2025, key="fin_year")
        fin_month = fin_col2.number_input("月", value=1, min_value=1, max_value=12, key="fin_month")
        
        fin_df = db_utils.get_office_financials(year=int(fin_year), month=int(fin_month))
        
        if not fin_df.empty:
            def rate_icon(actual, target):
                if target == 0:
                    return "➖"
                rate = actual / target * 100
                if rate >= 100:
                    return f"🟢 {rate:.0f}%"
                elif rate >= 80:
                    return f"🟡 {rate:.0f}%"
                else:
                    return f"🔴 {rate:.0f}%"
            
            def sga_icon(actual, target):
                """販管費は低いほうが良い"""
                if target == 0:
                    return "➖"
                rate = actual / target * 100
                if rate <= 100:
                    return f"🟢 {rate:.0f}%"
                elif rate <= 110:
                    return f"🟡 {rate:.0f}%"
                else:
                    return f"🔴 {rate:.0f}%"
            
            # Summary metrics
            total_rev = fin_df['revenue'].sum()
            total_rev_target = fin_df['revenue_target'].sum()
            total_sga = fin_df['sga'].sum()
            total_profit = fin_df['profit'].sum()
            total_new = fin_df['new_users'].sum()
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("💰 全事業所売上", f"¥{total_rev:,.0f}", f"目標比 {total_rev/total_rev_target*100:.0f}%" if total_rev_target else "")
            m2.metric("📊 全事業所販管費", f"¥{total_sga:,.0f}")
            m3.metric("📈 全事業所利益", f"¥{total_profit:,.0f}")
            m4.metric("👥 新規利用者(合計)", f"{total_new}名")
            
            st.divider()
            st.subheader("📊 事業所別 詳細比較")
            
            display_data = []
            for _, row in fin_df.iterrows():
                display_data.append({
                    '事業所': row['office_name'],
                    '売上': f"¥{int(row['revenue']):,}",
                    '売上目標': f"¥{int(row['revenue_target']):,}",
                    '売上達成': rate_icon(row['revenue'], row['revenue_target']),
                    '販管費': f"¥{int(row['sga']):,}",
                    '販管費目標': f"¥{int(row['sga_target']):,}",
                    '販管費管理': sga_icon(row['sga'], row['sga_target']),
                    '利益': f"¥{int(row['profit']):,}",
                    '利益目標': f"¥{int(row['profit_target']):,}",
                    '利益達成': rate_icon(row['profit'], row['profit_target']),
                    '新規': f"{int(row['new_users'])}名",
                    '新規目標': f"{int(row['new_users_target'])}名",
                    '新規達成': rate_icon(row['new_users'], row['new_users_target']),
                })
            
            st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
            
            # Ranking
            st.subheader("🏆 事業所ランキング（利益順）")
            ranked = fin_df.sort_values('profit', ascending=False).reset_index(drop=True)
            for i, row in ranked.iterrows():
                rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"  {i+1}."
                profit_color = "🟢" if row['profit'] > 0 else "🔴"
                st.markdown(f"{rank_emoji} **{row['office_name']}** — {profit_color} 利益 ¥{int(row['profit']):,} | 売上 ¥{int(row['revenue']):,}")
        else:
            st.info("📊 この期間のデータがありません。")

    with tab2:
        st.header("事業所別 営業KPI ダッシュボード")
        st.caption("直近120日間（INDEED除く）")

        kpi_df = db_utils.get_office_kpi()

        if not kpi_df.empty:
            # Target rates
            targets = {
                '問合→面談': 60.0, '面談→体験': 75.0, '体験→入所': 40.0,
                '問合→入所': 18.0, '面談→入所': 30.0
            }

            st.subheader("🎯 目標レート")
            tc1, tc2, tc3, tc4, tc5 = st.columns(5)
            tc1.metric("問合→面談", "60%")
            tc2.metric("面談→体験", "75%")
            tc3.metric("体験→入所", "40%")
            tc4.metric("問合→入所率", "18%")
            tc5.metric("面談→入所率", "30%")

            # Overall summary
            total = kpi_df[kpi_df['office_name'] == '全体'].iloc[0]
            st.divider()
            st.subheader("📈 全体サマリー")
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("問合数", f"{int(total['inquiries'])}件")
            sc2.metric("面談数", f"{int(total['interviews'])}件")
            sc3.metric("体験数", f"{int(total['trials'])}件")
            sc4.metric("入所数", f"{int(total['enrollments'])}件")

            # Conversion rates with delta
            cc1, cc2, cc3, cc4, cc5 = st.columns(5)
            cc1.metric("問合→面談", f"{total['inquiry_to_interview']}%", 
                       f"{total['inquiry_to_interview'] - targets['問合→面談']:.1f}%")
            cc2.metric("面談→体験", f"{total['interview_to_trial']}%",
                       f"{total['interview_to_trial'] - targets['面談→体験']:.1f}%")
            cc3.metric("体験→入所", f"{total['trial_to_enrollment']}%",
                       f"{total['trial_to_enrollment'] - targets['体験→入所']:.1f}%")
            cc4.metric("問合→入所率", f"{total['inquiry_to_enrollment']}%",
                       f"{total['inquiry_to_enrollment'] - targets['問合→入所']:.1f}%")
            cc5.metric("面談→入所率", f"{total['interview_to_enrollment']}%",
                       f"{total['interview_to_enrollment'] - targets['面談→入所']:.1f}%")

            st.divider()
            st.subheader("🏢 事業所別 詳細")

            # Prepare display dataframe
            offices = kpi_df[kpi_df['office_name'] != '全体'].copy()
            display = offices[['office_name', 'inquiries', 'interviews', 'trials', 'enrollments',
                              'inquiry_to_interview', 'interview_to_trial', 'trial_to_enrollment',
                              'inquiry_to_enrollment', 'interview_to_enrollment',
                              'interview_cancel_rate', 'trial_cancel_rate']].copy()
            display.columns = ['事業所', '問合数', '面談数', '体験数', '入所数',
                              '問合→面談%', '面談→体験%', '体験→入所%',
                              '問合→入所%', '面談→入所%', '面談Cancel%', '体験Cancel%']

            def color_rate(val, target, reverse=False):
                import pandas as _pd
                if _pd.isna(val): return ''
                if reverse:
                    return 'background-color: #ffcccc' if val > 30 else ''
                return 'background-color: #ffcccc' if val < target * 0.8 else ('background-color: #ccffcc' if val >= target else '')

            styled = display.style.apply(lambda x: [
                '', '', '', '', '',
                color_rate(x['問合→面談%'], 60), color_rate(x['面談→体験%'], 75),
                color_rate(x['体験→入所%'], 40), color_rate(x['問合→入所%'], 18),
                color_rate(x['面談→入所%'], 30), color_rate(x['面談Cancel%'], 30, True),
                color_rate(x['体験Cancel%'], 30, True)
            ], axis=1)

            st.dataframe(styled, use_container_width=True, hide_index=True)

            st.caption("🔴 赤: 目標達成率80%未満 | 🟢 緑: 目標達成 | キャンセル率: 30%超で赤")

            # Monthly Target vs Actual
            st.divider()
            st.subheader("📅 月次 目標 vs 実績")

            monthly_df = db_utils.get_monthly_targets()
            if not monthly_df.empty:
                offices_list = ['全体', '川崎', '横浜', '西船橋', '本厚木', '柏', '三鷹', '関内', '川越']
                months = monthly_df[['year', 'month']].drop_duplicates().sort_values(['year', 'month'])

                for _, m_row in months.iterrows():
                    yr, mn = int(m_row['year']), int(m_row['month'])
                    st.markdown(f"**{yr}年{mn}月**")
                    m_data = monthly_df[(monthly_df['year'] == yr) & (monthly_df['month'] == mn)]

                    # Build per-office columns
                    rows = []
                    for _, r in m_data.iterrows():
                        rows.append({
                            '事業所': r['office_name'],
                            '目標': int(r['target']),
                            '実績': int(r['actual']),
                            'ギャップ': int(r['gap']),
                            '達成率': f"{r['achievement_rate']:.1f}%"
                        })
                    display_monthly = pd.DataFrame(rows)

                    def color_achievement(val):
                        if isinstance(val, str) and '%' in val:
                            rate = float(val.replace('%', ''))
                            if rate >= 100: return 'background-color: #ccffcc'
                            if rate < 80: return 'background-color: #ffcccc'
                        return ''

                    def color_gap(val):
                        if isinstance(val, (int, float)):
                            if val < 0: return 'color: green; font-weight: bold'
                            if val > 0: return 'color: red'
                        return ''

                    styled_m = display_monthly.style.map(color_achievement, subset=['達成率']).map(color_gap, subset=['ギャップ'])
                    st.dataframe(styled_m, use_container_width=True, hide_index=True)
        else:
            st.info("KPIデータがありません。")




def _render_office_tabs(user, client, current_office_id, offices_df):
    """事業所用タブをレンダリング"""
    tab1, tab3, tab4, tab5, tab8, tab9, tab10, tab7, tab11, tab12, tab13, tab14 = st.tabs([
        "📋 朝礼・終礼", "📒 利用者台帳", "🏢 事業所運営",
        "👥 支援員・KPI", "📋 利用実績", "📝 支援記録", "💰 請求・CSV",
        "📑 行政申請", "📋 個別支援計画", "📊 モニタリング", "📝 アセスメント", "⚠️ 減算・自己負担"
    ])

    with tab1:
        st.header("朝礼・終礼 デイリーチェック")

        today = datetime.date.today()
        meeting_date = st.date_input("日付", value=today, key="meeting_date")

        meeting_mode = st.radio("会議種別", ["🌅 朝礼", "🌆 終礼"], horizontal=True)
        m_type = "morning" if "朝礼" in meeting_mode else "evening"

        # Load existing check state
        checked_ids = db_utils.get_checklist_log(meeting_date)
        existing_notes = db_utils.get_meeting_notes(meeting_date, m_type)

        if m_type == "morning":
            # --- 朝礼 ---
            st.subheader("📊 通所状況")
            mc1, mc2, mc3, mc4 = st.columns(4)
            att_total = mc1.number_input("通所人数（予定）", min_value=0, value=int(existing_notes['attendance_total']) if existing_notes is not None else 0, key="att_t")
            att_full = mc2.number_input("終日通所", min_value=0, value=int(existing_notes['attendance_fullday']) if existing_notes is not None else 0, key="att_f")
            att_am = mc3.number_input("午前のみ", min_value=0, value=int(existing_notes['attendance_am']) if existing_notes is not None else 0, key="att_am")
            att_pm = mc4.number_input("午後のみ", min_value=0, value=int(existing_notes['attendance_pm']) if existing_notes is not None else 0, key="att_pm")

            st.subheader("✅ 出勤後、すぐに確認しよう！")
            items = db_utils.get_checklist_items("morning", "daily")
            new_checked = []
            for _, item in items.iterrows():
                val = st.checkbox(item['item_text'], value=(item['id'] in checked_ids), key=f"m_{item['id']}")
                if val:
                    new_checked.append(item['id'])

            st.subheader("📝 本日の予定・行動・共有事項")
            schedule_notes = st.text_area("予定を入力", value=existing_notes['schedule_notes'] if existing_notes is not None and existing_notes['schedule_notes'] else "", key="sched_notes", height=100)

            st.subheader("📣 業務連絡")
            biz_notes = st.text_area("業務連絡を入力", value=existing_notes['business_notes'] if existing_notes is not None and existing_notes['business_notes'] else "", key="biz_notes", height=100)

            st.subheader("📅 週次面談")
            interviews = db_utils.get_weekly_interviews(str(meeting_date))
            if not interviews.empty:
                st.dataframe(interviews[['client_name', 'content', 'staff_name']], use_container_width=True)
            with st.expander("週次面談を追加"):
                with st.form("add_interview"):
                    iv_client = st.text_input("利用者氏名")
                    iv_content = st.text_area("面談内容（事前確認）")
                    iv_staff = st.text_input("担当スタッフ")
                    if st.form_submit_button("追加"):
                        db_utils.add_weekly_interview(str(meeting_date), iv_client, iv_content, iv_staff)
                        st.success("追加しました")
                        st.rerun()

            if st.button("朝礼内容を保存", type="primary"):
                db_utils.save_checklist_log(str(meeting_date), new_checked)
                db_utils.save_meeting_notes(str(meeting_date), "morning", {
                    'attendance_total': att_total, 'attendance_fullday': att_full,
                    'attendance_am': att_am, 'attendance_pm': att_pm,
                    'schedule_notes': schedule_notes, 'business_notes': biz_notes
                })
                st.success("朝礼内容を保存しました！")

        else:
            # --- 終礼 ---
            st.subheader("📊 通所実績")
            ec1, ec2, ec3, ec4 = st.columns(4)
            att_total = ec1.number_input("通所人数", min_value=0, value=int(existing_notes['attendance_total']) if existing_notes is not None else 0, key="e_att_t")
            abs_bonus = ec2.number_input("欠席時対応加算", min_value=0, value=int(existing_notes['absence_with_bonus']) if existing_notes is not None else 0, key="e_abs_b")
            abs_no = ec3.number_input("欠席（非加算）", min_value=0, value=int(existing_notes['absence_no_bonus']) if existing_notes is not None else 0, key="e_abs_n")
            late = ec4.number_input("遅刻・早退", min_value=0, value=int(existing_notes['late_early']) if existing_notes is not None else 0, key="e_late")

            st.subheader("✅ 毎日確認する（事業所の全員で確認しましょう）")
            items_daily = db_utils.get_checklist_items("evening", "daily")
            new_checked = []
            for _, item in items_daily.iterrows():
                val = st.checkbox(item['item_text'], value=(item['id'] in checked_ids), key=f"e_{item['id']}")
                if val:
                    new_checked.append(item['id'])

            st.subheader("✅ 週末に行う事")
            items_weekly = db_utils.get_checklist_items("evening", "weekly")
            for _, item in items_weekly.iterrows():
                val = st.checkbox(item['item_text'], value=(item['id'] in checked_ids), key=f"ew_{item['id']}")
                if val:
                    new_checked.append(item['id'])

            st.subheader("✅ 月末・月初に確認する")
            items_monthly = db_utils.get_checklist_items("evening", "monthly")
            for _, item in items_monthly.iterrows():
                val = st.checkbox(item['item_text'], value=(item['id'] in checked_ids), key=f"em_{item['id']}")
                if val:
                    new_checked.append(item['id'])

            st.subheader("📝 ご利用者共有事項・振り返り")
            client_notes = st.text_area("利用者共有事項", value=existing_notes['client_notes'] if existing_notes is not None and existing_notes['client_notes'] else "", key="cl_notes", height=100)

            st.subheader("📣 業務連絡")
            biz_notes = st.text_area("業務連絡を入力", value=existing_notes['business_notes'] if existing_notes is not None and existing_notes['business_notes'] else "", key="e_biz", height=100)

            st.subheader("📌 その他（備考欄）")
            other_notes = st.text_area("その他", value=existing_notes['other_notes'] if existing_notes is not None and existing_notes['other_notes'] else "", key="e_other", height=80)

            if st.button("終礼内容を保存", type="primary"):
                db_utils.save_checklist_log(str(meeting_date), new_checked)
                db_utils.save_meeting_notes(str(meeting_date), "evening", {
                    'attendance_total': att_total,
                    'absence_with_bonus': abs_bonus, 'absence_no_bonus': abs_no, 'late_early': late,
                    'client_notes': client_notes, 'business_notes': biz_notes, 'other_notes': other_notes
                })
                st.success("終礼内容を保存しました！")

        # 就労定着率 × 基本報酬 Reference Table (always visible)
        st.divider()
        st.subheader("📈 就労定着率 × 基本報酬 単位テーブル")
        rates = db_utils.get_reward_rates()
        if not rates.empty:
            st.dataframe(rates[['retention_label', 'units']].rename(columns={
                'retention_label': '就労定着率', 'units': '単位数（1日あたり）'
            }), use_container_width=True, hide_index=True)


    with tab3:
        st.header("利用者台帳")
        clients_df = db_utils.get_clients()

        if not clients_df.empty:
            # Key columns for overview
            display_cols = ['name', 'usage_status', 'recipient_number', 'city', 
                           'payment_period_start', 'payment_period_end', 'max_copay',
                           'certificate_acquired', 'contract_date', 'service_start', 'service_end',
                           'desired_employment_date']
            available_cols = [c for c in display_cols if c in clients_df.columns]

            col_labels = {
                'name': '氏名', 'usage_status': '利用状態', 'recipient_number': '受給者番号',
                'city': '市区町村', 'payment_period_start': '支給決定開始', 'payment_period_end': '支給決定終了',
                'max_copay': '負担上限額', 'certificate_acquired': '取得有無',
                'contract_date': '契約日', 'service_start': '利用開始', 'service_end': '利用終了',
                'desired_employment_date': '就職希望時期'
            }

            st.dataframe(
                clients_df[available_cols].rename(columns=col_labels),
                use_container_width=True
            )

            # Expiry Alerts
            st.subheader("⚠️ 期限アラート")
            import pandas as _pd
            today = _pd.Timestamp.now()
            for _, row in clients_df.iterrows():
                if row.get('payment_period_end'):
                    try:
                        end = _pd.Timestamp(row['payment_period_end'])
                        days_left = (end - today).days
                        if 0 < days_left <= 60:
                            st.warning(f"**{row['name']}**: 支給決定期間が残り{days_left}日です（{row['payment_period_end']}まで）。更新手続きを確認してください。")
                    except Exception:
                        pass
        else:
            st.info("利用者データがまだありません。")

        with st.expander("➕ 新規利用者登録"):
            with st.form("new_client"):
                nc1, nc2 = st.columns(2)
                with nc1:
                    cl_name = st.text_input("氏名")
                    cl_status = st.selectbox("利用状態", ["利用者", "体験", "見学", "卒業", "退所"])
                    cl_number = st.text_input("受給者番号")
                    cl_city = st.text_input("市区町村")
                    cl_copay = st.selectbox("負担上限額", ["0円", "4600円", "9300円", "37200円"])
                with nc2:
                    cl_start = st.date_input("支給決定期間 開始日")
                    cl_end = st.date_input("支給決定期間 最終日")
                    cl_contract = st.date_input("契約日")
                    cl_cert = st.selectbox("受給者証 取得有無", ["有", "無", "申請中"])
                    cl_desire = st.text_input("就職希望時期 (例: 2026/4)")

                if st.form_submit_button("利用者を登録"):
                    db_utils.add_client({
                        'name': cl_name, 'usage_status': cl_status,
                        'recipient_number': cl_number, 'city': cl_city,
                        'max_copay': cl_copay, 'payment_period_start': cl_start,
                        'payment_period_end': cl_end, 'contract_date': cl_contract,
                        'certificate_acquired': cl_cert, 'desired_employment_date': cl_desire
                    })
                    st.success(f"{cl_name} さんを登録しました！")
                    st.rerun()


    with tab4:
        st.header("事業所運営状況")
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("利用者候補パイプライン")
            candidates = db_utils.get_user_candidates()
            st.dataframe(candidates[['name', 'status', 'source', 'expected_revenue', 'staff_name', 'note']], use_container_width=True)

            # (New Candidate Form - Simplified for View)
            with st.expander("新規候補登録"):
               with st.form("new_candidate_mgr"):
                    staff_list = db_utils.get_staff_list()
                    c_name = st.text_input("氏名")
                    c_source = st.selectbox("紹介元", ["HP", "相談支援", "クリニック", "その他"])
                    c_status = st.selectbox("ステータス", ["問い合わせ", "見学", "体験", "受給者証申請", "契約"])
                    c_rev = st.number_input("見込み月商", value=150000)
                    c_staff = st.selectbox("担当支援員", staff_list['id'], format_func=lambda x: staff_list[staff_list['id'] == x]['name'].values[0])
                    if st.form_submit_button("登録"):
                        db_utils.add_user_candidate(c_name, c_source, c_status, c_staff, c_rev, "")
                        st.success("登録しました")
                        st.rerun()

        with col2:
            st.subheader("売上予測")
            if not candidates.empty:
                total_rev = candidates[candidates['status'].isin(['体験', '契約'])]['expected_revenue'].sum()
                st.metric("当月見込", f"¥{total_rev:,}")

            st.subheader("本日の通所者")
            st.info("15名 通所中")
            st.text_area("スタッフへの連絡事項", "本日15時より避難訓練を行います。")

        st.divider()
        st.subheader("議事録管理 (Whisper)")
        uploaded_file = st.file_uploader("会議録音アップロード", type=["mp3", "m4a", "wav"])
        if uploaded_file and st.button("議事録作成"):
            if client:
                with st.spinner("AIが分析中..."):
                    with open("temp_mgr.mp3", "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    transcript = whisper_utils.transcribe_audio(client, "temp_mgr.mp3")
                    summary = whisper_utils.summarize_text(client, transcript, type="meeting")
                    st.markdown(summary)
            else:
                st.error("API Key Missing")


    with tab5:
        st.header("チームマネジメント")
        st.dataframe(db_utils.get_staff_list())

        col1, col2 = st.columns(2)
        with col1: 
             st.subheader("KPI概況")
             st.metric("チーム全体 外交件数", "45件")
             st.metric("新規契約数", "5件")

        with col2:
             st.subheader("1on1 スケジューリング")
             st.write("2週間に1回の定期面談を設定")
             if st.button("全スタッフの次回1on1を一括設定 (カレンダー連携)"):
                 st.success("Google Calendarに招待を送信しました")


    with tab8:
        st.header("📋 利用実績管理")

        # Alerts at the top
        db_utils.seed_addition_defaults()
        alerts = db_utils.get_client_alerts()
        if alerts:
            st.subheader("⚠️ アラート")
            for a in alerts:
                if a['type'] == 'danger':
                    st.error(f"**{a['client']}**: {a['msg']}")
                else:
                    st.warning(f"**{a['client']}**: {a['msg']}")
            st.divider()

        # Daily record entry
        st.subheader("📅 日次通所実績の登録")
        clients_df = db_utils.get_clients()
        active_clients = clients_df[clients_df['usage_status'] == '利用者'] if not clients_df.empty else pd.DataFrame()

        if not active_clients.empty:
            cdr_col1, cdr_col2 = st.columns(2)
            with cdr_col1:
                sel_client = st.selectbox("利用者", active_clients['id'].tolist(),
                    format_func=lambda x: active_clients[active_clients['id']==x]['name'].values[0],
                    key="cdr_client")
                cdr_date = st.date_input("日付", datetime.date.today(), key="cdr_date")
                service_type = st.selectbox("サービス種別", ["通所", "欠席", "施設外支援", "体験"], key="cdr_svc")
            with cdr_col2:
                cdr_in = st.time_input("到着", datetime.time(9, 0), key="cdr_in")
                cdr_out = st.time_input("退所", datetime.time(16, 0), key="cdr_out")
                cdr_memo = st.text_input("メモ", key="cdr_memo")

            add_col1, add_col2, add_col3 = st.columns(3)
            pickup = add_col1.checkbox("🚗 迎え送迎", key="cdr_pickup")
            dropoff = add_col1.checkbox("🚗 送り送迎", key="cdr_dropoff")
            meal = add_col2.checkbox("🍱 食事提供", key="cdr_meal")
            absence_contact = add_col3.checkbox("📞 欠席連絡あり", key="cdr_abs_c")
            absence_support = add_col3.checkbox("📝 欠席時対応あり", key="cdr_abs_s")
            outside_support = add_col2.checkbox("🏢 施設外支援", key="cdr_outs")

            if st.button("✅ 実績を登録", type="primary"):
                db_utils.add_client_daily_record(
                    sel_client, str(cdr_date), service_type,
                    str(cdr_in), str(cdr_out),
                    int(pickup), int(dropoff), int(meal),
                    int(absence_contact), int(absence_support),
                    int(outside_support), cdr_memo, user['id'])
                st.success("通所実績を登録しました！")
                st.rerun()
        else:
            st.info("利用者が登録されていません。「利用者台帳」タブで登録してください。")

        # Monthly summary
        st.divider()
        st.subheader("📊 月次実績サマリー")
        sum_col1, sum_col2 = st.columns(2)
        sum_year = sum_col1.number_input("年", value=datetime.date.today().year, key="usage_sum_y")
        sum_month = sum_col2.number_input("月", value=datetime.date.today().month, min_value=1, max_value=12, key="usage_sum_m")

        summary = db_utils.get_monthly_usage_summary(int(sum_year), int(sum_month))
        if not summary.empty:
            display_cols = {
                'client_name': '利用者名', 'recipient_number': '受給者証番号',
                'total_days': '利用日数', 'attend_days': '通所日数',
                'pickup_count': '迎え', 'dropoff_count': '送り',
                'meal_count': '食事', 'absence_support_count': '欠席対応',
                'outside_support_count': '施設外', 'contracted_days': '契約日数'
            }
            st.dataframe(summary.rename(columns=display_cols)[list(display_cols.values())],
                        use_container_width=True, hide_index=True)
        else:
            st.info("指定月のデータはありません。")

        # Recent records
        st.divider()
        st.subheader("📜 直近の通所記録")
        recent = db_utils.get_client_daily_records(date_from=str(datetime.date.today() - datetime.timedelta(days=7)))
        if not recent.empty:
            st.dataframe(recent[['record_date', 'client_name', 'service_type', 'clock_in', 'clock_out',
                                 'pickup_flag', 'dropoff_flag', 'meal_flag']].rename(columns={
                'record_date': '日付', 'client_name': '利用者', 'service_type': '種別',
                'clock_in': '到着', 'clock_out': '退所', 'pickup_flag': '迎え',
                'dropoff_flag': '送り', 'meal_flag': '食事'
            }), use_container_width=True, hide_index=True)
        else:
            st.info("直近の記録はありません。")


    with tab9:
        st.header("📝 支援記録（ケース記録）")
        st.caption("通所実績と連動したサービス提供記録")

        clients_df2 = db_utils.get_clients()
        active_clients2 = clients_df2[clients_df2['usage_status'] == '利用者'] if not clients_df2.empty else pd.DataFrame()

        if not active_clients2.empty:
            sr_col1, sr_col2 = st.columns(2)
            with sr_col1:
                sr_client = st.selectbox("利用者", active_clients2['id'].tolist(),
                    format_func=lambda x: active_clients2[active_clients2['id']==x]['name'].values[0],
                    key="sr_client")
                sr_date = st.date_input("記録日", datetime.date.today(), key="sr_date")
            with sr_col2:
                sr_svc = st.selectbox("サービス種別", ["通所", "欠席時対応", "施設外支援", "体験"], key="sr_svc")
                sr_condition = st.selectbox("体調", ["良好", "やや不調", "不調", "休憩あり"], key="sr_cond")

            sr_content = st.text_area("支援内容", height=150, key="sr_content",
                placeholder="・本日のプログラム参加状況\n・面談内容\n・行動観察\n・特記事項")
            sr_goal = st.text_area("目標に対する進捗", height=80, key="sr_goal",
                placeholder="個別支援計画の目標に対する進捗状況")

            if st.button("📝 支援記録を保存", type="primary"):
                db_utils.add_support_record(sr_client, str(sr_date), sr_svc,
                    sr_content, sr_condition, sr_goal, user['id'], user['name'])
                st.success("支援記録を保存しました！")
                st.rerun()
        else:
            st.info("利用者が登録されていません。")

        # Record history
        st.divider()
        st.subheader("📜 支援記録一覧")
        sr_filter_col1, sr_filter_col2 = st.columns(2)
        sr_from = sr_filter_col1.date_input("開始日", datetime.date.today() - datetime.timedelta(days=30), key="sr_from")
        sr_to = sr_filter_col2.date_input("終了日", datetime.date.today(), key="sr_to")

        records = db_utils.get_support_records(date_from=str(sr_from), date_to=str(sr_to))
        if not records.empty:
            for _, rec in records.iterrows():
                with st.expander(f"📄 {rec['record_date']} — {rec['client_name']} [{rec['service_type']}]"):
                    st.write(f"**体調:** {rec['client_condition']}")
                    st.write(f"**支援内容:** {rec['support_content']}")
                    if rec['goal_progress']:
                        st.write(f"**目標進捗:** {rec['goal_progress']}")
                    st.caption(f"記録者: {rec['staff_name']}")
        else:
            st.info("指定期間の記録はありません。")


    with tab10:
        st.header("💰 国保連請求CSV ウィザード")
        st.caption("ステップに従って操作するだけで、正確なCSVを生成できます")

        # Import billing module
        from billing import config as bill_config
        from billing.main import process_billing, validate_records, parse_jisseki_csv

        # Step 1: 対象年月を選択
        st.subheader("📅 Step 1: 対象年月")
        bill_col1, bill_col2 = st.columns(2)
        bill_year = bill_col1.number_input("年", value=datetime.date.today().year, key="bill_y")
        bill_month = bill_col2.number_input("月", value=datetime.date.today().month,
                                            min_value=1, max_value=12, key="bill_m")

        st.divider()

        # Step 2: 事業所情報の確認
        st.subheader("🏢 Step 2: 事業所情報")
        st.info("� この情報はCSVのヘッダーに使用されます。初回設定後は自動入力されます。")

        oi_col1, oi_col2 = st.columns(2)
        office_id = oi_col1.text_input("事業所番号（10桁）",
            value=bill_config.OFFICE_INFO["office_id"], key="w_oid")
        office_name = oi_col2.text_input("事業所名",
            value=bill_config.OFFICE_INFO["office_name"], key="w_oname")
        corp_name = oi_col1.text_input("法人名",
            value=bill_config.OFFICE_INFO["corporation_name"], key="w_corp")

        base_code = oi_col2.selectbox("基本サービスコード", options=[
            "432025 — 就労移行(I) 定員20人以下 (1,020単位)",
            "432011 — 就労移行(I) 定員21~40人 (871単位)",
            "432015 — 就労移行(I) 定員41~60人 (804単位)",
        ], key="w_bcode")
        selected_base_code = base_code.split(" — ")[0].strip()

        st.divider()

        # Step 3: 入力データ選択
        st.subheader("📂 Step 3: データ入力方法")

        input_method = st.radio("データの取得元を選択してください", [
            "📊 DBから取得（利用実績タブで登録済みデータ）",
            "📄 CSVファイルをアップロード（knowbe等からエクスポート）",
        ], key="w_input")

        billing_result = None
        csv_uploaded = None

        if "CSVファイル" in input_method:
            csv_uploaded = st.file_uploader("実績記録票CSV", type=["csv"], key="w_csv")
            if csv_uploaded:
                csv_content = csv_uploaded.read().decode("utf-8", errors="replace")
                try:
                    billing_result = process_billing(
                        csv_content=csv_content,
                        addition_codes=[],
                    )
                    st.success(f"✅ CSVを読み込みました（{billing_result['summary']['total_users']}名分）")
                except Exception as e:
                    st.error(f"CSV読み込みエラー: {e}")
        else:
            # DB から取得
            try:
                summary_df = db_utils.get_monthly_usage_summary(int(bill_year), int(bill_month))
                records_df = db_utils.get_client_daily_records(
                    date_from=f"{int(bill_year)}-{int(bill_month):02d}-01",
                    date_to=f"{int(bill_year)}-{int(bill_month):02d}-31"
                )

                if not records_df.empty:
                    # クライアント情報を結合
                    clients_df = db_utils.get_clients()
                    if not clients_df.empty:
                        merge_cols = ['id', 'recipient_number', 'name']
                        if 'municipality_code' in clients_df.columns:
                            merge_cols.append('municipality_code')
                        merged = records_df.merge(
                            clients_df[merge_cols].rename(
                                columns={'id': 'client_id'}),
                            on='client_id', how='left', suffixes=('', '_client')
                        )
                    else:
                        merged = records_df

                    billing_result = process_billing(
                        records_df=merged,
                        year=int(bill_year),
                        month=int(bill_month),
                        office_id=office_id,
                        addition_codes=[],
                    )
                    st.success(f"✅ DBから{billing_result['summary']['total_users']}名分のデータを取得しました")
                else:
                    st.warning("📭 指定月のデータがDBにありません。利用実績タブで日次記録を登録するか、CSVをアップロードしてください。")
            except Exception as e:
                st.error(f"DB読み込みエラー: {e}")

        st.divider()

        # Step 4: バリデーション（エラーチェック）
        st.subheader("✅ Step 4: 提出前エラーチェック")

        if billing_result:
            validation = billing_result["validation"]

            if validation.errors:
                st.error(f"🔴 **{len(validation.errors)}件のエラーがあります。修正するまでCSVをダウンロードできません。**")
                for err in validation.errors:
                    st.markdown(f"- {err}")

            if validation.warnings:
                st.warning(f"⚠️ **{len(validation.warnings)}件の警告があります（要確認）**")
                for warn in validation.warnings:
                    st.markdown(f"- {warn}")

            if validation.is_valid and not validation.warnings:
                st.success("🎉 すべてのチェックに合格しました！")
            elif validation.is_valid:
                st.info("⚠️ 警告はありますが、CSVの生成は可能です。内容を確認してください。")

            st.divider()

            # Step 5: プレビュー
            st.subheader("📊 Step 5: 請求プレビュー")

            items = billing_result["billing_items"]
            summary = billing_result["summary"]

            # サマリーカード
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("👥 対象人数", f"{summary['total_users']}名")
            m2.metric("📊 合計単位数", f"{summary['total_units']:,}")
            m3.metric("💰 給付費請求額", f"¥{summary['total_billing']:,}")
            m4.metric("👤 利用者負担額", f"¥{summary['total_copay']:,}")

            # 利用者別明細
            with st.expander("📋 利用者別明細", expanded=True):
                detail_data = []
                for item in items:
                    detail_data.append({
                        '受給者証番号': item.user_id,
                        '市町村番号': item.city_code,
                        '利用日数': item.days_used,
                        '基本単位数': item.base_total_units,
                        '加算単位数': item.addition_total_units + item.monthly_addition_units,
                        '合計単位数': item.final_units,
                        '地域単価': f"{item.unit_price:.2f}",
                        '総費用額': f"¥{item.total_cost:,}",
                        '給付費': f"¥{item.billing_amount:,}",
                        '自己負担': f"¥{item.user_copay:,}",
                    })
                st.dataframe(pd.DataFrame(detail_data), use_container_width=True, hide_index=True)

            # J611 プレビュー
            with st.expander("📄 J611 CSV プレビュー（国保連伝送フォーマット）"):
                j611_lines = billing_result["j611_csv"].strip().split("\r\n")
                if j611_lines:
                    preview_count = min(10, len(j611_lines))
                    st.code("\n".join(j611_lines[:preview_count]), language="csv")
                    if len(j611_lines) > preview_count:
                        st.caption(f"...他 {len(j611_lines) - preview_count} 行")

            st.divider()

            # Step 6: CSVダウンロード
            st.subheader("📥 Step 6: CSVダウンロード")

            if validation.has_errors:
                st.error("🔴 エラーを修正してからダウンロードしてください。")
                st.button("📄 ダウンロード不可（エラーあり）", disabled=True, key="w_dl_disabled")
            else:
                ym = f"{int(bill_year)}{int(bill_month):02d}"

                dl1, dl2, dl3 = st.columns(3)

                with dl1:
                    st.markdown("#### 📄 様式第一")
                    st.caption("請求書鑑（自治体別集計）")
                    st.download_button(
                        "⬇️ 様式第一.csv",
                        billing_result["yoshiki_1_csv"],
                        file_name=f"yoshiki1_{ym}.csv",
                        mime="text/csv",
                        type="primary",
                        key="w_dl1"
                    )

                with dl2:
                    st.markdown("#### 📄 様式第二")
                    st.caption("明細書（利用者別）")
                    st.download_button(
                        "⬇️ 様式第二.csv",
                        billing_result["yoshiki_2_csv"],
                        file_name=f"yoshiki2_{ym}.csv",
                        mime="text/csv",
                        type="primary",
                        key="w_dl2"
                    )

                with dl3:
                    st.markdown("#### 📄 J611実績記録票")
                    st.caption("国保連伝送フォーマット")
                    st.download_button(
                        "⬇️ J611.csv",
                        billing_result["j611_csv"],
                        file_name=f"j611_{ym}.csv",
                        mime="text/csv",
                        type="primary",
                        key="w_dl3"
                    )

                st.success("✅ ダウンロード準備完了！ボタンをクリックしてCSVを取得してください。")

        else:
            st.info("📝 Step 3 でデータを入力するとバリデーション結果が表示されます。")

        # マスタ設定（折りたたみ）
        st.divider()
        with st.expander("⚙️ マスタ設定（サービスコード・地域単価）"):
            st.markdown("#### サービスコードマスタ")
            sc_data = []
            for code, info in bill_config.SERVICE_CODE_MASTER.items():
                sc_data.append({
                    'コード': code,
                    '名称': info['name'],
                    '単位数': info['units'],
                    '計算種別': info['calc_type'],
                    '加算率': f"{info.get('rate', 0) * 100:.1f}%" if info.get('rate') else '-',
                })
            st.dataframe(pd.DataFrame(sc_data), use_container_width=True, hide_index=True)

            st.markdown("#### 地域単価マスタ")
            gp_data = []
            for grade, prices in bill_config.GRADE_UNIT_PRICES.items():
                gp_data.append({
                    '級地': grade,
                    '就労移行': f"{prices['就労移行支援']:.2f}円",
                    '就労定着': f"{prices['就労定着支援']:.2f}円",
                })
            st.dataframe(pd.DataFrame(gp_data), use_container_width=True, hide_index=True)

    with tab7:
        st.header("📑 行政申請・届出管理")

        admin_mode = st.radio("表示", ["📋 変更届", "📋 体制届", "📊 対応履歴"], horizontal=True, key="office_admin_mode")

        if admin_mode == "📋 変更届":
            st.subheader("📋 変更届")
            st.caption("指定内容に変更があった場合に提出する届出")
            
            with st.form("change_notification_form"):
                cn_type = st.selectbox("届出種類", [
                    "事業所名称変更", "所在地変更", "管理者変更", 
                    "サービス管理責任者変更", "定員変更", "運営規程変更", "その他"
                ])
                cn_date = st.date_input("届出日")
                cn_status = st.selectbox("状況", ["準備中", "提出済", "受理完了"])
                cn_notes = st.text_area("備考")
                if st.form_submit_button("登録"):
                    st.success(f"変更届（{cn_type}）を登録しました")

        elif admin_mode == "📋 体制届":
            st.subheader("📋 体制届（加算届）")
            st.caption("加算の届出・体制の変更")

            with st.form("structure_notification_form"):
                sn_type = st.selectbox("届出種類", [
                    "就労移行支援体制加算", "福祉専門職員配置等加算",
                    "就労支援関係研修修了加算", "移行準備支援体制加算",
                    "通勤訓練加算", "在宅時生活支援サービス加算", "その他"
                ])
                sn_date = st.date_input("届出日", key="sn_date")
                sn_effective = st.date_input("適用開始日", key="sn_eff")
                sn_status = st.selectbox("状況", ["準備中", "提出済", "適用中"], key="sn_status")
                sn_notes = st.text_area("備考", key="sn_notes")
                if st.form_submit_button("登録"):
                    st.success(f"体制届（{sn_type}）を登録しました")

        else:
            st.subheader("📊 行政対応履歴")
            st.caption("過去の届出・申請の一覧")
            st.info("届出データは上記フォームから登録してください。（データベース連携は次フェーズで実装）")

    with tab11:
        st.header("📋 個別支援計画")
        clients_sp = db_utils.get_clients(office_id=current_office_id)
        active_sp = clients_sp[clients_sp['usage_status'] == '利用者'] if not clients_sp.empty else pd.DataFrame()

        if active_sp.empty:
            st.info("利用者が登録されていません。")
        else:
            with st.expander("✏️ 新しい支援計画を作成", expanded=False):
                with st.form("new_support_plan"):
                    sp_c1, sp_c2 = st.columns(2)
                    with sp_c1:
                        sp_client = st.selectbox("利用者", active_sp['id'].tolist(),
                            format_func=lambda x: active_sp[active_sp['id']==x]['name'].values[0], key="sp_client")
                        sp_date = st.date_input("計画作成日", datetime.date.today(), key="sp_date")
                        sp_review = st.date_input("見直し予定日",
                            datetime.date.today() + datetime.timedelta(days=90), key="sp_review")
                    with sp_c2:
                        sp_status = st.selectbox("ステータス", ["作成中", "確定", "更新中"], key="sp_status")

                    sp_long = st.text_area("長期目標", height=80, key="sp_long",
                        placeholder="例: 一般企業での事務職に就職する")
                    sp_short = st.text_area("短期目標", height=80, key="sp_short",
                        placeholder="例: PC基本操作を習得する（3ヶ月以内）")
                    sp_content = st.text_area("支援内容", height=120, key="sp_content",
                        placeholder="・ビジネスマナー研修\n・PC操作訓練\n・コミュニケーション練習")

                    if st.form_submit_button("📋 計画を保存", type="primary"):
                        db_utils.add_support_plan(sp_client, current_office_id,
                            str(sp_date), str(sp_review), sp_long, sp_short, sp_content,
                            user['id'], user['name'], sp_status)
                        st.success("個別支援計画を保存しました！")
                        st.rerun()

            # Plan list
            st.divider()
            st.subheader("📜 支援計画一覧")
            sp_filter = st.selectbox("利用者でフィルタ", [None] + active_sp['id'].tolist(),
                format_func=lambda x: "全員" if x is None else active_sp[active_sp['id']==x]['name'].values[0],
                key="sp_filter")
            plans = db_utils.get_support_plans(client_id=sp_filter, office_id=current_office_id)
            if not plans.empty:
                for _, p in plans.iterrows():
                    status_icon = {"作成中": "📝", "確定": "✅", "更新中": "🔄"}.get(p['status'], "📋")
                    with st.expander(f"{status_icon} {p['client_name']} — {p['plan_date']} [{p['status']}]"):
                        st.write(f"**長期目標:** {p['long_term_goal']}")
                        st.write(f"**短期目標:** {p['short_term_goal']}")
                        st.write(f"**支援内容:** {p['support_content']}")
                        st.write(f"**見直し予定:** {p['review_date']}")
                        st.caption(f"作成者: {p['staff_name']}")
                        # Status update
                        new_status = st.selectbox("ステータス変更", ["作成中", "確定", "更新中"],
                            index=["作成中", "確定", "更新中"].index(p['status']) if p['status'] in ["作成中", "確定", "更新中"] else 0,
                            key=f"sp_st_{p['id']}")
                        if st.button("更新", key=f"sp_upd_{p['id']}"):
                            db_utils.update_support_plan_status(p['id'], new_status)
                            st.success("ステータスを更新しました")
                            st.rerun()
            else:
                st.info("支援計画がまだ作成されていません。")


    with tab12:
        st.header("📊 モニタリング")
        clients_mon = db_utils.get_clients(office_id=current_office_id)
        active_mon = clients_mon[clients_mon['usage_status'] == '利用者'] if not clients_mon.empty else pd.DataFrame()

        if active_mon.empty:
            st.info("利用者が登録されていません。")
        else:
            with st.expander("✏️ 新しいモニタリング記録", expanded=False):
                with st.form("new_monitoring"):
                    mn_c1, mn_c2 = st.columns(2)
                    with mn_c1:
                        mn_client = st.selectbox("利用者", active_mon['id'].tolist(),
                            format_func=lambda x: active_mon[active_mon['id']==x]['name'].values[0], key="mn_client")
                        mn_date = st.date_input("モニタリング日", datetime.date.today(), key="mn_date")
                    with mn_c2:
                        # Link to support plan
                        all_plans = db_utils.get_support_plans(office_id=current_office_id)
                        plan_ids = [None] + (all_plans['id'].tolist() if not all_plans.empty else [])
                        mn_plan = st.selectbox("関連支援計画", plan_ids,
                            format_func=lambda x: "なし" if x is None else f"計画#{x}", key="mn_plan")
                        mn_next = st.date_input("次回モニタリング予定",
                            datetime.date.today() + datetime.timedelta(days=90), key="mn_next")

                    mn_goal = st.text_area("目標達成度", height=80, key="mn_goal",
                        placeholder="長期・短期目標に対する進捗状況")
                    mn_eval = st.text_area("支援の評価", height=80, key="mn_eval",
                        placeholder="提供した支援の適切さ・効果")
                    mn_satis = st.selectbox("本人の満足度", ["満足", "やや満足", "普通", "やや不満", "不満"], key="mn_satis")
                    mn_change = st.checkbox("計画変更の必要あり", key="mn_change")
                    mn_reason = st.text_area("変更理由", height=60, key="mn_reason",
                        placeholder="計画変更が必要な場合の理由") if mn_change else ""

                    if st.form_submit_button("📊 モニタリング記録を保存", type="primary"):
                        db_utils.add_monitoring_record(mn_client, mn_plan, current_office_id,
                            str(mn_date), mn_goal, mn_eval, mn_satis,
                            mn_change, mn_reason, str(mn_next), user['id'], user['name'])
                        st.success("モニタリング記録を保存しました！")
                        st.rerun()

            st.divider()
            st.subheader("📜 モニタリング記録一覧")
            mon_records = db_utils.get_monitoring_records(office_id=current_office_id)
            if not mon_records.empty:
                for _, mr in mon_records.iterrows():
                    change_mark = "🔄" if mr['needs_plan_change'] else ""
                    with st.expander(f"📊 {mr['client_name']} — {mr['monitoring_date']} {change_mark}"):
                        st.write(f"**目標達成度:** {mr['goal_achievement']}")
                        st.write(f"**支援評価:** {mr['support_evaluation']}")
                        st.write(f"**満足度:** {mr['client_satisfaction']}")
                        if mr['needs_plan_change']:
                            st.warning(f"⚠️ 計画変更理由: {mr['change_reason']}")
                        st.write(f"**次回予定:** {mr['next_monitoring_date']}")
                        st.caption(f"記録者: {mr['staff_name']}")
            else:
                st.info("モニタリング記録がありません。")


    with tab13:
        st.header("📝 アセスメント")
        clients_as = db_utils.get_clients(office_id=current_office_id)
        active_as = clients_as[clients_as['usage_status'] == '利用者'] if not clients_as.empty else pd.DataFrame()

        if active_as.empty:
            st.info("利用者が登録されていません。")
        else:
            with st.expander("✏️ 新しいアセスメント記録", expanded=False):
                with st.form("new_assessment"):
                    as_c1, as_c2 = st.columns(2)
                    with as_c1:
                        as_client = st.selectbox("利用者", active_as['id'].tolist(),
                            format_func=lambda x: active_as[active_as['id']==x]['name'].values[0], key="as_client")
                        as_date = st.date_input("アセスメント日", datetime.date.today(), key="as_date")
                    with as_c2:
                        as_type = st.selectbox("種別", ["初回", "定期", "随時"], key="as_type")

                    as_living = st.text_area("生活状況", height=60, key="as_living",
                        placeholder="居住形態、家族構成、日常生活の状況")
                    as_health = st.text_area("健康状態", height=60, key="as_health",
                        placeholder="障害の状態、服薬状況、通院状況")
                    as_disability = st.text_area("障害特性", height=60, key="as_disability",
                        placeholder="障害による困難さ、配慮事項")
                    as_work = st.text_area("就労経験", height=60, key="as_work",
                        placeholder="過去の就労経験、職種、期間")
                    as_strengths = st.text_area("強み・得意なこと", height=60, key="as_strengths")
                    as_challenges = st.text_area("課題", height=60, key="as_challenges")
                    as_needs = st.text_area("支援ニーズ", height=60, key="as_needs")
                    as_goal = st.text_area("就労目標", height=60, key="as_goal",
                        placeholder="希望する職種、就労形態、勤務条件")

                    if st.form_submit_button("📝 アセスメントを保存", type="primary"):
                        db_utils.add_assessment_record(as_client, current_office_id,
                            str(as_date), as_type, as_living, as_health, as_disability,
                            as_work, as_strengths, as_challenges, as_needs, as_goal,
                            user['id'], user['name'])
                        st.success("アセスメント記録を保存しました！")
                        st.rerun()

            st.divider()
            st.subheader("📜 アセスメント記録一覧")
            as_records = db_utils.get_assessment_records(office_id=current_office_id)
            if not as_records.empty:
                for _, ar in as_records.iterrows():
                    type_icon = {"初回": "🆕", "定期": "🔄", "随時": "⚡"}.get(ar['assessment_type'], "📝")
                    with st.expander(f"{type_icon} {ar['client_name']} — {ar['assessment_date']} [{ar['assessment_type']}]"):
                        st.write(f"**生活状況:** {ar['living_situation']}")
                        st.write(f"**健康状態:** {ar['health_condition']}")
                        st.write(f"**障害特性:** {ar['disability_characteristics']}")
                        st.write(f"**就労経験:** {ar['work_experience']}")
                        st.write(f"**強み:** {ar['strengths']}")
                        st.write(f"**課題:** {ar['challenges']}")
                        st.write(f"**支援ニーズ:** {ar['support_needs']}")
                        st.write(f"**就労目標:** {ar['employment_goal']}")
                        st.caption(f"記録者: {ar['staff_name']}")
            else:
                st.info("アセスメント記録がありません。")


    with tab14:
                st.header("⚠️ 減算・自己負担管理")

                ded_mode = st.radio("表示", ["📋 減算項目管理", "💰 自己負担月額チェック"], horizontal=True, key="ded_mode")

                if ded_mode == "📋 減算項目管理":
                    st.subheader("📋 減算項目管理")
                    clients_ded = db_utils.get_clients(office_id=current_office_id)
                    active_ded = clients_ded[clients_ded['usage_status'] == '利用者'] if not clients_ded.empty else pd.DataFrame()

                    with st.expander("✏️ 減算項目を追加", expanded=False):
                        with st.form("new_deduction"):
                            dd_c1, dd_c2 = st.columns(2)
                            with dd_c1:
                                if not active_ded.empty:
                                    dd_client = st.selectbox("利用者", active_ded['id'].tolist(),
                                        format_func=lambda x: active_ded[active_ded['id']==x]['name'].values[0], key="dd_client")
                                else:
                                    dd_client = None
                                    st.info("利用者がいません")
                                dd_year = st.number_input("年", value=datetime.date.today().year, key="dd_year")
                                dd_month = st.number_input("月", min_value=1, max_value=12,
                                    value=datetime.date.today().month, key="dd_month")
                            with dd_c2:
                                dd_type = st.selectbox("減算種別", [
                                    "サービス提供職員欠如減算",
                                    "サービス管理責任者欠如減算",
                                    "個別支援計画未作成減算",
                                    "身体拘束廃止未実施減算",
                                    "その他"
                                ], key="dd_type")
                                dd_units = st.number_input("減算単位数", value=0, key="dd_units")

                            dd_reason = st.text_area("減算理由", height=60, key="dd_reason")
                            dd_notes = st.text_area("備考", height=40, key="dd_notes")

                            if st.form_submit_button("⚠️ 減算を登録", type="primary"):
                                if dd_client:
                                    db_utils.add_deduction_item(dd_client, current_office_id,
                                        dd_year, dd_month, dd_type, dd_reason, dd_units,
                                        user['id'], dd_notes)
                                    st.success("減算項目を登録しました")
                                    st.rerun()

                    st.divider()
                    ded_items = db_utils.get_deduction_items(office_id=current_office_id)
                    if not ded_items.empty:
                        st.dataframe(ded_items[['client_name', 'year', 'month', 'deduction_type',
                            'deduction_reason', 'deduction_units', 'status']].rename(columns={
                            'client_name': '利用者', 'year': '年', 'month': '月',
                            'deduction_type': '減算種別', 'deduction_reason': '理由',
                            'deduction_units': '単位数', 'status': '状態'
                        }), use_container_width=True, hide_index=True)
                    else:
                        st.success("✅ 現在、減算項目はありません。")

                else:
                    # 自己負担月額チェック
                    st.subheader("💰 自己負担月額（max_copay）チェック")
                    st.caption("利用者台帳の「負担上限月額」が未設定の利用者を表示します。請求前に必ず確認してください。")

                    all_clients = db_utils.get_clients(office_id=current_office_id)
                    active_copay = all_clients[all_clients['usage_status'] == '利用者'] if not all_clients.empty else pd.DataFrame()

                    if not active_copay.empty:
                        missing_copay = active_copay[
                            (active_copay['max_copay'].isna()) |
                            (active_copay['max_copay'] == '') |
                            (active_copay['max_copay'].astype(str) == 'None')
                        ]
                        if not missing_copay.empty:
                            st.error(f"⛔ 自己負担月額が未設定の利用者が {len(missing_copay)} 名います！")
                            for _, mc in missing_copay.iterrows():
                                st.warning(f"⚠️ **{mc['name']}** — 負担上限月額が未設定です")
                        else:
                            st.success("✅ 全利用者の自己負担月額が設定済みです。")

                        st.divider()
                        st.subheader("📊 自己負担月額 一覧")
                        copay_data = active_copay[['name', 'max_copay', 'recipient_number']].rename(columns={
                            'name': '利用者名', 'max_copay': '負担上限月額', 'recipient_number': '受給者証番号'
                        })
                        st.dataframe(copay_data, use_container_width=True, hide_index=True)
                    else:
                        st.info("利用者が登録されていません。")

        # Client Dashboard (利用者ポータル)


# --- Main App Entry ---
print("[app.py] check_password...", flush=True)
if check_password():
    user = st.session_state["user_info"]
    
    # API Keys: 環境変数から自動読み込み（社員には非表示）
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    client = OpenAI(api_key=openai_key) if openai_key else None
    # Gemini API Key は notebooklm_helper 内で os.environ から自動取得
    
    if st.sidebar.button("ログアウト"):
        st.session_state["logged_in"] = False
        st.rerun()
    
    # Routing based on Role
    login_role = st.session_state.get("login_role", "staff")
    if login_role == "client":
        st.info("利用者ダッシュボードは準備中です。")
    elif login_role == "hq":
        hq_dashboard(user, client)
    elif login_role == "office":
        office_dashboard(user, client)
    else:
        staff_dashboard(user, client)
