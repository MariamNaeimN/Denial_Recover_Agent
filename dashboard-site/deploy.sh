#!/bin/bash
# Deploy dashboard site to S3 with WebSocket URL injected
# Usage: ./deploy.sh <stack-name> <region>

STACK_NAME=${1:-"denialrecover-dashboard-public-dev"}
REGION=${2:-"us-east-1"}

echo "Fetching stack outputs..."

# Get WebSocket URL from CloudFormation outputs
WS_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='WebSocketUrl'].OutputValue" \
    --output text)

# Get S3 bucket name
BUCKET=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='DashboardSiteBucket'].OutputValue" \
    --output text)

# Get CloudFront distribution ID
CF_DIST=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
    --output text)

echo "WebSocket URL: $WS_URL"
echo "S3 Bucket: $BUCKET"
echo "CloudFront: $CF_DIST"

# Create temp directory for processed files
TEMP_DIR=$(mktemp -d)
cp -r . "$TEMP_DIR/"
rm "$TEMP_DIR/deploy.sh"

# Inject WebSocket URL into index.html
sed -i "s|{{WEBSOCKET_URL}}|$WS_URL|g" "$TEMP_DIR/index.html"

echo "Uploading to S3..."
aws s3 sync "$TEMP_DIR" "s3://$BUCKET/" --delete --region "$REGION"

echo "Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
    --distribution-id "$CF_DIST" \
    --paths "/*" \
    --region "$REGION"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "Dashboard deployed successfully!"
echo "Public URL: https://$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='DashboardPublicUrl'].OutputValue" \
    --output text | sed 's|https://||')"
