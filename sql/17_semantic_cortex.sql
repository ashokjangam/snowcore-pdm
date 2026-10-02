/* ============================================================================
   PIADE-only presentation, semantic model and bounded Cortex narrative.

   Run after sql/18_piade_erp.sql because the semantic model intentionally
   includes its production-order, work-order and material contracts.
   No other dataset is referenced. Model quality is always read from persisted
   final-blind-test metrics; no metric is hard-coded in prose.
   ========================================================================== */
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE='UTC';
ALTER SESSION SET QUERY_TAG='snowcore-real|piade|semantic';

/* Fail immediately with an object-not-found error if deployment sequencing is
   wrong. Required order is 15 -> 18 -> 17. */
SELECT COUNT(*) AS ERP_DEPENDENCY_CHECK
FROM GOLD.PRODUCTION_ORDER
WHERE 1=0;

CREATE OR REPLACE VIEW GOLD.V_FLEET AS
SELECT PLANT_CODE,PLANT_LABEL,PLANT_ROLE,m.MACHINE_KEY,m.MACHINE_CODE,
  m.FIRST_SEEN,m.LAST_SEEN,m.SENSOR_WINDOWS AS SOURCE_ROWS,
  p.SOURCE_DOI,p.SOURCE_LICENSE,
  'OEE and stop-risk are available. The site and equipment identities are anonymised; no analogue sensor channels are published.'
    AS CAPABILITY_NOTE,
  'OBSERVED' AS DATA_ORIGIN
FROM SILVER.DIM_MACHINE m JOIN SILVER.DIM_PLANT p USING(PLANT_CODE)
WHERE m.PLANT_CODE='PLANT_B';

CREATE OR REPLACE VIEW GOLD.V_PIADE_MACHINE AS
SELECT MACHINE_KEY,MACHINE_CODE,FIRST_SEEN,LAST_SEEN,SENSOR_WINDOWS,DATA_ORIGIN
FROM SILVER.DIM_MACHINE WHERE PLANT_CODE='PLANT_B';

CREATE OR REPLACE VIEW GOLD.V_PIADE_WORK_ORDER AS
SELECT * FROM GOLD.WORK_ORDER WHERE PLANT_CODE='PLANT_B';

CREATE OR REPLACE VIEW GOLD.V_OEE_DAILY AS
SELECT PLANT_CODE,MACHINE_KEY,MACHINE_CODE,OEE_DATE,HOURS_OBSERVED,
  ROUND(PLANNED_SEC/3600,2) PLANNED_HOURS,
  ROUND(RUN_SEC/3600,2) RUN_HOURS,
  ROUND(DOWNTIME_SEC/3600,2) BREAKDOWN_HOURS,
  ROUND(IDLE_SEC/3600,2) IDLE_HOURS,
  ROUND(SLOW_SEC/3600,2) SLOW_RUNNING_HOURS,
  PACKAGES_IN,PACKAGES_OUT,THEORETICAL_PACKAGES,
  AVAILABILITY,PERFORMANCE,QUALITY,OEE,QUALITY_CLAMPED,
  ROUND(THEORETICAL_PACKAGES-PACKAGES_OUT,0) PACKAGES_FORGONE,
  DATA_ORIGIN
FROM GOLD.PIADE_OEE_DAILY WHERE PLANT_CODE='PLANT_B';

CREATE OR REPLACE VIEW GOLD.V_OEE_ROLLUP AS
SELECT PLANT_CODE,MACHINE_CODE,MIN(OEE_DATE) FROM_DATE,MAX(OEE_DATE) TO_DATE,
  COUNT(*) DAYS_OBSERVED,SUM(PLANNED_SEC)/3600 PLANNED_HOURS,
  SUM(RUN_SEC)/3600 RUN_HOURS,SUM(DOWNTIME_SEC)/3600 BREAKDOWN_HOURS,
  SUM(IDLE_SEC)/3600 IDLE_HOURS,SUM(SLOW_SEC)/3600 SLOW_RUNNING_HOURS,
  SUM(PACKAGES_OUT) PACKAGES_OUT,
  SUM(RUN_SEC)/NULLIF(SUM(PLANNED_SEC),0) AVAILABILITY,
  SUM(PACKAGES_OUT)/NULLIF(SUM(THEORETICAL_PACKAGES),0) PERFORMANCE,
  SUM(PACKAGES_OUT)/NULLIF(SUM(PACKAGES_IN),0) QUALITY,
  (SUM(RUN_SEC)/NULLIF(SUM(PLANNED_SEC),0))
   *(SUM(PACKAGES_OUT)/NULLIF(SUM(THEORETICAL_PACKAGES),0))
   *(SUM(PACKAGES_OUT)/NULLIF(SUM(PACKAGES_IN),0)) OEE,
  'DERIVED_FROM_OBSERVED' DATA_ORIGIN
FROM GOLD.PIADE_OEE_DAILY WHERE PLANT_CODE='PLANT_B'
GROUP BY ROLLUP(PLANT_CODE,MACHINE_CODE) HAVING PLANT_CODE IS NOT NULL;

CREATE OR REPLACE VIEW GOLD.V_DOWNTIME_PARETO AS
WITH aggregate_causes AS (
  SELECT PLANT_CODE,
    IFF(STOP_STATE='idle','IDLE_NO_ALARM',ALARM_CODE) CAUSE_CODE,
    IFF(STOP_STATE='idle','WAITING','FAULTED') LOSS_NATURE,
    IFF(STOP_STATE='idle','PLANNING','MAINTENANCE') OWNING_FUNCTION,
    COUNT(*) STOP_COUNT,SUM(STOP_DURATION_MIN)/60 STOP_HOURS,
    MEDIAN(STOP_DURATION_MIN) MEDIAN_STOP_MIN,MAX(STOP_DURATION_MIN) LONGEST_STOP_MIN,
    COUNT(DISTINCT MACHINE_CODE) MACHINES_AFFECTED,
    SUM(STOP_DURATION_MIN) STOP_MINUTES,
  CASE
    WHEN COUNT(*)>=5000 AND MEDIAN(STOP_DURATION_MIN)<5 THEN 'CHRONIC_SHORT'
    WHEN COUNT(*)<200 AND MEDIAN(STOP_DURATION_MIN)>=30 THEN 'RARE_MAJOR'
    WHEN MEDIAN(STOP_DURATION_MIN)>=10 THEN 'OCCASIONAL_LONG'
    ELSE 'INTERMITTENT'
    END STOP_PATTERN
  FROM GOLD.PIADE_DOWNTIME_EVENT
  WHERE PLANT_CODE='PLANT_B'
  GROUP BY PLANT_CODE,IFF(STOP_STATE='idle','IDLE_NO_ALARM',ALARM_CODE),
    IFF(STOP_STATE='idle','WAITING','FAULTED'),
    IFF(STOP_STATE='idle','PLANNING','MAINTENANCE')
)
SELECT PLANT_CODE,CAUSE_CODE,LOSS_NATURE,OWNING_FUNCTION,STOP_COUNT,STOP_HOURS,
  MEDIAN_STOP_MIN,LONGEST_STOP_MIN,MACHINES_AFFECTED,
  100*STOP_MINUTES/SUM(STOP_MINUTES) OVER(PARTITION BY LOSS_NATURE) PCT_OF_STOP_TIME,
  100*SUM(STOP_MINUTES) OVER(PARTITION BY LOSS_NATURE ORDER BY STOP_MINUTES DESC
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    /SUM(STOP_MINUTES) OVER(PARTITION BY LOSS_NATURE) CUMULATIVE_PCT,
  STOP_PATTERN,'OBSERVED' DATA_ORIGIN
FROM aggregate_causes;

CREATE OR REPLACE VIEW GOLD.V_PLANT_B_RISK AS
SELECT 'PLANT_B' PLANT_CODE,r.MACHINE_KEY,r.MACHINE_CODE,
  /* Snowpark write_pandas persists pandas timestamps as epoch nanoseconds on
     this account. Convert once in the presentation view so every consumer,
     including Streamlit, receives a real TIMESTAMP_NTZ. */
  TO_TIMESTAMP_NTZ(r.HOUR_TS/1000000000) HOUR_TS,
  r.RISK_SCORE,r.RISK_PERCENTILE,r.RISK_BAND,r.IS_FLAGGED,
  r.LABEL_HEAVY_STOP ACTUAL_HEAVY_STOP,r.NEXT_HOUR_DOWNTIME,
  m.AUC,m.AVG_PRECISION,m.TOP_DECILE_PRECISION,m.TOP_DECILE_RECALL,
  m.BASELINE_AUC,m.BASELINE_AVG_PRECISION,
  m.BASELINE_TOP_DECILE_PRECISION,m.BASELINE_TOP_DECILE_RECALL,
  IFF(m.TOP_DECILE_PRECISION>m.BASELINE_TOP_DECILE_PRECISION,FALSE,TRUE)
    MODEL_LOSES_TO_BASELINE,
  TO_TIMESTAMP_NTZ(m.BLIND_TEST_START/1000000000) BLIND_TEST_START,
  TO_TIMESTAMP_NTZ(m.BLIND_TEST_END/1000000000) BLIND_TEST_END,
  m.CAVEAT,r.DATA_ORIGIN
FROM ML.PLANT_B_RISK_SCORE r
LEFT JOIN ML.PLANT_B_MODEL_METRICS m ON m.SCOPE=r.MACHINE_CODE;

CREATE OR REPLACE VIEW GOLD.V_PROVENANCE AS
SELECT 'PLANT_B' PLANT_CODE,'PIADE production and stop events' SUBJECT,
  'OBSERVED' DATA_ORIGIN,'PIADE DOI 10.5281/zenodo.7071747, CC BY 4.0' SOURCE,
  'Machine, alarm and site identities are anonymised by the publisher.' NOTE
UNION ALL SELECT 'PLANT_B','OEE','DERIVED_FROM_OBSERVED',
  'Computed from PIADE intervals',
  'Ideal rate is best demonstrated speed; quality is throughput yield, not inspection quality.'
UNION ALL SELECT 'PLANT_B','Next-hour heavy-stop risk','DERIVED_FROM_OBSERVED',
  'ExtraTrees over PIADE hourly aggregates',
  'Selected on rolling-origin validation and measured once on the blind period from 2021-12-01; partly persistence and not causal.'
UNION ALL SELECT 'PLANT_B','ERP, work orders, materials, inventory and euros','SYNTHETIC_ERP',
  'Deterministic scenarios anchored to PIADE',
  'Invented business records and financial assumptions. Generic service-kit names do not identify physical components.';

/* Semantic-view identifiers use compact logical names while physical contracts
   stay explicit. If an account release does not support SEMANTIC VIEW, all
   presentation views above remain usable without Cortex Analyst. */
CREATE OR REPLACE SEMANTIC VIEW GOLD.SEM_SNOWCORE_OEE
  TABLES (
    machine AS GOLD.V_PIADE_MACHINE
      PRIMARY KEY (MACHINE_KEY)
      WITH SYNONYMS ('line','equipment','asset')
      COMMENT='Five anonymised PIADE packaging machines.',
    oee AS GOLD.PIADE_OEE_DAILY
      PRIMARY KEY (MACHINE_KEY,OEE_DATE)
      WITH SYNONYMS ('oee','daily production','line performance')
      COMMENT='Daily measures derived from observed PIADE intervals.',
    production_order AS GOLD.PRODUCTION_ORDER
      PRIMARY KEY (PRODUCTION_ORDER_ID)
      WITH SYNONYMS ('production order','erp order','daily order')
      COMMENT='SYNTHETIC_ERP order, one per observed PIADE machine/day.',
    work_order AS GOLD.V_PIADE_WORK_ORDER
      PRIMARY KEY (WORK_ORDER_ID)
      WITH SYNONYMS ('work order','repair','maintenance job')
      COMMENT='SYNTHETIC_IT work order anchored to an observed PIADE breakdown.',
    work_order_part AS GOLD.WORK_ORDER_PART
      PRIMARY KEY (WORK_ORDER_PART_ID)
      WITH SYNONYMS ('part consumption','service kit usage')
      COMMENT='SYNTHETIC_ERP deterministic reconciliation to work-order parts cost.',
    material AS GOLD.DIM_MATERIAL
      PRIMARY KEY (MATERIAL_ID)
      WITH SYNONYMS ('material','service kit')
      COMMENT='Generic scenario kit keyed by anonymised cause; not a physical component claim.'
  )
  RELATIONSHIPS (
    oee_to_machine AS oee(MACHINE_KEY) REFERENCES machine,
    production_order_to_machine AS production_order(MACHINE_KEY) REFERENCES machine,
    work_order_to_machine AS work_order(MACHINE_KEY) REFERENCES machine,
    part_to_work_order AS work_order_part(WORK_ORDER_ID) REFERENCES work_order,
    part_to_material AS work_order_part(MATERIAL_ID) REFERENCES material
  )
  FACTS (
    oee.run_seconds AS RUN_SEC,
    oee.planned_seconds AS PLANNED_SEC,
    oee.downtime_seconds AS DOWNTIME_SEC,
    oee.idle_seconds AS IDLE_SEC,
    oee.packages_out AS PACKAGES_OUT,
    oee.packages_in AS PACKAGES_IN,
    oee.theoretical_packages AS THEORETICAL_PACKAGES,
    production_order.target_units AS TARGET_OUTPUT_UNITS,
    production_order.actual_units AS ACTUAL_OUTPUT_UNITS,
    production_order.margin_exposure AS MARGIN_EXPOSURE_EUR,
    work_order.total_cost AS TOTAL_COST,
    work_order.labour_cost AS LABOUR_COST,
    work_order.parts_cost AS PARTS_COST,
    work_order_part.quantity AS QUANTITY,
    work_order_part.extended_cost AS EXTENDED_COST_EUR
  )
  DIMENSIONS (
    machine.machine_code AS MACHINE_CODE WITH SYNONYMS ('line name','equipment id'),
    oee.production_date AS OEE_DATE WITH SYNONYMS ('date','day'),
    production_order.order_id AS PRODUCTION_ORDER_ID,
    production_order.order_status AS ORDER_STATUS,
    work_order.priority AS PRIORITY,
    work_order.cause_code AS CAUSE_CODE
      COMMENT='Publisher-anonymised alarm code; do not infer component identity.',
    material.material_id AS MATERIAL_ID,
    material.material_name AS MATERIAL_NAME
      COMMENT='Synthetic generic service-kit name, not an observed component.'
  )
  METRICS (
    oee.availability AS SUM(oee.run_seconds)/NULLIF(SUM(oee.planned_seconds),0)
      WITH SYNONYMS ('availability','uptime'),
    oee.performance AS SUM(oee.packages_out)/NULLIF(SUM(oee.theoretical_packages),0)
      WITH SYNONYMS ('performance','speed efficiency'),
    oee.quality AS SUM(oee.packages_out)/NULLIF(SUM(oee.packages_in),0)
      WITH SYNONYMS ('quality','throughput yield'),
    oee.oee AS
      (SUM(oee.run_seconds)/NULLIF(SUM(oee.planned_seconds),0))
      *(SUM(oee.packages_out)/NULLIF(SUM(oee.theoretical_packages),0))
      *(SUM(oee.packages_out)/NULLIF(SUM(oee.packages_in),0)),
    oee.breakdown_hours AS SUM(oee.downtime_seconds)/3600,
    oee.idle_hours AS SUM(oee.idle_seconds)/3600,
    production_order.output AS SUM(production_order.actual_units),
    production_order.exposure AS SUM(production_order.margin_exposure)
      COMMENT='SYNTHETIC_ERP euros based on an assumed margin.',
    work_order.order_count AS COUNT(work_order.WORK_ORDER_ID),
    work_order.maintenance_cost AS SUM(work_order.total_cost)
      COMMENT='SYNTHETIC_IT euros, not observed accounting data.',
    work_order_part.part_cost AS SUM(work_order_part.extended_cost)
      COMMENT='SYNTHETIC_ERP and reconciled to work-order parts cost.'
  )
  COMMENT='PIADE-only OEE and traceable synthetic ERP. Synthetic records and euros must be identified as scenarios.';

/* Three aggregate-only calls. The model supplies prose, never facts. */
CREATE OR REPLACE TABLE GOLD.CORTEX_BRIEFING AS
WITH k AS (SELECT * FROM GOLD.V_EXECUTIVE_KPI),
m AS (SELECT * FROM ML.PLANT_B_MODEL_METRICS WHERE SCOPE='FLEET')
SELECT 'PIADE_EXECUTIVE' BRIEFING_KEY,
  SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b',
    'Write three cautious sentences using only these PIADE facts. Separate idle from breakdown because planning owns idle and maintenance owns faults. '
    ||'OEE='||ROUND(k.SITE_WEIGHTED_OEE*100,1)||'%, availability='||ROUND(k.AVAILABILITY*100,1)
    ||'%, performance='||ROUND(k.PERFORMANCE*100,1)||'%, throughput yield='||ROUND(k.QUALITY*100,1)
    ||'%, breakdown hours='||ROUND(k.BREAKDOWN_HOURS,1)||', idle hours='||ROUND(k.IDLE_HOURS,1)||'.') NARRATIVE,
  'DERIVED_FROM_OBSERVED' INPUT_ORIGIN,'llama3.3-70b' MODEL_USED,CURRENT_TIMESTAMP GENERATED_AT
FROM k
UNION ALL
SELECT 'PIADE_MODEL',
  SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b',
    'Write three sceptical sentences using only these final-blind-test metrics. Compare model with persistence, state that only the top 10% of rows were selected exactly, and do not claim optimality. '
    ||'AUC='||ROUND(m.AUC,3)||', AP='||ROUND(m.AVG_PRECISION,3)
    ||', top-decile precision='||ROUND(m.TOP_DECILE_PRECISION*100,1)||'%, recall='||ROUND(m.TOP_DECILE_RECALL*100,1)
    ||'%; persistence AUC='||ROUND(m.BASELINE_AUC,3)||', AP='||ROUND(m.BASELINE_AVG_PRECISION,3)
    ||', top-decile precision='||ROUND(m.BASELINE_TOP_DECILE_PRECISION*100,1)||'%. Caveat: '||m.CAVEAT),
  'DERIVED_FROM_OBSERVED','llama3.3-70b',CURRENT_TIMESTAMP
FROM m
UNION ALL
SELECT 'PIADE_FINANCIAL',
  SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b',
    'Write three sentences. Start by saying the euros and ERP records are synthetic scenarios anchored to PIADE, not observed accounting data. '
    ||'Estimated margin exposure EUR='||ROUND(k.ESTIMATED_MARGIN_EXPOSURE_EUR,0)
    ||', work orders='||k.WORK_ORDER_COUNT||', stock risks='||k.STOCK_RISK_COUNT
    ||'. Do not invent savings, ROI, suppliers or component identities.'),
  'SYNTHETIC_ERP','llama3.3-70b',CURRENT_TIMESTAMP
FROM k;

COMMENT ON TABLE GOLD.CORTEX_BRIEFING IS
  'Three bounded PIADE briefings. Narratives use aggregate facts only; synthetic financial inputs are explicitly labelled.';

/* Verification: all fleet rows must be PIADE and narratives must be the three
   approved keys only. Semantic metric results should reconcile to direct SQL. */
SELECT COUNT(*) FLEET_ROWS,COUNT_IF(PLANT_CODE<>'PLANT_B') NON_PIADE_ROWS FROM GOLD.V_FLEET;
SELECT COUNT(*) RISK_ROWS,MIN(HOUR_TS) FIRST_SCORE,MAX(HOUR_TS) LAST_SCORE,
  COUNT_IF(HOUR_TS<'2021-12-01'::TIMESTAMP_NTZ) PRE_BLIND_SCORES FROM GOLD.V_PLANT_B_RISK;
SELECT BRIEFING_KEY,INPUT_ORIGIN,MODEL_USED,NARRATIVE FROM GOLD.CORTEX_BRIEFING ORDER BY BRIEFING_KEY;
SELECT * FROM SEMANTIC_VIEW(
  GOLD.SEM_SNOWCORE_OEE
  DIMENSIONS machine.machine_code
  METRICS oee.availability,oee.performance,oee.quality,oee.oee,
          oee.breakdown_hours,oee.idle_hours
) ORDER BY MACHINE_CODE;
