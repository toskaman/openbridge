# ENGO feature traceability matrix

> Generated from [`feature_registry.json`](feature_registry.json) by `python dev/engo_feature_matrix.py`.
> Do not edit by hand. Statuses: `EXISTING`, `PARTIAL`, `PLANNED`, `BLOCKED`, `HARDWARE_REQUIRED`, `VALIDATED_REAL`.
> Evidence categories never merge: `EMULATOR`, `VIRTUAL_BLE`, `OFFICIAL_APP_BRIDGE`, `SIMULATED`, `REAL_HARDWARE`.
> **No feature is `VALIDATED_REAL` yet: the ENGO 3 Photochromic pair has not arrived.**

| Status | Count |
|---|---:|
| EXISTING | 66 |
| PARTIAL | 31 |
| PLANNED | 217 |
| BLOCKED | 14 |
| HARDWARE_REQUIRED | 6 |
| VALIDATED_REAL | 0 |
| **Total** | **334** |

## Core HUD

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| HUD-001 | Tableau de bord contextuel | PARTIAL | `src/glasses/ui.py:Home,SportDashboard` | `test_glasses.py` | SIMULATED | carousel + sport dashboard; not yet profile-adaptive |
| HUD-002 | Pages personnalisables | PLANNED |  |  |  |  |
| HUD-003 | Thèmes visuels | PLANNED |  |  |  |  |
| HUD-004 | Widgets adaptatifs | PLANNED |  |  |  |  |
| HUD-005 | Alertes transitoires | EXISTING | `src/glasses/events.py, ui.event_card` | `test_glasses_engines.py` | SIMULATED | scheduler: priority, expiry, coalescing, ack |
| HUD-006 | Affichage permanent minimal | PARTIAL | `src/glasses/ui.py:status_bar` | `test_glasses.py` | SIMULATED | clock, link, unread, GPS; not user-selectable yet |
| HUD-007 | Contraste et tailles | PARTIAL | `src/glasses/panel.py` | `test_glasses.py` | SIMULATED | large type, tones; real palette to confirm on ENGO 3 |
| HUD-008 | Mode sans distraction | PLANNED |  |  |  |  |
| HUD-009 | Prévisualisation HUD | EXISTING | `src/glasses/preview.py, HUD Studio` | `test_glasses.py`<br>`test_glasses_engines.py` | EMULATOR | emulator rendering, not the real optics |
| HUD-010 | Widgets communautaires | PLANNED |  |  |  |  |
| HUD-011 | Rotation de cartes par gestes | EXISTING | `src/glasses/ui.py:GestureDecoder,Menu` | `test_glasses.py` | EMULATOR | gestures browse only; actions need the PC grant |
| HUD-012 | Calibration d'affichage | PARTIAL | `src/glasses/ui.py:Calibration, panel.rotate180` | `test_glasses.py` | EMULATOR | orientation only; alignment and brightness on real glasses |

## Connection and maintenance

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| CONN-001 | Découverte et appairage des lunettes | PARTIAL | `src/glasses/hub.py:BleLink` |  |  | scan by name/service; HARDWARE_REQUIRED |
| CONN-002 | Contrôleur BLE unique avec détection de conflit | EXISTING | `src/glasses/transport.py:ControllerLock` | `test_glasses_engines.py` | SIMULATED | PC side; phone side when the Companion holds the link |
| CONN-003 | Reconnexion après perte de liaison, avec limites et backoff | EXISTING | `src/glasses/transport.py:Backoff, hub.BleLink` | `test_glasses_engines.py` | SIMULATED | reconnect loop untested on hardware |
| CONN-004 | État de batterie des lunettes et estimation prudente de durée restante si suffisamment de mesures réelles | HARDWARE_REQUIRED |  |  |  |  |
| CONN-005 | Informations modèle, révision et firmware lorsque les caractéristiques le fournissent | HARDWARE_REQUIRED |  |  |  |  |
| CONN-006 | RSSI et qualité du lien, sans présenter RSSI comme une distance exacte | HARDWARE_REQUIRED |  |  |  |  |
| CONN-007 | Diagnostic GATT et export de traces expurgées | HARDWARE_REQUIRED |  |  |  |  |
| CONN-008 | Test d'affichage, palette, geste et tactile | HARDWARE_REQUIRED |  |  |  |  |
| CONN-009 | Test de latence et débit sur matériel réel | HARDWARE_REQUIRED |  |  |  |  |
| CONN-010 | Gestion des versions et matrice de compatibilité | PLANNED |  |  |  |  |
| CONN-011 | Mode économie d'énergie : limiter les mises à jour, garder les alertes critiques | PLANNED |  |  |  |  |
| CONN-012 | Sauvegarde/restauration de profils HUD | PLANNED |  |  |  |  |
| CONN-013 | Guide de dépannage contextualisé | PLANNED |  |  |  |  |
| CONN-014 | Gestion sûre d'un changement téléphone/PC contrôleur | PARTIAL | `glasses run --takeover` | `test_glasses_engines.py` | SIMULATED | explicit switch on the PC; phone side planned |
| CONN-015 | Gestion de sessions longues, reprise et nettoyage de connexions | PLANNED |  |  |  |  |

## GPS and navigation

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| NAV-001 | Position GPS téléphone, précision et fraîcheur | PARTIAL | `src/glasses/live.py:SportEngine.gps` | `test_glasses_engines.py` | SIMULATED | phone GNSS feed through the Companion is next; simulation today |
| NAV-002 | Vitesse et direction de déplacement estimées | PARTIAL | `src/glasses/sport.py:Session.speed_mps` | `test_glasses_engines.py` | SIMULATED | speed yes, heading not shown |
| NAV-003 | Navigation virage par virage | EXISTING | `src/glasses/nav.py:detect_turns,Follower` | `test_glasses_engines.py` | SIMULATED | turns from route geometry only |
| NAV-004 | Flèche directionnelle du prochain changement | EXISTING | `src/glasses/ui.py:NavScreen, icons.arrow` | `test_glasses_engines.py` | SIMULATED |  |
| NAV-005 | Distance avant virage et nom de voie/rue si disponible | PARTIAL | `src/glasses/nav.py` | `test_glasses_engines.py` | SIMULATED | distance yes; street names not invented when the GPX has none |
| NAV-006 | Instructions de rond-point et intersection | PLANNED |  |  |  |  |
| NAV-007 | Détection de sortie d'itinéraire | EXISTING | `src/glasses/nav.py:Follower (40 m / 25 m hysteresis)` | `test_glasses_engines.py` | SIMULATED |  |
| NAV-008 | Recalcul d'itinéraire | PLANNED |  |  |  |  |
| NAV-009 | Import de GPX et suivi de trace | EXISTING | `src/glasses/nav.py:parse_gpx` | `test_glasses_engines.py` | SIMULATED | no DTD/entities, 5 MB cap |
| NAV-010 | Cartes hors ligne sur téléphone | PLANNED |  |  |  |  |
| NAV-011 | Retour au départ et inversion de trace | EXISTING | `src/glasses/nav.py:Route.reversed` | `test_glasses_engines.py` | SIMULATED | reverse of the loaded route |
| NAV-012 | Distance restante, ETA et heure d'arrivée | EXISTING | `src/glasses/nav.py:Follower` | `test_glasses_engines.py` | SIMULATED | ETA from smoothed speed |
| NAV-013 | Altitude, pente et profil altimétrique si source fiable | PLANNED |  |  |  |  |
| NAV-014 | Points d'intérêt : eau, refuge, ravitaillement, station et rendez-vous | PARTIAL | `src/glasses/nav.py (GPX waypoints)` | `test_glasses_engines.py` | SIMULATED | POIs from the GPX only |
| NAV-015 | Points de passage personnalisés | PARTIAL | `src/glasses/nav.py (GPX waypoints)` | `test_glasses_engines.py` | SIMULATED | import only, no creation on the go |
| NAV-016 | Itinéraire circulaire selon durée/distance disponible | PLANNED |  |  |  |  |
| NAV-017 | Préférence pistes cyclables et chemins adaptés, selon données cartographiques | PLANNED |  |  |  |  |
| NAV-018 | Évitement des axes dangereux ou interdits, uniquement si source fiable et juridiction prise en charge | PLANNED |  |  |  |  |
| NAV-019 | Navigation vers une position partagée avec consentement | PLANNED |  |  |  |  |
| NAV-020 | Navigation contextuelle par profil sportif | PLANNED |  |  |  |  |
| NAV-021 | Direction/boussole basée sur capteurs téléphone ; signaler les limites à l'arrêt | PLANNED |  |  |  |  |
| NAV-022 | Waypoints et marquage vocal d'une position | PLANNED |  |  |  |  |

## Running

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| RUN-001 | Allure instantanée, lissée, moyenne, tour et cible | PARTIAL | `src/glasses/sport.py:Session` | `test_glasses_engines.py` | SIMULATED | instant (15 s smoothed) and average; lap pace planned |
| RUN-002 | Écart à l'allure cible et temps gagné/perdu | PARTIAL | `src/glasses/ui.py:WorkoutScreen` | `test_glasses_engines.py` | SIMULATED | target vs current during work steps |
| RUN-003 | Cadence, longueur de foulée et fréquence de pas si disponibles | PARTIAL | `src/glasses/sensors.py:rsc` | `test_glasses_engines.py` | SIMULATED | from a BLE RSC footpod |
| RUN-004 | Puissance de course et dynamique depuis une source compatible | PLANNED |  |  |  |  |
| RUN-005 | Durée, distance, tour, temps actif et projection d'arrivée | EXISTING | `src/glasses/sport.py:Session` | `test_glasses_engines.py` | SIMULATED |  |
| RUN-006 | Zones de fréquence cardiaque et alertes de seuil | PARTIAL | `src/glasses/sport.py:hr_zone` | `test_glasses_engines.py` | SIMULATED | zones from the owner max HR; threshold alerts planned |
| RUN-007 | Créateur d'entraînements fractionnés | EXISTING | `src/glasses/sport.py:Workout.intervals, glasses run --workout` | `test_glasses_engines.py` | SIMULATED |  |
| RUN-008 | Échauffement, intervalles, récupération et retour au calme | EXISTING | `src/glasses/sport.py:Workout` | `test_glasses_engines.py` | SIMULATED |  |
| RUN-009 | Séances 30/30, 400 m, pyramides, seuil, tempo, côtes et progressives | PLANNED |  |  |  |  |
| RUN-010 | Compte à rebours et annonce du changement de phase | PARTIAL | `src/glasses/live.py (step events), WorkoutScreen` | `test_glasses_engines.py` | SIMULATED | remaining time/distance shown; audio cue planned |
| RUN-011 | Autolap et tour manuel | PARTIAL | `src/glasses/sport.py:Session laps` | `test_glasses_engines.py` | SIMULATED | autolap only |
| RUN-012 | Détection de pause/reprise avec contrôle utilisateur | PLANNED |  |  |  |  |
| RUN-013 | Analyse de régularité par kilomètre/segment | PLANNED |  |  |  |  |
| RUN-014 | Analyse de dérive cardiaque si les données sont suffisantes | PLANNED |  |  |  |  |
| RUN-015 | Estimation de projection 5 km, 10 km, semi et marathon, clairement indicative | PLANNED |  |  |  |  |
| RUN-016 | Negative split et objectif de temps final | PLANNED |  |  |  |  |
| RUN-017 | Profils route, piste, tapis, trail et compétition | PLANNED |  |  |  |  |
| RUN-018 | Rappels de ravitaillement/hydratation configurables | PLANNED |  |  |  |  |
| RUN-019 | Synthèse post-séance et export | PLANNED |  |  |  |  |
| RUN-020 | Comparaison avec une séance historique | PARTIAL | `src/glasses/sport.py:Ghost` | `test_glasses_engines.py` | SIMULATED | needs stored sessions |

## Trail and ultra

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| TRAIL-001 | Profil d'altitude et dénivelé restant | PLANNED |  |  |  |  |
| TRAIL-002 | Prochaine montée/descente, distance et pente estimée | PLANNED |  |  |  |  |
| TRAIL-003 | Points de ravitaillement et distance avant le prochain | PLANNED |  |  |  |  |
| TRAIL-004 | Barrières horaires, temps disponible et ETA | PLANNED |  |  |  |  |
| TRAIL-005 | Estimation de temps de passage | PLANNED |  |  |  |  |
| TRAIL-006 | Plan de ravitaillement et rappels personnalisés | PLANNED |  |  |  |  |
| TRAIL-007 | Navigation hors ligne et retour au parcours | PLANNED |  |  |  |  |
| TRAIL-008 | Partage de position et suivi de groupe | PLANNED |  |  |  |  |
| TRAIL-009 | Mode longue autonomie avec rafraîchissements réduits | PLANNED |  |  |  |  |
| TRAIL-010 | Alertes météo et coucher du soleil | PLANNED |  |  |  |  |

## Cycling

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| BIKE-001 | Vitesse, vitesse moyenne/max, distance et temps | PARTIAL | `src/glasses/sport.py, sensors.CSC` | `test_glasses_engines.py` | SIMULATED | speed, distance, time |
| BIKE-002 | Cadence et puissance | PARTIAL | `src/glasses/sensors.py:CSC,CyclingPower` | `test_glasses_engines.py` | SIMULATED | decoders only; pairing planned |
| BIKE-003 | Puissance moyenne/max et métriques avancées selon capteur | PLANNED |  |  |  |  |
| BIKE-004 | FTP, zones de puissance, IF/TSS/NP uniquement si données et formules validées | PLANNED |  |  |  |  |
| BIKE-005 | Équilibre gauche/droite, torque effectiveness et pedal smoothness si transmis | PLANNED |  |  |  |  |
| BIKE-006 | Pente, dénivelé, profil d'ascension et ETA sommet | PLANNED |  |  |  |  |
| BIKE-007 | Objectif puissance/cadence par segment | PLANNED |  |  |  |  |
| BIKE-008 | Comparaison d'ascensions historiques | PLANNED |  |  |  |  |
| BIKE-009 | Conseils de développement/rapport si transmission compatible | PLANNED |  |  |  |  |
| BIKE-010 | Données Di2/AXS lorsque l'API/protocole est autorisé et disponible | PLANNED |  |  |  |  |
| BIKE-011 | Radar arrière : événements, nombre de cibles et niveau si fourni par le radar | PLANNED |  |  |  |  |
| BIKE-012 | État de lumière et batterie d'accessoires | PLANNED |  |  |  |  |
| BIKE-013 | TPMS pression pneu si capteur compatible | PLANNED |  |  |  |  |
| BIKE-014 | Batterie e-bike, mode d'assistance et autonomie si accessible | PLANNED |  |  |  |  |
| BIKE-015 | Rappels d'entretien et kilométrage de composants | PLANNED |  |  |  |  |
| BIKE-016 | Profils route, gravel, VTT, cyclocross et e-bike | PLANNED |  |  |  |  |
| BIKE-017 | Détection/alerte de perte d'un capteur ou radar | PLANNED |  |  |  |  |
| BIKE-018 | Mode entraînement indoor via FTMS ou connecteur | PARTIAL | `src/glasses/sensors.py:indoor_bike` | `test_glasses_engines.py` | SIMULATED | FTMS indoor bike decode; control not implemented |

## Ghost Competition

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| GHOST-001 | Ghost d'une sortie précédente | PARTIAL | `src/glasses/sport.py:Ghost` | `test_glasses_engines.py` | SIMULATED | engine done; session storage/import next |
| GHOST-002 | Ghost du meilleur temps personnel | PARTIAL | `src/glasses/sport.py:Ghost` | `test_glasses_engines.py` | SIMULATED | same |
| GHOST-003 | Ghost d'un objectif cible | PARTIAL | `src/glasses/sport.py:Ghost` | `test_glasses_engines.py` | SIMULATED | a constant-pace track works as a target |
| GHOST-004 | Ghost par parcours, segment, montée ou tour | PLANNED |  |  |  |  |
| GHOST-005 | Affichage avance/retard en temps et distance | EXISTING | `src/glasses/sport.py:Ghost.compare, GhostScreen` | `test_glasses_engines.py` | SIMULATED |  |
| GHOST-006 | Projection du résultat final | EXISTING | `src/glasses/sport.py:Ghost.compare` | `test_glasses_engines.py` | SIMULATED | assumes the ghost pace for the rest |
| GHOST-007 | Plusieurs adversaires virtuels nommés | PLANNED |  |  |  |  |
| GHOST-008 | Modes de difficulté et rythme personnalisé | PLANNED |  |  |  |  |
| GHOST-009 | Import d'une activité autorisée d'un ami | PLANNED |  |  |  |  |
| GHOST-010 | Défi de groupe à distance, avec consentement au partage | PLANNED |  |  |  |  |
| GHOST-011 | Comparaison segment par segment | PLANNED |  |  |  |  |
| GHOST-012 | Journal de défi et résultat final | PLANNED |  |  |  |  |

## Sensors

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| SENSOR-001 | Découverte/appairage et nom convivial | PLANNED |  |  |  |  |
| SENSOR-002 | Association d'un capteur à un profil | PLANNED |  |  |  |  |
| SENSOR-003 | Connexion multi-capteurs selon les limites système | PLANNED |  |  |  |  |
| SENSOR-004 | Reconnexion avec backoff et timeout | PLANNED |  |  |  |  |
| SENSOR-005 | Niveau batterie si exposé | PLANNED |  |  |  |  |
| SENSOR-006 | RSSI et état de lien | PLANNED |  |  |  |  |
| SENSOR-007 | Détection de perte de données et valeurs périmées | EXISTING | `src/glasses/metrics.py:Store (TTL)` | `test_glasses_engines.py` | SIMULATED |  |
| SENSOR-008 | Sélection de source prioritaire par métrique | EXISTING | `src/glasses/metrics.py:Store (source priority)` | `test_glasses_engines.py` | SIMULATED |  |
| SENSOR-009 | Fusion de sources avec provenance préservée | PARTIAL | `src/glasses/metrics.py` | `test_glasses_engines.py` | SIMULATED | provenance kept; no fusion |
| SENSOR-010 | Diagnostic et journal d'erreur | PLANNED |  |  |  |  |
| SENSOR-011 | Filtrage des valeurs impossibles / aberrantes | EXISTING | `src/glasses/metrics.py:validate` | `test_glasses_engines.py` | SIMULATED |  |
| SENSOR-012 | Simulateurs de périphériques pour tests | PARTIAL | `src/glasses/nav.py:simulate` | `test_glasses_engines.py` | SIMULATED | GPS simulation; BLE sensor simulators planned |

## AI coach

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| AI-001 | Coach contextuel running | PLANNED |  |  |  |  |
| AI-002 | Coach cyclisme | PLANNED |  |  |  |  |
| AI-003 | Coach trail/randonnée | PLANNED |  |  |  |  |
| AI-004 | Analyse d'allure/puissance/cadence | PLANNED |  |  |  |  |
| AI-005 | Conseil de rythme et de récupération à partir de seuils utilisateur | PLANNED |  |  |  |  |
| AI-006 | Analyse post-séance | PLANNED |  |  |  |  |
| AI-007 | Génération d'un programme d'entraînement personnalisé | PLANNED |  |  |  |  |
| AI-008 | Ajustement de programme selon l'historique et la disponibilité | PLANNED |  |  |  |  |
| AI-009 | Questions/réponses sur les métriques actuelles | PLANNED |  |  |  |  |
| AI-010 | Récapitulatif vocal optionnel | PLANNED |  |  |  |  |
| AI-011 | Modèle local ou distant selon configuration et consentement | PLANNED |  |  |  |  |
| AI-012 | Mode hors ligne pour commandes et règles essentielles | PLANNED |  |  |  |  |
| AI-013 | Journal des conseils, raisons, données utilisées et version du modèle | PLANNED |  |  |  |  |

## Rules

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| RULE-001 | Déclencheur sur seuil de métrique | PLANNED |  |  |  |  |
| RULE-002 | Déclencheur GPS/géofence | PLANNED |  |  |  |  |
| RULE-003 | Déclencheur horaire/durée | PLANNED |  |  |  |  |
| RULE-004 | Déclencheur événement capteur | PLANNED |  |  |  |  |
| RULE-005 | Conditions multiples et temporisation | PLANNED |  |  |  |  |
| RULE-006 | Priorité et suppression de doublons | PLANNED |  |  |  |  |
| RULE-007 | Pause/résumé/désactivation de règles | PLANNED |  |  |  |  |
| RULE-008 | Historique d'exécution et explication | PLANNED |  |  |  |  |

## Voice

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| VOICE-001 | Activation du micro téléphone par commande/contrôle explicite | PLANNED |  |  |  |  |
| VOICE-002 | Push-to-talk via Companion | EXISTING | `Companion push-to-talk (MainActivity)` |  | REAL_HARDWARE: phone | verified earlier on the phone |
| VOICE-003 | Détection de fin de parole/VAD avec indicateur visible | PLANNED |  |  |  |  |
| VOICE-004 | Reconnaissance vocale français/anglais | EXISTING | `src/ai/stt_local.py, openbridge-intent model` | `test_glasses.py` | EMULATOR | FR/EN; see docs/AI_TRAINING.md |
| VOICE-005 | Commandes naturelles pour métriques, pages et navigation | PARTIAL | `src/glasses/hub.py:voice_action` | `test_glasses.py` | EMULATOR | TV and vacuum today; metrics and pages planned |
| VOICE-006 | Confirmation des opérations sensibles sur le téléphone ou un contrôle dédié | PLANNED |  |  |  |  |
| VOICE-007 | Réponse courte textuelle sur HUD | EXISTING | `src/glasses/ui.py:VoiceScreen` | `test_glasses.py` | EMULATOR |  |
| VOICE-008 | Synthèse vocale via casque/écouteurs externes | PLANNED |  |  |  |  |
| VOICE-009 | Intégration microphone Bluetooth externe si OS compatible | PLANNED |  |  |  |  |
| VOICE-010 | Sous-titres/traduction à la demande | PLANNED |  |  |  |  |
| VOICE-011 | Mode hors ligne si moteur local disponible | PLANNED |  |  |  |  |
| VOICE-012 | Indicateur micro actif et arrêt immédiat | PARTIAL | `Companion voice orb` |  |  | phone side only |
| VOICE-013 | Pas d'enregistrement permanent par défaut | EXISTING | `Companion: clip sent on demand only` |  |  |  |
| VOICE-014 | Suppression des buffers audio après traitement selon politique de conservation | PLANNED |  |  |  |  |

## Phone as sensor proxy

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| PHONE-001 | GPS/GNSS et vitesse | PLANNED |  |  |  |  |
| PHONE-002 | Accéléromètre/gyroscope pour événements de mouvement prudents | PLANNED |  |  |  |  |
| PHONE-003 | Baromètre lorsque disponible | PLANNED |  |  |  |  |
| PHONE-004 | Microphone à la demande | EXISTING | `Companion AudioRecord on demand` |  | REAL_HARDWARE: phone |  |
| PHONE-005 | Caméra à la demande, après déclenchement/consentement explicite | PLANNED |  |  |  |  |
| PHONE-006 | Analyse visuelle ponctuelle avec affichage d'un résumé court | PLANNED |  |  |  |  |
| PHONE-007 | État batterie, réseau et GPS | PLANNED |  |  |  |  |
| PHONE-008 | Mode brassard | PLANNED |  |  |  |  |
| PHONE-009 | Mode support guidon | PLANNED |  |  |  |  |
| PHONE-010 | Mode poche/sac avec limites de capteurs documentées | PLANNED |  |  |  |  |
| PHONE-011 | Contrôle à distance par boutons Companion | PARTIAL | `remote controls; glasses buttons planned` |  |  |  |
| PHONE-012 | Télécommande Bluetooth externe | PLANNED |  |  |  |  |
| PHONE-013 | Gestion de l'exécution en arrière-plan par plateforme | PLANNED |  |  |  |  |
| PHONE-014 | Mode dégradé sans Internet | PLANNED |  |  |  |  |

## Safety and SOS

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| SAFE-001 | Partage de position avec contacts désignés et durée limitée | PLANNED |  |  |  |  |
| SAFE-002 | Parcours prévu et heure de retour déclarée | PLANNED |  |  |  |  |
| SAFE-003 | Alerte de retard de sortie configurable | PLANNED |  |  |  |  |
| SAFE-004 | Chute potentielle détectée par profil de portage, avec confirmation/annulation | BLOCKED |  |  |  | needs legal / sector validation before any implementation (spec §5.12, §5.19) |
| SAFE-005 | Compte à rebours avant notification d'urgence | BLOCKED |  |  |  | needs legal / sector validation before any implementation (spec §5.12, §5.19) |
| SAFE-006 | SOS manuel via Companion ou télécommande dédiée | BLOCKED |  |  |  | needs legal / sector validation before any implementation (spec §5.12, §5.19) |
| SAFE-007 | Transmission de position et heure de l'événement | BLOCKED |  |  |  | needs legal / sector validation before any implementation (spec §5.12, §5.19) |
| SAFE-008 | Alerte de perte GPS/réseau/batterie | PLANNED |  |  |  |  |
| SAFE-009 | Perte de signal radar/capteur | PLANNED |  |  |  |  |
| SAFE-010 | Group tracking avec consentement mutuel | PLANNED |  |  |  |  |
| SAFE-011 | Alerte de météo dangereuse à partir d'une source qualifiée | PLANNED |  |  |  |  |
| SAFE-012 | Mode interface minimaliste en situation d'urgence | PLANNED |  |  |  |  |

## Weather

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| ENV-001 | Température, ressenti et humidité | PLANNED |  |  |  |  |
| ENV-002 | Pluie imminente et intensité | PLANNED |  |  |  |  |
| ENV-003 | Vent, direction, rafales et composante face/arrière/latérale | PLANNED |  |  |  |  |
| ENV-004 | Risque d'orage, neige, verglas ou brouillard si source disponible | PLANNED |  |  |  |  |
| ENV-005 | UV et durée de lumière restante | PLANNED |  |  |  |  |
| ENV-006 | Lever/coucher du soleil | PLANNED |  |  |  |  |
| ENV-007 | Qualité de l'air et particules fines si source disponible | PLANNED |  |  |  |  |
| ENV-008 | Pollen/allergènes si source disponible | PLANNED |  |  |  |  |
| ENV-009 | Météo le long du parcours et à destination | PLANNED |  |  |  |  |
| ENV-010 | Ajustement indicatif des recommandations sportives selon conditions | PLANNED |  |  |  |  |

## Recovery

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| HEALTH-001 | Import du sommeil depuis source compatible | PLANNED |  |  |  |  |
| HEALTH-002 | Import HRV si disponible | PLANNED |  |  |  |  |
| HEALTH-003 | Import fréquence cardiaque de repos | PLANNED |  |  |  |  |
| HEALTH-004 | Charge d'entraînement historique | PLANNED |  |  |  |  |
| HEALTH-005 | Estimation de récupération, non médicale | PLANNED |  |  |  |  |
| HEALTH-006 | Indicateur de disponibilité physique explicable | PLANNED |  |  |  |  |
| HEALTH-007 | Suivi d'hydratation et rappels configurés | PLANNED |  |  |  |  |
| HEALTH-008 | Plan de ravitaillement/glucides choisi par l'utilisateur | PLANNED |  |  |  |  |
| HEALTH-009 | Rapport de progression | PLANNED |  |  |  |  |
| HEALTH-010 | Export et suppression des données | PLANNED |  |  |  |  |

## Integrations

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| INT-001 | Import/export GPX/FIT/TCX/CSV selon le format et les droits | PLANNED |  |  |  |  |
| INT-002 | Import entraînements programmés | PLANNED |  |  |  |  |
| INT-003 | Import historique d'activités autorisées | PLANNED |  |  |  |  |
| INT-004 | Synchronisation records et objectifs | PLANNED |  |  |  |  |
| INT-005 | Intégration segments/records lorsqu'autorisé | PLANNED |  |  |  |  |
| INT-006 | Connecteurs cartographiques interchangeables | PLANNED |  |  |  |  |
| INT-007 | Connecteurs météo interchangeables | PLANNED |  |  |  |  |
| INT-008 | Gestion de tokens et révocation | PLANNED |  |  |  |  |
| INT-009 | Quotas, indisponibilités et cache | PLANNED |  |  |  |  |
| INT-010 | Afficher la provenance de chaque donnée | PLANNED |  |  |  |  |

## PC and simulators

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| PC-001 | Contrôle ActiveLook depuis Windows BLE | PARTIAL | `src/glasses/hub.py:BleLink` |  |  | HARDWARE_REQUIRED |
| PC-002 | Relais PC → Companion → lunettes | PLANNED |  |  |  |  |
| PC-003 | API locale sécurisée pour applications tierces | PLANNED |  |  |  |  |
| PC-004 | Télémétrie serveur/PC : CPU, RAM, GPU, stockage, réseau et températures exposées | PLANNED |  |  |  |  |
| PC-005 | Alertes GitHub/CI/CD, build, test, déploiement et erreurs | PLANNED |  |  |  |  |
| PC-006 | Notifications de services et conteneurs | PLANNED |  |  |  |  |
| PC-007 | Connecteur Zwift/FTMS | PLANNED |  |  |  |  |
| PC-008 | Connecteurs sim racing (selon interfaces autorisées) : Assetto Corsa, ACC, iRacing, rFactor 2, Automobilista 2, LMU, SimHub | PLANNED |  |  |  |  |
| PC-009 | Connecteurs simulateur de vol pour usage simulation/sol : MSFS, X-Plane | PLANNED |  |  |  |  |
| PC-010 | Alertes OBS/streaming/Discord et notifications de jeu | PLANNED |  |  |  |  |
| PC-011 | Enregistrement/relecture de sessions HUD | EXISTING | `HUD Studio sessions` | `test_hud_studio.py` | EMULATOR |  |
| PC-012 | Mode diagnostic développeur | PLANNED |  |  |  |  |

## Other sports

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| SPORT-001 | Randonnée | PLANNED |  |  |  |  |
| SPORT-002 | Golf | PLANNED |  |  |  |  |
| SPORT-003 | Aviron | PLANNED |  |  |  |  |
| SPORT-004 | Ski de fond et ski alpin (données adaptées et sécurité) | PLANNED |  |  |  |  |
| SPORT-005 | Kayak/paddle | PLANNED |  |  |  |  |
| SPORT-006 | Voile et navigation de loisir | PLANNED |  |  |  |  |
| SPORT-007 | Roller/patinage | PLANNED |  |  |  |  |
| SPORT-008 | Triathlon/duathlon | PLANNED |  |  |  |  |
| SPORT-009 | Fitness/rameur/tapis | PLANNED |  |  |  |  |
| SPORT-010 | VTT/gravel/BMX/cyclocross | PLANNED |  |  |  |  |

## Golf

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| GOLF-001 | Parcours et trou actuel | PLANNED |  |  |  |  |
| GOLF-002 | Distance entrée/centre/fond du green | PLANNED |  |  |  |  |
| GOLF-003 | Distance obstacles/bunkers/eau si cartographiés | PLANNED |  |  |  |  |
| GOLF-004 | Score/par/nombre de coups | PLANNED |  |  |  |  |
| GOLF-005 | Historique de parties | PLANNED |  |  |  |  |
| GOLF-006 | Distance habituelle par club issue de mesures utilisateur | PLANNED |  |  |  |  |
| GOLF-007 | Analyse de précision et tendances | PLANNED |  |  |  |  |
| GOLF-008 | Météo du parcours | PLANNED |  |  |  |  |
| GOLF-009 | Import parcours et mise à jour cartographique | PLANNED |  |  |  |  |
| GOLF-010 | Mode tournoi conforme aux règles applicables ; fonctions non conformes désactivées en compétition officielle | BLOCKED |  |  |  | needs legal / sector validation before any implementation (spec §5.12, §5.19) |

## Professional

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| PRO-001 | Notifications métier et consignes courtes | PLANNED |  |  |  |  |
| PRO-002 | Pick-by-location pour entrepôt, depuis WMS autorisé | PLANNED |  |  |  |  |
| PRO-003 | Référence, emplacement, quantité et progression de prélèvement | PLANNED |  |  |  |  |
| PRO-004 | Checklist de maintenance | PLANNED |  |  |  |  |
| PRO-005 | État machine et alarme depuis API industrielle validée | BLOCKED |  |  |  | needs legal / sector validation before any implementation (spec §5.12, §5.19) |
| PRO-006 | Étapes de procédure courtes | PLANNED |  |  |  |  |
| PRO-007 | Aide-mémoire et minuteur | PLANNED |  |  |  |  |
| PRO-008 | Calendrier et prochaine tâche | PLANNED |  |  |  |  |
| PRO-009 | Traduction de consignes | PLANNED |  |  |  |  |
| PRO-010 | Mode formation et suivi d'étape | PLANNED |  |  |  |  |

## Community

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| SOC-001 | Défis personnels quotidiens/hebdomadaires/mensuels | PLANNED |  |  |  |  |
| SOC-002 | Défis de distance, durée, dénivelé, cadence ou puissance | PLANNED |  |  |  |  |
| SOC-003 | Clubs et groupes | PLANNED |  |  |  |  |
| SOC-004 | Ghost partagé depuis une activité autorisée | PLANNED |  |  |  |  |
| SOC-005 | Suivi de position temporaire en groupe | PLANNED |  |  |  |  |
| SOC-006 | Classement par catégorie et période | PLANNED |  |  |  |  |
| SOC-007 | Événements et calendrier | PLANNED |  |  |  |  |
| SOC-008 | Rendez-vous et point de rassemblement | PLANNED |  |  |  |  |
| SOC-009 | Notifications d'événements et résultats | PLANNED |  |  |  |  |
| SOC-010 | Contrôles de confidentialité, blocage et retrait de partage | PLANNED |  |  |  |  |

## Privacy

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| PRIV-001 | Consentement séparé GPS, micro, caméra, santé, notifications et partage | PARTIAL | `Companion notification access, mic permission` |  |  | GPS/health consent with those features |
| PRIV-002 | Indicateur visible lorsque micro/caméra sont actifs | PLANNED |  |  |  |  |
| PRIV-003 | Arrêt immédiat des captures et flux | PLANNED |  |  |  |  |
| PRIV-004 | Aucun enregistrement audio permanent par défaut | EXISTING | `Companion + stt_local` |  |  |  |
| PRIV-005 | Données minimisées et pseudonymisées dans le Device Fabric | PLANNED |  |  |  |  |
| PRIV-006 | Conservation configurable et suppression | PLANNED |  |  |  |  |
| PRIV-007 | Export des données utilisateur | PLANNED |  |  |  |  |
| PRIV-008 | Jetons API dans un coffre/stockage sécurisé compatible avec la plateforme | PLANNED |  |  |  |  |
| PRIV-009 | Journaux sans secrets, tokens, numéros de série bruts ni coordonnées non nécessaires | PLANNED |  |  |  |  |
| PRIV-010 | Contrôle d'accès par module et connecteur | PLANNED |  |  |  |  |
| PRIV-011 | Revue de conformité RGPD et politique de confidentialité avant mise en production | PLANNED |  |  |  |  |

## Extensions

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| EXT-001 | Manifeste de plugin versionné | PLANNED |  |  |  |  |
| EXT-002 | Déclaration des sources de données et permissions requises | PLANNED |  |  |  |  |
| EXT-003 | Contrat d'événements typés | PLANNED |  |  |  |  |
| EXT-004 | Widgets HUD déclaratifs | PLANNED |  |  |  |  |
| EXT-005 | Connecteurs de capteurs | PLANNED |  |  |  |  |
| EXT-006 | Thèmes et profils importables | PLANNED |  |  |  |  |
| EXT-007 | Signature et provenance des extensions | PLANNED |  |  |  |  |
| EXT-008 | Validation, sandbox et limites d'exécution | PLANNED |  |  |  |  |
| EXT-009 | Compatibilité firmware/SDK déclarée | PLANNED |  |  |  |  |
| EXT-010 | Gestion de version, retrait et rollback | PLANNED |  |  |  |  |

## OpenBridge home on the glasses

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| OBH-001 | Messages from the phone on the glasses (Discord, Telegram, SMS, Messages) | EXISTING | `src/glasses/notifications.py, Companion NotifListener` | `test_glasses.py` | EMULATOR | Companion side to test on the phone |
| OBH-002 | TV remote: volume, apps, D-pad, play/pause, sleep/wake | EXISTING | `src/glasses/ui.py:TVHub, hub.run` | `test_glasses.py` | EMULATOR | not run on the TV yet (no ADB link at test time) |
| OBH-003 | Robot vacuum: start, pause, dock, find | EXISTING | `src/glasses/ui.py:VacuumScreen` | `test_glasses.py` | EMULATOR | not run on the robot yet |
| OBH-004 | Voice from the phone mic, shown on the glasses | EXISTING | `src/glasses/hub.py:voice` | `test_glasses.py` | EMULATOR |  |
| OBH-005 | One-time owner grant for glasses actions | EXISTING | `src/glasses/hub.py:grant_covers` | `test_glasses.py` | SIMULATED |  |
| OBH-006 | Transport: MTU writes, flow control, newest screen wins, bounded queue | EXISTING | `src/glasses/transport.py` | `test_glasses_engines.py` | SIMULATED | flow status byte values to confirm on ENGO 3 |
| OBH-007 | BLE sport sensor decoders (HR, RSC, CSC, power, FTMS bike, battery) | EXISTING | `src/glasses/sensors.py` | `test_glasses_engines.py` | SIMULATED | pairing and live connection planned |

## Français / English

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| I18N-001 | Language selector in the Companion: Auto / Français / English | EXISTING | `Companion L.java, MainActivity` |  |  | build verified; to try on the phone |
| I18N-002 | Glasses language follows the app, with an optional override | EXISTING | `src/glasses/i18n.py, glasses set --lang/--hud-lang` | `test_glasses_engines.py` | SIMULATED |  |
| I18N-003 | FR/EN locale files with a missing-key test | EXISTING | `src/glasses/locales/*.json` | `test_glasses_engines.py` | SIMULATED |  |
| I18N-004 | Language selector in the PC web interface | PLANNED |  |  |  | the PC web UI is English today |

## HUD Studio feature catalogue F01-F38

| ID | Feature | Status | Code | Tests | Evidence | Limits |
|---|---|---|---|---|---|---|
| F01 | Spatial Device Radar | EXISTING | `src/adapters/hud_features.py:spatial_radar` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F02 | Eyes-On-Target Receipt | EXISTING | `src/adapters/hud_features.py:eyes_on_target` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F03 | Two-Phase Abort Gate | EXISTING | `src/adapters/hud_features.py:two_phase_countdown` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F04 | Peripheral Telemetry | EXISTING | `src/adapters/hud_features.py:peripheral_telemetry` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F05 | Workshop Prompter | EXISTING | `src/adapters/hud_features.py:workflow_prompter` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F06 | Doorbell Subtitles | EXISTING | `src/adapters/hud_features.py:doorbell_subtitles` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F07 | AR Compass Wayfinder | EXISTING | `src/adapters/hud_features.py:compass_wayfinder` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F08 | Intrusion Shield | EXISTING | `src/adapters/hud_features.py:security_shield` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F09 | Bio-Adaptive Pacer | EXISTING | `src/adapters/hud_features.py:bio_pacer` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F10 | Touchless Media Remote | EXISTING | `src/adapters/hud_features.py:media_remote` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F11 | TempleTap Morse Input | EXISTING | `src/adapters/hud_features.py:silent_morse_input` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F12 | Speech Teleprompter | EXISTING | `src/adapters/hud_features.py:speech_teleprompter` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F13 | Energy Ghost Heatmap | EXISTING | `src/adapters/hud_features.py:spatial_energy_heatmap` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F14 | Vector Runner Arcade | EXISTING | `src/adapters/hud_features.py:arcade_runner` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F15 | Collision Sentry | EXISTING | `src/adapters/hud_features.py:collision_sentry` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F16 | Executive Brief | EXISTING | `src/adapters/hud_features.py:executive_briefing` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F17 | Biofeedback Stress | EXISTING | `src/adapters/hud_features.py:biofeedback_stress` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F18 | AR Stud & Inclinometer | EXISTING | `src/adapters/hud_features.py:diy_ar_stud_level` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F19 | CPR & Triage Pacer | BLOCKED | `src/adapters/hud_features.py:first_responder_cpr` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | concept demo with sample data; safety-critical use out of consumer scope |
| F20 | Directional Subtitles | EXISTING | `src/adapters/hud_features.py:directional_subtitles` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F21 | UAV Avionics VLOS | EXISTING | `src/adapters/hud_features.py:uav_avionics` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F22 | Stealth RF Sentry | EXISTING | `src/adapters/hud_features.py:stealth_rf_sentry` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F23 | Thermal Arc-Flash | BLOCKED | `src/adapters/hud_features.py:thermal_arc_flash` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | concept demo with sample data; safety-critical use out of consumer scope |
| F24 | Allergen Scanner | EXISTING | `src/adapters/hud_features.py:allergen_nutrition` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F25 | Tactical Marine HUD | EXISTING | `src/adapters/hud_features.py:tactical_marine` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F26 | Etiquette Whisperer | EXISTING | `src/adapters/hud_features.py:multilingual_whisperer` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F27 | Driver Vigilance | BLOCKED | `src/adapters/hud_features.py:driver_vigilance` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | concept demo with sample data; safety-critical use out of consumer scope |
| F28 | Pick-by-Vision | EXISTING | `src/adapters/hud_features.py:warehouse_pick` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F29 | Avalanche SAR 457kHz | BLOCKED | `src/adapters/hud_features.py:avalanche_sar` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | concept demo with sample data; safety-critical use out of consumer scope |
| F30 | Circadian Chrono | EXISTING | `src/adapters/hud_features.py:circadian_chrono` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F31 | Firefighter Mayday | BLOCKED | `src/adapters/hud_features.py:firefighter_mayday` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | concept demo with sample data; safety-critical use out of consumer scope |
| F32 | Precision Ballistics | BLOCKED | `src/adapters/hud_features.py:ballistic_drop` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | concept demo with sample data; safety-critical use out of consumer scope |
| F33 | Sterile Surgical HUD | BLOCKED | `src/adapters/hud_features.py:surgical_vitals` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | concept demo with sample data; safety-critical use out of consumer scope |
| F34 | Low-Vision Echo-Radar | BLOCKED | `src/adapters/hud_features.py:low_vision_echonav` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | concept demo with sample data; safety-critical use out of consumer scope |
| F35 | Neural Voice Co-Pilot | EXISTING | `src/adapters/hud_features.py:neural_voice_assistant` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F36 | Multimodal Vision Proxy | EXISTING | `src/adapters/hud_features.py:multimodal_vision_hud` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F37 | Ambient IoT Matrix | EXISTING | `src/adapters/hud_features.py:ambient_iot_matrix` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
| F38 | Spatial Translation | EXISTING | `src/adapters/hud_features.py:neural_translation_stream` | `test_engo_killer_features.py`<br>`test_hud_studio.py` | EMULATOR | demo screen with sample data, not wired to live sources |
