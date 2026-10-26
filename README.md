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

- `CORS_ALLOWED_ORIGINS` — already defaults to `http://localhost:5000`, no
  edits needed if you run the web client on that port (see "Run it" below).

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

### Running the web client

`flutter run -d chrome` picks a random port on every run, which the
backend's CORS allowlist (`CORS_ALLOWED_ORIGINS`, above) can't follow.
Pin the port instead, matching the default in `backend/.env.example`:

```bash
flutter run -d chrome --web-port=5000
```

If you'd rather not pin a port, set `CORS_ALLOW_LOCALHOST_REGEX=true` in
`backend/.env` (dev only — see its comment in `backend/app/config.py`;
never set this in a deployed environment) instead of editing
`CORS_ALLOWED_ORIGINS` every run.

### Running on a physical Android phone (backend on your laptop, over USB)

Uses `adb reverse` to forward the phone's own `localhost:8000` to the
backend running on your laptop — no LAN IP, Wi-Fi, or firewall rule needed.

1. Plug the phone in via USB with USB debugging enabled, and confirm it's
   visible:

   ```bash
   adb devices
   ```

2. Forward the phone's port 8000 to your laptop's port 8000:

   ```bash
   adb reverse tcp:8000 tcp:8000
   ```

   This only lasts until the phone is unplugged or `adb` restarts — re-run
   it if the app stops reaching the backend after a reconnect.

3. Start the backend as usual (step 3 above — `uvicorn app.main:app --reload
   --port 8000`, no `--host 0.0.0.0` needed; `adb reverse` handles reaching
   it from the phone).

4. Build the APK with `API_BASE_URL` pointed at localhost — from the
   phone's perspective, `adb reverse` makes that resolve to your laptop:

   ```bash
   cd client
   flutter build apk --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000
   ```

   The built APK is at `client/build/app/outputs/flutter-apk/app-debug.apk`
   — install it with `flutter install` or copy it to the phone and install
   manually.

   `API_BASE_URL` is only consulted on Android/iOS; web and desktop builds
   ignore it and keep using `localhost` as before (`client/lib/core/config/api_config.dart`).

   This is a debug build talking over plain HTTP, which Android blocks by
   default. `client/android/app/src/debug/res/xml/network_security_config.xml`
   permits cleartext traffic to `localhost`/`127.0.0.1` only, for debug
   builds only — it lives under `src/debug/`, so it cannot end up in a
   release build, and should never be copied into `src/main/` or a release
   source set. (Android's network security config has no CIDR/IP-range
   syntax, so if you need a phone to reach the backend over Wi-Fi/LAN
   instead of USB, add that specific IP as its own `<domain>` entry in that
   file rather than widening it to an unscoped `cleartextTrafficPermitted`.)

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
