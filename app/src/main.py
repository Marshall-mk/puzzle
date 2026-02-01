# Importing libraries
import os
import random
import numpy as np
from PIL import Image
from fastapi import FastAPI, Form, Header, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
import shutil
from app.src.config import get_grid_size, set_grid_size, get_countdown_time, set_countdown_time
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import json
from fastapi import Request
import uuid
from datetime import datetime, timedelta
import re
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from typing import Optional
import glob
import time

# Import our modules
from app.src.database import init_db, register_player, get_winners, get_max_score
from app.src.database import save_score as db_save_score, get_player_by_username, get_player_progress
from app.src.sessions import (
    get_or_create_session,
    get_session,
    cleanup_expired_sessions,
    game_sessions
)

# Creating API object
app = FastAPI()

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Load image metadata from JSON
with open("app/data/questions.json", "r") as f:
    image_metadata = json.load(f)

# Admin password from environment variable (default for development only)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


def cleanup_temp_images(max_age_hours: int = 24):
    """
    Clean up temporary images older than max_age_hours.
    This helps prevent the temp folder from growing indefinitely.
    """
    try:
        temp_folder = "app/static/images/temp"

        # Ensure temp folder exists
        if not os.path.exists(temp_folder):
            return

        current_time = datetime.now()

        # Get all image files in temp folder
        temp_images = glob.glob(f"{temp_folder}/*.jpg")

        removed_count = 0
        for image_path in temp_images:
            # Get file modification time
            file_mtime = datetime.fromtimestamp(os.path.getmtime(image_path))
            age = current_time - file_mtime

            # Remove if older than max_age_hours
            if age > timedelta(hours=max_age_hours):
                os.remove(image_path)
                removed_count += 1
                print(f"Removed old temp image: {image_path}")

        if removed_count > 0:
            print(f"Cleaned up {removed_count} old temporary images")

    except Exception as e:
        print(f"Error during temp image cleanup: {e}")


# Define the root url
@app.get("/")
def serve_html():
    """Serve the main HTML file."""
    return FileResponse("app/static/index.html")

# Load images
@app.get("/image")
def get_image(session_id: Optional[str] = Header(None, alias="X-Session-ID")):
    """Serve a random image from the current level and its metadata."""
    # Cleanup expired sessions and old temp images periodically
    cleanup_expired_sessions()
    cleanup_temp_images(max_age_hours=24)  # Remove temp images older than 24 hours

    # Get or create session
    session_id = get_or_create_session(session_id)
    session = game_sessions[session_id]
    print(f"Session ID for /image: {session_id[:8]}... (total sessions: {len(game_sessions)})")

    current_level = session["current_level"]

    if current_level not in image_metadata:
        return JSONResponse({"error": "Level data not found"}, status_code=404)

    level_data = image_metadata[current_level]
    if not level_data:
        return JSONResponse({"error": "No images available in the current level"}, status_code=404)

    # Select a random image
    image_name = random.choice(list(level_data.keys()))
    session["current_image_name"] = image_name  # Save selected image name

    # Build file path
    image_path = f"app/static/images/{current_level}/{image_name}"
    print(f"Attempting to load image from path: {image_path}")  # Debugging output

    # Check if the image exists
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")  # Debugging output
        return JSONResponse({"error": f"Image not found: {image_path}"}, status_code=404)

    # Set start time if not already set
    if session["start_time"] is None:
        session["start_time"] = datetime.now()
        print(f"Start time recorded: {session['start_time']}")  # Debugging output

    # Return image metadata
    metadata = level_data[image_name]
    return JSONResponse({
        "image_url": f"/static/images/{current_level}/{image_name}",
        "metadata": metadata,
        "start_time": session["start_time"].isoformat(),
        "session_id": session_id
    })




### Perform shuffling
@app.post("/shuffle")
def shuffle_image(session_id: Optional[str] = Header(None, alias="X-Session-ID")):
    """Shuffle the image into a grid."""
    try:
        print(f"[/shuffle] Received session_id: {session_id[:8] if session_id else 'None'}...")
        print(f"[/shuffle] Active sessions: {len(game_sessions)}, Session IDs: {[sid[:8] for sid in game_sessions.keys()]}")

        # Get or create session (handle server restarts gracefully)
        if not session_id or session_id not in game_sessions:
            print(f"WARNING: Invalid/missing session {session_id}, returning error")
            return JSONResponse({
                "error": "Session expired or invalid. Please refresh the page to start a new game.",
                "session_expired": True
            }, status_code=400)

        session = game_sessions[session_id]
        print(f"[/shuffle] Found session, current_level: {session['current_level']}, current_image: {session.get('current_image_name')}")
        current_level = session["current_level"]
        current_image_name = session["current_image_name"]

        # Validate session state
        if current_image_name is None:
            return JSONResponse({"error": "No image selected. Please load an image first."}, status_code=400)

        if current_level not in image_metadata:
            return JSONResponse({"error": "Invalid level"}, status_code=400)

        # Verify the image exists in the current level's metadata
        if current_image_name not in image_metadata[current_level]:
            return JSONResponse({"error": f"Image {current_image_name} not found in {current_level}"}, status_code=400)

        # Set patch size dynamically based on config
        grid_size = get_grid_size()
        patch_size = 512 // grid_size
        target_size = patch_size * grid_size # Ensure image is perfectly divisible

        # Debugging output
        print(f"Level: {current_level}, Grid Size: {grid_size}, PATCH_SIZE: {patch_size}, Target Size: {target_size}")

        # Ensure a valid image is selected
        if current_image_name is None:
            return JSONResponse({"error": "No image selected"}, status_code=400)

        image_path = f"app/static/images/{current_level}/{current_image_name}"

        # Check if the selected image exists
        if not os.path.exists(image_path):
            print(f"ERROR: Image not found at path: {image_path}")
            return JSONResponse({"error": "Image not found"}, status_code=404)

        # Open and process the image
        print(f"Opening image: {image_path}")
        img = Image.open(image_path).resize((target_size, target_size)).convert("L")  # Grayscale conversion
        img_array = np.array(img)

        # Divide the image into patches
        h, w = img_array.shape[:2]
        # Verify shape matching
        if h % patch_size != 0 or w % patch_size != 0:
             # This shouldn't happen if we resized to target_size
             pass

        patches = (
            img_array.reshape(h // patch_size, patch_size, -1, patch_size)
            .swapaxes(1, 2)
            .reshape(-1, patch_size, patch_size)
        )

        # Store patches in session
        session["patches"] = patches.tolist()  # Convert to list for JSON serialization
        session["original_positions"] = list(range(len(patches)))
        session["shuffled_positions"] = session["original_positions"].copy()

        # Shuffle the positions
        random.shuffle(session["shuffled_positions"])

        # Reconstruct the shuffled image
        shuffled_image = np.zeros_like(img_array)
        index = 0
        for i in range(0, h, patch_size):
            for j in range(0, w, patch_size):
                shuffled_image[i:i + patch_size, j:j + patch_size] = patches[session["shuffled_positions"][index]]
                index += 1

        # Ensure temp directory exists
        temp_dir = "app/static/images/temp"
        os.makedirs(temp_dir, exist_ok=True)

        # Save the shuffled image with unique name per session, level, and timestamp in temp folder
        timestamp = int(time.time() * 1000)
        shuffled_image_path = f"app/static/images/temp/shuffled_{session_id[:8]}_{current_level}_{timestamp}.jpg"

        print(f"Saving shuffled image to: {shuffled_image_path}")
        Image.fromarray(shuffled_image).save(shuffled_image_path)

        # Verify file was created
        if os.path.exists(shuffled_image_path):
            print(f"✓ Shuffled image created successfully: {shuffled_image_path}")
        else:
            print(f"✗ ERROR: Failed to create shuffled image at: {shuffled_image_path}")
            return JSONResponse({"error": "Failed to create shuffled image"}, status_code=500)

        # Store the current shuffled image path in session
        session["current_shuffled_image_path"] = shuffled_image_path

        shuffled_url = f"/static/images/temp/shuffled_{session_id[:8]}_{current_level}_{timestamp}.jpg"
        print(f"Returning shuffled image URL: {shuffled_url}")

        return JSONResponse({
            "shuffled_image_url": shuffled_url,
            "grid_size": grid_size
        })

    except Exception as e:
        print(f"✗ ERROR in shuffle_image: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": f"Shuffle failed: {str(e)}"}, status_code=500)


#####perform swapping
@app.post("/swap")
def swap_patches(
    index1: int = Form(...),
    index2: int = Form(...),
    session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Swap two patches in the shuffled image and return the updated image URL.
    """
    try:
        # Get session
        if not session_id or session_id not in game_sessions:
            return JSONResponse({"error": "Invalid session"}, status_code=400)

        session = game_sessions[session_id]
        shuffled_positions = session.get("shuffled_positions")
        patches_list = session.get("patches")

        # Ensure valid data exists for swapping
        if shuffled_positions is None or patches_list is None:
            return JSONResponse({"error": "No puzzle to swap"}, status_code=400)

        # Convert patches back to numpy array
        patches = np.array(patches_list)

        # Set patch size dynamically based on config
        grid_size = get_grid_size()
        patch_size = 512 // grid_size
        # Validate indices
        total_patches = len(shuffled_positions)
        if index1 < 0 or index2 < 0 or index1 >= total_patches or index2 >= total_patches:
            return JSONResponse({"error": "Invalid indices"}, status_code=400)

        # Debugging output
        print(f"Before swap: {shuffled_positions}")
        print(f"Swapping patches: {index1} <-> {index2}")

        # Swap positions in the shuffled list
        shuffled_positions[index1], shuffled_positions[index2] = shuffled_positions[index2], shuffled_positions[index1]
        session["shuffled_positions"] = shuffled_positions

        # Debugging output
        print(f"After swap: {shuffled_positions}")

        # Reconstruct the updated image based on the new shuffled positions
        target_size = patch_size * grid_size
        updated_image = np.zeros((target_size, target_size), dtype=np.uint8)  # Grayscale image

        index = 0
        for i in range(0, target_size, patch_size):
            for j in range(0, target_size, patch_size):
                patch = patches[shuffled_positions[index]]

                # Ensure patch size matches the calculated patch size
                if patch.shape != (patch_size, patch_size):
                    raise ValueError(
                        f"Patch at index {index} has invalid dimensions: {patch.shape}. Expected: ({patch_size}, {patch_size})"
                    )

                updated_image[i:i + patch_size, j:j + patch_size] = patch
                index += 1

        # Ensure temp directory exists
        temp_dir = "app/static/images/temp"
        os.makedirs(temp_dir, exist_ok=True)

        # Save the updated image with unique name per session, level, and timestamp in temp folder
        timestamp = int(time.time() * 1000)
        updated_image_path = f"app/static/images/temp/updated_{session_id[:8]}_{session['current_level']}_{timestamp}.jpg"

        print(f"Saving updated image to: {updated_image_path}")
        Image.fromarray(updated_image).save(updated_image_path)

        # Verify file was created
        if os.path.exists(updated_image_path):
            print(f"✓ Updated image created successfully")
        else:
            print(f"✗ ERROR: Failed to create updated image")
            return JSONResponse({"error": "Failed to create updated image"}, status_code=500)

        # Update session to track the latest image
        session["current_shuffled_image_path"] = updated_image_path

        updated_url = f"/static/images/temp/updated_{session_id[:8]}_{session['current_level']}_{timestamp}.jpg"
        print(f"Returning updated image URL: {updated_url}")

        return JSONResponse({"updated_image_url": updated_url})

    except Exception as e:
        print(f"✗ ERROR in swap_patches: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": f"Swap failed: {str(e)}"}, status_code=500)



##### Validating the swapped result
@app.post("/validate")
def validate_puzzle(session_id: Optional[str] = Header(None, alias="X-Session-ID")):
    """
    Validate the current arrangement of the grid.
    Checks if the shuffled_positions match the original_positions.
    """
    # Get session
    if not session_id or session_id not in game_sessions:
        return JSONResponse({"error": "Invalid session"}, status_code=400)

    session = game_sessions[session_id]
    original_positions = session.get("original_positions")
    shuffled_positions = session.get("shuffled_positions")

    # Ensure the positions are initialized
    if original_positions is None or shuffled_positions is None:
        return JSONResponse({"error": "No puzzle to validate"}, status_code=400)

    # Check if the shuffled positions match the original positions
    is_correct = shuffled_positions == original_positions

    # Return the validation result
    return JSONResponse({"is_correct": is_correct})


# Fetching questions
@app.get("/questions")
def get_questions(session_id: Optional[str] = Header(None, alias="X-Session-ID")):
    """Serve questions related to the current image."""
    # Get session
    if not session_id or session_id not in game_sessions:
        return JSONResponse({"error": "Invalid session"}, status_code=400)

    session = game_sessions[session_id]
    current_level = session["current_level"]
    current_image_name = session["current_image_name"]

    if current_image_name is None or current_level not in image_metadata:
        return JSONResponse({"error": "No image or level selected"}, status_code=400)

    # Fetch questions for the current image
    level_data = image_metadata[current_level]
    image_data = level_data.get(current_image_name)
    if not image_data:
        return JSONResponse({"error": "Image data not found"}, status_code=404)

    # Return the questions
    return {"questions": image_data.get("questions", [])}


# Check answers
@app.post("/check_answers")
async def check_answers(request: Request):
    """Validate the player's answers."""
    # Log the incoming request
    print("Checking answers...")

    # Get session ID from request
    session_id = request.headers.get("X-Session-ID")
    if not session_id or session_id not in game_sessions:
        return JSONResponse({"error": "Invalid session"}, status_code=400)

    session = game_sessions[session_id]
    current_level = session["current_level"]
    current_image_name = session["current_image_name"]

    # Ensure an image is selected
    if current_image_name is None:
        print("Error: No image selected.")
        return JSONResponse({"error": "No image selected"}, status_code=400)

    # Get the questions for the current image
    level_data = image_metadata[current_level]
    image_data = level_data.get(current_image_name)
    if not image_data:
        print("Error: Image data not found.")
        return JSONResponse({"error": "Image data not found"}, status_code=404)

    # Parse player's answers from the request body
    data = await request.json()
    print(f"Received data: {data}")
    player_answers = data.get("answers", [])

    # Validate answers
    questions = image_data["questions"]
    score = 0
    detailed_results = []

    for player_answer in player_answers:
        index = player_answer.get("index")
        answer = player_answer.get("answer")

        if index is not None and index < len(questions):
            correct_answer = questions[index]["answer"]
            is_correct = answer == correct_answer
            if is_correct:
                score += 1  # Increment score for each correct answer
            detailed_results.append({
                "question": questions[index]["question"],
                "player_answer": answer,
                "correct_answer": correct_answer,
                "is_correct": is_correct
            })

    print(f"Score: {score}, Detailed Results: {detailed_results}")
    # Return the result
    return JSONResponse({"score": score, "total_questions": len(questions), "details": detailed_results})



# Endpoint to proceed to next level
@app.post("/next_level")
def next_level(session_id: Optional[str] = Header(None, alias="X-Session-ID")):
    """Progress to the next level."""
    # Get session
    if not session_id or session_id not in game_sessions:
        return JSONResponse({"error": "Invalid session"}, status_code=400)

    session = game_sessions[session_id]
    current_level = session["current_level"]

    levels = list(image_metadata.keys())
    current_index = levels.index(current_level) if current_level in levels else -1

    if current_index < len(levels) - 1:
        session["current_level"] = levels[current_index + 1]
        session["current_image_name"] = None  # Reset current image for the new level

        # Clear all puzzle state to prevent stale data
        session["patches"] = None
        session["shuffled_positions"] = None
        session["original_positions"] = None
        session["start_time"] = None
        session["current_shuffled_image_path"] = None

        return JSONResponse({"message": "Progressed to the next level", "level": session["current_level"]})
    else:
        return JSONResponse({"message": "You have completed all levels!", "level": None})
    
    

@app.on_event("startup")
def ensure_directories():
    """Ensure required directories exist at startup."""
    # Ensure temp images directory exists
    temp_dir = "app/static/images/temp"
    os.makedirs(temp_dir, exist_ok=True)

    # Ensure player_data.json file exists (legacy support)
    player_data_path = "app/data/player_data.json"
    if not os.path.exists(player_data_path):
        with open(player_data_path, "w") as f:
            json.dump({"players": []}, f, indent=4)
        print("player_data.json file created.")


# Scoring
@app.post("/save_score")
@limiter.limit("10/minute")
async def save_score(request: Request):
    """Save the player's score for the current level with a timestamp."""
    # Get session ID from request
    session_id = request.headers.get("X-Session-ID")
    if session_id and session_id in game_sessions:
        session = game_sessions[session_id]
        start_time = session.get("start_time")
    else:
        start_time = None

    data = await request.json()
    print("Received data at /save_score:", data)  # Log received data

    player_id = data.get("player_id")
    level = data.get("level")
    score = data.get("score")

    print(f"Player ID: {player_id}, Level: {level}, Score: {score}")  # Detailed log

    if not player_id or not level or score is None:
        return JSONResponse({"error": "Invalid data"}, status_code=400)

    # Define weights for each level
    label_weights = {
        "level_1": {"weight": 10, "num_questions": 3},  # 10% weight, 3 questions
        "level_2": {"weight": 20, "num_questions": 3},  # 20% weight, 3 questions
        "level_3": {"weight": 30, "num_questions": 3},  # 30% weight, 3 questions
        "level_4": {"weight": 40, "num_questions": 5},  # 40% weight, 5 questions
    }

    # Calculate weighted score for the given level
    level_data = label_weights.get(level)
    if not level_data:
        return JSONResponse({"error": f"Invalid level: {level}"}, status_code=400)

    weight_per_question = level_data["weight"] / level_data["num_questions"]
    weighted_score = score * weight_per_question  # Scale the score by the weight per question

    # Save to database
    success, total_score, error = db_save_score(player_id, level, weighted_score)

    if not success:
        return JSONResponse({"error": f"Failed to save score: {error}"}, status_code=500)

    return JSONResponse({
        "message": "Score saved",
        "total_score": total_score,
        "weighted_score": round(weighted_score, 2),
        "timestamp": datetime.now().isoformat(),
        "start_time": start_time.isoformat() if start_time else "Not available"
    })

####DATABASE###
# Database initialization at startup
init_db()


### Registering Users
@app.post("/register")
@limiter.limit("5/minute")
def register_player_endpoint(request: Request, username: str = Form(...)):
    """Register a new player or resume existing player's game."""
    # Validate input - strip whitespace and check length
    username = username.strip()
    if not username or len(username) < 3:
        return {"error": "Username must be at least 3 characters long"}

    # Ensure username contains only letters and spaces
    if not re.match("^[a-zA-Z ]+$", username):
        return {"error": "Username must contain only letters (a-z, A-Z)"}

    # Check if player already exists
    existing_player = get_player_by_username(username)

    if existing_player:
        # Player exists - allow them to resume
        player_id = existing_player["player_id"]
        progress = get_player_progress(player_id)

        return {
            "message": "Welcome back! Resuming your game.",
            "player_id": player_id,
            "username": username,
            "is_returning": True,
            "total_score": existing_player["total_score"],
            "next_level": progress["next_level"],
            "completed_levels": progress["completed_levels"],
            "countdown_time": get_countdown_time()
        }

    # New player - generate unique ID and register
    player_id = str(uuid.uuid4())

    # Register in database
    success, error = register_player(player_id, username)

    if not success:
        return {"error": error or "Registration failed"}

    return {
        "message": "Player registered successfully",
        "player_id": player_id,
        "username": username,
        "is_returning": False,
        "total_score": 0,
        "next_level": "level_1",
        "completed_levels": [],
        "countdown_time": get_countdown_time()
    }


### Retrieving the Winner
@app.get("/winner")
def get_winner():
    """Retrieve the player(s) with the highest total score from database."""
    winners = get_winners()

    if not winners:
        return {"message": "No players found"}

    return {
        "winners": winners,
        "max_score": get_max_score()
    }


#winnere selection

PLAYER_DATA_PATH = "app/data/player_data.json"
WINNER_DATA_PATH = "app/data/winners.json"
# Function to calculate the winner
def select_winner():
    """Calculate and save the winner based on total scores and timestamps."""
    if not os.path.exists(PLAYER_DATA_PATH):
        print("No player data found.")
        return

    with open(PLAYER_DATA_PATH, "r") as f:
        player_data = json.load(f)

    players = player_data.get("players", [])

    if not players:
        print("No players found.")
        return
    
    # Calculate total time taken for each player and find the highest score
    for player in players:
        start_time = player.get("start_time")
        timestamps = player.get("timestamps", {})

        # Ensure start_time and timestamps exist
        if start_time and timestamps:
            # Convert start_time and latest timestamp to datetime objects
            start_time_dt = datetime.fromisoformat(start_time)
            latest_timestamp_dt = max(
                (datetime.fromisoformat(ts) for ts in timestamps.values()),
                default=None,
            )

            # Calculate total time taken
            if latest_timestamp_dt:
                player["total_time_taken"] = (latest_timestamp_dt - start_time_dt).total_seconds()
            else:
                player["total_time_taken"] = float("inf")  # Set to infinity if no timestamps exist

        else:
            player["total_time_taken"] = float("inf")  # Set to infinity if missing data

        # Find players with the highest total score
    max_score = max(player["total_score"] for player in players)
    candidates = [player for player in players if player["total_score"] == max_score]

    # Sort candidates by total time taken (ascending)
    candidates.sort(key=lambda p: p["total_time_taken"])

    # Select the winner(s)
    winner = candidates[0]
    winners = [c for c in candidates if c["total_time_taken"] == winner["total_time_taken"]]

    # Save the winner(s) to a file
    with open(WINNER_DATA_PATH, "w") as f:
        json.dump({"winners": winners, "max_score": max_score}, f, indent=4)

    print(f"Winners selected: {winners}")        

@app.get("/get_winners")
def get_winners():
    """Retrieve all winners with the highest total score."""
    if not os.path.exists(WINNER_DATA_PATH):
        return JSONResponse({"error": "Winner data not found."}, status_code=404)

    with open(WINNER_DATA_PATH, "r") as f:
        winner_data = json.load(f)

    return {
        "winners": winner_data.get("winners", []),
        "max_score": winner_data.get("max_score", 0),
    }

@app.post("/select_winner")
@limiter.limit("5/minute")
def manual_select_winner(request: Request, password: str = Form(...)):
    """Manually trigger the winner selection process (requires authentication)."""
    # Check password
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Unauthorized - Invalid password"}, status_code=401)

    # Get winners from database
    winners = get_winners()

    if not winners:
        return JSONResponse({"error": "No players found"}, status_code=404)

    return JSONResponse({
        "message": "Winner selection completed",
        "winners": winners,
        "max_score": get_max_score()
    })

@app.post("/admin/config")
def update_config(
    grid_size: Optional[int] = Form(None),
    countdown_time: Optional[int] = Form(None),
    password: str = Form(...)
):
    """Update the game configuration."""
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    messages = []
    
    if grid_size is not None:
        if grid_size < 2 or grid_size > 10:
             return JSONResponse({"error": "Grid size must be between 2 and 10"}, status_code=400)
        set_grid_size(grid_size)
        messages.append(f"Grid size updated to {grid_size}x{grid_size}")

    if countdown_time is not None:
        if countdown_time < 0 or countdown_time > 60:
            return JSONResponse({"error": "Countdown time must be between 0 and 60 seconds"}, status_code=400)
        set_countdown_time(countdown_time)
        messages.append(f"Countdown time updated to {countdown_time}s")

    return JSONResponse({"message": ", ".join(messages)})

@app.post("/admin/upload")
def upload_image(
    file: UploadFile = File(...), 
    level: str = Form(...), 
    password: str = Form(...)
):
    """Upload a new image to a specific level."""
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    if level not in image_metadata:
        # Create level if it doesn't exist in metadata, but for now strict to existing structure or just allow appending
        # For simplicity, if level implies a new key in json, we should handle it. 
        # But user asked to add to level.
        # Let's ensure directory exists first.
        pass

    # Save the file
    file_location = f"app/static/images/{level}/{file.filename}"
    os.makedirs(os.path.dirname(file_location), exist_ok=True)
    
    try:
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        return JSONResponse({"error": f"Failed to save file: {str(e)}"}, status_code=500)

    # Update questions.json (image_metadata)
    # Reload metadata to ensure we have latest (though in this simple app it's in-memory)
    # We need to update the in-memory variable `image_metadata` AND the file `app/data/questions.json`
    
    if level not in image_metadata:
        image_metadata[level] = {}

    # Check if image already exists in metadata
    if file.filename not in image_metadata[level]:
        # Add default placeholder data
        default_data = {
            "organ": "Unknown",
            "modality": "Unknown",
            "questions": [
                {
                    "question": "What is this image?",
                    "options": ["Puzzle Image", "Option B", "Option C"],
                    "answer": "Puzzle Image"
                }
            ]
        }
        image_metadata[level][file.filename] = default_data
        
        # Save back to JSON file
        with open("app/data/questions.json", "w") as f:
            json.dump(image_metadata, f, indent=4)
            
    return JSONResponse({"message": f"Image {file.filename} uploaded to {level} successfully."})
# Initialize Jinja2 templates
templates = Jinja2Templates(directory="app/templates")

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, password: Optional[str] = None):
    """
    Serve the admin panel page to manage winner selection (requires authentication).
    """
    # Simple authentication check
    if password != ADMIN_PASSWORD:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Admin Login</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .login-box {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                    }
                    input {
                        padding: 10px;
                        margin: 10px 0;
                        width: 250px;
                        border: 1px solid #ddd;
                        border-radius: 5px;
                    }
                    button {
                        padding: 10px 30px;
                        background: #667eea;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        cursor: pointer;
                        font-size: 16px;
                    }
                    button:hover {
                        background: #764ba2;
                    }
                    h1 { color: #333; }
                </style>
            </head>
            <body>
                <div class="login-box">
                    <h1>Admin Login</h1>
                    <form method="get" action="/admin">
                        <input type="password" name="password" placeholder="Enter admin password" required>
                        <br>
                        <button type="submit">Login</button>
                    </form>
                </div>
            </body>
            </html>
            """,
            status_code=401
        )

    return templates.TemplateResponse("admin.html", {"request": request, "password": password})







