# Tally Bridge — Setup Runbook (Windows)
**Phase 55.8 / Feb 2026** — one-way push of VHC bills → Tally Sales Vouchers.

## Architecture

```
                    [Internet]
                        |
   ┌────────────────────┴────────────────────┐
   │      VHC backend (ventureshrd.com)      │
   │  /api/tally/queue   /api/tally/ack      │
   └────────────────────┬────────────────────┘
                        │  HTTPS (X-Tally-Bridge-Token)
                        │  poll every 5 min
                        ↓
   ┌──────────────────────────────────────────┐
   │  Windows PC at Delhi office              │
   │  ┌────────────────────────────────────┐  │
   │  │ tally_bridge.py (this script)      │  │
   │  └──────────┬─────────────────────────┘  │
   │             │ POST XML to localhost:9000│
   │             ↓                            │
   │  ┌────────────────────────────────────┐  │
   │  │ Tally Prime / Tally.ERP 9          │  │
   │  │ (XML gateway enabled on :9000)     │  │
   │  └────────────────────────────────────┘  │
   └──────────────────────────────────────────┘
```

**Why this pattern?** Tally is LAN-only on port 9000. Instead of exposing
your office network to the internet, the bridge polls VHC outbound (HTTPS),
which works through any firewall without configuration.

---

## One-time setup on the Tally PC

### 1. Enable Tally's HTTP/XML gateway

**Tally Prime:**
1. From any screen press `F11` (Features)
2. Choose **Advanced Capabilities → ODBC/Tally HTTP Server**
3. Set **Enable Tally Server: Yes**
4. **Port: 9000** (default — change only if 9000 is in use)
5. Set **Allow remote connection: Yes** (only the bridge will connect via localhost)
6. Press `Ctrl+A` to save

**Tally.ERP 9:**
1. `Gateway of Tally → F12: Configure → Advanced Configuration`
2. **Tally is acting as: Both** *(Client and Server)*
3. **Enable ODBC Server: Yes**, **Port: 9000**
4. Press `Ctrl+A` to save

Verify with a browser on the Tally PC: open `http://127.0.0.1:9000`. You should see Tally's response (XML or "Tally Server Active").

### 2. Install Python + script

```cmd
:: 1. Install Python 3.11+ (https://python.org/downloads — tick "Add to PATH")
py -3 --version

:: 2. Install requests
py -3 -m pip install requests

:: 3. Create install folder + copy files
mkdir C:\VHCTallyBridge
copy tally_bridge.py        C:\VHCTallyBridge\
copy tally_bridge.ini.example  C:\VHCTallyBridge\tally_bridge.ini
```

### 3. Configure

Open `C:\VHCTallyBridge\tally_bridge.ini` in Notepad and fill in:

```ini
[vhc]
base_url     = https://ventureshrd.com
bridge_token = <ASK ADMIN FOR THE VALUE OF TALLY_BRIDGE_TOKEN>
poll_seconds = 300

[tally]
gateway_url = http://127.0.0.1:9000
company     = VENTURE HRD CENTRE PVT LTD
timeout_sec = 30

[bridge]
log_path    = C:\VHCTallyBridge\bridge.log
batch_size  = 25
```

> ⚠️ The `company` value MUST exactly match the company name as shown in
> Tally's "List of Companies" screen. Case-sensitive, no extra spaces.

### 4. Generate ledgers in Tally (one-time per client)

Before the very first bill for a new client arrives, the client's
ledger must exist in Tally. Either:

- **Manually**: In Tally, create a ledger under **Sundry Debtors** with the
  client's legal name and GSTIN.
- **Programmatically**: Open a future Phase 55.9 "Bulk ledger sync" feature.

In addition, these GST ledgers must exist (one-time setup):

| Ledger Name | Under | GST Type |
|---|---|---|
| `Sales - Placement Consultancy` | Sales Accounts | Services |
| `Output IGST @ 18%` | Duties & Taxes | IGST |
| `Output CGST @ 9%`  | Duties & Taxes | CGST |
| `Output SGST @ 9%`  | Duties & Taxes | SGST |

(If you've already been billing manually in Tally, these already exist.)

### 5. Test once

```cmd
cd C:\VHCTallyBridge
py -3 tally_bridge.py --once
```

You should see:
```
2026-02-XX 10:30:00 [INFO] One-shot: 3 bill(s).
2026-02-XX 10:30:01 [INFO]   VHC/26-27/4 success=True vch_id=1247 err=None
```

Open Tally → **Day Book** → today's date → you'll see the new Sales Vouchers.

### 6. Install as Windows Service (recommended)

Using **NSSM** (free, ~500 KB):

1. Download NSSM from https://nssm.cc/download
2. Extract `nssm.exe` to `C:\VHCTallyBridge\`
3. Run as Administrator:

```cmd
cd C:\VHCTallyBridge
nssm install VHCTallyBridge
```

In the GUI dialog:
- **Path**: `C:\Windows\py.exe`
- **Arguments**: `-3 C:\VHCTallyBridge\tally_bridge.py --config C:\VHCTallyBridge\tally_bridge.ini`
- **Startup directory**: `C:\VHCTallyBridge`
- Tab **I/O** → Stdout/Stderr: `C:\VHCTallyBridge\service.log`
- Tab **Details** → Display name: `VHC Tally Bridge`
- Click **Install service**

Start it:
```cmd
nssm start VHCTallyBridge
```

Verify it's running:
```cmd
sc query VHCTallyBridge
type C:\VHCTallyBridge\bridge.log
```

The bridge will auto-start on every Windows boot.

---

## Operations

### Daily

Nothing. The bridge runs by itself. Check the log if a client reports a
missing voucher in Tally.

### Weekly

Tail the log to confirm heartbeats are firing:
```cmd
type C:\VHCTallyBridge\bridge.log | findstr "HB"
```

### When a bill fails to push

The VHC backend marks the bill as `tally.pushed=false` with the error
message. Inspect via:
```bash
# On the server
mongosh "$MONGO_URL" --eval '
  db.bills.find(
    {"tally.pushed": false, "tally.last_error": {$exists: true}},
    {bill_number:1, "tally.last_error":1, "tally.last_attempt_at":1, _id:0}
  ).limit(20).toArray()
'
```

Common errors:

| Error | Cause | Fix |
|---|---|---|
| `Could not find LEDGER 'XYZ'` | Client ledger doesn't exist in Tally | Create the ledger in Tally manually |
| `ConnectionRefused — is Tally running` | Tally not running, or XML gateway disabled | Restart Tally and re-enable gateway |
| `Voucher Type 'Sales' does not exist` | Tally company doesn't have a Sales voucher type | Create it under **Accounts Info → Voucher Types** |
| `Duplicate REMOTEID` | Bill was already pushed (idempotent retry) | Already success — flip `tally.pushed=true` manually |

### To re-push a bill manually (after fixing root cause)

```bash
mongosh "$MONGO_URL" --eval '
  db.bills.updateOne({bill_number:"VHC/26-27/4"}, {$set:{"tally.pushed":false}})
'
```
The bridge will pick it up within `poll_seconds` and retry.

### Pause the bridge temporarily

```cmd
nssm stop VHCTallyBridge
```
VHC keeps queueing bills. Resume with `nssm start VHCTallyBridge` and
the queue drains.

---

## Security notes

- The `TALLY_BRIDGE_TOKEN` is a long random string and is the ONLY auth
  between the bridge and VHC. Treat it like a password. Rotate by:
  1. Generate new token: `python3 -c 'import secrets;print("vhc_tally_"+secrets.token_urlsafe(32))'`
  2. Update `backend/.env` on the server, restart backend
  3. Update `tally_bridge.ini` on the Windows PC, restart `VHCTallyBridge`
- Tally's port 9000 should be **firewalled to localhost only**. Don't expose
  it on the LAN unless multiple machines need direct Tally access.
- The bridge makes only **outbound HTTPS** calls — no inbound ports needed.

---

## Roadmap (not built yet)

- **Phase 55.9** — Bulk client-ledger sync (push VHC companies → Tally ledgers automatically)
- **Phase 55.10** — Pull payment receipts from Tally → auto `mark-paid` on VHC bills
- **Phase 55.11** — Admin UI: "Tally Bridge Health" page showing pending count, last sync, recent errors
