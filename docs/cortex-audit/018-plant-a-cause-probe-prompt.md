Measurement only. Read-only. Create nothing, alter nothing, drop nothing.

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

Plant A work orders currently all carry the constant cause code `MODULE_ALARM`,
because `SILVER.COMOPI_ALARM_10MIN` sums sixteen module alarm columns into one
`MODULE_ALARM_COUNT`. The individual columns still exist in
`BRONZE.COMOPI_ALARMS_RAW` as `AL_17, AL_18, AL_40, AL_41, AL_42, AL_43, AL_45,
AL_46, AL_47, AL_48, AL_49, AL_50, AL_51, AL_52, AL_53, AL_54`.

I want to know whether recovering per-code detail would give a genuinely
informative cause breakdown, or whether one code dominates so heavily that the
result is degenerate and not worth the change. Do not change anything based on
the answer — just measure.

## 1. How often each module alarm fires, and on how many machines

Unpivot the sixteen columns into long form using LATERAL FLATTEN over an
OBJECT_CONSTRUCT, counting only windows where that column is greater than zero:

    WITH long AS (
      SELECT SERIAL, f.KEY AS ALARM_CODE, f.VALUE::INT AS FIRES
      FROM BRONZE.COMOPI_ALARMS_RAW,
      LATERAL FLATTEN(input => OBJECT_CONSTRUCT(
        'AL_17', AL_17, 'AL_18', AL_18, 'AL_40', AL_40, 'AL_41', AL_41,
        'AL_42', AL_42, 'AL_43', AL_43, 'AL_45', AL_45, 'AL_46', AL_46,
        'AL_47', AL_47, 'AL_48', AL_48, 'AL_49', AL_49, 'AL_50', AL_50,
        'AL_51', AL_51, 'AL_52', AL_52, 'AL_53', AL_53, 'AL_54', AL_54)) f
      WHERE f.VALUE::INT > 0
    )
    SELECT ALARM_CODE,
      COUNT(*) AS WINDOWS_WITH_CODE,
      SUM(FIRES) AS TOTAL_ACTIVATIONS,
      COUNT(DISTINCT SERIAL) AS MACHINES,
      ROUND(100.0 * SUM(FIRES) / SUM(SUM(FIRES)) OVER (), 2) AS PCT_OF_ACTIVATIONS
    FROM long GROUP BY ALARM_CODE ORDER BY TOTAL_ACTIVATIONS DESC;

## 2. Concentration

From the same `long` CTE, report the share of total activations held by the
single largest code, and by the top three combined. Also report how many of the
sixteen codes account for 90% of activations, using a cumulative sum.

## 3. How many windows are ambiguous

A window can have several module alarms at once. Report, over windows where at
least one module alarm fired: how many have exactly one distinct code active,
how many have two, and how many have three or more. Express each as a
percentage. This tells me whether picking a single dominant code per window is
an honest attribution or a coin toss.

## 4. Does the dominant code vary by machine

    -- for each SERIAL, the module alarm with the most activations
    -- report SERIAL, that code, and its share of that machine's activations

Report whether different machines have different dominant codes, or whether
one code leads everywhere.

## Judgement

Answer these directly, and do not soften the answer to make the change look
worthwhile:

1. Is the distribution informative, or does one code hold so much of the
   volume that a per-code Pareto would just be one bar?
2. What fraction of alarm windows would have an ambiguous attribution if I
   picked the highest-count code per window?
3. Given 1 and 2, is replacing the constant `MODULE_ALARM` with a per-code
   attribution worth doing, or is the honest position that Plant A simply does
   not have a usable cause dimension? Say which, and why.
