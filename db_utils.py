import datetime
import pandas as pd
from db_config import get_connection

def get_staff_list(office_id=None):
    conn = get_connection()
    if office_id:
        df = pd.read_sql("SELECT * FROM staff WHERE office_id = %s", conn, params=[office_id])
    else:
        df = pd.read_sql("SELECT * FROM staff", conn)
    conn.close()
    return df

def get_user_candidates():
    conn = get_connection()
    df = pd.read_sql("SELECT uc.*, s.name as staff_name FROM user_candidates uc LEFT JOIN staff s ON uc.staff_id = s.id", conn)
    conn.close()
    return df

def add_daily_report(staff_id, date, sentiment, content, learning):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO daily_reports (staff_id, date, sentiment_score, content, learning) VALUES (%s, %s, %s, %s, %s)",
              (staff_id, date, sentiment, content, learning))
    conn.commit()
    conn.close()

def get_daily_reports(staff_id=None):
    conn = get_connection()
    query = "SELECT dr.*, s.name as staff_name FROM daily_reports dr LEFT JOIN staff s ON dr.staff_id = s.id"
    if staff_id:
        query += f" WHERE staff_id = {staff_id}"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def add_user_candidate(name, source, status, staff_id, expected_revenue, note):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO user_candidates (name, source, status, staff_id, contact_date, expected_revenue, note) VALUES (%s, %s, %s, %s, CURRENT_DATE, %s, %s)",
              (name, source, status, staff_id, expected_revenue, note))
    conn.commit()
    conn.close()

def get_todays_attendance(staff_id):
    conn = get_connection()
    c = conn.cursor()
    today = datetime.date.today()
    c.execute("SELECT * FROM attendance WHERE staff_id = %s AND date = %s", (staff_id, today))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0], "staff_id": row[1], "date": row[2], 
            "clock_in": row[3], "clock_out": row[4], 
            "break_start": row[5], "break_end": row[6], "status": row[7]
        }
    return None

def clock_action(staff_id, action):
    conn = get_connection()
    c = conn.cursor()
    today = datetime.date.today()
    now = datetime.datetime.now()
    
    # Check if record exists
    c.execute("SELECT id, status FROM attendance WHERE staff_id = %s AND date = %s", (staff_id, today))
    row = c.fetchone()
    
    if action == "clock_in":
        if not row:
            c.execute("INSERT INTO attendance (staff_id, date, clock_in, status) VALUES (%s, %s, %s, 'working')", (staff_id, today, now))
    
    elif action == "clock_out":
        if row:
            c.execute("UPDATE attendance SET clock_out = %s, status = 'finished' WHERE id = %s", (now, row[0]))
            
    elif action == "break_start":
        if row:
            c.execute("UPDATE attendance SET break_start = %s, status = 'break' WHERE id = %s", (now, row[0]))

    elif action == "break_end":
        if row:
            c.execute("UPDATE attendance SET break_end = %s, status = 'working' WHERE id = %s", (now, row[0]))

    conn.commit()
    conn.close()

def get_monthly_attendance(staff_id):
    conn = get_connection()
    # Simple query for now
    df = pd.read_sql(f"SELECT * FROM attendance WHERE staff_id = {staff_id} ORDER BY date DESC", conn)
    conn.close()
    return df

# --- Labor & Admin Utils ---

def upsert_staff_details(staff_id, address, birthday, phone, bank_info, dependents, transport, salary,
                          qualifications="", resume_file_path=None, notes=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO staff_details
        (staff_id, address, birthday, phone, bank_info, dependents_count,
         commuter_allowance, base_salary, qualifications, resume_file_path, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (staff_id) DO UPDATE SET
         address = EXCLUDED.address, birthday = EXCLUDED.birthday, phone = EXCLUDED.phone,
         bank_info = EXCLUDED.bank_info, dependents_count = EXCLUDED.dependents_count,
         commuter_allowance = EXCLUDED.commuter_allowance, base_salary = EXCLUDED.base_salary,
         qualifications = EXCLUDED.qualifications, resume_file_path = EXCLUDED.resume_file_path,
         notes = EXCLUDED.notes""",
              (staff_id, address, birthday, phone, bank_info, dependents, transport, salary,
               qualifications, resume_file_path, notes))
    conn.commit()
    conn.close()

def get_staff_details(staff_id):
    conn = get_connection()
    df = pd.read_sql(f"SELECT * FROM staff_details WHERE staff_id = {staff_id}", conn)
    conn.close()
    return df.iloc[0] if not df.empty else None

def add_labor_procedure(staff_id, category, item_name, due_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO labor_procedures (staff_id, category, item_name, status, due_date) VALUES (%s, %s, %s, 'not_started', %s)",
              (staff_id, category, item_name, due_date))
    conn.commit()
    conn.close()

def get_labor_procedures():
    conn = get_connection()
    df = pd.read_sql("SELECT lp.*, s.name as staff_name FROM labor_procedures lp LEFT JOIN staff s ON lp.staff_id = s.id", conn)
    conn.close()
    return df

def update_procedure_status(proc_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE labor_procedures SET status = %s WHERE id = %s", (status, proc_id))
    if status == 'completed':
        c.execute("UPDATE labor_procedures SET completed_date = CURRENT_DATE WHERE id = %s", (proc_id,))
    conn.commit()
    conn.close()

# --- Client / 利用者台帳 ---

# get_clients is defined at the bottom of this file with office_id support

def add_client(data_dict):
    conn = get_connection()
    c = conn.cursor()
    cols = ', '.join(data_dict.keys())
    placeholders = ', '.join(['%s'] * len(data_dict))
    c.execute(f"INSERT INTO clients ({cols}) VALUES ({placeholders})", list(data_dict.values()))
    conn.commit()
    conn.close()

def update_client(client_id, data_dict):
    conn = get_connection()
    c = conn.cursor()
    set_clause = ', '.join([f"{k} = %s" for k in data_dict.keys()])
    c.execute(f"UPDATE clients SET {set_clause} WHERE id = %s", list(data_dict.values()) + [client_id])
    conn.commit()
    conn.close()

# --- Meeting System (朝礼・終礼) ---

def get_checklist_items(meeting_type, category=None):
    conn = get_connection()
    query = "SELECT * FROM daily_checklist_master WHERE meeting_type = %s"
    params = [meeting_type]
    if category:
        query += " AND category = %s"
        params.append(category)
    query += " ORDER BY sort_order"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def save_checklist_log(date, checked_ids):
    """Save which items were checked for a given date."""
    conn = get_connection()
    c = conn.cursor()
    # Clear existing for date
    c.execute("DELETE FROM daily_checklist_log WHERE date = %s", (date,))
    for master_id in checked_ids:
        c.execute("INSERT INTO daily_checklist_log (date, checklist_master_id, checked) VALUES (%s, %s, 1)", (date, master_id))
    conn.commit()
    conn.close()

def get_checklist_log(date):
    conn = get_connection()
    df = pd.read_sql("SELECT checklist_master_id FROM daily_checklist_log WHERE date = %s AND checked = 1", conn, params=[date])
    conn.close()
    return set(df['checklist_master_id'].tolist()) if not df.empty else set()

def save_meeting_notes(date, meeting_type, data_dict):
    conn = get_connection()
    c = conn.cursor()
    # Upsert
    c.execute("DELETE FROM daily_meeting_notes WHERE date = %s AND meeting_type = %s", (date, meeting_type))
    cols = ['date', 'meeting_type'] + list(data_dict.keys())
    vals = [date, meeting_type] + list(data_dict.values())
    placeholders = ', '.join(['%s'] * len(vals))
    c.execute(f"INSERT INTO daily_meeting_notes ({', '.join(cols)}) VALUES ({placeholders})", vals)
    conn.commit()
    conn.close()

def get_meeting_notes(date, meeting_type):
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM daily_meeting_notes WHERE date = %s AND meeting_type = %s", conn, params=[date, meeting_type])
    conn.close()
    return df.iloc[0] if not df.empty else None

def get_reward_rates():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM reward_rate_table ORDER BY retention_min DESC", conn)
    conn.close()
    return df

def add_weekly_interview(date, client_name, content, staff_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO weekly_interviews (date, client_name, content, staff_name, completed) VALUES (%s, %s, %s, %s, 0)",
              (date, client_name, content, staff_name))
    conn.commit()
    conn.close()

def get_weekly_interviews(date=None):
    conn = get_connection()
    query = "SELECT * FROM weekly_interviews"
    params = []
    if date:
        query += " WHERE date = %s"
        params.append(date)
    query += " ORDER BY date DESC"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

# --- Office KPI ---

def get_office_kpi():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM office_kpi ORDER BY id", conn)
    conn.close()
    return df

def get_monthly_targets(year=None):
    conn = get_connection()
    query = "SELECT * FROM monthly_office_targets"
    params = []
    if year:
        query += " WHERE year = %s"
        params.append(year)
    query += " ORDER BY year, month, id"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

# --- Channel Messages ---

def post_channel_message(office_name, author_id, author_name, msg_type, content):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO channel_messages (office_name, author_id, author_name, msg_type, content) VALUES (%s, %s, %s, %s, %s)",
              (office_name, author_id, author_name, msg_type, content))
    conn.commit()
    conn.close()

def get_channel_messages(office_name, limit=50):
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM channel_messages WHERE office_name = %s ORDER BY created_at DESC LIMIT %s",
                      conn, params=[office_name, limit])
    conn.close()
    return df

# --- Roleplay Records ---

def save_roleplay_record(staff_id, staff_name, scenario, category, conversation, ai_feedback, learning_notes):
    conn = get_connection()
    c = conn.cursor()
    import json
    conv_json = json.dumps(conversation, ensure_ascii=False)
    c.execute("""INSERT INTO roleplay_records (staff_id, staff_name, scenario, category, conversation, ai_feedback, learning_notes)
                 VALUES (%s, %s, %s, %s, %s, %s, %s)""",
              (staff_id, staff_name, scenario, category, conv_json, ai_feedback, learning_notes))
    conn.commit()
    conn.close()

def get_roleplay_records(staff_id):
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM roleplay_records WHERE staff_id = %s ORDER BY created_at DESC", conn, params=[staff_id])
    conn.close()
    return df

def update_roleplay_application(record_id, application_notes):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE roleplay_records SET application_notes = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
              (application_notes, record_id))
    conn.commit()
    conn.close()

# --- 1on1 Records ---

def save_oneonone_record(manager_id, manager_name, staff_id, staff_name, meeting_date, minutes, next_date,
                          meeting_type='supervisor', client_id=None, client_name=''):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO oneonone_records
                 (manager_id, manager_name, staff_id, staff_name, meeting_date, minutes, next_meeting_date,
                  meeting_type, client_id, client_name)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
              (manager_id, manager_name, staff_id, staff_name, meeting_date, minutes, next_date,
               meeting_type, client_id, client_name))
    record_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return record_id

def get_oneonone_records(staff_id=None, manager_id=None, meeting_type=None):
    conn = get_connection()
    query = "SELECT * FROM oneonone_records"
    params = []
    conditions = []
    if staff_id:
        conditions.append("staff_id = ?")
        params.append(staff_id)
    if manager_id:
        conditions.append("manager_id = ?")
        params.append(manager_id)
    if meeting_type:
        conditions.append("meeting_type = ?")
        params.append(meeting_type)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY meeting_date DESC"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def add_oneonone_action(record_id, staff_id, action_text, due_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO oneonone_actions (record_id, staff_id, action_text, due_date) VALUES (%s, %s, %s, %s)",
              (record_id, staff_id, action_text, due_date))
    conn.commit()
    conn.close()

def get_oneonone_actions(staff_id=None, record_id=None):
    conn = get_connection()
    query = "SELECT * FROM oneonone_actions"
    params = []
    if record_id:
        query += " WHERE record_id = %s"
        params.append(record_id)
    elif staff_id:
        query += " WHERE staff_id = %s"
        params.append(staff_id)
    query += " ORDER BY created_at DESC"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def complete_oneonone_action(action_id, notes):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE oneonone_actions SET status = 'done', completion_notes = %s, completed_at = CURRENT_TIMESTAMP WHERE id = %s",
              (notes, action_id))
    conn.commit()
    conn.close()

# --- Attendance Reporting ---

def get_attendance_report(date_from=None, date_to=None, office_name=None):
    conn = get_connection()
    query = """SELECT a.*, s.name as staff_name, s.role
               FROM attendance a
               JOIN staff s ON a.staff_id = s.id
               WHERE 1=1"""
    params = []
    if date_from:
        query += " AND a.date >= %s"
        params.append(date_from)
    if date_to:
        query += " AND a.date <= %s"
        params.append(date_to)
    query += " ORDER BY a.date DESC, s.name"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def get_attendance_summary(date_from=None, date_to=None):
    conn = get_connection()
    query = """SELECT s.name as staff_name, s.role,
                      COUNT(a.id) as total_days,
                      SUM(CASE WHEN a.status = 'finished' THEN 1 ELSE 0 END) as completed_days,
                      COUNT(CASE WHEN a.clock_in IS NOT NULL THEN 1 END) as clocked_in_days
               FROM staff s
               LEFT JOIN attendance a ON s.id = a.staff_id"""
    params = []
    if date_from:
        query += " AND a.date >= %s"
        params.append(date_from)
    if date_to:
        query += " AND a.date <= %s"
        params.append(date_to)
    query += " GROUP BY s.id ORDER BY s.name"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

# --- Client Daily Records (利用者通所実績) ---

def add_client_daily_record(client_id, record_date, service_type, clock_in, clock_out,
                            pickup=0, dropoff=0, meal=0, absence_contact=0,
                            absence_support=0, outside_support=0, memo="", recorded_by=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO client_daily_records
                 (client_id, record_date, service_type, clock_in, clock_out,
                  pickup_flag, dropoff_flag, meal_flag, absence_contact,
                  absence_support, outside_support, memo, recorded_by)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
              (client_id, record_date, service_type, clock_in, clock_out,
               pickup, dropoff, meal, absence_contact, absence_support,
               outside_support, memo, recorded_by))
    conn.commit()
    conn.close()

def get_client_daily_records(client_id=None, date_from=None, date_to=None):
    conn = get_connection()
    query = """SELECT r.*, c.name as client_name, c.recipient_number
               FROM client_daily_records r
               JOIN clients c ON r.client_id = c.id WHERE 1=1"""
    params = []
    if client_id:
        query += " AND r.client_id = %s"
        params.append(client_id)
    if date_from:
        query += " AND r.record_date >= %s"
        params.append(date_from)
    if date_to:
        query += " AND r.record_date <= %s"
        params.append(date_to)
    query += " ORDER BY r.record_date DESC, c.name"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def get_monthly_usage_summary(year, month):
    """月次利用実績集計（利用者ごとの通所日数, 送迎回数, 食事回数, 欠席時対応回数）"""
    conn = get_connection()
    date_from = f"{year}-{month:02d}-01"
    if month == 12:
        date_to = f"{year+1}-01-01"
    else:
        date_to = f"{year}-{month+1:02d}-01"
    query = """SELECT c.id as client_id, c.name as client_name, c.recipient_number,
                      c.max_copay, c.contracted_days,
                      COALESCE(COUNT(r.id), 0) as total_days,
                      COALESCE(SUM(CASE WHEN r.service_type = '通所' THEN 1 ELSE 0 END), 0) as attend_days,
                      COALESCE(SUM(r.pickup_flag), 0) as pickup_count,
                      COALESCE(SUM(r.dropoff_flag), 0) as dropoff_count,
                      COALESCE(SUM(r.meal_flag), 0) as meal_count,
                      COALESCE(SUM(r.absence_support), 0) as absence_support_count,
                      COALESCE(SUM(r.outside_support), 0) as outside_support_count
               FROM clients c
               LEFT JOIN client_daily_records r ON c.id = r.client_id
                    AND r.record_date >= %s AND r.record_date < %s
               WHERE c.usage_status = '利用者'
               GROUP BY c.id
               ORDER BY c.name"""
    df = pd.read_sql(query, conn, params=[date_from, date_to])
    conn.close()
    df = df.fillna(0)
    return df

# --- Support Records (支援記録) ---

def add_support_record(client_id, record_date, service_type, content, condition, goal, staff_id, staff_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO support_records
                 (client_id, record_date, service_type, support_content, client_condition, goal_progress, staff_id, staff_name)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
              (client_id, record_date, service_type, content, condition, goal, staff_id, staff_name))
    conn.commit()
    conn.close()

def get_support_records(client_id=None, date_from=None, date_to=None):
    conn = get_connection()
    query = """SELECT s.*, c.name as client_name
               FROM support_records s
               JOIN clients c ON s.client_id = c.id WHERE 1=1"""
    params = []
    if client_id:
        query += " AND s.client_id = %s"
        params.append(client_id)
    if date_from:
        query += " AND s.record_date >= %s"
        params.append(date_from)
    if date_to:
        query += " AND s.record_date <= %s"
        params.append(date_to)
    query += " ORDER BY s.record_date DESC, c.name"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

# --- Addition Settings (加算設定) ---

def get_addition_settings(office_name=None):
    conn = get_connection()
    query = "SELECT * FROM addition_settings WHERE is_active = 1"
    params = []
    if office_name:
        query += " AND office_name = %s"
        params.append(office_name)
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def seed_addition_defaults():
    """就労移行支援の主な加算をデフォルト登録"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM addition_settings")
    if c.fetchone()[0] == 0:
        defaults = [
            ("全事業所", "初期加算", "6101", 30, "利用開始30日以内"),
            ("全事業所", "欠席時対応加算", "6111", 94, "欠席連絡+対応記録あり"),
            ("全事業所", "食事提供体制加算", "6121", 30, "食事提供あり"),
            ("全事業所", "送迎加算（片道）", "6131", 21, "送迎あり"),
            ("全事業所", "送迎加算（往復）", "6132", 42, "往復送迎"),
            ("全事業所", "移行準備支援体制加算(I)", "6141", 41, "就職率30%以上"),
            ("全事業所", "移行準備支援体制加算(II)", "6142", 12, "就職率20%以上"),
            ("全事業所", "就労定着支援体制加算", "6151", 0, "定着率70%以上"),
        ]
        for d in defaults:
            c.execute("INSERT INTO addition_settings (office_name, addition_name, addition_code, unit_price, notes) VALUES (%s, %s, %s, %s, %s)", d)
        conn.commit()
    conn.close()

# --- Client Alerts (アラート) ---

def get_client_alerts():
    """受給者証期限チェック、記録漏れチェック"""
    import datetime
    conn = get_connection()
    today = datetime.date.today()
    alerts = []

    # 受給者証期限チェック
    df = pd.read_sql("""SELECT id, name, certificate_expiry, payment_period_end
                        FROM clients WHERE usage_status = '利用者'""", conn)
    for _, row in df.iterrows():
        for col, label in [('certificate_expiry', '受給者証'), ('payment_period_end', '支給決定期間')]:
            if row[col]:
                try:
                    exp = datetime.date.fromisoformat(str(row[col]))
                    diff = (exp - today).days
                    if diff < 0:
                        alerts.append({"type": "danger", "client": row['name'],
                                       "msg": f"⛔ {label}が期限切れ（{row[col]}）"})
                    elif diff <= 7:
                        alerts.append({"type": "danger", "client": row['name'],
                                       "msg": f"🔴 {label}が7日以内に期限切れ（{row[col]}）"})
                    elif diff <= 30:
                        alerts.append({"type": "warning", "client": row['name'],
                                       "msg": f"🟡 {label}が30日以内に期限切れ（{row[col]}）"})
                except:
                    pass

    # 記録漏れチェック（通所実績があるのに支援記録がない）
    yesterday = today - datetime.timedelta(days=1)
    missing = pd.read_sql("""
        SELECT r.client_id, c.name, r.record_date
        FROM client_daily_records r
        JOIN clients c ON r.client_id = c.id
        LEFT JOIN support_records s ON r.client_id = s.client_id AND r.record_date = s.record_date
        WHERE s.id IS NULL AND r.record_date <= %s AND r.service_type = '通所'
        ORDER BY r.record_date DESC LIMIT 20
    """, conn, params=[str(yesterday)])
    for _, row in missing.iterrows():
        alerts.append({"type": "warning", "client": row['name'],
                       "msg": f"📝 {row['record_date']} の支援記録が未入力"})

    conn.close()
    return alerts

# --- 国保連CSV生成 ---

def generate_kokuhoren_csv(year, month):
    """サービス提供実績記録票のCSVデータ生成"""
    import io, csv, datetime
    summary = get_monthly_usage_summary(year, month)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "受給者証番号", "利用者名", "サービス種別", "提供年月",
        "利用日数", "通所日数", "送迎(迎)回数", "送迎(送)回数",
        "食事提供回数", "欠席時対応回数", "施設外支援日数",
        "契約支給量", "負担上限月額"
    ])
    
    for _, row in summary.iterrows():
        writer.writerow([
            row.get('recipient_number', ''),
            row['client_name'],
            "就労移行支援",
            f"{year}年{month:02d}月",
            row['total_days'],
            row['attend_days'],
            row['pickup_count'],
            row['dropoff_count'],
            row['meal_count'],
            row['absence_support_count'],
            row['outside_support_count'],
            row.get('contracted_days', 22),
            row.get('max_copay', '')
        ])
    
    return output.getvalue()

def generate_billing_detail_csv(year, month):
    """請求明細書CSVデータ生成"""
    import io, csv
    summary = get_monthly_usage_summary(year, month)
    additions = get_addition_settings()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "受給者証番号", "利用者名", "サービス種別", "提供年月",
        "基本報酬日数", "初期加算日数", "送迎加算回数", "食事加算回数",
        "欠席時対応加算回数", "合計単位数"
    ])
    
    # Get unit prices from addition settings
    unit_prices = {}
    for _, a in additions.iterrows():
        unit_prices[a['addition_name']] = a['unit_price']
    
    base_unit = 804  # 就労移行支援 基本報酬単位（定員20名以下）
    
    for _, row in summary.iterrows():
        _si = lambda v: 0 if v is None or (isinstance(v, float) and v != v) else int(v)
        attend = _si(row.get('attend_days', 0))
        pickup = _si(row.get('pickup_count', 0)) + _si(row.get('dropoff_count', 0))
        meal = _si(row.get('meal_count', 0))
        absence = _si(row.get('absence_support_count', 0))
        
        total_units = (attend * base_unit
                      + pickup * unit_prices.get('送迎加算（片道）', 21)
                      + meal * unit_prices.get('食事提供体制加算', 30)
                      + absence * unit_prices.get('欠席時対応加算', 94))
        
        writer.writerow([
            row.get('recipient_number', ''),
            row['client_name'],
            "就労移行支援",
            f"{year}年{month:02d}月",
            attend,
            0,  # 初期加算は別途計算
            pickup,
            meal,
            absence,
            total_units
        ])
    
    return output.getvalue()

# ====================================================================
# --- 事業所管理 ---
# ====================================================================

def get_offices():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM offices WHERE is_active = 1 ORDER BY id", conn)
    conn.close()
    return df

def get_office(office_id):
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM offices WHERE id = %s", conn, params=[office_id])
    conn.close()
    return df.iloc[0] if not df.empty else None

def get_office_summary(year, month):
    """全事業所のサマリー（利用者数/稼働率等）を取得"""
    conn = get_connection()
    date_from = f"{year}-{month:02d}-01"
    date_to = f"{year}-{month:02d}-31"

    query = """
    SELECT o.id as office_id, o.name as office_name, o.capacity,
           COUNT(DISTINCT c.id) as client_count,
           COUNT(DISTINCT CASE WHEN c.usage_status = '利用者' THEN c.id END) as active_clients,
           COALESCE(COUNT(DISTINCT r.id), 0) as total_records,
           COALESCE(SUM(CASE WHEN r.service_type = '通所' THEN 1 ELSE 0 END), 0) as attend_count
    FROM offices o
    LEFT JOIN clients c ON c.office_id = o.id
    LEFT JOIN client_daily_records r ON r.client_id = c.id
         AND r.record_date >= %s AND r.record_date <= %s
    WHERE o.is_active = 1
    GROUP BY o.id
    ORDER BY o.id
    """
    df = pd.read_sql(query, conn, params=[date_from, date_to])
    conn.close()
    df = df.fillna(0)
    return df

def get_clients(office_id=None):
    conn = get_connection()
    if office_id:
        df = pd.read_sql("SELECT * FROM clients WHERE office_id = %s ORDER BY id", conn, params=[office_id])
    else:
        df = pd.read_sql("SELECT * FROM clients ORDER BY id", conn)
    conn.close()
    return df

def get_user_candidates_by_office(office_id=None):
    conn = get_connection()
    if office_id:
        df = pd.read_sql("SELECT * FROM user_candidates WHERE office_id = %s ORDER BY id DESC", conn, params=[office_id])
    else:
        df = pd.read_sql("SELECT * FROM user_candidates ORDER BY id DESC", conn)
    conn.close()
    return df

# ====================================================================
# --- 行政対応履歴 ---
# ====================================================================

def add_admin_interaction(office_id, interaction_date, category, counterpart_org,
                          counterpart_person, channel, summary, audio_file_path=None,
                          next_action=None, next_action_date=None, staff_id=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO admin_interactions
        (office_id, interaction_date, category, counterpart_org, counterpart_person,
         channel, summary, audio_file_path, next_action, next_action_date, staff_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (office_id, interaction_date, category, counterpart_org, counterpart_person,
         channel, summary, audio_file_path, next_action, next_action_date, staff_id))
    conn.commit()
    conn.close()

def get_admin_interactions(office_id=None, category=None, limit=50):
    conn = get_connection()
    query = """SELECT ai.*, o.name as office_name, s.name as staff_name
               FROM admin_interactions ai
               LEFT JOIN offices o ON ai.office_id = o.id
               LEFT JOIN staff s ON ai.staff_id = s.id
               WHERE 1=1"""
    params = []
    if office_id:
        query += " AND ai.office_id = %s"
        params.append(office_id)
    if category:
        query += " AND ai.category = %s"
        params.append(category)
    query += f" ORDER BY ai.interaction_date DESC LIMIT {limit}"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def update_admin_interaction_status(interaction_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE admin_interactions SET status = %s WHERE id = %s", (status, interaction_id))
    conn.commit()
    conn.close()

# ============================================================
# Office Threads (Notion風)
# ============================================================

def get_threads(office_id, limit=50):
    conn = get_connection()
    df = pd.read_sql("""SELECT t.*, s.name as author_name,
        (SELECT COUNT(*) FROM thread_posts WHERE thread_id = t.id) as post_count
        FROM office_threads t
        LEFT JOIN staff s ON t.created_by = s.id
        WHERE t.office_id = %s
        ORDER BY t.pinned DESC, t.created_at DESC
        LIMIT %s""", conn, params=[office_id, limit])
    conn.close()
    return df

def create_thread(office_id, title, created_by, thread_type='general'):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO office_threads (office_id, title, created_by, thread_type) VALUES (%s,%s,%s,%s) RETURNING id",
              (office_id, title, created_by, thread_type))
    thread_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return thread_id

def get_thread_posts(thread_id):
    conn = get_connection()
    df = pd.read_sql("""SELECT p.*, s.name as author_name
        FROM thread_posts p
        LEFT JOIN staff s ON p.author_id = s.id
        WHERE p.thread_id = %s
        ORDER BY p.created_at ASC""", conn, params=[thread_id])
    conn.close()
    return df

def add_thread_post(thread_id, author_id, content):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO thread_posts (thread_id, author_id, content) VALUES (%s,%s,%s)",
              (thread_id, author_id, content))
    conn.commit()
    conn.close()

def toggle_thread_pin(thread_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE office_threads SET pinned = CASE WHEN pinned = 1 THEN 0 ELSE 1 END WHERE id = %s", (thread_id,))
    conn.commit()
    conn.close()

# ============================================================
# Class Schedule (授業カレンダー)
# ============================================================

def get_class_schedule(office_id, start_date=None, end_date=None):
    conn = get_connection()
    query = "SELECT * FROM class_schedule WHERE office_id = %s"
    params = [office_id]
    if start_date:
        query += " AND date >= %s"
        params.append(str(start_date))
    if end_date:
        query += " AND date <= %s"
        params.append(str(end_date))
    query += " ORDER BY date, start_time"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def add_class_schedule(office_id, date, start_time, end_time, title, description='', instructor=''):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO class_schedule (office_id, date, start_time, end_time, title, description, instructor)
        VALUES (%s,%s,%s,%s,%s,%s,%s)""", (office_id, date, start_time, end_time, title, description, instructor))
    conn.commit()
    conn.close()

# ============================================================
# Client Learning Log (利用者 学習記録)
# ============================================================

def get_client_learning_log(client_id, limit=50):
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM client_learning_log WHERE client_id = %s ORDER BY date DESC LIMIT %s",
                     conn, params=[client_id, limit])
    conn.close()
    return df

def add_client_learning_log(client_id, date, category, title, content):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO client_learning_log (client_id, date, category, title, content) VALUES (%s,%s,%s,%s,%s)",
              (client_id, date, category, title, content))
    conn.commit()
    conn.close()

# ============================================================
# Client Health Check-in (利用者 体調チェックイン)
# ============================================================

def get_client_health_checkins(client_id, limit=30):
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM client_health_checkin WHERE client_id = %s ORDER BY date DESC LIMIT %s",
                     conn, params=[client_id, limit])
    conn.close()
    return df

def add_client_health_checkin(client_id, date, sleep_hours, condition_score, meal_record, exercise_record, notes=''):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO client_health_checkin (client_id, date, sleep_hours, condition_score, meal_record, exercise_record, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s)""", (client_id, date, sleep_hours, condition_score, meal_record, exercise_record, notes))
    conn.commit()
    conn.close()

def get_todays_health_checkin(client_id):
    conn = get_connection()
    today = datetime.date.today().isoformat()
    df = pd.read_sql("SELECT * FROM client_health_checkin WHERE client_id = %s AND date = %s",
                     conn, params=[client_id, today])
    conn.close()
    return df.iloc[0] if not df.empty else None

# ============================================================
# Client Portal Helpers
# ============================================================

def get_client_by_id(client_id):
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM clients WHERE id = %s", conn, params=[int(client_id)])
    conn.close()
    return df.iloc[0] if not df.empty else None

def get_clients_for_login(office_id=None):
    conn = get_connection()
    query = "SELECT id, name, office_id FROM clients WHERE usage_status = '利用者'"
    params = []
    if office_id:
        query += " AND office_id = %s"
        params.append(office_id)
    query += " ORDER BY name"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def update_client_graduation_step(client_id, step):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE clients SET graduation_step = %s WHERE id = %s", (step, client_id))
    conn.commit()
    conn.close()

def get_client_oneonone_records(client_id, limit=20):
    """Get 1on1 records for a client (by matching client name in weekly_interviews)."""
    conn = get_connection()
    client = pd.read_sql("SELECT name FROM clients WHERE id = %s", conn, params=[client_id])
    if client.empty:
        conn.close()
        return pd.DataFrame()
    name = client.iloc[0]['name']
    df = pd.read_sql("SELECT * FROM weekly_interviews WHERE client_name = %s ORDER BY date DESC LIMIT %s",
                     conn, params=[name, limit])
    conn.close()
    return df

def get_todays_expected_clients(office_id=None):
    """Get clients expected to attend today based on client_daily_records."""
    conn = get_connection()
    today = datetime.date.today().isoformat()
    query = """SELECT c.id, c.name, c.disability_type, c.age, c.planned_months,
        cdr.clock_in, cdr.clock_out, cdr.service_type
        FROM client_daily_records cdr
        JOIN clients c ON cdr.client_id = c.id
        WHERE cdr.record_date = %s"""
    params = [today]
    if office_id:
        query += " AND cdr.office_id = %s"
        params.append(office_id)
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

import datetime


# ================================================================
# HQ Questions (本部への質問)
# ================================================================

def save_hq_question(staff_id, staff_name, office_id, question, ai_answer,
                     is_escalated=False, escalation_category=None):
    """本部への質問を保存"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO hq_questions
                 (staff_id, staff_name, office_id, question, ai_answer,
                  is_escalated, escalation_category)
                 VALUES (%s, %s, %s, %s, %s, %s, %s)""",
              (staff_id, staff_name, office_id, question, ai_answer,
               1 if is_escalated else 0, escalation_category))
    conn.commit()
    conn.close()


def get_hq_questions(staff_id=None, escalated_only=False):
    """本部への質問履歴を取得"""
    conn = get_connection()
    query = "SELECT * FROM hq_questions"
    params = []
    conditions = []
    if staff_id:
        conditions.append("staff_id = ?")
        params.append(staff_id)
    if escalated_only:
        conditions.append("is_escalated = 1")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df


# ================================================================
# Individual Support Plans (個別支援計画)
# ================================================================

def add_support_plan(client_id, office_id, plan_date, review_date,
                     long_term_goal, short_term_goal, support_content,
                     staff_id, staff_name, status='作成中'):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO individual_support_plans
                 (client_id, office_id, plan_date, review_date,
                  long_term_goal, short_term_goal, support_content,
                  staff_id, staff_name, status)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
              (client_id, office_id, plan_date, review_date,
               long_term_goal, short_term_goal, support_content,
               staff_id, staff_name, status))
    conn.commit()
    conn.close()

def get_support_plans(client_id=None, office_id=None, status=None):
    conn = get_connection()
    query = """SELECT sp.*, c.name as client_name
               FROM individual_support_plans sp
               JOIN clients c ON sp.client_id = c.id WHERE 1=1"""
    params = []
    if client_id:
        query += " AND sp.client_id = %s"
        params.append(client_id)
    if office_id:
        query += " AND sp.office_id = %s"
        params.append(office_id)
    if status:
        query += " AND sp.status = %s"
        params.append(status)
    query += " ORDER BY sp.plan_date DESC"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def update_support_plan_status(plan_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE individual_support_plans SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
              (status, plan_id))
    conn.commit()
    conn.close()


# ================================================================
# Monitoring Records (モニタリング記録)
# ================================================================

def add_monitoring_record(client_id, plan_id, office_id, monitoring_date,
                          goal_achievement, support_evaluation, client_satisfaction,
                          needs_plan_change, change_reason, next_monitoring_date,
                          staff_id, staff_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO monitoring_records
                 (client_id, plan_id, office_id, monitoring_date,
                  goal_achievement, support_evaluation, client_satisfaction,
                  needs_plan_change, change_reason, next_monitoring_date,
                  staff_id, staff_name)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
              (client_id, plan_id, office_id, monitoring_date,
               goal_achievement, support_evaluation, client_satisfaction,
               int(needs_plan_change), change_reason, next_monitoring_date,
               staff_id, staff_name))
    conn.commit()
    conn.close()

def get_monitoring_records(client_id=None, office_id=None):
    conn = get_connection()
    query = """SELECT mr.*, c.name as client_name
               FROM monitoring_records mr
               JOIN clients c ON mr.client_id = c.id WHERE 1=1"""
    params = []
    if client_id:
        query += " AND mr.client_id = %s"
        params.append(client_id)
    if office_id:
        query += " AND mr.office_id = %s"
        params.append(office_id)
    query += " ORDER BY mr.monitoring_date DESC"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df


# ================================================================
# Assessment Records (アセスメント記録)
# ================================================================

def add_assessment_record(client_id, office_id, assessment_date, assessment_type,
                          living_situation, health_condition, disability_characteristics,
                          work_experience, strengths, challenges, support_needs,
                          employment_goal, staff_id, staff_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO assessment_records
                 (client_id, office_id, assessment_date, assessment_type,
                  living_situation, health_condition, disability_characteristics,
                  work_experience, strengths, challenges, support_needs,
                  employment_goal, staff_id, staff_name)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
              (client_id, office_id, assessment_date, assessment_type,
               living_situation, health_condition, disability_characteristics,
               work_experience, strengths, challenges, support_needs,
               employment_goal, staff_id, staff_name))
    conn.commit()
    conn.close()

def get_assessment_records(client_id=None, office_id=None):
    conn = get_connection()
    query = """SELECT ar.*, c.name as client_name
               FROM assessment_records ar
               JOIN clients c ON ar.client_id = c.id WHERE 1=1"""
    params = []
    if client_id:
        query += " AND ar.client_id = %s"
        params.append(client_id)
    if office_id:
        query += " AND ar.office_id = %s"
        params.append(office_id)
    query += " ORDER BY ar.assessment_date DESC"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df


# ================================================================
# Deduction Items (減算項目管理)
# ================================================================

def add_deduction_item(client_id, office_id, year, month, deduction_type,
                       deduction_reason, deduction_units, staff_id, notes=''):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO deduction_items
                 (client_id, office_id, year, month, deduction_type,
                  deduction_reason, deduction_units, staff_id, notes)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
              (client_id, office_id, year, month, deduction_type,
               deduction_reason, deduction_units, staff_id, notes))
    conn.commit()
    conn.close()

def get_deduction_items(office_id=None, year=None, month=None):
    conn = get_connection()
    query = """SELECT di.*, c.name as client_name
               FROM deduction_items di
               LEFT JOIN clients c ON di.client_id = c.id WHERE 1=1"""
    params = []
    if office_id:
        query += " AND di.office_id = %s"
        params.append(office_id)
    if year:
        query += " AND di.year = %s"
        params.append(year)
    if month:
        query += " AND di.month = %s"
        params.append(month)
    query += " ORDER BY di.created_at DESC"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df


# ================================================================
# Emergency Contacts (緊急連絡先)
# ================================================================

def add_emergency_contact(person_type, person_id, person_name, relationship,
                          phone_primary, phone_secondary='', email='',
                          address='', notes='', office_id=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO emergency_contacts
                 (person_type, person_id, person_name, relationship,
                  phone_primary, phone_secondary, email, address, notes, office_id)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
              (person_type, person_id, person_name, relationship,
               phone_primary, phone_secondary, email, address, notes, office_id))
    conn.commit()
    conn.close()

def get_emergency_contacts(person_type=None, office_id=None):
    conn = get_connection()
    query = "SELECT * FROM emergency_contacts WHERE 1=1"
    params = []
    if person_type:
        query += " AND person_type = %s"
        params.append(person_type)
    if office_id:
        query += " AND office_id = %s"
        params.append(office_id)
    query += " ORDER BY person_type, person_name"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def update_emergency_contact(contact_id, **kwargs):
    conn = get_connection()
    c = conn.cursor()
    set_clauses = []
    params = []
    for key, val in kwargs.items():
        set_clauses.append(f"{key} = %s")
        params.append(val)
    params.append(contact_id)
    c.execute(f"UPDATE emergency_contacts SET {', '.join(set_clauses)} WHERE id = %s", params)
    conn.commit()
    conn.close()

def delete_emergency_contact(contact_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM emergency_contacts WHERE id = %s", (contact_id,))
    conn.commit()
    conn.close()


# ================================================================
# Office Financials (事業所別 P&L)
# ================================================================

def get_office_financials(year=None, month=None, office_name=None):
    conn = get_connection()
    query = "SELECT * FROM office_financials WHERE 1=1"
    params = []
    if year:
        query += " AND year = %s"
        params.append(year)
    if month:
        query += " AND month = %s"
        params.append(month)
    if office_name:
        query += " AND office_name = %s"
        params.append(office_name)
    query += " ORDER BY office_name, year, month"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def add_office_financial(office_name, year, month, revenue, revenue_target, sga, sga_target,
                          profit, profit_target, new_users, new_users_target):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO office_financials 
        (office_name, year, month, revenue, revenue_target, sga, sga_target, profit, profit_target, new_users, new_users_target)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (office_name, year, month, revenue, revenue_target, sga, sga_target, profit, profit_target, new_users, new_users_target))
    conn.commit()
    conn.close()


# ================================================================
# Threads (SNS投稿・コメント・いいね)
# ================================================================

def get_thread_posts(office_id=None, limit=50):
    conn = get_connection()
    query = "SELECT * FROM thread_posts WHERE 1=1"
    params = []
    if office_id:
        query += " AND office_id = %s"
        params.append(office_id)
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def add_thread_post(office_id, author_id, author_name, content, image_path=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO thread_posts (office_id, author_id, author_name, content, image_path)
        VALUES (%s, %s, %s, %s, %s) RETURNING id""", (office_id, author_id, author_name, content, image_path))
    post_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return post_id

def get_thread_comments(post_id):
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM thread_comments WHERE post_id = %s ORDER BY created_at ASC",
                      conn, params=[post_id])
    conn.close()
    return df

def add_thread_comment(post_id, author_id, author_name, content):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO thread_comments (post_id, author_id, author_name, content)
        VALUES (%s, %s, %s, %s)""", (post_id, author_id, author_name, content))
    conn.commit()
    conn.close()

def toggle_thread_like(post_id, user_id, user_name):
    conn = get_connection()
    c = conn.cursor()
    # Check if already liked
    c.execute("SELECT id FROM thread_likes WHERE post_id = %s AND user_id = %s", (post_id, user_id))
    existing = c.fetchone()
    if existing:
        c.execute("DELETE FROM thread_likes WHERE id = %s", (existing[0],))
        c.execute("UPDATE thread_posts SET likes_count = likes_count - 1 WHERE id = %s", (post_id,))
        liked = False
    else:
        c.execute("INSERT INTO thread_likes (post_id, user_id, user_name) VALUES (%s, %s, %s)",
                  (post_id, user_id, user_name))
        c.execute("UPDATE thread_posts SET likes_count = likes_count + 1 WHERE id = %s", (post_id,))
        liked = True
    conn.commit()
    conn.close()
    return liked

def get_thread_likes(post_id):
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM thread_likes WHERE post_id = %s", conn, params=[post_id])
    conn.close()
    return df
