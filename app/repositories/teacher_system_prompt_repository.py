import logging
from typing import Optional

import psycopg2

logger = logging.getLogger(__name__)


class TeacherSystemPromptRepository:
    """Repository for accessing teacher_system_prompts table via direct psycopg2."""

    def __init__(self, pg_connection_string: str):
        # SQLAlchemy uses "postgresql+psycopg2://" prefix; strip the driver part for psycopg2
        self._dsn = pg_connection_string.replace(
            "postgresql+psycopg2://", "postgresql://"
        )

    def get_prompt(self, teacher_id: Optional[str]) -> Optional[str]:
        """Return the active system prompt for a teacher, or None if not found."""
        if not teacher_id:
            return None

        try:
            conn = psycopg2.connect(self._dsn)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT prompt FROM teacher_system_prompts "
                        "WHERE teacher_id = %s AND is_active = TRUE",
                        (teacher_id,),
                    )
                    row = cur.fetchone()
                    return row[0] if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.warning(
                f"[TeacherSystemPromptRepository] Failed to fetch prompt for teacher={teacher_id}: {e}"
            )
            return None
