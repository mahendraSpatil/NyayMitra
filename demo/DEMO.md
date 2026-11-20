# Showing NyayMitra on a phone

Your laptop runs everything; a free Cloudflare tunnel gives it a public
HTTPS address the phone can reach from any network (mobile data is fine).
No accounts, no card.

## Once: build and install the app

```powershell
powershell -ExecutionPolicy Bypass -File D:\EDI_5\demo\build_apk.ps1
```

This creates `D:\EDI_5\demo\NyayMitra.apk`. Install it:

- **USB:** `adb install -r D:\EDI_5\demo\NyayMitra.apk`
  (Xiaomi: Developer options -> "Install via USB" on)
- **Or** send the APK to the phone (WhatsApp to yourself / Drive), open
  it, allow "install unknown apps" when asked.

Also copy a couple of test PDFs to the phone (Downloads) for the upload
demo, e.g. from `D:\nyaymitra\ocr_test_docs\`:
`1_typed_fir.pdf`, `4_scan_clean_fir.pdf`, `6_scan_bad_photocopy_fir.pdf`.

## Every demo: start the server

**Easiest:** double-click `D:\EDI_5\demo\START_NYAYMITRA.cmd` (stop with
`STOP_NYAYMITRA.cmd`). It uses the **v2** model, `D:\models\nyaymitra-v2.gguf`,
from Vedant's Drive folder `nyaymitra-v2-gguf`. To run the older September
model instead: `start_demo.ps1 -Model demo`. The script starts llama-server
with the right file and the backend with the matching prompt format, and
switches models if the wrong one is already loaded.

Other one-click tools in this folder (results go to `demo\.state\`):

| File | Does |
|---|---|
| `run_backend_tests.cmd` | Starts Postgres, migrates, runs all backend tests -> `pytest.log` |
| `run_e2e_phone_test.cmd` | Full phone-path test through the public address -> `e2e.log` |
| `run_compare_prompts.cmd` | Asks v2 ten questions with two Alpaca layouts -> `compare.json` |
| `run_law_check.cmd` | Asks v2 law questions with and without the law summaries -> `law_check.log` |
| `build_web.cmd` | Builds the committed app (HEAD) for the web -> `.state\webclient\client\build\web` (used for the screen recording) |
| `install_v2_model.cmd` | Checks the SHA-256 of `Downloads\nyaymitra-v2.gguf` and moves it to `D:\models` -> `install_model.log` |

Starting again while it is already running is fine: the new window stops
the old one first (otherwise two watchdogs fight over the tunnel and one
publishes a dead address). `STOP_NYAYMITRA.cmd` stops the window too.

### Law answers

The model is not trusted to quote law from memory (tested: it got Section
436A CrPC wrong). For law questions the backend adds short summaries from
`backend/app/llm/statute_kb.py` (436A/479 BNSS, default bail, 24-hour
production, grounds of arrest, bail, legal aid, meeting a lawyer) as
RELEVANT LAW, picked by keywords in the question. Questions about the
case's own facts get no law text. **Before any real use, have the guide or
a lawyer check every summary against the Acts** and fill in
`KB_REVIEWED_BY`. `STATUTE_KB_ENABLED=false` in `backend/.env` turns it off.

Or from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File D:\EDI_5\demo\start_demo.ps1
```

It starts Docker/Postgres, the AI model, the backend and a Cloudflare
tunnel, then **publishes the tunnel's address to the `demo-server` branch
of the GitHub repo**. The app reads it from there at launch and whenever
the server stops answering, so **nobody types an address**.

**Keep that window open.** It checks the public address every 30 s and,
if the tunnel drops (Wi-Fi blip, laptop network change), opens a new one
and publishes it; phones switch over by themselves on their next request.
It also stops the laptop sleeping while it's open.

Needs: the repo public (the app reads the address without logging in),
and `git push` working from this laptop. If publishing fails the script
says so - fix the push (sign in to GitHub on this laptop) and re-run, because
the phone app has no place to type an address.

When done: close the window, then
`powershell -ExecutionPolicy Bypass -File D:\EDI_5\demo\stop_demo.ps1`

## A 5-minute demo story

1. **Advocate** signs in -> opens a case (or creates "Ramesh Kale").
2. **Upload** `1_typed_fir.pdf` -> facts appear automatically (FIR no.,
   sections from the Acts table, offence/FIR dates).
3. **Upload a scan** `4_scan_clean_fir.pdf` -> badge *Scanned - text may be
   unreliable*, "4 facts to check". Open it: each fact shows what was read
   and its scan confidence.
4. **Upload the bad photocopy** -> the arrest year was misread as 2926 and
   is flagged. Tap **Correct it** -> `14/03/2026`. Point out: the original
   reading is kept, and who corrected it is recorded.
5. **Ask the chatbot**: "When was he arrested and when is the next hearing?"
   -> it uses confirmed facts and says unconfirmed ones aren't checked yet
   instead of guessing. (Takes ~10-25 s on the laptop with v2.)
   Then ask "What does Section 436A CrPC say?" or "We cannot afford a
   lawyer, what can we do?" -> answered from the law summaries.
6. **Family** account on the same case -> sees the documents and facts but
   can't confirm them (only advocate/NGO/case owner can).

The point to make: *the app never lets a misread number from a scan reach
the AI as fact - a person confirms it first.*

## If something goes wrong

| Symptom | Fix |
|---|---|
| "Can't reach the server" on sign-in | Is the start_demo window still open and the laptop online? Wait a minute and retry - the app looks the address up again by itself |
| Script: "Docker did not come up" | Open Docker Desktop, wait for *Engine running*, run the script again |
| Script: llama-server not found | `-LlamaExe` / `-ModelPath` to your paths, or `-NoAI` to demo without chat |
| Chat: "AI is offline" | llama-server window closed - re-run the script |
| Chat: "took too long" | Cloudflare stops requests at ~100 s; ask a shorter question |
| Scans upload as "No text layer" | Tesseract/poppler not found - check `TESSERACT_CMD` / `POPPLER_PATH` in `backend\.env` |
| Phone won't install the APK | Allow "install unknown apps" for the app you opened it from |

For a permanent address that doesn't need your laptop, see
`deploy/README.md` (cloud VM).
