# Data Systems Lead Technical Assessment - Sections 0, 1 and 2

This repository contains my response to the YearBeyond Data Systems Lead technical assessment.

The submission covers:

- **Section 0** - reproducible setup and data access
- **Section 1** - AWS S3 Select extraction of City of Cape Town H3 resolution-8 GeoJSON and data-quality validation
- **Section 2** - assignment of service requests to H3 resolution-8 cells, validation, logging and failure thresholds

Original challenge:
https://github.com/cityofcapetown/ds_code_challenge

## Quick start

The pipeline does not require a personal AWS account. It retrieves the challenge credentials at runtime, downloads the required public input files, and uses S3 Select to query the mixed-resolution GeoJSON.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run.py
```

Using the virtual-environment interpreter directly avoids depending on the local PowerShell script-execution policy.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
pytest -q
python run.py
```

No interactive input is required after dependencies are installed.

## Outputs

A successful run creates:

- `data/processed/city-hex-polygons-8-extracted.geojson`
- `data/processed/sr_with_h3.csv.gz`
- `logs/pipeline.log`

Raw and generated datasets are excluded from Git because they are downloaded or generated automatically.

## Section 1 - extraction and validation

The mixed-resolution GeoJSON is filtered with AWS S3 Select rather than downloaded and filtered locally.

The pipeline first samples the source to identify the H3 index property and the property whose value matches the H3 resolution of those cells. The final S3 Select query then filters for resolution 8.

The expected schema is defined in `config/geojson_schema.yaml`.

Observed real-data result:

- Extracted features: **3,832**
- Schema conformance: **100.00%**
- Missing reference H3 indexes: **0**
- Unexpected H3 indexes: **0**

## Section 2 - service-request transformation

For each valid coordinate pair, the pipeline calculates:

```python
h3.latlng_to_cell(latitude, longitude, 8)
```

The resulting cell is checked against the City resolution-8 H3 set produced in Section 1.

Missing latitude or longitude is assigned `h3_level8_index = "0"` as required by the challenge.

Coordinate-column names are resolved case-insensitively because the real source dataset uses lowercase `latitude` and `longitude`.

### Join-failure threshold

The maximum join-failure rate is configured at **1% of valid-coordinate rows**.

The observed real-data join-failure rate was approximately **0.0004%**.

### Reference validation and investigated anomalies

The generated `h3_level8_index` values are compared row-for-row with the supplied `sr_hex.csv.gz` reference.

The real-data run produced **3 mismatches out of 941,634 rows**, a mismatch rate of approximately **0.000319%**.

All three mismatches were investigated individually. For each row:

- the H3 index calculated from the supplied coordinates matched the H3 value in `sr_hex.csv.gz`;
- however, that H3 cell was absent from the supplied `city-hex-polygons-8.geojson` City resolution-8 set.

These rows are therefore retained as join failures rather than silently forced to the reference value.

The configured maximum reference mismatch rate is **0.001%**.

## Verified real-data results

- Section 1 features: **3,832**
- Section 1 schema conformance: **100.00%**
- Section 1 missing / extra H3 cells: **0 / 0**
- Section 2 rows processed: **941,634**
- Successful joins: **729,267**
- Missing-coordinate rows: **212,364**
- Invalid-coordinate rows: **0**
- Valid-coordinate join failures: **3**
- Reference mismatches: **3 (0.000319%)**
- End-to-end runtime: approximately **17 seconds**
- Automated tests: **24 passed**

## Tests

Run:

```bash
pytest -q
```

Or on Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The test suite covers S3 Select query construction, AWS challenge credential parsing, schema scoring, H3/resolution-field discovery, coordinate handling, lowercase City coordinate fields, failure thresholds, chunked processing and streaming reference comparison.

## AI usage

AI assistance was used during the assessment and is documented in `AI_log.md`.

The AI-generated implementation was not accepted without validation. Real-data execution identified assumptions that required correction, including the actual AWS credential structure and coordinate-column casing. The AI log documents these corrections and the investigation of the three remaining reference anomalies.
