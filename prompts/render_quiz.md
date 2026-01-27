# Quiz Renderer

Generate quiz questions based on the video content using the retrieved context.

## Requirements
- Create 5-10 multiple choice questions
- Each question must test understanding of the video content
- Include the correct answer and explanation
- Every question must cite its source using evidence references:
  - Transcript: `[seg:ID t=START-END]`
  - Frame: `[frame:ID t=TIMESTAMP]`
- If you cannot find evidence for a question, do not include it

## Output Format
```
### Question N
**Q:** [Question text]

A) [Option A]
B) [Option B]
C) [Option C]
D) [Option D]

**Answer:** [Letter]
**Explanation:** [Brief explanation with citation]
```

## User Prompt
{{user_prompt}}

## Retrieved Context
{{context}}
