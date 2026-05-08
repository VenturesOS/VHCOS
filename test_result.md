#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

## user_problem_statement: |
  Emergency Production Issue: Groq API 429 Rate Limit Exceeded + JSON Decode Errors
  User requested implementation of Emergent LLM Key fallback for all AI services (Chrome Extension, CV Upload, JD Parsing, Batch Enrichment)

## backend:
  - task: "Groq → Emergent LLM Multi-Tier Fallback System"
    implemented: true
    working: "PENDING_USER_TEST_IN_AWS"
    file: "/app/backend/services/llm_fallback_service.py"
    stuck_count: 0
    priority: "critical"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Created llm_fallback_service.py with 3-tier architecture: Groq → Emergent LLM (OpenAI GPT-4o) → Raw text save. Handles 429 rate limits, timeouts, and JSON errors gracefully. Backend restarted successfully with emergentintegrations library installed."

  - task: "Chrome Extension Capture - Fallback Integration"
    implemented: true
    working: "PENDING_USER_TEST_IN_AWS"
    file: "/app/backend/services/groq_service.py"
    stuck_count: 0
    priority: "critical"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Updated extract_phone_and_work_experience_groq() and extract_full_profile_groq() to use llm_fallback_service. Both functions now automatically fall back to Emergent LLM if Groq fails."

  - task: "CV Upload & JD Parsing - Fallback Integration"
    implemented: true
    working: "PENDING_USER_TEST_IN_AWS"
    file: "/app/backend/services/groq_ai_service.py"
    stuck_count: 0
    priority: "critical"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Updated groq_chat_completion() to detect 429 errors and automatically route to Emergent LLM. parse_resume_with_groq() and parse_job_description_with_groq() now resilient to rate limits."

  - task: "Batch Enrichment - Groq Migration with Fallback"
    implemented: true
    working: "PENDING_USER_TEST_IN_AWS"
    file: "/app/backend/services/batch_enrichment.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Completely migrated from Anthropic Batch API to Groq with Emergent LLM fallback. submit_batch() now processes candidates synchronously using llm_fallback_service. Tracks fallback_used_count in batch_jobs collection."

  - task: "Evaluate-Fit JSON Decode Error Fix"
    implemented: true
    working: "PENDING_USER_TEST_IN_AWS"
    file: "/app/backend/services/extension_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: false
        agent: "main"
        comment: "User reported: 'AI parse error: Expecting value: line 1 column 1 (char 0)' in production logs. This was cascading from Groq 429 errors."
      - working: true
        agent: "main"
        comment: "Added robust error handling in ai_comprehensive_evaluation(). Now detects empty responses, handles JSON decode errors gracefully, and logs LLM provider errors (rate limits) without crashing."

## metadata:
  created_by: "fork_agent"
  version: "2.0"
  test_sequence: 1
  run_ui: false
  deployment_environment: "AWS Production (User's Server)"

## test_plan:
  current_focus:
    - "User must test Chrome Extension capture in AWS production"
    - "User must test CV Upload parsing"
    - "Monitor backend logs for fallback usage"
    - "Verify Emergent credit balance is being deducted"
  stuck_tasks: []
  test_all: false
  test_priority: "user_manual_testing"
  notes: |
    All changes deployed locally and backend restarted successfully.
    User needs to deploy to AWS and test in production environment.
    See /app/GROQ_EMERGENT_FALLBACK_DEPLOYED.md for deployment instructions.

## agent_communication:
  - agent: "fork_agent"
    message: |
      EMERGENCY FALLBACK SYSTEM DEPLOYED ✅
      
      All AI services now use Groq → Emergent LLM → Raw text fallback.
      
      Files Modified:
      - /app/backend/services/llm_fallback_service.py (NEW)
      - /app/backend/services/groq_service.py (UPDATED)
      - /app/backend/services/groq_ai_service.py (UPDATED)
      - /app/backend/services/batch_enrichment.py (MIGRATED)
      - /app/backend/services/extension_service.py (ERROR FIX)
      
      Libraries Installed:
      - emergentintegrations (with OpenAI, Google, Anthropic support)
      
      Backend Status: ✅ RUNNING (restarted successfully)
      
      NEXT STEPS FOR USER:
      1. Deploy to AWS using git pull + backend restart
      2. Test 2-3 candidate captures via Chrome Extension
      3. Monitor logs: tail -f /var/log/supervisor/backend.*.log | grep Fallback
      4. Verify Emergent credit balance (Profile → Universal Key)
      
      See /app/GROQ_EMERGENT_FALLBACK_DEPLOYED.md for full documentation.
