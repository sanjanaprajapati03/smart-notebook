import asyncio
import json
import math
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import google.generativeai as genai
from pydantic import BaseModel

from ..core.config import (
    GEMINI_API_KEY,
    GEMINI_CHAT_MODEL,
    GEMINI_EMBEDDING_MODEL,
)
from ..dependencies import get_current_user
from .. import state
from ..utils import chunk_text, get_mock_embedding

router = APIRouter()
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
gemini_chat_model = genai.GenerativeModel(GEMINI_CHAT_MODEL) if GEMINI_API_KEY else None
_fallback_gemini_chat_model = None
_PREFERRED_GEMINI_MODELS = (
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
    "gemini-1.0-pro",
)


def _is_model_not_found(exc: Exception) -> bool:
    message = str(exc).lower()
    return "not found" in message or "not supported for generatecontent" in message


def _select_fallback_chat_model():
    global _fallback_gemini_chat_model
    if _fallback_gemini_chat_model is not None:
        return _fallback_gemini_chat_model
    try:
        models = genai.list_models()
    except Exception as exc:
        print(f"Failed to list Gemini models: {exc}")
        return None

    def supports_generate(model) -> bool:
        return "generateContent" in getattr(model, "supported_generation_methods", [])

    for preferred in _PREFERRED_GEMINI_MODELS:
        for model in models:
            if preferred in model.name and supports_generate(model):
                _fallback_gemini_chat_model = genai.GenerativeModel(model.name)
                return _fallback_gemini_chat_model

    for model in models:
        if supports_generate(model):
            _fallback_gemini_chat_model = genai.GenerativeModel(model.name)
            return _fallback_gemini_chat_model

    return None


def _generate_gemini_stream(prompt: str):
    if not gemini_chat_model:
        raise RuntimeError("Gemini chat model is not configured.")

    def stream_with_model(model):
        response = model.generate_content(prompt, stream=True)
        for chunk in response:
            yield chunk

    def stream():
        try:
            yield from stream_with_model(gemini_chat_model)
        except Exception as exc:
            if _is_model_not_found(exc):
                fallback = _select_fallback_chat_model()
                if fallback:
                    yield from stream_with_model(fallback)
                    return
            raise

    return stream()


class NoteCreateRequest(BaseModel):
    content: str
    note_id: str | None = None
    timestamp: int | None = None


class NoteIngestRequest(BaseModel):
    note_id: str
    user_id: str
    content: str
    timestamp: int


class NoteSummary(BaseModel):
    id: str
    content: str
    created_at: int | None = None
    updated_at: int | None = None


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b:
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    if GEMINI_API_KEY:

        async def embed_text(text: str) -> list[float]:
            try:
                response = await asyncio.to_thread(
                    genai.embed_content,
                    model=GEMINI_EMBEDDING_MODEL,
                    content=text,
                    task_type="retrieval_document",
                )
            except Exception as exc:
                print(f"Embedding failed: {exc}")
                return []
            embedding = getattr(response, "embedding", None)
            if embedding is None and isinstance(response, dict):
                embedding = response.get("embedding")
            return embedding or []

        embeddings = await asyncio.gather(*(embed_text(text) for text in texts))
        for idx, embedding in enumerate(embeddings):
            if embedding:
                continue
            embeddings[idx] = await get_mock_embedding(texts[idx])
        return embeddings

    embeddings = []
    for text in texts:
        embeddings.append(await get_mock_embedding(text))
    return embeddings


async def process_and_index_note(note: NoteIngestRequest):
    """
    Asynchronously chunks the text, creates vector embeddings,
    and writes nodes and structural relationships into Neo4j.
    """
    if not state.db_driver:
        print(f"Worker Error: Database driver unavailable for note {note.note_id}")
        return

    text_slices = chunk_text(note.content)
    embeddings = await get_embeddings(text_slices)

    async with state.db_driver.session() as session:
        await session.run(
            """
            MERGE (u:User {id: $user_id})
            MERGE (n:Note {id: $note_id})
            ON CREATE SET n.created_at = $timestamp
            SET n.user_id = $user_id,
                n.content = $content,
                n.updated_at = $timestamp
            MERGE (u)-[:OWNS]->(n)
            WITH n
            OPTIONAL MATCH (n)-[:HAS_CHUNK]->(c:Chunk)
            DETACH DELETE c
            """,
            note_id=note.note_id,
            user_id=note.user_id,
            timestamp=note.timestamp,
            content=note.content,
        )

        for idx, text_chunk in enumerate(text_slices):
            chunk_unique_id = f"{note.note_id}_chunk_{idx}"
            embedding = (
                embeddings[idx]
                if idx < len(embeddings)
                else await get_mock_embedding(text_chunk)
            )

            await session.run(
                """
                MATCH (n:Note {id: $note_id})
                MERGE (c:Chunk {id: $chunk_id})
                SET c.text = $text,
                    c.index = $idx,
                    c.embedding = $embedding
                MERGE (n)-[:HAS_CHUNK]->(c)
                """,
                note_id=note.note_id,
                chunk_id=chunk_unique_id,
                text=text_chunk,
                idx=idx,
                embedding=embedding,
            )

    print(
        f"Worker Success: Fully indexed note {note.note_id} into {len(text_slices)} chunks."
    )


@router.post("")
@router.post("/ingest")
async def ingest_note(
    payload: NoteCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    if not state.db_driver:
        raise HTTPException(status_code=500, detail="Database engine offline.")

    note_id = payload.note_id or str(uuid.uuid4())
    timestamp = payload.timestamp or int(time.time())
    ingest_payload = NoteIngestRequest(
        note_id=note_id,
        user_id=current_user["id"],
        content=payload.content,
        timestamp=timestamp,
    )
    async with state.db_driver.session() as session:
        await session.run(
            """
            MERGE (u:User {id: $user_id})
            MERGE (n:Note {id: $note_id})
            ON CREATE SET n.created_at = $timestamp
            SET n.user_id = $user_id,
                n.content = $content,
                n.updated_at = $timestamp
            MERGE (u)-[:OWNS]->(n)
            """,
            note_id=note_id,
            user_id=current_user["id"],
            timestamp=timestamp,
            content=payload.content,
        )
    background_tasks.add_task(process_and_index_note, ingest_payload)
    return {
        "status": "queued",
        "note_id": note_id,
    }


@router.get("", response_model=list[NoteSummary])
async def list_notes(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    if not state.db_driver:
        raise HTTPException(status_code=500, detail="Database engine offline.")

    safe_limit = max(1, min(limit, 200))
    async with state.db_driver.session() as session:
        result = await session.run(
            """
            MATCH (n:Note {user_id: $user_id})
            RETURN n.id AS id,
                   n.content AS content,
                   n.created_at AS created_at,
                   n.updated_at AS updated_at
            ORDER BY n.updated_at DESC
            LIMIT $limit
            """,
            user_id=current_user["id"],
            limit=safe_limit,
        )
        records = await result.data()

    return [
        {
            "id": rec.get("id"),
            "content": rec.get("content"),
            "created_at": rec.get("created_at"),
            "updated_at": rec.get("updated_at"),
        }
        for rec in records
    ]


@router.get("/discover")
async def discover_relationships(
    limit: int = 10,
    min_score: float = 0.78,
    max_chunks: int = 200,
    note_ids: list[str] | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    if not state.db_driver:
        raise HTTPException(status_code=500, detail="Database engine offline.")

    async def event_generator():
        try:
            if note_ids is not None and not note_ids:
                yield f"data: {json.dumps({'text': 'Select at least one note to analyze.'})}\n\n"
                return

            async with state.db_driver.session() as session:
                note_result = await session.run(
                    """
                    MATCH (n:Note {user_id: $user_id})
                    WHERE $note_ids IS NULL OR n.id IN $note_ids
                    RETURN n.id AS note_id, n.content AS content
                    ORDER BY n.updated_at DESC
                    """,
                    user_id=current_user["id"],
                    note_ids=note_ids,
                )
                note_records = await note_result.data()

            note_blocks = []
            for note in note_records:
                content = (note.get("content") or "").strip()
                if not content:
                    continue
                lines = content.splitlines()
                title = lines[0].strip() if lines else ""
                if not title:
                    title = "Untitled"
                body = "\n".join(lines[1:]).strip()
                if body:
                    note_blocks.append(f"### {title}\n{body}")
                else:
                    note_blocks.append(f"### {title}\n{content}")

            if not note_blocks:
                yield f"data: {json.dumps({'text': 'No notes available to analyze yet.'})}\n\n"
                return

            aggregated_notes = "\n\n".join(note_blocks)
            if not gemini_chat_model:
                yield f"data: {json.dumps({'text': f'Notes selected:\\n{aggregated_notes}'})}\n\n"
                return

            system_prompt = (
                "You are a concise analyst. Identify the most important connections, overlaps, dependencies, "
                "and actionable insights across the notes."
            )
            user_prompt = (
                "Analyze these notes and describe the key relationships and insights. Be specific and concise.\n\n"
                f"{aggregated_notes}"
            )
            prompt = f"{system_prompt}\n\n{user_prompt}"
            print("The prompt being sent to Gemini for discovery:\n", prompt)
            response = _generate_gemini_stream(prompt)
            for chunk in response:
                text = getattr(chunk, "text", None)
                if text:
                    yield f"data: {json.dumps({'text': text})}\n\n"
        except Exception as exc:
            print(f"Discovery failed: {exc}")
            yield f"data: {json.dumps({'text': f'Discovery failed: {exc}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
