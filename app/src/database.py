"""
Database operations for the eHealth Puzzle Game
"""
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Tuple

DATABASE_FILE = "app/db/game.db"


def init_db():
    """Initialize the SQLite database with required tables."""
    connection = sqlite3.connect(DATABASE_FILE)
    cursor = connection.cursor()

    # Create players table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            total_score INTEGER DEFAULT 0
        )
    """)

    # Create scores table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT NOT NULL,
            level TEXT NOT NULL,
            score INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(player_id)
        )
    """)

    connection.commit()
    connection.close()
    print("Database initialized successfully.")


def register_player(player_id: str, username: str) -> Tuple[bool, Optional[str]]:
    """
    Register a new player in the database.
    Returns (success, error_message)
    """
    try:
        connection = sqlite3.connect(DATABASE_FILE)
        cursor = connection.cursor()

        # Check if username already exists
        cursor.execute("SELECT * FROM players WHERE username = ?", (username,))
        if cursor.fetchone():
            connection.close()
            return False, "Username already exists"

        # Insert new player
        cursor.execute("""
            INSERT INTO players (player_id, username)
            VALUES (?, ?)
        """, (player_id, username))

        connection.commit()
        connection.close()
        return True, None

    except Exception as e:
        return False, str(e)


def save_score(player_id: str, level: str, weighted_score: int) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Save a player's score for a level.
    Returns (success, total_score, error_message)
    """
    try:
        connection = sqlite3.connect(DATABASE_FILE)
        cursor = connection.cursor()

        # Insert the level score
        cursor.execute("""
            INSERT INTO scores (player_id, level, score, timestamp)
            VALUES (?, ?, ?, ?)
        """, (player_id, level, int(weighted_score), datetime.now().isoformat()))

        # Update total_score in players table
        cursor.execute("""
            UPDATE players
            SET total_score = (
                SELECT SUM(score)
                FROM scores
                WHERE player_id = ?
            )
            WHERE player_id = ?
        """, (player_id, player_id))

        # Get updated total score
        cursor.execute("SELECT total_score FROM players WHERE player_id = ?", (player_id,))
        result = cursor.fetchone()
        total_score = result[0] if result else 0

        connection.commit()
        connection.close()

        return True, total_score, None

    except Exception as e:
        return False, None, str(e)


def get_winners() -> List[Dict]:
    """
    Get the player(s) with the highest total score.
    Returns list of winner dictionaries.
    """
    try:
        connection = sqlite3.connect(DATABASE_FILE)
        cursor = connection.cursor()

        cursor.execute("""
            SELECT p.username, p.player_id, p.total_score,
                   MIN(s.timestamp) as start_time,
                   MAX(s.timestamp) as end_time
            FROM players p
            LEFT JOIN scores s ON p.player_id = s.player_id
            GROUP BY p.player_id
            ORDER BY p.total_score DESC, end_time ASC
            LIMIT 10
        """)

        winners_data = cursor.fetchall()
        connection.close()

        if not winners_data:
            return []

        max_score = winners_data[0][2] if winners_data else 0
        winners = []

        for row in winners_data:
            if row[2] == max_score:
                winners.append({
                    "username": row[0],
                    "player_id": row[1],
                    "total_score": row[2],
                    "start_time": row[3],
                    "end_time": row[4]
                })

        return winners

    except Exception as e:
        print(f"Error getting winners: {e}")
        return []


def get_max_score() -> int:
    """Get the current maximum score."""
    winners = get_winners()
    return winners[0]["total_score"] if winners else 0


def get_player_by_username(username: str) -> Optional[Dict]:
    """
    Get player information by username.
    Returns player dict or None if not found.
    """
    try:
        connection = sqlite3.connect(DATABASE_FILE)
        cursor = connection.cursor()

        cursor.execute("""
            SELECT player_id, username, total_score
            FROM players
            WHERE username = ?
        """, (username,))

        result = cursor.fetchone()
        connection.close()

        if result:
            return {
                "player_id": result[0],
                "username": result[1],
                "total_score": result[2]
            }
        return None

    except Exception as e:
        print(f"Error getting player by username: {e}")
        return None


def get_player_progress(player_id: str) -> Dict:
    """
    Get player's progress (completed levels).
    Returns dict with level completion status.
    """
    try:
        connection = sqlite3.connect(DATABASE_FILE)
        cursor = connection.cursor()

        # Get all levels completed by the player
        cursor.execute("""
            SELECT DISTINCT level
            FROM scores
            WHERE player_id = ?
            ORDER BY level
        """, (player_id,))

        completed_levels = [row[0] for row in cursor.fetchall()]
        connection.close()

        # Determine next level to play
        all_levels = ["level_1", "level_2", "level_3", "level_4"]

        # Find the first incomplete level, or last level if all complete
        next_level = None
        for level in all_levels:
            if level not in completed_levels:
                next_level = level
                break

        # If all levels are completed, restart from level_1
        if next_level is None:
            next_level = "level_1"

        return {
            "completed_levels": completed_levels,
            "next_level": next_level
        }

    except Exception as e:
        print(f"Error getting player progress: {e}")
        return {
            "completed_levels": [],
            "next_level": "level_1"
        }
