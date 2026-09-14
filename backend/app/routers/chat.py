from fastapi import APIRouter

from ..models.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    # TODO(ocr_service): not connected — no document text is read here.
    # TODO(ner_service): no jurisdiction/statute extraction yet.
    # TODO(retrieval_service): no case-law retrieval yet.
    # TODO(generation_service): no Gemini/Mistral call yet — the text
    #     below is a hardcoded placeholder, not a model response.
    # TODO(translation_service): no Bhashini translation yet.
    # TODO(verification_service): always unverified until both law
    #     grounding and document faithfulness are implemented. Per
    #     CLAUDE.md's fail-closed rule, never stub this to return verified.
    return ChatResponse(
        text=(
            f"You asked: \"{payload.message}\". This is a placeholder reply "
            "from NyayMitra AI's stub service — the real verification "
            "pipeline isn't connected yet. Please confirm anything "
            "important with your advocate."
        ),
        verificationStatus="unverified",
        citedSections=[],
    )
