#!/usr/bin/env bash

#
# FDA Batch Processing - End-to-End Test Script
#
# Tests the complete FDA document processing pipeline with sample documents.
# This script sets up datasets, uploads documents, processes them, and runs
# the batch processing agents to extract questions and validate answers.
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
# Detect project root (directory containing this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SAMPLE_FILES="/Users/diegorey/Downloads/Test files"
OUTPUT_DIR="/tmp/fda_batch_test"
NAMESPACE="default"
PROJECT="fda-demo-1"
SKIP_PROCESSING=false

# Server URLs
SERVER_URL="http://localhost:8000"
AGENTS_URL="http://localhost:8003"

# Progress tracking
STEP=0
TOTAL_STEPS=12

# Function to print colored output
log_step() {
    STEP=$((STEP + 1))
    echo -e "\n${CYAN}[STEP $STEP/$TOTAL_STEPS]${NC} ${BLUE}$1${NC}"
    echo -e "${CYAN}$(printf '=%.0s' {1..80})${NC}"
}

log_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

log_success() {
    echo -e "${GREEN}✓${NC}  $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

log_error() {
    echo -e "${RED}✗${NC}  $1"
}

log_progress() {
    echo -e "${YELLOW}▶${NC}  $1"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-processing)
            SKIP_PROCESSING=true
            shift
            ;;
        --help)
            echo "FDA Batch Processing Setup Script"
            echo ""
            echo "Sets up RAG databases, uploads documents, and validates the system."
            echo "Run this before using fda_batch_process.sh for full batch processing."
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --skip-processing    Skip dataset upload and processing (use existing data)"
            echo "  --help               Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Cleanup function
cleanup_on_error() {
    log_error "Script failed at step $STEP"
    log_info "Check logs for details"
    exit 1
}

trap cleanup_on_error ERR

# Change to project root
cd "$PROJECT_ROOT"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo -e "${CYAN}"
echo "════════════════════════════════════════════════════════════════════════════════"
echo "  FDA Batch Processing - System Setup & Validation"
echo "════════════════════════════════════════════════════════════════════════════════"
echo -e "${NC}"
log_info "Project: $NAMESPACE/$PROJECT"
log_info "Sample files: $SAMPLE_FILES"
log_info "Output: $OUTPUT_DIR"
echo ""

# ============================================================================
# STEP 1: Verify services are running
# ============================================================================
log_step "Verifying Services"

log_progress "Checking server health..."
if curl -s -f "$SERVER_URL/health" > /dev/null; then
    SERVER_STATUS=$(curl -s "$SERVER_URL/health" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("status", "unknown"))' 2>/dev/null || echo "unknown")
    log_success "Server is $SERVER_STATUS"
else
    log_error "Server not responding at $SERVER_URL"
    log_info "Start with: nx start server"
    exit 1
fi

log_progress "Checking agents service..."
if curl -s -f "$AGENTS_URL/health/" > /dev/null; then
    AGENT_COUNT=$(curl -s "$AGENTS_URL/health/" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("agent_types_loaded", 0))' 2>/dev/null || echo "0")
    AGENT_TYPES=$(curl -s "$AGENTS_URL/health/" | python3 -c 'import json, sys; print(", ".join(json.load(sys.stdin).get("agent_types", [])))' 2>/dev/null || echo "")
    log_success "Agents service loaded $AGENT_COUNT agent types"
    log_info "Available: $AGENT_TYPES"
else
    log_error "Agents service not responding at $AGENTS_URL"
    log_info "Start with: nx start agents"
    exit 1
fi

# ============================================================================
# STEP 2: List available sample files
# ============================================================================
log_step "Scanning Sample Files"

log_progress "Counting documents in $SAMPLE_FILES..."
FILE_COUNT=$(find "$SAMPLE_FILES" -type f \( -name "*.pdf" -o -name "*.txt" \) | wc -l | tr -d ' ')
log_success "Found $FILE_COUNT documents"

log_info "Files:"
find "$SAMPLE_FILES" -type f \( -name "*.pdf" -o -name "*.txt" \) -exec basename {} \; | head -10 | while read -r file; do
    echo "  • $file"
done

if [[ "$SKIP_PROCESSING" == true ]]; then
    log_info "Skipping dataset creation and processing (--skip-processing flag)"
    echo ""
    # Jump to step 9
    STEP=8
else

# ============================================================================
# STEP 3: Create fda_letters dataset (full documents)
# ============================================================================
log_step "Creating fda_letters Dataset"

log_progress "Creating dataset with full document processor..."
if ./lf datasets add fda_letters_test \
    -s fda_full_document_processor \
    -b fda_letters_full_test 2>&1; then
    log_success "Created fda_letters_test dataset"
else
    log_warning "Dataset may already exist, continuing..."
fi

# ============================================================================
# STEP 4: Upload documents to fda_letters
# ============================================================================
log_step "Uploading FDA Letters"

log_progress "Uploading $FILE_COUNT documents (this may take 10-30 seconds)..."
UPLOAD_START=$(date +%s)

if ./lf datasets ingest fda_letters_test "$SAMPLE_FILES"/*.pdf "$SAMPLE_FILES"/*.txt 2>&1 | tee "$OUTPUT_DIR/upload_letters.log"; then
    UPLOAD_END=$(date +%s)
    UPLOAD_TIME=$((UPLOAD_END - UPLOAD_START))
    log_success "Uploaded in ${UPLOAD_TIME}s"
else
    log_error "Upload failed"
    exit 1
fi

# ============================================================================
# STEP 5: Process fda_letters into vector database
# ============================================================================
log_step "Processing FDA Letters into Vector Database"

log_progress "Processing documents (this may take 2-3 minutes)..."
log_info "Watch for: 'Processing Complete' message"
PROCESS_START=$(date +%s)

if ./lf datasets process fda_letters_test 2>&1 | tee "$OUTPUT_DIR/process_letters.log"; then
    PROCESS_END=$(date +%s)
    PROCESS_TIME=$((PROCESS_END - PROCESS_START))
    log_success "Processed in ${PROCESS_TIME}s"

    # Extract stats from output
    CHUNKS=$(grep -o "[0-9]* chunks created" "$OUTPUT_DIR/process_letters.log" | awk '{sum+=$1} END {print sum}' || echo "0")
    log_info "Created $CHUNKS total chunks"
else
    log_error "Processing failed"
    exit 1
fi

# ============================================================================
# STEP 6: Verify fda_letters database
# ============================================================================
log_step "Verifying fda_letters Database"

log_progress "Testing RAG query..."
QUERY_OUTPUT=$(./lf rag query --database fda_letters_full_test "virus testing" --top-k 2 2>&1)

if echo "$QUERY_OUTPUT" | grep -q "Found [1-9]"; then
    RESULT_COUNT=$(echo "$QUERY_OUTPUT" | grep -o "Found [0-9]*" | awk '{print $2}')
    log_success "Database is working ($RESULT_COUNT results found)"
else
    log_error "Database query returned no results"
    echo "$QUERY_OUTPUT"
    exit 1
fi

# ============================================================================
# STEP 7: Create fda_corpus dataset (chunked)
# ============================================================================
log_step "Creating fda_corpus Dataset"

log_progress "Creating dataset with chunked processor..."
if ./lf datasets add fda_corpus_test \
    -s fda_chunked_processor \
    -b fda_corpus_chunked_test 2>&1; then
    log_success "Created fda_corpus_test dataset"
else
    log_warning "Dataset may already exist, continuing..."
fi

# ============================================================================
# STEP 8: Upload and process corpus
# ============================================================================
log_step "Uploading and Processing Response Corpus"

log_progress "Uploading response documents..."
if ./lf datasets ingest fda_corpus_test "$SAMPLE_FILES"/*.pdf "$SAMPLE_FILES"/*.txt 2>&1 | tee "$OUTPUT_DIR/upload_corpus.log"; then
    log_success "Uploaded corpus documents"
else
    log_error "Corpus upload failed"
    exit 1
fi

log_progress "Processing corpus (chunked strategy)..."
if ./lf datasets process fda_corpus_test 2>&1 | tee "$OUTPUT_DIR/process_corpus.log"; then
    log_success "Processed corpus"

    CHUNKS=$(grep -o "[0-9]* chunks created" "$OUTPUT_DIR/process_corpus.log" | awk '{sum+=$1} END {print sum}' || echo "0")
    log_info "Created $CHUNKS semantic chunks"
else
    log_error "Corpus processing failed"
    exit 1
fi

fi  # End of SKIP_PROCESSING check

# ============================================================================
# STEP 9: Test Question Extractor
# ============================================================================
log_step "Testing FDA Question Extractor Agent"

# Get first document hash from dataset
log_progress "Retrieving document hash from dataset..."
curl -s "$SERVER_URL/v1/projects/$NAMESPACE/$PROJECT" > "$OUTPUT_DIR/project_config.json"

if [[ ! -s "$OUTPUT_DIR/project_config.json" ]]; then
    log_error "Failed to retrieve project config from API"
    exit 1
fi

FIRST_HASH=$(python3 << PYEOF
import json
import sys

try:
    with open("$OUTPUT_DIR/project_config.json") as f:
        project = json.load(f)
    datasets = project.get("project", {}).get("config", {}).get("datasets", [])
    fda_letters = next((d for d in datasets if d.get("name") == "fda_letters_test"), None)

    if fda_letters and fda_letters.get("files"):
        print(fda_letters["files"][0])
    else:
        print("No files in fda_letters_test dataset", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
)

if [[ -z "$FIRST_HASH" ]]; then
    log_error "Could not retrieve document hash"
    log_info "Check that fda_letters_test dataset has files"
    exit 1
fi

log_info "Document hash: ${FIRST_HASH:0:12}..."

log_progress "Running question extractor..."
EXTRACTOR_REQUEST=$(cat << EOF
{
  "namespace": "$NAMESPACE",
  "project": "$PROJECT",
  "agent_config": {
    "name": "fda_question_extractor",
    "type": "fda_question_extractor",
    "model": "fast",
    "config": {
      "database": "fda_letters_full_test",
      "min_confidence": 0.7
    }
  },
  "project_config": {},
  "input_data": {
    "document_hash": "$FIRST_HASH",
    "document_name": "test_document.pdf"
  }
}
EOF
)

EXTRACTOR_START=$(date +%s)
EXTRACTOR_RESPONSE=$(curl -s -X POST "$AGENTS_URL/v1/agents/run" \
  -H "Content-Type: application/json" \
  -d "$EXTRACTOR_REQUEST")
EXTRACTOR_END=$(date +%s)
EXTRACTOR_TIME=$((EXTRACTOR_END - EXTRACTOR_START))

echo "$EXTRACTOR_RESPONSE" > "$OUTPUT_DIR/extractor_response.json"

EXTRACTOR_STATUS=$(echo "$EXTRACTOR_RESPONSE" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("status", "unknown"))' 2>/dev/null || echo "failed")

if [[ "$EXTRACTOR_STATUS" == "completed" ]]; then
    QUESTION_COUNT=$(echo "$EXTRACTOR_RESPONSE" | python3 -c 'import json, sys; print(len(json.load(sys.stdin).get("result", {}).get("questions", [])))' 2>/dev/null || echo "0")
    log_success "Extractor completed in ${EXTRACTOR_TIME}s"
    log_info "Extracted $QUESTION_COUNT questions"

    # Show sample questions
    if [[ "$QUESTION_COUNT" -gt 0 ]]; then
        log_info "Sample questions:"
        echo "$EXTRACTOR_RESPONSE" | python3 << 'PYEOF'
import json, sys
data = json.load(sys.stdin)
questions = data.get("result", {}).get("questions", [])
for i, q in enumerate(questions[:3], 1):
    q_type = q.get("type", "unknown")
    q_text = q.get("question_text", "")[:80]
    print(f"  {i}. [{q_type}] {q_text}...")
PYEOF
    fi
else
    log_error "Extractor failed"
    log_info "Response saved to: $OUTPUT_DIR/extractor_response.json"
    exit 1
fi

# ============================================================================
# STEP 10: Test Answer Validator
# ============================================================================
log_step "Testing FDA Answer Validator Agent"

log_progress "Running answer validator with extracted questions..."

# Build validator request with extracted questions
VALIDATOR_REQUEST=$(python3 << PYEOF
import json
import sys

with open("$OUTPUT_DIR/extractor_response.json") as f:
    extractor_data = json.load(f)

questions = extractor_data.get("result", {}).get("questions", [])

# Only validate critical questions
critical_questions = [q for q in questions if q.get("type") == "critical"]

if not critical_questions:
    # If no critical questions, use first question
    critical_questions = questions[:1] if questions else []

request = {
    "namespace": "$NAMESPACE",
    "project": "$PROJECT",
    "agent_config": {
        "name": "fda_answer_validator",
        "type": "fda_answer_validator",
        "model": "fast",
        "config": {
            "database": "fda_corpus_chunked_test",
            "top_k": 10,
            "confidence_threshold": 0.75
        }
    },
    "project_config": {},
    "input_data": {
        "questions": critical_questions,
        "document_name": "test_document.pdf"
    }
}

print(json.dumps(request))
PYEOF
)

VALIDATOR_START=$(date +%s)
VALIDATOR_RESPONSE=$(curl -s -X POST "$AGENTS_URL/v1/agents/run" \
  -H "Content-Type: application/json" \
  -d "$VALIDATOR_REQUEST")
VALIDATOR_END=$(date +%s)
VALIDATOR_TIME=$((VALIDATOR_END - VALIDATOR_START))

echo "$VALIDATOR_RESPONSE" > "$OUTPUT_DIR/validator_response.json"

VALIDATOR_STATUS=$(echo "$VALIDATOR_RESPONSE" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("status", "unknown"))' 2>/dev/null || echo "failed")

if [[ "$VALIDATOR_STATUS" == "completed" ]]; then
    ANSWERED_COUNT=$(echo "$VALIDATOR_RESPONSE" | python3 -c 'import json, sys; print(len([v for v in json.load(sys.stdin).get("result", {}).get("validations", []) if v.get("answered")]))' 2>/dev/null || echo "0")
    TOTAL_VALIDATED=$(echo "$VALIDATOR_RESPONSE" | python3 -c 'import json, sys; print(len(json.load(sys.stdin).get("result", {}).get("validations", [])))' 2>/dev/null || echo "0")
    log_success "Validator completed in ${VALIDATOR_TIME}s"
    log_info "Validated $TOTAL_VALIDATED questions: $ANSWERED_COUNT answered"
else
    log_error "Validator failed"
    log_info "Response saved to: $OUTPUT_DIR/validator_response.json"
    exit 1
fi

# ============================================================================
# STEP 11: List agent types
# ============================================================================
log_step "Listing Available Agent Types"

log_progress "Querying agents service..."
AGENT_TYPES_RESPONSE=$(curl -s "$AGENTS_URL/v1/agents/types")
echo "$AGENT_TYPES_RESPONSE" | python3 << 'PYEOF'
import json, sys
data = json.load(sys.stdin)
types = data.get("types", [])
print(f"Total agent types: {len(types)}")
for agent_type in types:
    name = agent_type.get("type", "unknown")
    module = agent_type.get("module", "").split(".")[-1]
    print(f"  • {name} ({module})")
PYEOF

# ============================================================================
# STEP 12: Summary
# ============================================================================
log_step "Test Summary"

echo ""
log_success "All tests passed!"
echo ""
log_info "Summary:"
echo "  • Documents uploaded: $FILE_COUNT"
echo "  • Chunks created (full): $(grep -h "chunks created" "$OUTPUT_DIR/process_letters.log" | awk '{sum+=$1} END {print sum}')"
echo "  • Chunks created (chunked): $(grep -h "chunks created" "$OUTPUT_DIR/process_corpus.log" | awk '{sum+=$1} END {print sum}')"
echo "  • Questions extracted: $QUESTION_COUNT"
echo "  • Questions answered: $ANSWERED_COUNT/$TOTAL_VALIDATED"
echo "  • Total processing time: ~$((EXTRACTOR_TIME + VALIDATOR_TIME))s"
echo ""
log_info "Output files:"
echo "  • Upload logs: $OUTPUT_DIR/upload_*.log"
echo "  • Process logs: $OUTPUT_DIR/process_*.log"
echo "  • Extractor response: $OUTPUT_DIR/extractor_response.json"
echo "  • Validator response: $OUTPUT_DIR/validator_response.json"
echo ""

log_info "Next steps:"
echo "  1. Review extracted questions: cat $OUTPUT_DIR/extractor_response.json | python3 -m json.tool"
echo "  2. Review validations: cat $OUTPUT_DIR/validator_response.json | python3 -m json.tool"
echo "  3. Run full batch script: ./scripts/fda_batch_process.sh --help"
echo ""

echo -e "${GREEN}"
echo "════════════════════════════════════════════════════════════════════════════════"
echo "  ✓ FDA Batch Processing System Setup Complete"
echo "════════════════════════════════════════════════════════════════════════════════"
echo -e "${NC}"
echo ""
log_info "System is ready for batch processing!"
echo ""
log_info "To process all documents, run:"
echo "  ./scripts/fda_batch_process.sh --documents-dir $SAMPLE_FILES --responses-dir $SAMPLE_FILES"
echo ""
