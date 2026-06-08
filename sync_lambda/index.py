import os
import json
import boto3
import time
import re
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
redshift_data = boto3.client('redshift-data')

CLAIMS_TABLE = os.environ['CLAIMS_TABLE']
WORKGROUP_NAME = os.environ['WORKGROUP_NAME']
DATABASE_NAME = os.environ['DATABASE_NAME']
BUCKET = 'denialrecover-dev-data-193786182229'

def handler(event, context):
    sync_claims()
    return {'statusCode': 200, 'body': 'Sync completed'}

def sync_claims():
    table = dynamodb.Table(CLAIMS_TABLE)
    all_items = []
    response = table.scan()
    all_items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        all_items.extend(response.get('Items', []))
    print(f"Total items from DynamoDB: {len(all_items)}")

    sqls = ["TRUNCATE TABLE claims"]

    batch_size = 50
    for i in range(0, len(all_items), batch_size):
        batch = all_items[i:i+batch_size]
        values_list = []
        for item in batch:
            analysis = {}
            analysis_json_str = item.get('analysisJson', '')
            if analysis_json_str:
                try:
                    analysis = json.loads(analysis_json_str)
                except:
                    pass

            claim_id = str(item.get('claimId', '')).replace("'", "''")
            patient_id = str(item.get('patientId', '')).replace("'", "''")

            # Extract patient name from sourceDocument path
            patient_name = str(item.get('patientName', '') or '').replace("'", "''")
            if not patient_name:
                source_doc = item.get('sourceDocument', {})
                if isinstance(source_doc, dict):
                    s3_key = source_doc.get('key', '') or ''
                    parts = s3_key.split('/')
                    for part in parts:
                        if part.startswith('PAT') and '_' in part:
                            name_parts = part.split('_')[1:]
                            patient_name = ' '.join(p.capitalize() for p in name_parts).replace("'", "''")
                            break

            # Extract payer
            payer = str(item.get('payer', '') or '').replace("'", "''")
            if not payer or payer == 'unknown' or payer == 'Unknown':
                analysis_text = analysis_json_str or ''
                appeal_text = str(item.get('appealLetterText', '') or '')
                found_payer = ''
                dear_match = re.search(r'Dear\s+(.+?)\s+Appeals', appeal_text)
                if dear_match:
                    payer_candidate = dear_match.group(1).strip()
                    if payer_candidate and len(payer_candidate) < 50:
                        found_payer = payer_candidate
                if not found_payer:
                    payer_names = ['Medicare', 'Medicaid', 'Tricare', 'Cigna', 'Aetna',
                                   'Blue Cross Blue Shield', 'BCBS', 'UnitedHealthcare',
                                   'Humana', 'Kaiser', 'Anthem', 'Molina', 'Centene']
                    for p in payer_names:
                        if p.lower() in analysis_text.lower():
                            found_payer = p
                            break
                payer = found_payer.replace("'", "''") if found_payer else 'Unknown'

            status = str(item.get('status', '')).replace("'", "''")
            claim_amount = float(item.get('claimAmount', 0) or analysis.get('dollarImpact', 0))
            denial_code = str(item.get('denialCode', '') or analysis.get('denialReason', '')).replace("'", "''")
            denial_category = str(item.get('denialCategory', '') or analysis.get('denialReason', '')).replace("'", "''")
            success_prob = int(item.get('successProbability', 0) or analysis.get('successProbability', 0))
            priority = int(item.get('priorityScore', 0) or analysis.get('priorityScore', 0))
            expected_rec = float(item.get('expectedRecovery', 0) or analysis.get('expectedRecovery', 0))
            recovery_opp = str(item.get('recoveryOpportunity', '') or analysis.get('recoveryOpportunity', '')).replace("'", "''")
            appeal_deadline = str(item.get('appealDeadline', '') or analysis.get('appealDeadline', '')).replace("'", "''")
            created = str(item.get('createdAt', '')).replace("'", "''")
            updated = str(item.get('updatedAt', '')).replace("'", "''")
            
            # Build appeal PDF URL
            appeal_pdf_url = f"https://{BUCKET}.s3.us-east-1.amazonaws.com/appeals/{claim_id}/appeal_letter.pdf"

            values_list.append(
                f"('{claim_id}','{patient_id}','{patient_name}','{payer}','{status}',"
                f"{claim_amount},'{denial_code}','{denial_category}',{success_prob},"
                f"{priority},{expected_rec},'{recovery_opp}','{appeal_deadline}',"
                f"'{created}','{updated}','{appeal_pdf_url}')"
            )
        if values_list:
            sqls.append(f"INSERT INTO claims VALUES {','.join(values_list)}")

    # Denial trends
    sqls.append("TRUNCATE TABLE denial_trends")
    sqls.append(
        "INSERT INTO denial_trends "
        "SELECT CURRENT_DATE,payer,denial_code,denial_category,"
        "COUNT(*),SUM(claim_amount),AVG(success_probability) "
        "FROM claims WHERE denial_code != '' "
        "GROUP BY payer,denial_code,denial_category"
    )

    # Recovery summary
    sqls.append("TRUNCATE TABLE recovery_summary")
    sqls.append(
        "INSERT INTO recovery_summary "
        "SELECT CURRENT_DATE,SUM(claim_amount),"
        "SUM(CASE WHEN status='recovered' THEN claim_amount ELSE 0 END),"
        "SUM(expected_recovery),"
        "COUNT(CASE WHEN status='pending' THEN 1 END),"
        "CASE WHEN COUNT(*)>0 THEN AVG(success_probability) ELSE 0 END,"
        "COUNT(CASE WHEN recovery_opportunity='High' OR recovery_opportunity='HIGH' THEN 1 END) "
        "FROM claims"
    )

    full_sql = ";\n".join(sqls) + ";"
    stmt_id = execute_sql_wait(full_sql)
    print(f"Synced {len(all_items)} claims to Redshift. Statement: {stmt_id}")

def execute_sql_wait(sql):
    try:
        response = redshift_data.execute_statement(
            WorkgroupName=WORKGROUP_NAME,
            Database=DATABASE_NAME,
            Sql=sql
        )
        stmt_id = response['Id']
        for _ in range(30):
            time.sleep(2)
            desc = redshift_data.describe_statement(Id=stmt_id)
            status = desc['Status']
            if status == 'FINISHED':
                print(f"SQL completed successfully")
                return stmt_id
            elif status == 'FAILED':
                print(f"SQL FAILED: {desc.get('Error', 'unknown')}")
                return stmt_id
        print(f"SQL timed out, status: {status}")
        return stmt_id
    except Exception as e:
        print(f"SQL Error: {e}")
        return None
