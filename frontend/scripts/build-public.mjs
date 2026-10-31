import { readFile, writeFile, mkdir, cp, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const source = path.join(root, 'public-site');
const output = path.join(root, 'dist-public');
const config = JSON.parse(await readFile(path.join(source, 'site.config.json'), 'utf8'));
const missing = ['operatorName', 'contactEmail', 'siteUrl'].filter(key => !config[key]?.trim());
if (config.contactEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(config.contactEmail)) throw new Error('Set a valid public contactEmail in public-site/site.config.json');
if (config.siteUrl) {
  const url = new URL(config.siteUrl);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') throw new Error('siteUrl must be your public HTTPS origin, without a path or credentials.');
}
if (!/^\d{4}-\d{2}-\d{2}$/.test(config.updatedOn) || Number.isNaN(Date.parse(config.updatedOn))) throw new Error('Set updatedOn to YYYY-MM-DD.');
if (process.argv.includes('--release') && missing.length) throw new Error(`Public release blocked: fill ${missing.join(', ')} in public-site/site.config.json. Preview with npm run build:public.`);
const draft = missing.length > 0;
const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const contact = config.contactEmail
  ? `<a href="mailto:${escape(encodeURIComponent(config.contactEmail).replace('%40','@'))}">${escape(config.contactEmail)}</a>`
  : '<span class="missing-contact">Public contact email is not configured in this preview.</span>';
const template = await readFile(path.join(source, 'layout.html'), 'utf8');
const pages = [
  {file:'home.html', target:'index.html', title:'AI Influencer Studio — A home for your fictional cast', description:'A private creator workspace for fictional personalities, reviewed content drafts, and authorized account connections.', canonical:'/'},
  {file:'terms.html', target:'terms/index.html', title:'Terms of Service — AI Influencer Studio', description:'Terms for the private development version of AI Influencer Studio.', canonical:'/terms/'},
  {file:'privacy.html', target:'privacy/index.html', title:'Privacy Policy — AI Influencer Studio', description:'How AI Influencer Studio handles character data, connected accounts, and stored credentials.', canonical:'/privacy/'},
];
// Only the dedicated output directory is replaced. Never copy dashboard builds, .env files, or configuration.
await rm(output, {recursive:true, force:true});
await mkdir(path.join(output, 'assets'), {recursive:true});
await cp(path.join(source, 'assets'), path.join(output, 'assets'), {recursive:true});
await cp(path.join(source, 'styles.css'), path.join(output, 'styles.css'));
for (const page of pages) {
  let html = template.replace('{{BODY}}', await readFile(path.join(source, page.file), 'utf8'));
  const values = {
    TITLE:escape(page.title), DESCRIPTION:escape(page.description), OPERATOR:escape(config.operatorName || 'Operator details pending'),
    CONTACT:contact, UPDATED:escape(config.updatedOn),
    META:draft ? '<meta name="robots" content="noindex,nofollow">' : `<link rel="canonical" href="${escape(new URL(page.canonical, config.siteUrl).href)}">`,
    PREVIEW:draft ? '<div class="preview-notice" role="status">Configuration preview — operator, public contact, and website details must be completed before publication.</div>' : '',
  };
  for (const [key, value] of Object.entries(values)) html = html.replaceAll(`{{${key}}}`, value);
  if (/\{\{[A-Z]+\}\}/.test(html)) throw new Error('Unresolved public page placeholder');
  const target = path.join(output, page.target);
  await mkdir(path.dirname(target), {recursive:true});
  await writeFile(target, html);
}
await writeFile(path.join(output, 'robots.txt'), draft ? 'User-agent: *\nDisallow: /\n' : 'User-agent: *\nAllow: /\n');
console.log(`Built ${draft ? 'configuration preview' : 'release'}: dist-public (homepage, terms, privacy, icon).`);
if (draft) console.log(`Before publication, configure: ${missing.join(', ')}.`);
