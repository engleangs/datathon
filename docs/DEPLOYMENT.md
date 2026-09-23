# OVH Production Deployment

## Target

```text
Host: 139.99.68.73
Path: /datathon/prod
```

## 1. Server prerequisites

Confirm:

```bash
docker --version
docker compose version
git --version
```

The GitHub deployment user must be able to run Docker without an interactive password prompt.

## 2. Create deployment folder

```bash
sudo mkdir -p /datathon/prod
sudo chown -R YOUR_DEPLOY_USER:YOUR_DEPLOY_USER /datathon/prod
```

## 3. GitHub Actions secrets

Repository:

```text
Settings
→ Secrets and variables
→ Actions
```

Create:

```text
DEPLOY_USER
DEPLOY_SSH_KEY
```

`DEPLOY_SSH_KEY` is the private key matching a public key in the deployment user's `~/.ssh/authorized_keys`.

## 4. Server-side environment

After the first file sync, create:

```bash
cd /datathon/prod
cp .env.example .env
chmod 600 .env
nano .env
```

Fill in AWS Bedrock and Snowflake values.

The deployment workflow deliberately excludes `.env`.

## 5. Snowflake bootstrap

Run `sql/bootstrap.sql` once in Snowflake before the first application save.

## 6. Deploy

Push to `main`:

```bash
git push origin main
```

The workflow:

```text
test
 ↓
rsync repository
 ↓
/datathon/prod
 ↓
docker compose build
 ↓
docker compose up -d app
 ↓
docker compose run --rm dbt
```

## 7. Useful commands

```bash
cd /datathon/prod

docker compose ps
docker compose logs -f app
docker compose restart app
docker compose run --rm dbt
docker compose down
```

## 8. Nginx / HTTPS

For an internet-facing deployment, set:

```env
APP_BIND=127.0.0.1
```

and use the example under:

```text
deploy/nginx/nz-court-intelligence.conf.example
```

as the starting point for Nginx.

Then add TLS using your preferred certificate setup.
