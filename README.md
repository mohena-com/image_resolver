# Wikimedia Commercial-Safe Image API

## One-call person lookup + local cache

The main endpoint is:

```text
GET /v1/person/{person_name}
```

Example:

```bash
curl "http://localhost:8000/v1/person/Katrina%20Kaif"
```

### First request

If Katrina Kaif is not cached:

```text
GET /v1/person/Katrina Kaif
        ↓
people/Katrina_Kaif/
        ↓
Wikimedia Commons
        ↓
license + rights filtering
        ↓
approved image
        ↓
download
        ↓
local cache
        ↓
index.json
        ↓
response
```

### Second request

The same request:

```bash
curl "http://localhost:8000/v1/person/Katrina%20Kaif"
```

does NOT call Wikimedia again.

It does:

```text
GET /v1/person/Katrina Kaif
        ↓
index.json
        ↓
people/Katrina_Kaif/<image>
        ↓
CACHE HIT
        ↓
response
```

The response contains:

```json
{
  "success": true,
  "cache_hit": true,
  "person": "Katrina Kaif",
  "category": "people",
  "file": "/Volumes/.../images/people/...",
  "license": "CC BY 4.0",
  "author": "...",
  "license_url": "...",
  "download_sha256": "..."
}
```

## Canonical cache location

This version uses this persistent cache by default:

```text
/Volumes/Extreme SSD/webmaster-ai/POJO_PROJECT/data/images
```

`run.sh` exports this path before starting Uvicorn and fails if the
Extreme SSD path is not mounted.

You can explicitly override it with:

```bash
export WIKIMEDIA_IMAGE_CACHE="/some/other/path"
./run.sh
```

The resulting structure is:

```text
data/images/
├── people/
├── movies/
├── shows/
├── places/
├── organizations/
├── events/
├── other/
└── index.json
```

The current `/v1/person/{person_name}` endpoint stores images under:

```text
people/
```

For example:

```text
people/
└── Katrina_Kaif/
    ├── <image>.jpg
    ├── <image>_ATTRIBUTION.txt
    └── commons_license_manifest.json
```

and the global:

```text
index.json
```

contains the cache mapping.

## Cache behavior

The cache is keyed by:

```text
people:<normalized_person_name>
```

A cache hit is valid only when the indexed local file still exists.

If the file is deleted, the next request becomes a cache miss and the API
will query Wikimedia again.

## Existing endpoints

- `GET /health`
- `POST /v1/scan`
- `GET /v1/image/info`
- `POST /v1/image/download`
- `GET /v1/person/{person_name}`

## Automatic rights policy

The person endpoint automatically accepts only:

- Public Domain / PD
- CC0
- CC BY

and requires no personality-rights or trademark review flag.

CC BY-SA, NC, ND, unknown licenses and images requiring manual
personality/publicity-rights review are not automatically downloaded.

This is a conservative copyright-license screening workflow, not a legal
guarantee.
