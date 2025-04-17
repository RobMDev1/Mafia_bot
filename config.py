# config.py

# Default phase timers in seconds
DEFAULT_TIMERS = {
    "day": 300,     # 5 minutes
    "night": 180,   # 3 minutes
    "vote": 60      # 1 minute
}

# Player limits
MIN_PLAYERS = 5
MAX_PLAYERS = 10

# Roles enabled (useful for testing or future toggles)
ENABLED_ROLES = {
    "Doctor": True,
    "Lawyer": True
}
