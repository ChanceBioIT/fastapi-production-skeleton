# Task Plugin Guide

This directory contains **example plugins** that demonstrate the generic "task + plugin" pattern.

- `seq_tool`: Example implementation; you may remove or replace it with your own business plugins.
- For private projects, add new plugin modules under this directory, implement the `TaskPlugin` interface (see `base.py`), and register the `task_type` and plugin instance in `task_registry` in `__init__.py`.
- If you do not need the task feature, you may omit mounting the task router in `main.py`, and optionally remove this app or keep an empty shell.
