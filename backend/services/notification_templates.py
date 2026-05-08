"""
Notification Templates for VHC Talent OS
Centralized template storage - no hardcoded strings in business logic
"""
from typing import Dict, Optional
from string import Template

# ============== EMAIL TEMPLATES ==============

EMAIL_TEMPLATES = {
    "job_match_notification": {
        "subject": "New Job Match: ${job_title} at ${company_name}",
        "html": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #7CB342 0%, #558B2F 100%); padding: 30px; border-radius: 10px 10px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 24px;">🎯 New Job Match!</h1>
    </div>
    
    <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
        <p style="font-size: 16px;">Hi <strong>${candidate_name}</strong>,</p>
        
        <p>Great news! We found a job that matches your profile:</p>
        
        <div style="background: white; padding: 20px; border-radius: 8px; border-left: 4px solid #7CB342; margin: 20px 0;">
            <h2 style="color: #333; margin: 0 0 10px 0; font-size: 20px;">${job_title}</h2>
            <p style="color: #666; margin: 5px 0;"><strong>🏢 Company:</strong> ${company_name}</p>
            <p style="color: #666; margin: 5px 0;"><strong>📍 Location:</strong> ${job_location}</p>
            <p style="color: #666; margin: 5px 0;"><strong>⭐ Match Score:</strong> ${match_score}%</p>
        </div>
        
        <div style="background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <p style="margin: 0; color: #2e7d32;"><strong>Why this matches you:</strong></p>
            <p style="margin: 10px 0 0 0; color: #333;">${match_explanation}</p>
        </div>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="${apply_link}" style="background: #7CB342; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">View & Apply →</a>
        </div>
        
        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
        
        <p style="color: #888; font-size: 12px;">
            You received this email because you opted in to job alerts on VHC Talent OS.<br>
            <a href="${unsubscribe_link}" style="color: #7CB342;">Manage your notification preferences</a>
        </p>
    </div>
</body>
</html>
""",
        "text": """
New Job Match!

Hi ${candidate_name},

Great news! We found a job that matches your profile:

${job_title}
Company: ${company_name}
Location: ${job_location}
Match Score: ${match_score}%

Why this matches you:
${match_explanation}

View and Apply: ${apply_link}

---
You received this email because you opted in to job alerts on VHC Talent OS.
Manage your preferences: ${unsubscribe_link}
"""
    },
    
    "weekly_job_digest": {
        "subject": "Your Weekly Job Matches - ${match_count} New Opportunities",
        "html": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #7CB342 0%, #558B2F 100%); padding: 30px; border-radius: 10px 10px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 24px;">📊 Your Weekly Job Digest</h1>
    </div>
    
    <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
        <p style="font-size: 16px;">Hi <strong>${candidate_name}</strong>,</p>
        
        <p>Here are <strong>${match_count}</strong> new jobs that match your profile this week:</p>
        
        ${job_list_html}
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="${view_all_link}" style="background: #7CB342; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">View All Matches →</a>
        </div>
        
        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
        
        <p style="color: #888; font-size: 12px;">
            <a href="${unsubscribe_link}" style="color: #7CB342;">Manage your notification preferences</a>
        </p>
    </div>
</body>
</html>
""",
        "text": """
Your Weekly Job Digest

Hi ${candidate_name},

Here are ${match_count} new jobs that match your profile this week:

${job_list_text}

View All Matches: ${view_all_link}

---
Manage your preferences: ${unsubscribe_link}
"""
    },
    
    "alert_subscription_confirmed": {
        "subject": "Job Alerts Activated - VHC Talent OS",
        "html": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: #7CB342; padding: 20px; border-radius: 10px 10px 0 0;">
        <h1 style="color: white; margin: 0;">✅ Job Alerts Activated</h1>
    </div>
    
    <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
        <p>Hi <strong>${candidate_name}</strong>,</p>
        
        <p>Your job alert preferences have been saved. Here's what you'll receive:</p>
        
        <ul style="background: white; padding: 20px 20px 20px 40px; border-radius: 8px;">
            <li><strong>Skills:</strong> ${skills_list}</li>
            <li><strong>Location:</strong> ${location_pref}</li>
            <li><strong>Experience:</strong> ${experience_range}</li>
            <li><strong>Frequency:</strong> ${frequency}</li>
        </ul>
        
        <p>We'll notify you when new jobs match these criteria.</p>
        
        <p style="color: #888; font-size: 12px; margin-top: 30px;">
            <a href="${manage_link}" style="color: #7CB342;">Update your preferences anytime</a>
        </p>
    </div>
</body>
</html>
""",
        "text": """
Job Alerts Activated

Hi ${candidate_name},

Your job alert preferences have been saved:
- Skills: ${skills_list}
- Location: ${location_pref}
- Experience: ${experience_range}
- Frequency: ${frequency}

We'll notify you when new jobs match these criteria.

Update your preferences: ${manage_link}
"""
    }
}


# ============== WHATSAPP TEMPLATES ==============
# Note: These must be approved by WhatsApp before use

WHATSAPP_TEMPLATES = {
    "job_match_notification": {
        "template_name": "job_match_alert",
        "body": """🎯 New Job Match!

*${job_title}*
🏢 ${company_name}
📍 ${job_location}
⭐ ${match_score}% match

${match_explanation}

Apply now: ${apply_link}""",
        "category": "UTILITY"
    },
    
    "application_status_update": {
        "template_name": "application_update",
        "body": """📋 Application Update

Your application for *${job_title}* at ${company_name} has been updated.

Status: ${new_status}

View details: ${view_link}""",
        "category": "UTILITY"
    }
}


# ============== TEMPLATE HELPER FUNCTIONS ==============

def render_email_template(template_name: str, variables: Dict) -> Optional[Dict]:
    """
    Render email template with variables.
    Returns dict with subject, html, text or None if template not found.
    """
    if template_name not in EMAIL_TEMPLATES:
        return None
    
    template = EMAIL_TEMPLATES[template_name]
    
    try:
        # Use safe substitute to avoid errors on missing variables
        subject = Template(template["subject"]).safe_substitute(variables)
        html = Template(template["html"]).safe_substitute(variables)
        text = Template(template["text"]).safe_substitute(variables)
        
        return {
            "subject": subject,
            "html": html,
            "text": text
        }
    except Exception:
        return None


def render_whatsapp_template(template_name: str, variables: Dict) -> Optional[Dict]:
    """
    Render WhatsApp template with variables.
    Returns dict with template_name and body or None if template not found.
    """
    if template_name not in WHATSAPP_TEMPLATES:
        return None
    
    template = WHATSAPP_TEMPLATES[template_name]
    
    try:
        body = Template(template["body"]).safe_substitute(variables)
        
        return {
            "template_name": template["template_name"],
            "body": body,
            "category": template["category"]
        }
    except Exception:
        return None


def get_job_list_html(jobs: list) -> str:
    """Generate HTML list of jobs for digest email"""
    html_parts = []
    for job in jobs[:5]:  # Limit to 5 jobs
        html_parts.append(f"""
        <div style="background: white; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 3px solid #7CB342;">
            <h3 style="margin: 0 0 5px 0; font-size: 16px;">{job.get('title', 'Job Title')}</h3>
            <p style="margin: 0; color: #666; font-size: 14px;">
                🏢 {job.get('company', 'Company')} | 📍 {job.get('location', 'Location')} | ⭐ {job.get('score', 0)}% match
            </p>
        </div>
        """)
    return ''.join(html_parts)


def get_job_list_text(jobs: list) -> str:
    """Generate text list of jobs for digest email"""
    text_parts = []
    for i, job in enumerate(jobs[:5], 1):
        text_parts.append(f"{i}. {job.get('title', 'Job Title')} at {job.get('company', 'Company')} - {job.get('score', 0)}% match")
    return '\n'.join(text_parts)
