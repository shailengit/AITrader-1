# TEST.md

## Test Plan

### Unit Tests (`test_core.py`)

| Test Class | Description |
|-----------|-------------|
| `TestConfig` | Config load/save, backend URL, output format, env override |
| `TestSession` | Session CRUD, dry-run no-save, scan tracking, strategy tracking |
| `TestProject` | Project create/delete, scan/strategy association, notes |
| `TestExport` | JSON, CSV, table rendering, empty data handling |
| `TestAPIClient` | GET/POST success, HTTP error handling |

### E2E Tests (`test_full_e2e.py`)

| Test Method | Description |
|-------------|-------------|
| `test_health` | CLI health command via Click runner |
| `test_sectors_list` | Sectors list command |
| `test_screener_scan_and_status` | Scan start and status polling |
| `test_strategies_list` | Strategies list command |
| `test_quantgen_generate` | Strategy generation command |
| `test_project_create_and_show` | Project create/show commands |
| `test_config_set_and_show` | Config set-url and show |
| `test_json_output_flag` | Top-level --json flag |
| `test_repl_exit` | REPL exit command |
| `test_screener_list_empty` | List tracked scans when empty |
| `test_screener_ai_report` | Fetch AI analysis report for a scan |
| `test_screener_health` | Screener service health check |
| `test_quantgen_true_wfo` | True Walk-Forward Optimization command |
| `test_projects_notes` | Set and show project notes |
| `test_projects_add_scan` | Associate existing scan with project |
| `test_projects_add_strategy` | Associate existing strategy with project |
| `test_screener_scan_with_filters` | Scan with JSON filters file |
| `test_installed_help` | Subprocess: installed CLI help (requires `CLI_ANYTHING_FORCE_INSTALLED=1`) |
| `test_installed_sectors_list` | Subprocess: installed CLI sectors list (requires `CLI_ANYTHING_FORCE_INSTALLED=1`)

## Test Results

```
$ CLI_ANYTHING_FORCE_INSTALLED=1 pytest cli_anything/tradecraft/tests/ -v --tb=short

cli_anything/tradecraft/tests/test_core.py::TestConfig::test_env_backend_url PASSED
cli_anything/tradecraft/tests/test_core.py::TestConfig::test_load_default_config PASSED
cli_anything/tradecraft/tests/test_core.py::TestConfig::test_save_and_load_config PASSED
cli_anything/tradecraft/tests/test_core.py::TestConfig::test_set_backend_url PASSED
cli_anything/tradecraft/tests/test_core.py::TestConfig::test_set_output_format PASSED
cli_anything/tradecraft/tests/test_core.py::TestSession::test_add_scan PASSED
cli_anything/tradecraft/tests/test_core.py::TestSession::test_add_strategy PASSED
cli_anything/tradecraft/tests/test_core.py::TestSession::test_clear PASSED
cli_anything/tradecraft/tests/test_core.py::TestSession::test_dry_run_no_save PASSED
cli_anything/tradecraft/tests/test_core.py::TestSession::test_remove_scan PASSED
cli_anything/tradecraft/tests/test_core.py::TestSession::test_update_scan_status PASSED
cli_anything/tradecraft/tests/test_core.py::TestProject::test_add_scan PASSED
cli_anything/tradecraft/tests/test_core.py::TestProject::test_add_strategy PASSED
cli_anything/tradecraft/tests/test_core.py::TestProject::test_create_and_list PASSED
cli_anything/tradecraft/tests/test_core.py::TestProject::test_delete PASSED
cli_anything/tradecraft/tests/test_core.py::TestProject::test_set_notes PASSED
cli_anything/tradecraft/tests/test_core.py::TestProject::test_get_notes PASSED
cli_anything/tradecraft/tests/test_core.py::TestExport::test_render_csv PASSED
cli_anything/tradecraft/tests/test_core.py::TestExport::test_render_empty_table PASSED
cli_anything/tradecraft/tests/test_core.py::TestExport::test_render_json PASSED
cli_anything/tradecraft/tests/test_core.py::TestExport::test_render_table PASSED
cli_anything/tradecraft/tests/test_core.py::TestAPIClient::test_api_error PASSED
cli_anything/tradecraft/tests/test_core.py::TestAPIClient::test_get_success PASSED
cli_anything/tradecraft/tests/test_core.py::TestAPIClient::test_post_success PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_config_set_and_show PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_health PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_json_output_flag PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_project_create_and_show PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_projects_add_scan PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_projects_add_strategy PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_projects_notes PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_quantgen_generate PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_quantgen_true_wfo PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_repl_exit PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_screener_ai_report PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_screener_health PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_screener_list_empty PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_screener_scan_and_status PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_screener_scan_with_filters PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_sectors_list PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestE2EWorkflows::test_strategies_list PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestCLISubprocess::test_installed_help PASSED
cli_anything/tradecraft/tests/test_full_e2e.py::TestCLISubprocess::test_installed_sectors_list PASSED

43 passed in 0.31s
```

## Coverage Notes

- Core modules: 100% of public APIs tested
- E2E workflows: All major command groups exercised via Click runner
- Subprocess tests: PASS with `CLI_ANYTHING_FORCE_INSTALLED=1` after `pip install -e .`
- No external dependencies required for tests (all HTTP mocked)
- Total: 43 tests, 0 failures, 0 skips (installed run)
