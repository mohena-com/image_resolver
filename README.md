# Wikimedia Commercial-Safe Image API

FastAPI + Uvicorn API built around the conservative Wikimedia Commons
copyright-license downloader.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Start with Uvicorn

```bash
./run.sh
```

or:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

API documentation:

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

## Endpoints

### Health

```bash
curl http://localhost:8000/health
```

### Scan a Commons category

```bash
curl -X POST http://localhost:8000/v1/scan   -H "Content-Type: application/json"   -d '{
    "category": "Category:Katrina_Kaif",
    "limit": 15
  }'
```

This only scans metadata. It does not download images.

### Get metadata for one file

```bash
curl "http://localhost:8000/v1/image/info?file_title=File%3AExample.jpg"
```

### Download a specific approved file

```bash
curl -X POST http://localhost:8000/v1/image/download   -H "Content-Type: application/json"   -d '{
    "file_title": "File:Example.jpg"
  }'
```

The response includes the local image path, license, license URL, source
page, author, SHA-256 hash and attribution/manifest paths.

## Policy

The default automated download policy accepts:

- Public Domain / PD
- CC0
- CC BY

It rejects:

- CC BY-NC
- CC BY-ND
- unknown licenses
- other unrecognized licenses

CC BY-SA is treated as review-only.

Images involving identifiable people are also flagged for manual
personality/publicity-rights review. The API does not claim that a copyright
license clears those separate rights.

## Production notes

1. Put this API behind HTTPS/reverse proxy.
2. Replace the User-Agent in
   `wikimedia_commercial_safe_downloader.py` with a descriptive project
   identity/contact address.
3. Keep the generated JSON/CSV manifests and attribution files with your
   publishing records.
4. Do not use `--insecure` mode from the standalone downloader in production.
5. Add authentication/rate limiting before exposing the API publicly.
6. For celebrity/person photographs, perform manual rights review before
   commercial publication.

This project reduces copyright-license risk; it is not a legal guarantee.
