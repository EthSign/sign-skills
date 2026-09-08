[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object Text.UTF8Encoding($false)
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$wrapper = Join-Path $repositoryRoot 'scripts\invoke-claude.ps1'
$mockClaude = Join-Path $PSScriptRoot 'mock-claude.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('claude-delegator-durability-test-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($testRoot) | Out-Null

function Assert-True {
    param([bool] $Condition, [string] $Message)
    if (-not $Condition) { throw "Assertion failed: $Message" }
}

function ConvertTo-NativeArgument {
    param([AllowEmptyString()][string] $Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    return '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}

function Start-Wrapper {
    param([string] $RunDirectory, [bool] $Fail)
    $shell = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
    $arguments = @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$wrapper,'-Prompt','Durability regression test','-WorkingDirectory',$repositoryRoot,'-ClaudePath',$mockClaude,'-RunDirectory',$RunDirectory)
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $shell
    $startInfo.Arguments = ($arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.EnvironmentVariables['CLAUDE_DELEGATOR_TEST_DELAY_MS'] = '5000'
    $startInfo.EnvironmentVariables['CLAUDE_DELEGATOR_TEST_EARLY_OUTPUT'] = '1'
    $startInfo.EnvironmentVariables['CLAUDE_DELEGATOR_TEST_ERROR'] = if($Fail){'1'}else{'0'}
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw 'Test wrapper process did not start.' }
    return [pscustomobject]@{
        Process=$process
        StdoutTask=$process.StandardOutput.ReadToEndAsync()
        StderrTask=$process.StandardError.ReadToEndAsync()
    }
}

try {
    $successDirectory = Join-Path $testRoot 'success'
    $successInvocation = Start-Wrapper $successDirectory $false
    $successProcess = $successInvocation.Process
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(20)
        $running = $null
        while ([DateTime]::UtcNow -lt $deadline) {
            $statusPath = Join-Path $successDirectory 'status.json'
            if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
                try {
                    $running = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json
                    if ($running.status -eq 'running') { break }
                }
                catch [IO.IOException] {}
            }
            Start-Sleep -Milliseconds 50
        }
        Assert-True ($null -ne $running -and $running.status -eq 'running') 'status.json reaches running while the wrapper is still active'
        Assert-True ([bool]$running.claude_started) 'running status records that Claude started'
        Assert-True ([int]$running.process_id -gt 0) 'running status records the Claude PID'

        $streamPath = Join-Path $successDirectory 'stream.jsonl'
        $streamDeadline = [DateTime]::UtcNow.AddSeconds(5)
        while ([DateTime]::UtcNow -lt $streamDeadline -and (Get-Item -LiteralPath $streamPath).Length -eq 0) { Start-Sleep -Milliseconds 50 }
        Assert-True ((Get-Item -LiteralPath $streamPath).Length -gt 0) 'Claude output is spooled before process completion'

        Assert-True ($successProcess.WaitForExit(30000)) 'success wrapper exits within the test deadline'
        $successStdout = $successInvocation.StdoutTask.GetAwaiter().GetResult()
        $successStderr = $successInvocation.StderrTask.GetAwaiter().GetResult()
        Assert-True ($successProcess.ExitCode -eq 0) "success wrapper exits zero: $successStderr"
        Assert-True ($successStdout.Contains('CLAUDE_DELEGATION_METADATA=')) 'success stdout includes compact metadata'
    }
    finally { $successProcess.Dispose() }

    $successStatus = Get-Content -Raw -LiteralPath (Join-Path $successDirectory 'status.json') | ConvertFrom-Json
    $successResult = Get-Content -Raw -LiteralPath (Join-Path $successDirectory 'result.json') | ConvertFrom-Json
    $successMetadata = Get-Content -Raw -LiteralPath (Join-Path $successDirectory 'metadata.json') | ConvertFrom-Json
    Assert-True ($successStatus.status -eq 'success') 'success status is terminal'
    Assert-True ([bool]$successResult.terminal -and [bool]$successResult.review_complete) 'success result is terminal and complete'
    Assert-True ($successMetadata.prompt_sha256 -match '^[0-9a-f]{64}$') 'metadata contains a prompt hash'
    Assert-True (-not ($successMetadata.PSObject.Properties.Name -contains 'prompt')) 'metadata does not persist prompt text'

    $errorDirectory = Join-Path $testRoot 'error'
    $previousDelay = $env:CLAUDE_DELEGATOR_TEST_DELAY_MS
    $previousEarly = $env:CLAUDE_DELEGATOR_TEST_EARLY_OUTPUT
    $previousError = $env:CLAUDE_DELEGATOR_TEST_ERROR
    $errorCaught = $false
    try {
        $env:CLAUDE_DELEGATOR_TEST_DELAY_MS = '0'
        $env:CLAUDE_DELEGATOR_TEST_EARLY_OUTPUT = '1'
        $env:CLAUDE_DELEGATOR_TEST_ERROR = '1'
        try { & $wrapper -Prompt 'Durability failure regression test' -WorkingDirectory $repositoryRoot -ClaudePath $mockClaude -RunDirectory $errorDirectory | Out-Null }
        catch { $errorCaught = $true }
    }
    finally {
        $env:CLAUDE_DELEGATOR_TEST_DELAY_MS = $previousDelay
        $env:CLAUDE_DELEGATOR_TEST_EARLY_OUTPUT = $previousEarly
        $env:CLAUDE_DELEGATOR_TEST_ERROR = $previousError
    }
    Assert-True $errorCaught 'Claude-originated failure is surfaced to the caller'
    $errorResult = Get-Content -Raw -LiteralPath (Join-Path $errorDirectory 'result.json') | ConvertFrom-Json
    $errorMetadata = Get-Content -Raw -LiteralPath (Join-Path $errorDirectory 'metadata.json') | ConvertFrom-Json
    Assert-True ([bool]$errorResult.terminal -and -not [bool]$errorResult.review_complete) 'failed result is terminal but incomplete'
    Assert-True ([bool]$errorMetadata.claude_started) 'failed metadata prevents a blind retry'
    Assert-True ($errorResult.review -match 'Recovered test finding') 'partial review text remains recoverable'

    'Durable-run regression tests passed.'
}
finally {
    $resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $resolvedTest = [IO.Path]::GetFullPath($testRoot)
    if ($resolvedTest.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($resolvedTest) -like 'claude-delegator-durability-test-*') {
        for ($attempt=0; $attempt -lt 50 -and (Test-Path -LiteralPath $resolvedTest); $attempt++) {
            try { Remove-Item -LiteralPath $resolvedTest -Recurse -Force }
            catch { if ($attempt -eq 49) { throw }; Start-Sleep -Milliseconds 100 }
        }
    }
}
