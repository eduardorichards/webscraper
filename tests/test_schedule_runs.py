"""Tests for schedule run tracking: storage, /api/schedule-runs, /api/reviews and
/api/shortlist?exclude_reviewed (Flask test client, temp DB)."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest import mock

import web_app
from utils.sqlite_storage import SQLiteStorage


def _ago(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).strftime('%Y-%m-%dT%H:%M:%SZ')


JOB_IDS = ['4100000001', '4100000002', '4100000003', '4100000004']


class ScheduleRunsTestCase(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        db_path = self.db_path

        class TempStorage(SQLiteStorage):
            def __init__(self, db_file=None):
                with redirect_stdout(StringIO()):
                    super().__init__(db_file=db_file or db_path)

        self.storage = TempStorage()
        conn = sqlite3.connect(self.db_path)
        for i, job_id in enumerate(JOB_IDS):
            conn.execute("INSERT INTO job_searches (linkedin_job_id, title, company)"
                         " VALUES (?, ?, ?)", (job_id, 'Dev %d' % i, 'Co %d' % i))
            conn.execute("INSERT INTO job_posts (linkedin_job_id, date_time, weighted_score,"
                         " seniority_level, apply_type) VALUES (?, ?, ?, 'Entry level',"
                         " 'external')", (job_id, _ago(minutes=10 + i), 50.0 - i))
        conn.commit()
        conn.close()

        patcher = mock.patch.object(web_app, 'SQLiteStorage', TempStorage)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = web_app.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def _post(self, url, body=None, status=200):
        response = self.client.post(url, json=body if body is not None else {})
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        return response.get_json()

    def _backdate(self, run_id, started_at):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE schedule_runs SET started_at = ? WHERE id = ?",
                     (started_at, run_id))
        conn.commit()
        conn.close()


class TestScheduleRunsStorage(ScheduleRunsTestCase):

    def test_first_run_has_no_checkpoint(self):
        run = self.storage.start_schedule_run('apply')
        self.assertEqual(run['status'], 'running')
        self.assertIsNone(run['window_from'])
        self.assertIsNone(run['finished_at'])
        self.assertEqual(run['counts'], {})
        self.assertRegex(run['started_at'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')

    def test_checkpoint_is_start_of_last_completed_run(self):
        first = self.storage.start_schedule_run('apply')
        self._backdate(first['id'], _ago(hours=5))
        self.storage.finish_schedule_run(first['id'], 'completed')
        second = self.storage.start_schedule_run('apply')
        self.assertEqual(second['window_from'], _ago(hours=5))

    def test_interrupted_and_failed_runs_do_not_advance_checkpoint(self):
        done = self.storage.start_schedule_run('apply')
        self._backdate(done['id'], _ago(hours=9))
        self.storage.finish_schedule_run(done['id'], 'completed')
        for status in ('interrupted', 'failed'):
            run = self.storage.start_schedule_run('apply')
            self.assertEqual(run['window_from'], _ago(hours=9))
            self.storage.finish_schedule_run(run['id'], status)

    def test_checkpoint_is_per_name(self):
        other = self.storage.start_schedule_run('other')
        self.storage.finish_schedule_run(other['id'], 'completed')
        self.assertIsNone(self.storage.start_schedule_run('apply')['window_from'])

    def test_explicit_window_from_wins(self):
        run = self.storage.start_schedule_run('apply', window_from='2026-11-17T13:00:00Z')
        self.assertEqual(run['window_from'], '2026-11-17T13:00:00Z')

    def test_starting_closes_stale_running_run(self):
        stale = self.storage.start_schedule_run('apply')
        self.storage.start_schedule_run('apply')
        stale = self.storage.get_schedule_run(stale['id'])
        self.assertEqual(stale['status'], 'interrupted')
        self.assertIsNotNone(stale['finished_at'])

    def test_finish_unknown_run_and_invalid_status(self):
        self.assertIsNone(self.storage.finish_schedule_run(999, 'completed'))
        run = self.storage.start_schedule_run('apply')
        with self.assertRaises(ValueError):
            self.storage.finish_schedule_run(run['id'], 'running')

    def test_review_upsert_keeps_first_reviewed_at(self):
        self.storage.save_job_review(JOB_IDS[0], 'unprocessed')
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE job_reviews SET reviewed_at = '2026-11-01T00:00:00Z'")
        conn.commit()
        conn.close()
        self.storage.save_job_review(JOB_IDS[0], 'skipped', 'closed')
        [review] = self.storage.get_job_reviews()
        self.assertEqual(review['status'], 'skipped')
        self.assertEqual(review['reason'], 'closed')
        self.assertEqual(review['reviewed_at'], '2026-11-01T00:00:00Z')
        with self.assertRaises(ValueError):
            self.storage.save_job_review(JOB_IDS[0], 'sent')

    def test_run_counts_and_listing_order(self):
        old = self.storage.start_schedule_run('apply')
        self._backdate(old['id'], _ago(hours=3))
        run = self.storage.start_schedule_run('apply')
        self.storage.save_job_review(JOB_IDS[0], 'skipped', run_id=run['id'])
        self.storage.save_job_review(JOB_IDS[1], 'skipped', run_id=run['id'])
        self.storage.save_job_review(JOB_IDS[2], 'ready', run_id=run['id'])
        runs = self.storage.list_schedule_runs(name='apply')
        self.assertEqual([r['id'] for r in runs], [run['id'], old['id']])
        self.assertEqual(runs[0]['counts'], {'skipped': 2, 'ready': 1})
        self.assertEqual(self.storage.list_schedule_runs(limit=1)[0]['id'], run['id'])
        self.assertEqual(self.storage.list_schedule_runs(name='nope'), [])

    def test_hide_reviewed_filter(self):
        for job_id, status in zip(JOB_IDS, ('ready', 'skipped', 'partial', 'unprocessed')):
            self.storage.save_job_review(job_id, status)
        ids = lambda **kw: [j['linkedin_job_id'] for j in self.storage.get_job_summary(
            unique=True, per_page=None, sort='weighted_score', direction='desc', **kw)]
        self.assertEqual(ids(), JOB_IDS)
        self.assertEqual(ids(hide_reviewed=True), JOB_IDS[2:])


class TestScheduleRunsApi(ScheduleRunsTestCase):

    def test_run_lifecycle(self):
        run = self._post('/api/schedule-runs', {}, status=201)
        self.assertEqual(run['name'], 'apply')
        self.assertEqual(run['status'], 'running')
        self.assertIsNone(run['suggested_since'])

        finished = self._post('/api/schedule-runs/%d/finish' % run['id'],
                              {'status': 'completed', 'summary': '3 ready, 2 skipped'})
        self.assertEqual(finished['status'], 'completed')
        self.assertEqual(finished['summary'], '3 ready, 2 skipped')
        self.assertIsNotNone(finished['finished_at'])

        listing = self.client.get('/api/schedule-runs').get_json()
        self.assertEqual([r['id'] for r in listing], [run['id']])

    def test_next_run_gets_checkpoint_and_suggested_since(self):
        first = self._post('/api/schedule-runs', {}, status=201)
        self._backdate(first['id'], _ago(hours=5, minutes=20))
        self._post('/api/schedule-runs/%d/finish' % first['id'], {'status': 'completed'})
        second = self._post('/api/schedule-runs', {}, status=201)
        self.assertEqual(second['window_from'], _ago(hours=5, minutes=20))
        # 5 h 20 min rounds up to 6 h, plus 1 h of margin
        self.assertEqual(second['suggested_since'], '7h')

    def test_start_validation(self):
        self._post('/api/schedule-runs', {'name': 'x' * 51}, status=400)
        self._post('/api/schedule-runs', {'window_from': 'yesterday'}, status=400)
        self._post('/api/schedule-runs', {'window_from': '2026-11-17'}, status=400)
        run = self._post('/api/schedule-runs', {'name': ' nightly ',
                                                'window_from': '2026-11-17T13:00:00Z'},
                         status=201)
        self.assertEqual((run['name'], run['window_from']),
                         ('nightly', '2026-11-17T13:00:00Z'))

    def test_finish_validation(self):
        run = self._post('/api/schedule-runs', {}, status=201)
        url = '/api/schedule-runs/%d/finish' % run['id']
        self._post(url, {}, status=400)
        self._post(url, {'status': 'running'}, status=400)
        self._post(url, {'status': 'completed', 'summary': 'x' * 2001}, status=400)
        self._post('/api/schedule-runs/999/finish', {'status': 'completed'}, status=404)

    def test_list_validation(self):
        for query in ('?limit=0', '?limit=101', '?limit=abc'):
            with self.subTest(query=query):
                self.assertEqual(self.client.get('/api/schedule-runs' + query).status_code,
                                 400)
                self.assertEqual(self.client.get('/api/reviews' + query).status_code, 400)

    def test_review_flow(self):
        run = self._post('/api/schedule-runs', {}, status=201)
        saved = self._post('/api/reviews', {'linkedin_job_id': JOB_IDS[0],
                                            'status': 'skipped', 'reason': 'aggregator',
                                            'run_id': run['id']})
        self.assertEqual(saved['review_status'], 'skipped')
        self._post('/api/reviews', {'linkedin_job_id': JOB_IDS[1], 'status': 'ready',
                                    'run_id': run['id']})
        reviews = self.client.get('/api/reviews?run_id=%d' % run['id']).get_json()
        self.assertEqual({r['linkedin_job_id'] for r in reviews}, set(JOB_IDS[:2]))
        only_ready = self.client.get('/api/reviews?status=ready').get_json()
        self.assertEqual([r['linkedin_job_id'] for r in only_ready], [JOB_IDS[1]])
        listing = self.client.get('/api/schedule-runs').get_json()
        self.assertEqual(listing[0]['counts'], {'skipped': 1, 'ready': 1})

        response = self.client.open('/api/reviews', method='DELETE',
                                    json={'linkedin_job_id': JOB_IDS[0]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.client.get('/api/reviews').get_json()), 1)

    def test_review_validation(self):
        good = {'linkedin_job_id': JOB_IDS[0], 'status': 'skipped'}
        self._post('/api/reviews', dict(good, linkedin_job_id='nope'), status=400)
        self._post('/api/reviews', dict(good, status='sent'), status=400)
        self._post('/api/reviews', {'linkedin_job_id': JOB_IDS[0]}, status=400)
        self._post('/api/reviews', dict(good, reason='x' * 501), status=400)
        self._post('/api/reviews', dict(good, run_id='1'), status=400)
        self._post('/api/reviews', dict(good, run_id=True), status=400)
        self._post('/api/reviews', dict(good, run_id=999), status=404)
        self._post('/api/reviews', dict(good, linkedin_job_id='4199999999'), status=404)
        self.assertEqual(self.client.get('/api/reviews?status=sent').status_code, 400)
        self.assertEqual(self.client.get('/api/reviews?run_id=abc').status_code, 400)
        self.assertEqual(self.client.get('/api/reviews').get_json(), [])

    def test_shortlist_exclude_reviewed(self):
        def shortlist(query):
            response = self.client.get('/api/shortlist?since=3h&apply=all' + query)
            self.assertEqual(response.status_code, 200)
            return [j['linkedin_job_id'] for j in response.get_json()['jobs']]

        for job_id, status in zip(JOB_IDS, ('ready', 'skipped', 'partial', 'unprocessed')):
            self._post('/api/reviews', {'linkedin_job_id': job_id, 'status': status})
        self.assertEqual(shortlist(''), JOB_IDS)
        self.assertEqual(shortlist('&exclude_reviewed=0'), JOB_IDS)
        self.assertEqual(shortlist('&exclude_reviewed=1'), JOB_IDS[2:])
        self.assertEqual(shortlist('&exclude_reviewed=TRUE'), JOB_IDS[2:])
        data = self.client.get('/api/shortlist?exclude_reviewed=1').get_json()
        self.assertTrue(data['params']['exclude_reviewed'])
        # Reopening a job puts it back
        self.client.open('/api/reviews', method='DELETE',
                         json={'linkedin_job_id': JOB_IDS[1]})
        self.assertEqual(shortlist('&exclude_reviewed=1'), JOB_IDS[1:])

    def test_shortlist_exclude_reviewed_invalid(self):
        response = self.client.get('/api/shortlist?exclude_reviewed=maybe')
        self.assertEqual(response.status_code, 400)
        self.assertIn('exclude_reviewed', response.get_json()['invalid'])


if __name__ == '__main__':
    unittest.main()
