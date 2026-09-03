#!/bin/bash

set -u
set -o pipefail

script_dir=$(cd "$(/usr/bin/dirname "$0")" && pwd -P)
repository_dir=$(cd "$script_dir/.." && pwd -P)
wrapper="$repository_dir/scripts/invoke-claude.sh"
test_root=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/claude-delegator-tests-XXXXXXXX")
test_root=$(cd "$test_root" && pwd -P)
fixture="$test_root/fixture"
rename_fixture="$test_root/rename-fixture"
runtime_temp="$test_root/runtime"
runtime_link="$test_root/runtime-link"
fake_claude="$test_root/claude"
fake_bin="$test_root/fake-bin"
fake_home="$test_root/home"
test_number=0

cleanup() { /bin/rm -rf -- "$test_root"; }
trap cleanup EXIT HUP INT TERM

mkdir -p "$fixture" "$runtime_temp" "$fake_bin"
/bin/ln -s "$runtime_temp" "$runtime_link"

cat > "$fake_claude" <<'FAKE'
#!/bin/bash
set -u

if [ "${1-}" = '--help' ]; then
    if [ "${SLOW_HELP-}" = 1 ]; then
        [ -z "${SLOW_HELP_MARKER-}" ] || : > "$SLOW_HELP_MARKER"
        /bin/sleep 10
    fi
    printf '%s\n' '--setting-sources --no-session-persistence --permission-mode --tools --allowedTools --disallowedTools --mcp-config --strict-mcp-config --max-budget-usd --system-prompt --append-system-prompt --prompt-suggestions --include-partial-messages --output-format --verbose --effort --model --disable-slash-commands --no-chrome'
    exit 0
fi
if [ "${1-}" = '--version' ]; then printf '%s\n' "${FAKE_CLAUDE_VERSION:-2.1.223 (Claude Code)}"; exit 0; fi
if [ "${1-}" = 'auth' ] && [ "${2-}" = 'status' ] && [ "${3-}" = '--json' ]; then
    printf '{"authMethod":"claude.ai","apiProvider":"firstParty","subscriptionType":"max"}\n'
    exit 0
fi

if [ -n "${FAKE_LOG-}" ]; then
    : > "$FAKE_LOG"
    for argument in "$@"; do printf '%s\n' "$argument" >> "$FAKE_LOG"; done
fi
fake_input=$(/bin/cat)
[ -z "${FAKE_LOG-}" ] || printf 'STDIN:%s\n' "$fake_input" >> "$FAKE_LOG"

case "${FAKE_MODE-success}" in
    success)
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","num_turns":1,"session_id":"test-session","result":"No actionable findings\nREVIEW_COMPLETE","usage":{"input_tokens":10,"output_tokens":4}}'
        ;;
    native)
        if [ "${REMOVE_SNAPSHOT_BEFORE_EXIT-}" = 1 ]; then /bin/rm -rf -- "$PWD"; fi
        printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"'"$PWD"'/tracked.txt"}}]}}'
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","num_turns":2,"result":"No actionable findings","usage":{"input_tokens":10,"output_tokens":4}}'
        ;;
    native-isolation)
        [ ! -e "$PWD/../prompt" ] || exit 72
        [ ! -e "$PWD/../metadata.tsv" ] || exit 72
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","num_turns":1,"result":"No actionable findings","usage":{"input_tokens":10,"output_tokens":4}}'
        ;;
    bounded-isolation)
        case "$PWD" in */claude-delegator-analysis-????????????????????????????????/work) ;; *) exit 72 ;; esac
        [ ! -e "$PWD/../prompt" ] || exit 72
        [ ! -e "$PWD/../metadata.tsv" ] || exit 72
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings\nREVIEW_COMPLETE","usage":{"input_tokens":1,"output_tokens":2}}'
        ;;
    native-prototype-tool)
        printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"constructor","input":{}}]}}'
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","num_turns":2,"result":"No actionable findings","usage":{"input_tokens":10,"output_tokens":4}}'
        ;;
    timed-success)
        /bin/sleep 0.2
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings\nREVIEW_COMPLETE","usage":{"input_tokens":1,"output_tokens":1}}'
        ;;
    zero-usage)
        printf '%s\n' '{"type":"assistant","is_meta":true,"message":{"model":"<synthetic>","content":[{"type":"text","text":"No actionable findings"}]}}'
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","num_turns":0,"result":"No actionable findings","usage":{"input_tokens":0,"output_tokens":0,"cache_creation_input_tokens":0,"cache_read_input_tokens":0},"modelUsage":{}}'
        ;;
    auth-failure-used)
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","num_turns":0,"result":"Failed to authenticate. API Error: 401 OAuth access token has expired. Re-authenticate to continue.","usage":{"input_tokens":14,"output_tokens":22489,"cache_creation_input_tokens":98246,"cache_read_input_tokens":190521}}'
        ;;
    invalid-usage)
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings\nREVIEW_COMPLETE","usage":{"input_tokens":"n/a","output_tokens":5}}'
        ;;
    invalid-model-usage)
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings\nREVIEW_COMPLETE","modelUsage":{"claude-test":{"inputTokens":-1,"outputTokens":5,"cacheCreationInputTokens":0,"cacheReadInputTokens":0,"costUSD":0.01}}}'
        ;;
    tool-violation)
        printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"path":"/tmp"}},{"type":"text","text":"No actionable findings\nREVIEW_COMPLETE"}]}}'
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings\nREVIEW_COMPLETE"}'
        ;;
    missing-result)
        printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"text","text":"partial finding"}]}}'
        ;;
    error)
        printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"text","text":"partial finding"}]}}'
        printf '%s\n' '{"type":"result","is_error":true,"subtype":"error_max_budget_usd","result":"partial finding"}'
        exit 1
        ;;
    error-success)
        printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"text","text":"partial finding"}]}}'
        printf '%s\n' '{"type":"result","is_error":true,"subtype":"success","result":"partial finding","usage":{"input_tokens":1,"output_tokens":1}}'
        exit 1
        ;;
    incomplete)
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings"}'
        ;;
    marker-with-trailer)
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"REVIEW_COMPLETE\ntrailing text","usage":{"input_tokens":1,"output_tokens":2}}'
        ;;
    crlf-complete)
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings\r\nREVIEW_COMPLETE\r\n\r\n","usage":{"input_tokens":1,"output_tokens":2}}'
        ;;
    string-content)
        printf '%s\n' '{"type":"assistant","message":{"content":"synthetic assistant status"}}'
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings\nREVIEW_COMPLETE","usage":{"input_tokens":1,"output_tokens":2}}'
        ;;
    string-content-only)
        printf '%s\n' '{"type":"assistant","message":{"content":"synthetic assistant status"}}'
        ;;
    durable-readonly)
        /bin/chmod 500 "$RUN_DIRECTORY_TO_LOCK"
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings\nREVIEW_COMPLETE","usage":{"input_tokens":1,"output_tokens":2}}'
        ;;
    invalid-utf8)
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings\nREVIEW_COMPLETE","usage":{"input_tokens":1,"output_tokens":2}}'
        printf '\377'
        ;;
    large-complete)
        large_payload=$(/usr/bin/awk 'BEGIN { for (i = 0; i < 70000; i++) printf "x" }')
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"REVIEW_COMPLETE\n'"$large_payload"'\nREVIEW_COMPLETE","usage":{"input_tokens":1,"output_tokens":70002}}'
        ;;
    malformed)
        printf '%s\n' 'not-json'
        ;;
    malformed-readonly)
        /bin/chmod 500 "$RUN_DIRECTORY_TO_LOCK"
        printf '%s\n' 'not-json'
        ;;
    slow)
        /bin/sleep 10
        printf '%s\n' '{"type":"result","is_error":false,"subtype":"success","result":"No actionable findings\nREVIEW_COMPLETE"}'
        ;;
    *) exit 70 ;;
esac
FAKE
chmod 755 "$fake_claude"
mkdir -p "$fake_home/.local/bin"
/bin/cp "$fake_claude" "$fake_home/.local/bin/claude"

real_git=$(command -v git)
cat > "$fake_bin/git" <<'FAKE_GIT'
#!/bin/bash
set -u
is_worktree_add=false
is_worktree_remove=false
previous=''
worktree_path=''
for argument in "$@"; do
    if [ "$previous" = worktree ] && [ "$argument" = add ]; then is_worktree_add=true; fi
    if [ "$previous" = worktree ] && [ "$argument" = remove ]; then is_worktree_remove=true; fi
    if [ "$previous" = --detach ]; then worktree_path=$argument; fi
    previous=$argument
done
if [ "$is_worktree_remove" = true ] && [ "${FORCE_CLEANUP_FAILURE-}" = 1 ]; then
    [ -z "${RUN_DIRECTORY_TO_LOCK-}" ] || /bin/chmod 500 "$RUN_DIRECTORY_TO_LOCK"
    exit 71
fi
if [ "$is_worktree_add" = true ] && [ "${FORCE_REGISTERED_WORKTREE_ADD_FAILURE-}" = 1 ]; then
    "$REAL_GIT" "$@" || exit $?
    exit 72
fi
if [ "$is_worktree_add" = true ] && [ "${FORCE_WORKTREE_ADD_FAILURE-}" = 1 ]; then
    /bin/mkdir -p "$worktree_path"
    printf 'partial worktree state\n' > "$worktree_path/partial"
    exit 72
fi
"$REAL_GIT" "$@"
status=$?
if [ "$status" -eq 0 ] && [ "$is_worktree_add" = true ] && [ -n "${MUTATE_FILE-}" ]; then
    printf 'changed during snapshot\n' > "$MUTATE_FILE"
fi
exit "$status"
FAKE_GIT
chmod 755 "$fake_bin/git"

git -C "$fixture" init -q
git -C "$fixture" config user.name 'Claude Delegator Tests'
git -C "$fixture" config user.email 'tests@example.invalid'
printf 'first\n' > "$fixture/tracked.txt"
git -C "$fixture" add tracked.txt
git -C "$fixture" commit -qm initial
base_sha=$(git -C "$fixture" rev-parse HEAD)
printf 'second\n' > "$fixture/tracked.txt"
git -C "$fixture" commit -qam second
head_sha=$(git -C "$fixture" rev-parse HEAD)

mkdir -p "$rename_fixture"
git -C "$rename_fixture" init -q
git -C "$rename_fixture" config user.name 'Claude Delegator Tests'
git -C "$rename_fixture" config user.email 'tests@example.invalid'
printf 'rename me\n' > "$rename_fixture/before.txt"
git -C "$rename_fixture" add before.txt
git -C "$rename_fixture" commit -qm initial
rename_base_sha=$(git -C "$rename_fixture" rev-parse HEAD)
git -C "$rename_fixture" mv before.txt after.txt
git -C "$rename_fixture" commit -qm rename
rename_head_sha=$(git -C "$rename_fixture" rev-parse HEAD)

fail() {
    printf 'not ok %s - %s\n' "$test_number" "$1" >&2
    if [ -n "${current_err-}" ] && [ -s "$current_err" ]; then
        printf '%s\n' '--- wrapper stderr ---' >&2
        /bin/cat "$current_err" >&2
    fi
    if [ -n "${current_out-}" ] && [ -s "$current_out" ]; then
        printf '%s\n' '--- wrapper stdout ---' >&2
        /bin/cat "$current_out" >&2
    fi
    exit 1
}
pass() { printf 'ok %s - %s\n' "$test_number" "$1"; }
next_test() { test_number=$((test_number + 1)); }
assert_contains() { /usr/bin/grep -F -- "$2" "$1" >/dev/null || fail "expected $(/usr/bin/basename "$1") to contain: $2"; }
assert_not_contains() { [ ! -e "$1" ] || ! /usr/bin/grep -F -- "$2" "$1" >/dev/null || fail "expected $(/usr/bin/basename "$1") not to contain: $2"; }
assert_runtime_clean() {
    if /usr/bin/find "$runtime_temp" -maxdepth 1 -type d -name 'claude-delegator-*' | /usr/bin/grep . >/dev/null; then fail 'temporary review state was not cleaned'; fi
}
assert_private_state_clean() {
    if /usr/bin/find "$runtime_temp" -maxdepth 1 -type d -name 'claude-delegator-????????' | /usr/bin/grep . >/dev/null; then fail 'private temporary review state was not cleaned'; fi
}
remove_retained_runtime_state() {
    local retained_path retained_name
    for retained_path in "$runtime_temp"/claude-delegator-*; do
        [ -e "$retained_path" ] || continue
        retained_name=${retained_path##*/}
        case "$retained_name" in
            claude-delegator-????????|claude-delegator-sandbox-????????????????????????????????) /bin/rm -rf -- "$retained_path" ;;
            *) fail "refused to remove unexpected retained test path: $retained_path" ;;
        esac
    done
}

run_wrapper() {
    local mode=$1
    shift
    current_out="$test_root/test-$test_number.out"
    current_err="$test_root/test-$test_number.err"
    current_log="$test_root/test-$test_number.args"
    /usr/bin/env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_USE_BEDROCK -u CLAUDE_CODE_USE_VERTEX -u CLAUDE_CODE_USE_FOUNDRY \
        ANTHROPIC_API_KEY="${TEST_ANTHROPIC_API_KEY-}" CLAUDE_CODE_USE_BEDROCK="${TEST_BEDROCK_OVERRIDE-}" FAKE_MODE=$mode FAKE_LOG=$current_log FAKE_CLAUDE_VERSION="${FAKE_CLAUDE_VERSION-}" TMPDIR="${WRAPPER_TMPDIR-$runtime_temp/}" PATH="${WRAPPER_PATH-$PATH}" REAL_GIT="${REAL_GIT-$real_git}" MUTATE_FILE="${MUTATE_FILE-}" FORCE_CLEANUP_FAILURE="${FORCE_CLEANUP_FAILURE-}" FORCE_WORKTREE_ADD_FAILURE="${FORCE_WORKTREE_ADD_FAILURE-}" FORCE_REGISTERED_WORKTREE_ADD_FAILURE="${FORCE_REGISTERED_WORKTREE_ADD_FAILURE-}" REMOVE_SNAPSHOT_BEFORE_EXIT="${REMOVE_SNAPSHOT_BEFORE_EXIT-}" RUN_DIRECTORY_TO_LOCK="${RUN_DIRECTORY_TO_LOCK-}" "$wrapper" --claude-path "$fake_claude" "$@" >"$current_out" 2>"$current_err"
    current_status=$?
}

next_test
run_wrapper success --prompt 'Review this bounded evidence.' --working-directory "$fixture"
[ "$current_status" -eq 0 ] || fail 'bounded analysis failed'
assert_contains "$current_out" 'REVIEW_COMPLETE'
assert_contains "$current_out" '"status":"success"'
assert_contains "$current_out" '"budget_cap_applied":false'
assert_not_contains "$current_log" '--max-budget-usd'
assert_runtime_clean
pass 'bounded analysis uses subscription-aware settings'

next_test
run_wrapper bounded-isolation --prompt 'Keep bounded analysis in a dedicated scratch directory.' --working-directory "$fixture"
[ "$current_status" -eq 0 ] || fail 'bounded analysis sandbox exposed wrapper-private files'
assert_contains "$current_out" '"status":"success"'
assert_runtime_clean
pass 'bounded analysis uses a dedicated nested scratch directory'

next_test
current_out="$test_root/test-$test_number.out"
current_err="$test_root/test-$test_number.err"
current_log="$test_root/test-$test_number.args"
/usr/bin/env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_USE_BEDROCK -u CLAUDE_CODE_USE_VERTEX -u CLAUDE_CODE_USE_FOUNDRY HOME="$fake_home" PATH='/usr/bin:/bin' FAKE_MODE=success FAKE_LOG="$current_log" TMPDIR="$runtime_temp/" "$wrapper" --prompt 'Discover the native Claude installation.' --working-directory "$fixture" >"$current_out" 2>"$current_err"
current_status=$?
[ "$current_status" -eq 0 ] || fail 'standard native Claude path was not discovered'
assert_contains "$current_out" '"status":"success"'
assert_runtime_clean
pass 'native Claude is discovered at the standard macOS install path'

next_test
relative_path_root="$test_root/relative-path-root"
/bin/mkdir -p "$relative_path_root/bin"
/bin/cp "$fake_claude" "$relative_path_root/bin/claude"
current_out="$test_root/test-$test_number.out"
current_err="$test_root/test-$test_number.err"
current_log="$test_root/test-$test_number.args"
(cd "$relative_path_root" && /usr/bin/env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_USE_BEDROCK -u CLAUDE_CODE_USE_VERTEX -u CLAUDE_CODE_USE_FOUNDRY HOME="$test_root/no-home" PATH='bin:/usr/bin:/bin' FAKE_MODE=success FAKE_LOG="$current_log" TMPDIR="$runtime_temp/" "$wrapper" --prompt 'Resolve Claude from a relative PATH entry.' --working-directory "$fixture" >"$current_out" 2>"$current_err")
current_status=$?
[ "$current_status" -eq 0 ] || fail 'relative PATH Claude discovery failed'
assert_contains "$current_out" '"status":"success"'
assert_runtime_clean
pass 'relative PATH discovery is canonicalized before changing directories'

next_test
run_wrapper timed-success --prompt 'Measure a subsecond review.' --working-directory "$fixture"
[ "$current_status" -eq 0 ] || fail 'subsecond review failed'
assert_not_contains "$current_out" '"elapsed_ms":0'
assert_runtime_clean
pass 'elapsed time retains subsecond precision'

next_test
TEST_ANTHROPIC_API_KEY='test-only-not-a-real-key' run_wrapper success --prompt 'Review API-auth behavior.' --working-directory "$fixture"
[ "$current_status" -eq 0 ] || fail 'API override analysis failed'
assert_contains "$current_out" '"budget_cap_applied":true'
assert_contains "$current_out" '"provider_overrides_detected":["ANTHROPIC_API_KEY"]'
assert_contains "$current_log" '--max-budget-usd'
assert_runtime_clean
pass 'provider override retains the budget cap without exposing its value'

next_test
TEST_BEDROCK_OVERRIDE=' false ' run_wrapper success --prompt 'Ignore a whitespace-padded false provider flag.' --working-directory "$fixture"
[ "$current_status" -eq 0 ] || fail 'false provider override analysis failed'
assert_contains "$current_out" '"budget_cap_applied":false'
assert_contains "$current_out" '"provider_overrides_detected":[]'
assert_not_contains "$current_log" '--max-budget-usd'
assert_runtime_clean
pass 'whitespace-padded false provider flags stay inactive'

next_test
run_wrapper native --prompt 'Review the exact range.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha"
[ "$current_status" -eq 0 ] || fail "commit-range review failed: $(<"$current_err")"
assert_contains "$current_out" '"status":"success_native_review"'
assert_contains "$current_out" '"review_scope":"commit-range"'
assert_contains "$current_log" "/code-review"
assert_runtime_clean
pass 'exact commit range runs through the isolated native reviewer'

next_test
run_wrapper native --prompt 'Count both sides of a rename.' --working-directory "$rename_fixture" --base-revision "$rename_base_sha" --head-revision "$rename_head_sha"
[ "$current_status" -eq 0 ] || fail "rename-range review failed: $(<"$current_err")"
assert_contains "$current_out" '"changed_file_count":2'
assert_runtime_clean
pass 'commit-range metadata counts both rename paths'

next_test
run_wrapper native-isolation --prompt 'Keep wrapper-private state outside the review sandbox.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha"
[ "$current_status" -eq 0 ] || fail 'review sandbox exposed wrapper-private sibling files'
assert_contains "$current_out" '"status":"success_native_review"'
assert_runtime_clean
pass 'review sandbox excludes wrapper-private state'

next_test
worktree_count_before=$(git -C "$fixture" worktree list --porcelain | /usr/bin/grep -c '^worktree ')
FAKE_CLAUDE_VERSION='2.1.222 (Claude Code)' run_wrapper native --prompt 'Reject an old native reviewer before snapshot creation.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha"
[ "$current_status" -ne 0 ] || fail 'old Claude version unexpectedly started a repository review'
assert_contains "$current_err" 'requires Claude Code 2.1.223 or newer'
worktree_count_after=$(git -C "$fixture" worktree list --porcelain | /usr/bin/grep -c '^worktree ')
[ "$worktree_count_after" -eq "$worktree_count_before" ] || fail 'version preflight left a worktree registration behind'
assert_runtime_clean
pass 'repository version checks run before snapshot creation'

next_test
run_wrapper native-prototype-tool --prompt 'Record a denied prototype-named tool.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha"
[ "$current_status" -eq 0 ] || fail 'native diagnostic tool review failed'
assert_contains "$current_out" '"unexpected_tool_calls":["constructor"]'
assert_runtime_clean
pass 'native tool diagnostics do not inherit Object prototype names'

next_test
zero_usage_directory="$test_root/durable-zero-usage"
run_wrapper zero-usage --prompt 'Reject a synthetic zero-usage response.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --run-directory "$zero_usage_directory"
[ "$current_status" -ne 0 ] || fail 'synthetic zero-usage result unexpectedly succeeded'
assert_contains "$current_err" 'no verifiable model usage'
assert_contains "$current_err" '"status":"native_review_no_model_usage"'
assert_contains "$zero_usage_directory/result.json" '"review_complete": false'
assert_contains "$zero_usage_directory/result.json" 'No actionable findings'
assert_runtime_clean
pass 'zero-usage synthetic native results are incomplete'

next_test
run_wrapper auth-failure-used --prompt 'Reject an authentication failure after partial model usage.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha"
[ "$current_status" -ne 0 ] || fail 'positive-usage authentication failure unexpectedly succeeded'
assert_contains "$current_err" 'authentication expired before it produced a review'
assert_contains "$current_err" '"status":"authentication_failed"'
assert_not_contains "$current_err" 'success_native_review'
assert_runtime_clean
pass 'authentication failures remain incomplete after positive model usage'

next_test
run_wrapper invalid-usage --prompt 'Reject malformed usage metadata.' --working-directory "$fixture"
[ "$current_status" -ne 0 ] || fail 'malformed usage metadata unexpectedly succeeded'
assert_contains "$current_err" 'Claude token usage metadata was invalid.'
assert_contains "$current_err" '"status":"malformed_usage_metadata"'
assert_contains "$current_err" 'invalid input_tokens value'
assert_runtime_clean
pass 'malformed token usage fails closed in bounded analysis'

next_test
run_wrapper invalid-model-usage --prompt 'Reject malformed per-model usage metadata.' --working-directory "$fixture"
[ "$current_status" -ne 0 ] || fail 'negative per-model usage unexpectedly succeeded'
assert_contains "$current_err" 'Claude token usage metadata was invalid.'
assert_contains "$current_err" '"status":"malformed_usage_metadata"'
assert_contains "$current_err" 'invalid input_tokens value'
assert_runtime_clean
pass 'malformed per-model token usage fails closed'

next_test
run_wrapper native --prompt 'Inspect the planned invocation.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --dry-run
[ "$current_status" -eq 0 ] || fail 'commit-range dry run failed'
assert_contains "$current_out" '"status": "dry_run"'
assert_contains "$current_out" '"sandbox_cleanup_succeeded": true'
assert_contains "$current_out" '"Prompt": "/code-review high'
[ ! -e "$current_log" ] || fail 'dry run unexpectedly started the review process'
assert_runtime_clean
pass 'dry run performs preflight and removes its exact snapshot'

next_test
dry_run_directory="$test_root/durable-dry-run"
run_wrapper native --prompt 'Return one structured dry-run document.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --dry-run --run-directory "$dry_run_directory"
[ "$current_status" -eq 0 ] || fail 'durable dry run failed'
assert_not_contains "$current_out" 'CLAUDE_DELEGATION_RUN_DIRECTORY='
/usr/bin/osascript -l JavaScript -e 'ObjC.import("Foundation"); function run(argv) { var error = Ref(); var value = $.NSString.stringWithContentsOfFileEncodingError(argv[0], $.NSUTF8StringEncoding, error); if (!value) throw new Error("Could not read JSON output."); JSON.parse(ObjC.unwrap(value)); }' "$current_out" >/dev/null || fail 'durable dry-run output was not one valid JSON document'
assert_contains "$dry_run_directory/result.json" '"review_complete": false'
assert_runtime_clean
pass 'durable dry runs keep stdout as one structured JSON document'

next_test
reused_directory="$test_root/reused-run-directory"
mkdir -p "$reused_directory"
printf 'original status\n' > "$reused_directory/status.json"
printf 'original result\n' > "$reused_directory/result.json"
run_wrapper native --prompt 'Do not overwrite an existing run.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --run-directory "$reused_directory"
[ "$current_status" -ne 0 ] || fail 'non-empty run directory unexpectedly succeeded'
assert_contains "$current_err" 'Run directory must be new or empty'
assert_contains "$reused_directory/status.json" 'original status'
assert_contains "$reused_directory/result.json" 'original result'
pass 'non-empty run directories are rejected without overwriting artifacts'

next_test
cleanup_failure_directory="$test_root/durable-cleanup-publish-failure"
WRAPPER_PATH="$fake_bin:$PATH" REAL_GIT="$real_git" FORCE_CLEANUP_FAILURE=1 RUN_DIRECTORY_TO_LOCK="$cleanup_failure_directory" run_wrapper native --prompt 'Report a cleanup failure.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --dry-run --run-directory "$cleanup_failure_directory"
[ "$current_status" -ne 0 ] || fail 'cleanup failure unexpectedly succeeded'
/bin/chmod 700 "$cleanup_failure_directory"
assert_contains "$current_err" 'review snapshot could not be cleaned up'
assert_contains "$current_err" '"status":"sandbox_cleanup_failed"'
assert_contains "$current_err" '"sandbox_cleanup_succeeded":false'
assert_contains "$current_err" 'Git worktree cleanup failed with exit code 71.'
assert_contains "$current_err" 'Snapshot retained at '
[ "$(/usr/bin/grep -c '^CLAUDE_DELEGATION_METADATA=' "$current_err")" -eq 1 ] || fail 'dry-run cleanup failure emitted duplicate metadata records'
retained_snapshot=$(/usr/bin/find "$runtime_temp" -mindepth 2 -maxdepth 2 -type d -name repository -print -quit)
[ -n "$retained_snapshot" ] || fail 'failed cleanup did not retain the registered worktree'
assert_private_state_clean
"$real_git" -C "$fixture" worktree remove --force "$retained_snapshot"
retained_state=$(/usr/bin/dirname "$retained_snapshot")
case "$retained_state" in "$runtime_temp"/claude-delegator-sandbox-????????????????????????????????) ;; *) fail 'retained sandbox path escaped the test runtime' ;; esac
remove_retained_runtime_state
assert_runtime_clean
pass 'cleanup failures retain registered worktrees and report terminal errors'

next_test
printf 'preflight source\n' > "$fixture/tracked.txt"
preflight_failure_directory="$test_root/durable-preflight-cleanup-failure"
WRAPPER_PATH="$fake_bin:$PATH" REAL_GIT="$real_git" FORCE_CLEANUP_FAILURE=1 MUTATE_FILE="$fixture/tracked.txt" run_wrapper native --prompt 'Publish a terminal preflight cleanup failure.' --working-directory "$fixture" --review-working-tree --run-directory "$preflight_failure_directory"
[ "$current_status" -ne 0 ] || fail 'preflight cleanup failure unexpectedly succeeded'
assert_contains "$current_err" 'working tree changed while its review snapshot was being prepared'
assert_contains "$current_err" 'Snapshot retained at '
assert_contains "$preflight_failure_directory/status.json" '"status": "sandbox_cleanup_failed"'
assert_contains "$preflight_failure_directory/status.json" '"terminal": true'
assert_contains "$preflight_failure_directory/result.json" '"review_complete": false'
assert_private_state_clean
retained_snapshot=$(/usr/bin/find "$runtime_temp" -mindepth 2 -maxdepth 2 -type d -name repository -print -quit)
[ -n "$retained_snapshot" ] || fail 'preflight cleanup failure did not retain the registered worktree'
"$real_git" -C "$fixture" worktree remove --force "$retained_snapshot"
remove_retained_runtime_state
printf 'second\n' > "$fixture/tracked.txt"
assert_runtime_clean
pass 'preflight cleanup failures publish terminal durable status'

next_test
WRAPPER_PATH="$fake_bin:$PATH" WRAPPER_TMPDIR="$runtime_link/" REAL_GIT="$real_git" FORCE_CLEANUP_FAILURE=1 run_wrapper native --prompt 'Detect cleanup failure through a symlinked temp path.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --dry-run
[ "$current_status" -ne 0 ] || fail 'symlinked temp cleanup failure unexpectedly succeeded'
assert_contains "$current_err" 'review snapshot could not be cleaned up'
assert_contains "$current_err" 'Snapshot retained at '
retained_snapshot=$(/usr/bin/find "$runtime_temp" -mindepth 2 -maxdepth 2 -type d -name repository -print -quit)
[ -n "$retained_snapshot" ] || fail 'symlinked temp cleanup failure did not retain the registered worktree'
assert_private_state_clean
"$real_git" -C "$fixture" worktree remove --force "$retained_snapshot"
retained_state=$(/usr/bin/dirname "$retained_snapshot")
case "$retained_state" in "$runtime_temp"/claude-delegator-sandbox-????????????????????????????????) ;; *) fail 'symlinked retained sandbox escaped the test runtime' ;; esac
remove_retained_runtime_state
assert_runtime_clean
pass 'physical temp paths preserve cleanup registration checks'

next_test
WRAPPER_PATH="$fake_bin:$PATH" REAL_GIT="$real_git" FORCE_WORKTREE_ADD_FAILURE=1 run_wrapper native --prompt 'Clean a partial worktree-add failure.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --dry-run
[ "$current_status" -ne 0 ] || fail 'forced worktree-add failure unexpectedly succeeded'
assert_contains "$current_err" 'Git exited with code 72 while adding the review worktree.'
assert_runtime_clean
pass 'partial worktree-add failures clean temporary state'

next_test
worktree_count_before=$(git -C "$fixture" worktree list --porcelain | /usr/bin/grep -c '^worktree ')
WRAPPER_PATH="$fake_bin:$PATH" REAL_GIT="$real_git" FORCE_REGISTERED_WORKTREE_ADD_FAILURE=1 run_wrapper native --prompt 'Clean an ambiguously failed registered worktree.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --dry-run
[ "$current_status" -ne 0 ] || fail 'registered worktree-add failure unexpectedly succeeded'
worktree_count_after=$(git -C "$fixture" worktree list --porcelain | /usr/bin/grep -c '^worktree ')
[ "$worktree_count_after" -eq "$worktree_count_before" ] || fail 'failed worktree add left a Git registration behind'
assert_runtime_clean
pass 'ambiguous worktree-add failures remove Git registrations'

next_test
worktree_count_before=$(git -C "$fixture" worktree list --porcelain | /usr/bin/grep -c '^worktree ')
REMOVE_SNAPSHOT_BEFORE_EXIT=1 run_wrapper native --prompt 'Clean a registered worktree whose directory vanished.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha"
[ "$current_status" -eq 0 ] || fail 'missing snapshot directory cleanup failed'
worktree_count_after=$(git -C "$fixture" worktree list --porcelain | /usr/bin/grep -c '^worktree ')
[ "$worktree_count_after" -eq "$worktree_count_before" ] || fail 'missing snapshot directory left a Git registration behind'
assert_contains "$current_out" '"sandbox_cleanup_succeeded":true'
assert_runtime_clean
pass 'cleanup deregisters worktrees whose directories vanished'

next_test
durable_directory="$test_root/durable-success"
run_wrapper success --prompt 'Persist this bounded review.' --working-directory "$fixture" --run-directory "$durable_directory"
[ "$current_status" -eq 0 ] || fail 'durable bounded analysis failed'
assert_contains "$current_out" "CLAUDE_DELEGATION_RUN_DIRECTORY=$durable_directory"
for artifact in status.json stream.jsonl stderr.log result.json metadata.json; do [ -f "$durable_directory/$artifact" ] || fail "missing durable artifact: $artifact"; done
assert_contains "$durable_directory/status.json" '"status": "success"'
assert_contains "$durable_directory/status.json" '"terminal": true'
assert_contains "$durable_directory/result.json" '"review_complete": true'
assert_contains "$durable_directory/metadata.json" '"schema_version": 3'
assert_contains "$durable_directory/metadata.json" '"prompt_sha256": "'
assert_not_contains "$durable_directory/metadata.json" '"prompt":'
assert_contains "$durable_directory/stream.jsonl" '"type":"result"'
assert_runtime_clean
pass 'durable run directory publishes recoverable terminal artifacts'

next_test
readonly_directory="$test_root/durable-readonly"
RUN_DIRECTORY_TO_LOCK="$readonly_directory" run_wrapper durable-readonly --prompt 'Fail closed when durable output cannot be published.' --working-directory "$fixture" --run-directory "$readonly_directory"
[ "$current_status" -ne 0 ] || fail 'durable publish failure unexpectedly succeeded'
assert_contains "$current_err" 'Could not publish terminal durable results.'
assert_contains "$current_err" '<incomplete_claude_review>'
assert_not_contains "$current_out" 'No actionable findings'
/bin/chmod 700 "$readonly_directory"
assert_runtime_clean
pass 'durable publish failures never print a successful review'

next_test
preflight_signal_directory="$test_root/durable-preflight-signal"
current_out="$test_root/test-$test_number.out"
current_err="$test_root/test-$test_number.err"
current_log="$test_root/test-$test_number.args"
SLOW_HELP=1 FAKE_MODE=native FAKE_LOG="$current_log" TMPDIR="$runtime_temp/" "$wrapper" --claude-path "$fake_claude" --prompt 'Interrupt during preflight.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --run-directory "$preflight_signal_directory" >"$current_out" 2>"$current_err" &
preflight_signal_pid=$!
preflight_status_ready=false
preflight_attempt=0
while [ "$preflight_attempt" -lt 100 ]; do
    if [ -f "$preflight_signal_directory/status.json" ] && /usr/bin/grep -F '"status": "preflight"' "$preflight_signal_directory/status.json" >/dev/null; then preflight_status_ready=true; break; fi
    preflight_attempt=$((preflight_attempt + 1))
    /bin/sleep 0.1
done
[ "$preflight_status_ready" = true ] || fail 'preflight signal fixture never initialized durable status'
/bin/kill -TERM "$preflight_signal_pid"
wait "$preflight_signal_pid"
preflight_signal_status=$?
[ "$preflight_signal_status" -ne 0 ] || fail 'preflight signal unexpectedly exited zero'
assert_contains "$preflight_signal_directory/status.json" '"status": "interrupted"'
assert_contains "$preflight_signal_directory/status.json" '"terminal": true'
assert_contains "$preflight_signal_directory/status.json" '"claude_started": false'
assert_contains "$preflight_signal_directory/result.json" '"review_complete": false'
assert_runtime_clean
pass 'signals during preflight publish terminal interrupted status'

next_test
signal_marker="$test_root/no-directory-signal-started"
current_out="$test_root/test-$test_number.out"
current_err="$test_root/test-$test_number.err"
SLOW_HELP=1 SLOW_HELP_MARKER="$signal_marker" FAKE_MODE=native TMPDIR="$runtime_temp/" "$wrapper" --claude-path "$fake_claude" --prompt 'Interrupt without durable output.' --working-directory "$fixture" >"$current_out" 2>"$current_err" &
no_directory_signal_pid=$!
signal_marker_ready=false
signal_marker_attempt=0
while [ "$signal_marker_attempt" -lt 100 ]; do
    if [ -f "$signal_marker" ]; then signal_marker_ready=true; break; fi
    signal_marker_attempt=$((signal_marker_attempt + 1))
    /bin/sleep 0.1
done
[ "$signal_marker_ready" = true ] || fail 'no-directory signal fixture never entered Claude preflight'
/bin/kill -TERM "$no_directory_signal_pid"
wait "$no_directory_signal_pid"
no_directory_signal_status=$?
[ "$no_directory_signal_status" -ne 0 ] || fail 'no-directory signal unexpectedly exited zero'
assert_contains "$current_err" 'CLAUDE_DELEGATION_METADATA='
assert_contains "$current_err" '"status":"interrupted"'
assert_contains "$current_err" '"claude_started":false'
assert_runtime_clean
pass 'signals emit interrupted metadata without a run directory'

next_test
signal_directory="$test_root/durable-signal"
current_out="$test_root/test-$test_number.out"
current_err="$test_root/test-$test_number.err"
current_log="$test_root/test-$test_number.args"
FAKE_MODE=slow FAKE_LOG="$current_log" TMPDIR="$runtime_temp/" "$wrapper" --claude-path "$fake_claude" --prompt 'Interrupt this native review.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --run-directory "$signal_directory" >"$current_out" 2>"$current_err" &
signal_wrapper_pid=$!
signal_running=false
signal_attempt=0
while [ "$signal_attempt" -lt 200 ]; do
    if [ -f "$signal_directory/status.json" ] && /usr/bin/grep -F '"status": "running"' "$signal_directory/status.json" >/dev/null; then signal_running=true; break; fi
    signal_attempt=$((signal_attempt + 1))
    /bin/sleep 0.1
done
[ "$signal_running" = true ] || fail 'signal fixture never reached running state'
/bin/kill -TERM "$signal_wrapper_pid"
/bin/sleep 0.05
/bin/kill -TERM "$signal_wrapper_pid" 2>/dev/null || true
wait "$signal_wrapper_pid"
signal_status=$?
[ "$signal_status" -ne 0 ] || fail 'signaled wrapper unexpectedly exited zero'
assert_contains "$signal_directory/status.json" '"status": "interrupted"'
assert_contains "$signal_directory/status.json" '"terminal": true'
assert_not_contains "$signal_directory/status.json" '"status": "running"'
assert_contains "$signal_directory/result.json" '"review_complete": false'
assert_contains "$signal_directory/result.json" 'Claude delegation was interrupted by a signal.'
assert_runtime_clean
pass 'repeated signals publish one terminal interrupted status'

next_test
signal_publish_directory="$test_root/durable-signal-publish-failure"
current_out="$test_root/test-$test_number.out"
current_err="$test_root/test-$test_number.err"
current_log="$test_root/test-$test_number.args"
FAKE_MODE=slow FAKE_LOG="$current_log" TMPDIR="$runtime_temp/" "$wrapper" --claude-path "$fake_claude" --prompt 'Interrupt after making durable output unavailable.' --working-directory "$fixture" --base-revision "$base_sha" --head-revision "$head_sha" --run-directory "$signal_publish_directory" >"$current_out" 2>"$current_err" &
signal_publish_pid=$!
signal_publish_running=false
signal_publish_attempt=0
while [ "$signal_publish_attempt" -lt 200 ]; do
    if [ -f "$signal_publish_directory/status.json" ] && /usr/bin/grep -F '"status": "running"' "$signal_publish_directory/status.json" >/dev/null; then signal_publish_running=true; break; fi
    signal_publish_attempt=$((signal_publish_attempt + 1))
    /bin/sleep 0.1
done
[ "$signal_publish_running" = true ] || fail 'durable-failure signal fixture never reached running state'
/bin/chmod 500 "$signal_publish_directory"
/bin/kill -TERM "$signal_publish_pid"
wait "$signal_publish_pid"
signal_publish_status=$?
/bin/chmod 700 "$signal_publish_directory"
[ "$signal_publish_status" -ne 0 ] || fail 'durable-failure signal unexpectedly exited zero'
assert_contains "$current_err" '"status":"interrupted"'
assert_not_contains "$current_err" '"status":"post_claude_failure"'
[ "$(/usr/bin/grep -c '^CLAUDE_DELEGATION_METADATA=' "$current_err")" -eq 1 ] || fail 'signal durable failure emitted duplicate metadata records'
assert_runtime_clean
pass 'signal publication failures retain one interrupted metadata record'

next_test
run_wrapper native --prompt 'Review an empty range.' --working-directory "$fixture" --base-revision "$head_sha" --head-revision "$head_sha"
[ "$current_status" -eq 0 ] || fail 'empty-range preflight failed'
assert_contains "$current_out" 'No changes found in the requested review scope.'
assert_contains "$current_out" '"status":"no_changes"'
assert_runtime_clean
pass 'empty ranges do not start Claude'

next_test
run_wrapper native --prompt 'Return an empty range as raw JSON.' --working-directory "$fixture" --base-revision "$head_sha" --head-revision "$head_sha" --raw-json
[ "$current_status" -eq 0 ] || fail 'raw empty-range preflight failed'
assert_contains "$current_out" '"claude":null'
assert_contains "$current_out" '"recovered_review":null'
assert_contains "$current_out" '"status":"no_changes"'
assert_not_contains "$current_out" 'CLAUDE_DELEGATION_METADATA='
[ "$(/usr/bin/wc -l < "$current_out" | /usr/bin/tr -d ' ')" -eq 1 ] || fail 'raw empty-range output was not one JSON line'
assert_runtime_clean
pass 'raw empty ranges emit one structured JSON result'

untracked_only_fixture="$test_root/untracked-only-fixture"
/bin/mkdir -p "$untracked_only_fixture"
git -C "$untracked_only_fixture" init -q
git -C "$untracked_only_fixture" config user.name 'Claude Delegator Tests'
git -C "$untracked_only_fixture" config user.email 'tests@example.invalid'
printf 'tracked\n' > "$untracked_only_fixture/tracked.txt"
git -C "$untracked_only_fixture" add tracked.txt
git -C "$untracked_only_fixture" commit -qm initial
untracked_only_name=$'line\nbreak.txt'
printf 'untracked\n' > "$untracked_only_fixture/$untracked_only_name"
untracked_only_file_hash=$(/usr/bin/shasum -a 256 < "$untracked_only_fixture/$untracked_only_name" | /usr/bin/awk '{print $1}')
untracked_only_evidence_hash=$(printf '### UNTRACKED FILE STATE\n{"path":"line\\nbreak.txt","bytes":10,"sha256":"%s"}\n' "$untracked_only_file_hash" | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}')
next_test
run_wrapper native --prompt 'Review only an untracked file.' --working-directory "$untracked_only_fixture" --review-working-tree
[ "$current_status" -eq 0 ] || fail 'untracked-only evidence had a leading separator'
assert_contains "$current_out" '"status":"success_native_review"'
assert_contains "$current_out" "\"diff_sha256\":\"$untracked_only_evidence_hash\""
assert_runtime_clean
pass 'newline-named untracked evidence uses a canonical content hash'

printf 'staged addition\n' > "$fixture/[staged].txt"
/bin/mv "$fixture/tracked.txt" "$fixture/renamed tracked.txt"
git -C "$fixture" --literal-pathspecs add -A -- tracked.txt 'renamed tracked.txt' '[staged].txt'
git -C "$fixture" --literal-pathspecs ls-files --error-unmatch -- '[staged].txt' >/dev/null || fail 'bracketed addition was not staged'
next_test
run_wrapper native --prompt 'Review staged additions and renames.' --working-directory "$fixture" --review-working-tree
[ "$current_status" -eq 0 ] || fail "staged addition and rename review failed: $(<"$current_err")"
assert_contains "$current_out" '"status":"success_native_review"'
assert_contains "$current_out" '"changed_file_count":3'
assert_runtime_clean
pass 'working-tree snapshots preserve staged additions and renames'
git -C "$fixture" reset -q HEAD --
/bin/mv "$fixture/renamed tracked.txt" "$fixture/tracked.txt"
/bin/rm -f -- "$fixture/[staged].txt"

printf 'tracked and then untracked\n' > "$fixture/index-deleted.txt"
git -C "$fixture" add -- index-deleted.txt
git -C "$fixture" commit -qm 'add index deletion fixture'
git -C "$fixture" rm --cached -q -- index-deleted.txt
next_test
run_wrapper native --prompt 'Review a staged deletion whose path is also untracked.' --working-directory "$fixture" --review-working-tree
[ "$current_status" -eq 0 ] || fail "index deletion collision review failed: $(<"$current_err")"
assert_contains "$current_out" '"status":"success_native_review"'
assert_contains "$current_out" '"changed_file_count":1'
assert_contains "$current_out" '"untracked_file_count":1'
assert_runtime_clean
pass 'snapshots preserve index deletions whose paths are also untracked'
git -C "$fixture" add -- index-deleted.txt
git -C "$fixture" rm -q -- index-deleted.txt
git -C "$fixture" commit -qm 'remove index deletion fixture'

printf 'deleted after staging\n' > "$fixture/deleted-addition.txt"
git -C "$fixture" add -- deleted-addition.txt
/bin/rm -f -- "$fixture/deleted-addition.txt"
next_test
run_wrapper native --prompt 'Reject an addition deleted after staging.' --working-directory "$fixture" --review-working-tree
[ "$current_status" -ne 0 ] || fail 'deleted staged addition unexpectedly succeeded'
assert_contains "$current_err" 'Staged additions deleted from the working tree cannot be frozen safely: deleted-addition.txt'
assert_not_contains "$current_log" '--print'
assert_runtime_clean
pass 'deleted staged additions fail closed before Claude starts'
git -C "$fixture" reset -q HEAD -- deleted-addition.txt

printf 'ignored.bin\n' > "$fixture/.gitignore"
git -C "$fixture" add .gitignore
git -C "$fixture" commit -qm 'add ignored fixture'
printf 'force-added ignored content\n' > "$fixture/ignored.bin"
git -C "$fixture" add -f ignored.bin
next_test
run_wrapper native --prompt 'Review a force-added ignored file.' --working-directory "$fixture" --review-working-tree
[ "$current_status" -eq 0 ] || fail "force-added ignored review failed: $(<"$current_err")"
assert_contains "$current_out" '"status":"success_native_review"'
assert_contains "$current_out" '"changed_file_count":1'
assert_runtime_clean
pass 'snapshots preserve force-added ignored files'
git -C "$fixture" reset -q HEAD -- ignored.bin
/bin/rm -f -- "$fixture/ignored.bin"

submodule_repository="$test_root/submodule-source"
/bin/mkdir -p "$submodule_repository"
git -C "$submodule_repository" init -q
git -C "$submodule_repository" config user.name 'Claude Delegator Tests'
git -C "$submodule_repository" config user.email 'tests@example.invalid'
printf 'first submodule state\n' > "$submodule_repository/state.txt"
git -C "$submodule_repository" add state.txt
git -C "$submodule_repository" commit -qm first
submodule_first=$(git -C "$submodule_repository" rev-parse HEAD)
printf 'second submodule state\n' > "$submodule_repository/state.txt"
git -C "$submodule_repository" commit -qam second
submodule_second=$(git -C "$submodule_repository" rev-parse HEAD)
git -C "$fixture" -c protocol.file.allow=always submodule add -q "$submodule_repository" 'modules/[example]'
git -C "$fixture/modules/[example]" checkout -q "$submodule_first"
git -C "$fixture" --literal-pathspecs add .gitmodules 'modules/[example]'
git -C "$fixture" commit -qm 'add submodule fixture'
git -C "$fixture/modules/[example]" checkout -q "$submodule_second"
next_test
run_wrapper native --prompt 'Review a changed submodule pointer.' --working-directory "$fixture" --review-working-tree
[ "$current_status" -eq 0 ] || fail "changed submodule review failed: $(<"$current_err")"
assert_contains "$current_out" '"status":"success_native_review"'
assert_runtime_clean
pass 'working-tree snapshots preserve clean glob-named submodule pointer changes'
git -C "$fixture/modules/[example]" checkout -q "$submodule_first"

printf 'dirty\n' > "$fixture/tracked.txt"
printf 'space\n' > "$fixture/space name.txt"
printf 'unicode\n' > "$fixture/über.txt"
printf 'glob\n' > "$fixture/[glob].txt"
newline_name=$'line\nbreak.txt'
printf 'newline\n' > "$fixture/$newline_name"

next_test
run_wrapper native --prompt 'Review all current changes.' --working-directory "$fixture" --review-working-tree
[ "$current_status" -eq 0 ] || fail "working-tree review failed: $(<"$current_err")"
assert_contains "$current_out" '"review_scope":"working-tree"'
assert_contains "$current_out" '"untracked_file_count":4'
assert_contains "$current_out" '"sandbox_cleanup_succeeded":true'
assert_runtime_clean
pass 'working-tree snapshot preserves unusual filenames and cleans up'

next_test
WRAPPER_PATH="$fake_bin:$PATH" REAL_GIT="$real_git" MUTATE_FILE="$fixture/tracked.txt" run_wrapper native --prompt 'Detect an unstable source checkout.' --working-directory "$fixture" --review-working-tree
[ "$current_status" -ne 0 ] || fail 'source mutation unexpectedly succeeded'
assert_contains "$current_err" 'working tree changed while its review snapshot was being prepared'
assert_runtime_clean
printf 'dirty\n' > "$fixture/tracked.txt"
pass 'source mutation invalidates the frozen working-tree fingerprint'

next_test
untracked_limit_directory="$test_root/durable-untracked-limit"
run_wrapper native --prompt 'Enforce the untracked ceiling.' --working-directory "$fixture" --review-working-tree --max-untracked-files 0 --run-directory "$untracked_limit_directory"
[ "$current_status" -ne 0 ] || fail 'untracked ceiling unexpectedly succeeded'
assert_contains "$current_err" 'Working tree has 4 untracked files'
assert_contains "$current_err" 'local ceiling is 0'
assert_contains "$untracked_limit_directory/status.json" '"status": "preflight_failed"'
assert_contains "$untracked_limit_directory/status.json" '"terminal": true'
assert_contains "$untracked_limit_directory/result.json" '"review_complete": false'
assert_runtime_clean
pass 'pre-sandbox failures publish terminal durable status before Claude starts'

next_test
run_wrapper native --prompt 'Emit metadata without durable output.' --working-directory "$fixture" --review-working-tree --max-untracked-files 0
[ "$current_status" -ne 0 ] || fail 'no-directory preflight failure unexpectedly succeeded'
assert_contains "$current_err" '"status":"preflight_failed"'
assert_contains "$current_err" 'CLAUDE_DELEGATION_METADATA='
assert_runtime_clean
pass 'preflight failures emit metadata without a run directory'

next_test
run_wrapper success --prompt 'Return raw output.' --working-directory "$fixture" --raw-json
[ "$current_status" -eq 0 ] || fail 'raw JSON mode failed'
assert_contains "$current_out" '"delegation_metadata"'
assert_contains "$current_out" '"recovered_review":"No actionable findings\nREVIEW_COMPLETE"'
assert_runtime_clean
pass 'raw JSON mode emits one structured result'

next_test
run_wrapper tool-violation --prompt 'Do not permit tools.' --working-directory "$fixture"
[ "$current_status" -ne 0 ] || fail 'bounded tool violation unexpectedly succeeded'
assert_contains "$current_err" 'security_boundary_violation'
assert_runtime_clean
pass 'bounded analysis rejects reported tool use'

next_test
run_wrapper missing-result --prompt 'Recover partial output.' --working-directory "$fixture"
[ "$current_status" -ne 0 ] || fail 'missing result unexpectedly succeeded'
assert_contains "$current_err" '<incomplete_claude_review>'
assert_contains "$current_err" '"status":"missing_result_event"'
assert_runtime_clean
pass 'missing terminal events preserve partial evidence and metadata'

next_test
run_wrapper incomplete --prompt 'Require the completion marker.' --working-directory "$fixture"
[ "$current_status" -ne 0 ] || fail 'incomplete protocol unexpectedly succeeded'
assert_contains "$current_err" '"status":"protocol_incomplete"'
assert_runtime_clean
pass 'bounded responses require an explicit completion marker'

next_test
run_wrapper marker-with-trailer --prompt 'Reject a non-final completion marker.' --working-directory "$fixture"
[ "$current_status" -ne 0 ] || fail 'non-final completion marker unexpectedly succeeded'
assert_contains "$current_err" '"status":"protocol_incomplete"'
assert_runtime_clean
pass 'bounded completion markers must be the final non-empty line'

next_test
run_wrapper crlf-complete --prompt 'Accept a CRLF marker followed by a blank line.' --working-directory "$fixture"
[ "$current_status" -eq 0 ] || fail 'CRLF completion marker unexpectedly failed'
assert_contains "$current_out" '"completion_marker":"REVIEW_COMPLETE"'
assert_contains "$current_out" '"status":"success"'
assert_runtime_clean
pass 'CRLF blank lines do not obscure the final completion marker'

next_test
run_wrapper string-content --prompt 'Ignore non-array assistant content safely.' --working-directory "$fixture"
[ "$current_status" -eq 0 ] || fail 'string assistant content aborted stream parsing'
assert_contains "$current_out" '"status":"success"'
assert_runtime_clean
pass 'string assistant content does not abort terminal result parsing'

next_test
run_wrapper string-content-only --prompt 'Do not treat synthetic string content as review evidence.' --working-directory "$fixture"
[ "$current_status" -ne 0 ] || fail 'string-only assistant event unexpectedly succeeded'
assert_contains "$current_err" '"status":"missing_result_event"'
assert_contains "$current_err" '"partial_output_recovered":false'
assert_not_contains "$current_err" '<incomplete_claude_review>'
assert_runtime_clean
pass 'synthetic string content is not recovered as review evidence'

next_test
run_wrapper invalid-utf8 --prompt 'Recover valid result lines before invalid UTF-8.' --working-directory "$fixture"
[ "$current_status" -eq 0 ] || fail 'invalid UTF-8 discarded the valid terminal result'
assert_contains "$current_out" '"status":"success"'
assert_contains "$current_out" '"invalid_stream_utf8":true'
assert_runtime_clean
pass 'invalid UTF-8 preserves recoverable valid stream records'

next_test
run_wrapper large-complete --prompt 'Accept a large response with a final completion marker.' --working-directory "$fixture"
[ "$current_status" -eq 0 ] || fail 'large completed protocol unexpectedly failed'
assert_contains "$current_out" '"status":"success"'
assert_runtime_clean
pass 'large responses use the final non-empty completion marker without pipe failures'

next_test
run_wrapper error --prompt 'Preserve a Claude-originated error.' --working-directory "$fixture"
[ "$current_status" -ne 0 ] || fail 'Claude error unexpectedly succeeded'
assert_contains "$current_err" '<incomplete_claude_review>'
assert_contains "$current_err" '"status":"partial_error_max_budget_usd"'
[ "$(/usr/bin/grep -c '^CLAUDE_DELEGATION_METADATA=' "$current_err")" -eq 1 ] || fail 'Claude error emitted duplicate metadata records'
assert_runtime_clean
pass 'Claude-originated failures retain one recovered evidence and metadata record'

next_test
run_wrapper error-success --prompt 'Do not trust contradictory success subtypes.' --working-directory "$fixture"
[ "$current_status" -ne 0 ] || fail 'contradictory Claude error unexpectedly succeeded'
assert_contains "$current_err" '"status":"partial_claude_error"'
assert_not_contains "$current_err" '"status":"partial_success"'
assert_runtime_clean
pass 'failed results never publish success-like durable statuses'

next_test
run_wrapper malformed --prompt 'Reject a malformed stream.' --working-directory "$fixture"
[ "$current_status" -ne 0 ] || fail 'malformed stream unexpectedly succeeded'
assert_contains "$current_err" '"status":"missing_result_event"'
assert_contains "$current_err" '"invalid_stream_line_count":1'
assert_runtime_clean
pass 'malformed stream records are diagnostic rather than clean reviews'

next_test
run_wrapper slow --prompt 'Exercise timeout cleanup.' --working-directory "$fixture" --max-runtime-minutes 0.05
[ "$current_status" -ne 0 ] || fail 'timeout unexpectedly succeeded'
assert_contains "$current_err" '"status":"error_timeout"'
assert_contains "$current_err" '"timed_out":true'
assert_runtime_clean
pass 'wall-clock timeout terminates the process and cleans temporary state'

/bin/rm -f -- "$fixture/space name.txt" "$fixture/über.txt" "$fixture/[glob].txt" "$fixture/$newline_name"
/bin/dd if=/dev/zero of="$fixture/large.bin" bs=1048576 count=2 2>/dev/null
next_test
run_wrapper native --prompt 'Enforce the evidence ceiling.' --working-directory "$fixture" --review-working-tree --max-evidence-bytes 1048576
[ "$current_status" -ne 0 ] || fail 'evidence ceiling unexpectedly succeeded'
assert_contains "$current_err" 'local ceiling is 1048576 bytes'
assert_runtime_clean
pass 'evidence-size ceiling fails before Claude starts'
/bin/rm -f -- "$fixture/large.bin"

/bin/ln -s tracked.txt "$fixture/untracked-link"
next_test
run_wrapper native --prompt 'Reject symlink evidence.' --working-directory "$fixture" --review-working-tree
[ "$current_status" -ne 0 ] || fail 'symlink evidence unexpectedly succeeded'
assert_contains "$current_err" 'symbolic links are not reviewed'
assert_runtime_clean
pass 'untracked symbolic links are rejected at the snapshot boundary'

printf '1..%s\n' "$test_number"
