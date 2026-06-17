from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_LINK_LAB_OPD_VISIT = """
SELECT
    VNMST.HN,
    RIGHT('00000' + CAST(VNMST.VN AS VARCHAR), 5) +
    FORMAT(VNMST.VISITDATE, 'ddMMyyyy') +
    RIGHT('00' + CAST(VNDIAG.SUFFIX AS VARCHAR), 2) AS barcode,
    VNMST.VN,
    CONVERT(varchar, VNMST.VISITDATE, 120) AS VISITDATE
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
GROUP BY
    VNMST.HN,
    VNMST.VN,
    VNMST.VISITDATE,
    VNDIAG.SUFFIX
"""


SQL_CANCER_LINK_LAB_OPD_DETAIL = """
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


def build_payload(visit: dict[str, Any], lab: dict[str, Any]) -> dict[str, Any]:
    return {
        "hospcode": "10661",
        "hn": clean(visit.get("HN")),
        "vn": clean(visit.get("barcode")),
        "lab_code": clean(lab.get("LabCode")),
        "lab_name": clean(lab.get("LabName")),
        "lab_result": clean(lab.get("result")),
        "lab_unit": clean(lab.get("ITMUN")),
    }


def fetch_visits(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_CANCER_LINK_LAB_OPD_VISIT, target_date.isoformat())
        return fetch_dicts(cursor)


def fetch_labs(hn: Any, visit_datetime: Any) -> list[dict[str, Any]]:
    visit_datetime_text = clean(visit_datetime)

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            SQL_CANCER_LINK_LAB_OPD_DETAIL,
            clean(hn),
            visit_datetime_text,
            visit_datetime_text,
        )
        return fetch_dicts(cursor)


def insert_log(hn: Any, success: Any, message: Any) -> None:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Saraburi.dbo.API_log_cancerlink
                (HN, makedate, success, message, headersname)
            VALUES (?, GETDATE(), ?, ?, 'lab_opd')
            """,
            hn,
            str(success),
            str(message),
        )
        conn.commit()


def is_success(result_ok: bool, success: Any) -> bool:
    return result_ok and str(success).lower() in ("true", "1", "y", "success")


def build_visit_payload(visit: dict[str, Any]) -> list[dict[str, Any]]:
    labs = fetch_labs(visit.get("HN"), visit.get("VISITDATE"))
    return [build_payload(visit, lab) for lab in labs]


def run(target_date: date) -> tuple[int, int, int]:
    visits = fetch_visits(target_date)
    client = MophApiClient()

    sent_count = 0
    success_count = 0
    fail_count = 0

    for visit in visits:
        payload = build_visit_payload(visit)

        if not payload:
            continue

        result = client.send_cancer_link_lab_opd(payload)

        data = result.data if isinstance(result.data, dict) else {}
        success = data.get("success", result.ok)
        message = data.get("message", result.text)

        insert_log(visit.get("HN"), success, message)
        sent_count += 1

        if is_success(result.ok, success):
            success_count += 1
        else:
            fail_count += 1
            print(
                "CANCER_LINK_LAB_OPD FAIL",
                visit.get("HN"),
                result.status_code,
                result.text[:500],
            )

    return sent_count, success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Link Lab OPD")
    parser.add_argument("--date", help="วันที่ visit รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    visits = fetch_visits(target_date)

    if args.dry_run:
        sent_count = 0
        lab_row_count = 0

        print(f"CANCER_LINK_LAB_OPD วันที่ {target_date} พบ visit {len(visits)} รายการ")

        for i, visit in enumerate(visits, start=1):
            payload = build_visit_payload(visit)

            if not payload:
                continue

            sent_count += 1
            lab_row_count += len(payload)

            print("=" * 80)
            print(f"รายการที่ {sent_count} HN: {visit.get('HN')} VN: {visit.get('barcode')}")
            print(json.dumps(payload, ensure_ascii=False, indent=2))

        print(
            f"CANCER_LINK_LAB_OPD วันที่ {target_date} "
            f"ส่งได้ {sent_count} visit / {lab_row_count} lab rows"
        )
        return

    total, success_count, fail_count = run(target_date)
    print(
        f"CANCER_LINK_LAB_OPD วันที่ {target_date} "
        f"ทั้งหมด {total} visit สำเร็จ {success_count} ไม่สำเร็จ {fail_count}"
    )


if __name__ == "__main__":
    main()