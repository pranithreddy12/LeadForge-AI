# Deploy LeadForge on a free VM (Oracle Cloud Always-Free)

The whole stack (Postgres+pgvector, Redis, API, Celery worker+beat, Next.js) runs on
**one** VM via Docker Compose. Target: Oracle **Ampere A1 (ARM)** — up to 4 vCPU / 24 GB
RAM, free forever. Everything here is ARM-compatible (all images are multi-arch).

Only **one port (3001)** is ever public. The DB, Redis and API stay bound to localhost.

---

## 1. Create the VM (Oracle Cloud)

1. Sign up at cloud.oracle.com (credit card for verification — not charged on Always-Free).
2. **Compute → Instances → Create**:
   - Image: **Ubuntu 22.04**
   - Shape: **Ampere A1 (Arm)** — e.g. **2 OCPU / 12 GB** (the build needs headroom).
   - Add your SSH public key.
   - If "out of capacity", switch region/AD and retry (ARM is popular).
3. **Networking → open the app port:** VCN → Security List → add Ingress rule:
   `0.0.0.0/0`, TCP, port **3001**. (Skip this if you'll use a Cloudflare Tunnel — step 5b.)

SSH in: `ssh ubuntu@<PUBLIC_IP>`

---

## 2. Install Docker

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker
# Ubuntu's host firewall also blocks the port — open it for the app:
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3001 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true
```

---

## 3. Clone + configure

```bash
git clone https://github.com/pranithreddy12/LeadForge-AI.git
cd LeadForge-AI
cp .env.example .env
nano .env
```

**Minimum you must set in `.env`:**

| Key | Value |
|---|---|
| `APP_SECRET_KEY` | any long random string (`openssl rand -hex 32`) |
| `POSTGRES_PASSWORD` | a strong password |
| `DATABASE_URL` | `postgresql+psycopg://leadforge:<same-password>@postgres:5432/leadforge` |
| `APP_PUBLIC_URL` | `http://<PUBLIC_IP>:3001` (or your tunnel URL) |
| `GEMINI_API_KEY` | free key from aistudio.google.com/apikey (else it runs in demo mode) |
| `GOOGLE_MAPS_API_KEY` | for lead discovery |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` | to send email |

Leave Clerk/Stripe blank → the app runs in **demo mode** (no login). See the auth note
at the bottom before exposing it publicly. `NEXT_PUBLIC_API_URL` is overridden
automatically by the prod file — don't worry about it.

---

## 4. Launch

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
# first boot builds the images + runs `pnpm build` — give it a few minutes
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec api alembic upgrade head
```

Check it: `curl -I http://localhost:3001` on the box, then open
`http://<PUBLIC_IP>:3001` in your browser.

Handy alias so you don't retype the `-f` flags:

```bash
echo "alias lf='docker compose -f ~/LeadForge-AI/docker-compose.yml -f ~/LeadForge-AI/deploy/docker-compose.prod.yml'" >> ~/.bashrc && source ~/.bashrc
# then: lf ps   |   lf logs -f api   |   lf restart web
```

---

## 5. Get a public URL (no domain needed)

**5a. Raw IP (simplest):** just use `http://<PUBLIC_IP>:3001` (needs steps 1.3 + 2 firewall).
Plain HTTP.

**5b. Cloudflare Tunnel (HTTPS, hides your IP, free):**

```bash
# install cloudflared (ARM64)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o cloudflared
sudo mv cloudflared /usr/local/bin/ && sudo chmod +x /usr/local/bin/cloudflared

# quick tunnel — instant free https URL (rotates on restart):
cloudflared tunnel --url http://localhost:3001
```

For a **stable** URL, make a free Cloudflare account → `cloudflared tunnel login` →
`cloudflared tunnel create leadforge` → run it as a service. With a tunnel you can drop
the public 3001 rule (step 1.3) and change the web port to `127.0.0.1:3001` in
`deploy/docker-compose.prod.yml`.

---

## 6. Update / maintain

```bash
cd ~/LeadForge-AI && git pull
lf up -d --build
lf exec api alembic upgrade head    # if migrations changed

# backup the database (do this before big changes):
lf exec postgres pg_dump -U leadforge leadforge | gzip > ~/lf-$(date +%F).sql.gz
```

---

## Notes & caveats

- **Auth:** with Clerk blank the app has **no login** — anyone with the URL gets in. Fine
  behind an unguessable Cloudflare Tunnel URL for a personal tool, but for real exposure
  either fill in Clerk keys, or put **Cloudflare Access** (free) in front of the tunnel.
- **RAM:** the first `pnpm build` is the heaviest step. On a 2 GB box add swap if it OOMs:
  `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile`.
  A 8–12 GB Ampere box won't need it.
- **Playwright scraping** on ARM can be finicky; if the worker build fails on it, set
  `FEATURE_PLAYWRIGHT_SCRAPE=false` in `.env` (the app degrades gracefully — it's a JS-render
  safety net, not core).
- **Always-Free reclaim:** Oracle may stop a truly-idle Always-Free instance. Normal usage
  keeps it alive; the `restart: unless-stopped` policy brings services back on reboot.
