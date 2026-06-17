from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_PATIENT = """
SELECT *
FROM (
    SELECT main.HN,
           CONVERT(varchar, visit, 112) AS visit,
           dbo.GetNameWithoutTitle(PATIENT_NAME.FIRSTNAME) AS name,
           dbo.GetSSBName(PATIENT_NAME.LASTNAME) AS last_name,
           LEFT(PATIENT_REF.REF, 1) + '-' +
           SUBSTRING(PATIENT_REF.REF, 2, 4) + '-' +
           SUBSTRING(PATIENT_REF.REF, 6, 5) + '-' +
           SUBSTRING(PATIENT_REF.REF, 11, 2) + '-' +
           RIGHT(PATIENT_REF.REF, 1) AS cid,
           CONVERT(varchar, PATIENT_INFO.BIRTHDATETIME, 112) AS birth_date,
           sex,
           CASE
                WHEN NATIONALITY = 99 THEN '1'
                WHEN NATIONALITY = 44 THEN '2'
                WHEN NATIONALITY = 56 THEN '3'
                WHEN NATIONALITY = 57 THEN '4'
                WHEN NATIONALITY = 48 THEN '5'
                WHEN NATIONALITY IS NULL THEN '9'
                ELSE '8'
           END AS nationality_code,
           PATIENT_ADDRESS.MOO,
           PATIENT_ADDRESS.changwatcode + PATIENT_ADDRESS.ampurcode + PATIENT_ADDRESS.tamboncode AS area_code,
           TEL,
           '1' AS type,
           CASE
                WHEN InitialNameCode = '003' THEN '1'
                WHEN InitialNameCode = '005' THEN '2'
                WHEN InitialNameCode = '004' THEN '3'
                WHEN InitialNameCode = '001' THEN '4'
                WHEN InitialNameCode = '002' THEN '5'
                WHEN InitialNameCode = '864' THEN '6'
                ELSE '99'
           END AS title_code
    FROM (
        SELECT VNMST.HN,
               VNMST.VISITDATE AS visit
        FROM SSBDatabase.dbo.VNDIAG
        JOIN VNMST
            ON VNDIAG.VN = VNMST.VN
           AND VNDIAG.VISITDATE = VNMST.VISITDATE
        WHERE (
                ICDCODE BETWEEN 'D37' AND 'D489'
                OR ICDCODE LIKE 'C%'
              )
          AND VNDIAG.TYPEOFTHISDIAG = '1'
          AND CONVERT(date, DIAGDATETIME) = ?
        GROUP BY VNMST.HN,
                 VNMST.VISITDATE
    ) AS main
    JOIN PATIENT_INFO
        ON main.HN = PATIENT_INFO.HN
    JOIN PATIENT_NAME
        ON main.HN = PATIENT_NAME.HN
       AND PATIENT_NAME.SUFFIX = '0'
    JOIN PATIENT_REF
        ON main.HN = PATIENT_REF.HN
       AND PATIENT_REF.REFTYPE = '01'
    JOIN PATIENT_ADDRESS
        ON main.HN = PATIENT_ADDRESS.HN
       AND PATIENT_ADDRESS.SUFFIX = '1'

    UNION

    SELECT ADMMASTER.HN,
           CONVERT(varchar, ADMMASTER.ADMDATETIME, 112) AS visit,
           dbo.GetNameWithoutTitle(PATIENT_NAME.FIRSTNAME) AS name,
           dbo.GetSSBName(PATIENT_NAME.LASTNAME) AS last_name,
           LEFT(PATIENT_REF.REF, 1) + '-' +
           SUBSTRING(PATIENT_REF.REF, 2, 4) + '-' +
           SUBSTRING(PATIENT_REF.REF, 6, 5) + '-' +
           SUBSTRING(PATIENT_REF.REF, 11, 2) + '-' +
           RIGHT(PATIENT_REF.REF, 1) AS cid,
           CONVERT(varchar, PATIENT_INFO.BIRTHDATETIME, 112) AS birth_date,
           sex,
           CASE
                WHEN NATIONALITY = 99 THEN '1'
                WHEN NATIONALITY = 44 THEN '2'
                WHEN NATIONALITY = 56 THEN '3'
                WHEN NATIONALITY = 57 THEN '4'
                WHEN NATIONALITY = 48 THEN '5'
                WHEN NATIONALITY IS NULL THEN '9'
                ELSE '8'
           END AS nationality_code,
           PATIENT_ADDRESS.MOO,
           PATIENT_ADDRESS.PROVINCE + PATIENT_ADDRESS.AMPHOE + PATIENT_ADDRESS.TAMBON AS area_code,
           TEL,
           '2' AS type,
           CASE
                WHEN InitialNameCode = '003' THEN '1'
                WHEN InitialNameCode = '005' THEN '2'
                WHEN InitialNameCode = '004' THEN '3'
                WHEN InitialNameCode = '001' THEN '4'
                WHEN InitialNameCode = '002' THEN '5'
                WHEN InitialNameCode = '864' THEN '6'
                ELSE '99'
           END AS title_code
    FROM SSBDatabase.dbo.IPDSUMMARY
    JOIN ADMMASTER
        ON IPDSUMMARY.AN = ADMMASTER.AN
    JOIN PATIENT_INFO
        ON ADMMASTER.HN = PATIENT_INFO.HN
    JOIN PATIENT_NAME
        ON ADMMASTER.HN = PATIENT_NAME.HN
       AND PATIENT_NAME.SUFFIX = '0'
    JOIN PATIENT_REF
        ON ADMMASTER.HN = PATIENT_REF.HN
       AND PATIENT_REF.REFTYPE = '01'
    JOIN PATIENT_ADDRESS
        ON ADMMASTER.HN = PATIENT_ADDRESS.HN
       AND PATIENT_ADDRESS.SUFFIX = '1'
    WHERE (
            DIAGNOSES BETWEEN 'D37' AND 'D489'
            OR DIAGNOSES LIKE 'C%'
          )
      AND CONVERT(date, DIAGNOSESDATE) = ?
) AS main
WHERE area_code IS NOT NULL
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
        "hn": clean(row.get("HN")),
        "title_code": clean(row.get("title_code")),
        "name": clean(row.get("name")),
        "last_name": clean(row.get("last_name")),
        "birth_date": clean(row.get("birth_date")),
        "sex_code": clean(row.get("sex")),
        "nationality_code": clean(row.get("nationality_code")),
        "address_no": "",
        "address_moo": clean(row.get("MOO")),
        "area_code": clean(row.get("area_code")),
        "permanent_address_no": "",
        "permanent_address_moo": clean(row.get("MOO")),
        "permanent_area_code": clean(row.get("area_code")),
        "death_date": None,
        "death_cause_code": None,
        "email": None,
        "telephone_1": clean(row.get("TEL")),
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_CANCER_PATIENT, target_date.isoformat(), target_date.isoformat())
        return fetch_dicts(cursor)


def upsert_log(row: dict[str, Any], message: Any) -> None:
    sql_count = """
    SELECT COUNT(*) AS num
    FROM Saraburi.dbo.Cancer_anywhere_log
    WHERE HN = ? AND status = ? AND VISITDATE = ?
    """

    sql_insert = """
    INSERT INTO Saraburi.dbo.Cancer_anywhere_log
        (HN, status, VISITDATE, makedate, patient)
    VALUES
        (?, ?, ?, ?, ?)
    """

    sql_update = """
    UPDATE Saraburi.dbo.Cancer_anywhere_log
    SET patient = ?, makedate = ?
    WHERE HN = ? AND status = ? AND VISITDATE = ?
    """

    hn = clean(row.get("HN"))
    status = clean(row.get("type"))
    visit = clean(row.get("visit"))
    makedate = date.today().isoformat()

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(sql_count, hn, status, visit)
        count_row = cursor.fetchone()
        count = count_row[0] if count_row else 0

        if count == 0:
            cursor.execute(sql_insert, hn, status, visit, makedate, str(message))
        else:
            cursor.execute(sql_update, str(message), makedate, hn, status, visit)

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
            "Cancer Patient",
            "python jobs.cancer_patient",
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
        result = client.send_cancer_patient(payload)

        data = result.data if isinstance(result.data, dict) else {}
        message = data.get("message", result.text)

        if is_success(data, result.ok):
            upsert_log(row, message)
            success_count += 1
        else:
            upsert_log(row, "Error")
            fail_count += 1
            print("CANCER_PATIENT FAIL", row.get("HN"), result.status_code, result.text[:500])

    insert_api_log()
    return len(rows), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Anywhere Patient")
    parser.add_argument("--date", help="วันที่ diagnosis รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)

    if args.dry_run:
        print(f"CANCER_PATIENT วันที่ {target_date} พบข้อมูล {len(rows)} รายการ")
        for i, row in enumerate(rows, start=1):
            print("=" * 80)
            print(f"รายการที่ {i} HN: {row.get('HN')} TYPE: {row.get('type')}")
            print(json.dumps(build_payload(row), ensure_ascii=False, indent=2))
        return

    total, success_count, fail_count = run(target_date)
    print(
        f"CANCER_PATIENT วันที่ {target_date} "
        f"ทั้งหมด {total} สำเร็จ {success_count} ไม่สำเร็จ {fail_count}"
    )


if __name__ == "__main__":
    main()