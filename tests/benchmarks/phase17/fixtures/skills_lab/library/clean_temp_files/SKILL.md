---
name: clean_temp_files
description: Safely prune user temporary caches, crash dumps, and obsolete temp directories.
version: 1.0.0
author: AstraRun Engine
tags: [maintenance, disk, storage, cleanup]
inputs: [max_age_days, dry_run, target_scopes]
platforms: [windows]
---

# Safe Temporary File & Crash Dump Pruning Skill

## Overview
Performs safe, non-destructive cleanup of obsolete temporary files, crash dumps, and user cache directories without risking active processes.

## When to Use
- When local disk storage is low or drive E:/C: requires maintenance.
- After heavy compilation or benchmark runs creating transient outputs.
- When user explicitly requests temporary file cleanup.

## Required Parameters
- `max_age_days` (integer, optional): Only delete files older than this threshold in days (default: 3).
- `dry_run` (boolean, optional): If true, scans and calculates reclaimable bytes without deleting (default: false).
- `target_scopes` (list of strings, optional): Scopes to prune: ['user_temp', 'crash_dumps', 'pip_cache'] (default: ['user_temp', 'crash_dumps']).

## Procedure
1. Enumerate target directories:
   - User Temp: `%LOCALAPPDATA%\Temp`
   - Crash Dumps: `%LOCALAPPDATA%\CrashDumps`
2. Inspect each candidate file:
   - Check last modified timestamp against `max_age_days`.
   - Check file locks (attempt non-exclusive read open).
   - Skip files locked by running processes.
3. If `dry_run` is false, delete unpinned files matching age criteria.
4. Aggregate statistics: total files inspected, files deleted, bytes reclaimed, errors encountered.
5. Emit structured JSON report.

## Verification & Safety Rules
- NEVER delete files within project source trees (`src/`, `.git/`, `.venv/`).
- Skip any file locked by another process with zero fatal errors.

