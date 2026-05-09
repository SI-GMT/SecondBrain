#!/usr/bin/env pwsh
# Smoke-test stdio direct du serveur MCP secondbrain-memory-kit.
# Bypasse Gemini / Claude Code — parle JSON-RPC au binaire pipx.
#
# Garde stdin ouvert tant qu'on attend les réponses (sinon le serveur se ferme
# sur EOF avant d'avoir répondu aux tool calls).
#
# Usage :
#   pwsh scripts/smoke-mcp.ps1                      # mem_archeo_index_files par défaut
#   pwsh scripts/smoke-mcp.ps1 -ListTools           # tools/list
#   pwsh scripts/smoke-mcp.ps1 -Tool X -Args '{}'   # autre tool
#   pwsh scripts/smoke-mcp.ps1 -TimeoutSec 60       # attente plus longue
#
# Sortie : ce qui arrive sur stdout (JSON-RPC) + stderr (logs / crash) séparé.

[CmdletBinding()]
param(
    [string]$Tool = "mem_archeo_index_files",
    [string]$Args = '{"repo_path":"C:/_PROJETS/IRIS/PROD/USER","project":"ecosav"}',
    [switch]$ListTools,
    [int]$TimeoutSec = 30,
    [string]$ServerExe = "C:\Users\bdubois\pipx\venvs\memory-kit-mcp\Scripts\memory-kit-mcp.exe"
)

if (-not (Test-Path $ServerExe)) {
    Write-Error "Server executable not found: $ServerExe"
    exit 1
}

$initMsg = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
$initNotif = '{"jsonrpc":"2.0","method":"notifications/initialized"}'

if ($ListTools) {
    $callMsg = '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
} else {
    $payload = @{
        jsonrpc = "2.0"
        id      = 2
        method  = "tools/call"
        params  = @{ name = $Tool; arguments = ($Args | ConvertFrom-Json) }
    } | ConvertTo-Json -Compress -Depth 10
    $callMsg = $payload
}

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $ServerExe
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
$psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

$proc = [System.Diagnostics.Process]::Start($psi)

$stdoutBuilder = [System.Text.StringBuilder]::new()
$stderrBuilder = [System.Text.StringBuilder]::new()

$null = Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -Action {
    if ($EventArgs.Data) { [void]$Event.MessageData.AppendLine($EventArgs.Data) }
} -MessageData $stdoutBuilder
$null = Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived -Action {
    if ($EventArgs.Data) { [void]$Event.MessageData.AppendLine($EventArgs.Data) }
} -MessageData $stderrBuilder

$proc.BeginOutputReadLine()
$proc.BeginErrorReadLine()

# Send the 3 messages, with a small flush between each.
$proc.StandardInput.WriteLine($initMsg)
$proc.StandardInput.Flush()
Start-Sleep -Milliseconds 200
$proc.StandardInput.WriteLine($initNotif)
$proc.StandardInput.Flush()
Start-Sleep -Milliseconds 200
$proc.StandardInput.WriteLine($callMsg)
$proc.StandardInput.Flush()

# Wait up to TimeoutSec for an `id:2` response in stdout, then close stdin
# to let the server exit gracefully.
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$gotIdTwo = $false
while ((Get-Date) -lt $deadline) {
    if ($stdoutBuilder.ToString() -match '"id"\s*:\s*2') {
        $gotIdTwo = $true
        break
    }
    if ($proc.HasExited) { break }
    Start-Sleep -Milliseconds 200
}

try { $proc.StandardInput.Close() } catch {}
try { $proc.WaitForExit(2000) | Out-Null } catch {}
if (-not $proc.HasExited) { try { $proc.Kill() } catch {} }

Write-Host "===== STDOUT =====" -ForegroundColor Cyan
Write-Host $stdoutBuilder.ToString()
Write-Host "===== STDERR =====" -ForegroundColor Yellow
Write-Host $stderrBuilder.ToString()
Write-Host "===== STATUS =====" -ForegroundColor Green
if ($gotIdTwo) {
    Write-Host "OK : received id:2 response within ${TimeoutSec}s"
} else {
    Write-Host "WARN : no id:2 response within ${TimeoutSec}s (server hung or crashed)"
}
Write-Host "Exit code : $($proc.ExitCode)"
