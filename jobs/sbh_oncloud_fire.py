from __future__ import annotations

import argparse
import json
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_FIRE = """
SELECT
    Register.EmpID AS EMPID,
    SSBDatabase.dbo.GetSSBName(PYREXT.FIRSTTHAINAME) + ' ' +
    SSBDatabase.dbo.GetSSBName(PYREXT.LASTTHAINAME) AS USERNAME,
    REPLACE(section.ThaiName, '(ใหม่)', '') AS SECTIONNAME,
    Position.PositionName AS POSITIONNAME,
    FIRE.call AS [CALL]
FROM Saraburi.dbo.FIRE
JOIN Saraburi.dbo.Register
    ON FIRE.EmpID = Register.EmpID
LEFT JOIN SSBDatabase.dbo.sectioncode section
    ON Register.Section = section.Code
LEFT JOIN SSBDatabase.dbo.PositionView Position
    ON Register.nPosition = Position.PositionCode
LEFT JOIN SSBDatabase.dbo.PYREXT PYREXT
    ON PYREXT.PAYROLLNO = FIRE.EmpID
WHERE Register.nDate = CONVERT(date, GETDATE())
  AND nPeriod = (
        SELECT CASE
            WHEN CONVERT(time, GETDATE()) BETWEEN '08:30:00' AND '16:30:59' THEN 1
            WHEN CONVERT(time, GETDATE()) BETWEEN '16:31:00' AND '23:59:59' THEN 2
            ELSE 3
        END
  )
ORDER BY PYREXT.FIRSTTHAINAME
"""


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def fetch_rows() -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_FIRE)
        return fetch_dicts(cursor)


def build_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []

    for row in rows:
        payload.append(
            {
                "EMPID": clean(row.get("EMPID")),
                "USERNAME": clean(row.get("USERNAME")),
                "SECTIONNAME": clean(row.get("SECTIONNAME")),
                "POSITIONNAME": clean(row.get("POSITIONNAME")),
                "CALL": clean(row.get("CALL")),
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
            "FIRE OnCloud",
            "python jobs.sbh_oncloud_fire",
        )
        conn.commit()


def run() -> tuple[int, bool, str]:
    rows = fetch_rows()
    payload = build_payload(rows)

    client = MophApiClient()
    result = client.send_sbh_oncloud_fire(payload)

    data = result.data if isinstance(result.data, dict) else {}
    message = clean(data.get("message", result.text))

    ok = message == "DONE"

    if ok:
        insert_api_log()

    return len(rows), ok, message


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล SBH OnCloud FIRE")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    rows = fetch_rows()
    payload = build_payload(rows)

    if args.dry_run:
        print(f"SBH_ONCLOUD_FIRE พบข้อมูล {len(rows)} รายการ")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    total, ok, message = run()

    print(
        f"SBH_ONCLOUD_FIRE ทั้งหมด {total} "
        f"{'สำเร็จ' if ok else 'ไม่สำเร็จ'} message={message}"
    )


if __name__ == "__main__":
    main()