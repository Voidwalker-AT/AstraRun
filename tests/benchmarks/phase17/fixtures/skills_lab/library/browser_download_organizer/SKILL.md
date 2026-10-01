---
name: browser_download_organizer
description: Sort recent browser downloads into categorized project subfolders.
version: 1.0.0
author: AstraRun Engine
tags: [files, downloads, organization, browser]
inputs: [destination_path, file_types, dry_run]
platforms: [windows]
---

# Browser Download Triage & Routing Skill

## Overview
Scans the user default Downloads directory, identifies newly acquired files, and organizes them into categorized folders based on file extension, MIME type, and project naming heuristics.

## When to Use
- When sorting unorganized downloads or incoming test datasets.
- When preparing directories before or after benchmark runs.
- When instructed to organize downloads by document type.

## Required Parameters
- `destination_path` (string, optional): Base directory for categorized sorting (default: user Downloads folder).
- `file_types` (list of strings, optional): Extensions to organize: ['pdf', 'images', 'archives', 'code'] (default: all supported).
- `dry_run` (boolean, optional): Preview planned file moves without modifying filesystem (default: false).

## Procedure
1. Scan base Downloads folder for unmanaged files (non-directory items).
2. Classify each file by extension into categorization buckets:
   - Documents: `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.txt`
   - Archives: `.zip`, `.tar.gz`, `.7z`, `.rar`
   - Media: `.png`, `.jpg`, `.mp4`, `.wav`
   - Installers: `.exe`, `.msi`
3. Check destination subfolders, creating them if necessary.
4. For each file, ensure target path does not cause overwrite collisions (append timestamp hash if duplicate exists).
5. Move files to respective subfolders.
6. Return JSON summary detailing moved files, destinations, and skipped items.

## Verification Steps
- Verify all moved files exist at destination with identical SHA256 checksums.
- Ensure zero data loss or partial writes.

