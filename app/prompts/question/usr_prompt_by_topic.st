Generate exam questions for the following topic:

**Topic**: ${topic_name}
**Grade Level**: ${grade}
**Subject**: ${subject}
**Total Questions**: ${total_questions}
${additional_prompt}

${groups_section}

**Instructions**:
- Generate EXACTLY ${total_questions} questions total across all groups
- For each question, set the `group` field to match the group index (0-based)
- Follow the exact question counts per difficulty and type specified above
- Questions in a CONTEXT group must be directly based on the provided reading passage
- Questions in a NORMAL group are based on curriculum knowledge of the topic
- Return a JSON array of question objects following the schema in the system prompt
