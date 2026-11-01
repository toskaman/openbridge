"""UTF-8 regression: JSON with non-ASCII text must be read as UTF-8.

On Windows the locale default is cp1252, so a bare Path.read_text() mangles
curly quotes (U+201C/U+201D) and fails the HonestyGate-style JSON reads.
Every text read/write in the repo must pass encoding='utf-8'; this test pins
the fixture sensitivity, the fix, and a repo-wide scan so the guard itself
cannot pass vacuously.
"""
import ast
import io
import json
import tempfile
import tokenize
import unittest
from pathlib import Path

CURLY = '“hello”'  # U+201C/U+201D curly quotes
ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ('src', 'dev', 'scripts', 'tests')
TARGETS = {'open', 'read_text', 'write_text', 'fdopen'}


def _call_tokens(tokens, open_index):
    """Token slice of the balanced call starting at the '(' token index."""
    depth = 0
    for j in range(open_index, len(tokens)):
        tok = tokens[j]
        if tok.type == tokenize.OP and tok.string == '(':
            depth += 1
        elif tok.type == tokenize.OP and tok.string == ')':
            depth -= 1
            if depth == 0:
                return tokens[open_index:j + 1]
    raise AssertionError('unbalanced call parens')


def _significant(tokens):
    return [t for t in tokens
            if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT,
                              tokenize.INDENT, tokenize.DEDENT)]


def _callee(tokens, name_index):
    """Dotted callee walking back from a NAME call token ('open', 'os.fdopen',
    or '?.open' when the receiver is a call result like build_opener(...))."""
    parts = [tokens[name_index].string]
    i = name_index - 1
    while i - 1 >= 0 and tokens[i].string == '.' and tokens[i - 1].type == tokenize.NAME:
        parts.append(tokens[i - 1].string)
        i -= 2
    if i >= 0 and tokens[i].string == '.':
        parts.append('?')
    parts.reverse()
    return '.'.join(parts)


def _top_args(call):
    """Split a balanced-call token slice into top-level argument token lists."""
    args, current, depth = [], [], 0
    for tok in call[1:-1]:
        if tok.type == tokenize.OP and tok.string in '([':
            depth += 1
        elif tok.type == tokenize.OP and tok.string in ')]':
            depth -= 1
        if tok.type == tokenize.OP and tok.string == ',' and depth == 0:
            args.append(current)
            current = []
        else:
            current.append(tok)
    if current or len(args):
        args.append(current)
    return [_significant(a) for a in args]


def _string_value(arg):
    if len(arg) == 1 and arg[0].type == tokenize.STRING:
        try:
            return ast.literal_eval(arg[0].string)
        except (SyntaxError, ValueError):
            return None
    return None


def scan_file(path):
    """Return [(line, callee, reason)] bare-locale text-IO violations in file."""
    try:
        tokens = list(tokenize.generate_tokens(
            io.StringIO(path.read_text(encoding='utf-8')).readline))
    except (tokenize.TokenError, SyntaxError):
        return []  # unreadable file: not this guard's job
    sig = _significant(tokens)
    violations = []
    for i, tok in enumerate(sig):
        if tok.type != tokenize.NAME or tok.string not in TARGETS:
            continue
        if i + 1 >= len(sig) or sig[i + 1].string != '(':
            continue  # not a call (def, attribute, import)
        callee = _callee(sig, i)
        call = _call_tokens(sig, i + 1)
        has_encoding = any(t.type == tokenize.NAME and t.string == 'encoding'
                           for t in call)
        if tok.string in ('read_text', 'write_text'):
            if not has_encoding:
                violations.append((tok.start[0], callee, 'no encoding='))
            continue
        # open/fdopen: binary mode is fine, text mode needs encoding=.
        args = _top_args(call)
        is_dotted = '.' in callee
        if callee.endswith('fdopen'):
            mode = _string_value(args[1]) if len(args) > 1 else None
            if mode is None:
                mode = ''  # fd + default text mode
            if 'b' not in mode and not has_encoding:
                violations.append((tok.start[0], callee, 'text fdopen without encoding='))
        elif not is_dotted:
            # bare open(path[, mode]): first arg is the path, second the mode.
            mode = _string_value(args[1]) if len(args) > 1 else ''
            if 'b' not in (mode or '') and not has_encoding:
                violations.append((tok.start[0], callee, 'text open() without encoding='))
        else:
            # Receiver.open(...): a short mode-charset string first arg is a
            # mode (pathlib); anything else (request object, URL, fd flags)
            # is a network/fd-style call (urlopen, Image.open, os.open)
            # with no locale-dependent text mode.
            first = _string_value(args[0]) if args else None
            is_mode = (isinstance(first, str) and len(first) <= 8
                       and first != '' and all(c in 'rwxaubt+' for c in first))
            if is_mode and 'b' not in first and not has_encoding:
                violations.append((tok.start[0], callee, 'text .open() without encoding='))
    return violations


class Utf8ReadRegression(unittest.TestCase):
    def test_curly_quote_json_roundtrips_with_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'q.json'
            p.write_bytes(json.dumps({'note': CURLY}, ensure_ascii=False).encode('utf-8'))
            # Negative control: the cp1252 default on Windows mangles (or raises on)
            # this fixture, so a bare read_text() there would fail the assertion below.
            try:
                mangled = json.loads(p.read_bytes().decode('cp1252'))['note']
            except UnicodeDecodeError:
                mangled = None
            self.assertNotEqual(mangled, CURLY)
            # The fix: an explicit utf-8 read always round-trips.
            self.assertEqual(json.loads(p.read_text(encoding='utf-8'))['note'], CURLY)

    def test_no_bare_locale_text_io_in_repo(self):
        files = [p for d in SCAN_DIRS for p in sorted((ROOT / d).rglob('*.py'))]
        # Anti-vacuity pin: the scan must actually cover the repo.
        self.assertGreater(len(files), 100, 'scan covered too few files: %d' % len(files))
        violations = []
        for path in files:
            for line, callee, reason in scan_file(path):
                violations.append('%s:%d: %s (%s)'
                                  % (path.relative_to(ROOT), line, callee, reason))
        self.assertEqual(violations, [])


if __name__ == '__main__':
    unittest.main()
