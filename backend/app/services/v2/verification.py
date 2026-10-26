"""Fail-closed placeholder for /chat's verification step (NyayMitra.md's
"Verification" section: law grounding + document faithfulness, hard
veto, both must pass before a claim reaches a user). Neither check
actually exists yet — there's no statute_kb to confirm a citation is
real and current against, and no document_faithfulness classifier — so
this can never legitimately return verified=True.

Built now, in this fail-closed form, specifically so nothing later
"improves" it into faking a passed verification to make a demo look
better: this IS the floor, not a stand-in for something stricter that's
already implemented elsewhere.

cited_sections is real extraction, not a placeholder — it's just string
extraction of what the model claimed to cite, never confirmation that
those citations are correct or still current. Citing a section and being
verified against it are different claims; populating this one doesn't
relax the fail-closed rule on the other.
"""

import re
from dataclasses import dataclass, field

# Matches "Section 436A CrPC", "S. 302 IPC", "u/s 479 BNSS", etc. —
# deliberately permissive. A citation this regex misses just never shows
# up in cited_sections; it isn't "never checked" in any stronger sense,
# since nothing here checks citations against real law either way (see
# the module docstring) — err toward catching more plausible styles.
_CITATION_RE = re.compile(
    r"(?:Section|S\.?|u/s)\s*(\d+[A-Za-z\-]*)\s*(CrPC|IPC|BNSS|BNS|Cr\.?P\.?C\.?)",
    re.IGNORECASE,
)


@dataclass
class VerifyResult:
    verified: bool
    cited_sections: list[str] = field(default_factory=list)


def verify_draft(text: str) -> VerifyResult:
    sections: list[str] = []
    for number, act in _CITATION_RE.findall(text):
        label = f"Section {number} {act.upper().replace('.', '')}"
        if label not in sections:
            sections.append(label)

    return VerifyResult(verified=False, cited_sections=sections)
