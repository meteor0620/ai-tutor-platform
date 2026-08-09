"""AI 教辅智学平台后端主应用"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
import questions
import papers
import knowledge
import analytics

app = FastAPI(title="AI 教辅智学平台后端", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

app.include_router(questions.router)
app.include_router(papers.router)
app.include_router(knowledge.router)
app.include_router(analytics.router)

@app.get("/")
def root():
    return {"service": "AI 教辅智学平台后端", "status": "running"}
