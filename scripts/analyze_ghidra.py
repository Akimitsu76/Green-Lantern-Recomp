"""Import the validated PE with explicit Xbox language and project-local settings."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from native_port.errors import PortError
from native_port.pe import inspect_pe
from native_port.tasks import Cancellation,run_process
from native_port.workspace import Workspace

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghidra',type=Path,default=Path.home()/'.local/opt/ghidra_12.1.4_PUBLIC')
    parser.add_argument('--reuse',action='store_true',help='Export an existing matching project without rerunning auto-analysis')
    parser.add_argument('--project-name')
    parser.add_argument('--inspect-address',action='append',default=[])
    args=parser.parse_args()
    work=Workspace(PROJECT/'.aster',PROJECT)
    try:
        pe=work.path('analysis/green-lantern/normalized.pe')
        raw=pe.read_bytes();info=inspect_pe(raw)
        name=args.project_name or 'Xex_'+hashlib.sha256(raw).hexdigest()[:12]
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name):
            raise PortError('PROJECT_NAME','Nome de projeto Ghidra inválido.')
        projects=PROJECT/'build/ghidra/projects';projects.mkdir(parents=True,exist_ok=True)
        if (projects/(name+'.gpr')).exists() and not args.reuse:
            raise PortError('PROJECT_EXISTS','Projeto já existe; use --reuse para exportar sem reanalisar.')
        env=dict(os.environ)
        for folder in ('config','settings','cache','temp'):
            work.path('ghidra/'+folder).mkdir(parents=True,exist_ok=True)
        env['XDG_CONFIG_HOME']=str(work.path('ghidra/config'))
        env['GHIDRA_HEADLESS_JAVA_OPTIONS']=' '.join(
            '-Dapplication.'+key+'='+str(work.path('ghidra/'+folder))
            for key,folder in [('settingsdir','settings'),('cachedir','cache'),('tempdir','temp')])
        summary=work.path('analysis/green-lantern/ghidra-analysis.json')
        output=work.path('analysis/green-lantern/selected-functions.json')
        argv=[args.ghidra/'support/analyzeHeadless',projects,name]
        argv+=['-process',pe.name,'-readOnly','-noanalysis'] if args.reuse else ['-import',pe,'-processor','PowerPC:BE:64:A2ALT-32addr']
        argv+=['-scriptPath',PROJECT/'scripts/ghidra','-postScript','ExportPortAnalysis.java',summary,hex(info['entry_point'])]
        selected=[hex(info['entry_point'])]+[hex(int(a,0)) for a in args.inspect_address]
        argv+=['-postScript','ExportSelectedFunctions.java',output]+selected
        argv+=['-analysisTimeoutPerFile','300','-max-cpu','4','-log',work.path('analysis/green-lantern/ghidra-run.log')]
        result=run_process(list(map(str,argv)),PROJECT,Cancellation(),timeout=450,env=env)
        exported=json.loads(summary.read_text())
        if exported['language']!='PowerPC:BE:64:A2ALT-32addr' or exported.get('input_md5')!=hashlib.md5(raw).hexdigest():
            raise PortError('GHIDRA_IDENTITY','Idioma/hash do programa Ghidra divergente da entrada.')
        report={'schema':1,'state':'static-analysis-exported','game_ready':False,
                'normalized_sha256':hashlib.sha256(raw).hexdigest(),'project':str(projects/name),
                'functions':exported['function_count'],'language':exported['language'],'process':result,
                'limitations':['Generic PE loader is incomplete for Xbox imports/exceptions/TLS/RTTI.']}
        work.write_json('reports/ghidra-run.json',report)
        print(json.dumps({k:v for k,v in report.items() if k!='process'},indent=2))
    except (PortError,OSError,ValueError,KeyError) as e:
        print(json.dumps(e.as_dict() if isinstance(e,PortError) else {'error':str(e)}),file=sys.stderr)
        raise SystemExit(2)
