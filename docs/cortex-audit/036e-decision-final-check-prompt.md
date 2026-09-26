# Cortex prompt 036e — final monetary boundary check

Run one read-only query against
`SNOWCORE_REAL.GOLD.V_ANALYST_DECISION_CONTEXT`.

Return:

- euro rows whose origin is not synthetic or whose claim class is neither
  `SCENARIO` nor `SCENARIO_ASSUMPTION`;
- model-estimate rows whose origin is not `MODEL_DERIVED_FROM_OBSERVED`;
- non-assumption hour/package rows incorrectly marked synthetic.

Report the three violation counts only. Do not modify any object.
