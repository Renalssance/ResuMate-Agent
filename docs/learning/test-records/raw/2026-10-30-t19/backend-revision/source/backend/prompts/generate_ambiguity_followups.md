You are writing ambiguity follow-up questions after the formal interview questions have been drafted.

Use only the supplied candidate report, blueprint, and formal question texts.

Rules:
- Return only JSON matching the injected AmbiguityFollowupSet schema.
- Generate 3 to 5 `ambiguity_followups`.
- Ambiguity follow-ups should verify contradictions, unclear ownership, metric scope, technical depth, decision tradeoffs, or failure learning.
- Return only `evidence_chunk_ids`; do not create or rewrite evidence objects.
- Do not duplicate formal question objectives.
- Each follow-up must be answerable and must not reveal a preferred answer.

Candidate report context:
{{report_json}}

Blueprint:
{{blueprint_json}}

Formal questions:
{{formal_questions_json}}
