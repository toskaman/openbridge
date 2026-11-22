import unittest
from src.adapters.activelook import (
    ActiveLookAdapter, encode_packet, cmd_clear, cmd_luma, cmd_color,
    cmd_text, cmd_gauge, cmd_gesture_enable, cmd_line,
    cmd_hold_flush, cmd_layout_save, cmd_page_save, cmd_page_display,
    COLOR_GREEN, COLOR_AMBER, COLOR_RED
)
from src.adapters.activelook_emulator import parse_frames, HUDCanvas


class ActiveLookTests(unittest.TestCase):
    def test_clear_frame_exact_binary(self):
        clear_bytes = cmd_clear()
        self.assertEqual(clear_bytes, bytes([0xFF, 0x01, 0x00, 0x05, 0xAA]))
        frames = parse_frames(clear_bytes)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].cmd, 0x01)
        self.assertEqual(frames[0].data, b"")

    def test_color_command_engo3(self):
        color_bytes = cmd_color(COLOR_GREEN)
        self.assertEqual(color_bytes[0], 0xFF)
        self.assertEqual(color_bytes[1], 0x3D) # cmd 0x3D
        self.assertEqual(color_bytes[-1], 0xAA)
        frames = parse_frames(color_bytes)
        self.assertEqual(frames[0].cmd, 0x3D)
        self.assertEqual(frames[0].data, bytes([COLOR_GREEN]))

    def test_text_command_payload(self):
        txt_bytes = cmd_text(10, 20, "Vacuum Docked", font=1, color_or_grey=15)
        frames = parse_frames(txt_bytes)
        self.assertEqual(frames[0].cmd, 0x37)
        self.assertIn(b"Vacuum Docked", frames[0].data)

    def test_receipt_push_ok_and_refused(self):
        sent_chunks = []
        adapter = ActiveLookAdapter(transport=lambda b: sent_chunks.append(b), model="ENGO 3")
        
        # OK Receipt (Green)
        ok = adapter.push_receipt("VACUUM", "Docked in base station", status="ok")
        self.assertTrue(ok)
        self.assertEqual(len(sent_chunks), 1)
        frames = parse_frames(sent_chunks[0])
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x3D for f in frames))  # color
        self.assertTrue(any(f.cmd == 0x37 for f in frames))  # text

        # Refused Receipt (Red)
        adapter.push_receipt("SECURITY", "Action refused: stale state", status="refused")
        self.assertEqual(len(sent_chunks), 2)
        frames_refused = parse_frames(sent_chunks[1])
        # Verify COLOR_RED opcode payload is present
        color_frames = [f for f in frames_refused if f.cmd == 0x3D]
        self.assertEqual(color_frames[0].data, bytes([COLOR_RED]))

    def test_flow_control_pause_and_resume(self):
        sent = []
        adapter = ActiveLookAdapter(transport=lambda b: sent.append(b))
        self.assertTrue(adapter.send(b"\x01"))
        
        # MCU notifies buffer >= 75%
        adapter.handle_flow_control(0x02)
        self.assertTrue(adapter.paused_by_flow_control)
        # Attempted write must fail
        self.assertFalse(adapter.send(b"\x02"))
        
        # MCU drains buffer < 75%
        adapter.handle_flow_control(0x01)
        self.assertFalse(adapter.paused_by_flow_control)
        self.assertTrue(adapter.send(b"\x03"))

    def test_two_phase_commit_gesture_abort(self):
        aborted = [False]
        adapter = ActiveLookAdapter(transport=lambda b: None, model="ENGO 3")
        
        adapter.arm_two_phase_abort("Bedtime Routine", countdown_s=5, on_abort=lambda: aborted.__setitem__(0, True))
        self.assertIsNotNone(adapter.active_abort_handler)
        
        # User waves hand in front of ENGO glasses (gesture 0x01)
        res = adapter.handle_gesture(0x01)
        self.assertEqual(res["status"], "ABORT_TRIGGERED")
        self.assertTrue(aborted[0])
        self.assertIsNone(adapter.active_abort_handler)

    def test_discovery_schema_conformity(self):
        adapter = ActiveLookAdapter(model="ENGO 3 Titanium")
        disc = adapter.discover()
        self.assertEqual(disc["status"], "READY")
        dev = disc["devices"][0]
        self.assertEqual(dev["category"], "hud")
        self.assertEqual(dev["facts"]["resolution"], "304x256")
        self.assertTrue(dev["facts"]["color_support"])
        self.assertIn("hud_notify", dev["capabilities"])

    def test_layout_and_page_command_builders(self):
        # 1. Hold Flush
        hold_pkt = cmd_hold_flush(0)
        self.assertEqual(hold_pkt, b"\xFF\x39\x00\x06\x00\xAA")
        flush_pkt = cmd_hold_flush(1)
        self.assertEqual(flush_pkt, b"\xFF\x39\x00\x06\x01\xAA")

        # 2. Layout Save with 17-byte header
        line_sub = cmd_line(0, 0, 50, 0)
        layout_pkt = cmd_layout_save(
            layout_id=3,
            x=10, y=20, width=100, height=40,
            fore_color=15, back_color=0, font=2,
            text_valid=True, text_x=5, text_y=5,
            sub_commands=line_sub
        )
        self.assertEqual(layout_pkt[0], 0xFF)
        self.assertEqual(layout_pkt[1], 0x60)
        self.assertEqual(layout_pkt[-1], 0xAA)
        frames = parse_frames(layout_pkt)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].cmd, 0x60)

        # 3. Page Save & Display
        page_pkt = cmd_page_save(page_id=1, slots=[(3, 10, 20)])
        self.assertEqual(page_pkt[1], 0x80)
        disp_pkt = cmd_page_display(page_id=1, texts=["$$125.4"])
        self.assertEqual(disp_pkt[1], 0x83)
        self.assertIn(b"$$125.4\x00", disp_pkt)

    def test_emulator_layout_and_page_rendering_fidelity(self):
        canvas = HUDCanvas(model="ENGO 3")
        adapter = ActiveLookAdapter(transport=lambda b: canvas.dispatch(b), model="ENGO 3")

        # Step 1: Hold pipeline & clear
        adapter.hold_flush(0)
        adapter.send(cmd_clear())

        # Step 2: Register layout 5 with an embedded separator line
        line_sub = cmd_line(0, 25, 120, 25)
        adapter.save_layout(
            layout_id=5,
            x=20, y=30, width=150, height=60,
            fore_color=15, back_color=0, font=2,
            text_valid=True, text_x=4, text_y=2,
            sub_commands=line_sub
        )

        # Step 3: Register Page 2 referencing layout 5
        adapter.save_page(page_id=2, slots=[(5, 20, 30)])

        # Step 4: Multicast page update
        adapter.display_page(page_id=2, texts=["$$42 KM/H"])

        # Step 5: Flush pipeline
        adapter.hold_flush(1)

        # Verify active bank holds layout and page
        bank = canvas.active_bank
        self.assertIn(5, bank.layouts)
        self.assertIn(2, bank.pages)
        layout = bank.layouts[5]
        self.assertEqual(layout.width, 150)
        self.assertEqual(layout.font, 2)
        self.assertEqual(len(layout.sub_commands), 1)

        # Check optical fill factor is positive and non-zero
        fill = canvas.compute_pixel_fill()
        self.assertGreater(fill, 0.0)
        self.assertLess(fill, 15.0)

    def test_active_look_tcp_server_bridge(self):
        import socket, time
        from src.adapters.activelook_emulator import ActiveLookTCPServer, HUDCanvas

        canvas = HUDCanvas(model="ENGO 3")
        server = ActiveLookTCPServer(canvas, port=7795)
        server.start()

        time.sleep(0.1)

        # Connect client socket
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", 7795))

        # Send clear command (0xFF 0x01 0x00 0xAA)
        client.sendall(bytes([0xFF, 0x01, 0x00, 0xAA]))

        # Send text command "HELLO OPENBRIDGE"
        text_bytes = "HELLO OPENBRIDGE".encode("utf-8")
        frame = bytearray([0xFF, 0x37, 6 + len(text_bytes), 0x00, 0x10, 0x00, 0x20, 0x00, 0x01])
        frame.extend(text_bytes)
        frame.append(0xAA)
        client.sendall(bytes(frame))

        time.sleep(0.1)

        # Check command count increased
        self.assertGreater(canvas._cmd_count, 0)

        # Test broadcast gesture
        server.broadcast_gesture(0x01)
        resp = client.recv(1024)
        self.assertEqual(resp, bytes([0xFF, 0x0A, 0x01, 0x01, 0xAA]))

        client.close()
        server.stop()


if __name__ == "__main__":
    unittest.main()
