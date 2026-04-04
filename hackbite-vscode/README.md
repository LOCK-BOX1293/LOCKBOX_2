# Hackbite VS Code Extension (V1)

This extension integrates VS Code with the local Hackbite FastAPI backend (`http://localhost:8081` by default).

## Implemented now

- `Hackbite: Index Workspace` command
- `Hackbite: Ask a Question` webview panel with final answer + citations + evidence
- CodeLens `Ask Hackbite` above functions/classes in supported languages
- Hover summaries (one-line, cached) for symbols in supported languages
- Sidebar `Hackbite -> Code Symbols` tree (file -> symbol) with click-to-reveal
- `Hackbite: Open Code Map` interactive graph panel with node details + focused query
- Auto repo detection from git origin URL (stable hashed repo id)
- `Hackbite: Select Target Repository` lets users index/ask any local repo path
- `Hackbite: Use Workspace Repository` clears explicit target path
- Status bar states for indexing and backend availability
- Optional auto-index on startup when no successful index exists
- Debounced incremental indexing on file save (`hackbite.autoIndex=true`)

## One-Line Run (Dev)

From repo root (`LOCKBOX_2`), run exactly one command:

- Windows (PowerShell): `powershell -ExecutionPolicy Bypass -File .\scripts\run-hackbite-extension.ps1`
- Linux: `bash ./scripts/run-hackbite-extension.sh`
- macOS: `bash ./scripts/run-hackbite-extension.sh`

This installs deps, compiles the extension, and opens a VS Code Extension Development Host.

You do not need to run manual `npm install`, `npm run compile`, `vsce package`, or `code --install-extension` for normal development if you use the one-line dev command above.

## Where to run Hackbite commands

Run commands in the Extension Development Host window (the second VS Code window opened by F5):

- `Hackbite: Index Workspace`
- `Hackbite: Ask a Question`
- `Hackbite: Open Code Map`
- `Hackbite: Select Target Repository`
- `Hackbite: Use Workspace Repository`
- `Hackbite: Show Logs`

If `Hackbite` commands do not appear in Command Palette:

1. Confirm you launched from `LOCKBOX_2/hackbite-vscode` (not repo root)
2. Run `Developer: Reload Window` in the Extension Development Host
3. Run `Hackbite: Show Logs` and check Output channel `Hackbite`
4. In the original debug window, check `Run and Debug` is using `Run Hackbite Extension`

Note: backend is not required for commands to appear. Backend is required only for ask/index/graph API success.

## Settings

- `hackbite.backendUrl` (default `http://localhost:8081`)
- `hackbite.repoBranch` (default `main`)
- `hackbite.targetRepoPath` (default empty; when set, commands use this repo path)
- `hackbite.autoIndex` (default `false`)
- `hackbite.indexTimeoutMs` (default `600000`)
- `hackbite.role`
- `hackbite.apiKey` (optional)

## Package And Install VSIX (Only If Needed)

Use this only when you want to install the extension into your normal VS Code profile (outside Extension Development Host) or share a `.vsix` build.

From `LOCKBOX_2/hackbite-vscode`:

- Windows (PowerShell): `npm install; npm run compile; npx @vscode/vsce package --allow-missing-repository --allow-star-activation; $v=(Get-ChildItem *.vsix | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName; code --install-extension $v --force`
- Linux: `npm install && npm run compile && npx @vscode/vsce package --allow-missing-repository --allow-star-activation && code --install-extension "$(ls -t ./*.vsix | head -n 1)" --force`
- macOS: `npm install && npm run compile && npx @vscode/vsce package --allow-missing-repository --allow-star-activation && code --install-extension "$(ls -t ./*.vsix | head -n 1)" --force`

## One-Line Backend Run

From `LOCKBOX_2/agentic_backend`:

- Windows (PowerShell): `py -m pip install -r requirements.txt; uv run uvicorn app.main:app --reload --port 8081`
- Linux: `python3 -m pip install -r requirements.txt && uv run uvicorn app.main:app --reload --port 8081`
- macOS: `python3 -m pip install -r requirements.txt && uv run uvicorn app.main:app --reload --port 8081`

Frontend display inside `Hackbite: Open Code Map` is auto-started by the extension from `LOCKBOX_2/frontend`.
