from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_DM = """
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
        CONVERT(varchar, VISITDATE, 121) AS visit_date_time,
        CONVERT(varchar, DIAGDATETIME, 121) AS dx_date_time,
        CONVERT(varchar, TYPEOFTHISDIAG) AS TYPEOFTHISDIAG,
        ICDCODE,
        (
            SELECT result
            FROM dbo.GetLabResult(main.HN, VISITDATE, VISITDATE) lab_result
            JOIN MOPH.dbo.Ref_LabICD10TM lab
                ON lab_result.labcode = lab.labcode
            WHERE edmst = 3
              AND SSBLabCode = 'C040'
        ) AS LabCode
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
            DIAGDATETIME,
            ICDCODE
        FROM VNMST
        JOIN VNPRES
            ON VNMST.VN = VNPRES.VN
           AND VNMST.VISITDATE = VNPRES.VISITDATE
        JOIN VNDIAG
            ON VNPRES.VN = VNDIAG.VN
           AND VNPRES.VISITDATE = VNDIAG.VISITDATE
           AND VNPRES.SUFFIX = VNDIAG.SUFFIX
        WHERE VNMST.VISITDATE = ?
          AND VNDIAG.ICDCODE IN (
                'E119','E149','E111','E112','E113',
                'E114','E115','E116','E117','E118'
          )
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
    WHERE RowNO = 1
) main
WHERE main.LabCode IS NOT NULL
"""


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_DM, target_date.isoformat())
        return fetch_dicts(cursor)


def build_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": row["seq"],
        "hn": row["HN"],
        "pid": row["REF"],
        "id_type": "1",
        "title": row["title"],
        "fname": row["fname"],
        "lname": row["lname"],
        "occupa": row["OccName"],
        "marriage": row["marriage"],
        "dob": row["dob"],
        "sex": row["sex"],
        "nation": "099",
        "uuc": "1",
        "hcode": "10661",
        "hospital_name": "โรงพยาบาลสระบุรี",
        "visit_date_time": row["visit_date_time"][:16],
        "is_used_dm": "1",
        "is_used_ht": "0",
        "diagnosis": [
            {
                "dx_date_time": row["dx_date_time"][:16],
                "icd10": row["ICDCODE"],
                "dx_type": row["TYPEOFTHISDIAG"],
            }
        ],
        "claim_services": [
            {
                "name": "HbA1C",
                "code": "32401",
                "lab_result": str(row["LabCode"]).strip(),
            }
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
            (
                transaction_uid,
                HN,
                seq,
                makedate,
                API_Type,
                status,
                message
            )
            VALUES
            (
                ?, ?, ?, GETDATE(),
                'DM',
                ?, ?
            )
            """,
            transaction_uid,
            hn,
            seq,
            status,
            message,
        )

        conn.commit()


def run(target_date: date) -> None:

    client = MophApiClient()

    rows = fetch_rows(target_date)

    print("ROW COUNT =", len(rows))

    for row in rows:

        payload = build_payload(row)

        result = client.send_dmht(payload)

        data = result.data if isinstance(result.data, dict) else {}

        status = str(data.get("status", ""))
        message = str(data.get("message_th", result.text))

        transaction_uid = (
            data.get("data", {}).get("transaction_uid")
            if isinstance(data.get("data"), dict)
            else None
        )

        insert_log(
            hn=row["HN"],
            seq=row["seq"],
            status=status,
            message=message,
            transaction_uid=transaction_uid,
        )

        print(
            row["HN"],
            row["seq"],
            status,
            message,
        )


def main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    target_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else date.today()
    )

    rows = fetch_rows(target_date)

    if args.dry_run:
        print("ROW COUNT =", len(rows))

        for row in rows[:10]:
            print(
                json.dumps(
                    build_payload(row),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return

    run(target_date)


if __name__ == "__main__":
    main()