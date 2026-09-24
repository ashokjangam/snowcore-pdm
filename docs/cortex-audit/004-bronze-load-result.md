I'll start by reading the SQL script to understand what needs to be executed.I have the full picture. The script loads 4 Bronze tables: COMOPI_SENSORS_RAW, COMOPI_ALARMS_RAW, PIADE_DAILY_RAW, and PIADE_HOURLY_RAW. I'll execute each block (CREATE, COPY, verify) with the required session context prefixed.Starting with table 1: COMOPI_SENSORS_RAW.CREATE TABLE COMOPI_SENSORS_RAW: **success**. Now running the COPY INTO.COPY INTO COMOPI_SENSORS_RAW: **15704 rows loaded, 0 errors**. Now verifying.COMOPI_SENSORS_RAW: **15704 loaded, 15704 expected, MATCH = TRUE**.Now table 2: COMOPI_ALARMS_RAW. Let me read the COPY INTO portion to get all 123 alarm columns.Good. The 4 tables are: COMOPI_SENSORS_RAW (15704), COMOPI_ALARMS_RAW (150650), PIADE_INTERVALS_RAW (429394), PIADE_HOURLY_RAW (23376). Now executing table 2: COMOPI_ALARMS_RAW.CREATE TABLE COMOPI_ALARMS_RAW: **success**. Now the COPY INTO.COPY INTO COMOPI_ALARMS_RAW: **150650 rows loaded, 0 errors**. Verifying.COMOPI_ALARMS_RAW: **150650 loaded, 150650 expected, MATCH = TRUE**.Table 3: PIADE_INTERVALS_RAW.COPY INTO PIADE_INTERVALS_RAW: **429394 rows loaded, 0 errors**. Verifying.PIADE_INTERVALS_RAW: **429394 loaded, 429394 expected, MATCH = TRUE**.Table 4: PIADE_HOURLY_RAW. Let me read the CREATE and COPY for this one.Now executing CREATE and COPY for PIADE_HOURLY_RAW.CREATE TABLE PIADE_HOURLY_RAW: **success**. Now the COPY INTO.COPY INTO PIADE_HOURLY_RAW: **23376 rows loaded, 0 errors**. Verifying.PIADE_HOURLY_RAW: **23376 loaded, 23376 expected, MATCH = TRUE**.All 4 Bronze tables loaded successfully. Here is the summary:

## Bronze Load Summary

| Table | Loaded Rows | Expected Rows | Match |
|---|---|---|---|
| COMOPI_SENSORS_RAW | 15,704 | 15,704 | TRUE |
| COMOPI_ALARMS_RAW | 150,650 | 150,650 | TRUE |
| PIADE_INTERVALS_RAW | 429,394 | 429,394 | TRUE |
| PIADE_HOURLY_RAW | 23,376 | 23,376 | TRUE |

All 4 COPY INTO operations completed with 0 errors, and every row count matches the expected value from the published source files.