from pathlib import Path
import json
import lxml.html as LH
from bs4 import BeautifulSoup
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm
import concurrent.futures
import re
import os
from typing import Dict, List, Any, Optional, Union, Tuple

# Set to True to extract PDF metadata (requires exiftool)
ADD_PDF_METADATA = False

class SupremeCourtMetadataProcessor:
    def __init__(self, src_dir: Union[str, Path], batch_size=5000, output_path="processed_metadata.parquet"):
        """
        Initialize the Supreme Court Metadata Processor
        
        Args:
            src_dir: Source directory containing JSON files with raw_html
            batch_size: Number of records to process before writing a batch
            output_path: Output Parquet file path
        """
        self.src = Path(src_dir)
        self.without_rh = 0
        self.output_path = output_path
        self.record_count = 0
        self.batch_size = batch_size
        
        # For parallel processing
        self.output_dir = Path(os.path.dirname(output_path))
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # Buffer for batch processing
        self.record_buffer = []
        self.schema = None
        self.writer = None

        # Define fields to extract (Supreme Court specific, with removed fields as requested)
        self.all_fields = [
            "title",
            "petitioner",
            "respondent",
            "description",
            "judge",
            "author_judge",
            "citation",
            "case_id",
            "cnr",
            "decision_date",
            "disposal_nature",
            "court",
            "available_languages",
            "raw_html",
            "path",
            "nc_display",
            "scraped_at",
        ]

        if ADD_PDF_METADATA:
            self.all_fields.extend([
                "pdf_exists",
                "size",
                "file_type",
                "mime_type",
                "pdf_version",
                "pdf_linearized",
                "pdf_pages",
                "pdf_producer",
                "pdf_language",
            ])

    def get_metadata_files(self):
        """Find all JSON files in the source directory recursively."""
        for file in self.src.glob("**/*.json"):
            yield file

    def load_metadata(self, file: Union[Path, str]) -> dict:
        """Load JSON metadata from a file."""
        with open(file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def process_metadata(self, metadata: dict) -> Optional[dict]:
        """
        Process raw HTML metadata and extract structured information.
        
        This handles Supreme Court specific format.
        """
        if "raw_html" not in metadata:
            self.without_rh += 1
            return None

        html_s = metadata["raw_html"]
        
        # Use both parsers for maximum flexibility
        html_element = LH.fromstring(html_s)
        soup = BeautifulSoup(html_s, 'html.parser')

        # Initialize case details
        case_details = {
            "raw_html": html_s,
            "path": metadata.get("path", ""),
            "nc_display": metadata.get("nc_display", ""),
            "scraped_at": metadata.get("scraped_at", ""),
        }

        # Extract available languages (as CSV string)
        case_details["available_languages"] = self._extract_languages(soup)
        
        # Extract title, petitioner, respondent
        case_details.update(self._extract_case_title(soup, html_element))
        
        # Extract case description
        description_elem = html_element.xpath("./text()")
        case_details["description"] = description_elem[0].strip() if description_elem else ""
        
        # Extract judges information (with author judge identification)
        case_details.update(self._extract_judges(soup, html_element))
        
        # Extract citation information
        case_details.update(self._extract_citation(soup))
        
        # Extract case details from the caseDetailsTD element
        case_details.update(self._extract_case_details(soup, html_element))
        
        return case_details

    def _extract_languages(self, soup: BeautifulSoup) -> str:
        """Extract available languages from the language selector as CSV string."""
        language_codes = []
        lang_select = soup.select_one('select[id^="language"]')
        
        if not lang_select:
            return ""
            
        for option in lang_select.find_all('option'):
            value = option.get('value', '')
            text = option.text.strip()
            
            # Handle the default language (English) with empty value
            if value == '' and text == 'English':
                language_codes.append('ENG')
            elif value:
                language_codes.append(value)
                
        return ",".join(language_codes)

    def _extract_case_title(self, soup: BeautifulSoup, html_element) -> Dict[str, str]:
        """Extract case title, petitioner and respondent."""
        result = {
            "title": "",
            "petitioner": "",
            "respondent": ""
        }
        
        # Try BeautifulSoup approach first
        title_btn = soup.select_one('button[id^="link_"]')
        if title_btn:
            title_elem = title_btn.find('strong')
            if title_elem:
                full_title = title_elem.get_text().strip()
                result["title"] = full_title
                
                # Try to extract petitioner and respondent
                if 'versus' in full_title.lower():
                    parts = re.split(r'\s+versus\s+', full_title, flags=re.IGNORECASE)
                    if len(parts) >= 2:
                        result["petitioner"] = parts[0].strip()
                        result["respondent"] = parts[1].strip()
                return result
        
        # Fallback to lxml approach if BeautifulSoup didn't find it
        try:
            title = html_element.xpath("./button//text()")[0].strip()
            result["title"] = title
            
            # Try to extract petitioner and respondent
            if 'versus' in title.lower():
                parts = re.split(r'\s+versus\s+', title, flags=re.IGNORECASE)
                if len(parts) >= 2:
                    result["petitioner"] = parts[0].strip()
                    result["respondent"] = parts[1].strip()
        except (IndexError, KeyError):
            pass
            
        return result

    def _extract_judges(self, soup: BeautifulSoup, html_element) -> Dict[str, str]:
        """Extract judges information with author judge identification."""
        result = {
            "judge": "",
            "author_judge": None
        }
        
        # Try BeautifulSoup approach - FIX: changed 'text' to 'string'
        judges_elem = soup.find('strong', string=re.compile(r'Coram\s*:'))
        if judges_elem:
            judges_text = judges_elem.get_text().strip()
            if ':' in judges_text:
                judges_text = judges_text.split(':', 1)[1].strip()
                
            # Clean up judges text and identify author (marked with *)
            judges_list = [j.strip() for j in re.split(r',\s*', judges_text)]
            clean_judges = []
            
            for judge in judges_list:
                clean_judge = re.sub(r'\*$', '', judge)  # Remove asterisk
                clean_judges.append(clean_judge)
                
                # Check if this judge is the author (has asterisk)
                if '*' in judge:
                    result["author_judge"] = clean_judge
            
            result["judge"] = ", ".join(clean_judges)
            return result
        
        # Fallback to lxml approach
        judge_txt = html_element.xpath("./strong/text()")
        if judge_txt:
            if ":" in judge_txt[0]:
                judges_text = judge_txt[0].split(":", 1)[1].strip()
                result["judge"] = judges_text
                
                # Try to identify author judge
                if '*' in judges_text:
                    # Split by comma and look for the one with asterisk
                    judges_list = [j.strip() for j in re.split(r',\s*', judges_text)]
                    for judge in judges_list:
                        if '*' in judge:
                            result["author_judge"] = judge.replace('*', '').strip()
                            break
            else:
                result["judge"] = judge_txt[0].strip()
                
        return result

    def _extract_citation(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract citation information."""
        result = {
            "citation": "",
            "case_id": "",
            "cnr": ""
        }
        
        # Extract standard citation
        citation_elem = soup.select_one('.escrText')
        if citation_elem:
            result["citation"] = citation_elem.get_text().strip()
            
        # Extract case identifier
        nc_display_elem = soup.select_one('.ncDisplay')
        if nc_display_elem:
            result["case_id"] = nc_display_elem.get_text().strip()
            
        # Extract CNR (Case Number Record)
        cnr_input = soup.select_one('input[id="cnr"]')
        if cnr_input and cnr_input.has_attr('value'):
            result["cnr"] = cnr_input['value']
            
        return result

    def _extract_case_details(self, soup: BeautifulSoup, html_element) -> Dict[str, str]:
        """Extract case details like date, case number, disposal nature."""
        result = {
            "decision_date": None,
            "disposal_nature": "",
            "court": ""
        }
        
        # First try with BeautifulSoup for Supreme Court format
        details_elem = soup.find('strong', class_='caseDetailsTD')
        if details_elem:
            # Extract decision date - FIX: changed 'text' to 'string'
            date_span = details_elem.find('span', string=re.compile(r'Decision Date'))
            if date_span and date_span.find_next('font'):
                result["decision_date"] = date_span.find_next('font').get_text().strip()
                
            # Extract disposal nature - FIX: changed 'text' to 'string'
            disposal_span = details_elem.find('span', string=re.compile(r'Disposal Nature'))
            if disposal_span and disposal_span.find_next('font'):
                result["disposal_nature"] = disposal_span.find_next('font').get_text().strip()
                
            # Extract case number - FIX: changed 'text' to 'string'
            case_span = details_elem.find('span', string=re.compile(r'Case No'))
            if case_span and case_span.find_next('font'):
                case_number = case_span.find_next('font').get_text().strip()
                if "Supreme Court" in case_number:
                    result["court"] = "Supreme Court of India"
                else:
                    result["court"] = "Supreme Court of India"  # Default for Supreme Court data
            else:
                result["court"] = "Supreme Court of India"  # Default for Supreme Court data
            
            return result
        
        # Fallback to lxml XPath approach for other formats
        try:
            case_details_elements = html_element.xpath('//strong[@class="caseDetailsTD"]')[0]
            
            try:
                result["decision_date"] = case_details_elements.xpath(
                    './/span[contains(text(), "Decision Date")]/following-sibling::font/text()'
                )[0].strip()
            except (IndexError, KeyError):
                pass

            try:
                result["disposal_nature"] = case_details_elements.xpath(
                    './/span[contains(text(), "Disposal Nature")]/following-sibling::font/text()'
                )[0].strip()
            except (IndexError, KeyError):
                pass

            try:
                result["court"] = (
                    case_details_elements.xpath(
                        './/span[contains(text(), "Court")]/text()'
                    )[0]
                    .split(":")[1]
                    .strip()
                )
            except (IndexError, KeyError):
                result["court"] = "Supreme Court of India"  # Default for Supreme Court data
                
        except (IndexError, KeyError):
            result["court"] = "Supreme Court of India"  # Default for Supreme Court data
            
        return result

    def _add_pdf_metadata(self, processed, pdf_path: Path):
        """Add PDF metadata using exiftool if available."""
        if not ADD_PDF_METADATA:
            return
            
        if not pdf_path.exists():
            processed["pdf_exists"] = False
            return
            
        try:
            import exiftool
            with exiftool.ExifToolHelper() as et:
                pdf_metadata = et.get_metadata(str(pdf_path))
                if len(pdf_metadata) != 1:
                    print(f"Error processing {pdf_path} for exif metadata, count: {len(pdf_metadata)}")
                    return
                    
                pdf_metadata = pdf_metadata[0]
                processed["pdf_exists"] = True
                processed["size"] = pdf_metadata.get("File:FileSize", None)
                processed["file_type"] = pdf_metadata.get("File:FileType", None)
                processed["mime_type"] = pdf_metadata.get("File:MIMEType", None)
                processed["pdf_version"] = pdf_metadata.get("PDF:PDFVersion", None)
                processed["pdf_linearized"] = pdf_metadata.get("PDF:Linearized", None)
                processed["pdf_pages"] = pdf_metadata.get("PDF:PageCount", None)
                processed["pdf_producer"] = pdf_metadata.get("PDF:Producer", None)
                processed["pdf_language"] = pdf_metadata.get("PDF:Language", None)
        except ImportError:
            print("exiftool module not installed. PDF metadata extraction disabled.")
            processed["pdf_exists"] = True

    def process(self):
        """Process all JSON files in the source directory."""
        try:
            for file in tqdm(self.get_metadata_files()):
                try:
                    metadata = self.load_metadata(file)
                    processed = self.process_metadata(metadata)
                    
                    if not processed:
                        print(f"Skipping {file} because it has no raw_html")
                        continue
                        
                    if ADD_PDF_METADATA:
                        pdf_path = file.with_suffix(".pdf")
                        self._add_pdf_metadata(processed, pdf_path)
                        
                    self.add_record(processed)
                    
                except Exception as e:
                    print(f"Error processing {file}: {e}")
        except Exception as e:
            print(f"Error during processing: {e}")
        finally:
            if self.record_buffer:
                self.write_batch()
            if hasattr(self, "writer") and self.writer is not None:
                self.writer.close()
                print(f"Wrote {self.record_count} records to {self.output_path}")

    def add_record(self, record):
        """Add a record to the buffer and write if the buffer is full."""
        if not record:
            return
            
        self.record_buffer.append(record)

        # If buffer reaches batch size, write the batch
        if len(self.record_buffer) >= self.batch_size:
            self.write_batch()

    def write_batch(self):
        """Write the current buffer as a batch to the parquet file."""
        if not self.record_buffer:
            return

        # Ensure all records have all fields (with None for missing values)
        for record in self.record_buffer:
            for field in self.all_fields:
                if field not in record:
                    record[field] = None

        # Convert buffer to pandas DataFrame
        df = pd.DataFrame(self.record_buffer)

        # Ensure DataFrame has all expected columns in the right order
        for field in self.all_fields:
            if field not in df.columns:
                df[field] = None

        # Reorder columns to match expected schema
        df = df[self.all_fields]

        # Define explicit dtypes to ensure consistency across batches
        dtypes = {
            "title": "string",
            "petitioner": "string",
            "respondent": "string",
            "description": "string",
            "judge": "string",
            "author_judge": "string",
            "citation": "string",
            "case_id": "string",
            "cnr": "string",
            "decision_date": "string",        # Handle parsing later if needed
            "disposal_nature": "string",
            "court": "string",
            "available_languages": "string",  # Now a CSV string
            "path": "string",
            "nc_display": "string",
            "scraped_at": "string",
            "pdf_exists": "boolean",
            "size": "Int64",                  # Nullable integer
            "file_type": "string",
            "mime_type": "string",
            "pdf_version": "float64",
            "pdf_linearized": "boolean",
            "pdf_pages": "Int64",
            "pdf_producer": "string",
            "pdf_language": "string",
        }

        # Apply the dtypes to columns that exist
        for col, dtype in dtypes.items():
            if col in df.columns:
                try:
                    df[col] = df[col].astype(dtype)
                except:
                    # If conversion fails, leave as is
                    print(f"Warning: Could not convert {col} to {dtype}")

        # Convert to PyArrow Table
        table = pa.Table.from_pandas(df)

        # Initialize writer if needed
        if self.writer is None:
            self.schema = table.schema
            self.writer = pq.ParquetWriter(
                self.output_path,
                self.schema,
                compression="snappy",
            )

        # Write the batch
        self.writer.write_table(table)

        # Update record count
        self.record_count += len(self.record_buffer)

        # Clear the buffer
        self.record_buffer = []
        
    def process_court_dir(self, court_dir):
        """Process a single court directory and return the output file path."""
        court_name = court_dir.name
        output_file = self.output_dir / f"{court_name}_metadata.parquet"

        processor = SupremeCourtMetadataProcessor(court_dir, batch_size=self.batch_size)
        processor.output_path = output_file
        processor.process()

        return output_file, processor.record_count, processor.without_rh

    def process_parallel(self, max_workers=None):
        """Process all court directories in parallel."""
        court_dirs = [d for d in self.src.glob("court/cnrorders/*") if d.is_dir()]
        
        # If no court directories found, process the entire source directory
        if not court_dirs:
            court_dirs = [self.src]
            print("No court subdirectories found. Processing main directory.")
        else:
            print(f"Found {len(court_dirs)} court directories to process")

        total_records = 0
        total_without_rh = 0
        output_files = []

        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.process_court_dir, court_dir): court_dir.name
                for court_dir in court_dirs
            }

            for future in tqdm(
                concurrent.futures.as_completed(futures),
                total=len(futures),
                desc="Processing courts",
            ):
                court_name = futures[future]
                try:
                    output_file, record_count, without_rh = future.result()
                    output_files.append(output_file)
                    total_records += record_count
                    total_without_rh += without_rh
                    print(
                        f"Completed {court_name}: {record_count} records, {without_rh} without raw_html"
                    )
                except Exception as e:
                    print(f"Error processing {court_name}: {e}")

        if output_files:
            self.combine_parquet_files(output_files)

        print(f"Total records processed: {total_records}")
        print(f"Total records without raw_html: {total_without_rh}")

    def combine_parquet_files(self, file_paths):
        """Combine multiple parquet files into a single file."""
        if not file_paths:
            print("No files to combine")
            return

        print(f"Combining {len(file_paths)} parquet files...")

        # Read and combine all parquet files
        dfs = []
        for file_path in file_paths:
            if isinstance(file_path, Path) and file_path.exists() and file_path.stat().st_size > 0:
                try:
                    df = pd.read_parquet(file_path)
                    dfs.append(df)
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")

        if not dfs:
            print("No valid parquet files to combine")
            return

        combined_df = pd.concat(dfs, ignore_index=True)

        combined_df.to_parquet(self.output_path, compression="snappy")

        print(
            f"Combined {len(dfs)} files with {len(combined_df)} total records to {self.output_path}"
        )


# Utility functions
def process_single_json_file(file_path, output_path=None):
    """Process a single JSON file."""
    if output_path is None:
        output_path = Path(file_path).with_suffix(".parquet")
    
    processor = SupremeCourtMetadataProcessor(
        Path(file_path).parent, 
        batch_size=1, 
        output_path=output_path
    )
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    processed = processor.process_metadata(data)
    if processed:
        processor.add_record(processed)
        processor.write_batch()
    
    return processed


def process_single_json_string(json_string, output_path=None):
    """Process a JSON string."""
    data = json.loads(json_string)
    
    temp_dir = Path("./temp")
    temp_dir.mkdir(exist_ok=True)
    
    temp_file = temp_dir / "temp.json"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    
    result = process_single_json_file(temp_file, output_path)
    
    # Clean up
    if temp_file.exists():
        temp_file.unlink()
    
    return result


if __name__ == "__main__":
    # Example usage
    src_dir = Path("./test_meta_par/")
    processor = SupremeCourtMetadataProcessor(
        src_dir=src_dir,
        batch_size=1000, 
        output_path="./processed_data/supreme_court_metadata.parquet"
    )
    
    # Choose processing mode:
    # 1. Single process mode
    processor.process()