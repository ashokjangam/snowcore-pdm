/* ============================================================================
   SnowCore Real — foundation objects for two real manufacturing plants.

   Plant A  CoMoPI  Condition Monitoring for Packaging Industry
                    8 packaging machines, 10-minute sensors + alarm counters.
                    DOI 10.5281/zenodo.7572501, CC BY 4.0.
   Plant B  PIADE   Packaging Industry Anomaly DEtection
                    5 packaging machines, production intervals + stop alarms.
                    DOI 10.5281/zenodo.7071747, CC BY 4.0.

   The two plants are different sites with no published join key. Nothing in
   this build may merge them into a single factory.

   Safe to re-run: every statement is CREATE ... IF NOT EXISTS or CREATE OR
   REPLACE on objects this project owns. It touches nothing outside
   SNOWCORE_REAL.
   ========================================================================= */

USE ROLE ACCOUNTADMIN;
ALTER SESSION SET QUERY_TAG = 'snowcore-real|coco|setup';

CREATE DATABASE IF NOT EXISTS SNOWCORE_REAL
  COMMENT = 'Real manufacturing data: CoMoPI (PdM) and PIADE (production/OEE), kept as separate plants.';

USE DATABASE SNOWCORE_REAL;

CREATE SCHEMA IF NOT EXISTS BRONZE COMMENT = 'Raw landing, one table per published source file. No edits to source values.';
CREATE SCHEMA IF NOT EXISTS SILVER COMMENT = 'Typed, per-plant models. Derivations only; nothing invented.';
CREATE SCHEMA IF NOT EXISTS GOLD   COMMENT = 'Analytics: OEE, health features, semantic layer.';
CREATE SCHEMA IF NOT EXISTS ML     COMMENT = 'Feature store, models, chronological evaluation.';

/* --------------------------------------------------------------------------
   Stage and file format.

   PARSE_HEADER lets INFER_SCHEMA read the real column names, which matters
   because the sources contain names SQL cannot take bare: an unnamed pandas
   index column, "#changes", and "%production".
   -------------------------------------------------------------------------- */

CREATE FILE FORMAT IF NOT EXISTS BRONZE.FF_CSV_HEADER
  TYPE = CSV
  PARSE_HEADER = TRUE
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL = TRUE
  COMPRESSION = GZIP
  COMMENT = 'Header-parsing CSV format used for INFER_SCHEMA on the Zenodo extracts.';

CREATE FILE FORMAT IF NOT EXISTS BRONZE.FF_CSV_LOAD
  TYPE = CSV
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL = TRUE
  COMPRESSION = GZIP
  COMMENT = 'Loading format for COPY INTO once the target tables exist.';

CREATE STAGE IF NOT EXISTS BRONZE.SRC_STAGE
  FILE_FORMAT = BRONZE.FF_CSV_HEADER
  COMMENT = 'Checksum-verified Zenodo files. Contents are reproducible from scripts/download_sources.ps1.';

/* --------------------------------------------------------------------------
   Provenance registry.

   Every Bronze table points back to a row here, so the licence and checksum
   of any number shown in the app can be traced without leaving Snowflake.
   -------------------------------------------------------------------------- */

CREATE TABLE IF NOT EXISTS BRONZE.SOURCE_REGISTRY (
  SOURCE_KEY     VARCHAR       NOT NULL,
  PLANT_CODE     VARCHAR       NOT NULL,
  PLANT_LABEL    VARCHAR       NOT NULL,
  DATASET_NAME   VARCHAR       NOT NULL,
  SOURCE_FILE    VARCHAR       NOT NULL,
  SOURCE_DOI     VARCHAR       NOT NULL,
  SOURCE_LICENSE VARCHAR       NOT NULL,
  SOURCE_MD5     VARCHAR       NOT NULL,
  SOURCE_BYTES   NUMBER        NOT NULL,
  EXPECTED_ROWS  NUMBER        NOT NULL,
  DATA_ORIGIN    VARCHAR       NOT NULL,
  NOTES          VARCHAR,
  REGISTERED_AT  TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'One row per published source file, with the MD5 verified before upload.';

TRUNCATE TABLE BRONZE.SOURCE_REGISTRY;

INSERT INTO BRONZE.SOURCE_REGISTRY
  (SOURCE_KEY, PLANT_CODE, PLANT_LABEL, DATASET_NAME, SOURCE_FILE, SOURCE_DOI,
   SOURCE_LICENSE, SOURCE_MD5, SOURCE_BYTES, EXPECTED_ROWS, DATA_ORIGIN, NOTES)
VALUES
  ('COMOPI_SENSORS', 'PLANT_A', 'Plant A - packaging (CoMoPI)',
   'Condition Monitoring for Packaging Industry',
   'industrial_dataset_sensors_10m_agg.csv', '10.5281/zenodo.7572501', 'CC BY 4.0',
   'c0a3b7ad77ceaeb0e9128713be482467', 5057527, 15704, 'OBSERVED',
   '16 sensors on the watertight-closure module, rescaled to [0,1]. Physical units are not recoverable.'),

  ('COMOPI_ALARMS', 'PLANT_A', 'Plant A - packaging (CoMoPI)',
   'Condition Monitoring for Packaging Industry',
   'industrial_dataset_alarm_10m_agg.csv', '10.5281/zenodo.7572501', 'CC BY 4.0',
   'c7978f94ab2b8c08f461869c87ecefc2', 42677268, 150650, 'OBSERVED',
   'Counts of alarms AL_1..AL_123 per 10-minute window. AL_53/AL_54 are the published fault targets.'),

  ('PIADE_INTERVALS', 'PLANT_B', 'Plant B - packaging (PIADE)',
   'Packaging Industry Anomaly DEtection',
   'raw_data.csv', '10.5281/zenodo.7071747', 'CC BY 4.0',
   'a0fc01fbfc9414b0f754cd0a8e70c429', 49342406, 429394, 'OBSERVED',
   'Production intervals with state, stop alarm, cumulative package counters and speed.'),

  ('PIADE_HOURLY', 'PLANT_B', 'Plant B - packaging (PIADE)',
   'Packaging Industry Anomaly DEtection',
   'sequences_1h_data.csv', '10.5281/zenodo.7071747', 'CC BY 4.0',
   '5edf8a6806f272228d522c76825d955c', 11663660, 23376, 'OBSERVED',
   'Publisher hourly aggregate. Used to cross-check our own hourly derivation, not as the primary source.');

SELECT SOURCE_KEY, PLANT_CODE, EXPECTED_ROWS, SOURCE_LICENSE FROM BRONZE.SOURCE_REGISTRY ORDER BY SOURCE_KEY;
