[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$wrapper=(Resolve-Path (Join-Path $PSScriptRoot '../scripts/invoke-claude.ps1')).Path
$mock=(Resolve-Path (Join-Path $PSScriptRoot 'mock-claude.ps1')).Path
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('claude-failure-tests-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($testRoot)
function Assert-True($condition,$message) { if(-not $condition){throw $message} }
$previousMalformed=$env:CLAUDE_DELEGATOR_TEST_MALFORMED
try {
    $env:CLAUDE_DELEGATOR_TEST_MALFORMED='1'
    $run=Join-Path $testRoot 'malformed'
    $caught=$false
    try { & $wrapper -Prompt 'Malformed stream test' -ClaudePath $mock -RunDirectory $run | Out-Null }
    catch { $caught=$true }
    $m=Get-Content -Raw (Join-Path $run 'metadata.json')|ConvertFrom-Json
    $r=Get-Content -Raw (Join-Path $run 'result.json')|ConvertFrom-Json
    Assert-True ($caught -and $m.status -eq 'malformed_stream' -and $m.invalid_stream_line_count -eq 1) 'Malformed stream was not rejected'
    Assert-True ($r.terminal -and -not $r.review_complete -and $r.review) 'Incomplete evidence was not preserved'
    $env:CLAUDE_DELEGATOR_TEST_MALFORMED=$previousMalformed

    foreach($case in @('missing-cli','invalid-revisions')) {
        $run=Join-Path $testRoot $case
        $opts=@{Prompt='Preflight failure test';ClaudePath=$mock;RunDirectory=$run}
        if($case -eq 'missing-cli'){$opts.ClaudePath=Join-Path $testRoot 'missing.exe'}else{$opts.BaseRevision='HEAD'}
        $caught=$false
        try { & $wrapper @opts | Out-Null } catch { $caught=$true }
        $s=Get-Content -Raw (Join-Path $run 'status.json')|ConvertFrom-Json
        $r=Get-Content -Raw (Join-Path $run 'result.json')|ConvertFrom-Json
        Assert-True ($caught -and $s.terminal -and $s.status -eq 'preflight_error') 'Preflight failure has no terminal status'
        Assert-True (-not $s.claude_started -and -not $s.claude_start_attempted -and -not $r.review_complete) 'Preflight failure incorrectly recorded model activity'
    }

    # Load only production functions to inject a stream-open failure after launch.
    $ast=[Management.Automation.Language.Parser]::ParseFile($wrapper,[ref]$null,[ref]$null)
    foreach($f in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){Invoke-Expression $f.Extent.Text}
    $utf8NoBom=New-Object Text.UTF8Encoding($false)
    $script:testChild=$null
    $caught=$false
    try {
        try { Invoke-ClaudeProcess $mock @('--print') 'test' $testRoot @{} 3000 $testRoot $null {param($childId) $script:testChild=[Diagnostics.Process]::GetProcessById($childId)} | Out-Null }
        catch { $caught=$true }
        Assert-True ($caught -and $null -ne $script:testChild) 'Stream failure did not occur after launch'
        Assert-True ($script:testChild.WaitForExit(1000)) 'Child process survived a stream setup failure'
    }
    finally {
        if($null -ne $script:testChild){if(-not $script:testChild.HasExited){$script:testChild.Kill();[void]$script:testChild.WaitForExit(5000)};$script:testChild.Dispose()}
    }
    'All three failure-path regression checks passed.'
}
finally {
    $env:CLAUDE_DELEGATOR_TEST_MALFORMED=$previousMalformed
    $resolved=[IO.Path]::GetFullPath($testRoot)
    $tempPrefix=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\'
    if(-not $resolved.StartsWith($tempPrefix,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'claude-failure-tests-*'){throw 'Unexpected cleanup target'}
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
