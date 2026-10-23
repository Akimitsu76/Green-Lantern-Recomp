"""Build already-downloaded, reviewed local tooling; no install/system mutation."""
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from native_port.errors import PortError
from native_port.tasks import Cancellation,run_process
from native_port.workspace import Workspace
from native_port.xenon import XENON_COMMIT

if __name__=='__main__':
    work=Workspace(PROJECT/'.aster',PROJECT)
    logs=[]
    token=Cancellation()
    try:
        root=work.path('tools/XenonRecomp')
        def run(task,argv):
            r=run_process(list(map(str,argv)),PROJECT,token,timeout=300)
            logs.append(dict(task=task,**r))
            print(task, 'OK', f"{r['seconds']:.2f}s")
            return r
        if run('source revision',['git','-C',root,'rev-parse','HEAD'])['stdout'].strip()!=XENON_COMMIT:
            raise PortError('TOOL_REVISION','Checkout não corresponde à revisão revisada.')
        run('source unchanged',['git','-C',root,'diff','--exit-code'])
        submodules=run('submodule revisions',['git','-C',root,'submodule','status'])['stdout']
        if any(line.startswith(('-', '+', 'U')) for line in submodules.splitlines()):
            raise PortError('SUBMODULE_REVISION','Submódulos ausentes ou fora das revisões fixadas.')
        cmake=work.path('tools/cmake-runtime/cmake/data/bin/cmake')
        build=work.path('build/xenon')
        run('configure',[cmake,'-S',PROJECT/'integrations/xenonrecomp','-B',build,'-G','Ninja',
            '-DXENON_ROOT='+str(root),'-DCMAKE_C_COMPILER=clang','-DCMAKE_CXX_COMPILER=clang++',
            '-DCMAKE_BUILD_TYPE=RelWithDebInfo'])
        run('build',[cmake,'--build',build,'--target','aster-xex-inspect','aster-recompile-leaf',
                     'XenonAnalyse','XenonRecomp','-j','4'])
        work.write_json('reports/xenon-build.json',dict(schema=1,state='completed',game_ready=False,
                         xenon_commit=XENON_COMMIT,submodules=submodules,logs=logs))
    except PortError as e:
        work.write_json('reports/xenon-build.json',dict(schema=1,state='failed',error=e.as_dict(),logs=logs))
        print(json.dumps(e.as_dict(),ensure_ascii=False),file=sys.stderr)
        raise SystemExit(2)
