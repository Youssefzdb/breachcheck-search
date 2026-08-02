#!/usr/bin/env python3
"""
BreachCheck Client v5 — Lightweight Search Client
===================================================
لا يحمل أي بيانات — فقط يستعلم من السيرفر ويظهر النتائج plaintext.

Usage:
  python3 search_client.py user@example.com
  python3 search_client.py gmail.com --domain
  python3 search_client.py --interactive
"""

import sys
import os
import time
import json
import requests

# ============ CONFIG ============
# غيّر هذا الرابط برابط سيرفرك
SERVER_URL = os.environ.get("BREACHCHECK_SERVER", "http://localhost:8080")

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
  ║   🔍 BreachCheck Client v5.0                                ║
  ║   Fast Search • No Download • Instant Results               ║
  ╚═══════════════════════════════════════════════════════════╝
  {C.R}""", flush=True)


def mask_pw(pw):
    if len(pw) <= 4: return "***"
    return pw[:2] + "*" * (len(pw) - 4) + pw[-2:]


def check_server():
    """Check if server is online."""
    try:
        r = requests.get(f"{SERVER_URL}/health", timeout=5)
        data = r.json()
        return data
    except:
        return None


def search_email(email, plaintext=False):
    """Search for an email on the server."""
    t0 = time.time()
    
    if plaintext:
        # Use plaintext endpoint
        try:
            r = requests.get(f"{SERVER_URL}/search.txt", params={"email": email}, timeout=30)
            elapsed = time.time() - t0
            print(f"\n  {C.CYN}{'━'*58}")
            print(f"  🔍 {email} | {elapsed:.3f}s")
            print(f"  {'━'*58}{C.R}\n")
            if r.status_code == 200:
                print(r.text)
            elif r.status_code == 404:
                print(f"  {C.RED}❌ NOT FOUND{C.R}\n")
            else:
                print(f"  {C.RED}Error: {r.text}{C.R}")
            return
        except Exception as e:
            print(f"  {C.RED}❌ Connection error: {e}{C.R}")
            return
    
    try:
        r = requests.get(f"{SERVER_URL}/search", params={"email": email}, timeout=30)
        data = r.json()
        elapsed = time.time() - t0
        
        print(f"\n  {C.CYN}{C.B}{'━'*58}")
        print(f"  🔍 {email} | {data.get('search_time_ms', 0):.0f}ms (server) | {elapsed:.3f}s (total)")
        print(f"  {'━'*58}{C.R}\n")
        
        results = data.get("results", [])
        
        if results:
            print(f"  {C.GRN}🎯 FOUND {len(results)} record(s){C.R}\n")
            print(f"  {C.CYN}{'─'*55}")
            
            for i, res in enumerate(results, 1):
                em = res["email"]
                pw = res["password"]
                breach = res["breach"]
                print(f"  {C.B}#{i}{C.R}  {C.YLW}📁 {breach}{C.R}")
                print(f"      {C.B}Email:{C.R}     {em}")
                print(f"      {C.B}Password:{C.R}  {mask_pw(pw)}")
                print(f"      {C.B}Full PW:{C.R}   {pw}")
                if i < len(results):
                    print(f"  {C.CYN}{'─'*55}")
            
            print(f"  {C.CYN}{'─'*55}{C.R}")
            
            # Summary
            breaches = set(r["breach"] for r in results)
            passwords = set(r["password"] for r in results)
            print(f"\n  {C.B}Summary:{C.R}")
            print(f"    Breaches:      {C.YLW}{len(breaches)}{C.R}")
            print(f"    Unique PWs:    {C.YLW}{len(passwords)}{C.R}")
            print(f"    Total records: {C.YLW}{len(results)}{C.R}")
            
            # Save option
            save = input(f"\n  {C.YLW}Save to file? [y/N]:{C.R} ").strip().lower()
            if save == "y":
                fmt = input(f"  {C.YLW}Format: [1] Plaintext  [2] JSON:{C.R} ").strip()
                fname = f"result_{email.replace('@','_at_')}"
                if fmt == "2":
                    fname += ".json"
                    with open(fname, "w") as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                else:
                    fname += ".txt"
                    with open(fname, "w") as f:
                        for r in results:
                            f.write(f"{r['email']}:{r['password']} [{r['breach']}]\n")
                print(f"  {C.GRN}✅ Saved to {fname}{C.R}")
        else:
            print(f"  {C.RED}❌ NOT FOUND in {data.get('search_time_ms', 0):.0f}ms{C.R}")
        
        print()
        
    except Exception as e:
        print(f"  {C.RED}❌ Error: {e}{C.R}\n")


def search_domain(domain, limit=100):
    """Search for a domain on the server."""
    t0 = time.time()
    
    try:
        r = requests.get(f"{SERVER_URL}/domain", params={"d": domain, "limit": limit}, timeout=30)
        data = r.json()
        elapsed = time.time() - t0
        
        total = data.get("total_count", 0)
        returned = data.get("returned", 0)
        
        print(f"\n  {C.CYN}{C.B}{'━'*58}")
        print(f"  🔍 @{domain} | {data.get('search_time_ms', 0):.0f}ms (server) | {elapsed:.3f}s (total)")
        print(f"  {'━'*58}{C.R}\n")
        
        if total == 0:
            print(f"  {C.RED}❌ No records for @{domain}{C.R}\n")
            return
        
        results = data.get("results", [])
        print(f"  {C.YLW}📊 {total:,} total records | showing {returned}{C.R}\n")
        print(f"  {C.CYN}{'─'*55}")
        
        for i, res in enumerate(results, 1):
            em = res["email"]
            pw = res["password"]
            breach = res["breach"]
            print(f"  {C.B}#{i:4d}{C.R}  {em}:{mask_pw(pw)}  {C.YLW}[{breach}]{C.R}")
            if i % 50 == 0 and i < returned:
                cont = input(f"\n  {C.YLW}Show more? [Y/n]:{C.R} ").strip().lower()
                if cont == "n":
                    break
                print()
        
        print(f"  {C.CYN}{'─'*55}")
        
        # Export option
        if total > returned:
            print(f"\n  {C.B}Total:{C.R} {C.YLW}{total:,}{C.R} records")
            answer = input(f"  {C.YLW}Export all {total:,} records? [y/N]:{C.R} ").strip().lower()
            if answer == "y":
                export_domain_full(domain)
        
        print()
        
    except Exception as e:
        print(f"  {C.RED}❌ Error: {e}{C.R}\n")


def export_domain_full(domain):
    """Export all records for a domain."""
    print(f"  {C.BLU}ℹ{C.R} Downloading all records...")
    
    all_results = []
    offset = 0
    
    while True:
        r = requests.get(f"{SERVER_URL}/domain", 
                        params={"d": domain, "limit": 10000, "offset": offset}, timeout=60)
        data = r.json()
        results = data.get("results", [])
        if not results:
            break
        all_results.extend(results)
        offset += len(results)
        sys.stdout.write(f"\r  {C.CYN}Downloaded: {len(all_results):,}{C.R}")
        sys.stdout.flush()
        if len(results) < 10000:
            break
    
    sys.stdout.write("\n")
    
    fname = f"domain_{domain.replace('.','_')}.txt"
    with open(fname, "w") as f:
        for r in all_results:
            f.write(f"{r['email']}:{r['password']} [{r['breach']}]\n")
    
    print(f"  {C.GRN}✅ {len(all_results):,} records saved to {fname}{C.R}")


def show_stats():
    """Show server database statistics."""
    try:
        r = requests.get(f"{SERVER_URL}/stats", timeout=10)
        data = r.json()
        
        print(f"\n  {C.CYN}{C.B}{'━'*58}")
        print(f"  📊 DATABASE STATISTICS")
        print(f"  {'━'*58}{C.R}\n")
        
        print(f"  {C.B}Total records:{C.R}    {C.GRN}{data['total_records']:,}{C.R}")
        print(f"  {C.B}Unique emails:{C.R}    {C.GRN}{data['unique_emails']:,}{C.R}")
        print(f"  {C.B}Breach sources:{C.R}   {C.GRN}{data['breach_sources']}{C.R}")
        print(f"  {C.B}DB size:{C.R}          {C.YLW}{data['db_size_gb']}GB{C.R}")
        
        print(f"\n  {C.B}Top breach sources:{C.R}\n")
        for b in data.get("top_breaches", []):
            print(f"    {C.YLW}{b['count']:>10,}{C.R}  {b['name']}")
        
        print(f"\n  {C.B}Top domains:{C.R}\n")
        for d in data.get("top_domains", []):
            print(f"    {C.YLW}{d['count']:>10,}{C.R}  {d['domain']}")
        
        print()
        
    except Exception as e:
        print(f"  {C.RED}❌ Error: {e}{C.R}\n")


def interactive_menu():
    """Interactive terminal interface."""
    banner()
    
    # Check server
    print(f"  {C.BLU}ℹ{C.R} Connecting to: {C.B}{SERVER_URL}{C.R}")
    health = check_server()
    if health:
        print(f"  {C.GRN}✅{C.R} Server online | {C.YLW}{health['records']:,}{C.R} records | {health['db_size_gb']}GB")
    else:
        print(f"  {C.RED}❌ Server offline: {SERVER_URL}{C.R}")
        print(f"  {C.YLW}⚠{C.R} Set server URL: export BREACHCHECK_SERVER=https://your-server.com")
        print(f"  Or edit SERVER_URL in this file.\n")
        return
    
    while True:
        print(f"  {C.CYN}{C.B}{'━'*58}")
        print(f"  MENU")
        print(f"  {'━'*58}{C.R}")
        print(f"  {C.B}1.{C.R} Search by email (instant)")
        print(f"  {C.B}2.{C.R} Search by domain (instant)")
        print(f"  {C.B}3.{C.R} Database stats")
        print(f"  {C.B}4.{C.R} Export domain to file")
        print(f"  {C.B}5.{C.R} Plaintext output mode")
        print(f"  {C.B}6.{C.R} Exit")
        print()
        
        choice = input(f"  {C.YLW}Choice [1-6]:{C.R} ").strip()
        
        if choice == "6" or choice.lower() == "exit":
            print(f"\n  {C.CYN}Goodbye! 👋{C.R}\n")
            break
        
        elif choice == "1":
            email = input(f"  {C.YLW}Enter email:{C.R} ").strip()
            if email:
                search_email(email)
        
        elif choice == "2":
            domain = input(f"  {C.YLW}Enter domain (e.g. gmail.com):{C.R} ").strip()
            if domain:
                search_domain(domain)
        
        elif choice == "3":
            show_stats()
        
        elif choice == "4":
            domain = input(f"  {C.YLW}Enter domain to export:{C.R} ").strip()
            if domain:
                export_domain_full(domain)
        
        elif choice == "5":
            print(f"\n  {C.B}Plaintext mode{C.R} — results in email:password format\n")
            email = input(f"  {C.YLW}Enter email:{C.R} ").strip()
            if email:
                search_email(email, plaintext=True)
        
        else:
            print(f"  {C.RED}Invalid choice!{C.R}")


# ============ MAIN ============
if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
        
        if target == "--interactive" or target == "-i":
            interactive_menu()
        elif target == "--stats":
            show_stats()
        elif "--domain" in sys.argv:
            search_domain(target)
        elif "--txt" in sys.argv:
            search_email(target, plaintext=True)
        else:
            banner()
            health = check_server()
            if health:
                print(f"  {C.GRN}✅{C.R} Server: {C.YLW}{health['records']:,}{C.R} records\n")
                search_email(target)
            else:
                print(f"  {C.RED}❌ Server offline{C.R}")
    else:
        interactive_menu()
