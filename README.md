# 🔍 BreachCheck Fast Search v5

Search a 280GB SquashFS breach archive with **instant results** (< 1 second).

## How It Works

```
Step 1 (one-time):  build_index.py  →  Scans 280GB archive via Tor  →  Local SQLite index
                                                     ↓
Step 2 (instant):   search_fast.py  →  Searches local index  →  Results in < 1 second
```

## ✨ Features

- ⚡ **Instant Search** — Results in < 1 second after index is built
- 🎯 **Domain Filter** — Search by email or by domain (e.g., all gmail.com records)
- 🧅 **Tor Integration** — Each worker uses a separate Tor circuit (different IP)
- 🔄 **Auto Dedup** — Same (email + password) = one record
- 📊 **Statistics** — Database stats, top breaches, domain counts
- 📤 **Export** — Export domain results to JSON
- 🖥️ **Interactive UI** — Terminal menu with colors and progress bars

## Installation

```bash
git clone https://github.com/Youssefzdb/breachcheck-search.git
cd breachcheck-search

pip install -r requirements.txt --break-system-packages

# Start Tor
sudo systemctl start tor

# Enable stream isolation (different IP per worker)
echo "SocksPort 9050 IsolateSOCKSAuth" | sudo tee -a /etc/tor/torrc
sudo systemctl restart tor
```

## Usage

### Step 1: Build Index (one-time, ~2-4 hours)

```bash
python3 build_index.py --workers 20
```

This scans the entire 280GB archive via Tor and builds a local SQLite database.
- Time: ~2-4 hours (depends on Tor speed and worker count)
- Storage: ~5-8GB SQLite database
- Only needs to be done ONCE

### Step 2: Search (instant!)

```bash
# Interactive mode
python3 search_fast.py

# CLI: Search by email
python3 search_fast.py user@example.com

# CLI: Search by domain
python3 search_fast.py gmail.com --domain
```

### Menu Options (search_fast.py)
1. **Search by email** — Instant lookup of a specific email
2. **Search by domain** — Find all records for a domain (e.g., gmail.com)
3. **Show stats** — Database statistics, top breaches, record counts
4. **Export domain** — Export all records for a domain to JSON
5. **Exit**

## Files

| File | Description |
|------|-------------|
| `build_index.py` | One-time index builder (scans 280GB archive → SQLite) |
| `search_fast.py` | Instant search using local index (< 1 second) |
| `search_ui.py` | v4 — Live search via Tor (no index needed, slower) |
| `search_tor.py` | v3 — CLI Tor search |
| `search_archive.py` | v2 — Non-Tor CLI search |
| `http_range_file.py` | HTTP Range file reader for SquashFS |
| `requirements.txt` | Python dependencies |

## Workflow

```
First time:
  build_index.py  ──→  280GB archive via Tor  ──→  breachcheck_index.db (5-8GB)
                                                         |
After that:                                               ↓
  search_fast.py  ──→  breachcheck_index.db  ──→  Results in < 1 second
```

## Requirements

- Python 3.8+
- Tor (with SOCKS5 proxy)
- ~8GB free disk space (for the index)
- `pip install requests pysocks dissect`

## License

For defensive cybersecurity purposes only.
