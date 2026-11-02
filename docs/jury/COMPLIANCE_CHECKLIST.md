# Hackathon compliance checklist (updated 1 Nov 2026)

Source-backed; each item names its source or is marked OPEN for the owner to
verify in the accepted Official Rules / submission portal. Do not treat this
file as authoritative over the official rules.

Official sources read: [event page](https://dev.meta.ai/events/global-hackathon),
[sign-up page](https://cerebralvalley.ai/e/meta-ai-developer-hackathon) (hosts the
official rules), third-party rules summary (labeled T-P, not authoritative).

| # | Item | Status | Source / evidence |
|---|---|---|---|
| 1 | Deadline: project submissions due Nov 4, 9:00 PM ET | CONFIRMED | Event page Key Dates |
| 2 | Indie Developer track: individual builders, judged on creativity, technical ambition, whether it works | CONFIRMED | Event page tracks |
| 3 | Push the Frontier: new machine capability / better physical control via Meta models | CONFIRMED | Event page themes; OpenBridge: Meta-composed TV panel driving a real vacuum (S5 runbook) |
| 4 | One track per project | CONFIRMED | Sign-up page; T-P: one track, one representative |
| 5 | Scoring: impact 30 / Meta tooling 25 / technical depth 20 / demo 25 | GUIDE CONFIRMED | Participant-provided Cerebral Valley Guide, Judging Rubric, §8 |
| 6 | Three-minute demo video required | GUIDE CONFIRMED | Participant-provided Cerebral Valley Guide, §7 Submission Process |
| 7 | Public repository required | GUIDE CONFIRMED | Participant-provided Cerebral Valley Guide, §§4 and 7. Organizers' participant-supplied clarification states OSI-approved license not required; a public source-available license is acceptable if judges can run the demo |
| 8 | New work and clear pre-existing contributions | GUIDE CONFIRMED | Participant-provided Cerebral Valley Guide §4 + Discord clarification; independent provenance remains documented in `CONTRIBUTIONS.md` |
| 9 | Permitted model use (Meta Model API, open weights, coding agents) | CONFIRMED direction | Event pages: Muse Spark/Image/SAM via API, open weights, Muse Code agent |
| 10 | Runtime is Meta-only; dev assistants are not runtime models | TRUE | `THIRD_PARTY.md`, runtime manifest, Meta-only guards (tested) |
| 11 | No Git history rewrite, no backdated commits | TRUE | This run: merges only, no force-push, no rebase of pushed branches |
| 12 | IP/license: entrants own project; broad organizer license; no confidentiality | T-P ONLY | Third-party summary; owner accepted the official rules at selection |
| 13 | Bonus awards and conditions | GUIDE CONFIRMED | Participant-provided Cerebral Valley Guide §9: Most Viral, Open Weights, Community Vote, Agentic, Creative Build |
| 14 | No award guaranteed or officially approved (claims) | TRUE | No such claim in repo; bonus section is eligibility reasoning only |
| 15 | Submission + publication control stays with the owner | TRUE | Standing project rule; this run prepares materials only |
| 16 | Entrant eligibility exclusions (age/residency/employment/Meta ties) | OPEN | Not on public pages; owner accepted the official rules — confirm no exclusion applies |
| 17 | Organizer license scope (use of entry, name, likeness; duration) | OPEN | T-P: broad license incl. name/likeness, no confidentiality; confirm exact scope in accepted rules |
| 18 | Disputes / governing law / jury-audit rights | OPEN | Not on public pages; confirm in accepted rules |
| 19 | Submission editability after submit (video/repo updates) | OPEN | Not on public pages; confirm in portal before the deadline |

## Owner actions before submitting

1. Open the accepted Official Rules + submission portal; fill OPEN items 16–19 (5–8, 13 already GUIDE CONFIRMED via the Cerebral Valley Guide).
2. Confirm the video requirement + maximum duration before the final edit (storyboard assumes ~180 s).
3. Repository must remain public and accessible. Keep the judge evaluation path executable and source-available license terms clear; see [licensing history](../LICENSING_HISTORY.md).
4. Confirm no eligibility exclusion applies; note the organizer license scope.
5. Submit from the owner's account; keep the CONTRIBUTIONS.md disclosure attached.

## Submission line-in-sand

The submitted revision is the exact commit SHA the owner enters in the portal (TBD at submit time; the release-candidate notes in `docs/jury/RC_NOTES_20261102.md` record the prepared base). Every merged commit, evidence note, and video edit after that SHA is post-submission improvement and must not be presented as judged work. If the portal permits edits after submit (item 19, OPEN), any updated revision is declared with its new SHA and a dated changelog entry — never silently.

## License clarification (participant-provided, 1 November 2026)

The owner supplied a Cerebral Valley organizer clarification that **no OSI-approved license is required**, and public source-available licenses are acceptable if judges can access and run the submission. This is participant-provided organizer guidance, not an independently authenticated waiver. OpenBridge's current source-available license is [PolyForm Strict 1.0.0](../../LICENSE); judges receive a separate scoped [evaluation permission](../../HACKATHON_EVALUATION_PERMISSION.md). Historical MIT licenses remain effective for older versions. The repository must stay public, the demo instructions must work, and official hackathon entry terms continue to apply.
