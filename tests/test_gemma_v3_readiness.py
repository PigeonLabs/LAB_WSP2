"""Synthetic parser/unit fixtures only; no model scoring or held-out test data."""
import copy
import itertools
import json
from pathlib import Path
import pytest
from src.gemma_v3_readiness import (DISCLAIMERS,CONCEPTS,LANGUAGES,
    _render_synthetic_context,text_oracle,source_components,source_slots,
    exact_date,sha_file,_authorize)


def slots():
    return {'title':{'en':'Example work','ko':'예시 작품'},'original_type':'Painting, cassone panel',
            'height':'12.5','width':'105.25','dates':['1700-02-28','1801-03-01'],
            'owner':{'en':'Named collection','ko':'이름 붙은 소장처'}}


def test_all_factor_renderings_have_independent_oracle_and_balanced_length():
    for concept,lex,lang in itertools.product(CONCEPTS,(0,1),LANGUAGES):
        pairs=[]
        for state in (0,1):
            text,claim=_render_synthetic_context(concept,slots(),state,lex,lang)
            assert text_oracle(text,claim,concept,lang,lex) is bool(state)
            assert text.startswith(DISCLAIMERS[lang])
            pairs.append((text,claim))
        assert pairs[0][1]==pairs[1][1]
        assert len(pairs[0][0])==len(pairs[1][0])


@pytest.mark.parametrize('concept,lang,lex,text,claim,truth',[
 ('negation','en',0,'«Work» is classified as «Drawing», not «Painting».','The entry for «Work» excludes «Painting».',True),
 ('negation','ko',1,'«작품» 항목은 분류 «회화»를 포함하고 «사진»를 제외한다.','«작품» 항목은 «회화»를 제외한다.',False),
 ('numeric_comparison','en',1,'Size card for «Work»: vertical 9.99 cm; horizontal 10.01 cm.','The height of «Work» exceeds its width.',False),
 ('numeric_comparison','ko',0,'«작품»의 높이는 100.1 cm이고 너비는 20.9 cm이다.','«작품»의 높이는 너비보다 크다.',True),
 ('temporal_order','en',1,'The log about «Person» records blue entry on 1900-01-01, and red entry on 1899-12-31.','In the log about «Person», red entry precedes blue entry.',True),
 ('temporal_order','ko',0,'«인물» 일지의 가 항목 날짜는 2001-01-01이고 나 항목 날짜는 2000-12-31이다.','«인물» 일지의 가 항목은 나 항목보다 이르다.',False),
 ('ownership_coreference','en',0,'The entries are «Work» and «Study», in that order. «Archive» owns the former; «Collector» owns the latter.','In this record, «Collector» owns «Work».',False),
 ('ownership_coreference','ko',1,'첫 항목 «작품», 두 번째 항목 «습작»가 있다. 후자는 «보관소» 소유이며 전자는 «소장처» 소유이다.','이 기록에서 «소장처» 소유인 항목은 «작품»이다.',True)
])
def test_handwritten_semantic_cases(concept,lang,lex,text,claim,truth):
    assert text_oracle(DISCLAIMERS[lang]+text,claim,concept,lang,lex) is truth


def test_corrupt_scope_missing_fiction_and_invalid_date_rejected():
    text,claim=_render_synthetic_context('ownership_coreference',slots(),1,0,'en')
    with pytest.raises(ValueError):text_oracle(text,claim.replace('Example work','unknown'),'ownership_coreference','en',0)
    with pytest.raises(ValueError,match='disclosure'):text_oracle(text[len(DISCLAIMERS['en']):],claim,'ownership_coreference','en',0)
    text,claim=_render_synthetic_context('temporal_order',slots(),1,0,'en')
    with pytest.raises(ValueError):text_oracle(text.replace('1700-02-28','1700-02-30'),claim,'temporal_order','en',0)


def test_components_distinguish_publisher_and_actual_shared_ancestry():
    records=[{'record_id':x,'source_document_lineage':'doc:'+x,'underlying_entity_or_event':'event:'+x,'source_institution':'same museum','canonical_facts':[]} for x in 'abcd']
    assert len(set(source_components(records).values()))==4
    records[1]['derivation_parent']='a'
    assert len(set(source_components(records).values()))==3
    records[2]['external_entity_id']='Q42';records[3]['source_record_id']='Q42'
    assert len(set(source_components(records).values()))==2
    records[0]['source_cluster_candidates']=['reference/shared'];records[2]['source_cluster_candidates']=['reference/shared']
    assert len(set(source_components(records,True).values()))==1
    assert len(set(source_components(records).values()))==2


def test_raw_met_fact_verification_detects_value_or_snapshot_tamper(tmp_path):
    raw={'objectID':123,'title':'Fixture','measurements':[{'elementName':'Overall','elementMeasurements':{'Height':12.5,'Width':20.25}}]}
    path=tmp_path/'raw.json';path.write_text(json.dumps(raw))
    record={'raw_snapshot':'raw.json','raw_snapshot_sha256':sha_file(path),'concept':'numeric_comparison','underlying_entity_or_event':'met-object:123','canonical_facts':[{'predicate':'height_cm','value':12.5},{'predicate':'width_cm','value':20.25}]}
    assert source_slots(record,tmp_path)['height']=='12.5'
    wrong=copy.deepcopy(record);wrong['canonical_facts'][0]['value']=13
    with pytest.raises(ValueError,match='Dimensions'):source_slots(wrong,tmp_path)
    path.write_text('{}')
    with pytest.raises(ValueError,match='checksum'):source_slots(record,tmp_path)


def test_calendar_and_precision_are_not_silently_assumed():
    value={'time':'+1879-03-14T00:00:00Z','precision':11,'calendarmodel':'http://www.wikidata.org/entity/Q1985727'}
    assert exact_date(value)=='1879-03-14'
    value['precision']=9
    with pytest.raises(ValueError):exact_date(value)


def test_readiness_authorization_checked_before_materialization(tmp_path):
    lock=tmp_path/'lock.json';amendment=tmp_path/'amend.json'
    lock.write_text(json.dumps({'status':'PENDING'}));amendment.write_text('{}')
    with pytest.raises(ValueError,match='sealed'):_authorize(tmp_path,tmp_path/'missing-catalog.json',lock,amendment)
    assert not list(tmp_path.glob('*readiness*'))
