# AI Usage Log

AI assistance is permitted for this assessment. This log records how it was used and where the generated approach was reviewed and improved.

## Session 1 — assessment interpretation and implementation groundwork

- **Date:** 22 September 2026
- **Tool / model:** ChatGPT — GPT-5.6 Sol
- **Approximate usage:** substantial working session; approximately **30,000 tokens** as a rough estimate. The current client does not expose an exact per-chat token total, so this figure should be treated as approximate.
- **Primary prompts / requests:**
  - Review the YearBeyond technical-assessment email and linked City of Cape Town code challenge.
  - Identify exactly which sections are required and plan the work.
  - Prepare as much of Sections 0, 1 and 2 as possible while I was occupied with other work.
  - Produce a maintainable Python structure, validation approach, tests, README and AI log.
- **How AI was used:**
  - Interpreted the challenge requirements and repository documentation.
  - Researched the AWS S3 Select nested-JSON query syntax and current H3 Python API.
  - Proposed the module structure and test cases.
  - Drafted the initial implementation and documentation.
  - Ran local unit tests against synthetic fixtures and iteratively corrected the implementation.

### Example of AI output that was corrected / improved

An early design considered a general GeoPandas point-in-polygon spatial join for Section 2. On review, this was unnecessarily expensive for an H3-indexed problem. The design was changed to calculate the resolution-8 H3 cell directly from each coordinate with `h3.latlng_to_cell()` and then validate membership against the extracted City H3 set. This is deterministic, has a smaller dependency footprint, and directly uses the indexing system supplied by the challenge.

A second improvement was made to the source-schema discovery. The first version identified the resolution property by looking for small integer values. That could misidentify another numeric field. It was replaced with a stricter check: candidate resolution fields must match `h3.get_resolution()` for the corresponding sampled H3 cell on every checked feature.

## Candidate review before submission

Before submission I will personally:

- run the pipeline against the real challenge datasets;
- inspect the actual schema-conformance score and join-failure rate;
- review whether the configured 1% join threshold is justified by the observed data;
- inspect any mismatches against `sr_hex.csv.gz` rather than suppressing them;
- perform a clean-clone reproducibility test; and
- make sure I can explain the S3 Select query, schema score, H3 transformation, thresholds and tests in a follow-up interview.

## Session 2 - real-data execution, debugging and validation

- **Date:** 23 September 2026
- **Tool / model:** ChatGPT - GPT-5.6 Sol
- **Usage:** Extended interactive debugging and review session.

### How I used AI

I used AI to help draft the initial implementation, generate tests, interpret errors, and suggest debugging steps. I did not accept the generated implementation without validation. I ran it against the real challenge datasets, inspected failures, checked assumptions against the source data, and required changes where the generated solution did not match the real environment.

### Example where I corrected AI-generated work

The initial AI-generated implementation assumed that the service-request coordinate fields were named `Latitude` and `Longitude`.

When I ran the pipeline against the real `sr.csv.gz` dataset, it failed with `KeyError: 'Latitude'`. I inspected the actual dataset schema and identified that the fields are lowercase `latitude` and `longitude`.

I did not simply change the names in the code. I first added a regression test using the actual lowercase source schema and confirmed that the test failed. I then changed the transformation logic to resolve coordinate column names case-insensitively, allowing both naming styles while preserving the existing behavior. The new regression test and full test suite then passed.

### Additional validation decision I reviewed

The initial AI-generated configuration also required an exact 0% mismatch against the supplied `sr_hex.csv.gz` reference.

The real-data run produced only 3 mismatches out of 941,634 rows. Rather than simply increasing the tolerance, I investigated all three records individually.

For each record, the H3 index calculated directly from the coordinates matched the value in `sr_hex.csv.gz`. However, those H3 cells were absent from the supplied `city-hex-polygons-8.geojson` polygon set.

Because the task is to join service requests to the supplied City resolution-8 polygon set, I retained these records as join failures instead of forcing the reference value into the output. I then configured a small 0.001% reference mismatch tolerance, which allows the three verified source-reference inconsistencies while remaining strict enough to detect meaningful transformation errors.

## Verified real-data results

- Section 1 resolution-8 features extracted: 3,832
- Section 1 schema conformance: 100.00%
- Section 1 reference comparison: 0 missing, 0 extra
- Section 2 rows processed: 941,634
- Successful joins: 729,267
- Missing-coordinate rows: 212,364
- Invalid-coordinate rows: 0
- Valid-coordinate join failures: 3
- Reference mismatches: 3 (0.000319%)
- End-to-end runtime: approximately 17 seconds
- Automated tests: 24 passed

