/* ============================================================================
   Silver — typed, per-plant models.

   Rules enforced here:
   - The two plants stay in separate tables and share no surrogate keys.
   - Only derivations are allowed. Nothing is invented.
   - Every derived column that rests on an interpretation carries that
     interpretation in its comment, so a reviewer can disagree with the
     definition without having to guess what we did.
   ========================================================================= */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET QUERY_TAG = 'snowcore-real|coco|silver';

/* --------------------------------------------------------------------------
   Plant and machine dimensions.

   Machine identifiers in both sources are mock codes assigned by the
   publishers. We do not know the real sites, products, or locations, so no
   such attribute appears here.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE SILVER.DIM_PLANT AS
SELECT
  'PLANT_A'                                        AS PLANT_CODE,
  'Plant A - packaging (CoMoPI)'                   AS PLANT_LABEL,
  'Condition monitoring of a watertight-closure module'
                                                   AS PLANT_PURPOSE,
  'Predictive maintenance'                         AS PLANT_ROLE,
  8                                                AS MACHINE_COUNT,
  '10.5281/zenodo.7572501'                         AS SOURCE_DOI,
  'CC BY 4.0'                                      AS SOURCE_LICENSE,
  'OBSERVED'                                       AS DATA_ORIGIN,
  'Sensors are rescaled to [0,1] and alarm codes are anonymised. No production counts exist for this plant.'
                                                   AS LIMITATIONS
UNION ALL
SELECT
  'PLANT_B',
  'Plant B - packaging (PIADE)',
  'Production interval and stop-alarm logging across a packaging line',
  'Production and OEE',
  5,
  '10.5281/zenodo.7071747',
  'CC BY 4.0',
  'OBSERVED',
  'No analogue sensor channels exist for this plant. Quality is a package throughput yield, not a laboratory inspection result.';

COMMENT ON TABLE SILVER.DIM_PLANT IS
  'Two independent real plants. They are not the same site and must never be joined as one factory.';

CREATE OR REPLACE TABLE SILVER.DIM_MACHINE AS
SELECT
  'PLANT_A'                          AS PLANT_CODE,
  'PLANT_A:' || SERIAL               AS MACHINE_KEY,
  SERIAL                             AS MACHINE_CODE,
  'Packaging machine ' || SERIAL     AS MACHINE_LABEL,
  MIN(TIME_UTC)                      AS FIRST_SEEN,
  MAX(TIME_UTC)                      AS LAST_SEEN,
  COUNT(*)                           AS SENSOR_WINDOWS,
  'OBSERVED'                         AS DATA_ORIGIN
FROM BRONZE.COMOPI_SENSORS_RAW
GROUP BY SERIAL
UNION ALL
SELECT
  'PLANT_B',
  'PLANT_B:' || EQUIPMENT_ID,
  EQUIPMENT_ID,
  'Packaging machine ' || EQUIPMENT_ID,
  MIN(INTERVAL_START),
  MAX(INTERVAL_START),
  COUNT(*),
  'OBSERVED'
FROM BRONZE.PIADE_INTERVALS_RAW
GROUP BY EQUIPMENT_ID;

COMMENT ON TABLE SILVER.DIM_MACHINE IS
  'Machine codes are publisher-assigned mock identifiers. MACHINE_KEY is plant-prefixed so the two plants cannot be joined by accident.';

/* --------------------------------------------------------------------------
   Plant B: production intervals.

   Measured facts that drive the definitions below (see
   docs/cortex-audit/002-source-profile.md and scripts/probe_oee_feasibility.py):
   - ELAPSED_MS is milliseconds; it equals (END_EPOCH - START_EPOCH) * 1000.
   - PI_COUNTER and PO_COUNTER are cumulative lifetime counters, so per-interval
     output has to be differenced per machine.
   - The counters reset occasionally: 79 times on s_4 and 1-4 times on the
     others, out of 429,394 intervals. A reset makes that single delta
     meaningless, so it is nulled rather than clamped to zero, which would
     understate production.

   Interpretations, stated so they can be challenged:
   - RUNNING means the machine was producing, including while slow, so
     'production' and 'performance_loss' both count as run time.
   - 'scheduled_downtime' is the only state removed from planned production
     time. 'idle' and 'downtime' are treated as unplanned stops that count
     against Availability.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE SILVER.PIADE_INTERVAL AS
WITH typed AS (
  SELECT
    'PLANT_B:' || EQUIPMENT_ID                        AS MACHINE_KEY,
    EQUIPMENT_ID                                      AS MACHINE_CODE,
    INTERVAL_START,
    DATE_TRUNC('HOUR', INTERVAL_START)                AS INTERVAL_HOUR,
    TO_DATE(INTERVAL_START)                           AS INTERVAL_DATE,
    STATE_TYPE,
    ALARM_CODE,
    START_EPOCH,
    END_EPOCH,
    ELAPSED_MS,
    ELAPSED_MS / 1000.0                               AS DURATION_SEC,
    PI_COUNTER,
    PO_COUNTER,
    SPEED_PPH,
    STATE_TYPE IN ('production', 'performance_loss')  AS IS_RUNNING,
    STATE_TYPE = 'scheduled_downtime'                 AS IS_PLANNED_STOP,
    STATE_TYPE IN ('downtime', 'idle')                AS IS_UNPLANNED_STOP,
    -- A_000 is the placeholder the publisher uses when no alarm was active.
    ALARM_CODE <> 'A_000'                             AS HAS_STOP_ALARM,
    LAG(PI_COUNTER) OVER (PARTITION BY EQUIPMENT_ID ORDER BY START_EPOCH) AS PREV_PI,
    LAG(PO_COUNTER) OVER (PARTITION BY EQUIPMENT_ID ORDER BY START_EPOCH) AS PREV_PO
  FROM BRONZE.PIADE_INTERVALS_RAW
)
SELECT
  MACHINE_KEY,
  MACHINE_CODE,
  INTERVAL_START,
  INTERVAL_HOUR,
  INTERVAL_DATE,
  STATE_TYPE,
  ALARM_CODE,
  HAS_STOP_ALARM,
  DURATION_SEC,
  SPEED_PPH,
  IS_RUNNING,
  IS_PLANNED_STOP,
  IS_UNPLANNED_STOP,
  PI_COUNTER,
  PO_COUNTER,
  -- Null on a counter reset: a negative delta is not a real negative output.
  IFF(PI_COUNTER >= PREV_PI, PI_COUNTER - PREV_PI, NULL)  AS PACKAGES_IN,
  IFF(PO_COUNTER >= PREV_PO, PO_COUNTER - PREV_PO, NULL)  AS PACKAGES_OUT,
  (PI_COUNTER < PREV_PI OR PO_COUNTER < PREV_PO)          AS COUNTER_RESET,
  'OBSERVED'                                              AS DATA_ORIGIN
FROM typed;

COMMENT ON TABLE SILVER.PIADE_INTERVAL IS
  'Plant B production intervals. PACKAGES_IN/OUT are differenced from cumulative counters and are NULL across counter resets.';

/* --------------------------------------------------------------------------
   Plant A: sensors and alarms.

   The 16 sensor channels are anonymised and rescaled to [0,1]. Their physical
   meaning is withheld by the publisher, so they are exposed as opaque process
   measurements. Suffix A/B refers to the two elements performing the closure
   operation.

   Column SENSOR_B_AVAILABLE exists because machine C004 has no B-side
   readings at all: exactly 196 rows have NULL in every B channel.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE SILVER.COMOPI_SENSOR_10MIN AS
SELECT
  'PLANT_A:' || SERIAL                       AS MACHINE_KEY,
  SERIAL                                     AS MACHINE_CODE,
  TIME_UTC,
  DATE_TRUNC('HOUR', TIME_UTC)               AS WINDOW_HOUR,
  TO_DATE(TIME_UTC)                          AS WINDOW_DATE,
  AE, BE, AF, BF, APP, BPP, AP, BP,
  ALE, BLE, ALP, BLP, ADS, BDS, AES, BES,
  BE IS NOT NULL                             AS SENSOR_B_AVAILABLE,
  'OBSERVED'                                 AS DATA_ORIGIN
FROM BRONZE.COMOPI_SENSORS_RAW;

COMMENT ON TABLE SILVER.COMOPI_SENSOR_10MIN IS
  'Plant A 10-minute sensor averages. Channels are anonymised and rescaled to [0,1]; physical units are not recoverable.';

/* Alarm counts, narrowed to what the modelling actually uses.

   The published fault targets are AL_53 and AL_54, but profiling measured only
   41 windows containing them and only 10 of those coincide with a sensor row.
   Ten positives cannot train a supervised model, so the wider target-module
   alarm set is carried alongside them and the model uses that instead. Both
   flags are kept so the distinction stays visible rather than being quietly
   redefined. */

CREATE OR REPLACE TABLE SILVER.COMOPI_ALARM_10MIN AS
SELECT
  'PLANT_A:' || SERIAL                                    AS MACHINE_KEY,
  SERIAL                                                  AS MACHINE_CODE,
  TIME_UTC,
  DATE_TRUNC('HOUR', TIME_UTC)                            AS WINDOW_HOUR,
  TO_DATE(TIME_UTC)                                       AS WINDOW_DATE,
  AL_53,
  AL_54,
  AL_53 + AL_54                                           AS PUBLISHED_FAULT_COUNT,
  (AL_53 > 0 OR AL_54 > 0)                                AS IS_PUBLISHED_FAULT,
  AL_17 + AL_18 + AL_40 + AL_41 + AL_42 + AL_43 + AL_45
    + AL_46 + AL_47 + AL_48 + AL_49 + AL_50 + AL_51
    + AL_52 + AL_53 + AL_54                               AS MODULE_ALARM_COUNT,
  (AL_17 + AL_18 + AL_40 + AL_41 + AL_42 + AL_43 + AL_45
    + AL_46 + AL_47 + AL_48 + AL_49 + AL_50 + AL_51
    + AL_52 + AL_53 + AL_54) > 0                          AS IS_MODULE_ALARM,
  AL_1 + AL_2 + AL_3 + AL_4 + AL_5 + AL_6 + AL_7 + AL_8 + AL_9 + AL_10
    + AL_11 + AL_12 + AL_13 + AL_14 + AL_15 + AL_16 + AL_17 + AL_18 + AL_19
    + AL_20 + AL_21 + AL_22 + AL_23 + AL_24 + AL_25 + AL_26 + AL_27 + AL_28
    + AL_29 + AL_30 + AL_31 + AL_32 + AL_33 + AL_34 + AL_35 + AL_36 + AL_37
    + AL_38 + AL_39 + AL_40 + AL_41 + AL_42 + AL_43 + AL_44 + AL_45 + AL_46
    + AL_47 + AL_48 + AL_49 + AL_50 + AL_51 + AL_52 + AL_53 + AL_54 + AL_55
    + AL_56 + AL_57 + AL_58 + AL_59 + AL_60 + AL_61 + AL_62 + AL_63 + AL_64
    + AL_65 + AL_66 + AL_67 + AL_68 + AL_69 + AL_70 + AL_71 + AL_72 + AL_73
    + AL_74 + AL_75 + AL_76 + AL_77 + AL_78 + AL_79 + AL_80 + AL_81 + AL_82
    + AL_83 + AL_84 + AL_85 + AL_86 + AL_87 + AL_88 + AL_89 + AL_90 + AL_91
    + AL_92 + AL_93 + AL_94 + AL_95 + AL_96 + AL_97 + AL_98 + AL_99 + AL_100
    + AL_101 + AL_102 + AL_103 + AL_104 + AL_105 + AL_106 + AL_107 + AL_108
    + AL_109 + AL_110 + AL_111 + AL_112 + AL_113 + AL_114 + AL_115 + AL_116
    + AL_117 + AL_118 + AL_119 + AL_120 + AL_121 + AL_122 + AL_123          AS ALARM_COUNT_ALL,
  'OBSERVED'                                              AS DATA_ORIGIN
FROM BRONZE.COMOPI_ALARMS_RAW;

COMMENT ON TABLE SILVER.COMOPI_ALARM_10MIN IS
  'Plant A alarm counts per 10-minute window. IS_PUBLISHED_FAULT is AL_53/AL_54 only; IS_MODULE_ALARM is the wider target-module set used for modelling because the published pair is too rare.';

/* --------------------------------------------------------------------------
   Reconciliation. Every number below must be explainable from the profile
   report; anything else means a definition drifted.
   -------------------------------------------------------------------------- */

SELECT 'DIM_PLANT'            AS OBJECT, COUNT(*) AS ROWS FROM SILVER.DIM_PLANT
UNION ALL SELECT 'DIM_MACHINE',           COUNT(*) FROM SILVER.DIM_MACHINE
UNION ALL SELECT 'PIADE_INTERVAL',        COUNT(*) FROM SILVER.PIADE_INTERVAL
UNION ALL SELECT 'COMOPI_SENSOR_10MIN',   COUNT(*) FROM SILVER.COMOPI_SENSOR_10MIN
UNION ALL SELECT 'COMOPI_ALARM_10MIN',    COUNT(*) FROM SILVER.COMOPI_ALARM_10MIN;

SELECT
  COUNT(*)                                        AS INTERVALS,
  SUM(IFF(COUNTER_RESET, 1, 0))                   AS COUNTER_RESETS,
  SUM(IFF(PACKAGES_OUT IS NULL, 1, 0))            AS NULL_OUTPUT_DELTAS,
  SUM(IFF(IS_RUNNING, 1, 0))                      AS RUNNING_INTERVALS,
  SUM(IFF(IS_PLANNED_STOP, 1, 0))                 AS PLANNED_STOPS,
  SUM(IFF(IS_UNPLANNED_STOP, 1, 0))               AS UNPLANNED_STOPS,
  ROUND(SUM(DURATION_SEC) / 3600.0, 1)            AS TOTAL_HOURS
FROM SILVER.PIADE_INTERVAL;

SELECT
  SUM(IFF(IS_PUBLISHED_FAULT, 1, 0))  AS PUBLISHED_FAULT_WINDOWS,
  SUM(IFF(IS_MODULE_ALARM, 1, 0))     AS MODULE_ALARM_WINDOWS,
  COUNT(DISTINCT MACHINE_CODE)        AS MACHINES
FROM SILVER.COMOPI_ALARM_10MIN;
