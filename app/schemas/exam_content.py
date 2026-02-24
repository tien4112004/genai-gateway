"""Schemas for exam and question generation."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class Topic(BaseModel):
    """Represents a topic in the exam matrix."""

    id: str = Field(..., description="Unique identifier for the topic")
    name: str = Field(..., description="Name of the topic")
    description: Optional[str] = Field(
        None, description="Optional description of the topic"
    )


class MatrixContent(BaseModel):
    """Represents a content cell in the exam matrix."""

    difficulty: Literal["KNOWLEDGE", "COMPREHENSION", "APPLICATION"] = Field(
        ..., description="Difficulty level"
    )
    numberOfQuestions: int = Field(
        ...,
        ge=1,
        description="Number of questions for this difficulty",
        alias="number_of_questions",
    )
    selectedQuestions: Optional[List[str]] = Field(
        default=None,
        description="Question IDs currently selected for this cell (Runtime tracking)",
        alias="selected_questions",
    )

    class Config:
        populate_by_name = True


# ============================================================================
# New 3D Matrix Format - [topic][difficulty][question_type]
# ============================================================================


class MatrixCell(BaseModel):
    """A cell in the 3D matrix representing question requirements.

    When serialized, this becomes "count:points" string format.
    """

    count: int = Field(0, ge=0, description="Number of questions required")
    points: float = Field(0, ge=0, description="Total points for this cell")

    def to_string(self) -> str:
        """Convert to 'count:points' string format."""
        return f"{self.count}:{self.points}"

    @classmethod
    def from_string(cls, s: str) -> "MatrixCell":
        """Create from 'count:points' string format."""
        parts = s.split(":")
        return cls(count=int(parts[0]), points=float(parts[1]))


class DimensionSubtopic(BaseModel):
    """Subtopic dimension item in the matrix."""

    id: str = Field(..., description="Unique identifier for the subtopic")
    name: str = Field(..., description="Display name of the subtopic")


class DimensionTopic(BaseModel):
    """Topic as organizational container for subtopics."""

    name: str = Field(..., description="Display name of the topic")
    subtopics: List[DimensionSubtopic] = Field(
        ..., description="List of subtopics under this topic"
    )
    hasContext: Optional[bool] = Field(
        default=False,
        description="If true, system randomly selects a context for context-based questions",
    )


class MatrixDimensions(BaseModel):
    """Dimensions of the 3D exam matrix.

    Matrix is indexed by: matrix[subtopic_index][difficulty_index][question_type_index]
    Topics serve as organizational containers; subtopics are the actual first dimension.
    """

    topics: List[DimensionTopic] = Field(
        ...,
        description="List of topics with their subtopics (organizational hierarchy)",
    )
    difficulties: List[str] = Field(
        default=["KNOWLEDGE", "COMPREHENSION", "APPLICATION"],
        description="List of difficulty levels (second dimension)",
    )
    questionTypes: List[str] = Field(
        default=["MULTIPLE_CHOICE", "FILL_IN_BLANK", "MATCHING", "OPEN_ENDED"],
        description="List of question types (third dimension)",
        alias="question_types",
    )

    class Config:
        populate_by_name = True


class MatrixMetadata(BaseModel):
    """Metadata for the exam matrix."""

    id: str = Field(..., description="Unique identifier for this matrix")
    name: str = Field(..., description="Matrix name")
    grade: Optional[str] = Field(
        None, description="Grade level (e.g., '1', '2', '3', '4', '5')"
    )
    subject: Optional[str] = Field(
        None, description="Subject code (T, TV, TA)"
    )
    createdAt: Optional[str] = Field(
        None, description="ISO timestamp of creation", alias="created_at"
    )

    class Config:
        populate_by_name = True


class ExamMatrix(BaseModel):
    """
    3D exam matrix structure.

    Matrix is indexed as: matrix[topic_index][difficulty_index][question_type_index]
    Each cell is "count:points" string format for that combination.
    """

    metadata: MatrixMetadata = Field(..., description="Matrix metadata")
    dimensions: MatrixDimensions = Field(..., description="Matrix dimensions")
    matrix: List[List[List[str]]] = Field(
        ...,
        description="3D matrix: [topic][difficulty][question_type] -> 'count:points'",
    )

    class Config:
        populate_by_name = True

    def get_total_questions(self) -> int:
        """Calculate total questions across all cells."""
        total = 0
        for subtopic_row in self.matrix:  # Each subtopic
            for diff_row in subtopic_row:
                for cell_str in diff_row:
                    count, _ = cell_str.split(":")
                    total += int(count)
        return total

    def get_total_points(self) -> float:
        """Calculate total points across all cells."""
        total = 0.0
        for subtopic_row in self.matrix:  # Each subtopic
            for diff_row in subtopic_row:
                for cell_str in diff_row:
                    _, points = cell_str.split(":")
                    total += float(points)
        return total

    def get_cell(
        self, subtopic_idx: int, difficulty_idx: int, qtype_idx: int
    ) -> str:
        """Get a specific cell from the matrix as 'count:points' string."""
        return self.matrix[subtopic_idx][difficulty_idx][qtype_idx]


class TopicInput(BaseModel):
    """Topic with subtopics for matrix generation request."""

    name: str = Field(..., description="Topic name (organizational container)")
    subtopics: List[str] = Field(
        ...,
        min_length=1,
        description="List of subtopic names under this topic",
    )


class GenerateMatrixRequest(BaseModel):
    """Request to generate a 3D exam matrix using AI."""

    name: str = Field(..., description="Name for the exam matrix")
    chapters: List[str] = Field(
        ...,
        min_length=1,
        description="List of curriculum chapters (fetched by backend based on grade/subject)",
    )
    grade: str = Field(..., description="Grade level", alias="grade_level")
    subject: str = Field(..., description="Subject code (T, TV, TA)")
    totalQuestions: int = Field(
        ...,
        ge=1,
        description="Target total number of questions",
        alias="total_questions",
    )
    totalPoints: int = Field(
        ..., ge=1, description="Target total points", alias="total_points"
    )
    difficulties: Optional[List[str]] = Field(
        default=["KNOWLEDGE", "COMPREHENSION", "APPLICATION"],
        description="Difficulty levels to include",
    )
    questionTypes: Optional[List[str]] = Field(
        default=["MULTIPLE_CHOICE", "FILL_IN_BLANK", "OPEN_ENDED", "MATCHING"],
        description="Question types to include",
        alias="question_types",
    )
    prompt: Optional[str] = Field(
        None,
        description="Additional requirements or context for the exam",
        alias="prompt",
    )
    language: str = Field(
        default="vi",
        description="Language for AI responses (vi for Vietnamese, en for English)",
    )
    provider: str = Field(default="gemini", description="LLM provider")
    model: str = Field(
        default="gemini-2.5-flash", description="LLM model to use"
    )

    class Config:
        populate_by_name = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for prompt rendering."""
        return {
            "name": self.name,
            "chapters": "\n".join([f"- {ch}" for ch in self.chapters]),
            "grade": self.grade,
            "subject": self.subject,
            "total_questions": self.totalQuestions,
            "total_points": self.totalPoints,
            "difficulties": (
                ", ".join(self.difficulties)
                if self.difficulties
                else "KNOWLEDGE, COMPREHENSION, APPLICATION"
            ),
            "question_types": (
                ", ".join(self.questionTypes)
                if self.questionTypes
                else "MULTIPLE_CHOICE, FILL_IN_BLANK, MATCHING, OPEN_ENDED"
            ),
            "prompt": self.prompt or "",
            "language": self.language,
        }


class MatrixItem(BaseModel):
    """Represents a single item in the exam matrix (Legacy format)."""

    topic: str = Field(..., description="Topic or subtopic for questions")
    question_type: Literal[
        "MULTIPLE_CHOICE",
        "FILL_IN_BLANK",
        "OPEN_ENDED",
        "MATCHING",
    ] = Field(..., description="Type of question")
    count: int = Field(
        ..., ge=1, description="Number of questions to generate"
    )
    points_each: int = Field(..., ge=1, description="Points for each question")
    difficulty: Literal["KNOWLEDGE", "COMPREHENSION", "APPLICATION"] = Field(
        ..., description="Difficulty level"
    )
    requires_context: bool = Field(
        default=False,
        description="Whether question requires a context/passage",
    )
    context_type: Optional[
        Literal["reading_passage", "image", "audio", "video"]
    ] = Field(None, description="Type of context if required")


class QuestionContext(BaseModel):
    """Context for questions (reading passage, image, etc.)."""

    context_type: Literal["reading_passage", "image", "audio", "video"]
    title: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class MultipleChoiceOption(BaseModel):
    """Option for multiple choice question."""

    text: str
    imageUrl: Optional[str] = Field(None, alias="image_url")
    isCorrect: bool = Field(..., alias="is_correct")

    class Config:
        populate_by_name = True


class MultipleChoiceData(BaseModel):
    """Data for multiple choice question."""

    type: Literal["MULTIPLE_CHOICE"] = Field(
        default="MULTIPLE_CHOICE", description="Question type discriminator"
    )
    options: List[MultipleChoiceOption] = Field(
        ..., min_length=4, max_length=4
    )
    shuffleOptions: bool = Field(True, alias="shuffle_options")

    class Config:
        populate_by_name = True


class FillInBlankData(BaseModel):
    """Data for fill in the blank question. Backend parses this structure into segments.

    Example:
        {
            "type": "FILL_IN_BLANK",
            "data": "The capital is {{Hà Nội|Hanoi}}."
            "case_sensitive": false
        }
    """

    type: Literal["FILL_IN_BLANK"] = Field(
        default="FILL_IN_BLANK", description="Question type discriminator"
    )
    data: str = Field(
        ...,
        description="Raw text with {{answer|alternative}} placeholders. Backend will parse this.",
    )
    caseSensitive: bool = Field(False, alias="case_sensitive")

    class Config:
        populate_by_name = True


class MatchingPair(BaseModel):
    """Pair for matching question."""

    left: str
    leftImageUrl: Optional[str] = Field(None, alias="left_image_url")
    right: str
    rightImageUrl: Optional[str] = Field(None, alias="right_image_url")

    class Config:
        populate_by_name = True


class MatchingData(BaseModel):
    """Data for matching question."""

    type: Literal["MATCHING"] = Field(
        default="MATCHING", description="Question type discriminator"
    )
    pairs: List[MatchingPair] = Field(..., min_length=4)
    shufflePairs: bool = Field(True, alias="shuffle_pairs")

    class Config:
        populate_by_name = True


class OpenEndedData(BaseModel):
    """Data for open ended question."""

    type: Literal["OPEN_ENDED"] = Field(
        default="OPEN_ENDED", description="Question type discriminator"
    )
    expectedAnswer: str = Field(..., alias="expected_answer")
    maxLength: Optional[int] = Field(500, alias="max_length")

    class Config:
        populate_by_name = True


class Question(BaseModel):
    """Question entity matching backend Question class."""

    type: Literal["MULTIPLE_CHOICE", "FILL_IN_BLANK", "MATCHING", "OPEN_ENDED"]
    difficulty: Literal["KNOWLEDGE", "COMPREHENSION", "APPLICATION"]
    title: str = Field(..., description="Question text/prompt")
    titleImageUrl: Optional[str] = Field(None, alias="title_image_url")
    explanation: Optional[str] = None
    grade: Literal["K", "1", "2", "3", "4", "5"]
    chapter: str = Field(..., description="Topic/chapter name")
    subject: Literal["T", "TV", "TA"] = Field(
        ..., description="Subject code: T, TV, TA"
    )
    contextId: Optional[str] = Field(
        None,
        alias="context_id",
        description="ID of the context this question belongs to (for context-based questions)",
    )
    data: Union[
        MultipleChoiceData, FillInBlankData, MatchingData, OpenEndedData
    ]
    point: float = Field(default=1.0, ge=0)

    class Config:
        populate_by_name = True


class GenerateQuestionsRequest(BaseModel):
    """Request to generate questions from a matrix."""

    matrix: List[MatrixItem] = Field(
        ..., description="Exam matrix to generate from"
    )
    provider: str = Field(default="gemini", description="LLM provider")
    model: str = Field(
        default="gemini-2.5-flash", description="LLM model to use"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for prompt rendering."""
        return {
            "matrix_items": [item.model_dump() for item in self.matrix],
            "total_questions": sum(item.count for item in self.matrix),
        }


class GenerationProgress(BaseModel):
    """Progress update for question generation."""

    current: int = Field(..., description="Current progress")
    total: int = Field(..., description="Total items")
    message: str = Field(..., description="Progress message")


class QuestionGenerationStatus(BaseModel):
    """Status response for question generation."""

    status: Literal["GENERATING", "COMPLETED", "ERROR"]
    progress: Optional[GenerationProgress] = None
    questions: Optional[List[Question]] = None
    error: Optional[str] = None


class QuestionRequirement(BaseModel):
    """Requirement for a specific difficulty and question type."""

    count: int = Field(..., ge=1, description="Number of questions")
    points: float = Field(..., ge=0, description="Points per question")


class GenerateQuestionsFromTopicRequest(BaseModel):
    """Request to generate questions from a topic."""

    topic: str = Field(..., description="Topic or chapter name")
    grade: Optional[Literal["K", "1", "2", "3", "4", "5"]] = None
    subject: Optional[str] = Field(None, description="Subject code: T, TV, TA")

    questions_per_difficulty: Dict[
        Literal["KNOWLEDGE", "COMPREHENSION", "APPLICATION"],
        int,
    ] = Field(..., description="Number of questions for each difficulty level")

    question_types: List[
        Literal["MULTIPLE_CHOICE", "FILL_IN_BLANK", "MATCHING", "OPEN_ENDED"]
    ] = Field(..., description="Types of questions to generate")

    prompt: Optional[str] = Field(
        None,
        description="Additional requirements or context for question generation",
    )

    # LLM configuration
    provider: Optional[str] = Field(
        default="google", description="LLM provider"
    )
    model: Optional[str] = Field(
        default="gemini-2.5-flash", description="LLM model"
    )


class GenerateQuestionsFromContextRequest(BaseModel):
    """Request to generate questions from a context (text/image)."""

    context: str = Field(
        ..., description="The context content (text passage or base64 image)"
    )
    context_type: Literal["TEXT", "IMAGE"] = Field(
        ..., description="Type of context provided"
    )

    grade: Literal["K", "1", "2", "3", "4", "5"]
    subject: str = Field(..., description="Subject code: T, TV, TA")

    questions_per_difficulty: Dict[
        Literal["KNOWLEDGE", "COMPREHENSION", "APPLICATION"],
        Dict[
            Literal[
                "MULTIPLE_CHOICE", "FILL_IN_BLANK", "MATCHING", "OPEN_ENDED"
            ],
            QuestionRequirement,
        ],
    ] = Field(
        ...,
        alias="questionsPerDifficulty",
        description="Map of difficulty -> question_type -> requirement (count and points)",
    )

    prompt: Optional[str] = Field(
        None,
        description="User guidelines for question generation",
    )

    # LLM configuration
    provider: Optional[str] = Field(
        default="google", description="LLM provider"
    )
    model: Optional[str] = Field(
        default="gemini-2.5-flash", description="LLM model"
    )

    class Config:
        populate_by_name = True


# ============================================================================
# Context-Based Question Generation from Matrix
# ============================================================================


class ContextInfo(BaseModel):
    """Information about a randomly selected context."""

    topic_index: int = Field(
        ..., description="Index of the topic in the matrix"
    )
    topic_name: str = Field(..., description="Name of the topic")
    context_id: str = Field(..., description="ID of the selected context")
    context_type: Literal["TEXT", "IMAGE"] = Field(
        ..., description="Type of context"
    )
    context_content: str = Field(
        ...,
        description="Context content (text or base64-encoded image)",
    )
    context_title: Optional[str] = Field(
        None, description="Title of the context"
    )


class TopicRequirement(BaseModel):
    """Requirements for a single topic with optional context."""

    topic_index: int = Field(
        ..., description="Index for grouping questions by topic"
    )
    topic_name: str = Field(..., description="Name of the topic")
    context_info: Optional[ContextInfo] = Field(
        None,
        description="Context information if this topic has context-based questions",
    )
    questions_per_difficulty: Dict[
        Literal["KNOWLEDGE", "COMPREHENSION", "APPLICATION"],
        Dict[
            Literal[
                "MULTIPLE_CHOICE", "FILL_IN_BLANK", "MATCHING", "OPEN_ENDED"
            ],
            QuestionRequirement,
        ],
    ] = Field(
        ...,
        alias="questionsPerDifficulty",
        description="Map of difficulty -> question_type -> requirements",
    )

    class Config:
        populate_by_name = True


class GenerateQuestionsFromMatrixRequest(BaseModel):
    """Request to generate questions from matrix (supports context-based topics)."""

    grade: Literal["K", "1", "2", "3", "4", "5"] = Field(
        ..., description="Grade level"
    )
    subject: str = Field(..., description="Subject code (T, TV, TA)")
    topics: List[TopicRequirement] = Field(
        ...,
        description="List of topics with their question requirements",
    )
    provider: Optional[str] = Field(
        default="google", description="LLM provider"
    )
    model: Optional[str] = Field(
        default="gemini-2.5-flash", description="LLM model to use"
    )


class UsedContext(BaseModel):
    """Information about a context that was used for question generation."""

    context_id: str = Field(
        ..., alias="contextId", description="ID of the context used"
    )
    context_title: str = Field(
        ..., alias="contextTitle", description="Title of the context"
    )
    context_type: str = Field(
        ..., alias="contextType", description="Type of context (TEXT, IMAGE)"
    )
    context_content: str = Field(
        ..., alias="contextContent", description="The context content"
    )

    class Config:
        populate_by_name = True


class TopicWithQuestions(BaseModel):
    """A topic with its generated questions and optional context."""

    topic_index: int = Field(
        ..., alias="topicIndex", description="Index of the topic"
    )
    topic_name: str = Field(
        ..., alias="topicName", description="Name of the topic"
    )
    context: Optional[UsedContext] = Field(
        None, description="Context info if this is a context-based topic"
    )
    questions: List[Question] = Field(
        ..., description="Questions generated for this topic"
    )

    class Config:
        populate_by_name = True


class GenerateQuestionsFromMatrixResponse(BaseModel):
    """Response with generated questions from matrix, grouped by topic."""

    topics: List[TopicWithQuestions] = Field(
        ..., description="Topics with their questions and optional context"
    )
    total_questions: int = Field(
        ...,
        alias="totalQuestions",
        description="Total number of questions generated",
    )

    class Config:
        populate_by_name = True
