# News & Digital Magazine Portal

A small news portal with a Django REST API, a PostgreSQL database and a React frontend. Readers browse, search, comment, like, tag and report. Staff manage content, moderation and analytics through Django Admin.

All articles, towns, people and organisations in the demo data are fictional. They were written for this project.

## Requirements

- Python 3.11
- Node.js 24
- PostgreSQL 18

## Setup

1. Copy `.env.example` to `.env`. Set `DB_PASSWORD` to your PostgreSQL password, and set `DJANGO_SECRET_KEY` to the output of:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

2. Create the database:

   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres news_portal
   ```

3. Install the backend, create the tables and load the demo data:

   ```powershell
   cd backend
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   .venv\Scripts\python.exe manage.py migrate
   .venv\Scripts\python.exe manage.py seed_data
   ```

   `seed_data` can be run again at any time. It never creates duplicates.

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

| What | Where |
|---|---|
| Website | http://localhost:5173 |
| Admin | http://localhost:8000/admin/ |
| Analytics dashboard | http://localhost:8000/admin/analytics/ |

Vite proxies `/api` and `/media` to Django on port 8000, so session cookies work without CORS setup.

## Demo logins

**These accounts are for local demos only.** They share one public password, so never load `seed_data` on a real site.

Password for every account: `demo-password-123`

| Username | Role | Can use |
|---|---|---|
| `superadmin` | Super Admin | Admin: everything, including users, roles, logs and settings |
| `editor` | Content Manager | Admin: documents, publishing, categories and tags |
| `moderator` | Moderator | Admin: comments and reports |
| `seo` | Data & SEO | Admin: SEO fields, alt text and analytics |
| `reader1` | Reader | Website only |
| `reader2` | Reader | Website only |

Staff accounts can also log in to the website. Roles are Django Groups, and a logged-in user with no group is a Reader.

## Tests

```powershell
cd backend
.venv\Scripts\python.exe manage.py test
```

```powershell
cd frontend
npm run build
```

## How each requirement is met

| Requirement | How |
|---|---|
| Paginated home listing with summaries | `GET /api/documents`, shown by `pages/Home.jsx` |
| Detail view with content, images and metadata | `GET /api/documents/{slug}`, shown by `pages/Detail.jsx`. Each read adds 1 to `views_count` with an `F()` expression |
| Register, login, profile | `/api/auth/*` and `/api/profile`, using Django sessions and CSRF protection, not JWT |
| Commenting, liking, user tagging | `/api/documents/{id}/comments`, `/like` and `/tags`. The user always comes from the session, never the request body |
| Keyword search with filters | `GET /api/search`. All matching is in `search_documents()` in `portal/search.py`, the only function Phase 2 replaces |
| Super Admin | Every permission: users, roles (Groups), system logs (`LogEntry`, read-only) and `SiteSetting` |
| Content Manager | Document create, edit and delete, publish and unpublish actions, categories and tags |
| Moderator | Hide-comment and resolve-report actions, for spam control. Comment text cannot be edited |
| Data & SEO | Can edit only `seo_title`, `seo_description`, `seo_keywords` and `image_alt`, and can open the dashboard |
| Roles on every machine | Migration `0003_create_roles` creates the Groups. `portal/signals.py` keeps `is_staff` in step with them |
| `Document` fields | `portal/models.py`. `Document.save()` sanitizes `content` with `nh3` and generates `content_text` |
| `SearchClickLog` fields | `portal/models.py`. A search saves one row, and each click saves another with the same `query_id` |
| Analytics dashboard | `portal/analytics.py`: total views, most-viewed documents, top queries, zero-result queries and most-clicked documents |
| Public data rules | Public endpoints return only `published` documents and `visible` comments. A draft returns 404 |
| At least 50 to 100 seeded records | `seed_data` loads 100 articles from `portal/seed/articles.json`, plus accounts, comments, likes, reports and search logs |
| Code in a Git repository | This repository |

## Project layout

```
backend/
  config/      Django settings and root URLs
  portal/      Models, API, admin, search, analytics and tests
    seed/      The 100 demo articles
frontend/
  src/pages/       One file per page
  src/components/  Shared pieces such as the comment list
  src/api.js       Shared helper that sends the CSRF token
```
