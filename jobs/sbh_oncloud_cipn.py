from __future__ import annotations

import argparse
import json
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CIPN = """
SELECT
    cipn.No,
    cipn.AN,
    cipn.Drg,
    cipn.RW,
    cipn.AdjRW,
    P_CODE.p_name,
    T_CODE.t_name,
    CONVERT(varchar, FILE_ID.responsedate, 112) AS redate
FROM Saraburi.dbo.Statement_CIGN_Detail cipn
LEFT JOIN Saraburi.dbo.Statement_AIPNRef_pcode P_CODE
    ON cipn.pcode = P_CODE.pcode
LEFT JOIN Saraburi.dbo.Statement_AIPNRef_tcode T_CODE
    ON cipn.tcode = T_CODE.tcode
LEFT JOIN Saraburi.dbo.Statement_CIGN_Main FILE_ID
    ON cipn.responseid = FILE_ID.responseid
WHERE FILE_ID.OnCloud = '0'
"""


SQL_ERR = """
SELECT
    e.err,
    r.e_name
FROM Saraburi.dbo.Statement_CIGN_Error e
JOIN Saraburi.dbo.Statement_AIPNRef_err r
    ON e.err = r.err
WHERE e.No = ?
"""


def build_payload() -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()

        cursor.execute(SQL_CIPN)
        rows = fetch_dicts(cursor)

        payload: list[dict[str, Any]] = []

        for row in rows:
            cursor.execute(SQL_ERR, row["No"])
            errors = fetch_dicts(cursor)

            payload.append(
                {
                    "No": row["No"],
                    "AN": row["AN"],
                    "Drg": row["Drg"],
                    "RW": row["RW"],
                    "AdjRW": row["AdjRW"],
                    "p_name": row["p_name"],
                    "t_name": row["t_name"],
                    "responsedate": row["redate"],
                    "error": [
                        {
                            "err": err["err"],
                            "e_name": err["e_name"],
                        }
                        for err in errors
                    ],
                }
            )

        return payload


def update_oncloud() -> None:
    with connect() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE Saraburi.dbo.Statement_CIGN_Main
            SET OnCloud = '1'
            WHERE OnCloud = '0'
            """
        )

        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = build_payload()

    print("CIPN COUNT:", len(payload))

    if args.dry_run:
        print(json.dumps(payload[:3], ensure_ascii=False, indent=2))
        return

    client = MophApiClient()
    result = client.send_sbh_oncloud_cipn(payload)

    if isinstance(result.data, dict):
        message = result.data.get("message")
    else:
        message = None

    print(result.text)

    if message == "DONE":
        update_oncloud()
        print("UPDATE ONCLOUD SUCCESS")


if __name__ == "__main__":
    main()