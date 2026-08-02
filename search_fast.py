#!/usr/bin/env python3
"""
BreachCheck Fast Search v5 — Instant Search
=============================================
Search the local SQLite index built by build_index.py.
Results in < 1 second!

Usage:
  python3 search_fast.py user@example.com
  python3 search_fast.py user@gmail.com --domain
  python3 search_fast.py gmail.com --domain
"""

import sys
import os
import time
import sqlite3
import json

DB_PATH = "breachcheck_index.db"

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


def mask_pw(pw):
    if len(pw) <= 4: return "***"
    return pw[:2] + "*" * (len(pw) - 4) + pw[-2:]


def search_by_email(db, email):
    """Search for exact email — instant."""
    email = email.strip().lower().lstrip('\ufeff')
    
    print(f"\n  {C.CYN}{C.B}{'━'*58}")
    print(f"  🔍 SEARCHING FOR: {email}")
    print(f"  {'━'*58}{C.R}\n")
    
    t0 = time.time()
    
    cursor = db.execute(
        "SELECT email, password, breach FROM records WHERE email = ? ORDER BY breach",
        (email,)
    )
    results = cursor.fetchall()
    elapsed = time.time() - t0
    
    if results:
        print(f"  {C.GRN}🎯 FOUND {len(results)} record(s) in {elapsed:.3f}s{C.R}\n")
        print(f"  {C.CYN}{'─'*55}")
        
        for i, (em, pw, breach) in enumerate(results, 1):
            print(f"  {C.B}#{i}{C.R}  {C.YLW}📁 {breach}{C.R}")
            print(f"      {C.B}Email:{C.R}    {em}")
            print(f"      {C.B}Password:{C.R} {mask_pw(pw)}")
            print(f"      {C.B}Full PW:{C.R}  {pw}")
            if i < len(results):
                print(f"  {C.CYN}{'─'*55}")
        
        print(f"  {C.CYN}{'─'*55}{C.R}\n")
        
        # Breaches summary
        breaches = set(r[2] for r in results)
        passwords = set(r[1] for r in results)
        print(f"  {C.B}Summary:{C.R}")
        print(f"    Breaches:     {C.YLW}{len(breaches)}{C.R} ({', '.join(sorted(breaches))})")
        print(f"    Unique PWs:   {C.YLW}{len(passwords)}{C.R}")
        print(f"    Total records: {C.YLW}{len(results)}{C.R}")
        print(f"    Search time:  {C.GRN}{elapsed:.3f}s{C.R}\n")
    else:
        print(f"  {C.RED}❌ NOT FOUND: {email}{C.R}")
        print(f"  {C.BLU}ℹ{C.R} Search time: {elapsed:.3f}s\n")
    
    return results


def search_by_domain(db, domain, limit=100, export=False):
    """Search for all emails with a specific domain — instant."""
    domain = domain.strip().lower().lstrip('@')
    
    print(f"\n  {C.CYN}{C.B}{'━'*58}")
    print(f"  🔍 SEARCHING DOMAIN: @{domain}")
    print(f"  {'━'*58}{C.R}\n")
    
    t0 = time.time()
    
    # Count first
    count = db.execute(
        "SELECT COUNT(*) FROM records WHERE email LIKE ?",
        (f"%@{domain}",)
    ).fetchone()[0]
    
    elapsed_count = time.time() - t0
    
    print(f"  {C.YLW}📊 {count:,} records found for @{domain} ({elapsed_count:.3f}s){C.R}\n")
    
    if count == 0:
        print(f"  {C.RED}❌ No records for this domain{C.R}\n")
        return []
    
    # Get sample
    show = min(limit, count)
    cursor = db.execute(
        "SELECT email, password, breach FROM records WHERE email LIKE ? LIMIT ?",
        (f"%@{domain}", show)
    )
    results = cursor.fetchall()
    elapsed = time.time() - t0
    
    print(f"  {C.B}Showing first {show} of {count:,} records:{C.R}\n")
    print(f"  {C.CYN}{'─'*55}")
    
    for i, (em, pw, breach) in enumerate(results, 1):
        print(f"  {C.B}#{i:4d}{C.R}  {em}:{mask_pw(pw)}  {C.YLW}[{breach}]{C.R}")
        if i % 50 == 0 and i < show:
            cont = input(f"\n  {C.YLW}Show more? [Y/n]:{C.R} ").strip().lower()
            if cont == 'n':
                break
            print()
    
    print(f"  {C.CYN}{'─'*55}")
    
    # Unique emails count
    unique = db.execute(
        "SELECT COUNT(DISTINCT email) FROM records WHERE email LIKE ?",
        (f"%@{domain}",)
    ).fetchone()[0]
    
    print(f"\n  {C.B}Summary:{C.R}")
    print(f"    Total records:    {C.YLW}{count:,}{C.R}")
    print(f"    Unique emails:    {C.YLW}{unique:,}{C.R}")
    print(f"    Search time:      {C.GRN}{elapsed:.3f}s{C.R}")
    
    # Export option
    if export or count > show:
        answer = input(f"\n  {C.YLW}Export all {count:,} records to JSON? [y/N]:{C.R} ").strip().lower()
        if answer == 'y':
            export_path = f"domain_{domain.replace('.','_')}.json"
            print(f"  {C.BLU}ℹ{C.R} Exporting to {export_path}...")
            cursor = db.execute(
                "SELECT email, password, breach FROM records WHERE email LIKE ?",
                (f"%@{domain}",)
            )
            all_results = [{"email": r[0], "password": r[1], "breach": r[2]} for r in cursor.fetchall()]
            with open(export_path, 'w') as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)
            print(f"  {C.GRN}✅ Exported {len(all_results):,} records to {export_path}{C.R}")
    
    print()
    return results


def show_stats(db):
    """Show database statistics."""
    print(f"\n  {C.CYN}{C.B}{'━'*58}")
    print(f"  📊 DATABASE STATISTICS")
    print(f"  {'━'*58}{C.R}\n")
    
    t0 = time.time()
    
    total = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    emails = db.execute("SELECT COUNT(DISTINCT email) FROM records").fetchone()[0]
    breaches = db.execute("SELECT COUNT(DISTINCT breach) FROM records").fetchone()[0]
    
    db_size = os.path.getsize(DB_PATH) / 1024**3
    
    print(f"  {C.B}Total records:{C.R}    {C.GRN}{total:,}{C.R}")
    print(f"  {C.B}Unique emails:{C.R}    {C.GRN}{emails:,}{C.R}")
    print(f"  {C.B}Breach sources:{C.R}   {C.GRN}{breaches}{C.R}")
    print(f"  {C.B}Database size:{C.R}    {C.YLW}{db_size:.2f}GB{C.R}")
    print(f"  {C.B}Query time:{C.R}      {time.time()-t0:.3f}s")
    
    # Top breaches
    print(f"\n  {C.B}Top breach sources:{C.R}\n")
    cursor = db.execute(
        "SELECT breach, COUNT(*) as cnt FROM records GROUP BY breach ORDER BY cnt DESC LIMIT 10"
    )
    for breach, cnt in cursor:
        print(f"    {C.YLW}{cnt:>10,}{C.R}  {breach}")
    
    print()


def interactive_menu():
    """Interactive terminal interface."""
    print(f"""{C.CYN}{C.B}
  ╔═══════════════════════════════════════════════════════════╗
  ║   🔍 BreachCheck Fast Search v5.0                          ║
  ║   Local Index • Instant Search • < 1 second               ║
  ╚═══════════════════════════════════════════════════════════╝
  {C.R}""", flush=True)
    
    if not os.path.exists(DB_PATH):
        print(f"  {C.RED}❌ No index found: {DB_PATH}{C.R}")
        print(f"  {C.YLW}⚠{C.R} Run build_index.py first:")
        print(f"     python3 build_index.py --workers 20")
        return
    
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA cache_size=-100000")
    
    # Show stats on start
    show_stats(db)
    
    while True:
        print(f"  {C.CYN}{C.B}{'━'*58}")
        print(f"  MENU")
        print(f"  {'━'*58}{C.R}")
        print(f"  {C.B}1.{C.R} Search by email (instant)")
        print(f"  {C.B}2.{C.R} Search by domain (instant)")
        print(f"  {C.B}3.{C.R} Show database stats")
        print(f"  {C.B}4.{C.R} Export domain to JSON")
        print(f"  {C.B}5.{C.R} Exit")
        print()
        
        choice = input(f"  {C.YLW}Choice [1-5]:{C.R} ").strip()
        
        if choice == "5" or choice.lower() == "exit":
            print(f"\n  {C.CYN}Goodbye! 👋{C.R}\n")
            break
        
        elif choice == "1":
            email = input(f"  {C.YLW}Enter email:{C.R} ").strip()
            if email:
                results = search_by_email(db, email)
                if results:
                    save = input(f"  {C.YLW}Save to JSON? [y/N]:{C.R} ").strip().lower()
                    if save == 'y':
                        path = f"result_{email.replace('@','_at_')}.json"
                        with open(path, 'w') as f:
                            json.dump([{"email": r[0], "password": r[1], "breach": r[2]} 
                                      for r in results], f, indent=2, ensure_ascii=False)
                        print(f"  {C.GRN}✅ Saved to {path}{C.R}")
        
        elif choice == "2":
            domain = input(f"  {C.YLW}Enter domain (e.g. gmail.com):{C.R} ").strip()
            if domain:
                search_by_domain(db, domain, limit=100)
        
        elif choice == "3":
            show_stats(db)
        
        elif choice == "4":
            domain = input(f"  {C.YLW}Enter domain to export:{C.R} ").strip()
            if domain:
                domain = domain.strip().lower().lstrip('@')
                path = f"domain_{domain.replace('.','_')}.json"
                print(f"  {C.BLU}ℹ{C.R} Exporting all @{domain} records...")
                t0 = time.time()
                cursor = db.execute(
                    "SELECT email, password, breach FROM records WHERE email LIKE ?",
                    (f"%@{domain}",)
                )
                results = [{"email": r[0], "password": r[1], "breach": r[2]} for r in cursor.fetchall()]
                with open(path, 'w') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                print(f"  {C.GRN}✅ {len(results):,} records exported to {path} ({time.time()-t0:.1f}s){C.R}")
        
        else:
            print(f"  {C.RED}Invalid choice!{C.R}")
    
    db.close()


# ============ MAIN ============
if __name__ == "__main__":
    if len(sys.argv) > 1:
        # CLI mode
        target = sys.argv[1]
        domain_mode = "--domain" in sys.argv
        
        if not os.path.exists(DB_PATH):
            print(f"  {C.RED}❌ No index found: {DB_PATH}{C.R}")
            print(f"  Run: python3 build_index.py --workers 20")
            sys.exit(1)
        
        db = sqlite3.connect(DB_PATH)
        db.execute("PRAGMA journal_mode=WAL")
        
        if domain_mode:
            search_by_domain(db, target, limit=10000, export=True)
        else:
            results = search_by_email(db, target)
            if results:
                path = f"result_{target.replace('@','_at_')}.json"
                with open(path, 'w') as f:
                    json.dump([{"email": r[0], "password": r[1], "breach": r[2]} 
                              for r in results], f, indent=2, ensure_ascii=False)
                print(f"  {C.GRN}✅ Saved to {path}{C.R}")
        
        db.close()
    else:
        interactive_menu()
