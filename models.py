import sqlite3
import datetime
import os

DB_PATH = "employment_support.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. Staff Table (支援員)
    c.execute('''CREATE TABLE IF NOT EXISTS staff (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER,
        role TEXT DEFAULT 'staff', -- staff, manager
        joined_date DATE,
        email TEXT
    )''')
    
    # 2. User Candidates / Sales Pipeline (利用者候補・営業パイプライン)
    # ステータス: 問い合わせ -> 見学 -> 体験 -> 受給者証申請 -> 契約 -> 通所開始
    c.execute('''CREATE TABLE IF NOT EXISTS user_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        source TEXT, -- 紹介元（相談支援事業所、HP、チラシ等）
        status TEXT, 
        staff_id INTEGER, -- 担当支援員
        contact_date DATE,
        intake_date DATE,
        experience_date DATE,
        contract_date DATE,
        expected_revenue INTEGER, -- 見込み売上 (単価 x 日数)
        note TEXT,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')

    # 3. Daily Reports / Growth Log (日報・成長記録)
    c.execute('''CREATE TABLE IF NOT EXISTS daily_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER,
        date DATE,
        sentiment_score INTEGER, -- 0-100
        content TEXT,
        learning TEXT, -- 学び・気付き
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')

    # 4. KPI / Activity Log (活動記録: 外交数など)
    c.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER,
        date DATE,
        type TEXT, -- 外交, 面談, 同行, 事務 etc.
        count INTEGER DEFAULT 1,
        note TEXT,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')

    # 5. Daily User Comments (通所利用者へのコメント)
    c.execute('''CREATE TABLE IF NOT EXISTS daily_user_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        user_name TEXT, -- 既存利用者は簡単のため名前文字列で管理
        staff_id INTEGER, -- 担当（記入者）
        comment TEXT, -- 今日何をするか、様子など
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    
    # 6. Meeting Records (朝会・夕会・1on1)
    c.execute('''CREATE TABLE IF NOT EXISTS meeting_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        type TEXT, -- 朝会, 夕会, 1on1
        participants TEXT,
        summary TEXT, -- 自動要約結果
        audio_file_path TEXT,
        FOREIGN KEY (participants) REFERENCES staff(id) -- Simplified
    )''')

    # 7. Attendance Records (勤怠管理)
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER,
        date DATE,
        clock_in DATETIME,
        clock_out DATETIME,
        break_start DATETIME,
        break_end DATETIME,
        status TEXT, -- 'working', 'break', 'finished'
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')

    conn.commit()

    # 8. Staff Details (労務・給与用詳細情報)
    c.execute('''CREATE TABLE IF NOT EXISTS staff_details (
        staff_id INTEGER PRIMARY KEY,
        address TEXT,
        birthday DATE,
        phone TEXT,
        bank_info TEXT, -- 銀行名・口座番号など
        dependents_count INTEGER DEFAULT 0,
        commuter_allowance INTEGER DEFAULT 0,
        base_salary INTEGER DEFAULT 0,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')

    # 9. Labor Procedures (行政手続き進捗)
    c.execute('''CREATE TABLE IF NOT EXISTS labor_procedures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER,
        category TEXT, -- 'entry' (入社), 'exit' (退社), 'social_insurance' (社保), 'labor_insurance' (労保)
        item_name TEXT, -- '資格取得届', '雇用契約書', etc.
        status TEXT, -- 'not_started', 'preparing', 'submitted', 'completed'
        due_date DATE,
        completed_date DATE,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    
    # 10. Welfare Grants (処遇改善加算等)
    c.execute('''CREATE TABLE IF NOT EXISTS welfare_grants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fiscal_year INTEGER,
        category TEXT, -- 'shogu_kaizen_i', 'shogu_kaizen_ii', etc.
        requirement TEXT, -- 'キャリアパス要件1', '職場環境等要件'
        status TEXT, -- 'planned', 'documented', 'reported'
        note TEXT
    )''')

    conn.commit()

    # 11. Clients / 利用者台帳 (実際のスプレッドシート構造に対応)
    c.execute('''CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usage_status TEXT, -- 利用状態: 利用者, 卒業, 退所 等
        desired_employment_date TEXT, -- 就職希望時期
        name TEXT NOT NULL, -- 氏名
        recipient_number TEXT, -- 受給者番号
        city TEXT, -- 市区町村
        payment_period_start DATE, -- 支給決定期間 開始日
        payment_period_end DATE, -- 支給決定期間 最終日
        provisional_period_end DATE, -- 暫定期間 最終年月日
        max_copay TEXT, -- 負担上限額
        certificate_acquired TEXT, -- 取得有無
        certificate_expiry DATE, -- 有効期限
        contract_date DATE, -- 契約日
        discharge_date DATE, -- 退所日
        service_start DATE, -- サービス利用開始
        service_end DATE, -- サービス利用終了
        update_staff TEXT, -- 更新担当
        employment_date DATE, -- 入社日 (就職先)
        employment_contract TEXT, -- 雇用契約書有無
        employer TEXT, -- 就職先（勤務先）
        discharge_reason TEXT, -- 退所理由
        follow_start DATE, -- 定着支援開始
        follow_end DATE, -- 定着支援終了
        follow_contract_date DATE, -- 定着支援契約日
        follow_discharge_date DATE, -- 定着支援退所日
        resignation_date DATE, -- 退職日
        job_change_date DATE -- 転職日
    )''')

    conn.commit()

    # 12. Daily Checklist (朝礼・終礼チェックリスト マスタ)
    c.execute('''CREATE TABLE IF NOT EXISTS daily_checklist_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_type TEXT, -- 'morning' (朝礼) or 'evening' (終礼)
        category TEXT, -- 'daily', 'weekly', 'monthly'
        item_text TEXT NOT NULL,
        sort_order INTEGER DEFAULT 0
    )''')

    # 13. Daily Checklist Log (日次チェック実績)
    c.execute('''CREATE TABLE IF NOT EXISTS daily_checklist_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        checklist_master_id INTEGER,
        checked INTEGER DEFAULT 0, -- 0 or 1
        FOREIGN KEY (checklist_master_id) REFERENCES daily_checklist_master(id)
    )''')

    # 14. Weekly Interviews (週次面談)
    c.execute('''CREATE TABLE IF NOT EXISTS weekly_interviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        client_name TEXT,
        content TEXT,
        staff_name TEXT,
        completed INTEGER DEFAULT 0
    )''')

    # 15. Daily Meeting Notes (朝礼・終礼 自由記述)
    c.execute('''CREATE TABLE IF NOT EXISTS daily_meeting_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        meeting_type TEXT, -- 'morning', 'evening'
        attendance_total INTEGER DEFAULT 0,
        attendance_fullday INTEGER DEFAULT 0,
        attendance_am INTEGER DEFAULT 0,
        attendance_pm INTEGER DEFAULT 0,
        absence_with_bonus INTEGER DEFAULT 0, -- 欠席時対応加算
        absence_no_bonus INTEGER DEFAULT 0,   -- 欠席（非加算）
        late_early INTEGER DEFAULT 0,         -- 遅刻・早退
        schedule_notes TEXT, -- 本日の予定・行動・共有事項
        client_notes TEXT,   -- ご利用者共有事項
        business_notes TEXT, -- 業務連絡
        other_notes TEXT,    -- その他
        participants TEXT    -- 参加スタッフ
    )''')

    # 16. Reward Rate Table (就労定着率 × 基本報酬)
    c.execute('''CREATE TABLE IF NOT EXISTS reward_rate_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        retention_label TEXT, -- '50%以上', '40%以上 50%未満' etc.
        retention_min REAL,
        retention_max REAL,
        units INTEGER -- 単位数
    )''')

    conn.commit()

    # 17. Office KPI (事業所別営業KPI)
    c.execute('''CREATE TABLE IF NOT EXISTS office_kpi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period_start DATE,
        period_end DATE,
        office_name TEXT NOT NULL,
        inquiries INTEGER DEFAULT 0,       -- 問合数
        interviews INTEGER DEFAULT 0,      -- 面談実施数
        trials INTEGER DEFAULT 0,          -- 体験実施数
        enrollments INTEGER DEFAULT 0,     -- 入所
        inquiry_to_interview REAL,         -- 問合→面談率
        interview_to_trial REAL,           -- 面談→体験率
        trial_to_enrollment REAL,          -- 体験→入所率
        inquiry_to_enrollment REAL,        -- 問合→入所率
        interview_to_enrollment REAL,      -- 面談→入所率
        interview_cancel_rate REAL,        -- 面談キャンセル率
        interview_bookings INTEGER DEFAULT 0, -- 面談予約数
        trial_cancel_rate REAL             -- 体験キャンセル率
    )''')

    conn.commit()

    # 18. Monthly Office Targets (事業所別 月次目標 vs 実績)
    c.execute('''CREATE TABLE IF NOT EXISTS monthly_office_targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year INTEGER,
        month INTEGER,
        office_name TEXT NOT NULL,
        target INTEGER DEFAULT 0,
        actual INTEGER DEFAULT 0,
        gap INTEGER DEFAULT 0,
        achievement_rate REAL DEFAULT 0
    )''')

    conn.commit()

    # 19. Channel Messages (事業所チャンネル)
    c.execute('''CREATE TABLE IF NOT EXISTS channel_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        office_name TEXT NOT NULL,
        author_id INTEGER,
        author_name TEXT,
        msg_type TEXT DEFAULT 'general',
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # 20. Roleplay Records (ロープレ記録)
    c.execute('''CREATE TABLE IF NOT EXISTS roleplay_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER,
        staff_name TEXT,
        scenario TEXT,
        category TEXT,
        conversation TEXT,
        ai_feedback TEXT,
        learning_notes TEXT,
        application_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP
    )''')

    # 21. 1on1 Records (1on1議事録)
    c.execute('''CREATE TABLE IF NOT EXISTS oneonone_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        manager_id INTEGER,
        manager_name TEXT,
        staff_id INTEGER,
        staff_name TEXT,
        meeting_date DATE,
        minutes TEXT,
        next_meeting_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # 22. 1on1 Action Items (実行記録)
    c.execute('''CREATE TABLE IF NOT EXISTS oneonone_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id INTEGER,
        staff_id INTEGER,
        action_text TEXT,
        due_date DATE,
        status TEXT DEFAULT 'pending',
        completion_notes TEXT,
        completed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()

    # 23. Client Daily Records (利用者 日次通所実績)
    c.execute('''CREATE TABLE IF NOT EXISTS client_daily_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        record_date DATE NOT NULL,
        service_type TEXT DEFAULT '通所',
        clock_in TIME,
        clock_out TIME,
        pickup_flag INTEGER DEFAULT 0,
        dropoff_flag INTEGER DEFAULT 0,
        meal_flag INTEGER DEFAULT 0,
        absence_contact INTEGER DEFAULT 0,
        absence_support INTEGER DEFAULT 0,
        outside_support INTEGER DEFAULT 0,
        memo TEXT,
        recorded_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # 24. Support Records (支援記録/ケース記録)
    c.execute('''CREATE TABLE IF NOT EXISTS support_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        record_date DATE NOT NULL,
        service_type TEXT DEFAULT '通所',
        support_content TEXT,
        client_condition TEXT,
        goal_progress TEXT,
        staff_id INTEGER,
        staff_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # 25. Addition Settings (加算設定マスタ)
    c.execute('''CREATE TABLE IF NOT EXISTS addition_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        office_name TEXT NOT NULL,
        addition_name TEXT NOT NULL,
        addition_code TEXT,
        unit_price INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        notes TEXT
    )''')

    conn.commit()

    # 26. Offices (事業所マスタ)
    c.execute('''CREATE TABLE IF NOT EXISTS offices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        office_number TEXT,          -- 事業所番号（10桁）
        city_code TEXT,              -- 市町村番号（6桁）
        address TEXT,
        phone TEXT,
        service_type TEXT DEFAULT '就労移行支援',
        capacity INTEGER DEFAULT 20,  -- 定員
        is_active INTEGER DEFAULT 1
    )''')

    # 27. Admin Interactions (行政対応履歴)
    c.execute('''CREATE TABLE IF NOT EXISTS admin_interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        office_id INTEGER,
        interaction_date DATE,
        category TEXT,               -- '指定更新', '実地指導', '加算届出', '処遇改善', 'その他'
        counterpart_org TEXT,        -- 相手先機関（市役所、県庁等）
        counterpart_person TEXT,     -- 担当者名
        channel TEXT,                -- '電話', '訪問', 'メール', '書面'
        summary TEXT,                -- 会話内容・議事録
        audio_file_path TEXT,        -- 録音データパス
        next_action TEXT,            -- 次のアクション
        next_action_date DATE,       -- 次回期日
        status TEXT DEFAULT '対応中', -- '対応中', '完了', '保留'
        staff_id INTEGER,            -- 記録者
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (office_id) REFERENCES offices(id),
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')

    conn.commit()

    # Expand clients table with additional columns (safe ALTER TABLE)
    _safe_alter = lambda sql: _try_alter(c, sql)
    _safe_alter("ALTER TABLE clients ADD COLUMN contracted_days INTEGER DEFAULT 22")
    _safe_alter("ALTER TABLE clients ADD COLUMN office_name TEXT DEFAULT ''")
    _safe_alter("ALTER TABLE clients ADD COLUMN disability_type TEXT DEFAULT ''")
    _safe_alter("ALTER TABLE clients ADD COLUMN municipality_code TEXT DEFAULT ''")

    # Add office_id to existing tables
    _safe_alter("ALTER TABLE staff ADD COLUMN office_id INTEGER DEFAULT NULL")
    _safe_alter("ALTER TABLE clients ADD COLUMN office_id INTEGER DEFAULT NULL")
    _safe_alter("ALTER TABLE user_candidates ADD COLUMN office_id INTEGER DEFAULT NULL")
    _safe_alter("ALTER TABLE client_daily_records ADD COLUMN office_id INTEGER DEFAULT NULL")
    _safe_alter("ALTER TABLE support_records ADD COLUMN office_id INTEGER DEFAULT NULL")

    conn.commit()

    # 28. Office Threads (事業所スレッド — Notion風)
    c.execute('''CREATE TABLE IF NOT EXISTS office_threads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        office_id INTEGER,
        title TEXT NOT NULL,
        created_by INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        thread_type TEXT DEFAULT 'general',
        pinned INTEGER DEFAULT 0,
        FOREIGN KEY (office_id) REFERENCES offices(id),
        FOREIGN KEY (created_by) REFERENCES staff(id)
    )''')

    # 29. Thread Posts (スレッド投稿)
    c.execute('''CREATE TABLE IF NOT EXISTS thread_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id INTEGER,
        author_id INTEGER,
        content TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (thread_id) REFERENCES office_threads(id),
        FOREIGN KEY (author_id) REFERENCES staff(id)
    )''')

    # 30. Client Learning Log (利用者学習記録)
    c.execute('''CREATE TABLE IF NOT EXISTS client_learning_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        date DATE,
        category TEXT,
        title TEXT,
        content TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )''')

    # 31. Client Health Check-in (利用者体調チェックイン)
    c.execute('''CREATE TABLE IF NOT EXISTS client_health_checkin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        date DATE,
        sleep_hours REAL,
        condition_score INTEGER,
        meal_record TEXT,
        exercise_record TEXT,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )''')

    # 32. Class Schedule (授業カレンダー)
    c.execute('''CREATE TABLE IF NOT EXISTS class_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        office_id INTEGER,
        date DATE,
        start_time TEXT,
        end_time TEXT,
        title TEXT,
        description TEXT,
        instructor TEXT,
        FOREIGN KEY (office_id) REFERENCES offices(id)
    )''')

    # 33. HQ Questions (本部への質問)
    c.execute('''CREATE TABLE IF NOT EXISTS hq_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER,
        staff_name TEXT,
        office_id INTEGER,
        question TEXT,
        ai_answer TEXT,
        is_escalated INTEGER DEFAULT 0,
        escalation_category TEXT,
        escalation_status TEXT DEFAULT 'pending',
        human_response TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')

    # 34. Individual Support Plans (個別支援計画)
    c.execute('''CREATE TABLE IF NOT EXISTS individual_support_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        office_id INTEGER,
        plan_number INTEGER DEFAULT 1,
        plan_date DATE,
        review_date DATE,
        long_term_goal TEXT,
        short_term_goal TEXT,
        support_content TEXT,
        status TEXT DEFAULT '作成中',
        staff_id INTEGER,
        staff_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id),
        FOREIGN KEY (office_id) REFERENCES offices(id)
    )''')

    # 35. Monitoring Records (モニタリング記録)
    c.execute('''CREATE TABLE IF NOT EXISTS monitoring_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        plan_id INTEGER,
        office_id INTEGER,
        monitoring_date DATE,
        goal_achievement TEXT,
        support_evaluation TEXT,
        client_satisfaction TEXT,
        needs_plan_change INTEGER DEFAULT 0,
        change_reason TEXT,
        next_monitoring_date DATE,
        staff_id INTEGER,
        staff_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id),
        FOREIGN KEY (plan_id) REFERENCES individual_support_plans(id)
    )''')

    # 36. Assessment Records (アセスメント記録)
    c.execute('''CREATE TABLE IF NOT EXISTS assessment_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        office_id INTEGER,
        assessment_date DATE,
        assessment_type TEXT DEFAULT '初回',
        living_situation TEXT,
        health_condition TEXT,
        disability_characteristics TEXT,
        work_experience TEXT,
        strengths TEXT,
        challenges TEXT,
        support_needs TEXT,
        employment_goal TEXT,
        staff_id INTEGER,
        staff_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )''')

    # 37. Deduction Items (減算項目管理)
    c.execute('''CREATE TABLE IF NOT EXISTS deduction_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        office_id INTEGER,
        year INTEGER,
        month INTEGER,
        deduction_type TEXT,
        deduction_reason TEXT,
        deduction_units INTEGER DEFAULT 0,
        status TEXT DEFAULT '未確認',
        staff_id INTEGER,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )''')

    # 38. Emergency Contacts (緊急連絡先)
    c.execute('''CREATE TABLE IF NOT EXISTS emergency_contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_type TEXT NOT NULL,
        person_id INTEGER,
        person_name TEXT NOT NULL,
        relationship TEXT,
        phone_primary TEXT,
        phone_secondary TEXT,
        email TEXT,
        address TEXT,
        notes TEXT,
        office_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # 39. Office Financials (事業所別 P&L)
    c.execute('''CREATE TABLE IF NOT EXISTS office_financials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        office_name TEXT NOT NULL,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        revenue INTEGER DEFAULT 0,
        revenue_target INTEGER DEFAULT 0,
        sga INTEGER DEFAULT 0,
        sga_target INTEGER DEFAULT 0,
        profit INTEGER DEFAULT 0,
        profit_target INTEGER DEFAULT 0,
        new_users INTEGER DEFAULT 0,
        new_users_target INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # 40. Thread Posts (Threads投稿)
    c.execute('''CREATE TABLE IF NOT EXISTS thread_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        office_id INTEGER,
        author_id INTEGER,
        author_name TEXT,
        content TEXT NOT NULL,
        image_path TEXT,
        likes_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # 41. Thread Comments (Threadsコメント)
    c.execute('''CREATE TABLE IF NOT EXISTS thread_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        author_id INTEGER,
        author_name TEXT,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES thread_posts(id)
    )''')

    # 42. Thread Likes (Threadsいいね)
    c.execute('''CREATE TABLE IF NOT EXISTS thread_likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER,
        user_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES thread_posts(id),
        UNIQUE(post_id, user_id)
    )''')

    conn.commit()

    # Client portal columns
    _safe_alter("ALTER TABLE clients ADD COLUMN login_pin TEXT DEFAULT '1234'")
    _safe_alter("ALTER TABLE clients ADD COLUMN graduation_step TEXT DEFAULT 'training_basic'")
    _safe_alter("ALTER TABLE clients ADD COLUMN age INTEGER DEFAULT NULL")
    _safe_alter("ALTER TABLE clients ADD COLUMN disability_detail TEXT DEFAULT ''")
    _safe_alter("ALTER TABLE clients ADD COLUMN planned_months INTEGER DEFAULT NULL")

    # 1on1: meeting_type + client fields
    _safe_alter("ALTER TABLE oneonone_records ADD COLUMN meeting_type TEXT DEFAULT 'supervisor'")
    _safe_alter("ALTER TABLE oneonone_records ADD COLUMN client_id INTEGER DEFAULT NULL")
    _safe_alter("ALTER TABLE oneonone_records ADD COLUMN client_name TEXT DEFAULT ''")

    conn.commit()
    conn.close()


def _try_alter(cursor, sql):
    """Safe ALTER TABLE — ignore if column already exists."""
    try:
        cursor.execute(sql)
    except Exception:
        pass

def seed_data():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check if data exists
    c.execute("SELECT count(*) FROM staff")
    if c.fetchone()[0] == 0:
        print("Seeding initial data...")
        # Staff
        staffs = [
            ('高橋 支援員', 28, 'staff', '2024-04-01', 'takahashi@nihon-shuro.co.jp'),
            ('佐藤 マネージャー', 35, 'manager', '2020-04-01', 'sato@nihon-shuro.co.jp'),
            ('鈴木 支援員', 24, 'staff', '2025-04-01', 'suzuki@nihon-shuro.co.jp')
        ]
        c.executemany("INSERT INTO staff (name, age, role, joined_date, email) VALUES (?, ?, ?, ?, ?)", staffs)
        
        # User Candidates
        candidates = [
            ('田中 太郎', '相談支援A', '体験', 1, '2026-02-01', '2026-02-10', '2026-02-15', None, 150000, '精神障害、週3日希望'),
            ('山田 花子', 'HP問い合わせ', '見学', 1, '2026-02-12', None, None, None, 0, '事務職希望')
        ]
        c.executemany("INSERT INTO user_candidates (name, source, status, staff_id, contact_date, intake_date, experience_date, contract_date, expected_revenue, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", candidates)

        conn.commit()

    # Seed clients if empty
    c = conn.cursor()
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', clients)
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
        evening_weekly = [
            ('evening', 'weekly', '「11_外交報告」外交実績ワークフロー 報告', 1),
            ('evening', 'weekly', '備品在庫チェック 備品事前承認シート', 2),
            ('evening', 'weekly', '週報資料作成（MTG準備）', 3),
            ('evening', 'weekly', '顧客管理KPI', 4),
        ]
        evening_monthly = [
            ('evening', 'monthly', '朝礼・終礼・デイリーチェック 翌月分作成', 1),
            ('evening', 'monthly', '電子請求システム 支給決定通知の確認', 2),
            ('evening', 'monthly', 'knowbe請求書・代理受領書印刷 / ご利用者へお渡し', 3),
            ('evening', 'monthly', '責任者×スタッフ1on1日程調整', 4),
            ('evening', 'monthly', '外交スケジュール決める（Googleカレンダー共有する）', 5),
            ('evening', 'monthly', '勤務形態表作成 / 該当月 / 過去分ファイリング', 6),
            ('evening', 'monthly', '自社交通費助成申請用紙回収', 7),
            ('evening', 'monthly', '自社交通費助成申請内容を入力報告する', 8),
            ('evening', 'monthly', '各スタッフ（マネーフォワード勤怠最終確認、経費精算最終確認）', 9),
            ('evening', 'monthly', 'knowbe前月分の支援記録の誤字脱字確認・印刷・配布・ファイリング', 10),
            ('evening', 'monthly', 'knowbe前月分の実績記録表 / 運営KPIシート / 通所スケジュール 確認', 11),
            ('evening', 'monthly', '実績記録表の印刷・押印依頼・回収・ファイリング', 12),
            ('evening', 'monthly', 'ご利用者アンケート調査送信', 13),
            ('evening', 'monthly', '国保連請求業務', 14),
            ('evening', 'monthly', '個別支援計画更新時期確認 / スケジュール設定', 15),
            ('evening', 'monthly', '利用者自己負担額入力（請求管理表）', 16),
        ]
        all_items = morning_daily + evening_daily + evening_weekly + evening_monthly
        c.executemany("INSERT INTO daily_checklist_master (meeting_type, category, item_text, sort_order) VALUES (?, ?, ?, ?)", all_items)
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
        c.executemany("INSERT INTO reward_rate_table (retention_label, retention_min, retention_max, units) VALUES (?, ?, ?, ?)", rates)
        conn.commit()

    # Seed office KPI if empty
    c.execute("SELECT count(*) FROM office_kpi")
    if c.fetchone()[0] == 0:
        print("Seeding office KPI data...")
        kpi_data = [
            ('2025-10-19', '2026-02-16', '全体', 194, 138, 69, 24, 71.1, 50.0, 34.8, 12.4, 17.4, 14.3, 161, 29.59),
            ('2025-10-19', '2026-02-16', '川崎 駅前校', 20, 10, 4, 3, 50.0, 40.0, 75.0, 15.0, 30.0, 28.6, 14, 33.33),
            ('2025-10-19', '2026-02-16', '横浜西口 校', 35, 28, 17, 6, 80.0, 60.7, 35.3, 17.1, 21.4, 6.7, 30, 15.00),
            ('2025-10-19', '2026-02-16', '本厚木 駅前校', 15, 11, 3, 4, 73.3, 27.3, 133.3, 26.7, 36.4, 15.4, 13, 50.00),
            ('2025-10-19', '2026-02-16', '西船橋 駅前校', 27, 21, 11, 3, 77.8, 52.4, 27.3, 11.1, 14.3, 12.5, 24, 42.11),
            ('2025-10-19', '2026-02-16', '三鷹 駅前校', 41, 32, 17, 0, 78.0, 53.1, 0.0, 0.0, 0.0, 3.0, 33, 26.09),
            ('2025-10-19', '2026-02-16', '柏 駅前校', 17, 15, 9, 5, 88.2, 60.0, 55.6, 29.4, 33.3, 11.8, 17, 30.77),
            ('2025-10-19', '2026-02-16', '関内（馬車道） 駅前校', 6, 3, 0, 0, 50.0, 0.0, 0.0, 0.0, 0.0, 50.0, 6, 100.00),
            ('2025-10-19', '2026-02-16', '川越 駅前校', 33, 18, 8, 3, 54.5, 44.4, 37.5, 9.1, 16.7, 25.0, 24, 20.00),
        ]
        c.executemany('''INSERT INTO office_kpi (period_start, period_end, office_name, inquiries, interviews, trials, enrollments,
            inquiry_to_interview, interview_to_trial, trial_to_enrollment, inquiry_to_enrollment, interview_to_enrollment,
            interview_cancel_rate, interview_bookings, trial_cancel_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', kpi_data)
        conn.commit()

    # Seed monthly office targets if empty
    c.execute("SELECT count(*) FROM monthly_office_targets")
    if c.fetchone()[0] == 0:
        print("Seeding monthly office targets...")
        # (year, month, office_name, target, actual, gap, achievement_rate)
        targets = [
            # April
            (2025, 4, '全体', 465, 354, 111, 76.1),
            (2025, 4, '川崎', 30, 5, 25, 16.7),
            (2025, 4, '横浜', 75, 15, 60, 20.0),
            (2025, 4, '西船橋', 75, 114, -39, 152.0),
            (2025, 4, '本厚木', 75, 76, -1, 101.3),
            (2025, 4, '柏', 75, 80, -5, 106.7),
            (2025, 4, '三鷹', 100, 140, -40, 140.0),  # estimated from gap
            (2025, 4, '関内', 30, 15, 15, 50.0),
            (2025, 4, '川越', 30, 19, 11, 63.3),
            # May
            (2025, 5, '全体', 635, 661, -26, 104.1),
            (2025, 5, '川崎', 30, 61, -31, 203.3),
            (2025, 5, '横浜', 100, 28, 72, 28.0),
            (2025, 5, '西船橋', 100, 104, -4, 104.0),
            (2025, 5, '本厚木', 100, 110, -10, 110.0),
            (2025, 5, '柏', 100, 140, -40, 140.0),
            (2025, 5, '三鷹', 100, 142, -42, 142.0),
            (2025, 5, '関内', 30, 47, -17, 156.7),
            (2025, 5, '川越', 75, 29, 46, 38.7),
        ]
        c.executemany("INSERT INTO monthly_office_targets (year, month, office_name, target, actual, gap, achievement_rate) VALUES (?, ?, ?, ?, ?, ?, ?)", targets)
        conn.commit()
    
    # Seed offices if empty
    c.execute("SELECT count(*) FROM offices")
    if c.fetchone()[0] == 0:
        print("Seeding offices...")
        offices = [
            ('A事業所', '1234567890', '141003', '東京都品川区1-1-1', '03-1234-5678', '就労移行支援', 20, 1),
        ]
        c.executemany('''INSERT INTO offices (name, office_number, city_code, address, phone, service_type, capacity, is_active) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', offices)
        conn.commit()

    # Assign office_id to staff and clients if not set
    c.execute("UPDATE staff SET office_id = 1 WHERE office_id IS NULL")
    c.execute("UPDATE clients SET office_id = 1 WHERE office_id IS NULL")
    conn.commit()

    # Seed office_financials if empty
    c.execute("SELECT count(*) FROM office_financials")
    if c.fetchone()[0] == 0:
        print("Seeding office financials...")
        offices = ['川崎', '横浜', '西船橋', '本厚木', '柏', '三鷹', '関内', '川越']
        import random
        random.seed(42)
        financials = []
        for office in offices:
            for month in range(1, 7):  # Jan-Jun 2025
                rev_target = random.randint(3000000, 6000000)
                rev = int(rev_target * random.uniform(0.7, 1.3))
                sga_target = random.randint(2000000, 4000000)
                sga = int(sga_target * random.uniform(0.85, 1.15))
                profit = rev - sga
                profit_target = rev_target - sga_target
                new_target = random.randint(2, 8)
                new_actual = random.randint(0, 10)
                financials.append((office, 2025, month, rev, rev_target, sga, sga_target, profit, profit_target, new_actual, new_target))
        c.executemany("""INSERT INTO office_financials 
            (office_name, year, month, revenue, revenue_target, sga, sga_target, profit, profit_target, new_users, new_users_target) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", financials)
        conn.commit()
    
    conn.close()

if __name__ == "__main__":
    init_db()
    seed_data()
    print(f"Database initialized: {DB_PATH}")
