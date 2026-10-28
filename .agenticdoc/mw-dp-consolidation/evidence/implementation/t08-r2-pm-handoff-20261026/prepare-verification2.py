from pathlib import Path
import sys
assert sys.dont_write_bytecode
here=Path(__file__).resolve().parent
source=(here/'prepare-verification.py').read_text(encoding='utf-8')
prefix=source[:source.index('# Use the authoritative retired identity list')]
prefix=prefix.replace("str(p.RETIRED_DP_IDS[index-1]) if hasattr(p,'RETIRED_DP_IDS') else 'dp'+str(index)","p.RETIRED_DP_REGISTRY[index-1].id")
namespace={'__file__':str(here/'prepare-verification.py')}
exec(compile(prefix,str(here/'prepare-verification.py'),'exec'),namespace)
bootstrap=namespace['source'].replace(namespace['needle'],namespace['extra']+'\n'+namespace['needle'])
dest=here/'bootstrap.py';assert not dest.exists();dest.write_text(bootstrap,encoding='utf-8',newline='\n')
print('created evidence bootstrap; 39 independently asserted fixtures')
