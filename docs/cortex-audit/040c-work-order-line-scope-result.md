I'll execute these SQL statements in order against the `hackathon` connection.Script deployed successfully. Now running the verification queries.All steps completed successfully. Here's the summary:

| Step | Result |
|---|---|
| **PUT** | `23_risk_work_orders.sql` uploaded (11,600 bytes) |
| **Stage refresh** | File registered (updated) |
| **EXECUTE IMMEDIATE** | View `V_RISK_WORK_ORDER_SUMMARY` created |
| **GENERATE_RISK_WORK_ORDERS(8, 'LINE')** | 45 created, 16 confirmed within 4h |
| **V_RISK_WORK_ORDER_SUMMARY** | 6 rows — fleet-level hit rate 35.6%, lift vs random 1.26x; best line `s_2` at 62.5% hit rate |
| **THRESHOLD_SCOPE counts** | LINE: 45 orders |
| **Sample rows** | 6 rows returned with work order IDs, priorities (P2/P3), outcomes, and lead times ranging from 23–172 min |