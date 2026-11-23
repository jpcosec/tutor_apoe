import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { createHttpClient } from "./core/client";
import { SldbProvider } from "./react/context";
import { WorkbenchShell } from "./app/WorkbenchShell";
import "./styles/paper-tokens.css";

// La superficie legacy (y su app.css) se carga como chunk aparte, solo en `#/legacy`:
// así Vite no inyecta app.css en el bundle principal del Workbench.
const LegacyApp = lazy(() => import("./views/App").then((m) => ({ default: m.App })));

const baseUrl = import.meta.env.VITE_SLDB_URL ?? "/sldb";
const client = createHttpClient(baseUrl);
const useLegacySurface =
  typeof window !== "undefined" && window.location.hash.startsWith("#/legacy");

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <SldbProvider client={client}>
      {useLegacySurface ? (
        <Suspense fallback={null}>
          <LegacyApp />
        </Suspense>
      ) : (
        <WorkbenchShell baseUrl={baseUrl} client={client} />
      )}
    </SldbProvider>
  </StrictMode>,
);
