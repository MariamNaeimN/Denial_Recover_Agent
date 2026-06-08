# DenialRecover AI

An intelligent agent system that automates healthcare claim denial analysis, prioritization, and appeal generation using AWS AI/ML services. **Powered by Rackspace.**

## What It Does

DenialRecover AI processes denied medical claims through an automated pipeline that:

1. **Extracts** claim data from uploaded PDFs using Amazon Textract
2. **Identifies** medical entities using Amazon Comprehend Medical
3. **Analyzes** denial reasons and calculates recovery probability using Amazon Bedrock (Claude)
4. **Retrieves** relevant payer policies from OpenSearch (RAG)
5. **Generates** ready-to-submit appeal letters with clinical evidence
6. **Prioritizes** claims by expected recovery value
7. **Generates** professional PDF appeal letters (reportlab)
8. **Visualizes** denial trends and recoverable revenue in a real-time public dashboard

## Architecture

```
SharePoint/S3 Upload
    │
    ▼
S3 Intake Bucket (claims/, eobs/, medical-records/, prior-auths/)
    │
    ▼ (S3 Event Trigger)
Step Functions Pipeline
    │
    ├── Amazon Textract (document extraction)
    ├── Amazon Comprehend Medical (entity extraction)
    ├── Amazon Bedrock - Claude (analysis + RAG)
    ├── Amazon OpenSearch Serverless (payer policy retrieval)
    ├── Appeal PDF Generation (Lambda + reportlab)
    └── Priority Queue (DynamoDB)
    │
    ▼
DynamoDB (claims, priority-queue, denial-analysis)
    │
    ├──▶ (DynamoDB Streams) → WebSocket Broadcast → Dashboard (real-time)
    │
    ▼ (hourly sync)
Amazon Redshift Serverless (analytics)
    │
    ▼
Amazon QuickSight → CloudFront Public Dashboard
```

## Public Dashboard

The dashboard is publicly accessible via CloudFront with real-time WebSocket updates:

- **URL**: `https://d32s2hn1a29hfl.cloudfront.net`
- **Architecture**: S3 Static Site → CloudFront → API Gateway (embed URL) → QuickSight
- **Real-time**: DynamoDB Streams → Lambda → API Gateway WebSocket → Browser
- **Features**: Animated header, live connection status, toast notifications on claim changes

### Dashboard Stack

```
CloudFront Distribution
    ├── S3 Origin (static HTML/CSS/JS)
    ├── API Gateway REST (embed URL generation)
    └── API Gateway WebSocket (real-time push)
            ├── $connect → Lambda (store connection)
            ├── $disconnect → Lambda (remove connection)
            └── DynamoDB Stream → Lambda (broadcast updates)
```

## AWS Services Used

| Service | Purpose |
|---------|---------|
| Amazon S3 | Document storage + dashboard static site |
| Amazon CloudFront | Public dashboard CDN distribution |
| Amazon Textract | Async document text extraction from PDFs |
| Amazon Comprehend Medical | Medical entity extraction (diagnoses, procedures, medications) |
| Amazon Bedrock (Claude Sonnet 4.5) | Denial analysis, recovery scoring, appeal letter generation |
| Amazon OpenSearch Serverless | Payer policy knowledge base (RAG) |
| AWS Step Functions | Pipeline orchestration |
| AWS Lambda | Processing logic (15+ functions) |
| Amazon DynamoDB | Claims data, priority queue, denial analysis, WebSocket connections |
| Amazon Redshift Serverless | Analytics and trend aggregation |
| Amazon QuickSight | Revenue recovery dashboard (embedded) |
| Amazon EventBridge | Scheduled sync (hourly) |
| AWS API Gateway (REST) | SharePoint integration + embed URL endpoint |
| AWS API Gateway (WebSocket) | Real-time dashboard updates |

## Pipeline Flow

```
1. Upload claim PDF to S3 intake/claims/
2. S3 trigger fires → Step Functions starts
3. Wait 30 seconds (batch upload window)
4. List related files (EOBs, medical records, prior auths for same patient)
5. Textract extracts text from ALL related documents (parallel)
6. Merge Textract results
7. Comprehend Medical extracts clinical entities
8. Bedrock (Claude) analyzes denial:
   - Classifies denial reason (CODING_ERROR, AUTH_REQUIRED, etc.)
   - Calculates success probability (0-100%)
   - Computes expected recovery (amount × probability)
   - Identifies missing documentation
   - Recommends actions
   - Retrieves payer policies from OpenSearch (RAG)
9. Bedrock (Claude) generates appeal letter
10. Lambda generates professional PDF (reportlab)
11. Save to DynamoDB (claims + priority queue)
12. DynamoDB Stream → WebSocket broadcast (instant dashboard update)
13. Hourly sync to Redshift → QuickSight dataset refreshes
```

## Project Structure

```
DenialRecover AI/
├── cloudformation/
│   ├── denialrecover-Data-stack.yaml              # DynamoDB tables + S3 + SQS
│   ├── denialrecover-agent-stack.yaml             # OpenSearch + Bedrock roles
│   ├── denialrecover-processing-stack.yaml        # Pipeline (Lambdas + Step Functions)
│   ├── denialrecover-analytics-stack.yaml         # Redshift Serverless + sync Lambda
│   ├── denialrecover-sharepoint-sync-stack.yaml   # API Gateway for Power Automate
│   └── denialrecover-dashboard-public-stack.yaml  # CloudFront + WebSocket + public dashboard
├── dashboard-site/
│   ├── index.html                                 # Public dashboard page (animated)
│   ├── error.html                                 # 404 page
│   └── deploy.sh                                  # Deploy script (injects WebSocket URL)
├── pdf_lambda/
│   └── index.py                                   # Appeal letter PDF generator (reportlab)
├── sync_lambda/
│   └── index.py                                   # Enhanced DynamoDB → Redshift sync
├── lambda-layers/
│   └── opensearch-layer/                          # OpenSearch Python client layer
├── MVP_FLOW/
│   └── SAMPLE_DATA/SharePoint_Upload/intake/      # Sample claim documents
├── REDSHIFT_SETUP.md                              # Redshift configuration & schema
├── QUICKSIGHT_DASHBOARD_GUIDE.md                  # Dashboard chart-by-chart guide
└── README.md                                      # This file
```

## Deployment

### Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.11+ (for sample data generation)
- reportlab Python package (`pip install reportlab`)

### Deploy Stacks (in order)

```bash
# 1. Data layer (S3 + DynamoDB + SQS)
aws cloudformation deploy --template-file cloudformation/denialrecover-Data-stack.yaml \
  --stack-name denialrecover-dev --capabilities CAPABILITY_NAMED_IAM

# 2. Agent layer (OpenSearch + Bedrock roles)
aws cloudformation deploy --template-file cloudformation/denialrecover-agent-stack.yaml \
  --stack-name denialrecover-agent-dev --capabilities CAPABILITY_NAMED_IAM

# 3. Processing pipeline (Lambdas + Step Functions)
aws cloudformation deploy --template-file cloudformation/denialrecover-processing-stack.yaml \
  --stack-name denialrecover-processing-dev --capabilities CAPABILITY_NAMED_IAM \
  --s3-bucket denialrecover-dev-data-193786182229 --s3-prefix cfn-deploy

# 4. Analytics (Redshift + sync)
aws cloudformation deploy --template-file cloudformation/denialrecover-analytics-stack.yaml \
  --stack-name denialrecover-dev-analytics --capabilities CAPABILITY_NAMED_IAM

# 5. SharePoint sync (API Gateway)
aws cloudformation deploy --template-file cloudformation/denialrecover-sharepoint-sync-stack.yaml \
  --stack-name denialrecover-sharepoint-sync-dev --capabilities CAPABILITY_NAMED_IAM

# 6. Public Dashboard (CloudFront + WebSocket)
aws cloudformation deploy --template-file cloudformation/denialrecover-dashboard-public-stack.yaml \
  --stack-name denialrecover-dashboard-public-dev --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides QuickSightDashboardId=4ce46504-95bf-4ad4-a34d-025e808ee0ea
```

### Deploy Dashboard Site

```bash
cd dashboard-site
bash deploy.sh denialrecover-dashboard-public-dev us-east-1
```

### Generate Sample Data

```bash
pip install reportlab
python generate_all_docs.py
```

### Upload Claims to S3

```bash
aws s3 sync MVP_FLOW/SAMPLE_DATA/SharePoint_Upload/intake \
  s3://denialrecover-dev-data-193786182229/intake/ --region us-east-1
```

### Manual Redshift Sync

```bash
aws lambda invoke --function-name denialrecover-dev-data-sync --region us-east-1 output.json
```

## Key Features

### Real-time Dashboard
- WebSocket connection broadcasts claim updates instantly
- DynamoDB Streams trigger Lambda which pushes to all connected browsers
- Toast notifications for new/updated/removed claims
- Auto-reconnect with exponential backoff (max 10 retries)
- Connection status indicator (Live / Connecting / Offline)

### Anti-Hallucination
- All analysis is based ONLY on extracted document text
- Appeal letters cite only facts from Textract/Comprehend output
- Payer policies referenced only from OpenSearch RAG retrieval
- If data is unavailable, the system says "Unknown" rather than inventing

### RAG (Retrieval Augmented Generation)
- Payer policies indexed in OpenSearch Serverless
- Semantic search using Amazon Titan Embeddings (1536 dimensions)
- Retrieved policies augment the Claude prompt for accurate analysis
- ~4KB of relevant policy context per claim

### Priority Scoring
```
Expected Recovery = Claim Amount × (Success Probability / 100)

Recovery Opportunity:
  HIGH:   probability >= 75% OR expected_recovery > $50K
  MEDIUM: probability 40-74%
  LOW:    probability < 40%
```

### Appeal Letter PDF Generation
- Professional formatting with reportlab (headers, sections, bullet points)
- Smart text parsing (detects headers, key:value pairs, lists)
- Markdown/Unicode cleanup
- Falls back to .txt if PDF generation fails
- Saved to S3: `appeals/{claimId}/appeal_letter.pdf`

## Dashboard (QuickSight via CloudFront)

| Feature | Details |
|---------|---------|
| **Public URL** | `https://d32s2hn1a29hfl.cloudfront.net` |
| **Embedding** | Registered user embed (no capacity pricing required) |
| **Data Mode** | Direct Query to Redshift (live data) |
| **Real-time** | WebSocket push on DynamoDB changes |
| **WebSocket** | `wss://i9ixftt1yb.execute-api.us-east-1.amazonaws.com/prod` |

### Dashboard Visualizations
- Total recoverable revenue (KPI)
- Total denied amount (KPI)
- Average success probability (KPI)
- High priority claims count (KPI)
- Denial reasons by dollar impact (bar chart)
- Recovery opportunity distribution (donut)
- Expected recovery by denial type (stacked bar)
- Claims by payer (horizontal bar)
- Success probability by denial type (bar)
- Priority queue table (actionable work queue)
- Denial trend summary (table)
- Recovery opportunity treemap

## Configuration

| Parameter | Value |
|-----------|-------|
| Region | us-east-1 |
| S3 Bucket | denialrecover-dev-data-193786182229 |
| Bedrock Model | us.anthropic.claude-sonnet-4-5-20250929-v1:0 |
| Embedding Model | amazon.titan-embed-text-v1 (1536 dims) |
| OpenSearch Collection | denialrecover-dev-kb |
| Redshift Workgroup | denialrecover-dev-workgroup |
| Redshift Database | denialrecover |
| State Machine | denialrecover-dev-full-pipeline |
| Sync Schedule | Every 1 hour (EventBridge) |
| Dashboard CloudFront | d32s2hn1a29hfl.cloudfront.net |
| WebSocket API | i9ixftt1yb.execute-api.us-east-1.amazonaws.com |
| QuickSight Dashboard ID | 4ce46504-95bf-4ad4-a34d-025e808ee0ea |

## Demo Workflow

1. Open public dashboard: `https://d32s2hn1a29hfl.cloudfront.net`
2. Upload denied claim PDFs to S3 `intake/claims/`
3. Pipeline automatically processes (2-3 min per claim)
4. Toast notification appears in real-time on the dashboard
5. View results in DynamoDB or download appeal PDFs from S3 `appeals/`
6. Dashboard charts update after hourly Redshift sync (or trigger manually)
7. Appeal PDFs are ready to submit to payers

## Cost Estimate (Dev/Demo)

| Service | Estimated Monthly Cost |
|---------|----------------------|
| Bedrock (Claude) | ~$5-15 (per 100 claims) |
| Textract | ~$1.50 (per 100 pages) |
| Comprehend Medical | ~$1 (per 100 documents) |
| OpenSearch Serverless | ~$25 (2 OCU minimum) |
| Redshift Serverless | ~$10-20 (32 RPU, on-demand) |
| DynamoDB | ~$1 (on-demand) |
| Lambda | ~$0.50 |
| Step Functions | ~$0.50 |
| S3 + CloudFront | ~$1 |
| API Gateway (REST + WebSocket) | ~$0.50 |
| QuickSight | $18/author or $5/reader |
| **Total** | **~$65-95/month** |
