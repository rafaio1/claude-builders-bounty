#!/usr/bin/env python3
"""
Memory Expunge Routine - Alivia uso de memória/disco do servidor
Limpa logs antigos, caches temporários e arquivos órfãos sem remover dados críticos.
"""
import os, sys, shutil, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO_ROOT = Path("/Agentic")
LOG_DIRS = [
    REPO_ROOT / "logs",
    REPO_ROOT / "revenue" / "bounties",
]
CACHE_DIRS = [
    REPO_ROOT / ".cache",
    REPO_ROOT / "node_modules" / ".cache",
    Path.home() / ".npm" / "_cacache",
    Path.home() / ".cache" / "pip",
]
MAX_LOG_AGE_DAYS = 14
MAX_CACHE_AGE_DAYS = 7
DRY_RUN = "--dry-run" in sys.argv

def human_size(nbytes):
    for unit in ['B','KB','MB','GB']:
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f}{unit}"
        nbytes /= 1024
    return f"{nbytes:.1f}TB"

def clean_old_files(directory, max_age_days, pattern="*"):
    freed = 0
    count = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    
    if not directory.exists():
        return 0, 0
    
    for f in directory.rglob(pattern):
        if not f.is_file():
            continue
        # Never delete ledger.json or .env or active configs
        if f.name in ("ledger.json", ".env", "config.json", "package.json"):
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                size = f.stat().st_size
                if DRY_RUN:
                    print(f"  [DRY] Would remove: {f} ({human_size(size)})")
                else:
                    f.unlink()
                freed += size
                count += 1
        except Exception as e:
            print(f"  Skip {f}: {e}", file=sys.stderr)
    
    return freed, count

def clean_empty_dirs(directory):
    removed = 0
    if not directory.exists():
        return 0
    for d in sorted(directory.rglob("*"), reverse=True):
        if d.is_dir():
            try:
                if not any(d.iterdir()):
                    if DRY_RUN:
                        print(f"  [DRY] Would rmdir: {d}")
                    else:
                        d.rmdir()
                    removed += 1
            except Exception:
                pass
    return removed

def main():
    total_freed = 0
    total_files = 0
    
    print(f"=== Memory Expunge {'(DRY RUN)' if DRY_RUN else ''} ===")
    print(f"Cutoff: logs>{MAX_LOG_AGE_DAYS}d, caches>{MAX_CACHE_AGE_DAYS}d\n")
    
    # Clean old log files
    for log_dir in LOG_DIRS:
        if log_dir.exists():
            print(f"Scanning logs: {log_dir}")
            freed, count = clean_old_files(log_dir, MAX_LOG_AGE_DAYS, "*.log")
            freed2, count2 = clean_old_files(log_dir, MAX_LOG_AGE_DAYS, "*.tmp")
            freed3, count3 = clean_old_files(log_dir, MAX_LOG_AGE_DAYS, "*.bak")
            total_freed += freed + freed2 + freed3
            total_files += count + count2 + count3
            print(f"  Removed {count+count2+count3} files, freed {human_size(freed+freed2+freed3)}")
    
    # Clean caches
    for cache_dir in CACHE_DIRS:
        if cache_dir.exists():
            print(f"\nScanning cache: {cache_dir}")
            dir_size_before = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
            if DRY_RUN:
                print(f"  [DRY] Would remove entire cache dir: {human_size(dir_size_before)}")
            else:
                shutil.rmtree(cache_dir, ignore_errors=True)
            total_freed += dir_size_before
            print(f"  Freed {human_size(dir_size_before)}")
    
    # Remove empty directories
    print("\nCleaning empty directories...")
    for base in [REPO_ROOT / "logs", REPO_ROOT / "tmp"]:
        removed = clean_empty_dirs(base)
        if removed:
            print(f"  Removed {removed} empty dirs under {base}")
    
    print(f"\n{'='*50}")
    print(f"Total freed: {human_size(total_freed)}")
    print(f"Files removed: {total_files}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")

if __name__ == "__main__":
    main()
