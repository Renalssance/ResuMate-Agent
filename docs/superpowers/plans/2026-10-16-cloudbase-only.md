# CloudBase deployment implementation plan — current scope

Goal: deploy the complete current application on the existing domestic CloudBase environment `dev-d0g73fv8v22380036` while preserving business code.

Latest user decisions supersede the earlier PostgreSQL, Lighthouse and CloudBase AI proposals:

- Infrastructure uses CloudBase Run, the existing CloudBase MySQL and classic CloudBase private storage only.
- MySQL is `172.17.0.11:3306`, database equals environment ID, username `resume`. Credentials remain private.
- AI uses the project's own model, API key and base URL, including per-user settings. Embedding model is `qwen3.7-text-embedding-flash`.
- User explicitly authorized a permanent server API key for private CloudBase storage.
- Existing JWT login remains. One instance and one worker preserve the existing in-memory task progress hub.

Completed:

- MySQL driver, schema and document-scoped JSON embedding retrieval. All17tables initialized with administrator-only CloudBase permissions.
- Native classic CloudBase storage upload/download/delete, cloud:// persistence and temporary local cache cleanup. Storage ACL ADMINONLY.
- Docker/source package, private runtime config, VPC wiring, actual cloud build and deployment.
- Actual HTTPS health, SPA routes, MySQL registration/login, application create/list, custom AI settings and successful document parse/embedding in the backend.

Remaining:

- Adapt long AI calls to CloudBase's60second request limit. Actual parse succeeded after82seconds but the gateway returned504. Use asynchronous submission plus the existing progress channel; retain business operations and frontend result shapes.
- Redeploy and validate document upload/reparse, matching, questions, evidence retrieval, chat and cleanup of synthetic verification data.
- Deliver the working application URL and the most relevant next step.

Completed 2026-10-17: revision004 owns100%traffic; asynchronous tasks passed actual86.4s/80.5s/116s gateway tests; final immediate candidate summary agrees with persisted MySQL result. Questions/reports survived revision replacement. Evidence, chat, followups and extension APIs passed. Synthetic test documents, cloud originals, vectors, applications and user/dependent records were removed. Remaining items above are complete; production custom-domain binding is the suggested next step.
