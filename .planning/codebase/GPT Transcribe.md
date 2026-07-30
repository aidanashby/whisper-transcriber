# Product Roadmap: Dual Transcription Engine

## Vision

Transform Whisper Transcriber from a local transcription application into a transcription platform capable of using either:

* Local AI (existing faster-whisper implementation)
* Cloud AI (OpenAI GPT Transcribe)

without changing the existing user workflow.

The application should continue to feel like "Whisper Transcriber", with the transcription engine becoming an implementation detail chosen by the user.

---

# Product goals

## Preserve the existing experience

Existing users should experience almost no behavioural change.

The current workflow should remain:

* add WAV files
* press Start
* watch progress
* copy or save transcript

Users who never enable GPT should experience identical behaviour to today's application.

---

## Introduce engine choice

Users should be able to choose one of two transcription engines.

### Local

Uses the existing faster-whisper large-v3 implementation.

Characteristics:

* free after download
* offline
* GPU accelerated
* unlimited usage
* existing behaviour preserved

---

### OpenAI

Uses the OpenAI Transcription API with GPT-4o Transcribe (or its successor model if appropriate). The API supports both standard transcription and a diarization-capable model for identifying speakers. It offers improved recognition accuracy, language handling and punctuation compared with the original Whisper models. ([OpenAI Developers][1])

Characteristics:

* internet required
* API key required
* usage billed through OpenAI
* improved accuracy
* no local model download required

---

# User experience principles

## One application

Do not create separate editions.

The user chooses an engine inside the same application.

---

## Minimal configuration

Avoid turning the application into a "settings" tool.

Most users should never need to understand:

* models
* token pricing
* inference
* API endpoints

Instead they simply choose:

> Local

or

> OpenAI

---

## Feature parity

Where practical, both engines should expose the same experience.

Examples:

* identical queue
* identical progress UI
* identical transcript viewer
* identical export
* identical pause/stop behaviour where technically feasible

Engine differences should only appear where unavoidable.

---

# Account management

## OpenAI API key

Support entering an OpenAI API key.

Goals:

* entered once
* securely stored
* easy to replace
* easy to remove

The application should clearly indicate whether a valid key is configured.

---

## Engine availability

If OpenAI is selected but no API key exists:

Guide the user through configuration rather than allowing transcription to begin.

---

# Transcription behaviour

Regardless of engine:

Input:

* WAV files
* existing drag-and-drop
* existing queue

Output:

* plain text
* identical formatting conventions where possible

The application should not expose different transcript formats purely because different engines are used.

---

# Quality improvements

The OpenAI engine should be positioned as the premium-quality option.

Benefits may include:

* better punctuation
* better noisy audio handling
* improved proper nouns
* stronger multilingual recognition
* optional speaker attribution (future)

These advantages should not complicate the interface.

---

# Performance expectations

## Local

Optimised for:

* speed
* privacy
* unlimited throughput

---

## OpenAI

Optimised for:

* accuracy
* convenience
* difficult recordings

Upload time should be presented as part of transcription rather than as a separate technical stage.

---

# Error handling

OpenAI introduces new failure modes.

The application should gracefully communicate:

* internet unavailable
* authentication failed
* quota exceeded
* rate limiting
* service unavailable

without exposing raw API errors.

The local engine should remain usable regardless of OpenAI availability.

---

# Privacy

Users should always understand where their audio is processed.

Example messaging:

Local

> Audio never leaves this computer.

OpenAI

> Audio is securely uploaded to OpenAI for transcription.

No ambiguity.

---

# Future extensibility

Design the concept around **transcription providers**, not "Whisper versus GPT".

Possible future providers could include:

* OpenAI
* local Whisper
* Azure OpenAI
* Deepgram
* AssemblyAI

The UI should not require redesign if another provider is added later.

---

# Future capabilities (not required for first release)

These become possible once a cloud provider exists.

## Speaker identification

Leverage the diarization model to identify speakers in conversations. ([OpenAI Developers][2])

---

## Automatic summaries

After transcription:

Generate:

* meeting summary
* action items
* key decisions

---

## Structured exports

Allow exporting:

* transcript
* Markdown
* meeting notes
* JSON
* timestamped transcript

---

## Automatic language detection and translation

Keep transcription separate from translation, but allow translation as a post-processing option.

---

## Prompt-based transcript cleanup

Optional transformations such as:

* remove filler words
* improve punctuation
* preserve verbatim wording
* produce publication-ready transcript

---

## Cloud-only enhancements

Future OpenAI features may include richer transcript metadata, improved formatting, or new speech models. The provider abstraction should allow these to be adopted without affecting the local engine architecture. ([OpenAI Developers][1])

---

## Success criteria

The feature should be considered successful if:

* Existing users can continue using the app exactly as before.
* New users can choose between Local and OpenAI with a single, obvious decision.
* The rest of the application workflow is effectively unchanged.
* The transcription engine becomes a replaceable service rather than being embedded in the application's identity.
* Future transcription providers and transcription-related AI features can be added without requiring significant UI redesign or changes to the controller and queue-driven workflow.

[1]: https://developers.openai.com/api/docs/models/gpt-4o-transcribe?utm_source=chatgpt.com "GPT-4o Transcribe Model | OpenAI API"
[2]: https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize?utm_source=chatgpt.com "GPT-4o Transcribe Diarize Model | OpenAI API"
