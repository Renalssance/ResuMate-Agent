# Chat document picker and content classification design

## Goal

Replace the chat composer's exposed resume and job selects with one compact attachment control. The control lets the user choose an existing resume, choose an existing job description, or upload one local document. A local document is classified from its extracted content, never from its filename. The original is uploaded once and reused for classification, parsing, persistence, and indexing.

This change keeps the existing chat agent contract: a message may carry at most one selected resume ID and one selected job-description ID.

## User experience

The composer shows a paperclip icon without a text label. Hover and keyboard focus add a quiet circular tint, color change, and small upward movement. The button retains the accessible name `添加材料`.

Activating the button opens a glass panel centered above the icon with an 8px gap. Its initial view contains three buttons:

- `选择已有简历`
- `选择已有岗位`
- `选择本地文件`

The first two buttons replace the panel contents with a compact scrollable list of the corresponding parsed documents. Each row is a button, not a native select. Choosing a row returns to the initial panel view, closes the panel, and adds or replaces the corresponding material chip in the composer.

The local-file button opens the native file chooser for the existing supported extensions. After selection, the panel shows classification progress while the file is uploaded and its text is extracted. The filename is displayed for identity only and is not an input to classification.

When classification is decisive, the same run continues through parsing and indexing. When classification remains ambiguous, the panel asks `这份文件属于哪一类？` and presents `简历` and `岗位` buttons. Choosing one resumes the same run with the same stored original.

Selected materials appear inside the composer as compact chips before the text area. A resume uses a document/person icon; a job description uses a briefcase icon. Each chip shows the filename, truncates long names, exposes the full name as a title, and has a remove button. One resume chip and one job chip may be present together.

The panel closes after choosing an existing document, after an imported document is ready, on `Escape`, and when pointer focus moves outside the panel and its anchor. Clicking inside the panel does not close it.

## Motion and layout

The panel is absolutely anchored to the paperclip wrapper with `left: 50%`, `bottom: calc(100% + 8px)`, and a horizontal translation of `-50%`. It therefore remains centered on the icon at every composer width.

Open and close use one coordinated transition: opacity, 6px vertical travel, and scale from 0.96 to 1, with the transform origin at bottom center. The duration is approximately 180ms with an ease-out curve on entry and 140ms on exit. The paperclip hover uses a shorter 140ms transition. Reduced-motion mode keeps opacity only and removes travel and scale.

The panel remains within the viewport on narrow screens by using a width bounded by the viewport. Existing empty-state suggestions and the floating composer layout remain unchanged.

## Single-upload import flow

### Durable run

Add a durable run kind named `document_import`. The upload endpoint accepts one file without a declared business type, stores the original through the existing upload storage path, and creates this run with the stored-file metadata needed for retry. The run owns that staged original until it creates a typed document record.

The run executes inside the existing killable document subprocess and uses the existing document timeout. It has these stages:

1. Read the stored original and extract normalized page text with the existing PDF, DOCX, text, and OCR implementation.
2. Classify the extracted content.
3. If the result is decisive, create the `Resume` or `JobDescription` row.
4. Parse the structured profile with the existing resume or JD prompt.
5. Build chunks, generate embeddings, persist the structured result, and return the existing document response shape.

The typed row is created only after the type is known. The import never creates a tentative resume and later moves it to the job table.

Retries use the same stored original and content hash. Once a typed record has been created, the run records its document ID so replay cannot create a duplicate. On a failure after record creation, retry continues against that record using the existing document parse behavior.

### Classification

Classification uses document content only. A local classifier first inspects structural signals in the extracted text:

- resume-oriented sections such as education, work history, projects, skills, publications, and contact details;
- job-oriented sections such as responsibilities, requirements, qualifications, benefits, workplace, and application instructions.

The local classifier returns a decisive result only when the document structure clearly belongs to one category and does not contain competing structure from the other. It does not assign a type from a single keyword.

When local evidence is insufficient or conflicting, `AgentHarness` calls a new `document.classify` prompt with the extracted content and validates a small structured result:

- `document_type`: `resume`, `jd`, or `ambiguous`
- `confidence`: `high`, `medium`, or `low`
- `reason`: a short user-facing explanation based on content structure

Only a high-confidence `resume` or `jd` result continues automatically. Every other result asks the user. The LLM receives extracted content only; the filename is omitted from the prompt and classification variables.

### Ambiguous result

For an ambiguous result, the run creates one existing `input` action and enters `waiting_input`. Its public payload contains the filename for display, the short reason, and two allowed values: `resume` and `jd`. It does not contain the extracted document text or internal storage path.

The frontend answers the action through the existing run-action endpoint. The run resumes, reads the answered type, reuses the staged original, and continues at typed record creation. The user does not select the file again.

The staged path remains private run input and is excluded from public run snapshots. Cancelling an unfinished import removes the staged original. A successfully created document takes ownership of the original path, so import cleanup must not delete it. A run waiting for type confirmation retains the original because it is still resumable.

## API behavior

Add a chat-focused automatic import endpoint under `/api/documents/import`. It accepts exactly one supported file plus an optional request ID and returns the existing accepted-run envelope. It does not accept `document_type`.

The resulting run returns the existing `DocumentParseResponse` after success. On ambiguity, the normal run snapshot exposes the pending action. This lets the frontend use the established run stream and answer semantics instead of inventing a second polling protocol.

Existing typed `/api/documents` uploads remain supported for the document-management page and other callers. Their behavior does not change.

## Frontend state

`ChatView` owns the small amount of transient picker state:

- whether the panel is open;
- panel view: root, resume list, job list, classifying, or confirm type;
- the active import run and pending action;
- selected resume and job IDs already used by chat message submission.

The selected chip labels are computed from the document store. A newly imported document is inserted through the existing store adapter and selected immediately. Removing a chip clears only the chat context; it does not delete the database document.

Outside-click handling uses one document-level `pointerdown` listener registered while the panel is open and removed when it closes or the view unmounts. Escape handling follows the same lifecycle. The trigger and panel share one wrapper ref so both count as inside interactions.

## Errors and recovery

Unsupported, empty, encrypted, or unreadable files show the existing inline chat error and return the panel to its root view. Model or embedding failures keep the durable task available for retry. An ambiguous classification is a normal input state, not a failure.

If the user navigates away during classification, the durable run continues. Returning to the same chat can recover the active import run from its task ID while the original remains staged. The composer does not show a material chip until a typed document has been created successfully.

## Testing

Backend tests cover:

- clear resume content avoids the LLM and creates one resume;
- clear JD content avoids the LLM and creates one job description;
- conflicting content calls the LLM;
- medium, low, and ambiguous LLM results create an input action;
- answering the action resumes with the same stored original and creates one typed record;
- retry after typed-record creation does not create duplicates;
- filename text never influences classification;
- staged originals are cleaned up on cancellation and retained by successful documents.

Frontend component tests cover:

- the composer exposes only the paperclip icon before selection;
- the panel has the three requested root actions and no select elements;
- existing resume and job rows select the correct message context;
- selected materials render typed filename chips and can be removed;
- outside pointerdown and Escape close the panel;
- inside pointerdown does not close it;
- ambiguous imports render two confirmation buttons and answer the pending action;
- clear imports create and select a chip without another file selection.

The chat Playwright test verifies panel alignment, open and close motion end states, desktop and mobile containment, keyboard accessibility, and that sending a message still carries the selected resume and job IDs.
