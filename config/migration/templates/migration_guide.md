# Migration Guide: v{from_version} → v{to_version}

## Overview
This guide covers migration from CodeRoots v{from_version} to v{to_version}.

**New Features:**
{new_features}

**Breaking Changes:**
{breaking_changes}

## Prerequisites
- [ ] Backup your Neo4j database
- [ ] Review breaking changes
- [ ] Plan maintenance window
- [ ] Test migration in staging

## Migration Steps

### Step 1: Backup
```bash
{backup_command}
```

### Step 2: Stop Services
```bash
{stop_command}
```

### Step 3: Run Migration
```bash
python validation/migration/upgrade_script.py
```

### Step 4: Verify
```bash
python validation/migration/verify_migration.py
```

### Step 5: Restart Services
```bash
{start_command}
```

## Rollback Procedure
If issues occur:
```bash
python validation/migration/rollback_script.py
```

## Troubleshooting
{troubleshooting}
