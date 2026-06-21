import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ETLPipeline:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.extracted: List[Dict[str, Any]] = []
        self.transformed: List[Dict[str, Any]] = []

    # ── EXTRACT ──────────────────────────────────────────────

    def extract_csv(self, filename: str) -> List[Dict[str, Any]]:
        filepath = self.data_dir / filename
        with open(filepath, newline="") as f:
            return list(csv.DictReader(f))

    def extract_json(self, filename: str) -> List[Dict[str, Any]]:
        filepath = self.data_dir / filename
        with open(filepath) as f:
            data = json.load(f)
            return data if isinstance(data, list) else [data]

    def extract_sqlite(self, db_name: str, query: str) -> List[Dict[str, Any]]:
        db_path = self.data_dir / db_name
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def run_extract(self, source_type: str, **kwargs) -> List[Dict[str, Any]]:
        extractors = {
            "csv": self.extract_csv,
            "json": self.extract_json,
            "sqlite": self.extract_sqlite,
        }
        handler = extractors.get(source_type)
        if not handler:
            raise ValueError(f"Unknown source type: {source_type}")
        self.extracted = handler(**kwargs)
        print(f"Extracted {len(self.extracted)} records from {source_type}")
        return self.extracted

    # ── TRANSFORM ────────────────────────────────────────────

    def clean_missing(self, data: List[Dict], fill: Any = "") -> List[Dict]:
        return [{k: (v if v is not None else fill) for k, v in row.items()} for row in data]

    def filter_rows(self, data: List[Dict], field: str, value: Any) -> List[Dict]:
        return [row for row in data if row.get(field) == value]

    def drop_columns(self, data: List[Dict], columns: List[str]) -> List[Dict]:
        return [{k: v for k, v in row.items() if k not in columns} for row in data]

    def rename_columns(self, data: List[Dict], mapping: Dict[str, str]) -> List[Dict]:
        return [{mapping.get(k, k): v for k, v in row.items()} for row in data]

    def add_metadata(self, data: List[Dict]) -> List[Dict]:
        timestamp = datetime.utcnow().isoformat()
        return [{**row, "etl_processed_at": timestamp} for row in data]

    def aggregate(
        self, data: List[Dict], group_by: str, agg_field: str, agg_func: str = "sum"
    ) -> List[Dict]:
        groups: Dict[str, List] = {}
        for row in data:
            key = row.get(group_by)
            groups.setdefault(key, []).append(row)

        results = []
        for key, rows in groups.items():
            values = [r.get(agg_field, 0) or 0 for r in rows]
            if agg_func == "sum":
                result = sum(values)
            elif agg_func == "avg":
                result = sum(values) / len(values) if values else 0
            elif agg_func == "count":
                result = len(values)
            else:
                raise ValueError(f"Unknown agg function: {agg_func}")
            results.append({group_by: key, f"{agg_field}_{agg_func}": result})
        return results

    def run_transform(
        self,
        steps: Optional[List[Dict]] = None,
        data: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        data = data or self.extracted
        steps = steps or [
            {"type": "clean_missing", "fill": ""},
            {"type": "add_metadata"},
        ]

        pipeline = {
            "clean_missing": self.clean_missing,
            "filter_rows": self.filter_rows,
            "drop_columns": self.drop_columns,
            "rename_columns": self.rename_columns,
            "add_metadata": self.add_metadata,
            "aggregate": self.aggregate,
        }

        for step in steps:
            step_type = step.pop("type")
            handler = pipeline.get(step_type)
            if not handler:
                raise ValueError(f"Unknown transform step: {step_type}")
            data = handler(data, **step)
            print(f"  → Applied {step_type} ({len(data)} records)")

        self.transformed = data
        return self.transformed

    # ── LOAD ─────────────────────────────────────────────────

    def load_csv(self, data: List[Dict], filename: str):
        filepath = self.data_dir / filename
        if not data:
            print("No data to load")
            return
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        print(f"Loaded {len(data)} records → {filepath}")

    def load_json(self, data: List[Dict], filename: str):
        filepath = self.data_dir / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Loaded {len(data)} records → {filepath}")

    def load_sqlite(self, data: List[Dict], db_name: str, table: str):
        db_path = self.data_dir / db_name
        conn = sqlite3.connect(db_path)
        if data:
            cols = ", ".join(data[0].keys())
            placeholders = ", ".join("?" for _ in data[0])
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.execute(f"CREATE TABLE {table} ({cols})")
            rows = [tuple(row.values()) for row in data]
            conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
            conn.commit()
        conn.close()
        print(f"Loaded {len(data)} records → {db_name}.{table}")

    def run_load(self, target_type: str, **kwargs):
        loaders = {
            "csv": self.load_csv,
            "json": self.load_json,
            "sqlite": self.load_sqlite,
        }
        handler = loaders.get(target_type)
        if not handler:
            raise ValueError(f"Unknown target type: {target_type}")
        handler(self.transformed or self.extracted, **kwargs)

    # ── RUN FULL PIPELINE ────────────────────────────────────

    def run(
        self,
        source_type: str,
        source_kwargs: Dict,
        transform_steps: List[Dict],
        target_type: str,
        target_kwargs: Dict,
    ):
        print(f"[ETL] Starting pipeline at {datetime.utcnow().isoformat()}")
        self.run_extract(source_type, **source_kwargs)
        self.run_transform(steps=transform_steps)
        self.run_load(target_type, **target_kwargs)
        print(f"[ETL] Pipeline completed at {datetime.utcnow().isoformat()}")
        return self.transformed


# ── EXAMPLE USAGE ──────────────────────────────────────────

if __name__ == "__main__":
    pipeline = ETLPipeline()

    pipeline.run(
        source_type="csv",
        source_kwargs={"filename": "orders.csv"},
        transform_steps=[
            {"type": "clean_missing", "fill": 0},
            {"type": "drop_columns", "columns": ["internal_note"]},
            {"type": "filter_rows", "field": "status", "value": "completed"},
            {"type": "add_metadata"},
        ],
        target_type="sqlite",
        target_kwargs={"db_name": "warehouse.db", "table": "orders_clean"},
    )
