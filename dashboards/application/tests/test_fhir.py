from copy import deepcopy
import pytest
from app.fhir import make_bundle


def sample():return {'id':'r1','patient_id':'p1','synthetic':True,'recorded_at':'2026-11-14T08:00:00+00:00','quality':'valid','calibration':'C1','metrics':{'contact_seconds':30,'thumb_pct':20,'palm_pct':None,'episodes':2}}


def test_fhir_subject_units_absence_and_synthetic_tag():
    bundle=make_bundle('p1',[sample()])
    observations=[e['resource'] for e in bundle['entry'][1:]]
    assert len({e['fullUrl'] for e in bundle['entry']})==5
    assert all(r['subject']['reference']==bundle['entry'][0]['fullUrl'] for r in observations)
    assert observations[2]['valueQuantity']['code']=='%'
    assert 'dataAbsentReason' in observations[3] and 'valueQuantity' not in observations[3]
    assert all(r['meta']['tag'][0]['code']=='synthetic-test' for r in observations)


@pytest.mark.parametrize('change',[{'patient_id':'other'},{'synthetic':False},{'metrics':{'thumb_pct':101}},{'metrics':{'contact_seconds':-1}}])
def test_fhir_rejects_wrong_subject_real_or_invalid_data(change):
    with pytest.raises(ValueError):make_bundle('p1',[{**sample(),**change}])
