"""§7 stdlib PNG montage (pure functions; no devices, no third-party libs)."""
import unittest

from src.runtime import montage as M


def solid(w, h, rgba):
    return M.encode_png(w, h, bytes(rgba) * (w * h))


class PngCodecTest(unittest.TestCase):
    def test_round_trip_rgba(self):
        raw = solid(3, 2, (10, 20, 30, 255))
        w, h, px = M.decode_png(raw)
        self.assertEqual((w, h), (3, 2))
        self.assertEqual(px, bytes((10, 20, 30, 255)) * 6)

    def test_size_reads_ihdr(self):
        self.assertEqual(M.png_size(solid(7, 5, (0, 0, 0, 255))), (7, 5))

    def test_rejects_non_png(self):
        with self.assertRaises(M.MontageError):
            M.decode_png(b'not a png at all....................')

    def test_rejects_interlaced(self):
        import struct
        import zlib
        ihdr = struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 1)  # interlace = 1
        idat = zlib.compress(b'\x00' + b'\x00' * 16)
        def chunk(t, d):
            return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
        raw = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat)
        with self.assertRaises(M.MontageError):
            M.decode_png(raw)

    def test_rejects_truncated(self):
        with self.assertRaises(M.MontageError):
            M.decode_png(solid(4, 4, (1, 2, 3, 255))[:40])


class CombineTest(unittest.TestCase):
    def test_row_stacks_horizontally(self):
        a = solid(4, 2, (255, 0, 0, 255))
        b = solid(2, 2, (0, 0, 255, 255))
        w, h, px = M.decode_png(M.combine([a, b], layout='row'))
        self.assertEqual((w, h), (6, 2))
        self.assertEqual(px[0:4], bytes((255, 0, 0, 255)))
        self.assertEqual(px[4 * 4:4 * 5], bytes((0, 0, 255, 255)))

    def test_row_pads_shorter_image_with_background(self):
        a = solid(2, 4, (255, 0, 0, 255))
        b = solid(2, 2, (0, 0, 255, 255))
        w, h, px = M.decode_png(M.combine([a, b], layout='row'))
        self.assertEqual((w, h), (4, 4))
        # bottom-right corner = background (default opaque black)
        self.assertEqual(px[(4 * 3 + 3) * 4:(4 * 3 + 4) * 4], bytes((0, 0, 0, 255)))

    def test_grid_tiles_square(self):
        imgs = [solid(2, 2, (i, i, i, 255)) for i in (10, 20, 30, 40)]
        w, h, px = M.decode_png(M.combine(imgs, layout='grid'))
        self.assertEqual((w, h), (4, 4))
        self.assertEqual(px[0], 10)
        self.assertEqual(px[(4 * 2 + 2) * 4], 40)

    def test_grid_with_odd_count_pads_last_cell(self):
        imgs = [solid(2, 2, (9, 9, 9, 255))] * 3
        w, h, px = M.decode_png(M.combine(imgs, layout='grid'))
        self.assertEqual((w, h), (4, 4))
        self.assertEqual(px[(4 * 3 + 3) * 4:(4 * 3 + 4) * 4], bytes((0, 0, 0, 255)))

    def test_empty_list_rejected(self):
        with self.assertRaises(M.MontageError):
            M.combine([])

    def test_too_many_rejected(self):
        with self.assertRaises(M.MontageError):
            M.combine([solid(1, 1, (0, 0, 0, 255))] * 17)

    def test_bad_layout_rejected(self):
        with self.assertRaises(M.MontageError):
            M.combine([solid(1, 1, (0, 0, 0, 255))], layout='diagonal')


if __name__ == '__main__':
    unittest.main()
