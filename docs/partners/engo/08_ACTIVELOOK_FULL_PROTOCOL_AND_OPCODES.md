# ActiveLook Low-Level Binary Protocol & Complete Opcode Reference

> **Spécification Officielle ActiveLook® v4.x**  
> Utilisé par : ENGO 1, ENGO 2, ENGO 3, ENGO 3 Titanium, Julbo EVAD-1, Cosmo Connected.  
> Architecture SoC : Dialog Semiconductor / Renesas DA1469x ARM Cortex-M4 + MicroOLED 304×256.

---

## 1. Architecture BLE GATT & Services

ActiveLook expose un service GATT personnalisé propriétaire et des services standards :

| Service / Caractéristique | UUID | Propriétés | Rôle / Description |
| :--- | :--- | :--- | :--- |
| **ActiveLook Service** | `0783B03E-8535-B5A0-7140-A304D2495CB7` | — | Interface de commande principale |
| **Server TX** | `0783B03E-8535-B5A0-7140-A304D2495CB8` | `Notify` | Réponses aux requêtes, métadonnées, état |
| **Control / FlowCtrl** | `0783B03E-8535-B5A0-7140-A304D2495CB9` | `Notify` | Contrôle de flux (`0x01`=OK, `0x02`=Pause 75%) & Erreurs |
| **Server RX** | `0783B03E-8535-B5A0-7140-A304D2495CBA` | `Write`, `WriteWithoutResponse` | Flux d'écriture binaire (Central ➔ Lunettes) |
| **Gesture Event** | `0783B03E-8535-B5A0-7140-A304D2495CBB` | `Notify` | Notifie `0x01` lors d'un balayage optique IR |
| **Touch Event** | `0783B03E-8535-B5A0-7140-A304D2495CBC` | `Notify` | Notifie `0x01` lors d'un appui tactile branche |
| **Battery Service** | `0000180F-0000-1000-8000-00805F9B34FB` | — | Service batterie standard |
| **Battery Level** | `00002A19-0000-1000-8000-00805F9B34FB` | `Read`, `Notify` | Niveau 0-100% (auto-notify toutes les 30s) |
| **Device Information (DIS)** | `0000180A-0000-1000-8000-00805F9B34FB` | — | Modèle (`0x2A24`), Fabricant (`0x2A29`), FW (`0x2A26`) |
| **Dialog SUOTA Service** | `0000FEF5-0000-1000-8000-00805F9B34FB` | — | Mise à jour logicielle over-the-air (DA1469x) |

---

## 2. Anatomie du Paquet Binaire

Tous les paquets transitant par **Server RX** ou **Server TX** obéissent au cadrage binaire suivant :

```text
+----------+----------+------------+------------+---------------+--------------+----------+
| Start    | Opcode   | Cmd Format | Length     | Query ID      | Data Payload | Footer   |
| 1 Byte   | 1 Byte   | 1 Byte     | 1 ou 2 B   | 0..15 Bytes   | 0..512 Bytes | 1 Byte   |
| (0xFF)   | (Cmd ID) | (Bitmask)  | (Big-End)  | (Optionnel)   | (Paramètres) | (0xAA)   |
+----------+----------+------------+------------+---------------+--------------+----------+
```

### Détail des champs :
1. **Start Byte :** Toujours `0xFF`.
2. **Opcode (Command ID) :** `0x00` à `0xFF`.
3. **Command Format (1 octet - masque de bits) :**
   - **Bit 5 (`0x20`)** : Longueur sur 1 octet (`0`) si total $\le 255$ octets ; ou 2 octets (`1`) si total $> 255$ octets (Big-Endian).
   - **Bits 4..1 (`0x1E`)** : Longueur du Query ID (`0` à `15` octets) : `(fmt & 0x1E) >> 1`.
   - **Bits 7, 6, 0** : Réservés (0).
   - Format usuel sans Query ID : `0x00` (longueur 1B) ou `0x20` (longueur 2B).
4. **Length :** Longueur totale en octets de la trame complète, depuis `0xFF` jusqu'à `0xAA` inclus. Taille max = **533 octets** (1 + 1 + 1 + 2 + 15 + 512 + 1).
5. **Query ID (Optionnel) :** Identifiant arbitraire de suivi (0 à 15 octets). Le firmware renvoie cet identifiant exact dans la réponse TX asynchrone pour corrélation.
6. **Data Payload :** Paramètres de la commande. **Strictement Big-Endian (MSB First)** pour tous les entiers 16-bit et 32-bit (`s16`, `u16`, `u32`).
7. **Footer Byte :** Toujours `0xAA`.
8. **Intégrité :** Pas de CRC applicatif ; la couche liaison BLE L2CAP intègre un CRC matériel 24-bit. L'intégrité de la trame est validée par `0xFF`, la longueur exacte et `0xAA`.

---

## 3. Contrôle de Flux Matériel (`...5CB9`)

Le microcontrôleur des lunettes dispose d'un buffer de réception interne de **1 024 octets** (permettant de recevoir 2 trames maximales de 512 octets de données).

Notifications émises sur la caractéristique de contrôle `...5CB9` :
- `0x01` (`FLOW_OK`) : Buffer sous le seuil de sécurité. Le maître BLE peut émettre.
- `0x02` (`FLOW_PAUSE`) : Le buffer a atteint **75% de capacité** (768 octets). L'hôte **DOIT suspendre immédiatement ses écritures**.
- `0x03` (`CMD_ERROR`) : Trame corrompue (mauvais délimiteur `0xFF`/`0xAA`, longueur incohérente). Commande rejetée.
- `0x04` (`BUFFER_OVERFLOW`) : Buffer saturé (100%), paquet entrant rejeté.
- `0x06` (`MISSING_CONFIG`) : Tentative de modification de flash (layout, image, police) sans `cfgWrite` préalable (`0xD0`).

> [!WARNING]
> **Bug de blocage Flow Control (Field Workaround) :**  
> Si les lunettes émettent `0x02` mais que le paquet de reprise `0x01` est perdu en environnement RF bruité, l'émetteur hôte peut rester bloqué indéfiniment.  
> **Solution de production :** Armer un watchdog logiciel de **1 000 ms** dès réception de `0x02`. Si aucun `0x01` n'est reçu après 1 seconde, forcer `can_send = true` et dépiler le paquet suivant.

---

## 4. Registre Exhaustif des Opcodes ActiveLook

### 4.1 Système & Configuration Matérielle (`0x00` - `0x2F`)

| Opcode | Mnémonique | Paramètres | Description |
| :---: | :--- | :--- | :--- |
| `0x00` | `displayPower` | `bool en` (1B) | `0x00`=Éteint, `0x01`=Allumé. Active/désactive l'alimentation MicroOLED. |
| `0x01` | `clear` | Aucun | Efface la mémoire d'écran vers le noir absolu (0 mW). |
| `0x02` | `grey` | `u8 lvl` (1B, 0..15) | Remplit tout l'écran d'un niveau de gris uniforme. |
| `0x03` | `demo` | `u8 id` (1B) | `0`=fill, `1`=mire de visée, `2`=boucle d'images stockées. |
| `0x05` | `battery` | Aucun | Requête niveau de charge. Retourne `u8 percent` (0..100%). |
| `0x06` | `vers` | Aucun | Requête firmware. Retourne 9 octets : `fwVersion[4]`, `year`, `week`, `serial[3]`. |
| `0x08` | `led` | `u8 state` (1B) | `0`=Off, `1`=On, `2`=Toggle, `3`=Blink. Pilote la LED verte interne de test. |
| `0x09` | `shift` | `s16 x, s16 y` (4B) | Décalage optique global (-128..+127). Sauvegardé en mémoire flash. |
| `0x0A` | `settings` | Aucun | Requête configuration active. Retourne 5 octets (`x`, `y`, `luma`, `als`, `gesture`). |
| `0x10` | `luma` | `u8 level` (1B, 0..15) | Luminance manuelle de l'affichage (0=min, 15=max 10 000 nits). Persistant. |
| `0x20` | `sensor` | `bool en` (1B) | Active/désactive simultanément le capteur ALS et le capteur IR de geste. |
| `0x21` | `gesture` | `bool en` (1B) | Active/désactive uniquement le capteur infrarouge de balayage. Persistant. |
| `0x22` | `als` | `bool en` (1B) | Active/désactive uniquement le capteur de lumière ambiante. Persistant. |

---

### 4.2 Primitives Graphiques 2D & Texte (`0x30` - `0x3E`)

| Opcode | Mnémonique | Paramètres | Description |
| :---: | :--- | :--- | :--- |
| `0x30` | `grayscale` | `u8 lvl` (1B, 0..15) | Définit le niveau de gris actif pour les tracés suivants. |
| `0x31` | `point` | `s16 x, s16 y` | Dessine un pixel aux coordonnées `(x, y)`. |
| `0x32` | `line` | `s16 x0, y0, x1, y1` | Trace un segment de droite vecteur d'épaisseur 1 px. |
| `0x33` | `rect` | `s16 x0, y0, x1, y1` | Trace le contour d'un rectangle. |
| `0x34` | `rectf` | `s16 x0, y0, x1, y1` | Remplit un rectangle plein (pixels allumés au niveau de gris actif). |
| `0x35` | `circ` | `s16 x, y, u8 r` | Trace le contour d'un cercle de rayon `r`. |
| `0x36` | `circf` | `s16 x, y, u8 r` | Remplit un disque plein de rayon `r`. |
| `0x37` | `txt` | `s16 x, y, u8 rot, font, grey, str text\0` | Dessine une chaîne de caractères UTF-8/ASCII terminée par `0x00`. |
| `0x38` | `polyline` | `u8 thick, rsvd1, rsvd2, (s16 x, y)...` | Trace une polyligne continue avec épaisseur en pixels. |
| `0x39` | `holdFlush` | `u8 action` (1B) | `0` = Hold (mise en mémoire tampon), `1` = Flush (rendu atomique à l'écran). |
| `0x3C` | `arc` | `s16 x, y, u8 r, s16 start, end, u8 thick` | Trace un arc de cercle en degrés (0° = 3h, sens horaire). |
| `0x3D` | `color` | `u8 color_id` (1B) | Sélectionne la couleur active sur le modèle ENGO 3 MultiColor. |
| `0x3E` | `txtColor` | `s16 x, y, u8 rot, font, color, str text\0` | Dessine du texte directement avec un identifiant couleur palette. |

---

### 4.3 Images & Polices (`0x41` - `0x53`)

| Opcode | Mnémonique | Paramètres | Description |
| :---: | :--- | :--- | :--- |
| `0x41` | `imgSave` | `u8 id, u32 size, u16 w, u8 fmt` | Enregistre un bitmap 4bpp compressé (Heatshrink) dans la mémoire flash. |
| `0x42` | `imgDisplay` | `u8 id, s16 x, s16 y` | Affiche un bitmap stocké en flash aux coordonnées `(x, y)`. |
| `0x44` | `imgStream` | `u32 size, u16 w, s16 x, y, u8 fmt, data...` | Affiche un bitmap en flux direct sans écriture en mémoire flash. |
| `0x45` | `imgSave1bpp` | `u8 id, u32 size, u16 w` | Enregistre une image 1-bit monochrome (8 pixels/octet). |
| `0x46` | `imgDelete` | `u8 id` (1B) | Supprime l'image `id` (`0xFF` = supprime toutes les images). |
| `0x47` | `imgList` | Aucun | Retourne le tableau des images stockées `[u8 id, u16 w, u16 h]`. |
| `0x50` | `fontList` | Aucun | Retourne les polices disponibles `[u8 id, u8 height]`. |
| `0x51` | `fontSave` | `u8 id, u16 size` + chunks | Enregistre une table de glyphes de police personnalisée en flash. |
| `0x52` | `fontSelect` | `u8 id` (1B) | Définit la police active par défaut. |
| `0x53` | `fontDelete` | `u8 id` (1B) | Supprime la police personnalisée (`0xFF` = toutes). |

---

### 4.4 Moteur de Widgets, Layouts & Pages (`0x60` - `0x86`)

| Opcode | Mnémonique | Paramètres | Description |
| :---: | :--- | :--- | :--- |
| `0x60` | `layoutSave` | En-tête 17B + sous-commandes | Enregistre un gabarit de widget en niveaux de gris (boîte englobante, police, offset). |
| `0x61` | `layoutDelete` | `u8 id` | Supprime un layout (`0xFF` = tous). |
| `0x62` | `layoutDisplay` | `u8 id, str text\0` | Affiche du texte dynamique dans l'emplacement réservé du layout. |
| `0x63` | `layoutClear` | `u8 id` | Efface la zone de découpe (clipping) du layout. |
| `0x64` | `layoutList` | Aucun | Retourne la liste des IDs de layouts enregistrés. |
| `0x65` | `layoutPosition`| `u8 id, u16 x, u8 y` | Déplace de façon permanente l'origine du layout. |
| `0x69` | `layoutClearAndDisplay` | `u8 id, str text\0` | Effacement + tracé atomique dans le layout (sans clignotement). |
| `0x6B` | `layoutSaveInColor` | En-tête 17B + sous-commandes | Enregistre un gabarit de layout avec palettes de couleur (ENGO 3). |
| `0x70` | `gaugeDisplay`| `u8 id, u8 value` (2B) | Met à jour une jauge circulaire / linéaire (valeur 0 à 100%). |
| `0x71` | `gaugeSave` | 12 octets de définition | Crée une jauge (`id, x, y, r, rIn, start_deg, end_deg, clockWise`). |
| `0x80` | `pageSave` | `u8 id, (u8 layoutId, u16 x, u8 y)...` | Lie jusqu'à 10 layouts dans une vue multi-emplacements. |
| `0x83` | `pageDisplay` | `u8 id, str s1\0 s2\0 ... sN\0` | Met à jour simultanément tous les layouts de la page en 1 seul paquet BLE. |
| `0x86` | `pageClearAndDisplay` | `u8 id, str s1\0 s2\0 ... sN\0` | Effacement atomique des boîtes et mise à jour des textes. |

---

### 4.5 Gestion du Pool Flash NOR 3MB (`0xD0` - `0xD8`)

| Opcode | Mnémonique | Paramètres | Description |
| :---: | :--- | :--- | :--- |
| `0xD0` | `cfgWrite` | `str name[12], u32 ver, u32 pwd` | Ouvre/alloue un conteneur de configuration. Requiert batterie $\ge 5\%$. |
| `0xD1` | `cfgRead` | `str name[12]` | Retourne le nombre d'éléments dans le conteneur nommé. |
| `0xD2` | `cfgSet` / `cfgSelect` | `str name[12]` | Active la configuration (charge polices et gabarits en mémoire vive). |
| `0xD3` | `cfgList` | Aucun | Retourne le catalogue des configurations : taille, version, compteur d'usage. |
| `0xD4` | `cfgRename` | `str old[12], str new[12], u32 pwd` | Renomme un conteneur de configuration. |
| `0xD5` | `cfgDelete` | `str name[12]` | Supprime une configuration et libère les blocs flash associés. |
| `0xD6` | `cfgDeleteLessUsed` | Aucun | Ramasse-miettes LRU : supprime la configuration la moins utilisée. |
| `0xD7` | `cfgFreeSpace` | Aucun | Retourne l'espace mémoire flash disponible en octets (pool 3 MB). |
| `0xD8` | `cfgGetNb` | Aucun | Retourne le nombre total de conteneurs installés (max 12). |

---

### 4.6 Commandes Système Bas-Niveau & Diagnostic (`0xE0` - `0xE3`)

| Opcode | Mnémonique | Paramètres | Description |
| :---: | :--- | :--- | :--- |
| `0xE0` | `shutdown` | `u32 key` (4B) | Clé magique : `0x6F 0x7F 0xC4 0xEE`. Éteint le MCU. Interdit si USB connecté. |
| `0xE1` | `reset` | `u32 key` (4B) | Clé magique : `0x5C 0x1E 0x2D 0xE9`. Redémarre le MCU. Autorisé uniquement sous USB. |
| `0xE2` | `error` | `u8 cmdId, u8 err, u8 subErr` | Notification asynchrone émise vers le central lors d'une faute d'exécution. |
| `0xE3` | `rdDevInfo` | `u8 id` (1B) | Requête identité matérielle : `0`=Plateforme, `1`=Fabricant, `3`=Modèle, `5`=Version FW, `6`=Numéro de série. |
