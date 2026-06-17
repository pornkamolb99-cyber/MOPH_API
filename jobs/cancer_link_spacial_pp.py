from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_LINK_SPACIAL_PP = """
SELECT
    MAIN.HN,
    PATIENT_REF.REF AS cid,
    CONVERT(VARCHAR(10), MAIN.VISITDATE, 23) AS vstdate,
    MAIN.pp_code
FROM (
    SELECT
        VNMST.HN,
        VNTREAT.VN,
        VNTREAT.VISITDATE,
        VNTREAT.SUFFIX,
        MOPH.dbo.Ref_SpecialPP.PPSPECIAL AS pp_code,
        (
            SELECT COUNT(*)
            FROM VNDIAG
            JOIN VNMST AS mst
                ON VNDIAG.VN = mst.VN
               AND VNDIAG.VISITDATE = mst.VISITDATE
            WHERE (
                    VNDIAG.ICDCODE IN (
                        'Z014', 'Z124', 'R87', 'N87', 'D06', 'Z121',
                        'K635', 'K573', 'K51', 'Z123', 'Z016', 'N63'
                    )
                    OR VNDIAG.ICDCODE LIKE 'C%'
                  )
              AND VNDIAG.VISITDATE BETWEEN DATEADD(YEAR, -1, GETDATE()) AND CONVERT(date, GETDATE())
              AND mst.HN = VNMST.HN
        ) AS checkC
    FROM VNTREAT
    JOIN VNMST
        ON VNTREAT.VN = VNMST.VN
       AND VNTREAT.VISITDATE = VNMST.VISITDATE
    JOIN MOPH.dbo.Ref_SpecialPP
        ON VNTREAT.TREATMENTCODE = MOPH.dbo.Ref_SpecialPP.TreatmentCode
    WHERE MOPH.dbo.Ref_SpecialPP.PPSPECIAL IN ('1B0046','1B0060','1B0061')
      AND CONVERT(date, VNTREAT.VISITDATE) = ?
) AS MAIN
JOIN PATIENT_REF
    ON MAIN.HN = PATIENT_REF.HN
   AND PATIENT_REF.REFTYPE = '01'
WHERE MAIN.checkC > 0
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
        "cid": clean(row.get("cid")),
        "vstdate": clean(row.get("vstdate")),
        "pp_code": clean(row.get("pp_code")),
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_CANCER_LINK_SPACIAL_PP, target_date.isoformat())
        return fetch_dicts(cursor)


def insert_log(hn: Any, success: Any, message: Any) -> None:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Saraburi.dbo.API_log_cancerlink
                (HN, makedate, success, message, headersname)
            VALUES (?, GETDATE(), ?, ?, 'spacial_pp')
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
    client = MophApiClient()

    success_count = 0
    fail_count = 0

    for row in rows:
        payload = [build_payload(row)]
        result = client.send_cancer_link_spacial_pp(payload)

        data = result.data if isinstance(result.data, dict) else {}
        success = data.get("success", result.ok)
        message = data.get("message", result.text)

        insert_log(row.get("HN"), success, message)

        if is_success(result.ok, success):
            success_count += 1
        else:
            fail_count += 1
            print(
                "CANCER_LINK_SPACIAL_PP FAIL",
                row.get("HN"),
                result.status_code,
                result.text[:500],
            )

    return len(rows), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Link Spacial PP")
    parser.add_argument("--date", help="วันที่ visit รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)

    if args.dry_run:
        print(f"CANCER_LINK_SPACIAL_PP วันที่ {target_date} พบข้อมูล {len(rows)} รายการ")
        for i, row in enumerate(rows, start=1):
            print("=" * 80)
            print(f"รายการที่ {i} HN: {row.get('HN')}")
            print(json.dumps([build_payload(row)], ensure_ascii=False, indent=2))
        return

    total, success_count, fail_count = run(target_date)
    print(
        f"CANCER_LINK_SPACIAL_PP วันที่ {target_date} "
        f"ทั้งหมด {total} สำเร็จ {success_count} ไม่สำเร็จ {fail_count}"
    )


if __name__ == "__main__":
    main()