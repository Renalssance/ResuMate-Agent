You are writing one batch of formal interview questions from a fixed blueprint.

Use only the supplied candidate report and the supplied blueprint items. Do not choose new criteria or evidence IDs.

Rules:
- Return only JSON matching the injected QuestionBatch schema.
- Generate one formal question per supplied blueprint item, in the same order.
- Copy each blueprint item's question type, difficulty, related criteria, and evidence_chunk_ids.
- Use only `evidence_chunk_ids`; do not create or rewrite evidence objects.
- Make questions answerable and scoreable. Avoid compound questions and answer leakage.
- Keep assessment_points to 2-4 items, scoring_rubric to 3-5 items, and suggested_followups to exactly 1 item.
- Avoid duplicating or paraphrasing existing questions listed below.

Candidate report context:
{{report_json}}

Blueprint items:
{{blueprint_json}}

Existing question texts:
{{existing_questions_json}}
