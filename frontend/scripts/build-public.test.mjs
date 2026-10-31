import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, cp, mkdir, writeFile, readFile, readdir, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const sourceRoot = fileURLToPath(new URL('../', import.meta.url));
test('public build is separate, escapes public configuration, and gates unconfigured releases', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'studio-public-'));
  try {
    await mkdir(path.join(root, 'scripts'));
    await cp(path.join(sourceRoot,'public-site'),path.join(root,'public-site'),{recursive:true});
    await cp(path.join(sourceRoot,'scripts/build-public.mjs'),path.join(root,'scripts/build-public.mjs'));
    await writeFile(path.join(root,'.env'),'DUMMY_SECRET=must-not-be-published');
    const configPath=path.join(root,'public-site/site.config.json');
    const config={operatorName:'',contactEmail:'',siteUrl:'',updatedOn:'2026-10-31'};
    await writeFile(configPath,JSON.stringify(config));
    const build=(...args)=>spawnSync(process.execPath,[path.join(root,'scripts/build-public.mjs'),...args],{encoding:'utf8'});
    assert.notEqual(build('--release').status,0,'Missing public contact and domain must block a release');
    assert.equal(build().status,0);
    const preview=await readFile(path.join(root,'dist-public/index.html'),'utf8');
    assert.ok(preview.includes('noindex,nofollow'));
    assert.ok(preview.includes('Configuration preview'));
    await writeFile(configPath,JSON.stringify({...config,operatorName:'Example <script>alert(1)</script>',contactEmail:'support@example.invalid',siteUrl:'https://example.invalid'}));
    assert.equal(build('--release').status,0);
    const privacy=await readFile(path.join(root,'dist-public/privacy/index.html'),'utf8');
    assert.ok(privacy.includes('support@example.invalid'));
    assert.ok(privacy.includes('&lt;script&gt;'));
    assert.ok(!privacy.includes('<script>'));
    assert.ok(!privacy.includes('Configuration preview'));
    const files=await readdir(path.join(root,'dist-public'),{recursive:true});
    assert.ok(files.includes('terms/index.html') && files.includes('privacy/index.html'));
    assert.ok(!files.some(file=>file.endsWith('.js')||file.includes('.env')||file.includes('site.config')||file.includes('backend')));
    const allPages=await Promise.all(['index.html','terms/index.html','privacy/index.html'].map(file=>readFile(path.join(root,'dist-public',file),'utf8')));
    assert.ok(allPages.every(html=>!html.includes('must-not-be-published')&&!html.includes('/src/main.tsx')));
  } finally { await rm(root,{recursive:true,force:true}); }
});
