"""Service for exam and question generation."""

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.llms.executor import LLMExecutor
from app.prompts.loader import PromptStore
from app.schemas.exam_content import (
    DimensionSubtopic,
    DimensionTopic,
    ExamMatrix,
    GenerateMatrixRequest,
    GenerateQuestionsFromContextRequest,
    GenerateQuestionsFromMatrixRequest,
    GenerateQuestionsFromMatrixResponse,
    GenerateQuestionsFromTopicRequest,
    GenerateQuestionsRequest,
    GenerationProgress,
    MatrixCell,
    MatrixContent,
    MatrixDimensions,
    MatrixItem,
    MatrixMetadata,
    Question,
    QuestionGenerationStatus,
    Topic,
    TopicWithQuestions,
    UsedContext,
)
from app.utils.teacher_context import build_system_with_teacher_prompt

logger = logging.getLogger(__name__)


class ExamService:
    """Service for generating exams and questions using AI."""

    def __init__(self, llm_executor: LLMExecutor, prompt_store: PromptStore):
        self.llm_executor = llm_executor or LLMExecutor()
        self.prompt_store = prompt_store or PromptStore()

    def _system(self, key: str, vars: Dict[str, Any] | None) -> str:
        """Render a system prompt from the prompt store."""
        base = self.prompt_store.render(key, vars)
        return build_system_with_teacher_prompt(base)

    # Matrix Generation
    def generate_matrix(self, request: GenerateMatrixRequest) -> ExamMatrix:
        """
        Generate an exam matrix using LLM.

        The matrix is indexed as: matrix[subtopic_index][difficulty_index][question_type_index]
        Each cell contains {count, points} for that combination.

        Args:
            request: Request containing exam requirements and chapters (fetched by backend)

        Returns:
            ExamMatrix object representing the exam structure
        """
        # Prepare prompt variables (chapters already formatted in to_dict())
        prompt_vars = request.to_dict()
        prompt_vars["difficulties"] = request.difficulties or [
            "KNOWLEDGE",
            "COMPREHENSION",
            "APPLICATION",
        ]
        prompt_vars["question_types"] = request.questionTypes or [
            "MULTIPLE_CHOICE",
            "FILL_IN_BLANK",
            "OPEN_ENDED",
            "MATCHING",
        ]

        sys_msg = self._system("exam.matrix.system", prompt_vars)
        usr_msg = self._system("exam.matrix.user", prompt_vars)

        result, token_usage = self.llm_executor.batch(
            provider=request.provider,
            model=request.model,
            messages=[
                SystemMessage(content=sys_msg),
                HumanMessage(content=usr_msg),
            ],
        )

        # Parse the JSON response
        try:
            result_text = self._extract_json(result)
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

            # Parse dimensions
            dims_data = matrix_data.get("dimensions", {})

            # Parse topics with subtopics structure
            topics = []
            for t in dims_data.get("topics", []):
                subtopics = [
                    DimensionSubtopic(
                        id=st.get("id", str(uuid.uuid4())),
                        name=st.get("name", "Unknown Subtopic"),
                    )
                    for st in t.get("subtopics", [])
                ]
                topics.append(
                    DimensionTopic(
                        name=t.get("name", "Unknown Topic"),
                        subtopics=subtopics,
                        hasContext=t.get("hasContext", False),
                    )
                )

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
                        "OPEN_ENDED",
                        "MATCHING",
                    ],
                ),
            )

            # Parse matrix - convert to "count:points" string format
            # Matrix is now indexed by subtopic (flattened from all topics)
            raw_matrix = matrix_data.get("matrix", [])
            parsed_matrix = []
            for subtopic_row in raw_matrix:  # Each subtopic
                diff_rows = []
                for diff_row in subtopic_row:
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

        except json.JSONDecodeError as e:
            # Truncate response in error message to prevent overwhelming logs
            response_preview = (
                result[:500] + "..." if len(result) > 500 else result
            )
            raise ValueError(
                f"Failed to parse matrix response: {e}\nResponse preview: {response_preview}"
            )
        except Exception as e:
            raise ValueError(f"Failed to create matrix: {e}")

    def _extract_json(self, result: str) -> str:
        """Extract JSON from potential markdown code blocks.

        Uses regex to robustly extract content between code fences.
        """
        result_text = result.strip()

        # Try to extract JSON from code fences using regex
        # Matches ```json or ``` followed by content and closing ```
        code_fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        match = re.search(code_fence_pattern, result_text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: if no code fences found, return as-is
        return result_text

    # Question Generation from Matrix (Priority 1)
    def generate_questions_from_matrix(
        self, request: GenerateQuestionsFromMatrixRequest
    ) -> str:
        """
        Generate all questions in one LLM call (context-based + regular).
        Contexts are pre-selected by backend and included in request.

        Args:
            request: Request containing topics with question requirements

        Returns:
            Response with generated questions and used contexts list
        """
        logger.info(
            f"[EXAM_SERVICE] Generating questions from matrix for grade: {request.grade}, subject: {request.subject}"
        )

        # Separate context vs regular topics
        context_topics = [
            topic for topic in request.topics if topic.context_info
        ]
        regular_topics = [
            topic for topic in request.topics if not topic.context_info
        ]

        logger.info(
            f"[EXAM_SERVICE] Context topics: {len(context_topics)}, Regular topics: {len(regular_topics)}"
        )

        # Build unified prompt
        prompt_vars = self._build_matrix_prompt_vars(
            request, context_topics, regular_topics
        )

        sys_msg = self._system("exam.questions.system", prompt_vars)
        usr_msg = self._system("exam.questions.user", prompt_vars)

        # Build multimodal messages (text + images if present)
        messages = self._build_multimodal_messages(
            sys_msg, usr_msg, context_topics
        )

        # Execute LLM
        logger.info(
            f"[EXAM_SERVICE] Calling LLM with provider: {request.provider}, model: {request.model}"
        )

        result, token_usage = self.llm_executor.batch(
            provider=request.provider or "google",
            model=request.model or "gemini-2.5-flash",
            messages=messages,
        )

        logger.info(
            f"[EXAM_SERVICE] LLM call completed. Tokens: input={token_usage.input_tokens}, output={token_usage.output_tokens}"
        )

        # Extract and return raw JSON response (let backend handle parsing)
        try:
            result_text = self._extract_json(result)
            logger.info(
                "[EXAM_SERVICE] Successfully generated questions, returning raw response to backend"
            )

            # Return raw JSON string for backend to parse
            return result_text

        except json.JSONDecodeError as e:
            logger.error(f"[EXAM_SERVICE] JSON parsing error: {e}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")

    def _build_matrix_prompt_vars(
        self,
        request: GenerateQuestionsFromMatrixRequest,
        context_topics: List,
        regular_topics: List,
    ) -> Dict[str, Any]:
        """Build prompt variables for matrix-based generation."""

        # Build context topics section
        context_topics_section = ""
        if context_topics:
            context_sections = []
            for topic in context_topics:
                ctx_info = topic.context_info

                context_type_display = (
                    "Reading Passage"
                    if ctx_info.context_type == "TEXT"
                    else "Image"
                )

                # For text contexts, include the content in prompt
                context_content = ""
                if ctx_info.context_type == "TEXT":
                    context_content = (
                        f"\n\n**Context Content**:\n{ctx_info.context_content}"
                    )

                # Build requirements list from questionsPerDifficulty
                requirements = []
                for (
                    difficulty,
                    question_types,
                ) in topic.questions_per_difficulty.items():
                    for question_type, req in question_types.items():
                        requirements.append(
                            f"  - {difficulty} / {question_type}: "
                            f"{req.count} questions × {req.points} points"
                        )
                requirements_text = "\n".join(requirements)

                context_sections.append(
                    f"""
**Topic {topic.topic_index + 1}: {topic.topic_name}**
- Context Type: {context_type_display}
- Context Title: {ctx_info.context_title or 'N/A'}{context_content}

**Requirements:**
{requirements_text}
"""
                )

            context_topics_section = "\n".join(context_sections)

        # Build regular topics section
        regular_topics_section = ""
        if regular_topics:
            regular_sections = []
            for topic in regular_topics:
                # Build requirements list from questionsPerDifficulty
                requirements = []
                for (
                    difficulty,
                    question_types,
                ) in topic.questions_per_difficulty.items():
                    for question_type, req in question_types.items():
                        requirements.append(
                            f"  - {difficulty} / {question_type}: "
                            f"{req.count} questions × {req.points} points"
                        )
                requirements_text = "\n".join(requirements)

                regular_sections.append(
                    f"""
**Topic {topic.topic_index + 1}: {topic.topic_name}**
**Requirements:**
{requirements_text}
"""
                )

            regular_topics_section = "\n".join(regular_sections)

        # Calculate totals
        total_topics = len(request.topics)
        context_count = len(context_topics)
        regular_count = len(regular_topics)

        # Calculate total questions from nested structure
        total_questions = 0
        for topic in request.topics:
            for difficulty_reqs in topic.questions_per_difficulty.values():
                for req in difficulty_reqs.values():
                    total_questions += req.count

        return {
            "grade": request.grade,
            "subject": request.subject,  # Use code (T/TV/TA), not full name
            "context_topics_section": context_topics_section or "None",
            "regular_topics_section": regular_topics_section or "None",
            "total_topics": total_topics,
            "context_count": context_count,
            "regular_count": regular_count,
            "total_questions": total_questions,
        }

    def _build_multimodal_messages(
        self, sys_msg: str, usr_msg: str, context_items: List
    ) -> List[BaseMessage]:
        """Build messages with text and images for multimodal generation."""
        messages = [SystemMessage(content=sys_msg)]

        # Check if any context items have images
        image_items = [
            item
            for item in context_items
            if item.context_info.context_type == "IMAGE"
        ]

        if not image_items:
            # Text-only message
            messages.append(HumanMessage(content=usr_msg))
        else:
            # Multimodal message with images
            content_parts = [{"type": "text", "text": usr_msg}]

            for item in image_items:
                ctx_info = item.context_info
                # Clean base64 string if needed
                image_data = ctx_info.context_content
                if "," in image_data:
                    image_data = image_data.split(",")[1]

                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_data}"
                        },
                    }
                )

            messages.append(HumanMessage(content=content_parts))

        return messages

    def _parse_questions(
        self,
        questions_data: List[Dict],
        topic_to_context: Dict[int, str] = None,
    ) -> List[Question]:
        """
        Parse and validate question data (used by other endpoints).

        NOTE: The matrix endpoint now returns raw JSON to backend for parsing.
        This method is kept for other question generation endpoints.

        Args:
            questions_data: Raw question data from LLM
            topic_to_context: Optional mapping of topic_index to context_id
        """
        questions = []
        for i, q in enumerate(questions_data):
            try:
                # Set contextId if this question belongs to a context-based topic
                if topic_to_context:
                    topic_id = q.get("topicId")
                    if topic_id is not None and topic_id in topic_to_context:
                        q["contextId"] = topic_to_context[topic_id]

                question = Question(**q)
                questions.append(question)
            except Exception as e:
                logger.error(
                    f"[EXAM_SERVICE] Failed to parse question {i}: {e}"
                )
                logger.error(f"[EXAM_SERVICE] Question data: {q}")
                raise ValueError(f"Invalid question format at index {i}: {e}")
        return questions

    # # TODO: Do it later
    #     async def generate_questions_from_matrix_stream(
    #         self, request: GenerateQuestionsRequest
    #     ) -> AsyncGenerator[Dict[str, Any], None]:
    #         """
    #         Generate questions from matrix with streaming progress updates.

    #         Args:
    #             request: Request containing the matrix

    #         Yields:
    #             Progress updates and generated questions
    #         """
    #         sys_msg = self._system("exam.questions.system", None)
    #         usr_msg = self._system("exam.questions.user", request.to_dict())

    #         total_questions = sum(item.count for item in request.matrix)

    #         # Send initial progress
    #         yield {
    #             "status": "GENERATING",
    #             "progress": {
    #                 "current": 0,
    #                 "total": total_questions,
    #                 "message": "Starting question generation...",
    #             },
    #         }

    #         # Stream the LLM response
    #         accumulated_response = ""
    #         result_stream = self.llm_executor.stream(
    #             provider=request.provider,
    #             model=request.model,
    #             messages=[
    #                 SystemMessage(content=sys_msg),
    #                 HumanMessage(content=usr_msg),
    #             ],
    #         )

    #         for chunk in result_stream:
    #             accumulated_response += chunk

    #             # Try to parse partial JSON to show progress
    #             # This is a simplified approach - in production you might want more sophisticated parsing
    #             try:
    #                 # Count how many complete question objects we've received
    #                 question_count = accumulated_response.count('"question_type"')
    #                 if question_count > 0:
    #                     yield {
    #                         "status": "GENERATING",
    #                         "progress": {
    #                             "current": min(question_count, total_questions),
    #                             "total": total_questions,
    #                             "message": f"Generated {question_count} of {total_questions} questions...",
    #                         },
    #                     }
    #             except Exception as e:
    #                 logger.debug(
    #                     f"Could not parse partial streaming response: {e}"
    #                 )
    #                 # Continue streaming - partial parse failures are expected

    #         # Parse final response
    #         try:
    #             result_text = accumulated_response.strip()
    #             if result_text.startswith("```"):
    #                 lines = result_text.split("\n")
    #                 result_text = "\n".join(
    #                     line
    #                     for line in lines
    #                     if not line.strip().startswith("```")
    #                 )

    #             questions_data = json.loads(result_text)

    #             # Transform the response
    #             all_questions = []
    #             for item_data in questions_data:
    #                 context = (
    #                     item_data.get("context")
    #                     if item_data.get("context")
    #                     else None
    #                 )

    #                 for q in item_data.get("questions", []):
    #                     question_obj = QuestionWithContext(
    #                         context=context,
    #                         question_number=q.get("question_number"),
    #                         topic=q.get("topic"),
    #                         grade_level=q.get("grade_level"),
    #                         difficulty=q.get("difficulty"),
    #                         question=q,
    #                         default_points=q.get("default_points", 1),
    #                     )
    #                     all_questions.append(question_obj)

    #             # Send completion with questions
    #             yield {
    #                 "status": "COMPLETED",
    #                 "progress": {
    #                     "current": total_questions,
    #                     "total": total_questions,
    #                     "message": "Question generation completed!",
    #                 },
    #                 "questions": [q.model_dump() for q in all_questions],
    #             }

    #         except Exception as e:
    #             yield {
    #                 "status": "ERROR",
    #                 "error": f"Failed to process questions: {str(e)}",
    #             }

    def generate_questions_from_topic(
        self, request: GenerateQuestionsFromTopicRequest
    ) -> List[Question]:
        """
        Generate questions based on topic and requirements.

        Args:
            request: Request containing topic, grade, subject, and requirements

        Returns:
            List of generated Question objects
        """
        logger.info(
            f"[EXAM_SERVICE] Generating questions for topic: {request.topic}, grade: {request.grade}"
        )

        # Calculate total questions
        total_questions = sum(request.questions_per_difficulty.values())

        if total_questions == 0:
            raise ValueError("Total questions must be greater than 0")

        # Format difficulty distribution
        difficulty_distribution = "\n".join(
            [
                f"  - {difficulty}: {count} questions"
                for difficulty, count in request.questions_per_difficulty.items()
                if count > 0
            ]
        )

        # Map subject codes to names
        subject_map = {
            "T": "Toán (Mathematics)",
            "TV": "Tiếng Việt (Vietnamese)",
            "TA": "Tiếng Anh (English)",
        }
        subject_name = subject_map.get(request.subject)
        if not subject_name:
            raise ValueError(f"Unknown subject code: {request.subject}")

        # Format question types
        question_types_str = ", ".join(request.question_types)

        # Format additional requirements
        additional_req = ""
        if request.prompt:
            additional_req = f"\n**Additional Requirements**: {request.prompt}"

        # Build prompt variables
        prompt_vars = {
            "topic": request.topic,
            "grade": request.grade,
            "subject": subject_name,
            "total_questions": total_questions,
            "difficulty_distribution": difficulty_distribution,
            "question_types": question_types_str,
            "prompt": additional_req,
        }

        # Render prompts
        sys_msg = self._system("question.system", prompt_vars)
        usr_msg = self._system("question.user", prompt_vars)

        # Execute LLM call
        logger.info(
            f"[EXAM_SERVICE] Calling LLM with provider: {request.provider}, model: {request.model}"
        )

        result, token_usage = self.llm_executor.batch(
            provider=request.provider or "google",
            model=request.model or "gemini-2.5-flash",
            messages=[
                SystemMessage(content=sys_msg),
                HumanMessage(content=usr_msg),
            ],
        )

        logger.info(
            f"[EXAM_SERVICE] LLM call completed. Tokens: input={token_usage.input_tokens}, output={token_usage.output_tokens}"
        )

        # Parse result
        try:
            result_text = self._extract_json(result)
            questions_data = json.loads(result_text)

            # Validate is list
            if not isinstance(questions_data, list):
                raise ValueError(
                    f"Expected list of questions, got {type(questions_data)}"
                )

            # Validate count
            if len(questions_data) != total_questions:
                logger.warning(
                    f"[EXAM_SERVICE] Expected {total_questions} questions, got {len(questions_data)}"
                )

            # Convert to Question objects with validation
            questions = []
            for i, q in enumerate(questions_data):
                try:
                    question = Question(**q)
                    questions.append(question)
                except Exception as e:
                    logger.error(
                        f"[EXAM_SERVICE] Failed to parse question {i}: {e}"
                    )
                    logger.error(f"[EXAM_SERVICE] Question data: {q}")
                    raise ValueError(
                        f"Invalid question format at index {i}: {e}"
                    )

            logger.info(
                f"[EXAM_SERVICE] Successfully generated {len(questions)} questions"
            )
            return questions

        except json.JSONDecodeError as e:
            logger.error(f"[EXAM_SERVICE] JSON parsing error: {e}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")

    def generate_questions_from_context(
        self, request: GenerateQuestionsFromContextRequest
    ) -> List[Question]:
        """
        Generate questions based on context (image/text) and requirements.

        Args:
            request: Request containing context, topic, grade, subject, and requirements

        Returns:
            List of generated Question objects
        """
        logger.info(
            f"[EXAM_SERVICE] Generating questions from context for grade: {request.grade}"
        )

        # Derive distributions from structured QuestionRequirement objects
        total_questions = 0
        difficulty_lines = []
        question_types_set = set()

        for difficulty, type_map in request.questions_per_difficulty.items():
            diff_count = 0
            for q_type, req in type_map.items():
                count = req.count
                if count > 0:
                    diff_count += count
                    question_types_set.add(q_type)
            if diff_count > 0:
                difficulty_lines.append(
                    f"  - {difficulty}: {diff_count} questions"
                )
                total_questions += diff_count

        if total_questions == 0:
            raise ValueError("Total questions must be greater than 0")

        # Format difficulty distribution
        difficulty_distribution = "\n".join(difficulty_lines)

        # Map subject codes to names
        subject_map = {
            "T": "Toán (Mathematics)",
            "TV": "Tiếng Việt (Vietnamese)",
            "TA": "Tiếng Anh (English)",
        }
        subject_name = subject_map.get(request.subject)
        if not subject_name:
            raise ValueError(f"Unknown subject code: {request.subject}")

        # Derive question types from the map keys
        question_types_str = ", ".join(sorted(question_types_set))

        # Format user guidelines as objectives string
        objectives_str = (
            f"- {request.prompt}"
            if request.prompt
            else "- Generate questions relevant to the context"
        )

        # Format additional requirements (empty since prompt is already used as objectives)
        additional_req = ""

        # Build prompt variables
        prompt_vars = {
            "context_type": request.context_type,
            "objectives": objectives_str,
            "grade": request.grade,
            "subject": subject_name,
            "total_questions": total_questions,
            "difficulty_distribution": difficulty_distribution,
            "question_types": question_types_str,
            "prompt": additional_req,
        }

        # Render prompt text
        sys_msg_content = self._system("question.context.system", prompt_vars)
        usr_msg_content = self._system("question.context.user", prompt_vars)

        messages = [SystemMessage(content=sys_msg_content)]

        if request.context_type == "IMAGE":
            # For image, we need to construct a multipart message
            # Clean base64 string if needed
            image_data = request.context
            if "," in image_data:
                image_data = image_data.split(",")[1]

            messages.append(
                HumanMessage(
                    content=[
                        {"type": "text", "text": usr_msg_content},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            },
                        },
                    ]
                )
            )
        else:
            # For text, append context to user message
            full_usr_msg = (
                f"{usr_msg_content}\n\n**Context**:\n{request.context}"
            )
            messages.append(HumanMessage(content=full_usr_msg))

        # Execute LLM call
        logger.info(
            f"[EXAM_SERVICE] Calling LLM with provider: {request.provider}, model: {request.model}"
        )

        result, token_usage = self.llm_executor.batch(
            provider=request.provider or "google",
            model=request.model or "gemini-2.5-flash",
            messages=messages,
        )

        logger.info(
            f"[EXAM_SERVICE] LLM call completed. Tokens: input={token_usage.input_tokens}, output={token_usage.output_tokens}"
        )

        # Parse result
        try:
            result_text = self._extract_json(result)
            questions_data = json.loads(result_text)

            # Validate is list
            if not isinstance(questions_data, list):
                raise ValueError(
                    f"Expected list of questions, got {type(questions_data)}"
                )

            # Validate count
            if len(questions_data) != total_questions:
                logger.warning(
                    f"[EXAM_SERVICE] Expected {total_questions} questions, got {len(questions_data)}"
                )

            # Convert to Question objects with validation
            questions = []
            for i, q in enumerate(questions_data):
                try:
                    question = Question(**q)
                    questions.append(question)
                except Exception as e:
                    logger.error(
                        f"[EXAM_SERVICE] Failed to parse question {i}: {e}"
                    )
                    logger.error(f"[EXAM_SERVICE] Question data: {q}")
                    raise ValueError(
                        f"Invalid question format at index {i}: {e}"
                    )

            logger.info(
                f"[EXAM_SERVICE] Successfully generated {len(questions)} questions"
            )
            return questions

        except json.JSONDecodeError as e:
            logger.error(f"[EXAM_SERVICE] JSON parsing error: {e}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")
