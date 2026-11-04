"""Source-grounded CONDITIONAL readiness; original template gate remains failed.

Source records, upstream dependence, and reused renderers are separate axes.
Institutions alone do not merge source components. No readiness prompts are built
by the CLI audit command. Materialization requires both an E-only prompt lock and
an explicit pre-readiness amendment. Test/OOD construction is not implemented.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path
import re
from .gemma_v3_data import CONCEPTS, LANGUAGES, package_prompt, digest

ROOT=Path(__file__).resolve().parents[1]
VERSION='source-conditional-readiness-v1'
RENDERERS={c:'readiness-source-v1/'+c for c in CONCEPTS}
Q=r'«([^»\n]+)»'
D=r'(\d+(?:\.\d+)?)'
DATE=r'(\d{4}-\d{2}-\d{2})'
DISCLAIMERS={'en':'Imagined record adapted from public metadata; this is not a historical claim. ',
             'ko':'공개 메타데이터를 바탕으로 만든 가상 기록이며, 실제 역사에 관한 주장이 아닙니다. '}


def sha_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read_json(path):return json.loads(Path(path).read_text())
def match(pattern,text):
    found=re.fullmatch(pattern,text)
    if found is None:raise ValueError('Unrecognized or corrupted readiness sentence')
    return found.groups()
def safe_text(value):
    if not isinstance(value,str) or not value.strip() or any(c in value for c in ('«','»','\n','\r')):raise ValueError('Unsafe or empty source label')
    return value

def exact_date(value):
    if value.get('precision')!=11 or value.get('calendarmodel')!='http://www.wikidata.org/entity/Q1985727' or any(value.get(k,0)!=0 for k in ('before','after','timezone')):raise ValueError('Need exact Gregorian day, without time uncertainty')
    token=match(r'\+(\d{4}-\d{2}-\d{2})T00:00:00Z',value['time'])[0]
    date.fromisoformat(token)
    return token


def _fact(record,predicate):
    values=[f for f in record['canonical_facts'] if f['predicate']==predicate]
    if len(values)!=1:raise ValueError('Need one selected source fact: '+predicate)
    return values[0]


def source_slots(record,root):
    """Check typed facts against saved raw source statements, not paraphrases."""
    root=Path(root).resolve();relative=Path(record['raw_snapshot'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Snapshot must be archive-relative')
    path=root/relative
    if sha_file(path)!=record['raw_snapshot_sha256']:raise ValueError('Raw source snapshot checksum mismatch')
    raw=read_json(path);concept=record['concept']
    if concept in ('negation','numeric_comparison'):
        if 'met-object:'+str(raw.get('objectID'))!=record['underlying_entity_or_event']:raise ValueError('Met object identity mismatch')
        title=safe_text(raw['title'])
        if concept=='negation':
            label=_fact(record,'catalogue_object_type')['value']
            if raw['objectName']!=label or _fact(record,'catalogue_title')['value']!=title:raise ValueError('Met classification/title source mismatch')
            safe_text(label)
            return dict(title={'en':title,'ko':title},original_type=label)
        height=Decimal(str(_fact(record,'height_cm')['value']));width=Decimal(str(_fact(record,'width_cm')['value']))
        possibilities=[]
        for item in raw.get('measurements',[]):
            if item.get('elementName')=='Overall':
                m=item.get('elementMeasurements',{})
                if 'Height' in m and 'Width' in m:possibilities.append((Decimal(str(m['Height'])),Decimal(str(m['Width']))))
        if (height,width) not in possibilities or min(height,width)<=0 or height==width:raise ValueError('Dimensions missing, unequal or from another element')
        return dict(title={'en':title,'ko':title},height=str(height),width=str(width),unit='cm')
    qid=record['source_record_id'];entity=raw.get('entities',{}).get(qid)
    if entity is None and raw.get('id')==qid:entity=raw
    if not entity or entity.get('id')!=qid:raise ValueError('Wikidata entity absent from saved snapshot')
    if entity.get('lastrevid')!=record['source_revision']:raise ValueError('Wikidata revision mismatch')
    def checked_statement(fact,prop):
        found=[s for s in entity.get('claims',{}).get(prop,[]) if s['id'].lower()==fact['statement_id'].lower()]
        if len(found)!=1 or found[0].get('rank')=='deprecated':raise ValueError('Chosen source statement missing or deprecated')
        statement=found[0];snak=statement['mainsnak']
        if snak.get('snaktype')!='value':raise ValueError('Source statement has no explicit value')
        return statement,snak['datavalue']['value']
    if concept=='temporal_order':
        dates={}
        for prop in ('P569','P570'):
            fact=_fact(record,prop);_,value=checked_statement(fact,prop)
            if value!=fact['object']:raise ValueError('Date differs from raw statement')
            dates[prop]=exact_date(value)
        if dates['P569']==dates['P570']:raise ValueError('Dates cannot be equal for ordering')
        labels=record['labels']
        return dict(title={lang:safe_text(labels[lang]) for lang in LANGUAGES},dates=[dates['P569'],dates['P570']],role_transform='Birth/death roles removed; only dates used for hypothetical log entries')
    if concept=='ownership_coreference':
        fact=_fact(record,'P127/owned_by');statement,value=checked_statement(fact,'P127')
        if value.get('id')!=fact['object'] or statement.get('qualifiers',{})!=fact.get('qualifiers',{}):raise ValueError('Owner or historical qualifiers differ from raw assertion')
        return dict(title={'en':safe_text(record['entity_label_en']),'ko':safe_text(record['entity_label_ko'])},
                    owner={lang:safe_text(fact['object_label_'+lang]) for lang in LANGUAGES},qualifiers=fact.get('qualifiers',{}),owner_entity=fact['object'])
    raise ValueError('Unsupported source concept')


def source_components(records,include_references=False):
    """Connected explicit source/entity/event lineage, NOT publisher identity."""
    parent=list(range(len(records)));seen={};known_ids={r['record_id'] for r in records}
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for i,r in enumerate(records):
        keys=['record:'+r['record_id']]
        if r.get('derivation_parent') in known_ids:keys.append('record:'+r['derivation_parent'])
        for field in ('source_document_lineage','underlying_entity_or_event','derivation_parent','external_entity_id'):
            if r.get(field):keys.append(field+':'+str(r[field]))
        # Same Wikidata identity can occur through different provider labels.
        for value in (r.get('external_entity_id',''),r.get('source_record_id',''),r.get('derivation_parent','')):
            if re.fullmatch(r'Q\d+',str(value)):keys.append('entity:'+str(value))
        if include_references:
            keys += ['upstream:'+x for x in r.get('source_cluster_candidates',[]) if x.startswith('reference/')]
            for f in r['canonical_facts']:
                keys += ['upstream:reference/'+ref['hash'] for ref in f.get('references',[]) if 'hash' in ref]
        for key in keys:
            if key in seen:parent[find(i)]=find(seen[key])
            else:seen[key]=i
    clusters={}
    for i,r in enumerate(records):clusters.setdefault(find(i),[]).append(r['record_id'])
    return {rid:'source-component/'+digest(sorted(ids))[:20] for ids in clusters.values() for rid in ids}


def audit_source_catalog(catalog,root=ROOT,expected_per_concept=16):
    records=catalog['records'];ids=[r['record_id'] for r in records]
    if len(ids)!=len(set(ids)):raise ValueError('Repeated source record ID')
    counts=dict(Counter(r['concept'] for r in records))
    if counts!={c:expected_per_concept for c in CONCEPTS}:raise ValueError('Incomplete balanced source catalog')
    for record in records:
        for field in ('source_url','source_document_lineage','underlying_entity_or_event','source_institution','license','license_url'):
            if not record.get(field):raise ValueError('Missing source provenance: '+field)
        source_slots(record,root)
    clusters=source_components(records);sensitivity=source_components(records,True)
    return dict(status='SOURCE_FACTS_VERIFIED_NOT_READINESS_MATERIALIZED',records=len(records),counts_by_concept=counts,
                source_components=len(set(clusters.values())),components_by_concept={c:len({clusters[r['record_id']] for r in records if r['concept']==c}) for c in CONCEPTS},
                source_component_ids=clusters,shared_reference_sensitivity_components=len(set(sensitivity.values())),
                shared_reference_component_ids=sensitivity,shared_reference_components_by_concept={c:len({sensitivity[r['record_id']] for r in records if r['concept']==c}) for c in CONCEPTS},
                source_record_sha256={r['record_id']:digest(r) for r in records},source_facts_sha256={r['record_id']:digest(r['canonical_facts']) for r in records},
                source_institutions=dict(Counter(r['source_institution'] for r in records)),renderer_lineages=RENDERERS,
                renderer_lineage_count=4,strict_template_generalization_gate='FAIL_SHARED_RENDERERS',
                source_independence_proven=False,inference_scope='Conditional on four fixed renderers, chosen source sampling frame and fixed models; source-cluster uncertainty only',
                readiness_materialized=False,test_opened=False,ood_opened=False)


def _render_synthetic_context(concept,slots,state,lexical,language):
    """Pure renderer. Actual source records are routed only through locked builder."""
    title=safe_text(slots['title'][language]);ko=language=='ko'
    if concept=='negation':
        original=safe_text(slots['original_type']);foil='Drawing' if original!='Drawing' else 'Painting'
        yes,no=(foil,original) if state else (original,foil)
        if ko:
            text=(f'«{title}»의 분류는 «{yes}»이며 «{no}»는 아니다.' if not lexical else f'«{title}» 항목은 분류 «{yes}»를 포함하고 «{no}»를 제외한다.')
            claim=f'«{title}» 항목은 «{original}»를 제외한다.'
        else:
            text=(f'«{title}» is classified as «{yes}», not «{no}».' if not lexical else f'The entry for «{title}» includes type «{yes}» and excludes «{no}».')
            claim=f'The entry for «{title}» excludes «{original}».'
    elif concept=='numeric_comparison':
        lo,hi=sorted((Decimal(slots['height']),Decimal(slots['width'])))
        h,w=(hi,lo) if state else (lo,hi)
        if ko:
            text=(f'«{title}»의 높이는 {h} cm이고 너비는 {w} cm이다.' if not lexical else f'«{title}»의 크기 카드: 세로 {h} cm; 가로 {w} cm.')
            claim=f'«{title}»의 높이는 너비보다 크다.'
        else:
            text=(f'«{title}» has height {h} cm and width {w} cm.' if not lexical else f'Size card for «{title}»: vertical {h} cm; horizontal {w} cm.')
            claim=f'The height of «{title}» exceeds its width.'
    elif concept=='temporal_order':
        early,late=sorted(slots['dates']);red,blue=(early,late) if state else (late,early)
        if ko:
            text=(f'«{title}» 일지의 가 항목 날짜는 {red}이고 나 항목 날짜는 {blue}이다.' if not lexical else f'«{title}» 일지에는 나 항목이 {blue}, 가 항목이 {red}로 기록되어 있다.')
            claim=f'«{title}» 일지의 가 항목은 나 항목보다 이르다.'
        else:
            text=(f'In the log about «{title}», red entry is dated {red} and blue entry is dated {blue}.' if not lexical else f'The log about «{title}» records blue entry on {blue}, and red entry on {red}.')
            claim=f'In the log about «{title}», red entry precedes blue entry.'
    elif concept=='ownership_coreference':
        owner=safe_text(slots['owner'][language]);other='가상 보관소' if ko else 'Imaginary Archive';aux='가상 습작' if ko else 'imaginary study'
        if title==aux or owner==other:raise ValueError('Source collides with fictional comparison entity')
        first,second=(owner,other) if state else (other,owner)
        if ko:
            text=(f'항목은 순서대로 «{title}»와 «{aux}»이다. 전자의 소유자는 «{first}»이고 후자의 소유자는 «{second}»이다.' if not lexical else f'첫 항목 «{title}», 두 번째 항목 «{aux}»가 있다. 후자는 «{second}» 소유이며 전자는 «{first}» 소유이다.')
            claim=f'이 기록에서 «{owner}» 소유인 항목은 «{title}»이다.'
        else:
            text=(f'The entries are «{title}» and «{aux}», in that order. «{first}» owns the former; «{second}» owns the latter.' if not lexical else f'First comes «{title}», then «{aux}». The latter belongs to «{second}»; the former belongs to «{first}».')
            claim=f'In this record, «{owner}» owns «{title}».'
    else:raise ValueError('Unknown concept')
    return DISCLAIMERS[language]+text,claim


def text_oracle(context,claim,concept,language,lexical):
    """Independent parser evaluates displayed records, without state/source labels."""
    if not context.startswith(DISCLAIMERS[language]):raise ValueError('Missing hypothetical-record disclosure')
    text=context[len(DISCLAIMERS[language]):];ko=language=='ko'
    if concept=='negation':
        qtitle,qtype=match(Q+(r' 항목은 '+Q+r'를 제외한다\.' if ko else ''),claim) if ko else match(r'The entry for '+Q+r' excludes '+Q+r'\.',claim)
        if ko:pattern=Q+r'의 분류는 '+Q+r'이며 '+Q+r'는 아니다\.' if not lexical else Q+r' 항목은 분류 '+Q+r'를 포함하고 '+Q+r'를 제외한다\.'
        else:pattern=Q+r' is classified as '+Q+r', not '+Q+r'\.' if not lexical else r'The entry for '+Q+r' includes type '+Q+r' and excludes '+Q+r'\.'
        title,yes,no=match(pattern,text)
        if title!=qtitle or yes==no or qtype not in (yes,no):raise ValueError('Ambiguous classification scope')
        return qtype==no
    if concept=='numeric_comparison':
        qtitle=match(Q+r'의 높이는 너비보다 크다\.',claim)[0] if ko else match(r'The height of '+Q+r' exceeds its width\.',claim)[0]
        if ko:pattern=Q+r'의 높이는 '+D+r' cm이고 너비는 '+D+r' cm이다\.' if not lexical else Q+r'의 크기 카드: 세로 '+D+r' cm; 가로 '+D+r' cm\.'
        else:pattern=Q+r' has height '+D+r' cm and width '+D+r' cm\.' if not lexical else r'Size card for '+Q+r': vertical '+D+r' cm; horizontal '+D+r' cm\.'
        title,h,w=match(pattern,text)
        if title!=qtitle or Decimal(h)==Decimal(w):raise ValueError('Invalid numeric scope')
        return Decimal(h)>Decimal(w)
    if concept=='temporal_order':
        qtitle=match(Q+r' 일지의 가 항목은 나 항목보다 이르다\.',claim)[0] if ko else match(r'In the log about '+Q+r', red entry precedes blue entry\.',claim)[0]
        if ko:pattern=Q+r' 일지의 가 항목 날짜는 '+DATE+r'이고 나 항목 날짜는 '+DATE+r'이다\.' if not lexical else Q+r' 일지에는 나 항목이 '+DATE+r', 가 항목이 '+DATE+r'로 기록되어 있다\.'
        else:pattern=r'In the log about '+Q+r', red entry is dated '+DATE+r' and blue entry is dated '+DATE+r'\.' if not lexical else r'The log about '+Q+r' records blue entry on '+DATE+r', and red entry on '+DATE+r'\.'
        title,a,b=match(pattern,text);red,blue=(b,a) if lexical else (a,b)
        if title!=qtitle or red==blue:raise ValueError('Invalid date scope')
        return date.fromisoformat(red)<date.fromisoformat(blue)
    if concept=='ownership_coreference':
        owner,qtitle=match(r'이 기록에서 '+Q+r' 소유인 항목은 '+Q+r'이다\.',claim) if ko else match(r'In this record, '+Q+r' owns '+Q+r'\.',claim)
        if ko:pattern=r'항목은 순서대로 '+Q+r'와 '+Q+r'이다\. 전자의 소유자는 '+Q+r'이고 후자의 소유자는 '+Q+r'이다\.' if not lexical else r'첫 항목 '+Q+r', 두 번째 항목 '+Q+r'가 있다\. 후자는 '+Q+r' 소유이며 전자는 '+Q+r' 소유이다\.'
        else:pattern=r'The entries are '+Q+r' and '+Q+r', in that order\. '+Q+r' owns the former; '+Q+r' owns the latter\.' if not lexical else r'First comes '+Q+r', then '+Q+r'\. The latter belongs to '+Q+r'; the former belongs to '+Q+r'\.'
        first_title,second_title,a,b=match(pattern,text);first_owner,second_owner=(b,a) if lexical else (a,b)
        if first_title==second_title or first_owner==second_owner or qtitle not in (first_title,second_title) or owner not in (first_owner,second_owner):raise ValueError('Broken ownership/coreference scope')
        return owner==({first_title:first_owner,second_title:second_owner}[qtitle])
    raise ValueError('Unsupported readiness concept')


def _authorize(root,catalog_path,prompt_lock_path,amendment_path):
    lock=read_json(prompt_lock_path);amend=read_json(amendment_path)
    if lock.get('status')!='FROZEN_BEFORE_READINESS':raise ValueError('Readiness sealed: engineering prompt not frozen')
    engineering=root/'data/followup-v3-gemma-map/engineering.jsonl'
    if lock.get('engineering_data_sha256')!=sha_file(engineering):raise ValueError('Prompt lock does not bind actual engineering data')
    if set(lock.get('prefix',{}))!=set(LANGUAGES) or lock.get('variant') not in ('raw','common_fourshot_v1'):raise ValueError('Invalid common prompt lock')
    if lock['variant']=='raw' and any(lock['prefix'].values()):raise ValueError('Raw prompt must have empty prefixes')
    if lock['variant']=='common_fourshot_v1' and not all(lock['prefix'].values()):raise ValueError('Four-shot prefix missing')
    if not lock.get('selection_evidence_sha256'):raise ValueError('E-only format selection evidence missing')
    for rel,expected in lock['selection_evidence_sha256'].items():
        relative=Path(rel)
        if relative.is_absolute() or '..' in relative.parts or sha_file(root/relative)!=expected:raise ValueError('Prompt selection evidence changed')
    if amend.get('status')!='APPROVED_PRE_READINESS' or amend.get('conditional_capability_only') is not True or amend.get('strict_template_generalization_passed') is not False or amend.get('test_opened') is not False:raise ValueError('Explicit conditional pre-readiness amendment required')
    if amend.get('thresholds_unchanged')!={'accuracy':0.75,'descriptive_source_cluster_CI_lower':0.5}:raise ValueError('Readiness capability thresholds changed')
    if amend.get('source_catalog_sha256')!=sha_file(catalog_path) or amend.get('prompt_lock_sha256')!=sha_file(prompt_lock_path):raise ValueError('Amendment does not bind current sources and prompt')
    return lock,amend


def validate_readiness(rows,source_audit,prefix):
    ids={r['id']:r for r in rows};families={};prompt_set=set()
    if len(ids)!=len(rows) or len(rows)!=source_audit['records']*16:raise ValueError('Readiness row identity/count mismatch')
    for r in rows:
        if r['split']!='readiness' or r['concept'] not in CONCEPTS:raise ValueError('Only readiness is authorized')
        truth=text_oracle(r['context'],r['claim'],r['concept'],r['language'],r['lexical'])
        if truth!=bool(r['semantic_state']) or r['label']!=r['semantic_state'] or r['correct_index']!=(0 if truth else 1):raise ValueError('Independent text oracle/label mismatch')
        base,completions=package_prompt(r['context'],r['claim'],r['language'],r['answer_code'])
        pre=prefix[r['language']];offset=len(pre)+2 if pre else 0
        if r['prompt']!=(pre+'\n\n'+base if pre else base) or r['completions']!=completions or r['span']!=[offset,offset+len(r['context'])]:raise ValueError('Frozen prompt/span/completion mismatch')
        if r['canonical_proposition_ids']!=['statement_true','statement_false'] or r['correct']!=completions[r['correct_index']] or r['foil']!=completions[1-r['correct_index']]:raise ValueError('Readiness canonical answer mismatch')
        if r['source_record_sha256']!=source_audit['source_record_sha256'][r['source_record_key']] or digest(r['source_facts'])!=source_audit['source_facts_sha256'][r['source_record_key']]:raise ValueError('Readiness source facts changed')
        if r['prompt_sha256']!=digest(r['prompt'].encode()) or r['content_sha256']!=digest([r['context'],r['claim']]):raise ValueError('Readiness text checksum mismatch')
        if r['prompt'] in prompt_set:raise ValueError('Duplicate readiness prompt')
        prompt_set.add(r['prompt']);families.setdefault(r['family_id'],[]).append(r)
        if r['source_cluster_id']!=source_audit['source_component_ids'][r['source_record_key']] or r['lineage_id']!=RENDERERS[r['concept']]:raise ValueError('Source and renderer axes confused')
        for field,factor in [('counterfactual_donor_id','semantic_state'),('lexical_donor_id','lexical')]:
            donor=ids.get(r[field])
            if donor is None or donor[factor]!=1-r[factor]:raise ValueError('Missing or wrong donor')
            for key in ('family_id','concept','language','answer_code','semantic_state','lexical'):
                if key!=factor and donor[key]!=r[key]:raise ValueError('Donor changes extra factor')
    expected=set(itertools.product((0,1),(0,1),(0,1),LANGUAGES))
    for family,items in families.items():
        if len(items)!=16 or {(r['semantic_state'],r['lexical'],r['answer_code'],r['language']) for r in items}!=expected:raise ValueError('Incomplete readiness factorial')
        if len({r['source_cluster_id'] for r in items})!=1:raise ValueError('Variants split source lineage')
        selected=[r for r in items if r['causal_selected']]
        if len(selected)!=8 or {(r['semantic_state'],r['answer_code'],r['language']) for r in selected}!=set(itertools.product((0,1),(0,1),LANGUAGES)):raise ValueError('Causal subset changes primary strata')
    return dict(rows=len(rows),families=len(families),source_clusters=source_audit['source_components'],renderer_clusters=4,
                source_conditional_capability_only=True,strict_template_generalization_gate='FAIL_SHARED_RENDERERS',
                source_lineage_gate='OBSERVED_COMPONENTS_NOT_PROOF_OF_INDEPENDENCE',test_opened=False,ood_opened=False)


def materialize_readiness(catalog_path,prompt_lock_path,amendment_path,output_dir,root=ROOT):
    root=Path(root).resolve();catalog_path=Path(catalog_path);prompt_lock_path=Path(prompt_lock_path);amendment_path=Path(amendment_path)
    lock,amend=_authorize(root,catalog_path,prompt_lock_path,amendment_path)  # before building any R prompt
    catalog=read_json(catalog_path);audit=audit_source_catalog(catalog,root);rows=[]
    for index,source in enumerate(sorted(catalog['records'],key=lambda r:r['record_id'])):
        slots=source_slots(source,root);concept=source['concept'];family='R-'+source['record_id']
        for state,lexical,code,language in itertools.product((0,1),(0,1),(0,1),LANGUAGES):
            context,claim=_render_synthetic_context(concept,slots,state,lexical,language)
            prompt,completions=package_prompt(context,claim,language,code);pre=lock['prefix'][language];offset=len(pre)+2 if pre else 0
            if pre:prompt=pre+'\n\n'+prompt
            row=dict(id=f'{family}-s{state}-l{lexical}-c{code}-{language}',family_id=family,source_id=source['source_document_lineage'],
                     source_record_key=source['record_id'],source_cluster_id=audit['source_component_ids'][source['record_id']],
                     source_reference_cluster_id=audit['shared_reference_component_ids'][source['record_id']],
                     lineage_id=RENDERERS[concept],renderer_lineage_id=RENDERERS[concept],template_id=f'{RENDERERS[concept]}/lex{lexical}/{language}',
                     grammar_id=RENDERERS[concept],split='readiness',concept=concept,language=language,semantic_state=state,label=state,lexical=lexical,answer_code=code,
                     context=context,claim=claim,prompt=prompt,completions=completions,canonical_proposition_ids=['statement_true','statement_false'],correct_index=0 if state else 1,
                     span=[offset,offset+len(context)],pair_id=f'{family}-l{lexical}-c{code}-{language}',counterfactual_donor_id=f'{family}-s{1-state}-l{lexical}-c{code}-{language}',
                     lexical_donor_id=f'{family}-s{state}-l{1-lexical}-c{code}-{language}',causal_selected=lexical==index%2,
                     hypothetical_both_states=True,source_facts=source['canonical_facts'],source_record_sha256=digest(source),source_url=source['source_url'],
                     source_snapshot_sha256=source['raw_snapshot_sha256'],prompt_variant=lock['variant'])
            row['correct']=completions[row['correct_index']];row['foil']=completions[1-row['correct_index']]
            row['prompt_sha256']=digest(prompt.encode());row['content_sha256']=digest([context,claim]);rows.append(row)
    validation=validate_readiness(rows,audit,lock['prefix'])
    old=[json.loads(line) for line in (root/'data/followup-v3-gemma-map/engineering.jsonl').read_text().splitlines()]
    for key in ('prompt_sha256','content_sha256','grammar_id','lineage_id'):
        if {r[key] for r in rows}&{r[key] for r in old}:raise ValueError('Engineering/readiness overlap: '+key)
    raw=''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows).encode()
    manifest=dict(version=VERSION,status='CONDITIONAL_READINESS_MATERIALIZED_NOT_SCORED',data_sha256=digest(raw),source_catalog_sha256=sha_file(catalog_path),
                  prompt_lock_sha256=sha_file(prompt_lock_path),amendment_sha256=sha_file(amendment_path),source_code_sha256=sha_file(__file__),
                  validation=validation,source_audit=audit,original_confirmatory_claims_evaluable=False,test_opened=False,ood_opened=False,
                  limitations=['Original template-generalization requirement is not passed; only amended conditional capability may be evaluated.',
                               'Source components are documented provenance units, not proof of statistical independence; publishers/renderers are separate dependence axes.',
                               'Both semantic states are hypothetical adaptations, not assertions about actual historical ownership or altered museum metadata.',
                               'Temporal task compares generic dated entries; birth/death roles were removed to avoid automatic birth-before-death inference.',
                               'Negation uses exact recorded classification and explicit exclusion, not open-world absence inference.',
                               'Four controlled renderers do not establish general natural-language or free-generation competence.'])
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    payloads={output/'readiness.jsonl':raw,output/'readiness_manifest.json':(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n').encode()}
    for path,payload in payloads.items():
        if path.exists() and path.read_bytes()!=payload:raise FileExistsError('Refusing to overwrite readiness freeze')
    for path,payload in payloads.items():
        if not path.exists():path.write_bytes(payload)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['audit-sources','materialize']);parser.add_argument('--catalog',type=Path,required=True);parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--prompt-lock',type=Path);parser.add_argument('--amendment',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.stage=='audit-sources':result=audit_source_catalog(read_json(args.catalog),args.root)
    else:
        if not all((args.prompt_lock,args.amendment,args.output)):parser.error('materialize requires prompt lock, pre-readiness amendment and output')
        result=materialize_readiness(args.catalog,args.prompt_lock,args.amendment,args.output,args.root)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
