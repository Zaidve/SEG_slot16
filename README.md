# News & Digital Magazine Portal

A small news portal with a Django REST API, a PostgreSQL database and a React frontend.

## Requirements

- Python 3.11
- Node.js 24
- PostgreSQL 18

## Setup

1. Copy `.env.example` to `.env` and fill in `DJANGO_SECRET_KEY` and `DB_PASSWORD`.
2. Create the database:

   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres news_portal
   ```

3. Install the backend:

   ```powershell
   cd backend
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Install the frontend:

   ```powershell
   cd ..\frontend
   npm install
   ```

## Run

Start each server in its own terminal.

```powershell
cd backend
.venv\Scripts\python.exe manage.py runserver
```

```powershell
cd frontend
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/media` to Django on port 8000.
