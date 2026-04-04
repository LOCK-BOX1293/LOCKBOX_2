# Hackbite VS Code Extension (V1)

This extension integrates VS Code with the local Hackbite FastAPI backend (`http://localhost:8081` by default).

## Implemented now

- `Hackbite: Index Workspace` command
- `Hackbite: Ask a Question` webview panel (retrieval chunks + confidence)
- CodeLens `Ask Hackbite` above functions/classes in supported languages
- Hover summaries (one-line, cached) for symbols in supported languages
- Sidebar `Hackbite -> Code Symbols` tree (file -> symbol) with click-to-reveal
- `Hackbite: Open Code Map` basic graph overview panel
- Auto repo detection from git origin URL (stable hashed repo id)
- Status bar states for indexing and backend availability
- Optional auto-index on startup when no successful index exists
- Debounced incremental indexing on file save (`hackbite.autoIndex=true`)

## Local run

1. Open this folder in VS Code: `LOCKBOX_2/hackbite-vscode`
2. Run `npm install`
3. Run `npm run compile`
4. Press `F5` to launch Extension Development Host

## Settings

- `hackbite.backendUrl` (default `http://localhost:8081`)
- `hackbite.repoBranch` (default `main`)
- `hackbite.autoIndex` (default `true`)
- `hackbite.role`
- `hackbite.apiKey` (optional)
