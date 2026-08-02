# 🔍 BreachCheck v5 — Server + Client Architecture

Search 280GB breach archive with **instant results** via a central API server.

## Architecture

```
                    ┌─────────────────┐
                    │   Server (1x)   │
                    │  SQLite Index   │
                    │  280GB archive  │
                    │  5-8GB DB       │
                    └────────┬────────┘
                             │ HTTP API
            ┌────────────────┼────────────────┐
            │                │                │
     ┌──────┴──┐    ┌───────┴──┐    ┌────────┴──┐
     │ Client 1 │    │ Client 2 │    │ Telegram  │
     │ CLI/TUI  │    │ CLI/TUI  │    │ Bot       │
     │ 0 MB     │    │ 0 MB     │    │ 0 MB      │
     └──────────┘    └──────────┘    └───────────┘
```

**One server** holds the index. **All clients** just query it — no 280GB download needed.

## Quick Start

### Server Setup (one-time)

```bash
# 1. Build the index (scans 280GB archive via Tor, ~2-4 hours)
python3 build_index.py --workers 20
# → Creates: breachcheck_index.db (5-8GB)

# 2. Start the API server
python3 server.py --port 8080
# → API available at http://localhost:8080

# With Telegram bot:
python3 server.py --port 8080 --telegram YOUR_BOT_TOKEN

# With API key protection:
python3 server.py --port 8080 --api-key SECRET_KEY
```

### Client Usage (instant!)

```bash
# Set server URL
export BREACHCHECK_SERVER=https://your-server.com:8080

# Interactive mode
python3 search_client.py --interactive

# CLI — search by email
python3 search_client.py user@example.com

# CLI — search by domain
python3 search_client.py gmail.com --domain

# CLI — plaintext output
python3 search_client.py user@example.com --txt

# CLI — database stats
python3 search_client.py --stats
```

## API Endpoints

| Endpoint | Method | Description | Output |
|----------|--------|-------------|--------|
| `/search?email=user@example.com` | GET | Search by email | JSON |
| `/search.txt?email=user@example.com` | GET | Search by email | Plaintext |
| `/domain?d=gmail.com&limit=100` | GET | Search by domain | JSON |
| `/domain.txt?d=gmail.com` | GET | Search by domain | Plaintext |
| `/stats` | GET | Database statistics | JSON |
| `/health` | GET | Server health | JSON |
| `/bulk` | POST | Search multiple emails | JSON |

### API Examples

```bash
# Search email (JSON)
curl "http://localhost:8080/search?email=user@example.com"

# Search email (plaintext)
curl "http://localhost:8080/search.txt?email=user@example.com"
# Output: user@example.com:password123 [BreachName]

# Search domain (JSON)
curl "http://localhost:8080/domain?d=gmail.com&limit=50"

# Bulk search
curl -X POST "http://localhost:8080/bulk" \
  -H "Content-Type: application/json" \
  -d '{"emails": ["user1@gmail.com", "user2@yahoo.com"]}'

# Database stats
curl "http://localhost:8080/stats"
```

## Deployment

### Docker (recommended)

```bash
# Build and run
docker build -t breachcheck .
docker run -p 8080:8080 -v ./breachcheck_index.db:/app/breachcheck_index.db breachcheck

# Or with docker-compose
docker-compose up -d
```

### Render

```bash
# 1. Push to GitHub
# 2. Create new Web Service on Render
# 3. Connect repo
# 4. Build Command: pip install -r requirements.txt
# 5. Start Command: python3 server.py --port $PORT --host 0.0.0.0
```

### VPS (DigitalOcean, Hetzner, etc.)

```bash
# 1. SSH to server
# 2. Clone repo
# 3. Build index (one-time)
python3 build_index.py --workers 20

# 4. Start server with screen/tmux
screen python3 server.py --port 8080 --api-key YOUR_SECRET

# 5. Point clients to server
export BREACHCHECK_SERVER=http://your-vps-ip:8080
```

## Files

| File | Description |
|------|-------------|
| `server.py` | API server (Flask) + Telegram bot |
| `search_client.py` | Lightweight client — queries server, shows results |
| `build_index.py` | One-time index builder (280GB archive → SQLite) |
| `search_fast.py` | Local search (if you have the DB locally) |
| `search_ui.py` | v4 — Live Tor search (no index needed) |
| `Dockerfile` | Docker deployment |
| `docker-compose.yml` | Docker Compose config |

## Workflow

```
Server Setup (one-time):
  build_index.py → 280GB via Tor → breachcheck_index.db (5-8GB)
                                        ↓
  server.py → Load DB → API on :8080

Clients (instant):
  search_client.py → HTTP GET /search?email=... → Results in < 1 second
  Telegram bot → /search user@example.com → Results in < 1 second
  curl /search.txt?email=... → Plaintext output
```

## Telegram Bot Commands

```
/search user@example.com   — Search for email
/domain gmail.com          — Search by domain  
/stats                     — Database statistics
/help                      — Show help
```

Or just send an email address directly to the bot.

## Requirements

**Server:**
- Python 3.8+
- ~8GB free disk space (for SQLite index)
- ~1GB RAM
- `pip install flask requests pysocks dissect`

**Client:**
- Python 3.8+
- `pip install requests`
- No disk space needed!

## License

For defensive cybersecurity purposes only.
