"""PM assigned-file invocation; never import decision/CLI or run other tests."""
from pathlib import Path
import socket
import sys
HERE=Path(__file__).resolve().parent
PKG=HERE.parents[2]/'implementation-worktree/packages/multi-workers'
sys.path.insert(0,str(PKG))
def deny(*args,**kwargs):
    raise AssertionError('PM verification denies network')
socket.socket.connect=deny
socket.socket.connect_ex=deny
socket.create_connection=deny
import decision_policy
from autopilot import config
import pytest
assert Path(decision_policy.__file__).resolve()==PKG/'decision_policy.py'
assert Path(config.__file__).resolve()==PKG/'autopilot/config.py'
print('PM actual imported paths:',decision_policy.__file__,config.__file__)
raise SystemExit(pytest.main(['-p','no:cacheprovider','-q',str(PKG/'test_dp_consolidation_recovery.py')]))
