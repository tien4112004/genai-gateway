"""API endpoints for grading open-ended questions."""

import json
import logging

from fastapi import APIRouter, HTTPException, status
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.llms.executor import LLMExecutor
from app.prompts.loader import PromptStore
from app.schemas.grading import GradeQuestionRequest, GradeQuestionResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["grading"])


class GradingService:
    """Service for grading open-ended questions using AI."""

    # Hardcoded Gemini Flash 2.5 Lite model
    MODEL = "gemini-2.5-flash-lite"
    PROVIDER = "google"

    def __init__(self, llm_executor: LLMExecutor, prompt_store: PromptStore):
        self.llm_executor = llm_executor or LLMExecutor()
        self.prompt_store = prompt_store or PromptStore()

    def _render_prompt(
        self, key: str, variables: dict | None
    ) -> str:
        """Render a prompt from the prompt store."""
        return self.prompt_store.render(key, variables)

    def grade_question(
        self, request: GradeQuestionRequest
    ) -> GradeQuestionResponse:
        """
        Grade an open-ended question using AI.

        Args:
            request: The grading request containing question and answer details

        Returns:
            GradeQuestionResponse with score and feedback
        """
        try:
            # Prepare prompt variables
            prompt_vars = {
                "questionContent": request.questionContent,
                "questionExplaination": request.questionExplaination or "",
                "context": request.context or "",
                "answerData": request.answerData,
                "expectedAnswer": request.expectedAnswer or "",
                "maxScore": request.maxScore,
                "grade": request.grade,
                "chapter": request.chapter or "",
                "subject": request.subject or "",
            }

            # Render system and user prompts
            sys_prompt = self._render_prompt(
                "question.grading.system", prompt_vars
            )
            user_prompt = self._render_prompt(
                "question.grading.user", prompt_vars
            )

            # Create messages for LLM
            messages = [
                SystemMessage(content=sys_prompt),
                HumanMessage(content=user_prompt),
            ]

            # Call the LLM with hardcoded Gemini Flash 2.5 Lite
            response_text, token_usage = self.llm_executor.batch(
                provider=self.PROVIDER,
                model=self.MODEL,
                messages=messages,
            )

            logger.info(
                f"Grading completed for question: {request.questionContent} "
                f"(tokens used: {token_usage.total_tokens})"
            )

            # Parse the JSON response
            try:
                # Extract JSON from markdown code blocks if present
                parsed_text = response_text.strip()
                if parsed_text.startswith("```json"):
                    # Remove opening ```json
                    parsed_text = parsed_text[7:]
                    if parsed_text.startswith("\n"):
                        parsed_text = parsed_text[1:]
                elif parsed_text.startswith("```"):
                    # Remove opening ```
                    parsed_text = parsed_text[3:]
                    if parsed_text.startswith("\n"):
                        parsed_text = parsed_text[1:]
                
                # Remove closing ``` if present
                if parsed_text.endswith("```"):
                    parsed_text = parsed_text[:-3].strip()
                
                grading_result = json.loads(parsed_text)
                total_score = grading_result.get("totalScore", 0)
                feedback = grading_result.get("feedback", "")

                # Validate score doesn't exceed maxScore
                if total_score > request.maxScore:
                    logger.warning(
                        f"Score {total_score} exceeds maxScore "
                        f"{request.maxScore}, capping it"
                    )
                    total_score = request.maxScore

                return GradeQuestionResponse(
                    totalScore=total_score,
                    feedback=feedback,
                )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                logger.error(f"Raw response: {response_text}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to parse grading response from AI model",
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error grading question: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to grade question: {str(e)}",
            )


@router.post(
    "/questions/grade",
    response_model=GradeQuestionResponse,
)
def grade_question(request_body: GradeQuestionRequest):
    """
    Grade an open-ended student response using AI (Gemini Flash 2.5 Lite).

    This endpoint evaluates a student's answer to an open-ended question
    and provides a score and constructive feedback.

    The grading is based on:
    - Accuracy of content
    - Completeness of key ideas
    - Clarity appropriate for the student's grade level
    - Whether it answers the question correctly

    Args:
        request_body: GradeQuestionRequest containing:
            - questionContent: The main question
            - questionExplaination: Additional explanation (optional)
            - answerData: The student's answer
            - context: Reading passage or context (optional)
            - maxScore: Maximum possible score
            - grade: Student's grade level (1-5)
            - chapter: Chapter or topic (optional)
            - expectedAnswer: The expected/reference answer (optional)
            - subject: Subject of the question (optional)

    Returns:
        GradeQuestionResponse with:
            - totalScore: The awarded score (0 to maxScore)
            - feedback: Supportive feedback for the student
    """
    try:
        service = GradingService(
            llm_executor=LLMExecutor(),
            prompt_store=PromptStore(),
        )
        result = service.grade_question(request_body)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in grade_question endpoint")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to grade question: {str(e)}",
        )
