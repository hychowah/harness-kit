# Docs

How to write text a person reads. The grade can see some of these files. It cannot see a comment.

## Writing standard

The reader is a teammate who can use the product but has not read this code.

The first sentence says what it does and why it exists, in plain words.

Use a technical name only when no shorter word works. On first use, add a short gloss in parentheses.

Short sentences. Active voice. Steps in order. Say what the reader should see when a step works.

No marketing language. Do not use these words: leverage, utilize, robust, seamless.

This standard applies to a README, a guide, a comment meant for a person, the project page `docs/index.html`, and this repo's `docs/index.html`.

A comment follows this standard only. It has no draft file. The grade does not look at comments.

The parent writes the draft, then starts one subagent to rewrite it once. Do not ship the first draft. Copy this framing into that subagent's prompt:

> You are a teammate who can use this product. You have not read this code.
> Do not open the code. Keep every fact. Return only the rewritten text.
> The first sentence says what it does and why it exists.
> Use a technical name only when no shorter word works. On first use, add a short gloss in parentheses.
> Short sentences. Active voice. Steps in order. Say what the reader should see when a step works.
> No marketing language. Do not use these words: leverage, utilize, robust, seamless.

When the file is the project page, copy this framing instead:

> You are a teammate who can use this product. You have not read this code.
> Do not open the code. Keep every fact. Return only the rewritten page.
> The file is a static HTML page in the same shape as the kit site.
> Keep the tags and the class names. Keep the link to `../harness-kit/docs/site.css`. Do not add a second stylesheet.
> The lede is the first sentence: what the project does and why it exists.
> Keep the three points, the contents list, and the four sections: Project harness, Code structure, Architecture, and Sessions that changed the map.
> Keep a chart in Architecture. A chart is an element whose class includes `chart`.
> Rewrite the sentences a person reads. Short sentences. Active voice.
> Use a technical name only when no shorter word works. On first use, add a short gloss in parentheses.
> No marketing language. Do not use these words: leverage, utilize, robust, seamless.

A pack worker is not the record of this rewrite.

Bad: "The orchestration layer hydrates the context window via RAG retrieval."

Good: "Before it answers, the app searches your notes and pastes the relevant bits into the prompt. That search step is retrieval."

## The project page

The map is `docs/index.html`. `new-project` copies `templates/docs/index.html`. The page uses the same shape as this repo's site.

- `<!DOCTYPE html>`, a title, and `<link rel="stylesheet" href="../harness-kit/docs/site.css">`
- A skip link (`class="skip"`), a header (`class="top"`), a lede (`class="lede"`), and three points (`class="points"`)
- A contents list (`class="toc"`) and `<main id="content">`
- Four sections, each with a reading paragraph (`class="reading"`): `harness` (Project harness), `structure` (Code structure), `architecture` (Architecture), `sessions` (Sessions that changed the map)
- A chart inside Architecture. A chart is an element whose class includes `chart`.

The lede says what the project does and why it exists. Project harness says how this project uses the kit. Code structure says how the code is laid out. Architecture says how the parts fit together, and its chart shows those parts. Sessions that changed the map names the session that last changed the page.

## Ship record

The files the grade can see are `docs/index.html`, any file named `README.md`, and a markdown file directly in `docs/` (`docs/<name>.md`). A guide is `docs/<name>.md`. The page is not a guide.

The map is in play when `architecture_changed` is true or `writes` contains `docs/index.html`. A reader is owed for the map when it is in play, and for every other path on that list that `writes` contains.

For each owed path, the session holds `sessions/<id>/draft/<path>` (the first draft) and `sessions/<id>/return/<path>` (the rewrite).

The grade runs when the session phase is `closed`. `close-session` and `check` use that same grade. An open session is not graded for this. `abandon` does not take this grade.

A closed session this pin grades owes a human file when `writes` names that exact file. `architecture_changed` also owes the map. The draft differs from the return. Newlines may be CRLF on disk. The grade compares them as LF. A missing draft, a missing return, a file that is not UTF-8, or a return that is still the draft is `docs.reader`. The detail names the path.

The live file must equal exactly one of those returns. Any other count is one `docs.reader`. A return that is not that one is not compared to the live file. While the file is dirty and the one open session owes it, skip the live comparison. `closed_at` is not an order.

When the live file is the map, the grade also requires the page shape above and the owning session id somewhere in the file. The lede, each point, and each section's reading paragraph must be present, not empty, and not still the template sentence. That failure is `docs.map`. The detail names the path. It runs once.
