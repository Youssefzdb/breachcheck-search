#!/usr/bin/env python3
"""
BreachCheck Archive Search Tool v2
====================================
Searches the 280GB SquashFS archive directly via HTTP Range.
Parallel search, dedup results, early exit option.

Usage:
  python3 search_archive.py <email>
  python3 search_archive.py ambuguambuguambugu@gmail.com
"""

import sys
import time
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from http_range_file import HttpRangeFile
from dissect.squashfs import SquashFS

SQUASHFS_URL = (
    "https://ia600706.us.archive.org/20/items/"
    "2019-collection-1-5-antipublic-tri-pack-squashfs/"
    "Collection_%231-%235_Antipublic_tri-pack.squashfs"
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Thread-safe results
results_lock = threading.Lock()
all_results = {}  # (email, password) -> breach info
files_done = 0
files_lock = threading.Lock()
found_any = False


def search_file(sqfs_file, dir_name, file_name, target_email, stop_on_first=False):
    """Search one file for target email. Returns list of matches."""
    global found_any
    matches = []
    
    if stop_on_first and found_any:
        return matches
    
    try:
        fh = sqfs_file.open()
        chunk_size = 4 * 1024 * 1024  # 4MB
        leftover = b""
        
        while True:
            data = fh.read(chunk_size)
            if not data:
                # Process final leftover
                if leftover:
                    text = leftover.decode('utf-8', errors='replace')
                    if target_email in text:
                        for line in text.split('\n'):
                            process_line(line, target_email, dir_name, file_name, matches)
                break
            
            buffer = leftover + data
            text = buffer.decode('utf-8', errors='replace')
            
            # Fast check: is email in this chunk?
            if target_email in text:
                # Keep last 500 bytes for line boundary
                cut = buffer.rfind(b'\n')
                if cut == -1:
                    leftover = buffer
                    continue
                
                chunk_text = buffer[:cut].decode('utf-8', errors='replace')
                leftover = buffer[cut+1:]
                
                for line in chunk_text.split('\n'):
                    process_line(line, target_email, dir_name, file_name, matches)
            else:
                # Keep last 500 bytes
                leftover = buffer[-500:] if len(buffer) > 500 else buffer
        
        fh.close()
    except Exception as e:
        logger.debug(f"Error reading {dir_name}/{file_name}: {e}")
    
    return matches


def process_line(line, target_email, dir_name, file_name, matches):
    """Check if line contains the target email."""
    line = line.strip()
    if not line or ':' not in line:
        return
    # Quick check before parsing
    if target_email not in line.lower():
        return
    
    parts = line.rsplit(':', 1)
    if len(parts) != 2:
        return
    email = parts[0].strip().lower()
    # Remove BOM if present
    if email.startswith('\ufeff'):
        email = email[1:]
    password = parts[1].strip()
    
    if email == target_email:
        matches.append({
            "email": email,
            "password": password,
            "breach": dir_name,
            "file": file_name
        })


def search_archive(target_email, max_workers=20, stop_on_first=False):
    """Search entire SquashFS archive for a specific email."""
    global all_results, files_done, found_any
    
    target_email = target_email.strip().lower()
    # Remove BOM
    if target_email.startswith('\ufeff'):
        target_email = target_email[1:]
    
    logger.info("=" * 60)
    logger.info(f"🔍 Searching for: {target_email}")
    logger.info(f"   Workers: {max_workers} | Stop on first: {stop_on_first}")
    logger.info("=" * 60)
    
    # Open SquashFS
    t0 = time.time()
    http_file = HttpRangeFile(SQUASHFS_URL, block_size=4*1024*1024, cache_size=500)
    sqfs = SquashFS(http_file)
    logger.info(f"SquashFS opened in {time.time()-t0:.1f}s | {http_file.size/1024**3:.1f}GB")
    
    # Get all files
    all_files = []
    for top_dir in sqfs.root.iterdir():
        if not top_dir.is_dir():
            continue
        for sub in top_dir.iterdir():
            if sub.is_file() and sub.name.endswith('.txt'):
                all_files.append((top_dir.name, sub.name, sub))
            elif sub.is_dir():
                for f in sub.iterdir():
                    if f.is_file() and f.name.endswith('.txt'):
                        all_files.append((f"{top_dir.name}/{sub.name}", f.name, f))
    
    total_files = len(all_files)
    logger.info(f"Total files to search: {total_files:,}")
    
    # Parallel search
    t_start = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for dir_name, file_name, sqfs_file in all_files:
            future = executor.submit(search_file, sqfs_file, dir_name, file_name, target_email, stop_on_first)
            futures[future] = (dir_name, file_name)
        
        for future in as_completed(futures):
            dir_name, file_name = futures[future]
            
            with files_lock:
                files_done += 1
                current = files_done
            
            try:
                matches = future.result()
                if matches:
                    with results_lock:
                        for m in matches:
                            key = (m["email"], m["password"])
                            if key not in all_results:
                                all_results[key] = {
                                    "email": m["email"],
                                    "password": m["password"],
                                    "breaches": set()
                                }
                            all_results[key]["breaches"].add(m["breach"])
                        found_any = True
                    
                    logger.info(f"  🎯 FOUND in {dir_name}/{file_name} — "
                               f"{len(matches)} matches, {len(all_results)} unique so far")
                
            except Exception as e:
                logger.debug(f"Error: {e}")
            
            # Progress
            if current % 50 == 0:
                elapsed = time.time() - t_start
                rate = current / elapsed if elapsed > 0 else 0
                eta = (total_files - current) / rate if rate > 0 else 0
                pct = current / total_files * 100
                logger.info(f"  📊 {current}/{total_files} ({pct:.1f}%) | "
                           f"{rate:.1f} files/s | ETA: {eta/60:.0f}min | "
                           f"Found: {len(all_results)} unique")
            
            # Early exit
            if stop_on_first and found_any:
                logger.info("  ⏹️ Stopping early (found match)")
                break
    
    elapsed = time.time() - t_start
    
    # Convert sets to lists for JSON
    final_results = []
    for key, val in all_results.items():
        final_results.append({
            "email": val["email"],
            "password": val["password"],
            "breaches": list(val["breaches"])
        })
    
    logger.info(f"\n{'=' * 60}")
    logger.info(f"✅ Search complete in {elapsed/60:.1f} minutes")
    logger.info(f"   Files searched: {files_done}/{total_files}")
    logger.info(f"   Unique results: {len(final_results)}")
    logger.info(f"{'=' * 60}")
    
    if final_results:
        logger.info(f"\n🎯 Results for {target_email}:")
        for r in final_results:
            pw = r["password"]
            masked = pw[:2] + "*" * (len(pw) - 4) + pw[-2:] if len(pw) > 4 else "***"
            breaches = ", ".join(r["breaches"])
            logger.info(f"  📁 {breaches}")
            logger.info(f"     Email: {r['email']}")
            logger.info(f"     Password (masked): {masked}")
            logger.info(f"     Password (full): {pw}")
    else:
        logger.info(f"\n❌ {target_email} NOT found in 280GB archive")
    
    http_file.close()
    return final_results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 search_archive.py <email> [--full]")
        print("  --full: search all files (don't stop at first match)")
        sys.exit(1)
    
    email = sys.argv[1]
    stop_on_first = "--full" not in sys.argv
    
    results = search_archive(email, max_workers=20, stop_on_first=stop_on_first)
    
    if results:
        print("\n" + json.dumps(results, indent=2, ensure_ascii=False))
