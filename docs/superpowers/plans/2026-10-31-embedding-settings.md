# Embedding settings implementation plan

Goal: Add usable Embedding configuration to Settings while keeping chat attachment answers independent of indexing.
Architecture: Instance-wide settings match the existing shared Chroma/MySQL embedding contract. Store a single configuration row, return only a key hint, and resolve the saved configuration when creating each RAG store. With no saved row, retain the documented environment configuration. Do not silently borrow the user's chat credentials. A connection probe embeds only synthetic text.

- [x] Backend schema, persistence and authenticated GET/PUT/probe endpoints; test retained/cleared key and validation.
- [x] Runtime: new RAG stores resolve saved settings without worker restart; test actual client arguments and model selection with a fake transport.
- [x] Settings card: load/save/key clearing and connection feedback; component tests and frontend build.
- [x] Verify authorized real chat retry, restart services with existing local Redis destination, verify new route.
