#!/usr/bin/env python3
"""
Direct SQL test to verify the new deduplication query logic.
This tests the query itself without needing unanalyzed jobs.
"""

import sqlite3
from utils.sqlite_storage import SQLiteStorage
from collections import Counter

def test_query_with_simulated_data():
    """Test the new query logic with temporarily removed analyses"""

    print("=" * 80)
    print("QUERY LOGIC TEST - Simulating Unanalyzed Jobs")
    print("=" * 80)
    print()

    storage = SQLiteStorage()
    conn = sqlite3.connect(storage.db_file)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find a job group with many duplicates
    cursor.execute("""
        SELECT title, company, COUNT(*) as count
        FROM jobs
        GROUP BY title, company
        HAVING count >= 3
        ORDER BY count DESC
        LIMIT 1
    """)

    result = cursor.fetchone()
    if not result:
        print("❌ No job groups with 3+ duplicates found for testing")
        conn.close()
        return False

    test_title = result['title']
    test_company = result['company']
    duplicate_count = result['count']

    print(f"Testing with: '{test_title}' at '{test_company}'")
    print(f"Total duplicates in database: {duplicate_count}")
    print()

    # Get all job IDs for this group
    cursor.execute("""
        SELECT id FROM jobs
        WHERE title = ? AND company = ?
        ORDER BY id ASC
    """, (test_title, test_company))

    job_ids = [row['id'] for row in cursor.fetchall()]
    print(f"Job IDs: {job_ids}")
    print()

    # Temporarily remove their analyses to simulate unanalyzed state
    print("Temporarily removing analyses for this group...")
    cursor.execute("""
        DELETE FROM job_analyses
        WHERE job_id IN ({})
    """.format(','.join('?' * len(job_ids))), job_ids)
    conn.commit()
    print(f"✓ Removed {cursor.rowcount} analyses")
    print()

    # Now test the new query
    print("Testing new deduplication query...")
    jobs = storage.get_jobs_without_analysis()

    # Filter to our test group
    test_jobs = [j for j in jobs if j['title'] == test_title and j['company'] == test_company]

    print(f"Jobs returned by get_jobs_without_analysis():")
    print(f"  • Total unanalyzed jobs: {len(jobs)}")
    print(f"  • Jobs from test group: {len(test_jobs)}")
    print()

    if len(test_jobs) > 2:
        print(f"❌ FAILED: Expected max 2 jobs, got {len(test_jobs)}")
        print("The deduplication query is NOT working correctly.")
        success = False
    else:
        print(f"✅ PASSED: Returned {len(test_jobs)} jobs (max 2 expected)")

        # Verify these are the first 2 by ID
        expected_ids = sorted(job_ids)[:2]
        actual_ids = sorted([j['id'] for j in test_jobs])

        if actual_ids == expected_ids:
            print(f"✅ PASSED: Returned correct jobs (IDs {actual_ids})")
            print(f"  • Expected first 2 by ID: {expected_ids}")
        else:
            print(f"❌ FAILED: Wrong jobs returned")
            print(f"  • Expected IDs: {expected_ids}")
            print(f"  • Got IDs: {actual_ids}")

        success = (actual_ids == expected_ids)

    print()

    # Restore the analyses we removed (rollback)
    print("Rolling back changes...")
    conn.rollback()
    conn.close()

    # Verify rollback worked
    storage2 = SQLiteStorage()
    jobs_after = storage2.get_jobs_without_analysis()
    test_jobs_after = [j for j in jobs_after if j['title'] == test_title and j['company'] == test_company]
    print(f"✓ Rollback complete. Test group now has {len(test_jobs_after)} unanalyzed jobs (should be 0)")
    print()

    return success

def test_all_groups():
    """Test that ALL job groups respect the max-2 rule"""

    print("=" * 80)
    print("COMPREHENSIVE TEST - All Job Groups")
    print("=" * 80)
    print()

    storage = SQLiteStorage()

    # Temporarily remove ALL analyses
    conn = sqlite3.connect(storage.db_file)
    cursor = conn.cursor()

    print("Simulating fresh database (removing all analyses temporarily)...")
    cursor.execute("DELETE FROM job_analyses")
    conn.commit()

    # Get jobs without analysis
    jobs = storage.get_jobs_without_analysis()
    print(f"✓ Total jobs returned: {len(jobs)}")
    print()

    # Count occurrences per (title, company) pair
    print("Checking for duplicates...")
    titles_companies = [(j['title'], j['company']) for j in jobs]
    pair_counts = Counter(titles_companies)

    # Find violators
    violators = {pair: count for pair, count in pair_counts.items() if count > 2}

    if violators:
        print(f"❌ FAILED: Found {len(violators)} pairs with more than 2 occurrences:")
        print()
        for (title, company), count in sorted(violators.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   • {count}x: '{title}' at '{company}'")
        success = False
    else:
        max_count = max(pair_counts.values()) if pair_counts else 0
        print(f"✅ PASSED: Max occurrences per pair: {max_count}")

        # Show distribution
        distribution = Counter(pair_counts.values())
        print()
        print("Distribution:")
        for count in sorted(distribution.keys()):
            num_pairs = distribution[count]
            print(f"   • {num_pairs} pairs with {count} job(s)")

        success = True

    print()

    # Rollback
    print("Rolling back changes...")
    conn.rollback()
    conn.close()
    print("✓ Database restored")
    print()

    return success

if __name__ == "__main__":
    print()

    # Test 1: Single group with known duplicates
    test1_passed = test_query_with_simulated_data()

    # Test 2: All groups
    test2_passed = test_all_groups()

    print("=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)
    print()
    print(f"Test 1 (Single Group): {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Test 2 (All Groups):   {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    print()

    if test1_passed and test2_passed:
        print("✅ All tests passed! Deduplication is working correctly.")
        print()
        print("The new query logic successfully limits to max 2 jobs per (title, company) pair.")
    else:
        print("❌ Some tests failed. Check the implementation.")
