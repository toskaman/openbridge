# OpenBridge licensing transition — November 1, 2026

## Current published source-available terms

OpenBridge's repository now uses **PolyForm Strict License 1.0.0** in [LICENSE](../LICENSE). The published code remains visible to the public, and the license permits noncommercial use including research, experimentation, and testing. PolyForm Strict does **not** generally permit distribution of OpenBridge or modifications/derivative works.

A narrowly scoped [hackathon evaluation permission](../HACKATHON_EVALUATION_PERMISSION.md) supplements the current license so organizers and judges can clone, run, inspect, and evaluate the submitted repository. The official hackathon entry terms and their independently granted organizer rights are unaffected.

The current license is **source-available**, not OSI-approved open source. Do not label the current version as MIT-licensed, fully open-source, or commercial-reuse permitted.

## Historical MIT grant — do not revoke or misrepresent

The repository previously published OpenBridge under the MIT License, including commit `ae1194a6a2d486dfb2e61d2d082aea7ee17ea5f5` on November 1, 2026, and earlier public commits and releases. Copies legally received under MIT retain the MIT permissions associated with those historical versions; a new license cannot retroactively remove those rights.

The MIT text is recoverable unchanged from Git history, for example:

`https://github.com/toskaman/openbridge/blob/ae1194a6a2d486dfb2e61d2d082aea7ee17ea5f5/LICENSE`

This change applies to revisions intentionally published under the new license, to the extent that the copyright holder can license each contribution. It does not itself establish ownership of every file or change the terms of any separate repository or project.

## Third-party materials

Python and optional runtime packages, SDKs, model weights, API services, generated assets, and separately sourced content are subject to independent terms described in [THIRD_PARTY.md](../THIRD_PARTY.md). This licensing transition neither re-licenses those components nor removes applicable copyright and notice requirements.

Before shipping bundled binary releases, audit the actual contents (including notices, weights, assets, and components), rather than relying solely on the source repository inventory.

## Brand

The code license does not grant trademark or branding permission in the OpenBridge name, logo, or identity beyond rights otherwise required by law or specifically granted. No registered-trademark status is asserted here.

## Hackathon source

The participant supplied a Cerebral Valley organizer clarification stating: `No OSI-approved license is required. Organizers have said a source-available license such as PolyForm Noncommercial is fine, as long as the repository is public and open for access, and judges can still run the demo from your setup instructions. Any source-available license works, provided the repo is public.`

The public project must remain accessible and its demo setup reproducible. This document records that clarification as **participant-supplied information**, not an independently authenticated legal ruling. The exact accepted entry waiver governs separately.

## Rights verification

This repo-wide transition does not supersede the need to verify contributor rights and copyright ownership in files authored or supplied by anyone else. The repository owner should review the final legal documents before relying on them for enforcement.
