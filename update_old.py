import json
import boto3
import logging
from pathlib import Path
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

S3_BUCKET = "indian-supreme-court-judgments-test"

def format_file_size(size_bytes):
    """Convert bytes to a human-readable format"""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    unit_index = 0

    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.2f} {units[unit_index]}"

def update_index_with_zip_size(s3, bucket, year, archive_type):
    """Update a single index file with zip size information"""
    
    # Paths for zip and index files
    if archive_type == "metadata":
        s3_dir = f"metadata/zip/year={year}/"
    else:
        s3_dir = f"data/zip/year={year}/"
    
    zip_key = f"{s3_dir}{archive_type}.zip"
    index_key = f"{s3_dir}{archive_type}.index.json"
    
    try:
        # Check if zip file exists
        zip_response = s3.head_object(Bucket=bucket, Key=zip_key)
        zip_size = zip_response['ContentLength']
        
        # Download current index
        try:
            index_response = s3.get_object(Bucket=bucket, Key=index_key)
            index_data = json.loads(index_response['Body'].read().decode('utf-8'))
        except s3.exceptions.ClientError as e:
            if "NoSuchKey" in str(e):
                logger.warning(f"Index file not found: {index_key}, creating new one")
                index_data = {
                    "files": [],
                    "file_count": 0,
                    "created_at": datetime.now().isoformat(),
                }
            else:
                raise
        
        # Check if zip_size already exists
        if "zip_size" in index_data:
            logger.info(f"Zip size already exists for {year}/{archive_type}, skipping")
            return False
        
        # Add zip size information
        index_data["zip_size"] = zip_size
        index_data["zip_size_human"] = format_file_size(zip_size)
        # index_data["updated_at"] = datetime.now().isoformat()
        
        # Upload updated index
        s3.put_object(
            Bucket=bucket,
            Key=index_key,
            Body=json.dumps(index_data, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Updated {year}/{archive_type}: {index_data['zip_size_human']}")
        return True
        
    except s3.exceptions.ClientError as e:
        if "NoSuchKey" in str(e):
            logger.warning(f"Zip file not found: {zip_key}, skipping")
            return False
        else:
            logger.error(f"Error processing {year}/{archive_type}: {e}")
            return False

def main():
    """Update all index files from 1950-2024 with zip size information"""
    
    s3 = boto3.client('s3')
    
    # Archive types to process
    archive_types = ["metadata", "english", "regional"]
    
    updated_count = 0
    total_count = 0
    
    # Process years 1950-2024
    for year in range(1950, 2025):
        logger.info(f"Processing year {year}...")
        
        for archive_type in archive_types:
            total_count += 1
            
            try:
                if update_index_with_zip_size(s3, S3_BUCKET, year, archive_type):
                    updated_count += 1
            except Exception as e:
                logger.error(f"Failed to process {year}/{archive_type}: {e}")
    
    logger.info(f"Update complete: {updated_count}/{total_count} index files updated")

if __name__ == "__main__":
    main()