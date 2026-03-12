Project Askesis

A web-app to tracking everything related to health, fitness, diet, sleep, training for my family, me and my spouse. Google oauth with just allowed emails.

Reactive UI
Easy color scheme good for ADHD
Customizability

- Light/Dark/System
- Font size
- Fonts, (with Space Grotesk a must)
- Allow size of the central modal. (center the modal)

UX Principles (ADHD-friendly)

- Minimal clicks to log data
- Visual progress indicators (streaks, charts, completion rings)
- No walls of text - scannable layouts
- Satisfying micro-interactions (animations on save, streak celebrations)
- Quick-entry modes throughout (templates, "copy from yesterday", favorites)

After Login, (user specific info below)

- Dashboard showing summary of all metrics
- Another dashboard showing Mine & My spouse's metrics
- Training Calendar
- Entry Page
  - Daily Log
    - Weight
    - Sleep
    - Steps
    - Water Intake
    - Mood/Energy (1-5 scale, correlates with other metrics)
    - Caffeine Intake (affects sleep interpretation)
    - Notes
  - Nutrition Log
    - Flexible meal count (not fixed to 3 meals - some days 2, some days 5)
    - Each meal entry:
      - Label (Breakfast, Lunch, Dinner, Snack, or custom)
      - Calories
      - Time
      - Text (description of eaten food)
    - Quick-entry: "Same as yesterday" for recurring meals, saved meal templates
  - Activities
    - Each day there can be multiple activities.
      - Activity
        - Name
        - Type (Cardio/Strength)
        - Duration
        - Calories
        - Distance
        - Notes
        - Tags (Commute, Training, Race, Social, Fun, Weekend)
      - For strength
        - Include the exercises done with sets and reps.
    - Quick-entry: Saved workout templates (e.g., "Morning Run", "Leg Day")

Tech Stack

- Frontend: SvelteKit
- Backend: FastAPI (Python)
- Database: SQLite (WAL mode)
- ORM: SQLAlchemy + Alembic (migrations)
- Auth: Google OAuth (allowlisted emails only)
- Icons: Lucide Svelte
- Styling: Tailwind CSS
- Deploy: Railway + persistent volume

Future Plans:

- AI integration
  - Integrate Garmin, Apple Health, Google Fit, etc. to pull data automatically.
  - AI to suggest workouts, diet plans, etc. based on the data.
- Python analysis scripts (GP prediction, correlations) querying SQLite directly
