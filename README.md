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

   `seed_data` can be run again at any time. It never creates duplicates. The search index fills itself as articles are saved. To rebuild it from scratch, for example on a database created before Phase 2, run `manage.py build_index`.

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

## Deploy on Render

The repository includes a Render Blueprint (`render.yaml`) for a free web service and a free PostgreSQL database. In production Django serves everything from one address: the built React app, the API, the admin and uploaded images.

1. Push the repository to GitHub.
2. In the [Render dashboard](https://dashboard.render.com), choose **New > Blueprint** and pick the repository.
3. When asked for `DEMO_PASSWORD`, enter a password of your own. The demo accounts on the public site use it instead of the README password.
4. Click **Apply**. The first build takes a few minutes. The site then runs at `https://news-portal-XXXX.onrender.com`, with the admin at `/admin/`.

What happens on each deploy:

- `render-build.sh` installs Python packages, builds the React app into `frontend/dist` and collects the admin's static files.
- `render-start.sh` applies migrations, runs `seed_data` and starts Gunicorn. WhiteNoise serves the static files.

Limits of the free plan:

- The site sleeps after 15 minutes without visitors, and the next visit takes about a minute to wake it.
- The disk is wiped on every restart. Article banners are redrawn by `seed_data`, but avatars that users upload are lost.
- Render deletes free databases 30 days after they are created unless you upgrade.

## Tests

```powershell
cd backend
.venv\Scripts\python.exe manage.py test
```

```powershell
cd frontend
npm run build
```

To compare the two search engines on the judged test queries (add `--details` for every query):

```powershell
cd backend
.venv\Scripts\python.exe manage.py evaluate_search
```

## How each requirement is met

| Requirement | How |
|---|---|
| Paginated home listing with summaries | `GET /api/documents`, shown by `pages/Home.jsx` |
| Detail view with content, images and metadata | `GET /api/documents/{slug}`, shown by `pages/Detail.jsx`. Each read adds 1 to `views_count` with an `F()` expression |
| Register, login, profile | `/api/auth/*` and `/api/profile`, using Django sessions and CSRF protection, not JWT |
| Commenting, liking, user tagging | `/api/documents/{id}/comments`, `/like` and `/tags`. The user always comes from the session, never the request body |
| Keyword search with filters | `GET /api/search`. All matching is in `search_documents()` in `portal/search.py`, which Phase 2 replaced with BM25 (see below) |
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

## Phase 2: hand-built search engine

Phase 2 replaces only `search_documents()`. The API, click logging, analytics and React pages are unchanged.

| Part | File | What it does |
|---|---|---|
| Analyzer | `portal/text.py` | Lowercases, removes accents, splits text into words and undoes plurals (Harman's S-stemmer), so `Harbours` and `harbour` match. Articles and queries use the same steps |
| Inverted index | `Posting` and `IndexedDocument` in `portal/models.py`, `portal/indexing.py` | For every word, the published articles that contain it, with counts and positions, in two fields: the title, and the body (summary plus text) |
| Index upkeep | `portal/signals.py` | Saving an article reindexes it, so publishing and unpublishing take effect at once. `build_index` rebuilds everything |
| Ranking | `portal/search.py` | BM25F: rare words count more, repeats help less and less, long fields are marked down, and a title match counts 3 times a body match. Every query word must appear; `"quoted phrases"` must appear in order |
| Evaluation | `portal/evaluation.py`, `portal/seed/search_judgments.json` | 31 test queries, each with hand-graded relevant articles, scored for both engines |

### Results

From `evaluate_search` on the 100 seeded articles:

| Engine | nDCG@10 | MRR | Recall@10 |
|---|---|---|---|
| Phase 1 keyword (`icontains`) | 0.505 | 0.522 | 0.487 |
| Phase 2 BM25 | 0.865 | 1.000 | 0.721 |

- **nDCG@10** measures how well the top 10 are ordered (1.0 is perfect).
- **MRR** measures how high the first relevant result appears (1.0 means always first).
- **Recall@10** is the share of relevant articles found in the top 10.

BM25 is never worse on any single query. It fixes nine queries where Phase 1 found nothing, mostly because Phase 1 needed the exact words in that order: "flood warning", "employee owned brewery", `"heat pumps"`.

### Limits

- **Requiring every word** keeps results precise, but broad queries such as "renewable energy" miss articles that use other words for the same idea. Returning partial matches lower down would raise recall.
- **No synonyms or stemming beyond plurals:** "cyclists" does not match "cycling".
- **Small, self-written test set:** the same person wrote the articles and the judgments. The judgments were written before either engine's results were looked at, but the numbers show the direction of the change rather than a precise score.
- **Scores are computed in Python:** fine for hundreds of articles, but a large site would need document frequencies stored in the index.

## Project layout

```
backend/
  config/      Django settings and root URLs
  portal/      Models, API, admin, search, analytics and tests
    seed/      The 100 demo articles and the judged search queries
frontend/
  src/pages/       One file per page
  src/components/  Shared pieces such as the comment list
  src/api.js       Shared helper that sends the CSRF token
```
