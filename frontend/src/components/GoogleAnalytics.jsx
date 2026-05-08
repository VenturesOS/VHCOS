import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const GA_ID = "G-MY1EXKECH6";
const PORTAL_PREFIXES = ["/admin", "/recruiter", "/employer", "/candidate"];

let scriptLoaded = false;

function loadGtagScript() {
  if (scriptLoaded) return;
  scriptLoaded = true;

  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer || [];
  window.gtag = function () {
    window.dataLayer.push(arguments);
  };
  window.gtag("js", new Date());
  window.gtag("config", GA_ID, { send_page_view: false });
}

export default function GoogleAnalytics() {
  const location = useLocation();

  useEffect(() => {
    const isPortal = PORTAL_PREFIXES.some((p) =>
      location.pathname.startsWith(p)
    );
    if (isPortal) return;

    loadGtagScript();
    window.gtag("config", GA_ID, { page_path: location.pathname });
  }, [location]);

  return null;
}
