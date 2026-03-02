Generate children nodes to expand the following mindmap topic into deeper subtopics.

Inputs:

- **Topic:** ${topic}
- **Language:** ${language}
- **Maximum Depth (upper limit, not a target):** ${maxDepth}
- **Maximum Branches Per Node (upper limit, not a target):** ${maxBranchesPerNode}
- **Tree Context:** ${tree_context}

Requirements:

- Create a hierarchical mindmap that breaks down the topic into logical branches.
- The root node should be a refined summary of the topic.
- Ensure the mindmap is engaging and educational for children.
- Do not exceed the depth and branching limits, but use fewer nodes when the content is narrow or specific. Quality over quantity.
- **CRITICAL: If "Existing Children" are listed in the Tree Context, you MUST NOT generate content that duplicates or restates them. Generate only new, complementary subtopics that add deeper or different perspectives.**
- If the topic text contains multiple ideas separated by semicolons or commas, treat it as a single concept to expand upon with NEW deeper details, not as a list to split apart.
- Output a single valid JSON object.
