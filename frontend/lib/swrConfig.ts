import type { SWRConfiguration } from "swr";

/** Shared SWR settings for every data hook (lib/hooks.ts, the test page). Not a
 * global <SWRConfig> in _app, so public pages don't download SWR at all. */
export const swrConfig: SWRConfiguration = {
  revalidateOnFocus: true,
  dedupingInterval: 5000,
  errorRetryCount: 2,
  keepPreviousData: true,
  shouldRetryOnError: (err) => {
    // A 4xx (bad request, forbidden, not found, rate limit) won't fix itself.
    try {
      return !JSON.parse(err?.message)?.detail;
    } catch {
      return true;
    }
  },
};
