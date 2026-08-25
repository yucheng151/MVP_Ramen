import { mkdir, readFile, writeFile } from 'node:fs/promises';

const assets = {
  '/': ['text/html; charset=utf-8', await readFile('index.html', 'utf8')],
  '/index.html': ['text/html; charset=utf-8', await readFile('index.html', 'utf8')],
  '/styles.css': ['text/css; charset=utf-8', await readFile('styles.css', 'utf8')],
  '/app.js': ['text/javascript; charset=utf-8', await readFile('app.js', 'utf8')],
};

const worker = `const assets = ${JSON.stringify(assets)};

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const asset = assets[url.pathname];
    if (!asset) {
      return new Response('Not found', { status: 404 });
    }
    return new Response(asset[1], {
      headers: {
        'content-type': asset[0],
        'cache-control': url.pathname === '/' || url.pathname === '/index.html'
          ? 'public, max-age=0, must-revalidate'
          : 'public, max-age=3600',
        'x-content-type-options': 'nosniff',
      },
    });
  },
};
`;

await mkdir('dist/server', { recursive: true });
await writeFile('dist/server/index.js', worker, 'utf8');
console.log('Public site build ready.');
