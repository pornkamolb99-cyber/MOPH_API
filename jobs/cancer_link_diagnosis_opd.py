from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_LINK_DIAGNOSIS_OPD = """
SELECT
    VNMST.HN,
    RIGHT('00000' + CAST(VNMST.VN AS VARCHAR), 5) +
    FORMAT(VNMST.VISITDATE, 'ddMMyyyy') +
    RIGHT('00' + CAST(VNDIAG.SUFFIX AS VARCHAR), 2) AS barcode,
    VNMST.VN,
    VNDIAG.ICDCODE AS icd10,
    CASE
        WHEN VNDIAG.TYPEOFTHISDIAG = '1' THEN '1'
        WHEN VNDIAG.TYPEOFTHISDIAG = '2' THEN '3'
        WHEN VNDIAG.TYPEOFTHISDIAG = '3' THEN '4'
        WHEN VNDIAG.TYPEOFTHISDIAG = '4' THEN '2'
        ELSE NULL
    END AS diag_type
FROM VNMST
JOIN VNDIAG
    ON VNMST.VN = VNDIAG.VN
   AND VNMST.VISITDATE = VNDIAG.VISITDATE
WHERE (
        VNDIAG.ICDCODE IN (
            'Z014', 'Z124', 'R87', 'N87', 'D06', 'Z121',
            'K635', 'K573', 'K51', 'Z123', 'Z016', 'N63'
        )
        OR VNDIAG.ICDCODE LIKE 'C%'
      )
  AND CONVERT(date, VNMST.VISITDATE) = ?
GROUP BY VNMST.HN,
         VNMST.VN,
         VNMST.VISITDATE,
         VNDIAG.SUFFIX,
         VNDIAG.TYPEOFTHISDIAG,
         VNDIAG.ICDCODE
"""


def parse_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return date.today() - timedelta(days=1)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "hospcode": "10661",
        "hn": clean(row.get("HN")),
        "vn": clean(row.get("barcode")),
        "icd10": clean(row.get("icd10")),
        "diag_type": clean(row.get("diag_type")),
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_CANCER_LINK_DIAGNOSIS_OPD, target_date.isoformat())
        return fetch_dicts(cursor)


def group_by_hn(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    patient_group: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        hn = clean(row.get("HN"))

        if hn not in patient_group:
            patient_group[hn] = []

        patient_group[hn].append(build_payload(row))

    return patient_group


def insert_log(hn: Any, success: Any, message: Any) -> None:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Saraburi.dbo.API_log_cancerlink
                (HN, makedate, success, message, headersname)
            VALUES (?, GETDATE(), ?, ?, 'diagnosis_opd')
            """,
            hn,
            str(success),
            str(message),
        )
        conn.commit()


def is_success(result_ok: bool, success: Any) -> bool:
    return result_ok and str(success).lower() in ("true", "1", "y", "success")


def run(target_date: date) -> tuple[int, int, int]:
    rows = fetch_rows(target_date)
    patient_group = group_by_hn(rows)
    client = MophApiClient()

    success_count = 0
    fail_count = 0

    for hn, payload in patient_group.items():
        result = client.send_cancer_link_diagnosis_opd(payload)

        data = result.data if isinstance(result.data, dict) else {}
        success = data.get("success", result.ok)
        message = data.get("message", result.text)

        insert_log(hn, success, message)

        if is_success(result.ok, success):
            success_count += 1
        else:
            fail_count += 1
            print(
                "CANCER_LINK_DIAGNOSIS_OPD FAIL",
                hn,
                result.status_code,
                result.text[:500],
            )

    return len(patient_group), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Link Diagnosis OPD")
    parser.add_argument("--date", help="วันที่ visit รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)
    patient_group = group_by_hn(rows)

    if args.dry_run:
        print(f"CANCER_LINK_DIAGNOSIS_OPD วันที่ {target_date} พบข้อมูล {len(patient_group)} HN / {len(rows)} รายการ")
        for i, (hn, payload) in enumerate(patient_group.items(), start=1):
            print("=" * 80)
            print(f"รายการที่ {i} HN: {hn}")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    total, success_count, fail_count = run(target_date)
    print(
        f"CANCER_LINK_DIAGNOSIS_OPD วันที่ {target_date} "
        f"ทั้งหมด {total} HN สำเร็จ {success_count} ไม่สำเร็จ {fail_count}"
    )


if __name__ == "__main__":
    main()