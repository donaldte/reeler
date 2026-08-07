# Deployment

## Docker Compose (single host)

The straightforward path for a single-server deployment:

```bash
cp .env.example .env   # set real DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS,
                        # DJANGO_CSRF_TRUSTED_ORIGINS, DATABASE/REDIS creds
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

This builds the `prod` Dockerfile target for `web`/`worker` (gunicorn, no
bind mount, static collected at build time), drops the dev-only host port
bindings on `db`/`redis`/`ollama`, and puts nginx in front of `web` —
see [docs/docker.md](docker.md) for what each override changes.

Required production settings (see `config/settings/prod.py` and
`.env.example`):

- `DJANGO_SECRET_KEY` — required, no insecure fallback (unlike dev).
- `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` — your real domain(s).
- `DJANGO_SECURE_SSL_REDIRECT=true` if TLS terminates in front of nginx.

## GPU for faster transcription/inference

Neither `docker-compose.yml` nor the prod overlay requests a GPU by
default, to keep the base setup portable across dev machines without the
NVIDIA container runtime. To use a GPU for the `worker` service (faster
Whisper transcription, faster Ollama inference), add a
`docker-compose.override.yml`:

```yaml
services:
  worker:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

and set `WHISPER_DEVICE=cuda` in `.env`. Requires the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
on the host.

## Backups

- **Postgres**: back up the `postgres_data` volume (or run
  `pg_dump`/`pg_restore` against the `db` service on a schedule).
- **Media**: back up the `media_files` volume — it holds the original
  uploaded videos.
- Model caches (`ollama_data`, `whisper_cache`) are re-derivable and don't
  need backing up.

## Scaling

- `worker` is horizontally scalable — the pipeline is fully driven by
  Postgres state, not in-memory state, so running multiple worker
  containers/replicas is safe. Bump `--workers` on gunicorn and/or run
  multiple `web` replicas behind nginx/a load balancer for read traffic.
- CPU-bound Whisper transcription is the main throughput bottleneck on
  CPU-only deployments — see the GPU section above, or reduce
  `WHISPER_MODEL_SIZE`.

## What's not covered yet

Kubernetes manifests, managed-cloud Terraform, and horizontal Ollama
serving are tracked in [docs/roadmap.md](roadmap.md), not provided here.
