// In-memory only. Never persist administrator credentials in browser storage.
let key = '';
export function setAdminKey(value: string) { key = value; }
export function adminHeaders(): Record<string, string> { return key ? { 'X-Studio-Key': key } : {}; }
