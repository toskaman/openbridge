/* SPDX-License-Identifier: Apache-2.0
 * OpenBridge integration kit in the browser: the same rules as src/partner_kit_api.py and src/partner_kit.py,
 * applied to an OpenAPI 3 description. The templates come from data/integrate-kit.json, which the site build exports
 * from partner_kit.py, and tests/unit/test_partner_kit_api.py checks that this file writes the same bytes as the
 * command line. Runs entirely in the page: the description never leaves the browser.
 *   node integrate-core.js --stdin   < {"kit": ..., "openapi": ..., "name": ..., "category": ...}
 */
(function (root) {
  'use strict';
  var own = function (o, k) { return Object.prototype.hasOwnProperty.call(o, k); };
  var isObj = function (x) { return x !== null && typeof x === 'object' && !Array.isArray(x); };
  var isScalar = function (x) { return typeof x === 'string' || typeof x === 'number' || typeof x === 'boolean'; };
  var SCALARS = ['string', 'integer', 'number', 'boolean'];
  var METHODS = ['put', 'patch', 'post'];

  function SpecError(message) { this.name = 'SpecError'; this.message = message; }
  SpecError.prototype = Object.create(Error.prototype);

  function snake(text) {
    var s = String(text == null ? '' : text).replace(/([a-z0-9])([A-Z])/g, '$1_$2');
    s = s.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '').toLowerCase();
    return s.slice(0, 40) || 'value';
  }

  function ref(doc, node) {
    var depth = 0;
    while (isObj(node) && own(node, '$ref')) {
      var r = node.$ref;
      if (depth > 10 || typeof r !== 'string' || r.indexOf('#/') !== 0) throw new SpecError('only local $ref are supported: ' + JSON.stringify(r));
      var cur = doc;
      r.slice(2).split('/').forEach(function (part) {
        part = part.replace(/~1/g, '/').replace(/~0/g, '~');
        cur = isObj(cur) && own(cur, part) ? cur[part] : null;
      });
      if (cur == null) throw new SpecError('unresolved $ref ' + JSON.stringify(r));
      node = cur; depth += 1;
    }
    return node;
  }

  function jsonSchema(doc, content) {
    content = ref(doc, content) || {};
    var mimes = ['application/json', 'application/json; charset=utf-8'];
    for (var i = 0; i < mimes.length; i++) {
      if (isObj(content) && isObj(content[mimes[i]]) && own(content, mimes[i])) return ref(doc, content[mimes[i]].schema || {});
    }
    return null;
  }

  function values(prop) {
    if (Array.isArray(prop.enum) && prop.enum.length && prop.enum.every(isScalar)) return prop.enum.slice();
    var t = prop.type;
    if (t === 'boolean') return [true, false];
    if ((t === 'integer' || t === 'number') && typeof prop.minimum === 'number' && typeof prop.maximum === 'number') {
      var lo = Math.trunc(prop.minimum), hi = Math.trunc(prop.maximum);
      if (lo <= hi && hi - lo <= KIT.max_span) return { min: lo, max: hi };
    }
    return null;
  }

  function defaultOf(prop, vals) {
    var keys = ['default', 'example'];
    for (var i = 0; i < keys.length; i++) if (own(prop, keys[i]) && isScalar(prop[keys[i]])) return prop[keys[i]];
    if (Array.isArray(vals)) return prop.type === 'boolean' ? vals[vals.length - 1] : vals[0];
    if (isObj(vals)) return vals.min;
    var d = { string: '', integer: 0, number: 0, boolean: false };
    return own(d, prop.type) ? d[prop.type] : '';
  }

  function unit(name, prop) {
    if (typeof prop['x-unit'] === 'string') return prop['x-unit'].slice(0, 8);
    return /percent|_pct$/.test(name) ? '%' : '';
  }

  function props(doc, schema) {
    schema = ref(doc, schema || {});
    if (!isObj(schema) || (own(schema, 'type') ? schema.type : 'object') !== 'object' || !isObj(schema.properties)) return null;
    return Object.keys(schema.properties).sort().map(function (k) {
      var v = schema.properties[k];
      return [snake(k), k, isObj(v) ? ref(doc, v) : {}];
    });
  }

  function sorted(o) { var out = {}; Object.keys(o).sort().forEach(function (k) { out[k] = o[k]; }); return out; }
  var lastSeg = function (path) { var p = path.replace(/\/+$/, '').split('/'); return p[p.length - 1]; };

  function apiSpec(doc) {
    var DANGEROUS = new RegExp(KIT.dangerous, 'i');
    if (!isObj(doc) || String(doc.openapi == null ? '' : doc.openapi).indexOf('3') !== 0)
      throw new SpecError('an OpenAPI 3 description (JSON) is needed; convert Swagger 2 or YAML first');
    var paths = doc.paths;
    if (!isObj(paths) || !Object.keys(paths).length) throw new SpecError('the description has no paths');
    var servers = Array.isArray(doc.servers) ? doc.servers : [];
    var base = servers.length && isObj(servers[0]) ? (own(servers[0], 'url') ? servers[0].url : '') : '';
    var title = String((isObj(doc.info) && doc.info.title) || 'Device').slice(0, 60);
    var skipped = [], names = Object.keys(paths).sort();

    var gets = [];
    names.forEach(function (path) {
      var op = isObj(paths[path]) ? ref(doc, paths[path]).get : null;
      if (!isObj(op)) return;
      var resp = ref(doc, (op.responses || {})['200'] || {});
      var ps = isObj(resp) ? props(doc, jsonSchema(doc, resp.content || {}) || {}) : null;
      if (path.indexOf('{') !== -1) skipped.push('GET ' + path + ': path parameters are not filled automatically');
      else if (ps && ps.length) gets.push([/state|status/i.test(path) ? 0 : 1, path, ps]);
    });
    if (!gets.length) throw new SpecError('no GET returns a JSON object to read the device state from');
    gets.sort(function (a, b) { return a[0] - b[0] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0); });
    var readPath = gets[0][1], readProps = gets[0][2];
    gets.slice(1).forEach(function (g) { skipped.push('GET ' + g[1] + ': only one state endpoint is read (' + readPath + ')'); });
    var fields = {}, policy = {}, fieldProps = {};
    var SECRET = new RegExp(KIT.secret, 'i');
    readProps.forEach(function (p) {
      var name = p[0], raw = p[1], prop = p[2];
      if (SECRET.test(name)) {
        skipped.push('field ' + raw + ': looks like a secret, never read');
        policy[name] = raw + ' is never read or changed by OpenBridge (found in the API description).';
        return;
      }
      if (SCALARS.indexOf(prop.type) === -1) { skipped.push('field ' + raw + ': not a plain value (object or list)'); return; }
      fields[name] = { key: raw, unit: unit(name, prop), default: defaultOf(prop, values(prop)) };
      fieldProps[name] = raw;
    });

    var writable = {}, commands = {};
    names.forEach(function (path) {
      var item = isObj(paths[path]) ? ref(doc, paths[path]) : {};
      METHODS.forEach(function (method) {
        var op = item[method];
        if (!isObj(op) || !own(item, method)) return;
        var where = method.toUpperCase() + ' ' + path;
        if (path.indexOf('{') !== -1) { skipped.push(where + ': path parameters are not filled automatically'); return; }
        if (DANGEROUS.test(path)) {
          policy[snake(lastSeg(path))] = where + ' is never used by OpenBridge (found in the API description).';
          return;
        }
        var body = ref(doc, op.requestBody || {});
        var hasBody = isObj(body) && Object.keys(body).length > 0;
        var ps = hasBody ? props(doc, jsonSchema(doc, body.content || {}) || {}) : null;
        if (!ps || !ps.length) {
          if (hasBody) { skipped.push(where + ': body is not a JSON object with properties'); return; }
          if (method !== 'post') { skipped.push(where + ': no body'); return; }
          var cname = snake(lastSeg(path));
          if (own(commands, cname) || own(writable, cname)) { skipped.push(where + ': name ' + cname + ' already used'); return; }
          commands[cname] = { values: null, method: 'POST', path: path, body: null };
          return;
        }
        ps.forEach(function (p) {
          var name = p[0], raw = p[1], prop = p[2];
          if (DANGEROUS.test(name)) { policy[name] = raw + ' is never changed by OpenBridge (found in the API description).'; return; }
          if (SCALARS.indexOf(prop.type) === -1) { skipped.push(where + ' field ' + raw + ': not a plain value'); return; }
          var vals = values(prop);
          if (vals === null) { skipped.push(where + ' field ' + raw + ': no enum or minimum/maximum, so no allowlist'); return; }
          if (own(writable, name) || own(commands, name)) { skipped.push(where + ' field ' + raw + ': already mapped'); return; }
          var entry = { values: vals, method: method.toUpperCase(), path: path, body: raw };
          if (own(fields, name)) writable[name] = entry; else commands[name] = entry;
        });
      });
    });
    Object.keys(fields).forEach(function (name) {
      if (DANGEROUS.test(name) && !own(policy, name))
        policy[name] = fieldProps[name] + ' is never changed by OpenBridge (found in the API description).';
    });
    if (!Object.keys(writable).length && !Object.keys(commands).length)
      skipped.push('no bounded setting or command found: the adapter will only read');
    return { title: title, base_url: base, read: { method: 'GET', path: readPath, fields: sorted(fields) },
             writable: sorted(writable), commands: sorted(commands), policy: sorted(policy), skipped: skipped };
  }

  function pylit(v) {
    if (v === true) return 'True';
    if (v === false) return 'False';
    if (v === null || v === undefined) return 'None';
    if (typeof v === 'number') return String(v);
    if (typeof v === 'string')
      return "'" + v.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n').replace(/\r/g, '\\r') + "'";
    if (isObj(v) && Object.keys(v).length === 2 && own(v, 'min') && own(v, 'max')) return 'range(' + v.min + ', ' + (v.max + 1) + ')';
    if (Array.isArray(v)) { var items = v.map(pylit); return items.length === 1 ? '(' + items[0] + ',)' : '(' + items.join(', ') + ')'; }
    if (isObj(v)) return '{' + Object.keys(v).map(function (k) { return pylit(k) + ': ' + pylit(v[k]); }).join(', ') + '}';
    throw new SpecError('cannot write ' + String(v));
  }

  function block(name, mapping, indent) {
    var keys = Object.keys(mapping), pad = new Array((indent || 4) + 1).join(' ');
    if (!keys.length) return name + ' = {}';
    return name + ' = {\n' + keys.map(function (k) { return pad + pylit(k) + ': ' + pylit(mapping[k]) + ','; }).join('\n') + '\n}';
  }

  function mapObj(o, f) { var out = {}; Object.keys(o).forEach(function (k) { out[k] = f(o[k], k); }); return out; }

  function templateValues(spec) {
    var fields = spec.read.fields, pk = Object.keys(spec.policy);
    var md = ['| Read | `GET ' + spec.read.path + '` | ' + (Object.keys(fields).map(function (k) { return '`' + k + '`'; }).join(', ') || '-') + ' |']
      .concat(Object.keys(spec.writable).map(function (k) { var w = spec.writable[k]; return '| Setting `' + k + '` | `' + w.method + ' ' + w.path + '` | read back, exact Undo |'; }))
      .concat(Object.keys(spec.commands).map(function (k) { var c = spec.commands[k]; return '| Command `' + k + '` | `' + c.method + ' ' + c.path + '` | momentary, consent per command |'; }))
      .concat(pk.map(function (k) { return '| Refused `' + k + '` | | ' + spec.policy[k] + ' |'; }));
    return {
      read_block: block('READ', mapObj(fields, function (f) { return f.unit; })),
      writable_block: block('WRITABLE', mapObj(spec.writable, function (w) { return w.values; })),
      commands_block: block('COMMANDS', mapObj(spec.commands, function (c) { return c.values; })),
      policy_block: pk.length ? 'POLICY = {\n' + pk.map(function (k) { return '    (' + pylit(k) + ", '*'): " + pylit(spec.policy[k]) + ','; }).join('\n') + '\n}' : 'POLICY = {}',
      base_url: pylit(spec.base_url),
      read_path: pylit(spec.read.path),
      read_keys: block('READ_KEYS', mapObj(fields, function (f) { return f.key; })),
      write_routes: block('WRITE_ROUTES', mapObj(spec.writable, function (w) { return [w.method, w.path, w.body]; })),
      command_routes: block('COMMAND_ROUTES', mapObj(spec.commands, function (c) { return [c.method, c.path, c.body]; })),
      state_block: block('STATE', mapObj(fields, function (f) { return f.default; }), 4),
      endpoints_md: md.join('\n'),
      skipped_md: spec.skipped.map(function (s) { return '- ' + s; }).join('\n') || '- nothing'
    };
  }

  function format(tpl, v) {
    return tpl.replace(/\{\{|\}\}|\{([a-z_]+)\}/g, function (m, k) {
      if (m === '{{') return '{';
      if (m === '}}') return '}';
      if (!own(v, k)) throw new SpecError('template field ' + k + ' is missing');
      return v[k];
    });
  }

  function slugify(name) {
    var slug = String(name || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    if (!/^[a-z][a-z0-9_]{1,30}$/.test(slug) || KIT.reserved.indexOf(slug) !== -1)
      throw new SpecError('device name must give a short id like "acme_lamp" (letters, digits, underscores; not an existing adapter)');
    return slug;
  }

  function generate(openapi, name, category, title) {
    var spec = apiSpec(openapi);
    var slug = slugify(name);
    category = category || 'device';
    if (!/^[a-z_]{2,24}$/.test(category)) throw new SpecError('category must be a short lowercase word, e.g. lamp, plug, glasses');
    title = String(title || name || slug).trim().slice(0, 60) || slug;
    var v = templateValues(spec);
    v.slug = slug;
    v.cls = slug.split('_').map(function (p) { return p ? p[0].toUpperCase() + p.slice(1) : ''; }).join('');
    v.title = title.split('"').join("'");
    v.category = category;
    v.source = slug.toUpperCase();
    var t = KIT.templates, files = {};
    files['src/adapters/' + slug + '.py'] = KIT.py_header + format(t.adapter, v);
    files['src/adapters/' + slug + '_emulator.py'] = KIT.py_header + format(t.emulator, v);
    files['src/fabric/' + slug + '_ingest.py'] = KIT.py_header + format(t.ingest, v);
    files['tests/partners/test_' + slug + '.py'] = KIT.py_header + format(t.tests, v);
    files['docs/partners/' + slug + '/README.md'] = format(t.readme, v) + KIT.md_footer;
    return { slug: slug, spec: spec, files: files };
  }

  var KIT = null;
  var api = { setKit: function (k) { KIT = k; }, apiSpec: apiSpec, generate: generate, pylit: pylit, SpecError: SpecError };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    if (require.main === module && process.argv.indexOf('--stdin') !== -1) {
      var chunks = [];
      process.stdin.on('data', function (c) { chunks.push(c); });
      process.stdin.on('end', function () {
        var job = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        api.setKit(job.kit);
        var out = generate(job.openapi, job.name, job.category, job.title);
        process.stdout.write(JSON.stringify({ spec: out.spec, files: out.files }));
      });
    }
  } else {
    root.OBKit = api;
  }
})(this);
