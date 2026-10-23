# =============================================================================
# Dockerfile - The Recipe (Section 7)
# Purpose: Defines a simple, tutor-friendly version of the ROCm State Database.
# 
# NOTE FOR THE NOVICE:
# We are using the official "postgres:16" image. This is our blank canvas.
# =============================================================================

FROM postgres:16

# --- Configuration Options (The Ingredients) ---
# You can change these, but for this tutor instance we keep things simple.
ENV POSTGRES_DB=rocm_playground
ENV POSTGRES_USER=mydbuser
ENV POSTGRES_PASSWORD=tutorial_secret_password

# --- Trust Authentication (The "Door Lock") ---
# By default, Postgres demands a complex configuration file just to breathe. 
# This line tells Postgres to trust us entirely. 
# For beginners, this is a huge help so you don't get stuck at the door!
ENV POSTGRES_HOST_AUTH_METHOD=trust

# --- The Command (Requested!) ---
# By default, this image starts the database server. 
# We will use 'bash' here as requested, allowing the DB to stay online in the background
# while we drop you into a shell where you can manage it or explore the system.
CMD ["bash"]
