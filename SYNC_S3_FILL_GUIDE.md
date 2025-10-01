# 📦 5-Year Chunk Gap Filling Guide

## Overview

The `--sync-s3-fill` mode has been redesigned to process data in **5-year chunks** with **immediate uploads** after each year. This prevents data loss and avoids the 6-hour timeout limit.

## ✨ Key Features

### 1. **5-Year Chunks**

- Each run processes ONE 5-year chunk (e.g., 1950-1954, 1955-1959, etc.)
- Automatically determines the next chunk based on progress
- Run the same command repeatedly to process all chunks

### 2. **Immediate Year-by-Year Upload**

- Data is uploaded to S3 **immediately** after each year completes
- No waiting until the end of the run
- **Data is safe** even if the process is interrupted

### 3. **No Duplicate Uploads on Interruption**

- Pressing Ctrl+C does **NOT** trigger additional uploads
- Already uploaded data is tracked and won't be re-uploaded
- Simply run the command again to retry the chunk

### 4. **Automatic Resume**

- Progress is saved in `sc_fill_progress.json`
- If a chunk isn't completed, it restarts from the beginning of that chunk
- Once a chunk completes, progress moves to the next 5-year period

## 🚀 Usage

### Basic Command

```bash
python download.py --sync-s3-fill
```

This will:

1. Process data from 1950 to present in 5-year chunks
2. Handle one chunk per run
3. Upload data immediately after each year
4. Save progress and exit when chunk completes

### Custom Date Range

```bash
python download.py --sync-s3-fill --start_date 1950-01-01 --end_date 2025-01-01
```

### Adjust Workers and Timeout

```bash
python download.py --sync-s3-fill --max_workers 10 --timeout-hours 5.5
```

## 📊 How It Works

### Example: Processing 1950-2025

The entire period is divided into 5-year chunks:

- Chunk 1: 1950-01-01 to 1954-12-31
- Chunk 2: 1955-01-01 to 1959-12-31
- Chunk 3: 1960-01-01 to 1964-12-31
- ... (and so on)
- Last chunk: 2020-01-01 to 2025-01-01 (partial)

### First Run

```
🚀 Starting 5-year chunk S3 gap-filling process...
📊 Total 5-year chunks: 15
⏳ Remaining chunks: 15
📦 Processing chunk 1/15: 1950-01-01 to 1954-12-31

  Processing data for 1950...
  📤 Uploading 1950 data...
  Processing data for 1951...
  📤 Uploading 1951 data...
  ...

✅ Completed chunk: 1950-01-01 to 1954-12-31
💾 Progress saved
📌 Chunk completed! 14 chunks remaining
📌 Run the same command again to process the next chunk
```

### Second Run

```
📋 Found existing progress from previous run:
  Last completed chunk: 1954-12-31
  Completed chunks: 1

📦 Processing chunk 2/15: 1955-01-01 to 1959-12-31
...
```

## 🛡️ Safety Features

### Data Protection

- ✅ **Immediate uploads**: Data uploaded year-by-year
- ✅ **No data loss**: Even if interrupted, uploaded data is safe
- ✅ **Deduplication**: Won't re-download or re-upload existing files
- ✅ **Graceful Ctrl+C**: Won't trigger duplicate uploads

### Progress Tracking

- Progress saved in `sc_fill_progress.json`
- Tracks:
  - Overall date range
  - Completed chunks
  - Last chunk end date
  - Last update timestamp

### Error Handling

- **Timeout reached**: Exits gracefully, chunk retries next run
- **Ctrl+C pressed**: Exits immediately, chunk retries next run
- **Exception thrown**: Logs error, chunk retries next run

## 📝 Progress File Format

`sc_fill_progress.json`:

```json
{
  "start_date": "1950-01-01",
  "end_date": "2025-01-01",
  "last_chunk_end": "1959-12-31",
  "completed_chunks": [
    ["1950-01-01", "1954-12-31"],
    ["1955-01-01", "1959-12-31"]
  ],
  "last_updated": "2025-10-01T10:30:00.123456"
}
```

## 🔄 Workflow for CI/CD

### GitHub Actions Example

Run the same command in separate workflow runs:

```yaml
name: Sync S3 Data (5-Year Chunks)

on:
  workflow_dispatch:
  schedule:
    - cron: "0 */6 * * *" # Every 6 hours

jobs:
  sync-chunk:
    runs-on: ubuntu-latest
    timeout-minutes: 350 # 5.8 hours

    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Process one 5-year chunk
        run: python download.py --sync-s3-fill --timeout-hours 5.5

      # Progress is automatically saved to S3 or can be committed to repo
```

### Manual Runs

```bash
# Run 1: Processes 1950-1954
python download.py --sync-s3-fill

# Run 2: Processes 1955-1959 (automatic)
python download.py --sync-s3-fill

# Run 3: Processes 1960-1964 (automatic)
python download.py --sync-s3-fill

# Continue until all chunks complete
```

## 🎯 Benefits

### vs. Old Approach

| Feature                | Old                       | New                         |
| ---------------------- | ------------------------- | --------------------------- |
| Upload timing          | End of run                | After each year             |
| Data loss on interrupt | ⚠️ All data lost          | ✅ Only current year lost   |
| Timeout handling       | ⚠️ May lose hours of work | ✅ Only loses current chunk |
| Resume capability      | ⚠️ Manual tracking        | ✅ Automatic                |
| Duplicate uploads      | ⚠️ Can happen on Ctrl+C   | ✅ Prevented                |
| 6-hour limit           | ⚠️ Can exceed             | ✅ Always within limit      |

## 🔍 Monitoring

### Check Progress

```bash
cat sc_fill_progress.json | python -m json.tool
```

### View Logs

The script provides emoji-rich logging:

- 🚀 Process start
- 📦 Chunk processing
- 📤 Year upload
- ✅ Chunk completion
- 🎉 All chunks complete
- ⚠️ Warnings/interruptions
- ❌ Errors

## ❓ FAQ

**Q: What happens if I press Ctrl+C?**
A: The process exits immediately. Data uploaded so far is safe. The current chunk will retry from the beginning on the next run.

**Q: Can I change the date range mid-process?**
A: No. Once started, the process will complete the original date range. To start fresh, delete `sc_fill_progress.json`.

**Q: How long does each chunk take?**
A: Depends on data density. Early years (1950s) are faster. Recent years may take 3-5 hours per chunk.

**Q: What if a chunk takes longer than 6 hours?**
A: The timeout (default 5.5h) will stop processing gracefully. The chunk will retry on the next run. Consider reducing `--day_step` for dense periods.

**Q: Can I run multiple instances in parallel?**
A: No. The progress file doesn't support concurrent access. Run one instance at a time.

## 🚨 Troubleshooting

### Chunk keeps timing out

- Reduce `--max_workers` (less parallel = slower but more reliable)
- Increase `--timeout-hours` (if you have more time available)
- Check network connectivity

### Progress file corrupted

```bash
rm sc_fill_progress.json
python download.py --sync-s3-fill  # Starts fresh
```

### Want to restart from scratch

```bash
rm sc_fill_progress.json
python download.py --sync-s3-fill --start_date 1950-01-01
```

## 📚 Technical Details

### Code Changes

1. **S3ArchiveManager**: Added `immediate_upload` mode and `upload_year_archives()` method
2. **sync_s3_fill_gaps**: Complete rewrite to process 5-year chunks
3. **Progress tracking**: Changed from date ranges to chunk-based tracking
4. **Graceful shutdown**: KeyboardInterrupt handler prevents duplicate uploads

### S3 Structure

```
s3://bucket/
  metadata/zip/year=1950/
    metadata.zip
    metadata.index.json
  metadata/zip/year=1951/
    ...
  data/zip/year=1950/
    english.zip
    english.index.json
    regional.zip
    regional.index.json
```

Each year is uploaded independently, making resume reliable and efficient.
