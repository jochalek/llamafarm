#!/usr/bin/env bash

#
# FDA Batch Processing Script
#
# Processes ALL documents in the dataset through the FDA batch orchestrator agent.
# Extracts questions from each document and validates answers in the response corpus.
#
# Prerequisites: Run fda_batch_setup.sh first to create datasets and upload documents.
#
# Usage:
#   ./scripts/fda_batch_process.sh [options]
#
# Options:
#   --namespace NS          Project namespace (default: default)
#   --project PROJ          Project name (default: fda-demo-1)
#   --batch-size N          Documents per batch (default: 5)
#   --output-dir DIR        Output directory (default: /tmp/fda_batch)
#   --model MODEL           Model to use (default: fast)
#   --help                  Show this help message
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
NAMESPACE="default"
PROJECT="fda-demo-1"
BATCH_SIZE=5
OUTPUT_DIR="/tmp/fda_batch"
MODEL="fast"

# Server URLs
SERVER_URL="http://localhost:8000"
AGENTS_URL="http://localhost:8003"

# Logging functions
log_info() { echo -e "${BLUE}ℹ${NC}  $1"; }
log_success() { echo -e "${GREEN}✓${NC}  $1"; }
log_warning() { echo -e "${YELLOW}⚠${NC}  $1"; }
log_error() { echo -e "${RED}✗${NC}  $1"; }
log_progress() { echo -e "${YELLOW}▶${NC}  $1"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace) NAMESPACE="$2"; shift 2 ;;
        --project) PROJECT="$2"; shift 2 ;;
        --batch-size) BATCH_SIZE="$2"; shift 2 ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        --model) MODEL="$2"; shift 2 ;;
        --help)
            cat << EOF
FDA Batch Processing Script

Processes ALL documents in the fda_letters_test dataset through question extraction
and answer validation. Generates comprehensive report with statistics.

Prerequisites:
  1. Run fda_batch_setup.sh first to create datasets and upload documents
  2. Ensure server and agents service are running

Usage:
  $0 [options]

Options:
  --namespace NS          Project namespace (default: default)
  --project PROJ          Project name (default: fda-demo-1)
  --batch-size N          Documents per batch (default: 5)
  --output-dir DIR        Output directory (default: /tmp/fda_batch)
  --model MODEL           Model to use (default: fast)
  --help                  Show this help message

Examples:
  # Process all documents with default settings
  $0

  # Process with larger batches and different model
  $0 --batch-size 10 --model balanced

  # Custom output directory
  $0 --output-dir /data/fda_results

Output:
  - Progress state: \$OUTPUT_DIR/batch_state.json
  - Final report: \$OUTPUT_DIR/batch_XXXXX_report.json
  - CSV export: \$OUTPUT_DIR/batch_XXXXX_report.csv

EOF
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo -e "${CYAN}"
echo "════════════════════════════════════════════════════════════════════════════════"
echo "  FDA Batch Document Processing"
echo "════════════════════════════════════════════════════════════════════════════════"
echo -e "${NC}"
log_info "Project: $NAMESPACE/$PROJECT"
log_info "Batch size: $BATCH_SIZE documents"
log_info "Model: $MODEL"
log_info "Output: $OUTPUT_DIR"
echo ""

# Verify services
log_progress "Verifying services..."
if ! curl -s -f "$SERVER_URL/health" > /dev/null; then
    log_error "Server not responding at $SERVER_URL"
    exit 1
fi

if ! curl -s -f "$AGENTS_URL/health/" > /dev/null; then
    log_error "Agents service not responding at $AGENTS_URL"
    exit 1
fi
log_success "Services healthy"
echo ""

# Get document list from dataset
log_progress "Retrieving document list from fda_letters_test dataset..."
curl -s "$SERVER_URL/v1/projects/$NAMESPACE/$PROJECT" > "$OUTPUT_DIR/project_config.json"

if [[ ! -s "$OUTPUT_DIR/project_config.json" ]]; then
    log_error "Failed to retrieve project configuration"
    exit 1
fi

# Build document list
DOCUMENT_COUNT=$(python3 << PYEOF
import json

with open("$OUTPUT_DIR/project_config.json") as f:
    project = json.load(f)

datasets = project.get("project", {}).get("config", {}).get("datasets", [])
fda_letters = next((d for d in datasets if d.get("name") == "fda_letters_test"), None)

if not fda_letters:
    print("0")
    exit(1)

files = fda_letters.get("files", [])
print(len(files))

# Build document list for batch orchestrator
documents = [{"hash": f, "name": f[:12] + "..."} for f in files]

with open("$OUTPUT_DIR/documents.json", "w") as out:
    json.dump(documents, out, indent=2)
PYEOF
)

if [[ "$DOCUMENT_COUNT" == "0" ]]; then
    log_error "No documents found in fda_letters_test dataset"
    log_info "Run fda_batch_setup.sh first to upload documents"
    exit 1
fi

log_success "Found $DOCUMENT_COUNT documents to process"
echo ""

# Build batch orchestrator request
log_progress "Preparing batch processing request..."
cat > "$OUTPUT_DIR/batch_request.json" << EOF
{
  "namespace": "$NAMESPACE",
  "project": "$PROJECT",
  "agent_config": {
    "name": "fda_batch_orchestrator",
    "type": "fda_batch_orchestrator",
    "model": "$MODEL",
    "config": {
      "batch_size": $BATCH_SIZE,
      "output_path": "$OUTPUT_DIR",
      "resume_on_failure": true,
      "extractor_config": {
        "database": "fda_letters_full_test",
        "min_confidence": 0.7,
        "extract_informal": true
      },
      "validator_config": {
        "database": "fda_corpus_chunked_test",
        "retrieval_strategy": "semantic_search",
        "top_k": 10,
        "confidence_threshold": 0.75,
        "max_recursion_depth": 2
      }
    }
  },
  "project_config": {},
  "input_data": {
    "dataset_name": "fda_letters_test",
    "documents": $(cat "$OUTPUT_DIR/documents.json")
  }
}
EOF

log_success "Batch request prepared"
log_info "Processing $DOCUMENT_COUNT documents in batches of $BATCH_SIZE"
echo ""

# Execute batch processing
log_warning "Starting batch processing - this will take several minutes..."
log_info "Estimated time: ~9 seconds per document (based on testing with 15 docs in 2m 22s)"
log_info "Total estimated time: ~$((DOCUMENT_COUNT * 9 / 60)) minutes"
echo ""

START_TIME=$(date +%s)

log_progress "Sending request to batch orchestrator agent..."
BATCH_RESPONSE=$(curl -s -X POST "$AGENTS_URL/v1/agents/run" \
  -H "Content-Type: application/json" \
  -d @"$OUTPUT_DIR/batch_request.json" 2>&1)

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
DURATION_MIN=$((DURATION / 60))
DURATION_SEC=$((DURATION % 60))

echo ""
echo "$BATCH_RESPONSE" > "$OUTPUT_DIR/batch_response.json"

# Check if successful
STATUS=$(echo "$BATCH_RESPONSE" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("status", "failed"))' 2>/dev/null || echo "failed")

if [[ "$STATUS" == "completed" ]]; then
    log_success "Batch processing completed in ${DURATION_MIN}m ${DURATION_SEC}s"
    echo ""

    # Extract and display summary
    log_info "Summary Statistics:"
    python3 << PYEOF
import json

with open("$OUTPUT_DIR/batch_response.json") as f:
    response = json.load(f)

result = response.get("result", {})
report = result.get("report", {})
summary = report.get("summary", {})

print(f"  Documents processed:    {summary.get('total_documents', 0)}")
print(f"  Total questions:        {summary.get('total_questions', 0)}")
print(f"  Critical questions:     {summary.get('critical_questions', 0)}")
print(f"  Administrative:         {summary.get('administrative_questions', 0)}")
print(f"  Questions answered:     {summary.get('answered_questions', 0)}")
print(f"  Questions unanswered:   {summary.get('unanswered_questions', 0)}")
answer_rate = summary.get('answer_rate', 0)
print(f"  Answer rate:            {answer_rate}%")
PYEOF

    echo ""

    # Get report file path
    REPORT_FILE=$(echo "$BATCH_RESPONSE" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("result", {}).get("report_file", ""))' 2>/dev/null || echo "")

    if [[ -n "$REPORT_FILE" ]] && [[ -f "$REPORT_FILE" ]]; then
        log_success "Detailed report: $REPORT_FILE"

        # Generate CSV if possible
        log_progress "Generating CSV export..."
        CSV_FILE="${REPORT_FILE%.json}.csv"

        python3 << PYEOF
import json
import csv

with open("$REPORT_FILE") as f:
    report = json.load(f)

# Write answered questions to CSV
with open("$CSV_FILE", "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow([
        "Source Document",
        "Question",
        "Question Type",
        "Answered",
        "Confidence",
        "Completeness",
        "Evidence",
        "Summary"
    ])

    for validation in report.get("answered_questions", []):
        evidence = ", ".join([e.get("document", "") for e in validation.get("evidence", [])])
        writer.writerow([
            validation.get("source_document", ""),
            validation.get("question", "")[:100],
            validation.get("question_type", ""),
            "Yes",
            validation.get("confidence", 0),
            validation.get("completeness", ""),
            evidence,
            validation.get("summary", "")[:200]
        ])

    for validation in report.get("unanswered_questions", []):
        writer.writerow([
            validation.get("source_document", ""),
            validation.get("question", "")[:100],
            validation.get("question_type", ""),
            "No",
            validation.get("confidence", 0),
            validation.get("completeness", "incomplete"),
            "",
            validation.get("summary", "")[:200]
        ])

print(f"CSV exported: $CSV_FILE")
PYEOF

        log_success "CSV export: $CSV_FILE"
    fi

    echo ""
    echo -e "${GREEN}"
    echo "════════════════════════════════════════════════════════════════════════════════"
    echo "  ✓ Batch Processing Complete"
    echo "════════════════════════════════════════════════════════════════════════════════"
    echo -e "${NC}"
    echo ""
    log_info "Output files:"
    echo "  • Detailed report (JSON): $REPORT_FILE"
    echo "  • CSV export:             $CSV_FILE"
    echo "  • Batch response:         $OUTPUT_DIR/batch_response.json"
    echo "  • Batch request:          $OUTPUT_DIR/batch_request.json"
    echo ""

else
    log_error "Batch processing failed"
    echo ""

    ERROR_MSG=$(echo "$BATCH_RESPONSE" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("error", "Unknown error"))' 2>/dev/null || echo "Failed to parse response")
    log_error "Error: $ERROR_MSG"
    echo ""
    log_info "Debug info saved to:"
    echo "  • $OUTPUT_DIR/batch_response.json"
    echo "  • $OUTPUT_DIR/batch_request.json"
    exit 1
fi
