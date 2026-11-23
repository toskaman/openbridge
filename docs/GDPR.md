# Personal data and the GDPR

How OpenBridge handles personal data, for owners, for companies evaluating or deploying it, and for partners.
[Version française](#version-française). This page describes the software; it is not legal advice and has not yet
been reviewed by counsel.

## The short version

OpenBridge runs on **your** machine. The author of OpenBridge receives **no** personal data from it: no telemetry, no
account, no analytics, no crash reports ([privacy note](PRIVACY.md)). Whoever runs OpenBridge decides what it
processes, and is the one the GDPR looks at.

| Who runs it | Role under the GDPR |
|---|---|
| A person, at home | Usually outside the GDPR (household activity, Art. 2(2)(c)) |
| A company (evaluation, internal use, product) | The company is the **controller** for what its installation processes |
| The OpenBridge author | Neither controller nor processor of installations; processor only for files a partner chooses to send under a written agreement |

## What an installation processes, and where it stays

All in the OpenBridge data folder on the PC (`%LOCALAPPDATA%\OpenBridge` on Windows, `~/.local/share/OpenBridge`
elsewhere):

| Data | File | Personal? | Kept |
|---|---|---|---|
| Device inventory (salted pseudonyms, categories, labels you gave) | data folder | labels can be (e.g. "Anna's lamp") | until removed |
| Typed and spoken requests | handled on the PC; the audio is not saved; the text can appear in receipts and logs | yes | until removed |
| Receipts, approvals, evidence logs | data folder | can reveal habits | until removed |
| What OpenBridge learned per device | `device_learning.json` | indirectly (habits) | until `openbridge learn reset` |
| Device links and skills | `device_links.json`, `skill_library.json` | indirectly | until removed |
| Quality reports (off by default) | `quality.json` | no: counts per model and firmware only | until `quality disable --forget` |
| Home Assistant address and token, Tuya keys | `home_assistant.json`, `tuya.json`, the OS vault (`vault`) | credentials | until disconnected |
| Pairing keys of the Companions | data folder and the paired device | no | until revoked |

Voice clips are transcribed on the PC and the audio is not saved. Raw device serials and addresses never reach the shared graph.

## When data leaves the PC

Only when the owner sets it up: connecting a remote AI by hand (each request then goes to that address, with consent
per request), a device talking to its own vendor's cloud, or the owner sending an exported file (skills, quality
report). For a company, a remote AI provider is a processor or a third party: check its terms and any transfer outside
the EU before connecting it.

## Rights of the people concerned

Everything is local and readable, so an installation can answer access, rectification and erasure requests itself:
`openbridge learn reset --consent ALLOW`, `openbridge quality disable --forget`, `openbridge skills remove ID`, `openbridge links remove
ID`, revoking pairings, or deleting the data folder. People who live or work where OpenBridge runs should be told
what it does, especially voice and device-activity history.

## Companies: a checklist

- Record the processing in your register; name the purpose (for example, testing your devices).
- Keep receipts and learning only as long as you need them, then erase.
- Do not connect a remote AI with personal requests unless you have assessed the provider.
- For workplace use, inform staff, and consult the works council where required.
- A data protection impact assessment may be needed for voice processing at scale.

## Partners

Documents, SDKs, firmware and test data shared under NDA stay out of the public repository. Quality report files hold
no personal data by design; when a partner plan includes processing anything personal, the agreement includes data
processing terms (Art. 28). Contact: [info@lepcpro.fr](mailto:info@lepcpro.fr?subject=OpenBridge%3A%20GDPR).

---

## Version française

**RGPD, en bref.** OpenBridge fonctionne sur **votre** machine et l'auteur ne reçoit **aucune** donnée personnelle
(ni télémétrie, ni compte, ni statistiques). Chez un particulier, l'usage relève en général de l'exemption domestique
(art. 2(2)(c)). Une entreprise qui l'utilise est **responsable de traitement** pour son installation. L'auteur n'est
ni responsable ni sous-traitant des installations ; il n'est sous-traitant que pour les fichiers qu'un partenaire
choisit de lui envoyer dans le cadre d'un accord écrit.

Les données (inventaire pseudonymisé, demandes, reçus, apprentissage, liens, skills, identifiants Home Assistant et
Tuya, clés d'appairage) restent dans le dossier de données du PC. L'audio de la voix est transcrit sur le PC et n'est
pas conservé (le texte peut figurer dans les reçus). Les rapports qualité sont désactivés par défaut et ne contiennent que des comptes par modèle et firmware.
Rien ne sort sans action du propriétaire (IA distante connectée à la main, cloud du fabricant d'un appareil, fichier
exporté et envoyé).

Droits des personnes : tout est local et lisible ; effacement avec `learn reset`, `quality disable --forget`,
`skills remove`, `links remove`, révocation des appairages, ou suppression du dossier de données. Les personnes qui
vivent ou travaillent là où OpenBridge fonctionne doivent être informées. Cette page décrit le logiciel ; ce n'est pas
un avis juridique et elle n'a pas encore été relue par un avocat.
