# -*- coding: utf-8 -*-
"""
テスト用ダミーCSVデータ生成スクリプト
実績記録票（jissekikiroku.csv）のサンプルを生成する。
"""

import csv
import io
import random
import os
from datetime import datetime


def generate_dummy_jisseki(year: int = 2026, month: int = 1,
                           num_users: int = 5,
                           office_id: str = "1415001708",
                           city_code: str = "131113") -> str:
    """
    J611フォーマットのダミー実績CSVを生成する。

    Parameters:
        year: 対象年
        month: 対象月
        num_users: 利用者数
        office_id: 事業所番号
        city_code: 市町村番号

    Returns:
        CSV文字列
    """
    output = io.StringIO()
    writer = csv.writer(output)

    year_month = f"{year}{month:02d}"

    # ダミー利用者の受給者証番号
    user_ids = [f"{3000006500 + i:010d}" for i in range(num_users)]

    # サービスコード（就労移行 or 就労定着）
    service_codes = ["1601"] * num_users  # 全員就労移行

    # ヘッダー行（レコード種別 = 1）
    header_row = [
        1,                  # No
        1,                  # RecordType (ヘッダー)
        0,                  # ServiceKind
        235,                # Seq
        "J61",              # 様式番号
        0,                  #
        office_id,          # 事業所番号
        0,                  #
        1,                  #
        year_month,         # 提供年月
    ]
    writer.writerow(header_row)

    record_no = 2
    for idx, user_id in enumerate(user_ids):
        # ランダムな利用日パターン（月15~22日利用）
        num_days = random.randint(15, 22)
        # 平日を中心に利用日を設定（1~28日の範囲）
        possible_days = list(range(1, 29))
        used_days = sorted(random.sample(possible_days, min(num_days, len(possible_days))))

        # Day1~Day31 フラグ
        daily_flags = [0] * 31
        for d in used_days:
            daily_flags[d - 1] = 1

        # 基本単位数
        base_units = 1020  # 就労移行支援(I)

        # J611レコード
        row = [
            record_no,          # No (レコード番号)
            "J611",             # RecordType
            2,                  # ServiceKind (就労移行)
            year_month,         # 提供年月
            city_code,          # 市町村番号
            office_id,          # 事業所番号
            user_id,            # 受給者証番号
            service_codes[idx], # サービスコード
            "",                 # 空
        ]
        row.extend(daily_flags)     # Day1~Day31

        # 後続フィールド
        total_days = sum(daily_flags)
        total_units = base_units * total_days
        row.extend([
            total_units,        # 合計単位数
            "",                 # 備考
        ])

        writer.writerow(row)
        record_no += 1

    # フッター行
    footer_row = [
        record_no,
        9,                  # RecordType (フッター)
        "",
        year_month,
        num_users,          # 件数
    ]
    writer.writerow(footer_row)

    return output.getvalue()


def generate_dummy_jisseki_per_day(year: int = 2026, month: int = 1,
                                   num_users: int = 5,
                                   office_id: str = "1415001708",
                                   city_code: str = "131113") -> str:
    """
    ユーザーのサンプルと同じ形式：
    1利用者×1利用日 = 1行 のJ611 CSVを生成する。
    """
    output = io.StringIO()
    writer = csv.writer(output)

    year_month = f"{year}{month:02d}"
    user_ids = [f"{3000006500 + i:010d}" for i in range(num_users)]

    record_no = 1
    base_units = 1020
    unit_price = 10.94  # 2級地

    for user_id in user_ids:
        # ランダムな利用日
        num_days = random.randint(15, 22)
        used_days = sorted(random.sample(range(1, 29), min(num_days, 28)))

        for day in used_days:
            import math
            cost = math.floor(base_units * unit_price)

            row = [
                record_no,          # レコード番号
                "J611",             # レコード種別
                2,                  # サービス種類コード
                year_month,         # 提供年月
                city_code,          # 市町村番号
                office_id,          # 事業所番号
                user_id,            # 受給者証番号
                "1601",             # サービスコード
                "",                 # 空
                day,                # 日
                "", "", "",         # 空
                base_units,         # 単位数
                cost,               # 算定額
                "", "", "", "", "", # 空
                0,                  # 未使用
                0,                  # 未使用
            ]
            writer.writerow(row)
            record_no += 1

    return output.getvalue()


def save_dummy_files(output_dir: str = "./test_data"):
    """テスト用ファイルを生成して保存"""
    os.makedirs(output_dir, exist_ok=True)

    # パターン1: 月次集計型
    csv1 = generate_dummy_jisseki(year=2026, month=1, num_users=5)
    path1 = os.path.join(output_dir, "jissekikiroku_monthly.csv")
    with open(path1, "w", encoding="utf-8") as f:
        f.write(csv1)
    print(f"✅ 生成: {path1}")

    # パターン2: 日次型（ユーザーのサンプル形式）
    csv2 = generate_dummy_jisseki_per_day(year=2026, month=1, num_users=3)
    path2 = os.path.join(output_dir, "jissekikiroku_daily.csv")
    with open(path2, "w", encoding="utf-8") as f:
        f.write(csv2)
    print(f"✅ 生成: {path2}")

    # パターン3: エラーを含むデータ
    csv3 = generate_dummy_with_errors()
    path3 = os.path.join(output_dir, "jissekikiroku_errors.csv")
    with open(path3, "w", encoding="utf-8") as f:
        f.write(csv3)
    print(f"✅ 生成: {path3} (バリデーションエラー含む)")


def generate_dummy_with_errors() -> str:
    """バリデーションエラーを含むダミーデータ"""
    output = io.StringIO()
    writer = csv.writer(output)

    # 正常レコード
    writer.writerow([
        1, "J611", 2, "202601", "131113", "1415001708",
        "3000006522", "1601", "", 5, "", "", "", 1020, 11338,
        "", "", "", "", "", 0, 0,
    ])

    # エラー: 受給者証番号が短い（8桁）
    writer.writerow([
        2, "J611", 2, "202601", "131113", "1415001708",
        "30000065", "1601", "", 6, "", "", "", 1020, 11338,
        "", "", "", "", "", 0, 0,
    ])

    # エラー: 市町村番号が空
    writer.writerow([
        3, "J611", 2, "202601", "", "1415001708",
        "3000006523", "1601", "", 7, "", "", "", 1020, 0,
        "", "", "", "", "", 0, 0,
    ])

    # 警告: 利用日数0日
    writer.writerow([
        4, "J611", 2, "202601", "131113", "1415001708",
        "3000006524", "1601", "", 0, "", "", "", 0, 0,
        "", "", "", "", "", 0, 0,
    ])

    return output.getvalue()


if __name__ == "__main__":
    save_dummy_files()
    print("\n全てのダミーデータを生成しました。")
