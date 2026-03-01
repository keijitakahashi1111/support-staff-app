"""
Database models and initialization for Supabase PostgreSQL.
Tables are created during migration; init_db verifies/seeds only.
"""
import datetime
import os
from db_config import get_connection


def init_db():
    """Ensure tables exist and seed initial data if needed."""
    import sys
    try:
        conn = get_connection()
        c = conn.cursor()

        # Verify connection by checking if staff table exists
        c.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'staff'
            )
        """)
        if not c.fetchone()[0]:
            print("WARNING: Database tables not found. Please run migrate_to_supabase.py first.", file=sys.stderr)
            conn.close()
            return

        conn.commit()
        conn.close()
        
        # Seed data if needed
        seed_data()
    except Exception as e:
        print(f"ERROR in init_db: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        raise


def seed_data():
    conn = get_connection()
    c = conn.cursor()

    # Check if data exists
    c.execute("SELECT count(*) FROM staff")
    if c.fetchone()[0] == 0:
        print("Seeding initial data...")
        staffs = [
            ('高橋 支援員', 28, 'staff', '2024-04-01', 'takahashi@nihon-shuro.co.jp'),
            ('佐藤 マネージャー', 35, 'manager', '2020-04-01', 'sato@nihon-shuro.co.jp'),
            ('鈴木 支援員', 24, 'staff', '2025-04-01', 'suzuki@nihon-shuro.co.jp')
        ]
        c.executemany("INSERT INTO staff (name, age, role, joined_date, email) VALUES (%s, %s, %s, %s, %s)", staffs)

        candidates = [
            ('田中 太郎', '相談支援A', '体験', 1, '2026-02-01', '2026-02-10', '2026-02-15', None, 150000, '精神障害、週3日希望'),
            ('山田 花子', 'HP問い合わせ', '見学', 1, '2026-02-12', None, None, None, 0, '事務職希望')
        ]
        c.executemany(
            "INSERT INTO user_candidates (name, source, status, staff_id, contact_date, intake_date, experience_date, contract_date, expected_revenue, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            candidates)
        conn.commit()

    # Seed clients if empty
    c.execute("SELECT count(*) FROM clients")
    if c.fetchone()[0] == 0:
        print("Seeding client data...")
        clients = [
            ('利用者', '2026/2', '就労太郎', '1000054321', '○○市○○区',
             '2025-11-01', '2026-10-31', '2025-12-09', '9300円', '有', '2027-04-30',
             '2024-10-09', None, '2025-05-31', '2025-08-30', None,
             None, None, None, None, None, None, None, None, None, None),
            ('利用者', '2026/4/1', '就労花子', '0000012345', '○○市',
             '2024-10-10', '2025-11-06', None, '0円', '無', None,
             '2024-10-10', None, '2025-08-31', '2025-11-30', None,
             None, None, None, None, None, None, None, None, None, None),
        ]
        c.executemany('''INSERT INTO clients (usage_status, desired_employment_date, name, recipient_number, city,
            payment_period_start, payment_period_end, provisional_period_end, max_copay, certificate_acquired, certificate_expiry,
            contract_date, discharge_date, service_start, service_end, update_staff,
            employment_date, employment_contract, employer, discharge_reason,
            follow_start, follow_end, follow_contract_date, follow_discharge_date, resignation_date, job_change_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''', clients)
        conn.commit()

    # Seed checklist master if empty
    c.execute("SELECT count(*) FROM daily_checklist_master")
    if c.fetchone()[0] == 0:
        print("Seeding checklist master...")
        morning_daily = [
            ('morning', 'daily', 'Googleカレンダー本日の全体スケジュール', 1),
            ('morning', 'daily', 'Gメール確認', 2),
            ('morning', 'daily', '事業所直通LINE確認', 3),
            ('morning', 'daily', 'Slackの確認', 4),
            ('morning', 'daily', '前日の終礼議事録確認', 5),
            ('morning', 'daily', '本日の通所人数・通所者', 6),
            ('morning', 'daily', '本日の全体のスケジュール調整（スタッフ認識合わせ）', 7),
            ('morning', 'daily', '前日終礼振り返り', 8),
            ('morning', 'daily', 'ご利用者：個別作業内容（進捗確認）', 9),
            ('morning', 'daily', 'ご利用者：個別共有（面談、その他）', 10),
            ('morning', 'daily', 'ご利用者：週次面談内容・担当者', 11),
        ]
        evening_daily = [
            ('evening', 'daily', '理念唱和', 1),
            ('evening', 'daily', '環境整備（空調、掃除、フロア・職員スペースの整理整頓）', 2),
            ('evening', 'daily', '感染症対策（喚起、手洗い、消毒、除菌）', 3),
            ('evening', 'daily', 'knowbe支援記録の入力漏れありませんか？', 4),
            ('evening', 'daily', '実績記録確認（打刻漏れ：通退所時間）', 5),
            ('evening', 'daily', '加算確認（欠席時対応加算、移行準備体制加算、地域連携計画会議加算）', 6),
            ('evening', 'daily', '本日通所分入力の再確認　運営KPIシートの入力', 7),
            ('evening', 'daily', '本日通所分入力の再確認　通所スケジュールの確認', 8),
            ('evening', 'daily', '利用者検討ステップシートの更新・確認', 9),
            ('evening', 'daily', 'インテーク予約枠の更新・確認', 10),
            ('evening', 'daily', '外交実績リスト_統合版への更新・確認', 11),
            ('evening', 'daily', 'ご利用者情報の更新はないか？利用者情報一覧の更新・確認', 12),
            ('evening', 'daily', '日報をあげる', 13),
        ]
        all_items = morning_daily + evening_daily
        c.executemany("INSERT INTO daily_checklist_master (meeting_type, category, item_text, sort_order) VALUES (%s, %s, %s, %s)", all_items)
        conn.commit()

    # Seed reward rate table if empty
    c.execute("SELECT count(*) FROM reward_rate_table")
    if c.fetchone()[0] == 0:
        print("Seeding reward rate table...")
        rates = [
            ('50%以上', 50, 100, 1210),
            ('40%以上 50%未満', 40, 50, 1020),
            ('30%以上 40%未満', 30, 40, 879),
            ('20%以上 30%未満', 20, 30, 719),
            ('10%以上 20%未満', 10, 20, 569),
            ('0%超 10%未満', 0.1, 10, 519),
            ('0%', 0, 0, 479),
        ]
        c.executemany("INSERT INTO reward_rate_table (retention_label, retention_min, retention_max, units) VALUES (%s, %s, %s, %s)", rates)
        conn.commit()

    conn.close()


def _try_alter(cursor, sql):
    """Safe ALTER TABLE — ignore if column already exists."""
    try:
        cursor.execute(sql)
    except Exception:
        pass
