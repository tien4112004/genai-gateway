from fastapi import APIRouter

from .endpoints import exams, generate, grading_question, modification

api = APIRouter()
api.include_router(generate.router)
api.include_router(exams.router)
api.include_router(modification.router)
api.include_router(grading_question.router)
