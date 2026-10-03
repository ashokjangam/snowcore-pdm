# Parse Synthea C-CDA files and, with -Load, copy RAW.DOCUMENT_SECTION through the Snowflake CLI.
# Credentials stay in the snow connection profile. This script refuses config keys that carry secrets.

[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$Load,
    [switch]$CreateWarehouse,
    [switch]$SelfCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$patient360 = Split-Path $PSScriptRoot -Parent
$repo = Split-Path $patient360 -Parent
if (-not $ConfigPath) {
    $ConfigPath = Join-Path $patient360 'config\patient360.example.json'
}
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Config not found: $ConfigPath"
}

$cfg = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$secretKeys = @(
    'password', 'secret', 'token', 'private_key', 'private_key_passphrase',
    'oauth_client_secret', 'pat', 'access_token'
)
foreach ($key in $secretKeys) {
    $property = $cfg.PSObject.Properties[$key]
    if ($null -ne $property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
        throw "Config contains $key. Refusing to run. Keep credentials in the snow connection profile."
    }
}

function Assert-Ident {
    param([string]$Name, [string]$Label)
    if ($Name -notmatch '^[A-Za-z_][A-Za-z0-9_$]*$') {
        throw "$Label is not a safe SQL identifier: $Name"
    }
}

function Get-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        return @{ Command = 'py'; Prefix = @('-3') }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        return @{ Command = 'python'; Prefix = @() }
    }
    throw 'Python 3 was not found on PATH.'
}

function Invoke-Native {
    param([string]$File, [string[]]$ArgumentList)
    & $File @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$File exited with code $LASTEXITCODE"
    }
}

$parser = Join-Path $PSScriptRoot 'parse_ccda.py'
$ccda = Join-Path $repo 'data\patient-360\ccda'
$patients = Join-Path $repo 'data\patient-360\csv\patients.csv'
$csvDir = Join-Path $repo 'data\patient-360\csv'
$output = Join-Path $patient360 'generated'
$python = Get-Python
$expected = 108
if ($null -ne $cfg.PSObject.Properties['expected_documents']) {
    $expected = [int]$cfg.expected_documents
}

if ($SelfCheck) {
    Invoke-Native -File $python.Command -ArgumentList ($python.Prefix + @($parser, '--self-check'))
}

$parseArgs = $python.Prefix + @(
    $parser,
    '--ccda-dir', $ccda,
    '--patients-csv', $patients,
    '--csv-dir', $csvDir,
    '--output-dir', $output,
    '--expected-documents', "$expected"
)
Invoke-Native -File $python.Command -ArgumentList $parseArgs

$summaryPath = Join-Path $output 'parse_summary.json'
if (-not (Test-Path -LiteralPath $summaryPath)) {
    throw "Parser did not write $summaryPath"
}
$summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($summary.ok -ne $true) {
    throw "Parser validation failed with exit $($summary.exit_code)."
}

if (-not $Load) {
    Write-Output "Parse complete. validation=$($summary.ok) documents=$($summary.documents) rows=$($summary.rows)"
    Write-Output "CSV: $($summary.output_csv)"
    return
}

$snow = Get-Command snow -ErrorAction SilentlyContinue
if ($null -eq $snow) {
    throw 'snow was not found on PATH. Install Snowflake CLI and add a connection before -Load.'
}

$connection = [string]$cfg.snow_connection
$database = [string]$cfg.database
$schema = [string]$cfg.schema
$warehouse = [string]$cfg.warehouse
$role = [string]$cfg.role
$stage = [string]$cfg.stage
$fileFormat = [string]$cfg.file_format
$table = [string]$cfg.table
foreach ($pair in @(
        @{ Name = $database; Label = 'database' },
        @{ Name = $schema; Label = 'schema' },
        @{ Name = $warehouse; Label = 'warehouse' },
        @{ Name = $stage; Label = 'stage' },
        @{ Name = $fileFormat; Label = 'file_format' },
        @{ Name = $table; Label = 'table' }
    )) {
    Assert-Ident -Name $pair.Name -Label $pair.Label
}
if ($role) {
    Assert-Ident -Name $role -Label 'role'
}
if ([string]::IsNullOrWhiteSpace($connection)) {
    throw 'snow_connection is empty. Set it to a Snowflake CLI connection name, not a password.'
}

$createWarehouse = $CreateWarehouse.IsPresent -or ($cfg.create_warehouse -eq $true)
$tokens = @{
    '__DATABASE__' = $database
    '__SCHEMA__' = $schema
    '__WAREHOUSE__' = $warehouse
    '__STAGE__' = $stage
    '__FILE_FORMAT__' = $fileFormat
    '__TABLE__' = $table
}

function Expand-Sql {
    param([string]$RelativePath)
    $text = Get-Content -LiteralPath (Join-Path $PSScriptRoot $RelativePath) -Raw -Encoding UTF8
    foreach ($token in $tokens.Keys) {
        $text = $text.Replace($token, $tokens[$token])
    }
    if ($text -match '__[A-Z_]+__') {
        throw "Unresolved SQL token in $RelativePath"
    }
    $outFile = Join-Path $output ([IO.Path]::GetFileName($RelativePath))
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText($outFile, $text, $utf8)
    return $outFile
}

$ddl = Expand-Sql -RelativePath 'document_section.sql'
$copy = Expand-Sql -RelativePath 'copy_document_section.sql'
if ($createWarehouse) {
    $warehouseSql = @"
CREATE WAREHOUSE IF NOT EXISTS $warehouse
  WAREHOUSE_SIZE = XSMALL
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Patient 360 demo. XS is enough for the Synthea sample.';
"@
    $warehouseFile = Join-Path $output 'create_warehouse.sql'
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText($warehouseFile, $warehouseSql, $utf8)
}

$snowCommon = @('--connection', $connection, '--warehouse', $warehouse, '--database', $database, '--schema', $schema)
if ($role) {
    $snowCommon += @('--role', $role)
}

if ($createWarehouse) {
    Invoke-Native -File 'snow' -ArgumentList (@('sql', '--filename', $warehouseFile) + $snowCommon)
}
Invoke-Native -File 'snow' -ArgumentList (@('sql', '--filename', $ddl) + $snowCommon)

$csvPath = Join-Path $output 'document_section.csv'
if (-not (Test-Path -LiteralPath $csvPath)) {
    throw "Missing parser CSV: $csvPath"
}
$destination = "@$database.$schema.$stage/document_section"
Invoke-Native -File 'snow' -ArgumentList (@(
        'stage', 'copy', $csvPath, $destination,
        '--overwrite', '--no-auto-compress'
    ) + $snowCommon)
Invoke-Native -File 'snow' -ArgumentList (@('sql', '--filename', $copy) + $snowCommon)
Write-Output "Loaded $database.$schema.$table from $csvPath"
