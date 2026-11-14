#!/usr/bin/env bash
# Render runs this once per deploy to build the site. Stop at the first error.
set -o errexit

pip install -r backend/requirements.txt

# Build the React app into frontend/dist, which Django then serves.
npm ci --prefix frontend
npm run build --prefix frontend

# Copy the admin's CSS and JS into backend/staticfiles for WhiteNoise.
python backend/manage.py collectstatic --no-input
