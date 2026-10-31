$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$outputDirectory = Join-Path $root 'artifacts'
[void][IO.Directory]::CreateDirectory($outputDirectory)
$files = @(
    '.dockerignore', '.gitignore', 'compose.yaml', 'Dockerfile', 'pyproject.toml',
    'requirements.txt', 'requirements.lock', 'requirements-dev.txt',
    'requirements-portfolio.txt', 'requirements-report.txt', 'requirements-diagnostics.txt',
    '.env.example', 'README.md', 'DATASET.md', 'THIRD_PARTY_NOTICES.md', 'CONTEXT_RESEARCH.md'
)
foreach ($folder in @('app', 'scripts', 'tests', 'licenses', 'docs', 'reports')) {
    $files += Get-ChildItem -LiteralPath (Join-Path $root $folder) -Recurse -File |
        Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]|\.pyc$' } |
        ForEach-Object { $_.FullName.Substring($root.Length + 1).Replace('\','/') }
}
$files = @($files | Sort-Object -Unique)
$listPath = Join-Path $outputDirectory 'SOURCE_FILES.txt'
[IO.File]::WriteAllLines($listPath, $files, [Text.UTF8Encoding]::new($false))
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archivePath = Join-Path $outputDirectory 'slang-inspector-files.zip'
$archiveStream = [IO.File]::Open($archivePath, [IO.FileMode]::Create)
$archive = [IO.Compression.ZipArchive]::new($archiveStream, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($relative in $files) {
        $filePath = Join-Path $root $relative
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $filePath, $relative.Replace('\','/'))
    }
} finally { $archive.Dispose(); $archiveStream.Dispose() }
Write-Host "Packaged $($files.Count) source/document files: $archivePath"
Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
