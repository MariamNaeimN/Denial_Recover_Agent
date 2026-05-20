# QuickSight Dashboard Guide — DenialRecover AI

## Dataset

Use this custom SQL query (Direct Query mode):

```sql
SELECT
    c.claim_id,
    c.patient_id,
    c.patient_name,
    c.payer,
    c.status,
    c.claim_amount,
    c.denial_code,
    c.denial_category,
    c.success_probability,
    c.priority_score,
    c.expected_recovery,
    c.recovery_opportunity,
    c.appeal_deadline,
    c.created_at,
    c.updated_at,
    dt.claim_count AS denial_trend_count,
    dt.total_amount AS denial_trend_total,
    dt.avg_success_rate AS denial_trend_avg_rate,
    rs.total_denied AS summary_total_denied,
    rs.total_recovered AS summary_total_recovered,
    rs.total_expected AS summary_total_expected,
    rs.pending_appeals AS summary_pending_appeals,
    rs.success_rate AS summary_success_rate,
    rs.high_priority_count AS summary_high_priority
FROM claims c
LEFT JOIN denial_trends dt
    ON c.denial_code = dt.denial_code
    AND c.payer = dt.payer
CROSS JOIN recovery_summary rs
ORDER BY c.expected_recovery DESC
```

---

## Calculated Fields (create these first)

| Name | Formula | Purpose |
|------|---------|---------|
| `success_rate_pct` | `success_probability / 100` | Proper percentage display |
| `is_high_priority` | `ifelse(recovery_opportunity = 'HIGH', 1, 0)` | Count high priority |
| `days_to_deadline` | `dateDiff(now(), parseDate(appeal_deadline, 'yyyy-MM-dd'), 'DD')` | Urgency calc |

---

## Chart 1: Total Recoverable Revenue (KPI)

**Type:** KPI

**Purpose:** Shows the total dollar amount that can potentially be recovered from all denied claims.

**Setup:**
- Value: `expected_recovery` → Aggregation: **Sum**
- Format: Currency, 0 decimal places
- Comparison: `summary_total_denied` (Sum) — shows recovery as % of total denied

**What it tells you:** "We have $X in recoverable revenue sitting in the queue."

---

## Chart 2: Total Denied Amount (KPI)

**Type:** KPI

**Purpose:** Total dollar value of all denied claims being tracked.

**Setup:**
- Value: `claim_amount` → Aggregation: **Sum**
- Format: Currency, 0 decimal places

**What it tells you:** "We're tracking $X in total denied claims."

---

## Chart 3: Average Success Probability (KPI)

**Type:** KPI

**Purpose:** Overall likelihood of winning appeals across all claims.

**Setup:**
- Value: `success_probability` → Aggregation: **Average**
- Format: **Number** (NOT percentage), Suffix: `%`, 0 decimal places

**What it tells you:** "On average, our claims have X% chance of successful appeal."

---

## Chart 4: High Priority Claims Count (KPI)

**Type:** KPI

**Purpose:** Number of claims with high recovery opportunity.

**Setup:**
- Value: `claim_id` → Aggregation: **Count**
- Filter: `recovery_opportunity` = 'HIGH'
- Format: Number, 0 decimal places

**What it tells you:** "X claims are high-priority and should be appealed immediately."

---

## Chart 5: Top Denial Reasons by Dollar Impact (Horizontal Bar)

**Type:** Horizontal Bar Chart

**Purpose:** Shows which denial reasons are costing the most money — the "root cause" view.

**Setup:**
- Y-axis (Categories): `denial_code`
- Value: `claim_amount` → Aggregation: **Sum**
- Sort: By value, descending
- Color: Single color (blue) or by `denial_code`

**What it tells you:** "CODING_ERROR denials cost us $953K — that's our biggest problem."

---

## Chart 6: Recovery Opportunity Distribution (Donut)

**Type:** Donut Chart

**Purpose:** Shows the proportion of claims by recovery opportunity level.

**Setup:**
- Group: `recovery_opportunity`
- Value: `claim_id` → Aggregation: **Count**
- Colors: HIGH = green, MEDIUM = yellow/orange, LOW = red

**What it tells you:** "X% of our claims are high-opportunity — we should focus there."

---

## Chart 7: Expected Recovery by Denial Type (Stacked Bar)

**Type:** Vertical Stacked Bar Chart

**Purpose:** Shows how much money is recoverable per denial type, broken down by priority.

**Setup:**
- X-axis: `denial_code`
- Value: `expected_recovery` → Aggregation: **Sum**
- Color/Group: `recovery_opportunity`
- Sort: By value, descending

**What it tells you:** "CODING_ERROR has the most recoverable dollars, mostly high-priority."

---

## Chart 8: Claims by Payer (Horizontal Bar)

**Type:** Horizontal Bar Chart

**Purpose:** Shows which payers are generating the most denials.

**Setup:**
- Y-axis: `payer`
- Value: `claim_id` → Aggregation: **Count**
- Sort: By value, descending

**Note:** If payer shows "unknown", that's because payer data isn't stored at the top level in DynamoDB yet. This will improve as more data flows through.

**What it tells you:** "Payer X is denying the most claims — we need to review their rules."

---

## Chart 9: Success Probability by Denial Type (Bar)

**Type:** Vertical Bar Chart

**Purpose:** Shows which denial types are easiest to overturn.

**Setup:**
- X-axis: `denial_code`
- Value: `success_probability` → Aggregation: **Average**
- Format: Number with `%` suffix
- Sort: By value, descending
- Conditional color: > 70 green, 40-70 yellow, < 40 red

**What it tells you:** "DUPLICATE denials have 79% success rate — always appeal those."

---

## Chart 10: Priority Queue Table (Table)

**Type:** Table

**Purpose:** The actionable work queue — shows every claim ranked by expected recovery.

**Setup:**
- Columns (in order):
  1. `claim_id`
  2. `patient_name`
  3. `denial_code`
  4. `claim_amount` (format: currency)
  5. `success_probability` (format: number + % suffix)
  6. `expected_recovery` (format: currency)
  7. `recovery_opportunity`
- Sort: `expected_recovery` descending
- Conditional formatting:
  - `recovery_opportunity` = HIGH → green background
  - `recovery_opportunity` = MEDIUM → yellow background
  - `recovery_opportunity` = LOW → red background

**What it tells you:** "Here are the exact claims to appeal, in priority order."

---

## Chart 11: Denial Trend Summary (Table)

**Type:** Table

**Purpose:** Aggregated view of denial patterns for management reporting.

**Setup:**
- Columns:
  1. `denial_code`
  2. `denial_trend_count` (rename to "Claims")
  3. `denial_trend_total` (rename to "Total $", format: currency)
  4. `denial_trend_avg_rate` (rename to "Avg Success %", format: number + % suffix)
- Sort: `denial_trend_total` descending

**What it tells you:** "Here's the pattern — CODING_ERROR is 24 claims worth $953K with 50% win rate."

---

## Chart 12: Recovery Opportunity Treemap

**Type:** Tree Map

**Purpose:** Visual representation of where the money is — bigger boxes = more dollars.

**Setup:**
- Group by: `denial_code`
- Size: `expected_recovery` → Aggregation: **Sum**
- Color: `success_probability` → Aggregation: **Average** (gradient: red → green)

**What it tells you:** Big green boxes = appeal first. Big red boxes = hard to win but high value.

---

## Filters (add to top of dashboard)

| Filter | Field | Type | Default |
|--------|-------|------|---------|
| Denial Reason | `denial_code` | Dropdown multi-select | All |
| Priority | `recovery_opportunity` | Dropdown | All |
| Payer | `payer` | Dropdown | All |
| Min Claim Amount | `claim_amount` | Slider | $0 |
| Min Success Rate | `success_probability` | Slider | 0 |

---

## Dashboard Layout (suggested)

```
┌─────────────────────────────────────────────────────────────┐
│  [KPI: Total    ] [KPI: Total  ] [KPI: Avg    ] [KPI: High ]│
│  [Recoverable  ] [Denied      ] [Success %   ] [Priority # ]│
├─────────────────────────────────┬───────────────────────────┤
│                                 │                           │
│  Chart 5: Top Denial Reasons    │  Chart 6: Recovery        │
│  (Horizontal Bar)               │  Opportunity (Donut)      │
│                                 │                           │
├─────────────────────────────────┼───────────────────────────┤
│                                 │                           │
│  Chart 7: Expected Recovery     │  Chart 9: Success Rate    │
│  by Denial Type (Stacked Bar)   │  by Denial Type (Bar)     │
│                                 │                           │
├─────────────────────────────────┴───────────────────────────┤
│                                                             │
│  Chart 10: Priority Queue Table                             │
│  (Full width — the main actionable view)                    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Chart 11: Denial Trend Summary  │  Chart 12: Treemap       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Tips

- Use **Number** format with `%` suffix for success_probability (NOT percentage format)
- Sort tables by `expected_recovery` DESC for priority ordering
- Use conditional formatting (green/yellow/red) on `recovery_opportunity`
- All data refreshes live from Redshift (Direct Query mode)
- Redshift syncs from DynamoDB every hour automatically
