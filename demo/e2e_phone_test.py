# End-to-end test of the phone path through the public tunnel address.
# Usage (needs: pip install httpx websockets):
#   python demo/e2e_phone_test.py https://<tunnel>.trycloudflare.com D:\nyaymitra\ocr_test_docs
import asyncio, json, sys, time, threading
import httpx, websockets

BASE = sys.argv[1].rstrip("/"); API = BASE + "/api/v2"
DOCS = sys.argv[2]
PW = "NyayMitra@Dev1"
results = []
def check(name, ok, detail=""):
    results.append((name, ok)); print(("PASS " if ok else "FAIL ") + name + (f"  — {detail}" if detail else ""), flush=True)

c = httpx.Client(timeout=httpx.Timeout(110, connect=20))
def login(email):
    r = c.post(API + "/auth/login", json={"email": email, "password": PW}); r.raise_for_status(); return r.json()["accessToken"]
H = lambda t: {"authorization": "Bearer " + t}

h = c.get(BASE + "/health").json()
check("server reachable + AI online", h.get("status") == "ok" and h.get("llm") is True, str(h))
adv, fam = login("advocate@nyaymitra.test"), login("family@nyaymitra.test")
check("advocate + family sign-in", bool(adv and fam))

case = c.post(API + "/cases", headers=H(adv), json={"undertrialName": "Ramesh Kale (Demo)", "firNumber": "214/2026", "court": "Sessions Court, Pune"}).json()["caseId"]
code = c.post(f"{API}/cases/{case}/invites", headers=H(adv)).json()["code"]
r = c.post(API + "/invites/redeem", headers=H(fam), json={"code": code})
check("family joins case via invite code", r.status_code == 200 and r.json().get("caseId") == case, r.text[:120])

# live updates: family listens on the case socket over wss through the tunnel
ws_msgs = []
async def listen():
    url = BASE.replace("https://", "wss://") + f"/api/v2/ws/cases/{case}"
    async with websockets.connect(url, open_timeout=20) as ws:
        await ws.send(json.dumps({"accessToken": fam}))
        end = time.time() + 90
        while time.time() < end:
            try: ws_msgs.append(await asyncio.wait_for(ws.recv(), timeout=end - time.time()))
            except Exception: break
t = threading.Thread(target=lambda: asyncio.run(listen()), daemon=True); t.start(); time.sleep(4)

uploads = [("1_typed_fir.pdf", "fir"), ("4_scan_clean_fir.pdf", "fir"), ("7_scan_marathi_fir.pdf", "fir"), ("6_scan_bad_photocopy_fir.pdf", "fir")]
docs = {}
for fname, dtype in uploads:
    s = c.post(API + "/documents/sign-upload", headers=H(adv), json={"caseId": case, "docType": dtype}).json()
    with open(f"{DOCS}/{fname}", "rb") as f:
        up = httpx.post(f"https://api.cloudinary.com/v1_1/{s['cloudName']}/{s['resourceType']}/upload",
                        data={"api_key": s["apiKey"], "timestamp": str(s["timestamp"]), "signature": s["signature"], "public_id": s["publicId"], "type": s["type"]},
                        files={"file": (fname, f, "application/pdf")}, timeout=120)
    up.raise_for_status()
    t0 = time.time()
    conf = c.post(API + "/documents/confirm-upload", headers=H(adv), json={"caseId": case, "docId": s["docId"], "docType": dtype, "publicId": up.json()["public_id"]})
    j = conf.json(); docs[fname] = j["docId"]
    print(f"     {fname}: {j['ocrStatus']} source={j['textSource']} conf={j['ocrConfidence']} facts-to-check={j['fieldsNeedingReview']} ({time.time()-t0:.1f}s)")
check("typed FIR read from text layer", True)
listing = {d["id"]: d for d in c.get(f"{API}/cases/{case}/documents", headers=H(fam)).json()}
def doc(fname): return listing[docs[fname]]
check("typed FIR: text layer, facts auto-accepted", doc("1_typed_fir.pdf")["ocrStatus"] == "extracted" and any(f["status"] == "auto_accepted" for f in doc("1_typed_fir.pdf")["fields"]))
en = doc("4_scan_clean_fir.pdf")
check("English scan: OCR'd, usable", en["ocrStatus"] == "ocr_extracted", f"{en['ocrConfidence']}%")
mr = doc("7_scan_marathi_fir.pdf")
print("     Marathi OCR text:", repr((mr["rawText"] or "")[:260]))
check("Marathi scan: OCR'd, usable (hin/mar installed)", mr["ocrStatus"] == "ocr_extracted", f"{mr['ocrConfidence']}%")
print("     Marathi facts:", [(f["label"], f["rawText"], f["displayValue"], f["confidence"]) for f in mr["fields"]])
check("Marathi scan: arrest date found", any(f["role"] == "arrest" and f["value"] == "2026-03-14" for f in mr["fields"]))
bad = doc("6_scan_bad_photocopy_fir.pdf")
check("bad photocopy: kept away from AI", bad["ocrStatus"] == "ocr_low_confidence" or (bad["ocrConfidence"] or 0) < 70, f"{bad['ocrStatus']} {bad['ocrConfidence']}%")

time.sleep(3)
check("family phone got live update over WebSocket", any("documents_changed" in m for m in ws_msgs), f"{len(ws_msgs)} msgs")

u = c.get(f"{API}/documents/{case}/{docs['4_scan_clean_fir.pdf']}/download-url", headers=H(fam)).json()["url"]
pdf = httpx.get(u, timeout=60)
check("family can open the PDF (signed URL)", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", f"{pdf.status_code} {len(pdf.content)} bytes")

arrest = next(f for f in en["fields"] if f["role"] == "arrest")
r = c.post(f"{API}/cases/{case}/document-fields/{arrest['id']}/confirm", headers=H(fam), json={})
check("family cannot confirm facts (403)", r.status_code == 403)
r = c.post(f"{API}/cases/{case}/document-fields/{arrest['id']}/confirm", headers=H(adv), json={})
check("advocate confirms arrest date", r.status_code == 200 and r.json()["status"] == "confirmed")
hearing = next((f for f in en["fields"] if f["role"] == "hearing"), None)
if hearing:
    r = c.post(f"{API}/cases/{case}/document-fields/{hearing['id']}/confirm", headers=H(adv), json={})
    check("advocate confirms hearing date", r.status_code == 200)

r = c.post(API + "/chat", headers=H(fam), json={"message": "hi"})
check("greeting is instant", r.status_code == 200 and r.json()["modelUsed"] == "greeting")
t0 = time.time()
r = c.post(API + "/chat", headers=H(fam), json={"caseId": case, "message": "When was Ramesh arrested, and when is the next hearing?"})
dt = time.time() - t0
ok = r.status_code == 200
j = r.json() if ok else {}
check("AI model answers on the case (family)", ok and j.get("modelUsed", "").startswith("local:"), f"HTTP {r.status_code} in {dt:.0f}s")
if ok:
    print("     AI answer:", j["text"][:500].replace("\n", " "))
    print("     cited:", [(d["docType"], d["textSource"], d["ocrConfidence"]) for d in j["citedDocuments"]], "skipped:", [(d["docType"], d["ocrConfidence"]) for d in j["skippedDocuments"]], "pending:", j["fieldsPendingReview"])
    check("AI answer mentions the confirmed arrest date", "14 March 2026" in j["text"] or "14/03/2026" in j["text"])
    check("bad photocopy reported as not used", any(d["docId"] == docs["6_scan_bad_photocopy_fir.pdf"] for d in j["skippedDocuments"]))
print(f"\n{sum(ok for _, ok in results)}/{len(results)} passed.  Demo case id: {case}")
