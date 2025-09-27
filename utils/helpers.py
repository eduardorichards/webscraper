import csv
import pandas as pd
import re
from datetime import datetime

def clean_text(text):
    """Clean and normalize text data"""
    if not text:
        return ""
    
    cleaned = ' '.join(text.split())
    cleaned = re.sub(r'[^\w\s\-\.,!?()]', '', cleaned)

                     
    return cleaned.strip()
    
def save_to_csv(jobs_data, filename="data/offers.csv"):
    """Save job to CSV file"""
    try:
        df = pd.DataFrame(jobs_data)
        df.to_csv(filename, index=False)
        print(f"✅ Data saved to {filename}")
        return True
    except Exception as e:
        print(f"❌ Error saving data: {e}")
        return False
    
def print_job_summary(job):
    """Print a formatted summary of a job"""
    print(f"""
    📋 Job Title: {job.get('title', 'N/A')}
    🏢 Company: {job.get('company', 'N/A')}
    📍 Location: {job.get('location', 'N/A')}
    💰 Salary: {job.get('salary', 'N/A')}
    🔗 URL: {job.get('url', 'N/A')}
    """)