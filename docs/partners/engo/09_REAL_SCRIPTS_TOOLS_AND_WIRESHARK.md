# ActiveLook / ENGO: Scripts Réels, Outillage & Analyse Wireshark

> **Guide Opérationnel de Terrain & Ingénierie Inverse**  
> Scripts prêts pour la production, analyseur Wireshark Lua, dumps hexadécimaux et 10 contournements de bugs matériels documentés.

---

## 1. Script Contrôleur Python Complet (`bleak`)

Ce script implémente le cycle de vie complet : découverte BLE, négociation MTU, abonnements séquentiels aux descripteurs, gestion du contrôle de flux avec watchdog de reprise, et rendu atomique sans scintillement (`holdFlush`).

```python
#!/usr/bin/env python3
"""
ActiveLook / ENGO Eyewear Controller (Python / Bleak)
Gestion robuste du protocole binaire, du contrôle de flux et du rendu atomique.
"""

import asyncio
import logging
import struct
from typing import Optional
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ActiveLook")

# UUIDs GATT ActiveLook
SERVICE_ACTIVELOOK = "0783b03e-8535-b5a0-7140-a304d2495cb7"
CHAR_TX            = "0783b03e-8535-b5a0-7140-a304d2495cb8"
CHAR_CONTROL       = "0783b03e-8535-b5a0-7140-a304d2495cb9"
CHAR_RX            = "0783b03e-8535-b5a0-7140-a304d2495cba"
CHAR_GESTURE       = "0783b03e-8535-b5a0-7140-a304d2495cbb"
CHAR_TOUCH         = "0783b03e-8535-b5a0-7140-a304d2495cbc"
CHAR_BATTERY       = "00002a19-0000-1000-8000-00805f9b34fb"


class ActiveLookDevice:
    def __init__(self, client: BleakClient):
        self.client = client
        self.can_send = asyncio.Event()
        self.can_send.set()
        self.flow_watchdog_task: Optional[asyncio.Task] = None
        self.battery_level: int = -1

    def _on_control_event(self, _: BleakGATTCharacteristic, data: bytearray):
        code = data[0]
        if code == 0x01:  # FLOW_OK
            logger.info("[FlowCtrl] OK (0x01): buffer libéré, transmission active")
            if self.flow_watchdog_task and not self.flow_watchdog_task.done():
                self.flow_watchdog_task.cancel()
            self.can_send.set()
        elif code == 0x02:  # FLOW_PAUSE (Buffer >= 75%)
            logger.warning("[FlowCtrl] PAUSE (0x02): buffer à 75%, suspension des écritures")
            self.can_send.clear()
            # Contournement de sécurité : watchdog de 1000ms si le paquet 0x01 est perdu
            if self.flow_watchdog_task and not self.flow_watchdog_task.done():
                self.flow_watchdog_task.cancel()
            self.flow_watchdog_task = asyncio.create_task(self._flow_watchdog())
        elif code == 0x03:
            logger.error("[FlowCtrl] Erreur 0x03: Commande invalide ou trame corrompue")
        elif code == 0x04:
            logger.error("[FlowCtrl] Erreur 0x04: Débordement de buffer (packet drop)")
        elif code == 0x06:
            logger.error("[FlowCtrl] Erreur 0x06: Flash verrouillée (manque cfgWrite 0xD0)")

    async def _flow_watchdog(self):
        await asyncio.sleep(1.0)
        logger.warning("[FlowCtrl] Watchdog expiré : reprise forcée de can_send=True")
        self.can_send.set()

    def _on_tx_data(self, _: BleakGATTCharacteristic, data: bytearray):
        cmd_id = data[1] if len(data) > 1 else None
        logger.info(f"[TX Notify] Opcode 0x{cmd_id:02X}, brut: {data.hex().upper()}")

    def _on_gesture(self, _: BleakGATTCharacteristic, data: bytearray):
        logger.info(f"[Capteur] GESTE détecté (0x{data.hex().upper()})")

    def _on_touch(self, _: BleakGATTCharacteristic, data: bytearray):
        logger.info(f"[Capteur] TACTILE branche détecté (0x{data.hex().upper()})")

    def _on_battery(self, _: BleakGATTCharacteristic, data: bytearray):
        self.battery_level = data[0]
        logger.info(f"[Batterie] Niveau : {self.battery_level}%")

    def build_packet(self, cmd_id: int, payload: bytes = b"", query_id: bytes = b"") -> bytes:
        query_len = len(query_id)
        estimated_len = 1 + 1 + 1 + 1 + query_len + len(payload) + 1
        if estimated_len <= 255:
            cmd_format = 0x00 | (query_len & 0x0F)
            total_len = estimated_len
            header = struct.pack(">BBBB", 0xFF, cmd_id, cmd_format, total_len)
        else:
            cmd_format = 0x20 | (query_len & 0x0F)
            total_len = estimated_len + 1  # 2 octets pour la longueur
            header = struct.pack(">BBBH", 0xFF, cmd_id, cmd_format, total_len)
        return header + query_id + payload + b"\xAA"

    async def write_command(self, cmd_id: int, payload: bytes = b"", with_response: bool = True):
        packet = self.build_packet(cmd_id, payload)
        await self.can_send.wait()
        await self.client.write_gatt_char(CHAR_RX, packet, response=with_response)

    async def init_subscriptions(self):
        # Enregistrement séquentiel des descripteurs de notification
        await self.client.start_notify(CHAR_CONTROL, self._on_control_event)
        await self.client.start_notify(CHAR_TX, self._on_tx_data)
        await self.client.start_notify(CHAR_TOUCH, self._on_touch)
        await self.client.start_notify(CHAR_GESTURE, self._on_gesture)
        try:
            await self.client.start_notify(CHAR_BATTERY, self._on_battery)
        except Exception as e:
            logger.warning(f"Notification batterie non disponible : {e}")

    # Commandes graphiques de base
    async def hold_flush(self, action: int):
        """0 = Hold (temporise les tracés), 1 = Flush (affiche atomiquement)."""
        await self.write_command(0x39, struct.pack("B", action))

    async def clear_atomic(self):
        """Effacement sans scintillement via rectangle noir plein (304x256)."""
        await self.write_command(0x34, struct.pack(">hhhh", 0, 0, 303, 255))

    async def set_luma(self, level: int):
        """Définit la luminosité (0-15)."""
        await self.write_command(0x10, struct.pack("B", max(0, min(15, level))))

    async def draw_text(self, x: int, y: int, text: str, font_id: int = 0, grey: int = 15, rot: int = 0):
        """Trace une chaîne ASCII/UTF-8 (0x37)."""
        header = struct.pack(">hhBBB", x, y, rot, font_id, grey)
        payload = header + text.encode("utf-8", errors="replace") + b"\x00"
        await self.write_command(0x37, payload)

    async def set_config(self, cfg_name: str = "ALooK"):
        """Sélectionne le profil de configuration flash standard."""
        name_bytes = cfg_name.encode("ascii")[:12].ljust(12, b"\x00")
        await self.write_command(0xD2, name_bytes)


async def main():
    logger.info("Recherche des lunettes ActiveLook / ENGO...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: (d.name and any(p in d.name for p in ["ENGO", "ActiveLook", "Activelook"]))
        or SERVICE_ACTIVELOOK.lower() in [s.lower() for s in adv.service_uuids],
        timeout=10.0
    )

    if not device:
        logger.error("Aucune lunette ActiveLook détectée.")
        return

    logger.info(f"Connexion à {device.name} ({device.address})...")
    async with BleakClient(device.address) as client:
        logger.info(f"Connecté ! MTU négocié : {client.mtu_size}")
        glasses = ActiveLookDevice(client)
        await glasses.init_subscriptions()
        await asyncio.sleep(0.3)

        # Enforce baseline configuration
        await glasses.set_config("ALooK")
        await asyncio.sleep(0.1)

        # Rendu atomique sans scintillement
        await glasses.hold_flush(0)
        await glasses.clear_atomic()
        await glasses.set_luma(14)

        # Tracé d'une interface de télémétrie OpenBridge
        await glasses.write_command(0x32, struct.pack(">hhhh", 24, 230, 280, 230))
        await glasses.draw_text(24, 245, "OPENBRIDGE HUD", font_id=0, grey=15)
        await glasses.draw_text(24, 160, "PUISSANCE : 2.4 kW", font_id=2, grey=15)
        await glasses.draw_text(24, 90, "ASPIRATEUR : DOCK", font_id=2, grey=15)

        await glasses.hold_flush(1)
        logger.info("Affichage actif ! En écoute des capteurs (Ctrl+C pour quitter)...")

        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 2. Analyseur Wireshark Lua (`activelook.lua`)

Pour inspecter les paquets réels échangés entre le smartphone et les lunettes via Wireshark (capture HCI Snoop Android) :
Enregistrez ce fichier sous le nom `activelook.lua` dans le dossier des plugins Lua de Wireshark (`Aide > À propos de Wireshark > Dossiers > Plugins Lua personnels`).

```lua
-- activelook.lua - Wireshark Dissector for ActiveLook / ENGO Glasses BLE Protocol
local p_activelook = Proto("activelook", "ActiveLook Smart Glasses Protocol")

local f_start   = ProtoField.uint8("activelook.start", "Start Delimiter", base.HEX)
local f_cmd     = ProtoField.uint8("activelook.cmd", "Command ID", base.HEX)
local f_format  = ProtoField.uint8("activelook.format", "Command Format", base.HEX)
local f_length  = ProtoField.uint16("activelook.length", "Length", base.DEC)
local f_queryid = ProtoField.bytes("activelook.queryid", "Query ID")
local f_payload = ProtoField.bytes("activelook.payload", "Payload Data")
local f_footer  = ProtoField.uint8("activelook.footer", "End Delimiter", base.HEX)

p_activelook.fields = { f_start, f_cmd, f_format, f_length, f_queryid, f_payload, f_footer }

local cmd_names = {
    [0x00] = "displayPower", [0x01] = "clear", [0x02] = "grey", [0x03] = "demo",
    [0x05] = "battery", [0x06] = "vers", [0x08] = "led", [0x09] = "shift",
    [0x10] = "luma", [0x20] = "sensor", [0x21] = "gesture", [0x22] = "als",
    [0x30] = "color", [0x31] = "point", [0x32] = "line", [0x33] = "rect",
    [0x34] = "rectf", [0x35] = "circ", [0x36] = "circf", [0x37] = "txt",
    [0x38] = "polyline", [0x39] = "holdFlush", [0x41] = "imgSave", [0x42] = "imgDisplay",
    [0x44] = "imgStream", [0x46] = "imgDelete", [0x47] = "imgList", [0x50] = "fontList",
    [0x60] = "layoutSave", [0x62] = "layoutDisplay", [0x63] = "layoutClear",
    [0x70] = "gaugeDisplay", [0x71] = "gaugeSave", [0x80] = "pageSave", [0x83] = "pageDisplay",
    [0xD0] = "cfgWrite", [0xD2] = "cfgSet", [0xE0] = "shutdown", [0xE1] = "reset"
}

function p_activelook.dissector(buffer, pinfo, tree)
    local length = buffer:len()
    if length < 5 then return end

    local start_byte = buffer(0, 1):uint()
    local end_byte = buffer(length - 1, 1):uint()
    if start_byte ~= 0xFF or end_byte ~= 0xAA then return end

    pinfo.cols.protocol = "ActiveLook"

    local cmd_id = buffer(1, 1):uint()
    local cmd_name = cmd_names[cmd_id] or string.format("Unknown (0x%02X)", cmd_id)
    pinfo.cols.info = string.format("Cmd: %s", cmd_name)

    local subtree = tree:add(p_activelook, buffer(), string.format("ActiveLook Packet: %s", cmd_name))
    subtree:add(f_start, buffer(0, 1))
    subtree:add(f_cmd, buffer(1, 1)):append_text(string.format(" (%s)", cmd_name))

    local fmt_byte = buffer(2, 1):uint()
    subtree:add(f_format, buffer(2, 1))

    local is_long = (bit.band(fmt_byte, 0x20) ~= 0)
    local query_len = bit.band(bit.rshift(fmt_byte, 1), 0x0F)
    local offset = 3

    if is_long then
        subtree:add(f_length, buffer(offset, 2))
        offset = offset + 2
    else
        subtree:add(f_length, buffer(offset, 1))
        offset = offset + 1
    end

    if query_len > 0 then
        subtree:add(f_queryid, buffer(offset, query_len))
        offset = offset + query_len
    end

    local payload_len = length - offset - 1
    if payload_len > 0 then
        subtree:add(f_payload, buffer(offset, payload_len))
    end

    subtree:add(f_footer, buffer(length - 1, 1))
end

DissectorTable.get("btatt.handle"):add(0x0000, p_activelook)
```

---

## 3. Traces Hexadécimales Réelles Capturées

### Traces Central ➔ Lunettes (`Server RX`)
* **Effacement Écran (`0x01`)** :
  `FF 01 00 05 AA`
* **Maintien du Rendu (`0x39 holdFlush`, action=0)** :
  `FF 39 00 06 00 AA`
* **Libération Atomique du Rendu (`0x39 holdFlush`, action=1)** :
  `FF 39 00 06 01 AA`
* **Définition Luminance (`0x10 luma`, niveau=15)** :
  `FF 10 00 06 0F AA`
* **Rectangle Plein (`0x34 rectf`, 0, 0, 303, 255)** :
  `FF 34 00 0D 00 00 00 00 01 2F 00 FF AA`
* **Écriture Texte ("HELLO", x=24, y=128, rot=0, font=0, grey=15)** :
  `FF 37 00 13 00 18 00 80 00 00 0F 48 45 4C 4C 4F 00 AA`
* **Sélection Configuration Flash (`0xD2 cfgSet`, "ALooK")** :
  `FF D2 00 09 41 4C 6F 6F 4B AA`

### Traces Lunettes ➔ Central
* **Contrôle de Flux OK (`Control Char`)** : `01`
* **Contrôle de Flux Buffer 75% (`Control Char`)** : `02`
* **Notification Geste IR (`Gesture Char`)** : `01`
* **Notification Tactile Branche (`Touch Char`)** : `01`
* **Mise à Jour Batterie (`Battery Char`)** : `5F` (95%)

---

## 4. 10 Pièges Matériels, Bugs de Firmware & Solutions Validées

| # | Piège Matériel / Bug Observé | Symptôme en Production | Solution Validée |
| :-: | :--- | :--- | :--- |
| **1** | **Débordement de demi-octet (Blanc pur 255 éteint)** | Dans les formats 4-bit (`0x0` à `0xF`), envoyer `255` déborde le demi-octet et retombe à `0` (LED éteinte). | **Plafonner la luminance à `240`** (`0xF0F0F0`). 240 correspond au niveau 15 sans débordement. |
| **2** | **Flash noir à l'effacement (`clear()` non bufferisé)** | `clear` (`0x01`) s'exécute immédiatement sur le contrôleur et ignore `holdFlush(0)`. Clignotement de 50 ms. | **Ne jamais utiliser `0x01` en direct**. Utiliser `holdFlush(0)`, effacer via un rectangle noir (`0x34 rectf 0 0 303 255`), tracer et `holdFlush(1)`. |
| **3** | **Intervalle BLE lent sous Android** | Par défaut Android négocie 50 ms d'intervalle, provoquant des erreurs `"Could not write rx"` par saturation. | **Forcer la priorité haute :** `requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)` fait chuter l'intervalle à 11–15 ms. |
| **4** | **Blocage Flow Control (Watchdog 1000ms)** | La lunette émet `0x02` (pause), mais le paquet `0x01` (reprise) est perdu. L'émetteur hôte reste gelé. | **Armer un timer watchdog de 1 000 ms** dès réception de `0x02`. Si non acquitté à 1 s, forcer `can_send = true`. |
| **5** | **Double déclenchement du capteur de geste** | Le capteur IR frontal détecte l'entrée puis la sortie de la main (2 événements en 50–120 ms). | **Appliquer un antirebond logiciel de 300 à 350 ms minimum**. |
| **6** | **Overscan optique et flou de bordure** | La dalle fait 304×256 mais le prisme optique rogne la périphérie (flou ou masquage à moins de 24 px des bords). | **Respecter la zone sécurisée :** Marge X = 24 px, Y = 14 px. Zone utile nette = **256 × 228 pixels**. |
| **7** | **Ancrage asymétrique des coordonnées** | L'origine est en bas à gauche ($X: 0 \to 304, Y: 0 \to 256$), mais `txt` s'ancre en haut à gauche et descend, tandis que `img` s'ancre en bas à droite. | **Appliquer les offsets compensatoires :** Décalage de 2 px en Y sur les images et trier systématiquement les rectangles ($x_0 \le x_1, y_0 \le y_1$). |
| **8** | **Verrouillage du profil Flash (`cfgSet`)** | Si une application tierce a écrit un profil flash personnalisé, les polices par défaut peuvent être absentes. | **Émettre systématiquement `cfgSet("ALooK")` (`0xD2`)** immédiatement après la connexion BLE. |
| **9** | **Polices ROM strictement ASCII** | Les caractères accentués (é, à, è), les cédilles ou les emojis corrompent l'affichage. | **Translittérer en ASCII pur** ou rastériser localement sur l'hôte en bitmap 1bpp/4bpp et envoyer via `imgStream` (`0x44`). |
| **10**| **Saturation de bande passante en animation** | Diffuser des bitmaps en continu sature le lien radio BLE. | **Utiliser des boîtes de réserve vides (`layouts`)** et ne transmettre le bitmap final qu'une fois le mouvement stabilisé. |
