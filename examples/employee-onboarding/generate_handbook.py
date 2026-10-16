"""Rebuild the fictional text-based PDF with the project's existing ReportLab dependency."""
from pathlib import Path
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

destination = Path(__file__).with_name("benefits_handbook.pdf")
styles = getSampleStyleSheet()
sections = [
    ("Northstar Studio - Benefits and Starter Handbook", "Title"),
    ("Fictional demo data | Handbook HR-BEN-01 | Effective 1 October 2026", "Normal"),
    ("First-week checklist", "Heading2"),
    ("Complete benefits enrolment in the People Portal within your first 5 working days. Complete security awareness training and acknowledge the starter checklist by the end of your first week. Your manager schedules your first-week welcome meeting.", "Normal"),
    ("Learning budget", "Heading2"),
    ("Employees can request up to GBP 500 per calendar year for approved learning after completing probation. Obtain line manager approval before booking a course. Submit the course name and cost through the People Portal. This handbook does not describe performance bonuses.", "Normal"),
    ("Wellbeing support", "Heading2"),
    ("A confidential employee assistance service is available to all employees. The access link is in the People Portal under Wellbeing. This demo does not include private health insurer names or future provider arrangements.", "Normal"),
    ("Work location and office access", "Heading2"),
    ("Your office_id links to office_locations.csv: LON is London Studio, MAN is Manchester Studio, and REMOTE is Remote Workspace. Check the directory for opening hours and expected on-site days. Collect an office access pass from reception on your first office visit.", "Normal"),
    ("Equipment before you start", "Heading2"),
    ("Request the standard laptop, equipment_id EQ-LAP-01, through the IT Service Desk portal at least 5 working days before your start date. Line manager approval is required. Employees assigned to REMOTE can receive their laptop by home delivery; coordinate the delivery address and date with IT. Do not send private delivery details to the shared office contact address.", "Normal"),
    ("Further equipment and leave", "Heading2"),
    ("See equipment_catalogue.json for monitors, USB headsets and chair availability. See leave_policy.txt, policy HR-LEAVE-01, for annual leave requests, carryover and sickness reporting. A missing policy or date must not be treated as an implied entitlement or promise.", "Normal"),
]
story = []
for text, style in sections:
    story.extend([Paragraph(text, styles[style]), Spacer(1, 8)])
SimpleDocTemplate(str(destination), title="Fictional Northstar Onboarding", author="Demo dataset").build(story)
print(destination)
