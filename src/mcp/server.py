"""Read-only MCP server over stdio for the OpenBridge device fabric.

Speaks newline-delimited JSON-RPC 2.0 (MCP stdio transport) with three read-only
tools backed by the versioned v2 read model of a RUNNING OpenBridge server over
loopback HTTP. No writes, no primitives, no shell: anything state-changing stays
behind the owner's consent-gated UI. Start OpenBridge first, then point an MCP
client at: python -m src.mcp.server --port 18765
"""
import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener, HTTPRedirectHandler

SERVER_INFO = {'name': 'openbridge-mcp', 'version': '0.1.0'}
SUPPORTED_PROTOCOL_VERSIONS = ('2025-06-18', '2025-03-26', '2024-11-05')
MAX_LINE = 1_000_000
MAX_REPLY = 1_000_000
HTTP_TIMEOUT = 10
SHOW_NAMES = False

TOOLS = (
    {'name': 'openbridge_get_graph', 'path': '/api/v2/graph',
     'description': 'List discovered devices, links and providers from the current OpenBridge graph snapshot. Read-only; run discovery in OpenBridge first.',
     'args': {}},
    {'name': 'openbridge_get_capabilities', 'path': '/api/v2/capabilities',
     'description': 'List per-device capabilities (discovered/observed/readable/verified) with required permissions. Optional device key filters to one device.',
     'args': {'device': 'Device key from openbridge_get_graph (optional).'}},
    {'name': 'openbridge_get_facts', 'path': '/api/v2/facts',
     'description': 'Read verified evidence facts (value, sources, observation time) for one device. Optional source restricts to one reporting source.',
     'args': {'device': 'Device key from openbridge_get_graph (required).',
              'source': 'Source tag such as RELAY:r1 (optional).'}},
)


class _ToolError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    """Redirects are never followed: only the validated loopback base URL is ever contacted."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _ok(mid, result):
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def _err(mid, code, message):
    return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': code, 'message': message}}


def _tool_result(mid, text, is_error):
    result = {'content': [{'type': 'text', 'text': text}]}
    if is_error:
        result['isError'] = True
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def tool_schema(tool):
    props = {k: {'type': 'string', 'description': v} for k, v in tool['args'].items()}
    return {'name': tool['name'], 'description': tool['description'],
            'inputSchema': {'type': 'object', 'properties': props,
                            'required': ['device'] if tool['name'] == 'openbridge_get_facts' else [],
                            'additionalProperties': False},
            'annotations': {'readOnlyHint': True, 'destructiveHint': False,
                            'idempotentHint': True, 'openWorldHint': False}}


def _get(base_url, path, query):
    url = base_url.rstrip('/') + path + (('?' + urlencode(query)) if query else '')
    req = Request(url, headers={'Accept': 'application/json'}, method='GET')
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(req, timeout=HTTP_TIMEOUT) as r:
            raw = r.read(MAX_REPLY + 1)
    except HTTPError as error:
        if 300 <= error.code < 400:   # never follow: a loopback URL must not hand us to another host or port
            raise _ToolError(f'OpenBridge answered with a redirect ({error.code}); redirects are refused.') from None
        detail = error.read(2000).decode('utf-8', 'replace')
        try:
            detail = json.loads(detail).get('error', detail)
        except ValueError:
            pass
        raise _ToolError(f'OpenBridge refused ({error.code}): {detail}') from None
    except (URLError, OSError, TimeoutError) as error:
        raise _ToolError(f'OpenBridge is not reachable at {base_url} (start the server on this port first): {type(error).__name__}') from None
    if len(raw) > MAX_REPLY:
        raise _ToolError('OpenBridge reply exceeded 1 MB; narrow the query.')
    try:
        return json.loads(raw)
    except ValueError:
        raise _ToolError('OpenBridge returned a non-JSON reply.') from None


def call_tool(base_url, mid, params):
    name, args = params.get('name'), params.get('arguments') or {}
    tool = next((t for t in TOOLS if t['name'] == name), None)
    if tool is None:
        return _tool_result(mid, f"Unknown tool {name!r}. Available: {', '.join(t['name'] for t in TOOLS)}.", True)
    if not isinstance(args, dict):
        return _tool_result(mid, 'arguments must be an object.', True)
    if set(args) - set(tool['args']):
        return _tool_result(mid, f'Unexpected arguments {sorted(set(args) - set(tool["args"]))}. Allowed: {sorted(tool["args"]) or "none"}.', True)
    query = {}
    for key in ('device', 'source'):
        if key in args:
            if not isinstance(args[key], str) or not args[key] or len(args[key]) > 256:
                return _tool_result(mid, f'Argument {key!r} must be a non-empty string up to 256 chars.', True)
            query[key] = args[key]
    if tool['name'] == 'openbridge_get_facts' and 'device' not in query:
        return _tool_result(mid, "Argument 'device' is required (a device key from openbridge_get_graph).", True)
    try:
        body = _get(base_url, tool['path'], query)
        if not SHOW_NAMES:
            body = redact_graph(body)
        return _tool_result(mid, json.dumps(body), False)
    except _ToolError as error:
        return _tool_result(mid, str(error), True)


def handle_message(base_url, msg):
    if not isinstance(msg, dict) or msg.get('jsonrpc') != '2.0':
        return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid JSON-RPC 2.0 message'}}
    mid, method, params = msg.get('id'), msg.get('method'), msg.get('params') or {}
    if mid is None:
        return None   # notification: no reply
    if not isinstance(params, dict):
        return _err(mid, -32602, 'params must be an object')
    if method == 'initialize':
        version = params.get('protocolVersion')
        return _ok(mid, {'protocolVersion': version if version in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0],
                         'capabilities': {'tools': {}}, 'serverInfo': dict(SERVER_INFO)})
    if method == 'ping':
        return _ok(mid, {})
    if method == 'tools/list':
        return _ok(mid, {'tools': [tool_schema(t) for t in TOOLS]})
    if method == 'tools/call':
        return call_tool(base_url, mid, params)
    return _err(mid, -32601, f'Unknown method {method!r}')


def serve(base_url, stdin=None, stdout=None):
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    for line in stdin:
        if not line.strip():
            continue
        if len(line) > MAX_LINE:
            stdout.write(json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Line too long'}}) + '\n')
            stdout.flush()
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            stdout.write(json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}) + '\n')
            stdout.flush()
            continue
        try:
            reply = handle_message(base_url, msg)
        except Exception as error:   # never leak tracebacks or drop the loop on client input
            reply = {'jsonrpc': '2.0', 'id': msg.get('id') if isinstance(msg, dict) else None,
                     'error': {'code': -32603, 'message': f'Internal error: {type(error).__name__}'}}
        if reply is not None:
            stdout.write(json.dumps(reply) + '\n')
            stdout.flush()


LOOPBACK = ('127.0.0.1', '::1', 'localhost')


def loopback_only(base_url):
    from urllib.parse import urlsplit
    u = urlsplit(base_url)
    try:
        u.port
    except ValueError:
        raise SystemExit('openbridge-mcp: invalid port in --base-url') from None
    if (u.scheme != 'http' or u.hostname not in LOOPBACK or u.username is not None or u.password is not None
            or u.path not in ('', '/') or u.query or u.fragment):
        raise SystemExit('openbridge-mcp only talks to an OpenBridge server on this machine (http://127.0.0.1:<port>, '
                         'no credentials, path, query or fragment)')
    return base_url.rstrip('/')


def redact_graph(body):
    """Replace the `label` of each entry in a top-level `devices` list with `<category> <n>` unless the owner
    passes --show-names. Scope is deliberately narrow: this covers the graph reply (openbridge_get_graph). It does
    not rewrite capability rows or fact values, which can still contain names a device reports about itself or its
    surroundings (e.g. a Bluetooth advertised name or a network name). It is label minimisation, not anonymisation."""
    counters = {}
    for d in body.get('devices', []) if isinstance(body, dict) else []:
        cat = d.get('category', 'device')
        counters[cat] = counters.get(cat, 0) + 1
        if 'label' in d:
            d['label'] = f'{cat} {counters[cat]}'
    return body


def main(argv=None):
    ap = argparse.ArgumentParser(description='OpenBridge read-only MCP server (stdio). Queries a running OpenBridge over loopback HTTP.')
    ap.add_argument('--base-url', default=None)
    ap.add_argument('--port', type=int, default=18765)
    ap.add_argument('--show-names', action='store_true', help='Send real device labels in graph replies (default: category + ordinal; fact values are not rewritten)')
    args = ap.parse_args(argv)
    global SHOW_NAMES
    SHOW_NAMES = args.show_names
    serve(loopback_only(args.base_url or f'http://127.0.0.1:{args.port}'))


if __name__ == '__main__':
    main()
