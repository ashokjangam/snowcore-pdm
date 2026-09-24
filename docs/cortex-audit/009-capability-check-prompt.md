Read-only capability check. Do not create, drop or modify any object except
where a statement below explicitly says to create a throwaway test object, and
drop those again afterwards.

A previous run reported that every class in `SNOWFLAKE.ML` has `version = None`
and that `CREATE SNOWFLAKE.ML.CLASSIFICATION` fails with "CLASSIFICATION must
have an active version defined". I need that verified independently, and I need
to know what else is or is not available, because the rest of the build depends
on it. Report each item as WORKS or FAILS with the exact error text.

## 1. Account facts

Run and report:

    SELECT CURRENT_ACCOUNT(), CURRENT_REGION(), CURRENT_ROLE(),
           CURRENT_WAREHOUSE(), CURRENT_VERSION();
    SHOW PARAMETERS LIKE 'ENABLE%' IN ACCOUNT;

Also report the account edition if you can obtain it.

## 2. Built-in ML classes

    SHOW SNOWFLAKE.ML CLASSES IN SCHEMA SNOWFLAKE.ML;
    SHOW VERSIONS IN CLASS SNOWFLAKE.ML.CLASSIFICATION;
    SHOW VERSIONS IN CLASS SNOWFLAKE.ML.ANOMALY_DETECTION;
    SHOW VERSIONS IN CLASS SNOWFLAKE.ML.FORECAST;

Report the version column verbatim for each. If a class has versions listed but
none active, say so explicitly — that is a different problem from having no
versions at all.

Then check the privilege side, because "no active version" can also be what you
see when the role lacks the grant:

    SHOW GRANTS TO ROLE ACCOUNTADMIN;

and look for anything mentioning CLASSIFICATION, FORECAST, ANOMALY_DETECTION or
SNOWFLAKE.ML. Report what you find, or state plainly that nothing matches.

## 3. Cortex LLM functions

These matter more than the ML classes, because the application layer depends on
them. Test each and report the actual output or the actual error:

    SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-4-sonnet', 'Reply with exactly: OK');
    SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2', 'Reply with exactly: OK');
    SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.1-8b', 'Reply with exactly: OK');
    SELECT SNOWFLAKE.CORTEX.SENTIMENT('The bearing is running hot again.');
    SELECT SNOWFLAKE.CORTEX.SUMMARIZE('Line 3 stopped twice on Tuesday for a jammed infeed guide, then again on Wednesday for the same cause.');
    SELECT AI_COMPLETE('claude-4-sonnet', 'Reply with exactly: OK');

If a model name is rejected, list which models ARE available in this region and
retry with one of them. Getting at least one working COMPLETE call is the point.

## 4. Semantic views and Cortex Analyst

    SHOW SEMANTIC VIEWS IN ACCOUNT;

Then create a minimal throwaway semantic view over SNOWCORE_REAL.GOLD to prove
the syntax is accepted on this version, query it once, and drop it. Something
like a single table, one dimension, one metric. Report whether CREATE SEMANTIC
VIEW is supported at all.

## 5. Snowpark Python

Confirm the fallback path actually works, since a previous run used it:

    SHOW FUNCTIONS LIKE '%' IN SCHEMA SNOWCORE_REAL.ML;
    SHOW PROCEDURES IN SCHEMA SNOWCORE_REAL.ML;

Report which Python runtime versions are available and which of
scikit-learn, xgboost, lightgbm, pandas and pyarrow are in the Snowflake
Anaconda channel for this account.

## 6. Streamlit in Snowflake

    SHOW STREAMLITS IN ACCOUNT;

and state whether the account can create a Streamlit app (check for the
privilege, do not create one).

## What to conclude

Finish with a short plain list under two headings: AVAILABLE and NOT AVAILABLE.
For anything not available, say whether it looks like a provisioning problem, a
privilege problem, a region problem, or an edition problem, and say which one
you are confident about versus guessing. Do not speculate confidently.
