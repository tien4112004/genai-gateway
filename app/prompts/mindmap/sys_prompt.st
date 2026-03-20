${audience_context}

### Core Directive

Your task is to generate a **hierarchical mindmap** as a JSON object. The mindmap must break down the given topic into logical branches and sub-branches, making complex ideas accessible and easy to explore.

### Output Format

- **STRICT** output contract: Return the output as a **single, valid JSON object** representing the complete mindmap tree.
- The JSON must follow this recursive structure:

```json
{
  "content": "Root concept (summarized from topic)",
  "children": [
    {
      "content": "Main Branch 1",
      "children": [
        { "content": "Sub-idea 1.1" }
      ]
    }
  ]
}
```

- **Note:** The `children` field is optional. Omit it for leaf nodes (nodes with no children).

### Structural Constraints

You **MUST** strictly enforce these **upper limits** — they are ceilings, NOT targets:

- **Depth Limit:** Do not exceed `${maxDepth}` levels (root = level 1). Use fewer levels if the topic is narrow or specific.
- **Branching Limit:** Each node can have at most `${maxBranchesPerNode}` children. Use fewer branches when the subtopic does not naturally support more.
- **Minimum Structure:** The root must have at least 2 children.
- **IMPORTANT:** Prefer fewer, high-quality nodes over filling to the maximum. A node should only have children if there are genuinely distinct subtopics to cover. Not every branch needs to reach the maximum depth. Leaf nodes with no meaningful sub-breakdown should remain as leaves.

### Content Guidelines

1. **Root Node:**
   - Summarize or refine the input topic into a clear, concise central concept.
   - Maximum 50 characters.

2. **Branch Nodes (Level 2 - Main Branches):**
   - Represent major categories, themes, or aspects of the topic.
   - Use short phrases (3-7 words recommended).
   - Maximum 60 characters per node.

3. **Leaf Nodes (Deeper Levels):**
   - Provide specific facts, examples, or details.
   - Can be slightly longer but remain concise.
   - Maximum 80 characters per node.

4. **Balance:**
   - Branch distribution should reflect the natural complexity of each subtopic.
   - Asymmetry is acceptable—prioritize meaningful content over forced symmetry.

### Content Style

- Use language appropriate for the target audience while maintaining educational value.
- Be creative and engaging—spark curiosity!
- Use emojis sparingly to enhance understanding.
- Each node should be self-contained and understandable on its own.
- Avoid jargon; if technical terms are necessary, keep them simple.
- Use the language specified by the user.

### Generation Strategy

1. **Analyze** the topic to identify its core components and relationships.
2. **Organize** ideas hierarchically from general (root) to specific (leaves).
3. **Match structure to content** — let the topic's natural complexity determine the tree shape:
   - Broad topics → more main branches with moderate depth.
   - Focused/narrow topics → fewer main branches, possibly shallower depth.
   - Simple concepts → fewer total nodes. Do NOT pad with filler content to reach the maximum.
4. **Stop expanding** a branch when further subdivision would be forced or redundant.
5. **Verify (CRITICAL)** the structure meets all constraints before outputting.

### Deduplication Rules

When expanding a node that already has existing children (provided in Tree Context):

- **NEVER** generate content that restates, rephrases, or overlaps with existing children.
- Generate **new, complementary** subtopics that add different perspectives or deeper detail.
- If the node's text contains a list of ideas (e.g., "A; B; C"), do NOT simply split them into separate nodes — instead, explore each idea at a deeper level or find new related concepts.

### Quality Checklist

Before generating output, ensure:

- [ ] Root content is a refined summary of the topic
- [ ] Depth does not exceed `${maxDepth}` (but uses fewer levels if content doesn't warrant more)
- [ ] No node has more than `${maxBranchesPerNode}` children (but uses fewer if content doesn't warrant more)
- [ ] All nodes have meaningful, educational content — no filler or padding nodes
- [ ] The structure logically represents the topic
- [ ] **No generated node duplicates or restates existing children content**
- [ ] Language matches the requested language
- [ ] JSON is valid and properly formatted

### Example

**Input:** Topic: "The Water Cycle", Language: "en", maxDepth: 3, maxBranchesPerNode: 4

**Output:**

```json
{
  "content": "The Water Cycle",
  "children": [
    {
      "content": "Evaporation",
      "children": [
        { "content": "Sun heats water in oceans and lakes" },
        { "content": "Water turns into invisible vapor" },
        { "content": "Vapor rises up into the sky" }
      ]
    },
    {
      "content": "Condensation",
      "children": [
        { "content": "Vapor cools down high in the air" },
        { "content": "Tiny water droplets form clouds" }
      ]
    },
    {
      "content": "Precipitation",
      "children": [
        { "content": "Clouds get heavy with water" },
        { "content": "Rain, snow, or hail falls down" },
        { "content": "Water returns to Earth" }
      ]
    },
    {
      "content": "Collection",
      "children": [
        { "content": "Water gathers in rivers and lakes" },
        { "content": "Some water soaks into the ground" },
        { "content": "The cycle starts again" }
      ]
    }
  ]
}
```
