import { createHash } from 'node:crypto'
import { readdir, readFile, writeFile } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const output = new URL('../dist-offline/', import.meta.url)
const files = (await readdir(output, { recursive: true, withFileTypes: true }))
  .filter(file => file.isFile() && !['offline-worker.js', '_headers'].includes(file.name))
  .map(file => '/' + relative(fileURLToPath(output), join(file.parentPath, file.name)).replaceAll('\\', '/'))
  .sort()

const hash = createHash('sha256')
for (const file of files) {
  hash.update(file)
  hash.update(await readFile(new URL(file.slice(1), output)))
}

await writeFile(new URL('offline-worker.js', output), `const PREFIX = 'zhixueban-offline-';
const CACHE = PREFIX + ${JSON.stringify(hash.digest('hex').slice(0, 16))};
const FILES = ${JSON.stringify(files)};
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith(PREFIX) && key !== CACHE).map(key => caches.delete(key))
  )).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (event.request.mode === 'navigate' && url.pathname === '/') {
    event.respondWith(fetch(event.request, { cache: 'no-cache' }).catch(() => caches.open(CACHE).then(cache => cache.match('/index.html'))));
  } else if (FILES.includes(url.pathname)) {
    event.respondWith(caches.open(CACHE).then(cache => cache.match(event.request)).then(cached => cached || fetch(event.request)));
  }
});\n`, 'utf8')

await writeFile(new URL('_headers', output), `/
  Cache-Control: no-cache
/index.html
  Cache-Control: no-cache
/offline-worker.js
  Cache-Control: no-cache
`, 'utf8')
