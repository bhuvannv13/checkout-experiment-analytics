"""Build the SQLite warehouse: load raw CSVs, run SQL models layer by layer
(staging -> intermediate -> marts, dbt-style), then run data-quality tests.

Usage: python pipeline.py
"""
from pathlib import Path
import re
import sqlite3
import sys
import time

import pandas as pd

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "warehouse.db"
LAYERS = ["staging", "intermediate", "marts"]

INDEXES = {
    "stg_orders": ["user_id"],
    "stg_checkout_events": ["user_id"],
    "int_experiment_users": ["user_id"],
    "int_user_orders": ["user_id"],
}

# dbt-style schema tests: (model, test, column, arg)
TESTS = [
    ("stg_users", "unique", "user_id", None),
    ("stg_users", "not_null", "device", None),
    ("stg_users", "accepted_values", "country", ["IE", "GB", "DE", "FR", "ES", "NL"]),
    ("stg_orders", "unique", "order_id", None),
    ("stg_orders", "positive", "order_value", None),
    ("stg_orders", "relationships", "user_id", ("stg_users", "user_id")),
    ("stg_assignments", "unique", "user_id", None),
    ("stg_assignments", "accepted_values", "variant", ["control", "treatment"]),
    ("fct_experiment_user_outcomes", "unique", "user_id", None),
    ("fct_experiment_user_outcomes", "not_null", "revenue", None),
]


def load_raw(con: sqlite3.Connection) -> None:
    for f in sorted(RAW.glob("*.csv")):
        pd.read_csv(f).to_sql(f"raw_{f.stem}", con, if_exists="replace", index=False)


def model_order() -> list[tuple[str, Path]]:
    """Topologically sort models by the other models each one references."""
    files = {f.stem: (layer, f) for layer in LAYERS for f in (ROOT / "sql" / layer).glob("*.sql")}
    deps = {n: {m for m in files if m != n and re.search(rf"\b{m}\b", f.read_text())}
            for n, (_, f) in files.items()}
    order, done = [], set()

    def visit(n, stack=()):
        if n in done:
            return
        if n in stack:
            raise ValueError(f"cycle: {stack + (n,)}")
        for d in sorted(deps[n]):
            visit(d, stack + (n,))
        done.add(n)
        order.append((files[n][0], files[n][1]))

    for n in sorted(files, key=lambda k: (LAYERS.index(files[k][0]), k)):
        visit(n)
    return order


def run_models(con: sqlite3.Connection) -> list[str]:
    built = []
    for layer, sql_file in model_order():
        if True:
            name = sql_file.stem
            t = time.time()
            con.execute(f"drop table if exists {name}")
            con.execute(f"create table {name} as {sql_file.read_text()}")
            for col in INDEXES.get(name, []):
                con.execute(f"create index if not exists ix_{name}_{col} on {name}({col})")
            n = con.execute(f"select count(*) from {name}").fetchone()[0]
            print(f"  [{layer:12}] {name:32} {n:>9,} rows  {time.time() - t:5.2f}s")
            built.append(name)
    return built


def failing_rows(con: sqlite3.Connection, model, test, col, arg) -> int:
    if test == "unique":
        q = f"select count(*) from (select {col} from {model} group by {col} having count(*) > 1)"
    elif test == "not_null":
        q = f"select count(*) from {model} where {col} is null"
    elif test == "positive":
        q = f"select count(*) from {model} where {col} <= 0"
    elif test == "accepted_values":
        vals = ",".join(f"'{v}'" for v in arg)
        q = f"select count(*) from {model} where {col} not in ({vals})"
    elif test == "relationships":
        parent, pcol = arg
        q = (f"select count(*) from {model} c left join {parent} p on c.{col} = p.{pcol} "
             f"where p.{pcol} is null")
    else:
        raise ValueError(test)
    return con.execute(q).fetchone()[0]


def run_tests(con: sqlite3.Connection) -> bool:
    ok = True
    for model, test, col, arg in TESTS:
        bad = failing_rows(con, model, test, col, arg)
        status = "PASS" if bad == 0 else f"FAIL ({bad} rows)"
        ok &= bad == 0
        print(f"  {status:14} {test:16} {model}.{col}")
    return ok


def main() -> int:
    if not RAW.exists():
        sys.exit("No raw data. Run: python data/generate.py")
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    print("Loading raw data ...")
    load_raw(con)
    print("Building models ...")
    run_models(con)
    print("Running data tests ...")
    ok = run_tests(con)
    con.commit()
    con.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
