"""CLI toggle helper: only an exact YES enables (no default, no bypass)."""
import unittest

from dev.pc_full_control import confirm


class ConfirmTest(unittest.TestCase):
    def test_exact_yes_enables(self):
        self.assertTrue(confirm('w', input_fn=lambda _p: 'YES'))

    def test_anything_else_aborts(self):
        for answer in ('yes', 'Y', '', 'NO', 'YES PLEASE', 'y'):
            with self.subTest(answer=answer):
                self.assertFalse(confirm('w', input_fn=lambda _p, a=answer: a))

    def test_surrounding_whitespace_is_tolerated(self):
        self.assertTrue(confirm('w', input_fn=lambda _p: '  YES  '))

    def test_eof_aborts(self):
        def boom(_p):
            raise EOFError

        self.assertFalse(confirm('w', input_fn=boom))


if __name__ == '__main__':
    unittest.main()
