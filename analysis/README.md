# Askesis Analysis

Python package for analyzing your Askesis health tracking data.

## Installation

```bash
cd analysis
pip install -e .

# With Jupyter support
pip install -e ".[dev]"
```

## Quick Start

1. **Export your data** from Askesis Settings page → "Export Data"
2. **Load in Python**:

```python
from askesis import load_db, viz

# Load your exported database
db = load_db("~/Downloads/askesis-2024-03-09.db")

# View summary
print(db)
# AskesisDB('askesis-2024-03-09.db')
#   User: John Doe
#   Exported: 2024-03-09 14:30
#   Daily logs: 365
#   Meals: 1095
#   Activities: 156
#   Measurements: 12

# Access DataFrames
db.daily_logs      # Daily weight, sleep, steps, etc.
db.meals           # Meal entries with calories
db.activities      # Workouts and exercises
db.measurements    # Body measurements

# Convenience methods
db.weight_series()        # Weight as time series
db.sleep_series()         # Sleep hours as time series
db.calories_by_date()     # Daily calorie totals
db.activity_summary()     # Activity stats by type
db.measurement_changes()  # First vs last measurements
```

## Visualizations

```python
import matplotlib.pyplot as plt
from askesis import viz

# Setup matplotlib style
viz.setup_style()

# Individual plots
viz.plot_weight_trend(db)
viz.plot_sleep_trend(db)
viz.plot_calories_trend(db)
viz.plot_measurement_progress(db)
viz.plot_activity_calendar(db)

# Full dashboard
fig = viz.dashboard(db)
plt.show()
```

## Notebooks

See `notebooks/exploration.ipynb` for an interactive example.

```bash
cd analysis
jupyter notebook notebooks/exploration.ipynb
```

## Data Schema

The exported SQLite database contains:

| Table | Description |
|-------|-------------|
| `daily_logs` | Daily weight, sleep, steps, water, feelings |
| `meals` | Meal entries with calories, time, descriptions |
| `activities` | Workouts with type, duration, distance |
| `exercises` | Individual exercises within activities |
| `body_measurements` | Body measurements (chest, waist, arms, etc.) |
| `progress_photos` | Photo metadata (not actual files) |
| `user_settings` | Theme, units, preferences |
| `_export_meta` | Export metadata (version, timestamp, user) |
