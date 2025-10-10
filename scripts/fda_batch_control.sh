#!/bin/bash
# FDA Batch Processing Control Script
# Provides stop/resume/status commands for batch jobs

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BATCH_DIR="${BATCH_DIR:-/tmp/fda_batch}"
STOP_SIGNAL="$BATCH_DIR/STOP_BATCH"
STATE_FILE="$BATCH_DIR/batch_state.json"

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ ${NC}$1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

# Command: stop
stop_batch() {
    log_info "Sending stop signal to batch processing..."

    mkdir -p "$BATCH_DIR"
    touch "$STOP_SIGNAL"

    log_success "Stop signal created: $STOP_SIGNAL"
    log_info "The batch will stop gracefully after completing the current document"
    log_info "State will be saved and you can resume later"
}

# Command: resume
resume_batch() {
    log_info "Preparing to resume batch processing..."

    if [[ ! -f "$STATE_FILE" ]]; then
        log_error "No state file found at $STATE_FILE"
        log_info "Nothing to resume. Start a new batch instead."
        exit 1
    fi

    # Check if stop signal exists
    if [[ -f "$STOP_SIGNAL" ]]; then
        rm -f "$STOP_SIGNAL"
        log_success "Cleared stop signal"
    fi

    # Get batch info
    BATCH_ID=$(jq -r '.batch_id' "$STATE_FILE")
    PROCESSED=$(jq -r '.processed_documents' "$STATE_FILE")
    TOTAL=$(jq -r '.total_documents' "$STATE_FILE")

    log_info "Batch ID: $BATCH_ID"
    log_info "Progress: $PROCESSED/$TOTAL documents completed"
    log_info "Remaining: $((TOTAL - PROCESSED)) documents"

    echo ""
    log_warning "Resuming batch processing..."
    echo ""

    # Call the batch processing script with resume flag
    ./lf agents run fda_batch_orchestrator --input-json "{\"resume\": true}"
}

# Command: status
show_status() {
    if [[ ! -f "$STATE_FILE" ]]; then
        log_info "No active batch found"
        log_info "State file: $STATE_FILE"
        exit 0
    fi

    # Parse state file
    BATCH_ID=$(jq -r '.batch_id' "$STATE_FILE")
    PROCESSED=$(jq -r '.processed_documents' "$STATE_FILE")
    TOTAL=$(jq -r '.total_documents' "$STATE_FILE")
    STATUS=$(jq -r '.status' "$STATE_FILE")
    STARTED=$(jq -r '.started_at' "$STATE_FILE")
    UPDATED=$(jq -r '.updated_at' "$STATE_FILE")

    # Calculate progress
    PERCENT=$((PROCESSED * 100 / TOTAL))
    REMAINING=$((TOTAL - PROCESSED))

    # Format timestamps
    STARTED_DATE=$(date -r "$STARTED" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "Unknown")
    UPDATED_DATE=$(date -r "$UPDATED" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "Unknown")

    # Check if stop signal exists
    if [[ -f "$STOP_SIGNAL" ]]; then
        STOP_STATUS="${RED}STOP REQUESTED${NC}"
    else
        STOP_STATUS="${GREEN}RUNNING${NC}"
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${BLUE}FDA BATCH PROCESSING STATUS${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Batch ID:      $BATCH_ID"
    echo -e "Status:        $STOP_STATUS"
    echo "Progress:      $PROCESSED/$TOTAL documents ($PERCENT%)"
    echo "Remaining:     $REMAINING documents"
    echo ""
    echo "Started:       $STARTED_DATE"
    echo "Last Updated:  $UPDATED_DATE"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Show recent results
    echo ""
    log_info "Recent results:"
    echo ""

    # Get stats from results
    TOTAL_QUESTIONS=$(jq '[.results[].questions | length] | add // 0' "$STATE_FILE")
    TOTAL_ANSWERED=$(jq '[.results[].stats.answered // 0] | add // 0' "$STATE_FILE")
    TOTAL_UNANSWERED=$(jq '[.results[].stats.unanswered // 0] | add // 0' "$STATE_FILE")

    echo "  Questions Extracted: $TOTAL_QUESTIONS"
    echo "  Answered:            $TOTAL_ANSWERED"
    echo "  Unanswered:          $TOTAL_UNANSWERED"
    echo ""

    # Show interim files
    INTERIM_FILES=$(ls -1 "$BATCH_DIR/${BATCH_ID}_doc_"*.json 2>/dev/null | wc -l)
    if [[ $INTERIM_FILES -gt 0 ]]; then
        log_info "Interim reports: $INTERIM_FILES files"
        log_info "Location: $BATCH_DIR/${BATCH_ID}_doc_*.json"
    fi

    echo ""
}

# Command: clean
clean_batch() {
    log_warning "Cleaning batch state..."

    if [[ -f "$STOP_SIGNAL" ]]; then
        rm -f "$STOP_SIGNAL"
        log_success "Removed stop signal"
    fi

    if [[ -f "$STATE_FILE" ]]; then
        BATCH_ID=$(jq -r '.batch_id' "$STATE_FILE" 2>/dev/null || echo "unknown")

        # Ask for confirmation
        echo ""
        log_warning "This will delete:"
        echo "  - State file: $STATE_FILE"
        echo "  - All interim reports for batch: $BATCH_ID"
        echo ""
        read -p "Are you sure? (y/N) " -n 1 -r
        echo

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -f "$STATE_FILE"
            rm -f "$BATCH_DIR/${BATCH_ID}"_*.json 2>/dev/null || true
            log_success "Cleaned batch state"
        else
            log_info "Cancelled"
        fi
    else
        log_info "No state file to clean"
    fi
}

# Command: list-results
list_results() {
    log_info "Batch results in $BATCH_DIR:"
    echo ""

    # List all batch report files
    if ls "$BATCH_DIR"/batch_*_report.json 1> /dev/null 2>&1; then
        for report in "$BATCH_DIR"/batch_*_report.json; do
            BATCH_ID=$(basename "$report" | sed 's/_report.json$//')
            DOCS=$(jq -r '.summary.total_documents' "$report")
            QUESTIONS=$(jq -r '.summary.total_questions' "$report")
            ANSWERED=$(jq -r '.summary.answered_questions' "$report")

            echo "  📄 $BATCH_ID"
            echo "     Documents: $DOCS | Questions: $QUESTIONS | Answered: $ANSWERED"
            echo "     File: $report"
            echo ""
        done
    else
        log_info "No completed batches found"
    fi

    # List interim reports for current batch
    if [[ -f "$STATE_FILE" ]]; then
        BATCH_ID=$(jq -r '.batch_id' "$STATE_FILE")
        INTERIM_COUNT=$(ls -1 "$BATCH_DIR/${BATCH_ID}_doc_"*.json 2>/dev/null | wc -l)

        if [[ $INTERIM_COUNT -gt 0 ]]; then
            echo ""
            log_info "Current batch interim reports: $INTERIM_COUNT"
            log_info "Pattern: $BATCH_DIR/${BATCH_ID}_doc_*.json"
        fi
    fi
}

# Main command dispatcher
case "${1:-}" in
    stop)
        stop_batch
        ;;
    resume)
        resume_batch
        ;;
    status)
        show_status
        ;;
    clean)
        clean_batch
        ;;
    results|list)
        list_results
        ;;
    *)
        echo "FDA Batch Processing Control"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  stop     - Send stop signal (graceful shutdown after current document)"
        echo "  resume   - Resume stopped batch from last checkpoint"
        echo "  status   - Show current batch status and progress"
        echo "  results  - List all batch results and reports"
        echo "  clean    - Clean up batch state (WARNING: cannot resume after this)"
        echo ""
        echo "Examples:"
        echo "  $0 status          # Check current batch progress"
        echo "  $0 stop            # Stop batch gracefully"
        echo "  $0 resume          # Resume from where it stopped"
        echo ""
        exit 1
        ;;
esac
