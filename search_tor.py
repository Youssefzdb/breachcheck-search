#!/usr/bin/env python3
"""
BreachCheck Archive Search Tool v3 — Tor Edition
===================================================
Searches the 280GB SquashFS archive via HTTP Range through Tor.
Each worker thread uses its own Tor circuit (different IP) + rotating UserAgent.
Auto-deduplicates results (email + password).

Requirements (on your machine):
  pip install requests pysocks dissect

  Tor must be running with SOCKS5 on port 9050.
  For stream isolation (different IP per thread), add to torrc:
    SocksPort 9050 IsolateSOCKSAuth
    ControlPort 9051
    # OR start multiple Tor instances on different ports

Usage:
  python3 search_tor.py <email>
  python3 search_tor.py ambuguambuguambugu@gmail.com
  python3 search_tor.py user@example.com --workers 30 --tor-port 9050
"""

import sys
import time
import json
import random
import logging
import threading
import socks
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import requests

# Try to import dissect
try:
    from dissect.squashfs import SquashFS
    HAS_DISSECT = True
except ImportError:
    HAS_DISSECT = False
    print("ERROR: Install dissect: pip install dissect")
    sys.exit(1)

# ============ CONFIG ============
SQUASHFS_URL = (
    "https://ia600706.us.archive.org/20/items/"
    "2019-collection-1-5-antipublic-tri-pack-squashfs/"
    "Collection_%231-%235_Antipublic_tri-pack.squashfs"
)

TOR_HOST = "127.0.0.1"
TOR_PORT = 9050

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
    "curl/8.5.0",
    "Wget/1.21.4",
    "Python-urllib/3.11",
]

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ============ TOR HTTP RANGE FILE ============
class TorHttpRangeFile:
    """File-like object that reads remote files via HTTP Range through Tor SOCKS5.
    
    Each instance uses unique SOCKS5 credentials for Tor stream isolation
    (different circuit = different exit IP).
    """
    
    def __init__(self, url, worker_id=0, block_size=4*1024*1024, cache_size=300,
                 tor_host=TOR_HOST, tor_port=TOR_PORT):
        self.url = url
        self.block_size = block_size
        self.pos = 0
        self.size = 0
        self.cache = {}
        self.cache_order = []
        self.max_cache = cache_size
        self.worker_id = worker_id
        
        # Unique SOCKS5 credentials per worker = different Tor circuit
        self.socks_user = f"worker{worker_id}"
        self.socks_pass = f"circuit{worker_id}_{random.randint(1000,9999)}"
        
        # Create a session with SOCKS5 proxy
        self.session = requests.Session()
        self.session.proxies = {
            "http": f"socks5h://{self.socks_user}:{self.socks_pass}@{tor_host}:{tor_port}",
            "https": f"socks5h://{self.socks_user}:{self.socks_pass}@{tor_host}:{tor_port}",
        }
        self.session.headers["User-Agent"] = random.choice(USER_AGENTS)
        
        # Get file size
        for attempt in range(5):
            try:
                resp = self.session.head(url, timeout=60, allow_redirects=True)
                self.size = int(resp.headers.get('content-length', 0))
                if self.size > 0:
                    break
            except Exception as e:
                logger.debug(f"[W{worker_id}] HEAD attempt {attempt}: {e}")
                time.sleep(3)
        
        if self.size == 0:
            raise Exception(f"[W{worker_id}] Failed to get file size")
        
        logger.info(f"[W{worker_id}] Connected via Tor | Size: {self.size/1024**3:.1f}GB | "
                   f"UA: {self.session.headers['User-Agent'][:30]}...")
    
    def seekable(self):
        return True
    
    def seek(self, offset, whence=0):
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        elif whence == 2:
            self.pos = self.size + offset
        return self.pos
    
    def tell(self):
        return self.pos
    
    def read(self, size=-1):
        if size == -1:
            size = self.size - self.pos
        if size == 0:
            return b''
        if self.pos >= self.size:
            return b''
        end = min(self.pos + size, self.size)
        data = self._read_range(self.pos, end)
        self.pos = end
        return data
    
    def _read_range(self, start, end):
        result = bytearray()
        pos = start
        while pos < end:
            block_idx = pos // self.block_size
            block_start = block_idx * self.block_size
            block_end = min(block_start + self.block_size, self.size)
            
            if block_idx not in self.cache:
                self._download_block(block_idx)
            
            block_data = self.cache[block_idx]
            offset_in_block = pos - block_start
            bytes_to_read = min(block_end - pos, end - pos)
            result.extend(block_data[offset_in_block:offset_in_block + bytes_to_read])
            pos += bytes_to_read
        
        return bytes(result)
    
    def _download_block(self, block_idx):
        start = block_idx * self.block_size
        end = min(start + self.block_size - 1, self.size - 1)
        
        # Rotate UserAgent on each block download
        self.session.headers["User-Agent"] = random.choice(USER_AGENTS)
        
        headers = {
            'Range': f'bytes={start}-{end}',
            'User-Agent': random.choice(USER_AGENTS),
        }
        
        for attempt in range(5):
            try:
                resp = self.session.get(self.url, headers=headers, timeout=120)
                if resp.status_code in (206, 200):
                    data = resp.content
                    self.cache[block_idx] = data
                    self.cache_order.append(block_idx)
                    if len(self.cache_order) > self.max_cache:
                        old = self.cache_order.pop(0)
                        if old != block_idx:
                            self.cache.pop(old, None)
                    return
                elif resp.status_code == 429:
                    # Rate limited — wait and retry with new circuit
                    logger.debug(f"[W{self.worker_id}] Rate limited, waiting 30s...")
                    time.sleep(30)
                    # Force new UserAgent
                    self.session.headers["User-Agent"] = random.choice(USER_AGENTS)
                else:
                    logger.debug(f"[W{self.worker_id}] HTTP {resp.status_code}")
                    time.sleep(5)
            except Exception as e:
                if attempt < 4:
                    logger.debug(f"[W{self.worker_id}] Block {block_idx} retry {attempt}: {e}")
                    time.sleep(5)
                else:
                    raise
        
        raise Exception(f"[W{self.worker_id}] Failed to download block {block_idx}")
    
    def close(self):
        self.cache.clear()
        self.session.close()


# ============ SEARCH ============
results_lock = threading.Lock()
all_results = {}  # (email, password) -> set of breaches
files_done = 0
files_lock = threading.Lock()
found_any = False
stop_event = threading.Event()


def process_line(line, target_email, breach_name, matches):
    """Check if a line contains the target email."""
    line = line.strip()
    if not line or ':' not in line:
        return
    if target_email not in line.lower():
        return
    parts = line.rsplit(':', 1)
    if len(parts) != 2:
        return
    email = parts[0].strip().lower().lstrip('\ufeff')
    password = parts[1].strip()
    if email == target_email:
        matches.append((email, password, breach_name))


def search_file_worker(sqfs_file, dir_name, file_name, target_email, worker_id):
    """Search one file through a Tor circuit."""
    global found_any
    matches = []
    
    if stop_event.is_set():
        return matches
    
    try:
        fh = sqfs_file.open()
        chunk_size = 4 * 1024 * 1024
        leftover = b""
        
        while True:
            if stop_event.is_set():
                break
            data = fh.read(chunk_size)
            if not data:
                if leftover:
                    text = leftover.decode('utf-8', errors='replace')
                    if target_email in text:
                        for line in text.split('\n'):
                            process_line(line, target_email, dir_name, matches)
                break
            
            buffer = leftover + data
            text = buffer.decode('utf-8', errors='replace')
            
            if target_email in text:
                cut = buffer.rfind(b'\n')
                if cut == -1:
                    leftover = buffer
                    continue
                chunk_text = buffer[:cut].decode('utf-8', errors='replace')
                leftover = buffer[cut+1:]
                for line in chunk_text.split('\n'):
                    process_line(line, target_email, dir_name, matches)
            else:
                leftover = buffer[-500:] if len(buffer) > 500 else buffer
        
        fh.close()
    except Exception as e:
        logger.debug(f"[W{worker_id}] Error {dir_name}/{file_name}: {e}")
    
    return matches


def search_archive_tor(target_email, max_workers=20, tor_port=TOR_PORT, stop_on_first=False):
    """Search the entire archive using Tor for IP rotation."""
    global all_results, files_done, found_any
    
    target_email = target_email.strip().lower().lstrip('\ufeff')
    
    logger.info("=" * 60)
    logger.info(f"🔍 BreachCheck Tor Search")
    logger.info(f"   Target: {target_email}")
    logger.info(f"   Workers: {max_workers} (each via separate Tor circuit)")
    logger.info(f"   Tor: {TOR_HOST}:{tor_port}")
    logger.info("=" * 60)
    
    # ============ Phase 1: Get file list using one Tor connection ============
    t0 = time.time()
    logger.info("[Phase 1] Opening SquashFS via Tor...")
    
    list_file = TorHttpRangeFile(SQUASHFS_URL, worker_id=0, block_size=4*1024*1024, cache_size=500,
                                 tor_port=tor_port)
    list_sqfs = SquashFS(list_file)
    
    all_files = []
    for top_dir in list_sqfs.root.iterdir():
        if not top_dir.is_dir():
            continue
        for sub in top_dir.iterdir():
            if sub.is_file() and sub.name.endswith('.txt'):
                all_files.append((top_dir.name, sub.name))
            elif sub.is_dir():
                for f in sub.iterdir():
                    if f.is_file() and f.name.endswith('.txt'):
                        all_files.append((f"{top_dir.name}/{sub.name}", f.name))
    
    total_files = len(all_files)
    logger.info(f"[Phase 1] Done in {time.time()-t0:.1f}s | {total_files:,} files found")
    list_file.close()
    
    # ============ Phase 2: Open N SquashFS instances (one per worker) ============
    logger.info(f"[Phase 2] Opening {max_workers} Tor circuits...")
    
    worker_sqfs = []
    for i in range(max_workers):
        try:
            wf = TorHttpRangeFile(SQUASHFS_URL, worker_id=i+1, block_size=4*1024*1024, cache_size=300,
                                  tor_port=tor_port)
            ws = SquashFS(wf)
            worker_sqfs.append((wf, ws))
            logger.info(f"  Worker {i+1}/{max_workers} connected (circuit {i+1})")
        except Exception as e:
            logger.error(f"  Worker {i+1} failed: {e}")
            if not worker_sqfs:
                logger.error("No workers available!")
                return []
    
    # Build file index for each worker's SquashFS
    worker_files = []
    for wf, ws in worker_sqfs:
        wf_map = {}
        for top_dir in ws.root.iterdir():
            if not top_dir.is_dir():
                continue
            for sub in top_dir.iterdir():
                if sub.is_file() and sub.name.endswith('.txt'):
                    wf_map[f"{top_dir.name}/{sub.name}"] = sub
                elif sub.is_dir():
                    for f in sub.iterdir():
                        if f.is_file() and f.name.endswith('.txt'):
                            wf_map[f"{top_dir.name}/{sub.name}/{f.name}"] = f
        worker_files.append(wf_map)
    
    logger.info(f"[Phase 2] All {len(worker_sqfs)} workers ready")
    
    # ============ Phase 3: Parallel search ============
    logger.info(f"[Phase 3] Searching {total_files:,} files...")
    t_start = time.time()
    
    # Distribute files round-robin to workers
    file_queue = []
    for i, (dir_name, file_name) in enumerate(all_files):
        worker_idx = i % len(worker_sqfs)
        full_path = f"{dir_name}/{file_name}"
        sqfs_file = worker_files[worker_idx].get(full_path)
        if sqfs_file:
            file_queue.append((worker_idx, sqfs_file, dir_name, file_name))
    
    logger.info(f"  Distributed {len(file_queue):,} files to {len(worker_sqfs)} workers")
    
    def do_search(args):
        worker_idx, sqfs_file, dir_name, file_name = args
        return search_file_worker(sqfs_file, dir_name, file_name, target_email, worker_idx)
    
    with ThreadPoolExecutor(max_workers=len(worker_sqfs)) as executor:
        futures = {executor.submit(do_search, f): f for f in file_queue}
        
        for future in as_completed(futures):
            with files_lock:
                files_done += 1
                current = files_done
            
            try:
                matches = future.result()
                if matches:
                    with results_lock:
                        for email, password, breach in matches:
                            key = (email, password)
                            if key not in all_results:
                                all_results[key] = {
                                    "email": email,
                                    "password": password,
                                    "breaches": set()
                                }
                            all_results[key]["breaches"].add(breach)
                        found_any = True
                    
                    logger.info(f"  🎯 FOUND: {len(matches)} matches in "
                               f"{futures[future][3]} | Unique: {len(all_results)}")
                
            except Exception as e:
                logger.debug(f"  Search error: {e}")
            
            if current % 50 == 0:
                elapsed = time.time() - t_start
                rate = current / elapsed if elapsed > 0 else 0
                eta = (total_files - current) / rate if rate > 0 else 0
                logger.info(f"  📊 {current}/{total_files} ({current/total_files*100:.1f}%) | "
                           f"{rate:.1f} files/s | ETA: {eta/60:.0f}min | "
                           f"Found: {len(all_results)} unique")
            
            if stop_on_first and found_any:
                logger.info("  ⏹️ Found match — stopping remaining searches")
                stop_event.set()
                break
    
    elapsed = time.time() - t_start
    
    # ============ Results ============
    final_results = []
    for key, val in all_results.items():
        final_results.append({
            "email": val["email"],
            "password": val["password"],
            "breaches": sorted(list(val["breaches"]))
        })
    
    logger.info(f"\n{'=' * 60}")
    logger.info(f"✅ Search complete in {elapsed/60:.1f} minutes")
    logger.info(f"   Files searched: {files_done}/{total_files}")
    logger.info(f"   Unique results: {len(final_results)}")
    logger.info(f"   Tor circuits used: {len(worker_sqfs)}")
    logger.info(f"{'=' * 60}")
    
    if final_results:
        logger.info(f"\n🎯 Results for {target_email}:")
        for r in final_results:
            pw = r["password"]
            masked = pw[:2] + "*" * (len(pw) - 4) + pw[-2:] if len(pw) > 4 else "***"
            logger.info(f"  📁 Breaches: {', '.join(r['breaches'])}")
            logger.info(f"     Email: {r['email']}")
            logger.info(f"     Password (masked): {masked}")
            logger.info(f"     Password (full): {pw}")
    else:
        logger.info(f"\n❌ {target_email} NOT found in 280GB archive")
    
    # Cleanup
    for wf, ws in worker_sqfs:
        wf.close()
    
    return final_results


# ============ MAIN ============
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BreachCheck Archive Search (Tor)")
    parser.add_argument("email", help="Email to search for")
    parser.add_argument("--workers", type=int, default=20, help="Number of parallel Tor workers")
    parser.add_argument("--tor-port", type=int, default=9050, help="Tor SOCKS5 port")
    parser.add_argument("--full", action="store_true", help="Search all files (don't stop at first match)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()
    
    results = search_archive_tor(
        args.email,
        max_workers=args.workers,
        tor_port=args.tor_port,
        stop_on_first=not args.full
    )
    
    if results and args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif results:
        print(f"\n{'='*40}")
        print(f"Found {len(results)} unique result(s):")
        for r in results:
            print(f"  {r['email']}:{r['password']} [{', '.join(r['breaches'])}]")
    else:
        print(f"\n❌ Not found: {args.email}")
