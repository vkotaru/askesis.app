"""Load Askesis SQLite exports into pandas DataFrames."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


@dataclass
class ExportMeta:
    """Metadata about the export."""
    schema_version: int
    exported_at: datetime
    user_id: int
    user_email: str
    user_name: str


class AskesisDB:
    """
    Load and analyze Askesis health tracking data.

    Usage:
        db = AskesisDB("path/to/askesis-2024-03-09.db")

        # Access DataFrames
        db.daily_logs
        db.activities
        db.meals
        db.measurements

        # Metadata
        db.meta.user_name
        db.meta.exported_at
    """

    def __init__(self, db_path: str | Path):
        """Load an Askesis SQLite export."""
        self.path = Path(db_path)
        if not self.path.exists():
            raise FileNotFoundError(f"Database not found: {self.path}")

        self._conn = sqlite3.connect(str(self.path))
        self._meta: Optional[ExportMeta] = None
        self._daily_logs: Optional[pd.DataFrame] = None
        self._meals: Optional[pd.DataFrame] = None
        self._activities: Optional[pd.DataFrame] = None
        self._exercises: Optional[pd.DataFrame] = None
        self._measurements: Optional[pd.DataFrame] = None
        self._photos: Optional[pd.DataFrame] = None
        self._settings: Optional[pd.DataFrame] = None

    def close(self):
        """Close the database connection."""
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @property
    def meta(self) -> ExportMeta:
        """Export metadata."""
        if self._meta is None:
            df = pd.read_sql("SELECT key, value FROM _export_meta", self._conn)
            meta_dict = dict(zip(df["key"], df["value"]))
            self._meta = ExportMeta(
                schema_version=int(meta_dict["schema_version"]),
                exported_at=datetime.fromisoformat(meta_dict["exported_at"]),
                user_id=int(meta_dict["user_id"]),
                user_email=meta_dict["user_email"],
                user_name=meta_dict["user_name"],
            )
        return self._meta

    @property
    def daily_logs(self) -> pd.DataFrame:
        """Daily log entries with weight, sleep, steps, etc."""
        if self._daily_logs is None:
            self._daily_logs = pd.read_sql(
                "SELECT * FROM daily_logs ORDER BY date",
                self._conn,
                parse_dates=["date", "created_at"]
            )
            # Convert ate_outside to boolean
            if "ate_outside" in self._daily_logs.columns:
                self._daily_logs["ate_outside"] = self._daily_logs["ate_outside"].astype(bool)
        return self._daily_logs

    @property
    def meals(self) -> pd.DataFrame:
        """Meal entries with calories and descriptions."""
        if self._meals is None:
            self._meals = pd.read_sql(
                "SELECT * FROM meals ORDER BY date, time",
                self._conn,
                parse_dates=["date", "created_at"]
            )
        return self._meals

    @property
    def activities(self) -> pd.DataFrame:
        """Activity/workout entries."""
        if self._activities is None:
            self._activities = pd.read_sql(
                "SELECT * FROM activities ORDER BY date",
                self._conn,
                parse_dates=["date", "created_at"]
            )
        return self._activities

    @property
    def exercises(self) -> pd.DataFrame:
        """Individual exercises within strength activities."""
        if self._exercises is None:
            self._exercises = pd.read_sql(
                "SELECT * FROM exercises",
                self._conn
            )
        return self._exercises

    @property
    def measurements(self) -> pd.DataFrame:
        """Body measurements (chest, waist, arms, etc.)."""
        if self._measurements is None:
            self._measurements = pd.read_sql(
                "SELECT * FROM body_measurements ORDER BY date",
                self._conn,
                parse_dates=["date", "created_at"]
            )
        return self._measurements

    @property
    def photos(self) -> pd.DataFrame:
        """Progress photo metadata."""
        if self._photos is None:
            self._photos = pd.read_sql(
                "SELECT * FROM progress_photos ORDER BY date",
                self._conn,
                parse_dates=["date", "created_at"]
            )
        return self._photos

    @property
    def settings(self) -> pd.DataFrame:
        """User settings."""
        if self._settings is None:
            self._settings = pd.read_sql(
                "SELECT * FROM user_settings",
                self._conn
            )
        return self._settings

    # Convenience methods

    def weight_series(self) -> pd.Series:
        """Get weight as a time series indexed by date."""
        df = self.daily_logs[self.daily_logs["weight"].notna()].copy()
        return df.set_index("date")["weight"]

    def sleep_series(self) -> pd.Series:
        """Get sleep hours as a time series indexed by date."""
        df = self.daily_logs[self.daily_logs["sleep_hours"].notna()].copy()
        return df.set_index("date")["sleep_hours"]

    def steps_series(self) -> pd.Series:
        """Get steps as a time series indexed by date."""
        df = self.daily_logs[self.daily_logs["steps"].notna()].copy()
        return df.set_index("date")["steps"]

    def calories_by_date(self) -> pd.Series:
        """Get total calories per day."""
        return self.meals.groupby("date")["calories"].sum()

    def activity_summary(self) -> pd.DataFrame:
        """Summarize activities by type."""
        return self.activities.groupby("activity_type").agg({
            "id": "count",
            "duration_mins": "sum",
            "calories": "sum",
            "distance_km": "sum"
        }).rename(columns={"id": "count"})

    def measurement_changes(self) -> pd.DataFrame:
        """
        Calculate changes in body measurements from first to last entry.
        """
        if len(self.measurements) < 2:
            return pd.DataFrame()

        first = self.measurements.iloc[0]
        last = self.measurements.iloc[-1]

        cols = [
            "neck", "shoulders", "chest", "bicep_left", "bicep_right",
            "forearm_left", "forearm_right", "waist", "abdomen", "hips",
            "thigh_left", "thigh_right", "calf_left", "calf_right"
        ]

        data = []
        for col in cols:
            if pd.notna(first[col]) and pd.notna(last[col]):
                data.append({
                    "measurement": col,
                    "first": first[col],
                    "last": last[col],
                    "change": last[col] - first[col],
                    "change_pct": ((last[col] - first[col]) / first[col]) * 100
                })

        return pd.DataFrame(data)

    def __repr__(self) -> str:
        return (
            f"AskesisDB('{self.path.name}')\n"
            f"  User: {self.meta.user_name}\n"
            f"  Exported: {self.meta.exported_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"  Daily logs: {len(self.daily_logs)}\n"
            f"  Meals: {len(self.meals)}\n"
            f"  Activities: {len(self.activities)}\n"
            f"  Measurements: {len(self.measurements)}"
        )


def load_db(path: str | Path) -> AskesisDB:
    """
    Load an Askesis SQLite export.

    Args:
        path: Path to the .db file

    Returns:
        AskesisDB instance with lazy-loaded DataFrames

    Example:
        >>> db = load_db("~/Downloads/askesis-2024-03-09.db")
        >>> db.daily_logs.head()
        >>> db.weight_series().plot()
    """
    return AskesisDB(path)
