/**
 * VHCAnalytics — Phase 56
 *
 * Tiny mount-only component that triggers our first-party analytics tracker
 * on every route change. Drop next to <GoogleAnalytics /> in App.js so it
 * fires for both marketing and portal routes.
 */
import { useAnalytics } from "../hooks/useAnalytics";

export default function VHCAnalytics() {
  useAnalytics();
  return null;
}
