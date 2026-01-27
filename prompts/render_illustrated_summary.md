# Illustrated Summary Renderer

Generate a markdown summary of the video content using the retrieved context.

## Requirements
- Include section headers for major topics
- Embed relevant keyframes using markdown image syntax
- Every claim must cite its source using evidence references:
  - Transcript: `[seg:ID t=START-END]`
  - Frame: `[frame:ID t=TIMESTAMP]`
- If you cannot find evidence for a claim, state "Not found in sources"

## User Prompt
{{user_prompt}}

## Retrieved Context
{{context}}
