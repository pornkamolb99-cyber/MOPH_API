from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_TREATMENT_DRUG = """
SELECT 
    LEFT(PATIENT_REF.REF, 1) + '-' +
    SUBSTRING(PATIENT_REF.REF, 2, 4) + '-' +
    SUBSTRING(PATIENT_REF.REF, 6, 5) + '-' +
    SUBSTRING(PATIENT_REF.REF, 11, 2) + '-' +
    RIGHT(PATIENT_REF.REF, 1) AS cid,
    CONVERT(varchar, VNDIAG.VISITDATE, 112) AS visit,
    Cancer_Drug.treatment_code,
    CONVERT(varchar, VNDIAG.VISITDATE, 112) AS treatment_start_date,
    CONVERT(varchar, VNDIAG.VISITDATE, 112) AS treatment_end_date,
    '1' AS type,
    VNMST.HN,
    VNDIAG.ICDCODE
FROM SSBDatabase.dbo.VNDIAG
JOIN VNPRES
    ON VNDIAG.VN = VNPRES.VN
   AND VNDIAG.VISITDATE = VNPRES.VISITDATE
   AND VNDIAG.SUFFIX = VNPRES.SUFFIX
JOIN VNMST
    ON VNDIAG.VN = VNMST.VN
   AND VNDIAG.VISITDATE = VNMST.VISITDATE
JOIN PATIENT_REF
    ON VNMST.HN = PATIENT_REF.HN
   AND PATIENT_REF.REFTYPE = '01'
JOIN VNMEDICINE
    ON VNDIAG.VN = VNMEDICINE.VN
   AND VNDIAG.VISITDATE = VNMEDICINE.VISITDATE
   AND VNDIAG.SUFFIX = VNMEDICINE.SUFFIX
JOIN Cancer_Drug
    ON VNMEDICINE.STOCKCODE = Cancer_Drug.drug_code
WHERE (
        VNDIAG.ICDCODE BETWEEN 'D37' AND 'D489'
        OR VNDIAG.ICDCODE LIKE 'C%'
      )
  AND VNDIAG.TYPEOFTHISDIAG = '1'
  AND CONVERT(date, DIAGDATETIME) = ?
GROUP BY PATIENT_REF.REF,
         VNDIAG.VISITDATE,
         Cancer_Drug.treatment_code,
         VNMST.HN,
         VNDIAG.ICDCODE

UNION

SELECT 
    LEFT(PATIENT_REF.REF, 1) + '-' +
    SUBSTRING(PATIENT_REF.REF, 2, 4) + '-' +
    SUBSTRING(PATIENT_REF.REF, 6, 5) + '-' +
    SUBSTRING(PATIENT_REF.REF, 11, 2) + '-' +
    RIGHT(PATIENT_REF.REF, 1) AS cid,
    CONVERT(varchar, ADMMASTER.ADMDATETIME, 112) AS visit,
    Cancer_Drug.treatment_code,
    CONVERT(varchar, ADMMASTER.ADMDATETIME, 112) AS treatment_start_date,
    CONVERT(varchar, ADMMASTER.DISCHARGEDATETIME, 112) AS treatment_end_date,
    '2' AS type,
    ADMMASTER.HN,
    DIAGNOSES AS ICDCODE
FROM SSBDatabase.dbo.IPDSUMMARY
JOIN ADMMASTER
    ON IPDSUMMARY.AN = ADMMASTER.AN
JOIN PATIENT_REF
    ON ADMMASTER.HN = PATIENT_REF.HN
   AND PATIENT_REF.REFTYPE = '01'
JOIN IPDDRUGHIST
    ON IPDSUMMARY.AN = IPDDRUGHIST.AN
JOIN Cancer_Drug
    ON IPDDRUGHIST.STOCKCODE = Cancer_Drug.drug_code
WHERE (
        DIAGNOSES BETWEEN 'D37' AND 'D489'
        OR DIAGNOSES LIKE 'C%'
      )
  AND CONVERT(date, DIAGNOSESDATE) = ?
GROUP BY PATIENT_REF.REF,
         Cancer_Drug.treatment_code,
         ADMMASTER.ADMDATETIME,
         ADMMASTER.DISCHARGEDATETIME,
         ADMMASTER.HN,
         DIAGNOSES
"""


SQL_CANCER_TREATMENT_PROCEDURE = """
SELECT 
    LEFT(PATIENT_REF.REF, 1) + '-' +
    SUBSTRING(PATIENT_REF.REF, 2, 4) + '-' +
    SUBSTRING(PATIENT_REF.REF, 6, 5) + '-' +
    SUBSTRING(PATIENT_REF.REF, 11, 2) + '-' +
    RIGHT(PATIENT_REF.REF, 1) AS cid,
    CONVERT(varchar, ADMMASTER.ADMDATETIME, 112) AS visit,
    '1' AS treatment_code,
    CONVERT(varchar, ADMMASTER.ADMDATETIME, 112) AS treatment_start_date,
    CONVERT(varchar, ADMMASTER.DISCHARGEDATETIME, 112) AS treatment_end_date,
    '2' AS type,
    ADMMASTER.HN,
    DIAGNOSES AS ICDCODE
FROM SSBDatabase.dbo.IPDSUMMARY
JOIN ADMMASTER
    ON IPDSUMMARY.AN = ADMMASTER.AN
JOIN PATIENT_REF
    ON ADMMASTER.HN = PATIENT_REF.HN
   AND PATIENT_REF.REFTYPE = '01'
WHERE (
        DIAGNOSES BETWEEN 'D37' AND 'D489'
        OR DIAGNOSES LIKE 'C%'
      )
  AND CONVERT(date, DIAGNOSESDATE) = ?
  AND (
        ProcudureIcdCmCode IN ('8622','1371','1341','741','8339','6632','8659','4709','9354','8604')
        OR ProcudureIcdCmCode2 IN ('8622','1371','1341','741','8339','6632','8659','4709','9354','8604')
        OR ProcudureIcdCmCode3 IN ('8622','1371','1341','741','8339','6632','8659','4709','9354','8604')
        OR ProcudureIcdCmCode4 IN ('8622','1371','1341','741','8339','6632','8659','4709','9354','8604')
        OR OTHERPROCUDUREICDCMCODE IN ('8622','1371','1341','741','8339','6632','8659','4709','9354','8604')
        OR OTHERPROCUDUREICDCMCODE2 IN ('8622','1371','1341','741','8339','6632','8659','4709','9354','8604')
        OR OTHERPROCUDUREICDCMCODE3 IN ('8622','1371','1341','741','8339','6632','8659','4709','9354','8604')
        OR OTHERPROCUDUREICDCMCODE4 IN ('8622','1371','1341','741','8339','6632','8659','4709','9354','8604')
        OR OTHERPROCUDUREICDCMCODE5 IN ('8622','1371','1341','741','8339','6632','8659','4709','9354','8604')
      )
GROUP BY PATIENT_REF.REF,
         ADMMASTER.ADMDATETIME,
         ADMMASTER.DISCHARGEDATETIME,
         ADMMASTER.HN,
         DIAGNOSES
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
        "cid": clean(row.get("cid")),
        "visit_date": clean(row.get("visit")),
        "icd10_code": clean(row.get("ICDCODE")),
        "treatment_code": clean(row.get("treatment_code")),
        "treatment_start_date": clean(row.get("treatment_start_date")),
        "treatment_end_date": clean(row.get("treatment_end_date")),
        "note": "",
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with connect() as conn:
        cursor = conn.cursor()

        cursor.execute(
            SQL_CANCER_TREATMENT_DRUG,
            target_date.isoformat(),
            target_date.isoformat(),
        )
        rows.extend(fetch_dicts(cursor))

        cursor.execute(SQL_CANCER_TREATMENT_PROCEDURE, target_date.isoformat())
        rows.extend(fetch_dicts(cursor))

    return rows


def upsert_log(row: dict[str, Any], message: Any) -> None:
    sql_count = """
    SELECT COUNT(*) AS num
    FROM Saraburi.dbo.Cancer_anywhere_log
    WHERE HN = ? AND status = ? AND VISITDATE = ?
    """

    sql_insert = """
    INSERT INTO Saraburi.dbo.Cancer_anywhere_log
        (HN, status, VISITDATE, makedate, treatment)
    VALUES
        (?, ?, ?, GETDATE(), ?)
    """

    sql_update = """
    UPDATE Saraburi.dbo.Cancer_anywhere_log
    SET treatment = ?
    WHERE HN = ? AND status = ? AND VISITDATE = ?
    """

    hn = clean(row.get("HN"))
    status = clean(row.get("type"))
    visit = clean(row.get("visit"))

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(sql_count, hn, status, visit)
        count_row = cursor.fetchone()
        count = count_row[0] if count_row else 0

        if count == 0:
            cursor.execute(sql_insert, hn, status, visit, str(message))
        else:
            cursor.execute(sql_update, str(message), hn, status, visit)

        conn.commit()


def insert_api_log() -> None:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Saraburi.dbo.API_log
                (IP, Makedate, apiwork, host)
            VALUES
                (?, GETDATE(), ?, ?)
            """,
            "",
            "Cancer Treatment",
            "python jobs.cancer_treatment",
        )
        conn.commit()


def is_success(data: dict[str, Any], result_ok: bool) -> bool:
    return result_ok and str(data.get("status")).lower() in ("1", "true", "success")


def run(target_date: date) -> tuple[int, int, int]:
    rows = fetch_rows(target_date)
    client = MophApiClient()

    success_count = 0
    fail_count = 0

    for row in rows:
        payload = build_payload(row)
        result = client.send_cancer_treatment(payload)

        data = result.data if isinstance(result.data, dict) else {}
        message = data.get("message", result.text)

        if is_success(data, result.ok):
            upsert_log(row, message)
            success_count += 1
        else:
            upsert_log(row, "Error")
            fail_count += 1
            print("CANCER_TREATMENT FAIL", row.get("HN"), result.status_code, result.text[:500])

    insert_api_log()
    return len(rows), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Anywhere Treatment")
    parser.add_argument("--date", help="วันที่ diagnosis รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)

    if args.dry_run:
        print(f"CANCER_TREATMENT วันที่ {target_date} พบข้อมูล {len(rows)} รายการ")
        for i, row in enumerate(rows, start=1):
            print("=" * 80)
            print(f"รายการที่ {i} HN: {row.get('HN')} TYPE: {row.get('type')}")
            print(json.dumps(build_payload(row), ensure_ascii=False, indent=2))
        return

    total, success_count, fail_count = run(target_date)
    print(
        f"CANCER_TREATMENT วันที่ {target_date} "
        f"ทั้งหมด {total} สำเร็จ {success_count} ไม่สำเร็จ {fail_count}"
    )


if __name__ == "__main__":
    main()