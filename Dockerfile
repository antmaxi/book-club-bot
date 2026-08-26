# Use an official Python runtime as a parent image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY --chown=10001:10001 bookclub/ ./bookclub/
COPY --chown=10001:10001 bookclub_bot.py .

# Run the application as a dedicated non-root uid/gid.
RUN groupadd --gid 10001 bot \
    && useradd --uid 10001 --gid bot --no-create-home --shell /usr/sbin/nologin bot \
    && mkdir -p /app/data /app/logs \
    && chown -R bot:bot /app
USER bot

# Command to run the bot
CMD ["python", "bookclub_bot.py"]
