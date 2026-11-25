import importlib.util
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).parents[1]
SPEC=importlib.util.spec_from_file_location('runtime_campaign',ROOT/'scripts/experiments/runtime_campaign.py')
campaign=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(campaign)


def test_campaign_preserves_failure_and_cleans_up_owned_profile(tmp_path,monkeypatch):
    operations=[]
    def control(command,operation,controller,**fields):
        operations.append(operation)
        return {'schema':'rig-lifecycle/1','ok':True,'operation':operation}
    def fail(*args,**kwargs):raise OSError('fixture provider unavailable')
    monkeypatch.setattr(campaign,'urlopen',fail)
    config={'schema':'benchmark-runtime-campaign/1','controller':'operator','runtime_command':['rig'],
            'cases':[{'id':'split','profile_id':'mine','spec':{'model':'m'},'gpu_ids':[0],
                      'prompt':'hi','endpoint':'http://localhost/v1','repeats':1}]}
    with pytest.raises(OSError): campaign.run(config,tmp_path/'out',control=control)
    assert operations==['controller.claim','profile.register','load','stop']
    receipt=json.loads((tmp_path/'out/receipt.json').read_text())
    assert receipt['state']=='failed' and receipt['finished_at']
    assert receipt['cases'][0]['telemetry'] is None


def test_managed_lease_refuses_missing_controller(monkeypatch):
    sys.path.insert(0,str(ROOT/'scripts/integration'))
    import managed_lease
    monkeypatch.delenv('BENCHMARK_CONTROLLER',raising=False)
    with pytest.raises(ValueError,match='CONTROLLER'):managed_lease.main(['acquire','0','owner','run'])


def test_search_campaign_uses_installed_provider(monkeypatch):
    import types
    sys.path.insert(0,str(ROOT/'scripts/experiments'))
    import search_provider_benchmark as search
    module=types.ModuleType('rig_search.duckduckgo')
    module.search=lambda query,limit:{'results':[{'url':'https://example.test'}],'rate_limit_signal':False}
    monkeypatch.setitem(sys.modules,'rig_search',types.ModuleType('rig_search'))
    monkeypatch.setitem(sys.modules,'rig_search.duckduckgo',module)
    assert search.ddg_search('test',1)[0]==[{'url':'https://example.test'}]
