from __future__ import annotations

import logging
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.agents.harness import AgentHarness
from backend.rag.milvus import MilvusRagStore
from backend.schemas.workflow import (
    DocumentParseResponse,
    DocumentParseResult,
    FollowUpAnalysisRequest,
    FollowUpAnalysisResponse,
    JobProfile,
    ResumeProfile,
)
from backend.services.documents import chunk_pages, extract_upload_pages

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"])


@router.post("/documents/parse", response_model=DocumentParseResponse)
async def parse_documents(
    document_type: Literal["jd", "resume"] = Form(...),
    files: list[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="at least one file is required")

    logger.info("Document parse request start | type=%s files=%s", document_type, len(files))
    harness = AgentHarness()
    rag_store = MilvusRagStore()
    results: list[DocumentParseResult] = []

    for file in files:
        filename = file.filename or "upload"
        try:
            logger.info("Document parse file start | type=%s filename=%s", document_type, filename)
            pages = await extract_upload_pages(file)
            raw_text = "\n\n".join(page.text for page in pages)
            document_id = f"{document_type}_{uuid4().hex[:12]}"
            candidate_id = document_id if document_type == "resume" else ""
            chunks = chunk_pages(
                pages=pages,
                run_id=document_id,
                candidate_id=candidate_id,
                document_type=document_type,
                filename=filename,
            )
            rag_store.index_chunks(chunks)

            if document_type == "jd":
                profile = harness.run_schema(
                    task="document.parse_jd",
                    prompt_name="parse_jd",
                    schema=JobProfile,
                    variables={"jd_text": raw_text[:24000]},
                )
                parsed_content = profile.model_dump(mode="json")
                parsed_content["title"] = profile.job_title
                summary = profile.summary
                artifact_type = "job_profile"
            else:
                chunks_payload = [
                    {
                        "chunk_id": chunk.id,
                        "page_number": chunk.page_number,
                        "section": chunk.section,
                        "text": chunk.text,
                    }
                    for chunk in chunks
                ]
                profile = harness.run_schema(
                    task="document.parse_resume",
                    prompt_name="parse_resume",
                    schema=ResumeProfile,
                    variables={"filename": filename, "chunks_json": chunks_payload[:80]},
                )
                parsed_content = profile.model_dump(mode="json")
                parsed_content["name"] = profile.candidate_name
                summary = profile.candidate_name
                artifact_type = "resume_profile"

            rag_store.persist_artifact(
                run_id=document_id,
                candidate_id=candidate_id,
                artifact_type=artifact_type,
                summary=summary,
                content=parsed_content,
            )

            results.append(
                DocumentParseResult(
                    id=document_id,
                    type=document_type,
                    filename=filename,
                    size=file.size or len(raw_text.encode("utf-8")),
                    raw_text=raw_text,
                    parsed_content=parsed_content,
                )
            )
            logger.info("Document parse file completed | type=%s id=%s filename=%s", document_type, document_id, filename)
        except Exception as exc:
            logger.exception("Document parse file failed | type=%s filename=%s", document_type, filename)
            raise HTTPException(status_code=400, detail=f"{filename}: {exc}") from exc

    logger.info("Document parse request completed | type=%s parsed=%s", document_type, len(results))
    return DocumentParseResponse(documents=results)


@router.post("/followups/analyze", response_model=FollowUpAnalysisResponse)
async def analyze_followup(request: FollowUpAnalysisRequest):
    logger.info(
        "Follow-up analysis start | question_chars=%s answer_chars=%s history=%s",
        len(request.question),
        len(request.answer),
        len(request.history),
    )
    if len(request.question.strip()) < 4:
        raise HTTPException(status_code=400, detail="question is required")
    if len(request.answer.strip()) < 2:
        raise HTTPException(status_code=400, detail="answer is required")

    try:
        result = AgentHarness().run_schema(
            task="followup.analyze_answer",
            prompt_name="generate_followup",
            schema=FollowUpAnalysisResponse,
            variables=request.model_dump(mode="json"),
        )
    except Exception as exc:
        logger.exception("Follow-up analysis failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Follow-up analysis completed | follow_up_chars=%s", len(result.follow_up))
    return result
