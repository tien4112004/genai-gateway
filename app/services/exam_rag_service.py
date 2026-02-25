import json
import logging
import re
import uuid
from datetime import datetime

from app.schemas.exam_content import (
    DimensionSubtopic,
    DimensionTopic,
    ExamMatrix,
    GenerateMatrixRequest,
    GenerateQuestionsFromTopicRequest,
    MatrixDimensions,
    MatrixMetadata,
    Question,
)
from app.services.base_rag_service import BaseRagService

logger = logging.getLogger(__name__)


class ExamRagService(BaseRagService):
    """Service for generating exam content (matrices and questions) using RAG.

    Handles exam matrix and question generation with document retrieval
    based on subject and grade filters.
    """

    def _extract_json(self, result: str) -> str:
        """Extract JSON from potential markdown code blocks.

        Args:
            result: Result string that may contain JSON in markdown code blocks

        Returns:
            Extracted JSON string
        """
        result_text = result.strip()
        code_fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        match = re.search(code_fence_pattern, result_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return result_text

    def generate_matrix_with_rag(
        self, request: GenerateMatrixRequest
    ) -> ExamMatrix:
        """Generate exam matrix using LLM with RAG.

        Args:
            request: Request object containing parameters for matrix generation

        Returns:
            Generated ExamMatrix object

        Raises:
            ContentMismatchError: If retrieved documents don't match topic/subject/grade
            ValueError: If matrix generation or parsing fails
        """
        sys_msg = self._system_with_subject_grade(
            "exam.matrix.system.rag",
            request.to_dict(),
            request.subject,
            request.grade,
        )
        usr_msg = self._system("exam.matrix.user", request.to_dict())

        filters = self._build_filters(request.subject, request.grade)

        result, _ = self._rag_batch_call(
            provider=request.provider,
            model=request.model,
            query=usr_msg,
            system_prompt=sys_msg,
            filters=filters,
        )

        try:
            result_text = self._extract_json(result["answer"])
            matrix_data = json.loads(result_text)

            metadata = MatrixMetadata(
                id=matrix_data.get("metadata", {}).get(
                    "id", str(uuid.uuid4())
                ),
                name=matrix_data.get("metadata", {}).get("name", request.name),
                grade=request.grade,
                subject=request.subject,
                created_at=matrix_data.get("metadata", {}).get(
                    "createdAt", datetime.utcnow().isoformat()
                ),
            )

            dims_data = matrix_data.get("dimensions", {})
            topics = [
                DimensionTopic(
                    name=t.get("name", "Unknown"),
                    subtopics=[
                        DimensionSubtopic(
                            id=st.get("id", str(uuid.uuid4())),
                            name=st.get("name", "Unknown"),
                        )
                        for st in t.get("subtopics", [])
                    ],
                    hasContext=t.get("hasContext", False),
                )
                for t in dims_data.get("topics", [])
            ]

            dimensions = MatrixDimensions(
                topics=topics,
                difficulties=dims_data.get(
                    "difficulties",
                    ["KNOWLEDGE", "COMPREHENSION", "APPLICATION"],
                ),
                question_types=dims_data.get(
                    "questionTypes",
                    [
                        "MULTIPLE_CHOICE",
                        "FILL_IN_BLANK",
                        "TRUE_FALSE",
                        "MATCHING",
                    ],
                ),
            )

            raw_matrix = matrix_data.get("matrix", [])
            parsed_matrix = []
            for topic_row in raw_matrix:
                diff_rows = []
                for diff_row in topic_row:
                    qtype_cells = []
                    for cell in diff_row:
                        if isinstance(cell, str):
                            qtype_cells.append(cell)
                        elif isinstance(cell, list):
                            qtype_cells.append(
                                f"{int(cell[0])}:{float(cell[1])}"
                            )
                        else:
                            qtype_cells.append(
                                f"{cell.get('count', 0)}:{cell.get('points', 0)}"
                            )
                    diff_rows.append(qtype_cells)
                parsed_matrix.append(diff_rows)

            return ExamMatrix(
                metadata=metadata, dimensions=dimensions, matrix=parsed_matrix
            )

        except Exception as e:
            raise ValueError(f"Failed to create matrix with RAG: {e}")

    def generate_questions_with_rag(
        self, request: GenerateQuestionsFromTopicRequest
    ) -> list[Question]:
        """Generate exam questions using LLM with RAG.

        Args:
            request: Request object containing parameters for question generation

        Returns:
            List of generated Question objects

        Raises:
            ContentMismatchError: If retrieved documents don't match topic/subject/grade
            ValueError: If question generation or parsing fails, or if no questions requested
        """
        total_questions = sum(request.questions_per_difficulty.values())
        if total_questions == 0:
            raise ValueError("Total questions must be greater than 0")

        difficulty_distribution = "\n".join(
            [
                f"  - {difficulty}: {count} questions"
                for difficulty, count in request.questions_per_difficulty.items()
                if count > 0
            ]
        )

        subject_map = {
            "T": "Toán (Mathematics)",
            "TV": "Tiếng Việt (Vietnamese)",
            "TA": "Tiếng Anh (English)",
        }
        subject_name = subject_map.get(request.subject, request.subject)

        question_types_str = ", ".join(request.question_types)
        additional_req = ""
        if request.prompt:
            additional_req = f"\n**Additional Requirements**: {request.prompt}"

        prompt_vars = {
            "topic": request.topic,
            "grade": request.grade,
            "subject": subject_name,
            "total_questions": total_questions,
            "difficulty_distribution": difficulty_distribution,
            "question_types": question_types_str,
            "prompt": additional_req,
        }

        sys_msg = self._system_with_subject_grade(
            "question.system.rag",
            None,
            request.subject,
            request.grade,
        )
        usr_msg = self._system("question.user", prompt_vars)

        filters = self._build_filters(request.subject, request.grade)

        result, _ = self._rag_batch_call(
            provider=request.provider,
            model=request.model,
            query=usr_msg,
            system_prompt=sys_msg,
            filters=filters,
        )

        try:
            answer = result.get("answer", "")
            logger.info(
                f"[EXAM_RAG_SERVICE] RAG response length: {len(answer)} chars"
            )

            if not answer or not answer.strip():
                logger.error("[EXAM_RAG_SERVICE] LLM returned empty response")
                raise ValueError(
                    "LLM returned empty response - no questions generated"
                )

            result_text = self._extract_json(answer)

            if not result_text:
                logger.error(
                    "[EXAM_RAG_SERVICE] No JSON content extracted from response"
                )
                raise ValueError("No JSON content found in LLM response")

            questions_data = json.loads(result_text)

            if not isinstance(questions_data, list):
                raise ValueError(
                    f"Expected list of questions, got {type(questions_data)}"
                )

            if len(questions_data) != total_questions:
                logger.warning(
                    f"[EXAM_RAG_SERVICE] Expected {total_questions} questions, got {len(questions_data)}"
                )

            questions = []
            for i, q in enumerate(questions_data):
                try:
                    question = Question(**q)
                    questions.append(question)
                except Exception as e:
                    logger.error(
                        f"[EXAM_RAG_SERVICE] Failed to parse question {i}: {e}"
                    )
                    logger.error(f"[EXAM_RAG_SERVICE] Question data: {q}")
                    raise ValueError(
                        f"Invalid question format at index {i}: {e}"
                    )

            logger.info(
                f"[EXAM_RAG_SERVICE] Successfully generated {len(questions)} questions"
            )
            return questions

        except json.JSONDecodeError as e:
            logger.error(f"[EXAM_RAG_SERVICE] JSON parsing error: {e}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")
