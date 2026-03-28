# TODO Implementation

## Purpose

This file is the operational implementation backlog for the current phase of the project.
It complements `TODO.md`.

- `TODO.md` stays as the high-level product and architecture backlog.
- `TODO-IMPLEMENTATION.md` is the concrete working list for the next iterations.

This file should be kept pragmatic and test-oriented.

## Current Stable Baseline

- Desktop app launches on macOS from the project virtualenv.
- ZIP loading works.
- Participant abbreviations can be edited in the app.
- Output `.docx` path can be selected in the app.
- Scrollable participant area is in place.
- Generation progress is visible in the status line.
- WhatsApp chat text decoding is robust across common encodings.
- URL fallback HTML decoding is robust across common encodings.
- Google Drive upload failures no longer hard-stop generation.
- Google Drive service/folder reuse is implemented for video uploads.

## Known Product Constraints

- When the app is launched from Terminal, Terminal stays attached to the GUI process.
- The shell prompt returns only when the app exits.
- This is expected for now and will be solved later by packaging the app as a standalone macOS application.

## Priority Order For The Next Work

1. Spotify poem mode
2. Audio transcription
3. URLs carrying no useful information
4. Rich media URL handling
5. Layout and document polish
6. Multi-step assistant UX

## Batch 1: Spotify Mode Poeme

### Goals

- Make `spotify_mode = poeme` real, not only declarative.
- Distinguish better between lyrical music and instrumental/classical content.
- Avoid false positives such as Beethoven works incorrectly marked as lyrics-searchable.

### Tasks

- Implement a proper `poeme` rendering branch for Spotify links.
- Decide how lyrics are fetched or inferred.
- Add robust heuristics for `Paroles trouvables`.
- Treat classical, piano-only, instrumental, and likely non-lyric works conservatively.
- Ensure wrapped/share Spotify links inherit the same treatment.

### Acceptance Criteria

- In `simple` mode, Spotify shows concise metadata only.
- In `poeme` mode, lyrics are inserted only when confidence is high enough.
- Beethoven / instrumental examples do not incorrectly claim lyrics are available.
- Album-only links do not behave like song lyrics candidates.

## Batch 2: Audio Transcription

### Goals

- Add transcription support for WhatsApp audio attachments.
- Keep privacy and deployment flexibility in mind.

### Tasks

- Decide the first transcription backend.
- Start with a robust local-first implementation if feasible.
- Detect audio attachments and include a transcript block in the document.
- Preserve the attachment itself while adding transcript text.
- Expose audio transcription as an explicit option in the UI/profile system.

### Acceptance Criteria

- Audio attachments are detected reliably.
- A transcript can be inserted in the document when enabled.
- A failed transcription does not block document generation.
- The output clearly distinguishes original audio from transcript text.

## Batch 3: URLs With No Useful Information

### Goals

- Avoid noisy or low-value previews.
- Replace them with minimal, readable output.

### Targets

- Teams
- Zoom
- Google Meet
- Similar meeting / logistics links

### Tasks

- Classify low-information service links explicitly.
- Avoid screenshots/previews for those links.
- Render a small, useful hyperlink block instead.
- Keep error messages explicit when the target cannot be resolved.

### Acceptance Criteria

- Teams / Zoom / Meet no longer generate useless preview images.
- These links remain clickable.
- Error states are visible in the document when a link is unreachable.

## Batch 4: Rich Media URL Handling

### Goals

- Improve media-like URL treatment beyond Facebook and Spotify.

### Targets

- YouTube
- Dubb
- Dropbox direct video links
- Google Drive shared video links
- Google Docs shared documents
- X / Twitter
- LinkedIn posts

### Tasks

- Improve YouTube metadata so the document reflects the real topic of the video.
- Treat Dubb like a hosted video page.
- Treat Dropbox / Google Drive shared videos like other remote videos.
- Explore clickable preview support for Google Docs shared documents.
- Shorten oversized LinkedIn summaries.
- Explore an `X` treatment analogous to Facebook where possible.

### Acceptance Criteria

- YouTube entries are more descriptive than generic `Type: page`.
- Dropbox and Google Drive video links render as video-like entries.
- LinkedIn summaries are capped to a useful length.
- No preview should be inserted if it adds no real information.

## Batch 5: Layout And Document Polish

### Goals

- Make the generated `.docx` more consistent and readable.

### Tasks

- Ensure images never exceed page margins.
- Revisit media sizing rules per source type.
- Improve preview cropping/orientation where useful.
- Prevent unnecessary or redundant preview blocks.
- Improve summary/introduction formatting.
- Include participant abbreviations explicitly in the introduction.

### Acceptance Criteria

- Images fit within margins.
- Intro clearly lists participants with abbreviations.
- Redundant previews are reduced.
- Media blocks look intentional, not accidental.

## Batch 6: Assistant UX

### Goals

- Move from the current single-screen utility UI toward a guided assistant.

### Tasks

- Split the app into steps:
  - import
  - participants
  - options
  - generation
  - result
- Expose the important settings directly in the desktop UI:
  - Spotify `simple` vs `poeme`
  - video policy
  - summary on/off
  - audio transcription on/off
- Show warnings and progress more clearly.

### Acceptance Criteria

- The user can configure the main generation options without going through the CLI.
- The generation screen communicates what is happening.
- The result screen shows warnings in a readable way.

## Confirmed Feedback From Dominique Test

### Confirmed or likely real issues

- Participant abbreviation mismatch between UI and generated document must be verified and fixed.
- Participant abbreviations must appear in the intro.
- YouTube descriptions are too weak.
- Teams preview is not useful.
- Some unresolved links need manual inspection one by one.
- Erroring links should say so explicitly in the document.
- Lyrics detection is too optimistic for some classical content.
- Dropbox / Google Drive remote video links should be treated more like videos.
- Some previews are too large or exceed margins.
- LinkedIn summary can be too long.

### Observed but not yet fully designed

- X / Twitter should be evaluated for a Facebook-like treatment.
- Shared Google Docs deserve a clickable preview if feasible.
- Some media blocks still feel redundant or overly literal.

## Working Rule For Future Changes

- Favor graceful degradation over hard failures.
- Do not block the whole document because one URL, one preview, one transcript, or one upload fails.
- Prefer concise, useful metadata over noisy screenshots.
- Preserve clickability wherever possible.
- Optimize for document readability first, technical completeness second.

