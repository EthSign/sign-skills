[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)][string[]] $RemainingArguments,
    [Parameter(ValueFromPipeline = $true)][AllowEmptyString()][string] $InputObject
)

begin {
    [Console]::InputEncoding = New-Object Text.UTF8Encoding($false)
    $inputLines = [Collections.Generic.List[string]]::new()
}
process {
    if ($PSBoundParameters.ContainsKey('InputObject')) { $inputLines.Add($InputObject) }
}
end {
    $stdin = [Console]::In.ReadToEnd()
    if ($stdin) { $inputLines.Add($stdin) }

    if ($RemainingArguments.Count -ge 3 -and $RemainingArguments[0] -eq 'auth' -and $RemainingArguments[1] -eq 'status') {
        [ordered]@{ loggedIn=$true; authMethod='claude.ai'; apiProvider='firstParty'; subscriptionType='pro' } | ConvertTo-Json -Compress
        return
    }
    if ($RemainingArguments -contains '--help') {
        '--setting-sources --no-session-persistence --permission-mode --tools --allowedTools --disallowedTools --mcp-config --max-budget-usd --strict-mcp-config --system-prompt --append-system-prompt --prompt-suggestions --include-partial-messages --output-format --verbose --effort --model --disable-slash-commands --no-chrome'
        return
    }
    if ($RemainingArguments -contains '--version') { '2.1.238 (durability mock)'; return }

    if ($env:CLAUDE_DELEGATOR_TEST_EARLY_OUTPUT -eq '1') {
        [ordered]@{ type='system'; subtype='mock_started' } | ConvertTo-Json -Compress
        [Console]::Out.Flush()
    }
    if ($env:CLAUDE_DELEGATOR_TEST_DELAY_MS) { Start-Sleep -Milliseconds ([int]$env:CLAUDE_DELEGATOR_TEST_DELAY_MS) }

    $review = if ($env:CLAUDE_DELEGATOR_TEST_ERROR -eq '1') {
        '[P1] sample.cs:1 - Recovered test finding. The mocked review intentionally fails after returning partial evidence.'
    }
    else { "No actionable findings`nREVIEW_COMPLETE" }

    [ordered]@{
        type='stream_event'
        event=[ordered]@{ type='content_block_delta'; delta=[ordered]@{ type='text_delta'; text=$review } }
    } | ConvertTo-Json -Depth 8 -Compress
    [ordered]@{
        type='assistant'
        message=[ordered]@{ role='assistant'; content=@([ordered]@{ type='text'; text=$review }) }
    } | ConvertTo-Json -Depth 8 -Compress
    $isError = $env:CLAUDE_DELEGATOR_TEST_ERROR -eq '1'
    $terminal = [ordered]@{
        type='result'; is_error=$isError; subtype=if($isError){'error_mock'}else{'success'}
        num_turns=1; session_id='00000000-0000-0000-0000-000000000001'; total_cost_usd=0
        duration_ms=10; duration_api_ms=5; stop_reason='end_turn'; terminal_reason=if($isError){'mock_error'}else{'success'}
        usage=[ordered]@{ input_tokens=1; output_tokens=1; cache_creation_input_tokens=0; cache_read_input_tokens=0 }
    }
    if (-not $isError) { $terminal.result=$review }
    $terminal | ConvertTo-Json -Depth 8 -Compress
}
