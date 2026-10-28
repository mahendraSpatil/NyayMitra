# Deploying NyayMitra to a cloud VM

One Linux VM runs everything: Postgres, the backend (with OCR), the AI
model (llama.cpp) and Caddy (automatic HTTPS). Cloudinary stays as is.
The Android app points at `https://<DOMAIN>`.

Recommended: **Azure for Students** (no card; verify with your college
email; $100 credit/year). VM size **Standard_B2as_v2** (2 vCPU, 8 GB RAM,
about $0.05/hour in Central India). Stop (deallocate) the VM when you are
not demoing and it costs almost nothing.

> Student subscriptions only allow some regions and cap you at 4 cores.
> If a size or region fails, try another allowed region; leave
> "Availability zone" empty ("No infrastructure redundancy required").

## 1. Create the VM (Azure portal)

1. Create a resource -> Virtual machine.
2. Image **Ubuntu Server 24.04 LTS**, size **Standard_B2as_v2**,
   authentication **SSH public key** (download the .pem it creates).
3. Inbound ports: allow **SSH (22), HTTP (80), HTTPS (443)**.
4. Disk: Standard SSD, 64 GB is plenty.
5. After it's created: VM -> Overview -> Public IP -> **Configuration** ->
   DNS name label, e.g. `nyaymitra` -> Save. Your domain is now
   `nyaymitra.<region>.cloudapp.azure.com`.

## 2. Install Docker on the VM

```bash
ssh -i nyaymitra_key.pem azureuser@nyaymitra.<region>.cloudapp.azure.com
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && exit      # log out and back in
```

## 3. Get the code and the model onto the VM

```bash
# Private repo: create a fine-grained GitHub token with read access to this repo.
git clone https://github.com/mahendraSpatil/NyayMitra.git
cd NyayMitra/deploy
mkdir -p models
```

Copy the model from your laptop (PowerShell; ~4.4 GB, takes a while on
home upload speeds):

```powershell
scp -i nyaymitra_key.pem D:\models\nyaymitra-demo.gguf azureuser@nyaymitra.<region>.cloudapp.azure.com:~/NyayMitra/deploy/models/
```

## 4. Configure and start

```bash
cp .env.prod.example .env.prod
nano .env.prod          # DOMAIN, two generated secrets, Cloudinary values
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml logs -f backend   # Ctrl+C to stop watching
curl https://$(grep ^DOMAIN .env.prod | cut -d= -f2)/health
```

`{"status":"ok","llm":true,...}` means it's live. Caddy gets the HTTPS
certificate automatically on first request (port 80 must be open).

Create accounts through the app's Register screen. **Don't run
`scripts/seed.py` here** — it creates test accounts with a password that is
in the repo, which is fine on a laptop and not on a public server.

## 5. Point the app at it

Either set the server in the app (sign-in screen -> server icon), or build
an APK with it baked in:

```powershell
powershell -ExecutionPolicy Bypass -File D:\EDI_5\demo\build_apk.ps1 -ServerUrl https://nyaymitra.<region>.cloudapp.azure.com
```

## Day to day

| Task | Command (in `~/NyayMitra/deploy`) |
|---|---|
| Update after a push | `git pull && docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build` |
| Logs | `docker compose -f docker-compose.prod.yml logs -f backend` |
| Stop to save credit | Azure portal -> VM -> **Stop** (deallocates; disk and data stay) |
| Start again | Azure portal -> VM -> **Start** (containers restart by themselves) |

## Notes

- Chat on 2 cloud vCPUs is slower than a laptop (expect 1-3 minutes per
  answer); the timeouts here allow 4-5 minutes.
- Data stays in the region you pick (Central India keeps case documents
  in India).
- Not yet built and run end to end — the Dockerfile and compose file were
  written and checked for syntax only. Expect to fix small things on the
  first `up --build`.
