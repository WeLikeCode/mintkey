/**
 * Stub for react-router-dom — used only by the jsdom render test harness.
 */
import { vi } from "vitest";

export const navigate = vi.fn();

export const useNavigate = () => navigate;

// Stub useSearchParams: returns an empty URLSearchParams by default.
// Tests that need query params can override via the exported searchParamsMock.
export const searchParamsMock = new URLSearchParams();
export const setSearchParams = vi.fn();
export const useSearchParams = () => [searchParamsMock, setSearchParams] as const;
