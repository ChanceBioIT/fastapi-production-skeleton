# Task API Tests

## Running tests

### Install test dependencies

```bash
pip install -r requirements.txt
```

### Run all tests

```bash
pytest
```

### Run a specific test file

```bash
pytest tests/test_tasks_api.py
```

### Run a specific test class

```bash
pytest tests/test_tasks_api.py::TestTaskSubmit
```

### Run a specific test method

```bash
pytest tests/test_tasks_api.py::TestTaskSubmit::test_submit_task_success_gc_content
```

### View test coverage

```bash
pytest --cov=apps --cov=framework --cov-report=html
```

Coverage report is generated in `htmlcov/index.html`.

## Cleaning test data

### Method 1: Using pytest (recommended)

Clean all test data (removes all data from the database):

```bash
pytest --clean-test-data
```

**Note**: This command cleans data and exits without running tests.

### Method 2: Standalone script

Clean all test data:

```bash
python -m tests.cleanup_test_data --all
```

Clean only test data matching a pattern (e.g. records containing "test"):

```bash
python -m tests.cleanup_test_data --pattern test
```

### Method 3: Disable auto-cleanup

To keep data after tests for debugging:

```bash
pytest --no-cleanup
```

### Auto-cleanup behavior

By default, test data is cleaned automatically after each test (via `cleanup_test_data` fixture).

- **Auto-clean**: After each test (default)
- **Disable**: Use `--no-cleanup`
- **Manual**: Use `--clean-test-data` or the standalone script

## Test structure

- `conftest.py`: Test config and shared fixtures
- `test_tasks_api.py`: Task API test cases

## Test coverage

### TestTaskSubmit
- Submit GC content task successfully
- Submit reverse complement task successfully
- Unsupported task type
- Invalid base sequence
- Missing required params
- Unsupported operation type
- Async mode submit
- Empty sequence validation

### TestTaskValidation
- Sequence case insensitive
- Sequence with N (unknown base)

### TestTaskResults
- GC content result correctness
- Reverse complement result correctness
