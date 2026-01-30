import os
from dotenv import load_dotenv
load_dotenv() 

DATABASE_URL = os.getenv("DATABASE_URL")

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, Integer, String, Text, select
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from typing import List, Optional

# ===== DATABASE SETUP =====
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# ===== MODELS =====
class Note(Base):
    __tablename__ = "notes"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)

# ===== PYDANTIC SCHEMAS =====
class NoteCreate(BaseModel):
    title: str
    content: str

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class NoteResponse(BaseModel):
    id: int
    title: str
    content: str
    user_id: int
    
    model_config = ConfigDict(from_attributes=True)

# ===== DEPENDENCIES =====
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

def get_user_id(x_user_id: int = Header(..., alias="X-User-ID")):
    return x_user_id

# ===== FASTAPI APP =====
app = FastAPI(title="Notes Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== DATABASE INIT =====
@app.on_event("startup")
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ===== ENDPOINTS =====
@app.get("/")
async def root():
    return {"service": "Notes Service", "status": "running"}

@app.post("/notes", response_model=NoteResponse, status_code=201)
async def create_note(
    note_data: NoteCreate,
    user_id: int = Depends(get_user_id),
    db: AsyncSession = Depends(get_db)
):
    new_note = Note(
        title=note_data.title,
        content=note_data.content,
        user_id=user_id
    )
    db.add(new_note)
    await db.flush()
    return new_note

@app.get("/notes", response_model=List[NoteResponse])
async def get_notes(
    user_id: int = Depends(get_user_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Note).where(Note.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@app.get("/notes/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: int,
    user_id: int = Depends(get_user_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Note).where(Note.id == note_id, Note.user_id == user_id)
    result = await db.execute(stmt)
    note = result.scalars().first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note

@app.put("/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    note_data: NoteUpdate,
    user_id: int = Depends(get_user_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Note).where(Note.id == note_id, Note.user_id == user_id)
    result = await db.execute(stmt)
    note = result.scalars().first()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    if note_data.title is not None:
        note.title = note_data.title
    if note_data.content is not None:
        note.content = note_data.content
    
    await db.flush()
    await db.refresh(note)
    return note

@app.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    user_id: int = Depends(get_user_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Note).where(Note.id == note_id, Note.user_id == user_id)
    result = await db.execute(stmt)
    note = result.scalars().first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    await db.delete(note)
    return None

@app.get("/health")
async def health_check():
    return {"status": "healthy"}