You are planning an interview question set. Return a compact QuestionBlueprint only.

Use only the supplied candidate report. Do not write full questions, rubrics, answer directions, or follow-ups.

Blueprint rules:
- Create exactly 10 formal question blueprint items.
- Distribution must be: 3 resume_experience, 2 jd_core_capability, 2 scenario_design, 2 gap_validation, 1 behavior_review.
- Use stable unique IDs such as `q01` through `q10`.
- Cover at least four distinct criteria when at least four criteria exist.
- Do not repeat the same assessment objective.
- Use `evidence_chunk_ids` only from the candidate report evaluations.
- Non-gap items must include 1-2 direct evidence IDs from the candidate report evaluations.
- Do not use the same first `evidence_chunk_ids` value as the primary basis for more than two formal questions.
- Gap items may have empty evidence IDs when the report has no supporting evidence.
- Ambiguity sources should describe only resume ambiguities or evidence conflicts present in the report.

Candidate report context:
{{report_json}}
