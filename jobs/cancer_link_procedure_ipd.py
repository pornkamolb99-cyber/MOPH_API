from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_LINK_PROCEDURE_IPD = """
SELECT
    ADMMASTER.HN,
    ADMMASTER.AN,
    ipd.ProcedureCode AS procedure_code
FROM ADMMASTER
JOIN IPDSUMMARY
    ON ADMMASTER.AN = IPDSUMMARY.AN
JOIN IpdDiag
    ON ADMMASTER.AN = IpdDiag.AN
CROSS APPLY (
    VALUES
        (IPDSUMMARY.ProcudureIcdCmCode),
        (IPDSUMMARY.ProcudureIcdCmCode2),
        (IPDSUMMARY.ProcudureIcdCmCode3),
        (IPDSUMMARY.ProcudureIcdCmCode4)
) ipd(ProcedureCode)
WHERE ipd.ProcedureCode IS NOT NULL
  AND (
        IpdDiag.icd10 IN (
            'Z014', 'Z124', 'R87', 'N87', 'D06', 'Z121',
            'K635', 'K573', 'K51', 'Z123', 'Z016', 'N63'
        )
        OR IpdDiag.icd10 LIKE 'C%'
      )
  AND CONVERT(date, ADMMASTER.DISCHARGEDATETIME) = ?
GROUP BY
    ADMMASTER.HN,
    ADMMASTER.AN,
    ipd.ProcedureCode
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
        "an": clean(row.get("AN")),
        "procedure_code": clean(row.get("procedure_code")),
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_CANCER_LINK_PROCEDURE_IPD, target_date.isoformat())
        return fetch_dicts(cursor)


def group_by_an(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    patient_group: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        an = clean(row.get("AN"))

        if an not in patient_group:
            patient_group[an] = []

        patient_group[an].append(build_payload(row))

    return patient_group


def insert_log(hn: Any, success: Any, message: Any) -> None:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Saraburi.dbo.API_log_cancerlink
                (HN, makedate, success, message, headersname)
            VALUES (?, GETDATE(), ?, ?, 'procedure_ipd')
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
    patient_group = group_by_an(rows)
    client = MophApiClient()

    success_count = 0
    fail_count = 0

    for an, payload in patient_group.items():
        result = client.send_cancer_link_procedure_ipd(payload)

        data = result.data if isinstance(result.data, dict) else {}
        success = data.get("success", result.ok)
        message = data.get("message", result.text)

        hn = payload[0].get("hn", "")
        insert_log(hn, success, message)

        if is_success(result.ok, success):
            success_count += 1
        else:
            fail_count += 1
            print(
                "CANCER_LINK_PROCEDURE_IPD FAIL",
                an,
                result.status_code,
                result.text[:500],
            )

    return len(patient_group), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Link Procedure IPD")
    parser.add_argument("--date", help="วันที่ discharge รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)
    patient_group = group_by_an(rows)

    if args.dry_run:
        print(
            f"CANCER_LINK_PROCEDURE_IPD วันที่ {target_date} "
            f"พบข้อมูล {len(patient_group)} AN / {len(rows)} procedure rows"
        )
        for i, (an, payload) in enumerate(patient_group.items(), start=1):
            print("=" * 80)
            print(f"รายการที่ {i} AN: {an} HN: {payload[0].get('hn')}")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    total, success_count, fail_count = run(target_date)
    print(
        f"CANCER_LINK_PROCEDURE_IPD วันที่ {target_date} "
        f"ทั้งหมด {total} AN สำเร็จ {success_count} ไม่สำเร็จ {fail_count}"
    )


if __name__ == "__main__":
    main()