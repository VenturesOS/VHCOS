/**
 * TeamsTabsPage — Phase 55.5
 *
 * Historically this page tabbed between two views (Teams + Hierarchy).
 * As of May 2026 the Hierarchy view is folded into the Teams page itself —
 * the "Manage Members" dialog now surfaces the full employer → recruiter
 * tree inline. This wrapper simply renders the Teams page directly so
 * existing routes / sidebar links keep working.
 */
import TeamsPage from './TeamsPage';

export default function TeamsTabsPage() {
  return <TeamsPage />;
}
