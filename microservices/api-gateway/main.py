from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from typing import Any

# ===== KONFIGURACJA =====
import os

# Automatycznie wykrywa czy działa w Dockerze czy lokalnie
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
NOTES_SERVICE_URL = os.getenv("NOTES_SERVICE_URL", "http://localhost:8002")

# ===== FASTAPI APP =====
app = FastAPI(title="API Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== HELPER FUNCTIONS =====
async def validate_token(authorization: str) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{AUTH_SERVICE_URL}/validate-token",
                headers={"Authorization": authorization},
                timeout=5.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token"
                )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Auth service unavailable"
            )

async def forward_to_notes_service(
    method: str,
    path: str,
    user_id: int,
    body: Any = None,
    headers: dict = None
) -> JSONResponse:
    async with httpx.AsyncClient() as client:
        try:
            forward_headers = {"X-User-ID": str(user_id)}
            if headers:
                forward_headers.update(headers)
            
            response = await client.request(
                method=method,
                url=f"{NOTES_SERVICE_URL}{path}",
                json=body,
                headers=forward_headers,
                timeout=10.0
            )
            
            return JSONResponse(
                status_code=response.status_code,
                content=response.json() if response.content else None
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Notes service unavailable"
            )

# ===== ENDPOINTS =====

@app.get("/")
def root():
    return {
        "service": "API Gateway",
        "version": "1.0.0",
        "routes": {
            "auth": ["/api/register", "/api/login"],
            "notes": ["/api/notes", "/api/notes/{id}"]
        }
    }

# ===== AUTH ENDPOINTS =====
@app.post("/api/register")
async def register(request: Request):
    """Przekieruj do Auth Service"""
    body = await request.json()
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AUTH_SERVICE_URL}/register",
            json=body,
            timeout=5.0
        )
        return JSONResponse(
            status_code=response.status_code,
            content=response.json()
        )

@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AUTH_SERVICE_URL}/login",
            json=body,
            timeout=5.0
        )
        return JSONResponse(
            status_code=response.status_code,
            content=response.json()
        )

# ===== NOTES ENDPOINTS (z walidacją tokena) =====

@app.get("/api/notes")
async def get_notes(request: Request):
    
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )
    
    user_data = await validate_token(authorization)
    user_id = user_data["user_id"]
    
    return await forward_to_notes_service("GET", "/notes", user_id)

@app.post("/api/notes")
async def create_note(request: Request):
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    user_data = await validate_token(authorization)
    user_id = user_data["user_id"]
    
    body = await request.json()
    return await forward_to_notes_service("POST", "/notes", user_id, body=body)

@app.get("/api/notes/{note_id}")
async def get_note(note_id: int, request: Request):
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    user_data = await validate_token(authorization)
    user_id = user_data["user_id"]
    
    return await forward_to_notes_service("GET", f"/notes/{note_id}", user_id)

@app.put("/api/notes/{note_id}")
async def update_note(note_id: int, request: Request):
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    user_data = await validate_token(authorization)
    user_id = user_data["user_id"]
    
    body = await request.json()
    return await forward_to_notes_service("PUT", f"/notes/{note_id}", user_id, body=body)

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int, request: Request):
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    user_data = await validate_token(authorization)
    user_id = user_data["user_id"]
    
    return await forward_to_notes_service("DELETE", f"/notes/{note_id}", user_id)

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "api-gateway"}