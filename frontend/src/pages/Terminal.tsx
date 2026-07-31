export default function TerminalPage() {
  // No-op stub. All terminal behavior is owned by <TerminalHost />
  // at the Layout level so the WebSocket and xterm.js instance
  // survive route changes. This page exists only as a route
  // placeholder so App.tsx's <Route element={<TerminalPage />} />
  // has something to render when the URL is /terminal.
  return null;
}
