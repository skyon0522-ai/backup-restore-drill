# Documentation reference and intended use

Reader: a technical reviewer assessing a bounded business-data recovery example before considering real backup work. Purpose: understand the run, source composition, evidence, and limits without executing an unfamiliar engine or supplying user data. Voice: plain technical English; preserve identifiers, quantities, authority, and uncertainty.

Inspected reference: the approved local `transactional-outbox-service` public stage's README, PROVENANCE, VERIFICATION, source manifests, verification helpers, and `.github/workflows/checks.yml`. Adopted order: concrete use case → executable local procedure → expected output → composition/attribution → limits. Keep source provenance and observed original/duplicate/composed checks in separate editable Markdown files. The source verifier reuses its size/SHA-256 manifest comparison approach; this stage adds original Git blob checks.

Implementation references: the pinned Rustic subprocess tests and repository fixture helper identified in PROVENANCE.md. The drill's command order and acceptance checks derive from those original implementations. No new visual direction was introduced. Markdown is the source-native medium for repository review; links connect exact source paths, manifests, diffs, and license files.

Checks: read back the saved Markdown, exercise every command block, verify local relative links, inspect staged source inclusion/exclusion, and compare all copied bytes. English language review is handled separately by the parent before any release. A local stage does not establish public publication or remote CI execution.


## Linux usability increment, 2026-10-15

Retain the copied engine and original drill. Add a standard-library Python
entrypoint around that exact command flow and a current-file reader beside the
existing verifier. Reuse the RAG Citation Review layout: current summary first,
separate saved results, keyboard-scrollable table, expandable JSON and visible
scope. Recorded success must not override a current mismatch. Source, restore
and saved baseline remain distinct, with literal comparison alongside hashes.
State the fixed public password accurately. Separate empty-target compilation,
later cache reuse, file checks, changed-input controls and actual rendering.
