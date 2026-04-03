from fastapi import FastAPI
from backend.routes.upload import router as upload_router

# ✅ IMPORT THIS
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ✅ CORRECT FORMAT (multi-line, clean)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all (development only)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
