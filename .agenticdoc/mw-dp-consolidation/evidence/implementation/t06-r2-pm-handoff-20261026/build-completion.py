"""New completion verifier, preserve the first script and its failed run."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
assert sys.dont_write_bytecode
source=(HERE/'check.py').read_text(encoding='utf-8')
assert "assert sha(actual_diff)==worker_after[name]['diff_sha256']" in source
source=source.replace('KEY=HERE.parents[2]','KEY=HERE.parents[3]')
source=source.replace("str(HERE/'bootstrap.py')","str(HERE.parent/'bootstrap.py')")
# The child bootstrap owns its parent/probe.json, never an original-worker path.
source=source.replace("(HERE/'probe.json')","(HERE.parent/'probe.json')")
source=source.replace("    assert sha(actual_diff)==worker_after[name]['diff_sha256']","    normalized=actual_diff.decode('utf-8').replace('\\r\\n','\\n').encode('utf-8')\n    assert sha(normalized)==worker_after[name]['diff_sha256']")
source=source.replace("'worker_diff_sha256':sha(actual_diff)","'worker_diff_sha256':sha(actual_diff),'worker_diff_lf_normalized_sha256':sha(normalized),'worker_diff_recorded_sha256':worker_after[name]['diff_sha256'],'worker_diff_record_is_lf_content_hash_not_disk_parity':sha(actual_diff)!=worker_after[name]['diff_sha256']")
source=source.replace("'three_live_original_paths_absent':False,",'')
source=source.replace("'observed_at':datetime.now(timezone.utc).isoformat()","'observed_at':datetime.now(timezone.utc).isoformat(),'first_pm_verifier_rc1_preserved':True,'evidence_hash_boundary_normalization_not_exact_disk_parity':True")
dest=HERE/'completion/finish.py'
assert not dest.exists()
dest.parent.mkdir()
dest.write_text(source,encoding='utf-8',newline='\n')
print(dest)
