from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_DT = """
SELECT
    NHSOs.dbo.GetSeqOnlyOne(VNMST.VN, VNMST.VISITDATE) AS seq,
    VNMST.HN,
    Patient_Ref.REF,
    dbo.GetTitle(VNMST.HN) AS title,
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
    CONVERT(varchar, PATIENT_INFO.BIRTHDATETIME, 23) AS dob,
    CONVERT(varchar, PATIENT_INFO.SEX) AS sex,
    RIGHT(REPLICATE('0', 3) + PATIENT_INFO.nationality, 3) AS nation,
    CONVERT(varchar, VNMST.VISITDATE, 121) AS visit_date_time,
    VNMEDICINE.LOTNO,
    VNMEDICINE.DOSEQTYCODE,
    CONVERT(varchar, EXPIRYDATE, 23) AS expiration_date,
    dbo.GetUserFullName(VNPRES.DOCTOR) AS name,
    CERTIFYPUBLICNO
FROM VNMEDICINE
JOIN VNMST
    ON VNMEDICINE.VISITDATE = VNMST.VISITDATE
   AND VNMEDICINE.VN = VNMST.VN
JOIN VNPRES
    ON VNMEDICINE.VISITDATE = VNPRES.VISITDATE
   AND VNMEDICINE.VN = VNPRES.VN
   AND VNMEDICINE.SUFFIX = VNPRES.SUFFIX
JOIN PATIENT_INFO
    ON VNMST.HN = PATIENT_INFO.HN
JOIN PATIENT_REF
    ON VNMST.HN = PATIENT_REF.HN
   AND PATIENT_REF.REFTYPE = '01'
LEFT JOIN PATIENT_NAME
    ON VNMST.HN = PATIENT_NAME.HN
   AND PATIENT_NAME.SUFFIX = 0
LEFT JOIN Occupation
    ON PATIENT_INFO.OCCUPATION = Occupation.CODE
LEFT JOIN HNDOCTOR
    ON VNPRES.DOCTOR = HNDOCTOR.DOCTOR
WHERE VNMEDICINE.VISITDATE = ?
  AND STOCKCODE IN ('1152120', '9000065')
  AND dbo.age(PATIENT_INFO.BIRTHDATETIME, VNMEDICINE.VISITDATE) >= 25
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
        "nation": clean(row.get("nation")),
        "hcode": "10661",
        "hospital_name": "โรงพยาบาลสระบุรี",
        "visit_date_time": short_datetime(row.get("visit_date_time")),
        "vaccine": [
            {
                "code": "106",
                "lot_number": clean(row.get("LOTNO")),
                "dose_quantity": clean(row.get("DOSEQTYCODE")),
                "manufacturer": "",
                "expiration_date": clean(row.get("expiration_date")),
                "occurence_date_time": short_datetime(row.get("visit_date_time")),
                "site_code": "IM",
                "route_code": "LUA",
                "license_no": clean(row.get("CERTIFYPUBLICNO")),
                "name": clean(row.get("name")),
                "note": "",
            }
        ],
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_DT, target_date.isoformat())
        return fetch_dicts(cursor)


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
                (?, ?, ?, GETDATE(), 'DT', ?, ?)
            """,
            transaction_uid,
            hn,
            seq,
            status,
            message,
        )
        conn.commit()


def run(target_date: date) -> tuple[int, int, int]:
    rows = fetch_rows(target_date)
    client = MophApiClient()

    success_count = 0
    fail_count = 0

    for row in rows:
        payload = build_payload(row)
        result = client.send_dt(payload)

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
            print("DT FAIL", row.get("HN"), row.get("seq"), status, message)

    return len(rows), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล DT")
    parser.add_argument("--date", help="วันที่ visit รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้วันนี้")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)

    if args.dry_run:
        print(f"DT วันที่ {target_date} พบข้อมูล {len(rows)} รายการ")
        for i, row in enumerate(rows, start=1):
            print("=" * 80)
            print(f"รายการที่ {i} HN: {row.get('HN')} SEQ: {row.get('seq')}")
            print(json.dumps(build_payload(row), ensure_ascii=False, indent=2))
        return

    total, success_count, fail_count = run(target_date)
    print(f"DT วันที่ {target_date} ทั้งหมด {total} สำเร็จ {success_count} ไม่สำเร็จ {fail_count}")


if __name__ == "__main__":
    main()