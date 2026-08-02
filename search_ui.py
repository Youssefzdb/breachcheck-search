#!/usr/bin/env python3
"""
BreachCheck Search Tool v4 — Terminal UI + Domain Filter + Tor Auto-Start
==========================================================================
Two-phase search:
  Phase 1: Filter all records by domain (e.g., gmail.com) → collect matches
  Phase 2: Search within filtered records for specific email

Usage:
  python3 search_ui.py
  python3 search_ui.py user@example.com
"""

import sys
import os
import time
import json
import random
import logging
import threading
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    import requests
except ImportError:
    print("❌ Install requests: pip install requests --break-system-packages")
    sys.exit(1)

try:
    from dissect.squashfs import SquashFS
except ImportError:
    print("❌ Install dissect: pip install dissect --break-system-packages")
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
    "curl/8.5.0",
    "Wget/1.21.4",
    "Python-urllib/3.11",
]

# ============ TERMINAL UI ============
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"
    
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"


def banner():
    print(f"""{Colors.CYAN}{Colors.BOLD}
  ╔═══════════════════════════════════════════════════════════╗
  ║   🔍 BreachCheck Archive Search Tool v4.0                 ║
  ║   280GB SquashFS • Tor • Domain Filter • Parallel         ║
  ╚═══════════════════════════════════════════════════════════╝
  {Colors.RESET}""", flush=True)


def print_phase(num, title, color=Colors.CYAN):
    print(f"\n{color}{Colors.BOLD}{'━'*60}")
    print(f"  PHASE {num}: {title}")
    print(f"{'━'*60}{Colors.RESET}\n", flush=True)


def print_info(msg):
    print(f"  {Colors.BLUE}ℹ{Colors.RESET}  {msg}", flush=True)


def print_ok(msg):
    print(f"  {Colors.GREEN}✅{Colors.RESET}  {msg}", flush=True)


def print_warn(msg):
    print(f"  {Colors.YELLOW}⚠{Colors.RESET}  {msg}", flush=True)


def print_err(msg):
    print(f"  {Colors.RED}❌{Colors.RESET}  {msg}", flush=True)


def print_found(msg):
    print(f"  {Colors.GREEN}🎯{Colors.RESET}  {msg}", flush=True)


def progress_bar(current, total, width=40, label=""):
    if total == 0:
        return
    pct = current / total * 100
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    sys.stdout.write(f"\r  {Colors.CYAN}{bar}{Colors.RESET} {pct:5.1f}% | {current:,}/{total:,} {label}")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")
        sys.stdout.flush()


def mask_password(pw):
    if len(pw) <= 4:
        return "***"
    return pw[:2] + "*" * (len(pw) - 4) + pw[-2:]


# ============ TOR MANAGER ============
def check_tor_running(port=TOR_PORT):
    """Check if Tor SOCKS5 is listening."""
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
    """Try to start Tor automatically."""
    print_info("Checking Tor status...")
    
    if check_tor_running(port):
        print_ok(f"Tor is already running on port {port}")
        return True
    
    print_warn("Tor not detected. Attempting to start...")
    
    # Try systemctl
    try:
        subprocess.run(["systemctl", "start", "tor"], capture_output=True, timeout=10)
        time.sleep(5)
        if check_tor_running(port):
            print_ok("Tor started via systemctl")
            return True
    except:
        pass
    
    # Try service
    try:
        subprocess.run(["service", "tor", "start"], capture_output=True, timeout=10)
        time.sleep(5)
        if check_tor_running(port):
            print_ok("Tor started via service")
            return True
    except:
        pass
    
    # Try direct tor binary
    try:
        tor_path = shutil.which("tor")
        if tor_path:
            subprocess.Popen([tor_path, "--SocksPort", str(port), 
                            "--IsolateSOCKSAuth", "1"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(10)
            if check_tor_running(port):
                print_ok(f"Tor started directly on port {port}")
                return True
    except:
        pass
    
    print_err("Could not start Tor automatically.")
    print_warn("Please start Tor manually: sudo systemctl start tor")
    print_warn(f"Or: tor --SocksPort {port} --IsolateSOCKSAuth 1")
    return False


# ============ TOR HTTP RANGE FILE ============
class TorHttpRangeFile:
    """HTTP Range file reader through Tor SOCKS5 with stream isolation."""
    
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
        
        self.socks_user = f"worker{worker_id}"
        self.socks_pass = f"circuit{worker_id}_{random.randint(1000,9999)}"
        
        self.session = requests.Session()
        self.session.proxies = {
            "http": f"socks5h://{self.socks_user}:{self.socks_pass}@{tor_host}:{tor_port}",
            "https": f"socks5h://{self.socks_user}:{self.socks_pass}@{tor_host}:{tor_port}",
        }
        self.session.headers["User-Agent"] = random.choice(USER_AGENTS)
        
        for attempt in range(5):
            try:
                resp = self.session.head(url, timeout=60, allow_redirects=True)
                self.size = int(resp.headers.get('content-length', 0))
                if self.size > 0:
                    break
            except Exception as e:
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
                    time.sleep(30)
                else:
                    time.sleep(5)
            except Exception as e:
                if attempt < 4:
                    time.sleep(5)
                else:
                    raise
        raise Exception(f"[W{self.worker_id}] Failed block {block_idx}")
    
    def close(self):
        self.cache.clear()
        self.session.close()


# ============ SEARCH ENGINE ============
class BreachSearcher:
    def __init__(self, max_workers=20, tor_port=TOR_PORT):
        self.max_workers = max_workers
        self.tor_port = tor_port
        self.results_lock = threading.Lock()
        self.counters_lock = threading.Lock()
        
        # Phase 1: domain filter results
        self.domain_matches = []  # list of (email, password, breach, file)
        self.domain_count = 0
        
        # Phase 2: email search results  
        self.email_matches = {}  # (email, password) -> set of breaches
        self.email_count = 0
        
        # Stats
        self.files_done = 0
        self.bytes_read = 0
        self.stop_event = threading.Event()
        self.found_target = False
    
    def extract_domain(self, email):
        """Extract domain from email address."""
        if '@' in email:
            return email.split('@', 1)[1].lower()
        return None
    
    def get_file_list(self, sqfs):
        """Get all .txt files from SquashFS."""
        all_files = []
        for top_dir in sqfs.root.iterdir():
            if not top_dir.is_dir():
                continue
            for sub in top_dir.iterdir():
                if sub.is_file() and sub.name.endswith('.txt'):
                    if sub.size > 1000:  # Skip tiny files like README
                        all_files.append((top_dir.name, sub.name))
                elif sub.is_dir():
                    for f in sub.iterdir():
                        if f.is_file() and f.name.endswith('.txt'):
                            if f.size > 1000:
                                all_files.append((f"{top_dir.name}/{sub.name}", f.name))
        return all_files
    
    def search_file_domain(self, sqfs_file, dir_name, file_name, target_domain, target_email):
        """Phase 1+2 combined: filter by domain, then search for email within matches."""
        matches_domain = []
        matches_email = []
        
        if self.stop_event.is_set():
            return matches_domain, matches_email
        
        try:
            fh = sqfs_file.open()
            chunk_size = 4 * 1024 * 1024
            leftover = b""
            
            while True:
                if self.stop_event.is_set():
                    break
                data = fh.read(chunk_size)
                if not data:
                    if leftover:
                        text = leftover.decode('utf-8', errors='replace')
                        for line in text.split('\n'):
                            d_match, e_match = self._check_line(line, target_domain, target_email, dir_name)
                            if d_match: matches_domain.append(d_match)
                            if e_match: matches_email.append(e_match)
                    break
                
                buffer = leftover + data
                text = buffer.decode('utf-8', errors='replace')
                
                # Quick domain check
                if target_domain in text:
                    cut = buffer.rfind(b'\n')
                    if cut == -1:
                        leftover = buffer
                        continue
                    chunk_text = buffer[:cut].decode('utf-8', errors='replace')
                    leftover = buffer[cut+1:]
                    
                    for line in chunk_text.split('\n'):
                        d_match, e_match = self._check_line(line, target_domain, target_email, dir_name)
                        if d_match: matches_domain.append(d_match)
                        if e_match: matches_email.append(e_match)
                else:
                    leftover = buffer[-500:] if len(buffer) > 500 else buffer
            
            fh.close()
        except Exception as e:
            pass
        
        return matches_domain, matches_email
    
    def _check_line(self, line, target_domain, target_email, breach_name):
        """Check a line against domain and email. Returns (domain_match, email_match)."""
        line = line.strip()
        if not line or ':' not in line:
            return None, None
        
        # Phase 1: Domain filter (fast)
        if target_domain not in line.lower():
            return None, None
        
        parts = line.rsplit(':', 1)
        if len(parts) != 2:
            return None, None
        email = parts[0].strip().lower().lstrip('\ufeff')
        password = parts[1].strip()
        
        # Verify domain in email
        if '@' not in email:
            return None, None
        domain = email.split('@', 1)[1]
        
        if domain == target_domain:
            domain_match = (email, password, breach_name)
            
            # Phase 2: Check if this is also the target email
            email_match = None
            if target_email and email == target_email:
                email_match = (email, password, breach_name)
            
            return domain_match, email_match
        
        return None, None
    
    def search(self, target_email, max_workers=None):
        """Run two-phase search: domain filter → email search."""
        if max_workers is None:
            max_workers = self.max_workers
        
        target_email = target_email.strip().lower().lstrip('\ufeff')
        target_domain = self.extract_domain(target_email)
        
        if not target_domain:
            print_err(f"Invalid email: {target_email}")
            return []
        
        print_info(f"Target email: {Colors.BOLD}{target_email}{Colors.RESET}")
        print_info(f"Target domain: {Colors.BOLD}{target_domain}{Colors.RESET}")
        print_info(f"Strategy: Filter by '{target_domain}' first → search for email within matches")
        
        # ============ Phase 1: Open SquashFS & get file list ============
        print_phase(1, f"Scanning archive for domain: {target_domain}", Colors.YELLOW)
        
        t0 = time.time()
        print_info("Opening SquashFS via Tor...")
        
        list_file = TorHttpRangeFile(SQUASHFS_URL, worker_id=0, block_size=4*1024*1024,
                                     cache_size=500, tor_port=self.tor_port)
        list_sqfs = SquashFS(list_file)
        
        all_files = self.get_file_list(list_sqfs)
        total_files = len(all_files)
        print_ok(f"SquashFS opened in {time.time()-t0:.1f}s | {total_files:,} files to scan")
        list_file.close()
        
        # ============ Open worker connections ============
        print_info(f"Opening {max_workers} Tor circuits...")
        worker_sqfs = []
        for i in range(max_workers):
            try:
                wf = TorHttpRangeFile(SQUASHFS_URL, worker_id=i+1, block_size=4*1024*1024,
                                      cache_size=300, tor_port=self.tor_port)
                ws = SquashFS(wf)
                worker_sqfs.append((wf, ws))
                sys.stdout.write(f"\r  {Colors.CYAN}Worker {i+1}/{max_workers} connected{Colors.RESET}")
                sys.stdout.flush()
            except Exception as e:
                print_err(f"Worker {i+1} failed: {e}")
                if not worker_sqfs:
                    return []
        
        sys.stdout.write("\n")
        print_ok(f"{len(worker_sqfs)} Tor circuits ready (different IPs)")
        
        # Build file maps for each worker's SquashFS
        print_info("Building file index for each worker...")
        worker_files = []
        for wf, ws in worker_sqfs:
            wf_map = {}
            for top_dir in ws.root.iterdir():
                if not top_dir.is_dir(): continue
                for sub in top_dir.iterdir():
                    if sub.is_file() and sub.name.endswith('.txt') and sub.size > 1000:
                        wf_map[f"{top_dir.name}/{sub.name}"] = sub
                    elif sub.is_dir():
                        for f in sub.iterdir():
                            if f.is_file() and f.name.endswith('.txt') and f.size > 1000:
                                wf_map[f"{top_dir.name}/{sub.name}/{f.name}"] = f
            worker_files.append(wf_map)
        
        # ============ Phase 2: Parallel domain + email search ============
        print_phase(2, f"Searching for '{target_domain}' records + '{target_email}'", Colors.MAGENTA)
        
        t_start = time.time()
        self.files_done = 0
        self.domain_count = 0
        self.email_count = 0
        
        # Distribute files
        file_queue = []
        for i, (dir_name, file_name) in enumerate(all_files):
            worker_idx = i % len(worker_sqfs)
            full_path = f"{dir_name}/{file_name}"
            sqfs_file = worker_files[worker_idx].get(full_path)
            if sqfs_file:
                file_queue.append((worker_idx, sqfs_file, dir_name, file_name))
        
        print_info(f"Searching {len(file_queue):,} files with {len(worker_sqfs)} workers...")
        print()
        
        def do_search(args):
            worker_idx, sqfs_file, dir_name, file_name = args
            return self.search_file_domain(sqfs_file, dir_name, file_name, 
                                           target_domain, target_email)
        
        with ThreadPoolExecutor(max_workers=len(worker_sqfs)) as executor:
            futures = {executor.submit(do_search, f): f for f in file_queue}
            
            for future in as_completed(futures):
                with self.counters_lock:
                    self.files_done += 1
                    current = self.files_done
                
                try:
                    d_matches, e_matches = future.result()
                    
                    if d_matches:
                        with self.results_lock:
                            self.domain_count += len(d_matches)
                            for em, pw, breach in e_matches:
                                key = (em, pw)
                                if key not in self.email_matches:
                                    self.email_matches[key] = set()
                                self.email_matches[key].add(breach)
                                self.email_count += 1
                                self.found_target = True
                                
                                # Print found results immediately
                                masked = mask_password(pw)
                                print(f"\r  {Colors.GREEN}🎯 FOUND: {em}:{masked} in {breach}{Colors.RESET}")
                    
                except Exception as e:
                    pass
                
                # Progress
                if current % 25 == 0 or current == total_files:
                    elapsed = time.time() - t_start
                    rate = current / elapsed if elapsed > 0 else 0
                    eta = (total_files - current) / rate if rate > 0 else 0
                    pct = current / total_files * 100
                    
                    filled = int(35 * current / total_files)
                    bar = "█" * filled + "░" * (35 - filled)
                    
                    sys.stdout.write(
                        f"\r  {Colors.CYAN}{bar}{Colors.RESET} {pct:5.1f}% | "
                        f"{current:,}/{total_files:,} files | "
                        f"{rate:.1f} f/s | "
                        f"ETA: {eta/60:.0f}m | "
                        f"{Colors.YELLOW}Domain: {self.domain_count:,}{Colors.RESET} | "
                        f"{Colors.GREEN}Found: {self.email_count}{Colors.RESET}  "
                    )
                    sys.stdout.flush()
                
                # Stop early if found (optional)
                # if self.found_target and self.email_count > 0:
                #     self.stop_event.set()
                #     break
        
        elapsed = time.time() - t_start
        sys.stdout.write("\n")
        
        # ============ Results ============
        print(f"\n{'━'*60}")
        print(f"  {Colors.BOLD}SEARCH RESULTS{Colors.RESET}")
        print(f"{'━'*60}\n")
        
        print_info(f"Search time: {elapsed/60:.1f} minutes")
        print_info(f"Files scanned: {self.files_done:,}/{total_files:,}")
        print_info(f"Domain '{target_domain}' records found: {Colors.YELLOW}{self.domain_count:,}{Colors.RESET}")
        print_info(f"Target email matches: {Colors.GREEN}{self.email_count}{Colors.RESET}")
        
        final_results = []
        for key, breaches in self.email_matches.items():
            final_results.append({
                "email": key[0],
                "password": key[1],
                "breaches": sorted(list(breaches))
            })
        
        if final_results:
            print(f"\n  {Colors.GREEN}{Colors.BOLD}🎯 MATCHES FOUND!{Colors.RESET}\n")
            for r in final_results:
                pw = r["password"]
                masked = mask_password(pw)
                print(f"  {Colors.CYAN}{'─'*50}")
                print(f"  {Colors.BOLD}Email:{Colors.RESET}    {r['email']}")
                print(f"  {Colors.BOLD}Password:{Colors.RESET} {masked}")
                print(f"  {Colors.BOLD}Full PW:{Colors.RESET}  {pw}")
                print(f"  {Colors.BOLD}Breaches:{Colors.RESET} {', '.join(r['breaches'])}")
                print(f"  {Colors.CYAN}{'─'*50}{Colors.RESET}")
        else:
            print(f"\n  {Colors.RED}{Colors.BOLD}❌ {target_email} NOT found in 280GB archive{Colors.RESET}")
            print_info(f"But found {self.domain_count:,} records for domain '{target_domain}'")
        
        # Cleanup
        for wf, ws in worker_sqfs:
            wf.close()
        
        return final_results


# ============ INTERACTIVE TERMINAL UI ============
def interactive_menu():
    """Interactive terminal interface."""
    # Default settings
    max_workers = 20
    tor_port = TOR_PORT
    
    banner()
    
    # Tor status
    tor_ok = start_tor()
    if not tor_ok:
        print_warn("Continuing without Tor (direct connection)...")
        use_tor = False
    else:
        use_tor = True
    
    print_ok(f"Tor: {'enabled' if use_tor else 'disabled'}")
    
    while True:
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'━'*60}")
        print(f"  MENU")
        print(f"{'━'*60}{Colors.RESET}")
        print(f"  {Colors.BOLD}1.{Colors.RESET} Search by email (full search)")
        print(f"  {Colors.BOLD}2.{Colors.RESET} Search by email (quick — stop at first match)")
        print(f"  {Colors.BOLD}3.{Colors.RESET} Search by domain only")
        print(f"  {Colors.BOLD}4.{Colors.RESET} Settings (workers, Tor port)")
        print(f"  {Colors.BOLD}5.{Colors.RESET} Exit")
        print()
        
        choice = input(f"  {Colors.YELLOW}Choice [1-5]:{Colors.RESET} ").strip()
        
        if choice == "5" or choice.lower() == "exit":
            print(f"\n  {Colors.CYAN}Goodbye! 👋{Colors.RESET}\n")
            break
        
        elif choice == "4":
            workers = input(f"  Workers (current {max_workers}): ").strip() or str(max_workers)
            port = input(f"  Tor port (current {tor_port}): ").strip() or str(tor_port)
            try:
                max_workers = int(workers)
                tor_port = int(port)
            except:
                pass
            print_ok(f"Settings updated: {max_workers} workers, port {tor_port}")
            continue
        
        elif choice in ("1", "2", "3"):
            email = input(f"  {Colors.YELLOW}Enter email or domain:{Colors.RESET} ").strip()
            if not email:
                print_warn("Empty input!")
                continue
            
            if not use_tor:
                print_warn("Tor not available — using direct connection")
                # Fall back to non-Tor search
                from http_range_file import HttpRangeFile
                # TODO: implement non-Tor fallback
                print_err("Tor required for this tool. Please start Tor first.")
                continue
            
            searcher = BreachSearcher(max_workers=max_workers, tor_port=tor_port)
            
            if choice == "3":
                # Domain-only search — search for all emails with this domain
                domain = email if '@' not in email else email.split('@')[1]
                # Create a fake email to extract domain
                fake_email = f"___nodomain___@{domain}"
                results = searcher.search(fake_email, max_workers=max_workers)
                print_info(f"Found {searcher.domain_count:,} records for {domain}")
            
            else:
                results = searcher.search(email, max_workers=max_workers)
            
            # Save results
            if results:
                filename = f"results_{email.replace('@','_at_')}_{int(time.time())}.json"
                with open(filename, 'w') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                print_ok(f"Results saved to: {filename}")
        
        else:
            print_warn("Invalid choice!")


# ============ MAIN ============
if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command-line mode
        email = sys.argv[1]
        workers = 20
        tor_port = TOR_PORT
        
        for i, arg in enumerate(sys.argv):
            if arg == "--workers" and i+1 < len(sys.argv):
                workers = int(sys.argv[i+1])
            elif arg == "--tor-port" and i+1 < len(sys.argv):
                tor_port = int(sys.argv[i+1])
        
        banner()
        start_tor(tor_port)
        
        searcher = BreachSearcher(max_workers=workers, tor_port=tor_port)
        results = searcher.search(email, max_workers=workers)
        
        if results:
            filename = f"results_{email.replace('@','_at_')}_{int(time.time())}.json"
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print_ok(f"Results saved to: {filename}")
    else:
        # Interactive mode
        interactive_menu()
