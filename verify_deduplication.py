#!/usr/bin/env python3
"""
Verification script to test deduplication logic in get_jobs_without_analysis()
"""

from utils.sqlite_storage import SQLiteStorage
from collections import Counter

def verify_deduplication():
    """Verify that get_jobs_without_analysis() returns max 2 jobs per (title, company) pair"""

    storage = SQLiteStorage()

    print("=" * 80)
    print("DEDUPLICATION VERIFICATION TEST")
    print("=" * 80)
    print()

    # Get jobs without analysis
    print("Fetching jobs without analysis...")
    jobs = storage.get_jobs_without_analysis()
    print(f"✓ Total jobs to analyze: {len(jobs)}")
    print()

    if not jobs:
        print("⚠️  No unanalyzed jobs found. Run the scraper first:")
        print("   python main.py")
        return

    # Count occurrences of each (title, company) pair
    print("Checking for duplicate (title, company) pairs...")
    titles_companies = [(j['title'], j['company']) for j in jobs]
    pair_counts = Counter(titles_companies)

    # Find any pairs that appear more than 2 times
    duplicates = {pair: count for pair, count in pair_counts.items() if count > 2}

    if duplicates:
        print(f"❌ FAILED: Found {len(duplicates)} pairs with more than 2 occurrences:")
        print()
        for (title, company), count in sorted(duplicates.items(), key=lambda x: x[1], reverse=True):
            print(f"   • {count}x: '{title}' at '{company}'")
        print()
        print("The deduplication logic is NOT working correctly.")
        return False
    else:
        max_duplicates = max(pair_counts.values()) if pair_counts else 0
        print(f"✅ PASSED: Max duplicates per (title, company) pair: {max_duplicates}")
        print()

        # Show distribution
        distribution = Counter(pair_counts.values())
        print("Distribution of job counts per (title, company):")
        for count in sorted(distribution.keys()):
            num_pairs = distribution[count]
            print(f"   • {num_pairs} pairs appear {count} time(s)")
        print()

        print("✅ Deduplication is working correctly!")
        print()

        # Show some examples
        if len(jobs) > 0:
            print("Sample jobs to be analyzed:")
            for i, job in enumerate(jobs[:5], 1):
                print(f"   {i}. {job['title']} at {job['company']}")

        return True

def check_database_stats():
    """Show database statistics"""
    import sqlite3

    print()
    print("=" * 80)
    print("DATABASE STATISTICS")
    print("=" * 80)
    print()

    storage = SQLiteStorage()
    conn = sqlite3.connect(storage.db_file)
    cursor = conn.cursor()

    # Total jobs
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]
    print(f"Total jobs in database: {total_jobs}")

    # Analyzed jobs
    cursor.execute("SELECT COUNT(DISTINCT job_id) FROM job_analyses")
    analyzed_jobs = cursor.fetchone()[0]
    print(f"Jobs with analysis: {analyzed_jobs}")
    print(f"Jobs without analysis: {total_jobs - analyzed_jobs}")
    print()

    # Duplicate statistics
    cursor.execute("""
        SELECT COUNT(*) as count, COUNT(DISTINCT title || '||' || company) as unique_pairs
        FROM jobs
    """)
    total, unique = cursor.fetchone()
    print(f"Unique (title, company) pairs: {unique}")
    print(f"Average jobs per pair: {total / unique:.1f}")
    print()

    # Top duplicates
    print("Top 10 jobs with most duplicates:")
    cursor.execute("""
        SELECT title, company, COUNT(*) as count
        FROM jobs
        GROUP BY title, company
        HAVING count > 1
        ORDER BY count DESC
        LIMIT 10
    """)

    for i, (title, company, count) in enumerate(cursor.fetchall(), 1):
        print(f"   {i}. {count}x: '{title}' at '{company}'")

    conn.close()

if __name__ == "__main__":
    # Run verification
    success = verify_deduplication()

    # Show database stats
    check_database_stats()

    print()
    print("=" * 80)

    if success:
        print("✅ All checks passed! Ready to run analysis.")
        print()
        print("Next steps:")
        print("   python main.py  # Run keyword analysis with deduplication")
    else:
        print("❌ Verification failed. Check the implementation.")
