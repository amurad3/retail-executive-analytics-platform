"""Load step: fast bulk loading into Postgres via COPY, which is orders of
magnitude faster than row-by-row INSERT at the 8-10M row scale this project
targets."""
import io
import logging

import pandas as pd

logger = logging.getLogger(__name__)


def truncate_tables(conn, table_names: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE;")
    conn.commit()


def copy_dataframe(conn, df: pd.DataFrame, table_name: str) -> int:
    if df.empty:
        return 0
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="")
    buf.seek(0)
    columns = ", ".join(df.columns)
    with conn.cursor() as cur:
        cur.copy_expert(
            f"COPY {table_name} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '')",
            buf,
        )
    conn.commit()
    return len(df)
