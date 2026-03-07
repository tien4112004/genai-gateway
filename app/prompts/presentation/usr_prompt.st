Transform this approved outline into a kid-friendly slide deck using the given templates.

Inputs:
- Language: ${language}
- Target age: children ages 6 to 11
- Slide count: ${slide_count}
- Learning objective: Students can understand the key ideas of the presentation and can explain it easily.${chapter_context}

Approved outline (Markdown):
---
${outline}
---

Requirements:
- Follow the STRICT output contract.
- Produce exactly ${slide_count} slides.
- Choose the most suitable template for each slide.
- Use <em> or <strong> once per slide for emphasis.
- Include a one-sentence conclusion per slide as specified (inline in an allowed field).
- Return only the JSON object, with no text before or after.
