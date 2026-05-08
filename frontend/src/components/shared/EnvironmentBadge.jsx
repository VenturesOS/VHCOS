import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";

export default function EnvironmentBadge() {
  const [env, setEnv] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem("vhc_token");
    if (!token) return;
    fetch(`/api/system-health/env-info`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((data) => {
        if (data && !data.is_production) setEnv(data.environment);
      });
  }, []);

  if (!env) return null;

  return (
    <div
      className="fixed top-0 left-0 right-0 z-[100] flex items-center justify-center gap-2 bg-amber-500 text-white text-xs font-semibold py-1 select-none pointer-events-none"
      data-testid="environment-badge"
    >
      <AlertTriangle className="w-3.5 h-3.5" />
      <span>
        {env.toUpperCase()} MODE — DATA MAY NOT MATCH LIVE
      </span>
    </div>
  );
}
