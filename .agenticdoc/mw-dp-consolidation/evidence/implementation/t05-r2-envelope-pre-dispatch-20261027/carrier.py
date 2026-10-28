import hashlib,importlib.util,json,socket,sys
from datetime import datetime,timezone
from pathlib import Path
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];CARD=KEY/'tasks/isolated/T05-eight-cases-r2-envelope.md'
def deny(*args,**kwargs):raise AssertionError('PM face carrier probe forbids network')
socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.create_connection=deny
SOURCE=KEY/'evidence/implementation/dpc-t05-eight-cases/rework-r2/tools/diagnose_face.py';spec=importlib.util.spec_from_file_location('pm_readonly_face_diagnosis',SOURCE);assert spec and spec.loader;module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
text=CARD.read_text(encoding='utf-8');declared=module.frontmatter_entries(text);body=module.section_body(text,'写入允许面');extracted=module.dispatch._card_write_face_entries({'extras':[{'title':'写入允许面','body':body}]});assert declared==extracted and len(extracted)==12
rendered=module.dispatch.render_write_face_line(extracted);assert module.write_face._split_single_line(rendered.split(':',1)[1].strip())==extracted;parsed=module.write_face.parse_write_face(rendered,base=str(KEY.parents[1]),case_insensitive=sys.platform=='win32');assert isinstance(parsed,module.write_face.WriteFace) and len(parsed.allow_entries)==12
previous=module.previous_card_control();assert previous['extracted_entry_count']==12 and previous['head_is_the_extracted_list']
old_text=(KEY/'tasks/isolated/T05-eight-cases-r2.md').read_text(encoding='utf-8');old=module.dispatch._card_write_face_entries({'extras':[{'title':'写入允许面','body':module.section_body(old_text,'写入允许面')}]});assert len(old)==1
result={'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'card_sha256':hashlib.sha256(CARD.read_bytes()).hexdigest(),'new_declared_entries':declared,'new_extracted_entries':extracted,'rendered_header':rendered,'parsed_allow_entries':list(parsed.allow_entries),'new_12_entries_roundtrip':True,'original_T05_control':previous,'original_bad_R2_entries':old,'old_bad_card_not_modified':True,'readonly_module_loader_did_not_call_worker_main':True,'shipped_dispatch_extractor_renderer_parser_used':True,'module_comprehensive_source_audit':False,'inspection_scope':'PM fully read worker diagnosis utility and relevant shipped extractor/renderer functions, not the complete dispatcher/parser files'};(HERE/'carrier.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');print(json.dumps(result,ensure_ascii=False,indent=2))
