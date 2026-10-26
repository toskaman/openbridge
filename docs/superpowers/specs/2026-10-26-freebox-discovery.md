# Freebox read-only identification

Add an explicit third source that reads only the documented GET /api_version discovery endpoint on the participant's local Freebox. No subnet discovery, pairing, credentials, login challenge, authenticated endpoint or router changes.

Use the vendor's fixed discovery hostname mafreebox.freebox.fr. Reject redirects and environment proxies. Bound response size and timeout. Return only validated API version, API base path and device family. Never return the gateway address, unique ID, custom device name, API domain or raw error. Device identification is not authenticated control; the UI must say so.

The adapter returns an unavailable state for malformed or unreachable responses. Inspection re-reads the endpoint; it never falls back to a simulated device. Unit tests cover redaction, malformed schemas, failures and unknown handles. Integration and browser tests cover explicit source selection and physical-data refusal by the model endpoint. Verify once against the actual owned gateway and record only non-identifying capability evidence.

Vendor reference: https://dev.freebox.fr/sdk/os/#freebox-discovery.
