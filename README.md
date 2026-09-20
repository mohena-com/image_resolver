"# image_resolver" 
Get Royalti Free images of  "person", "movie", "tv_show", "place", "organization", "event", "other"
 
# Reusable Image Resolver API

A standalone FastAPI/Uvicorn service for resolving a named entity into a cached image.

## Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

## Test

Health:

```bash
curl http://127.0.0.1:8010/health
```

Resolve an entity:

```bash
curl -X POST http://127.0.0.1:8010/image \
  -H "Content-Type: application/json" \
  -d '{"name":"Sayani Gupta","type":"person"}'
```

Get the actual image:

```text
http://127.0.0.1:8010/image/person/Sayani%20Gupta
```

## Architecture

1. Cache lookup
2. Wikipedia article search + lead image
3. Commons fallback
4. License verification for Commons
5. Persistent local cache

Wikipedia images are returned as `NOT_VERIFIED` because this service does not
silently infer a license from the Wikipedia article. Commons images must pass
the configured license allow-list.

The image resolver is deliberately independent of BollywoodKoko and can be
used by other projects.
