// Build-time environment, set by deploy/deploy.sh (VITE_APP_ENV = dev | prod). Unset = local `npm run dev`.
// Developer tools (interface editor, data-source badge, debug overlay) are left out of the prod build.
export const APP_ENV = import.meta.env.VITE_APP_ENV || 'local'
export const DEV_TOOLS = APP_ENV !== 'prod'
