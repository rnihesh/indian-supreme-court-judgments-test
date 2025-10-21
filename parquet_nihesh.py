#!/usr/bin/env python3
"""
Manual script to generate parquet files from metadata.zip files in S3
for years 2005-2009 using the existing process_metadata.py code.
"""

import logging
from process_metadata import SupremeCourtS3Processor

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
S3_BUCKET = "indian-supreme-court-judgments-test"
# write for 1950-2004
YEARS_TO_PROCESS = ["1950", "1951", "1952", "1953", "1954", "1955", "1956", "1957", "1958", "1959",
                   "1960", "1961", "1962", "1963", "1964", "1965", "1966", "1967", "1968", "1969",
                   "1970", "1971", "1972", "1973", "1974", "1975", "1976", "1977", "1978", "1979",
                   "1980", "1981", "1982", "1983", "1984", "1985", "1986", "1987", "1988", "1989",
                   "1990", "1991", "1992", "1993", "1994", "1995", "1996", "1997", "1998", "1999",
                   "2000", "2001", "2002", "2003"]  # Strings to match S3 path extraction #


def main():
    """Main function to process metadata.zip files and generate parquet files."""
    logger.info(f"Processing years: {YEARS_TO_PROCESS}")
    logger.info(f"S3 Bucket: {S3_BUCKET}")
    logger.info("")

    processor = SupremeCourtS3Processor(
        s3_bucket=S3_BUCKET,
        s3_prefix="",
        batch_size=10000,
        years_to_process=YEARS_TO_PROCESS,
    )

    processed_years, total_records = processor.process_bucket_metadata()

    if total_records > 0:
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ Processing complete!")
        logger.info(f"Total records processed: {total_records}")
        logger.info(f"Years processed: {processed_years}")
        logger.info("=" * 60)
    else:
        logger.warning("No metadata records were processed to parquet format")


if __name__ == "__main__":
    main()
