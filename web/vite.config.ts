import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GHPAGES_BASE is set by CI when deploying under a subpath
// (https://<user>.github.io/ctespn/); unset locally and on a custom domain.
export default defineConfig({
  plugins: [react()],
  base: process.env.GHPAGES_BASE ?? "/",
});
