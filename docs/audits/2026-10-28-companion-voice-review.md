# Companion voice review — 28 October 2026

PR86 exact head96289e244a294db9c2179a6e24966a7156b779df. Scope: independent source review and temporary javac compile. [Compile receipt/source hashes](companion-voice-96289e2.json).

## Verified

All3 Java source files from the pinned Git tree compile with javac --release11 against the installed official Android34 SDK jar; exit0, no diagnostics. Exact sources were written into a new temporary fixture directory and removed afterward. No shared source changes, build script execution, APK packaging/signing, installation, launch, microphone, network provider or hardware activity. The build helper was deliberately not run because it deletes an output directory and accesses signing material; those operations were unnecessary for this source review.

Source shows onResults fills commandInput and does not call submitCommand; Send remains a separate listener. Mic permission requested from Speak, unavailable recognition hides Speak, recognizer destroyed on pause/destroy. These are source observations, not exercised Android UI/permission/recognizer tests. Existing CI6checks pass but does not prove speech behavior. Contributor reported hidden buttons on the two owned devices; that demonstrates unavailable fallback, not successful speech transcription.

## P1 — default recognizer can transmit audio before command review

MainActivity.listen uses SpeechRecognizer.createSpeechRecognizer(this), then startListening. There is no on-device-only factory selection or disclosure/approval of recognizer provider/network audio. Android's official SpeechRecognizer reference states the default implementation is likely to stream audio to remote servers. onResults keeping command text unsent does not keep the microphone stream local. The OS RECORD_AUDIO permission is distinct from consent to disclose spoken private information to a provider.

Primary source: https://developer.android.com/reference/android/speech/SpeechRecognizer (read28Oct2026). It provides isOnDeviceRecognitionAvailable/createOnDeviceSpeechRecognizer on API31+. Use an enforced on-device path when available; on older/unsupported devices, keep typed input available and disable voice unless there is separately explicit provider/data-disclosure approval consistent with project model/privacy policy. Do not use a best-effort offline hint as proof of local-only processing. Separate platform speech-input attribution from Meta planning/proposal inference.

Required regression/acceptance: on-device service present/absent, grant/deny/revoke mic, recognizer unavailable/error/no-match, pause/destroy cancellation and late callback, successful transcription fills editable text but produces zero command submissions until Send, explicit provider/data policy enforcement. Exercise through mock instrumentation or a scoped approved physical run; do not silently open microphone or install a recognizer as a reviewer.

## Remaining project work

- Native owner: revise voice provider/privacy boundary and supply behavior tests; successful real voice path remains NOT_REVERIFIED.
- Credit owner: PR78 arbitrary live ledger override restriction remains unchanged atd49d7a9. Default shared ledger closure and reported owner eval policy decisions remain separately recorded.
- Native owner: PR85 proposed audio-state oracle has offline parser coverage and contributor hardware transcript, not independently witnessed physical acceptance.
- Muse/evaluation owners: correct G3 known-fixture novelty claim, independent oracle/fair rules baseline, and freeze genuinely unseen task before generation.
- Joint owners: full generator/compile/sandbox/grant/install/invoke/read-back/revoke/restart/cleanup evidence, loaded runtime revision and final submission receipt. No video without new explicit owner request.

Release remains BLOCKED. New receipt/review files only; no existing production/protected/frozen artifacts modified, so no existing-file delta backup was required.
