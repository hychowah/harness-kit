# Docs

How to write text a person reads. The grade can see some of these files. It cannot see a comment.

## Writing standard

The reader is a teammate who can use the product but has not read this code.

The first sentence says what it does and why it exists, in plain words.

Use a technical name only when no shorter word works. On first use, add a short gloss in parentheses.

Short sentences. Active voice. Steps in order. Say what the reader should see when a step works.

No marketing language. Do not use these words: leverage, utilize, robust, seamless.

This standard applies to a README, a guide, a comment meant for a person, the map `project/ARCHITECTURE.md`, and this repo's `docs/index.html`.

A comment follows this standard only. It has no draft file. The grade does not look at comments.

The parent writes the draft, then starts one subagent to rewrite it once. Do not ship the first draft. Copy this framing into that subagent's prompt:

> You are a teammate who can use this product. You have not read this code.
> Do not open the code. Keep every fact. Return only the rewritten text.
> The first sentence says what it does and why it exists.
> Use a technical name only when no shorter word works. On first use, add a short gloss in parentheses.
> Short sentences. Active voice. Steps in order. Say what the reader should see when a step works.
> No marketing language. Do not use these words: leverage, utilize, robust, seamless.

A pack worker is not the record of this rewrite.

Bad: "The orchestration layer hydrates the context window via RAG retrieval."

Good: "Before it answers, the app searches your notes and pastes the relevant bits into the prompt. That search step is retrieval."

## Ship record

The files the grade can see are `project/ARCHITECTURE.md`, any file named `README.md`, and a markdown file directly in `docs/` (`docs/<name>.md`). A guide is `docs/<name>.md`.

The map is in play when `architecture_changed` is true or `writes` contains `project/ARCHITECTURE.md`. A reader is owed for the map when it is in play, and for every other path on that list that `writes` contains.

For each owed path, the session holds `sessions/<id>/draft/<path>` (the first draft) and `sessions/<id>/return/<path>` (the rewrite).

The grade runs when the session phase is `closed`. `close-session` and `check` use that same grade. An open session is not graded for this. `abandon` does not take this grade.

For each owed path, the shipped file matches the return and differs from the draft. Newlines may be CRLF on disk. The grade compares them as LF. A missing file, a file that is not UTF-8, a shipped file that is not the return, or a shipped file that is still the draft is `docs.reader`. The detail names the path.

The map's first sentence says what the project does and why it exists. Its sections are `## Project harness` (how this project uses the kit), `## Code structure` (how the code is laid out), `## Architecture` (how the parts fit together), and `## Sessions that changed the map`.

When the map is in play, the grade also requires those headings, the session id somewhere in the file, and a section body that is not empty and not still the template text. That failure is `docs.map`. The detail names the path.
