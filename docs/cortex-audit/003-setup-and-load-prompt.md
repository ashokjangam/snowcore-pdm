# Cortex prompt 003 — execute setup, upload files, load Bronze

```text
Execute the reviewed script sql/10_real_setup.sql against the hackathon connection,
statement by statement, using the Snowflake SQL tool. Report the result of each.

Then upload the four staged files and load them into Bronze.

Local files (already gzipped, checksums verified against Zenodo):
  data/stage/comopi_sensors.csv.gz
  data/stage/comopi_alarms.csv.gz
  data/stage/piade_intervals.csv.gz
  data/stage/piade_hourly.csv.gz

Steps:
1. PUT each file to @SNOWCORE_REAL.BRONZE.SRC_STAGE with AUTO_COMPRESS = FALSE
   and SOURCE_COMPRESSION = GZIP. Use the file:// URI form with forward slashes
   and the absolute Windows path.
2. LIST @SNOWCORE_REAL.BRONZE.SRC_STAGE and report names and sizes.
3. For each file, run INFER_SCHEMA with FILE_FORMAT => 'SNOWCORE_REAL.BRONZE.FF_CSV_HEADER'
   and show the inferred columns. The CoMoPI files begin with an unnamed pandas
   index column, and the PIADE hourly file contains column names such as
   "#changes" and "%production". Report exactly how INFER_SCHEMA names these.
4. Do NOT create the Bronze tables yet. Stop after reporting the inferred schemas.

Constraints:
- Use warehouse COMPUTE_WH.
- Do not drop or modify anything outside the SNOWCORE_REAL database.
- Do not invent column names; report what Snowflake actually returns.
```
