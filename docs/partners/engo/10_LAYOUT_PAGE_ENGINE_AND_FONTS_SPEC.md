# ActiveLook Moteur de Layouts, Pages, Polices & Mémoire Flash

> **Spécification d'Implémentation Haute-Fidélité**  
> Comment ActiveLook élimine le scintillement, divise la bande passante par 10 et gère les profils flash persistants.

---

## 1. Pourquoi le Modèle Layout / Page ?

L'envoi de commandes graphiques brutes (`txt`, `rect`, `line`) à 1 Hz pour rafraîchir plusieurs données (vitesse, fréquence cardiaque, puissance, heure) pose 3 problèmes majeurs :
1. **Saturation de la bande passante BLE :** 4 champs distincts nécessitent ~150 octets par seconde.
2. **Latence perçue et scintillement :** Chaque commande est traitée séquentiellement par le microcontrôleur.
3. **Surconsommation radio :** Le module BLE reste en mode émission haute puissance.

ActiveLook résout ce problème en séparant l'interface en deux niveaux hiérarchiques :
- **Les Layouts (`0x60` / `0x6B`) :** Gabarits persistants stockés en flash (boîte de découpe, position du texte, police, couleur, éléments statiques d'arrière-plan).
- **Les Pages (`0x80`) :** Assemblages de 1 à 10 layouts sur un même écran.
- **L'Affichage Multi-Emplacements (`0x83 pageDisplay`) :** Une unique trame BLE de 15 à 30 octets transmettant uniquement les chaînes de texte séparées par des zéros binaires (`\0`).

---

## 2. Structure Binaire d'un Layout (`layoutSave` `0x60` / `0x6B`)

Un Layout est défini par un **en-tête de base fixe de 17 octets**, suivi optionnellement de sous-commandes graphiques vectorielles sérialisées :

```text
+----+------+--------+----+---------+----+-----------+-----------+------+-----------+--------+--------+----------+-----------+
| id | size | x      | y  | width   | h  | foreColor | backColor | font | textValid | textX  | textY  | textRot  | textOpac  |
| 1B | 1B   | 2B(BE) | 1B | 2B(BE)  | 1B | 1B        | 1B        | 1B   | 1B        | 2B(BE) | 1B     | 1B       | 1B        |
+----+------+--------+----+---------+----+-----------+-----------+------+-----------+--------+--------+----------+-----------+
0    1      2        4    5         7    8           9           10     11          12       14       15         16
```

### Table des Champs de l'En-tête (17 octets) :
| Offset | Type | Nom | Description |
| :---: | :--- | :--- | :--- |
| `0` | `u8` | `id` | Identifiant du layout (`0x00` à `0xFF`). |
| `1` | `u8` | `size` | Taille en octets des sous-commandes statiques qui suivent (`0` si aucune). |
| `2..3` | `u16` (BE) | `x` | Coordonnée X supérieure gauche de la zone de découpe (`0` à `303`). |
| `4` | `u8` | `y` | Coordonnée Y supérieure gauche de la zone de découpe (`0` à `255`). |
| `5..6` | `u16` (BE) | `width` | Largeur de la zone de découpe en pixels. |
| `7` | `u8` | `height` | Hauteur de la zone de découpe en pixels. |
| `8` | `u8` | `foreColor` | Couleur de premier plan (niveaux de gris `0..15` ou palette `0x00..0x50` ENGO 3). |
| `9` | `u8` | `backColor` | Couleur d'arrière-plan (généralement `0` = noir éteint). |
| `10` | `u8` | `font` | Identifiant de police utilisée pour le champ texte dynamique (`1..5`). |
| `11` | `u8` / `bool`| `textValid` | `1` = le layout accepte du texte dynamique, `0` = widget purement graphique. |
| `12..13`| `u16` (BE) | `textX` | Décalage X du texte relatif à l'origine du layout. |
| `14` | `u8` | `textY` | Décalage Y du texte relatif à l'origine du layout. |
| `15` | `u8` | `textRotation` | Mode d'ancrage et d'orientation (`0` = LTR horizontal, `4` = centré). |
| `16` | `u8` | `textOpacity` | `0` = fond transparent, `1` = fond opaque. |

### Sous-Commandes Sérialisées (Octets 17 à 17 + `size`) :
Si `size > 0`, l'en-tête est suivi de commandes graphiques statiques (icônes, lignes de séparation, unités) automatiquement rognées à la zone de découpe `(x, y, width, height)`.

---

## 3. Définition et Affichage d'une Page (`pageSave` & `pageDisplay`)

### A. Enregistrement d'une Page (`0x80 pageSave`)
Une page rassemble jusqu'à 10 layouts sur un même écran avec des coordonnées d'affichage explicites :
- `Byte 0` : `u8 id` (Identifiant de la page).
- Séquence de slots (4 octets par slot) :
  `u8 layoutId, u16 x, u8 y`

### B. Affichage Atomique (`0x83 pageDisplay` / `0x86 pageClearAndDisplay`)
Pour mettre à jour la totalité de l'écran, le central transmet simplement l'ID de la page suivi des textes dynamiques concaténés et séparés par des zéros (`\x00`) :
`[0xFF] [0x83] [Fmt] [Len] [u8 pageId] [String_Layout1\x00] [String_Layout2\x00] ... [String_LayoutN\x00] [0xAA]`

#### Comportement dans le Firmware :
1. Pour chaque slot $i$ de la page :
   - L'origine cible est `(page.x_i, page.y_i)`.
   - La boîte de découpe `[ox, oy, ox + layout.width, oy + layout.height]` est effacée à `backColor` (noir).
   - Les sous-commandes statiques du layout sont tracées.
   - Si `textValid` est vrai et que la chaîne `String_Layout_i` n'est pas vide, elle est dessinée à `(ox + layout.textX, oy + layout.textY)`.
2. Résultat : Aucun clignotement, aucune transmission de coordonnées ou de polices sur le réseau BLE.

---

## 4. Polices Typographiques Intégrées & Caractères Fantômes

Les lunettes ENGO utilisent la famille typographique **SourceSansPro SemiBold** bitmap :

| Identifiant | Hauteur en Pixels | Jeu de Caractères | Usage Typique |
| :---: | :---: | :--- | :--- |
| **Font 1** | **24 px** | ASCII complet (`0x20` à `0x7E`) | Étiquettes d'unités ("km/h", "bpm", "w"), états |
| **Font 2** | **38 px** | ASCII complet (`0x20` à `0x7E`) | Métriques secondaires, écrans 3 et 4 champs |
| **Font 3** | **64 px** | ASCII complet (`0x20` à `0x7E`) | Métrique principale, fréquence cardiaque, allure |
| **Font 4** | **75 px** | Chiffres et ponctuation (`0x20` à `0x3B`) | Grands compteurs numériques de vitesse |
| **Font 5** | **82 px** | Chiffres et ponctuation (`0x20` à `0x3B`) | Affichage plein écran géant 1 seul champ |

### Caractères Fantômes d'Alignement Numérique :
Pour éviter que les nombres oscillent de droite à gauche lors des changements de valeur sans imposer une police à espacement fixe (monospace inesthétique), ActiveLook a introduit deux glyphes invisibles :
1. **`$` (ASCII `0x24`) :** Dessiné en noir absolu (pixels éteints = invisible). Sa largeur d'avance est **strictement identique au chiffre '0'**.  
   *Exemple :* `$$5` occupe exactement la même largeur physique que `125`.
2. **`&` (ASCII `0x26`) :** Dessiné en noir absolu. Sa largeur d'avance est **identique aux signes de ponctuation** ('.', ':', ',').  
   *Exemple :* Réserve l'espace pour aligner les virgules décimales dans un tableau.

---

## 5. Gestionnaire de Flash NOR 3MB & Profils de Configuration

Le firmware réserve une mémoire flash NOR de **3 mégaoctets** segmentée en **12 conteneurs de configuration** :

```text
+---------------------------------------------------------------------+
| Flash NOR 3 MB (Shared Storage Pool)                                |
| +---------------------+ +---------------------+ +-----------------+ |
| | Config "ALooK"      | | Config "OpenBridge" | | Config "UserApp"| |
| | - Layouts 0..30     | | - Layouts 0..15     | | - Layouts       | |
| | - Fonts 1..5        | | - Custom Fonts      | | - Custom Icons  | |
| | - Icons & Bitmaps   | | - Bitmaps           | | - Animations    | |
| +---------------------+ +---------------------+ +-----------------+ |
+---------------------------------------------------------------------+
```

### Commandes de Gestion :
- `0xD0 cfgWrite` : Ouvre la session d'écriture (`nom[12], version, mot_de_passe`). Requiert un niveau de batterie $\ge 5\%$.
- `0xD2 cfgSet` : Rend un profil actif en mémoire vive. Charge instantanément les gabarits associés.
- `0xD6 cfgDeleteLessUsed` : Ramasse-miettes (LRU) automatique éliminant la configuration au compteur d'usage (`usgCnt`) le plus faible en cas de manque d'espace.
- `0xD7 cfgFreeSpace` : Interroge les octets libres restants.
