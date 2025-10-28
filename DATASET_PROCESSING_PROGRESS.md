# Dataset Processing Progress & Status Tracking

## Overview
Enhanced the dataset processing system to provide real-time per-file progress tracking and detailed result display in the Designer UI.

## What We've Built

### 1. **Real-Time Task Status Tracking**

#### Backend Changes (`server/api/routers/projects/projects.py`)

**Problem:**
- Task status endpoint only returned "PENDING" for Celery group tasks
- No visibility into individual file processing progress
- `GroupResult.restore()` doesn't work reliably with filesystem backend

**Solution:**
- Store child task IDs and metadata when creating task groups
- Query each child task directly to get individual file status
- Return new "PROGRESS" state with per-file details

**Response Format:**
```json
{
  "task_id": "abc-123",
  "state": "PROGRESS",
  "meta": {
    "current": 2,
    "total": 5,
    "progress": 40,
    "message": "Processing 2/5 files",
    "files": [
      {
        "index": 0,
        "task_id": "child-1",
        "state": "success",
        "filename": "file_hash_123",
        "chunks": 42,
        "error": null
      },
      {
        "index": 1,
        "task_id": "child-2",
        "state": "processing",
        "filename": "file_hash_456",
        "chunks": null,
        "error": null
      },
      {
        "index": 2,
        "task_id": "child-3",
        "state": "pending",
        "filename": "file_hash_789",
        "chunks": null,
        "error": null
      }
    ]
  }
}
```

**File States:**
- `pending` - Queued, not started yet
- `processing` - Currently being processed
- `success` - Completed successfully
- `failure` - Failed with error

#### Frontend Changes (`designer/src/components/Data/DatasetView.tsx`)

**New Features:**
1. **Live Processing Progress Section** - Shows real-time status of each file
2. **Visual Status Indicators:**
   - ○ Gray circle = Pending
   - ⟳ Spinning blue circle = Processing
   - ✓ Green checkmark = Success
   - ✗ Red X = Failed
3. **Progress Badge** - Shows "Processing 2/5" or "Processing 40%"
4. **Background Polling** - Continues updating even when tab loses focus

**Hook Improvements (`designer/src/hooks/useDatasets.ts`):**
```typescript
refetchIntervalInBackground: true  // Continue polling when tab inactive
refetchInterval: (query) => {
  // Smart polling - stops only when complete
  const data = query.state.data as any
  if (data?.state === 'SUCCESS' || data?.state === 'FAILURE') {
    return false  // Stop polling
  }
  return 2000  // Poll every 2 seconds
}
```

### 2. **Enhanced Completion Notifications**

**Before:** "Dataset processing completed"
**After:** "✅ Processing complete! 5 file(s) processed"

**Console Logging:**
```javascript
Task status update: {
  taskId: "abc-123",
  state: "PROGRESS",
  fileCount: 5,
  filesData: [...]
}
```

---

## Current Limitations & Next Steps

### 1. **Improve Final Results Display** ✅ COMPLETED

**Previous Issue:**
The final SUCCESS result contains rich data that wasn't being fully displayed:

```json
{
  "result": {
    "details": [
      {
        "file_hash": "cc8a152b...",
        "success": true,
        "details": {
          "filename": "document.pdf",           // ← Show this
          "parser": "PDFParser_LlamaIndex",     // ← Show this
          "extractors": ["KeywordExtractor"],   // ← Show this
          "chunks": 16,                         // ← Show this
          "stored_count": 0,                    // ← Show this
          "skipped_count": 16,                  // ← Show this
          "status": "skipped",                  // ← Show this
          "reason": "duplicate",                // ← Show why skipped
          "embedder": "OllamaEmbedder"
        }
      }
    ]
  }
}
```

**Proposed UI Enhancement:**

```
┌─ Processing Results ────────────────────────────────────┐
│  3 files processed                            [Clear]   │
│                                                          │
│  📄 document.pdf                                         │
│     ⚠️  SKIPPED (duplicate)                              │
│     16 chunks created, 0 stored, 16 skipped             │
│     Parser: PDFParser_LlamaIndex                        │
│     Extractors: KeywordExtractor                        │
│     Embedder: OllamaEmbedder                            │
│                                                          │
│  📄 report.pdf                                           │
│     ✅ SUCCESS                                           │
│     24 chunks created, 24 stored, 0 skipped             │
│     Parser: PDFParser_PyPDF2                            │
│     Extractors: KeywordExtractor, TableExtractor        │
│                                                          │
│  📄 data.csv                                             │
│     ❌ FAILED: Unsupported encoding                     │
└──────────────────────────────────────────────────────────┘
```

**Implementation Tasks:**
- [x] Update `DatasetView.tsx` to parse and display `result.details`
- [x] Add badges for status (SKIPPED, SUCCESS, FAILED)
- [x] Show chunks breakdown (created, stored, skipped)
- [x] Display parser and extractors used
- [x] Show skip/failure reasons
- [x] Make it scrollable for large datasets (max-h-96)

**✅ Implementation Complete (designer/src/components/Data/DatasetView.tsx)**

**What Was Built:**
1. **Enhanced File Display:**
   - File type emoji icons (📄 for documents, 📁 for other files)
   - Actual filename from `result.filename` with hash fallback
   - Status icons (✓ green checkmark, ! yellow warning, ✗ red error)
   - Status badges with emojis (✓ SUCCESS, ⚠️ SKIPPED, ✗ FAILED)

2. **Comprehensive Chunk Statistics:**
   - Visual chunk display: `📦 16 chunks created ✓ 0 stored ⊘ 16 skipped`
   - Uses `result.document_count` or `details.chunks` for total
   - Shows `result.stored_count` and `result.skipped_count`
   - Highlighted in background with proper spacing

3. **Processing Metadata:**
   - Parser: Shows `result.parsers_used` array or falls back to `details.parser`
   - Extractors: Displayed as individual badges (e.g., [KeywordExtractor] [TableExtractor])
   - Embedder: From `result.embedder` or `details.embedder`
   - Document IDs: Shows count of documents stored in vector database

4. **Enhanced Reason Display:**
   - Highlighted backgrounds (yellow for skipped, red for failed)
   - Proper color coding for light/dark modes
   - Clear "Reason:" label with formatted reason text

5. **Better UX:**
   - Hover effects on file rows (`hover:bg-muted/30`)
   - Better visual hierarchy with proper spacing
   - Grid layout for parser/embedder info
   - Responsive design with `md:` breakpoints
   - Scrollable container (max-height-96)

**Data Mapping:**
```typescript
// Filename display priority
displayFilename = result.filename || details.filename || fileResult.file_hash

// Chunk statistics
totalChunks = result.document_count || details.chunks || 0
storedChunks = result.stored_count || 0
skippedChunks = result.skipped_count || 0

// Parser info
parser = result.parsers_used?.join(', ') || details.parser

// Extractors
extractors = result.extractors_applied || details.extractors

// Embedder
embedder = result.embedder || details.embedder

// Status and reason
status = result.status || details.status
reason = result.reason || details.reason
```

---

### 2. **Create Dataset Processing Info Endpoint** ⭐ PRIORITY

**Goal:**
Provide a comprehensive view of dataset processing history and current state.

**Proposed Endpoint:**
```
GET /projects/{namespace}/{project}/datasets/{dataset}/info
```

**Response:**
```json
{
  "dataset": {
    "name": "my_dataset",
    "database": "main_database",
    "strategy": "universal_processor",
    "created_at": "2025-01-15T10:00:00Z",
    "last_processed": "2025-01-15T14:30:00Z"
  },
  "files": {
    "total": 10,
    "processed": 8,
    "pending": 2,
    "failed": 0
  },
  "processing_history": [
    {
      "timestamp": "2025-01-15T14:30:00Z",
      "task_id": "abc-123",
      "status": "completed",
      "processed": 3,
      "skipped": 2,
      "failed": 0,
      "duration_seconds": 45
    }
  ],
  "file_details": [
    {
      "hash": "cc8a152b...",
      "original_filename": "document.pdf",
      "status": "processed",
      "last_processed": "2025-01-15T14:30:00Z",
      "chunks_stored": 16,
      "parser_used": "PDFParser_LlamaIndex",
      "skip_reason": "duplicate"
    }
  ],
  "vector_database_stats": {
    "total_chunks": 1247,
    "total_documents": 156,
    "embeddings_generated": 1247
  }
}
```

**Implementation Tasks:**
- [ ] Create new endpoint in `datasets.py`
- [ ] Query processing logs/history from disk or database
- [ ] Aggregate file processing status
- [ ] Get vector database stats from RAG service
- [ ] Create frontend hook `useDatasetInfo()`
- [ ] Add "Dataset Info" tab or section in DatasetView

---

### 3. **Persistent Processing Logs**

**Current Issue:**
Processing results are only available in the task result, which may be garbage collected.

**Proposed Solution:**

**Store processing logs to disk:**
```
~/.llamafarm/projects/{namespace}/{project}/lf_data/processing_logs/
  ├── 2025-01-15_14-30-00_abc123.json   # Processing run log
  ├── 2025-01-15_16-45-00_def456.json
  └── latest.json                        # Symlink to most recent
```

**Log Format:**
```json
{
  "task_id": "abc-123",
  "started_at": "2025-01-15T14:30:00Z",
  "completed_at": "2025-01-15T14:30:45Z",
  "dataset": "my_dataset",
  "strategy": "universal_processor",
  "database": "main_database",
  "files": [
    {
      "hash": "cc8a152b...",
      "filename": "document.pdf",
      "status": "skipped",
      "reason": "duplicate",
      "chunks": 16,
      "stored": 0,
      "parser": "PDFParser_LlamaIndex",
      "extractors": ["KeywordExtractor"],
      "duration_seconds": 2.3
    }
  ],
  "summary": {
    "processed": 3,
    "skipped": 2,
    "failed": 0
  }
}
```

**Implementation Tasks:**
- [ ] Update `process_single_file_task` to log results
- [ ] Create logging utility in `services/processing_log_service.py`
- [ ] Store logs after each processing run
- [ ] Add endpoint to query historical logs
- [ ] Display in UI via dataset info endpoint

---

### 4. **Enhanced Error Handling & Retry**

**Current Issue:**
- Failed files don't show actionable information
- No way to retry individual failed files
- Unclear why files are being skipped

**Proposed Features:**

1. **Detailed Error Messages:**
   ```
   ❌ Failed: document.pdf
   Parser: PDFParser_LlamaIndex
   Error: Invalid PDF structure at page 5
   Suggestion: Try PDFParser_PyPDF2 instead
   [Retry with different parser] [Skip file]
   ```

2. **Retry Individual Files:**
   - Button to reprocess specific failed files
   - Option to switch parser/strategy
   - Retry with different configuration

3. **Skip Reasons:**
   - Better categorization (duplicate, already processed, unsupported format)
   - Show hash of duplicate documents
   - Provide option to force reprocess

**Implementation Tasks:**
- [ ] Enhance error messages in RAG tasks
- [ ] Add retry endpoint: `POST /datasets/{dataset}/retry/{file_hash}`
- [ ] UI button for retrying failed files
- [ ] Show skip reasons prominently
- [ ] Add "Force Reprocess" option

---

### 5. **Performance Optimizations**

**Current Issue:**
- Polling every 2 seconds for large datasets creates load
- All child task results queried on each poll

**Proposed Improvements:**

1. **WebSocket Support** (Long-term):
   - Push updates instead of polling
   - Real-time progress without HTTP overhead

2. **Caching & Batching** (Short-term):
   - Cache child task results for 1-2 seconds
   - Only query changed tasks
   - Batch status queries

3. **Progressive Loading:**
   - Show first 10-20 files initially
   - "Show more" for large datasets
   - Virtual scrolling for 1000+ files

**Implementation Tasks:**
- [ ] Add WebSocket endpoint for task updates
- [ ] Implement caching layer for task results
- [ ] Add pagination to file status list
- [ ] Virtual scrolling component for large lists

---

## Testing Checklist

### Functionality Tests
- [x] Process dataset with single file
- [x] Process dataset with multiple files (3-5)
- [ ] Process dataset with many files (50+)
- [x] View progress while processing
- [x] See completion notification
- [ ] View detailed results after completion
- [ ] Check skipped files display correctly
- [ ] Verify failed files show errors
- [ ] Test with browser tab in background
- [ ] Test with browser minimized

### Edge Cases
- [ ] Cancel processing mid-way
- [ ] Network interruption during processing
- [ ] Server restart during processing
- [ ] Very large files (100MB+)
- [ ] Duplicate detection
- [ ] Unsupported file types
- [ ] Corrupted files

### Performance Tests
- [ ] Process 100 files - measure UI responsiveness
- [ ] Process 1000 files - check memory usage
- [ ] Rapid polling - verify no memory leaks
- [ ] Multiple datasets processing simultaneously

---

## Files Changed

### Backend
- `server/api/routers/projects/projects.py` - Enhanced task status endpoint
- `server/api/routers/datasets/datasets.py` - Store group metadata
- `server/core/celery/tasks/task_process_dataset.py` - Task chain creation

### Frontend
- `designer/src/hooks/useDatasets.ts` - Smart polling with background support
- `designer/src/components/Data/DatasetView.tsx` - Live progress UI
- `designer/src/api/datasets.ts` - Task status types

---

## API Reference

### Get Task Status
```
GET /api/v1/projects/{namespace}/{project}/tasks/{task_id}
```

**File:** `server/api/routers/projects/projects.py` (line 426)

**Response States:**
- `PENDING` - Task queued, not started
- `PROGRESS` - Task in progress (new state we added)
- `STARTED` - Celery task running
- `SUCCESS` - Task completed successfully
- `FAILURE` - Task failed

**When PENDING (group task with stored metadata):**
```json
{
  "task_id": "e05a7b32-8549-431d-aeeb-3b53d27f977e",
  "state": "PENDING",
  "meta": null,
  "result": {
    "type": "group",
    "children": ["child-task-1", "child-task-2", "child-task-3"],
    "total_files": 3,
    "file_hashes": ["cc8a152b...", "dab7a046...", "02c71d6c..."]
  }
}
```

**When PROGRESS (actively processing):**
```json
{
  "task_id": "e05a7b32-8549-431d-aeeb-3b53d27f977e",
  "state": "PROGRESS",
  "meta": {
    "current": 2,
    "total": 5,
    "progress": 40,
    "message": "Processing 2/5 files",
    "files": [
      {
        "index": 0,
        "task_id": "child-task-1",
        "state": "success",
        "filename": "cc8a152b719403bb44156443ffd632d6cf9d1e4586403c09d8c0f0bc3910d240",
        "chunks": 16,
        "error": null
      },
      {
        "index": 1,
        "task_id": "child-task-2",
        "state": "processing",
        "filename": "dab7a04651df99437271e0a7f935376fd1b5cdaaddac7ad29e154eaa4bffdba3",
        "chunks": null,
        "error": null
      },
      {
        "index": 2,
        "task_id": "child-task-3",
        "state": "pending",
        "filename": "02c71d6cc6c7d4f96fde72cfb00c478bbb491f17fa2db6a8c648c7c706d79dbe",
        "chunks": null,
        "error": null
      }
    ]
  },
  "result": null,
  "error": null,
  "traceback": null
}
```

**When SUCCESS (completed):**
```json
{
  "task_id": "e05a7b32-8549-431d-aeeb-3b53d27f977e",
  "state": "SUCCESS",
  "meta": null,
  "result": {
    "processed_files": 3,
    "failed_files": 0,
    "skipped_files": 0,
    "details": [
      {
        "file_hash": "cc8a152b719403bb44156443ffd632d6cf9d1e4586403c09d8c0f0bc3910d240",
        "success": true,
        "details": {
          "filename": "022517Orig1s000OtherActionLtrs.pdf",
          "parser": "PDFParser_LlamaIndex",
          "extractors": ["KeywordExtractor"],
          "chunks": 16,
          "chunk_size": null,
          "embedder": "OllamaEmbedder",
          "error": null,
          "reason": "duplicate",
          "result": {
            "status": "skipped",
            "filename": "022517Orig1s000OtherActionLtrs.pdf",
            "document_count": 16,
            "stored_count": 0,
            "skipped_count": 16,
            "document_ids": [],
            "parsers_used": ["PDFParser_LlamaIndex"],
            "extractors_applied": ["KeywordExtractor"],
            "embedder": "OllamaEmbedder",
            "reason": "duplicate"
          },
          "status": "skipped",
          "stored_count": 0,
          "skipped_count": 16
        }
      }
    ]
  },
  "error": null,
  "traceback": null
}
```

**File States in `meta.files`:**
- `pending` - Not started yet
- `processing` - Currently being processed (Celery state: STARTED)
- `success` - Completed successfully
- `failure` - Failed with error

### Process Dataset
```
POST /api/v1/projects/{namespace}/{project}/datasets/{dataset}/process?async_processing=true
```

**File:** `server/api/routers/datasets/datasets.py` (line 278)

**Request:**
```
POST /api/v1/projects/default/sample-app/datasets/New/process?async_processing=true
```

**Response:**
```json
{
  "message": "Dataset processing started asynchronously",
  "processed_files": 0,
  "skipped_files": 0,
  "failed_files": 0,
  "strategy": "love",
  "database": "main_database",
  "details": [
    {
      "hash": "cc8a152b...",
      "filename": null,
      "status": "pending",
      "error": null
    }
  ],
  "task_id": "e05a7b32-8549-431d-aeeb-3b53d27f977e"
}
```

### List Datasets
```
GET /api/v1/projects/{namespace}/{project}/datasets
```

**File:** `server/api/routers/datasets/datasets.py`

**Response:**
```json
{
  "total": 3,
  "datasets": [
    {
      "name": "New",
      "data_processing_strategy": "love",
      "database": "main_database",
      "files": [
        "cc8a152b719403bb44156443ffd632d6cf9d1e4586403c09d8c0f0bc3910d240",
        "dab7a04651df99437271e0a7f935376fd1b5cdaaddac7ad29e154eaa4bffdba3"
      ],
      "details": {
        "files_metadata": [
          {
            "hash": "cc8a152b...",
            "original_filename": "document.pdf",
            "size": 1234567,
            "timestamp": 1705334400,
            "mime_type": "application/pdf"
          }
        ]
      }
    }
  ]
}
```

### Upload File to Dataset
```
POST /api/v1/projects/{namespace}/{project}/datasets/{dataset}/upload
```

**File:** `server/api/routers/datasets/datasets.py`

**Request (multipart/form-data):**
```
POST /api/v1/projects/default/sample-app/datasets/New/upload
Content-Type: multipart/form-data

file: <binary file data>
```

**Response:**
```json
{
  "message": "File uploaded successfully",
  "file_hash": "cc8a152b719403bb44156443ffd632d6cf9d1e4586403c09d8c0f0bc3910d240",
  "original_filename": "document.pdf"
}
```

### Delete File from Dataset
```
DELETE /api/v1/projects/{namespace}/{project}/datasets/{dataset}/files/{file_hash}?remove_from_disk=true
```

**File:** `server/api/routers/datasets/datasets.py`

**Response:**
```json
{
  "message": "File deleted successfully",
  "file_hash": "cc8a152b...",
  "removed_from_disk": true
}
```

---

## Frontend API Hooks

### File: `designer/src/hooks/useDatasets.ts`

**useTaskStatus** - Poll for task status updates
```typescript
const { data: taskStatus } = useTaskStatus(
  namespace,
  project,
  taskId,        // Task ID from process endpoint
  { enabled: !!taskId }
)

// Returns TaskStatusResponse with states: PENDING, PROGRESS, SUCCESS, FAILURE
```

**useProcessDataset** - Trigger dataset processing
```typescript
const processMutation = useProcessDataset()

const result = await processMutation.mutateAsync({
  namespace: 'default',
  project: 'sample-app',
  dataset: 'New'
})

// Returns { task_id: "...", message: "...", ... }
```

**useListDatasets** - Get all datasets for a project
```typescript
const { data: datasetsResponse } = useListDatasets(namespace, project)

// Returns { total: 3, datasets: [...] }
```

**useUploadFileToDataset** - Upload files
```typescript
const uploadMutation = useUploadFileToDataset()

await uploadMutation.mutateAsync({
  namespace,
  project,
  dataset,
  file: File  // File object from input
})
```

**useDeleteDatasetFile** - Delete a file
```typescript
const deleteFileMutation = useDeleteDatasetFile()

await deleteFileMutation.mutateAsync({
  namespace,
  project,
  dataset,
  fileHash: "cc8a152b...",
  removeFromDisk: true
})
```

---

## Frontend Components

### File: `designer/src/components/Data/DatasetView.tsx`

**Key State:**
```typescript
const [currentTaskId, setCurrentTaskId] = useState<string | null>(null)
const [processingResult, setProcessingResult] = useState<any>(null)

// Task status polling (updates every 2 seconds)
const { data: taskStatus } = useTaskStatus(
  activeProject?.namespace || '',
  activeProject?.project || '',
  currentTaskId,
  { enabled: !!currentTaskId && !!activeProject }
)
```

**Processing Flow:**
1. User clicks "Process Dataset" button
2. Call `processMutation.mutateAsync()` → gets task_id
3. Store task_id in state: `setCurrentTaskId(result.task_id)`
4. `useTaskStatus` hook starts polling every 2 seconds
5. Display "Live Processing Progress" section with per-file status
6. When complete, store result in `processingResult` state
7. Display "Processing Results" section with detailed file info

**UI Sections:**
1. **Header** - Dataset name, description, Process button, status badge
2. **Connected Database** - Shows which database dataset uses
3. **Processing Strategy** - Shows which strategy is configured
4. **Live Processing Progress** - Real-time per-file status (only while processing)
5. **Processing Results** - Detailed results after completion
6. **Raw Data** - File upload/management

---

## Celery Task Structure

### File: `server/core/celery/tasks/task_process_dataset.py`

**create_dataset_processing_chain()** (line 196)
- Creates a Celery group of parallel tasks
- One task per file in the dataset
- Returns a `group` object

**process_single_file_task()** (line 121)
- Processes one file
- Chains to RAG ingest task
- Polls for RAG completion
- Returns file processing details

**Task Chain Flow:**
```
1. POST /datasets/{dataset}/process
   ↓
2. create_dataset_processing_chain()
   ↓
3. group([
     process_single_file_task(file1),
     process_single_file_task(file2),
     process_single_file_task(file3)
   ])
   ↓
4. Each task → RAG ingest_file task
   ↓
5. Poll for completion
   ↓
6. Return aggregated results
```

**Metadata Storage:**
```python
# When creating group task
celery_app.backend.store_result(
    result.id,
    {
        "type": "group",
        "children": [child.id for child in result.results],
        "total_files": len(child_task_ids),
        "file_hashes": ["cc8a152b...", "dab7a046...", ...]
    },
    "PENDING"
)
```

This metadata is retrieved by the task status endpoint to track individual file progress.

---

## Celery Configuration

### File: `server/core/celery/celery.py`

**Result Backend:**
- Filesystem: `file://{lf_data_dir}/broker/results`
- Or external (Redis/RabbitMQ): `settings.celery_result_backend`

**Task Routing:**
- RAG tasks → `rag` queue
- Server tasks → `server` queue

**Worker:**
- Runs in background thread
- Pool: `solo` (single worker)
- Queue: `server` only (RAG worker handles `rag` queue)

---

## Next Sprint Priorities

1. **Enhance Results Display** - Show detailed file processing info
2. **Create Dataset Info Endpoint** - Historical processing data
3. **Persistent Logging** - Store processing logs to disk
4. **Error Handling** - Better messages and retry capability
5. **Performance** - Optimize for large datasets

---

## Known Issues

1. **GroupResult.restore() doesn't work** with filesystem backend
   - **Workaround:** Store child task IDs manually ✅

2. **No processing history** after task completes
   - **Fix:** Implement persistent logging (next step)

3. **Large datasets slow down UI** with all files displayed
   - **Fix:** Add pagination/virtual scrolling (next step)

4. **No way to retry failed files** individually
   - **Fix:** Add retry endpoint (next step)

---

## Questions & Decisions Needed

1. **Processing Logs Location:**
   - Store in project directory or separate logs database?
   - Retention policy (keep last N runs, or forever)?

2. **WebSocket vs Polling:**
   - Invest in WebSocket now or optimize polling first?

3. **Duplicate Detection:**
   - Should we show duplicates in UI with option to force reprocess?
   - Should duplicate checking be configurable per dataset?

4. **Performance Target:**
   - What's the max number of files we need to support?
   - What's acceptable processing time for 1000 files?
