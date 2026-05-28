/**
 * Stub for react-router-dom — used only by the jsdom render test harness.
 */
import { vi } from "vitest";

export const navigate = vi.fn();

export const useNavigate = () => navigate;
