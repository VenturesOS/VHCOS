// Vite entry point. Mirrors src/index.js so craco (CRA) and Vite can coexist
// during the migration. Once Vite is the only bundler, delete src/index.js
// and this file becomes the sole entry.
import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { initErrorCapture } from "@/lib/errorCapture";

initErrorCapture();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch(() => {});
  });
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
