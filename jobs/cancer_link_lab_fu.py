from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_LINK_LAB_FU = """
SELECT
    PATIENT_REF.REF AS cid,
    A.vstdate,
    A.ICD10TM AS labtest,
    A.result AS labresult,
    A.HN
FROM (
    SELECT
        main.HN,
        lab.ICD10TM,
        CONVERT(VARCHAR(10), main.RequestDate, 23) AS vstdate,
        main.result,
        (
            SELECT COUNT(*)
            FROM VNDIAG
            JOIN VNMST
                ON VNDIAG.VN = VNMST.VN
               AND VNDIAG.VISITDATE = VNMST.VISITDATE
            WHERE (
                    VNDIAG.ICDCODE IN (
                        'Z014', 'Z124', 'R87', 'N87', 'D06', 'Z121',
                        'K635', 'K573', 'K51', 'Z123', 'Z016', 'N63'
                    )
                    OR VNDIAG.ICDCODE LIKE 'C%'
                  )
              AND VNDIAG.VISITDATE BETWEEN DATEADD(YEAR, -1, GETDATE()) AND CONVERT(date, GETDATE())
              AND VNMST.HN = main.HN
        ) AS checkC
    FROM SSBDatabase.dbo.GetLabFU(?, ?) AS main
    JOIN VNMST
        ON main.HN = VNMST.HN
       AND main.RequestDate = VNMST.VISITDATE
    JOIN MOPH.dbo.Ref_LabICD10TM lab
        ON main.labcode = lab.labcode
    GROUP BY
        main.HN,
        lab.ICD10TM,
        main.RequestDate,
        main.result
) AS A
JOIN PATIENT_REF
    ON A.HN = PATIENT_REF.HN
   AND PATIENT_REF.REFTYPE = '01'
WHERE A.checkC > 0
ORDER BY PATIENT_REF.REF ASC
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
        "pid": clean(row.get("HN")),
        "cid": clean(row.get("cid")),
        "seq": clean(row.get("cid")),
        "vstdate": clean(row.get("vstdate")),
        "labtest": clean(row.get("labtest")),
        "labresult": clean(row.get("labresult")),
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    date_text = target_date.isoformat()

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_CANCER_LINK_LAB_FU, date_text, date_text)
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
            VALUES (?, GETDATE(), ?, ?, 'lab_fu')
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
        result = client.send_cancer_link_lab_fu(payload)

        data = result.data if isinstance(result.data, dict) else {}
        success = data.get("success", result.ok)
        message = data.get("message", result.text)

        insert_log(hn, success, message)

        if is_success(result.ok, success):
            success_count += 1
        else:
            fail_count += 1
            print(
                "CANCER_LINK_LAB_FU FAIL",
                hn,
                result.status_code,
                result.text[:500],
            )

    return len(patient_group), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Link Lab FU")
    parser.add_argument("--date", help="วันที่ request lab รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)
    patient_group = group_by_hn(rows)

    if args.dry_run:
        print(
            f"CANCER_LINK_LAB_FU วันที่ {target_date} "
            f"พบข้อมูล {len(patient_group)} HN / {len(rows)} lab rows"
        )

        for i, (hn, payload) in enumerate(patient_group.items(), start=1):
            print("=" * 80)
            print(f"รายการที่ {i} HN: {hn}")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    total, success_count, fail_count = run(target_date)
    print(
        f"CANCER_LINK_LAB_FU วันที่ {target_date} "
        f"ทั้งหมด {total} HN สำเร็จ {success_count} ไม่สำเร็จ {fail_count}"
    )


if __name__ == "__main__":
    main()