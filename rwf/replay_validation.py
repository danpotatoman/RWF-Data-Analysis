"""Recompute aggregate feasibility findings offline from ignored local artifacts.

No clients, OAuth exchanges, or network calls. Prints aggregate findings only.
"""
from collections import Counter
from datetime import datetime, timezone
import json

from rwf.validation import ROOT, compare_rosters, estimated_target_cost, latest, validate_queries


def audit_fights(report):
    actors = {a['id'] for a in report['masterData']['actors']}
    rows = []
    for fight in report['fights']:
        arrays = [fight.get(k) for k in ('friendlyPlayers', 'friendlySpecs', 'friendlyItemLevels')]
        aligned = all(isinstance(a, list) for a in arrays) and len({len(a) for a in arrays}) == 1
        rows.append(dict(
            id=fight['id'], aligned=aligned,
            unresolved_actors=sum(a not in actors for a in (arrays[0] or [])),
            within_report=0 <= fight['startTime'] <= fight['endTime'] <= report['endTime']-report['startTime'],
            absolute_start=datetime.fromtimestamp((report['startTime']+fight['startTime'])/1000, timezone.utc).isoformat(),
            absolute_end=datetime.fromtimestamp((report['startTime']+fight['endTime'])/1000, timezone.utc).isoformat()))
    return rows


def gear_overlap(wcl_gear, blizzard_items):
    """Multiset overlap, NOT slot or identity matching, and NOT acquisition evidence."""
    w = Counter((r['id'], r.get('itemLevel')) for r in wcl_gear if r['id'])
    b = Counter((r['item']['id'], r['level']['value']) for r in blizzard_items)
    wi, bi = Counter(), Counter()
    for (item, _), count in w.items():
        wi[item] += count
    for (item, _), count in b.items():
        bi[item] += count
    return dict(wcl_nonzero_entries=sum(w.values()), blizzard_entries=sum(b.values()),
                shared_item_ids=sum((wi & bi).values()), shared_id_level=sum((w & b).values()))


def field_counts(items, fields):
    return {key: dict(present=sum(key in r for r in items),
                      null=sum(key in r and r[key] is None for r in items),
                      missing=sum(key not in r for r in items)) for key in fields}


def replay(root=ROOT):
    def get(label):
        return latest(label, root)
    results = {'evidence_date': '2026-09-17', 'network_calls': 0,
               'schema': validate_queries(get('full-schema')['data'])}
    wcl = get('wcl-roster')['rows']
    # This study has one verified region. Do not silently mix other regions.
    if {r['server']['region']['name'] for r in wcl} != {'United States'}:
        raise ValueError('Reconcile regions before comparing rosters')
    results['roster'] = compare_rosters(wcl, get('blizzard-roster')['members'])
    items = [r for i in range(3) for r in get(f'sample-{i}-equipment')['equipped_items']]
    results['equipment_fields'] = field_counts(items, [
        'item', 'slot', 'level', 'bonus_list', 'context', 'modified_crafting_stat',
        'set', 'sockets', 'enchantments', 'spells', 'name_description'])
    codes = ['AjJV74zaLcTkYNvK', 'PXm9nVyY6c2MHQCq', 'DZzR9jwYmQA6tbV7']
    reports = {code: get('report-'+code)['data']['reportData']['report'] for code in codes}
    results['fights'] = {code: audit_fights(r) for code, r in reports.items()}
    current = get('sample-1-equipment')['equipped_items']
    results['gear_comparisons'] = []
    for code, label, actor_id, fight_id in [
        (codes[0], 'combatants-one-fight', 77, 2),
        (codes[1], 'combatants-page-0', 541, 20)]:
        actor = next(a for a in reports[code]['masterData']['actors'] if a['id'] == actor_id)
        if actor['gameID'] != get('sample-1-character')['id']:
            raise ValueError('Sample identity evidence changed')
        event = next(e for e in get(label)['data']['reportData']['report']['events']['data']
                     if e['sourceID'] == actor_id and e['fight'] == fight_id)
        results['gear_comparisons'].append(dict(report=code, fight=fight_id,
                                              **gear_overlap(event['gear'], current)))
    results['event_pages'] = []
    for cursor in [2847821, 2848017, 2848633]:
        page = get(f'all-events-page-{cursor}')['data']['reportData']['report']['events']
        results['event_pages'].append(dict(start=cursor, count=len(page['data']),
            next=page['nextPageTimestamp'], first=min(e['timestamp'] for e in page['data']),
            last=max(e['timestamp'] for e in page['data'])))
    results['compositions'] = []
    for encounter in [3470, 3492]:
        for difficulty in [4, 5]:
            value = get(f'composition-{encounter}-{difficulty}')['data']['progressRaceData']['detailedComposition']
            players = [p for role in value['roles'] for p in role['players']]
            results['compositions'].append(dict(encounter=encounter, difficulty=difficulty,
                players=len(players), gear_slots=sorted({g['slot'] for p in players for g in p['gearItems']})))
    costs = [json.loads(line) for line in (root/'costs.jsonl').read_text().splitlines()]
    results['costs'] = [dict(label=c['label'], query_sha256=c['query_sha256'],
        attempt=c['attempt'], observed_delta=c['delta'],
        estimated_target=estimated_target_cost(c['before'], c['after'])) for c in costs]
    return results


def main():
    print(json.dumps(replay(), ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
