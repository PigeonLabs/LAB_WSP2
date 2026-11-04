import copy
import json
import pytest
from src.gemma_v3_data import (build_engineering, validate_records, oracle,
    freeze_engineering, build_readiness, prompt_packager_hash)


def test_full_engineering_factorial_and_honest_lineage():
    rows=build_engineering()
    assert rows==build_engineering()
    manifest=validate_records(rows,32,'engineering')
    assert manifest['rows']==512
    assert manifest['scenario_families']==32
    assert manifest['lineage_clusters']==4
    assert set(manifest['lineages_per_concept'].values())=={1}
    assert manifest['independent_template_generalization_gate']=='FAIL_INSUFFICIENT_LINEAGES'
    assert sum(r['causal_selected'] for r in rows)==256
    assert sum(r['semantic_state'] for r in rows)==256


@pytest.mark.parametrize('context,claim,concept,language,lexical,truth',[
    ('Ada carries the bag. Bea does not carry the bag.','Bea carries the bag.','negation','en',0,False),
    ('우산을 들고 있는 사람은 민아다. 준호는 우산을 들고 있지 않다.','민아는 우산을 들고 있다.','negation','ko',1,True),
    ('Ada gave the bag to Bea. Then Bea gave it to Cia.','Ada owns the bag now.','ownership_coreference','en',0,False),
    ('우산은 민아에게서 준호에게 넘어갔다. 이후 준호는 그것을 소라에게 넘겼다.','현재 우산의 주인은 소라다.','ownership_coreference','ko',1,True),
    ('Bea arrived after Ada. Cia arrived after Bea.','Cia arrived before Ada.','temporal_order','en',1,False),
    ('민아는 준호보다 먼저 도착했다. 준호는 소라보다 먼저 도착했다.','민아는 소라보다 먼저 도착했다.','temporal_order','ko',0,True),
    ('Token counts: Ada=19, Bea=101.','Ada has more tokens than Bea.','numeric_comparison','en',1,False),
    ('민아의 토큰 수는 101개이다. 준호의 토큰 수는 19개이다.','민아의 토큰 수는 준호보다 많다.','numeric_comparison','ko',0,True),
])
def test_semantic_oracle_on_independent_handwritten_cases(context,claim,concept,language,lexical,truth):
    assert oracle(context,claim,concept,language,lexical) is truth


def test_oracle_rejects_broken_reference_and_inconsistent_object():
    with pytest.raises(ValueError,match='chain'):
        oracle('Ada gave the bag to Bea. Then Cia gave it to Dia.','Dia owns the bag now.','ownership_coreference','en',0)
    with pytest.raises(ValueError,match='Ambiguous'):
        oracle('Ada carries the bag. Bea does not carry the pen.','Ada carries the bag.','negation','en',0)


def test_answer_code_does_not_change_semantics():
    rows=build_engineering();by_id={r['id']:r for r in rows}
    for row in rows:
        other=next(r for r in rows if r['family_id']==row['family_id'] and r['language']==row['language'] and r['lexical']==row['lexical'] and r['semantic_state']==row['semantic_state'] and r['answer_code']!=row['answer_code'])
        assert row['context']==other['context'] and row['claim']==other['claim']
        assert row['correct_index']==other['correct_index']
        assert row['completions'][0].split('.')[0]!=other['completions'][0].split('.')[0]
        donor=by_id[row['counterfactual_donor_id']]
        assert donor['correct_index']!=row['correct_index']
        assert donor['completions']==row['completions']


def test_corruption_and_independence_laundering_rejected():
    rows=build_engineering();rows[0]['semantic_state']=1
    with pytest.raises(ValueError,match='oracle'):validate_records(rows)
    rows=build_engineering()
    for row in rows:
        row['lineage_id']=row['family_id']
    with pytest.raises(ValueError,match='falsely assigned'):validate_records(rows)
    rows=build_engineering();rows[0]['counterfactual_donor_id']=rows[0]['id']
    with pytest.raises(ValueError,match='flip'):validate_records(rows)
    rows=build_engineering();rows.pop()
    with pytest.raises(ValueError):validate_records(rows)


def test_only_engineering_is_frozen_and_overwrite_is_refused(tmp_path):
    manifest=freeze_engineering(tmp_path)
    assert manifest==freeze_engineering(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir())==['engineering.jsonl','engineering_manifest.json']
    assert manifest['test_opened'] is False and manifest['ood_opened'] is False
    assert len((tmp_path/'engineering.jsonl').read_text().splitlines())==512
    with pytest.raises(FileExistsError):freeze_engineering(tmp_path,seed=20261105)


def test_readiness_is_sealed_and_missing_independent_catalog_fails(tmp_path):
    manifest=freeze_engineering(tmp_path)
    with pytest.raises(ValueError,match='sealed'):build_readiness([],manifest,None)
    receipt={'status':'FROZEN_ENGINEERING_PROMPT','engineering_data_sha256':manifest['data_sha256'],'prompt_packager_sha256':prompt_packager_hash()}
    with pytest.raises(ValueError,match='BLOCKED_DATA_GATE'):build_readiness([],manifest,receipt)
    receipt['prompt_packager_sha256']='corrupt'
    with pytest.raises(ValueError,match='changed'):build_readiness([],manifest,receipt)


def test_test_and_ood_are_not_available():
    for split in ('test','ood'):
        rows=build_engineering()
        for row in rows:row['split']=split
        with pytest.raises(ValueError,match='remain closed'):validate_records(rows)
