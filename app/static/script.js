// Global variables
let currentGridSize = 4;
let selectedIndex = null;
let puzzleValid = false;
let timerInterval = null;
let timeLeft = 300; // 5 minutes
let countdownTime = 3; // Default countdown

// ===== SESSION MANAGEMENT =====
function getSessionId() {
    return sessionStorage.getItem('game_session_id') || '';
}

function setSessionId(sessionId) {
    if (sessionId) {
        sessionStorage.setItem('game_session_id', sessionId);
    }
}

async function fetchWithSession(url, options = {}) {
    try {
        const sessionId = getSessionId();
        console.log(`[fetchWithSession] Calling ${url} with session:`, sessionId ? sessionId.substring(0, 8) + '...' : 'none');

        options.headers = options.headers || {};
        if (sessionId) {
            options.headers['X-Session-ID'] = sessionId;
        }

        const response = await fetch(url, options);
        console.log(`[fetchWithSession] ${url} response status:`, response.status);

        // Try to parse JSON regardless of status
        let data;
        try {
            data = await response.json();
        } catch (parseError) {
            console.error(`[fetchWithSession] Failed to parse JSON from ${url}:`, parseError);
            const text = await response.text();
            console.error(`[fetchWithSession] Response text:`, text);
            throw new Error(`Invalid JSON response from server`);
        }

        if (data.session_id) {
            setSessionId(data.session_id);
        }

        return { response, data };
    } catch (error) {
        console.error(`[fetchWithSession] Error for ${url}:`, error);
        console.error(`[fetchWithSession] Error stack:`, error.stack);
        throw error; // Re-throw so caller can handle it
    }
}

// ===== GAME INITIALIZATION =====
document.addEventListener("DOMContentLoaded", () => {
    // Check local storage for returning player
    const savedPlayerId = localStorage.getItem("playerId");
    if (savedPlayerId) {
        document.getElementById("player-id").value = savedPlayerId;
    }
});

function startGame() {
    const playerIdInput = document.getElementById("player-id");
    const playerId = playerIdInput.value.trim();
    const errorMsg = document.getElementById("error-message");

    errorMsg.style.display = 'none';

    if (!playerId || playerId.length < 3 || !/^[a-zA-Z ]+$/.test(playerId)) {
        showError("Invalid name. Must be 3+ letters only.");
        return;
    }

    fetch("/register", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username: playerId }),
    })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showError(data.error);
            } else {
                localStorage.setItem("playerId", data.player_id);
                // Set level from backend response (defaults to level_1 for new players)
                if (data.next_level) {
                    localStorage.setItem("currentLevel", data.next_level);
                } else {
                    localStorage.setItem("currentLevel", "level_1");
                }

                if (data.countdown_time !== undefined) {
                    countdownTime = data.countdown_time;
                }

                setSessionId(null); // Clear session for new game entry
                showGameArea();
                loadImage();
                startTimer();
            }
        })
        .catch(() => showError("Connection failed."));
}

function showError(msg) {
    const el = document.getElementById("error-message");
    el.textContent = msg;
    el.classList.remove("hidden");
}

function showGameArea() {
    document.getElementById("player-id-area").classList.add("hidden");
    document.getElementById("sidebar").classList.remove("hidden");

    // Use flex for split view
    document.getElementById("game-split-view").classList.remove("hidden");
    document.getElementById("game-split-view").style.display = "flex";

    // Show quiz panel immediately 
    document.getElementById("quiz-panel").classList.remove("hidden");

    document.getElementById("timer-container").style.display = "block";
}

function goHome() {
    if (confirm("Go home? Progress will be lost.")) {
        location.reload();
    }
}

function restartLevel() {
    if (confirm("Restart level?")) {
        startCurrentLevel();
        resetTimer();
    }
}

function startCurrentLevel() {
    // Reset state
    document.getElementById("result-container").classList.add("hidden");
    document.getElementById("game-split-view").classList.remove("hidden");
    document.getElementById("game-split-view").style.display = "flex";

    document.getElementById("validate-button").classList.add("hidden");

    // Reset quiz feedback
    document.getElementById("quiz-feedback").classList.add("hidden");
    document.getElementById("submit-quiz-btn").disabled = false;

    // Reset questions inputs
    document.querySelectorAll('input[type="radio"]').forEach(el => el.checked = false);
    document.querySelectorAll('.question-block').forEach(el => {
        el.classList.remove('correct-answer', 'incorrect-answer');
        const feedback = el.querySelector('.feedback-text');
        if (feedback) feedback.remove();
    });

    // Clear puzzle image to prevent showing old content
    const img = document.getElementById("puzzle-image");
    img.src = "";
    img.onclick = null;
    img.style.cursor = "default";
    img.style.border = "none";

    loadImage();
}

// ===== TIMER =====
function startTimer() {
    timeLeft = 300; // 5 mins
    updateTimerDisplay();
    clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        timeLeft--;
        updateTimerDisplay();
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            showModal('timeout-modal');
        }
    }, 1000);
}

function resetTimer() {
    startTimer();
}

function updateTimerDisplay() {
    const m = Math.floor(timeLeft / 60).toString().padStart(2, '0');
    const s = (timeLeft % 60).toString().padStart(2, '0');
    document.getElementById("timer").textContent = `${m}:${s}`;
}

// ===== SIDEBAR LOGIC =====
function toggleModality(id) {
    // Hide all
    document.querySelectorAll('.modality-content').forEach(el => {
        if (el.id !== id + '-content') el.style.display = 'none';
    });
    // Toggle current
    const content = document.getElementById(id + '-content');
    if (content.style.display === 'block') {
        content.style.display = 'none';
    } else {
        content.style.display = 'block';
    }
}

function openModalityHint(modality) {
    // Attempt to map string to ID
    if (!modality) return;
    const lower = modality.toLowerCase();

    if (lower.includes("mri")) toggleModality('mri');
    else if (lower.includes("ct")) toggleModality('ct');
    else if (lower.includes("x-ray") || lower.includes("xray")) toggleModality('xray');
    else if (lower.includes("ultrasound")) toggleModality('ultrasound');
}


// ===== COUNTDOWN LOGIC =====
function startCountdown(seconds, callback) {
    const overlay = document.getElementById("countdown-overlay");
    overlay.style.display = "block";
    overlay.innerText = seconds;

    let count = seconds;
    const interval = setInterval(() => {
        count--;
        if (count > 0) {
            overlay.innerText = count;
        } else {
            clearInterval(interval);
            overlay.style.display = "none";
            if (callback) {
                try {
                    // Handle both sync and async callbacks
                    const result = callback();
                    if (result instanceof Promise) {
                        result.catch(err => {
                            console.error("Error in countdown callback:", err);
                            alert(`An error occurred: ${err.message}`);
                        });
                    }
                } catch (error) {
                    console.error("Error in countdown callback:", error);
                    alert(`An error occurred: ${error.message}`);
                }
            }
        }
    }, 1000);
}

// ===== PUZZLE LOGIC =====
async function loadImage() {
    try {
        console.log("Loading image...");
        const { response, data } = await fetchWithSession('/image');

        if (response.ok) {
            console.log("Image loaded successfully:", data.image_url);
            const img = document.getElementById("puzzle-image");
            img.src = data.image_url;
            img.style.display = "block";
            img.onclick = null; // Disable clicks initially
            img.style.cursor = "default";
            img.style.border = "none";

            // Metadata
            const meta = document.getElementById("metadata");
            if (data.metadata) {
                meta.textContent = `${data.metadata.organ} • ${data.metadata.modality}`;
                // Open relevant hint
                openModalityHint(data.metadata.modality);
            }

            // Load questions correctly
            loadQuestions();

            // Start visible countdown
            console.log(`Starting countdown (${countdownTime} seconds) before shuffle`);
            startCountdown(countdownTime, shuffleImage);
        } else {
            if (data.error && data.error.includes("No images")) {
                alert("Level complete!");
            } else {
                console.error("Load image failed:", data.error);
                alert(`Failed to load image: ${data.error || 'Unknown error'}`);
            }
        }
    } catch (error) {
        console.error("Error during loadImage:", error);
        alert(`Failed to load image: ${error.message}. Please refresh the page.`);
    }
}

async function shuffleImage() {
    try {
        console.log("Starting shuffle...");
        const { response, data } = await fetchWithSession('/shuffle', { method: 'POST' });

        if (response.ok) {
            console.log("Shuffle successful, loading image:", data.shuffled_image_url);
            const img = document.getElementById("puzzle-image");
            img.src = data.shuffled_image_url + "?t=" + new Date().getTime();
            currentGridSize = data.grid_size || 4;

            document.getElementById("validate-button").classList.remove("hidden");

            // Enable swapping
            img.style.cursor = "pointer";
            img.onclick = handleImageClick;
            img.style.border = "2px solid #34495e";
        } else {
            console.error("Shuffle failed:", data);

            // Check if session expired
            if (data.session_expired) {
                console.log("Session expired, reloading image to get new session...");
                alert("Your session expired. Reloading the game...");
                // Clear the old session and reload
                sessionStorage.removeItem('game_session_id');
                await loadImage();
                return;
            }

            alert(`Failed to shuffle puzzle: ${data.error || 'Unknown error'}. Please try restarting the level.`);
        }
    } catch (error) {
        console.error("Error during shuffle:", error);
        alert(`Failed to shuffle puzzle: ${error.message}. Please refresh the page.`);
    }
}

function handleImageClick(e) {
    const img = e.target;
    // Calculate index
    const rect = img.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const col = Math.floor((x / rect.width) * currentGridSize);
    const row = Math.floor((y / rect.height) * currentGridSize);

    if (col >= currentGridSize || row >= currentGridSize) return;

    const index = row * currentGridSize + col;

    if (selectedIndex === null) {
        selectedIndex = index;
        img.style.opacity = "0.7";
    } else {
        performSwap(selectedIndex, index);
        selectedIndex = null;
        img.style.opacity = "1.0";
    }
}

async function performSwap(idx1, idx2) {
    if (idx1 === idx2) return;

    const formData = new FormData();
    formData.append("index1", idx1);
    formData.append("index2", idx2);

    const { response, data } = await fetchWithSession('/swap', {
        method: 'POST',
        body: formData
    });

    if (response.ok) {
        const img = document.getElementById("puzzle-image");
        img.src = data.updated_image_url + "?t=" + new Date().getTime();
    }
}

async function validatePuzzle() {
    const { response, data } = await fetchWithSession('/validate', { method: 'POST' });
    if (response.ok && data.is_correct) {
        puzzleValid = true; // Mark puzzle as valid
        showModal('success-modal');
    } else {
        puzzleValid = false;
        showModal('try-again-modal');
    }
}

function showModal(id) {
    const el = document.getElementById(id);
    el.classList.remove("hidden");
    el.style.display = "flex";
}

function closeModal(id) {
    const el = document.getElementById(id);
    el.classList.add("hidden");
    el.style.display = "none";
}

// ===== QUIZ LOGIC =====
async function loadQuestions() {
    try {
        const { response, data } = await fetchWithSession('/questions');
        if (response.ok) {
            renderQuestions(data.questions);
        } else {
            console.error("Failed to load questions:", data.error);
            renderQuestions([]); // Show empty questions
        }
    } catch (error) {
        console.error("Error loading questions:", error);
        renderQuestions([]); // Show empty questions
    }
}

function renderQuestions(questions) {
    const container = document.getElementById("questions-container");
    container.innerHTML = "";

    if (!questions || questions.length === 0) {
        container.innerHTML = "<p>No questions for this image.</p>";
        return;
    }

    questions.forEach((q, idx) => {
        const div = document.createElement("div");
        div.className = "question-block";
        div.innerHTML = `<p>${idx + 1}. ${q.question}</p>`;

        q.options.forEach(opt => {
            div.innerHTML += `
                <label>
                    <input type="radio" name="q${idx}" value="${opt}"> ${opt}
                </label>
            `;
        });
        container.appendChild(div);
    });

    // Store questions for submission
    window.currentQuestions = questions;
}

async function submitAnswers() {
    // Check if puzzle is valid first
    if (!puzzleValid) {
        alert("Please solve the puzzle correctly before submitting answers!");
        return;
    }

    const questions = window.currentQuestions;
    if (!questions) return;

    const answers = [];
    let allAnswered = true;

    questions.forEach((q, idx) => {
        const checked = document.querySelector(`input[name="q${idx}"]:checked`);
        if (!checked) allAnswered = false;
        else answers.push({ index: idx, answer: checked.value });
    });

    if (!allAnswered) {
        alert("Please answer all questions.");
        return;
    }

    const { response, data } = await fetchWithSession('/check_answers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers })
    });

    if (response.ok) {
        // Show inline feedback
        const feedbackDiv = document.getElementById("quiz-feedback");
        feedbackDiv.classList.remove("hidden");
        feedbackDiv.innerHTML = `<h4>Score: ${data.score} / ${data.total_questions}</h4>`;

        // Disable submit
        document.getElementById("submit-quiz-btn").disabled = true;

        // Iterate questions to show feedback
        const qBlocks = document.querySelectorAll(".question-block");
        data.details.forEach((detail, idx) => {
            const block = qBlocks[idx];
            if (detail.is_correct) {
                block.style.borderLeft = "4px solid #2e7d32";
                block.style.backgroundColor = "rgba(46, 125, 50, 0.1)";
            } else {
                block.style.borderLeft = "4px solid #c0392b";
                block.style.backgroundColor = "rgba(192, 57, 43, 0.1)";
                // Show correct answer
                const p = document.createElement("p");
                p.className = "feedback-text";
                p.style.color = "#c0392b";
                p.style.fontWeight = "bold";
                p.style.fontSize = "0.9rem";
                p.style.marginTop = "5px";
                p.innerText = `Correct Answer: ${detail.correct_answer}`;
                block.appendChild(p);
            }
        });

        // Save score
        saveScore(data.score);

        // Next Level button
        feedbackDiv.innerHTML += `<button class="btn-primary" onclick="nextLevel()" style="width:100%; margin-top:10px;">Next Level</button>`;
    }
}

async function saveScore(score) {
    const playerId = localStorage.getItem("playerId");
    const level = localStorage.getItem("currentLevel") || "level_1";

    await fetchWithSession('/save_score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            player_id: playerId,
            level: level,
            score: score
        })
    });
}

async function nextLevel() {
    const { response, data } = await fetchWithSession('/next_level', { method: 'POST' });
    if (response.ok) {
        if (data.level) {
            localStorage.setItem("currentLevel", data.level);
            startCurrentLevel();
            resetTimer();
        } else {
            // Game Over
            document.getElementById("game-split-view").classList.add("hidden");
            document.getElementById("sidebar").classList.add("hidden");
            document.getElementById("timer-container").style.display = "none";

            const resultContainer = document.getElementById("result-container");
            resultContainer.classList.remove("hidden");
            resultContainer.innerHTML = `<h2>All Levels Completed!</h2><p>Check the leaderboard.</p><button class="btn-primary" onclick="window.location.reload()">Home</button>`;
        }
    }
}
