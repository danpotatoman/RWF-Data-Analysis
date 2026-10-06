"""Read-only raw replay. Projections are disposable outputs, never collector inputs."""
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

from rwf.pilot_state import VERSION, dumps, read_database, code_signature, SNAPSHOT_LAG

TEXT_KEYS={'name','description','display_string','name_description','key','media','icon',
           'transmog','modified_appearance_id','durability','sell_price'}


def semantic(value):
    if isinstance(value,dict):
        return {k:semantic(v) for k,v in value.items() if k not in TEXT_KEYS}
    if isinstance(value,list):
        return sorted((semantic(v) for v in value),key=dumps)
    return value


def present(value, field):
    return dict(present=field in value, value=value.get(field))


def equipment(payload):
    """No empty projection for an unknown shape; retain source ordinal and slot ambiguity."""
    if not isinstance(payload.get('equipped_items'),list):
        raise ValueError('equipment list missing')
    entries=[]; slots=[]
    for ordinal,item in enumerate(payload['equipped_items']):
        if not isinstance(item,dict) or not isinstance(item.get('item'),dict) or not isinstance(item.get('slot'),dict) or not isinstance(item.get('level'),dict):
            raise ValueError('equipment entry shape')
        if (type(item['item'].get('id')) is not int or item['item']['id']<=0
                or not isinstance(item['slot'].get('type'),str)
                or type(item['level'].get('value')) not in (int,float)
                or not math.isfinite(item['level']['value'])):
            raise ValueError('equipment identity/level shape')
        slot=item['slot']['type']; slots.append(slot)
        craft={k:present(item,k) for k in item if any(s in k for s in ('craft','upgrade','embellish'))}
        craft['context']=present(item,'context')
        categories=dict(item_id=item['item']['id'], item_level=item['level']['value'],
            bonus_lists=semantic(present(item,'bonus_list')), crafting=semantic(craft),
            set_state=semantic(present(item,'set')), enchants=semantic(present(item,'enchantments')),
            sockets_gems=semantic(present(item,'sockets')))
        known={'item','slot','level','bonus_list','context','set','enchantments','sockets'} | set(craft)
        categories['other_fields']=semantic({k:v for k,v in item.items() if k not in known})
        entries.append(dict(ordinal=ordinal,slot=slot,categories=categories,
                            field_presence={k:('null' if v is None else 'present') for k,v in item.items()}))
    if len(set(slots))!=len(slots):
        raise ValueError('duplicate slots require explicit parser review')
    signature={e['slot']:e['categories'] for e in entries}
    signature['__equipped_item_sets']=semantic(present(payload,'equipped_item_sets'))
    return entries,signature


def difference(before,after):
    changes=[]
    for slot in sorted(set(before)|set(after)):
        if slot not in before or slot not in after:
            changes.append(dict(slot=slot,category='slot_presence',before=present(before,slot),after=present(after,slot)))
        elif slot=='__equipped_item_sets':
            if before[slot]!=after[slot]:
                changes.append(dict(slot=slot,category='set_state',before=before[slot],after=after[slot]))
        else:
            for category in sorted(set(before[slot])|set(after[slot])):
                if before[slot].get(category)!=after[slot].get(category):
                    changes.append(dict(slot=slot,category=category,before=before[slot].get(category),after=after[slot].get(category)))
    return changes


def summarize(directory, asof=None, output=None):
    """Read one consistent SQLite snapshot; state transitions do not influence success parsing.

    Immutable plans/intents provide denominators. Provider bodies provide results. The live
    worker's mutable job completion flags and any prior generated projections are not trusted.
    """
    db=read_database(directory)
    db.execute('BEGIN')
    streams={}
    try:
        meta={r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM meta')}
        asof=asof if asof is not None else meta.get('finished',time.time())
        start=meta.get('start',meta['created']); end=meta.get('end')
        if output:
            output=Path(output).resolve()
            if output == (Path(directory)/'pilot.sqlite').resolve():
                raise ValueError('Output must be a directory')
            output.mkdir(parents=True,exist_ok=True)
            for name in ('equipment','differences','context','wcl','anomalies','timing'):
                streams[name]=(output/(name+'.jsonl')).open('w',encoding='utf-8')
        def emit(name,row):
            if name in streams:
                streams[name].write(dumps(dict(version=VERSION,**row))+'\n')
        targets={r['id']:dict(r) for r in db.execute('SELECT * FROM target')}
        jobs={r['id']:dict(r) for r in db.execute('SELECT * FROM job')}
        per={ident:dict(target=ident,realm=t['realm'],name=t['name'],provider_id=t['provider_id'],baseline=bool(t['baseline']),
                discovered=t['discovered'],reason=t['reason'],deferred=t['deferred'],planned=0,scheduled=0,
                attempted=0,successful=0,failed=0,missed=0,unavailable_observations=0,identity_conflicts=0,
                initially_accessible=None) for ident,t in targets.items()}
        eq_jobs={j['id']:j for j in jobs.values() if j['op']=='equipment' and j['provider']=='blizzard'}
        for j in eq_jobs.values():
            t=per[j['target']]; t['planned']+=1
            if j['planned']<=asof:
                t['scheduled']+=1
        attempted=set(); success=set(); first_result={}; last={}; contexts={}
        transitions=Counter(); changes_targets=set(); comparisons=unchanged=cosmetic=0
        statuses=Counter(); requests=Counter(); op_requests=Counter(); buckets=Counter()
        raw_bytes=0; seen_hashes=set(); unique_bytes=0; retry_count=0; job_sends=Counter(); actual_times=[]
        guild_codes=set(); char_codes=set(); shapes=[]; id_mismatches=[]; raw_attempts=0
        rate_rows=[]; windows=defaultdict(deque); peak_hourly=Counter(); previous_send={}; min_spacing={}
        first_attempt={}; unavailable_jobs=set()
        chains={}; wcl_rosters={}; blizzard_rosters=[]
        for j in jobs.values():
            if j['provider']=='wcl' and j['op'] in ('guild','reports','character-reports','combatants') and j['planned']<=asof:
                chain=(j['op'],j['target'],j['round'])
                p=json.loads(j['params']); cursor=p.get('page',p.get('start'))
                record=chains.setdefault(chain,dict(first=cursor,pages={}))
                record['first']=min(record['first'],cursor)
        # Capture membership from raw successful roster responses, independent of current target flags.
        last_roster=set(); baseline_roster=set(); equipment_digest=hashlib.sha256()
        query='''SELECT a.*,b.content,i.at AS sent,i.job AS job_id FROM attempt a
                 JOIN intent i ON i.id=a.id LEFT JOIN body b ON b.sha256=a.body_sha256
                 WHERE i.at<=? ORDER BY i.at,a.rowid'''
        for row in db.execute(query,(asof,)):
            raw_attempts+=1; actual_times.append(row['sent'])
            job=jobs[row['job_id']]; provider=job['provider']; op=job['op']; ident=job['target']
            first_attempt.setdefault(job['id'],dict(at=row['sent'],observation=row['id']))
            if row['status'] in (403,404):
                unavailable_jobs.add(job['id'])
            statuses[f'{provider}:{row["status"] if row["status"] is not None else "transport_failure"}']+=1
            requests[provider]+=1; op_requests[f'{provider}:{op}']+=1
            window=windows[provider]
            while window and window[0]<=row['sent']-3600:
                window.popleft()
            window.append(row['sent']); peak_hourly[provider]=max(peak_hourly[provider],len(window))
            if provider in previous_send:
                spacing=row['sent']-previous_send[provider]
                min_spacing[provider]=min(spacing,min_spacing.get(provider,float('inf')))
            previous_send[provider]=row['sent']
            buckets[f'{provider}:{int((row["sent"]-start)//3600)}']+=1
            job_sends[job['id']]+=1
            if job_sends[job['id']]>1:
                retry_count+=1
            if row['content']:
                raw_bytes+=len(row['content'])
                if row['body_sha256'] not in seen_hashes:
                    unique_bytes+=len(row['content']); seen_hashes.add(row['body_sha256'])
            try:
                payload=json.loads(row['content']) if row['content'] else None
            except (ValueError,UnicodeError):
                payload=None
            ok=row['status'] is not None and 200<=row['status']<300 and isinstance(payload,dict)
            received=datetime.fromisoformat(row['received_at']).timestamp()
            provenance=dict(observation=row['id'],job=job['id'],observed_at=received,requested_at=row['sent'],
                            http_started_at=row['started_at'],http_received_at=row['received_at'],
                            source_timestamp=payload.get('last_login_timestamp') if isinstance(payload,dict) else None)
            if provider=='wcl':
                # Rebuild rate observations from raw bodies, including partial GraphQL data.
                rate=payload.get('data',{}).get('rateLimitData') if isinstance(payload,dict) and isinstance(payload.get('data'),dict) else None
                if isinstance(rate,dict):
                    try:
                        spent,limit,reset=(float(rate[k]) for k in ('pointsSpentThisHour','limitPerHour','pointsResetIn'))
                        if not all(math.isfinite(v) for v in (spent,limit,reset)) or spent<0 or limit<=0 or reset<=0:
                            raise ValueError()
                        prev=rate_rows[-1] if rate_rows else None
                        delta=round(spent-prev['spent'],6) if prev and abs(prev['reset_at']-(row['sent']+reset))<10 and spent>=prev['spent'] else None
                        rate_rows.append(dict(attempt=row['id'],at=row['sent'],spent=spent,allowance=limit,reset_at=row['sent']+reset,delta=delta))
                    except (ValueError,TypeError,KeyError):
                        shapes.append(dict(**provenance,reason='rate_shape'))
                emit('wcl',dict(**provenance,temporal_evidence='historical_report_context',operation=op,
                    parameters=json.loads(job['params']),response=payload))
                if ok and not payload.get('errors'):
                    try:
                        page=None
                        if op=='guild':
                            guild=payload['data']['guildData']['guild']
                            if guild['id']!=488971:raise ValueError('wrong guild')
                            page=guild['members']
                        elif op=='reports':page=payload['data']['reportData']['reports']
                        elif op=='character-reports':page=payload['data']['characterData']['character']['recentReports']
                        elif op=='combatants':page=payload['data']['reportData']['report']['events']
                        if page is not None and isinstance(page.get('data'),list):
                            params=json.loads(job['params']);cursor=params.get('page',params.get('start'))
                            if op=='combatants':
                                next_cursor=page['nextPageTimestamp']
                                if next_cursor is not None and (isinstance(next_cursor,bool) or not isinstance(next_cursor,(float,int)) or not math.isfinite(next_cursor) or not cursor<next_cursor<=params['end']):
                                    raise ValueError('invalid event cursor')
                            else:
                                if page['current_page']!=cursor or type(page['has_more_pages']) is not bool:
                                    raise ValueError('invalid page')
                                next_cursor=cursor+1 if page['has_more_pages'] else None
                            chains[(op,ident,job['round'])]['pages'][cursor]=dict(next=next_cursor,observation=row['id'])
                            if op=='guild':
                                wcl_rosters[row['id']]=dict(rows=page['data'],observed_at=received)
                        if op=='reports':
                            guild_codes.update(r['code'] for r in payload['data']['reportData']['reports']['data'] if r.get('visibility')=='public')
                        elif op=='character-reports':
                            char_codes.update(r['code'] for r in payload['data']['characterData']['character']['recentReports']['data'] if r.get('visibility')=='public')
                    except (TypeError,KeyError,ValueError,AttributeError):
                        shapes.append(dict(**provenance,reason='wcl_discovery_shape'))
                continue
            if op=='roster' and ok:
                try:
                    if payload.get('guild',{}).get('id')!=52374740 or not payload.get('members'):
                        raise ValueError('wrong/empty guild')
                    roster={(r['character']['realm']['slug'].casefold(),r['character']['name'].casefold(),r['character']['id']) for r in payload['members']}
                    if row['id']==meta.get('baseline_evidence'):
                        baseline_roster=roster
                    last_roster=roster
                    blizzard_rosters.append(dict(observation=row['id'],observed_at=received,rows=payload['members']))
                except (KeyError,TypeError,ValueError,AttributeError):
                    shapes.append(dict(**provenance,reason='roster_shape'))
            if op in ('character','status','specializations','raids'):
                context_key=(ident,op)
                previous=contexts.get(context_key)
                emit('context',dict(**provenance,target=ident,operation=op,response=payload,
                    previous_observation=previous[0] if previous else None,
                    changed=(previous[1]!=payload) if previous else None,
                    relevant_context={k:present(payload,k) for k in ('average_item_level','equipped_item_level','active_spec','active_specialization','specializations','active_hero_talent_tree','guild','last_login_timestamp')}
                        if isinstance(payload,dict) else None))
                if ok:
                    contexts[context_key]=(row['id'],payload)
            if job['id'] not in eq_jobs:
                continue
            attempted.add(job['id'])
            if row['status'] in (403,404):
                per[ident]['unavailable_observations']+=1
            if ok:
                if payload.get('character',{}).get('id')!=targets[ident]['provider_id']:
                    ok=False
                    per[ident]['identity_conflicts']+=1
                    id_mismatches.append(dict(**provenance,target=ident,reason='equipment_provider_id'))
                else:
                    try:
                        entries,signature=equipment(payload)
                    except (ValueError,TypeError,KeyError,AttributeError):
                        ok=False
                        shapes.append(dict(**provenance,target=ident,reason='equipment_shape'))
            if job['round']==0 and ident not in first_result:
                first_result[ident]=ok
            # A successful retry of the initial slot establishes initial accessibility.
            if job['round']==0 and ok:
                first_result[ident]=True
            if not ok:
                continue
            success.add(job['id'])
            previous=last.get(ident)
            emit('equipment',dict(**provenance,target=ident,temporal_evidence='published_profile_observation',entries=entries,
                                   root_set_state=present(payload,'equipped_item_sets')))
            equipment_digest.update(dumps([row['id'],signature]).encode())
            if previous:
                comparisons+=1
                diffs=difference(previous['signature'],signature)
                text_changed=previous['payload']!=payload
                if not diffs:
                    unchanged+=1
                    cosmetic+=int(text_changed)
                else:
                    changes_targets.add(ident)
                    transitions.update(d['category'] for d in diffs)
                emit('differences',dict(**provenance,target=ident,previous_observation=previous['observation'],
                    previous_observed_at=previous['at'],interpretation='detected API-state change between observations',
                    changes=diffs,cosmetic_text_or_order_only=bool(text_changed and not diffs),identical_payload=not text_changed))
            last[ident]=dict(signature=signature,payload=payload,observation=row['id'],at=received)
        for j in eq_jobs.values():
            if j['planned']>asof:
                continue
            t=per[j['target']]
            if j['id'] in attempted:
                t['attempted']+=1
                if j['id'] in success:
                    t['successful']+=1
                else:
                    t['failed']+=1
            elif j['deadline']<=asof:
                t['missed']+=1
        for ident,t in per.items():
            t['initially_accessible']=first_result.get(ident)
        def coverage(rows):
            rows=list(rows)
            totals={k:sum(t[k] for t in rows) for k in ('planned','scheduled','attempted','successful','failed','missed')}
            totals['targets']=len(rows)
            totals['completion_fraction']=totals['attempted']/totals['scheduled'] if totals['scheduled'] else None
            totals['success_fraction']=totals['successful']/totals['scheduled'] if totals['scheduled'] else None
            return totals
        denominators=dict(baseline=coverage(t for t in per.values() if t['baseline']),
            later_added=coverage(t for t in per.values() if not t['baseline']),
            initially_accessible_baseline=coverage(t for t in per.values() if t['baseline'] and t['initially_accessible'] is True),
            initially_unavailable_baseline=coverage(t for t in per.values() if t['baseline'] and t['initially_accessible'] is False),
            initial_access_unknown_baseline=coverage(t for t in per.values() if t['baseline'] and t['initially_accessible'] is None),
            later_unavailable=coverage(t for t in per.values() if t['unavailable_observations'] and t['initially_accessible'] is True),
            population_deferred=coverage(t for t in per.values() if t['deferred']=='population_cap'),
            identity_quarantined=coverage(t for t in per.values() if t['deferred']=='identity_conflict'))
        per_realm={realm:coverage(t for t in per.values() if t['realm']==realm) for realm in sorted({t['realm'] for t in per.values()})}
        per_round=defaultdict(Counter)
        for j in eq_jobs.values():
            if j['planned']<=asof:
                cohort='baseline' if targets[j['target']]['baseline'] else 'later_added'
                counts=per_round[(cohort,j['round'])]; counts['scheduled']+=1
                counts['attempted']+=int(j['id'] in attempted); counts['successful']+=int(j['id'] in success)
                counts['missed']+=int(j['deadline']<=asof and j['id'] not in attempted)
        page_chains=[]
        for (op,target,round_),chain in sorted(chains.items()):
            cursor=chain['first'];visited=set();evidence=[];complete=False
            while cursor in chain['pages'] and cursor not in visited:
                visited.add(cursor);page=chain['pages'][cursor];evidence.append(page['observation'])
                cursor=page['next']
                if cursor is None:
                    complete=True;break
            page_chains.append(dict(operation=op,target=target,round=round_,complete=complete,
                                    accepted_pages=len(visited),next_cursor=cursor,observations=evidence))
        roster_comparisons=[]
        from rwf.validation import compare_rosters
        for chain in page_chains:
            if chain['operation']!='guild':continue
            comparison=dict(round=chain['round'],complete=chain['complete'],wcl_observations=chain['observations'],
                interpretation='Asynchronous address-string comparison, not a provider-ID or ownership merge')
            if chain['complete'] and blizzard_rosters:
                reference=blizzard_rosters[0 if chain['round']==0 else -1]
                pages=[wcl_rosters[a] for a in chain['observations']]
                rows=[r for p in pages for r in p['rows']]
                comparison.update(blizzard_observation=reference['observation'],blizzard_observed_at=reference['observed_at'],
                    wcl_observation_interval=[min(p['observed_at'] for p in pages),max(p['observed_at'] for p in pages)])
                try:
                    # The fixed pilot is US-only. Never silently map a new/unknown region to US.
                    if any(r['server']['region'].get('name')!='United States' for r in rows):
                        raise ValueError('region mapping requires review')
                    comparison['counts']=compare_rosters(rows,reference['rows'])
                except (KeyError,TypeError,ValueError,AttributeError):
                    comparison['comparison_unavailable']='roster_shape_or_region_requires_review'
            roster_comparisons.append(comparison)
        deferred_rows=[dict(r) for r in db.execute('SELECT * FROM deferral WHERE at<=? ORDER BY id',(asof,))]
        budget_jobs={r['job'] for r in deferred_rows if r['reason'] in
            ('blizzard_hourly_budget','wcl_local_budget','wcl_optional_reserve','wcl_provider_headroom','metadata_call_cap')}
        timing=defaultdict(Counter)
        for j in jobs.values():
            if j['planned']>asof:
                continue
            snapshot=j['provider']=='blizzard' and j['op'] in SNAPSHOT_LAG
            attempt=first_attempt.get(j['id'])
            lag=attempt['at']-j['planned'] if attempt else None
            if attempt:
                if attempt['at']>=j['deadline']:
                    category='sent_after_deadline_violation'
                elif lag<=5:
                    category='completed_on_time'
                elif snapshot:
                    category='completed_late_snapshot_within_tolerance'
                else:
                    category='completed_late_meaningful'
            elif j['deadline']<=asof:
                category='missed_expired_historical_snapshot' if snapshot else 'missed_expired_other'
            else:
                category='pending'
            counts=timing[f"{j['provider']}:{j['op']}"]
            counts[category]+=1
            counts['budget_deferred_slots']+=int(j['id'] in budget_jobs)
            counts['provider_unavailable_slots']+=int(j['id'] in unavailable_jobs)
            emit('timing',dict(job=j['id'],provider=j['provider'],operation=j['op'],target=j['target'],round=j['round'],
                planned=j['planned'],deadline=j['deadline'],observation=attempt['observation'] if attempt else None,
                execution_lag_seconds=lag,category=category,budget_deferred=j['id'] in budget_jobs,
                provider_unavailable=j['id'] in unavailable_jobs))
        events=[dict(r) for r in db.execute('SELECT * FROM event WHERE at<=? ORDER BY at,id',(asof,))]
        event_counts=Counter(e['kind'] for e in events)
        for e in events:
            if 'anomaly' in e['kind'] or 'discrepancy' in e['kind']:
                emit('anomalies',dict(kind=e['kind'],event=e['id'],**json.loads(e['detail'])))
        for anomaly in shapes+id_mismatches:
            emit('anomalies',anomaly)
        unknown_costs=sum(r['delta'] is None for r in rate_rows)
        points=sum(r['delta'] or 0 for r in rate_rows)
        indeterminate=db.execute('''SELECT count(*) FROM intent i LEFT JOIN attempt a ON a.id=i.id
                                   WHERE a.id IS NULL AND i.at<=?''',(asof,)).fetchone()[0]
        baseline=denominators['baseline']['targets']; elapsed=max(0,min(asof,meta.get('finished',asof))-start)
        db_bytes=sum(p.stat().st_size for p in Path(directory).glob('pilot.sqlite*') if p.is_file())
        report=dict(version=VERSION,collector_version=meta['version'],collector_code_signature=meta.get('code_signature'),projection_code_signature=code_signature(),
            mode='synthetic' if meta['synthetic'] else 'live',as_of=asof,start=start,
            planned_end=end,actual_end=meta.get('finished'),actual_duration_seconds=elapsed,status=meta['status'],
            baseline_roster_size=baseline,newly_discovered=denominators['later_added']['targets'],
            baseline_departures=len(baseline_roster-last_roster),coverage=denominators,
            per_character=list(per.values()),per_realm=per_realm,
            per_equipment_round=[dict(cohort=c,round=r,**dict(v)) for (c,r),v in sorted(per_round.items())],
            pagination_chains=page_chains,
            timing_by_operation={k:dict(v) for k,v in timing.items()},
            equipment=dict(adjacent_comparisons=comparisons,unchanged=unchanged,
                unchanged_fraction=unchanged/comparisons if comparisons else None,cosmetic_text_or_order_only=cosmetic,
                characters_with_detected_changes=len(changes_targets),transition_categories=dict(transitions),
                projection_digest=equipment_digest.hexdigest()),
            requests=dict(counts=dict(requests),operations=dict(op_requests),status_distribution=dict(statuses),
                hourly_buckets=dict(buckets),peak_rolling_hour_api_attempts=dict(peak_hourly),minimum_api_reservation_spacing=min_spacing,
                retries_or_duplicate_sends=retry_count,raw_attempts=raw_attempts,
                indeterminate_sends=indeterminate,mean_blizzard_requests_per_hour=requests['blizzard']/(elapsed/3600) if elapsed else None),
            wcl=dict(observed_account_points=round(points,6),unattributed_reset_or_initial_intervals=unknown_costs,
                roster_comparisons=roster_comparisons,
                cost_scope='account deltas including possible other-client activity; no fabricated per-query tariff',
                rate_observations=rate_rows,character_public_reports_absent_from_guild_discovery=sorted(char_codes-guild_codes)),
            storage=dict(raw_response_bytes_with_repeats=raw_bytes,unique_body_bytes=unique_bytes,unique_bodies=len(seen_hashes),
                sqlite_and_wal_bytes=db_bytes,raw_bytes_per_hour=raw_bytes/(elapsed/3600) if elapsed else None),
            anomalies=dict(shape_count=len(shapes),equipment_identity_count=len(id_mismatches),event_counts=dict(event_counts)),
            deferrals=deferred_rows,
            restart=dict(session_count=event_counts['session_start'],indeterminate_sends=indeterminate,
                recovery_reapplications=event_counts['recovered_observation']),
            interpretation='Instrument coverage; no acquisition times, ownership, loot attribution or Armory freshness guarantee',
            retention='Temporary pilot archive; long-term provider retention requirements remain unresolved')
        report['criteria']=dict(
            baseline_completion_95=(denominators['baseline']['completion_fraction'] or 0)>=.95 if baseline else None,
            initially_accessible_success_95=(denominators['initially_accessible_baseline']['success_fraction'] or 0)>=.95 if denominators['initially_accessible_baseline']['targets'] else None,
            every_send_has_response_or_explicit_indeterminate=raw_attempts+indeterminate==db.execute('SELECT count(*) FROM intent WHERE at<=?',(asof,)).fetchone()[0],
            blizzard_api_hourly_limit_respected=peak_hourly['blizzard']<=meta['config']['blizzard_hourly'],
            blizzard_local_send_rate_respected=min_spacing.get('blizzard',1)>=.5,
            provisional=meta.get('finished') is None or end is None or asof<end)
        report['extrapolation']={str(n):dict(comparable_guilds=n,characters=baseline*n,
            measured_window_seconds=elapsed,api_attempts=raw_attempts*n,raw_response_bytes=raw_bytes*n,
            unique_body_bytes=unique_bytes*n,assumption='Linear comparable-population extrapolation; no cross-guild deduplication assumed') for n in (10,20)}
        if output:
            (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=True),encoding='utf-8')
        return report
    finally:
        for stream in streams.values():
            stream.close()
        db.close()
