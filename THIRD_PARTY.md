# Third-party materials

Runtime: Python 3.14.4 standard library (Python Software Foundation license) and browser-native HTML/CSS/JavaScript APIs. No vendored libraries, external fonts, downloaded images or historical application assets.

Development browser verification pins Playwright 1.63.0 (Apache-2.0), with pyee 13.0.1, greenlet 3.4.0 and typing_extensions 4.16.0 in requirements-dev.txt. These packages are optional test dependencies and their source/binaries are not bundled in the release archive. Package metadata and licenses are available from their respective PyPI project pages. CI uses actions/checkout v4 and actions/setup-python v5. No third-party model weights are included.

Playwright package reference: https://pypi.org/project/playwright/1.63.0/.

Optional local runtime model: Meta Llama 3.2 3B Instruct (`llama3.2:3b-instruct-q4_K_M`), Llama 3.2 Community License, Copyright © Meta Platforms, Inc. All Rights Reserved. Built with Llama. Weights are downloaded by the user from the official Ollama registry into a private directory and are not redistributed. Ollama is installed separately (MIT). License: https://www.llama.com/llama3_2/license/

Optional PC Bluetooth: bleak 3.0.2 (MIT) with winrt-runtime on Windows, installed separately; not bundled.
Companion build: official Android SDK command-line tools, build-tools 34.0.0 and platform android-34 (Android Software Development Kit License, accepted by the participant); the Companion uses only Android framework APIs and no third-party libraries. The SDK is not redistributed.
