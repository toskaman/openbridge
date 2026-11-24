# Event-driven Android connection updates

When the user explicitly selects Android USB, the browser may subscribe to a local server-sent event stream. The server uses the installed ADB track-devices command rather than subnet scanning or periodic discovery. Track output is consumed privately; only the existing adapter's redacted inventory is published.

Share one owned tracking subprocess among subscribers. Start it on first subscription; stop it after the last subscriber leaves or the server closes. Use bounded subscriber queues, suppress duplicate device-state frames and publish a safe unavailable state if ADB exits. Never log serials or return raw subprocess output.

The browser closes the stream on source changes or errors. Incoming inventory events invalidate stale inspection results and refresh device states. Manual listing remains available when tracking is unavailable. No model call or device write is triggered by an event.

Tests cover missing ADB, fixed command arguments, redaction, duplicate suppression, bounded queues and cleanup. Browser tests use controlled event data for disconnection and authorization changes; actual local tracking receives a separately labeled smoke test. Desktop input is never used.
