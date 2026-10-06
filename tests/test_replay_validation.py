from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rwf.replay_validation import audit_fights, field_counts, gear_overlap, main


class ReplayTests(unittest.TestCase):
    def test_fight_times_alignment_missing_arrays_and_unresolved_actor(self):
        report = dict(startTime=1000000, endTime=1001000, masterData={'actors':[{'id':1}]}, fights=[
            dict(id=1,startTime=0,endTime=500,friendlyPlayers=[1],friendlySpecs=[2],friendlyItemLevels=[3]),
            dict(id=2,startTime=1,endTime=1001,friendlyPlayers=[9],friendlySpecs=[],friendlyItemLevels=[3]),
            dict(id=3,startTime=1,endTime=2,friendlyPlayers=None,friendlySpecs=None,friendlyItemLevels=None)])
        rows = audit_fights(report)
        self.assertTrue(rows[0]['aligned'])
        self.assertEqual(rows[0]['absolute_start'], '1970-01-01T00:16:40+00:00')
        self.assertFalse(rows[1]['aligned'])
        self.assertFalse(rows[1]['within_report'])
        self.assertEqual(rows[1]['unresolved_actors'], 1)
        self.assertFalse(rows[2]['aligned'])

    def test_gear_overlap_retains_multiplicity_ignores_zero_placeholders(self):
        w = [dict(id=1,itemLevel=10),dict(id=1,itemLevel=10),dict(id=2,itemLevel=20),dict(id=0,itemLevel=0)]
        b = [dict(item={'id':1},level={'value':10}),dict(item={'id':2},level={'value':21})]
        self.assertEqual(gear_overlap(w,b), dict(wcl_nonzero_entries=3,blizzard_entries=2,shared_item_ids=2,shared_id_level=1))

    def test_missing_null_and_false_remain_distinct(self):
        self.assertEqual(field_counts([{}, {'a':None}, {'a':False}], ['a']),
                         {'a':dict(present=2,null=1,missing=1)})

    def test_main_prints_only_replayed_result(self):
        with patch('rwf.replay_validation.replay',return_value={'network_calls':0}), patch('builtins.print') as out:
            main()
        self.assertIn('"network_calls": 0', out.call_args.args[0])
