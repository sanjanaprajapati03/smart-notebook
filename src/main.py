from contextlib import asynccontextmanager
from fastapi import FastAPI
from neo4j import AsyncGraphDatabase
import asyncpg

from .core.config import (
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    POSTGRES_DSN,
)
from . import state
from .routes.auth import router as auth_router
from .routes.notes import router as notes_router
from .routes.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        state.pg_pool = await asyncpg.create_pool(dsn=POSTGRES_DSN, min_size=1, max_size=5)
        async with state.pg_pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL
                )
                """
            )

        state.db_driver = AsyncGraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        async with state.db_driver.session() as session:
            await session.run(
                "CREATE CONSTRAINT unique_note_id IF NOT EXISTS FOR (n:Note) REQUIRE n.id IS UNIQUE"
            )
            await session.run(
                "CREATE CONSTRAINT unique_chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE"
            )
            await session.run(
                """
                CREATE VECTOR INDEX note_chunks_vector_index IF NOT EXISTS
                FOR (c:Chunk) ON (c.embedding)
                OPTIONS { indexConfig: { `vector.dimensions`: 1536, `vector.similarity_function`: 'cosine' } }
                """
            )
            print("Databases initialized and constraints verified.")
        yield
    except Exception as exc:
        print(f"Database initialization failed: {exc}")
        raise
    finally:
        if state.db_driver:
            await state.db_driver.close()
            print("Database driver connection closed cleanly.")
        if state.pg_pool:
            await state.pg_pool.close()
            print("Postgres pool closed cleanly.")


app = FastAPI(title="AI Hidden Relationship Engine", lifespan=lifespan)
app.include_router(auth_router, prefix="/v1/auth", tags=["auth"])
app.include_router(notes_router, prefix="/v1/notes", tags=["notes"])
app.include_router(health_router, tags=["health"])
