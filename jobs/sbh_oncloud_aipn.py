from __future__ import annotations

import argparse
import json
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_AIPN_BASE = """
SELECT aipn.No,
       aipn.AN,
       aipn.Drg,
       aipn.RW,
       aipn.AdjRW,
       P_CODE.p_name,
       T_CODE.t_name,
       IP_TYPE.i_name,
       CARE_AS.c_name,
       aipn.SS,
       ST_CODE.s_name,
       CONVERT(varchar, FILE_ID.responsedate, 112) AS redate
FROM Saraburi.dbo.Statement_AIPN_Detail aipn
LEFT JOIN Saraburi.dbo.Statement_AIPNRef_pcode P_CODE
    ON aipn.pcode = P_CODE.pcode
LEFT JOIN Saraburi.dbo.Statement_AIPNRef_tcode T_CODE
    ON aipn.tcode = T_CODE.tcode
LEFT JOIN Saraburi.dbo.Statement_AIPNRef_iptype IP_TYPE
    ON aipn.iptype = IP_TYPE.iptype
LEFT JOIN Saraburi.dbo.Statement_AIPNRef_careas CARE_AS
    ON aipn.CareAs = CARE_AS.CareAs
LEFT JOIN Saraburi.dbo.Statement_AIPNRef_st ST_CODE
    ON aipn.ST = ST_CODE.ST
LEFT JOIN Saraburi.dbo.Statement_AIPN_Main FILE_ID
    ON aipn.responseid = FILE_ID.responseid
"""


SQL_AIPN_ERROR = """
SELECT Statement_AIPN_Error.err,
       Statement_AIPNRef_err.e_name
FROM Saraburi.dbo.Statement_AIPN_Error
JOIN Saraburi.dbo.Statement_AIPNRef_err
    ON Statement_AIPN_Error.err = Statement_AIPNRef_err.err
WHERE No = ?
"""


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def fetch_errors(no: Any) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_AIPN_ERROR, no)
        rows = fetch_dicts(cursor)

    return [
        {
            "err": clean(row.get("err")),
            "e_name": clean(row.get("e_name")),
        }
        for row in rows
    ]


def fetch_rows(responseid: str | None = None) -> list[dict[str, Any]]:
    if responseid:
        sql = SQL_AIPN_BASE + "\nWHERE aipn.responseid = ?"
        params = [responseid]
    else:
        sql = SQL_AIPN_BASE + "\nWHERE FILE_ID.OnCloud = '0'"
        params = []

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, *params)
        return fetch_dicts(cursor)


def build_payload_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "No": row.get("No"),
        "AN": clean(row.get("AN")),
        "Drg": clean(row.get("Drg")),
        "RW": clean(row.get("RW")),
        "AdjRW": clean(row.get("AdjRW")),
        "p_name": clean(row.get("p_name")),
        "t_name": clean(row.get("t_name")),
        "i_name": clean(row.get("i_name")),
        "c_name": clean(row.get("c_name")),
        "SS": clean(row.get("SS")),
        "s_name": clean(row.get("s_name")),
        "responsedate": clean(row.get("redate")),
        "error": fetch_errors(row.get("No")),
    }


def build_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_payload_item(row) for row in rows]


def mark_oncloud(responseid: str | None = None) -> None:
    if responseid:
        sql = """
        UPDATE Saraburi.dbo.Statement_AIPN_Main
        SET OnCloud = '1'
        WHERE responseid = ?
        """
        params = [responseid]
    else:
        sql = """
        UPDATE Saraburi.dbo.Statement_AIPN_Main
        SET OnCloud = '1'
        WHERE OnCloud = '0'
        """
        params = []

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, *params)
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
            "AIPN OnCloud",
            "python jobs.sbh_oncloud_aipn",
        )
        conn.commit()


def run(responseid: str | None = None) -> tuple[int, bool, str]:
    rows = fetch_rows(responseid)
    payload = build_payload(rows)

    client = MophApiClient()
    result = client.send_sbh_oncloud_aipn(payload)

    data = result.data if isinstance(result.data, dict) else {}
    message = clean(data.get("message", result.text))

    ok = message == "DONE"

    if ok:
        mark_oncloud(responseid)
        insert_api_log()

    return len(rows), ok, message


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล SBH OnCloud AIPN")
    parser.add_argument("--responseid", help="ส่งเฉพาะ responseid ที่ต้องการ")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    rows = fetch_rows(args.responseid)
    payload = build_payload(rows)

    if args.dry_run:
        print(f"SBH_ONCLOUD_AIPN พบข้อมูล {len(rows)} รายการ")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    total, ok, message = run(args.responseid)

    print(
        f"SBH_ONCLOUD_AIPN ทั้งหมด {total} "
        f"{'สำเร็จ' if ok else 'ไม่สำเร็จ'} message={message}"
    )


if __name__ == "__main__":
    main()