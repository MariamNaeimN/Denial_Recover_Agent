# Redshift Serverless - DenialRecover AI Analytics

## Connection Details

| Property | Value |
|----------|-------|
| **Workgroup** | `denialrecover-dev-workgroup` |
| **Database** | `denialrecover` |
| **Admin User** | `admin` |
| **Region** | `us-east-1` |
| **VPC** | `vpc-0f59e6a70abf16538` |
| **Publicly Accessible** | No (internal VPC only) |
| **Base Capacity** | 32 RPU |

---

## Tables

### 1. `claims` (87 rows)

Stores all processed claim data synced from DynamoDB.

```sql
CREATE TABLE IF NOT EXISTS claims (
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
    updated_at VARCHAR(50),
    appeal_pdf_url VARCHAR(500)
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

Aggregated denial patterns by category and payer.

```sql
CREATE TABLE IF NOT EXISTS denial_trends (
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
CREATE TABLE IF NOT EXISTS recovery_summary (
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

### Architecture

```
DynamoDB (claims table)
    │
    ▼ (EventBridge: every 1 hour)
Lambda: denialrecover-dev-data-sync
    │
    ├── Scan all DynamoDB items (paginated)
    ├── Parse analysisJson field
    ├── Extract payer from appeal text (regex)
    ├── Extract patient name from S3 key path
    ├── Build appeal PDF URLs
    │
    ▼
Redshift Serverless (full refresh: TRUNCATE + INSERT)
    │
    ▼
QuickSight (Direct Query — live data)
```

### Sync Lambda Details

- **Name**: `denialrecover-dev-data-sync`
- **Runtime**: Python 3.11
- **Memory**: 512 MB
- **Timeout**: 300 seconds
- **Schedule**: Every 1 hour (EventBridge)
- **Source Code**: `sync_lambda/index.py`

### Data Enrichment

The sync Lambda enriches raw DynamoDB data:

| Field | Source |
|-------|--------|
| `patient_name` | Extracted from S3 key path (e.g., `PAT_john_smith/`) |
| `payer` | Regex from appeal letter text ("Dear [Payer] Appeals") or known payer list |
| `denial_code` | `analysisJson.denialReason` |
| `claim_amount` | `analysisJson.dollarImpact` |
| `success_probability` | `analysisJson.successProbability` |
| `expected_recovery` | `analysisJson.expectedRecovery` |
| `recovery_opportunity` | `analysisJson.recoveryOpportunity` |
| `appeal_pdf_url` | Constructed: `https://{bucket}.s3.us-east-1.amazonaws.com/appeals/{claimId}/appeal_letter.pdf` |

### Sync Behavior

| Scenario | Result |
|----------|--------|
| New claim added to DynamoDB | Appears in Redshift after next hourly sync |
| Claim deleted from DynamoDB | Removed from Redshift after next hourly sync |
| Claim updated in DynamoDB | Updated in Redshift after next hourly sync |
| Manual sync needed | `aws lambda invoke --function-name denialrecover-dev-data-sync --region us-east-1 out.json` |

### SQL Execution

The Lambda builds a single SQL statement containing:
1. `TRUNCATE TABLE claims`
2. Batch `INSERT INTO claims VALUES (...)` (50 rows per statement)
3. `TRUNCATE TABLE denial_trends` + aggregate INSERT
4. `TRUNCATE TABLE recovery_summary` + aggregate INSERT

It uses `redshift-data` API with a polling loop (`describe_statement`) to wait for completion.

---

## Real-time Updates (WebSocket)

In addition to hourly Redshift sync, claim changes are pushed to the dashboard in real-time:

```
DynamoDB Streams (claims table)
    │
    ▼
Lambda: denialrecover-dev-ws-broadcast
    │
    ▼
API Gateway WebSocket → All connected browsers
```

- **WebSocket URL**: `wss://i9ixftt1yb.execute-api.us-east-1.amazonaws.com/prod`
- **Connections Table**: `denialrecover-dev-ws-connections` (DynamoDB, TTL: 24h)
- **Batch Size**: 25 records, 5s batching window

---

## Issues Fixed

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Only 5 of 78 claims synced | DynamoDB scan not paginated | Added `LastEvaluatedKey` pagination loop |
| `permission denied for relation claims` | IAM role lacked table permissions | `GRANT ALL ON TABLE ... TO PUBLIC` |
| Async race condition | TRUNCATE + INSERT ran without waiting | Added `describe_statement` polling loop |
| Empty denial_code/amount fields | Data nested in `analysisJson` string | Parse JSON and extract fields |
| `INSERT has more expressions than target columns` | Table schema mismatch | Added `appeal_pdf_url` column |
| Payer showing "unknown" | Not stored at top level in DynamoDB | Regex extraction from appeal letter text |

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
SELECT claim_id, patient_name, payer, claim_amount, success_probability, expected_recovery
FROM claims
WHERE recovery_opportunity = 'HIGH'
ORDER BY expected_recovery DESC;
```

### Claims by payer
```sql
SELECT payer, COUNT(*) as count, SUM(claim_amount) as total, AVG(success_probability) as avg_rate
FROM claims
GROUP BY payer
ORDER BY total DESC;
```

### Recovery summary KPIs
```sql
SELECT * FROM recovery_summary;
```

### Claims with appeal PDFs
```sql
SELECT claim_id, patient_name, appeal_pdf_url
FROM claims
WHERE appeal_pdf_url IS NOT NULL
ORDER BY expected_recovery DESC;
```

---

## QuickSight Connection

- **Data Source Type**: Amazon Redshift (Serverless)
- **Workgroup**: `denialrecover-dev-workgroup`
- **Database**: `denialrecover`
- **Mode**: Direct Query (live, no SPICE import)
- **Dashboard ID**: `4ce46504-95bf-4ad4-a34d-025e808ee0ea`
- **Public Access**: CloudFront embedded at `https://d32s2hn1a29hfl.cloudfront.net`
- **Embedding Type**: Registered user (`GenerateEmbedUrlForRegisteredUser`)
