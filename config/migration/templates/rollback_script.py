#!/usr/bin/env python
"""
Rollback script: v{to_version} → v{from_version}
Use this to revert a failed migration.
"""
import argparse

# Version constants (substituted by template)
FROM_VERSION = "{from_version}"
TO_VERSION = "{to_version}"


def restore_backup(backup_dir):
    """Restore from backup"""
    {restore_logic}


def downgrade_schema():
    """Revert schema changes"""
    {downgrade_logic}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backup', required=True)
    args = parser.parse_args()

    print(f"Rolling back from v{TO_VERSION} to v{FROM_VERSION}")
    restore_backup(args.backup)
    downgrade_schema()
    print("Rollback complete")


if __name__ == "__main__":
    main()
