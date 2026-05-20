# DenialRecover AI

An intelligent agent system that automates healthcare claim denial analysis, prioritization, and appeal generation using AWS AI/ML services.

## What It Does

DenialRecover AI processes denied medical claims through an automated pipeline that:

1. **Extracts** claim data from uploaded PDFs using Amazon Textract
2. **Identifies** medical entities using Amazon Comprehend Medical
3. **Analyzes** denial reasons and calculates recovery probability using Amazon Bedrock (Claude)
4. **Retrieves** relevant payer policies from OpenSearch (RAG)
5. **Generates** ready-to-submit appeal letters with clinical evidence
6. **Prioritizes** claims by expected recovery value
7. **Visualizes** denial trends and recoverable revenue in QuickSight

## Architecture

```
SharePoint/S3 Upload
    |
    v
S3 Intake Bucket (claims/, eobs/, medical-records/, prior-auths/)
    |
    v (S3 Event Trigger)
Step Functions Pipeline
    |
    ├── Amazon Textract (document extraction)
    ├── Amazon Comprehend Medical (entity extraction)
    ├── Amazon Bedrock - Claude (analysis + RAG)
    ├── Amazon OpenSearch Serverless (payer policy retrieval)
    ├── Appeal PDF Generation (Lambda)
    └── Priority Queue (DynamoDB)
    |
    v
DynamoDB (claims, priority-queue, denial-analysis)
    |
    v (hourly sync)
Amazon Redshift Serverless (analytics)
    |
    v
Amazon QuickSight (dashboard)
```

## AWS Services Used

| Service | Purpose |
|---------|---------|
| Amazon S3 | Document storage (claims, EOBs, medical records, prior auths, appeals) |
| Amazon Textract | Async document text extraction from PDFs |
| Amazon Comprehend Medical | Medical entity extraction (diagnoses, procedures, medications) |
| Amazon Bedrock (Claude Sonnet 4.5) | Denial analysis, recovery scoring, appeal letter generation |
| Amazon OpenSearch Serverless | Payer policy knowledge base (RAG) |
| AWS Step Functions | Pipeline orchestration |
| AWS Lambda | Processing logic (12 functions) |
| Amazon DynamoDB | Claims data, priority queue, denial analysis |
| Amazon Redshift Serverless | Analytics and trend aggregation |
| Amazon QuickSight | Revenue recovery dashboard |
| Amazon EventBridge | Scheduled sync (hourly) |
| AWS API Gateway | SharePoint integration endpoint |

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
   - Computes expected recovery (amount x probability)
   - Identifies missing documentation
   - Recommends actions
   - Retrieves payer policies from OpenSearch (RAG)
9. Bedrock (Claude) generates appeal letter
10. Lambda generates professional PDF
11. Save to DynamoDB (claims + priority queue)
12. Hourly sync to Redshift → QuickSight dashboard updates
```

## Project Structure

```
DenialRecover AI/
├── cloudformation/
│   ├── denialrecover-processing-stack.yaml    # Main pipeline (Lambdas + Step Functions)
│   ├── denialrecover-agent-stack.yaml         # OpenSearch + Bedrock roles
│   ├── denialrecover-Data-stack.yaml          # DynamoDB tables + S3 bucket
│   ├── denialrecover-analytics-stack.yaml     # Redshift Serverless + sync Lambda
│   └── denialrecover-sharepoint-sync-stack.yaml # API Gateway for Power Automate
├── lambda-layers/
│   └── opensearch-layer/                      # OpenSearch Python client layer
├── MVP_FLOW/
│   └── SAMPLE_DATA/
│       └── SharePoint_Upload/
│           └── intake/
│               ├── claims/                    # Denied claim PDFs
│               ├── eobs/                      # Explanation of Benefits
│               ├── medical-records/           # Medical records
│               └── prior-auths/              # Prior authorizations
├── generate_all_docs.py                       # Generate consistent sample data
├── clear_and_upload.py                        # Clear DB and re-upload claims
├── lambda_sync_fixed.py                       # Redshift sync Lambda code
├── REDSHIFT_SETUP.md                          # Redshift configuration details
├── QUICKSIGHT_DASHBOARD_GUIDE.md              # Dashboard chart guide
└── README.md                                  # This file
```

## Deployment

### Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.11+ (for sample data generation)
- reportlab Python package (`pip install reportlab`)

### Deploy Stacks (in order)

```bash
# 1. Data layer (S3 + DynamoDB)
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
```

### Generate Sample Data

```bash
pip install reportlab
python generate_all_docs.py
```

### Upload Claims to S3

```bash
# Upload all documents (claims trigger the pipeline automatically)
aws s3 sync MVP_FLOW/SAMPLE_DATA/SharePoint_Upload/intake \
  s3://denialrecover-dev-data-193786182229/intake/ --region us-east-1
```

### Manual Redshift Sync

```bash
aws lambda invoke --function-name denialrecover-dev-data-sync --region us-east-1 output.json
```

## Key Features

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
Expected Recovery = Claim Amount x (Success Probability / 100)

Recovery Opportunity:
  HIGH:   probability >= 75% OR expected_recovery > $50K
  MEDIUM: probability 40-74%
  LOW:    probability < 40%
```

### Appeal Letter Structure
1. Header (Date, To, RE, Amount)
2. Patient Information
3. Insurance Information
4. Denial Details
5. Introduction and Appeal Statement
6. Clinical Summary
7. Medical Necessity Justification
8. Coding and Billing Analysis
9. Financial Impact
10. Request for Reconsideration
11. Submission and Deadline
12. Closing

## Dashboard (QuickSight)

The dashboard shows:
- Total recoverable revenue
- Denial trends by category and payer
- Expected revenue impact
- Priority queue (claims ranked by recovery value)
- Payer-specific analysis

Connection: Direct Query to Redshift Serverless (live data, no refresh needed)

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

## Demo Workflow

1. Upload denied claim PDFs to S3 `intake/claims/`
2. Pipeline automatically processes (2-3 min per claim)
3. View results in DynamoDB or download appeal PDFs from S3 `appeals/`
4. Dashboard updates after hourly Redshift sync (or trigger manually)
5. Appeal PDFs are ready to submit to payers

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
| S3 | ~$0.50 |
| QuickSight | $18/author or $5/reader |
| **Total** | **~$65-90/month** |
