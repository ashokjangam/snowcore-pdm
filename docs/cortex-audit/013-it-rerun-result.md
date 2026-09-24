I'll read the SQL file first, then execute it.I'll execute the full script in stages: session setup, table creation, then all verification queries.Session setup done. Now creating the IT_ASSUMPTION table.Now the big one — the WORK_ORDER generator.WORK_ORDER created. Now running all 7 verification queries in parallel.No syntax changes were needed. The script ran as written.

---

## Verification Report

### Query 1 — Count integrity
| Check | Expected | Actual |
|---|---|---|
| Plant B (stops >= 30 min) | 4,061 | **4,061** |
| Plant A (merged incidents) | 1,042 | **1,042** |

### Query 2 — Orphans and cross-plant
| Plant | Orders | Machines | Unknown Machines | Cross-plant rows |
|---|---|---|---|---|
| PLANT_B | 4,061 | 5 | 0 | 0 |
| PLANT_A | 1,042 | 8 | 0 | 0 |

Clean on both plants.

### Query 3 — Cost shape
| Plant | Orders | Labour | Parts | Lost Production | Grand Total | Avg/Order |
|---|---|---|---|---|---|---|
| PLANT_B | 4,061 | 290,313 | 389,686 | 8,899,403 | 9,579,396 | 2,358.88 |
| PLANT_A | 1,042 | 35,168 | 37,316 | NULL | 72,483 | 69.56 |

### Query 4 — Undiagnosed cost (Plant B)
UNDIAGNOSED: 3,592 orders, 8,060 stop-hours, 8,997,942 EUR (93.9% of Plant B cost). The top diagnosed alarm codes are A_006 (2.25%), A_065 (1.45%), A_001 (1.15%).

### Query 5 — Determinism
| Orders checked | Mismatches |
|---|---|
| 5,103 | **0** |

### Query 5b — Parts probability by priority band
| Plant | Priority | Orders | With Parts | PCT_WITH_PARTS | Avg Parts Cost |
|---|---|---|---|---|---|
| PLANT_A | P2 | 6 | 4 | **66.7%** | 216.17 |
| PLANT_A | P3 | 29 | 13 | **44.8%** | 145.19 |
| PLANT_A | P4 | 1,007 | 107 | **10.6%** | 31.59 |
| PLANT_B | P1 | 619 | 485 | **78.4%** | 225.10 |
| PLANT_B | P2 | 689 | 406 | **58.9%** | 155.92 |
| PLANT_B | P3 | 1,075 | 337 | **31.3%** | 90.71 |
| PLANT_B | P4 | 1,678 | 179 | **10.7%** | 27.06 |

### Query 6 — Priority mix
| Plant | Priority | Orders | Avg Event Minutes |
|---|---|---|---|
| PLANT_A | P2 | 6 | 148.3 |
| PLANT_A | P3 | 29 | 75.5 |
| PLANT_A | P4 | 1,007 | 14.9 |
| PLANT_B | P1 | 619 | 384.4 |
| PLANT_B | P2 | 689 | 171.3 |
| PLANT_B | P3 | 1,075 | 83.5 |
| PLANT_B | P4 | 1,678 | 42.0 |

---

## Judgement

**1. Query 1 counts exact?** Yes. Plant B = 4,061, Plant A = 1,042, both exact.

**2. Query 5 exactly zero?** Yes. 5,103 orders checked, 0 mismatches.

**3. Does PCT_WITH_PARTS track the intended 10/30/55/80?**
Yes. Using Plant B (which has all four bands with meaningful sample sizes):
- P4: **10.7%** (target 10)
- P3: **31.3%** (target 30)
- P2: **58.9%** (target 55)
- P1: **78.4%** (target 80)

All track closely. Plant A's P4 at 10.6% also matches. Its P3 (44.8%) and P2 (66.7%) are slightly above target, but those bands have only 29 and 6 orders respectively — small-sample noise from the hash-based draw.

**4. Plant A parts vs labour — did the fix work?**
Previous run: labour 35,167 EUR, parts 303,692 EUR (parts 8.6x labour).
This run: labour 35,168 EUR, parts **37,316 EUR**.

Parts are now roughly equal to labour rather than eight times it. Parts is no longer larger than labour in any meaningful sense — 37,316 vs 35,168 is essentially parity, which is a reasonable shape for a plant whose median incident is a 10-minute alarm blip. **The fix went far enough.**

**5. Is Plant B's cost still dominated by lost production?**
Yes. The split:
- Lost production: **8,899,403 EUR** (92.9% of Plant B's 9,579,396 grand total)
- Labour: 290,313 EUR (3.0%)
- Parts: 389,686 EUR (4.1%)

Maintenance spend (labour + parts = 679,999 EUR) is 7.1% of the total. Lost production dominates by a factor of 13:1. This is the expected shape for an OEE story where the cost of the machine not running dwarfs the cost of fixing it.All tables rebuilt, all checks pass. No syntax changes were made — the script executed cleanly as written.