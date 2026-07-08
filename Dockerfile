# Playwright's official Python image includes Chromium + system deps.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the pipeline code.
COPY . .

# `docker compose run app python collect.py` etc. — no default action.
CMD ["python", "run_all.py"]
