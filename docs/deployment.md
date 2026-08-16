# Hosting Meridian Sentinel

Deploys the whole system to one small server: Elasticsearch, Kibana, the model
server, a continuous transaction stream, and the React dashboard behind
automatic HTTPS.

The dashboard starts empty and fills up from live traffic.

---

## What you need

| | |
|---|---|
| Server | 1 vCPU / **4 GB RAM** minimum, Ubuntu 22.04+ |
| Cost | roughly $6–12/month (Hetzner CX22, DigitalOcean, Vultr) |
| Domain | a name you control, with an A record pointing at the server |
| Ports | 80 and 443 open |

**4 GB, not 2.** Elasticsearch takes a 1 GB heap, Kibana another ~600 MB, and
the model server holds the ONNX graph in memory. A 2 GB box will boot and then
OOM-kill Elasticsearch under load, which looks like a random outage.

---

## 1. Point DNS at the server first

Caddy requests a Let's Encrypt certificate on first start, and Let's Encrypt
verifies by connecting to the domain. If DNS is not resolving yet, issuance
fails and Caddy retries with a backoff.

```
A    fraud.example.com    ->    <server IP>
```

Confirm before continuing:

```bash
dig +short fraud.example.com
```

---

## 2. Install Docker on the server

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # log out and back in
```

---

## 3. Get the code onto the server

```bash
git clone https://github.com/kevgum/Meridian.git
cd Meridian
```

The trained checkpoint (`models/lstm_checkpoint_best.pt`) is committed, so the
model server converts it to ONNX on first start. Nothing else needs uploading.

---

## 4. Configure

```bash
cp .env.prod.example .env.prod
nano .env.prod
```

Set `DOMAIN`, `ACME_EMAIL`, and a strong `ELASTIC_PASSWORD`:

```bash
openssl rand -base64 24
```

Then derive the header Caddy injects:

```bash
chmod +x deploy/init.sh
./deploy/init.sh
```

That writes `ES_BASIC_AUTH` and sets the file to mode 600. Deriving it rather
than typing it twice means the value Caddy sends can never drift out of sync
with the password Elasticsearch expects — a mismatch there returns 401 on every
dashboard poll and looks exactly like the cluster being down.

---

## 5. Start it

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

First build takes several minutes (the model server installs torch). Watch
certificate issuance:

```bash
docker compose -f docker-compose.prod.yml logs -f caddy
```

`certificate obtained successfully` means TLS is live.

---

## 6. Confirm it works

```bash
curl -s https://fraud.example.com/api/meridian-transactions-*/_count
```

A JSON count means the dashboard's data path is working end to end. Then open
`https://fraud.example.com` — the console should show transactions appearing on
their own every few seconds.

---

## Starting from zero

The stream begins writing as soon as it starts, so a fresh server is already
empty. To reset an existing deployment:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod stop live-stream

docker compose -f docker-compose.prod.yml --env-file .env.prod \
    run --rm -e ELASTIC_HOST=http://elasticsearch:9200 \
    live-stream python -m scripts.reset_stack_data --yes

docker compose -f docker-compose.prod.yml --env-file .env.prod start live-stream
```

Without `--yes` it reports what it would delete and stops. Kibana's own saved
objects are left alone, so the data views survive.

---

## Security

**Only Caddy is exposed.** Elasticsearch, Kibana and the model server have no
published ports in `docker-compose.prod.yml` — they are reachable only on the
internal Compose network. The development `docker-compose.yml` publishes
9200/5601/8080 to the host, which is fine on a laptop and would be an open
cluster on a public server. Do not deploy with the development file.

**`/api` is read-only.** The dashboard polls Elasticsearch directly, and the
browser never receives the password: Caddy injects the `Authorization` header
server-side. Because that endpoint is public, it also rejects every method
except `GET`. Raw Elasticsearch over HTTP happily accepts `DELETE /index` and
`POST _bulk`, so without that rule a single curl could drop every index.

The ordering of those rules matters and is easy to get wrong — see the comment
in `deploy/Caddyfile`. Verify after any change to it:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE https://fraud.example.com/api/some-index
# must print 405
```

**Kibana** is served at `/kibana` behind its own login. Comment out that block
in the Caddyfile to keep it private.

---

## Operating it

```bash
# logs
docker compose -f docker-compose.prod.yml logs -f live-stream
docker compose -f docker-compose.prod.yml logs -f lstm-serving

# slow the stream down (edit .env.prod, then)
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d live-stream

# deploy new code
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

# stop, keeping data
docker compose -f docker-compose.prod.yml --env-file .env.prod down
```

`down` without `-v` preserves the `es_data` and `caddy_data` volumes, so
transactions and the TLS certificate survive a restart. Adding `-v` destroys
both and forces certificate re-issuance, which Let's Encrypt rate-limits.

### Disk growth

At the default 4–12 second interval the stream writes roughly 7,000–20,000
transactions a day, each with its audit records. Watch it:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD localhost:9200/_cat/indices/meridian-*?v
```

Indices roll over daily, so old ones can simply be deleted. For a long-lived
deployment, add an ILM policy rather than doing it by hand.
