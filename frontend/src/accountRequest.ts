import { adminHeaders } from './admin';

// Account-management calls are local API requests, not long-running AI generation.
export async function accountRequest<T>(url: string, method = 'GET', body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, {
      method, cache: 'no-store', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...adminHeaders() },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : `Account request failed (${response.status}). Check the backend is up to date.`);
    }
    return response.status === 204 ? undefined as T : await response.json();
  } catch (error) {
    if (controller.signal.aborted) throw new Error('The backend did not respond within 15 seconds. Check that it is running, then refresh the account list before retrying.');
    if (error instanceof TypeError) throw new Error('Cannot reach the backend. Start FastAPI on port 8000 and refresh the dashboard.');
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}
