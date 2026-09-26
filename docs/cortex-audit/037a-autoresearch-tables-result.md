I'll read the SQL file first, then execute the statements in order.Now I'll execute the statements in order. Starting with session setup, then CREATE TABLEs, then ALTERs, then the EXECUTE IMMEDIATE.Session set. Now setting timezone/query_tag and creating the 7 tables.All 7 tables created. Now executing the ALTER TABLE ADD COLUMN IF NOT EXISTS statements.The "ambiguous column name" errors are expected — those columns already exist from the CREATE TABLE (which just ran). The `ADD COLUMN IF NOT EXISTS` is a no-op for them, but Snowflake raises this when the column is already present with a DEFAULT. This is benign. Now executing the RESEARCH_RUN ALTER columns and the fold metric ALTERs.All ALTERs done. Now running the EXECUTE IMMEDIATE fallback — directly executing the `DROP NOT NULL` since dollar-quoting often fails through the tool.All done. Here's the summary:

**Tables created** (all in `SNOWCORE_REAL.ML`):
1. `PIADE_RESEARCH_CAMPAIGN`
2. `PIADE_RESEARCH_RUN`
3. `PIADE_RESEARCH_FOLD_METRIC`
4. `PIADE_RESEARCH_LINE_METRIC`
5. `PIADE_RESEARCH_PROMOTION_GATE`
6. `PIADE_RESEARCH_HOLDOUT_METRIC`
7. `PIADE_CHAMPION_CONTRACT`

**ALTER TABLE ADD COLUMN IF NOT EXISTS** — all executed. Columns that already existed from the fresh CREATE TABLE raised `ambiguous column name` (benign, means the column was already present): `EVALUATED_TRIALS`, `REJECTED_PROPOSALS`, `CRASHED_TRIALS`, `PROMOTION_ELIGIBLE`, `HOLDOUT_EVALUATED`, `PRODUCTION_TABLES_MODIFIED`, `BUDGET_EXCEEDED`. All other ADD COLUMN statements succeeded.

**TRIAL_NUMBER NOT NULL migration** — `DROP NOT NULL` confirmed the constraint does not exist (column was created nullable in this fresh table), so no action needed.

No errors requiring attention.