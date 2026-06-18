from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_HT = """
SELECT *
FROM (
    SELECT
        seq,
        main.HN,
        Patient_Ref.REF,
        dbo.GetTitle(main.HN) AS title,
        dbo.GetNameWithoutTitle(PATIENT_NAME.FIRSTNAME) AS fname,
        dbo.GetNameWithoutTitle(PATIENT_NAME.LASTNAME) AS lname,
        Occupation.OccName,
        CASE
            WHEN MARITALSTATUS = 1 THEN '1'
            WHEN MARITALSTATUS = 2 THEN '2'
            WHEN MARITALSTATUS = 3 THEN '4'
            WHEN MARITALSTATUS = 4 THEN '1'
            WHEN MARITALSTATUS = 5 THEN '3'
            ELSE '9'
        END AS marriage,
        CONVERT(varchar, BIRTHDATETIME, 23) AS dob,
        CONVERT(varchar, SEX) AS sex,
        NationalityView.NationalityName,
        CONVERT(varchar, VISITDATE, 121) AS visit_date_time,
        CONVERT(varchar, DIAGDATETIME, 121) AS dx_date_time,
        CONVERT(varchar, TYPEOFTHISDIAG) AS TYPEOFTHISDIAG,
        (
            SELECT TOP 1 result
            FROM dbo.GetLabResult(main.HN, VISITDATE, VISITDATE) AS lab_result
            JOIN MOPH.dbo.Ref_LabICD10TM lab
                ON lab_result.labcode = lab.labcode
            WHERE edmst = 3
              AND SSBLabCode = 'C006'
        ) AS LabCode,
        (
            SELECT TOP 1 result
            FROM dbo.GetLabResult(main.HN, VISITDATE, VISITDATE) AS lab_result
            JOIN MOPH.dbo.Ref_LabICD10TM lab
                ON lab_result.labcode = lab.labcode
            WHERE edmst = 3
              AND SSBLabCode = 'C003'
        ) AS LabCode2
    FROM (
        SELECT
            VNMST.HN,
            VNMST.VISITDATE,
            VNPRES.RIGHTCODE,
            ROW_NUMBER() OVER (
                PARTITION BY VNMST.HN
                ORDER BY VNDIAG.SUFFIX
            ) AS RowNO,
            VNDIAG.TYPEOFTHISDIAG,
            NHSOs.dbo.GetSeqOnlyOne(VNMST.VN, VNMST.VISITDATE) AS seq,
            DIAGDATETIME
        FROM VNMST
        JOIN VNPRES
            ON VNMST.VN = VNPRES.VN
           AND VNMST.VISITDATE = VNPRES.VISITDATE
        JOIN VNDIAG
            ON VNPRES.VN = VNDIAG.VN
           AND VNPRES.VISITDATE = VNDIAG.VISITDATE
           AND VNPRES.SUFFIX = VNDIAG.SUFFIX
        WHERE VNMST.VISITDATE = ?
          AND VNDIAG.ICDCODE = 'I10'
          AND (
                CLOSEVISITTYPE NOT IN (
                    SELECT *
                    FROM Saraburi.dbo.CloseVisitType
                )
                OR CLOSEVISITTYPE IS NULL
          )
          AND VNPRES.RIGHTCODE IN (
                SELECT ssb_rightcode
                FROM nhsos.dbo.nhsoref_inscl_right_mapping
                WHERE nhso_inscl = 'ucs'
          )
    ) AS main
    JOIN PATIENT_REF
        ON main.HN = PATIENT_REF.HN
       AND PATIENT_REF.REFTYPE = '01'
    LEFT JOIN PATIENT_NAME
        ON main.HN = PATIENT_NAME.HN
       AND PATIENT_NAME.SUFFIX = 0
    LEFT JOIN PATIENT_INFO
        ON main.HN = PATIENT_INFO.HN
    LEFT JOIN Occupation
        ON PATIENT_INFO.OCCUPATION = Occupation.CODE
    LEFT JOIN NationalityView
        ON PATIENT_INFO.nationality = NationalityView.Nationality
    WHERE RowNO = 1
) AS main
WHERE main.LabCode IS NOT NULL
  AND main.LabCode2 IS NOT NULL
"""


def parse_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return date.today()


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def short_datetime(value: Any) -> str:
    return clean(value)[:16]


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_HT, target_date.isoformat())
        return fetch_dicts(cursor)


def build_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": clean(row.get("seq")),
        "hn": clean(row.get("HN")),
        "pid": clean(row.get("REF")),
        "id_type": "1",
        "title": clean(row.get("title")),
        "fname": clean(row.get("fname")),
        "lname": clean(row.get("lname")),
        "occupa": clean(row.get("OccName")),
        "marriage": clean(row.get("marriage")),
        "dob": clean(row.get("dob")),
        "sex": clean(row.get("sex")),
        "nation": "099",
        "uuc": "1",
        "hcode": "10661",
        "hospital_name": "โรงพยาบาลสระบุรี",
        "visit_date_time": short_datetime(row.get("visit_date_time")),
        "is_used_dm": "0",
        "is_used_ht": "1",
        "diagnosis": [
            {
                "dx_date_time": short_datetime(row.get("dx_date_time")),
                "icd10": "I10",
                "dx_type": clean(row.get("TYPEOFTHISDIAG")),
            }
        ],
        "claim_services": [
            {
                "name": "Potassium (K)",
                "code": "32103",
                "lab_result": clean(row.get("LabCode")),
            },
            {
                "name": "Creatinine (Cr)",
                "code": "32202",
                "lab_result": clean(row.get("LabCode2")),
            },
        ],
    }


def insert_log(
    hn: str,
    seq: str,
    status: str,
    message: str,
    transaction_uid: str | None = None,
) -> None:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Saraburi.dbo.API_Moph_Claim_Response
                (transaction_uid, HN, seq, makedate, API_Type, status, message)
            VALUES
                (?, ?, ?, GETDATE(), 'HT', ?, ?)
            """,
            transaction_uid,
            hn,
            seq,
            status,
            message,
        )
        conn.commit()


def send_ht(client: MophApiClient, payload: dict[str, Any]):
    if hasattr(client, "send_ht"):
        return client.send_ht(payload)

    if hasattr(client, "send_dmht"):
        return client.send_dmht(payload)

    return client.send_dm(payload)


def run(target_date: date) -> tuple[int, int, int]:
    rows = fetch_rows(target_date)
    client = MophApiClient()

    success_count = 0
    fail_count = 0

    for row in rows:
        payload = build_payload(row)
        result = send_ht(client, payload)

        data = result.data if isinstance(result.data, dict) else {}
        status = clean(data.get("status"))
        message = clean(data.get("message_th", result.text))

        transaction_uid = None
        if isinstance(data.get("data"), dict):
            transaction_uid = data["data"].get("transaction_uid")

        insert_log(
            hn=clean(row.get("HN")),
            seq=clean(row.get("seq")),
            status=status,
            message=message,
            transaction_uid=transaction_uid,
        )

        if status == "200":
            success_count += 1
        else:
            fail_count += 1
            print("HT FAIL", row.get("HN"), row.get("seq"), status, message)

    return len(rows), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล HT")
    parser.add_argument("--date", help="วันที่ visit รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้วันนี้")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)

    if args.dry_run:
        print(f"HT วันที่ {target_date} พบข้อมูล {len(rows)} รายการ")
        for i, row in enumerate(rows, start=1):
            print("=" * 80)
            print(f"รายการที่ {i} HN: {row.get('HN')} SEQ: {row.get('seq')}")
            print(json.dumps(build_payload(row), ensure_ascii=False, indent=2))
        return

    total, success_count, fail_count = run(target_date)
    print(f"HT วันที่ {target_date} ทั้งหมด {total} สำเร็จ {success_count} ไม่สำเร็จ {fail_count}")


if __name__ == "__main__":
    main()