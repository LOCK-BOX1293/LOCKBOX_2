param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = "C:\Users\Tanmay\Desktop\Hackbyte\LOCKBOX_2"
$extRoot = Join-Path $repoRoot "hackbite-vscode"

Write-Host "Compiling extension..."
Push-Location $extRoot
try {
  npm run compile | Out-Host
} finally {
  Pop-Location
}

$codeExe = $null
$cmd = Get-Command code -ErrorAction SilentlyContinue
if ($cmd) {
  $codeExe = $cmd.Source
}

if (-not $codeExe) {
  $candidates = @(
    "$env:LocalAppData\Programs\Microsoft VS Code\Code.exe",
    "$env:ProgramFiles\Microsoft VS Code\Code.exe",
    "$env:ProgramFiles(x86)\Microsoft VS Code\Code.exe"
  )

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      $codeExe = $candidate
      break
    }
  }
}

if (-not $codeExe) {
  throw "Could not find VS Code executable. Install code CLI or update script paths."
}

$args = @(
  "--new-window",
  "--extensionDevelopmentPath=$extRoot",
  $repoRoot
)

Write-Host "Launching Development Host using: $codeExe"
Write-Host "Args: $($args -join ' ')"

if (-not $DryRun) {
  Start-Process -FilePath $codeExe -ArgumentList $args | Out-Null
}
