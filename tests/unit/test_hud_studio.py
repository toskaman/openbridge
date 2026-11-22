"""HUD Studio engine, protocol decoding, control API, ALooK layout bank and F01–F38 catalog."""
import json
import socket
import struct
import threading
import time
import unittest

from src.adapters import alook_layouts, hud_features as hf
from src.adapters import hud_studio as hs
from src.adapters.activelook_emulator import HUDCanvas, scan_frames


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FrameCodecTests(unittest.TestCase):
    def test_frame_bytes_short_and_wide(self):
        short = hs.frame_bytes(0x37, b"x" * 10)
        self.assertEqual(short[:4], bytes([0xFF, 0x37, 0x00, 15]))
        wide = hs.frame_bytes(0x62, b"y" * 300)
        self.assertEqual(wide[2], 0x20)
        self.assertEqual(struct.unpack(">H", wide[3:5])[0], len(wide))
        frames, consumed = scan_frames(short + wide)
        self.assertEqual([f.cmd for f in frames], [0x37, 0x62])
        self.assertEqual(consumed, len(short) + len(wide))

    def test_scanner_resyncs_and_keeps_partial_tail(self):
        good = hs.frame_bytes(0x01)
        frames, consumed = scan_frames(b"\xFF\x37\x00\x00garbage" + good + good[:3])
        self.assertEqual([f.cmd for f in frames], [0x01])
        self.assertLess(consumed, len(b"\xFF\x37\x00\x00garbage" + good + good[:3]))

    def test_decode_txt_and_feature(self):
        f = hs.Frame(0x37, struct.pack(">hhBBB", 10, 20, 0, 1, 15) + b"HI\x00")
        self.assertIn("“HI”", hs.decode(f))
        self.assertTrue(hs.decode(hs.Frame(0xF0, bytes([7]))).startswith("F07"))


class CatalogTests(unittest.TestCase):
    def test_38_features_resolve_every_way(self):
        self.assertEqual(len(hf.FEATURES), 38)
        self.assertEqual([f.number for f in hf.FEATURES], list(range(1, 39)))
        f7 = hf.BY_ID["F07"]
        for ref in ("F07", "f7", 7, "7", "compass_wayfinder", f7):
            self.assertIs(hf.resolve(ref), f7)

    def test_every_feature_draws_pixels(self):
        hud = HUDCanvas(model="ENGO 3")
        from src.adapters.activelook import ActiveLookAdapter
        adapter = ActiveLookAdapter(transport=hud.dispatch, model="ENGO 3")
        for feat in hf.FEATURES:
            hud._cmd_clear()
            hf.run_feature(adapter, feat)
            self.assertGreater(hud.compute_pixel_fill(), 0.0, feat.fid)


class ALooKTests(unittest.TestCase):
    def test_known_layout_ids(self):
        for lid in (7, 10, 11, 12, 13, 21, 43, 46, 49, 73, 75, 178, 180, 182):
            self.assertTrue(alook_layouts.known(lid), lid)

    def test_extended_display_uses_activelook_coordinates(self):
        hud = HUDCanvas(model="ENGO 2")
        # top row (y=153, ActiveLook bottom-right origin) must land in the upper half of the screen
        hud.dispatch(hs.frame_bytes(0x66, bytes([12]) + struct.pack(">HB", 30, 153) + b"12.48"))
        box = hud._img.getbbox()
        self.assertIsNotNone(box)
        self.assertLess(box[3], 128)
        self.assertGreaterEqual(box[0], 20)


class EngineAndControlTests(unittest.TestCase):
    def setUp(self):
        self.phone_port, self.ctrl_port = _free_port(), _free_port()
        self.eng = hs.StudioEngine(model="ENGO 3", phone_port=self.phone_port, control_port=self.ctrl_port)
        self.eng.start()
        self._stop = False
        self.t = threading.Thread(target=self._pump, daemon=True)
        self.t.start()
        time.sleep(0.25)

    def _pump(self):
        while not self._stop:
            self.eng.pump()
            time.sleep(0.003)

    def tearDown(self):
        self._stop = True
        self.eng.stop()

    def call(self, **req):
        return hs.send_control(req, self.ctrl_port)

    def test_control_feature_status_and_unknown(self):
        self.assertTrue(self.call(cmd="ping")["ok"])
        self.assertEqual(self.call(cmd="feature", id="F21")["feature"], "F21")
        st = self.call(cmd="status")
        self.assertEqual(st["last_feature"], "F21")
        self.assertGreater(st["frames"], 0)
        self.assertFalse(self.call(cmd="nope")["ok"])

    def test_phone_frames_feature_trigger_and_gesture(self):
        ph = socket.create_connection(("127.0.0.1", self.phone_port))
        time.sleep(0.2)
        ph.sendall(hs.frame_bytes(OB := hs.OB_FEATURE_CMD, bytes([31])))
        time.sleep(0.4)
        self.assertEqual(self.call(cmd="status")["last_feature"], "F31")
        self.assertEqual(self.call(cmd="gesture")["phones"], 1)
        ph.settimeout(2)
        self.assertEqual(ph.recv(5), bytes([0xFF, 0x0A, 0x01, 0x01, 0xAA]))
        ph.close()
        self.assertEqual(OB, 0xF0)

    def test_record_and_replay_roundtrip(self):
        import tempfile, os
        self.call(cmd="record", action="start")
        self.call(cmd="inject", hex=hs.frame_bytes(0x37, struct.pack(">hhBBB", 4, 4, 0, 1, 15) + b"REC\x00").hex())
        path = os.path.join(tempfile.mkdtemp(), "t.obsession")
        self.assertEqual(self.call(cmd="record", action="stop", path=path)["path"], path)
        with open(path, encoding="utf-8") as fh:
            head = json.loads(fh.readline())
        self.assertEqual(head["format"], "openbridge-hud-session")
        self.assertEqual(self.call(cmd="replay", path=path, speed=4)["chunks"], 1)

    def test_render_modes(self):
        img = self.eng.hud._img
        for mode in ("pixels", "oled", "lens"):
            out = hs.render_hud(img, mode, 2, 10, mono=(mode == "lens"))
            self.assertEqual(out.size, (608, 512))


if __name__ == "__main__":
    unittest.main()
