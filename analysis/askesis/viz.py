"""Visualization helpers for Askesis data."""

from typing import Optional, TYPE_CHECKING

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

if TYPE_CHECKING:
    from .db import AskesisDB


def setup_style():
    """Set up matplotlib style for Askesis visualizations."""
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "figure.figsize": (12, 6),
        "axes.titlesize": 14,
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.dpi": 100,
    })


def plot_weight_trend(
    db: "AskesisDB",
    rolling_window: int = 7,
    ax: Optional[plt.Axes] = None,
    show_rolling: bool = True
) -> plt.Axes:
    """
    Plot weight trend over time.

    Args:
        db: AskesisDB instance
        rolling_window: Window size for rolling average
        ax: Optional matplotlib Axes
        show_rolling: Whether to show rolling average line
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 5))

    weight = db.weight_series()
    if len(weight) == 0:
        ax.text(0.5, 0.5, "No weight data", ha="center", va="center", transform=ax.transAxes)
        return ax

    ax.scatter(weight.index, weight.values, alpha=0.5, s=30, label="Daily weight")

    if show_rolling and len(weight) >= rolling_window:
        rolling = weight.rolling(window=rolling_window, min_periods=1).mean()
        ax.plot(rolling.index, rolling.values, linewidth=2, color="coral", label=f"{rolling_window}-day average")

    ax.set_xlabel("Date")
    ax.set_ylabel("Weight (kg)")
    ax.set_title("Weight Trend")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45)
    plt.tight_layout()

    return ax


def plot_sleep_trend(
    db: "AskesisDB",
    rolling_window: int = 7,
    ax: Optional[plt.Axes] = None
) -> plt.Axes:
    """Plot sleep hours trend over time."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 5))

    sleep = db.sleep_series()
    if len(sleep) == 0:
        ax.text(0.5, 0.5, "No sleep data", ha="center", va="center", transform=ax.transAxes)
        return ax

    ax.bar(sleep.index, sleep.values, alpha=0.6, width=1, label="Sleep hours")

    if len(sleep) >= rolling_window:
        rolling = sleep.rolling(window=rolling_window, min_periods=1).mean()
        ax.plot(rolling.index, rolling.values, linewidth=2, color="purple", label=f"{rolling_window}-day average")

    ax.axhline(y=8, color="green", linestyle="--", alpha=0.5, label="8h target")
    ax.set_xlabel("Date")
    ax.set_ylabel("Hours")
    ax.set_title("Sleep Trend")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.xticks(rotation=45)
    plt.tight_layout()

    return ax


def plot_activity_calendar(
    db: "AskesisDB",
    ax: Optional[plt.Axes] = None
) -> plt.Axes:
    """Plot activity frequency as a calendar heatmap."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(14, 4))

    activities = db.activities.copy()
    if len(activities) == 0:
        ax.text(0.5, 0.5, "No activity data", ha="center", va="center", transform=ax.transAxes)
        return ax

    # Count activities per day
    daily = activities.groupby("date").size().reset_index(name="count")
    daily["date"] = pd.to_datetime(daily["date"])

    # Create a full date range
    date_range = pd.date_range(
        start=daily["date"].min(),
        end=daily["date"].max(),
        freq="D"
    )
    full_df = pd.DataFrame({"date": date_range})
    full_df = full_df.merge(daily, on="date", how="left").fillna(0)

    ax.scatter(
        full_df["date"],
        [1] * len(full_df),
        c=full_df["count"],
        cmap="Greens",
        s=100,
        marker="s"
    )
    ax.set_yticks([])
    ax.set_xlabel("Date")
    ax.set_title("Activity Calendar")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.tight_layout()

    return ax


def plot_calories_trend(
    db: "AskesisDB",
    rolling_window: int = 7,
    ax: Optional[plt.Axes] = None
) -> plt.Axes:
    """Plot daily calorie intake trend."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 5))

    calories = db.calories_by_date()
    if len(calories) == 0:
        ax.text(0.5, 0.5, "No calorie data", ha="center", va="center", transform=ax.transAxes)
        return ax

    ax.bar(calories.index, calories.values, alpha=0.6, width=1)

    if len(calories) >= rolling_window:
        rolling = calories.rolling(window=rolling_window, min_periods=1).mean()
        ax.plot(rolling.index, rolling.values, linewidth=2, color="orange", label=f"{rolling_window}-day average")

    ax.set_xlabel("Date")
    ax.set_ylabel("Calories")
    ax.set_title("Daily Calorie Intake")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.xticks(rotation=45)
    plt.tight_layout()

    return ax


def plot_measurement_progress(
    db: "AskesisDB",
    measurements: Optional[list[str]] = None,
    ax: Optional[plt.Axes] = None
) -> plt.Axes:
    """
    Plot body measurement progress over time.

    Args:
        db: AskesisDB instance
        measurements: List of measurement columns to plot (default: waist, chest, bicep_left)
        ax: Optional matplotlib Axes
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 5))

    df = db.measurements
    if len(df) == 0:
        ax.text(0.5, 0.5, "No measurement data", ha="center", va="center", transform=ax.transAxes)
        return ax

    if measurements is None:
        measurements = ["waist", "chest", "bicep_left"]

    for m in measurements:
        if m in df.columns:
            data = df[df[m].notna()]
            if len(data) > 0:
                ax.plot(data["date"], data[m], marker="o", label=m.replace("_", " ").title())

    ax.set_xlabel("Date")
    ax.set_ylabel("cm")
    ax.set_title("Body Measurements Progress")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.xticks(rotation=45)
    plt.tight_layout()

    return ax


def dashboard(db: "AskesisDB") -> plt.Figure:
    """
    Create a dashboard with multiple visualizations.

    Returns a matplotlib Figure with 4 subplots:
    - Weight trend
    - Sleep trend
    - Calories trend
    - Activity summary
    """
    setup_style()
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    plot_weight_trend(db, ax=axes[0, 0])
    plot_sleep_trend(db, ax=axes[0, 1])
    plot_calories_trend(db, ax=axes[1, 0])

    # Activity summary pie chart
    summary = db.activity_summary()
    if len(summary) > 0:
        axes[1, 1].pie(
            summary["count"],
            labels=summary.index,
            autopct="%1.0f%%",
            startangle=90
        )
        axes[1, 1].set_title("Activity Distribution")
    else:
        axes[1, 1].text(0.5, 0.5, "No activity data", ha="center", va="center")

    fig.suptitle(f"Askesis Dashboard - {db.meta.user_name}", fontsize=16)
    plt.tight_layout()

    return fig
