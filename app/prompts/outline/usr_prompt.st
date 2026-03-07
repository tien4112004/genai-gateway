Create a slide-aligned lesson outline on: **${topic}** for subject ${subject_name} and grade ${grade}.

Parameters
- Language: ${language}
- Target age: children ages 6 to 11
- Slide count: ${slide_count}
- Learning objective: Students grasp the key ideas and can explain the **${topic}** simply.${chapter_context}

Requirements
- Follow the STRICT output contract.
- Provide exactly ${slide_count} sections with `### {Slide Title}` and 3–5 concise bullets each.
- Return Markdown only, with no extra sections beyond the ${slide_count}.
