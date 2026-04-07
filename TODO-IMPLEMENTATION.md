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
- ZIP loading currently assumes a single usable WhatsApp chat `.txt`.
- Participant abbreviations can be edited in the app.
- Output `.docx` path can be selected in the app.
- Scrollable participant area is in place.
- Generation progress is visible in the status line and as an estimated-time progress bar.
- Desktop UI can optionally write performance reports.
- Generation now has pre-run duration estimation and timeout settings.
- Performance output can include JSON, text, SVG dashboard, and prediction-vs-actual comparison.
- WhatsApp chat text decoding is robust across common encodings.
- URL fallback HTML decoding is robust across common encodings.
- Google Drive upload failures no longer hard-stop generation.
- Google Drive service/folder reuse is implemented for video uploads.
- Google Drive readonly metadata is available for shared Google Docs / Drive links when the local OAuth token has access.
- Spotify `poeme` mode is implemented and validated on real files.
- Spotify poem blocks use section breaks, column breaks, and a blank line before lyrics.
- Inline attachment parsing now catches attachments that appear on continuation lines.
- Local audio transcription is integrated into the document pipeline.
- English audio transcription is validated as good enough for current use.
- French audio transcription is acceptable with a stronger local model.
- Dutch should use the same stronger local model strategy as French.

## Known Product Constraints

- When the app is launched from Terminal, Terminal stays attached to the GUI process.
- The shell prompt returns only when the app exits.
- This is expected for now and will be solved later by packaging the app as a standalone macOS application.

## Priority Order For The Next Work

1. Complete remaining rich media URL handling
2. Spotify false positives and remaining poem refinements
3. Layout and document polish
4. Assistant UX remaining steps
5. Full-link investigation for unresolved cases

## Completed In Current Phase

- Batch 1: URLs carrying no useful information.
- Rich media partials:
  - YouTube metadata and unavailable-video fallback.
  - Dubb hosted-video rendering with static image preview.
  - Dropbox shared video preview via static image frame.
  - Google Docs / Drive shared file metadata and preview when accessible.
  - iCloud shared document/file handling.
  - Mixed inline URL cleanup for the handled rich-media services.
- Assistant UX partials:
  - Performance report yes/no option.
  - Pre-run duration estimate.
  - Timeout by predicted-duration multiplier or fixed minutes.
  - Progress bar based on predicted duration.
  - Manual stop and timeout interruption.
  - Prediction-vs-actual report after completion, stop, failure, or timeout.
  - SVG performance dashboard.

## Previous Priority Order Reference

1. URLs carrying no useful information
2. Rich media URL handling
3. Spotify false positives and remaining poem refinements
4. Layout and document polish
5. Multi-step assistant UX
6. Full-link investigation for unresolved cases

## Validated Recently

### Spotify

- The new Spotify poem format is now the reference format.
- The section-break / continuous-section approach is validated.
- Murithul and Dominique were both used as real test corpora.
- A blank paragraph before the lyrics block is part of the approved format.

### Audio Transcription

- Jilan validates the English audio flow.
- Bruno validates that the transcription feature is useful enough to keep.
- Current language strategy:
  - English can use a lighter local model.
  - French should use `medium`.
  - Dutch should also use `medium`.
- Current quality position:
  - English: validated.
  - French: acceptable, but not final-quality without re-reading.

## Batch 1: URLs With No Useful Information

Status: done.

### Goals

- Avoid noisy or low-value previews.
- Replace them with minimal, readable output.

### Targets

- Teams
- Zoom
- Google Meet
- Similar meeting / logistics links
- Microsoft Teams images/previews specifically removed when they add no useful information.

### Tasks

- Classify low-information service links explicitly.
- Avoid screenshots/previews for those links.
- Render a small, useful hyperlink block instead.
- Keep error messages explicit when the target cannot be resolved.

### Acceptance Criteria

- Done: Teams / Zoom / Meet no longer generate useless preview images.
- Done: These links remain clickable.
- Done: Error states are visible in the document when a link is unreachable.
- Done: Meeting links render as one compact clickable line, without `Join conversation` / `Lien de reunion`.

## Batch 2: Rich Media URL Handling

Status: in progress. YouTube, Dubb, Dropbox, Google Docs / Drive, and iCloud are implemented; LinkedIn, X / Twitter, and SWR-like media pages remain.

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
- SWR and similar media-rich article/video pages

### Tasks

- Done: Improve YouTube metadata so the document reflects the real topic of the video.
- Done: Add explicit unavailable-video fallback: `This video isn't available any more`.
- Done: Treat Dubb like a hosted video page.
- Done: Render Dubb as title plus static image preview, not embedded video wording.
- Done: Treat Dropbox / Google Drive shared videos like other remote videos.
- Done: Add Dropbox video static preview extraction.
- Done: Explore clickable preview support for Google Docs shared documents.
- Done: Add Google Drive readonly metadata lookup for accessible Docs / Drive files.
- Done: Add iCloud shared file/document handling.
- Shorten oversized LinkedIn summaries.
- Explore an `X` treatment analogous to Facebook where possible.
- Done for handled rich-media services: Ensure mixed message + inline URL cases do not duplicate or misplace the raw link when a useful preview exists.
- Partially done: Review why some pages are classified with technical labels such as `Type: page` or `Type: video.other` and replace them with more human output.
- Remaining: Review SWR and similar media-rich pages.

### Acceptance Criteria

- Done: YouTube entries are more descriptive than generic `Type: page`.
- Done: Dropbox and Google Drive video links render as shared video/file entries with previews where available.
- LinkedIn summaries are capped to a useful length.
- Partially done: No preview should be inserted if it adds no real information.

## Batch 3: Spotify False Positives And Remaining Poem Refinements

### Goals

- Keep the new Spotify poem format as the reference format.
- Reduce remaining false positives in lyrics detection without regressing working cases.
- Polish the poem layout so columns balance more naturally.

### Tasks

- Re-check classical/instrumental false positives such as Beethoven 5th.
- Preserve correct `Paroles trouvables: non` behavior for instrumental albums and piano-only works.
- Keep the new section-break + column-break poem format as the standard.
- Re-test wrapped/share Spotify links under the same rules.
- Keep the pre-lyrics blank line in place.

### Acceptance Criteria

- Lyrics blocks begin after a blank line and distribute more evenly across columns.
- Beethoven-like cases do not incorrectly return `oui`.
- Non-lyrical Spotify items continue to render as concise metadata blocks.
- The poem format remains stable on both Murithul and Dominique test files.

## Batch 4: Layout And Document Polish

### Goals

- Make the generated `.docx` more consistent and readable.

### Tasks

- Ensure images never exceed page margins.
- Revisit media sizing rules per source type.
- Improve preview cropping/orientation where useful.
- Prevent unnecessary or redundant preview blocks.
- Improve summary/introduction formatting.
- Include participant abbreviations explicitly in the introduction.
- Ensure participant abbreviations in the generated intro match the values chosen in the UI.
- Investigate and fix cases where images exceed page margins on real documents.

### Acceptance Criteria

- Images fit within margins.
- Intro clearly lists participants with abbreviations.
- Redundant previews are reduced.
- Media blocks look intentional, not accidental.

## Batch 5: Assistant UX

Status: in progress. The UI is still not a full multi-step assistant and remains French-only, but estimation/progress/timeout/performance-report UX is now implemented.

### Goals

- Move from the current single-screen utility UI toward a guided assistant.
- Allow the user to choose the application language at startup instead of keeping the UI French-only.
- Allow the user to choose the conversation when a zip contains multiple usable chat `.txt` files.

### Tasks

- Split the app into steps:
  - import
  - conversation selection when needed
  - participants
  - options
  - generation
  - result
- Done partially: Add a pre-run estimation section after ZIP load.
- Done partially: Add a generation screen area with progress bar based on predicted duration.
- Done partially: Add performance report yes/no option.
- Done partially: Add timeout configuration as predicted-duration multiplier or fixed minutes.
- Done partially: Write prediction-vs-actual analysis after completion, stop, failure, or timeout.
- Done partially: Generate SVG performance dashboard for runs with performance reporting enabled.
- Add a startup language selector for the desktop app.
- Expose the important settings directly in the desktop UI:
  - Spotify `simple` vs `poeme`
  - video policy
  - summary on/off
  - audio transcription on/off
- Show warnings and progress more clearly.
- Preserve terminal usability expectations until the app is packaged as a standalone macOS application.
- Introduce a translation layer for UI labels/messages so the startup language choice applies consistently.
- Detect and ignore archive noise such as `__MACOSX` entries and `._` AppleDouble files during import.

### Acceptance Criteria

- The user can configure the main generation options without going through the CLI.
- If a zip contains multiple valid chat `.txt` files, the app lets the user choose which one(s) to process.
- The generation screen communicates what is happening.
- The result screen shows warnings in a readable way.
- The startup menu lets the user choose the UI language.
- The desktop UI is no longer hard-coded in French.

## Batch 6: Full-Link Investigation For Unresolved Cases

### Goals

- Review unresolved or weakly resolved links one by one instead of relying on generic rules.

### Targets

- `https://ppsimons.com/2018/05/20/het-beethoven-fries-van-klimt-en-de-negende-symfonie-van-beethoven`
- `https://share.mindmanager.com/#publish/NCoHDx_lAAP89WYXyPQ2J4R-cvTUV8BtBqWyh0H0`
- `https://gocar.be/nl/autonieuws/mobiliteit/elektrische-mobiliteit-de-eu-denkwijze-is-onrealistisch`
- `https://www.josvanimmerseel.com/huisconcerten`
- `https://app.emergent.sh/landing/?via=dde`
- erroring links from `scaleup.vlaanderen`, `jobtoolz.be`, and `googleadservices.com`

### Tasks

- Inspect each target manually and determine the exact failure mode:
  - blocked by bot protection
  - missing Open Graph metadata
  - redirect chain issue
  - unusual HTML structure
  - unsupported document/share type
- Encode a source-specific handling rule where useful.
- Ensure error links produce an explicit human-readable message in the document.

### Acceptance Criteria

- Each listed link has a documented reason for current behavior.
- Where feasible, handling is improved.
- Where not feasible, the document states the failure clearly.

## Confirmed Feedback From Dominique Test And Follow-Up

### Confirmed or likely real issues

- Terminal remains attached to the app process when launched from Terminal; expected for now.
- Participant abbreviations must remain visible in the intro.
- YouTube descriptions were too weak; first pass fixed via YouTube oEmbed.
- Teams preview is not useful; fixed by compact meeting-link rendering.
- Some unresolved links need manual inspection one by one.
- Erroring links should say so explicitly in the document.
- Lyrics detection is too optimistic for some classical content.
- Dropbox / Google Drive remote video links should be treated more like videos; first pass implemented.
- Dubb-hosted video links should be treated more like videos.
- Google Docs shared documents deserve a clickable preview if feasible.
- X / Twitter should be evaluated for a Facebook-like treatment.
- Some previews are too large or exceed margins.
- LinkedIn summary can be too long.
- Some media blocks still feel redundant or overly literal.
- Some inline links still appear in the document when the preview/metadata block should probably replace them.

## Confirmed Feedback From Jilan And Bruno Tests

- English audio transcription is good enough to keep.
- French audio transcription is acceptable only with a stronger local model.
- Dutch should use the same stronger local model strategy as French.
- Inline photo attachments on continuation lines were missing and are now fixed.
- `Généré le:` replaces `Genere le:` in the introduction.
- Bruno full-run with Spotify, audio, and URL enrichment is acceptable as a baseline.
- Klara Festival missing image preview needs investigation.
- YouTube handling remains on the active URL improvement backlog.

## New Import Requirement

- `archive.zip` in the project directory is a reference case for multi-chat imports.
- It contains many `.txt` entries, including unwanted `__MACOSX` duplicates.
- The import layer should:
  - filter out macOS archive noise
  - list the real chat `.txt` candidates
  - let the user choose one or several conversations to process

## Working Rule For Future Changes

- Favor graceful degradation over hard failures.
- Do not block the whole document because one URL, one preview, one transcript, or one upload fails.
- Prefer concise, useful metadata over noisy screenshots.
- Preserve clickability wherever possible.
- Optimize for document readability first, technical completeness second.

## Technical Debt To Track Explicitly

- The desktop app is currently French-only.
- We need a real UI internationalization layer so the startup menu can offer language selection cleanly.
