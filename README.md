# Wikimedia Commercial-Safe Image API

## One-call person image endpoint

The main API is now:

```text
GET /v1/person/{person_name}
```

Example:

```bash
curl "http://localhost:8000/v1/person/Katrina%20Kaif"
```

Optional candidate limit:

```bash
curl "http://localhost:8000/v1/person/Katrina%20Kaif?limit=30"
```

The API internally performs:

```text
person name
   ↓
Category:Person_Name
   ↓
scan Wikimedia Commons
   ↓
copyright-license filter
   ↓
personality/trademark review filter
   ↓
select approved candidate
   ↓
final metadata re-check
   ↓
download
   ↓
attribution + manifest
   ↓
JSON response
```

No separate client-side curl commands are required.

## Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

Then:

```bash
curl "http://localhost:8000/v1/person/Katrina%20Kaif"
```

Swagger:

```text
http://localhost:8000/docs
```

## Output location

By default:

```text
./downloads/<Person_Name>/
```

You can change it:

```bash
export WIKIMEDIA_OUTPUT_DIR=/path/to/downloads
./run.sh
```

## Existing endpoints

The original endpoints remain:

- `GET /health`
- `POST /v1/scan`
- `GET /v1/image/info`
- `POST /v1/image/download`

`auto_download.py` is now an internal helper module used by
`/v1/person/{person_name}` rather than a separate command-line workflow.

## Automatic approval

The person endpoint automatically downloads only files with:

- `SAFE_WITH_ATTRIBUTION`, or
- `SAFE_NO_ATTRIBUTION`

and:

- no personality-rights review flag
- no trademark review flag
- `NO_AUTOMATED_NONCOPYRIGHT_CLEARANCE`

CC BY-SA, NC, ND, unknown licenses and flagged people/personality-rights
cases are not automatically downloaded.

## Important

This is a conservative copyright-license screening and evidence workflow.
It is not a legal guarantee. Separate publicity/personality, privacy,
trademark, model-release and jurisdiction-specific rights can still apply.
