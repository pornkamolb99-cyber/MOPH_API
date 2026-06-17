from __future__ import annotations

import argparse
import json
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_HRM_NURSE = """
SELECT
    PAYROLLNO,
    dbo.GetSSBName(ISNULL(scon.thainame, scon.englishname)) AS PersonnelTypeName,
    REPLACE(CONVERT(varchar, FIRSTEMPLOYEEDATE, 111), '/', '-') AS STARTDATE,
    REPLACE(CONVERT(varchar, TERMINATEDATE, 111), '/', '-') AS TERMINATEDATE,
    SSBDatabase.dbo.GetSSBName(
        ISNULL(SYSCONFIG.ENGLISHNAME, SYSCONFIG.THAINAME)
    ) AS terminate,
    SECTION,
    IDCARD
FROM SSBDatabase.dbo.PYREXT
LEFT OUTER JOIN SSBDatabase.dbo.sysconfig scon
    ON pyrext.positioncode = scon.code
   AND scon.ctrlcode = '10079'
LEFT JOIN SSBDatabase.dbo.SYSCONFIG
    ON SYSCONFIG.CTRLCODE = '60022'
   AND PYREXT.TERMINATEREASON = SYSCONFIG.CODE
WHERE PYREXT.POSITIONCODE IN ('59','58','2403','103','601')
  AND LEFT(PAYROLLNO,1) NOT IN ('P','Z')
"""


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def fetch_rows() -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_HRM_NURSE)
        return fetch_dicts(cursor)


def build_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = []

    for row in rows:
        payload.append(
            {
                "EMPID": clean(row.get("PAYROLLNO")),
                "POSITION": clean(row.get("PersonnelTypeName")),
                "STARTDATE": clean(row.get("STARTDATE")),
                "TERMINATEDATE": clean(row.get("TERMINATEDATE")),
                "TERMINATE_REASON": clean(row.get("terminate")),
                "SECTION": clean(row.get("SECTION")),
                "IDCARD": clean(row.get("IDCARD")),
            }
        )

    return payload


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
            "HRM Nurse OnCloud",
            "python jobs.sbh_oncloud_hrm_nurse",
        )

        conn.commit()


def run() -> tuple[int, bool, str]:
    rows = fetch_rows()
    payload = build_payload(rows)

    client = MophApiClient()
    result = client.send_sbh_oncloud_hrm_nurse(payload)

    data = result.data if isinstance(result.data, dict) else {}

    message = str(data.get("message", result.text))

    success = message == "DONE"

    if success:
        insert_api_log()

    return len(rows), success, message


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ส่งข้อมูล SBH OnCloud HRM Nurse"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ดู JSON ก่อนส่ง API",
    )

    args = parser.parse_args()

    rows = fetch_rows()
    payload = build_payload(rows)

    if args.dry_run:
        print(f"SBH_ONCLOUD_HRM_NURSE พบข้อมูล {len(payload)} รายการ")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    total, success, message = run()

    print(
        f"SBH_ONCLOUD_HRM_NURSE "
        f"ทั้งหมด {total} "
        f"{'สำเร็จ' if success else 'ไม่สำเร็จ'} "
        f"message={message}"
    )


if __name__ == "__main__":
    main()