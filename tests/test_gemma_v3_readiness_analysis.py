import itertools
import numpy as np
import pytest
from scripts.analyze_gemma_v3_readiness import cluster_draws,threshold,response_diagnostics,MODELS,CONCEPTS,LANGUAGES


def test_whole_unequal_clusters_preserve_family_estimand_and_joint_models():
    panel=np.array([np.ones((2,2)),np.ones((2,2)),np.ones((2,2)),np.zeros((2,2))])
    meta=[{'concept':'negation','source_reference_cluster_id':'large' if i<3 else 'small'} for i in range(4)]
    draws,keys,sizes=cluster_draws(panel,meta,'negation','source_reference_cluster_id',1000)
    assert sizes==[3,1]
    assert set(draws[:,0,0])=={0.,.75,1.}
    assert np.array_equal(draws[:,0,0],draws[:,1,1])
    meta[-1]['concept']='temporal_order';meta[-1]['source_reference_cluster_id']='large'
    with pytest.raises(ValueError,match='Cross-concept'):cluster_draws(panel,meta,'negation','source_reference_cluster_id',100)


def test_original_threshold_is_not_relaxed():
    assert threshold(.75,.500001)
    assert not threshold(.75,.5)
    assert not threshold(.749999,.8)


def test_constant_answer_letter_detected_without_attributing_reasoning_mechanism():
    records=[];raw={m:{'rows':[]} for m in MODELS}
    for concept,state,lexical,code,language in itertools.product(CONCEPTS,(0,1),(0,1),(0,1),LANGUAGES):
        rid=f'{concept}/{state}/{lexical}/{code}/{language}';letters=('A','B') if code==0 else ('B','A')
        row=dict(id=rid,family_id=concept,concept=concept,semantic_state=state,lexical=lexical,answer_code=code,language=language,correct_index=0 if state else 1,completions=[f' {letters[0]}. True.',f' {letters[1]}. False.'])
        records.append(row)
        for model in MODELS:raw[model]['rows'].append({'id':rid,'scores':[-1.,-2.] if code==0 else [-2.,-1.]})
    result=response_diagnostics(records,raw)
    for model in MODELS:
        assert result[model]['overall']['accuracy']==.5
        assert result[model]['overall']['predicted_answer_code_frequencies']=={'A':1.,'B':0.}
        assert result[model]['answer_code_reversal']['same_output_letter_rate']==1.
        assert result[model]['answer_code_reversal']['semantic_prediction_consistency_rate']==0.
        assert result[model]['semantic_counterfactual']['prediction_flip_rate']==0.
