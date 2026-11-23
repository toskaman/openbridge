# ENGO × OpenBridge — Dossier de collaboration technique et demandes d'évolution

> **Version destinée à ENGO / Microoled — partage externe après revue**  
> Version : 1.0 — 23 novembre 2026  
> Langues : Français / English  
> Produit de référence : ENGO 3 Photochromic — ActiveLook  
> Projet logiciel : OpenBridge — https://github.com/toskaman/openbridge

---

# PARTIE A — FRANÇAIS

## 1. Objet de ce dossier

OpenBridge développe une plateforme logicielle qui permet à différents appareils connectés de partager des données, des notifications et des fonctionnalités de manière sécurisée. Les lunettes ENGO 3 Photochromic constituent un périphérique d'affichage tête haute particulièrement intéressant : elles peuvent présenter à l'utilisateur les informations importantes sans qu'il ait à consulter constamment son téléphone ou son compteur.

Nous avons déjà développé une intégration logicielle OpenBridge / ActiveLook comprenant un adaptateur, un pont téléphone/IA, un émulateur HUD, HUD Studio, des écrans de démonstration, des outils de test et une première bibliothèque de fonctionnalités. Cette intégration doit désormais être consolidée avec le matériel ENGO 3 réel, puis documentée avec des preuves reproductibles.

**Notre objectif :** proposer aux utilisateurs ENGO un écosystème complémentaire qui étend les possibilités des lunettes sans compromettre leur légèreté, leur autonomie, leur lisibilité et leur simplicité.

Ce dossier sépare volontairement :

1. les fonctions réalisables dans OpenBridge sans changement matériel ;
2. les informations, API et clarifications que nous sollicitons auprès d'ENGO / Microoled ;
3. les évolutions firmware éventuellement utiles ;
4. les améliorations matérielles qui ne pourraient concerner qu'une future génération de lunettes.

## 2. Architecture d'utilisation proposée

Les ENGO 3 restent l'écran HUD et le point d'interaction gestuelle. Un smartphone porté au bras, dans une poche ou fixé au guidon peut fournir le GPS, le microphone, la caméra à la demande, la connexion Internet et les connexions aux capteurs. Un PC OpenBridge peut compléter le système avec l'IA locale, les services connectés, les données de simulateurs ou des notifications techniques.

```text
Capteurs BLE / GPS / microphone / applications / PC / services autorisés
                              |
                              v
                    OpenBridge Companion
                    (Android / iOS selon support)
                              |
                       BLE ActiveLook
                              |
                              v
                      ENGO 3 Photochromic
                       HUD 304 × 256
```

Le Companion peut également relayer des données vers le moteur OpenBridge PC. Dans ce mode, le PC exécute les traitements plus lourds et renvoie aux lunettes des événements HUD courts et localisés.

### Principes de conception

- Le calcul, l'IA, la navigation et l'agrégation des capteurs sont réalisés sur le téléphone ou le PC.
- Les lunettes affichent des valeurs, symboles, jauges, directions et alertes concises.
- Aucun flux vidéo continu n'est nécessaire.
- Les interactions gestuelles ne remplacent pas les consentements explicites pour les actions sensibles.
- Les fonctions restent disponibles en mode dégradé lorsque le téléphone perd Internet ; les capacités qui nécessitent le cloud doivent le signaler.
- Les données sont privées par défaut et les permissions restent contrôlables par l'utilisateur.

## 3. Fonctionnalités envisagées côté OpenBridge

Les groupes de fonctions ci-dessous sont des **fonctions logicielles côté OpenBridge**. Ils ne nécessitent pas nécessairement de modification du firmware ou de la monture, à condition que les capacités ActiveLook documentées soient accessibles aux applications partenaires.

### 3.1 Sport et entraînement

- Running : allure instantanée/cible, distance, durée, cadence, zones cardio, puissance si fournie, intervalles, autolap et progression.
- Cyclisme : vitesse, cadence, puissance, dénivelé, pente, objectifs de puissance et données compatibles de transmission.
- Trail et randonnée : suivi GPX, altitude, dénivelé restant, points de ravitaillement, ETA et barrières horaires.
- Entraînements structurés : échauffement, répétitions, récupération, seuil, tempo, pyramides, côtes et compte à rebours.
- Historique et rapports : comparaison entre sorties, records, synthèses et exports.
- Sports complémentaires : aviron, indoor, ski, golf et activités nautiques lorsque les capteurs/API nécessaires sont disponibles.

### 3.2 Navigation

- Guidage virage par virage avec flèche et distance.
- Import et suivi de fichiers GPX.
- Alerte de sortie d'itinéraire et recalcul.
- Navigation hors ligne avec cartes téléchargées sur le téléphone.
- Retour au point de départ.
- ETA, distance et dénivelé restant.
- Points d'intérêt : eau, refuge, ravitaillement et rendez-vous.
- Navigation adaptée au profil running, vélo ou randonnée.

### 3.3 Ghost Competition

- Comparaison avec une sortie précédente ou un record personnel.
- Adversaire virtuel basé sur une activité historique.
- Écart en temps et distance.
- Projection du résultat final.
- Défis partagés avec des amis lorsque le partage est autorisé.
- Comparaison par kilomètre, segment, tour ou ascension.

### 3.4 Coach et assistant vocal

- Coach contextuel basé sur les métriques disponibles.
- Conseils courts de rythme, puissance, cadence et récupération.
- Analyse après la séance.
- Génération d'un plan d'entraînement.
- Commandes vocales en français et en anglais via le microphone du téléphone ou un microphone externe compatible.
- Réponses courtes dans le HUD et réponses audio via des écouteurs externes.
- Traduction et sous-titres à la demande.

### 3.5 Capteurs et accessoires

- Ceintures cardio et capteurs optiques compatibles BLE.
- Capteurs de vitesse, cadence et puissance vélo.
- Footpods et capteurs de dynamique de course.
- Radars arrière compatibles.
- Capteurs de pression des pneus.
- Home trainers, tapis, rameurs et vélos indoor utilisant des profils standard compatibles.
- Montres et plateformes sportives, selon les possibilités officielles d'export/API.
- ANT+ via un relais ou adaptateur compatible lorsque nécessaire.

### 3.6 Téléphone et PC

- Téléphone utilisé comme source GPS, microphone, caméra à la demande et passerelle Internet.
- Mode brassard pour la course et mode support guidon pour le vélo.
- Alertes de navigation et d'entraînement.
- Télémétrie d'applications PC et de simulateurs.
- Notifications de build, CI/CD, serveurs et applications autorisées.
- API locale pour extensions et connecteurs.

### 3.7 OpenBridge et appareils connectés

- Notifications d'état d'appareils.
- Confirmations d'action vérifiées.
- Alertes de déconnexion ou d'erreur.
- Informations de réseau, énergie, météo et environnement lorsque les sources existent.
- Affichage compact du statut d'un robot, téléviseur, routeur, service ou appareil domotique.
- Toute action sur un appareil reste soumise aux règles de consentement, de sécurité et de vérification OpenBridge.

### 3.8 Sécurité et confidentialité

- Partage de position avec contacts désignés.
- SOS manuel.
- Alerte de perte GPS, réseau ou batterie.
- Détection expérimentale de chute avec confirmation et limites clairement affichées.
- Pas de promesse de sécurité vitale ou de détection infaillible.
- Microphone et caméra utilisés à la demande, avec indicateur visible et arrêt immédiat.
- Pas d'enregistrement permanent par défaut.

### 3.9 Interface bilingue

L'application OpenBridge propose un sélecteur explicite :

`Réglages / Settings → Général / General → Langue / Language → Auto | Français | English`

La préférence s'applique au Companion et au HUD, avec une option permettant de choisir une langue HUD différente de celle de l'application. Les unités sont réglables indépendamment de la langue. (L'interface web du PC reste en anglais à ce jour.)

### 3.10 État factuel au 23 novembre 2026

| Domaine | État | Niveau de preuve |
|---|---|---|
| Menus HUD, messages du téléphone, télécommande TV, aspirateur, voix | Implémenté | Émulateur HUD Studio uniquement |
| Transport ActiveLook (MTU, flow control, file bornée, contrôleur unique, reconnexion) | Implémenté | Tests unitaires ; matériel réel non testé |
| Course, vélo, séances fractionnées, Ghost, navigation GPX | Moteurs implémentés | Données simulées uniquement |
| Décodeurs capteurs BLE standard (FC, RSC, CSC, puissance, FTMS, batterie) | Implémentés | Tests sur octets de la spécification ; aucun capteur réel connecté |
| Français / English (Companion et HUD) | Implémenté | Compilation et tests ; pas encore essayé sur téléphone |
| Connexion à une ENGO 3 Photochromic physique | **Non réalisée** | En attente de la paire |

Le détail par fonctionnalité figure dans la matrice de traçabilité jointe. Aucun résultat d'émulateur n'est présenté comme une validation matérielle.

## 4. Demandes adressées à ENGO / Microoled

Notre première demande est la confirmation écrite des capacités déjà disponibles. Nous préférons utiliser correctement les API et firmwares actuels plutôt que demander des évolutions inutiles.

### 4.1 Documentation et accès développeur — priorité P0

Nous sollicitons :

1. La documentation officielle et à jour de l'API ActiveLook correspondant précisément à l'ENGO 3 Photochromic.
2. La version du SDK Android et iOS recommandée pour ce modèle et son firmware.
3. Les conditions d'accès, de redistribution et d'utilisation commerciale des SDK, API, exemples et outils.
4. La procédure officielle d'appairage et les éventuelles contraintes liées à l'application ENGO Compagnon.
5. La confirmation du nombre de connexions BLE centrales simultanées autorisées.
6. Les règles de coexistence entre une application tierce et l'application officielle.
7. La procédure de certification ou de validation d'une application partenaire.
8. La liste des versions firmware compatibles et les règles de dépréciation.
9. Les limites de débit, MTU, taille des commandes, flow control, cadence d'actualisation et taille de file recommandée.
10. Les limites exactes concernant les layouts persistants, les polices, icônes, ressources graphiques et mémoire.

### 4.2 Informations techniques à confirmer — priorité P0

Merci de confirmer pour ENGO 3 Photochromic :

- résolution et zone utile réelle de l'écran ;
- palette couleur et commandes disponibles ;
- dimensions, coordonnées, orientation et éventuelles zones optiques non lisibles ;
- liste des polices embarquées, encodages et caractères supportés ;
- prise en charge réelle de UTF-8, accents français et ponctuation ;
- longueur maximale recommandée des lignes et des chaînes ;
- tailles maximales de layouts, d'images, de polices et de stockage persistant ;
- gestes reconnus, événements BLE, comportement du tactile et options de configuration ;
- données accessibles par BLE : niveau de batterie, modèle, révision, firmware, état capteurs ;
- commandes de luminosité et relation avec la luminosité automatique ;
- comportement de veille, réveil et effacement ;
- comportement en cas de perte de liaison et de reconnexion ;
- comportement de flow control et sémantique de chaque état ;
- autonomie officiellement mesurée selon une méthode reproductible.

### 4.3 Capacités API / firmware utiles — priorité P1

Si elles ne sont pas déjà supportées, nous aimerions étudier les évolutions suivantes, sous réserve de faisabilité et de votre feuille de route :

- notifications fiables et documentées pour les événements de geste/toucher ;
- paramètres configurables des gestes, ou au minimum description stable de leur sémantique ;
- lecture standardisée de la batterie et de l'état de l'appareil ;
- identification stable du modèle et de la version firmware ;
- commandes d'affichage atomiques ou mises à jour ciblées de widgets ;
- gestion documentée des pages/layouts utilisateur ;
- récupération et vérification de la configuration des layouts ;
- signalement clair des erreurs de trame et d'overflow ;
- flow control avec état explicite et documenté ;
- procédure de calibration ou d'orientation accessible aux applications partenaires ;
- API de diagnostic non intrusive ;
- mode développeur permettant de tester un écran sans modifier les préférences permanentes de l'utilisateur.

### 4.4 Outils développeur souhaités — priorité P1/P2

- SDK Android maintenu avec exemples de connexion, gestes, affichage, flow control et reconnexion.
- SDK iOS avec les mêmes capacités documentées lorsque les règles iOS le permettent.
- Exemple ou SDK desktop (Windows/macOS/Linux) si le support PC direct est envisageable.
- Outil de diagnostic GATT officiel.
- Outil de calibration écran et gestes.
- Jeu de layouts d'exemple pour ENGO 3 couleur.
- Simulateur ou émulateur officiel, ou format de test permettant de comparer un rendu logiciel à l'affichage réel.
- Changelog de firmware et notes de compatibilité.
- Canal de support technique pour développeurs partenaires.

## 5. Évolutions matérielles — uniquement pour une future génération

Les fonctions suivantes ne peuvent pas être ajoutées par une simple application si le matériel actuel ne comporte pas les composants correspondants. Elles sont donc des pistes de discussion pour une génération future, et non des prérequis à l'intégration actuelle :

- microphone intégré à faible consommation ;
- transducteurs audio ouverts ou conduction osseuse ;
- caméra intégrée avec obturateur/indicateur physique et contrôles de confidentialité ;
- GNSS/GPS intégré ;
- capteurs inertiels avancés si ceux existants ne suffisent pas ;
- retour haptique discret ;
- mémoire/flash ou RAM supplémentaires si une capacité locale plus importante est envisagée ;
- antenne et architecture radio optimisées pour les environnements sportifs ;
- ergonomie adaptée à différents accessoires ou corrections optiques.

Notre approche actuelle reste de déporter ces fonctions sur le smartphone afin de conserver le poids, l'autonomie et la simplicité des ENGO.

## 6. Tests et critères d'acceptation communs

Nous proposons de valider ensemble les points suivants sur une paire physique identifiée par modèle et version de firmware :

| Domaine | Test d'acceptation |
|---|---|
| Découverte BLE | L'application partenaire découvre et identifie correctement les lunettes |
| Appairage | Connexion et déconnexion propres, sans conflit avec le fonctionnement prévu |
| Affichage | Texte, icônes, chiffres et couleurs rendus dans la zone attendue |
| Français | Accents et caractères requis correctement affichés, ou limites documentées |
| Gestes | Chaque événement est reçu une seule fois et possède une sémantique documentée |
| Flow control | Aucune transmission durant PAUSE ; reprise conforme à l'événement de reprise |
| Charge | Pas de perte de trame dans le profil de test convenu |
| Reconnexion | Récupération après perte BLE, sans commandes dupliquées |
| Batterie | Mesures réalisées avec profil HUD et fréquence de mise à jour décrits |
| Compatibilité | Matrice modèle/firmware/SDK/OS publiée ou convenue |
| Mise à jour | Procédure officielle et limites de responsabilité clairement documentées |

Les tests d'émulateur seront fournis séparément des résultats sur lunettes réelles. Les deux catégories ne seront jamais fusionnées.

## 7. Livrables OpenBridge prévus pour le constructeur

Une fois l'intégration stabilisée et testée sur le matériel physique, nous pouvons fournir :

- un adaptateur logiciel ActiveLook intégré à OpenBridge ;
- une application Companion et son architecture de relais, dans les limites de la licence applicable ;
- un catalogue de fonctionnalités et de layouts ;
- des exemples de données et d'événements HUD ;
- une matrice de compatibilité testée ;
- des tests unitaires, tests d'intégration et scénarios de non-régression ;
- un rapport de latence, de débit et de stabilité mesuré ;
- des captures et vidéos de démonstration sur lunettes physiques ;
- des traces BLE expurgées et des scénarios de reproduction ;
- une liste de limitations et de demandes d'évolution priorisées ;
- une documentation développeur et une proposition d'intégration officielle.

Les livrables partagés seront vérifiés pour retirer les clés, tokens, identifiants personnels, adresses privées, numéros de série non nécessaires et éléments soumis à des droits tiers.

## 8. Points à clarifier avant une intégration officielle

1. Quel est le parcours officiel pour qu'une application indépendante pilote l'ENGO 3 Photochromic ?
2. Peut-on maintenir une connexion BLE tierce pendant que l'application ENGO officielle est installée ou utilisée ?
3. Existe-t-il une contrainte de contrôleur central unique ?
4. Quel est le débit de mise à jour recommandé pour un HUD avec plusieurs widgets dynamiques ?
5. Quels sont les formats et encodages officiellement supportés par le rendu texte ?
6. Peut-on installer ou gérer des layouts personnalisés sans risque pour les layouts de l'application officielle ?
7. Les événements de geste et tactile peuvent-ils être exposés à une application tierce de manière stable entre firmwares ?
8. Quelle est la procédure recommandée de mise à jour firmware ? Une application tierce doit-elle impérativement rediriger vers l'application officielle ?
9. Quelles exigences de certification et de licence s'appliquent à une application open source ou commerciale ?
10. Seriez-vous intéressés par une démonstration technique et une campagne de tests conjointe ?

## 9. Proposition de collaboration

Nous proposons une démarche en trois étapes :

**Étape 1 — Validation technique.** Confirmation des SDK, capacités, versions et limites ; connexion sur matériel réel ; revue des tests.

**Étape 2 — Démonstration.** Présentation des fonctions sportives, navigation, Ghost Competition, assistant vocal via téléphone, capteurs et notifications OpenBridge.

**Étape 3 — Intégration partenaire.** Définition d'un contrat d'API stable, d'une matrice de compatibilité, d'un processus de certification et d'un éventuel plan d'évolution firmware.

Notre objectif est de valoriser la plateforme ENGO/ActiveLook en démontrant que des développeurs tiers peuvent créer des expériences complémentaires, utiles et vérifiables autour de vos lunettes.

## 10. Références

- OpenBridge : https://github.com/toskaman/openbridge
- Dossier technique ENGO dans OpenBridge : https://github.com/toskaman/openbridge/tree/main/docs/partners/engo
- Matrice de traçabilité : https://github.com/toskaman/openbridge/blob/main/docs/partners/engo/21_FEATURE_TRACEABILITY_MATRIX.md
- ENGO : https://www.engoeyewear.com/
- ActiveLook : https://www.activelook.net/
- ActiveLook développeurs : https://github.com/ActiveLook

---

# PART B — ENGLISH

## 1. Purpose of this document

OpenBridge is developing a software platform that allows connected devices to exchange data, notifications and capabilities in a secure and interoperable way. The ENGO 3 Photochromic glasses are a compelling heads-up display: they can surface relevant information without requiring the wearer to constantly check a phone or a bike computer.

We have already developed an OpenBridge / ActiveLook software integration comprising an adapter, a phone/AI bridge, a HUD emulator, HUD Studio, display demonstrations, test tools and an initial feature library. The next step is to consolidate the integration against physical ENGO 3 hardware and document the results with reproducible evidence.

**Our objective:** provide ENGO users with a complementary software ecosystem that expands the glasses' usefulness while preserving their lightweight design, battery life, readability and simplicity.

This document deliberately separates:

1. features OpenBridge can deliver without hardware changes;
2. APIs, documentation and clarifications requested from ENGO / Microoled;
3. firmware improvements that may be useful;
4. hardware changes that would only apply to a future generation.

## 2. Proposed system architecture

The ENGO 3 remains the HUD display and limited gesture input device. A smartphone carried on an armband, in a pocket or mounted on a bicycle can provide GPS, microphone, on-demand camera capture, Internet access and Bluetooth sensor connections. An OpenBridge PC can add local AI, connected-device data, simulator telemetry and developer notifications.

```text
BLE sensors / phone GPS / microphone / apps / PC / approved services
                              |
                              v
                    OpenBridge Companion
                    (Android / iOS where supported)
                              |
                       ActiveLook BLE
                              |
                              v
                      ENGO 3 Photochromic
                         304 × 256 HUD
```

The Companion may also relay data to the OpenBridge PC runtime. In that configuration, the PC performs heavier processing and sends short, localized HUD events back to the glasses.

### Design principles

- Processing, AI, navigation and sensor aggregation run on the phone or PC.
- The glasses display concise values, icons, gauges, directions and alerts.
- No continuous video stream is required.
- Gestures do not replace explicit consent for sensitive actions.
- Local features should remain usable in degraded/no-Internet conditions whenever possible.
- Data is private by default and permissions remain under user control.

## 3. OpenBridge software feature scope

The following items are primarily **OpenBridge software features**. They do not inherently require a hardware or firmware modification, provided the relevant ActiveLook capabilities are available to partner applications.

### 3.1 Sports and training

- Running: current/target pace, distance, duration, cadence, heart-rate zones, power when supplied, intervals and progress.
- Cycling: speed, cadence, power, elevation, gradient, power targets and compatible drivetrain data.
- Trail and hiking: GPX tracking, altitude, remaining ascent/descent, aid stations, ETA and cut-off times.
- Structured workouts: warm-up, repeats, recovery, threshold, tempo, pyramids, hill repeats and countdowns.
- Training history, session reports, personal records and comparisons.
- Additional sports: rowing, indoor training, skiing, golf and water sports where compatible data sources exist.

### 3.2 Navigation

- Turn-by-turn guidance with a directional arrow and distance.
- GPX import and route following.
- Off-route detection and route recalculation.
- Offline maps stored on the phone.
- Return-to-start navigation.
- ETA, remaining distance and elevation.
- Points of interest such as water, shelters, aid stations and meeting points.
- Navigation profiles for running, cycling and hiking.

### 3.3 Ghost Competition

- Compare the current activity with a previous session or personal best.
- Virtual opponent based on a historical activity.
- Time and distance gap.
- Projected finish result.
- Shared challenges based on explicitly authorized activities.
- Comparison by kilometre, segment, lap or climb.

### 3.4 AI coach and voice assistant

- Context-aware coaching based on available metrics.
- Short pace, power, cadence and recovery suggestions.
- Post-session analysis.
- Training-plan generation.
- French and English voice commands through the phone microphone or a compatible external microphone.
- Short HUD answers and optional audio responses through external headphones.
- On-demand translation and subtitles.

### 3.5 Sensors and accessories

- Compatible BLE heart-rate straps and optical sensors.
- Cycling speed, cadence and power sensors.
- Running footpods and running-dynamics sensors.
- Compatible rear radars.
- Tyre-pressure sensors.
- Smart trainers, treadmills, rowers and indoor bikes using supported standard profiles.
- Watches and sports platforms, subject to their official API/export capabilities.
- ANT+ through a compatible relay or adapter where required.

### 3.6 Phone and PC

- Smartphone as GPS, microphone, on-demand camera and Internet gateway.
- Armband running mode and handlebar cycling mode.
- Navigation and workout alerts.
- PC and simulator telemetry.
- Build, CI/CD, server and approved application notifications.
- Local API for extensions and connectors.

### 3.7 OpenBridge connected devices

- Device status notifications.
- Verified action receipts.
- Offline and error alerts.
- Network, energy, weather and environmental data when sources are available.
- Compact status for a robot, TV, router, service or smart-home device.
- Any action affecting another device remains subject to OpenBridge consent, safety policy and verification.

### 3.8 Safety and privacy

- Location sharing with selected contacts.
- Manual SOS.
- GPS, network and battery-loss alerts.
- Experimental fall detection with confirmation and clearly stated limitations.
- No claim of life-critical reliability or infallible detection.
- Microphone and camera are on-demand, visibly indicated and immediately stoppable.
- No always-on recording by default.

### 3.9 Bilingual interface

The OpenBridge application provides an explicit selector:

`Settings / Réglages → General / Général → Language / Langue → Auto | Français | English`

The preference applies to the Companion and the HUD, with an optional independent HUD language. Units are configurable separately from language. (The PC web interface is still English-only.)

### 3.10 Factual status, 23 November 2026

| Area | Status | Evidence level |
|---|---|---|
| HUD menus, phone messages, TV remote, vacuum, voice | Implemented | HUD Studio emulator only |
| ActiveLook transport (MTU, flow control, bounded queue, single controller, reconnect) | Implemented | Unit tests; not run on real hardware |
| Running, cycling, interval workouts, Ghost, GPX navigation | Engines implemented | Simulated data only |
| Standard BLE sensor decoders (HR, RSC, CSC, power, FTMS, battery) | Implemented | Tested against specification byte layouts; no real sensor connected |
| Français / English (Companion and HUD) | Implemented | Build and tests; not yet tried on a phone |
| Connection to a physical ENGO 3 Photochromic | **Not done** | Waiting for the pair |

Per-feature detail is in the attached traceability matrix. No emulator result is presented as hardware validation.

## 4. Requests to ENGO / Microoled

Our first request is written confirmation of the capabilities already available. We would prefer to use the current APIs and firmware correctly instead of requesting unnecessary changes.

### 4.1 Developer documentation and access — priority P0

We request:

1. Current official ActiveLook API documentation for the exact ENGO 3 Photochromic model.
2. Recommended Android and iOS SDK versions for this model and firmware.
3. SDK/API/sample-code access, redistribution and commercial-use terms.
4. Official pairing procedure and any constraints involving the ENGO Companion application.
5. Confirmation of the number of simultaneous BLE central connections supported.
6. Coexistence rules between a third-party application and the official application.
7. Partner application certification or validation process.
8. Supported firmware versions and deprecation policy.
9. Recommended throughput, MTU, maximum command sizes, flow control, refresh rate and queue size.
10. Exact limits for persistent layouts, fonts, icons, graphical resources and device memory.

### 4.2 Technical characteristics to confirm — priority P0

For the ENGO 3 Photochromic, please confirm:

- actual display resolution and usable display area;
- supported colour palette and colour commands;
- coordinate system, orientation and optical safe area;
- installed fonts, encodings and supported characters;
- actual UTF-8 support, including French accents and punctuation;
- recommended maximum line length and text string size;
- maximum layout, image, font and persistent-storage sizes;
- supported gestures, BLE events, touch behaviour and configuration options;
- BLE-readable data: battery level, model, hardware revision, firmware and sensor state;
- brightness commands and interaction with automatic brightness;
- sleep, wake and clear-screen behaviour;
- disconnection and reconnection behaviour;
- flow-control states and their exact semantics;
- officially measured battery life under a reproducible test method.

### 4.3 Useful API / firmware capabilities — priority P1

If not already supported, we would like to discuss the feasibility and roadmap for:

- reliable, documented gesture/touch event notifications;
- configurable gesture settings or, at minimum, stable documented event semantics;
- standardized battery and device-state reporting;
- stable model and firmware identification;
- atomic display commands or targeted widget updates;
- documented user-layout management;
- layout configuration read-back and verification;
- explicit frame-error and overflow reporting;
- documented flow control with well-defined states;
- display orientation and calibration workflow accessible to partner applications;
- non-invasive diagnostic API;
- developer mode for testing a layout without changing the user's persistent preferences.

### 4.4 Developer tooling — priority P1/P2

- Maintained Android SDK with connection, gesture, display, flow-control and reconnection examples.
- iOS SDK with equivalent documented capabilities where iOS permits them.
- Desktop example or SDK (Windows/macOS/Linux) if direct PC support is feasible.
- Official GATT diagnostic tool.
- Display and gesture calibration tool.
- Sample layout library for the ENGO 3 colour display.
- Official simulator/emulator, or a test format to compare software output with the real display.
- Firmware changelog and compatibility notes.
- Technical support channel for partner developers.

## 5. Hardware improvements — future generation only

The following features cannot be added by a software application if the required components are not present in the current product. They are therefore future-generation discussion topics, not requirements for the current integration:

- low-power integrated microphone;
- open-ear audio transducers or bone-conduction audio;
- integrated camera with physical privacy shutter/indicator and clear controls;
- integrated GNSS/GPS;
- advanced inertial sensors if current sensors are insufficient;
- discreet haptic feedback;
- additional memory/flash or RAM for greater local capability;
- radio/antenna improvements for demanding sports environments;
- frame ergonomics for accessories or prescription options.

Our current approach is to offload these functions to the smartphone so that the ENGO glasses retain their low weight, battery life and simplicity.

## 6. Joint test plan and acceptance criteria

We propose validating the following on a physical pair identified by model and firmware version:

| Area | Acceptance test |
|---|---|
| BLE discovery | Partner application discovers and identifies the glasses correctly |
| Pairing | Clean connect/disconnect without conflicts with the agreed operating mode |
| Display | Text, icons, numbers and colours render in the expected area |
| French | Required accents and characters render correctly, or limitations are documented |
| Gestures | Each event is delivered once and has documented semantics |
| Flow control | No writes while PAUSE is active; resume follows the documented notification |
| Load | No frame loss in the agreed stress profile |
| Reconnection | Recovery after BLE loss without duplicate commands |
| Battery | Measurements taken with a documented HUD profile and refresh rate |
| Compatibility | Model/firmware/SDK/OS matrix published or agreed |
| Firmware update | Official update procedure and responsibilities clearly documented |

Emulator tests will be reported separately from real-glasses results. They will never be merged into one validation category.

## 7. OpenBridge deliverables for the manufacturer

Once the integration is stable and validated on physical hardware, we can provide:

- ActiveLook software adapter integrated into OpenBridge;
- Companion application and relay architecture, subject to applicable licensing;
- feature and HUD-layout catalogue;
- HUD data and event examples;
- tested compatibility matrix;
- unit, integration and regression tests;
- measured latency, throughput and reliability report;
- physical-glasses screenshots and demo videos;
- sanitized BLE traces and reproducible test cases;
- known limitations and prioritized enhancement requests;
- developer documentation and an official integration proposal.

Shared deliverables will be reviewed to remove keys, tokens, personal identifiers, private addresses, unnecessary serial numbers and third-party material that we are not entitled to redistribute.

## 8. Questions to resolve before an official integration

1. What is the official process for a third-party application to control the ENGO 3 Photochromic?
2. Can a third-party BLE connection coexist with the official ENGO application installed or running?
3. Is there a single-central connection restriction?
4. What update rate is recommended for a HUD with several dynamic widgets?
5. Which text formats and encodings are officially supported?
6. Can custom layouts be installed or managed without affecting official application layouts?
7. Are gesture and touch events exposed to third-party applications consistently across firmware versions?
8. What is the recommended firmware update process? Must third-party applications redirect users to the official application?
9. Which certification and licensing requirements apply to a third-party or commercial application?
10. Would ENGO / Microoled be interested in a technical demonstration and joint validation campaign?

## 9. Collaboration proposal

We suggest three steps:

**Step 1 — Technical validation.** Confirm SDKs, capabilities, versions and limits; connect to physical hardware; review tests.

**Step 2 — Demonstration.** Present sports features, navigation, Ghost Competition, phone-based voice assistant, sensors and OpenBridge notifications.

**Step 3 — Partner integration.** Define a stable API contract, compatibility matrix, certification process and any firmware improvement roadmap.

Our goal is to demonstrate the value of the ENGO / ActiveLook platform by showing that third-party developers can build useful, reliable and verifiable experiences around your glasses.

## 10. References

- OpenBridge: https://github.com/toskaman/openbridge
- OpenBridge ENGO technical dossier: https://github.com/toskaman/openbridge/tree/main/docs/partners/engo
- Traceability matrix: https://github.com/toskaman/openbridge/blob/main/docs/partners/engo/21_FEATURE_TRACEABILITY_MATRIX.md
- ENGO: https://www.engoeyewear.com/
- ActiveLook: https://www.activelook.net/
- ActiveLook developer organization: https://github.com/ActiveLook

---

## Annexe — Checklist avant envoi / Pre-send checklist

- [x] Statut factuel au 23 novembre 2026 ajouté (§3.10) ; à remettre à jour après les essais réels.
- [ ] Remplacer toute formulation au futur restante par un statut factuel actualisé.
- [ ] Ajouter le commit/tag OpenBridge correspondant aux fichiers livrés.
- [ ] Ajouter la version de l'application Companion.
- [ ] Ajouter le modèle et firmware exacts testés.
- [ ] Joindre les rapports de tests sur lunettes physiques.
- [x] Séparer les preuves émulateur et matériel réel (catégories distinctes dans la matrice).
- [ ] Inclure une vidéo courte montrant la connexion BLE réelle et plusieurs fonctions.
- [x] Inclure les limites connues et les fonctions non validées (§3.10 et matrice de traçabilité).
- [ ] Vérifier les licences des SDK, bibliothèques, captures et exemples.
- [x] Supprimer toutes les clés, tokens, données personnelles et adresses privées (vérifié le 23 novembre 2026 ; à refaire avant chaque envoi).
- [ ] Faire relire le dossier par ENGO / Microoled avant toute communication publique de compatibilité.
