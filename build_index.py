#!/usr/bin/env python3
"""
BreachCheck Fast Search v5 — Index Builder + Instant Search
=============================================================
Two tools:
  1. build_index.py  — One-time scan of 280GB archive → local SQLite index
  2. search_fast.py  — Instant search using local index (< 1 second)

Usage:
  # Step 1: Build index (one-time, takes ~2-4 hours via Tor)
  python3 build_index.py --workers 20

  # Step 2: Search (instant!)
  python3 search_fast.py user@example.com
  python3 search_fast.py user@gmail.com --domain
"""

import sys
import os
import time
import json
import random
import sqlite3
import threading
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("❌ pip install requests --break-system-packages")
    sys.exit(1)

try:
    from dissect.squashfs import SquashFS
except ImportError:
    print("❌ pip install dissect --break-system-packages")
    sys.exit(1)

# ============ CONFIG ============
SQUASHFS_URL = (
    "https://ia600706.us.archive.org/20/items/"
    "2019-collection-1-5-antipublic-tri-pack-squashfs/"
    "Collection_%231-%235_Antipublic_tri-pack.squashfs"
)

TOR_HOST = "127.0.0.1"
TOR_PORT = 9050
DB_PATH = "breachcheck_index.db"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
    "curl/8.5.0",
    "Wget/1.21.4",
]

# ============ COLORS ============
class C:
    R = "\033[0m"
    B = "\033[1m"
    RED = "\033[91m"
    GRN = "\033[92m"
    YLW = "\033[93m"
    BLU = "\033[94m"
    MAG = "\033[95m"
    CYN = "\033[96m"


def banner():
    print(f"""{C.CYN}{C.B}
  ╔═══════════════════════════════════════════════════════════╗
  ║   🔍 BreachCheck Fast Search v5.0                          ║
  ║   Local Index • Instant Search • Tor • Parallel           ║
  ╚═══════════════════════════════════════════════════════════╝
  {C.R}""", flush=True)


# ============ TOR ============
def check_tor(port=TOR_PORT):
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((TOR_HOST, port))
        s.close()
        return True
    except:
        return False


def start_tor(port=TOR_PORT):
    if check_tor(port):
        print(f"  {C.GRN}✅{C.R} Tor running on port {port}")
        return True
    print(f"  {C.YLW}⚠{C.R} Starting Tor...")
    for cmd in [["systemctl", "start", "tor"], ["service", "tor", "start"]]:
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
            time.sleep(5)
            if check_tor(port):
                print(f"  {C.GRN}✅{C.R} Tor started")
                return True
        except:
            pass
    try:
        tor_path = shutil.which("tor")
        if tor_path:
            subprocess.Popen([tor_path, "--SocksPort", str(port), "--IsolateSOCKSAuth", "1"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(10)
            if check_tor(port):
                print(f"  {C.GRN}✅{C.R} Tor started")
                return True
    except:
        pass
    print(f"  {C.RED}❌{C.R} Start Tor manually: sudo systemctl start tor")
    return False


# ============ TOR HTTP RANGE FILE ============
class TorHttpRangeFile:
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
        self.session = requests.Session()
        self.session.proxies = {
            "http": f"socks5h://worker{worker_id}:circuit{worker_id}_{random.randint(1000,9999)}@{tor_host}:{tor_port}",
            "https": f"socks5h://worker{worker_id}:circuit{worker_id}_{random.randint(1000,9999)}@{tor_host}:{tor_port}",
        }
        self.session.headers["User-Agent"] = random.choice(USER_AGENTS)
        for _ in range(5):
            try:
                resp = self.session.head(url, timeout=60, allow_redirects=True)
                self.size = int(resp.headers.get('content-length', 0))
                if self.size > 0: break
            except:
                time.sleep(3)
        if self.size == 0:
            raise Exception(f"[W{worker_id}] Failed to get file size")

    def seekable(self): return True
    def seek(self, offset, whence=0):
        if whence == 0: self.pos = offset
        elif whence == 1: self.pos += offset
        elif whence == 2: self.pos = self.size + offset
        return self.pos
    def tell(self): return self.pos
    def read(self, size=-1):
        if size == -1: size = self.size - self.pos
        if size == 0: return b''
        if self.pos >= self.size: return b''
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
        headers = {'Range': f'bytes={start}-{end}', 'User-Agent': random.choice(USER_AGENTS)}
        for attempt in range(5):
            try:
                resp = self.session.get(self.url, headers=headers, timeout=120)
                if resp.status_code in (206, 200):
                    self.cache[block_idx] = resp.content
                    self.cache_order.append(block_idx)
                    if len(self.cache_order) > self.max_cache:
                        old = self.cache_order.pop(0)
                        if old != block_idx: self.cache.pop(old, None)
                    return
                elif resp.status_code == 429: time.sleep(30)
                else: time.sleep(5)
            except:
                if attempt < 4: time.sleep(5)
                else: raise
        raise Exception(f"[W{self.worker_id}] Block {block_idx} failed")
    def close(self):
        self.cache.clear()
        self.session.close()


# ============ INDEX BUILDER ============
def build_index(max_workers=20, tor_port=TOR_PORT):
    """Scan entire archive and build local SQLite index."""
    
    banner()
    print(f"  {C.CYN}{C.B}{'━'*58}")
    print(f"  INDEX BUILDER — One-time scan of 280GB archive")
    print(f"  {'━'*58}{C.R}\n")
    
    # Check if index already exists
    if os.path.exists(DB_PATH):
        size_gb = os.path.getsize(DB_PATH) / 1024**3
        print(f"  {C.YLW}⚠{C.R} Index exists: {DB_PATH} ({size_gb:.1f}GB)")
        answer = input(f"  {C.YLW}Rebuild? [y/N]:{C.R} ").strip().lower()
        if answer != 'y':
            print(f"  {C.BLU}ℹ{C.R} Use search_fast.py to search the existing index")
            return
    
    if not start_tor(tor_port):
        return
    
    # Create database
    print(f"  {C.BLU}ℹ{C.R} Creating SQLite database: {DB_PATH}")
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-200000")  # 200MB cache
    db.execute("""CREATE TABLE IF NOT EXISTS records (
        email TEXT NOT NULL,
        password TEXT NOT NULL,
        breach TEXT NOT NULL,
        PRIMARY KEY (email, password, breach)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_email ON records(email)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_domain ON records(email)")
    db.commit()
    
    # ============ Phase 1: Get file list ============
    print(f"\n  {C.BLU}ℹ{C.R} Opening SquashFS via Tor...")
    t0 = time.time()
    
    list_file = TorHttpRangeFile(SQUASHFS_URL, worker_id=0, block_size=4*1024*1024,
                                 cache_size=500, tor_port=tor_port)
    list_sqfs = SquashFS(list_file)
    
    all_files = []
    seen_names = set()
    for top_dir in list_sqfs.root.iterdir():
        if not top_dir.is_dir(): continue
        for sub in top_dir.iterdir():
            if sub.is_file() and sub.name.endswith('.txt') and sub.size > 1000:
                key = f"{sub.name}:{sub.size}"
                if key not in seen_names:
                    all_files.append((top_dir.name, sub.name, sub.size))
                    seen_names.add(key)
            elif sub.is_dir():
                for f in sub.iterdir():
                    if f.is_file() and f.name.endswith('.txt') and f.size > 1000:
                        key = f"{f.name}:{f.size}"
                        if key not in seen_names:
                            all_files.append((f"{top_dir.name}/{sub.name}", f.name, f.size))
                            seen_names.add(key)
    
    total_files = len(all_files)
    list_file.close()
    
    print(f"  {C.GRN}✅{C.R} {total_files:,} unique files | {time.time()-t0:.1f}s")
    
    # ============ Phase 2: Open workers ============
    print(f"  {C.BLU}ℹ{C.R} Opening {max_workers} Tor circuits...")
    worker_sqfs = []
    for i in range(max_workers):
        try:
            wf = TorHttpRangeFile(SQUASHFS_URL, worker_id=i+1, block_size=4*1024*1024,
                                  cache_size=300, tor_port=tor_port)
            ws = SquashFS(wf)
            worker_sqfs.append((wf, ws))
            sys.stdout.write(f"\r  {C.CYN}Worker {i+1}/{max_workers}{C.R}")
            sys.stdout.flush()
        except:
            if not worker_sqfs:
                print(f"\n  {C.RED}❌{C.R} No workers available")
                return
    sys.stdout.write("\n")
    
    # Build file maps
    print(f"  {C.BLU}ℹ{C.R} Building file index per worker...")
    worker_files = []
    for wf, ws in worker_sqfs:
        wf_map = {}
        for top_dir in ws.root.iterdir():
            if not top_dir.is_dir(): continue
            for sub in top_dir.iterdir():
                if sub.is_file() and sub.name.endswith('.txt') and sub.size > 1000:
                    wf_map[f"{sub.name}:{sub.size}"] = (top_dir.name, sub)
                elif sub.is_dir():
                    for f in sub.iterdir():
                        if f.is_file() and f.name.endswith('.txt') and f.size > 1000:
                            wf_map[f"{f.name}:{f.size}"] = (f"{top_dir.name}/{sub.name}", f)
        worker_files.append(wf_map)
    
    print(f"  {C.GRN}✅{C.R} All {len(worker_sqfs)} workers ready\n")
    
    # ============ Phase 3: Extract & Index ============
    print(f"  {C.CYN}{C.B}{'━'*58}")
    print(f"  EXTRACTING & INDEXING {total_files:,} FILES")
    print(f"  {'━'*58}{C.R}\n")
    
    t_start = time.time()
    files_done = 0
    records_inserted = 0
    lock = threading.Lock()
    batch_buffer = []
    BATCH_SIZE = 10000
    
    def flush_batch():
        nonlocal batch_buffer, records_inserted
        if len(batch_buffer) >= BATCH_SIZE:
            with lock:
                db.executemany(
                    "INSERT OR IGNORE INTO records (email, password, breach) VALUES (?, ?, ?)",
                    batch_buffer[:BATCH_SIZE]
                )
                records_inserted += db.total_changes
                db.commit()
                batch_buffer = batch_buffer[BATCH_SIZE:]
    
    def extract_file(args):
        worker_idx, sqfs_file, breach_name, file_name, file_size = args
        records = []
        try:
            fh = sqfs_file.open()
            chunk_size = 4 * 1024 * 1024
            leftover = b""
            while True:
                data = fh.read(chunk_size)
                if not data:
                    if leftover:
                        text = leftover.decode('utf-8', errors='replace')
                        for line in text.split('\n'):
                            r = parse_line(line, breach_name)
                            if r: records.append(r)
                    break
                buffer = leftover + data
                cut = buffer.rfind(b'\n')
                if cut == -1:
                    leftover = buffer
                    continue
                chunk_text = buffer[:cut].decode('utf-8', errors='replace')
                leftover = buffer[cut+1:]
                for line in chunk_text.split('\n'):
                    r = parse_line(line, breach_name)
                    if r: records.append(r)
            fh.close()
        except:
            pass
        return records
    
    def parse_line(line, breach_name):
        line = line.strip()
        if not line or ':' not in line:
            return None
        parts = line.rsplit(':', 1)
        if len(parts) != 2:
            return None
        email = parts[0].strip().lower().lstrip('\ufeff')
        password = parts[1].strip()
        if '@' not in email or not password:
            return None
        return (email, password, breach_name)
    
    # Distribute files
    file_queue = []
    for i, (breach, fname, fsize) in enumerate(all_files):
        worker_idx = i % len(worker_sqfs)
        key = f"{fname}:{fsize}"
        entry = worker_files[worker_idx].get(key)
        if entry:
            file_queue.append((worker_idx, entry[1], entry[0], fname, fsize))
    
    print(f"  {C.BLU}ℹ{C.R} Processing {len(file_queue):,} files...\n")
    
    with ThreadPoolExecutor(max_workers=len(worker_sqfs)) as executor:
        futures = {executor.submit(extract_file, f): f for f in file_queue}
        
        for future in as_completed(futures):
            with lock:
                files_done += 1
                current = files_done
            
            try:
                records = future.result()
                if records:
                    with lock:
                        batch_buffer.extend(records)
                        if len(batch_buffer) >= BATCH_SIZE:
                            db.executemany(
                                "INSERT OR IGNORE INTO records (email, password, breach) VALUES (?, ?, ?)",
                                batch_buffer[:BATCH_SIZE]
                            )
                            batch_buffer = batch_buffer[BATCH_SIZE:]
                            db.commit()
            except:
                pass
            
            # Progress
            if current % 25 == 0 or current == total_files:
                elapsed = time.time() - t_start
                rate = current / elapsed if elapsed > 0 else 0
                eta = (total_files - current) / rate if rate > 0 else 0
                pct = current / total_files * 100
                filled = int(35 * current / total_files)
                bar = "█" * filled + "░" * (35 - filled)
                
                # Get current record count
                cur = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
                
                sys.stdout.write(
                    f"\r  {C.CYN}{bar}{C.R} {pct:5.1f}% | "
                    f"{current:,}/{total_files:,} | "
                    f"{rate:.1f} f/s | "
                    f"ETA: {eta/60:.0f}m | "
                    f"{C.GRN}Records: {cur:,}{C.R}  "
                )
                sys.stdout.flush()
    
    # Flush remaining
    if batch_buffer:
        with lock:
            db.executemany(
                "INSERT OR IGNORE INTO records (email, password, breach) VALUES (?, ?, ?)",
                batch_buffer
            )
            db.commit()
    
    elapsed = time.time() - t_start
    sys.stdout.write("\n")
    
    # ============ Stats ============
    total_records = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    unique_emails = db.execute("SELECT COUNT(DISTINCT email) FROM records").fetchone()[0]
    db_size = os.path.getsize(DB_PATH) / 1024**3
    
    print(f"\n  {C.GRN}{C.B}{'━'*58}")
    print(f"  ✅ INDEX BUILD COMPLETE")
    print(f"  {'━'*58}{C.R}\n")
    print(f"  {C.BLU}ℹ{C.R} Time: {elapsed/60:.1f} minutes")
    print(f"  {C.BLU}ℹ{C.R} Files processed: {files_done:,}/{total_files:,}")
    print(f"  {C.BLU}ℹ{C.R} Total records: {C.GRN}{total_records:,}{C.R}")
    print(f"  {C.BLU}ℹ{C.R} Unique emails: {C.GRN}{unique_emails:,}{C.R}")
    print(f"  {C.BLU}ℹ{C.R} Database size: {C.YLW}{db_size:.1f}GB{C.R}")
    print(f"  {C.BLU}ℹ{C.R} Location: {C.B}{DB_PATH}{C.R}")
    print(f"\n  {C.GRN}✅{C.R} Now use: {C.B}python3 search_fast.py user@example.com{C.R}")
    
    # Cleanup
    for wf, ws in worker_sqfs:
        wf.close()
    db.close()


# ============ MAIN ============
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BreachCheck Index Builder")
    parser.add_argument("--workers", type=int, default=20, help="Number of Tor workers")
    parser.add_argument("--tor-port", type=int, default=9050, help="Tor SOCKS5 port")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Database path")
    args = parser.parse_args()
    
    DB_PATH = args.db
    build_index(max_workers=args.workers, tor_port=args.tor_port)
