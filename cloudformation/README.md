# CloudFormation Stacks — DenialRecover AI

## Overview

This directory contains all AWS CloudFormation templates for the DenialRecover AI platform. Stacks must be deployed in order due to cross-stack references (exports/imports).

---

## Stack Dependency Graph

```
┌─────────────────────────────────┐
│  1. denialrecover-Data-stack    │  ← Foundation (S3, DynamoDB, SQS, KMS)
└──────────────┬──────────────────┘
               │ exports: bucket ARNs, table ARNs, queue ARNs, KMS key
               ▼
┌──────────────────────────────────────────────────────────────┐
│  2. denialrecover-agent-stack         │  3. denialrecover-   │
│     (OpenSearch, Bedrock roles)       │     analytics-stack  │
│                                       │     (Redshift, Sync) │
└──────────────┬────────────────────────┴──────────────────────┘
               │ exports: OpenSearch ARN, Bedrock role
               ▼
┌─────────────────────────────────────────┐
│  4. denialrecover-processing-stack      │  ← Main pipeline (Step Functions + Lambdas)
└──────────────┬──────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  5. denialrecover-sharepoint-sync-stack │  6. denialrecover- │
│     (API GW for Power Automate)        │     dashboard-      │
│                                        │     public-stack    │
│                                        │     (CloudFront +   │
│                                        │      WebSocket)     │
└────────────────────────────────────────┴─────────────────────┘
```

---

## Stacks

### 1. `denialrecover-Data-stack.yaml`

**Stack Name:** `denialrecover-dev`

Foundation layer — all data storage resources.

| Resource | Type | Purpose |
|----------|------|---------|
| KMS Key | `AWS::KMS::Key` | Encryption for S3, DynamoDB, SQS |
| DataBucket | `AWS::S3::Bucket` | Document storage (intake, processed, appeals) |
| PayerRulesBucket | `AWS::S3::Bucket` | Payer policy documents for RAG |
| ClaimsTable | `AWS::DynamoDB::Table` | Main claims data (streams enabled) |
| DenialAnalysisTable | `AWS::DynamoDB::Table` | Analysis results per claim |
| PriorityQueueTable | `AWS::DynamoDB::Table` | Claims ranked by recovery value |
| AppealOutcomesTable | `AWS::DynamoDB::Table` | Appeal results tracking |
| CompaniesTable | `AWS::DynamoDB::Table` | Multi-tenant support |
| ClaimsProcessingQueue | `AWS::SQS::Queue` | Batch processing queue |
| HighPriorityClaimsQueue | `AWS::SQS::Queue` | Urgent claims (deadline approaching) |
| ClaimsDeadLetterQueue | `AWS::SQS::Queue` | Failed message retention |

**Key Exports:** `DataBucketArn`, `ClaimsTableArn`, `ClaimsTableStreamArn`, `KMSKey`

---

### 2. `denialrecover-agent-stack.yaml`

**Stack Name:** `denialrecover-agent-dev`

AI/ML layer — OpenSearch for RAG and Bedrock access roles.

| Resource | Type | Purpose |
|----------|------|---------|
| OpenSearch Collection | Serverless | Payer policy knowledge base (vector search) |
| Bedrock IAM Role | `AWS::IAM::Role` | Invoke Claude + Titan Embeddings |
| OpenSearch Access Policy | Collection policy | Lambda access to vector index |
| Encryption Policy | Collection policy | At-rest encryption |
| Network Policy | Collection policy | VPC/public access rules |

**Key Exports:** `OpenSearchEndpoint`, `BedrockRoleArn`

---

### 3. `denialrecover-processing-stack.yaml`

**Stack Name:** `denialrecover-processing-dev`

Main pipeline — Step Functions orchestrating all processing Lambdas.

| Resource | Type | Purpose |
|----------|------|---------|
| Step Functions State Machine | `AWS::StepFunctions::StateMachine` | Full pipeline orchestration |
| S3 Trigger Lambda | `AWS::Lambda::Function` | Starts pipeline on S3 upload |
| Wait & List Lambda | `AWS::Lambda::Function` | Batch window + find related docs |
| Textract Lambda | `AWS::Lambda::Function` | Start async document extraction |
| Textract Result Lambda | `AWS::Lambda::Function` | Retrieve extraction results |
| Merge Textract Lambda | `AWS::Lambda::Function` | Combine multi-document results |
| Comprehend Medical Lambda | `AWS::Lambda::Function` | Extract clinical entities |
| Bedrock Analysis Lambda | `AWS::Lambda::Function` | Denial analysis + RAG |
| Appeal Generator Lambda | `AWS::Lambda::Function` | Generate appeal letter text |
| PDF Generator Lambda | `AWS::Lambda::Function` | Create professional PDF |
| Save Results Lambda | `AWS::Lambda::Function` | Write to DynamoDB |
| OpenSearch Layer | `AWS::Lambda::LayerVersion` | opensearch-py client |

**Key Exports:** `StateMachineArn`

---

### 4. `denialrecover-analytics-stack.yaml`

**Stack Name:** `denialrecover-dev-analytics`

Analytics layer — Redshift Serverless for QuickSight.

| Resource | Type | Purpose |
|----------|------|---------|
| Redshift Namespace | `AWS::RedshiftServerless::Namespace` | Database container |
| Redshift Workgroup | `AWS::RedshiftServerless::Workgroup` | Compute (32 RPU base) |
| Private Subnets (2,3) | `AWS::EC2::Subnet` | Redshift needs 3 AZs |
| Security Group | `AWS::EC2::SecurityGroup` | Port 5439 within VPC |
| Data Sync Lambda | `AWS::Lambda::Function` | DynamoDB → Redshift hourly sync |
| EventBridge Schedule | `AWS::Events::Rule` | Trigger sync every 1 hour |
| Redshift IAM Role | `AWS::IAM::Role` | S3 + DynamoDB read access |

**Key Exports:** `RedshiftEndpoint`, `RedshiftWorkgroup`

---

### 5. `denialrecover-sharepoint-sync-stack.yaml`

**Stack Name:** `denialrecover-sharepoint-sync-dev`

Integration layer — REST API for Power Automate / SharePoint.

| Resource | Type | Purpose |
|----------|------|---------|
| API Gateway (REST) | `AWS::ApiGateway::RestApi` | Receive uploads from Power Automate |
| Upload Lambda | `AWS::Lambda::Function` | Process incoming documents |
| API Key + Usage Plan | `AWS::ApiGateway::ApiKey` | Authentication |

---

### 6. `denialrecover-dashboard-public-stack.yaml`

**Stack Name:** `denialrecover-dashboard-public-dev`

Public dashboard — CloudFront-hosted with real-time WebSocket.

| Resource | Type | Purpose |
|----------|------|---------|
| S3 Bucket | `AWS::S3::Bucket` | Static site (index.html) |
| CloudFront Distribution | `AWS::CloudFront::Distribution` | CDN + HTTPS |
| Origin Access Control | `AWS::CloudFront::OriginAccessControl` | Secure S3 access |
| API Gateway (REST) | `AWS::ApiGateway::RestApi` | Embed URL generation endpoint |
| Embed URL Lambda | `AWS::Lambda::Function` | QuickSight `GenerateEmbedUrlForRegisteredUser` |
| WebSocket API | `AWS::ApiGatewayV2::Api` | Real-time push to browsers |
| WS Connect Lambda | `AWS::Lambda::Function` | Store connection ID |
| WS Disconnect Lambda | `AWS::Lambda::Function` | Remove connection ID |
| WS Default Lambda | `AWS::Lambda::Function` | Ping/pong heartbeat |
| WS Broadcast Lambda | `AWS::Lambda::Function` | Push DynamoDB changes to clients |
| Connections Table | `AWS::DynamoDB::Table` | Track active WebSocket clients |
| DynamoDB Stream Mapping | `AWS::Lambda::EventSourceMapping` | Claims stream → broadcast |

**Key Exports:** `DashboardPublicUrl`, `WebSocketUrl`

---

## Deployment Commands

```bash
# 1. Data layer
aws cloudformation deploy \
  --template-file denialrecover-Data-stack.yaml \
  --stack-name denialrecover-dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 2. Agent layer
aws cloudformation deploy \
  --template-file denialrecover-agent-stack.yaml \
  --stack-name denialrecover-agent-dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 3. Processing pipeline
aws cloudformation deploy \
  --template-file denialrecover-processing-stack.yaml \
  --stack-name denialrecover-processing-dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --s3-bucket denialrecover-dev-data-193786182229 \
  --s3-prefix cfn-deploy \
  --region us-east-1

# 4. Analytics
aws cloudformation deploy \
  --template-file denialrecover-analytics-stack.yaml \
  --stack-name denialrecover-dev-analytics \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 5. SharePoint sync
aws cloudformation deploy \
  --template-file denialrecover-sharepoint-sync-stack.yaml \
  --stack-name denialrecover-sharepoint-sync-dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 6. Public dashboard
aws cloudformation deploy \
  --template-file denialrecover-dashboard-public-stack.yaml \
  --stack-name denialrecover-dashboard-public-dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides QuickSightDashboardId=4ce46504-95bf-4ad4-a34d-025e808ee0ea \
  --region us-east-1
```

---

## Parameters

### Common Parameters (all stacks)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `Environment` | `dev` | Environment name (dev/uat/prod) |
| `ProjectName` | `denialrecover` | Prefix for all resource names |

### Stack-specific Parameters

| Stack | Parameter | Default | Description |
|-------|-----------|---------|-------------|
| Data | — | — | No additional params |
| Agent | `DataStackName` | `denialrecover-dev` | Cross-stack import |
| Processing | `DataStackName` | `denialrecover-dev` | Cross-stack import |
| Processing | `AgentStackName` | `denialrecover-agent-dev` | Cross-stack import |
| Analytics | `DataStackName` | `denialrecover-dev` | Cross-stack import |
| Analytics | `AdminPassword` | — | Redshift admin password |
| Dashboard | `QuickSightDashboardId` | — | Dashboard to embed |
| Dashboard | `DataStackName` | `denialrecover-dev` | For DynamoDB stream ARN |

---

## Useful Commands

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name denialrecover-dev --query "Stacks[0].StackStatus"

# View stack outputs
aws cloudformation describe-stacks --stack-name denialrecover-dev --query "Stacks[0].Outputs" --output table

# Delete stack (caution: destroys resources)
aws cloudformation delete-stack --stack-name denialrecover-dashboard-public-dev

# Validate template
aws cloudformation validate-template --template-body file://denialrecover-Data-stack.yaml
```

---

## Resource Counts

| Stack | Resources | Lambdas | IAM Roles |
|-------|-----------|---------|-----------|
| Data | 14 | 0 | 0 |
| Agent | 7 | 0 | 2 |
| Processing | 28 | 10 | 3 |
| Analytics | 9 | 1 | 2 |
| SharePoint | 12 | 1 | 1 |
| Dashboard | 22 | 5 | 3 |
| **Total** | **92** | **17** | **11** |
