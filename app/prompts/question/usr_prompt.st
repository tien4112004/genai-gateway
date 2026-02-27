Generate exam questions with the following specifications:

**Topic**: ${topic}
**Grade Level**: ${grade}
**Subject**: ${subject}

**Generate ${total_questions} questions distributed as follows**:
${difficulty_distribution}

**Question Types to use**: ${question_types}
${prompt}

**Important Instructions**:
- Create EXACTLY ${total_questions} questions
- Follow the difficulty distribution specified above
- Use only the question types listed (${question_types})
- Ensure each question follows the schema in the system prompt
- For grade level ${grade}, use age-appropriate language and concepts
- For subject ${subject}, use appropriate language (Vietnamese or English)
- Return ONLY a valid JSON array. Do not include any thinking, reasoning, or extra text before or after the JSON.

Generate the questions now.
