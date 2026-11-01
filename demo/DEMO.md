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
   instead of guessing. (Takes ~40 s on the laptop.)
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
