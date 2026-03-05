Generate exactly ${slide_count} slide(s) for an existing presentation.

Inputs:
- Language: ${language}
- Slide count: ${slide_count}
- User instruction: ${prompt}

Context from the existing presentation:
---
${context}
---

Requirements:
- Follow the STRICT output contract: return a JSON array of slide objects.
- Produce exactly ${slide_count} slides.
- Choose the most suitable template for each slide based on the content.
- Use <em> or <strong> once per slide for emphasis.
- Do NOT generate a title slide unless the user explicitly requests one.
- Return ONLY the JSON array, with no text before or after.
