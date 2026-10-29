param(
    [ValidateRange(1024,65535)][int]$PreferredPort = 18640,
    [switch]$NoBuild
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    Write-Host "Project: $((Get-Location).Path)"
    docker info --format '{{.OSType}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop Linux engine is unavailable.' }

    # Include stopped containers so a later restart does not create a collision.
    $containerIds = @(docker ps -aq)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read Docker containers.' }
    $reservedPorts = [System.Collections.Generic.HashSet[int]]::new()
    $ownRunningPorts = [System.Collections.Generic.HashSet[int]]::new()
    if ($containerIds.Count -gt 0) {
        $containers = docker inspect $containerIds | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Docker port bindings.' }
        foreach ($container in $containers) {
            $ownContainer = $container.Config.Labels.'com.docker.compose.project' -eq 'slang-inspector'
            foreach ($property in $container.HostConfig.PortBindings.psobject.Properties) {
                foreach ($binding in $property.Value) {
                    if ($binding.HostPort) {
                        if ($ownContainer) {
                            if ($container.State.Running) { [void]$ownRunningPorts.Add([int]$binding.HostPort) }
                        } else { [void]$reservedPorts.Add([int]$binding.HostPort) }
                    }
                }
            }
        }
    }
    $selectedPort = $null
    foreach ($candidatePort in $PreferredPort..([Math]::Min(65535, $PreferredPort + 199))) {
        if ($reservedPorts.Contains($candidatePort)) { continue }
        if ($ownRunningPorts.Contains($candidatePort)) { $selectedPort = $candidatePort; break }
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $candidatePort)
        try { $listener.Start(); $selectedPort = $candidatePort; break }
        catch [System.Net.Sockets.SocketException] { continue }
        finally { $listener.Stop() }
    }
    if (-not $selectedPort) { throw 'No free port was found in the requested range.' }
    # Persist only the chosen non-secret setting; no Docker credentials are copied.
    $settings = @()
    if (Test-Path -LiteralPath '.env') {
        $settings = @(Get-Content -LiteralPath '.env' | Where-Object { $_ -notmatch '^\s*SLANG_PORT\s*=' })
    }
    $settings += "SLANG_PORT=$selectedPort"
    [IO.File]::WriteAllLines((Join-Path $projectRoot '.env'), $settings, [Text.UTF8Encoding]::new($false))
    $env:SLANG_PORT = [string]$selectedPort
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Invalid Compose configuration.' }
    if ($NoBuild) { docker compose up -d --wait --wait-timeout 180 }
    else { docker compose up -d --build --wait --wait-timeout 180 }
    if ($LASTEXITCODE -ne 0) { throw 'Container startup failed. Run: docker compose logs --tail 80' }
    $url = "http://127.0.0.1:$selectedPort"
    $health = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 10
    if ($health.status -ne 'ok') { throw 'Application health verification failed.' }
    Write-Host "Ready: $url" -ForegroundColor Green
    docker compose ps
}
finally { Pop-Location }
