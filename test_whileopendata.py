import boto3
import json
from botocore import UNSIGNED
from botocore.client import Config

# Create an S3 client without requiring AWS credentials
s3_client = boto3.client('s3', config=Config(signature_version=UNSIGNED))

# List all files in the data directory
response = s3_client.list_objects_v2(
    Bucket='indian-supreme-court-judgments',
    Prefix='data/'
)

# Find all index.json files and count judgments
total_judgments = 0
judgment_counts = {}

for obj in response['Contents']:
    key = obj['Key']
    if key.endswith('.index.json'):
        try:
            # Download and read each index file
            obj_data = s3_client.get_object(
                Bucket='indian-supreme-court-judgments', 
                Key=key
            )
            index_content = json.loads(obj_data['Body'].read().decode('utf-8'))
            
            # Get file count from the index
            file_count = index_content.get('file_count', 0)
            total_judgments += file_count
            
            # Store counts by archive type and year
            archive_name = key.replace('data/', '').replace('.index.json', '')
            judgment_counts[archive_name] = file_count
            
            print(f"{archive_name}: {file_count} files")
            
        except Exception as e:
            print(f"Error reading {key}: {e}")

print(f"\n--- SUMMARY ---")
print(f"Total judgment files across all archives: {total_judgments}")

# Show breakdown by type
english_total = sum(count for name, count in judgment_counts.items() if 'english' in name)
metadata_total = sum(count for name, count in judgment_counts.items() if 'metadata' in name)
regional_total = sum(count for name, count in judgment_counts.items() if 'regional' in name)

print(f"\nBreakdown by type:")
print(f"English judgments: {english_total}")
print(f"Metadata files: {metadata_total}")
print(f"Regional judgments: {regional_total}")

# Show breakdown by year
years = set()
for name in judgment_counts.keys():
    year_match = name.split('-')[2] if len(name.split('-')) > 2 else None
    if year_match and year_match.isdigit():
        years.add(year_match)

print(f"\nBreakdown by year:")
for year in sorted(years):
    year_total = sum(count for name, count in judgment_counts.items() if year in name)
    print(f"Year {year}: {year_total} files")