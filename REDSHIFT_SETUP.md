# Redshift Serverless - DenialRecover AI Analytics

## Connection Details

| Property | Value |
|----------|-------|
| **Workgroup** | `denialrecover-dev-workgroup` |
| **Database** | `denialrecover` |
| **Admin User** | `admin` |
| **Admin Password** | `DenialRecover2024!` |
| **Region** | `us-east-1` |
| **VPC** | `vpc-0f59e6a70abf16538` (market-intelligence-vpc-dev) |
| **Publicly Accessible** | Yes |

---

## Tables

### 1. `claims` (78 rows)

Stores all processed claim data synced from DynamoDB.

```sql
CREATE TABLE claims (
    claim_id VARCHAR(100) PRIMARY KEY,
    patient_id VARCHAR(100),
    patient_name VARCHAR(200),
    payer VARCHAR(200),
    status VARCHAR(50),
    claim_amount DECIMAL(10,2),
    denial_code VARCHAR(20),
    denial_category VARCHAR(200),
    success_probability INT,
    priority_score INT,
    expected_recovery DECIMAL(10,2),
    recovery_opportunity VARCHAR(50),
    appeal_deadline VARCHAR(50),
    created_at VARCHAR(50),
    updated_at VARCHAR(50)
);
```

**Sample Data:**

| claim_id | denial_code | claim_amount | success_probability | expected_recovery | recovery_opportunity |
|----------|-------------|--------------|---------------------|-------------------|---------------------|
| CLM003 | CODING_ERROR | 125,000 | 85 | 106,250 | HIGH |
| CLM03802 | CODING_ERROR | 68,891 | 85 | 58,557 | HIGH |
| CLM04001 | MISSING_INFO | 32,864 | 75 | 27,934 | HIGH |
| CLM04501 | BUNDLED | 19,970 | 25 | 4,993 | LOW |

---

### 2. `denial_trends` (8 rows)

Aggregated denial patterns by category.

```sql
CREATE TABLE denial_trends (
    trend_date DATE,
    payer VARCHAR(200),
    denial_code VARCHAR(20),
    denial_category VARCHAR(200),
    claim_count INT,
    total_amount DECIMAL(12,2),
    avg_success_rate DECIMAL(5,2)
);
```

**Current Data:**

| denial_code | claim_count | total_amount | avg_success_rate |
|-------------|-------------|--------------|-----------------|
| CODING_ERROR | 24 | $953,619 | 50% |
| AUTH_REQUIRED | 15 | $452,372 | 65% |
| DUPLICATE | 9 | $424,992 | 79% |
| MISSING_INFO | 9 | $257,011 | 68% |
| NON_COVERED | 9 | $201,178 | 48% |
| BUNDLED | 8 | $136,839 | 45% |
| MEDICAL_NECESSITY | 2 | $94,533 | 25% |
| TIMELY_FILING | 2 | $92,450 | 35% |

---

### 3. `recovery_summary` (1 row)

High-level KPIs for the dashboard.

```sql
CREATE TABLE recovery_summary (
    summary_date DATE,
    total_denied DECIMAL(12,2),
    total_recovered DECIMAL(12,2),
    total_expected DECIMAL(12,2),
    pending_appeals INT,
    success_rate DECIMAL(5,2),
    high_priority_count INT
);
```

---

## Data Sync Process

### How It Works

```
DynamoDB (claims table) → Lambda (hourly) → Redshift (full refresh)
```

1. **EventBridge** triggers the `denialrecover-dev-data-sync` Lambda every hour
2. Lambda **scans all items** from DynamoDB `denialrecover-dev-claims` table (with pagination)
3. Lambda **parses `analysisJson`** field to extract denial codes, amounts, probabilities
4. Lambda **TRUNCATES** all 3 Redshift tables
5. Lambda **INSERTs** all claims in batches of 50
6. Lambda **aggregates** denial_trends and recovery_summary from the claims data
7. Lambda **waits** for SQL completion before returning

### Key Fix: analysisJson Parsing

DynamoDB stores analysis results inside a JSON string field called `analysisJson`. The Lambda parses this to extract:
- `denialReason` → `denial_code`
- `dollarImpact` → `claim_amount`
- `successProbability` → `success_probability`
- `priorityScore` → `priority_score`
- `expectedRecovery` → `expected_recovery`
- `recoveryOpportunity` → `recovery_opportunity`
- `appealDeadline` → `appeal_deadline`

### Sync Behavior

| Scenario | Result |
|----------|--------|
| New claim added to DynamoDB | Appears in Redshift after next hourly sync |
| Claim deleted from DynamoDB | Removed from Redshift after next hourly sync |
| Claim updated in DynamoDB | Updated in Redshift after next hourly sync |
| Manual sync needed | Invoke Lambda: `aws lambda invoke --function-name denialrecover-dev-data-sync` |

---

## Issues Fixed

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Only 5 of 78 claims synced | DynamoDB scan not paginated | Added `LastEvaluatedKey` pagination loop |
| `permission denied for relation claims` | IAM role lacked table permissions | `GRANT ALL ON TABLE ... TO PUBLIC` |
| Async race condition | TRUNCATE + INSERT ran without waiting | Added `describe_statement` polling loop |
| Empty denial_code/amount fields | Data nested in `analysisJson` string | Parse JSON and extract fields |
| `INSERT has more expressions than target columns` | Table schema mismatch | Dropped and recreated tables with correct 15-column schema |

---

## Useful Queries

### Total recoverable revenue
```sql
SELECT SUM(expected_recovery) as total_recoverable FROM claims;
```

### Top denial reasons by dollar impact
```sql
SELECT denial_code, claim_count, total_amount, avg_success_rate
FROM denial_trends
ORDER BY total_amount DESC;
```

### High-priority claims
```sql
SELECT claim_id, patient_name, claim_amount, success_probability, expected_recovery
FROM claims
WHERE recovery_opportunity = 'HIGH'
ORDER BY expected_recovery DESC;
```

### Claims by status
```sql
SELECT status, COUNT(*) as count, SUM(claim_amount) as total
FROM claims
GROUP BY status;
```

### Recovery summary KPIs
```sql
SELECT * FROM recovery_summary;
```

---

## QuickSight Connection

- **Data Source Type**: Amazon Redshift (Serverless)
- **Workgroup**: `denialrecover-dev-workgroup`
- **Database**: `denialrecover`
- **Credentials**: `admin` / `DenialRecover2024!`
- **Tables to visualize**: `claims`, `denial_trends`, `recovery_summary`

### Recommended Visualizations

1. **KPI** — Total Expected Recovery (SUM of `expected_recovery`)
2. **Bar Chart** — Denial Trends by Code (`denial_code` vs `total_amount`)
3. **Pie Chart** — Claims by Recovery Opportunity (HIGH/MEDIUM/LOW)
4. **Table** — Priority Queue (claims sorted by `expected_recovery` DESC)
5. **Gauge** — Average Success Rate
6. **Line Chart** — Trends over time (when `trend_date` accumulates history)

---

## Lambda Function

- **Name**: `denialrecover-dev-data-sync`
- **Runtime**: Python 3.11
- **Memory**: 512 MB
- **Timeout**: 300 seconds
- **Schedule**: Every 1 hour (EventBridge)
- **Source Code**: `lambda_sync_fixed.py` (in project root)
