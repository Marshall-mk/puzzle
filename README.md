# Puzzle Game

## 🚀 How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Set admin password (optional, defaults to admin123)
export ADMIN_PASSWORD="your_secure_password"

# Run the server
uvicorn app.src.main:app --host 0.0.0.0 --port 8000 --reload
```

**Access at:**
- Game: <http://localhost:8000>
- Admin: <http://localhost:8000/admin?password=admin123>

---

## ⚙️ Configuration

### Game Timings
- **Shuffle countdown**: 6 seconds
  - Location: `app/static/index.html:807`
  - Change: `startCountdown(6, ...)` → `startCountdown(YOUR_SECONDS, ...)`

- **Background rotation**: 10 seconds
  - Location: `app/static/index.html:666`
  - Change: `setInterval(changeBackground, 10000)` → `setInterval(changeBackground, YOUR_MS)`

### Database & Cleanup
- **Temp images cleanup**: 24 hours
  - Location: `app/src/main.py:104`
  - Change: `cleanup_temp_images(max_age_hours=24)` → `cleanup_temp_images(max_age_hours=YOUR_HOURS)`

- **Database location**: `app/db/game.db`
- **Data files**: `app/data/` (questions.json, player_data.json, winners.json)

### Admin Settings
- **Admin password**: Set via `ADMIN_PASSWORD` environment variable
- **Default**: `admin123`

---

## 🔒 Security Reminder

Before deploying to production:

1. Change the admin password via environment variable
2. Update CORS origins to your specific domain (app/src/main.py)
3. Never commit .env file or database files to git
