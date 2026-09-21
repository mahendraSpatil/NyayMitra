# NyayMitra AI

Multilingual legal-tech co-pilot for the Indian undertrial backlog. Flutter
client + FastAPI backend + Firebase (Auth/Firestore). See [NyayMitra.md](NyayMitra.md)
for the full architecture and conventions.

## Prerequisites

- [Flutter](https://docs.flutter.dev/get-started/install) (stable channel)
- Python 3.11+
- Node.js — needed for `firebase-tools` and the FlutterFire CLI
- Docker — runs local Postgres (the backend is mid-migration off Firebase;
  see [NyayMitra.md](NyayMitra.md))

## 1. Get the four files nothing in the repo ships with

None of these are checked in (secrets, or machine-specific config). Get all
four before anything will run.

**`client/lib/firebase_options.dart` and `client/android/app/google-services.json`**
— generated together by one command:

```bash
npm install -g firebase-tools
dart pub global activate flutterfire_cli
firebase login
flutterfire configure --project=nyaymitra-ai-92fcc
```

Pick the platforms you need when prompted; both files land in the right
place automatically.

**`backend/.env`** — copy the example and fill in real values:

```bash
cp backend/.env.example backend/.env
```

Fill in `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
from the project's Cloudinary dashboard. `FIREBASE_WEB_API_KEY` isn't secret
(it's the same key inside `firebase_options.dart`) but is also read from here,
used by the backend test suite to sign in as the seeded test accounts.

**A Firebase service account key**, for the Admin SDK (seeding data, running
the backend):

1. Firebase Console → Project Settings → Service Accounts → **Generate new
   private key**.
2. Save it *outside the repo*: `~/.nyaymitra/serviceAccount.json`.
3. Point `GOOGLE_APPLICATION_CREDENTIALS` at it before running anything backend-side:

   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=~/.nyaymitra/serviceAccount.json
   ```

   (PowerShell: `$env:GOOGLE_APPLICATION_CREDENTIALS = "$HOME\.nyaymitra\serviceAccount.json"`)

## 2. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Seed the three test accounts and demo cases (needs `GOOGLE_APPLICATION_CREDENTIALS`
set, as above):

```bash
python scripts/seed.py
```

### Postgres (local dev)

The backend is mid-migration off Firebase onto Postgres (see NyayMitra.md) —
both are live and in use until that migration's last step. Start Postgres,
apply migrations, and seed it, from the repo root and `backend/` respectively:

```bash
docker compose up -d               # from the repo root

cd backend                         # venv active, as above
alembic upgrade head
python scripts/seed_pg.py
```

`backend/.env.example`'s `DATABASE_URL` already points at the container
`docker-compose.yml` creates (`localhost:5433` — not the default 5432, in
case something else on your machine already uses it), so no edits are
needed there.

## 3. Run it

```bash
# backend, from backend/ with the venv active
uvicorn app.main:app --reload --port 8000

# client, from client/, in another terminal
flutter run -d windows   # or your device/platform of choice
```

## Test accounts

Seeded by `seed.py`, password `NyayMitra@Dev1` for all three:

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
