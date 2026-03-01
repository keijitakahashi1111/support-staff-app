# -*- coding: utf-8 -*-
"""
国保連請求CSV生成ツール — メインスクリプト
就労移行支援・就労定着支援の実績記録票CSVから、
様式第一（請求書鑑）・様式第二（明細書）を生成する。
"""

import csv
import io
import math
import os
import sys
import logging
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

# 同パッケージからインポート
from . import config

logger = logging.getLogger(__name__)


# ====================================================================
# 1. データ読み込み
# ====================================================================

class ServiceRecord:
    """1利用者×1ヶ月分の実績レコード"""
    def __init__(self):
        self.record_type = ""       # J611 等
        self.service_kind = ""      # 1601(移行), 2201(定着)
        self.year_month = ""        # 202601
        self.city_code = ""         # 131113
        self.office_id = ""         # 1415001708
        self.user_id = ""           # 受給者証番号
        self.service_code = ""      # 432025 等
        self.daily_flags: List[int] = [0] * 31  # Day1~Day31
        self.days_used = 0          # 利用日数（計算後）
        # 加算レコード
        self.addition_records: List['ServiceRecord'] = []


def parse_jisseki_csv(csv_content: str) -> List[ServiceRecord]:
    """
    実績記録票CSVを解析してServiceRecordのリストを返す。

    想定フォーマット:
    No, RecordType, ServiceKind(Seq), ..., YearMonth, CityCode, OfficeID, UserID, ServiceCode, Day1..Day31

    実際のJ611レコードのカラム配置:
    Index 0: No (レコード番号)
    Index 1: RecordType (J611)
    Index 2: ServiceKind or Sequence
    Index 3: YearMonth (202601)
    Index 4: CityCode (131113)
    Index 5: OfficeID (1415001708)
    Index 6: UserID (受給者証番号)
    Index 7: ServiceCode (1601, 2201)
    Index 8: (空)
    Index 9~39: Day1~Day31
    以降: 単位数, 算定額 等
    """
    records = []
    reader = csv.reader(io.StringIO(csv_content))

    for row in reader:
        if len(row) < 10:
            continue

        # ヘッダー行・集計行をスキップ
        record_type = row[1].strip() if len(row) > 1 else ""
        if record_type != "J611":
            continue

        rec = ServiceRecord()
        rec.record_type = record_type
        rec.service_kind = row[7].strip() if len(row) > 7 else ""
        rec.year_month = row[3].strip() if len(row) > 3 else ""
        rec.city_code = row[4].strip() if len(row) > 4 else ""
        rec.office_id = row[5].strip() if len(row) > 5 else ""
        rec.user_id = row[6].strip() if len(row) > 6 else ""
        rec.service_code = row[7].strip() if len(row) > 7 else ""

        # Day flags (Index 9 ~ 39)
        daily_flags = []
        for i in range(9, min(40, len(row))):
            try:
                val = int(row[i].strip()) if row[i].strip() else 0
                daily_flags.append(1 if val > 0 else 0)
            except ValueError:
                daily_flags.append(0)

        # 31日分にパディング
        while len(daily_flags) < 31:
            daily_flags.append(0)

        rec.daily_flags = daily_flags[:31]
        rec.days_used = sum(rec.daily_flags)

        records.append(rec)

    return records


def parse_jisseki_from_db(records_df, year: int, month: int,
                          office_id: str = None) -> List[ServiceRecord]:
    """
    既存のDB(client_daily_records)からServiceRecordリストを構築する。
    Streamlit統合用。
    """
    from collections import defaultdict
    import calendar

    if office_id is None:
        office_id = config.OFFICE_INFO["office_id"]

    year_month = f"{year}{month:02d}"
    _, max_day = calendar.monthrange(year, month)

    # 利用者ごとにグループ化
    user_records = defaultdict(lambda: {
        "daily_flags": [0] * 31,
        "city_code": "",
        "user_id": "",
        "service_kind": "1601",
    })

    for _, row in records_df.iterrows():
        cid = row.get("client_id", "")
        user_id = row.get("recipient_number", "")
        city_code = row.get("municipality_code", "")
        record_date = str(row.get("record_date", ""))
        service_type = row.get("service_type", "通所")

        if not record_date:
            continue

        # 日付から日を取得
        try:
            day = int(record_date.split("-")[2])
        except (IndexError, ValueError):
            continue

        key = user_id or str(cid)
        user_records[key]["user_id"] = user_id
        user_records[key]["city_code"] = city_code
        if service_type == "通所" and 1 <= day <= 31:
            user_records[key]["daily_flags"][day - 1] = 1

    # ServiceRecordに変換
    result = []
    for key, data in user_records.items():
        rec = ServiceRecord()
        rec.record_type = "J611"
        rec.service_kind = data["service_kind"]
        rec.year_month = year_month
        rec.city_code = data["city_code"]
        rec.office_id = office_id
        rec.user_id = data["user_id"]
        rec.service_code = config.OFFICE_INFO.get("base_service_code", "432025")
        rec.daily_flags = data["daily_flags"]
        rec.days_used = sum(data["daily_flags"])
        result.append(rec)

    return result


# ====================================================================
# 2. バリデーション
# ====================================================================

class ValidationResult:
    def __init__(self):
        self.errors: List[str] = []    # 🔴 ダウンロード不可
        self.warnings: List[str] = []  # ⚠️ 要確認

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def is_valid(self) -> bool:
        return not self.has_errors

    def add_error(self, msg: str):
        self.errors.append(f"🔴 {msg}")

    def add_warning(self, msg: str):
        self.warnings.append(f"⚠️ {msg}")


def validate_records(records: List[ServiceRecord],
                     copay_limits: Dict[str, int] = None) -> ValidationResult:
    """提出前バリデーション"""
    result = ValidationResult()

    if not records:
        result.add_error("実績データが0件です。")
        return result

    for i, rec in enumerate(records):
        prefix = f"利用者 {rec.user_id or f'(行{i+1})'}"

        # --- 受給者証番号チェック ---
        if not rec.user_id:
            result.add_error(f"{prefix}: 受給者証番号が未入力です。")
        elif len(rec.user_id) != 10:
            result.add_error(
                f"{prefix}: 受給者証番号は10桁必要です（現在{len(rec.user_id)}桁: {rec.user_id}）")
        elif not rec.user_id.isdigit():
            result.add_error(f"{prefix}: 受給者証番号に数字以外が含まれています: {rec.user_id}")

        # --- 事業所番号チェック ---
        if not rec.office_id:
            result.add_error(f"{prefix}: 事業所番号が未設定です。")
        elif len(rec.office_id) != 10:
            result.add_error(
                f"{prefix}: 事業所番号は10桁必要です（現在{len(rec.office_id)}桁）")

        # --- 市町村番号チェック ---
        if not rec.city_code:
            result.add_error(f"{prefix}: 市町村番号が未設定です。")
        elif len(rec.city_code) != 6:
            result.add_error(
                f"{prefix}: 市町村番号は6桁必要です（現在{len(rec.city_code)}桁: {rec.city_code}）")

        # --- サービスコードチェック ---
        if rec.service_code not in config.SERVICE_KIND_MAP:
            # service_codeがサービス種類コードかもしれない
            pass

        # --- 地域単価チェック ---
        grade = config.get_grade(rec.city_code)
        if grade == config.DEFAULT_GRADE:
            result.add_warning(
                f"{prefix}: 市町村番号 {rec.city_code} の級地が未登録です。"
                f"デフォルト単価（{config.DEFAULT_GRADE}）を使用します。")

        # --- 利用日数チェック ---
        if rec.days_used == 0:
            result.add_warning(
                f"{prefix}: 当月の利用日数が0日です。請求対象外か確認してください。")
        elif rec.days_used > 23:
            result.add_warning(
                f"{prefix}: 利用日数が{rec.days_used}日あります（通常は22日以下）。確認してください。")

        # --- 提供年月チェック ---
        if not rec.year_month or len(rec.year_month) != 6:
            result.add_error(f"{prefix}: 提供年月の形式が不正です: {rec.year_month}")

    # --- 重複チェック ---
    user_ids = [r.user_id for r in records if r.user_id]
    duplicates = [uid for uid in set(user_ids) if user_ids.count(uid) > 1]
    if duplicates:
        result.add_warning(
            f"複数レコードが存在する受給者証番号: {', '.join(duplicates)}（加算等の場合は正常）")

    return result


# ====================================================================
# 3. 計算ロジック
# ====================================================================

class BillingItem:
    """1利用者分の請求計算結果"""
    def __init__(self):
        self.user_id = ""
        self.city_code = ""
        self.office_id = ""
        self.service_kind = ""
        self.year_month = ""
        self.daily_flags: List[int] = []
        self.days_used = 0

        # 計算結果
        self.base_code = ""
        self.base_units_per_day = 0
        self.daily_addition_units = 0   # 日次加算の合計単位/日
        self.base_total_units = 0       # 基本単位 × 日数
        self.addition_total_units = 0   # 日次加算 × 日数
        self.subtotal_units = 0         # 小計単位数（日別合計）
        self.monthly_addition_units = 0 # 月次加算単位数
        self.final_units = 0            # 最終合計単位数
        self.unit_price = 0.0           # 1単位あたりの単価
        self.total_cost = 0             # 総費用額 (truncate)
        self.billing_amount = 0         # 給付費請求額
        self.user_copay = 0             # 利用者負担額
        self.copay_limit = 0            # 上限月額

        # 内訳
        self.detail_lines: List[Dict] = []  # サービスコード別の内訳


def calculate_billing(records: List[ServiceRecord],
                      copay_limits: Dict[str, int] = None,
                      addition_codes: List[str] = None) -> List[BillingItem]:
    """
    実績レコードから請求額を計算する。

    計算順序:
    1. 基本単位 × 利用日数
    2. 日次加算 × 利用日数
    3. 月次加算 = truncate(小計 × 加算率)
    4. 総費用額 = truncate(合計単位数 × 地域単価)
    5. 利用者負担額 = min(truncate(総費用額 × 0.1), 上限月額)
    6. 給付費請求額 = 総費用額 - 利用者負担額
    """
    if copay_limits is None:
        copay_limits = {}

    if addition_codes is None:
        addition_codes = []

    # 利用者ごとにグループ化（同一user_idのレコードをまとめる）
    user_groups = defaultdict(list)
    for rec in records:
        user_groups[rec.user_id].append(rec)

    billing_items = []

    for user_id, user_records in user_groups.items():
        # 最初のレコードから基本情報を取得
        primary = user_records[0]

        item = BillingItem()
        item.user_id = user_id
        item.city_code = primary.city_code
        item.office_id = primary.office_id
        item.service_kind = primary.service_code  # 1601 or 2201
        item.year_month = primary.year_month
        item.daily_flags = primary.daily_flags
        item.days_used = primary.days_used

        # --- Step 1: 基本サービスコードの特定 ---
        base_code = config.OFFICE_INFO.get("base_service_code", "432025")
        base_info = config.get_service_code_info(base_code)
        item.base_code = base_code
        item.base_units_per_day = base_info["units"]

        # サービス種類による単価取得
        service_kind_code = base_info.get("service_kind", "1601")
        kind_info = config.SERVICE_KIND_MAP.get(service_kind_code, {})
        service_type_name = kind_info.get("price_key", "就労移行支援")

        # --- Step 2: 基本報酬 ---
        if base_info["calc_type"] == "daily":
            item.base_total_units = item.base_units_per_day * item.days_used
        elif base_info["calc_type"] == "monthly":
            item.base_total_units = item.base_units_per_day  # 月額

        # 明細行追加(基本)
        item.detail_lines.append({
            "code": base_code,
            "name": base_info["name"],
            "units": item.base_units_per_day,
            "count": item.days_used if base_info["calc_type"] == "daily" else 1,
            "total_units": item.base_total_units,
        })

        # --- Step 3: 日次加算 ---
        daily_addition_total = 0
        for add_code in addition_codes:
            add_info = config.get_service_code_info(add_code)
            if add_info["calc_type"] == "daily":
                add_units = add_info["units"] * item.days_used
                daily_addition_total += add_units
                item.detail_lines.append({
                    "code": add_code,
                    "name": add_info["name"],
                    "units": add_info["units"],
                    "count": item.days_used,
                    "total_units": add_units,
                })

        item.addition_total_units = daily_addition_total
        item.subtotal_units = item.base_total_units + daily_addition_total

        # --- Step 4: 月次加算（処遇改善等） ---
        monthly_addition = 0
        for add_code in addition_codes:
            add_info = config.get_service_code_info(add_code)
            if add_info["calc_type"] == "monthly_rate":
                rate = add_info.get("rate", 0)
                add_units = config.truncate(item.subtotal_units * rate)
                monthly_addition += add_units
                item.detail_lines.append({
                    "code": add_code,
                    "name": add_info["name"],
                    "units": 0,
                    "count": 1,
                    "total_units": add_units,
                    "rate": rate,
                })

        item.monthly_addition_units = monthly_addition
        item.final_units = item.subtotal_units + monthly_addition

        # --- Step 5: 総費用額 ---
        item.unit_price = config.get_unit_price(item.city_code, service_kind_code)
        item.total_cost = config.truncate(item.final_units * item.unit_price)

        # --- Step 6: 利用者負担額 ---
        item.copay_limit = copay_limits.get(user_id, config.DEFAULT_COPAY_LIMIT)
        raw_copay = config.truncate(item.total_cost * 0.1)
        item.user_copay = min(raw_copay, item.copay_limit)

        # --- Step 7: 給付費請求額 ---
        item.billing_amount = item.total_cost - item.user_copay

        billing_items.append(item)

    return billing_items


# ====================================================================
# 4. CSV出力 — 様式第一（請求書鑑）
# ====================================================================

def generate_yoshiki_1(billing_items: List[BillingItem],
                       year: int, month: int) -> str:
    """
    様式第一（介護給付費・訓練等給付費等請求書）を生成する。
    自治体ごとの集計を行う。
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator=config.OUTPUT_LINE_ENDING)

    # 自治体ごとにグループ化
    city_groups = defaultdict(list)
    for item in billing_items:
        city_groups[item.city_code].append(item)

    for city_code, items in city_groups.items():
        # 集計
        count = len(items)
        total_units = sum(i.final_units for i in items)
        total_cost = sum(i.total_cost for i in items)
        billing_amount = sum(i.billing_amount for i in items)
        user_copay = sum(i.user_copay for i in items)

        office_id = config.OFFICE_INFO["office_id"]
        office_name = config.OFFICE_INFO["office_name"]
        corporation = config.OFFICE_INFO["corporation_name"]
        grade = config.get_grade(city_code)

        # --- 様式第一 ヘッダー ---
        writer.writerow(["", "", "（様式第一）"] + [""] * 25)
        writer.writerow(["", "", "介護給付費・訓練等給付費等請求書"] + [""] * 25)
        writer.writerow([])

        # 事業所情報
        writer.writerow([
            "", "", "", "事業所番号", office_id,
            "", "", "", "", "",
            "サービス種類", "就労移行支援",
        ])
        writer.writerow([
            "", "", "", "事業者名", corporation,
            "", "", "", "", "",
            "事業所名", office_name,
        ])
        writer.writerow([])

        # 請求年月
        writer.writerow([
            "", "", "", "請求年月", "",
            f"令和{year - 2018}年", f"{month}月分",
        ])

        # 市町村番号
        writer.writerow([
            "", "", "", "市町村番号", city_code,
            "", "", "級地区分", grade,
        ])
        writer.writerow([])

        # 請求金額
        writer.writerow([
            "", "", "", "請求金額", "", "", "",
            "", "", "", "", billing_amount,
        ])
        writer.writerow([])

        # 明細ヘッダー
        writer.writerow([
            "", "", "", "区 分", "", "", "", "",
            "", "件数", "単位数", "費用合計", "給付費請求額", "利用者負担額", "自治体助成額",
        ])

        # 訓練等給付費
        writer.writerow([
            "", "", "", "訓練等給付費", "", "", "", "",
            "", count, total_units, total_cost, billing_amount, user_copay, 0,
        ])

        writer.writerow([])
        writer.writerow(["=" * 60])
        writer.writerow([])

    return output.getvalue()


# ====================================================================
# 5. CSV出力 — 様式第二（明細書）
# ====================================================================

def generate_yoshiki_2(billing_items: List[BillingItem],
                       year: int, month: int) -> str:
    """
    様式第二（介護給付費・訓練等給付費等明細書）を生成する。
    利用者ごとの明細書。
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator=config.OUTPUT_LINE_ENDING)

    office_id = config.OFFICE_INFO["office_id"]
    office_name = config.OFFICE_INFO["office_name"]
    corporation = config.OFFICE_INFO["corporation_name"]

    for item in billing_items:
        grade = config.get_grade(item.city_code)

        # --- 様式第二 ヘッダー ---
        writer.writerow(["", "", "（様式第二）"] + [""] * 70)
        writer.writerow([
            "", "介護給付費・訓練等給付費等明細書"] + [""] * 70)
        writer.writerow([])

        # 基本情報
        writer.writerow([
            "", "", "", "市町村番号", item.city_code,
            "", "", "", "", "", "", "", "", "",
            f"令和{year - 2018}年", f"{month}月分",
        ])
        writer.writerow([
            "", "", "", "受給者証番号", item.user_id,
            "", "", "", "",
            "事業者名", "", "", corporation,
        ])
        writer.writerow([
            "", "", "", "事業所番号", office_id,
            "", "", "", "",
            "事業所名", "", "", office_name,
        ])
        writer.writerow([
            "", "", "", "級地区分", grade,
            "", "", "", "",
            "地域単価", f"{item.unit_price:.2f}円/単位",
        ])
        writer.writerow([])

        # --- 給付費明細欄 ---
        writer.writerow([
            "", "", "", "給付費明細欄", "",
            "サービス内容", "", "", "", "", "",
            "", "", "", "", "", "", "", "", "", "",
            "サービスコード", "単位数", "回数", "サービス単位数",
        ])

        for line in item.detail_lines:
            writer.writerow([
                "", "", "", "", "",
                line["name"], "", "", "", "", "",
                "", "", "", "", "", "", "", "", "", "",
                line["code"],
                line["units"],
                line["count"],
                line["total_units"],
            ])

        writer.writerow([])

        # --- 請求額集計欄 ---
        writer.writerow([
            "", "", "", "請求額集計欄", "",
            "給付単位数", "", "", "", "", item.final_units,
        ])
        writer.writerow([
            "", "", "", "", "",
            "総費用額", "", "", "", "", item.total_cost,
        ])
        writer.writerow([
            "", "", "", "", "",
            "利用者負担額", "", "", "", "", item.user_copay,
            "", "上限月額", item.copay_limit,
        ])
        writer.writerow([
            "", "", "", "", "",
            "給付費請求額", "", "", "", "", item.billing_amount,
        ])

        writer.writerow([])
        writer.writerow(["=" * 80])
        writer.writerow([])

    return output.getvalue()


# ====================================================================
# 6. 実績記録票CSV出力（国保連伝送用J611フォーマット）
# ====================================================================

def generate_j611_csv(billing_items: List[BillingItem],
                      year: int, month: int) -> str:
    """
    国保連伝送用のJ611形式（サービス提供実績記録票情報）CSVを生成する。
    ユーザーのサンプルフォーマットに準拠。

    フィールド順:
    レコード番号, レコード種別(J611), サービス種類コード, 提供年月,
    市町村番号, 事業所番号, 受給者証番号, サービスコード, (空),
    日, (空)×3, 単位数, 算定額, (空)×5, 0, 0
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator=config.OUTPUT_LINE_ENDING)

    record_no = 1
    year_month = f"{year}{month:02d}"

    for item in billing_items:
        # 利用した日ごとに1行出力
        for day_idx, flag in enumerate(item.daily_flags):
            if flag == 0:
                continue

            day = day_idx + 1
            units = item.base_units_per_day
            cost = config.truncate(units * item.unit_price)

            row = [
                record_no,          # レコード番号
                "J611",             # レコード種別
                2,                  # サービス種類コード (就労移行)
                year_month,         # 提供年月
                item.city_code,     # 市町村番号
                item.office_id,     # 事業所番号
                item.user_id,       # 受給者証番号
                item.base_code,     # サービスコード
                "",                 # 空
                day,                # 日
                "", "", "",         # 空×3
                units,              # 単位数
                cost,               # 算定額
                "", "", "", "", "", # 空×5
                0,                  # 未使用
                0,                  # 未使用
            ]
            writer.writerow(row)
            record_no += 1

    return output.getvalue()


# ====================================================================
# 7. メイン実行関数
# ====================================================================

def process_billing(csv_content: str = None,
                    records_df=None,
                    year: int = None, month: int = None,
                    addition_codes: List[str] = None,
                    copay_limits: Dict[str, int] = None,
                    office_id: str = None) -> Dict:
    """
    メイン処理: CSV読み込み or DB入力 → バリデーション → 計算 → CSV出力

    Returns:
        {
            "validation": ValidationResult,
            "billing_items": List[BillingItem],
            "yoshiki_1_csv": str,
            "yoshiki_2_csv": str,
            "j611_csv": str,
            "summary": dict,
        }
    """
    # --- 入力データ取得 ---
    if csv_content:
        records = parse_jisseki_csv(csv_content)
    elif records_df is not None and year and month:
        records = parse_jisseki_from_db(records_df, year, month, office_id)
    else:
        raise ValueError("csv_content または records_df + year + month を指定してください")

    # 年月の自動取得
    if year is None or month is None:
        if records:
            ym = records[0].year_month
            year = int(ym[:4])
            month = int(ym[4:6])
        else:
            now = datetime.now()
            year = now.year
            month = now.month

    # --- バリデーション ---
    validation = validate_records(records)

    # --- 計算 ---
    billing_items = calculate_billing(
        records,
        copay_limits=copay_limits or {},
        addition_codes=addition_codes or [],
    )

    # --- CSV生成 ---
    yoshiki_1 = generate_yoshiki_1(billing_items, year, month)
    yoshiki_2 = generate_yoshiki_2(billing_items, year, month)
    j611 = generate_j611_csv(billing_items, year, month)

    # --- サマリー ---
    summary = {
        "year": year,
        "month": month,
        "total_users": len(billing_items),
        "total_units": sum(i.final_units for i in billing_items),
        "total_cost": sum(i.total_cost for i in billing_items),
        "total_billing": sum(i.billing_amount for i in billing_items),
        "total_copay": sum(i.user_copay for i in billing_items),
    }

    return {
        "validation": validation,
        "billing_items": billing_items,
        "yoshiki_1_csv": yoshiki_1,
        "yoshiki_2_csv": yoshiki_2,
        "j611_csv": j611,
        "summary": summary,
    }


# ====================================================================
# CLI実行
# ====================================================================

def main():
    """コマンドライン実行"""
    import argparse

    parser = argparse.ArgumentParser(description="国保連請求CSV生成ツール")
    parser.add_argument("input_csv", help="入力実績CSV(jissekikiroku.csv)")
    parser.add_argument("--output-dir", "-o", default="./output", help="出力ディレクトリ")
    parser.add_argument("--additions", nargs="*", default=[],
                        help="適用する加算コード（スペース区切り）例: 436036 436900")
    args = parser.parse_args()

    # 入力読み込み
    with open(args.input_csv, "r", encoding="utf-8") as f:
        csv_content = f.read()

    # 処理実行
    result = process_billing(
        csv_content=csv_content,
        addition_codes=args.additions,
    )

    # バリデーション結果表示
    validation = result["validation"]
    if validation.errors:
        print("\n=== 🔴 エラー ===")
        for e in validation.errors:
            print(f"  {e}")
    if validation.warnings:
        print("\n=== ⚠️ 警告 ===")
        for w in validation.warnings:
            print(f"  {w}")

    if validation.has_errors:
        print("\n❌ エラーがあるため、CSVは生成されません。エラーを修正してください。")
        sys.exit(1)

    # 出力ディレクトリ作成
    os.makedirs(args.output_dir, exist_ok=True)

    # CSV出力
    summary = result["summary"]
    ym = f"{summary['year']}{summary['month']:02d}"

    files = {
        f"yoshiki1_{ym}.csv": result["yoshiki_1_csv"],
        f"yoshiki2_{ym}.csv": result["yoshiki_2_csv"],
        f"j611_{ym}.csv": result["j611_csv"],
    }

    for fname, content in files.items():
        path = os.path.join(args.output_dir, fname)
        with open(path, "w", encoding=config.OUTPUT_ENCODING, errors="replace") as f:
            f.write(content)
        print(f"✅ 出力: {path}")

    # サマリー表示
    print(f"\n=== 請求サマリー ({ym}) ===")
    print(f"  対象人数:     {summary['total_users']}名")
    print(f"  合計単位数:   {summary['total_units']:,}")
    print(f"  総費用額:     {summary['total_cost']:,}円")
    print(f"  給付費請求額: {summary['total_billing']:,}円")
    print(f"  利用者負担額: {summary['total_copay']:,}円")


if __name__ == "__main__":
    main()
