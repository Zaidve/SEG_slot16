# News & Digital Magazine Portal

University assignment: a small full-stack news portal with CRUD, authentication and role-based access control. Phase 2 (a later assignment) adds a hand-built search engine, so Phase 1 stores the data it needs.

Keep it small. Build what this file lists and nothing more: no revision history, outbox, Kafka, Docker, or index code. Write code a student can explain.

## How to work

1. Work through the steps below in order. Before starting, check whether a step is already done by looking at the code and `git log`, then continue from the first unfinished step.
2. Finish a step only when its "Done when" check passes. Actually run the check.
3. After each finished step, commit with a message like `Step 3: roles and permissions`. Never push unless asked.
4. If something is blocked (for example, PostgreSQL is missing or a password is needed), stop and ask rather than swapping the stack.
5. The environment is Windows 11 with PowerShell. Keep secrets in `.env`, never in Git.

`research_notes/` and `reports/` hold background research. They are not needed to build this, and they stay out of Git.

## Stack

- Backend: Django + Django REST Framework (REST API)
- Database: PostgreSQL
- Frontend: React with Vite and React Router, responsive
- Admin interface: Django Admin, plus one custom analytics page
- Auth: Django session login with CSRF protection, not JWT
- Version control: Git, hosted on GitHub by the project owner

Folders: `backend/` and `frontend/`. The Vite dev server proxies `/api` and `/media` to Django, so session cookies work without CORS setup.

## Decisions already made

- **"User tagging"** means users adding tags to articles (`UserTag`), not @mentions.
- **"Rating/liking"** means likes only, one per user per document.
- **Moderation** covers comments only, because users cannot submit posts.
- **Tables** keep the brief's names: `Document` and `SearchClickLog`.
- **Roles** are Django Groups. A logged-in user with no group is a Reader.

## Step 1: Project setup

- Run `git init` and add `.gitignore`, covering `.env`, virtual environments, `node_modules`, media uploads, `research_notes/` and `reports/`.
- Add `.env.example` and a short README.
- Create the Django project in `backend/` and the Vite React app in `frontend/`.
- Configure PostgreSQL from `.env`.

**Done when:** both dev servers run and React shows a response from a test `/api/health` endpoint through the proxy.

## Step 2: Data models

Create the custom user model before the first migration.

| Model | Fields |
|---|---|
| `User` (extends `AbstractUser`) | `display_name`, `avatar`, `bio` |
| `Category` | `name`, `slug` |
| `Tag` | `name`, `slug` |
| `Document` | `id`, `title`, `slug`, `content` (HTML), `content_text` (plain text), `summary`, `category` (FK), `tags` (M2M), `author` (FK to User), `image`, `image_alt`, `status` (`draft`, `published`, `unpublished`), `created_at`, `updated_at`, `published_at`, `views_count`, `seo_title`, `seo_description`, `seo_keywords` |
| `Comment` | `document`, `user`, `body`, `status` (`visible`, `hidden`), `created_at` |
| `Like` | `user`, `document`; unique together |
| `UserTag` | `user`, `document`, `tag`; unique together |
| `Report` | `comment`, `reporter`, `reason`, `status` (`open`, `resolved`), `resolved_by`, `created_at` |
| `SearchClickLog` | `user` (nullable, for guests), `query_string`, `clicked_doc` (nullable), `timestamp`, `query_id` (UUID), `position` (nullable), `result_count` |
| `SiteSetting` | `key` (unique), `value` |

Add indexes on `Document.status`, `Document.published_at` and `SearchClickLog.query_id`.

**Done when:** migrations apply cleanly on PostgreSQL and every model has a `__str__`.

## Step 3: Roles and permissions

Create these groups in a data migration, so they exist on every machine:

| Action | Super Admin | Content Manager | Moderator | Data & SEO | Reader |
|---|---|---|---|---|---|
| Manage users, roles and settings | ✓ | | | | |
| View system logs | ✓ | | | | |
| Create, edit, delete documents | ✓ | ✓ | | | |
| Publish or unpublish | ✓ | ✓ | | | |
| Manage categories and tags | ✓ | ✓ | | | |
| Hide comments, handle reports | ✓ | | ✓ | | |
| Edit SEO fields and alt text | ✓ | ✓ | | ✓ | |
| View analytics | ✓ | | | ✓ | |
| Comment, like, tag, report | ✓ | ✓ | ✓ | ✓ | ✓ |

Grant staff access (`is_staff`) to everyone in the first four roles. Add tests that check each role's allowed and forbidden actions.

**Done when:** the role tests pass.

## Step 4: Django Admin

- **Document:** list filters, search, and publish and unpublish actions. Publishing sets `published_at` the first time only.
- **Data & SEO role:** use `get_readonly_fields` so this role can edit only `seo_title`, `seo_description`, `seo_keywords` and `image_alt`.
- **Moderation:** hide-comment and resolve-report actions.
- **System logs:** register `LogEntry` as a read-only admin screen for Super Admin.
- **Settings:** register `SiteSetting` for Super Admin.
- **`Document.save()`:** sanitize `content` with `nh3`, then generate `content_text` from it by stripping tags, unescaping entities and collapsing whitespace.

**Done when:** a Content Manager can create and publish a document in the admin, and `content_text` holds clean text.

## Step 5: REST API

| Method and path | Purpose | Access |
|---|---|---|
| `POST /api/auth/register`, `/login`, `/logout` | Account access | Public |
| `GET /api/auth/csrf` | Set the CSRF cookie | Public |
| `GET`, `PATCH /api/profile` | View or edit own profile | Logged in |
| `GET /api/documents?page=` | Paginated latest items with summaries | Public |
| `GET /api/documents/{slug}` | Full detail; adds 1 to `views_count` | Public |
| `GET /api/categories`, `/api/tags` | Filter options | Public |
| `GET`, `POST /api/documents/{id}/comments` | Read or add comments | Read public, write logged in |
| `POST /api/documents/{id}/like` | Toggle like | Logged in |
| `POST /api/documents/{id}/tags` | Add a user tag | Logged in |
| `POST /api/comments/{id}/report` | Flag a comment | Logged in |
| `GET /api/search?q=&category=&tag=&from=&to=&page=` | Search and filter | Public |
| `POST /api/search/click` | Record a result click | Public |

Rules:

- Public endpoints return only `status=published` documents and `status=visible` comments.
- Increase `views_count` with an `F()` expression.
- Return the real user from the session. Never accept a user ID from the request body.

**Done when:** API tests pass, including that drafts return 404 and logged-out writes are rejected.

## Step 6: Search and click logging

- Put search in one function, `search_documents(query, filters)`, in `backend/<app>/search.py`. Phase 2 replaces only this function.
- Match with `Q(title__icontains=q) | Q(content_text__icontains=q)`, combined with the category, tag and date range filters.
- Each search generates a `query_id`, saves one log row with `clicked_doc` empty, and returns the `query_id` with the results.
- Each click saves a new row with the same `query_id`, plus `clicked_doc` and `position` (1-based rank across pages).

**Done when:** a test shows one search and one click produce two rows sharing a `query_id`, and a draft never appears in results.

## Step 7: React frontend

| Page | Contents |
|---|---|
| Home | Paginated latest items with summary snippets |
| Detail | Full content, image, author, date, views, category, tags, comments, like button, add-tag form, report button |
| Search | Keyword box, category, tag and date filters, paginated results; clicks call `/api/search/click` |
| Login, Register | Forms with validation errors |
| Profile | Edit `display_name`, `bio`, `avatar` |

Use a shared API helper that sends the CSRF token, and handle loading, empty and error states. Render `content` only after server-side sanitizing.

**Done when:** `npm run build` succeeds, and in a browser a guest can browse and search while a logged-in user can comment, like, tag and report. Check at desktop and 375px width.

## Step 8: Analytics dashboard

Add one custom admin page, visible to Data & SEO and Super Admin, showing:

- Total views
- Most-viewed documents
- Top search queries
- Zero-result queries
- Most-clicked documents

Link it from the admin index.

**Done when:** the numbers change after searching and clicking on the site, and other roles get a 403.

## Step 9: Seed data and finish

- Write a `seed_data` management command that can be run repeatedly without creating duplicates.
- Load 100 original articles from a JSON file, across about six categories, each 150 to 300 words of realistic text, with no Lorem Ipsum and nothing copied from real publishers. Include summaries and tags.
- Create one demo account per role plus two Readers, using obviously fake passwords that are listed in the README as demo-only.
- Add sample comments, likes, reports and search logs so the dashboard is not empty.
- Finish the README: setup, run commands, demo logins, and how each requirement is met.

**Done when:** a fresh database works with `migrate`, `seed_data` and `runserver`, the Django tests pass, and every item in the checklist below has been tried.

## Final checklist

- [ ] Paginated home listing with summaries
- [ ] Detail view with content, images and all metadata
- [ ] Register, login, profile management
- [ ] Commenting, liking, user tagging
- [ ] Keyword search with category, tag and date filters
- [ ] Super Admin: users, roles, permissions, system logs, global settings
- [ ] Content Manager: CRUD, publish and unpublish, taxonomy
- [ ] Moderator: comments, reports, spam control
- [ ] Data & SEO: SEO metadata, alt text, analytics dashboard
- [ ] `Document` has all required fields
- [ ] `SearchClickLog` has `user_id`, `query_string`, `clicked_doc_id`, `timestamp`
- [ ] At least 50 to 100 realistic seeded records
- [ ] Code in a Git repository
