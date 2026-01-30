import json
import os

CONFIG_PATH = "app/data/config.json"

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"grid_size": 4}
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

def get_grid_size():
    config = load_config()
    return config.get("grid_size", 4)

def set_grid_size(size):
    config = load_config()
    config["grid_size"] = size
    save_config(config)

def get_countdown_time():
    config = load_config()
    return config.get("countdown_time", 3)

def set_countdown_time(seconds):
    config = load_config()
    config["countdown_time"] = seconds
    save_config(config)
