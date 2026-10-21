import useSWR, { SWRConfiguration } from "swr";
import { api } from "./api";
import { useAuth } from "./useAuth";
import { swrConfig } from "./swrConfig";

/**
 * Cached, de-duplicated GET of a backend path (SWR). Going back to a page shows the
 * last data instantly and refreshes it in the background; the same path requested
 * by two components is fetched once. Waits for the session, so the Bearer token is
 * always there. Pass null as the path to skip (e.g. until an id is known).
 *
 *   const { data, error, isLoading, mutate } = useApi("/progress");
 */
export function useApi<T = any>(path: string | null, options?: SWRConfiguration) {
  const { ready, user } = useAuth();
  return useSWR<T>(ready && user && path ? path : null, (p: string) => api(p), { ...swrConfig, ...options });
}
