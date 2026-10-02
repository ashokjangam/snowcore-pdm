# PNEUMORA: verify the app's structured Cortex call

Role `PNEUMORA_ROLE`, warehouse `PNEUMORA_WH`. Read only. Do not edit local files.
Run each statement below exactly as written, one at a time, and report each result or
error verbatim. Do not rewrite or retry a failing statement.

```sql
USE ROLE PNEUMORA_ROLE;
USE WAREHOUSE PNEUMORA_WH;

-- A: the app's exact form
SELECT AI_COMPLETE(model => 'llama3.3-70b',
  prompt => 'Facts: {"failure_id":"F04","longest_loaded_run_minutes_during_failure":176.9}. Explain in two sentences.',
  response_format => TYPE OBJECT(answer STRING, evidence ARRAY(STRING), caveats ARRAY(STRING), next_check STRING)) AS R;

-- B: scalar fields only
SELECT AI_COMPLETE(model => 'llama3.3-70b',
  prompt => 'Facts: {"failure_id":"F04","longest_loaded_run_minutes_during_failure":176.9}. Explain in two sentences.',
  response_format => TYPE OBJECT(answer STRING, next_check STRING)) AS R;

-- C: same as A with another model
SELECT AI_COMPLETE(model => 'claude-3-5-sonnet',
  prompt => 'Facts: {"failure_id":"F04","longest_loaded_run_minutes_during_failure":176.9}. Explain in two sentences.',
  response_format => TYPE OBJECT(answer STRING, evidence ARRAY(STRING), caveats ARRAY(STRING), next_check STRING)) AS R;
```
