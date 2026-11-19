"""Asks nyaymitra-v2 (via llama-server's raw /completion) the same
questions with and without the standard Alpaca preamble, so we can keep
the layout the model actually answers best with.

Usage (backend venv python, llama-server on 8081 with v2 loaded):
    python demo/compare_prompts.py [--port 8081] [--out demo/.state/compare.json]
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.llm.prompts import SYSTEM_PROMPT, alpaca_prompt  # noqa: E402

FIR = (
    "FIRST INFORMATION REPORT (FIR) No. 214/2026, Police Station Swargate, Pune City. "
    "Under Section 379 of the Indian Penal Code. The accused, Ramesh Kale, was arrested "
    "on 14 March 2026. He has been in custody since that date and has not been convicted. "
    "The next hearing is on 22 July 2026 before the Sessions Court, Pune."
)
CASES = [
    ("When was Ramesh arrested?", FIR),
    ("When is the next hearing?", FIR),
    ("What is he accused of, in simple words?", FIR),
    ("Which section of law is he charged under?", FIR),
    ("What does 'undertrial' mean?", ""),
    ("Can he get bail? What should we do next?", FIR),
    ("What is the name of the judge?", FIR),
    ("What does Section 436A CrPC say about undertrials?", ""),
    ("Explain this FIR to me like I am a family member with no legal knowledge.", FIR),
    ("How long can police keep him in custody before a charge sheet?", ""),
]
STOP = ["</s>", "### Instruction", "### Input", "### Response"]


def ask(client, port, prompt):
    t0 = time.time()
    r = client.post(
        f"http://127.0.0.1:{port}/completion",
        json={"prompt": prompt, "n_predict": 300, "temperature": 0.2, "stop": STOP, "cache_prompt": True},
    )
    r.raise_for_status()
    j = r.json()
    return {
        "text": j["content"].strip(),
        "seconds": round(time.time() - t0, 1),
        "tokens": j.get("tokens_predicted"),
        "stopped": j.get("stop_type") or ("eos" if j.get("stopped_eos") else "word" if j.get("stopped_word") else "limit" if j.get("stopped_limit") else None),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--out", default=str(Path(__file__).parent / ".state" / "compare.json"))
    args = ap.parse_args()
    model = httpx.get(f"http://127.0.0.1:{args.port}/v1/models", timeout=10).json()["data"][0]["id"]
    print("model:", model, flush=True)
    results = {"model": model, "cases": []}
    with httpx.Client(timeout=600) as client:
        for q, doc in CASES:
            instruction = f"{SYSTEM_PROMPT}\n\nQuestion from the family: {q}"
            entry = {"question": q}
            for name, pre in (("no_preamble", False), ("preamble", True)):
                entry[name] = ask(client, args.port, alpaca_prompt(instruction, f"DOCUMENT EXCERPT:\n{doc}" if doc else "", preamble=pre))
                print(f"[{name}] {q} -> ({entry[name]['seconds']}s, {entry[name]['stopped']}) {entry[name]['text'][:160]!r}", flush=True)
            results["cases"].append(entry)
            Path(args.out).parent.mkdir(exist_ok=True)
            Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", args.out)


if __name__ == "__main__":
    main()
