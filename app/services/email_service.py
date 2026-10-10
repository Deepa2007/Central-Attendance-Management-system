"""
PRODUCTION REAL Email Service - FIXED v4
- Your log: FROM=USER match OK but Connection closed during login
- Cause: Wrong App Password (regular password, spaces, 2FA off) or firewall
- Fix: Try 587 TLS first, fallback to 465 SSL, validate App Password format
"""

import smtplib
import ssl
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from ..core.config import settings


def get_smtp_config_status():
    # Mask password for security but show length
    pass_len = len(settings.SMTP_PASS) if settings.SMTP_PASS else 0
    # Check if password looks like App Password (16 chars, no spaces) vs regular password
    is_app_password_format = False
    if settings.SMTP_PASS:
        cleaned = settings.SMTP_PASS.replace(" ", "")
        # App Password is 16 chars, lowercase letters only (Google format)
        if len(cleaned) == 16 and cleaned.isalpha() and cleaned.islower():
            is_app_password_format = True
        elif len(cleaned) == 16:
            is_app_password_format = True  # Might be with uppercase, still 16 chars

    return {
        "host": settings.SMTP_HOST or "NOT SET",
        "port": settings.SMTP_PORT,
        "user": settings.SMTP_USER or "NOT SET",
        "from": settings.SMTP_FROM or settings.SMTP_USER or "NOT SET",
        "configured": bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASS),
        "password_set": bool(settings.SMTP_PASS),
        "password_length": pass_len,
        "password_looks_like_app_password": is_app_password_format,
        "password_has_spaces": " " in settings.SMTP_PASS if settings.SMTP_PASS else False,
        "company": settings.COMPANY_NAME,
        "hint": "App Password should be 16 chars lowercase, no spaces. Example: abcd efgh ijkl mnop -> abcdefghijklmnop",
    }


def validate_app_password():
    """Check if SMTP_PASS looks like valid App Password"""
    if not settings.SMTP_PASS:
        return False, "Password empty"

    pwd = settings.SMTP_PASS
    has_spaces = " " in pwd
    cleaned = pwd.replace(" ", "")

    if has_spaces:
        return (
            False,
            f"Password has spaces! Remove spaces. You have '{pwd}' -> should be '{cleaned}'. Gmail App Password copied from Google has spaces like 'abcd efgh ijkl mnop' but you must remove spaces in .env",
        )

    if len(cleaned) != 16:
        return (
            False,
            f"App Password should be 16 chars, you have {len(cleaned)} chars ({len(pwd)} with spaces). Regular Gmail password is longer. You need App Password from myaccount.google.com -> Security -> App Passwords",
        )

    # App Password is usually all lowercase letters
    if not cleaned.isalpha():
        return (
            False,
            "App Password should be only letters (16 chars), you have non-letters. Might be regular password. App Password example: abcdefghijklmnop (16 lowercase letters)",
        )

    return True, "Looks like valid App Password format: 16 chars, no spaces, only letters - OK"


def send_email(to_email: str, subject: str, body_html: str = None, body_text: str = None, cc: list = None):
    config_status = get_smtp_config_status()
    print(f"[EMAIL] Config: {config_status}")
    print(f"[EMAIL] Sending to: {to_email} | Subject: {subject}")

    # Validate App Password format
    is_valid_format, format_msg = validate_app_password()
    print(f"[EMAIL] Password format check: valid={is_valid_format}, msg={format_msg}")
    if not is_valid_format:
        print(f"[EMAIL WARNING] Password format issue: {format_msg}")

    if not settings.SMTP_HOST or not settings.SMTP_HOST.strip() or not settings.SMTP_USER or not settings.SMTP_PASS:
        print(f"\n{'='*60}")
        print("[EMAIL DEV MODE] SMTP not fully configured - logging only")
        print(f"HOST={settings.SMTP_HOST or 'empty'} USER={settings.SMTP_USER or 'empty'}")
        print(f"To: {to_email} | Subject: {subject}")
        print(f"{'='*60}\n")
        return {
            "status": "logged",
            "mode": "dev",
            "to": to_email,
            "subject": subject,
            "message": "SMTP not configured - logged to console. Set SMTP_HOST, SMTP_USER, SMTP_PASS in .env",
            "config": config_status,
        }

    from_name = settings.COMPANY_NAME or "Attendance System"

    # FORCE FROM=USER for Gmail
    if settings.SMTP_USER and "@gmail.com" in settings.SMTP_USER.lower():
        from_email = settings.SMTP_USER
        if settings.SMTP_FROM and settings.SMTP_FROM.lower() != settings.SMTP_USER.lower():
            print(
                f"[EMAIL FIX] USER={settings.SMTP_USER} != FROM={settings.SMTP_FROM} -> FORCING FROM=USER={from_email}"
            )
    else:
        from_email = settings.SMTP_FROM or settings.SMTP_USER

    print(
        f"[EMAIL] Using FROM={from_email} USER={settings.SMTP_USER} - Match: {from_email.lower()==settings.SMTP_USER.lower()}"
    )
    print(
        f"[EMAIL] Password length: {len(settings.SMTP_PASS)} chars, has_spaces: {' ' in settings.SMTP_PASS}, looks_like_app_password: {config_status['password_looks_like_app_password']}"
    )

    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)

    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))
    elif body_text:
        fallback_html = "<html><body><pre>" + body_text + "</pre></body></html>"
        msg.attach(MIMEText(fallback_html, "html", "utf-8"))

    # Try 587 first, then fallback to 465 if 587 fails with connection closed
    last_error = None

    # Attempt 1: Port 587 TLS (original)
    try:
        print(f"[EMAIL] Attempt 1: Connecting to {settings.SMTP_HOST}:587 with TLS (timeout 30s)...")
        with smtplib.SMTP(settings.SMTP_HOST, 587, timeout=30) as server:
            server.set_debuglevel(0)
            server.ehlo()
            print("[EMAIL] Starting TLS on 587...")
            context = ssl.create_default_context()
            server.starttls(context=context)
            server.ehlo()
            print(f"[EMAIL] Logging in as {settings.SMTP_USER} on 587...")
            print(
                f"[EMAIL] Using password length {len(settings.SMTP_PASS)} (first 4 chars: {settings.SMTP_PASS[:4]}... masked)"
            )
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            recipients = [to_email] + (cc or [])
            print(f"[EMAIL] Sending email to {recipients} from {from_email} on 587...")
            server.sendmail(from_email, recipients, msg.as_string())
            print(f"[EMAIL SENT] To: {to_email} | Subject: {subject} via 587 TLS")
            return {
                "status": "sent",
                "to": to_email,
                "subject": subject,
                "mode": "real",
                "from_used": from_email,
                "port": 587,
                "password_format_ok": is_valid_format,
            }

    except smtplib.SMTPAuthenticationError as e:
        print(f"[EMAIL FAILED 587] Auth failed: {e}")
        last_error = e
        # Don't try 465 if auth failed - password is wrong for both ports
        return {
            "status": "failed",
            "to": to_email,
            "error": str(e),
            "error_type": "auth_failed",
            "config": config_status,
            "port_tried": 587,
            "password_format_check": format_msg,
            "help": f"AUTH FAILED on 587: {e}. Your App Password is WRONG. You used regular Gmail password, not App Password. Go to myaccount.google.com (logged in as {settings.SMTP_USER}) -> Security -> 2-Step Verification ON -> App Passwords -> Mail -> Other -> Generate 16 chars -> Remove spaces -> Use that as SMTP_PASS. Current password length {len(settings.SMTP_PASS)}, has_spaces={ ' ' in settings.SMTP_PASS }, looks_like_app_password={config_status['password_looks_like_app_password']}. {format_msg}",
            "fix": f"1) Login as {settings.SMTP_USER} at myaccount.google.com 2) Security -> 2FA ON 3) App Passwords -> Generate 16 chars 4) Remove spaces 5) Paste in .env SMTP_PASS",
        }

    except (smtplib.SMTPServerDisconnected, ConnectionResetError, smtplib.SMTPConnectError, OSError) as e:
        print(f"[EMAIL FAILED 587] Connection closed/disconnected: {e}")
        print("[EMAIL] 587 failed with connection closed - trying 465 SSL fallback...")
        last_error = e

    except Exception as e:  # noqa: BLE001
        print(f"[EMAIL FAILED 587] Other error: {e}")
        traceback.print_exc()
        last_error = e
        # Try 465 as fallback for connection issues

    # Attempt 2: Port 465 SSL fallback
    try:
        print(f"[EMAIL] Attempt 2: Connecting to {settings.SMTP_HOST}:465 with SSL (timeout 30s)...")
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(settings.SMTP_HOST, 465, context=context, timeout=30) as server:
            server.set_debuglevel(0)
            print(f"[EMAIL] Logging in as {settings.SMTP_USER} on 465 SSL...")
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            recipients = [to_email] + (cc or [])
            print(f"[EMAIL] Sending email to {recipients} from {from_email} on 465 SSL...")
            server.sendmail(from_email, recipients, msg.as_string())
            print(f"[EMAIL SENT] To: {to_email} | Subject: {subject} via 465 SSL")
            return {
                "status": "sent",
                "to": to_email,
                "subject": subject,
                "mode": "real",
                "from_used": from_email,
                "port": 465,
                "fallback": True,
                "password_format_ok": is_valid_format,
            }

    except smtplib.SMTPAuthenticationError as e:
        print(f"[EMAIL FAILED 465] Auth failed: {e}")
        return {
            "status": "failed",
            "to": to_email,
            "error": str(e),
            "error_type": "auth_failed",
            "config": config_status,
            "port_tried": [587, 465],
            "last_error_587": str(last_error),
            "password_format_check": format_msg,
            "help": f"AUTH FAILED on both 587 and 465: {e}. Your App Password is WRONG for {settings.SMTP_USER}. You are using regular password or App Password for different account. Steps: 1) Login Gmail as {settings.SMTP_USER} 2) myaccount.google.com -> Security -> 2FA ON -> App Passwords -> Generate 16 chars for Mail 3) Remove spaces 4) Use as SMTP_PASS. Current: length {len(settings.SMTP_PASS)}, has_spaces={ ' ' in settings.SMTP_PASS }, valid_format={is_valid_format}. {format_msg}",
            "fix": f"Generate NEW App Password for {settings.SMTP_USER} at myaccount.google.com -> Security -> App Passwords. Must be 16 lowercase letters, no spaces.",
        }

    except Exception as e2:
        print(f"[EMAIL FAILED 465] Failed: {e2}")
        traceback.print_exc()
        # Both ports failed
        return {
            "status": "failed",
            "to": to_email,
            "error": f"Both 587 and 465 failed. 587 error: {last_error}, 465 error: {e2}",
            "error_type": "connection_closed",
            "config": config_status,
            "port_tried": [587, 465],
            "password_format_check": format_msg,
            "help": f"Connection closed on BOTH 587 and 465. Causes: 1) Wrong App Password (you used regular Gmail password, not 16-char App Password) 2) 2FA not enabled for {settings.SMTP_USER} 3) Firewall blocking SMTP 4) Antivirus blocking. Check: password length {len(settings.SMTP_PASS)} should be 16, has_spaces={ ' ' in settings.SMTP_PASS }. Your error 587: {last_error}, 465: {e2}. {format_msg}",
            "fix": f"1) Verify 2FA ON for {settings.SMTP_USER} at myaccount.google.com -> Security 2) Generate App Password (16 chars) 3) Remove spaces 4) Update .env SMTP_PASS 5) Try disabling antivirus firewall temporarily 6) Try port 465 if 587 blocked. Current password: length {len(settings.SMTP_PASS)}, has_spaces={ ' ' in settings.SMTP_PASS }",
            "your_bug": f"You have USER={settings.SMTP_USER} FROM={from_email}. Password length {len(settings.SMTP_PASS)} - should be 16. If length is >16, you used regular password, not App Password. If has spaces, remove them. Go to myaccount.google.com as {settings.SMTP_USER} -> Security -> App Passwords",
        }


def email_template_checkin(employee_name: str, entry_time: datetime, verified: bool, distance: float):
    loc_text = f"Verified ({distance}km)" if verified else f"Outside ({distance}km)" if distance else "No location"
    subject = f"Check-in Confirmed - {entry_time}"
    text = f"Hi {employee_name},\n\nYour check-in has been recorded:\n- Time: {entry_time}\n- Location Verified: {loc_text}\n- Status: Present\n\n{settings.COMPANY_NAME}"
    html = f"<html><body><h2>Check-in Confirmed</h2><p>Hi <b>{employee_name}</b></p><p>Time: {entry_time}<br>Location: {loc_text}</p></body></html>"
    return subject, text, html


def email_template_checkout(employee_name: str, entry: datetime, exit: datetime, hours: float):
    subject = f"Check-out - {hours:.1f} hrs worked today"
    text = f"Hi {employee_name},\nCheck-out recorded:\n- Entry: {entry}\n- Exit: {exit}\n- Hours: {hours}\n\n{settings.COMPANY_NAME}"
    return subject, text, None


def email_template_leave_request(employee_name: str, leave_type: str, start, end, reason: str):
    subject = f"Leave Request - {leave_type} - {start} to {end}"
    text = f"Hi HR/Manager,\n\n{employee_name} has requested leave:\n- Type: {leave_type}\n- Dates: {start} to {end}\n- Reason: {reason}\n\n{settings.COMPANY_NAME}"
    return subject, text, None


def email_template_leave_approved(employee_name: str, leave_type: str, start, end, approved_by: str):
    subject = f"Leave Approved - {leave_type} - {start}"
    text = f"Hi {employee_name},\nYour leave has been APPROVED by {approved_by}:\n- Type: {leave_type}\n- Dates: {start} to {end}\n\n{settings.COMPANY_NAME}"
    return subject, text, None


def email_template_stale_alert(employee_name: str, entry_time: datetime, hours_open: float):
    subject = f"Action Required: Missing Check-out - Open since {entry_time}"
    text = f"Hi {employee_name},\nYour session is still OPEN:\n- Checked in: {entry_time}\n- Hours open: {hours_open}\n\n{settings.COMPANY_NAME}"
    return subject, text, None


def email_template_violation(
    employee_name: str, week_start, week_end, days_present: int, required_days: int, hours: float, required_hours: float
):
    subject = f"Weekly Compliance Violation - Week {week_start}"
    text = f"Hi {employee_name},\nWeekly compliance FAILED:\n- Week: {week_start} to {week_end}\n- Days: {days_present}/{required_days}\n- Hours: {hours}/{required_hours}\n\n{settings.COMPANY_NAME}"
    return subject, text, None


def email_template_daily_reminder(employee_name: str, date):
    subject = f"Reminder: Check-in for {date}"
    text = f"Hi {employee_name},\nYou have not checked in today ({date}).\nRequired: {settings.REQUIRED_DAYS} days / {settings.REQUIRED_HOURS} hrs\n\n{settings.COMPANY_NAME}"
    return subject, text, None


def email_template_weekly_report(employee_name: str, stats: dict, to_email: str):
    week_start = stats.get("week_start", "N/A")
    week_end = stats.get("week_end", "N/A")
    days_present = stats.get("days_present", 0)
    eff_days = stats.get("effective_required_days", 0)
    total_hours = stats.get("total_hours", 0)
    eff_hours = stats.get("effective_required_hours", 0)
    is_compliant = stats.get("is_compliant", False)
    waived_days = stats.get("waived_days", 0)
    actual_hours = stats.get("actual_hours", 0)
    credited_hours = stats.get("credited_hours", 0)
    stale_sessions = stats.get("stale_sessions", 0)
    compliant_text = "YES" if is_compliant else "NO"
    deficit_days = max(0, eff_days - days_present)
    deficit_hours = max(0, eff_hours - total_hours)
    subject = f"Weekly Attendance Report - {week_start} to {week_end} - {total_hours} hrs"
    text = f"Hi {employee_name} ({to_email}),\n\nWeekly Report:\nWeek: {week_start} to {week_end}\nDays: {days_present}/{eff_days} (Waived: {waived_days})\nHours: {total_hours} (Actual: {actual_hours} + Credited: {credited_hours})\nRequired: {eff_hours}\nCompliant: {compliant_text}\nDeficit: {deficit_days} days, {round(deficit_hours,1)} hrs\n\n{settings.COMPANY_NAME}"
    html = f"<html><body><h2>Weekly Report</h2><p>Hi <b>{employee_name}</b> ({to_email})</p><p>Week: {week_start} to {week_end}</p><ul><li>Days: {days_present}/{eff_days}</li><li>Hours: {total_hours}/{eff_hours}</li><li>Compliant: {compliant_text}</li></ul><p>Stale: {stale_sessions}</p></body></html>"
    return subject, text, html


def email_template_admin_to_employee(admin_name: str, employee_name: str, message: str, report_data: dict = None):
    subject = f"Message from {admin_name} - Attendance System"
    text = (
        f"Hi {employee_name},\n\nMessage from {admin_name} (admin@company.com):\n\n{message}\n\n{settings.COMPANY_NAME}"
    )
    if report_data:
        week_start = report_data.get("week_start", "")
        week_end = report_data.get("week_end", "")
        subject = f"Attendance Report from {admin_name} - {week_start} to {week_end}"
        text = (
            text
            + f"\n\nWeekly Summary:\n- Days: {report_data.get('days_present')}/{report_data.get('effective_required_days')}\n- Hours: {report_data.get('total_hours')}/{report_data.get('effective_required_hours')}\n"
        )
    return subject, text, None


def email_template_checkout_early(
    employee_name: str, entry: datetime, exit: datetime, hours: float, min_daily: float = 5.0
):
    """Early checkout - worked less than 5 hours"""
    deficit = round(min_daily - hours, 2)
    subject = f"⚠️ Early Check-out Alert - Only {hours:.1f} hrs today (Required {min_daily} hrs)"
    text = f"""Hi {employee_name},

⚠️ EARLY CHECK-OUT DETECTED - Action May Be Required

You checked out early today:
- Check-in: {entry}
- Check-out: {exit}
- Hours Worked Today: {hours:.2f} hrs
- Minimum Required Per Day: {min_daily} hrs
- Deficit Today: {deficit:.2f} hrs

What this means:
❌ Today does NOT count as a full compliant day if your company requires {min_daily}+ hrs
❌ You need to work {deficit:.2f} more hours to meet daily minimum
❌ This affects your weekly compliance (Required: {settings.REQUIRED_DAYS} days / {settings.REQUIRED_HOURS} hrs)

What to do:
- If you left for a valid reason, please apply for leave (casual/sick) or WFH for today
- If this was an error, request attendance correction from dashboard
- Your manager and HR have been notified

Weekly Impact:
Your weekly report will show this day as present but with low hours. You still need to meet weekly required hours.

Best regards,
{settings.COMPANY_NAME} - Central Attendance System
Automated Alert | Please do not reply
"""
    html = f"""
<html><body style="font-family: Arial; padding: 20px; background: #fff3e0;">
<div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-left: 5px solid #ff9800;">
<h2 style="color: #e65100;">⚠️ Early Check-out Alert</h2>
<p>Hi <b>{employee_name}</b>,</p>
<div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #ffcc80;">
<p style="margin: 5px 0;"><b>Check-in:</b> {entry}</p>
<p style="margin: 5px 0;"><b>Check-out:</b> {exit}</p>
<p style="margin: 5px 0;"><b>Hours Today:</b> <span style="color: #d32f2f; font-weight: bold;">{hours:.2f} hrs</span></p>
<p style="margin: 5px 0;"><b>Required Minimum:</b> {min_daily} hrs</p>
<p style="margin: 5px 0;"><b>Deficit:</b> <span style="color: #d32f2f;">{deficit:.2f} hrs</span></p>
</div>
<div style="background: #fce4ec; padding: 15px; border-radius: 8px; margin: 15px 0;">
<h3 style="color: #c62828; margin-top: 0;">What this means:</h3>
<ul>
<li>Today does NOT count as fully compliant if {min_daily}+ hrs required</li>
<li>You need {deficit:.2f} more hours to meet daily minimum</li>
<li>Affects weekly compliance (Required: {settings.REQUIRED_DAYS} days / {settings.REQUIRED_HOURS} hrs)</li>
</ul>
</div>
<div style="background: #e8f5e9; padding: 15px; border-radius: 8px;">
<h3 style="color: #2e7d32; margin-top: 0;">What to do:</h3>
<ul>
<li>If valid reason, apply for leave or WFH for today</li>
<li>If error, request attendance correction from dashboard</li>
<li>Manager and HR have been notified</li>
</ul>
</div>
<hr style="margin: 20px 0;">
<small style="color: #666;">{settings.COMPANY_NAME} - Automated Alert | Please do not reply</small>
</div></body></html>
"""
    return subject, text, html


def email_template_checkout_success(
    employee_name: str, entry: datetime, exit: datetime, hours: float, weekly_stats: dict = None
):
    """Successful checkout - worked >=5 hours, meaningful summary"""
    min_daily = getattr(settings, "MIN_DAILY_HOURS", 5.0)
    status_icon = "✅" if hours >= min_daily else "⚠️"

    weekly_info = ""
    if weekly_stats:
        days = weekly_stats.get("days_present", 0)
        total = weekly_stats.get("total_hours", 0)
        req_days = weekly_stats.get("effective_required_days", settings.REQUIRED_DAYS)
        req_hours = weekly_stats.get("effective_required_hours", settings.REQUIRED_HOURS)
        remaining_days = max(0, req_days - days)
        remaining_hours = max(0, req_hours - total)
        compliant = weekly_stats.get("is_compliant", False)

        weekly_info = f"""
Weekly Progress (Mon-Sun):
- Days Present This Week: {days}/{req_days} (Remaining: {remaining_days} days)
- Total Hours This Week: {total:.1f}/{req_hours} hrs (Remaining: {remaining_hours:.1f} hrs)
- Compliance Status: {'✅ COMPLIANT' if compliant else '❌ NOT YET COMPLIANT'}
- You need {remaining_days} more days and {remaining_hours:.1f} more hours to be compliant this week
"""
    else:
        weekly_info = "Weekly stats will be updated shortly. Check dashboard for weekly compliance."

    subject = f"{status_icon} Check-out Confirmed - {hours:.1f} hrs today | Weekly: {weekly_stats.get('days_present', 0) if weekly_stats else 0} days"
    text = f"""Hi {employee_name},

{status_icon} CHECK-OUT CONFIRMED - Great Work Today!

Today's Summary:
- Check-in: {entry}
- Check-out: {exit}
- Hours Worked Today: {hours:.2f} hrs
- Daily Status: {'✅ MET daily minimum' if hours >= min_daily else f'⚠️ Below {min_daily} hrs minimum - {min_daily - hours:.1f} hrs short'}
- Location: Office Verified

{weekly_info}

Keep Going:
{'🎉 You are COMPLIANT for this week!' if weekly_stats and weekly_stats.get('is_compliant') else '💪 Keep checking in to meet weekly target of 3 days / 15 hours'}

Tips:
- Daily target: {min_daily}+ hours counts as full day
- Weekly target: {settings.REQUIRED_DAYS} days and {settings.REQUIRED_HOURS} hours
- Early checkout (<{min_daily} hrs) may require leave/WFH adjustment

Best regards,
{settings.COMPANY_NAME} - Attendance System
"""
    html = f"""
<html><body style="font-family: Arial; padding: 20px;">
<div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-left: 5px solid {'#4caf50' if hours >= min_daily else '#ff9800'};">
<h2 style="color: {'#2e7d32' if hours >= min_daily else '#e65100'};">{status_icon} Check-out Confirmed</h2>
<p>Hi <b>{employee_name}</b>,</p>
<div style="background: {'#e8f5e9' if hours >= min_daily else '#fff3e0'}; padding: 15px; border-radius: 8px; margin: 15px 0;">
<p style="margin: 5px 0;"><b>Check-in:</b> {entry}</p>
<p style="margin: 5px 0;"><b>Check-out:</b> {exit}</p>
<p style="margin: 5px 0;"><b>Hours Today:</b> <span style="font-weight: bold; color: {'#2e7d32' if hours >= min_daily else '#d32f2f'};">{hours:.2f} hrs</span> {status_icon}</p>
<p style="margin: 5px 0;"><b>Daily Status:</b> {'✅ MET minimum' if hours >= min_daily else f'⚠️ Below {min_daily} hrs'}</p>
</div>
<div style="background: #e3f2fd; padding: 15px; border-radius: 8px; margin: 15px 0;">
<h3 style="color: #1565c0; margin-top: 0;">📊 Weekly Progress</h3>
<pre style="margin: 0; font-family: Arial; white-space: pre-wrap;">{weekly_info}</pre>
</div>
<p style="color: #666; font-size: 14px;">Keep up the good work! Check dashboard for detailed report.</p>
<hr>
<small>{settings.COMPANY_NAME} - Attendance System</small>
</div></body></html>
"""
    return subject, text, html


def email_template_compliance_stage(employee_name: str, stage: str, stats: dict):
    """
    Stage-based compliance emails
    stage: daily_warning, mid_week_warning, friday_violation, weekly_failure
    """
    days = stats.get("days_present", 0)
    total = stats.get("total_hours", 0)
    req_days = stats.get("effective_required_days", settings.REQUIRED_DAYS)
    req_hours = stats.get("effective_required_hours", settings.REQUIRED_HOURS)
    week_start = stats.get("week_start")
    week_end = stats.get("week_end")

    remaining_days = max(0, req_days - days)
    remaining_hours = max(0, req_hours - total)

    templates = {
        "daily_warning": {
            "subject": f"📅 Daily Reminder - Only {days}/{req_days} days this week",
            "color": "#ff9800",
            "title": "Daily Compliance Check",
            "message": f"You have completed {days} out of {req_days} required days this week. You still need {remaining_days} more days and {remaining_hours:.1f} hours.",
            "action": "Please ensure you check-in tomorrow to stay compliant.",
        },
        "mid_week_warning": {
            "subject": f"⚠️ Mid-Week Alert - {days}/{req_days} days, {remaining_days} days short",
            "color": "#ff5722",
            "title": "Mid-Week Compliance Warning",
            "message": f"It's Wednesday and you have only {days}/{req_days} days. You are at risk of weekly violation!",
            "action": f"You need {remaining_days} more days and {remaining_hours:.1f} hours by Sunday to avoid violation.",
        },
        "friday_violation": {
            "subject": f"🚨 Friday Violation - Weekly Target Not Met: {days}/{req_days} days",
            "color": "#d32f2f",
            "title": "Weekly Compliance VIOLATION",
            "message": f"Week {week_start} to {week_end}: You have only {days}/{req_days} days and {total:.1f}/{req_hours} hours. This is a VIOLATION.",
            "action": f"Deficit: {remaining_days} days, {remaining_hours:.1f} hours. Manager and HR notified. Please check-in over weekend if office open, or apply for leave/WFH adjustments, or this will be marked non-compliant.",
        },
        "weekly_failure": {
            "subject": f"❌ Weekly Failure - {days}/{req_days} days, Non-Compliant Week",
            "color": "#b71c1c",
            "title": "Weekly Compliance FAILED",
            "message": f"Final: Week {week_start} to {week_end} - You finished with {days}/{req_days} days and {total:.1f}/{req_hours} hours. Status: NON-COMPLIANT.",
            "action": f"You missed target by {remaining_days} days and {remaining_hours:.1f} hours. This has been reported to HR and Management. Please ensure compliance next week.",
        },
        "early_checkout_warning": {
            "subject": f"⚠️ Early Leave - {stats.get('hours_today', 0):.1f} hrs today, need {settings.MIN_DAILY_HOURS} hrs",
            "color": "#ff9800",
            "title": "Early Checkout Warning",
            "message": f"You checked out after only {stats.get('hours_today', 0):.1f} hours today, less than required {settings.MIN_DAILY_HOURS} hours.",
            "action": "Please apply for leave or ensure you meet daily minimum tomorrow.",
        },
    }

    tpl = templates.get(stage, templates["daily_warning"])

    subject = tpl["subject"]
    text = f"""Hi {employee_name},

{tpl["title"].upper()}

{tpl["message"]}

Details:
- Week: {week_start} to {week_end}
- Days Present: {days}/{req_days} (Need {remaining_days} more)
- Hours: {total:.1f}/{req_hours} hrs (Need {remaining_hours:.1f} more)
- Status: {'✅ COMPLIANT' if stats.get('is_compliant') else '❌ NOT COMPLIANT'}

Action Required:
{tpl["action"]}

Best regards,
{settings.COMPANY_NAME} - Attendance System
Stage: {stage} | Automated Compliance Monitoring
"""
    html = f"""
<html><body style="font-family: Arial; padding: 20px;">
<div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; border-left: 5px solid {tpl['color']}; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
<h2 style="color: {tpl['color']};">{tpl['title']}</h2>
<p>Hi <b>{employee_name}</b>,</p>
<div style="background: #f5f5f5; padding: 15px; border-radius: 8px;">
<p>{tpl['message']}</p>
<p><b>Week:</b> {week_start} to {week_end}<br>
<b>Days:</b> {days}/{req_days} (Need {remaining_days} more)<br>
<b>Hours:</b> {total:.1f}/{req_hours} hrs (Need {remaining_hours:.1f} more)<br>
<b>Status:</b> {'✅ COMPLIANT' if stats.get('is_compliant') else '❌ NOT COMPLIANT'}</p>
</div>
<div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin-top: 15px;">
<p><b>Action:</b> {tpl['action']}</p>
</div>
<hr><small>{settings.COMPANY_NAME} - Stage: {stage} | Automated</small>
</div></body></html>
"""
    return subject, text, html


def email_template_weekly_violation_enhanced(employee_name: str, week_start, week_end, stats: dict):
    """Enhanced violation email with meaningful message"""
    days = stats.get("days_present", 0)
    total = stats.get("total_hours", 0)
    req_days = stats.get("effective_required_days", settings.REQUIRED_DAYS)
    req_hours = stats.get("effective_required_hours", settings.REQUIRED_HOURS)
    remaining_days = max(0, req_days - days)
    remaining_hours = max(0, req_hours - total)
    waived = stats.get("waived_days", 0)

    # Determine stage and meaningful message
    if days == 0:
        level = "CRITICAL - No attendance this week"
        advice = "You did not check-in at all this week. If you were on leave, ensure your leave was approved. If working remotely, apply for WFH. Otherwise, this will be marked as absenteeism."
    elif days < req_days and total < req_hours:
        level = "VIOLATION - Both days and hours short"
        advice = f"You are short by {remaining_days} days and {remaining_hours:.1f} hours. You need to check-in {remaining_days} more days with at least {settings.MIN_DAILY_HOURS} hrs each to meet weekly target."
    elif days < req_days:
        level = f"VIOLATION - Days short: {days}/{req_days}"
        advice = f"You have hours ({total:.1f}) but only {days}/{req_days} days. You need {remaining_days} more days. Even short days count, but aim for {settings.MIN_DAILY_HOURS}+ hrs."
    else:
        level = f"VIOLATION - Hours short: {total:.1f}/{req_hours}"
        advice = f"You have {days} days but only {total:.1f}/{req_hours} hours. You need {remaining_hours:.1f} more hours. Your average is {total/max(days,1):.1f} hrs/day, need {settings.MIN_DAILY_HOURS}+ hrs/day."

    subject = f"🚨 Weekly Compliance {level} - {days}/{req_days} days, {total:.1f}/{req_hours} hrs"
    text = f"""Hi {employee_name},

🚨 WEEKLY COMPLIANCE VIOLATION - {level}

Week: {week_start} to {week_end}

Your Attendance:
- Days Present: {days}/{req_days} (Required)
- Hours Worked: {total:.1f}/{req_hours} hrs (Required)
- Waived Days (Leave/Holiday): {waived}
- Deficit: {remaining_days} days, {remaining_hours:.1f} hours
- Status: ❌ NON-COMPLIANT

Analysis:
{level}
{advice}

Impact:
- This violation has been reported to your Manager and HR
- Repeated violations may affect performance review
- If you had approved leaves, they are already counted as waived: {waived} days

What to do now:
1. Check dashboard for detailed daily breakdown
2. If you were on leave/WFH, ensure approvals are in system
3. For next week, aim for {settings.REQUIRED_DAYS} days and {settings.REQUIRED_HOURS} hrs
4. Daily minimum to avoid early checkout warning: {settings.MIN_DAILY_HOURS} hrs

Best regards,
{settings.COMPANY_NAME} - HR & Attendance System
Auto-generated Violation Notice | Week {week_start}
"""
    html = f"""
<html><body style="font-family: Arial; padding: 20px; background: #ffebee;">
<div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; border-left: 6px solid #d32f2f; box-shadow: 0 4px 20px rgba(0,0,0,0.15);">
<h2 style="color: #b71c1c;">🚨 Weekly Compliance Violation</h2>
<p style="background: #ffebee; padding: 10px; border-radius: 5px;"><b>{level}</b></p>
<p>Hi <b>{employee_name}</b>,</p>
<p><b>Week:</b> {week_start} to {week_end}</p>
<div style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 15px 0;">
<p><b>Days:</b> {days}/{req_days} | <b>Hours:</b> {total:.1f}/{req_hours} hrs<br>
<b>Waived:</b> {waived} days | <b>Deficit:</b> {remaining_days} days, {remaining_hours:.1f} hrs<br>
<b>Status:</b> <span style="color: #d32f2f; font-weight: bold;">❌ NON-COMPLIANT</span></p>
</div>
<div style="background: #fff3e0; padding: 15px; border-radius: 8px; border: 1px solid #ffcc80;">
<p><b>Analysis:</b> {advice}</p>
</div>
<div style="background: #e8f5e9; padding: 15px; border-radius: 8px; margin-top: 15px;">
<h4 style="margin-top: 0; color: #2e7d32;">What to do:</h4>
<ol>
<li>Check dashboard for daily breakdown</li>
<li>Ensure leave/WFH approvals are in system</li>
<li>Next week target: {settings.REQUIRED_DAYS} days / {settings.REQUIRED_HOURS} hrs</li>
<li>Daily minimum: {settings.MIN_DAILY_HOURS} hrs to avoid early warning</li>
</ol>
</div>
<hr><small>{settings.COMPANY_NAME} - Auto Violation Notice</small>
</div></body></html>
"""
    return subject, text, html


def test_smtp_connection():
    config = get_smtp_config_status()
    is_valid, msg = validate_app_password()
    if not config["configured"]:
        return {"status": "not_configured", "config": config, "password_check": msg, "message": "SMTP not configured"}
    try:
        if config["host"] == "NOT SET":
            return {"status": "not_configured"}
        # Try 587 first
        try:
            with smtplib.SMTP(settings.SMTP_HOST, 587, timeout=10) as server:
                server.ehlo()
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
                server.login(settings.SMTP_USER, settings.SMTP_PASS)
            return {
                "status": "success",
                "config": config,
                "port": 587,
                "password_check": msg,
                "message": "SMTP 587 TLS connection successful",
            }
        except Exception as e587:
            print(f"587 failed {e587}, trying 465")
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(settings.SMTP_HOST, 465, context=context, timeout=10) as server:
                server.login(settings.SMTP_USER, settings.SMTP_PASS)
            return {
                "status": "success",
                "config": config,
                "port": 465,
                "password_check": msg,
                "message": "SMTP 465 SSL connection successful (587 failed, 465 worked)",
                "error_587": str(e587),
            }
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return {
            "status": "failed",
            "config": config,
            "error": str(e),
            "password_check": msg,
            "help": f"Gmail: Enable 2FA for {settings.SMTP_USER}, create App Password 16 chars, no spaces. Current: length {len(settings.SMTP_PASS) if settings.SMTP_PASS else 0}, has_spaces={' ' in settings.SMTP_PASS if settings.SMTP_PASS else False}. {msg}",
        }
