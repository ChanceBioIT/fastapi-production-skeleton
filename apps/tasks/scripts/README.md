# Background Task Execution Script Guide

## Overview

`run_task.py` is a command-line script for executing tasks from the database in the background. It supports specifying the task to run by `task_id` or `job_id`.

## Features

- ✅ Look up task by `task_id` or `job_id`
- ✅ Automatically detect task type and invoke the corresponding plugin
- ✅ Automatically update task status (RUNNING → COMPLETED/FAILED)
- ✅ Full error handling and logging
- ✅ Load task params from database or filesystem

## Usage

### Basic usage

```bash
# Execute task by task_id
python -m apps.tasks.scripts.run_task --task-id 123

# Execute task by job_id
python -m apps.tasks.scripts.run_task --job-id abc123def456...
```

### Arguments

- `--task-id`: Task ID (database primary key, integer)
- `--job-id`: Task job_id (32-character UUID string)

**Note**: You must provide either `--task-id` or `--job-id`, not both.

### Background execution

```bash
# Linux/Mac - run in background with log output
nohup python -m apps.tasks.scripts.run_task --task-id 123 > task_123.log 2>&1 &

# Windows PowerShell - run in background
Start-Process python -ArgumentList "-m", "apps.tasks.scripts.run_task", "--task-id", "123" -WindowStyle Hidden
```

## Execution flow

1. **Look up task**
   - Query the database by the given `task_id` or `job_id`
   - Verify the task exists

2. **Check task status**
   - If status is not `PENDING` or `RUNNING`, skip execution
   - Update task status to `RUNNING`

3. **Load task params**
   - Prefer reading from the database `params` field
   - If not in database, read from filesystem (`input.json`)

4. **Execute task**
   - Find the plugin by `task_type`
   - Call the plugin's `execute()` method

5. **Save result**
   - Save result to filesystem (`output.json`)
   - Update task status to `COMPLETED`

6. **Error handling**
   - On failure, update task status to `FAILED`
   - Record error message in `error_message` field

## Exit codes

- `0`: Task executed successfully
- `1`: Task execution failed or error occurred

## Log output

The script logs detailed information, including:
- Task lookup result
- Task execution start/end time
- Key steps during execution
- Error messages (if execution failed)

## Examples

### Example 1: Execute a task

```bash
$ python -m apps.tasks.scripts.run_task --task-id 5

============================================================
Task Execution Script Started
============================================================
Querying task with task_id=5...
Task found: ID=5, JobID=abc123..., Type=seq_toolkit, Status=pending
Starting task execution...
Task 5 started execution
Executing task 5 | Type: seq_toolkit | Params keys: ['sequence', 'operation', ...]
Task 5 completed successfully | Result keys: ['result', ...]
============================================================
Task Execution Completed Successfully
============================================================
```

### Example 2: Task not found

```bash
$ python -m apps.tasks.scripts.run_task --task-id 999

ERROR: Business error: Task not found: task_id=999
```

### Example 3: Unsupported task type

```bash
$ python -m apps.tasks.scripts.run_task --task-id 10

ERROR: Business error: Unsupported task type: unknown_type
```

## Notes

1. **Environment**
   - Ensure database connection is configured correctly
   - Ensure all plugins are registered

2. **Task status**
   - Only tasks in `PENDING` or `RUNNING` status will be executed
   - Tasks in other statuses will be skipped

3. **Param loading**
   - Prefer database `params` field
   - If not in database, attempt to load from filesystem

4. **Concurrent execution**
   - The script does not handle concurrency control
   - To avoid duplicate execution, check task status before invoking

## Troubleshooting

### Issue 1: Task not found

**Error**: `Task not found: task_id=xxx`

**Solution**:
- Verify `task_id` or `job_id` is correct
- Confirm the task exists in the database

### Issue 2: Unsupported task type

**Error**: `Unsupported task type: xxx`

**Solution**:
- Check that the task type is registered in `task_registry`
- Confirm the plugin file exists and is imported correctly

### Issue 3: Param loading failed

**Error**: Params are empty when task executes

**Solution**:
- Check the task's `params` field in the database
- Check that `input.json` exists on the filesystem
- Confirm task param format is correct

### Issue 4: Database connection failed

**Error**: Database connection related errors

**Solution**:
- Check database config (e.g. `DATABASE_URL`)
- Confirm the database service is running
- Check network and firewall settings

## Integration

### As a scheduled job

```bash
# Add to crontab (Linux/Mac)
# Run every hour for all PENDING tasks (requires additional query script)
0 * * * * /usr/bin/python3 -m apps.tasks.scripts.run_task --task-id $(get_next_pending_task_id)
```

### As a system service

You can create a systemd service or Windows service to run tasks periodically.

## Related files

- `apps/tasks/service.py` - Task service layer
- `apps/tasks/plugins/` - Task plugin directory
- `apps/tasks/storage.py` - File storage utilities
