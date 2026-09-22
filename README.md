# NyayMitra AI

Multilingual legal-tech co-pilot for the Indian undertrial backlog. Flutter
client + FastAPI backend + PostgreSQL. See [NyayMitra.md](NyayMitra.md)
for the full architecture and conventions.

## Prerequisites

- [Flutter](https://docs.flutter.dev/get-started/install) (stable channel)
- Python 3.11+
- Docker — runs local Postgres

## 1. `backend/.env`

Not checked in (secrets). Copy the example and fill in real values:

```bash
cp backend/.env.example backend/.env
```

- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` — from
  the project's Cloudinary dashboard.
- `DATABASE_URL` — already points at the container `docker-compose.yml`
  creates (`localhost:5433`), no edits needed for local dev.
- `JWT_SECRET` — generate your own, never reuse the example's:

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

## 2. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Start Postgres, apply migrations, and seed the three test accounts and demo
cases, from the repo root and `backend/` respectively:

```bash
docker compose up -d               # from the repo root

cd backend                         # venv active, as above
alembic upgrade head
python scripts/seed.py
```

## 3. Run it

```bash
# backend, from backend/ with the venv active
uvicorn app.main:app --reload --port 8000

# client, from client/, in another terminal
flutter run -d windows   # or your device/platform of choice
```

## Test accounts

Seeded by `scripts/seed.py`, password `NyayMitra@Dev1` for all three:

| Role     | Email                     |
|----------|---------------------------|
| Advocate | advocate@nyaymitra.test   |
| NGO      | ngo@nyaymitra.test        |
| Family   | family@nyaymitra.test     |

## Contributing

- **Never put a real value in `.env.example`.** It's committed; `.env` is the
  only gitignored place secrets belong.
- **Run a secret scan before pushing.** If you don't have one installed:

  ```bash
  gitleaks detect --source . -v
  ```
