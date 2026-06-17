from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_LINK_LAB_IPD_ADMIT = """
SELECT
    ADMMASTER.HN,
    ADMMASTER.AN,
    CONVERT(varchar, ADMMASTER.ADMDATETIME, 120) AS ADMDATETIME,
    CONVERT(varchar, ADMMASTER.DISCHARGEDATETIME, 120) AS DISCHARGEDATETIME
FROM ADMMASTER
JOIN IpdDiag
    ON ADMMASTER.AN = IpdDiag.AN
WHERE (
        IpdDiag.icd10 IN (
            'Z014', 'Z124', 'R87', 'N87', 'D06', 'Z121',
            'K635', 'K573', 'K51', 'Z123', 'Z016', 'N63'
        )
        OR IpdDiag.icd10 LIKE 'C%'
      )
  AND CONVERT(date, ADMMASTER.DISCHARGEDATETIME) = ?
GROUP BY ADMMASTER.HN,
         ADMMASTER.AN,
         ADMMASTER.ADMDATETIME,
         ADMMASTER.DISCHARGEDATETIME
"""


SQL_CANCER_LINK_LAB_IPD_DETAIL = """
SELECT
    ICD10TM AS LabCode,
    main.LabName,
    main.result,
    main.ITMUN
FROM dbo.GetLabResult(?, ?, ?) AS main
JOIN MOPH.dbo.Ref_LabICD10TM lab
    ON main.labcode = lab.labcode
WHERE edmst = 3
GROUP BY
    ICD10TM,
    main.LabName,
    main.result,
    main.ITMUN
"""


def parse_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return date.today() - timedelta(days=1)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_payload(admit: dict[str, Any], lab: dict[str, Any]) -> dict[str, Any]:
    return {
        "hospcode": "10661",
        "hn": clean(admit.get("HN")),
        "an": clean(admit.get("AN")),
        "lab_code": clean(lab.get("LabCode")),
        "lab_name": clean(lab.get("LabName")),
        "lab_result": clean(lab.get("result")),
        "lab_unit": clean(lab.get("ITMUN")),
    }


def fetch_admits(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_CANCER_LINK_LAB_IPD_ADMIT, target_date.isoformat())
        return fetch_dicts(cursor)


def fetch_labs(hn: Any, admit_datetime: Any, discharge_datetime: Any) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            SQL_CANCER_LINK_LAB_IPD_DETAIL,
            clean(hn),
            clean(admit_datetime),
            clean(discharge_datetime),
        )
        return fetch_dicts(cursor)


def insert_log(hn: Any, success: Any, message: Any) -> None:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Saraburi.dbo.API_log_cancerlink
                (HN, makedate, success, message, headersname)
            VALUES (?, GETDATE(), ?, ?, 'lab_ipd')
            """,
            hn,
            str(success),
            str(message),
        )
        conn.commit()


def is_success(result_ok: bool, success: Any) -> bool:
    return result_ok and str(success).lower() in ("true", "1", "y", "success")


def build_admit_payload(admit: dict[str, Any]) -> list[dict[str, Any]]:
    labs = fetch_labs(
        admit.get("HN"),
        admit.get("ADMDATETIME"),
        admit.get("DISCHARGEDATETIME"),
    )
    return [build_payload(admit, lab) for lab in labs]


def run(target_date: date) -> tuple[int, int, int]:
    admits = fetch_admits(target_date)
    client = MophApiClient()

    sent_count = 0
    success_count = 0
    fail_count = 0

    for admit in admits:
        payload = build_admit_payload(admit)

        if not payload:
            continue

        result = client.send_cancer_link_lab_ipd(payload)

        data = result.data if isinstance(result.data, dict) else {}
        success = data.get("success", result.ok)
        message = data.get("message", result.text)

        insert_log(admit.get("HN"), success, message)
        sent_count += 1

        if is_success(result.ok, success):
            success_count += 1
        else:
            fail_count += 1
            print(
                "CANCER_LINK_LAB_IPD FAIL",
                admit.get("AN"),
                result.status_code,
                result.text[:500],
            )

    return sent_count, success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Link Lab IPD")
    parser.add_argument("--date", help="วันที่ discharge รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    admits = fetch_admits(target_date)

    if args.dry_run:
        sent_count = 0
        lab_row_count = 0

        print(f"CANCER_LINK_LAB_IPD วันที่ {target_date} พบ admission {len(admits)} รายการ")

        for admit in admits:
            payload = build_admit_payload(admit)

            if not payload:
                continue

            sent_count += 1
            lab_row_count += len(payload)

            print("=" * 80)
            print(f"รายการที่ {sent_count} AN: {admit.get('AN')} HN: {admit.get('HN')}")
            print(json.dumps(payload, ensure_ascii=False, indent=2))

        print(
            f"CANCER_LINK_LAB_IPD วันที่ {target_date} "
            f"ส่งได้ {sent_count} admission / {lab_row_count} lab rows"
        )
        return

    total, success_count, fail_count = run(target_date)
    print(
        f"CANCER_LINK_LAB_IPD วันที่ {target_date} "
        f"ทั้งหมด {total} admission สำเร็จ {success_count} ไม่สำเร็จ {fail_count}"
    )


if __name__ == "__main__":
    main()