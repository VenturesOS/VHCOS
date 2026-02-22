"""Generate Training Manual PDF"""
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, ListFlowable, ListItem, KeepTogether
)

NAVY = HexColor("#1a2744")
GREEN = HexColor("#2d6a4f")
ACCENT = HexColor("#40916c")
GRAY = HexColor("#6b7280")
LIGHT_BG = HexColor("#f0fdf4")
WHITE = HexColor("#ffffff")
TABLE_HEAD = HexColor("#1a2744")
TABLE_ALT = HexColor("#f8fafc")
BORDER = HexColor("#cbd5e1")

def build_pdf():
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle("DocTitle", parent=styles["Title"],
        fontSize=26, textColor=NAVY, spaceAfter=4*mm, alignment=TA_CENTER, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("DocSubtitle", parent=styles["Normal"],
        fontSize=12, textColor=GRAY, spaceAfter=8*mm, alignment=TA_CENTER))
    styles.add(ParagraphStyle("H1", parent=styles["Heading1"],
        fontSize=20, textColor=NAVY, spaceBefore=10*mm, spaceAfter=5*mm, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("H2", parent=styles["Heading2"],
        fontSize=15, textColor=GREEN, spaceBefore=7*mm, spaceAfter=3*mm, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("H3", parent=styles["Heading3"],
        fontSize=12, textColor=NAVY, spaceBefore=5*mm, spaceAfter=2*mm, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("Body", parent=styles["Normal"],
        fontSize=10, leading=15, spaceAfter=2*mm, textColor=HexColor("#1e293b")))
    styles.add(ParagraphStyle("BodyBold", parent=styles["Normal"],
        fontSize=10, leading=15, spaceAfter=2*mm, textColor=HexColor("#1e293b"), fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("Bullet", parent=styles["Normal"],
        fontSize=10, leading=15, leftIndent=12, spaceAfter=1*mm, textColor=HexColor("#1e293b")))
    styles.add(ParagraphStyle("SmallGray", parent=styles["Normal"],
        fontSize=8, textColor=GRAY, spaceAfter=1*mm))
    styles.add(ParagraphStyle("Tip", parent=styles["Normal"],
        fontSize=9.5, leading=14, leftIndent=10, textColor=HexColor("#065f46"),
        backColor=HexColor("#ecfdf5"), borderPadding=6, spaceAfter=3*mm))
    styles.add(ParagraphStyle("Mistake", parent=styles["Normal"],
        fontSize=9.5, leading=14, leftIndent=10, textColor=HexColor("#9a3412"),
        backColor=HexColor("#fff7ed"), borderPadding=6, spaceAfter=3*mm))
    styles.add(ParagraphStyle("Exercise", parent=styles["Normal"],
        fontSize=9.5, leading=14, leftIndent=10, textColor=HexColor("#1e40af"),
        backColor=HexColor("#eff6ff"), borderPadding=6, spaceAfter=3*mm))
    styles.add(ParagraphStyle("TOCItem", parent=styles["Normal"],
        fontSize=11, leading=18, textColor=NAVY, leftIndent=5))
    styles.add(ParagraphStyle("CheckItem", parent=styles["Normal"],
        fontSize=10, leading=15, leftIndent=12, spaceAfter=1.5*mm, textColor=HexColor("#1e293b")))

    story = []

    def heading(text, level=1):
        story.append(Paragraph(text, styles[f"H{level}"]))

    def body(text):
        story.append(Paragraph(text, styles["Body"]))

    def bold_body(text):
        story.append(Paragraph(text, styles["BodyBold"]))

    def bullet(text):
        story.append(Paragraph(f"&bull;  {text}", styles["Bullet"]))

    def numbered(num, text):
        story.append(Paragraph(f"<b>{num}.</b>  {text}", styles["Bullet"]))

    def tip(text):
        story.append(Paragraph(f"<b>Trainer Tip:</b> {text}", styles["Tip"]))

    def mistake(text):
        story.append(Paragraph(f"<b>Common Mistake:</b> {text}", styles["Mistake"]))

    def exercise(text):
        story.append(Paragraph(f"<b>Do This Now:</b> {text}", styles["Exercise"]))

    def check(text):
        story.append(Paragraph(f"[ ]  {text}", styles["CheckItem"]))

    def space(h=3):
        story.append(Spacer(1, h*mm))

    def table(headers, rows, col_widths=None):
        data = [headers] + rows
        w = col_widths or [doc.width / len(headers)] * len(headers)
        t = Table(data, colWidths=w, repeatRows=1)
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEAD),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('LEADING', (0, 0), (-1, -1), 13),
            ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]
        for i in range(1, len(data)):
            if i % 2 == 0:
                style_cmds.append(('BACKGROUND', (0, i), (-1, i), TABLE_ALT))
        t.setStyle(TableStyle(style_cmds))
        story.append(t)
        space(3)

    # ============ COVER PAGE ============
    story.append(Spacer(1, 40*mm))
    story.append(Paragraph("Ventures HRD", styles["DocTitle"]))
    story.append(Paragraph("Talent OS", styles["DocTitle"]))
    space(5)
    story.append(Paragraph("Portal Training Manual", ParagraphStyle("sub", parent=styles["DocSubtitle"], fontSize=16, textColor=GREEN)))
    space(10)
    story.append(Paragraph("Version 1.0  |  February 2026", styles["DocSubtitle"]))
    story.append(Paragraph("Internal Document — For Trainer &amp; Trainee Use", styles["DocSubtitle"]))
    story.append(Paragraph("Skill Level: Beginner", styles["DocSubtitle"]))
    story.append(Paragraph("Estimated Training Time: 4–5 hours per role", styles["DocSubtitle"]))
    story.append(PageBreak())

    # ============ TABLE OF CONTENTS ============
    heading("Table of Contents")
    for item in [
        "1.  Introduction",
        "2.  Quick Start Guide (15 Minutes)",
        "3.  Employer Training Guide (Modules E1–E10)",
        "4.  Recruiter Training Guide (Modules R1–R8)",
        "5.  Role Comparison Table",
        "6.  Trainer's Guide",
        "7.  Readiness Checklist",
        "8.  Frequently Asked Questions",
        "     Appendix: Suggested UI Tooltip Text",
    ]:
        story.append(Paragraph(item, styles["TOCItem"]))
    story.append(PageBreak())

    # ============ 1. INTRODUCTION ============
    heading("1. Introduction")

    heading("1.1 What Is Ventures HRD Talent OS?", 2)
    body("Ventures HRD Talent OS is a recruitment management portal designed for industrial hiring. It helps employers post jobs, track candidates through a structured hiring pipeline, and collaborate with recruiters — all from a single dashboard.")

    heading("1.2 Who Is This Training For?", 2)
    body("This manual is designed for two roles:")
    bullet("<b>Employers</b> — Team leaders or hiring managers who create jobs, review candidates, and make hiring decisions.")
    bullet("<b>Recruiters</b> — Sourcing professionals who find candidates, submit them to jobs, and move them through pipeline stages.")

    heading("1.3 What You Will Learn", 2)
    body("By the end of this training, you will be able to:")
    bullet("Log in and navigate the portal confidently")
    bullet("Understand your dashboard and its key sections")
    bullet("Perform your daily tasks without assistance")
    bullet("Track candidates through the hiring pipeline")
    bullet("Use the submission tracker to monitor progress")
    bullet("Avoid common mistakes that slow down your workflow")

    heading("1.4 What This Training Does NOT Cover", 2)
    body("This training focuses on foundational daily operations only. The following are excluded and will be covered in separate training:")
    bullet("AI-powered candidate screening and matching")
    bullet("Advanced search and filtering")
    bullet("Analytics deep-dives and automation workflows")
    bullet("Revenue intelligence and system administration")
    story.append(PageBreak())

    # ============ 2. QUICK START GUIDE ============
    heading("2. Quick Start Guide (15 Minutes)")
    body("Use this section to get someone operational immediately.")

    heading("2.1 Logging In", 2)
    numbered(1, "Open your browser and go to the portal URL provided by your administrator.")
    numbered(2, "Enter your <b>email address</b> in the Email field.")
    numbered(3, "Enter your <b>password</b> in the Password field.")
    numbered(4, "Click the <b>Login</b> button.")
    numbered(5, "You will be taken to your role-specific dashboard.")
    mistake("Using a personal email instead of the company email assigned to you. Your account is linked to the email your administrator registered.")
    tip("If you forget your password, use the 'Forgot Password' link on the login page.")

    heading("2.2 Dashboard Overview", 2)
    body("After logging in, you will see your Dashboard. This is your home base.")
    table(
        ["Area", "What It Shows"],
        [
            ["Left Sidebar", "Navigation menu — all portal sections listed here"],
            ["Main Content Area", "The page you are currently viewing"],
            ["Top Section", "Your name, role, and account options"],
        ],
        [doc.width*0.3, doc.width*0.7]
    )
    body("<b>The sidebar is your map.</b> If you ever feel lost, click Dashboard to return home.")

    heading("2.3 Key Navigation — Employers", 3)
    bullet("<b>Dashboard</b> — Overview of your hiring activity")
    bullet("<b>My Jobs</b> — All jobs you have created")
    bullet("<b>Post Job</b> — Create a new job listing")
    bullet("<b>Pipeline</b> — See where candidates are in the hiring process")
    bullet("<b>Trackers</b> — Detailed submission tracking spreadsheets")
    bullet("<b>My Team</b> — Your team members and their activity")
    bullet("<b>Companies</b> — Company profiles linked to your account")
    bullet("<b>Approvals</b> — Jobs awaiting your approval")

    heading("2.3 Key Navigation — Recruiters", 3)
    bullet("<b>Dashboard</b> — Overview of your sourcing activity")
    bullet("<b>Mandates</b> — Jobs assigned to you for sourcing")
    bullet("<b>Pipeline</b> — Candidates you are managing across stages")
    bullet("<b>Candidates</b> — Candidate profiles you are working with")
    bullet("<b>Candidate Bank</b> — Your searchable talent database")
    bullet("<b>Referrals</b> — Candidate referrals you have submitted")

    heading("2.4 Basic Daily Workflow", 2)
    table(
        ["Employer Daily Routine", "Recruiter Daily Routine"],
        [
            ["1. Check Dashboard for new activity", "1. Check Dashboard for assigned mandates"],
            ["2. Review pending job approvals", "2. Review Pipeline for status updates"],
            ["3. Check Pipeline for candidate updates", "3. Add new candidates sourced during the day"],
            ["4. Review Tracker for submission changes", "4. Update candidate stages as progress is made"],
            ["5. Take action on candidates", "5. Check Tracker for submission tracking updates"],
        ],
        [doc.width*0.5, doc.width*0.5]
    )
    story.append(PageBreak())

    # ============ 3. EMPLOYER TRAINING GUIDE ============
    heading("3. Employer Training Guide")

    # E1
    heading("Module E1: Profile and Account Setup", 2)
    body("<b>Purpose:</b> Ensure your account is properly configured.  |  <b>Time:</b> 10 minutes")
    numbered(1, "After logging in, locate your name at the bottom of the left sidebar.")
    numbered(2, "Note your role displayed below your name (it should show 'Employer').")
    numbered(3, "Verify your email address is correct.")
    mistake("Assuming someone else will set up your account. Each user should verify their own profile immediately after first login.")
    tip("Have each trainee log in on their own device during training. Walk the room to verify everyone sees the correct role.")

    # E2
    heading("Module E2: Company Profile", 2)
    body("<b>Purpose:</b> Your company profile is what candidates and recruiters see.  |  <b>Time:</b> 15 minutes")
    numbered(1, "Click <b>Companies</b> in the left sidebar.")
    numbered(2, "You will see a list of companies assigned to your account.")
    numbered(3, "Click on a company name to view its details.")
    numbered(4, "Review Company Name, Industry, and other details.")
    numbered(5, "If information needs updating, contact your administrator.")
    mistake("Trying to create a new company directly. Companies are created and assigned by the system administrator.")
    tip("Show trainees where company information appears to candidates on job listings, so they understand why accuracy matters.")

    # E3
    heading("Module E3: Creating a Job Listing", 2)
    body("<b>Purpose:</b> The most important employer task. Every hiring process starts here.  |  <b>Time:</b> 20 minutes")
    numbered(1, "Click <b>Post Job</b> in the left sidebar.")
    numbered(2, "Fill in all required fields (see table below).")
    numbered(3, "Review all fields carefully.")
    numbered(4, "Click <b>Submit</b> or <b>Create Job</b>.")
    numbered(5, "The job may go to 'Pending Approval' status depending on settings.")
    space(2)
    table(
        ["Field", "What to Enter", "Example"],
        [
            ["Title", "The job position name", "Production Manager"],
            ["Description", "Detailed role description", "Free-text, be thorough"],
            ["Company", "Select from dropdown", "—"],
            ["Location", "Where the job is based", "Gurgaon, Haryana"],
            ["Job Type", "Employment type", "Full-time / Part-time / Contract / Remote"],
            ["Salary Min / Max", "Salary range (optional)", "800000 / 1200000"],
            ["Experience Min / Max", "Years required", "5 / 10"],
            ["Public Company Alias", "Masked name for candidates", "Leading Steel Manufacturer"],
        ],
        [doc.width*0.25, doc.width*0.4, doc.width*0.35]
    )
    exercise("Create a test job: Title 'Test Engineer — Training Exercise', Location 'Delhi', Full-time, 3–5 years experience. Verify it appears in My Jobs.")
    mistake("Leaving the description empty. A detailed description attracts better candidates. Also: forgetting to set the Public Company Alias when confidentiality is needed.")
    tip("Create one job together as a group exercise, then have each trainee create their own.")

    # E4
    heading("Module E4: Editing a Job", 2)
    body("<b>Purpose:</b> Update jobs after creation.  |  <b>Time:</b> 10 minutes")
    numbered(1, "Click <b>My Jobs</b> in the left sidebar.")
    numbered(2, "Find and click the job to open its detail view.")
    numbered(3, "Click the <b>Edit</b> button.")
    numbered(4, "Make changes and click <b>Save</b>.")
    space(2)
    table(
        ["Status", "Meaning"],
        [
            ["Draft", "Saved but not yet submitted"],
            ["Pending Approval", "Submitted, waiting for admin approval"],
            ["Active", "Live — candidates can be added"],
            ["On Hold", "Temporarily paused"],
            ["Closed", "Hiring complete, no new candidates"],
            ["Archived", "Stored for records, no longer visible"],
        ],
        [doc.width*0.3, doc.width*0.7]
    )
    mistake("Editing a closed job and expecting candidates to appear. Reopen it (set to Active) first.")

    # E5
    heading("Module E5: Understanding the Pipeline", 2)
    body("<b>Purpose:</b> The pipeline is the heart of the portal.  |  <b>Time:</b> 20 minutes")
    body("Every candidate moves through these 7 stages:")
    table(
        ["#", "Stage", "What Happens Here"],
        [
            ["1", "Applied", "Candidate has been added or applied to the job"],
            ["2", "Shortlisted", "Recruiter has reviewed and shortlisted"],
            ["3", "Submitted to Client", "Profile sent to employer for review"],
            ["4", "Interview", "Candidate is in the interview process"],
            ["5", "Offered", "An offer has been extended"],
            ["6", "Hired", "Candidate has accepted the offer"],
            ["7", "Joined", "Candidate has started working"],
        ],
        [doc.width*0.06, doc.width*0.25, doc.width*0.69]
    )
    body("<b>Additional Statuses:</b> Rejected (not selected) and On Hold (decision paused) — can happen at any stage.")
    exercise("Open Pipeline and answer: How many in Interview? Which job has most in Submitted to Client? Anyone On Hold?")
    mistake("Confusing 'Hired' with 'Joined.' Hired = offer accepted. Joined = person started work. Both must be updated.")
    tip("Project the Pipeline on screen and walk through 2–3 real candidates.")

    # E6
    heading("Module E6: Managing Applicants", 2)
    body("<b>Purpose:</b> Take action on candidates.  |  <b>Time:</b> 15 minutes")
    numbered(1, "Click on a candidate from Pipeline or Job detail view.")
    numbered(2, "Review: name, email, phone, resume, current stage, notes.")
    numbered(3, "To advance: select the next stage and confirm.")
    numbered(4, "To reject: select 'Rejected' from stage options.")
    numbered(5, "To pause: select 'On Hold.'")
    mistake("Moving a candidate forward without reviewing their resume. Also: leaving candidates in limbo instead of rejecting.")
    tip("Show: open profile → read resume → make decision → move stage. Have each trainee do it once.")

    # E7
    heading("Module E7: Using the Submission Tracker", 2)
    body("<b>Purpose:</b> Spreadsheet view of all submissions.  |  <b>Time:</b> 15 minutes")
    numbered(1, "Click <b>Trackers</b> in the left sidebar.")
    numbered(2, "Click on a tracker to open the spreadsheet grid.")
    numbered(3, "Review columns: Candidate Name, Job, Stage, Date, Status, Notes.")
    numbered(4, "Click any row to see full details.")
    space(2)
    table(
        ["Feature", "Pipeline", "Tracker"],
        [
            ["View Type", "Visual board (cards)", "Spreadsheet (rows & columns)"],
            ["Best For", "Quick status overview", "Detailed data review"],
            ["Actions", "Move candidates between stages", "View and filter data"],
        ],
        [doc.width*0.2, doc.width*0.4, doc.width*0.4]
    )
    mistake("Thinking Pipeline and Tracker are the same. Use Pipeline for actions, Tracker for detailed review.")

    # E8
    heading("Module E8: My Team", 2)
    body("<b>Purpose:</b> View team members and activity.  |  <b>Time:</b> 10 minutes")
    numbered(1, "Click <b>My Team</b> in the sidebar.")
    numbered(2, "View: name, email, role, assigned companies, activity metrics.")
    mistake("Expecting to add/remove team members yourself. Team assignments are managed by admin.")

    # E9
    heading("Module E9: Approvals", 2)
    body("<b>Purpose:</b> Review pending items.  |  <b>Time:</b> 10 minutes")
    numbered(1, "Click <b>Approvals</b> in the sidebar.")
    numbered(2, "Click on an item to review it.")
    numbered(3, "Choose to Approve or Reject.")
    mistake("Ignoring Approvals. Pending items block recruiters. Check at least once a day.")

    # E10
    heading("Module E10: Notifications and Daily Routine", 2)
    body("<b>Purpose:</b> Stay informed.  |  <b>Time:</b> 10 minutes")
    table(
        ["Time", "Action"],
        [
            ["Start of Day", "Check Dashboard for overnight updates"],
            ["Mid-Day", "Review Pipeline for new submissions"],
            ["End of Day", "Check Approvals queue, clear pending items"],
        ],
        [doc.width*0.25, doc.width*0.75]
    )
    tip("Have each trainee write down their daily check routine. Habits beat training.")
    story.append(PageBreak())

    # ============ 4. RECRUITER TRAINING GUIDE ============
    heading("4. Recruiter Training Guide")

    # R1
    heading("Module R1: Account Setup and First Login", 2)
    body("<b>Purpose:</b> Get your account ready.  |  <b>Time:</b> 10 minutes")
    numbered(1, "Open the portal URL and log in with your email and password.")
    numbered(2, "Verify 'Recruiter' appears below your name in the sidebar.")
    numbered(3, "Click through each sidebar item to explore.")
    tip("Give trainees 3 minutes of free exploration. Then ask: 'How many sidebar items do you have?'")

    # R2
    heading("Module R2: Dashboard Navigation", 2)
    body("<b>Purpose:</b> Use the dashboard as your daily control center.  |  <b>Time:</b> 10 minutes")
    table(
        ["Section", "Purpose"],
        [
            ["Active Mandates", "Jobs currently assigned to you"],
            ["Pipeline Summary", "Quick counts of candidates in each stage"],
            ["Recent Activity", "Latest actions taken by you or on your candidates"],
        ],
        [doc.width*0.3, doc.width*0.7]
    )
    exercise("From your dashboard, answer: How many jobs assigned to you? How many candidates in Interview stage?")
    mistake("Treating the Dashboard as just a home screen. It is your daily briefing.")

    # R3
    heading("Module R3: Understanding Mandates", 2)
    body("<b>Purpose:</b> Mandates are jobs assigned to you — your primary work items.  |  <b>Time:</b> 15 minutes")
    numbered(1, "Click <b>Mandates</b> in the sidebar.")
    numbered(2, "Review each mandate: title, company, location, type, experience, salary, description.")
    numbered(3, "Click on a mandate to see full details.")
    numbered(4, "Note the number of candidates already submitted.")
    space(2)
    body("<b>Real-World Example:</b> You see 'Plant Head — Leading Steel Manufacturer — Gurgaon — 15–20 years.' Your task: read the full description, note key requirements, begin sourcing matching candidates.")
    mistake("Starting to source without fully reading the job description. This leads to mismatched submissions.")
    tip("Open one mandate together. Read aloud. Ask: 'What are the 3 most important requirements here?'")

    # R4
    heading("Module R4: Adding Candidates Manually", 2)
    body("<b>Purpose:</b> Add sourced candidates to the system.  |  <b>Time:</b> 20 minutes")
    numbered(1, "Click <b>Candidate Bank</b> in the sidebar.")
    numbered(2, "Click <b>Add Candidate</b>.")
    numbered(3, "Fill in candidate details (see table below).")
    numbered(4, "Click <b>Save</b>.")
    space(2)
    table(
        ["Field", "What to Enter", "Required?"],
        [
            ["Full Name", "Candidate's complete name", "Yes"],
            ["Email", "Candidate's email address", "Yes"],
            ["Phone", "Mobile number", "Yes"],
            ["Current Company", "Where they work now", "Recommended"],
            ["Current Designation", "Current job title", "Recommended"],
            ["Experience (Years)", "Total work experience", "Recommended"],
            ["Current Location", "Where they are based", "Recommended"],
            ["Current / Expected CTC", "Annual compensation", "Recommended"],
            ["Notice Period", "How soon they can join", "Recommended"],
            ["Resume", "Upload CV (PDF/DOC/DOCX, max 5MB)", "Highly Recommended"],
        ],
        [doc.width*0.28, doc.width*0.47, doc.width*0.25]
    )
    exercise("Add a test candidate: 'Training Test Candidate', test.candidate@training.com, 9999900000, 5 years, Delhi. Verify in Candidate Bank.")
    mistake("Uploading unsupported format (only PDF, DOC, DOCX). File too large (max 5MB). Duplicate email. Skipping phone number.")

    # R5
    heading("Module R5: Moving Candidates Through Stages", 2)
    body("<b>Purpose:</b> Your most frequent daily task.  |  <b>Time:</b> 20 minutes")
    body("Pipeline flow: <b>Applied → Shortlisted → Submitted to Client → Interview → Offered → Hired → Joined</b>")
    body("Parallel statuses: <b>Rejected</b> and <b>On Hold</b> can happen at any stage.")
    space(2)
    table(
        ["Transition", "When to Do It"],
        [
            ["Applied → Shortlisted", "Resume reviewed, candidate is a potential fit"],
            ["Shortlisted → Submitted to Client", "Sending profile to employer for review"],
            ["Submitted to Client → Interview", "Employer wants to interview"],
            ["Interview → Offered", "Employer extending an offer"],
            ["Offered → Hired", "Candidate accepted the offer"],
            ["Hired → Joined", "Candidate started work"],
            ["Any → Rejected", "Candidate not moving forward"],
            ["Any → On Hold", "Decision pending"],
        ],
        [doc.width*0.4, doc.width*0.6]
    )
    exercise("Move the test candidate through: Applied → Shortlisted → Submitted to Client → Interview. Verify after each move.")
    mistake("Skipping stages. Forgetting to update after a phone call. Leaving candidates in 'Submitted to Client' for weeks.")
    tip("This is the most critical module. Spend extra time here. Have each trainee move a candidate through 3 stages.")

    # R6
    heading("Module R6: Submission Tracking", 2)
    body("<b>Purpose:</b> Detailed spreadsheet view of submissions.  |  <b>Time:</b> 15 minutes")
    numbered(1, "Navigate to the relevant tracker.")
    numbered(2, "Review the spreadsheet grid: each row is a submission.")
    numbered(3, "Click any row for full details.")
    space(2)
    table(
        ["Need", "Use"],
        [
            ["Quick stage update", "Pipeline"],
            ["Detailed submission review", "Tracker"],
            ["Moving candidates", "Pipeline"],
            ["Weekly reporting", "Tracker"],
        ],
        [doc.width*0.4, doc.width*0.6]
    )
    mistake("Trying to move candidates from the Tracker. Use Pipeline for stage changes.")

    # R7
    heading("Module R7: Working with Referrals", 2)
    body("<b>Purpose:</b> Track candidates you have referred.  |  <b>Time:</b> 10 minutes")
    numbered(1, "Click <b>Referrals</b> in the sidebar.")
    numbered(2, "View: candidate name, job/mandate, current stage, date.")
    mistake("Confusing referrals with regular additions. A referral is specifically tied to a mandate submission.")

    # R8
    heading("Module R8: Daily Workflow", 2)
    body("<b>Purpose:</b> Establish an efficient daily routine.  |  <b>Time:</b> 10 minutes")
    table(
        ["Time", "Task", "Where"],
        [
            ["9:00 AM", "Check Dashboard for new mandates", "Dashboard"],
            ["9:15 AM", "Review Pipeline for overnight changes", "Pipeline"],
            ["9:30 AM", "Follow up on Submitted to Client candidates", "Pipeline"],
            ["10 AM – 4 PM", "Source and add new candidates", "Candidate Bank"],
            ["4:00 PM", "Update all candidate stages", "Pipeline"],
            ["4:30 PM", "Review Tracker for missed updates", "Tracker"],
            ["5:00 PM", "Check Dashboard before logging off", "Dashboard"],
        ],
        [doc.width*0.2, doc.width*0.5, doc.width*0.3]
    )
    heading("Quick Tips for Efficiency", 3)
    numbered(1, "Update stages immediately — do not batch to end of day.")
    numbered(2, "Add notes when moving candidates.")
    numbered(3, "Check Candidate Bank before sourcing externally.")
    numbered(4, "Keep candidate contact info current.")
    numbered(5, "Do not leave candidates in limbo for more than a week.")
    story.append(PageBreak())

    # ============ 5. ROLE COMPARISON TABLE ============
    heading("5. Role Comparison Table")
    table(
        ["Capability", "Employer", "Recruiter"],
        [
            ["Dashboard", "Hiring overview", "Sourcing overview"],
            ["Create Jobs", "Yes (may need approval)", "Yes (may need approval)"],
            ["Edit Jobs", "Yes (own jobs)", "Yes (assigned jobs)"],
            ["Delete Jobs", "Yes (own jobs)", "No"],
            ["View Pipeline", "Own jobs and team", "Assigned mandates"],
            ["Move Candidates", "Yes", "Yes"],
            ["Add to Candidate Bank", "Yes", "Yes"],
            ["Upload Resumes", "Yes", "Yes"],
            ["View Tracker", "All team trackers", "Assigned trackers"],
            ["Create Trackers", "No", "Yes"],
            ["Manage Team", "View only", "Not available"],
            ["View Companies", "Assigned companies", "Not available"],
            ["Approve Jobs", "Yes (if active)", "No"],
            ["Referrals", "Not available", "Yes"],
            ["View Analytics", "Yes", "Not available"],
        ],
        [doc.width*0.3, doc.width*0.35, doc.width*0.35]
    )
    body("<b>Key Difference:</b> Employers are decision-makers (create jobs, approve/reject). Recruiters are executors (source candidates, manage pipeline). Both rely on each other.")
    story.append(PageBreak())

    # ============ 6. TRAINER'S GUIDE ============
    heading("6. Trainer's Guide")

    heading("6.1 Pre-Training Checklist", 2)
    check("All trainee accounts are created and active")
    check("All trainees have received login credentials via email")
    check("At least 2–3 test jobs exist in the system")
    check("At least 5–10 test candidates exist in Candidate Bank")
    check("Training room has stable internet and projector/screen")
    check("Each trainee has a laptop or computer with a browser")

    heading("6.2 Recommended 1-Day Schedule", 2)
    bold_body("Morning Session (3 hours)")
    table(
        ["Time", "Module", "Duration", "Activity"],
        [
            ["09:00–09:15", "Welcome", "15 min", "Introduce portal, purpose, agenda"],
            ["09:15–09:30", "Quick Start", "15 min", "Everyone logs in, dashboard tour"],
            ["09:30–10:00", "Module 1", "30 min", "Profile & account verification"],
            ["10:00–10:15", "Break", "15 min", "—"],
            ["10:15–10:45", "Module 2", "30 min", "Emp: Company+Jobs / Rec: Mandates+Bank"],
            ["10:45–11:15", "Module 3", "30 min", "Emp: Applicants / Rec: Adding Candidates"],
            ["11:15–12:00", "Module 4", "45 min", "Both: Pipeline deep-dive (hands-on)"],
        ],
        [doc.width*0.16, doc.width*0.14, doc.width*0.12, doc.width*0.58]
    )
    bold_body("Lunch Break: 12:00 – 13:00")
    bold_body("Afternoon Session (2.5 hours)")
    table(
        ["Time", "Module", "Duration", "Activity"],
        [
            ["13:00–13:30", "Module 5", "30 min", "Submission Tracker"],
            ["13:30–14:00", "Module 6", "30 min", "Daily workflow & quick tips"],
            ["14:00–14:15", "Break", "15 min", "—"],
            ["14:15–15:00", "Practice", "45 min", "Independent exercises, trainer observes"],
            ["15:00–15:30", "Wrap-Up", "30 min", "Readiness checklist, Q&A, distribute manual"],
        ],
        [doc.width*0.16, doc.width*0.14, doc.width*0.12, doc.width*0.58]
    )
    body("<b>Employers:</b> E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9 → E10")
    body("<b>Recruiters:</b> R1 → R2 → R3 → R4 → R5 → R6 → R7 → R8")

    heading("6.3 Practice Exercises", 2)
    bold_body("Employer Exercises")
    numbered(1, "Create a job with all required fields (10 min)")
    numbered(2, "Edit the job — change location, add description (5 min)")
    numbered(3, "Open Pipeline — identify candidates per stage (5 min)")
    numbered(4, "Move a candidate to the next stage (5 min)")
    numbered(5, "Open Tracker — find a submission status (5 min)")
    numbered(6, "Check Approvals queue (3 min)")
    space(2)
    bold_body("Recruiter Exercises")
    numbered(1, "Add a new candidate with full details (10 min)")
    numbered(2, "Find the candidate in Candidate Bank (3 min)")
    numbered(3, "View an assigned mandate and read description (5 min)")
    numbered(4, "Move a candidate through 3 stages (10 min)")
    numbered(5, "Open a Tracker and read all columns (5 min)")
    numbered(6, "Write down daily workflow schedule (5 min)")

    heading("6.4 Common Onboarding Issues", 2)
    table(
        ["Issue", "Solution"],
        [
            ["Can't log in", "Verify email matches admin registration. Use 'Forgot Password'."],
            ["No jobs visible", "Jobs must be created/assigned. Check team/company assignment with admin."],
            ["Can't create a job", "Verify correct role and permissions."],
            ["Pipeline is empty", "No candidates added yet — normal for new accounts."],
            ["Resume upload error", "Check format (PDF/DOC/DOCX only) and size (max 5MB)."],
            ["Wrong stage move", "Contact admin to correct. Double-check before confirming."],
            ["Can't see team", "Recruiters don't have My Team access — this is expected."],
        ],
        [doc.width*0.3, doc.width*0.7]
    )
    story.append(PageBreak())

    # ============ 7. READINESS CHECKLIST ============
    heading("7. Readiness Checklist")
    body("All items must be checked before the trainee is cleared for live work.")

    heading("Employer Readiness", 2)
    check("Can log in independently")
    check("Knows where all sidebar sections are")
    check("Has reviewed their company profile")
    check("Has successfully created at least 1 job")
    check("Has successfully edited a job")
    check("Can explain all 7 pipeline stages")
    check("Has moved at least 1 candidate between stages")
    check("Has opened and read a Tracker")
    check("Knows to check Approvals daily")
    check("Has written down their daily workflow routine")
    check("Knows who to contact for technical support")
    space(5)
    body("<b>Cleared by Trainer:</b> _______________________     <b>Date:</b> _______________")

    heading("Recruiter Readiness", 2)
    check("Can log in independently")
    check("Knows where all sidebar sections are")
    check("Has reviewed their assigned mandates")
    check("Has successfully added at least 1 candidate to Candidate Bank")
    check("Has uploaded a resume successfully")
    check("Can explain all 7 pipeline stages")
    check("Has moved at least 1 candidate through 3 stages")
    check("Has opened and read a Tracker")
    check("Understands Pipeline vs. Tracker difference")
    check("Has written down their daily workflow routine")
    check("Knows who to contact for technical support")
    space(5)
    body("<b>Cleared by Trainer:</b> _______________________     <b>Date:</b> _______________")
    story.append(PageBreak())

    # ============ 8. FAQs ============
    heading("8. Frequently Asked Questions")

    heading("General", 2)
    bold_body("Q: Can I access the portal from my phone?")
    body("A: The portal is designed for desktop/laptop browsers. We recommend using a computer for the best experience.")
    bold_body("Q: What browser should I use?")
    body("A: Google Chrome (latest) is recommended. Firefox and Edge also work. Avoid Internet Explorer.")
    bold_body("Q: What happens if I close my browser?")
    body("A: Saved data is stored on the server. Unsaved form data will be lost. Always click Save/Submit before closing.")
    bold_body("Q: Can I undo a stage change?")
    body("A: Stage changes are logged and generally should not be undone. Contact your administrator if needed.")

    heading("Employer Questions", 2)
    bold_body("Q: Can I see which recruiter submitted a candidate?")
    body("A: Yes. The candidate profile and tracker show which recruiter submitted each candidate.")
    bold_body("Q: What does 'Public Company Alias' mean?")
    body("A: The company name candidates see on job listings. Use it to keep the actual company name confidential.")
    bold_body("Q: A job is stuck in 'Pending Approval.' What do I do?")
    body("A: Your administrator needs to approve it. Contact them directly or check status in My Jobs.")

    heading("Recruiter Questions", 2)
    bold_body("Q: What is the difference between Candidate Bank and Pipeline?")
    body("A: Candidate Bank is your talent database (all candidates). Pipeline shows only candidates actively assigned to a job and moving through stages.")
    bold_body("Q: Can I submit the same candidate to multiple jobs?")
    body("A: Yes. They will appear separately in each job's pipeline.")
    bold_body("Q: What file formats can I upload?")
    body("A: PDF, DOC, and DOCX only. Maximum file size is 5MB.")
    bold_body("Q: Can I delete a candidate added by mistake?")
    body("A: Generally no, to maintain data integrity. Contact your administrator for duplicates or test records.")
    story.append(PageBreak())

    # ============ APPENDIX ============
    heading("Appendix: Suggested UI Tooltip Text")
    body("The following text can be added to the portal interface for contextual guidance.")
    table(
        ["UI Element", "Suggested Tooltip Text"],
        [
            ["Post Job button", "Create a new job listing. Fill in required fields and submit."],
            ["Job Title field", "Enter the position title. Example: Production Manager."],
            ["Public Company Alias", "Name shown to candidates instead of real company name."],
            ["Job Type dropdown", "Full-time, Part-time, Contract, or Remote."],
            ["Pipeline view", "Click candidates to view details or update their stage."],
            ["Stage: Applied", "Candidate added. Review profile to decide next steps."],
            ["Stage: Shortlisted", "Reviewed and marked as a potential fit."],
            ["Stage: Submitted to Client", "Profile sent to employer for review."],
            ["Stage: Interview", "In the interview process with the employer."],
            ["Stage: Offered", "An offer has been extended."],
            ["Stage: Hired", "Offer accepted. Awaiting joining date."],
            ["Stage: Joined", "Started working. Recruitment complete."],
            ["Stage: Rejected", "Not selected for this position."],
            ["Stage: On Hold", "Decision paused. Follow up when ready."],
            ["Tracker view", "Spreadsheet view of submissions. Click rows for details."],
            ["Candidate Bank", "Searchable database of all candidates."],
            ["Resume Upload", "PDF, DOC, DOCX only. Maximum 5MB."],
            ["Mandates", "Jobs assigned to you. Click for full requirements."],
            ["Approvals", "Items awaiting your review. Approve or reject."],
            ["My Team", "Your team members, roles, and assigned companies."],
        ],
        [doc.width*0.3, doc.width*0.7]
    )

    space(10)
    story.append(Paragraph("— End of Training Manual —", ParagraphStyle("end", parent=styles["DocSubtitle"], fontSize=11)))
    story.append(Paragraph("Prepared for Ventures HRD — Talent OS", styles["SmallGray"]))

    doc.build(story)
    buf.seek(0)
    return buf.read()


if __name__ == "__main__":
    pdf_data = build_pdf()
    with open("/app/backend/static/training_manual.pdf", "wb") as f:
        f.write(pdf_data)
    print(f"PDF generated: {len(pdf_data)} bytes")
