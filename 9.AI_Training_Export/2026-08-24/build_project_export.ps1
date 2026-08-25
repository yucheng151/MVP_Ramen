param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)

$exportRoot = $PSScriptRoot
$snapshotRoot = Join-Path $exportRoot 'project_snapshot'
$manifestPath = Join-Path $exportRoot 'manifests\project_file_manifest.csv'

$includeRoots = @(
    'KNOWHOW.md',
    'FB_AutoIPCAction.st',
    '1.PLC\MVP_V2_101',
    '1.PLC\import.csv',
    '1.PLC\mermaid-diagram.svg',
    '2.電路圖',
    '3.HMI\0.0.3',
    '4.IO',
    '5.Robot',
    '6.IPC\0.0.1',
    '6.IPC\0.0.2',
    '7.Ordering\0.0.1',
    '8.TEST_Code'
)

$excludedDirectoryNames = @('__pycache__', '.pytest_cache', 'node_modules', 'logs')
$excludedFilePatterns = @('*.pyc', '*.pyo', '*.tmp', '*.log', '*.~bak')

New-Item -ItemType Directory -Force $snapshotRoot | Out-Null
New-Item -ItemType Directory -Force (Split-Path $manifestPath) | Out-Null

function Test-ExcludedFile([System.IO.FileInfo]$File) {
    foreach ($directory in $File.DirectoryName.Split([System.IO.Path]::DirectorySeparatorChar)) {
        if ($excludedDirectoryNames -contains $directory) { return $true }
    }
    foreach ($pattern in $excludedFilePatterns) {
        if ($File.Name -like $pattern) { return $true }
    }
    return $false
}

foreach ($relativeRoot in $includeRoots) {
    $source = Join-Path $ProjectRoot $relativeRoot
    if (-not (Test-Path -LiteralPath $source)) { continue }

    $item = Get-Item -LiteralPath $source
    if (-not $item.PSIsContainer) {
        $destination = Join-Path $snapshotRoot $relativeRoot
        New-Item -ItemType Directory -Force (Split-Path $destination) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
        continue
    }

    Get-ChildItem -LiteralPath $source -Recurse -File | ForEach-Object {
        if (Test-ExcludedFile $_) { return }
        $relative = $_.FullName.Substring($ProjectRoot.Length).TrimStart('\')
        $destination = Join-Path $snapshotRoot $relative
        New-Item -ItemType Directory -Force (Split-Path $destination) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
    }
}

$textExtensions = @('.md', '.txt', '.py', '.st', '.csv', '.json', '.js', '.mjs', '.html', '.css', '.cmd', '.ps1', '.vbs', '.ini', '.xml', '.yaml', '.yml', '.svg')
$manifest = Get-ChildItem -LiteralPath $snapshotRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($snapshotRoot.Length).TrimStart('\').Replace('\', '/')
    $extension = $_.Extension.ToLowerInvariant()
    $sha = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    [pscustomobject]@{
        path = $relative
        bytes = $_.Length
        sha256 = $sha
        media = if ($textExtensions -contains $extension) { 'text_or_code' } else { 'binary_or_vendor_format' }
        training_use = if ($textExtensions -contains $extension) { 'corpus_candidate' } else { 'reference_only' }
    }
}

$manifest | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding utf8

$summary = [pscustomobject]@{
    generated_at = (Get-Date).ToString('o')
    project_root = $ProjectRoot
    snapshot_files = @($manifest).Count
    snapshot_bytes = ($manifest | Measure-Object bytes -Sum).Sum
    corpus_candidates = @($manifest | Where-Object training_use -eq 'corpus_candidate').Count
    reference_only = @($manifest | Where-Object training_use -eq 'reference_only').Count
}
$summary | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $exportRoot 'manifests\export_summary.json') -Encoding utf8

Write-Output ($summary | ConvertTo-Json -Compress)
