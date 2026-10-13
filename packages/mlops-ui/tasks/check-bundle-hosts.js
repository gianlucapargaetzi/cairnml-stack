// Fails the build when the bundle mentions an external host that is not on the list below.
// The bundle may contain strings from third-party libraries (documentation, licences). The
// list names them; anything else is a new host, which needs a decision before it ships.
// Runtime requests to external hosts are blocked by the Content-Security-Policy of /ui-next.
const fs = require('fs');
const path = require('path');

const BUILD = process.argv[2] || path.join(__dirname, '..', 'build');

// Documentation, specifications and licence hosts: text in the bundle, never requested.
const INERT = [
  'w3.org', 'github.com', 'stackoverflow.com', 'stitches.dev', 'radix-ui.com', 'reactjs.org',
  'redux.js.org', 'mozilla.org', 'developer.mozilla.org', 'developers.google.com', 'momentjs.com',
  'plotly.com', 'highcharts.com', 'prosemirror.net', 'get.webgl.org', 'creativecommons.org',
  'aimstack.readthedocs.io', 'aimstack.io', 'community.aimstack.io', 'tablericons.com',
  '30secondsofcode.org', 'bugzilla.mozilla.org', 'gist.github.com', 'colab.research.google.com',
  'babeljs.io', 'babel.dev', 'www.apache.org', 'cldr.unicode.org', 'unicode.org',
  'www.currency-iso.org', 'tc39.es', 'www.iso.org', 'unstats.un.org',
  'npms.io', 'git.io', 'material-ui.com', 'fb.me', 'marked.js.org', 'go.microsoft.com',
  'code.visualstudio.com', 'sass-lang.com', 'www.ietf.org', 'wiki.whatwg.org', 'support.google.com',
  'www.dmoz.org', 'help.yahoo.com', 'www.bing.com', 'drafts.csswg.org', 'www.iana.org',
  'tools.ietf.org', 'www.whatwg.org', 'code.google.com', 'googlechrome.github.io',
  'html.spec.whatwg.org', 'r12a.github.io', 'en.wikipedia.org', 'schema.org', 'json-schema.org',
  'aka.ms', 'bit.ly',
];
// Library strings for map tiles and avatars. The explorer never renders these; the CSP blocks
// the requests if a library ever tries them.
const LIBRARY_TILES = [
  'mapbox.com', 'api.mapbox.com', 'api.mapbox.cn', 'events.mapbox.cn', 'stamen.com',
  'stamen-tiles.a.ssl.fastly.net', 'openstreetmap.org', 'www.openstreetmap.org',
  'carto.com', 'cartodb-basemaps-c.global.ssl.fastly.net', 'secure.gravatar.com',
  'avatars.githubusercontent.com', 'cdn.jsdelivr.net', 'cdn.plot.ly', 'graph.facebook.com',
  'api.skype.com',
];
const ALLOWED = new Set([...INERT, ...LIBRARY_TILES]);

function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return files(full);
    return /\.(js|css|html)$/.test(entry.name) && !entry.name.endsWith('.gz') ? [full] : [];
  });
}

const found = new Map();
for (const file of files(BUILD)) {
  const text = fs.readFileSync(file, 'utf8');
  for (const match of text.matchAll(/https?:\/\/([a-zA-Z0-9.-]+)/g)) {
    const host = match[1].toLowerCase();
    const known = [...ALLOWED].some((a) => host === a || host.endsWith(`.${a}`));
    if (!known) found.set(host, (found.get(host) || 0) + 1);
  }
}

if (found.size) {
  console.error('Unlisted external hosts in the bundle:');
  for (const [host, count] of found) console.error(`  ${host} (${count})`);
  console.error('Decide whether each host is inert, then add it to tasks/check-bundle-hosts.js.');
  process.exit(1);
}
console.log('Bundle hosts: all listed.');
