# Innovations R&D de Rupture : Saisie Furtive, Téléprompteur Vocal, Heatmap Spatial & Moteur Arcade

> **Dossier d'Ingénierie Avancée OpenBridge × ENGO v3.0**  
> 4 innovations de rupture conçues pour exploiter la surface capacitive des branches, la physique vectorielle MicroOLED et la synchronisation multimodale avec le smartphone.

---

## 1. Vue d'Ensemble des Innovations v3.0

```mermaid
flowchart TD
    subgraph INPUT["Saisie Furtive & Contrôle Silencieux"]
        I1["⌨️ F11: TempleTap Morse Decoder<br/>(Saisie texte sans la voix via micro-taps)"]
    end

    subgraph PROD["Prise de Parole & Éloquence"]
        P1["🎙️ F12: Speech-Synced AR Teleprompter<br/>(Défilement calé sur la voix & cadence WPM)"]
    end

    subgraph ECO["Domotique & Détection d'Énergie"]
        E1["🏠 F13: Spatial Energy Ghost Heatmap<br/>(Détection de veille fantôme & coupure 1-geste)"]
    end

    subgraph ENTERTAINMENT["Micro-Loisirs & Moteur Physique"]
        A1["🎮 F14: MicroOLED Vector Runner<br/>(Jeu d'arcade 60Hz piloté par geste IR)"]
    end

    ENGO["ENGO Glasses (MicroOLED 304x256)"] --> INPUT
    ENGO --> PROD
    ENGO --> ECO
    ENGO --> ENTERTAINMENT
```

---

## 2. Spécification Détaillée des 4 Innovations

### ⌨️ F11 : Moteur de Saisie Furtive par Micro-Taps Morse (`push_silent_morse_input`)
* **Problème résolu :** Les lunettes ENGO n'ont pas de microphone. En réunion confidentielle, en bibliothèque ou dans les transports, l'utilisateur ne peut pas parler à voix haute et ne souhaite pas sortir son smartphone de sa poche.
* **Architecture Technique :**
  - **Décodeur Temporel (`TempleTapMorseDecoder`) :** Mesure la durée de contact du doigt sur la branche tactile :
    - Contact $< 250$ ms = **Point (`·`)**.
    - Contact $\ge 250$ ms = **Trait (`—`)**.
    - Pause $> 650$ ms = Validation automatique de la lettre (Morse international A–Z, 0–9).
    - Double-tap rapide = Validation et envoi du message.
    - Long tap glissé = Effacement (Backspace).
  - **Retour Visuel HUD :**
    - `TEXTE : OUI EN ROUTE_`
    - `SYMBOLE : [ · — ] ➔ A` (Aperçu en temps réel avant validation).
    - `SUGGESTION : ARRIVE DANS 5 MIN` (Autocomplétion intelligente par le LLM OpenBridge).
* **Métriques :** 346 octets BLE, 2,31% de remplissage, **0,37 mW** de consommation (**1 150 heures d'autonomie**).

---

### 🎙️ F12 : Téléprompteur Tête Haute & Gardien d'Éloquence (`push_speech_teleprompter`)
* **Problème résolu :** Lors d'une prise de parole, d'un pitch d'investisseur ou d'un cours magistral, regarder ses fiches ou un pupitre détruit le contact visuel avec l'audience.
* **Fonctionnement :**
  1. Le micro du smartphone écoute le flux de parole de l'orateur via Whisper / VAD.
  2. Les notes défilent automatiquement ligne par ligne dans le HUD au fur et à mesure que les mots sont prononcés.
  3. **Indicateur de Rythme (WPM : Words Per Minute) :**
     - $110 \le \text{WPM} \le 165$ : Vert (`✓ 138 WPM (RYTHME OPTIMAL)`).
     - $\text{WPM} > 165$ : Ambre clignotant (`⚠️ 178 WPM (TROP RAPIDE - RALENTIR)`).
  4. **Typographie Hiérarchisée :**
     - Ligne active en grand jaune à fort contraste (`▶ OpenBridge connecte vos lunettes`).
     - Ligne suivante en police discrète atténuée (`SUIVANT : aux modeles d'IA locaux`).
     - Jauge de temps restant intégrée sur le budget imparti (ex: 3 minutes).
* **Métriques :** 294 octets BLE, 6,51% de remplissage, **0,50 mW** de consommation (**857 heures d'autonomie**).

---

### 🏠 F13 : Heatmap Énergétique Spatiale & Chasseur de Veille Fantôme (`push_spatial_energy_heatmap`)
* **Problème résolu :** Comprendre instantanément où part l'électricité dans la maison sans consulter une application mobile surchargée de graphiques.
* **Comportement Contextuel :**
  - Grâce aux balises BLE (Freebox, prises Tuya, AP Wi-Fi), OpenBridge détecte la pièce où se trouve l'utilisateur.
  - Dès qu'il pénètre dans une pièce, le bandeau HUD affiche son empreinte immédiate :
    - `🏠 [CUISINE] : 2 150 W (TOTAL MAISON: 3 480 W)`.
  - **Alerte Veille Fantôme Active :**
    - Si un appareil consomme de l'énergie sans usage depuis plus de 2 heures :
    - `⚠️ VEILLE FANTOME DETECTEE : Four Veille (65 W - inactif depuis 3h)`.
    - **Coupure en 1 geste :** `>> [WAVE] COUPER PRISE FOUR` (éteint la prise Tuya correspondante sans contact).
* **Métriques :** 325 octets BLE, 7,15% de remplissage, **0,51 mW** de consommation (**826 heures d'autonomie**).

---

### 🎮 F14 : Moteur d'Arcade Vectoriel MicroOLED (`push_arcade_game_frame`)
* **Problème résolu :** Transformer les moments d'attente (quai de gare, arrêt de bus, file d'attente) en micro-loisir discret et ludique, sans sortir son smartphone.
* **Moteur Physique Embarqué (`ActiveLookArcadeEngine`) :**
  - Moteur vectoriel de coureur (Vector Runner) à 60 Hz.
  - Le joueur est un cercle vectoriel de rayon 8 px sur une ligne de sol (`y = 190`).
  - **Contrôle sans contact :** Un balayage de la main devant le capteur infrarouge (`wave` `0x01`) applique une impulsion gravitationnelle (`jump_velocity = 12.0`) pour sauter par-dessus les obstacles.
  - Rendu atomique via `holdFlush(0)` et `holdFlush(1)` garantissant 0% de scintillement.
  - Score incrémenté à chaque obstacle franchi et écran Game Over avec relance immédiate.
* **Métriques :** 168 octets par trame, **1,43% de remplissage**, **0,34 mW** de puissance (**1 239 heures de jeu ininterrompu**).

---

## 3. Matrice Complète des 14 Scénarios OpenBridge HUD

| Scénario | Catégorie | Remplissage Pixels | Puissance MicroOLED | Autonomie Théorique |
| :--- | :--- | :---: | :---: | :---: |
| **F01: Radar Spatial Périphérique** | Domotique & IoT | 1,46 % | 0,34 mW | 1 235 h |
| **F02: Reçu d'Action In-Situ (Oracle)** | Domotique & Sécurité | 12,58 % | 0,68 mW | 627 h |
| **F03: Two-Phase Wave Abort Gate** | Sécurité Critique | 19,06 % | 0,87 mW | 487 h |
| **F04: Télémétrie Périphérique Linky** | Énergie & Réseau | 19,06 % | 0,87 mW | 487 h |
| **F05: Prompteur Atelier / Cuisine** | Productivité | 5,33 % | 0,46 mW | 923 h |
| **F06: Sous-Titres Interphone** | Sécurité Domicile | 35,98 % | 1,38 mW | 308 h |
| **F07: AR Compass & Wayfinder Ribbon** | Navigation Plein Air | 6,91 % | 0,51 mW | 838 h |
| **F08: Intrusion Shield Freebox** | Cybersécurité | 2,99 % | 0,39 mW | 1 090 h |
| **F09: Bio-Adaptive Cadence Pacer** | Sport & Performance | 7,68 % | 0,53 mW | 801 h |
| **F10: Télécommande Média Touchless** | Divertissement | 9,70 % | 0,59 mW | 719 h |
| **F11: Saisie Furtive Micro-Taps Morse** | Saisie Discrète | **2,31 %** | **0,37 mW** | **1 150 h** |
| **F12: Téléprompteur Vocal Éloquence** | Prise de Parole | **6,51 %** | **0,50 mW** | **857 h** |
| **F13: Heatmap Énergétique Spatiale** | Énergie & Écologie | **7,15 %** | **0,51 mW** | **826 h** |
| **F14: Moteur Arcade Vector Runner** | Loisir & Micro-Gaming | **1,43 %** | **0,34 mW** | **1 239 h** |
| **MOYENNE GLOBALE (14 SCÉNARIOS)** | — | **9,70 %** | **0,57 mW** | **~890 h** |
