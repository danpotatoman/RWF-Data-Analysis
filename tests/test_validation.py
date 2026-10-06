import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from graphql import build_schema, graphql_sync, get_introspection_query
from rwf.probe import ProbeError, Response
from rwf.validation import (Session, compare_rosters, cost_delta, event_pages,
                            estimated_target_cost, latest, paginate, roster_key, validate_queries)


class ValidationTests(unittest.TestCase):
    def test_schema_validator_checks_types_fields_enums_and_nullability(self):
        schema = build_schema('enum Kind { A } type Query { sample(id: Int!, kind: Kind): Int }')
        data = graphql_sync(schema, get_introspection_query()).data
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'valid.graphql').write_text('query($id:Int!){ sample(id:$id,kind:A) }')
            (p / 'invalid.graphql').write_text('query($id:String){ sample(id:$id,kind:B) missing }')
            results = validate_queries(data, p)
            self.assertEqual(results['valid.graphql'], [])
            self.assertEqual(len(results['invalid.graphql']), 3)
            (p / 'null.graphql').write_text('query($id:Int){ sample(id:$id) }')
            self.assertTrue(validate_queries(data, p)['null.graphql'])
            (p / 'syntax.graphql').write_text('query {')
            self.assertTrue(validate_queries(data, p)['syntax.graphql'])

    def test_pagination_terminal_and_duplicates_preserved(self):
        fetch = Mock(side_effect=[dict(current_page=1, data=[1], has_more_pages=True),
                                  dict(current_page=2, data=[1, 2], has_more_pages=False)])
        rows, pages = paginate(fetch)
        self.assertEqual(rows, [1, 1, 2])
        self.assertEqual(len(pages), 2)
        self.assertEqual(fetch.call_count, 2)

    def test_page_budget_and_invalid_or_partial_pages_fail(self):
        for bad in (None, {}, dict(current_page=2, data=[], has_more_pages=False),
                    dict(current_page=1, data=None, has_more_pages=False),
                    dict(current_page=1, data=[], has_more_pages=0)):
            with self.subTest(bad=bad), self.assertRaises(ProbeError):
                paginate(lambda p: bad)
        with self.assertRaisesRegex(ProbeError, 'budget'):
            paginate(lambda p: dict(current_page=p, data=[], has_more_pages=True), max_pages=2)

    def test_event_pagination_uses_exact_cursor_and_allows_oversize_page(self):
        fetch = Mock(side_effect=[dict(data=[1]*107, nextPageTimestamp=200),
                                  dict(data=[2], nextPageTimestamp=None)])
        pages = event_pages(fetch, 100, 1000)
        self.assertEqual([len(p['data']) for p in pages], [107, 1])
        self.assertEqual([c.args[0] for c in fetch.call_args_list], [100, 200])

    def test_event_invalid_cursors_and_missing_terminal_key_fail(self):
        for cursor in (100, 99, 1001, True, '200', float('nan')):
            with self.subTest(cursor=cursor), self.assertRaises(ProbeError):
                event_pages(lambda p: dict(data=[], nextPageTimestamp=cursor), 100, 1000)
        with self.assertRaises(ProbeError):
            event_pages(lambda p: dict(data=[]), 100, 1000)
        with self.assertRaisesRegex(ProbeError, 'budget'):
            event_pages(lambda p: dict(data=[], nextPageTimestamp=p+1), 0, 100, max_pages=2)

    def test_roster_matching_preserves_realms_and_string_match_counts(self):
        w = [{'name':'ImFiReDuP', 'server':{'slug':'one'}}, {'name':'IMFIREDUP', 'server':{'slug':'two'}}]
        b = [{'character':{'name':'imfiredup','realm':{'slug':'one'}}},
             {'character':{'name':'Other','realm':{'slug':'one'}}}]
        result = compare_rosters(w, b)
        self.assertEqual((result['overlap'],result['wcl_only'],result['blizzard_only']), (1,1,1))
        self.assertEqual(result['imfiredup_wcl_characters'], 2)
        self.assertEqual(result['imfiredup_wcl'], ['imfiredup'])
        self.assertEqual(len(result['imfiredup_addresses']), 2)
        self.assertEqual(roster_key('E\u0301','ONE','US'), roster_key('\u00c9','one','us'))

    def test_cost_delta_detects_reset_and_preserves_fractional_cost(self):
        before = dict(pointsSpentThisHour=10, pointsResetIn=100)
        self.assertEqual(cost_delta(before, dict(pointsSpentThisHour=13.03, pointsResetIn=97)), 3.03)
        self.assertIsNone(cost_delta(before, dict(pointsSpentThisHour=0, pointsResetIn=3600)))
        self.assertIsNone(cost_delta(before, dict(pointsSpentThisHour=20, pointsResetIn=3600)))

    def test_target_cost_subtracts_observer_and_rejects_reset_or_underflow(self):
        before = dict(pointsSpentThisHour=10, pointsResetIn=100)
        after = dict(pointsSpentThisHour=13.03, pointsResetIn=97)
        self.assertEqual(estimated_target_cost(before, after), 2.03)
        self.assertEqual(estimated_target_cost(before, after, observer_cost=2), 1.03)
        self.assertIsNone(estimated_target_cost(before, dict(pointsSpentThisHour=10.5, pointsResetIn=97)))
        self.assertIsNone(estimated_target_cost(before, dict(pointsSpentThisHour=1, pointsResetIn=3600)))

    def test_blizzard_token_failure_does_not_save_stale_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            s = Session(Path(directory))
            try:
                s.last_response = Mock(return_value=('previous', 200, {'old': True}))
                s.clients['blizzard'] = Mock()
                s.clients['blizzard'].request.side_effect = ProbeError('OAuth failed')
                with self.assertRaisesRegex(ProbeError, 'before a new'):
                    s.blizzard('failed', 'equipment', realm='test', name='test')
                self.assertFalse((s.root / 'index.jsonl').exists())
            finally:
                s.close()

    def test_blizzard_http_failure_saves_its_own_response(self):
        with tempfile.TemporaryDirectory() as directory:
            s = Session(Path(directory))
            try:
                s.last_response = Mock(side_effect=[('previous', 200, {}), ('new', 404, {'code': 404})])
                s.clients['blizzard'] = Mock()
                s.clients['blizzard'].request.side_effect = ProbeError('HTTP 404')
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertIsNone(s.blizzard('failed', 'equipment', realm='test', name='test'))
                self.assertEqual(latest('failed', s.root), {'code': 404})
            finally:
                s.close()

    def test_session_archives_evidence_and_correlates_cost_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            s=Session(Path(directory))
            self.addCleanup(s.close)
            # Session uses the existing authenticated client's archive; this fake
            # writes synthetic bodies without receiving any actual credentials.
            count=0
            def request(url, payload):
                nonlocal count
                count+=1
                value={'data':{'rateLimitData':dict(limitPerHour=3600, pointsSpentThisHour=count, pointsResetIn=100-count)}}
                s.archive.save(str(count),'wcl',{'query':payload['query']},'now',Response(200,{},json.dumps(value).encode()))
                return value
            s.clients['wcl']=Mock(request=request)
            with contextlib.redirect_stdout(io.StringIO()):
                s.wcl('test','query { sample }')
            costs=json.loads((s.root/'costs.jsonl').read_text())
            self.assertEqual((costs['before_attempt'],costs['attempt'],costs['after_attempt']), ('1','2','3'))
            self.assertEqual(costs['delta'],2)
            self.assertIn('data',latest('test',s.root))
            s.save('test',{'new':1})
            self.assertEqual(latest('test',s.root), {'new':1})
            self.assertEqual(len(list(s.root.glob('*-test.json'))),2)
            s.close()

    def test_session_budget_stops_target_call(self):
        with tempfile.TemporaryDirectory() as directory:
            s=Session(Path(directory))
            try:
                s.rate=Mock(return_value=dict(limitPerHour=100,pointsSpentThisHour=51,pointsResetIn=100))
                with self.assertRaisesRegex(ProbeError,'budget'):
                    s.wcl('test','query { sample }')
            finally:s.close()

    def test_no_new_api_attempt_is_not_mislabeled_as_previous_response(self):
        with tempfile.TemporaryDirectory() as directory:
            s=Session(Path(directory))
            try:
                s.rate=Mock(return_value=dict(limitPerHour=100,pointsSpentThisHour=1,pointsResetIn=100))
                s.last_response=Mock(return_value=('previous',200,{'data':{}}))
                s.clients['wcl']=Mock()
                s.clients['wcl'].request.side_effect=ProbeError('OAuth failed')
                with self.assertRaisesRegex(ProbeError,'before a new'):
                    s.wcl('test','query { sample }')
            finally:s.close()
