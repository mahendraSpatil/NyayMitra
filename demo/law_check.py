"""Asks nyaymitra-v2 the questions families ask about the law, with and
without the RELEVANT LAW summaries from backend/app/llm/statute_kb.py,
using exactly the prompt the backend sends. Shows whether grounding
changes the answers. Output: demo/.state/law_check.json and the console.

Usage (backend venv python, llama-server on 8081 with v2 loaded):
    python demo/law_check.py [--port 8081]
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings  # noqa: E402
from app.llm.prompts import build_alpaca_prompt  # noqa: E402
from app.llm.statute_kb import find_provisions, statute_context  # noqa: E402

CASE = {"undertrialName": "Ramesh Kale", "firNumber": "214/2026", "court": "Sessions Court, Pune"}
FIR = (
    "[fir #1]\nFIRST INFORMATION REPORT (FIR) No. 214/2026, Police Station Swargate, Pune City. "
    "Under Section 379 of the Indian Penal Code. The accused, Ramesh Kale, was arrested on 14 March 2026. "
    "He has been in custody since that date and has not been convicted. "
    "The next hearing is on 22 July 2026 before the Sessions Court, Pune."
)
QUESTIONS = [
    "What does Section 436A CrPC say about undertrials?",
    "How long can police keep him in custody before a charge sheet?",
    "Can he get bail?",
    "We cannot afford a lawyer. What can we do?",
    "Why was he arrested?",
    "Did the police have to tell him the grounds of arrest?",
    "Within how many hours must he be taken to a magistrate?",
    "How long will he stay in jail without a verdict?",
    "What is the name of the judge?",
]


def ask(client, port, prompt):
    t0 = time.time()
    r = client.post(f"http://127.0.0.1:{port}/completion", json={
        "prompt": prompt, "n_predict": settings.llm_max_tokens, "temperature": settings.llm_temperature,
        "stop": settings.llm_alpaca_stop, "cache_prompt": True})
    r.raise_for_status()
    j = r.json()
    return {"text": j["content"].strip(), "seconds": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8081)
    args = ap.parse_args()
    out = Path(__file__).parent / ".state" / "law_check.json"
    results = []
    with httpx.Client(timeout=600) as client:
        for q in QUESTIONS:
            law = statute_context(q)
            entry = {"question": q, "law_sent": " | ".join(p.title for p in find_provisions(q)),
                     "without_law": ask(client, args.port, build_alpaca_prompt(CASE, FIR, "", q))}
            entry["with_law"] = ask(client, args.port, build_alpaca_prompt(CASE, FIR, law, q)) if law else entry["without_law"]
            results.append(entry)
            print(f"\nQ: {q}\n   law: {entry['law_sent'] or '(none)'}")
            print(f"   WITHOUT: {entry['without_law']['text']}")
            if law:
                print(f"   WITH   : {entry['with_law']['text']}  ({entry['with_law']['seconds']}s)")
            out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nsaved", out)


if __name__ == "__main__":
    main()
