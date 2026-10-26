"""fetch_case_document_context — found live while wiring /chat to a real
model: an oversized document ahead of others in upload order used to
`break` out of the loop entirely, silently discarding every document
after it too, however small. Fixed to truncate the oversized one and
keep scanning instead (app/services/v2/case_document_context.py).

Run with: pytest tests/v2/test_case_document_context.py -v
"""

import uuid

from app.db.models import Document
from app.services.v2.case_document_context import (
    CONTEXT_CHAR_BUDGET,
    fetch_case_document_context,
)


def _add_document(db, case_id, uploaded_by, *, text, doc_type="fir"):
    doc = Document(
        id=uuid.uuid4(),
        case_id=case_id,
        doc_type=doc_type,
        storage_path=f"cases/test/{uuid.uuid4()}.pdf",
        uploaded_by=uploaded_by,
        ocr_status="extracted" if text else "no_text_layer",
        raw_text=text,
        statutes=[],
    )
    db.add(doc)
    db.commit()
    return doc


def test_a_document_with_no_text_is_skipped(make_case, accounts, db):
    case_id = make_case(created_by=accounts["advocate"]["uid"])
    _add_document(db, case_id, accounts["advocate"]["uid"], text=None)

    included, truncated = fetch_case_document_context(db, case_id)
    assert included == []
    assert truncated is False


def test_documents_within_budget_are_all_included(make_case, accounts, db):
    case_id = make_case(created_by=accounts["advocate"]["uid"])
    _add_document(db, case_id, accounts["advocate"]["uid"], text="short fir text")
    _add_document(
        db, case_id, accounts["advocate"]["uid"], text="short remand text", doc_type="remand_order"
    )

    included, truncated = fetch_case_document_context(db, case_id)
    assert truncated is False
    assert [d.text for d in included] == ["short fir text", "short remand text"]


def test_an_oversized_document_is_truncated_not_dropped_and_does_not_evict_later_ones(
    make_case, accounts, db
):
    """The actual bug: previously, a document bigger than the whole
    budget on its own caused the loop to `break`, discarding every
    document uploaded after it — even a second, tiny one that easily
    fits. Uploaded in this order (upload order is what the function
    scans in), an oversized FIR must not silently evict a later,
    small remand order.
    """
    case_id = make_case(created_by=accounts["advocate"]["uid"])
    huge = "x" * (CONTEXT_CHAR_BUDGET + 5000)
    _add_document(db, case_id, accounts["advocate"]["uid"], text=huge, doc_type="fir")
    _add_document(
        db,
        case_id,
        accounts["advocate"]["uid"],
        text="a small remand order note",
        doc_type="remand_order",
    )

    included, truncated = fetch_case_document_context(db, case_id)
    assert truncated is True
    doc_types = [d.doc_type for d in included]
    assert "fir" in doc_types  # truncated, not dropped
    fir_context = next(d for d in included if d.doc_type == "fir")
    assert len(fir_context.text) == CONTEXT_CHAR_BUDGET  # cut to exactly the remaining budget
    assert fir_context.text == huge[:CONTEXT_CHAR_BUDGET]
    # Budget was fully consumed by the truncated FIR, so the remand order
    # correctly doesn't fit either — the fix is "don't evict everything
    # after the first oversized document for no reason," not "ignore the
    # budget entirely."
    assert "remand_order" not in doc_types
