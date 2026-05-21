# Auto-Deploy Script Runbook — `scripts/deploy.sh`

**Phase 55.7 / Feb 2026** — fixes the recurring "I pulled but the UI still
looks old" problem on the EC2 production box.

## What it does

Single command that runs the full prod-deploy chain:

1. `git pull --ff-only origin main`
2. `pip install -r backend/requirements.txt` (only if requirements changed)
3. `sudo systemctl restart vhc-backend`
4. Healthchecks `http://127.0.0.1:8001/api/health`
5. `yarn install --frozen-lockfile` (only if `package.json`/`yarn.lock` changed)
6. `yarn build` → React production bundle
7. `sudo rsync -a --delete frontend/build/ /var/www/html/`
8. `sudo nginx -t && sudo systemctl reload nginx`

It refuses to run on a dirty working tree (unless you pass `--skip-pull`)
and prints clear pass/fail at each stage.

## One-time install on the EC2 box

```bash
cd /home/ubuntu/vhc-platform
git pull
chmod +x scripts/deploy.sh scripts/post-merge.hook

# Symlink the post-merge hook so `git pull` auto-deploys
ln -sf ../../scripts/post-merge.hook .git/hooks/post-merge

# Sudo passwordless for systemctl + nginx + rsync (one-time)
# Append to /etc/sudoers.d/vhc-deploy (visudo!):
#   ubuntu ALL=(root) NOPASSWD: /bin/systemctl restart vhc-backend, \
#                                /bin/systemctl reload nginx, \
#                                /usr/sbin/nginx -t, \
#                                /usr/bin/rsync
```

## Day-to-day usage

```bash
# Standard deploy (after pushing to origin)
cd /home/ubuntu/vhc-platform && git pull
# ── that's it. The post-merge hook fires deploy.sh automatically. ──
```

If you ever need to re-deploy without pulling:

```bash
./scripts/deploy.sh --skip-pull
```

Other flags:

| Flag                | Purpose                                  |
|---------------------|------------------------------------------|
| `--frontend-only`   | Just rebuild + rsync + reload Nginx      |
| `--backend-only`    | Just `pip install` + restart vhc-backend |
| `--skip-pull`       | Use current working tree (no git pull)   |

Bypass the hook for a single pull:

```bash
VHC_SKIP_DEPLOY=1 git pull
```

## Environment overrides

If your prod layout differs from the defaults, export before running:

```bash
REPO_DIR=/opt/vhc                \
FRONTEND_DIR=/opt/vhc/frontend   \
BACKEND_DIR=/opt/vhc/backend     \
VENV_DIR=/opt/vhc/venv           \
NGINX_WEB_ROOT=/srv/www/vhc      \
BACKEND_SERVICE=vhc-backend      \
HEALTHCHECK_URL=http://127.0.0.1:8001/api/health \
GIT_BRANCH=main                  \
./scripts/deploy.sh
```

## Failure modes & recovery

| Stage failure              | What you'll see                       | Recover with                                            |
|----------------------------|---------------------------------------|---------------------------------------------------------|
| Backend healthcheck fails  | `Backend healthcheck FAILED.`         | `sudo journalctl -u vhc-backend -n 80` then redeploy   |
| `yarn build` errors        | npm/yarn error stack                  | Fix the React error locally, push, repull               |
| `nginx -t` fails           | Nginx config syntax error             | Revert recent `nginx.conf` edits; reload manually       |
| Dirty working tree         | `Working tree has uncommitted changes`| `git stash` then redeploy, or `--skip-pull`             |

Atomicity note: the rsync uses `--delete`, so a half-built bundle would
truncate the live site briefly. Because `yarn build` is run **before**
the rsync, a broken build never reaches Nginx — the script aborts first.
